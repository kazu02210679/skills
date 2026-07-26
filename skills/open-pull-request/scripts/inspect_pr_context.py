#!/usr/bin/env python3
"""Report local publish context for the open-pull-request Skill.

Read-only: runs local git queries only. Never commits, pushes, contacts a
remote, or creates a pull request.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

KNOWN_EVIDENCE_PREFIXES = ("docs/reviews/",)


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git_output(repository: Path, *arguments: str) -> str:
    result = _git(repository, *arguments)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve(repository: Path, revision: str) -> str:
    if not revision:
        return ""
    return _git_output(repository, "rev-parse", "--verify", f"{revision}^{{commit}}")


def _display_ref(reference: str) -> str:
    for prefix in ("refs/heads/", "refs/remotes/origin/", "origin/"):
        if reference.startswith(prefix):
            return reference[len(prefix) :]
    return reference


def _is_dirty(result: subprocess.CompletedProcess[str]) -> bool:
    """Report dirtiness only when git actually answered.

    `git diff --quiet` exits 1 for "differences exist" and 128 when it could
    not run at all. Treating every non-zero code as dirty makes a directory
    that is not a repository look like one with uncommitted work.
    """

    return result.returncode == 1


def _resolve_base(repository: Path, base: str | None) -> tuple[str, str, str]:
    if base is not None:
        return base, base, "user"

    upstream = _git_output(
        repository,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
    )
    if upstream:
        return _display_ref(upstream), upstream, "upstream"

    origin_head = _git_output(
        repository,
        "symbolic-ref",
        "--quiet",
        "--short",
        "refs/remotes/origin/HEAD",
    )
    if origin_head:
        return _display_ref(origin_head), origin_head, "origin-head"

    for candidate in ("main", "master"):
        result = _git(
            repository,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{candidate}",
        )
        if result.returncode == 0:
            return candidate, candidate, "main-or-master"

    return "", "", "unresolved"


def _repository_label(repository: Path) -> str:
    remote = _git_output(repository, "config", "--get", "remote.origin.url")
    if not remote:
        return str(repository.resolve())

    normalized = remote.rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if ":" in normalized and "://" not in normalized:
        normalized = normalized.split(":", 1)[1]
    else:
        normalized = normalized.rsplit("://", 1)[-1]
        parts = normalized.split("/", 1)
        normalized = parts[1] if len(parts) == 2 else normalized
    path_parts = normalized.replace("\\", "/").split("/")
    if len(path_parts) >= 2:
        return "/".join(path_parts[-2:])
    return str(repository.resolve())


def _untracked_paths(repository: Path) -> list[str]:
    result = _git(repository, "ls-files", "--others", "--exclude-standard", "-z")
    if result.returncode != 0:
        return []
    return sorted(
        path.replace("\\", "/")
        for path in result.stdout.split("\0")
        if path
    )


def _codex_plan_ids(repository: Path, base_revision: str) -> list[str]:
    if not base_revision:
        return []
    result = _git(
        repository,
        "log",
        "--reverse",
        "--format=%(trailers:key=Codex-Plan,valueonly,separator=%x1f)%x1e",
        f"{base_revision}..HEAD",
    )
    if result.returncode != 0:
        return []

    plan_ids: list[str] = []
    for commit_values in result.stdout.split("\x1e"):
        for value in commit_values.strip().split("\x1f"):
            plan_id = value.strip()
            if plan_id and plan_id not in plan_ids:
                plan_ids.append(plan_id)
    return plan_ids


def _review_artifacts(
    repository: Path,
    head_sha: str,
    merge_base_sha: str,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    paths = sorted(repository.glob("docs/reviews/*/review-data.json"))
    for path in paths:
        relative_path = path.relative_to(repository).as_posix()
        valid = False
        recorded_base: Any = None
        recorded_head: Any = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data.get("meta") if isinstance(data, dict) else None
            if isinstance(meta, dict) and "base" in meta and "head" in meta:
                valid = True
                recorded_base = meta["base"]
                recorded_head = meta["head"]
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass

        head_matches = False
        base_matches = False
        if valid:
            if isinstance(recorded_head, str) and recorded_head != "WORKTREE":
                head_matches = bool(head_sha) and (
                    _resolve(repository, recorded_head) == head_sha
                )
            if isinstance(recorded_base, str):
                base_matches = bool(merge_base_sha) and (
                    _resolve(repository, recorded_base) == merge_base_sha
                )

        artifacts.append(
            {
                "path": relative_path,
                "valid": valid,
                "headMatches": head_matches,
                "baseMatches": base_matches,
            }
        )
    return artifacts


def inspect(repository: Path, base: str | None = None) -> dict[str, Any]:
    """Return the publish context contract for `repository`.

    `base` overrides base detection. When it is None the base is resolved in
    this order and `baseResolution` records which rule matched: the branch
    upstream, `refs/remotes/origin/HEAD`, then a local `main` or `master`.
    When no rule matches, `baseResolution` is `unresolved` and `baseRef` and
    `baseSha` are empty — never a guessed branch name, because every field
    derived from a fabricated base is silently wrong.
    `baseProvisional` is always True here because no remote is contacted.
    """

    repository = Path(repository).resolve()
    head_ref = _git_output(repository, "symbolic-ref", "--quiet", "--short", "HEAD")
    head_sha = _resolve(repository, "HEAD")
    base_ref, base_revision, base_resolution = _resolve_base(repository, base)
    base_sha = _resolve(repository, base_revision)
    merge_base_sha = (
        _git_output(repository, "merge-base", base_revision, "HEAD")
        if base_revision
        else ""
    )

    staged_result = _git(repository, "diff", "--cached", "--quiet")
    tracked_result = _git(repository, "diff", "--quiet")
    untracked = _untracked_paths(repository)
    untracked_local_evidence = [
        path
        for path in untracked
        if path.startswith(KNOWN_EVIDENCE_PREFIXES)
    ]
    untracked_other = [
        path
        for path in untracked
        if not path.startswith(KNOWN_EVIDENCE_PREFIXES)
    ]

    # Guard the empty base explicitly: `git rev-list --count ..HEAD` succeeds,
    # because git defaults an omitted range side to HEAD, so an unresolved base
    # would silently produce a computed HEAD..HEAD rather than "not measured".
    commits_ahead = 0
    if base_revision:
        commits_ahead_output = _git_output(
            repository, "rev-list", "--count", f"{base_revision}..HEAD"
        )
        try:
            commits_ahead = int(commits_ahead_output)
        except ValueError:
            commits_ahead = 0

    return {
        "repository": _repository_label(repository),
        "headRef": head_ref,
        "headSha": head_sha,
        "baseRef": base_ref,
        "baseSha": base_sha,
        "baseResolution": base_resolution,
        "baseProvisional": True,
        "mergeBaseSha": merge_base_sha,
        "isDefaultBranch": bool(head_ref) and head_ref == base_ref,
        "stagedDirty": _is_dirty(staged_result),
        "trackedDirty": _is_dirty(tracked_result),
        "untrackedLocalEvidence": untracked_local_evidence,
        "untrackedOther": untracked_other,
        "commitsAhead": commits_ahead,
        "codexPlanIds": _codex_plan_ids(repository, base_revision),
        "reviewArtifacts": _review_artifacts(
            repository, head_sha, merge_base_sha
        ),
    }


def main() -> int:
    """Write the context as JSON to stdout."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--base")
    arguments = parser.parse_args()
    json.dump(inspect(arguments.repository, arguments.base), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
