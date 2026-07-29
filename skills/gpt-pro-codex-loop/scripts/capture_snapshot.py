#!/usr/bin/env python3
"""Fail-closed deterministic product snapshots for GPT Pro Codex Loop reviews."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Sequence


METADATA_DIRECTORY = ".ai-pro-loop"
SNAPSHOT_DISCOVERY_INTENT = "snapshot-discovered product change"
MAX_STABILITY_SAMPLES = 3


class SnapshotError(RuntimeError):
    """Raised when a complete, safe product snapshot cannot be produced."""


def run_git(repository: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotError(message or "git command failed")
    return completed.stdout


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _decode_paths(raw: bytes) -> list[str]:
    if not raw:
        return []
    if not raw.endswith(b"\0"):
        raise SnapshotError("git returned an unterminated NUL-delimited path list")
    try:
        return [entry.decode("utf-8") for entry in raw[:-1].split(b"\0")]
    except UnicodeDecodeError as exc:
        raise SnapshotError("git returned a path that is not valid UTF-8") from exc


def _repository_root(repository: Path) -> Path:
    supplied = repository.resolve()
    if not supplied.is_dir():
        raise SnapshotError("repository path is not a directory")
    root_text = run_git(supplied, "rev-parse", "--show-toplevel").decode(
        "utf-8", errors="strict"
    ).strip()
    root = Path(root_text).resolve()
    if root != supplied:
        raise SnapshotError("repository path must be the Git repository root")
    return root


def _baseline_commit(repository: Path, baseline_head: str) -> str:
    if not isinstance(baseline_head, str) or not baseline_head.strip():
        raise SnapshotError("baseline commit must be a non-empty string")
    try:
        return run_git(
            repository, "rev-parse", "--verify", f"{baseline_head}^{{commit}}"
        ).decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise SnapshotError("git returned an invalid baseline commit") from exc


def _normalize_path(repository: Path, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise SnapshotError("product path must be a non-empty string")
    raw = value.replace("\\", "/")
    candidate = PurePosixPath(raw)
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.parts[0].endswith(":")
    ):
        raise SnapshotError(f"invalid product path: {value}")
    normalized = "/".join(candidate.parts)
    resolved = (repository / Path(*candidate.parts)).resolve()
    try:
        resolved.relative_to(repository)
    except ValueError as exc:
        raise SnapshotError(f"product path resolves outside repository: {normalized}") from exc
    return normalized


def _is_metadata_path(repository: Path, path: str) -> bool:
    first_component = path.split("/", 1)[0]
    if first_component == METADATA_DIRECTORY:
        return True
    if first_component.casefold() != METADATA_DIRECTORY.casefold():
        return False
    if os.path.normcase(first_component) == os.path.normcase(METADATA_DIRECTORY):
        return True
    actual = repository / first_component
    canonical = repository / METADATA_DIRECTORY
    try:
        return actual.exists() and canonical.exists() and actual.samefile(canonical)
    except OSError as exc:
        raise SnapshotError("could not determine metadata path identity") from exc


def _reject_tracked_or_staged_metadata(repository: Path) -> tuple[bytes, bytes]:
    tracked_raw = run_git(repository, "ls-files", "-z")
    staged_raw = run_git(repository, "diff", "--cached", "--name-only", "-z")
    tracked = _decode_paths(tracked_raw)
    staged = _decode_paths(staged_raw)
    for path in [*tracked, *staged]:
        normalized = _normalize_path(repository, path)
        if _is_metadata_path(repository, normalized):
            raise SnapshotError(".ai-pro-loop metadata must not be tracked or staged")
    return tracked_raw, staged_raw


def _untracked_files(repository: Path) -> list[dict[str, str]]:
    candidates = _decode_paths(
        run_git(repository, "ls-files", "--others", "--exclude-standard", "-z")
    )
    files: list[dict[str, str]] = []
    for candidate in candidates:
        normalized = _normalize_path(repository, candidate)
        if _is_metadata_path(repository, normalized):
            continue
        path = (repository / Path(*PurePosixPath(normalized).parts)).resolve()
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise SnapshotError(f"could not read untracked product path: {normalized}") from exc
        files.append({"path": normalized, "content_digest": _bytes_digest(content)})
    return sorted(files, key=lambda item: item["path"])


def _tracked_status(repository: Path, baseline_head: str) -> bytes:
    return run_git(
        repository,
        "diff",
        "--name-status",
        "-z",
        "-M",
        "--no-ext-diff",
        baseline_head,
        "--",
    )


def _parse_tracked_changes(repository: Path, raw: bytes) -> list[dict[str, str]]:
    tokens = _decode_paths(raw)
    status_names = {
        "A": "added",
        "C": "copied",
        "D": "deleted",
        "M": "modified",
        "R": "renamed",
        "T": "type_changed",
        "U": "unmerged",
    }
    changes: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        status_token = tokens[index]
        index += 1
        if not status_token:
            raise SnapshotError("git returned an empty diff status")
        code = status_token[0]
        if code not in status_names:
            raise SnapshotError(f"git returned an unsupported diff status: {status_token}")
        path_count = 2 if code in {"C", "R"} else 1
        if index + path_count > len(tokens):
            raise SnapshotError("git returned an incomplete diff status record")
        paths = [_normalize_path(repository, token) for token in tokens[index : index + path_count]]
        index += path_count
        if any(_is_metadata_path(repository, path) for path in paths):
            raise SnapshotError(".ai-pro-loop metadata must not be tracked or staged")
        entry = {
            "path": paths[-1],
            "source": "tracked",
            "status": status_names[code],
        }
        if path_count == 2:
            entry["previous_path"] = paths[0]
        changes.append(entry)
    return sorted(changes, key=lambda item: (item["path"], item["status"], item.get("previous_path", "")))


def _preflight_manifest(repository: Path, baseline_head: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    _reject_tracked_or_staged_metadata(repository)
    tracked = _parse_tracked_changes(repository, _tracked_status(repository, baseline_head))
    return tracked, _untracked_files(repository)


def _component_observation(
    repository: Path, baseline_head: str
) -> tuple[bytes, bytes, bytes, bytes, list[dict[str, str]]]:
    tracked_paths, staged_paths = _reject_tracked_or_staged_metadata(repository)
    tracked_diff = run_git(
        repository, "diff", "--binary", "--no-ext-diff", baseline_head, "--"
    )
    tracked_status = _tracked_status(repository, baseline_head)
    untracked = _untracked_files(repository)
    return tracked_paths, staged_paths, tracked_diff, tracked_status, untracked


def _capture_components(
    repository: Path, baseline_head: str
) -> tuple[bytes, list[dict[str, str]], list[dict[str, str]]]:
    """Return components observed unchanged across a bracketed interval.

    This proves a stable observed interval; it is not OS-level transactional locking.
    """
    for _ in range(MAX_STABILITY_SAMPLES):
        before = _component_observation(repository, baseline_head)
        after = _component_observation(repository, baseline_head)
        if before == after:
            _, _, tracked_diff, tracked_status, untracked = after
            return (
                tracked_diff,
                _parse_tracked_changes(repository, tracked_status),
                untracked,
            )
    raise SnapshotError("product paths changed while capturing snapshot")


def inspect_preflight(repository: Path, baseline_head: str) -> dict[str, object]:
    """Record baseline-relative product paths that existed before implementation."""
    root = _repository_root(repository)
    baseline = _baseline_commit(root, baseline_head)
    tracked, untracked = _preflight_manifest(root, baseline)
    tracked_paths = sorted(
        {path for entry in tracked for path in (entry["path"], entry.get("previous_path", "")) if path}
    )
    untracked_paths = [entry["path"] for entry in untracked]
    product_paths = sorted(set(tracked_paths) | set(untracked_paths))
    return {
        "baseline_head": baseline,
        "tracked_paths": tracked_paths,
        "untracked_paths": untracked_paths,
        "initial_product_paths": product_paths,
    }


def validate_preflight(
    preflight: dict[str, object], approved_existing_paths: Sequence[str]
) -> list[str]:
    """Return deterministic errors when initial product changes lack exact approval."""
    errors: list[str] = []
    if not isinstance(preflight, dict):
        return ["preflight: must be an object"]
    initial = preflight.get("initial_product_paths")
    if not isinstance(initial, list):
        return ["preflight.initial_product_paths: must be a list"]
    if isinstance(approved_existing_paths, (str, bytes)):
        return ["approved_existing_paths: must be a sequence of paths"]
    try:
        approved_values = list(approved_existing_paths)
    except TypeError:
        return ["approved_existing_paths: must be a sequence of paths"]

    def normalize_for_validation(value: object, field: str) -> str | None:
        if not isinstance(value, str):
            errors.append(f"{field}: must contain only paths")
            return None
        try:
            raw = value.replace("\\", "/")
            path = PurePosixPath(raw)
            if (
                path.is_absolute()
                or not path.parts
                or any(part in {"", ".", ".."} for part in path.parts)
                or path.parts[0].endswith(":")
            ):
                raise ValueError
            return "/".join(path.parts)
        except ValueError:
            errors.append(f"{field}: contains an invalid path")
            return None

    initial_paths = [
        normalized
        for value in initial
        if (normalized := normalize_for_validation(value, "preflight.initial_product_paths"))
        is not None
    ]
    approved_paths = [
        normalized
        for value in approved_values
        if (normalized := normalize_for_validation(value, "approved_existing_paths"))
        is not None
    ]
    if len(set(initial_paths)) != len(initial_paths):
        errors.append("preflight.initial_product_paths: contains duplicate paths")
    if len(set(approved_paths)) != len(approved_paths):
        errors.append("approved_existing_paths: contains duplicate paths")
    initial_set = set(initial_paths)
    approved_set = set(approved_paths)
    for path in sorted(initial_set - approved_set):
        errors.append(f"unapproved pre-existing product path: {path}")
    for path in sorted(approved_set - initial_set):
        errors.append(f"approved path was not present in the initial product manifest: {path}")
    return sorted(set(errors))


def capture_snapshot(repository: Path, baseline_head: str) -> dict[str, object]:
    """Capture a canonical baseline-relative snapshot of all product changes."""
    root = _repository_root(repository)
    baseline = _baseline_commit(root, baseline_head)
    tracked_diff, tracked, untracked = _capture_components(root, baseline)
    tracked_digest = _bytes_digest(tracked_diff)
    untracked_digest = _canonical_digest(untracked)
    snapshot_digest = _canonical_digest(
        {
            "baseline_head": baseline,
            "tracked_diff_digest": tracked_digest,
            "untracked_manifest_digest": untracked_digest,
        }
    )
    changed_files: list[dict[str, str]] = [
        {**entry, "intent": SNAPSHOT_DISCOVERY_INTENT} for entry in tracked
    ]
    changed_files.extend(
        {
            "path": entry["path"],
            "source": "untracked",
            "status": "untracked",
            "content_digest": entry["content_digest"],
            "intent": SNAPSHOT_DISCOVERY_INTENT,
        }
        for entry in untracked
    )
    return {
        "baseline_head": baseline,
        "tracked_diff_digest": tracked_digest,
        "untracked_manifest_digest": untracked_digest,
        "snapshot_digest": snapshot_digest,
        "tracked_files": tracked,
        "untracked_files": untracked,
        "changed_files": sorted(
            changed_files,
            key=lambda item: (item["path"], item["source"], item["status"]),
        ),
    }
