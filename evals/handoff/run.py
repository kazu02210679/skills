#!/usr/bin/env python3
"""Run blind, candidate-pinned behavioral evaluations for the handoff Skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


EVAL_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EVAL_ROOT.parents[1]
CANDIDATE_PATH = REPOSITORY_ROOT / "skills" / "handoff" / "SKILL.md"
OS_TEMP_PLACEHOLDER = "{{OS_TEMP_DIRECTORY}}"


def build_execution_prompt(candidate_path: Path, input_path: Path) -> str:
    """Build the criteria-free prompt used in an isolated execution workspace."""

    return (
        "Evaluate the requested scenario by following the candidate Skill.\n"
        f"Read {candidate_path.as_posix()} completely, then read "
        f"{input_path.as_posix()}.\n"
        "Treat environment declarations in the input as authoritative simulated "
        "capabilities. Produce the complete response and destination payload, "
        "plus only the concise observable mock capability action/result needed "
        "to show what the Skill would do. Do not emit debug or tool logs. "
        "Do not inspect any other files. Do not discuss evaluation rules."
    )


def build_evaluator_prompt(
    case_id: str,
    raw_input: str,
    response: str,
    universal_conditions: list[str],
    case_conditions: list[str],
) -> str:
    payload = {
        "case_id": case_id,
        "raw_input": raw_input,
        "candidate_response": response,
        "universal_conditions": universal_conditions,
        "case_conditions": case_conditions,
    }
    return (
        "Act as a strict behavioral evaluator. Assess only the supplied response "
        "against every supplied condition. Return JSON with keys case_id, pass "
        "(boolean), and findings (array of concise strings). Do not infer omitted "
        "behavior as passing.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def build_evidence_manifest(
    *,
    candidate_commit: str,
    skill_sha256: str,
    codex_version: str,
    model: str,
    execution_prompts: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": {
            "commit": candidate_commit,
            "skill_sha256": skill_sha256,
        },
        "runtime": {
            "codex_version": codex_version,
            "model": model,
        },
        "execution_prompts": execution_prompts,
        "cases": {},
    }


def assert_candidate_content(
    committed_skill: bytes,
    checkout_skill: bytes,
) -> str:
    """Return the shared digest or reject a dirty/different candidate."""

    committed_digest = hashlib.sha256(committed_skill).hexdigest()
    checkout_digest = hashlib.sha256(checkout_skill).hexdigest()
    if committed_digest != checkout_digest:
        raise ValueError(
            "Candidate SKILL.md does not match the recorded commit "
            f"({checkout_digest} != {committed_digest})."
        )
    return checkout_digest


def materialize_case_input(
    case_id: str,
    source_input: str,
    os_temp_directory: Path,
) -> str:
    """Inject runtime-only environment values into a raw case input."""

    if case_id != "case-3":
        return source_input
    if OS_TEMP_PLACEHOLDER not in source_input:
        raise ValueError(
            f"{case_id} input is missing {OS_TEMP_PLACEHOLDER}."
        )
    return source_input.replace(
        OS_TEMP_PLACEHOLDER,
        str(os_temp_directory.resolve()),
    )


def _run(
    command: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _read_committed_candidate(commit: str) -> tuple[str, bytes]:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("--candidate-commit must be a full 40-hex commit ID.")
    resolved = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{commit}}"],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if resolved.returncode != 0:
        raise ValueError(
            "Unable to resolve candidate commit: "
            + resolved.stderr.decode("utf-8", errors="replace").strip()
        )
    resolved_commit = resolved.stdout.decode("ascii").strip().lower()
    if resolved_commit != commit.lower():
        raise ValueError(
            f"Candidate commit resolved to unexpected ID {resolved_commit}."
        )
    shown = subprocess.run(
        ["git", "show", f"{resolved_commit}:skills/handoff/SKILL.md"],
        cwd=REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if shown.returncode != 0:
        raise ValueError(
            "Unable to read handoff Skill from candidate commit: "
            + shown.stderr.decode("utf-8", errors="replace").strip()
        )
    return resolved_commit, shown.stdout


def _codex_command(
    codex: str,
    prompt: str,
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
        "read-only",
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


def _safe_simulated_temp_root(
    requested_root: str | Path | None,
) -> Path:
    """Resolve and create a simulated temp root outside the repository."""

    root = (
        Path(requested_root)
        if requested_root is not None
        else Path(tempfile.gettempdir())
    ).resolve()
    repository = REPOSITORY_ROOT.resolve()
    try:
        root.relative_to(repository)
    except ValueError:
        pass
    else:
        raise ValueError(
            "The simulated temp root must be outside the repository."
        )
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise ValueError(
            f"The simulated temp root is not a directory: {root}"
        )
    return root


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
        raise RuntimeError(f"Unable to read Codex version: {version_result.stderr}")
    codex_version = version_result.stdout.strip()

    criteria = yaml.safe_load(
        (EVAL_ROOT / "criteria.yaml").read_text(encoding="utf-8")
    )
    case_ids = sorted(criteria["cases"])
    prompts = {
        case_id: build_execution_prompt(
            Path("candidate/SKILL.md"),
            Path(f"inputs/{case_id}.md"),
        )
        for case_id in case_ids
    }
    candidate_commit, committed_skill = _read_committed_candidate(
        args.candidate_commit
    )
    skill_digest = assert_candidate_content(
        committed_skill,
        CANDIDATE_PATH.read_bytes(),
    )
    manifest = build_evidence_manifest(
        candidate_commit=candidate_commit,
        skill_sha256=skill_digest,
        codex_version=codex_version,
        model=args.model or "codex-default",
        execution_prompts=prompts,
    )
    simulated_temp_root = _safe_simulated_temp_root(
        getattr(args, "simulated_temp_root", None)
    )
    case_three_temp_context = tempfile.TemporaryDirectory(
        prefix="handoff-eval-case-3-",
        dir=simulated_temp_root,
    )
    os_temp_directory = Path(case_three_temp_context.name).resolve()

    for case_id in case_ids:
        case_output = output_directory / case_id
        case_output.mkdir()
        source_input_path = EVAL_ROOT / "inputs" / f"{case_id}.md"
        raw_input = materialize_case_input(
            case_id,
            source_input_path.read_text(encoding="utf-8"),
            os_temp_directory,
        )
        (case_output / "input.md").write_text(
            raw_input,
            encoding="utf-8",
        )
        with tempfile.TemporaryDirectory(
            prefix=f"handoff-eval-{case_id}-"
        ) as temporary_directory:
            workspace = Path(temporary_directory)
            candidate_directory = workspace / "candidate"
            input_directory = workspace / "inputs"
            candidate_directory.mkdir()
            input_directory.mkdir()
            shutil.copy2(CANDIDATE_PATH, candidate_directory / "SKILL.md")
            effective_input_path = input_directory / f"{case_id}.md"
            effective_input_path.write_text(
                raw_input,
                encoding="utf-8",
            )

            execution_prompt = prompts[case_id]
            (case_output / "execution-prompt.txt").write_text(
                execution_prompt,
                encoding="utf-8",
            )
            response_path = case_output / "response.md"
            execution_command = _codex_command(
                codex,
                execution_prompt,
                response_path,
                model=args.model,
            )
            execution = _run(
                execution_command,
                cwd=workspace,
                input_text=execution_prompt,
            )
            (case_output / "execution-transcript.jsonl").write_text(
                execution.stdout,
                encoding="utf-8",
            )
            (case_output / "execution-stderr.txt").write_text(
                execution.stderr,
                encoding="utf-8",
            )
            if execution.returncode != 0:
                raise RuntimeError(
                    f"{case_id} execution failed ({execution.returncode}); "
                    f"see {case_output}"
                )

        response = response_path.read_text(encoding="utf-8")
        evaluator_prompt = build_evaluator_prompt(
            case_id,
            raw_input,
            response,
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
            evaluator_prompt,
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
        assessment_text = evaluator_output.read_text(encoding="utf-8")
        assessment = _parse_assessment(assessment_text, case_id)
        (case_output / "assessment.json").write_text(
            json.dumps(assessment, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        case_evidence = {
            "pass": assessment["pass"],
            "findings": assessment["findings"],
            "execution_command": execution_command,
            "evaluator_prompt": evaluator_prompt,
            "evaluator_command": evaluator_command,
            "artifacts": {
                "input": f"{case_id}/input.md",
                "execution_transcript": f"{case_id}/execution-transcript.jsonl",
                "response": f"{case_id}/response.md",
                "evaluator_transcript": f"{case_id}/evaluator-transcript.jsonl",
                "assessment": f"{case_id}/assessment.json",
            },
        }
        if case_id == "case-3":
            case_evidence["environment"] = {
                "simulated_temp_root": str(simulated_temp_root),
                "os_temp_directory": str(os_temp_directory),
            }
        manifest["cases"][case_id] = case_evidence

    passed = sum(
        1 for result in manifest["cases"].values() if result["pass"]
    )
    manifest["summary"] = {
        "passed": passed,
        "total": len(case_ids),
    }
    (output_directory / "evidence.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    case_three_temp_context.cleanup()
    print(f"Handoff evaluation: {passed}/{len(case_ids)} passed.")
    print(f"Evidence: {output_directory}")
    return 0 if passed == len(case_ids) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--model")
    parser.add_argument("--codex")
    parser.add_argument(
        "--simulated-temp-root",
        help=(
            "Root outside the repository for the unique Case 3 simulated "
            "OS temporary directory (default: the runtime OS temp root)."
        ),
    )
    return parser.parse_args()


def main() -> int:
    try:
        return run_evaluation(parse_args())
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
