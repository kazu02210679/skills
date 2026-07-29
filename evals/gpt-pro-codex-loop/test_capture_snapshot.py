"""Unit tests for deterministic GPT Pro Codex Loop product snapshots."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "gpt-pro-codex-loop"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIRECTORY))

import capture_snapshot as snapshot_module  # noqa: E402
from capture_snapshot import (  # noqa: E402
    SnapshotError,
    capture_snapshot,
    inspect_preflight,
    validate_preflight,
)
from validate_packet import canonical_digest, validate_report  # noqa: E402


def run_git(repository: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


def valid_requirements() -> dict[str, object]:
    return {
        "schema_version": 1,
        "requirements_revision": 1,
        "supersedes_digest": None,
        "change_reason": "initial requirements",
        "behavior_changed": False,
        "user_approval_required": False,
        "user_approval_received": False,
        "scope_changed": False,
        "public_contract_changed": False,
        "prior_evidence_invalidated": False,
        "review_round_reset": False,
        "decision": "PLAN_READY",
        "objective": "Capture a deterministic product snapshot.",
        "requirements": [{"id": "REQ-1", "statement": "Snapshots are deterministic."}],
        "in_scope": ["snapshot capture"],
        "out_of_scope": ["deployment"],
        "constraints": ["standard library"],
        "acceptance_criteria": [
            {
                "id": "AC-1",
                "criterion": "Snapshot reports validate.",
                "required_evidence": "unit test output",
            }
        ],
        "design_direction": ["fail closed"],
        "risk_items": [
            {
                "id": "RISK-1",
                "risk": "Repository drift",
                "required_mitigation": "stable capture",
            }
        ],
        "verification_strategy": ["run unit tests"],
        "open_questions": [],
    }


class CaptureSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name) / "repository"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "config", "user.email", "test@example.invalid")
        run_git(self.repo, "config", "user.name", "Snapshot Test")
        (self.repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        (self.repo / "app.py").write_text("print('initial')\n", encoding="utf-8")
        (self.repo / "old.txt").write_text("old name\n", encoding="utf-8")
        (self.repo / "blob.bin").write_bytes(b"\x00initial\xff")
        run_git(self.repo, "add", ".")
        run_git(self.repo, "commit", "-qm", "baseline")
        self.baseline = run_git(self.repo, "rev-parse", "HEAD").decode().strip()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_snapshot_changes_when_tracked_content_changes(self) -> None:
        first = capture_snapshot(self.repo, self.baseline)
        (self.repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
        second = capture_snapshot(self.repo, self.baseline)
        self.assertNotEqual(first["snapshot_digest"], second["snapshot_digest"])

    def test_snapshot_changes_when_untracked_content_changes(self) -> None:
        path = self.repo / "new.txt"
        path.write_text("one\n", encoding="utf-8")
        first = capture_snapshot(self.repo, self.baseline)
        path.write_text("two\n", encoding="utf-8")
        second = capture_snapshot(self.repo, self.baseline)
        self.assertNotEqual(first["snapshot_digest"], second["snapshot_digest"])

    def test_tracked_or_staged_run_metadata_is_rejected(self) -> None:
        metadata = self.repo / ".ai-pro-loop" / "task" / "state.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("{}\n", encoding="utf-8")
        run_git(self.repo, "add", str(metadata))
        with self.assertRaises(SnapshotError):
            capture_snapshot(self.repo, self.baseline)

    def test_staged_case_variant_metadata_follows_filesystem_case_rules(self) -> None:
        metadata = self.repo / ".AI-PRO-LOOP" / "task" / "state.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("{}\n", encoding="utf-8")
        aliases_metadata_directory = (self.repo / ".ai-pro-loop").exists()
        run_git(self.repo, "add", str(metadata))

        if aliases_metadata_directory:
            with self.assertRaises(SnapshotError):
                capture_snapshot(self.repo, self.baseline)
        else:
            snapshot = capture_snapshot(self.repo, self.baseline)
            self.assertIn(".AI-PRO-LOOP/task/state.json", [item["path"] for item in snapshot["changed_files"]])

    def test_untracked_case_variant_metadata_follows_filesystem_case_rules(self) -> None:
        metadata = self.repo / ".AI-PRO-LOOP" / "task" / "state.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("{}\n", encoding="utf-8")
        aliases_metadata_directory = (self.repo / ".ai-pro-loop").exists()

        snapshot = capture_snapshot(self.repo, self.baseline)
        changed_paths = [item["path"] for item in snapshot["changed_files"]]
        if aliases_metadata_directory:
            self.assertNotIn(".AI-PRO-LOOP/task/state.json", changed_paths)
        else:
            self.assertIn(".AI-PRO-LOOP/task/state.json", changed_paths)

    def test_unchanged_tracked_case_variant_metadata_is_rejected_when_aliased(self) -> None:
        metadata = self.repo / ".AI-PRO-LOOP" / "task" / "state.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("{}\n", encoding="utf-8")
        aliases_metadata_directory = (self.repo / ".ai-pro-loop").exists()
        run_git(self.repo, "add", str(metadata))
        run_git(self.repo, "commit", "-qm", "track case-variant metadata")
        baseline = run_git(self.repo, "rev-parse", "HEAD").decode().strip()

        if aliases_metadata_directory:
            with self.assertRaises(SnapshotError):
                capture_snapshot(self.repo, baseline)
        else:
            snapshot = capture_snapshot(self.repo, baseline)
            self.assertEqual([], snapshot["changed_files"])

    @unittest.skipUnless(os.name == "posix", "requires POSIX case-sensitive paths")
    def test_git_case_symlink_does_not_spoof_metadata_alias_detection(self) -> None:
        (self.repo / ".git" / "info" / "exclude").write_text(
            ".GIT\n", encoding="utf-8"
        )
        (self.repo / ".GIT").symlink_to(".git", target_is_directory=True)
        product = self.repo / ".AI-PRO-LOOP" / "task" / "product.txt"
        product.parent.mkdir(parents=True)
        product.write_text("legitimate product content\n", encoding="utf-8")

        snapshot = capture_snapshot(self.repo, self.baseline)
        self.assertIn(
            ".AI-PRO-LOOP/task/product.txt",
            [item["path"] for item in snapshot["changed_files"]],
        )

    def test_renamed_files_have_normalized_manifest_entries(self) -> None:
        (self.repo / "old.txt").rename(self.repo / "renamed.txt")
        run_git(self.repo, "add", "-A")
        snapshot = capture_snapshot(self.repo, self.baseline)
        self.assertIn(
            {
                "intent": "snapshot-discovered product change",
                "path": "renamed.txt",
                "previous_path": "old.txt",
                "source": "tracked",
                "status": "renamed",
            },
            snapshot["changed_files"],
        )

    def test_binary_tracked_content_changes_the_snapshot(self) -> None:
        first = capture_snapshot(self.repo, self.baseline)
        (self.repo / "blob.bin").write_bytes(b"\x00changed\xfe")
        second = capture_snapshot(self.repo, self.baseline)
        self.assertNotEqual(first["tracked_diff_digest"], second["tracked_diff_digest"])

    def test_ignored_files_are_not_in_the_product_snapshot(self) -> None:
        first = capture_snapshot(self.repo, self.baseline)
        (self.repo / "ignored.txt").write_text("ignored\n", encoding="utf-8")
        second = capture_snapshot(self.repo, self.baseline)
        self.assertEqual(first, second)

    def test_preflight_requires_exact_approval_for_existing_product_paths(self) -> None:
        (self.repo / "app.py").write_text("print('pre-existing')\n", encoding="utf-8")
        (self.repo / "existing.txt").write_text("existing\n", encoding="utf-8")
        preflight = inspect_preflight(self.repo, self.baseline)
        self.assertEqual(
            [
                "unapproved pre-existing product path: app.py",
                "unapproved pre-existing product path: existing.txt",
            ],
            validate_preflight(preflight, []),
        )
        self.assertEqual(
            [], validate_preflight(preflight, ["app.py", "existing.txt"])
        )

    def test_untracked_paths_are_normalized_and_metadata_is_excluded(self) -> None:
        product_path = self.repo / "nested" / "new.txt"
        product_path.parent.mkdir()
        product_path.write_text("product\n", encoding="utf-8")
        metadata = self.repo / ".ai-pro-loop" / "task" / "state.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("metadata\n", encoding="utf-8")

        snapshot = capture_snapshot(self.repo, self.baseline)
        self.assertEqual(
            [
                {
                    "content_digest": snapshot["untracked_files"][0]["content_digest"],
                    "intent": "snapshot-discovered product change",
                    "path": "nested/new.txt",
                    "source": "untracked",
                    "status": "untracked",
                }
            ],
            snapshot["changed_files"],
        )
        self.assertEqual([], validate_preflight(inspect_preflight(self.repo, self.baseline), ["nested\\new.txt"]))

    def test_invalid_baseline_is_rejected(self) -> None:
        with self.assertRaises(SnapshotError):
            capture_snapshot(self.repo, "not-a-commit")

    def test_snapshot_changed_files_are_valid_report_entries(self) -> None:
        (self.repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
        snapshot = capture_snapshot(self.repo, self.baseline)
        requirements = valid_requirements()
        report = {
            "baseline_head": snapshot["baseline_head"],
            "requirements_revision": 1,
            "requirements_digest": canonical_digest(requirements),
            "review_round": 0,
            "snapshot_digest": snapshot["snapshot_digest"],
            "tracked_diff_digest": snapshot["tracked_diff_digest"],
            "untracked_manifest_digest": snapshot["untracked_manifest_digest"],
            "changed_files": snapshot["changed_files"],
            "intent_summary": "Captured snapshot-discovered product changes.",
            "acceptance_evidence": {"AC-1": ["snapshot test"]},
            "test_commands": [
                {
                    "command": "python test_capture_snapshot.py -v",
                    "outcome": "PASS",
                    "output_summary": "snapshot tests pass",
                }
            ],
            "diff_evidence": [],
            "omissions": [],
            "unresolved_risks_or_blockers": [],
        }
        self.assertEqual([], validate_report(report, requirements))

    def test_snapshot_retries_when_tracked_state_drifts_mid_capture(self) -> None:
        tracked_diff_calls = 0
        original_run_git = snapshot_module.run_git

        def drifting_run_git(repository: Path, *args: str) -> bytes:
            nonlocal tracked_diff_calls
            result = original_run_git(repository, *args)
            if args[:3] == ("diff", "--binary", "--no-ext-diff"):
                tracked_diff_calls += 1
                if tracked_diff_calls == 1:
                    (self.repo / "app.py").write_text(
                        "print('drifted')\n", encoding="utf-8"
                    )
            return result

        with patch.object(snapshot_module, "run_git", side_effect=drifting_run_git):
            snapshot = capture_snapshot(self.repo, self.baseline)

        stable_snapshot = capture_snapshot(self.repo, self.baseline)
        self.assertGreaterEqual(tracked_diff_calls, 3)
        self.assertEqual(stable_snapshot, snapshot)

    def test_snapshot_brackets_a_mixed_component_sample_before_retrying(self) -> None:
        tracked_diff_calls = 0
        original_run_git = snapshot_module.run_git

        def drifting_run_git(repository: Path, *args: str) -> bytes:
            nonlocal tracked_diff_calls
            result = original_run_git(repository, *args)
            if args[:3] == ("diff", "--binary", "--no-ext-diff"):
                tracked_diff_calls += 1
                if tracked_diff_calls == 1:
                    (self.repo / "app.py").write_text(
                        "print('changed between observations')\n", encoding="utf-8"
                    )
            return result

        with patch.object(snapshot_module, "run_git", side_effect=drifting_run_git):
            snapshot = capture_snapshot(self.repo, self.baseline)

        stable_snapshot = capture_snapshot(self.repo, self.baseline)
        self.assertEqual(4, tracked_diff_calls)
        self.assertEqual(stable_snapshot, snapshot)


if __name__ == "__main__":
    unittest.main()
