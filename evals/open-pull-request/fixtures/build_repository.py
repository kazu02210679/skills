#!/usr/bin/env python3
"""Materialize throwaway Git repositories for open-pull-request evaluations."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FIXED_IDENTITY = {
    "GIT_AUTHOR_NAME": "Open Pull Request Eval",
    "GIT_AUTHOR_EMAIL": "open-pull-request-eval@example.invalid",
    "GIT_COMMITTER_NAME": "Open Pull Request Eval",
    "GIT_COMMITTER_EMAIL": "open-pull-request-eval@example.invalid",
}
FIRST_COMMIT_DATE = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _run_git(
    arguments: list[str],
    *,
    cwd: Path,
    step: str,
    commit_number: int | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(FIXED_IDENTITY)
    if commit_number is not None:
        date = FIRST_COMMIT_DATE + timedelta(seconds=commit_number)
        timestamp = date.isoformat().replace("+00:00", "Z")
        environment["GIT_AUTHOR_DATE"] = timestamp
        environment["GIT_COMMITTER_DATE"] = timestamp
    result = subprocess.run(
        ["git", *arguments],
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
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Git fixture step '{step}' failed ({result.returncode}): {detail}"
        )
    return result


def _write_files(repository: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _commit_message(commit: dict[str, Any]) -> str:
    message = str(commit["message"])
    trailers = commit.get("trailers", {})
    if isinstance(trailers, dict):
        trailer_lines = [
            f"{key}: {value}"
            for key, value in trailers.items()
        ]
    else:
        trailer_lines = [str(trailer) for trailer in trailers]
    if trailer_lines:
        message += "\n\n" + "\n".join(trailer_lines)
    return message


def _initialize_bare(
    path: Path,
    default_branch: str,
    repository: Path,
    step: str,
) -> None:
    path.mkdir(parents=True)
    _run_git(
        ["init", "--bare", f"--initial-branch={default_branch}", str(path)],
        cwd=repository,
        step=step,
    )


def _publish_remote(
    repository: Path,
    destination: Path,
    specification: dict[str, Any],
    default_branch: str,
    head_branch: str,
    commit_number: int,
) -> None:
    primary = destination.parent / f"{destination.name}-remote.git"
    _initialize_bare(
        primary,
        default_branch,
        repository,
        "initialize primary bare remote",
    )

    fork = bool(specification.get("fork"))
    if fork:
        origin = destination.parent / f"{destination.name}-origin.git"
        _initialize_bare(
            origin,
            default_branch,
            repository,
            "initialize fork bare remote",
        )
        _run_git(
            ["remote", "add", "upstream", str(primary)],
            cwd=repository,
            step="register upstream remote",
        )
    else:
        origin = primary

    _run_git(
        ["remote", "add", "origin", str(origin)],
        cwd=repository,
        step="register origin remote",
    )

    base_sha = _run_git(
        ["rev-parse", default_branch],
        cwd=repository,
        step="resolve base commit for remote",
    ).stdout.strip()
    base_targets = [origin, primary] if fork else [origin]
    for index, target in enumerate(base_targets):
        _run_git(
            [
                "push",
                str(target),
                f"{base_sha}:refs/heads/{default_branch}",
            ],
            cwd=repository,
            step=f"publish base branch to remote {index + 1}",
        )

    requested_head = str(specification.get("headSha", "equal"))
    if requested_head == "equal":
        published_head = "HEAD"
    elif requested_head.startswith("ancestor:"):
        try:
            distance = int(requested_head.partition(":")[2])
        except ValueError as exc:
            raise ValueError(
                f"Invalid remote headSha value: {requested_head}"
            ) from exc
        published_head = _run_git(
            ["rev-parse", f"HEAD~{distance}"],
            cwd=repository,
            step=f"resolve remote ancestor {distance}",
        ).stdout.strip()
    elif requested_head == "diverged":
        empty_tree = _run_git(
            ["mktree"],
            cwd=repository,
            step="create empty tree for diverged remote",
            input_text="",
        ).stdout.strip()
        published_head = _run_git(
            ["commit-tree", empty_tree, "-m", "Diverged remote fixture"],
            cwd=repository,
            step="create diverged remote commit",
            commit_number=commit_number,
        ).stdout.strip()
    else:
        raise ValueError(f"Invalid remote headSha value: {requested_head}")

    _run_git(
        [
            "push",
            str(origin),
            f"{published_head}:refs/heads/{head_branch}",
        ],
        cwd=repository,
        step="publish remote head branch",
    )
    _run_git(
        ["fetch", "origin"],
        cwd=repository,
        step="fetch origin tracking references",
    )
    if fork:
        _run_git(
            ["fetch", "upstream"],
            cwd=repository,
            step="fetch upstream tracking references",
        )
    # Without this the branch has no configured upstream, and the Skill's
    # inspector tries `@{upstream}` before falling back to origin/HEAD — so
    # every case would exercise the fallback and never the preferred path.
    # A published branch that git considers untracked is also not what
    # `headSha: equal | ancestor:N` is meant to model.
    _run_git(
        ["branch", "--set-upstream-to", f"origin/{head_branch}", head_branch],
        cwd=repository,
        step="configure upstream tracking for the head branch",
    )


def build_repository(
    specification: dict[str, Any],
    destination: Path,
) -> Path:
    """Create a repository at ``destination`` from a declarative specification.

    The sibling ``githubState`` key is intentionally ignored. The evaluation
    runner passes that state to the command shims instead.
    """

    default_branch = str(specification.get("defaultBranch", "main"))
    destination.mkdir(parents=True)
    _run_git(
        ["init", f"--initial-branch={default_branch}", str(destination)],
        cwd=destination.parent,
        step="initialize working repository",
    )
    _run_git(
        ["commit", "--allow-empty", "-m", "Base fixture"],
        cwd=destination,
        step="create base commit",
        commit_number=0,
    )

    head_branch = str(specification.get("headBranch", default_branch))
    if head_branch != default_branch:
        _run_git(
            ["switch", "-c", head_branch],
            cwd=destination,
            step=f"create head branch {head_branch}",
        )

    commits = specification.get("commits", [])
    for index, commit in enumerate(commits, start=1):
        files = commit.get("files", {})
        _write_files(destination, files)
        if files:
            _run_git(
                ["add", "--", *files],
                cwd=destination,
                step=f"stage fixture commit {index}",
            )
        _run_git(
            ["commit", "--allow-empty", "-m", _commit_message(commit)],
            cwd=destination,
            step=f"create fixture commit {index}",
            commit_number=index,
        )

    remote = specification.get("remote")
    if remote is not None:
        _publish_remote(
            destination,
            destination,
            remote,
            default_branch,
            head_branch,
            len(commits) + 1,
        )

    _write_files(destination, specification.get("untracked", {}))
    staged = specification.get("staged", {})
    _write_files(destination, staged)
    if staged:
        _run_git(
            ["add", "--", *staged],
            cwd=destination,
            step="stage requested worktree files",
        )
    _write_files(destination, specification.get("modified", {}))

    for slug, review_data in specification.get("reviewData", {}).items():
        review_path = (
            destination
            / "docs"
            / "reviews"
            / slug
            / "review-data.json"
        )
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps(review_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return destination
