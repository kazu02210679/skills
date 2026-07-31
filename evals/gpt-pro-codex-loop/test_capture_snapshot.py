"""Unit tests for deterministic GPT Pro Codex Loop product snapshots."""

from __future__ import annotations

import json
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


def capture(repository: Path, baseline: str) -> dict[str, object]:
    preflight = inspect_preflight(repository, baseline)
    return capture_snapshot(repository, baseline, preflight)


class CaptureSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name) / "repository"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "config", "user.email", "test@example.invalid")
        run_git(self.repo, "config", "user.name", "Snapshot Test")
        run_git(self.repo, "config", "core.autocrlf", "false")
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
        preflight = inspect_preflight(self.repo, self.baseline)
        first = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertEqual(
            first["preflight_digest"],
            canonical_digest(preflight),
        )
        (self.repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
        second = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertNotEqual(first["snapshot_digest"], second["snapshot_digest"])

    def test_snapshot_changes_when_untracked_content_changes(self) -> None:
        path = self.repo / "new.txt"
        path.write_text("one\n", encoding="utf-8")
        preflight = inspect_preflight(self.repo, self.baseline)
        first = capture_snapshot(self.repo, self.baseline, preflight)
        path.write_text("two\n", encoding="utf-8")
        second = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertNotEqual(first["snapshot_digest"], second["snapshot_digest"])

    def test_tracked_or_staged_run_metadata_is_rejected(self) -> None:
        metadata = self.repo / ".ai-pro-loop" / "task" / "state.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("{}\n", encoding="utf-8")
        run_git(self.repo, "add", str(metadata))
        with self.assertRaises(SnapshotError):
            capture(self.repo, self.baseline)

    def test_staged_case_variant_metadata_follows_filesystem_case_rules(self) -> None:
        metadata = self.repo / ".AI-PRO-LOOP" / "task" / "state.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("{}\n", encoding="utf-8")
        aliases_metadata_directory = (self.repo / ".ai-pro-loop").exists()
        run_git(self.repo, "add", str(metadata))

        if aliases_metadata_directory:
            with self.assertRaises(SnapshotError):
                capture(self.repo, self.baseline)
        else:
            snapshot = capture(self.repo, self.baseline)
            self.assertIn(".AI-PRO-LOOP/task/state.json", [item["path"] for item in snapshot["changed_files"]])

    def test_untracked_case_variant_metadata_follows_filesystem_case_rules(self) -> None:
        metadata = self.repo / ".AI-PRO-LOOP" / "task" / "state.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("{}\n", encoding="utf-8")
        aliases_metadata_directory = (self.repo / ".ai-pro-loop").exists()

        snapshot = capture(self.repo, self.baseline)
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
                capture(self.repo, baseline)
        else:
            snapshot = capture(self.repo, baseline)
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

        snapshot = capture(self.repo, self.baseline)
        self.assertIn(
            ".AI-PRO-LOOP/task/product.txt",
            [item["path"] for item in snapshot["changed_files"]],
        )

    def test_renamed_files_have_normalized_manifest_entries(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        (self.repo / "old.txt").rename(self.repo / "renamed.txt")
        run_git(self.repo, "add", "-A")
        snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        renamed = next(
            item for item in snapshot["changed_files"] if item["path"] == "renamed.txt"
        )
        self.assertEqual("old.txt", renamed["previous_path"])
        self.assertEqual("renamed", renamed["status"])
        self.assertTrue(renamed["changed_since_preflight"])

    def test_untouched_preexisting_rename_is_not_claimed_as_loop_change(self) -> None:
        (self.repo / "old.txt").rename(self.repo / "renamed.txt")
        run_git(self.repo, "add", "-A")
        preflight = inspect_preflight(self.repo, self.baseline)
        snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        renamed = next(
            item for item in snapshot["changed_files"] if item["path"] == "renamed.txt"
        )
        self.assertTrue(renamed["preexisting"])
        self.assertFalse(renamed["changed_since_preflight"])

    def test_binary_tracked_content_changes_the_snapshot(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        first = capture_snapshot(self.repo, self.baseline, preflight)
        (self.repo / "blob.bin").write_bytes(b"\x00changed\xfe")
        second = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertNotEqual(first["tracked_diff_digest"], second["tracked_diff_digest"])

    def test_ignored_files_are_not_in_the_product_snapshot(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        first = capture_snapshot(self.repo, self.baseline, preflight)
        (self.repo / "ignored.txt").write_text("ignored\n", encoding="utf-8")
        second = capture_snapshot(self.repo, self.baseline, preflight)
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

        snapshot = capture(self.repo, self.baseline)
        self.assertEqual(
            [
                {
                    "content_digest": snapshot["untracked_files"][0]["content_digest"],
                    "changed_since_preflight": False,
                    "intent": "snapshot-discovered product change",
                    "path": "nested/new.txt",
                    "preexisting": True,
                    "source": "untracked",
                    "status": "untracked",
                }
            ],
            snapshot["changed_files"],
        )
        self.assertEqual([], validate_preflight(inspect_preflight(self.repo, self.baseline), ["nested\\new.txt"]))

    def test_invalid_baseline_is_rejected(self) -> None:
        with self.assertRaises(SnapshotError):
            capture_snapshot(self.repo, "not-a-commit", {})

    def test_snapshot_changed_files_are_valid_report_entries(self) -> None:
        (self.repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
        snapshot = capture(self.repo, self.baseline)
        requirements = valid_requirements()
        report = {
            "schema_version": 1,
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

    def test_preflight_and_snapshot_use_versioned_canonical_digest_formula(self) -> None:
        (self.repo / "app.py").write_text("print('pre-existing')\n", encoding="utf-8")
        preflight = inspect_preflight(self.repo, self.baseline)
        self.assertEqual(1, preflight["schema_version"])
        self.assertEqual(
            canonical_digest(
                {
                    "schema_version": 1,
                    "baseline_head": self.baseline,
                    "tracked_manifest_digest": preflight["tracked_manifest_digest"],
                    "untracked_manifest_digest": preflight["untracked_manifest_digest"],
                }
            ),
            preflight["baseline_snapshot_digest"],
        )
        snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertEqual(1, snapshot["schema_version"])
        self.assertEqual(
            canonical_digest(
                {
                    "schema_version": 1,
                    "baseline_head": self.baseline,
                    "baseline_snapshot_digest": preflight["baseline_snapshot_digest"],
                    "tracked_manifest_digest": snapshot["tracked_manifest_digest"],
                    "untracked_manifest_digest": snapshot["untracked_manifest_digest"],
                }
            ),
            snapshot["snapshot_digest"],
        )

    def test_dirty_baseline_is_immutable_and_attribution_is_explicit(self) -> None:
        (self.repo / "app.py").write_text("print('pre-existing')\n", encoding="utf-8")
        (self.repo / "existing.txt").write_text("one\n", encoding="utf-8")
        preflight = inspect_preflight(self.repo, self.baseline)
        first = capture_snapshot(self.repo, self.baseline, preflight)
        by_path = {item["path"]: item for item in first["changed_files"]}
        self.assertTrue(by_path["app.py"]["preexisting"])
        self.assertFalse(by_path["app.py"]["changed_since_preflight"])
        self.assertTrue(by_path["existing.txt"]["preexisting"])
        self.assertFalse(by_path["existing.txt"]["changed_since_preflight"])

        (self.repo / "app.py").write_text("print('loop')\n", encoding="utf-8")
        (self.repo / "existing.txt").write_text("two\n", encoding="utf-8")
        (self.repo / "new.txt").write_text("new\n", encoding="utf-8")
        second = capture_snapshot(self.repo, self.baseline, preflight)
        by_path = {item["path"]: item for item in second["changed_files"]}
        self.assertTrue(by_path["app.py"]["preexisting"])
        self.assertTrue(by_path["app.py"]["changed_since_preflight"])
        self.assertTrue(by_path["existing.txt"]["preexisting"])
        self.assertTrue(by_path["existing.txt"]["changed_since_preflight"])
        self.assertFalse(by_path["new.txt"]["preexisting"])
        self.assertTrue(by_path["new.txt"]["changed_since_preflight"])

    def test_preflight_rejects_path_only_tampering_and_wrong_baseline(self) -> None:
        path_only = {
            "baseline_head": self.baseline,
            "initial_product_paths": [],
        }
        self.assertTrue(validate_preflight(path_only, []))

        preflight = inspect_preflight(self.repo, self.baseline)
        tampered = json.loads(json.dumps(preflight))
        tampered["baseline_snapshot_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(SnapshotError, "preflight"):
            capture_snapshot(self.repo, self.baseline, tampered)
        (self.repo / "later.txt").write_text("later\n", encoding="utf-8")
        run_git(self.repo, "add", "later.txt")
        run_git(self.repo, "commit", "-qm", "later baseline")
        with self.assertRaisesRegex(SnapshotError, "baseline"):
            capture_snapshot(self.repo, "HEAD", preflight)

    def test_tracked_manifest_records_baseline_index_and_worktree_states(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        (self.repo / "app.py").write_text("print('staged')\n", encoding="utf-8")
        run_git(self.repo, "add", "app.py")
        (self.repo / "app.py").write_text("print('worktree')\n", encoding="utf-8")
        snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        entry = next(item for item in snapshot["tracked_files"] if item["path"] == "app.py")
        self.assertNotEqual(entry["baseline"], entry["index"])
        self.assertNotEqual(entry["index"], entry["worktree"])
        self.assertEqual("file", entry["baseline"]["kind"])
        self.assertEqual("file", entry["index"]["kind"])
        self.assertEqual("file", entry["worktree"]["kind"])

    def test_staged_only_and_unstaged_only_states_remain_distinct(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        (self.repo / "app.py").write_text("print('unstaged')\n", encoding="utf-8")
        unstaged = capture_snapshot(self.repo, self.baseline, preflight)
        entry = next(item for item in unstaged["tracked_files"] if item["path"] == "app.py")
        self.assertEqual(entry["baseline"], entry["index"])
        self.assertNotEqual(entry["index"], entry["worktree"])

        run_git(self.repo, "add", "app.py")
        staged = capture_snapshot(self.repo, self.baseline, preflight)
        entry = next(item for item in staged["tracked_files"] if item["path"] == "app.py")
        self.assertNotEqual(entry["baseline"], entry["index"])
        self.assertEqual(entry["index"], entry["worktree"])

    def test_delete_and_type_change_are_manifest_identity(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        (self.repo / "old.txt").unlink()
        snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        deleted = next(item for item in snapshot["tracked_files"] if item["path"] == "old.txt")
        self.assertIsNotNone(deleted["baseline"])
        self.assertIsNotNone(deleted["index"])
        self.assertIsNone(deleted["worktree"])

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_symlink_target_bytes_are_snapshot_identity(self) -> None:
        link = self.repo / "link"
        try:
            link.symlink_to("one")
        except OSError:
            self.skipTest("symlink creation is not permitted")
        run_git(self.repo, "add", "link")
        run_git(self.repo, "commit", "-qm", "symlink baseline")
        baseline = run_git(self.repo, "rev-parse", "HEAD").decode().strip()
        preflight = inspect_preflight(self.repo, baseline)
        link.unlink()
        link.symlink_to("two")
        snapshot = capture_snapshot(self.repo, baseline, preflight)
        entry = next(item for item in snapshot["tracked_files"] if item["path"] == "link")
        self.assertEqual("symlink", entry["baseline"]["kind"])
        self.assertEqual("symlink", entry["worktree"]["kind"])
        self.assertNotEqual(
            entry["baseline"]["content_digest"], entry["worktree"]["content_digest"]
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_type_change_and_untracked_symlink_do_not_follow_target(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        (self.repo / "app.py").unlink()
        external = Path(self.temporary_directory.name) / "external-secret.txt"
        external.write_text("must not be read\n", encoding="utf-8")
        try:
            (self.repo / "app.py").symlink_to(external)
            (self.repo / "outside-link").symlink_to(external)
        except OSError:
            self.skipTest("symlink creation is not permitted")
        snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        tracked = next(item for item in snapshot["tracked_files"] if item["path"] == "app.py")
        self.assertEqual("file", tracked["baseline"]["kind"])
        self.assertEqual("symlink", tracked["worktree"]["kind"])
        untracked = next(item for item in snapshot["untracked_files"] if item["path"] == "outside-link")
        self.assertEqual("symlink", untracked["kind"])
        self.assertEqual(
            "sha256:" + __import__("hashlib").sha256(os.readlink(self.repo / "outside-link").encode()).hexdigest(),
            untracked["content_digest"],
        )

    def test_submodule_pointer_is_identity_and_dirty_submodule_fails_closed(self) -> None:
        source = Path(self.temporary_directory.name) / "submodule-source"
        source.mkdir()
        run_git(source, "init", "-q")
        run_git(source, "config", "user.email", "test@example.invalid")
        run_git(source, "config", "user.name", "Submodule Test")
        run_git(source, "config", "core.autocrlf", "false")
        (source / "value.txt").write_text("one\n", encoding="utf-8")
        run_git(source, "add", ".")
        run_git(source, "commit", "-qm", "submodule baseline")
        nested = self.repo / "vendor" / "sub"
        nested.parent.mkdir()
        cloned = subprocess.run(
            ["git", "clone", "-q", str(source), str(nested)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, cloned.returncode, cloned.stderr.decode())
        run_git(self.repo, "add", "vendor/sub")
        run_git(self.repo, "commit", "-qam", "add submodule")
        baseline = run_git(self.repo, "rev-parse", "HEAD").decode().strip()
        preflight = inspect_preflight(self.repo, baseline)

        (nested / "value.txt").write_text("two\n", encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "dirty submodule"):
            capture_snapshot(self.repo, baseline, preflight)

        run_git(nested, "config", "user.email", "test@example.invalid")
        run_git(nested, "config", "user.name", "Nested Test")
        run_git(nested, "add", "value.txt")
        run_git(nested, "commit", "-qm", "advance submodule")
        snapshot = capture_snapshot(self.repo, baseline, preflight)
        entry = next(item for item in snapshot["tracked_files"] if item["path"] == "vendor/sub")
        self.assertEqual("submodule", entry["baseline"]["kind"])
        self.assertEqual("submodule", entry["worktree"]["kind"])
        self.assertNotEqual(
            entry["baseline"]["content_digest"], entry["worktree"]["content_digest"]
        )

    @unittest.skipUnless(os.name == "posix", "requires POSIX executable mode")
    def test_mode_only_change_is_snapshot_identity(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        os.chmod(self.repo / "app.py", 0o755)
        snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        entry = next(item for item in snapshot["tracked_files"] if item["path"] == "app.py")
        self.assertNotEqual(entry["baseline"]["mode"], entry["worktree"]["mode"])

    def test_unmerged_index_is_rejected(self) -> None:
        run_git(self.repo, "checkout", "-qb", "other")
        (self.repo / "app.py").write_text("print('other')\n", encoding="utf-8")
        run_git(self.repo, "commit", "-qam", "other")
        run_git(self.repo, "checkout", "-q", "-")
        (self.repo / "app.py").write_text("print('main')\n", encoding="utf-8")
        run_git(self.repo, "commit", "-qam", "main")
        subprocess.run(
            ["git", "-C", str(self.repo), "merge", "other"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        with self.assertRaisesRegex(SnapshotError, "unmerged"):
            inspect_preflight(self.repo, self.baseline)

    def test_raw_diff_bytes_do_not_define_snapshot_identity(self) -> None:
        (self.repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
        preflight = inspect_preflight(self.repo, self.baseline)
        normal = capture_snapshot(self.repo, self.baseline, preflight)
        original_run_git = snapshot_module.run_git

        def altered_diff(repository: Path, *args: str) -> bytes:
            result = original_run_git(repository, *args)
            if args and args[0] == "-c" and "diff" in args and "--binary" in args:
                return result + b"\nreview-only-diff-presentation\n"
            return result

        with patch.object(snapshot_module, "run_git", side_effect=altered_diff):
            altered = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertNotEqual(normal["tracked_diff_digest"], altered["tracked_diff_digest"])
        self.assertEqual(normal["snapshot_digest"], altered["snapshot_digest"])

    def test_host_diff_configuration_does_not_change_manifest_identity(self) -> None:
        (self.repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
        preflight = inspect_preflight(self.repo, self.baseline)
        before = capture_snapshot(self.repo, self.baseline, preflight)
        run_git(self.repo, "config", "diff.renames", "copies")
        run_git(self.repo, "config", "color.ui", "always")
        run_git(self.repo, "config", "core.quotepath", "true")
        after = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertEqual(before["tracked_files"], after["tracked_files"])
        self.assertEqual(before["snapshot_digest"], after["snapshot_digest"])

    def test_preflight_is_closed_versioned_and_manifest_bound(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        boolean_version = json.loads(json.dumps(preflight))
        boolean_version["schema_version"] = True
        self.assertTrue(validate_preflight(boolean_version, []))
        unknown = json.loads(json.dumps(preflight))
        unknown["extra"] = "unsafe"
        self.assertTrue(validate_preflight(unknown, []))
        if preflight["tracked_files"]:
            self.fail("clean preflight unexpectedly contains tracked files")
        (self.repo / "new.txt").write_text("new\n", encoding="utf-8")
        dirty = inspect_preflight(self.repo, self.baseline)
        tampered = json.loads(json.dumps(dirty))
        tampered["untracked_files"][0]["content_digest"] = "sha256:" + "0" * 64
        self.assertTrue(validate_preflight(tampered, ["new.txt"]))
        derived = json.loads(json.dumps(dirty))
        derived["initial_product_paths"] = []
        self.assertTrue(validate_preflight(derived, []))
        noncanonical = json.loads(json.dumps(preflight))
        noncanonical["baseline_head"] = "HEAD"
        noncanonical["baseline_snapshot_digest"] = canonical_digest(
            {
                "schema_version": 1,
                "baseline_head": "HEAD",
                "tracked_manifest_digest": noncanonical["tracked_manifest_digest"],
                "untracked_manifest_digest": noncanonical["untracked_manifest_digest"],
            }
        )
        self.assertTrue(validate_preflight(noncanonical, []))

    def test_cli_commands_emit_canonical_json_and_fail_closed(self) -> None:
        script = SCRIPT_DIRECTORY / "capture_snapshot.py"
        inspect = subprocess.run(
            [sys.executable, str(script), "inspect-preflight", str(self.repo), self.baseline],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, inspect.returncode, inspect.stderr.decode())
        self.assertEqual(b"\n", inspect.stdout[-1:])
        preflight = json.loads(inspect.stdout)
        packet = Path(self.temporary_directory.name) / "preflight.json"
        packet.write_bytes(inspect.stdout)

        validate = subprocess.run(
            [
                sys.executable,
                str(script),
                "validate-preflight",
                str(packet),
                "--repository",
                str(self.repo),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, validate.returncode, validate.stderr.decode())
        self.assertEqual(preflight, json.loads(validate.stdout))

        captured = subprocess.run(
            [
                sys.executable,
                str(script),
                "capture",
                str(self.repo),
                self.baseline,
                "--preflight",
                str(packet),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, captured.returncode, captured.stderr.decode())
        self.assertEqual(1, json.loads(captured.stdout)["schema_version"])

        bad = subprocess.run(
            [sys.executable, str(script), "capture", str(self.repo), self.baseline],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(2, bad.returncode)
        self.assertEqual(b"", bad.stdout)
        self.assertTrue(bad.stderr)

    def test_validate_cli_requires_exact_approval_and_writes_no_partial_json(self) -> None:
        (self.repo / "app.py").write_text("print('pre-existing')\n", encoding="utf-8")
        script = SCRIPT_DIRECTORY / "capture_snapshot.py"
        preflight = inspect_preflight(self.repo, self.baseline)
        packet = Path(self.temporary_directory.name) / "dirty-preflight.json"
        packet.write_text(json.dumps(preflight), encoding="utf-8")
        rejected = subprocess.run(
            [
                sys.executable,
                str(script),
                "validate-preflight",
                str(packet),
                "--repository",
                str(self.repo),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(2, rejected.returncode)
        self.assertEqual(b"", rejected.stdout)
        self.assertIn(b"unapproved pre-existing product path: app.py", rejected.stderr)
        approved = subprocess.run(
            [
                sys.executable,
                str(script),
                "validate-preflight",
                str(packet),
                "--repository",
                str(self.repo),
                "--approved-existing-path",
                "app.py",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, approved.returncode, approved.stderr.decode())
        self.assertEqual(preflight, json.loads(approved.stdout))

    def test_snapshot_retries_when_tracked_state_drifts_mid_capture(self) -> None:
        tracked_diff_calls = 0
        original_run_git = snapshot_module.run_git
        preflight = inspect_preflight(self.repo, self.baseline)

        def drifting_run_git(repository: Path, *args: str) -> bytes:
            nonlocal tracked_diff_calls
            result = original_run_git(repository, *args)
            if args and args[0] == "-c" and "diff" in args and "--binary" in args:
                tracked_diff_calls += 1
                if tracked_diff_calls == 1:
                    (self.repo / "app.py").write_text(
                        "print('drifted')\n", encoding="utf-8"
                    )
            return result

        with patch.object(snapshot_module, "run_git", side_effect=drifting_run_git):
            snapshot = capture_snapshot(self.repo, self.baseline, preflight)

        stable_snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertGreaterEqual(tracked_diff_calls, 3)
        self.assertEqual(stable_snapshot, snapshot)

    def test_snapshot_brackets_a_mixed_component_sample_before_retrying(self) -> None:
        tracked_diff_calls = 0
        original_run_git = snapshot_module.run_git
        preflight = inspect_preflight(self.repo, self.baseline)

        def drifting_run_git(repository: Path, *args: str) -> bytes:
            nonlocal tracked_diff_calls
            result = original_run_git(repository, *args)
            if args and args[0] == "-c" and "diff" in args and "--binary" in args:
                tracked_diff_calls += 1
                if tracked_diff_calls == 1:
                    (self.repo / "app.py").write_text(
                        "print('changed between observations')\n", encoding="utf-8"
                    )
            return result

        with patch.object(snapshot_module, "run_git", side_effect=drifting_run_git):
            snapshot = capture_snapshot(self.repo, self.baseline, preflight)

        stable_snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertEqual(4, tracked_diff_calls)
        self.assertEqual(stable_snapshot, snapshot)

    def test_snapshot_retries_when_presentation_changes_after_identity_capture(self) -> None:
        preflight = inspect_preflight(self.repo, self.baseline)
        name_status_calls = 0
        original_run_git = snapshot_module.run_git

        def drifting_run_git(repository: Path, *args: str) -> bytes:
            nonlocal name_status_calls
            result = original_run_git(repository, *args)
            if "--name-status" in args:
                name_status_calls += 1
                if name_status_calls == 1:
                    (self.repo / "app.py").write_text(
                        "print('drift after presentation')\n", encoding="utf-8"
                    )
            return result

        with patch.object(snapshot_module, "run_git", side_effect=drifting_run_git):
            snapshot = capture_snapshot(self.repo, self.baseline, preflight)
        stable = capture_snapshot(self.repo, self.baseline, preflight)
        self.assertGreaterEqual(name_status_calls, 3)
        self.assertEqual(stable, snapshot)


if __name__ == "__main__":
    unittest.main()
