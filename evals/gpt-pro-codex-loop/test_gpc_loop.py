"""Tests for GPT Pro Codex Loop controller run initialization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "gpt-pro-codex-loop"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

import gpc_loop_controller as controller  # noqa: E402
import gpc_loop as cli  # noqa: E402


def write_raw_envelope(
    path: Path,
    expected: dict[str, object],
    payload: dict[str, object],
) -> dict[str, object]:
    envelope = {**expected, "payload": payload}
    path.write_text(
        "```json\n" + json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n```\n",
        encoding="utf-8",
    )
    return envelope


def valid_requirements(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "requirements_revision": 1,
        "supersedes_digest": None,
        "change_reason": "Initial requirements.",
        "behavior_changed": False,
        "user_approval_required": False,
        "user_approval_received": False,
        "scope_changed": False,
        "public_contract_changed": False,
        "prior_evidence_invalidated": False,
        "review_round_reset": False,
        "decision": "PLAN_READY",
        "objective": "Implement deterministic behavior.",
        "requirements": [{"id": "REQ-1", "statement": "Behavior is deterministic."}],
        "in_scope": ["example.py"],
        "out_of_scope": ["deployment"],
        "constraints": ["standard library"],
        "acceptance_criteria": [{
            "id": "AC-1",
            "criterion": "The focused test passes.",
            "required_evidence": "Focused unittest output.",
        }],
        "design_direction": ["Keep the implementation small."],
        "risk_items": [{
            "id": "RISK-1",
            "risk": "Evidence may be incomplete.",
            "required_mitigation": "Require AC-1 evidence.",
        }],
        "verification_strategy": ["Run the focused unittest."],
        "open_questions": [],
    }
    value.update(overrides)
    return value


class ControllerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name) / "repo"
        self.repository.mkdir()
        subprocess.run(["git", "init"], cwd=self.repository, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "controller@example.invalid"],
            cwd=self.repository,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Controller Test"],
            cwd=self.repository,
            check=True,
        )
        subprocess.run(
            ["git", "config", "core.autocrlf", "false"],
            cwd=self.repository,
            check=True,
        )
        (self.repository / "README.md").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.repository, check=True)
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=self.repository,
            check=True,
            capture_output=True,
        )
        self.input_directory = Path(self.temporary.name) / "controller-inputs"
        self.input_directory.mkdir()
        self.request = self.input_directory / "request.txt"
        self.context = self.input_directory / "context.txt"
        self.request.write_text("Add deterministic behavior.\n", encoding="utf-8")
        self.context.write_text("The repository uses Python.\n", encoding="utf-8")

    def _init_run(self) -> dict[str, object]:
        return controller.initialize_run(
            self.repository,
            "controller-test",
            self.request,
            self.context,
            [],
            "PRO_CLASS",
            None,
        )

    def _run_dir(self) -> Path:
        return self.repository / ".ai-pro-loop" / "controller-test"

    def _state(self) -> dict[str, object]:
        return controller.load_json(self._run_dir() / "state.json")

    def _state_bytes(self) -> bytes:
        return (self._run_dir() / "state.json").read_bytes()

    def _freeze_initial_requirements(
        self, requirements: dict[str, object] | None = None
    ) -> dict[str, object]:
        self._init_run()
        attempt = controller.prepare_requirements(self.repository, "controller-test")
        expected = controller.load_json(Path(attempt["expected_header_path"]))
        raw = self.input_directory / "requirements.raw.md"
        write_raw_envelope(raw, expected, requirements or valid_requirements())
        return controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            "https://chatgpt.com/c/controller-test",
            "Pro",
        )

    def _write_local_evidence(
        self, intents: dict[str, str], **overrides: object
    ) -> Path:
        path = self.input_directory / "local-evidence.json"
        value: dict[str, object] = {
            "schema_version": 1,
            "changed_file_intents": intents,
            "intent_summary": "Implement AC-1.",
            "acceptance_evidence": {"AC-1": ["Focused unittest passed."]},
            "test_commands": [
                {
                    "command": "python -m unittest test_example.py -v",
                    "outcome": "PASS",
                    "output_summary": "1 test passed.",
                }
            ],
            "diff_evidence": ["example.py implements AC-1."],
            "omissions": [],
            "unresolved_risks_or_blockers": [],
        }
        value.update(overrides)
        path.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def _build_valid_report(self, **evidence_overrides: object) -> dict[str, object]:
        self._freeze_initial_requirements()
        (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
        evidence = self._write_local_evidence(
            {"example.py": "Implement AC-1."}, **evidence_overrides
        )
        return controller.build_report(self.repository, "controller-test", evidence)

    def _active_report(self) -> dict[str, object]:
        return controller.load_json(self._run_dir() / "implementation-report.json")

    def _valid_pass_review(self) -> dict[str, object]:
        report = self._active_report()
        return {
            "schema_version": 1,
            "requirements_digest": self._state()["active_requirements_digest"],
            "reviewed_snapshot_digest": report["snapshot_digest"],
            "decision": "PASS",
            "acceptance_results": {
                "AC-1": {"status": "PASS", "evidence": "Focused unittest passed."}
            },
            "findings": [],
            "scope_violations": [],
            "next_instruction": "Run final verification.",
        }

    def _valid_changes_review(
        self, action: str, category: str, root_cause_key: str
    ) -> dict[str, object]:
        review = self._valid_pass_review()
        review.update(
            decision="CHANGES_REQUESTED",
            acceptance_results={
                "AC-1": {"status": "FAIL", "evidence": "The behavior is incomplete."}
            },
            findings=[
                {
                    "id": "F-1",
                    "acceptance_id": "AC-1",
                    "root_cause_key": root_cause_key,
                    "severity": "HIGH",
                    "category": category,
                    "required_action": action,
                    "evidence": "The behavior is incomplete.",
                    **(
                        {"required_evidence": "Supply the requested proof."}
                        if action == "PROVIDE_EVIDENCE"
                        else {"required_change": "Implement the missing AC-1 behavior."}
                        if action in {"CODE_CHANGE", "TEST_CHANGE"}
                        else {}
                    ),
                }
            ],
            next_instruction="Apply the routed correction.",
        )
        return review

    def _prepare_valid_review(self, **evidence_overrides: object) -> dict[str, object]:
        self._build_valid_report(**evidence_overrides)
        return controller.prepare_review(self.repository, "controller-test")

    def _write_review_response(
        self, attempt: dict[str, object], payload: dict[str, object]
    ) -> Path:
        expected = controller.load_json(Path(attempt["expected_header_path"]))
        raw = self.input_directory / "review.raw.md"
        write_raw_envelope(raw, expected, payload)
        return raw

    def _accept_pass_review(self, **evidence_overrides: object) -> dict[str, object]:
        attempt = self._prepare_valid_review(**evidence_overrides)
        raw = self._write_review_response(attempt, self._valid_pass_review())
        return controller.accept_review(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )

    def _accept_evidence_request(self) -> dict[str, object]:
        attempt = self._prepare_valid_review()
        review = self._valid_changes_review(
            "PROVIDE_EVIDENCE", "INSUFFICIENT_EVIDENCE", "missing-focused-output"
        )
        raw = self._write_review_response(attempt, review)
        result = controller.accept_review(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
        self.assertEqual(result["phase"], "LOCAL_VERIFICATION")
        return result

    def _prepare_supplemental_review(self) -> dict[str, object]:
        self._accept_evidence_request()
        supplemental = self.input_directory / "supplemental.txt"
        supplemental.write_text("Focused output: 1 test passed.\n", encoding="utf-8")
        return controller.prepare_review(
            self.repository, "controller-test", supplemental
        )

    def _seed_evidence_only_route(self) -> dict[str, object]:
        self._build_valid_report()
        state = self._state()
        review: dict[str, object] = {
            "schema_version": 1,
            "requirements_digest": state["active_requirements_digest"],
            "reviewed_snapshot_digest": state["current_snapshot_digest"],
            "decision": "CHANGES_REQUESTED",
            "acceptance_results": {
                "AC-1": {
                    "status": "UNVERIFIED",
                    "evidence": "Focused output is missing exact detail.",
                }
            },
            "findings": [
                {
                    "id": "F-EVIDENCE",
                    "acceptance_id": "AC-1",
                    "root_cause_key": "missing-focused-output",
                    "severity": "MEDIUM",
                    "category": "INSUFFICIENT_EVIDENCE",
                    "required_action": "PROVIDE_EVIDENCE",
                    "evidence": "The report summarizes but does not quote the focused output.",
                    "required_evidence": "Attach the exact focused output summary.",
                }
            ],
            "scope_violations": [],
            "next_instruction": "Provide only the requested evidence.",
        }
        requirements = controller.load_json(self._run_dir() / "requirements.json")
        report = controller.load_json(self._run_dir() / "implementation-report.json")
        self.assertEqual(controller.validate_packet.validate_review(review, requirements, report), [])
        finding = review["findings"][0]
        self.assertIsInstance(finding, dict)
        state.update(
            phase="LOCAL_VERIFICATION",
            review_round=1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["PROVIDE_EVIDENCE"],
            unresolved_finding_ids=["F-EVIDENCE"],
            blocker_fingerprints=sorted(
                {
                    controller.validate_packet.derive_root_cause_fingerprint(finding),
                    controller.validate_packet.derive_root_cause_route_fingerprint(finding),
                }
            ),
            active_review_packet_digest=controller.validate_packet.canonical_digest(review),
            reviewed_snapshot_digest=state["current_snapshot_digest"],
            last_consumed_packet_digest="sha256:" + "e" * 64,
            last_consumed_review_envelope_digest="sha256:" + "e" * 64,
        )
        controller.write_json_atomic(self._run_dir() / "review.json", review)
        controller.write_json_atomic(self._run_dir() / "state.json", state)
        return review

    def _seed_requirements_revision_pending(self) -> None:
        state = self._state()
        state.update(
            phase="REQUIREMENTS_PENDING",
            latest_decision="CHANGES_REQUESTED",
            latest_requirements_decision=None,
            required_actions=["REQUIREMENTS_REVISION"],
            pending_requirements_envelope_digest=None,
            pending_review_envelope_digest=None,
        )
        controller.write_json_atomic(self._run_dir() / "state.json", state)

    def _write_conflict(self) -> Path:
        path = self.repository / "conflict.txt"
        path.write_text(
            "Repository evidence requires a material behavior revision.\n",
            encoding="utf-8",
        )
        return path

    def _prepare_raw_requirements(
        self, payload: dict[str, object], name: str = "requirements.raw.md"
    ) -> tuple[dict[str, object], Path]:
        attempt = controller.prepare_requirements(
            self.repository,
            "controller-test",
            conflict_evidence_path=(
                self._write_conflict()
                if payload.get("requirements_revision") != 1
                else None
            ),
        )
        expected = controller.load_json(Path(attempt["expected_header_path"]))
        raw = self.input_directory / name
        write_raw_envelope(raw, expected, payload)
        return expected, raw

    def test_resolve_run_rejects_traversal_and_separator_slugs(self) -> None:
        for slug in ("../escape", r"a\b", "a/b", ".", "..", "a\nb"):
            with self.subTest(slug=slug):
                with self.assertRaisesRegex(controller.ControllerError, "task slug"):
                    controller.resolve_run(self.repository, slug)

    def test_init_creates_valid_unbound_requirements_pending_state(self) -> None:
        result = self._init_run()
        run = self._run_dir()
        state = controller.load_json(run / "state.json")
        self.assertEqual(result["phase"], "REQUIREMENTS_PENDING")
        self.assertEqual(state["phase"], "REQUIREMENTS_PENDING")
        self.assertEqual(state["conversation_binding_state"], "CONVERSATION_UNBOUND")
        self.assertIsNone(state["bound_conversation_url"])
        self.assertIsNone(state["visible_model_label"])
        self.assertEqual(state["approved_existing_paths"], [])

    def test_init_refuses_existing_run_and_unapproved_dirty_baseline(self) -> None:
        self._init_run()
        with self.assertRaisesRegex(controller.ControllerError, "already exists"):
            self._init_run()

        (self.repository / "new-product.py").write_text("value = 1\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.ControllerError, "unapproved pre-existing"):
            controller.initialize_run(
                self.repository, "dirty-test", self.request, self.context, [], "PRO_CLASS", None
            )

    def test_status_is_read_only_and_reports_lock_and_orphan_transaction(self) -> None:
        self._init_run()
        paths = controller.resolve_run(self.repository, "controller-test")
        original = paths.state.read_bytes()
        paths.lock.write_text('{"pid":999999}\n', encoding="utf-8")
        (paths.transactions / "orphan").mkdir(parents=True)
        status = controller.status_run(self.repository, "controller-test")
        self.assertTrue(status["lock_present"])
        self.assertEqual(status["orphan_transactions"], ["orphan"])
        self.assertEqual(status["next_commands"], ["prepare-requirements"])
        self.assertEqual(paths.state.read_bytes(), original)

    def test_cli_status_prints_one_canonical_json_object(self) -> None:
        self._init_run()

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "gpc_loop.py"),
                "status",
                "--repo",
                str(self.repository),
                "--task",
                "controller-test",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0)
        value = json.loads(completed.stdout)
        self.assertEqual(value["ok"], True)
        self.assertEqual(value["command"], "status")
        self.assertEqual(completed.stderr, "")

    def test_cli_expected_error_is_json_and_exit_two(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "gpc_loop.py"),
                "status",
                "--repo",
                str(self.repository),
                "--task",
                "missing",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        error = json.loads(completed.stdout)["error"]
        self.assertEqual(error["code"], "RUN_NOT_FOUND")
        self.assertNotIn("Traceback", completed.stdout)

    def test_cli_help_covers_each_command_and_its_special_arguments(self) -> None:
        expected_arguments = {
            "init": [
                "--request",
                "--repository-context",
                "--approved-existing-path",
                "--model-policy",
                "--requested-model-label",
            ],
            "prepare-requirements": ["--conflict-evidence"],
            "accept-requirements": [
                "--raw-response",
                "--observed-conversation-url",
                "--observed-model-label",
            ],
            "approve-requirements": ["--approval-evidence"],
            "build-report": ["--local-evidence"],
            "prepare-review": ["--supplemental-evidence"],
            "accept-review": [
                "--raw-response",
                "--observed-conversation-url",
                "--observed-model-label",
            ],
            "final-verify": [],
            "status": [],
            "abandon-attempt": ["--send-status", "--not-sent-evidence"],
        }

        root_help = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "gpc_loop.py"), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(root_help.returncode, 0)
        for command, arguments in expected_arguments.items():
            with self.subTest(command=command):
                self.assertIn(command, root_help.stdout)
                completed = subprocess.run(
                    [sys.executable, str(SCRIPT_DIR / "gpc_loop.py"), command, "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0)
                self.assertIn("--repo", completed.stdout)
                self.assertIn("--task", completed.stdout)
                for argument in arguments:
                    self.assertIn(argument, completed.stdout)

    def test_cli_rejects_each_missing_required_command_argument(self) -> None:
        required_arguments = {
            "init": [
                ("--request", "request.md"),
                ("--repository-context", "context.md"),
                ("--model-policy", "PRO_CLASS"),
            ],
            "accept-requirements": [
                ("--raw-response", "response.md"),
                ("--observed-conversation-url", "https://chatgpt.com/c/example"),
                ("--observed-model-label", "Pro"),
            ],
            "approve-requirements": [("--approval-evidence", "approval.txt")],
            "build-report": [("--local-evidence", "evidence.json")],
            "accept-review": [
                ("--raw-response", "response.md"),
                ("--observed-conversation-url", "https://chatgpt.com/c/example"),
                ("--observed-model-label", "Pro"),
            ],
            "abandon-attempt": [
                ("--send-status", "NOT_SENT"),
                ("--not-sent-evidence", "not-sent.txt"),
            ],
        }
        for command, arguments in required_arguments.items():
            complete = [
                sys.executable,
                str(SCRIPT_DIR / "gpc_loop.py"),
                command,
                "--repo",
                str(self.repository),
                "--task",
                "controller-test",
            ]
            for option, value in arguments:
                complete.extend((option, value))
            for option, value in arguments:
                with self.subTest(command=command, option=option):
                    missing = list(complete)
                    missing.remove(option)
                    missing.remove(value)
                    completed = subprocess.run(
                        missing,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(completed.returncode, 2)
                    error = json.loads(completed.stdout)["error"]
                    self.assertEqual(error["code"], "ARGUMENT_ERROR")
                    self.assertEqual(completed.stderr, "")

    def test_cli_writes_canonical_utf8_bytes_with_one_lf(self) -> None:
        script = (
            "import sys; "
            f"sys.path.insert(0, {str(SCRIPT_DIR)!r}); "
            "import gpc_loop as cli; "
            "cli._dispatch = lambda args: {'label': '東京🍣'}; "
            "raise SystemExit(cli.main(['status', '--repo', '.', '--task', 'controller-test']))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script], check=False, capture_output=True
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            completed.stdout,
            b'{"command":"status","ok":true,"result":{"label":"\xe6\x9d\xb1\xe4\xba\xac\xf0\x9f\x8d\xa3"}}\n',
        )
        self.assertNotIn(b"\r", completed.stdout)
        self.assertEqual(completed.stderr, b"")

    def test_cli_parse_errors_do_not_echo_non_command_inputs(self) -> None:
        unsafe_values = [
            "https://chatgpt.com/c/private",
            str(self.repository / "private evidence.txt"),
            "Pro Experimental",
            "not-sent-evidence.txt",
        ]
        for value in unsafe_values:
            with self.subTest(value=value):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT_DIR / "gpc_loop.py"),
                        "--unknown-option",
                        value,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 2)
                payload = json.loads(completed.stdout)
                self.assertIsNone(payload["command"])
                self.assertNotIn(value, completed.stdout)

    def test_cli_rejects_missing_common_and_command_arguments(self) -> None:
        required_arguments = {
            "init": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
                ("--request", "request.md"),
                ("--repository-context", "context.md"),
                ("--model-policy", "PRO_CLASS"),
            ],
            "prepare-requirements": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
            ],
            "accept-requirements": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
                ("--raw-response", "response.md"),
                ("--observed-conversation-url", "https://chatgpt.com/c/example"),
                ("--observed-model-label", "Pro"),
            ],
            "approve-requirements": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
                ("--approval-evidence", "approval.txt"),
            ],
            "build-report": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
                ("--local-evidence", "evidence.json"),
            ],
            "prepare-review": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
            ],
            "accept-review": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
                ("--raw-response", "response.md"),
                ("--observed-conversation-url", "https://chatgpt.com/c/example"),
                ("--observed-model-label", "Pro"),
            ],
            "final-verify": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
            ],
            "status": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
            ],
            "abandon-attempt": [
                ("--repo", str(self.repository)),
                ("--task", "controller-test"),
                ("--send-status", "NOT_SENT"),
                ("--not-sent-evidence", "not-sent.txt"),
            ],
        }
        for command, arguments in required_arguments.items():
            complete = [sys.executable, str(SCRIPT_DIR / "gpc_loop.py"), command]
            for option, value in arguments:
                complete.extend((option, value))
            for option, value in arguments:
                with self.subTest(command=command, option=option):
                    missing = list(complete)
                    missing.remove(option)
                    missing.remove(value)
                    completed = subprocess.run(
                        missing, check=False, capture_output=True, text=True
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertEqual(json.loads(completed.stdout)["command"], command)

    def test_cli_dispatches_each_command_with_parsed_values(self) -> None:
        request = Path("request.md")
        context = Path("context.md")
        response = Path("response.md")
        evidence = Path("evidence.txt")
        cases = [
            (
                "initialize_run",
                [
                    "init", "--repo", ".", "--task", "run", "--request", str(request),
                    "--repository-context", str(context), "--approved-existing-path", "old.py",
                    "--approved-existing-path", "legacy.py", "--model-policy", "EXACT_LABEL",
                    "--requested-model-label", "Pro",
                ],
                (Path("."), "run", request, context, ["old.py", "legacy.py"], "EXACT_LABEL", "Pro"),
            ),
            ("prepare_requirements", ["prepare-requirements", "--repo", ".", "--task", "run", "--conflict-evidence", str(evidence)], (Path("."), "run", evidence)),
            ("accept_requirements", ["accept-requirements", "--repo", ".", "--task", "run", "--raw-response", str(response), "--observed-conversation-url", "https://chatgpt.com/c/1", "--observed-model-label", "Pro"], (Path("."), "run", response, "https://chatgpt.com/c/1", "Pro")),
            ("approve_requirements", ["approve-requirements", "--repo", ".", "--task", "run", "--approval-evidence", str(evidence)], (Path("."), "run", evidence)),
            ("build_report", ["build-report", "--repo", ".", "--task", "run", "--local-evidence", str(evidence)], (Path("."), "run", evidence)),
            ("prepare_review", ["prepare-review", "--repo", ".", "--task", "run", "--supplemental-evidence", str(evidence)], (Path("."), "run", evidence)),
            ("accept_review", ["accept-review", "--repo", ".", "--task", "run", "--raw-response", str(response), "--observed-conversation-url", "https://chatgpt.com/c/1", "--observed-model-label", "Pro"], (Path("."), "run", response, "https://chatgpt.com/c/1", "Pro")),
            ("final_verify", ["final-verify", "--repo", ".", "--task", "run"], (Path("."), "run")),
            ("status_run", ["status", "--repo", ".", "--task", "run"], (Path("."), "run")),
            ("abandon_attempt", ["abandon-attempt", "--repo", ".", "--task", "run", "--send-status", "NOT_SENT", "--not-sent-evidence", str(evidence)], (Path("."), "run", "NOT_SENT", evidence)),
        ]
        for function_name, arguments, expected in cases:
            with self.subTest(command=arguments[0]):
                with patch.object(cli.controller, function_name, return_value={}) as dispatch:
                    with patch.object(cli, "_write"):
                        self.assertEqual(cli.main(arguments), 0)
                dispatch.assert_called_once_with(*expected)

    def test_failed_preflight_cleans_owned_run_and_allows_same_slug_retry(self) -> None:
        (self.repository / "new-product.py").write_text("value = 1\n", encoding="utf-8")
        paths = controller.resolve_run(self.repository, "retry-test")
        with self.assertRaisesRegex(controller.ControllerError, "unapproved pre-existing"):
            controller.initialize_run(
                self.repository, "retry-test", self.request, self.context, [], "PRO_CLASS", None
            )
        self.assertFalse(paths.run.exists())
        (self.repository / "new-product.py").unlink()
        result = controller.initialize_run(
            self.repository, "retry-test", self.request, self.context, [], "PRO_CLASS", None
        )
        self.assertEqual(result["phase"], "REQUIREMENTS_PENDING")

    def test_run_lock_refuses_contention_without_deleting_foreign_lock(self) -> None:
        paths = controller.resolve_run(self.repository, "locked-test")
        paths.run.mkdir(parents=True)
        paths.lock.write_text('{"pid":999999}\n', encoding="utf-8")
        with self.assertRaisesRegex(controller.ControllerError, "already locked"):
            with controller.run_lock(paths.lock):
                self.fail("foreign lock must prevent entry")
        self.assertEqual(paths.lock.read_text(encoding="utf-8"), '{"pid":999999}\n')

    def test_concurrent_initialization_has_one_owner_and_one_valid_run(self) -> None:
        barrier = threading.Barrier(2)

        def initialize() -> object:
            barrier.wait()
            try:
                return controller.initialize_run(
                    self.repository,
                    "race-test",
                    self.request,
                    self.context,
                    [],
                    "PRO_CLASS",
                    None,
                )
            except controller.ControllerError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: initialize(), range(2)))
        successes = [result for result in results if isinstance(result, dict)]
        failures = [result for result in results if isinstance(result, controller.ControllerError)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(successes[0]["phase"], "REQUIREMENTS_PENDING")
        self.assertEqual(len(failures), 1)
        self.assertIn(failures[0].code, {"RUN_LOCKED", "RUN_EXISTS"})
        paths = controller.resolve_run(self.repository, "race-test")
        self.assertTrue(paths.state.is_file())
        self.assertEqual(list(paths.transactions.iterdir()), [])

    def test_staging_failure_cleans_transaction_and_untrusted_run_artifacts(self) -> None:
        paths = controller.resolve_run(self.repository, "failure-test")
        replace = controller.os.replace

        def fail_state_commit(source: object, destination: object) -> None:
            if Path(destination) == paths.state:
                raise OSError("injected state replacement failure")
            replace(source, destination)

        with patch.object(controller.os, "replace", side_effect=fail_state_commit):
            with self.assertRaises(controller.ControllerError):
                controller.initialize_run(
                    self.repository,
                    "failure-test",
                    self.request,
                    self.context,
                    [],
                    "PRO_CLASS",
                    None,
                )
        self.assertFalse(paths.run.exists())
        result = controller.initialize_run(
            self.repository,
            "failure-test",
            self.request,
            self.context,
            [],
            "PRO_CLASS",
            None,
        )
        self.assertEqual(result["phase"], "REQUIREMENTS_PENDING")

    def test_template_rendering_is_platform_stable_and_does_not_reparse_values(self) -> None:
        template = controller.Template(
            (
                "Request:\n",
                controller.Token("USER_REQUEST"),
                "\nDigest:",
                controller.Token("PROMPT_DIGEST"),
                "\n",
            )
        )
        value = "literal {{PROMPT_DIGEST}}\r\nline"
        first = controller.render_prompt(template, {"USER_REQUEST": value})
        second = controller.render_prompt(
            template, {"USER_REQUEST": value.replace("\r\n", "\n")}
        )
        self.assertEqual(first, second)
        self.assertIn("literal {{PROMPT_DIGEST}}", first["prompt"])
        self.assertRegex(first["prompt_digest"], r"sha256:[0-9a-f]{64}")

    def test_template_rejects_missing_duplicate_and_unknown_tokens(self) -> None:
        with self.assertRaisesRegex(controller.ControllerError, "duplicate"):
            controller.parse_template("{{USER_REQUEST}}{{USER_REQUEST}}\n", {"USER_REQUEST"})
        with self.assertRaisesRegex(controller.ControllerError, "unknown"):
            controller.parse_template("{{UNSUPPORTED}}\n", {"USER_REQUEST"})
        with self.assertRaisesRegex(controller.ControllerError, "unknown"):
            controller.parse_template("{{BAD-TOKEN}}\n", {"USER_REQUEST"})
        with self.assertRaisesRegex(controller.ControllerError, "missing"):
            controller.parse_template("plain\n", {"USER_REQUEST"})

    def test_template_rejects_unmatched_incomplete_and_multiline_braces(self) -> None:
        malformed = (
            "{{USER_REQUEST}}\n{{BROKEN}\n",
            "{{USER_REQUEST}}\nBROKEN}}\n",
            "{{USER_REQUEST}}\n{{BROKEN\nTOKEN}}\n",
            "{{USER_REQUEST}}\n{{\n",
            "{{USER_REQUEST}}\n}}\n",
        )
        for raw in malformed:
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(controller.ControllerError, "malformed"):
                    controller.parse_template(raw, {"USER_REQUEST"})

    def test_prepare_requirements_persists_expected_header_before_return(self) -> None:
        self._init_run()
        result = controller.prepare_requirements(self.repository, "controller-test")
        expected = controller.load_json(Path(result["expected_header_path"]))
        self.assertEqual(expected["packet_type"], "requirements")
        self.assertEqual(expected["previous_packet_digest"], None)
        self.assertTrue(Path(result["prompt_path"]).is_file())
        self.assertEqual(expected["prompt_digest"], result["prompt_digest"])
        self.assertEqual(
            controller.status_run(self.repository, "controller-test")["next_commands"],
            ["accept-requirements", "abandon-attempt"],
        )

    def test_second_outstanding_attempt_is_refused(self) -> None:
        self._init_run()
        controller.prepare_requirements(self.repository, "controller-test")
        with self.assertRaisesRegex(controller.ControllerError, "outstanding"):
            controller.prepare_requirements(self.repository, "controller-test")

    def test_abandon_requires_proven_not_sent_and_preserves_state(self) -> None:
        self._init_run()
        controller.prepare_requirements(self.repository, "controller-test")
        paths = controller.resolve_run(self.repository, "controller-test")
        original = paths.state.read_bytes()
        evidence = self.repository / "not-sent.txt"
        evidence.write_text(
            "The composer remained empty; no send action occurred.\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(controller.ControllerError, "NOT_SENT"):
            controller.abandon_attempt(
                self.repository, "controller-test", "AMBIGUOUS", evidence
            )
        result = controller.abandon_attempt(
            self.repository, "controller-test", "NOT_SENT", evidence
        )
        self.assertEqual(paths.state.read_bytes(), original)
        self.assertTrue(Path(result["abandoned_attempt_path"]).is_file())
        self.assertEqual(
            Path(result["abandoned_attempt_path"]), paths.run / "expected-attempt-01.json"
        )
        self.assertEqual(
            controller.load_json(Path(result["abandoned_attempt_path"]))["status"],
            "ABANDONED_NOT_SENT",
        )
        replacement = controller.prepare_requirements(self.repository, "controller-test")
        self.assertNotEqual(result["nonce"], replacement["nonce"])

    def test_tampered_abandoned_receipts_keep_the_semantic_turn_blocked(self) -> None:
        self._init_run()
        controller.prepare_requirements(self.repository, "controller-test")
        evidence = self.repository / "not-sent.txt"
        evidence.write_text("The composer remained empty.\n", encoding="utf-8")
        abandoned = controller.abandon_attempt(
            self.repository, "controller-test", "NOT_SENT", evidence
        )
        receipt_path = Path(abandoned["abandoned_attempt_path"])
        receipt = controller.load_json(receipt_path)
        tampered_receipts = {
            "missing fields": {"status": "ABANDONED_NOT_SENT"},
            "unknown field": {**receipt, "unknown": True},
            "wrong schema type": {**receipt, "schema_version": True},
            "wrong header digest": {
                **receipt,
                "expected_header_digest": "sha256:" + "0" * 64,
            },
            "wrong copied nonce": {**receipt, "nonce": "tampered"},
            "wrong copied prompt digest": {
                **receipt,
                "prompt_digest": "sha256:" + "1" * 64,
            },
            "wrong evidence type": {**receipt, "evidence": ["not sent"]},
            "wrong timestamp type": {**receipt, "abandoned_at_unix": True},
        }
        for name, tampered in tampered_receipts.items():
            with self.subTest(name=name):
                controller.write_json_atomic(receipt_path, tampered)
                status = controller.status_run(self.repository, "controller-test")
                self.assertEqual(status["next_commands"], [])
                with self.assertRaisesRegex(controller.ControllerError, "outstanding"):
                    controller.prepare_requirements(self.repository, "controller-test")

        controller.write_json_atomic(receipt_path, receipt)
        malformed_sequence_receipt = receipt_path.with_name("abandoned-attempt-99.json")
        controller.write_json_atomic(
            malformed_sequence_receipt, {"status": "ABANDONED_NOT_SENT"}
        )
        with self.assertRaisesRegex(controller.ControllerError, "abandoned"):
            controller.prepare_requirements(self.repository, "controller-test")

    def test_accept_initial_requirements_binds_browser_and_freezes(self) -> None:
        self._init_run()
        attempt = controller.prepare_requirements(self.repository, "controller-test")
        expected = controller.load_json(Path(attempt["expected_header_path"]))
        raw = self.repository / "requirements.raw.md"
        envelope = write_raw_envelope(raw, expected, valid_requirements())
        result = controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            "https://chatgpt.com/c/controller-test",
            "Pro",
        )
        self.assertEqual(result["phase"], "REQUIREMENTS_FROZEN")
        state = self._state()
        self.assertEqual(
            state["last_consumed_packet_digest"],
            controller.validate_packet.canonical_digest(envelope),
        )
        self.assertEqual(
            state["bound_conversation_url"],
            "https://chatgpt.com/c/controller-test",
        )

    def test_accept_requirements_rejects_wrong_observed_browser_without_state_change(self) -> None:
        self._init_run()
        attempt = controller.prepare_requirements(self.repository, "controller-test")
        expected = controller.load_json(Path(attempt["expected_header_path"]))
        raw = self.repository / "requirements.raw.md"
        write_raw_envelope(raw, expected, valid_requirements())
        before = self._state_bytes()
        with self.assertRaisesRegex(controller.ControllerError, "model"):
            controller.accept_requirements(
                self.repository,
                "controller-test",
                raw,
                "https://chatgpt.com/c/controller-test",
                "Standard",
            )
        self.assertEqual(self._state_bytes(), before)

    def test_orphan_envelope_does_not_enter_consumed_history(self) -> None:
        self._init_run()
        paths = controller.resolve_run(self.repository, "controller-test")
        (paths.run / "envelope-99.json").write_text(
            json.dumps({"schema_version": 1}) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(controller.consumed_chain_heads(self._state()), set())

    def test_material_proposal_requires_digest_bound_local_approval(self) -> None:
        self._freeze_initial_requirements()
        self._seed_requirements_revision_pending()
        attempt = controller.prepare_requirements(
            self.repository,
            "controller-test",
            conflict_evidence_path=self._write_conflict(),
        )
        expected = controller.load_json(Path(attempt["expected_header_path"]))
        proposal = valid_requirements(
            requirements_revision=2,
            supersedes_digest=self._state()["active_requirements_digest"],
            decision="NEED_USER_INPUT",
            behavior_changed=True,
            user_approval_required=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        raw = self.repository / "revision.raw.md"
        write_raw_envelope(raw, expected, proposal)
        stopped = controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
        self.assertEqual(stopped["phase"], "USER_DECISION_REQUIRED")
        evidence = self.repository / "approval.txt"
        evidence.write_text("The user approved this exact proposal.\n", encoding="utf-8")
        frozen = controller.approve_requirements(
            self.repository, "controller-test", evidence
        )
        self.assertEqual(frozen["phase"], "REQUIREMENTS_FROZEN")
        self.assertEqual(frozen["review_round"], 0)

    def test_acceptance_rolls_back_if_state_publish_fails(self) -> None:
        self._init_run()
        expected, raw = self._prepare_raw_requirements(valid_requirements())
        paths = controller.resolve_run(self.repository, "controller-test")
        before = paths.state.read_bytes()
        replace = controller.os.replace

        def fail_state_publish(source: object, destination: object) -> None:
            if Path(destination) == paths.state:
                raise OSError("injected state publish failure")
            replace(source, destination)

        with patch.object(controller.os, "replace", side_effect=fail_state_publish):
            with self.assertRaisesRegex(controller.ControllerError, "commit"):
                controller.accept_requirements(
                    self.repository,
                    "controller-test",
                    raw,
                    "https://chatgpt.com/c/controller-test",
                    "Pro",
                )
        self.assertEqual(paths.state.read_bytes(), before)
        self.assertTrue(Path(self._run_dir() / "expected-attempt-01.json").is_file())
        self.assertFalse((paths.run / "envelope-01.json").exists())
        self.assertFalse((paths.run / "requirements-revision-01.json").exists())
        self.assertFalse((paths.run / "requirements.json").exists())
        self.assertFalse((paths.run / "responses" / f"{expected['turn_id']}.raw.md").exists())
        self.assertEqual(list(paths.transactions.iterdir()), [])

    def test_acceptance_requires_manual_recovery_after_interrupted_publish(self) -> None:
        self._init_run()
        _, raw = self._prepare_raw_requirements(valid_requirements())
        paths = controller.resolve_run(self.repository, "controller-test")
        replace = controller.os.replace

        def interrupt_state_publish(source: object, destination: object) -> None:
            if Path(destination) == paths.state:
                raise KeyboardInterrupt("simulated process interruption")
            replace(source, destination)

        with patch.object(controller.os, "replace", side_effect=interrupt_state_publish):
            with self.assertRaises(KeyboardInterrupt):
                controller.accept_requirements(
                    self.repository,
                    "controller-test",
                    raw,
                    "https://chatgpt.com/c/controller-test",
                    "Pro",
                )
        with self.assertRaisesRegex(controller.ControllerError, "recovery"):
            controller.accept_requirements(
                self.repository, "controller-test", raw,
                "https://chatgpt.com/c/controller-test", "Pro",
            )
        self.assertNotEqual(list(paths.transactions.iterdir()), [])

    def test_approval_requires_manual_recovery_after_interrupted_publish(self) -> None:
        self._freeze_initial_requirements()
        self._seed_requirements_revision_pending()
        _, raw = self._prepare_raw_requirements(
            valid_requirements(
                requirements_revision=2,
                supersedes_digest=self._state()["active_requirements_digest"],
                decision="NEED_USER_INPUT",
                behavior_changed=True,
                user_approval_required=True,
                prior_evidence_invalidated=True,
                review_round_reset=True,
            ),
            "revision.raw.md",
        )
        controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
        paths = controller.resolve_run(self.repository, "controller-test")
        prior_active = (paths.run / "requirements.json").read_bytes()
        approval = self.repository / "approval.txt"
        approval.write_text("The user approved this exact proposal.\n", encoding="utf-8")
        replace = controller.os.replace

        def interrupt_state_publish(source: object, destination: object) -> None:
            if Path(destination) == paths.state:
                raise KeyboardInterrupt("simulated process interruption")
            replace(source, destination)

        with patch.object(controller.os, "replace", side_effect=interrupt_state_publish):
            with self.assertRaises(KeyboardInterrupt):
                controller.approve_requirements(
                    self.repository, "controller-test", approval
                )
        self.assertEqual(self._state()["phase"], "USER_DECISION_REQUIRED")
        self.assertNotEqual((paths.run / "requirements.json").read_bytes(), prior_active)
        with self.assertRaisesRegex(controller.ControllerError, "recovery"):
            controller.approve_requirements(self.repository, "controller-test", approval)
        self.assertNotEqual(list(paths.transactions.iterdir()), [])

    def test_acceptance_cleanup_interruption_keeps_manifest_for_repeatable_recovery(
        self,
    ) -> None:
        self._freeze_initial_requirements()
        self._seed_requirements_revision_pending()
        active_digest = self._state()["active_requirements_digest"]
        _, raw = self._prepare_raw_requirements(
            valid_requirements(
                requirements_revision=2,
                supersedes_digest=active_digest,
                change_reason="Clarify the existing behavior without changing it.",
            ),
            "revision-cleanup.raw.md",
        )
        paths = controller.resolve_run(self.repository, "controller-test")
        unlink = Path.unlink
        iterdir = Path.iterdir
        interrupted = False

        def manifest_first(path: Path):
            entries = list(iterdir(path))
            if path.parent == paths.transactions:
                entries.sort(key=lambda entry: entry.name != "manifest.json")
            return iter(entries)

        def interrupt_backup_cleanup(
            path: Path, *args: object, **kwargs: object
        ) -> None:
            nonlocal interrupted
            if path.name.startswith("backup-") and not interrupted:
                interrupted = True
                raise KeyboardInterrupt("simulated cleanup interruption")
            unlink(path, *args, **kwargs)

        with (
            patch.object(Path, "iterdir", new=manifest_first),
            patch.object(Path, "unlink", new=interrupt_backup_cleanup),
        ):
            with self.assertRaises(KeyboardInterrupt):
                controller.accept_requirements(
                    self.repository,
                    "controller-test",
                    raw,
                    self._state()["bound_conversation_url"],
                    "Pro",
                )

        transaction = next(paths.transactions.iterdir())
        self.assertTrue((transaction / "manifest.json").is_file())
        self.assertTrue(
            any(path.name.startswith("backup-") for path in transaction.iterdir())
        )
        self.assertEqual(self._state()["phase"], "REQUIREMENTS_FROZEN")
        for _ in range(2):
            with self.assertRaisesRegex(controller.ControllerError, "recovery"):
                controller.prepare_requirements(self.repository, "controller-test")
        self.assertNotEqual(list(paths.transactions.iterdir()), [])

    def test_approval_cleanup_interruption_keeps_manifest_for_repeatable_recovery(
        self,
    ) -> None:
        self._freeze_initial_requirements()
        self._seed_requirements_revision_pending()
        _, raw = self._prepare_raw_requirements(
            valid_requirements(
                requirements_revision=2,
                supersedes_digest=self._state()["active_requirements_digest"],
                decision="NEED_USER_INPUT",
                behavior_changed=True,
                user_approval_required=True,
                prior_evidence_invalidated=True,
                review_round_reset=True,
            ),
            "revision-approval-cleanup.raw.md",
        )
        controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
        paths = controller.resolve_run(self.repository, "controller-test")
        approval = self.repository / "approval-cleanup.txt"
        approval.write_text("Approved exact material proposal.\n", encoding="utf-8")
        unlink = Path.unlink
        iterdir = Path.iterdir
        interrupted = False

        def manifest_first(path: Path):
            entries = list(iterdir(path))
            if path.parent == paths.transactions:
                entries.sort(key=lambda entry: entry.name != "manifest.json")
            return iter(entries)

        def interrupt_backup_cleanup(
            path: Path, *args: object, **kwargs: object
        ) -> None:
            nonlocal interrupted
            if path.name.startswith("backup-") and not interrupted:
                interrupted = True
                raise KeyboardInterrupt("simulated cleanup interruption")
            unlink(path, *args, **kwargs)

        with (
            patch.object(Path, "iterdir", new=manifest_first),
            patch.object(Path, "unlink", new=interrupt_backup_cleanup),
        ):
            with self.assertRaises(KeyboardInterrupt):
                controller.approve_requirements(
                    self.repository, "controller-test", approval
                )

        transaction = next(paths.transactions.iterdir())
        self.assertTrue((transaction / "manifest.json").is_file())
        self.assertTrue(
            any(path.name.startswith("backup-") for path in transaction.iterdir())
        )
        self.assertEqual(self._state()["phase"], "REQUIREMENTS_FROZEN")
        for _ in range(2):
            with self.assertRaisesRegex(controller.ControllerError, "recovery"):
                controller.prepare_requirements(self.repository, "controller-test")
        self.assertNotEqual(list(paths.transactions.iterdir()), [])

    def test_initial_requirements_need_user_input_preserves_proposal(self) -> None:
        self._init_run()
        _, raw = self._prepare_raw_requirements(
            valid_requirements(
                decision="NEED_USER_INPUT",
                change_reason="A product choice remains open.",
                open_questions=["Which behavior should be selected?"],
            )
        )
        result = controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            "https://chatgpt.com/c/controller-test",
            "Pro",
        )
        self.assertEqual(result["phase"], "USER_DECISION_REQUIRED")
        state = self._state()
        self.assertEqual(state["pending_requirements_revision"], 1)
        self.assertEqual(
            state["pending_requirements_digest"],
            controller.validate_packet.canonical_digest(valid_requirements(
                decision="NEED_USER_INPUT",
                change_reason="A product choice remains open.",
                open_questions=["Which behavior should be selected?"],
            )),
        )

    def test_initial_requirements_block_is_a_valid_terminal_route(self) -> None:
        self._init_run()
        _, raw = self._prepare_raw_requirements(
            valid_requirements(
                decision="BLOCK",
                change_reason="Repository evidence is insufficient.",
            )
        )
        result = controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            "https://chatgpt.com/c/controller-test",
            "Pro",
        )
        self.assertEqual(result["phase"], "BLOCKED")
        self.assertIsNone(self._state()["active_requirements_digest"])

    def test_requirements_revision_block_preserves_active_and_clears_proposal(self) -> None:
        self._freeze_initial_requirements()
        active_digest = self._state()["active_requirements_digest"]
        self._seed_requirements_revision_pending()
        _, raw = self._prepare_raw_requirements(
            valid_requirements(
                requirements_revision=2,
                supersedes_digest=active_digest,
                decision="BLOCK",
                change_reason="The revision cannot be made safely.",
            ),
            "revision-block.raw.md",
        )
        result = controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
        self.assertEqual(result["phase"], "BLOCKED")
        state = self._state()
        self.assertEqual(state["active_requirements_digest"], active_digest)
        self.assertIsNone(state["pending_requirements_revision"])
        self.assertIsNone(state["pending_requirements_digest"])

    def test_material_approval_clears_every_review_binding(self) -> None:
        self._freeze_initial_requirements()
        state = self._state()
        review_head = "sha256:" + "9" * 64
        state.update(
            phase="REQUIREMENTS_PENDING",
            review_round=2,
            latest_decision="CHANGES_REQUESTED",
            latest_requirements_decision=None,
            required_actions=["REQUIREMENTS_REVISION"],
            unresolved_finding_ids=["F-1"],
            blocker_fingerprints=["sha256:" + "4" * 64],
            active_report_digest="sha256:" + "1" * 64,
            current_snapshot_digest="sha256:" + "2" * 64,
            active_review_packet_digest="sha256:" + "3" * 64,
            reviewed_snapshot_digest="sha256:" + "2" * 64,
            last_consumed_packet_digest=review_head,
            last_consumed_review_envelope_digest=review_head,
        )
        controller.write_json_atomic(self._run_dir() / "state.json", state)
        _, raw = self._prepare_raw_requirements(
            valid_requirements(
                requirements_revision=2,
                supersedes_digest=state["active_requirements_digest"],
                decision="NEED_USER_INPUT",
                behavior_changed=True,
                user_approval_required=True,
                prior_evidence_invalidated=True,
                review_round_reset=True,
            ),
            "revision-reset.raw.md",
        )
        controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            state["bound_conversation_url"],
            "Pro",
        )
        requirements_head = self._state()["last_consumed_packet_digest"]
        approval = self.repository / "approval-reset.txt"
        approval.write_text("Approved exact material proposal.\n", encoding="utf-8")
        controller.approve_requirements(self.repository, "controller-test", approval)
        frozen = self._state()
        self.assertEqual(frozen["review_round"], 0)
        self.assertEqual(frozen["latest_decision"], None)
        self.assertEqual(frozen["required_actions"], [])
        self.assertEqual(frozen["unresolved_finding_ids"], [])
        self.assertEqual(frozen["blocker_fingerprints"], [])
        for field in (
            "pending_review_envelope_digest",
            "active_report_digest",
            "current_snapshot_digest",
            "active_review_packet_digest",
            "reviewed_snapshot_digest",
        ):
            with self.subTest(field=field):
                self.assertIsNone(frozen[field])
        self.assertEqual(frozen["last_consumed_packet_digest"], requirements_head)
        self.assertEqual(frozen["last_consumed_review_envelope_digest"], review_head)

    def test_tampered_expected_turn_id_cannot_escape_run(self) -> None:
        self._init_run()
        attempt = controller.prepare_requirements(self.repository, "controller-test")
        expected_path = Path(attempt["expected_header_path"])
        expected = controller.load_json(expected_path)
        expected["turn_id"] = "../../escape"
        controller.write_json_atomic(expected_path, expected)
        raw = self.repository / "traversal.raw.md"
        write_raw_envelope(raw, expected, valid_requirements())
        before = self._state_bytes()
        with self.assertRaisesRegex(controller.ControllerError, "attempt"):
            controller.accept_requirements(
                self.repository,
                "controller-test",
                raw,
                "https://chatgpt.com/c/controller-test",
                "Pro",
            )
        self.assertEqual(self._state_bytes(), before)
        self.assertFalse((self._run_dir().parent / "escape.raw.md").exists())

    def test_tampered_expected_identifiers_are_rejected(self) -> None:
        self._init_run()
        attempt = controller.prepare_requirements(self.repository, "controller-test")
        expected_path = Path(attempt["expected_header_path"])
        original = controller.load_json(expected_path)
        cases = (
            ("run_id", "gpc-loop-other"),
            ("turn_id", "requirements-99"),
            ("nonce", "not-a-generated-nonce"),
        )
        for field, value in cases:
            with self.subTest(field=field):
                tampered = dict(original)
                tampered[field] = value
                controller.write_json_atomic(expected_path, tampered)
                raw = self.repository / f"tampered-{field}.raw.md"
                write_raw_envelope(raw, tampered, valid_requirements())
                with self.assertRaisesRegex(controller.ControllerError, "attempt"):
                    controller.accept_requirements(
                        self.repository,
                        "controller-test",
                        raw,
                        "https://chatgpt.com/c/controller-test",
                        "Pro",
                    )

    def test_tampered_expected_nonce_is_rejected_even_when_shape_is_valid(self) -> None:
        self._init_run()
        attempt = controller.prepare_requirements(self.repository, "controller-test")
        expected_path = Path(attempt["expected_header_path"])
        tampered = controller.load_json(expected_path)
        replacement = "0" * 32
        if tampered["nonce"] == replacement:
            replacement = "1" * 32
        tampered["nonce"] = replacement
        controller.write_json_atomic(expected_path, tampered)
        raw = self.repository / "tampered-valid-nonce.raw.md"
        write_raw_envelope(raw, tampered, valid_requirements())
        before = self._state_bytes()
        with self.assertRaisesRegex(controller.ControllerError, "attempt"):
            controller.accept_requirements(
                self.repository,
                "controller-test",
                raw,
                "https://chatgpt.com/c/controller-test",
                "Pro",
            )
        self.assertEqual(self._state_bytes(), before)

    def test_build_report_fills_controller_owned_fields_and_binds_snapshot(self) -> None:
        self._freeze_initial_requirements()
        (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
        evidence = self._write_local_evidence({"example.py": "Implement AC-1."})
        result = controller.build_report(self.repository, "controller-test", evidence)
        report = controller.load_json(Path(result["report_path"]))
        snapshot = controller.load_json(Path(result["snapshot_path"]))
        self.assertEqual(report["snapshot_digest"], snapshot["snapshot_digest"])
        self.assertEqual(
            report["requirements_digest"],
            self._state()["active_requirements_digest"],
        )
        self.assertEqual(self._state()["phase"], "REVIEW_PENDING")

    def test_build_report_rejects_missing_and_extra_changed_path_intents(self) -> None:
        self._freeze_initial_requirements()
        (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
        for intents in ({}, {"example.py": "Implement AC-1.", "ghost.py": "extra"}):
            with self.subTest(intents=intents):
                evidence = self._write_local_evidence(intents)
                before = self._state_bytes()
                with self.assertRaisesRegex(controller.ControllerError, "changed_file_intents"):
                    controller.build_report(self.repository, "controller-test", evidence)
                self.assertEqual(self._state_bytes(), before)

    def test_prepare_review_binds_active_requirements_report_and_snapshot(self) -> None:
        self._build_valid_report()
        result = controller.prepare_review(self.repository, "controller-test")
        expected = controller.load_json(Path(result["expected_header_path"]))
        prompt = Path(result["prompt_path"]).read_text(encoding="utf-8")
        self.assertEqual(expected["packet_type"], "review")
        self.assertEqual(
            expected["previous_packet_digest"],
            self._state()["last_consumed_packet_digest"],
        )
        self.assertIn(self._state()["active_requirements_digest"], prompt)
        self.assertEqual(
            controller.status_run(self.repository, "controller-test")["next_commands"],
            ["accept-review", "abandon-attempt"],
        )

    def test_prepare_review_rejects_repository_drift_before_creating_attempt(self) -> None:
        self._build_valid_report()
        run = self._run_dir()
        before_state = self._state_bytes()
        before_artifacts = sorted(
            path.relative_to(run).as_posix()
            for path in run.rglob("*")
            if path.is_file()
        )
        (self.repository / "example.py").write_text("value = 2\n", encoding="utf-8")

        with self.assertRaisesRegex(controller.ControllerError, "snapshot"):
            controller.prepare_review(self.repository, "controller-test")

        self.assertEqual(self._state_bytes(), before_state)
        self.assertEqual(
            sorted(
                path.relative_to(run).as_posix()
                for path in run.rglob("*")
                if path.is_file()
            ),
            before_artifacts,
        )

    def test_evidence_only_review_renders_prior_review_and_exact_envelope(self) -> None:
        prior_review = self._seed_evidence_only_route()
        supplemental = self.input_directory / "supplemental.txt"
        supplemental.write_text("Focused output: 1 test passed.\n", encoding="utf-8")

        result = controller.prepare_review(
            self.repository, "controller-test", supplemental
        )
        expected = controller.load_json(Path(result["expected_header_path"]))
        prompt = Path(result["prompt_path"]).read_text(encoding="utf-8")
        for field in (
            "schema_version",
            "packet_type",
            "run_id",
            "turn_id",
            "nonce",
            "in_reply_to",
            "prompt_digest",
            "previous_packet_digest",
        ):
            value = "null" if expected[field] is None else str(expected[field])
            with self.subTest(field=field):
                self.assertIn(f"{field}={value}\n", prompt)
        self.assertIn(
            json.dumps(prior_review, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            prompt,
        )
        self.assertIn("Attach the exact focused output summary.", prompt)

    def test_evidence_only_review_rejects_prior_review_digest_mismatch(self) -> None:
        self._seed_evidence_only_route()
        review_path = self._run_dir() / "review.json"
        tampered = controller.load_json(review_path)
        tampered["next_instruction"] = "Tampered instruction."
        controller.write_json_atomic(review_path, tampered)
        supplemental = self.input_directory / "supplemental.txt"
        supplemental.write_text("Focused output: 1 test passed.\n", encoding="utf-8")
        before = self._state_bytes()

        with self.assertRaisesRegex(controller.ControllerError, "review"):
            controller.prepare_review(self.repository, "controller-test", supplemental)

        self.assertEqual(self._state_bytes(), before)
        self.assertEqual(list(self._run_dir().glob("expected-attempt-*.json")), [])

    def test_evidence_only_review_accepts_pass_against_prior_round_report(self) -> None:
        attempt = self._prepare_supplemental_review()
        raw = self._write_review_response(attempt, self._valid_pass_review())

        result = controller.accept_review(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )

        self.assertEqual(result["phase"], "FINAL_VERIFICATION")
        self.assertEqual(result["review_round"], 2)

    def test_evidence_only_review_accepts_new_changes_requested_route(self) -> None:
        attempt = self._prepare_supplemental_review()
        review = self._valid_changes_review(
            "REQUIREMENTS_REVISION", "REQUIREMENTS", "requirements-ambiguity"
        )
        review["findings"][0]["id"] = "F-2"
        raw = self._write_review_response(attempt, review)

        result = controller.accept_review(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )

        self.assertEqual(result["phase"], "REQUIREMENTS_PENDING")
        self.assertEqual(result["review_round"], 2)

    def test_accept_review_rejects_valid_shaped_in_reply_to_tampering(self) -> None:
        attempt = self._prepare_valid_review()
        expected_path = Path(attempt["expected_header_path"])
        tampered = controller.load_json(expected_path)
        tampered["in_reply_to"] = "sha256:" + "a" * 64
        controller.write_json_atomic(expected_path, tampered)
        raw = self._write_review_response(attempt, self._valid_pass_review())
        before = self._state_bytes()

        with self.assertRaises(controller.ControllerError):
            controller.accept_review(
                self.repository,
                "controller-test",
                raw,
                self._state()["bound_conversation_url"],
                "Pro",
            )

        self.assertEqual(self._state_bytes(), before)

    def test_accept_review_rejects_valid_shaped_prompt_and_expected_tampering(self) -> None:
        attempt = self._prepare_valid_review()
        expected_path = Path(attempt["expected_header_path"])
        tampered = controller.load_json(expected_path)
        original_digest = tampered["prompt_digest"]
        tampered_digest = "sha256:" + "b" * 64
        tampered["prompt_digest"] = tampered_digest
        controller.write_json_atomic(expected_path, tampered)
        prompt_path = Path(attempt["prompt_path"])
        prompt = prompt_path.read_text(encoding="utf-8")
        prompt_path.write_text(
            prompt.replace(str(original_digest), tampered_digest), encoding="utf-8"
        )
        raw = self._write_review_response(attempt, self._valid_pass_review())
        before = self._state_bytes()

        with self.assertRaises(controller.ControllerError):
            controller.accept_review(
                self.repository,
                "controller-test",
                raw,
                self._state()["bound_conversation_url"],
                "Pro",
            )

        self.assertEqual(self._state_bytes(), before)

    def test_accept_pass_review_consumes_round_and_routes_to_final_verification(self) -> None:
        attempt = self._prepare_valid_review()
        raw = self._write_review_response(attempt, self._valid_pass_review())

        result = controller.accept_review(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )

        self.assertEqual(result["phase"], "FINAL_VERIFICATION")
        self.assertEqual(result["review_round"], 1)
        self.assertEqual(result["required_actions"], [])

    def test_accept_changes_requested_routes_and_derives_fingerprints(self) -> None:
        attempt = self._prepare_valid_review()
        raw = self._write_review_response(
            attempt,
            self._valid_changes_review(
                "CODE_CHANGE", "CORRECTNESS", "missing-empty-input-guard"
            ),
        )

        result = controller.accept_review(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )

        self.assertEqual(result["phase"], "IMPLEMENTING")
        self.assertEqual(result["required_actions"], ["CODE_CHANGE"])
        self.assertEqual(len(result["blocker_fingerprints"]), 2)

    def test_accept_review_routes_structural_actions(self) -> None:
        cases = {
            ("PASS", ()): "FINAL_VERIFICATION",
            ("BLOCK", ()): "USER_DECISION_REQUIRED",
            ("CHANGES_REQUESTED", ("CODE_CHANGE",)): "IMPLEMENTING",
            ("CHANGES_REQUESTED", ("TEST_CHANGE",)): "IMPLEMENTING",
            ("CHANGES_REQUESTED", ("PROVIDE_EVIDENCE",)): "LOCAL_VERIFICATION",
            ("CHANGES_REQUESTED", ("REQUIREMENTS_REVISION",)): "REQUIREMENTS_PENDING",
            ("CHANGES_REQUESTED", ("USER_DECISION",)): "USER_DECISION_REQUIRED",
        }
        for (decision, actions), expected_phase in cases.items():
            with self.subTest(decision=decision, actions=actions):
                self.assertEqual(controller.review_target(decision, actions), expected_phase)

    def test_accept_review_rejects_wrong_current_conversation_and_model(self) -> None:
        attempt = self._prepare_valid_review()
        raw = self._write_review_response(attempt, self._valid_pass_review())
        before = self._state_bytes()
        for url, label in (
            ("https://chatgpt.com/c/other", "Pro"),
            (self._state()["bound_conversation_url"], "Standard"),
        ):
            with self.subTest(url=url, label=label):
                with self.assertRaises(controller.ControllerError):
                    controller.accept_review(
                        self.repository, "controller-test", raw, url, label
                    )
                self.assertEqual(self._state_bytes(), before)

    def test_final_verify_derives_gate_and_completes_unchanged_snapshot(self) -> None:
        self._accept_pass_review()

        result = controller.final_verify(self.repository, "controller-test")
        gate = controller.load_json(self._run_dir() / "final-gate.json")

        self.assertEqual(result["phase"], "COMPLETE")
        self.assertTrue(
            all(
                gate[field] is True
                for field in (
                    "acceptance_gate_passed",
                    "local_checks_passed",
                    "scope_gate_passed",
                    "artifact_hygiene_passed",
                )
            )
        )

    def test_final_verify_rejects_failed_report_omission_or_blocker(self) -> None:
        cases = (
            {
                "test_commands": [
                    {
                        "command": "python -m unittest test_example.py -v",
                        "outcome": "FAIL",
                        "output_summary": "1 test failed.",
                    }
                ]
            },
            {"omissions": ["AC-1 edge case was not exercised."]},
            {"unresolved_risks_or_blockers": ["Required dependency is unavailable."]},
        )
        for evidence_overrides in cases:
            with self.subTest(evidence_overrides=evidence_overrides):
                self._accept_pass_review(**evidence_overrides)
                before = self._state_bytes()
                with self.assertRaises(controller.ControllerError):
                    controller.final_verify(self.repository, "controller-test")
                self.assertEqual(self._state_bytes(), before)
                self.temporary.cleanup()
                self.setUp()

    def test_pass_with_scope_violation_is_rejected_before_final_gate(self) -> None:
        attempt = self._prepare_valid_review()
        review = self._valid_pass_review()
        review["scope_violations"] = ["example.py changed outside the frozen scope."]
        raw = self._write_review_response(attempt, review)
        before = self._state_bytes()

        with self.assertRaises(controller.ControllerError):
            controller.accept_review(
                self.repository,
                "controller-test",
                raw,
                self._state()["bound_conversation_url"],
                "Pro",
            )

        self.assertEqual(self._state_bytes(), before)

    def test_final_verify_rejects_tracked_metadata_and_product_drift(self) -> None:
        self._accept_pass_review()
        subprocess.run(
            ["git", "add", "-f", ".ai-pro-loop/controller-test/state.json"],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        )
        before = self._state_bytes()
        with self.assertRaises(controller.ControllerError):
            controller.final_verify(self.repository, "controller-test")
        self.assertEqual(self._state_bytes(), before)

        subprocess.run(["git", "reset"], cwd=self.repository, check=True, capture_output=True)
        (self.repository / "example.py").write_text("value = 2\n", encoding="utf-8")
        with self.assertRaises(controller.ControllerError):
            controller.final_verify(self.repository, "controller-test")
        self.assertEqual(self._state_bytes(), before)

    def test_correction_loop_replaces_snapshot_and_rejects_first_review_replay(self) -> None:
        first_attempt = self._prepare_valid_review()
        first_raw = self._write_review_response(
            first_attempt,
            self._valid_changes_review(
                "CODE_CHANGE", "CORRECTNESS", "missing-empty-input-guard"
            ),
        )
        first_result = controller.accept_review(
            self.repository,
            "controller-test",
            first_raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
        first_snapshot = self._state()["current_snapshot_digest"]
        self.assertEqual(first_result["phase"], "IMPLEMENTING")

        (self.repository / "example.py").write_text("value = 2\n", encoding="utf-8")
        evidence = self._write_local_evidence({"example.py": "Correct AC-1."})
        controller.build_report(self.repository, "controller-test", evidence)
        second_attempt = controller.prepare_review(self.repository, "controller-test")
        second_raw = self._write_review_response(second_attempt, self._valid_pass_review())
        result = controller.accept_review(
            self.repository,
            "controller-test",
            second_raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )

        with self.assertRaises(controller.ControllerError):
            controller.accept_review(
                self.repository,
                "controller-test",
                first_raw,
                self._state()["bound_conversation_url"],
                "Pro",
            )
        gate_result = controller.final_verify(self.repository, "controller-test")
        gate = controller.load_json(self._run_dir() / "final-gate.json")
        self.assertEqual(result["review_round"], 2)
        self.assertEqual(gate_result["phase"], "COMPLETE")
        self.assertNotEqual(first_snapshot, gate["current_snapshot_digest"])
        self.assertEqual(gate["current_snapshot_digest"], self._state()["reviewed_snapshot_digest"])

    def test_second_review_rejects_repeated_blocker_but_allows_new_route(self) -> None:
        first_attempt = self._prepare_valid_review()
        first_raw = self._write_review_response(
            first_attempt,
            self._valid_changes_review("CODE_CHANGE", "CORRECTNESS", "missing-guard"),
        )
        controller.accept_review(
            self.repository,
            "controller-test",
            first_raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
        (self.repository / "example.py").write_text("value = 2\n", encoding="utf-8")
        controller.build_report(
            self.repository,
            "controller-test",
            self._write_local_evidence({"example.py": "Correct AC-1."}),
        )
        repeated_attempt = controller.prepare_review(self.repository, "controller-test")
        repeated_raw = self._write_review_response(
            repeated_attempt,
            self._valid_changes_review("CODE_CHANGE", "CORRECTNESS", "missing-guard"),
        )
        result = controller.accept_review(
            self.repository,
            "controller-test",
            repeated_raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
        self.assertEqual(result["phase"], "BLOCKED")
        self.assertEqual(result["review_round"], 2)
        self.assertEqual(result["next_commands"], [])
        self.assertEqual(result["stop_origin_category"], "REVIEW_REPEATED_BLOCKER")
        self.assertEqual(list(self._run_dir().glob("expected-attempt-*.json")), [])
        self.assertEqual(len(list(self._run_dir().glob("consumed-attempt-*.json"))), 3)
        with self.assertRaises(controller.ControllerError):
            controller.accept_review(
                self.repository,
                "controller-test",
                repeated_raw,
                self._state()["bound_conversation_url"],
                "Pro",
            )

    def test_third_changes_review_durably_stops_before_round_four(self) -> None:
        first_attempt = self._prepare_valid_review()
        first_review = self._valid_changes_review(
            "CODE_CHANGE", "CORRECTNESS", "first-correction"
        )
        controller.accept_review(
            self.repository,
            "controller-test",
            self._write_review_response(first_attempt, first_review),
            self._state()["bound_conversation_url"],
            "Pro",
        )
        for value, action, category, key, finding_id in (
            (2, "TEST_CHANGE", "TEST_COVERAGE", "second-correction", "F-2"),
            (3, "CODE_CHANGE", "CORRECTNESS", "third-correction", "F-3"),
        ):
            (self.repository / "example.py").write_text(
                f"value = {value}\n", encoding="utf-8"
            )
            controller.build_report(
                self.repository,
                "controller-test",
                self._write_local_evidence({"example.py": "Continue AC-1."}),
            )
            attempt = controller.prepare_review(self.repository, "controller-test")
            review = self._valid_changes_review(action, category, key)
            review["findings"][0]["id"] = finding_id
            result = controller.accept_review(
                self.repository,
                "controller-test",
                self._write_review_response(attempt, review),
                self._state()["bound_conversation_url"],
                "Pro",
            )

        self.assertEqual(result["phase"], "BLOCKED")
        self.assertEqual(result["review_round"], 3)
        self.assertEqual(result["next_commands"], [])
        self.assertEqual(result["stop_origin_category"], "REVIEW_ROUND_LIMIT")
        with self.assertRaises(controller.ControllerError):
            controller.prepare_review(self.repository, "controller-test")

    def test_dynamic_path_and_acceptance_ids_are_not_secret_schema_fields(self) -> None:
        requirements = valid_requirements(
            in_scope=["token"],
            acceptance_criteria=[
                {
                    "id": "SESSION",
                    "criterion": "The token path has deterministic behavior.",
                    "required_evidence": "Focused unittest output.",
                }
            ],
        )
        self._freeze_initial_requirements(requirements)
        (self.repository / "token").write_text("value = 1\n", encoding="utf-8")
        evidence = self._write_local_evidence(
            {"token": "Implement SESSION."},
            acceptance_evidence={"SESSION": ["Focused unittest passed."]},
        )

        result = controller.build_report(self.repository, "controller-test", evidence)

        report = controller.load_json(Path(result["report_path"]))
        self.assertEqual(report["changed_files"][0]["path"], "token")
        self.assertEqual(report["acceptance_evidence"], {"SESSION": ["Focused unittest passed."]})

    def test_requirements_expected_header_is_bound_in_trusted_state(self) -> None:
        self._init_run()
        attempt = controller.prepare_requirements(self.repository, "controller-test")
        paths = controller.resolve_run(self.repository, "controller-test")
        expected_path = Path(attempt["expected_header_path"])
        expected = controller.load_json(expected_path)
        self.assertEqual(
            self._state()["pending_requirements_expected_header_digest"],
            controller.validate_packet.canonical_digest(expected),
        )
        for field, replacement in (
            ("in_reply_to", "sha256:" + "0" * 64),
            ("prompt_digest", "sha256:" + "1" * 64),
        ):
            with self.subTest(field=field):
                tampered = dict(expected)
                tampered[field] = replacement
                controller.write_json_atomic(expected_path, tampered)
                raw = self.input_directory / f"tampered-{field}.md"
                write_raw_envelope(raw, tampered, valid_requirements())
                with self.assertRaisesRegex(controller.ControllerError, "attempt"):
                    controller.accept_requirements(
                        self.repository, "controller-test", raw,
                        "https://chatgpt.com/c/controller-test", "Pro",
                    )
                self.assertEqual(paths.state.read_bytes(), self._state_bytes())
                controller.write_json_atomic(expected_path, expected)

    def test_mutation_requires_manual_recovery_without_touching_orphan(self) -> None:
        self._init_run()
        paths = controller.resolve_run(self.repository, "controller-test")
        orphan = paths.transactions / "consume-interrupted"
        orphan.mkdir()
        state = paths.state.read_bytes()
        with self.assertRaisesRegex(controller.ControllerError, "recovery"):
            controller.prepare_requirements(self.repository, "controller-test")
        self.assertTrue(orphan.is_dir())
        self.assertEqual(paths.state.read_bytes(), state)

    def test_state_race_before_replace_preserves_external_state(self) -> None:
        self._freeze_initial_requirements()
        (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
        paths = controller.resolve_run(self.repository, "controller-test")
        external = self._state()
        external["format_error_count"] = 1
        real_check = controller._require_state_digest
        checks = 0

        def inject_race(run_paths: object, digest: object) -> None:
            nonlocal checks
            checks += 1
            if checks == 2:
                controller.write_json_atomic(paths.state, external)
            real_check(run_paths, digest)

        with patch.object(controller, "_require_state_digest", new=inject_race):
            with self.assertRaisesRegex(controller.ControllerError, "state"):
                controller.build_report(
                    self.repository,
                    "controller-test",
                    self._write_local_evidence({"example.py": "Implement AC-1."}),
                )
        self.assertEqual(checks, 2)
        self.assertEqual(paths.state.read_bytes(), controller._canonical_json_bytes(external))

    def test_event_is_not_published_when_state_commit_fails(self) -> None:
        self._freeze_initial_requirements()
        (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
        paths = controller.resolve_run(self.repository, "controller-test")
        before_events = paths.events.read_bytes()
        replace = controller.os.replace

        def fail_state(source: object, destination: object) -> None:
            if Path(destination) == paths.state:
                raise OSError("injected state failure")
            replace(source, destination)

        with patch.object(controller.os, "replace", side_effect=fail_state):
            with self.assertRaises(controller.ControllerError):
                controller.build_report(
                    self.repository, "controller-test",
                    self._write_local_evidence({"example.py": "Implement AC-1."}),
                )
        self.assertEqual(paths.events.read_bytes(), before_events)

    def test_event_failure_after_state_commit_may_omit_only_event(self) -> None:
        self._freeze_initial_requirements()
        (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
        paths = controller.resolve_run(self.repository, "controller-test")
        before_events = paths.events.read_bytes()
        with patch.object(controller, "_record_events", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                controller.build_report(
                    self.repository, "controller-test",
                    self._write_local_evidence({"example.py": "Implement AC-1."}),
                )
        self.assertEqual(self._state()["phase"], "REVIEW_PENDING")
        self.assertEqual(paths.events.read_bytes(), before_events)
