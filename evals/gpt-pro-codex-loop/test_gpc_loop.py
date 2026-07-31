"""Tests for GPT Pro Codex Loop controller run initialization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
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
        input_directory = Path(self.temporary.name) / "controller-inputs"
        input_directory.mkdir()
        self.request = input_directory / "request.txt"
        self.context = input_directory / "context.txt"
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

    def _freeze_initial_requirements(self) -> dict[str, object]:
        self._init_run()
        attempt = controller.prepare_requirements(self.repository, "controller-test")
        expected = controller.load_json(Path(attempt["expected_header_path"]))
        raw = self.repository / "requirements.raw.md"
        write_raw_envelope(raw, expected, valid_requirements())
        return controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            "https://chatgpt.com/c/controller-test",
            "Pro",
        )

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
