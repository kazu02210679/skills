#!/usr/bin/env python3
"""Run blind, candidate-pinned evaluations for the open-pull-request Skill."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


EVAL_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EVAL_ROOT.parents[1]
CANDIDATE_ROOT = REPOSITORY_ROOT / "skills" / "open-pull-request"
CANDIDATE_SKILL_PATH = CANDIDATE_ROOT / "SKILL.md"
CANDIDATE_SCRIPTS_PATH = CANDIDATE_ROOT / "scripts"
BUILDER_PATH = EVAL_ROOT / "fixtures" / "build_repository.py"


def _load_builder():
    specification = importlib.util.spec_from_file_location(
        "open_pull_request_fixture_builder",
        BUILDER_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Unable to load fixture builder: {BUILDER_PATH}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.build_repository


build_repository = _load_builder()


def build_execution_prompt(candidate_path: Path, input_path: Path) -> str:
    """Build the criteria-free prompt used in an isolated Git workspace."""

    return (
        "Follow the candidate Skill to handle the user's pull request request.\n"
        f"Read {candidate_path.as_posix()} completely, then read "
        f"{input_path.as_posix()}.\n"
        "The real Git fixture is the repository/ directory in this workspace. "
        "Run the Skill's inspector and any other commands it calls for against "
        "that repository, and produce the complete response to the user. "
        "Do not inspect files outside candidate/, inputs/, and repository/. "
        "Do not discuss evaluation rules."
    )


def build_evaluator_prompt(
    case_id: str,
    raw_input: str,
    fixture_specification: dict[str, Any],
    response: str,
    calls_log: str,
    execution_evidence: list[dict[str, Any]],
    universal_conditions: list[str],
    case_conditions: list[str],
) -> str:
    payload = {
        "case_id": case_id,
        "raw_input": raw_input,
        "fixture_specification": fixture_specification,
        "candidate_response": response,
        "calls_log": calls_log,
        "execution_transcript": execution_evidence,
        "universal_conditions": universal_conditions,
        "case_conditions": case_conditions,
    }
    return (
        "Act as a strict behavioral evaluator. Assess the supplied response and "
        "the observed command evidence against every supplied condition. "
        "calls.log records only Git and GitHub CLI commands and is authoritative "
        "for those commands. Use execution_transcript for all other commands; "
        "do not infer that a non-Git command was skipped merely because it is "
        "absent from calls.log. Return "
        "JSON with keys case_id, pass (boolean), and findings (array of concise "
        "strings). Do not infer omitted behavior as passing.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def extract_execution_evidence(transcript: str) -> list[dict[str, Any]]:
    """Extract completed command and file-change records from the transcript."""

    evidence: list[dict[str, Any]] = []
    for line in transcript.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "command_execution":
            evidence.append(
                {
                    "type": item_type,
                    **{
                        key: item.get(key)
                        for key in (
                            "command",
                            "aggregated_output",
                            "exit_code",
                            "status",
                        )
                    },
                }
            )
        elif item_type == "file_change":
            evidence.append(
                {
                    "type": item_type,
                    "changes": item.get("changes"),
                    "status": item.get("status"),
                }
            )
    return evidence


def build_evidence_manifest(
    *,
    candidate_commit: str,
    candidate_files_sha256: dict[str, str],
    codex_version: str,
    model: str,
    execution_prompts: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "commit": candidate_commit,
            "files_sha256": candidate_files_sha256,
        },
        "runtime": {
            "codex_version": codex_version,
            "model": model,
        },
        "execution_prompts": execution_prompts,
        "cases": {},
    }


def _write_windows_executable_shims(directory: Path) -> None:
    """Compile `.exe` launchers so CreateProcess cannot bypass the shims."""

    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    compiler_candidates = (
        windows
        / "Microsoft.NET"
        / framework
        / "v4.0.30319"
        / "csc.exe"
        for framework in ("Framework64", "Framework")
    )
    compiler = next(
        (candidate for candidate in compiler_candidates if candidate.is_file()),
        None,
    )
    if compiler is None:
        raise RuntimeError(
            "A Windows C# compiler is required to build no-shell command "
            "shims. Refusing to run an evaluation that CreateProcess can "
            "bypass."
        )

    source = r'''
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

public static class CommandShimLauncher
{
    private static string Quote(string value)
    {
        if (value.Length == 0)
        {
            return "\"\"";
        }
        if (value.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) < 0)
        {
            return value;
        }

        StringBuilder quoted = new StringBuilder("\"");
        int backslashes = 0;
        foreach (char character in value)
        {
            if (character == '\\')
            {
                backslashes += 1;
            }
            else if (character == '"')
            {
                quoted.Append('\\', backslashes * 2 + 1);
                quoted.Append('"');
                backslashes = 0;
            }
            else
            {
                quoted.Append('\\', backslashes);
                quoted.Append(character);
                backslashes = 0;
            }
        }
        quoted.Append('\\', backslashes * 2);
        quoted.Append('"');
        return quoted.ToString();
    }

    public static int Main(string[] arguments)
    {
        string executable = Environment.GetCommandLineArgs()[0];
        string tool = Path.GetFileNameWithoutExtension(executable).ToLowerInvariant();
        string script = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory,
            "command_shim.py"
        );

        StringBuilder childArguments = new StringBuilder(Quote(script));
        childArguments.Append(' ');
        childArguments.Append(Quote(tool));
        foreach (string argument in arguments)
        {
            childArguments.Append(' ');
            childArguments.Append(Quote(argument));
        }

        ProcessStartInfo start = new ProcessStartInfo(
            "python.exe",
            childArguments.ToString()
        );
        start.UseShellExecute = false;
        using (Process child = Process.Start(start))
        {
            child.WaitForExit();
            return child.ExitCode;
        }
    }
}
'''
    source_path = directory / "command_shim_launcher.cs"
    launcher_path = directory / "command_shim_launcher.exe"
    source_path.write_text(source, encoding="utf-8", newline="\n")
    compilation = subprocess.run(
        [
            str(compiler),
            "/nologo",
            "/target:exe",
            f"/out:{launcher_path}",
            str(source_path),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if compilation.returncode != 0 or not launcher_path.is_file():
        detail = compilation.stderr.strip() or compilation.stdout.strip()
        raise RuntimeError(f"Unable to compile Windows command shims: {detail}")
    for tool in ("git", "gh"):
        shutil.copy2(launcher_path, directory / f"{tool}.exe")


def write_command_shims(
    directory: Path,
    github_state: dict[str, Any],
) -> Path:
    """Write cross-platform Git and GitHub CLI wrappers into ``directory``."""

    directory.mkdir(parents=True, exist_ok=True)
    configuration = {
        "githubState": github_state,
        "realExecutables": {
            "git": shutil.which("git"),
            "gh": shutil.which("gh") or shutil.which("gh.exe"),
        },
    }
    (directory / "shim-config.json").write_text(
        json.dumps(configuration, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shim_program = r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


directory = Path(__file__).resolve().parent
configuration = json.loads(
    (directory / "shim-config.json").read_text(encoding="utf-8")
)
tool, *arguments = sys.argv[1:]
with (directory / "calls.log").open("a", encoding="utf-8", newline="\n") as log:
    log.write(json.dumps([tool, *arguments], ensure_ascii=False) + "\n")

state = configuration["githubState"]
is_git_push = tool == "git" and "push" in arguments
is_gh_mutation = tool == "gh" and any(
    arguments[index:index + 2] in (
        ["pr", "create"],
        ["pr", "edit"],
        ["pr", "ready"],
        ["pr", "reopen"],
    )
    for index in range(max(0, len(arguments) - 1))
)
if (is_git_push or is_gh_mutation) and not state.get("allowMutations", False):
    print(
        f"{tool} mutation blocked by open-pull-request evaluation shim",
        file=sys.stderr,
    )
    raise SystemExit(97)

if (
    tool == "git"
    and arguments[:2] == ["remote", "get-url"]
    and len(arguments) >= 3
):
    modelled_url = state.get("remoteUrls", {}).get(arguments[2])
    if modelled_url:
        print(modelled_url)
        raise SystemExit(0)

if tool == "gh" and arguments[:2] in (["pr", "list"], ["pr", "view"]):
    print(json.dumps(state.get("pullRequests", []), ensure_ascii=False))
    raise SystemExit(0)
if tool == "gh" and arguments[:2] == ["auth", "status"]:
    print("github.com: authenticated as open-pull-request-eval")
    raise SystemExit(0)
if tool == "gh" and arguments[:2] == ["repo", "view"]:
    print(
        json.dumps(
            {
                "defaultBranchRef": {
                    "name": state.get("defaultBranch", "main")
                },
                "viewerPermission": state.get("viewerPermission", "WRITE"),
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0)
if (
    tool == "gh"
    and arguments[:2] == ["pr", "create"]
    and state.get("failCreate", False)
):
    print("gh pr create forced to fail by evaluation fixture", file=sys.stderr)
    raise SystemExit(98)

if tool == "gh":
    # Everything the fixture models is answered above. Forwarding anything
    # else would hand the operator's real, authenticated gh to the candidate:
    # `gh pr merge` and `gh api -X POST` are not in the mutation blocklist and
    # would reach github.com for real. An evaluation must not be able to touch
    # anything outside its fixture, so unmodelled gh commands are refused.
    print(
        f"gh {' '.join(arguments[:2])} is not modelled by the evaluation "
        "fixture and was refused",
        file=sys.stderr,
    )
    raise SystemExit(96)

executable = configuration["realExecutables"].get(tool)
if not executable:
    print(f"real {tool} executable was not found", file=sys.stderr)
    raise SystemExit(127)
try:
    completed = subprocess.run(
        [executable, *arguments],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
except OSError as exc:
    forwarding = {
        "tool": tool,
        "arguments": arguments,
        "returncode": None,
        "stdout": "",
        "stderr": f"{type(exc).__name__}: {exc}",
    }
    with (directory / "forwarding.log").open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as log:
        log.write(json.dumps(forwarding, ensure_ascii=False) + "\n")
    print(forwarding["stderr"], file=sys.stderr)
    raise SystemExit(127)
forwarding = {
    "tool": tool,
    "arguments": arguments,
    "returncode": completed.returncode,
    "stdout": completed.stdout,
    "stderr": completed.stderr,
}
with (directory / "forwarding.log").open(
    "a",
    encoding="utf-8",
    newline="\n",
) as log:
    log.write(json.dumps(forwarding, ensure_ascii=False) + "\n")
sys.stdout.write(completed.stdout)
sys.stderr.write(completed.stderr)
raise SystemExit(completed.returncode)
'''
    script_path = directory / "command_shim.py"
    script_path.write_text(shim_program, encoding="utf-8", newline="\n")

    quoted_python = shlex.quote(sys.executable)
    quoted_script = shlex.quote(str(script_path))
    for tool in ("git", "gh"):
        shell_wrapper = directory / tool
        shell_wrapper.write_text(
            "#!/bin/sh\n"
            f"exec {quoted_python} {quoted_script} {tool} \"$@\"\n",
            encoding="utf-8",
            newline="\n",
        )
        shell_wrapper.chmod(0o755)
        # cmd.exe reads a batch file in the OEM code page, not UTF-8, so any
        # non-ASCII byte in it is mis-decoded and the interpreter path fails to
        # resolve. Keep the file pure ASCII: %~dp0 is expanded by cmd itself at
        # run time, and `python` is resolved from PATH, so neither the script
        # path nor the interpreter path is ever written into the file.
        command_wrapper = directory / f"{tool}.cmd"
        command_wrapper.write_text(
            f'@python "%~dp0{script_path.name}" {tool} %*\n',
            encoding="ascii",
            newline="\r\n",
        )
    if os.name == "nt":
        _write_windows_executable_shims(directory)
    (directory / "calls.log").touch()
    return directory


def shimmed_path(shim_directory: Path, original_path: str) -> str:
    """Put the shims first and leave the rest of PATH intact.

    Prepending alone was once not enough on Windows: `CreateProcess` appends
    `.exe` to a bare name, so `subprocess.run(["git", ...])` — the form the
    Skill's own inspector uses — walked past the extension-less shim and found
    the real `git.exe` further down PATH, mutating the remote without reaching
    calls.log. This function used to drop every directory holding a real git
    or gh so that a bypass failed loudly instead of succeeding silently.

    Compiled `git.exe` and `gh.exe` shims now sit in the shim directory and
    `write_command_shims` refuses to run without them, so PATH order alone
    decides and the removal is obsolete. Keeping it was actively harmful:
    `git-upload-pack` and `git-receive-pack` live beside `git.exe`, so
    dropping that directory left the real git unable to find its own transport
    helpers. Every remote read failed, and case-03 recorded the Skill
    correctly refusing to publish against a remote it could not verify — a
    fixture failure wearing the shape of a Skill failure.
    """

    return os.pathsep.join(
        [str(shim_directory)]
        + [entry for entry in original_path.split(os.pathsep) if entry]
    )


def build_candidate_environment(shim_directory: Path) -> dict[str, str]:
    """Build a hermetic environment for a sandbox-owned toy repository."""

    environment = os.environ.copy()
    environment["PATH"] = shimmed_path(
        shim_directory,
        environment.get("PATH", ""),
    )
    # Windows Codex commands run as a low-privilege sandbox account, while the
    # fixture is created by the host account. Mark only this evaluation process
    # as accepting such repositories; never mutate the user's global Git config.
    environment["GIT_CONFIG_COUNT"] = "1"
    environment["GIT_CONFIG_KEY_0"] = "safe.directory"
    environment["GIT_CONFIG_VALUE_0"] = "*"
    return environment


def assert_shims_intercept(
    shim_directory: Path,
    environment: dict[str, str],
) -> None:
    """Fail the run unless both spawn styles actually reach the shim.

    A shim that stops intercepting does not announce itself — the evaluation
    keeps running and every case silently reports "no command was attempted".
    Prove interception before trusting a single case, through a shell and
    without one, because the two resolve executables by different rules.
    """

    log = shim_directory / "calls.log"
    probe_directory = shim_directory.parent
    before = log.read_text(encoding="utf-8") if log.exists() else ""
    subprocess.run(
        "git --version",
        shell=True,
        env=environment,
        cwd=probe_directory,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    # On Windows, CreateProcess resolves a shell=False executable against the
    # parent process environment rather than the `env` override supplied to
    # this individual Popen call. The candidate itself is a child launched
    # with the shimmed environment, so prove the same boundary by launching a
    # Python child first and making its no-shell call from there.
    subprocess.run(
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
        cwd=probe_directory,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    after = log.read_text(encoding="utf-8") if log.exists() else ""
    recorded = after[len(before) :].count('"git", "--version"')
    if recorded < 2:
        raise RuntimeError(
            "Command shims did not intercept both spawn styles "
            f"({recorded}/2 reached {log}). Refusing to run: an unintercepted "
            "candidate can mutate the remote without leaving a trace."
        )


def _run(
    command: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _git_bytes(arguments: list[str], *, step: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Unable to {step}: {detail}")
    return result.stdout


def _read_committed_candidate(commit: str) -> tuple[str, dict[str, bytes]]:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("--candidate-commit must be a full 40-hex commit ID.")
    resolved_commit = _git_bytes(
        ["rev-parse", f"{commit}^{{commit}}"],
        step="resolve candidate commit",
    ).decode("ascii").strip().lower()
    if resolved_commit != commit.lower():
        raise ValueError(
            f"Candidate commit resolved to unexpected ID {resolved_commit}."
        )

    prefix = "skills/open-pull-request"
    listed = _git_bytes(
        [
            "ls-tree",
            "-r",
            "--name-only",
            resolved_commit,
            f"{prefix}/SKILL.md",
            f"{prefix}/scripts",
        ],
        step="list candidate files",
    ).decode("utf-8").splitlines()
    expected_skill = f"{prefix}/SKILL.md"
    if expected_skill not in listed:
        raise ValueError(
            "Candidate commit does not contain skills/open-pull-request/SKILL.md."
        )
    files = {
        path: _git_bytes(
            ["show", f"{resolved_commit}:{path}"],
            step=f"read {path} from candidate commit",
        )
        for path in listed
    }
    return resolved_commit, files


def assert_candidate_content(committed_files: dict[str, bytes]) -> dict[str, str]:
    """Return file digests or reject a dirty/different candidate checkout."""

    checkout_files = {
        relative_path: REPOSITORY_ROOT / relative_path
        for relative_path in committed_files
    }
    digests: dict[str, str] = {}
    for relative_path, committed_content in committed_files.items():
        checkout_path = checkout_files[relative_path]
        if not checkout_path.is_file():
            raise ValueError(
                f"Candidate checkout is missing {relative_path}."
            )
        checkout_content = checkout_path.read_bytes()
        committed_digest = hashlib.sha256(committed_content).hexdigest()
        checkout_digest = hashlib.sha256(checkout_content).hexdigest()
        if checkout_digest != committed_digest:
            raise ValueError(
                f"Candidate {relative_path} does not match the recorded commit "
                f"({checkout_digest} != {committed_digest})."
            )
        digests[relative_path] = checkout_digest
    return digests


def _codex_command(
    codex: str,
    output_file: Path,
    *,
    model: str | None,
) -> list[str]:
    command = [
        codex,
        "exec",
        "--ephemeral",
        "--json",
        "--sandbox",
        "workspace-write",
        "--skip-git-repo-check",
        "-o",
        str(output_file),
    ]
    if model:
        command.extend(["--model", model])
    command.append("-")
    return command


def _safe_output_directory(output_directory: Path) -> Path:
    resolved = output_directory.resolve()
    repository = REPOSITORY_ROOT.resolve()
    try:
        relative = resolved.relative_to(repository)
    except ValueError:
        return resolved
    if not relative.parts or relative.parts[0] != ".superpowers":
        raise ValueError(
            "Output must be outside the repository or under ignored .superpowers/."
        )
    return resolved


def _selected_case_ids(
    criteria: dict[str, Any],
    requested_cases: str | None,
) -> list[str]:
    available = set(criteria["cases"])
    if requested_cases is None:
        return sorted(available)
    selected = [
        case_id.strip()
        for case_id in requested_cases.split(",")
        if case_id.strip()
    ]
    if not selected:
        raise ValueError("--cases must name at least one case.")
    unknown = sorted(set(selected) - available)
    if unknown:
        raise ValueError("Unknown case ID(s): " + ", ".join(unknown))
    return list(dict.fromkeys(selected))


def _parse_assessment(text: str, case_id: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        assessment = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return {
            "case_id": case_id,
            "pass": False,
            "findings": [f"Evaluator returned invalid JSON: {exc}"],
            "raw": text,
        }
    if (
        not isinstance(assessment, dict)
        or assessment.get("case_id") != case_id
        or not isinstance(assessment.get("pass"), bool)
        or not isinstance(assessment.get("findings"), list)
    ):
        return {
            "case_id": case_id,
            "pass": False,
            "findings": ["Evaluator JSON did not match the required schema."],
            "raw": text,
        }
    return assessment


def run_evaluation(args: argparse.Namespace) -> int:
    output_directory = _safe_output_directory(Path(args.output_dir))
    if output_directory.exists() and any(output_directory.iterdir()):
        raise ValueError(f"Output directory is not empty: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)

    codex = args.codex or shutil.which("codex") or shutil.which("codex.cmd")
    if not codex:
        raise RuntimeError("Codex CLI was not found; pass --codex PATH.")
    version_result = _run([codex, "--version"], cwd=REPOSITORY_ROOT)
    if version_result.returncode != 0:
        raise RuntimeError(
            "Unable to read Codex version: " + version_result.stderr.strip()
        )

    criteria = yaml.safe_load(
        (EVAL_ROOT / "criteria.yaml").read_text(encoding="utf-8")
    )
    case_ids = _selected_case_ids(criteria, args.cases)
    prompts = {
        case_id: build_execution_prompt(
            Path("candidate/SKILL.md"),
            Path(f"inputs/{case_id}.md"),
        )
        for case_id in case_ids
    }
    candidate_commit, committed_files = _read_committed_candidate(
        args.candidate_commit
    )
    candidate_digests = assert_candidate_content(committed_files)
    manifest = build_evidence_manifest(
        candidate_commit=candidate_commit,
        candidate_files_sha256=candidate_digests,
        codex_version=version_result.stdout.strip(),
        model=args.model or "codex-default",
        execution_prompts=prompts,
    )

    for case_id in case_ids:
        case_output = output_directory / case_id
        case_output.mkdir()
        raw_input = (EVAL_ROOT / "inputs" / f"{case_id}.md").read_text(
            encoding="utf-8"
        )
        fixture_specification = json.loads(
            (EVAL_ROOT / "fixtures" / f"{case_id}.json").read_text(
                encoding="utf-8"
            )
        )
        (case_output / "input.md").write_text(raw_input, encoding="utf-8")
        (case_output / "fixture.json").write_text(
            json.dumps(fixture_specification, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

        with tempfile.TemporaryDirectory(
            prefix=f"open-pull-request-eval-{case_id}-"
        ) as temporary_directory:
            workspace = Path(temporary_directory)
            candidate_directory = workspace / "candidate"
            input_directory = workspace / "inputs"
            candidate_directory.mkdir()
            input_directory.mkdir()
            candidate_prefix = Path("skills/open-pull-request")
            for relative_path in committed_files:
                source = REPOSITORY_ROOT / relative_path
                relative_candidate_path = Path(relative_path).relative_to(
                    candidate_prefix
                )
                target = candidate_directory / relative_candidate_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            (input_directory / f"{case_id}.md").write_text(
                raw_input,
                encoding="utf-8",
            )
            build_repository(fixture_specification, workspace / "repository")
            shim_directory = write_command_shims(
                workspace / "shims",
                fixture_specification.get("githubState", {}),
            )
            candidate_environment = build_candidate_environment(
                shim_directory,
            )
            assert_shims_intercept(shim_directory, candidate_environment)

            execution_prompt = prompts[case_id]
            (case_output / "execution-prompt.txt").write_text(
                execution_prompt,
                encoding="utf-8",
            )
            response_path = case_output / "response.md"
            execution_command = _codex_command(
                codex,
                response_path,
                model=args.model,
            )
            execution = _run(
                execution_command,
                cwd=workspace,
                input_text=execution_prompt,
                environment=candidate_environment,
            )
            (case_output / "execution-transcript.jsonl").write_text(
                execution.stdout,
                encoding="utf-8",
            )
            (case_output / "execution-stderr.txt").write_text(
                execution.stderr,
                encoding="utf-8",
            )
            shutil.copy2(shim_directory / "calls.log", case_output / "calls.log")
            shutil.copy2(
                shim_directory / "forwarding.log",
                case_output / "forwarding.log",
            )
            if execution.returncode != 0:
                raise RuntimeError(
                    f"{case_id} execution failed ({execution.returncode}); "
                    f"see {case_output}"
                )

        response = response_path.read_text(encoding="utf-8")
        calls_log = (case_output / "calls.log").read_text(encoding="utf-8")
        evaluator_prompt = build_evaluator_prompt(
            case_id,
            raw_input,
            fixture_specification,
            response,
            calls_log,
            extract_execution_evidence(execution.stdout),
            criteria["universal_pass_conditions"],
            criteria["cases"][case_id]["pass_conditions"],
        )
        (case_output / "evaluator-prompt.txt").write_text(
            evaluator_prompt,
            encoding="utf-8",
        )
        evaluator_output = case_output / "assessment-raw.json"
        evaluator_command = _codex_command(
            codex,
            evaluator_output,
            model=args.model,
        )
        evaluation = _run(
            evaluator_command,
            cwd=output_directory,
            input_text=evaluator_prompt,
        )
        (case_output / "evaluator-transcript.jsonl").write_text(
            evaluation.stdout,
            encoding="utf-8",
        )
        (case_output / "evaluator-stderr.txt").write_text(
            evaluation.stderr,
            encoding="utf-8",
        )
        if evaluation.returncode != 0:
            raise RuntimeError(
                f"{case_id} evaluator failed ({evaluation.returncode}); "
                f"see {case_output}"
            )
        assessment = _parse_assessment(
            evaluator_output.read_text(encoding="utf-8"),
            case_id,
        )
        (case_output / "assessment.json").write_text(
            json.dumps(assessment, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest["cases"][case_id] = {
            "pass": assessment["pass"],
            "findings": assessment["findings"],
            "execution_command": execution_command,
            "evaluator_prompt": evaluator_prompt,
            "evaluator_command": evaluator_command,
            "artifacts": {
                "input": f"{case_id}/input.md",
                "fixture": f"{case_id}/fixture.json",
                "calls_log": f"{case_id}/calls.log",
                "forwarding_log": f"{case_id}/forwarding.log",
                "execution_transcript": f"{case_id}/execution-transcript.jsonl",
                "response": f"{case_id}/response.md",
                "evaluator_transcript": f"{case_id}/evaluator-transcript.jsonl",
                "assessment": f"{case_id}/assessment.json",
            },
        }

    passed = sum(
        1 for result in manifest["cases"].values() if result["pass"]
    )
    manifest["summary"] = {"passed": passed, "total": len(case_ids)}
    (output_directory / "evidence.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Open pull request evaluation: {passed}/{len(case_ids)} passed.")
    print(f"Evidence: {output_directory}")
    return 0 if passed == len(case_ids) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--model")
    parser.add_argument("--codex")
    parser.add_argument(
        "--cases",
        help="Comma-separated case IDs to run (default: every case).",
    )
    return parser.parse_args()


def main() -> int:
    try:
        return run_evaluation(parse_args())
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
