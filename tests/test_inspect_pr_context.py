from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPOSITORY_ROOT / "skills" / "open-pull-request" / "scripts" / "inspect_pr_context.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("inspect_pr_context", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
    )
    return result.stdout.strip()


def make_repository(directory: Path) -> Path:
    git(directory, "init", "--initial-branch", "main", "--quiet")
    git(directory, "config", "user.email", "test@example.com")
    git(directory, "config", "user.name", "Test")
    (directory / "README.md").write_text("base\n", encoding="utf-8")
    git(directory, "add", "README.md")
    git(directory, "commit", "--quiet", "-m", "Initial commit")
    return directory


class InspectContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_reports_default_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            context = self.module.inspect(repository, base="main")
            self.assertTrue(context["isDefaultBranch"])
            self.assertEqual(0, context["commitsAhead"])

    def test_counts_commits_ahead_on_feature_branch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(repository, "checkout", "--quiet", "-b", "feature")
            (repository / "feature.txt").write_text("work\n", encoding="utf-8")
            git(repository, "add", "feature.txt")
            git(repository, "commit", "--quiet", "-m", "Add feature")
            context = self.module.inspect(repository, base="main")
            self.assertFalse(context["isDefaultBranch"])
            self.assertEqual(1, context["commitsAhead"])
            self.assertEqual("feature", context["headRef"])
            self.assertEqual(
                git(repository, "rev-parse", "HEAD"), context["headSha"]
            )

    def test_separates_known_evidence_from_other_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            evidence = repository / "docs" / "reviews" / "slug"
            evidence.mkdir(parents=True)
            (evidence / "review-data.json").write_text("{}", encoding="utf-8")
            (repository / "src_new_feature.py").write_text("x = 1\n", encoding="utf-8")
            context = self.module.inspect(repository, base="main")
            self.assertEqual(
                ["docs/reviews/slug/review-data.json"],
                context["untrackedLocalEvidence"],
            )
            self.assertEqual(["src_new_feature.py"], context["untrackedOther"])

    def test_reports_tracked_and_staged_dirtiness_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            (repository / "README.md").write_text("changed\n", encoding="utf-8")
            context = self.module.inspect(repository, base="main")
            self.assertTrue(context["trackedDirty"])
            self.assertFalse(context["stagedDirty"])
            git(repository, "add", "README.md")
            context = self.module.inspect(repository, base="main")
            self.assertTrue(context["stagedDirty"])

    def test_marks_base_provisional_without_remote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            context = self.module.inspect(repository)
            self.assertTrue(context["baseProvisional"])
            self.assertIn(
                context["baseResolution"],
                {"user", "upstream", "origin-head", "main-or-master"},
            )

    def test_collects_codex_plan_ids_from_trailers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(repository, "checkout", "--quiet", "-b", "feature")
            (repository / "feature.txt").write_text("work\n", encoding="utf-8")
            git(repository, "add", "feature.txt")
            git(
                repository,
                "commit",
                "--quiet",
                "-m",
                "Add feature\n\nCodex-Plan: plan-alpha\nCodex-Task: T1",
            )
            context = self.module.inspect(repository, base="main")
            self.assertEqual(["plan-alpha"], context["codexPlanIds"])

    def test_reports_zero_commits_ahead_for_unborn_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            git(repository, "init", "--initial-branch", "main", "--quiet")
            context = self.module.inspect(repository, base="main")
            self.assertEqual(0, context["commitsAhead"])

    def test_lists_malformed_review_artifact_as_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            artifact = repository / "docs" / "reviews" / "broken"
            artifact.mkdir(parents=True)
            (artifact / "review-data.json").write_text("{", encoding="utf-8")
            context = self.module.inspect(repository, base="main")
            self.assertEqual(
                [
                    {
                        "path": "docs/reviews/broken/review-data.json",
                        "valid": False,
                        "headMatches": False,
                        "baseMatches": False,
                    }
                ],
                context["reviewArtifacts"],
            )

    def test_worktree_review_head_never_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            artifact = repository / "docs" / "reviews" / "worktree"
            artifact.mkdir(parents=True)
            (artifact / "review-data.json").write_text(
                '{"meta": {"base": "main", "head": "WORKTREE"}}',
                encoding="utf-8",
            )
            context = self.module.inspect(repository, base="main")
            self.assertFalse(context["reviewArtifacts"][0]["headMatches"])

    def test_classifies_untracked_review_and_source_paths_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            artifact = repository / "docs" / "reviews" / "slug"
            artifact.mkdir(parents=True)
            (artifact / "notes.txt").write_text("notes\n", encoding="utf-8")
            source = repository / "src"
            source.mkdir()
            (source / "new_feature.py").write_text("x = 1\n", encoding="utf-8")
            context = self.module.inspect(repository, base="main")
            self.assertEqual(
                ["docs/reviews/slug/notes.txt"],
                context["untrackedLocalEvidence"],
            )
            self.assertEqual(["src/new_feature.py"], context["untrackedOther"])

    def test_detached_head_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(repository, "checkout", "--quiet", "--detach")
            context = self.module.inspect(repository, base="main")
            self.assertEqual(git(repository, "rev-parse", "HEAD"), context["headSha"])


if __name__ == "__main__":
    unittest.main()
