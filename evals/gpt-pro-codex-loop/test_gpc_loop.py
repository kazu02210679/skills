"""Tests for GPT Pro Codex Loop controller run initialization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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
