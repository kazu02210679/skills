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

    def test_tracking_feature_branch_does_not_become_the_pull_request_base(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            make_repository(repository)
            remote = root / "remote.git"
            git(root, "init", "--bare", "--initial-branch", "main", str(remote))
            git(repository, "remote", "add", "origin", str(remote))
            git(repository, "push", "--quiet", "origin", "main")
            git(repository, "remote", "set-head", "origin", "main")
            git(repository, "checkout", "--quiet", "-b", "feature")
            (repository / "feature.txt").write_text("work\n", encoding="utf-8")
            git(repository, "add", "feature.txt")
            git(repository, "commit", "--quiet", "-m", "Add feature")
            git(repository, "push", "--quiet", "-u", "origin", "feature")

            context = self.module.inspect(repository)

            self.assertEqual("main", context["baseRef"])
            self.assertEqual("origin-head", context["baseResolution"])
            self.assertEqual(1, context["commitsAhead"])

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

    def test_ignores_codex_plan_labels_in_commit_body_prose(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(repository, "checkout", "--quiet", "-b", "feature")
            (repository / "feature.txt").write_text("first\n", encoding="utf-8")
            git(repository, "add", "feature.txt")
            git(
                repository,
                "commit",
                "--quiet",
                "-m",
                (
                    "Describe the plan\n\n"
                    "Codex-Plan: body-only\n\n"
                    "This paragraph proves the label is body prose, not a trailer."
                ),
            )
            (repository / "feature.txt").write_text("second\n", encoding="utf-8")
            git(repository, "add", "feature.txt")
            git(
                repository,
                "commit",
                "--quiet",
                "-m",
                "Implement the plan\n\nCodex-Plan: plan-real\nCodex-Task: T2",
            )

            context = self.module.inspect(repository, base="main")

            self.assertEqual(["plan-real"], context["codexPlanIds"])

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

    def test_display_ref_strips_any_remote_not_only_origin(self) -> None:
        # Stripping only `origin/` made a branch tracking `upstream/main`
        # report a base ref of `upstream/main`, which never equals the head
        # ref — so isDefaultBranch was false on the default branch itself and
        # the stop protecting the trunk did not fire.
        self.assertEqual(
            "main", self.module._display_ref("upstream/main", ["origin", "upstream"])
        )
        self.assertEqual("main", self.module._display_ref("refs/remotes/fork/main"))
        self.assertEqual("main", self.module._display_ref("refs/heads/main"))
        self.assertEqual(
            "feature/search",
            self.module._display_ref(
                "refs/remotes/origin/feature/search", ["origin"]
            ),
        )

    def test_reports_default_branch_when_upstream_is_another_remote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin_path = root / "origin"
            origin_path.mkdir()
            make_repository(origin_path)
            repository = root / "clone"
            git(root, "clone", "--quiet", str(origin_path), str(repository))
            git(repository, "remote", "rename", "origin", "upstream")
            git(repository, "fetch", "--quiet", "upstream")
            git(repository, "branch", "--set-upstream-to", "upstream/main", "main")

            context = self.module.inspect(repository)

            self.assertEqual("main", context["headRef"])
            self.assertEqual("main", context["baseRef"])
            self.assertTrue(context["isDefaultBranch"])

    def test_collects_plan_trailers_without_the_git_2_24_placeholder(self) -> None:
        # Parsing bodies here rather than asking git for %(trailers:key=...)
        # keeps the answer correct on git older than 2.24, where that
        # placeholder is emitted literally and every commit looks
        # trailer-free — an empty list meaning "no plans" instead of "cannot
        # answer".
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(repository, "checkout", "--quiet", "-b", "feature")
            for index, plan in enumerate(("plan-alpha", "plan-beta", "plan-alpha")):
                path = repository / f"f{index}.txt"
                path.write_text("x\n", encoding="utf-8")
                git(repository, "add", str(path.name))
                git(
                    repository,
                    "commit",
                    "--quiet",
                    "-m",
                    f"Work {index}\n\nCodex-Plan: {plan}\nCodex-Task: T{index}",
                )

            context = self.module.inspect(repository, base="main")

            self.assertEqual(["plan-alpha", "plan-beta"], context["codexPlanIds"])

    def test_repository_label_does_not_invent_a_slug_from_a_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(repository, "remote", "add", "origin", "/srv/git/acme-widgets.git")

            label = self.module.inspect(repository, base="main")["repository"]

            self.assertNotEqual("git/acme-widgets", label)
            self.assertEqual(str(Path(repository).resolve()), label)

    def test_repository_label_keeps_forge_slugs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(
                repository,
                "remote",
                "add",
                "origin",
                "https://github.com/example/project.git",
            )

            self.assertEqual(
                "example/project",
                self.module.inspect(repository, base="main")["repository"],
            )

    def test_repository_label_keeps_scp_style_slugs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = make_repository(Path(directory))
            git(repository, "remote", "add", "origin", "git@github.com:example/project.git")

            self.assertEqual(
                "example/project",
                self.module.inspect(repository, base="main")["repository"],
            )


if __name__ == "__main__":
    unittest.main()
