"""Unit tests for deterministic GPT Pro Codex Loop product snapshots."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "gpt-pro-codex-loop"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIRECTORY))

from capture_snapshot import (  # noqa: E402
    SnapshotError,
    capture_snapshot,
    inspect_preflight,
    validate_preflight,
)


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

    def test_renamed_files_have_normalized_manifest_entries(self) -> None:
        (self.repo / "old.txt").rename(self.repo / "renamed.txt")
        run_git(self.repo, "add", "-A")
        snapshot = capture_snapshot(self.repo, self.baseline)
        self.assertIn(
            {
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


if __name__ == "__main__":
    unittest.main()
