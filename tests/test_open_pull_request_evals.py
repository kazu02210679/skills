from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = REPOSITORY_ROOT / "evals" / "open-pull-request"
BUILDER_PATH = EVAL_ROOT / "fixtures" / "build_repository.py"
RUNNER_PATH = EVAL_ROOT / "run.py"


def load(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class OpenPullRequestEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load(BUILDER_PATH, "open_pull_request_fixture_builder")
        cls.runner = load(RUNNER_PATH, "open_pull_request_eval_runner")

    def build(self, root: Path, specification: dict) -> Path:
        return self.builder.build_repository(specification, root / "repo")

    def test_builder_creates_head_branch_one_commit_ahead_of_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "defaultBranch": "main",
                    "headBranch": "feature",
                    "commits": [
                        {"message": "Add feature", "files": {"a.txt": "a\n"}}
                    ],
                },
            )

            branch = run_git(repository, "branch", "--show-current")
            ahead = run_git(repository, "rev-list", "--count", "main..HEAD")

            self.assertEqual(0, branch.returncode, branch.stderr)
            self.assertEqual("feature", branch.stdout.strip())
            self.assertEqual(0, ahead.returncode, ahead.stderr)
            self.assertEqual("1", ahead.stdout.strip())

    def test_builder_leaves_untracked_files_untracked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "untracked": {"src/new_feature.py": "answer = 42\n"},
                },
            )

            status = run_git(
                repository,
                "status",
                "--porcelain",
                "--untracked-files=all",
            )

            self.assertEqual(0, status.returncode, status.stderr)
            self.assertIn("?? src/new_feature.py", status.stdout.splitlines())

    def test_builder_creates_distinct_index_and_worktree_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "commits": [
                        {
                            "message": "Track source",
                            "files": {"tracked.txt": "original\n"},
                        }
                    ],
                    "staged": {"staged.txt": "staged\n"},
                    "modified": {"tracked.txt": "modified\n"},
                },
            )

            status = run_git(repository, "status", "--porcelain")

            self.assertEqual(0, status.returncode, status.stderr)
            self.assertEqual(
                {"A  staged.txt", " M tracked.txt"},
                set(status.stdout.splitlines()),
            )

    def test_remote_ancestor_two_is_ancestor_of_local_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "commits": [
                        {"message": "One", "files": {"one.txt": "1\n"}},
                        {"message": "Two", "files": {"two.txt": "2\n"}},
                        {"message": "Three", "files": {"three.txt": "3\n"}},
                    ],
                    "remote": {"headSha": "ancestor:2"},
                },
            )
            remote_head = run_git(repository, "rev-parse", "origin/feature")
            ancestry = run_git(
                repository,
                "merge-base",
                "--is-ancestor",
                remote_head.stdout.strip(),
                "HEAD",
            )

            self.assertEqual(0, remote_head.returncode, remote_head.stderr)
            self.assertEqual(0, ancestry.returncode, ancestry.stderr)

    def test_diverged_remote_head_is_not_ancestor_of_local_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "commits": [
                        {"message": "Local", "files": {"local.txt": "local\n"}}
                    ],
                    "remote": {"headSha": "diverged"},
                },
            )
            remote_head = run_git(repository, "rev-parse", "origin/feature")
            ancestry = run_git(
                repository,
                "merge-base",
                "--is-ancestor",
                remote_head.stdout.strip(),
                "HEAD",
            )

            self.assertEqual(0, remote_head.returncode, remote_head.stderr)
            self.assertEqual(1, ancestry.returncode, ancestry.stderr)

    def test_review_data_is_written_as_parseable_json(self) -> None:
        review = {"result": "approved", "verification": [{"status": "passed"}]}
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "reviewData": {"feature-review": review},
                },
            )

            review_path = (
                repository
                / "docs"
                / "reviews"
                / "feature-review"
                / "review-data.json"
            )
            self.assertEqual(
                review,
                json.loads(review_path.read_text(encoding="utf-8")),
            )

    def test_commit_trailers_appear_in_git_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "commits": [
                        {
                            "message": "Implement plan",
                            "files": {"plan.txt": "done\n"},
                            "trailers": {"Codex-Plan": "plan-alpha"},
                        }
                    ],
                },
            )

            log = run_git(repository, "log", "-1", "--format=%B")

            self.assertEqual(0, log.returncode, log.stderr)
            self.assertIn("Codex-Plan: plan-alpha", log.stdout)

    def test_windows_command_wrappers_contain_no_non_ascii_bytes(self) -> None:
        # cmd.exe reads a batch file in the OEM code page rather than UTF-8, so
        # a non-ASCII byte in one of these wrappers — an interpreter or script
        # path under a home directory with non-Latin characters, for instance —
        # is mis-decoded and the shim silently stops intercepting. CI runs on
        # Linux and never executes these files, so this is the only place that
        # failure can be caught.
        with tempfile.TemporaryDirectory() as directory:
            shim_directory = self.runner.write_command_shims(
                Path(directory) / "shims", {}
            )
            for tool in ("git", "gh"):
                wrapper = shim_directory / f"{tool}.cmd"
                content = wrapper.read_bytes()
                offending = [byte for byte in content if byte > 0x7F]
                self.assertEqual(
                    [],
                    offending,
                    f"{wrapper.name} must stay ASCII; found non-ASCII bytes "
                    f"{offending[:8]}",
                )

    def test_shim_intercepts_git_through_path_and_logs_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shim_directory = self.runner.write_command_shims(
                Path(directory) / "shims",
                {},
            )
            environment = os.environ.copy()
            environment["PATH"] = (
                str(shim_directory) + os.pathsep + environment["PATH"]
            )

            intercepted = subprocess.run(
                "git --version",
                env=environment,
                shell=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            calls = (shim_directory / "calls.log").read_text(encoding="utf-8")

            self.assertEqual(0, intercepted.returncode, intercepted.stderr)
            self.assertIn('"git", "--version"', calls)

    def test_shim_refuses_and_logs_git_push_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = self.build(
                root,
                {"headBranch": "feature", "remote": {"headSha": "equal"}},
            )
            shim_directory = self.runner.write_command_shims(root / "shims", {})
            environment = os.environ.copy()
            environment["PATH"] = (
                str(shim_directory) + os.pathsep + environment["PATH"]
            )

            push = subprocess.run(
                "git push origin HEAD:blocked",
                cwd=repository,
                env=environment,
                shell=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            calls = (shim_directory / "calls.log").read_text(encoding="utf-8")

            self.assertNotEqual(0, push.returncode)
            self.assertIn("blocked by open-pull-request evaluation shim", push.stderr)
            self.assertIn('"git", "push", "origin", "HEAD:blocked"', calls)

    def test_shim_allows_and_logs_git_push_when_mutations_are_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = self.build(
                root,
                {"headBranch": "feature", "remote": {"headSha": "equal"}},
            )
            shim_directory = self.runner.write_command_shims(
                root / "shims",
                {"allowMutations": True},
            )
            environment = os.environ.copy()
            environment["PATH"] = (
                str(shim_directory) + os.pathsep + environment["PATH"]
            )

            push = subprocess.run(
                "git push origin HEAD:allowed",
                cwd=repository,
                env=environment,
                shell=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            calls = (shim_directory / "calls.log").read_text(encoding="utf-8")
            published = run_git(
                repository,
                "--git-dir",
                str(root / "repo-remote.git"),
                "rev-parse",
                "refs/heads/allowed",
            )

            self.assertEqual(0, push.returncode, push.stderr)
            self.assertIn('"git", "push", "origin", "HEAD:allowed"', calls)
            self.assertEqual(0, published.returncode, published.stderr)


if __name__ == "__main__":
    unittest.main()
