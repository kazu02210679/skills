"""Collect bounded, redacted Git context for an implementation review."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
from typing import Sequence


ASSIGNMENT_SECRET = re.compile(
    r"""(?ix)
    \b(
      api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|
      password|passwd|secret|private[_-]?key
    )
    (\s*[:=]\s*)
    (["']?)
    ([^\s"'`,;]{6,})
    \3
    """
)
PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
DIFF_RISK_PATTERNS = {
    "auth_or_authorization": re.compile(
        r"(?:^|[^a-z0-9])(?:auth(?:entication|orization)?|permissions?|authorize|access[_-]?control)(?:$|[^a-z0-9])",
        re.I,
    ),
    "secrets_or_credentials": re.compile(
        r"\b(api[_-]?key|access[_-]?token|auth[_-]?token|credential|password|secret|private[_-]?key)\b",
        re.I,
    ),
    "sandbox_or_permissions": re.compile(r"\b(sandbox|approvals?|permissions?|capabilit(?:y|ies))\b", re.I),
    "command_or_rce": re.compile(r"\b(subprocess|shell|exec|eval|system|popen|rce)\b", re.I),
    "destructive_data_change": re.compile(r"\b(delete|drop|truncate|purge|migration|remove[_-]?all)\b", re.I),
    "release_or_signing_trust": re.compile(r"\b(release|signing|signature|provenance|supply[_-]?chain)\b", re.I),
    "reviewer_or_safety_policy": re.compile(r"\b(reviewer|auto[_-]?review|safety[_-]?policy|guardrail)\b", re.I),
}


def redact_text(text: str) -> tuple[str, list[str]]:
    """Replace likely credentials while returning the matched secret labels."""
    labels: list[str] = []

    def replace_assignment(match: re.Match[str]) -> str:
        label = match.group(1)
        labels.append(label.upper().replace("-", "_"))
        return f"{label}{match.group(2)}[REDACTED]"

    redacted = ASSIGNMENT_SECRET.sub(replace_assignment, text)
    if PRIVATE_KEY_BLOCK.search(redacted):
        labels.append("PRIVATE_KEY")
        redacted = PRIVATE_KEY_BLOCK.sub("[REDACTED PRIVATE KEY]", redacted)
    return redacted, list(dict.fromkeys(labels))


def detect_diff_risk_signals(diff: str) -> list[str]:
    """Return categories only; never copy matching source into the result."""
    changed_lines = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            changed_lines.append(line[1:])
    changed_text = "\n".join(changed_lines)
    return sorted(
        category
        for category, pattern in DIFF_RISK_PATTERNS.items()
        if pattern.search(changed_text)
    )


def diff_stats(diff: str) -> dict[str, int]:
    added = 0
    deleted = 0
    for line in diff.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return {"added_lines": added, "deleted_lines": deleted}


def _run_git(root: pathlib.Path, args: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise ValueError(message)
    return result.stdout


def _parse_changed_files(name_status: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        entry = {"status": status, "path": parts[-1]}
        if len(parts) > 2:
            entry["old_path"] = parts[1]
        files.append(entry)
    return files


def _truncate_lines(text: str, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    kept: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        line_size = len(line.encode("utf-8"))
        if size + line_size > max_bytes:
            break
        kept.append(line)
        size += line_size
    return "".join(kept), True


def collect_context(
    repo: pathlib.Path, base: str, head: str, max_bytes: int
) -> dict:
    """Collect changed files and a bounded diff from a Git repository."""
    repo = pathlib.Path(repo).resolve()
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    try:
        root_text = _run_git(repo, ["rev-parse", "--show-toplevel"])
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(f"Not a Git repository: {repo}") from exc
    root = pathlib.Path(root_text.strip()).resolve()

    _run_git(root, ["rev-parse", "--verify", base])
    if head == "WORKTREE":
        range_arg = base
    else:
        _run_git(root, ["rev-parse", "--verify", head])
        range_arg = f"{base}...{head}"

    name_status = _run_git(root, ["diff", "--name-status", range_arg])
    if head == "WORKTREE":
        untracked = _run_git(root, ["ls-files", "--others", "--exclude-standard"])
    else:
        untracked = ""
    changed_files = _parse_changed_files(name_status)
    known_paths = {item["path"] for item in changed_files}
    for path in untracked.splitlines():
        if path and path not in known_paths:
            changed_files.append({"status": "?", "path": path})

    diff = _run_git(root, ["diff", "--unified=40", range_arg])
    risk_signals = detect_diff_risk_signals(diff)
    if untracked:
        risk_signals = sorted(set(risk_signals) | {"untracked_content_uninspected"})
    redacted_diff, labels = redact_text(diff)
    bounded_diff, truncated = _truncate_lines(redacted_diff, max_bytes)

    return {
        "repository": str(root),
        "base": base,
        "head": head,
        "changed_files": changed_files,
        "diff": bounded_diff,
        "truncated": truncated,
        "redactions": labels,
        "risk_signals": risk_signals,
        "diff_stats": diff_stats(diff),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="WORKTREE")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=500_000)
    args = parser.parse_args()

    try:
        context = collect_context(args.repo, args.base, args.head, args.max_bytes)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote review context: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
