from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import patch


SCRIPT = (
    Path(__file__).parents[2]
    / "skills"
    / "co-create-plan"
    / "scripts"
    / "planning_peer.py"
)
SPEC = importlib.util.spec_from_file_location("planning_peer", SCRIPT)
assert SPEC and SPEC.loader
planning_peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planning_peer)

VALID_PEER_RESPONSE = """## Position
Proceed with the bounded change.
## Agreements
The scope is clear.
## Challenges
None.
## Proposed plan changes
None.
## Open decisions
None.
## Vote
AGREE"""

VALID_BRIEF = """# Planning brief
## Objective
Plan a safe change.
## Requirements
- Preserve behavior.
## Constraints
- Planning only.
## In scope
- The requested change.
## Out of scope
- Unrequested features.
## Evidence and assumptions
- Repository evidence must be checked.
## Open decisions
- None.
## Acceptance signals
- The implementation checks pass."""


class PlanningPeerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.brief = self.root / "brief.md"
        self.brief.write_text("# Brief\nPlan a safe change.\n", encoding="utf-8")
        self.outdir = self.repo / ".ai-planning" / "safe-change"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _codex_start_result(self, command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text(VALID_PEER_RESPONSE + "\n", encoding="utf-8")
        return CompletedProcess(
            command,
            0,
            stdout='{"type":"thread.started","thread_id":"thread-123"}\n',
            stderr="",
        )

    def test_codex_start_is_read_only_and_records_exact_session(self) -> None:
        args = Namespace(
            peer="codex",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(
                planning_peer.subprocess,
                "run",
                side_effect=self._codex_start_result,
            ) as run,
        ):
            response = planning_peer.run_start(args)

        command = run.call_args.args[0]
        self.assertIn("--sandbox", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("mcp_servers={}", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 900)
        self.assertEqual(response, self.outdir / "round-01-peer.md")
        state = json.loads((self.outdir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["session_id"], "thread-123")
        self.assertEqual(state["round"], 1)

    def test_codex_reply_resumes_recorded_session_not_last(self) -> None:
        start_args = Namespace(
            peer="codex",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(
                planning_peer.subprocess,
                "run",
                side_effect=self._codex_start_result,
            ),
        ):
            planning_peer.run_start(start_args)

        message = self.outdir / "round-01-host.md"
        message.write_text("I addressed the migration risk.\n", encoding="utf-8")

        def reply_result(command, **kwargs):
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(VALID_PEER_RESPONSE + "\n", encoding="utf-8")
            return CompletedProcess(command, 0, stdout="{}\n", stderr="")

        reply_args = Namespace(
            state=str(self.outdir / "state.json"),
            message=str(message),
            cli=None,
            retry=False,
            timeout_seconds=None,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(
                planning_peer.subprocess, "run", side_effect=reply_result
            ) as run,
        ):
            planning_peer.run_reply(reply_args)

        command = run.call_args.args[0]
        self.assertIn("thread-123", command)
        self.assertNotIn("--last", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("sandbox_mode=\"read-only\"", command)
        self.assertIn("mcp_servers={}", command)
        state = json.loads((self.outdir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["round"], 2)

    def test_claude_start_uses_plan_permission_and_writes_result(self) -> None:
        args = Namespace(
            peer="claude",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        payload = json.dumps(
            {
                "session_id": "claude-session-1",
                "result": VALID_PEER_RESPONSE,
            }
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="claude"),
            patch.object(
                planning_peer.subprocess,
                "run",
                return_value=CompletedProcess([], 0, stdout=payload, stderr=""),
            ) as run,
        ):
            response = planning_peer.run_start(args)

        command = run.call_args.args[0]
        self.assertIn("--permission-mode", command)
        self.assertEqual(command[command.index("--permission-mode") + 1], "plan")
        self.assertIn("--safe-mode", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertEqual(command[command.index("--mcp-config") + 1], "{}")
        self.assertEqual(
            response.read_text(encoding="utf-8"), VALID_PEER_RESPONSE + "\n"
        )

    def test_existing_state_is_not_overwritten(self) -> None:
        self.outdir.mkdir(parents=True)
        (self.outdir / "state.json").write_text("{}", encoding="utf-8")
        args = Namespace(
            peer="codex",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        with self.assertRaises(planning_peer.PlanningPeerError):
            planning_peer.run_start(args)

    def test_timeout_preserves_partial_logs_without_creating_state(self) -> None:
        args = Namespace(
            peer="codex",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=3,
            max_rounds=3,
        )
        timeout = TimeoutExpired(
            cmd=["codex"],
            timeout=3,
            output='{"type":"thread.started","thread_id":"partial"}\n',
            stderr="network stalled",
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(
                planning_peer.subprocess, "run", side_effect=timeout
            ),
            self.assertRaises(planning_peer.PlanningPeerError),
        ):
            planning_peer.run_start(args)

        self.assertIn(
            '"thread_id":"partial"',
            (self.outdir / "round-01-peer-events.jsonl").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            (self.outdir / "round-01-peer-stderr.log").read_text(
                encoding="utf-8"
            ),
            "network stalled",
        )
        self.assertFalse((self.outdir / "state.json").exists())

    def test_codex_session_comes_only_from_thread_started_event(self) -> None:
        stdout = "\n".join(
            [
                '{"type":"item.completed","item":{"session_id":"wrong"}}',
                '{"type":"thread.started","thread_id":"right"}',
            ]
        )
        self.assertEqual(planning_peer._parse_codex_session(stdout), "right")

    def test_codex_session_missing_thread_started_is_rejected(self) -> None:
        stdout = '{"type":"item.completed","item":{"session_id":"wrong"}}'
        with self.assertRaises(planning_peer.PlanningPeerError):
            planning_peer._parse_codex_session(stdout)

    def test_non_utf8_brief_reports_planning_peer_error(self) -> None:
        self.brief.write_bytes(b"\x82\xff")
        with self.assertRaises(planning_peer.PlanningPeerError):
            planning_peer._read_text(self.brief, "planning brief")

    def test_claude_reply_requires_same_session(self) -> None:
        start_args = Namespace(
            peer="claude",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        start_payload = json.dumps(
            {"session_id": "claude-session-1", "result": VALID_PEER_RESPONSE}
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="claude"),
            patch.object(
                planning_peer.subprocess,
                "run",
                return_value=CompletedProcess(
                    [], 0, stdout=start_payload, stderr=""
                ),
            ),
        ):
            planning_peer.run_start(start_args)

        message = self.outdir / "round-01-host.md"
        message.write_text("Address the blocker.\n", encoding="utf-8")
        mismatch_payload = json.dumps(
            {"session_id": "different-session", "result": VALID_PEER_RESPONSE}
        )
        reply_args = Namespace(
            state=str(self.outdir / "state.json"),
            message=str(message),
            cli=None,
            retry=False,
            timeout_seconds=None,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="claude"),
            patch.object(
                planning_peer.subprocess,
                "run",
                return_value=CompletedProcess(
                    [], 0, stdout=mismatch_payload, stderr=""
                ),
            ) as run,
            self.assertRaises(planning_peer.PlanningPeerError),
        ):
            planning_peer.run_reply(reply_args)

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--resume") + 1], "claude-session-1")
        state = json.loads((self.outdir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["round"], 1)

    def test_claude_reply_writes_result_and_advances_state(self) -> None:
        start_args = Namespace(
            peer="claude",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        start_payload = json.dumps(
            {"session_id": "claude-session-1", "result": VALID_PEER_RESPONSE}
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="claude"),
            patch.object(
                planning_peer.subprocess,
                "run",
                return_value=CompletedProcess(
                    [], 0, stdout=start_payload, stderr=""
                ),
            ),
        ):
            planning_peer.run_start(start_args)

        message = self.outdir / "round-01-host.md"
        message.write_text("Address the blocker.\n", encoding="utf-8")
        reply_payload = json.dumps(
            {"session_id": "claude-session-1", "result": VALID_PEER_RESPONSE}
        )
        reply_args = Namespace(
            state=str(self.outdir / "state.json"),
            message=str(message),
            cli=None,
            retry=False,
            timeout_seconds=None,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="claude"),
            patch.object(
                planning_peer.subprocess,
                "run",
                return_value=CompletedProcess(
                    [], 0, stdout=reply_payload, stderr=""
                ),
            ),
        ):
            response = planning_peer.run_reply(reply_args)

        self.assertEqual(
            response.read_text(encoding="utf-8"), VALID_PEER_RESPONSE + "\n"
        )
        state = json.loads((self.outdir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["round"], 2)

    def test_failed_reply_can_be_retried_without_losing_artifacts(self) -> None:
        start_args = Namespace(
            peer="codex",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(
                planning_peer.subprocess,
                "run",
                side_effect=self._codex_start_result,
            ),
        ):
            planning_peer.run_start(start_args)

        message = self.outdir / "round-01-host.md"
        message.write_text("Retry this turn safely.\n", encoding="utf-8")
        failed = CompletedProcess([], 1, stdout="partial", stderr="network failed")
        first_reply = Namespace(
            state=str(self.outdir / "state.json"),
            message=str(message),
            cli=None,
            retry=False,
            timeout_seconds=None,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(planning_peer.subprocess, "run", return_value=failed),
            self.assertRaises(planning_peer.PlanningPeerError),
        ):
            planning_peer.run_reply(first_reply)

        def successful_retry(command, **kwargs):
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(VALID_PEER_RESPONSE + "\n", encoding="utf-8")
            return CompletedProcess(command, 0, stdout="{}\n", stderr="")

        retry_reply = Namespace(
            state=str(self.outdir / "state.json"),
            message=str(message),
            cli=None,
            retry=True,
            timeout_seconds=None,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(
                planning_peer.subprocess, "run", side_effect=successful_retry
            ),
        ):
            planning_peer.run_reply(retry_reply)

        failed_dir = self.outdir / "failed-attempts" / "round-02-attempt-01"
        self.assertTrue((failed_dir / "round-02-peer-events.jsonl").is_file())
        self.assertTrue((failed_dir / "round-02-peer-stderr.log").is_file())
        state = json.loads((self.outdir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["round"], 2)

    def test_failed_start_requires_retry_and_archives_artifacts(self) -> None:
        args = Namespace(
            peer="codex",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        failed = CompletedProcess([], 1, stdout="partial", stderr="network failed")
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(planning_peer.subprocess, "run", return_value=failed),
            self.assertRaises(planning_peer.PlanningPeerError),
        ):
            planning_peer.run_start(args)

        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            self.assertRaises(planning_peer.PlanningPeerError),
        ):
            planning_peer.run_start(args)

        args.retry = True
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(
                planning_peer.subprocess,
                "run",
                side_effect=self._codex_start_result,
            ),
        ):
            planning_peer.run_start(args)

        failed_dir = self.outdir / "failed-attempts" / "round-01-attempt-01"
        self.assertTrue((failed_dir / "round-01-peer-events.jsonl").is_file())
        self.assertTrue((self.outdir / "state.json").is_file())

    def test_max_rounds_is_enforced(self) -> None:
        self.outdir.mkdir(parents=True)
        state = {
            "version": planning_peer.STATE_VERSION,
            "peer": "codex",
            "peer_cli": "codex",
            "model": None,
            "repo": str(self.repo),
            "brief": str(self.brief),
            "outdir": str(self.outdir),
            "session_id": "thread-123",
            "timeout_seconds": 900,
            "max_rounds": 2,
            "round": 2,
            "turns": [],
        }
        state_path = self.outdir / "state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        message = self.outdir / "round-02-host.md"
        message.write_text("One more turn.\n", encoding="utf-8")
        args = Namespace(
            state=str(state_path),
            message=str(message),
            cli=None,
            retry=False,
            timeout_seconds=None,
        )
        with self.assertRaises(planning_peer.PlanningPeerError):
            planning_peer.run_reply(args)

    def test_parser_defaults_cover_timeout_rounds_and_retry(self) -> None:
        args = planning_peer.build_parser().parse_args(
            [
                "start",
                "--peer",
                "codex",
                "--repo",
                str(self.repo),
                "--brief",
                str(self.brief),
                "--outdir",
                str(self.outdir),
            ]
        )
        self.assertEqual(args.timeout_seconds, 900)
        self.assertEqual(args.max_rounds, 3)
        self.assertFalse(args.retry)

    def test_missing_cli_is_reported(self) -> None:
        with (
            patch.object(planning_peer.shutil, "which", return_value=None),
            self.assertRaises(planning_peer.PlanningPeerError),
        ):
            planning_peer._resolve_cli("codex", "definitely-missing-codex")

    def test_reply_rejects_zero_timeout(self) -> None:
        self.outdir.mkdir(parents=True)
        state = {
            "version": planning_peer.STATE_VERSION,
            "peer": "codex",
            "peer_cli": "codex",
            "model": None,
            "repo": str(self.repo),
            "brief": str(self.brief),
            "outdir": str(self.outdir),
            "session_id": "thread-123",
            "timeout_seconds": 900,
            "max_rounds": 3,
            "round": 1,
            "turns": [],
        }
        state_path = self.outdir / "state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        message = self.outdir / "round-01-host.md"
        message.write_text("Continue.\n", encoding="utf-8")
        args = Namespace(
            state=str(state_path),
            message=str(message),
            cli=None,
            retry=False,
            timeout_seconds=0,
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            self.assertRaises(planning_peer.PlanningPeerError),
        ):
            planning_peer.run_reply(args)

    def test_openai_yaml_is_utf8(self) -> None:
        path = (
            Path(__file__).parents[2]
            / "skills"
            / "co-create-plan"
            / "agents"
            / "openai.yaml"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("Co-create Plan", text)

    def test_start_rejects_outdir_outside_repo_planning_root(self) -> None:
        args = Namespace(
            peer="codex",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.root / "outside"),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )
        with self.assertRaisesRegex(
            planning_peer.PlanningPeerError, r"\.ai-planning"
        ):
            planning_peer.run_start(args)
        self.assertFalse((self.root / "outside").exists())

    def test_reply_rejects_state_outside_repo_planning_root(self) -> None:
        unsafe_outdir = self.repo / "product-config"
        unsafe_outdir.mkdir()
        state = {
            "version": planning_peer.STATE_VERSION,
            "peer": "codex",
            "peer_cli": "codex",
            "model": None,
            "repo": str(self.repo),
            "brief": str(self.brief),
            "outdir": str(unsafe_outdir),
            "session_id": "thread-123",
            "timeout_seconds": 900,
            "max_rounds": 3,
            "round": 1,
            "turns": [],
        }
        state_path = unsafe_outdir / "state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        message = unsafe_outdir / "round-01-host.md"
        message.write_text("Continue.\n", encoding="utf-8")
        args = Namespace(
            state=str(state_path),
            message=str(message),
            cli=None,
            retry=False,
            timeout_seconds=None,
        )
        with self.assertRaisesRegex(
            planning_peer.PlanningPeerError, r"\.ai-planning"
        ):
            planning_peer.run_reply(args)

    def test_malformed_peer_response_does_not_create_state(self) -> None:
        args = Namespace(
            peer="codex",
            repo=str(self.repo),
            brief=str(self.brief),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
            max_rounds=3,
        )

        def malformed_result(command, **kwargs):
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text("A response without the protocol.\n", encoding="utf-8")
            return CompletedProcess(
                command,
                0,
                stdout='{"type":"thread.started","thread_id":"thread-123"}\n',
                stderr="",
            )

        with (
            patch.object(planning_peer, "_resolve_cli", return_value="codex"),
            patch.object(
                planning_peer.subprocess, "run", side_effect=malformed_result
            ),
            self.assertRaisesRegex(
                planning_peer.PlanningPeerError, "required sections"
            ),
        ):
            planning_peer.run_start(args)

        self.assertFalse((self.outdir / "state.json").exists())
        self.assertEqual(
            (self.outdir / "round-01-peer.md").read_text(encoding="utf-8"),
            "A response without the protocol.\n",
        )

    def test_claude_brief_generates_structured_requirements_without_state(self) -> None:
        request = self.outdir / "request.md"
        self.outdir.mkdir(parents=True)
        request.write_text("Add a safe feature.\n", encoding="utf-8")
        args = Namespace(
            repo=str(self.repo),
            request=str(request),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
        )
        payload = json.dumps({"result": VALID_BRIEF})
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="claude"),
            patch.object(
                planning_peer.subprocess,
                "run",
                return_value=CompletedProcess([], 0, stdout=payload, stderr=""),
            ) as run,
        ):
            response = planning_peer.run_brief(args)

        self.assertEqual(response, self.outdir / "requirements.md")
        self.assertEqual(response.read_text(encoding="utf-8"), VALID_BRIEF + "\n")
        self.assertFalse((self.outdir / "state.json").exists())
        prompt = run.call_args.kwargs["input"]
        self.assertIn("## Objective", prompt)
        self.assertIn("## Requirements", prompt)
        self.assertIn("## Constraints", prompt)

    def test_failed_claude_brief_can_be_retried_without_losing_artifacts(
        self,
    ) -> None:
        request = self.outdir / "request.md"
        self.outdir.mkdir(parents=True)
        request.write_text("Add a safe feature.\n", encoding="utf-8")
        args = Namespace(
            repo=str(self.repo),
            request=str(request),
            outdir=str(self.outdir),
            model=None,
            cli=None,
            retry=False,
            timeout_seconds=900,
        )
        failed = CompletedProcess([], 1, stdout="partial", stderr="network failed")
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="claude"),
            patch.object(planning_peer.subprocess, "run", return_value=failed),
            self.assertRaises(planning_peer.PlanningPeerError),
        ):
            planning_peer.run_brief(args)

        args.retry = True
        payload = json.dumps(
            {"session_id": "brief-session", "result": VALID_BRIEF}
        )
        with (
            patch.object(planning_peer, "_resolve_cli", return_value="claude"),
            patch.object(
                planning_peer.subprocess,
                "run",
                return_value=CompletedProcess([], 0, stdout=payload, stderr=""),
            ),
        ):
            planning_peer.run_brief(args)

        failed_dir = (
            self.outdir
            / "failed-attempts"
            / "requirements-attempt-01"
        )
        self.assertTrue((failed_dir / "requirements-events.json").is_file())
        self.assertTrue((failed_dir / "requirements-stderr.log").is_file())
        self.assertEqual(
            (self.outdir / "requirements.md").read_text(encoding="utf-8"),
            VALID_BRIEF + "\n",
        )

    def test_parser_supports_claude_brief_command(self) -> None:
        args = planning_peer.build_parser().parse_args(
            [
                "brief",
                "--repo",
                str(self.repo),
                "--request",
                str(self.brief),
                "--outdir",
                str(self.outdir),
            ]
        )
        self.assertEqual(args.command, "brief")
        self.assertEqual(args.timeout_seconds, 900)
        self.assertFalse(args.retry)


if __name__ == "__main__":
    unittest.main()
