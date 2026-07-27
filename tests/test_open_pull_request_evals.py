from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


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

    def test_every_case_has_an_input_and_a_fixture(self) -> None:
        criteria = yaml.safe_load(
            (EVAL_ROOT / "criteria.yaml").read_text(encoding="utf-8")
        )
        case_ids = set(criteria["cases"])
        self.assertEqual(14, len(case_ids))
        inputs = {path.stem for path in (EVAL_ROOT / "inputs").glob("*.md")}
        fixtures = {
            path.stem for path in (EVAL_ROOT / "fixtures").glob("case-*.json")
        }
        self.assertEqual(case_ids, inputs)
        self.assertEqual(case_ids, fixtures)

    def test_inputs_never_contain_pass_conditions(self) -> None:
        for path in (EVAL_ROOT / "inputs").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("pass_conditions", text)
            self.assertNotIn("Pass conditions", text)
            self.assertNotIn("criteria.yaml", text)

    def test_skill_forbids_dry_run_push_before_approval(self) -> None:
        skill = (
            REPOSITORY_ROOT / "skills" / "open-pull-request" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("`git push --dry-run` is still `git push`", skill)
        self.assertIn("Never use it before approval", skill)

    def test_skill_requires_reporting_refused_steps_after_recovery(self) -> None:
        skill = (
            REPOSITORY_ROOT / "skills" / "open-pull-request" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "Report every failed or policy-refused workflow step",
            skill,
        )
        self.assertIn("even when a later fallback succeeds", skill)

    def test_skill_does_not_call_a_worktree_clean_when_evidence_is_untracked(
        self,
    ) -> None:
        skill = (
            REPOSITORY_ROOT / "skills" / "open-pull-request" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "Never call the worktree clean while either untracked list is non-empty",
            skill,
        )
        self.assertIn("tracked changes are clean", skill)

    def test_every_declared_fixture_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in sorted((EVAL_ROOT / "fixtures").glob("case-*.json")):
                specification = json.loads(path.read_text(encoding="utf-8"))
                repository = self.builder.build_repository(
                    specification,
                    root / path.stem / "repo",
                )
                self.assertTrue(
                    (repository / ".git").is_dir(),
                    path.name,
                )

    def test_case_03_has_a_remote_push_target(self) -> None:
        specification = json.loads(
            (EVAL_ROOT / "fixtures" / "case-03.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual("ancestor:1", specification["remote"]["headSha"])

    def test_every_declared_fixture_passes_git_diff_check(self) -> None:
        # Python rewrites \n to \r\n when writing text on Windows, so fixture
        # files arrived with CRLF and `git diff --check` reported every added
        # line as trailing whitespace. The skill then paused over a failing
        # check the fixture had invented — correct behaviour, wrong premise.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in sorted((EVAL_ROOT / "fixtures").glob("case-*.json")):
                specification = json.loads(path.read_text(encoding="utf-8"))
                if not specification.get("commits"):
                    continue
                repository = self.builder.build_repository(
                    specification, root / path.stem / "repo"
                )
                base = specification.get("defaultBranch", "main")
                checked = run_git(
                    repository, "diff", "--check", f"{base}...HEAD"
                )
                self.assertEqual(
                    0, checked.returncode, f"{path.name}: {checked.stdout}"
                )

    def test_every_fixture_with_commits_ignores_python_bytecode(self) -> None:
        # Running the repository's tests generates __pycache__. Without an
        # ignore it shows up as an untracked file, and every "proceed" case
        # stops over a byproduct of its own verification step.
        for path in sorted((EVAL_ROOT / "fixtures").glob("case-*.json")):
            specification = json.loads(path.read_text(encoding="utf-8"))
            if not specification.get("commits"):
                continue
            committed = {
                name: content
                for commit in specification["commits"]
                for name, content in commit.get("files", {}).items()
            }
            self.assertIn(".gitignore", committed, path.name)
            self.assertIn("__pycache__/", committed[".gitignore"], path.name)

    def test_evaluator_prompt_includes_execution_evidence_and_log_scope(
        self,
    ) -> None:
        evidence = self.runner.extract_execution_evidence(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "python -m pytest",
                        "aggregated_output": "1 passed",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            )
            + "\n"
        )
        prompt = self.runner.build_evaluator_prompt(
            "case-03",
            "Push this and open a PR.",
            {},
            "Proposed body",
            '["git", "status"]\n',
            evidence,
            ["Report honestly."],
            ["Request approval."],
        )

        self.assertIn("execution_transcript", prompt)
        self.assertIn("python -m pytest", prompt)
        # The harness shares its environment with the candidate, so calls.log
        # is a superset of the candidate's actions. Mutations count wherever
        # they came from; a read is the candidate's only if the transcript
        # shows it. Without this the evaluator contradicted an accurate report
        # using a command the candidate never ran.
        self.assertIn("superset of what the candidate did", prompt)
        self.assertIn("counts regardless of which process issued it", prompt)
        # case-09 exercises publication, so a blanket "any mutation is a
        # violation" rule failed the very behaviour the case asks for.
        self.assertIn("allowMutations", prompt)
        self.assertIn("harness noise", prompt)

    def test_execution_evidence_includes_completed_file_changes(self) -> None:
        evidence = self.runner.extract_execution_evidence(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "file_change",
                        "changes": [
                            {
                                "path": "C:/tmp/pr-body.md",
                                "kind": "delete",
                            }
                        ],
                        "status": "completed",
                    },
                }
            )
            + "\n"
        )

        self.assertEqual("file_change", evidence[0]["type"])
        self.assertEqual("delete", evidence[0]["changes"][0]["kind"])

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

            # --is-ancestor alone is also true for `equal`, since a commit is
            # its own ancestor, so it would stay green if ancestor:N silently
            # regressed to publishing HEAD. Pin the distance too.
            distance = run_git(
                repository, "rev-list", "--count", "origin/feature..HEAD"
            )

            self.assertEqual(0, remote_head.returncode, remote_head.stderr)
            self.assertEqual(0, ancestry.returncode, ancestry.stderr)
            self.assertEqual("2", distance.stdout.strip())

    def test_diverged_remote_shares_a_base_with_local_head(self) -> None:
        # Real divergence shares history and then parts. A parentless commit
        # also fails --is-ancestor, but it is not a state the skill will meet.
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "commits": [
                        {"message": "Local", "files": {"local.txt": "l\n"}}
                    ],
                    "remote": {"headSha": "diverged"},
                },
            )
            merge_base = run_git(
                repository, "merge-base", "origin/feature", "HEAD"
            )

            self.assertEqual(0, merge_base.returncode, merge_base.stderr)
            self.assertTrue(merge_base.stdout.strip())

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

    def test_review_data_can_be_written_verbatim_for_malformed_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "reviewData": {"broken-review": "{ definitely not json"},
                },
            )
            review_path = (
                repository
                / "docs"
                / "reviews"
                / "broken-review"
                / "review-data.json"
            )
            self.assertEqual(
                "{ definitely not json",
                review_path.read_text(encoding="utf-8"),
            )

    def test_remote_base_can_advance_beyond_local_tracking_ref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "commits": [
                        {"message": "Feature", "files": {"feature.txt": "1\n"}}
                    ],
                    "remote": {"headSha": "equal", "baseAhead": 1},
                },
            )
            local_base = run_git(repository, "rev-parse", "origin/main")
            remote_base = run_git(
                repository,
                "ls-remote",
                "--refs",
                "origin",
                "refs/heads/main",
            )

            self.assertEqual(0, local_base.returncode, local_base.stderr)
            self.assertEqual(0, remote_base.returncode, remote_base.stderr)
            self.assertNotEqual(
                local_base.stdout.strip(),
                remote_base.stdout.split()[0],
            )

    def test_fork_fixture_has_distinct_origin_and_upstream_remotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "commits": [
                        {"message": "Feature", "files": {"feature.txt": "1\n"}}
                    ],
                    "remote": {"headSha": "equal", "fork": True},
                },
            )
            origin = run_git(repository, "remote", "get-url", "origin")
            upstream = run_git(repository, "remote", "get-url", "upstream")

            self.assertEqual(0, origin.returncode, origin.stderr)
            self.assertEqual(0, upstream.returncode, upstream.stderr)
            self.assertNotEqual(origin.stdout.strip(), upstream.stdout.strip())

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
                # The ASCII check alone does not hold on CI, where every path
                # happens to be ASCII already: reinstating an absolute
                # interpreter path would pass there and fail only on a machine
                # whose home directory is not Latin. Pin the mechanism instead
                # — %~dp0 is what keeps the path out of the file at all.
                text = content.decode("ascii")
                self.assertIn("%~dp0command_shim.py", text)
                self.assertNotIn(":\\", text)
                self.assertNotRegex(text, r'"\s*/')

    def test_shimmed_path_keeps_git_transport_helpers_reachable(self) -> None:
        # git-upload-pack and git-receive-pack live beside git itself, and the
        # real git resolves them from PATH. Dropping that directory to block a
        # bypass also broke every remote read, so the skill correctly refused
        # to publish against a remote it could not verify and the case failed
        # for a fixture reason. PATH order plus the compiled .exe shims is what
        # blocks the bypass now, so the directory must stay.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "realbin"
            real.mkdir()
            suffix = ".exe" if os.name == "nt" else ""
            for name in ("git", "git-upload-pack", "git-receive-pack"):
                executable = real / f"{name}{suffix}"
                executable.write_text("", encoding="utf-8")
                # shutil.which honours the executable bit on POSIX.
                executable.chmod(0o755)
            harmless = root / "otherbin"
            harmless.mkdir()
            shims = root / "shims"
            shims.mkdir()

            result = self.runner.shimmed_path(
                shims, os.pathsep.join([str(real), str(harmless)])
            )
            entries = result.split(os.pathsep)

            self.assertEqual(str(shims), entries[0])
            self.assertIn(str(real), entries)
            self.assertIn(str(harmless), entries)
            self.assertIsNotNone(
                shutil.which("git-upload-pack", path=result),
                "git transport helpers must stay reachable",
            )

    def test_candidate_environment_marks_sandbox_fixture_as_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shim_directory = self.runner.write_command_shims(
                Path(directory) / "shims", {}
            )

            environment = self.runner.build_candidate_environment(
                shim_directory,
            )

            self.assertEqual("1", environment["GIT_CONFIG_COUNT"])
            self.assertEqual("safe.directory", environment["GIT_CONFIG_KEY_0"])
            self.assertEqual("*", environment["GIT_CONFIG_VALUE_0"])

    def test_shimmed_path_preserves_order_on_every_platform(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "system-bin"
            real.mkdir()
            (real / "git").write_text("", encoding="utf-8")
            harmless = root / "other-bin"
            harmless.mkdir()
            shims = root / "shims"
            shims.mkdir()

            result = self.runner.shimmed_path(
                shims,
                os.pathsep.join([str(real), str(harmless)]),
            )

            self.assertEqual(
                [str(shims), str(real), str(harmless)],
                result.split(os.pathsep),
            )

    def test_intercept_assertion_rejects_a_bypassable_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shim_directory = self.runner.write_command_shims(
                Path(directory) / "shims", {}
            )
            environment = os.environ.copy()
            # The shim directory is absent from PATH, so nothing can intercept.
            with self.assertRaises(RuntimeError) as raised:
                self.runner.assert_shims_intercept(shim_directory, environment)
            self.assertIn("did not intercept", str(raised.exception))

    @unittest.skipUnless(os.name == "nt", "Windows-specific no-shell behavior")
    def test_intercept_assertion_accepts_executable_windows_shims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shim_directory = self.runner.write_command_shims(
                Path(directory) / "shims",
                {},
            )
            environment = self.runner.build_candidate_environment(shim_directory)

            self.runner.assert_shims_intercept(shim_directory, environment)

    def test_remote_fixture_configures_upstream_tracking(self) -> None:
        # The skill's inspector resolves the base from @{upstream} first and
        # only then from origin/HEAD. Without tracking, every case would
        # silently exercise the fallback instead of the preferred path.
        with tempfile.TemporaryDirectory() as directory:
            repository = self.build(
                Path(directory),
                {
                    "headBranch": "feature",
                    "commits": [
                        {"message": "Add feature", "files": {"a.txt": "a\n"}}
                    ],
                    "remote": {"headSha": "ancestor:1"},
                },
            )
            upstream = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "feature@{upstream}"],
                cwd=repository,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, upstream.returncode, upstream.stderr)
            self.assertEqual("origin/feature", upstream.stdout.strip())

    def test_calls_log_excludes_processes_without_the_run_token(self) -> None:
        # The shims sit on PATH, so anything started with this environment
        # reaches them. An unrelated `git ls-remote` once landed in calls.log
        # and the evaluator failed a case over a command the candidate never
        # ran. Only the candidate carries the token.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shim_directory = self.runner.write_command_shims(root / "shims", {})
            candidate = self.runner.build_candidate_environment(shim_directory)
            foreign = dict(candidate)
            foreign.pop("OPR_EVAL_RUN_TOKEN")

            for environment, marker in ((candidate, "rev-parse"), (foreign, "var")):
                subprocess.run(
                    f"git {marker} --help",
                    env=environment, shell=True, check=False,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )

            calls = (shim_directory / "calls.log").read_text(encoding="utf-8")
            foreign_calls = (
                shim_directory / "foreign-calls.log"
            ).read_text(encoding="utf-8")

            self.assertIn("rev-parse", calls)
            self.assertNotIn('"var"', calls)
            self.assertIn('"var"', foreign_calls)

    def test_candidate_environment_requires_built_shims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bare = Path(directory) / "shims"
            bare.mkdir()

            with self.assertRaises(RuntimeError) as raised:
                self.runner.build_candidate_environment(bare)

            self.assertIn("shim configuration", str(raised.exception))

    def test_both_remote_url_routes_report_the_modelled_forge_url(self) -> None:
        # The fixture pushes to a local bare path, so the config form reported
        # that path while `git remote get-url` reported the forge URL. The
        # inspector reads the config form, so the repository came back as a
        # filesystem path and the fork case had no owner to qualify its head.
        with tempfile.TemporaryDirectory() as directory:
            state = {
                "remoteUrls": {
                    "origin": "https://github.com/contributor/project.git"
                }
            }
            shim_directory = self.runner.write_command_shims(
                Path(directory) / "shims", state
            )
            environment = self.runner.build_candidate_environment(shim_directory)

            for command in (
                "git config --get remote.origin.url",
                "git remote get-url origin",
            ):
                result = subprocess.run(
                    command, env=environment, shell=True, text=True,
                    encoding="utf-8", errors="replace",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )
                self.assertEqual(
                    "https://github.com/contributor/project.git",
                    result.stdout.strip(),
                    command,
                )

            viewed = subprocess.run(
                "gh repo view contributor/project --json nameWithOwner",
                env=environment, shell=True, text=True,
                encoding="utf-8", errors="replace",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(
                "contributor/project",
                json.loads(viewed.stdout)["nameWithOwner"],
            )

    def test_gh_pr_view_returns_an_object_like_the_real_cli(self) -> None:
        # The real `gh pr view --json` returns one object. Echoing the list
        # payload taught the candidate a shape it will never meet in practice.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = {
                "pullRequests": [
                    {"number": 7, "state": "OPEN", "headRefName": "feature"}
                ]
            }
            shim_directory = self.runner.write_command_shims(root / "shims", state)
            environment = self.runner.build_candidate_environment(shim_directory)

            listed = subprocess.run(
                "gh pr list --json number",
                env=environment, shell=True, text=True,
                encoding="utf-8", errors="replace",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            viewed = subprocess.run(
                "gh pr view 7 --json number",
                env=environment, shell=True, text=True,
                encoding="utf-8", errors="replace",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )

            self.assertIsInstance(json.loads(listed.stdout), list)
            payload = json.loads(viewed.stdout)
            self.assertIsInstance(payload, dict)
            self.assertEqual(7, payload["number"])

    def test_gh_shim_refuses_commands_the_fixture_does_not_model(self) -> None:
        # An unmodelled gh command must never reach the operator's real,
        # authenticated gh — `gh pr merge` and `gh api -X POST` are outside the
        # mutation blocklist and would otherwise hit github.com for real.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shim_directory = self.runner.write_command_shims(root / "shims", {})
            environment = self.runner.build_candidate_environment(shim_directory)

            for command in ("gh pr merge 12 --squash", "gh api -X POST /repos"):
                result = subprocess.run(
                    command,
                    env=environment,
                    shell=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertNotEqual(0, result.returncode, command)
                self.assertIn("not modelled by the evaluation", result.stderr)

            calls = (shim_directory / "calls.log").read_text(encoding="utf-8")
            self.assertIn('"gh", "pr", "merge"', calls)

    def test_gh_shim_models_read_only_auth_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shim_directory = self.runner.write_command_shims(root / "shims", {})
            environment = self.runner.build_candidate_environment(shim_directory)

            result = subprocess.run(
                "gh auth status",
                env=environment,
                shell=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("github.com", result.stdout)

    def test_gh_shim_models_write_permission_for_publishable_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shim_directory = self.runner.write_command_shims(
                root / "shims",
                {"defaultBranch": "main", "viewerPermission": "WRITE"},
            )
            environment = self.runner.build_candidate_environment(shim_directory)

            result = subprocess.run(
                "gh repo view --json defaultBranchRef,viewerPermission",
                env=environment,
                shell=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("WRITE", json.loads(result.stdout)["viewerPermission"])

    def test_git_shim_models_public_remote_urls_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = self.build(
                root,
                {"headBranch": "feature", "remote": {"headSha": "equal"}},
            )
            shim_directory = self.runner.write_command_shims(
                root / "shims",
                {
                    "remoteUrls": {
                        "origin": "https://github.com/contributor/project.git",
                        "upstream": "https://github.com/upstream/project.git",
                    }
                },
            )
            environment = self.runner.build_candidate_environment(shim_directory)

            result = subprocess.run(
                "git remote get-url origin",
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

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                "https://github.com/contributor/project.git",
                result.stdout.strip(),
            )

    def test_shim_intercepts_git_through_path_and_logs_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shim_directory = self.runner.write_command_shims(
                Path(directory) / "shims",
                {},
            )
            environment = self.runner.build_candidate_environment(shim_directory)

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

    @unittest.skipUnless(os.name == "nt", "Windows-specific no-shell behavior")
    def test_shim_intercepts_git_without_a_shell_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shim_directory = self.runner.write_command_shims(
                Path(directory) / "shims",
                {},
            )
            environment = self.runner.build_candidate_environment(shim_directory)
            self.assertEqual(
                (shim_directory / "git.exe").resolve(),
                Path(shutil.which("git", path=environment["PATH"])).resolve(),
            )

            intercepted = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import subprocess,sys;"
                        "result=subprocess.run(['git','--version'],check=False);"
                        "sys.exit(result.returncode)"
                    ),
                ],
                env=environment,
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

    @unittest.skipUnless(os.name == "nt", "Windows-specific no-shell behavior")
    def test_windows_executable_shim_forwards_git_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = self.build(root, {"headBranch": "feature"})
            shim_directory = self.runner.write_command_shims(root / "shims", {})
            environment = self.runner.build_candidate_environment(shim_directory)

            forwarded = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import subprocess,sys;"
                        "result=subprocess.run("
                        "['git','branch','--show-current'],"
                        "text=True,capture_output=True,check=False"
                        ");"
                        "sys.stdout.write(result.stdout);"
                        "sys.stderr.write(result.stderr);"
                        "sys.exit(result.returncode)"
                    ),
                ],
                cwd=repository,
                env=environment,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, forwarded.returncode, forwarded.stderr)
            self.assertEqual("feature", forwarded.stdout.strip())
            forwarding = [
                json.loads(line)
                for line in (shim_directory / "forwarding.log")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(0, forwarding[-1]["returncode"])
            self.assertEqual("feature", forwarding[-1]["stdout"].strip())

    @unittest.skipUnless(os.name == "nt", "Windows-specific PowerShell behavior")
    def test_inspector_reads_repository_through_windows_shims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = self.build(root, {"headBranch": "feature"})
            shim_directory = self.runner.write_command_shims(root / "shims", {})
            environment = self.runner.build_candidate_environment(shim_directory)
            inspector = (
                REPOSITORY_ROOT
                / "skills"
                / "open-pull-request"
                / "scripts"
                / "inspect_pr_context.py"
            )

            inspected = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    (
                        "python "
                        f"'{inspector}' "
                        f"--repository '{repository}'"
                    ),
                ],
                cwd=root,
                env=environment,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, inspected.returncode, inspected.stderr)
            context = json.loads(inspected.stdout)
            self.assertEqual("feature", context["headRef"])
            self.assertTrue(context["headSha"])
            self.assertEqual("main", context["baseRef"])
            self.assertTrue(context["baseSha"])

    def test_shim_refuses_and_logs_git_push_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = self.build(
                root,
                {"headBranch": "feature", "remote": {"headSha": "equal"}},
            )
            shim_directory = self.runner.write_command_shims(root / "shims", {})
            environment = self.runner.build_candidate_environment(shim_directory)

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
            environment = self.runner.build_candidate_environment(shim_directory)

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
