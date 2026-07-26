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
        output.write_text("## Vote\nAGREE_WITH_CHANGES\n", encoding="utf-8")
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
            output.write_text("## Vote\nAGREE\n", encoding="utf-8")
            return CompletedProcess(command, 0, stdout="{}\n", stderr="")

        reply_args = Namespace(
            state=str(self.outdir / "state.json"),
            message=str(message),
            cli=None,
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
        )
        payload = json.dumps(
            {
                "session_id": "claude-session-1",
                "result": "## Vote\nBLOCK",
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
        self.assertEqual(response.read_text(encoding="utf-8"), "## Vote\nBLOCK\n")

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
            timeout_seconds=3,
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


if __name__ == "__main__":
    unittest.main()
