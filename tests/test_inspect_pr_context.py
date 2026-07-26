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
                {
                    "user",
                    "upstream",
                    "origin-head",
                    "main-or-master",
                    "unresolved",
                },
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
            self.assertEqual("", context["headSha"])

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
            artifact_context = context["reviewArtifacts"][0]
            self.assertFalse(artifact_context["headMatches"])
            self.assertTrue(artifact_context["valid"])
            self.assertTrue(artifact_context["baseMatches"])

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
            self.assertFalse(context["isDefaultBranch"])

    def test_reports_unresolved_base_rather_than_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            git(repository, "init", "--initial-branch", "trunk", "--quiet")
            git(repository, "config", "user.email", "test@example.com")
            git(repository, "config", "user.name", "Test")
            (repository / "README.md").write_text("base\n", encoding="utf-8")
            git(repository, "add", "README.md")
            git(repository, "commit", "--quiet", "-m", "Initial commit")
            git(repository, "checkout", "--quiet", "-b", "feature")
            (repository / "feature.txt").write_text("work\n", encoding="utf-8")
            git(repository, "add", "feature.txt")
            git(
                repository,
                "commit",
                "--quiet",
                "-m",
                "Add feature\n\nCodex-Plan: plan-zeta",
            )
            context = self.module.inspect(repository)
            self.assertEqual("unresolved", context["baseResolution"])
            self.assertEqual("", context["baseRef"])
            self.assertEqual("", context["baseSha"])
            self.assertEqual("", context["mergeBaseSha"])
            self.assertFalse(context["isDefaultBranch"])
            self.assertEqual(0, context["commitsAhead"])
            self.assertEqual([], context["codexPlanIds"])

    def test_explicit_base_that_does_not_resolve_reports_empty_shas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            context = self.module.inspect(repository, base="does-not-exist")
            self.assertEqual("user", context["baseResolution"])
            self.assertEqual("", context["baseSha"])
            self.assertEqual("", context["mergeBaseSha"])

    def test_non_repository_directory_is_not_reported_as_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self.module.inspect(Path(directory))
            self.assertFalse(context["stagedDirty"])
            self.assertFalse(context["trackedDirty"])
            self.assertEqual("", context["headSha"])
            self.assertFalse(context["isDefaultBranch"])

    def test_resolves_base_from_local_main_without_remote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(repository, "checkout", "--quiet", "-b", "feature")
            context = self.module.inspect(repository)
            self.assertEqual("main-or-master", context["baseResolution"])
            self.assertEqual("main", context["baseRef"])

    def test_resolves_base_from_origin_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin_path = root / "origin"
            origin_path.mkdir()
            origin = make_repository(origin_path)
            repository = root / "clone"
            git(root, "clone", "--quiet", str(origin), str(repository))
            git(repository, "checkout", "--quiet", "-b", "feature")
            context = self.module.inspect(repository)
            self.assertEqual("origin-head", context["baseResolution"])
            self.assertEqual("main", context["baseRef"])

    def test_resolves_base_from_branch_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin_path = root / "origin"
            origin_path.mkdir()
            origin = make_repository(origin_path)
            repository = root / "clone"
            git(root, "clone", "--quiet", str(origin), str(repository))
            git(repository, "checkout", "--quiet", "-b", "feature")
            git(repository, "branch", "--set-upstream-to", "origin/main")
            context = self.module.inspect(repository)
            self.assertEqual("upstream", context["baseResolution"])
            self.assertEqual("main", context["baseRef"])

    def test_returns_exactly_the_contract_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            context = self.module.inspect(repository, base="main")
            self.assertEqual(
                {
                    "repository",
                    "headRef",
                    "headSha",
                    "baseRef",
                    "baseSha",
                    "baseResolution",
                    "baseProvisional",
                    "mergeBaseSha",
                    "isDefaultBranch",
                    "stagedDirty",
                    "trackedDirty",
                    "untrackedLocalEvidence",
                    "untrackedOther",
                    "commitsAhead",
                    "codexPlanIds",
                    "reviewArtifacts",
                },
                set(context),
            )


if __name__ == "__main__":
    unittest.main()
