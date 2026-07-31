#!/usr/bin/env python3
"""Canonical, fail-closed product snapshots for GPT Pro Codex Loop reviews."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Sequence


SCHEMA_VERSION = 1
METADATA_DIRECTORY = ".ai-pro-loop"
SNAPSHOT_DISCOVERY_INTENT = "snapshot-discovered product change"
MAX_STABILITY_SAMPLES = 3
PREFLIGHT_FIELDS = {
    "schema_version",
    "baseline_head",
    "baseline_snapshot_digest",
    "tracked_manifest_digest",
    "untracked_manifest_digest",
    "tracked_files",
    "untracked_files",
    "initial_product_paths",
}


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


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"value is not canonical JSON: {exc}") from exc


def _canonical_digest(value: object) -> str:
    return _bytes_digest(_canonical_json(value).encode("utf-8"))


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _decode_z(raw: bytes, label: str) -> list[bytes]:
    if not raw:
        return []
    if not raw.endswith(b"\0"):
        raise SnapshotError(f"git returned an unterminated {label}")
    return raw[:-1].split(b"\0")


def _decode_path(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SnapshotError("git returned a path that is not valid UTF-8") from exc


def _repository_root(repository: Path) -> Path:
    supplied = repository.resolve()
    if not supplied.is_dir():
        raise SnapshotError("repository path is not a directory")
    try:
        root_text = run_git(supplied, "rev-parse", "--show-toplevel").decode(
            "utf-8", errors="strict"
        ).strip()
    except UnicodeDecodeError as exc:
        raise SnapshotError("git returned a repository path that is not valid UTF-8") from exc
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
    candidate = PurePosixPath(value.replace("\\", "/"))
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.parts[0].endswith(":")
    ):
        raise SnapshotError(f"invalid product path: {value}")
    normalized = "/".join(candidate.parts)
    parent = repository.joinpath(*candidate.parts[:-1]).resolve()
    try:
        parent.relative_to(repository)
    except ValueError as exc:
        raise SnapshotError(
            f"product path parent resolves outside repository: {normalized}"
        ) from exc
    return normalized


def _filesystem_path(repository: Path, normalized: str) -> Path:
    return repository.joinpath(*PurePosixPath(normalized).parts)


def _is_metadata_path(repository: Path, path: str) -> bool:
    first = path.split("/", 1)[0]
    if first == METADATA_DIRECTORY:
        return True
    if first.casefold() != METADATA_DIRECTORY.casefold():
        return False
    if os.path.normcase(first) == os.path.normcase(METADATA_DIRECTORY):
        return True
    actual = repository / first
    canonical = repository / METADATA_DIRECTORY
    try:
        return actual.exists() and canonical.exists() and actual.samefile(canonical)
    except OSError as exc:
        raise SnapshotError("could not determine metadata path identity") from exc


def _check_product_path(repository: Path, raw_path: str) -> str:
    path = _normalize_path(repository, raw_path)
    if _is_metadata_path(repository, path):
        raise SnapshotError(".ai-pro-loop metadata must not be tracked or staged")
    return path


def _kind_for_mode(mode: str) -> str:
    if mode == "120000":
        return "symlink"
    if mode == "160000":
        return "submodule"
    if mode in {"100644", "100755"}:
        return "file"
    raise SnapshotError(f"unsupported Git mode: {mode}")


def _object_state(
    repository: Path, path: str, mode: str, object_id: str
) -> dict[str, str]:
    kind = _kind_for_mode(mode)
    return {
        "path": path,
        "mode": mode,
        "kind": kind,
        "content_digest": _object_content_digest(
            str(repository), kind, object_id
        ),
    }


@lru_cache(maxsize=4096)
def _object_content_digest(
    repository_text: str, kind: str, object_id: str
) -> str:
    if kind == "submodule":
        content = object_id.encode("ascii")
    else:
        content = run_git(Path(repository_text), "cat-file", "blob", object_id)
    return _bytes_digest(content)


def _baseline_map(
    repository: Path, baseline: str
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    raw = run_git(
        repository, "ls-tree", "-rz", "--full-tree", baseline
    )
    for record in _decode_z(raw, "tree record"):
        try:
            header, raw_path = record.split(b"\t", 1)
            mode_raw, _type_raw, object_raw = header.split(b" ", 2)
            mode = mode_raw.decode("ascii")
            object_id = object_raw.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise SnapshotError("git returned an invalid tree record") from exc
        path = _check_product_path(repository, _decode_path(raw_path))
        if path in result:
            raise SnapshotError(f"duplicate baseline path: {path}")
        result[path] = _object_state(repository, path, mode, object_id)
    return result


def _index_map(repository: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    raw = run_git(repository, "ls-files", "--stage", "-z")
    for record in _decode_z(raw, "index record"):
        try:
            header, raw_path = record.split(b"\t", 1)
            mode_raw, object_raw, stage_raw = header.split(b" ", 2)
            mode = mode_raw.decode("ascii")
            object_id = object_raw.decode("ascii")
            stage = int(stage_raw.decode("ascii"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SnapshotError("git returned an invalid index record") from exc
        path = _check_product_path(repository, _decode_path(raw_path))
        if stage != 0:
            raise SnapshotError(f"unmerged index entry: {path}")
        if path in result:
            raise SnapshotError(f"duplicate index path: {path}")
        result[path] = _object_state(repository, path, mode, object_id)
    return result


def _submodule_worktree_state(
    repository: Path, path: str
) -> dict[str, str] | None:
    location = _filesystem_path(repository, path)
    if not location.exists():
        return None
    try:
        commit = run_git(location, "rev-parse", "--verify", "HEAD^{commit}").decode(
            "ascii", errors="strict"
        ).strip()
    except (SnapshotError, UnicodeDecodeError) as exc:
        raise SnapshotError(f"submodule worktree is unavailable: {path}") from exc
    if run_git(location, "status", "--porcelain", "--untracked-files=all"):
        raise SnapshotError(f"dirty submodule worktree: {path}")
    return {
        "path": path,
        "mode": "160000",
        "kind": "submodule",
        "content_digest": _bytes_digest(commit.encode("ascii")),
    }


def _worktree_state(
    repository: Path,
    path: str,
    reference: dict[str, str] | None,
) -> dict[str, str] | None:
    location = _filesystem_path(repository, path)
    if reference is not None and reference["kind"] == "submodule":
        return _submodule_worktree_state(repository, path)
    if not os.path.lexists(location):
        return None
    try:
        info = location.lstat()
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(location).encode("utf-8", errors="surrogateescape")
            return {
                "path": path,
                "mode": "120000",
                "kind": "symlink",
                "content_digest": _bytes_digest(target),
            }
        if not stat.S_ISREG(info.st_mode):
            raise SnapshotError(f"unsupported product file type: {path}")
        content = location.read_bytes()
    except OSError as exc:
        raise SnapshotError(f"could not inspect product path: {path}") from exc
    if os.name == "posix":
        mode = "100755" if info.st_mode & stat.S_IXUSR else "100644"
    elif reference is not None and reference["mode"] in {"100644", "100755"}:
        mode = reference["mode"]
    else:
        mode = "100644"
    return {
        "path": path,
        "mode": mode,
        "kind": "file",
        "content_digest": _bytes_digest(content),
    }


def _tracked_manifest(
    repository: Path, baseline: str
) -> list[dict[str, object]]:
    baseline_files = _baseline_map(repository, baseline)
    index_files = _index_map(repository)
    manifest: list[dict[str, object]] = []
    for path in sorted(set(baseline_files) | set(index_files)):
        baseline_state = baseline_files.get(path)
        index_state = index_files.get(path)
        worktree_state = _worktree_state(
            repository, path, index_state if index_state is not None else baseline_state
        )
        if baseline_state == index_state == worktree_state:
            continue
        manifest.append(
            {
                "path": path,
                "baseline": baseline_state,
                "index": index_state,
                "worktree": worktree_state,
            }
        )
    return manifest


def _untracked_manifest(repository: Path) -> list[dict[str, str]]:
    raw = run_git(
        repository, "ls-files", "--others", "--exclude-standard", "-z"
    )
    entries: list[dict[str, str]] = []
    for raw_path in _decode_z(raw, "untracked path list"):
        path = _normalize_path(repository, _decode_path(raw_path))
        if _is_metadata_path(repository, path):
            continue
        state = _worktree_state(repository, path, None)
        if state is None:
            raise SnapshotError(f"untracked product path disappeared: {path}")
        entries.append(state)
    return sorted(entries, key=lambda item: item["path"])


def _fixed_review_diff(repository: Path, baseline: str) -> bytes:
    return run_git(
        repository,
        "-c",
        "diff.external=",
        "-c",
        "diff.renames=false",
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--no-renames",
        baseline,
        "--",
    )


def _observation(
    repository: Path, baseline: str
) -> tuple[
    bytes,
    list[dict[str, object]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    return (
        _fixed_review_diff(repository, baseline),
        _tracked_manifest(repository, baseline),
        _untracked_manifest(repository),
        _parse_presentation_changes(repository, baseline),
    )


def _stable_observation(
    repository: Path, baseline: str
) -> tuple[
    bytes,
    list[dict[str, object]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    for _ in range(MAX_STABILITY_SAMPLES):
        before = _observation(repository, baseline)
        after = _observation(repository, baseline)
        if before == after:
            return after
    raise SnapshotError("product state changed while capturing snapshot")


def _initial_paths(
    tracked: Sequence[dict[str, object]], untracked: Sequence[dict[str, str]]
) -> list[str]:
    return sorted(
        {str(item["path"]) for item in tracked}
        | {str(item["path"]) for item in untracked}
    )


def _preflight_errors(preflight: object) -> list[str]:
    if not isinstance(preflight, dict):
        return ["preflight: must be an object"]
    errors: list[str] = []
    missing = sorted(PREFLIGHT_FIELDS - set(preflight))
    unknown = sorted(set(preflight) - PREFLIGHT_FIELDS)
    errors.extend(f"preflight.{field}: missing required field" for field in missing)
    errors.extend(f"preflight.{field}: unknown field" for field in unknown)
    if missing:
        return sorted(errors)
    version = preflight.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        errors.append("preflight.schema_version: must be integer 1")
    baseline = preflight.get("baseline_head")
    if not isinstance(baseline, str) or not baseline:
        errors.append("preflight.baseline_head: must be a non-empty string")
    elif re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline) is None:
        errors.append("preflight.baseline_head: must be a canonical commit ID")
    tracked = preflight.get("tracked_files")
    untracked = preflight.get("untracked_files")
    initial = preflight.get("initial_product_paths")
    if not isinstance(tracked, list):
        errors.append("preflight.tracked_files: must be a list")
        tracked = []
    if not isinstance(untracked, list):
        errors.append("preflight.untracked_files: must be a list")
        untracked = []
    if not isinstance(initial, list) or any(not isinstance(path, str) for path in initial):
        errors.append("preflight.initial_product_paths: must be a list of paths")
        initial = []

    tracked_paths: list[str] = []

    def is_canonical_manifest_path(path: str) -> bool:
        candidate = PurePosixPath(path)
        return (
            bool(path)
            and "\\" not in path
            and not candidate.is_absolute()
            and bool(candidate.parts)
            and not candidate.parts[0].endswith(":")
            and all(part not in {"", ".", ".."} for part in candidate.parts)
            and "/".join(candidate.parts) == path
            and candidate.parts[0].casefold() != METADATA_DIRECTORY.casefold()
        )

    for index, entry in enumerate(tracked):
        prefix = f"preflight.tracked_files.{index}"
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "baseline",
            "index",
            "worktree",
        }:
            errors.append(f"{prefix}: invalid tracked manifest entry")
            continue
        path = entry.get("path")
        if not isinstance(path, str):
            errors.append(f"{prefix}.path: must be a path")
            continue
        if not is_canonical_manifest_path(path):
            errors.append(f"{prefix}.path: invalid canonical path")
            continue
        tracked_paths.append(path)
        for state_name in ("baseline", "index", "worktree"):
            state_value = entry.get(state_name)
            if state_value is None:
                continue
            if not isinstance(state_value, dict) or set(state_value) != {
                "path",
                "mode",
                "kind",
                "content_digest",
            }:
                errors.append(f"{prefix}.{state_name}: invalid state")
                continue
            if state_value.get("path") != path:
                errors.append(f"{prefix}.{state_name}.path: does not match entry path")
            try:
                expected_kind = _kind_for_mode(str(state_value.get("mode")))
            except SnapshotError:
                errors.append(f"{prefix}.{state_name}.mode: invalid Git mode")
            else:
                if state_value.get("kind") != expected_kind:
                    errors.append(f"{prefix}.{state_name}.kind: does not match mode")
            digest = state_value.get("content_digest")
            if (
                not isinstance(digest, str)
                or len(digest) != 71
                or not digest.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in digest[7:])
            ):
                errors.append(f"{prefix}.{state_name}.content_digest: invalid digest")
        if entry.get("baseline") == entry.get("index") == entry.get("worktree"):
            errors.append(f"{prefix}: unchanged entry must not be present")

    untracked_paths: list[str] = []
    for index, entry in enumerate(untracked):
        prefix = f"preflight.untracked_files.{index}"
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "mode",
            "kind",
            "content_digest",
        }:
            errors.append(f"{prefix}: invalid untracked manifest entry")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not is_canonical_manifest_path(path):
            errors.append(f"{prefix}.path: must be a path")
            continue
        untracked_paths.append(path)
        try:
            expected_kind = _kind_for_mode(str(entry.get("mode")))
        except SnapshotError:
            errors.append(f"{prefix}.mode: invalid Git mode")
        else:
            if entry.get("kind") != expected_kind:
                errors.append(f"{prefix}.kind: does not match mode")
        digest = entry.get("content_digest")
        if (
            not isinstance(digest, str)
            or len(digest) != 71
            or not digest.startswith("sha256:")
            or any(character not in "0123456789abcdef" for character in digest[7:])
        ):
            errors.append(f"{prefix}.content_digest: invalid digest")

    if tracked_paths != sorted(set(tracked_paths)):
        errors.append("preflight.tracked_files: paths must be sorted and unique")
    if untracked_paths != sorted(set(untracked_paths)):
        errors.append("preflight.untracked_files: paths must be sorted and unique")
    expected_initial = sorted(set(tracked_paths) | set(untracked_paths))
    if initial != expected_initial:
        errors.append("preflight.initial_product_paths: does not match manifests")
    tracked_digest = _canonical_digest(tracked)
    untracked_digest = _canonical_digest(untracked)
    if preflight.get("tracked_manifest_digest") != tracked_digest:
        errors.append("preflight.tracked_manifest_digest: does not match manifest")
    if preflight.get("untracked_manifest_digest") != untracked_digest:
        errors.append("preflight.untracked_manifest_digest: does not match manifest")
    if isinstance(baseline, str):
        expected_snapshot = _canonical_digest(
            {
                "schema_version": SCHEMA_VERSION,
                "baseline_head": baseline,
                "tracked_manifest_digest": tracked_digest,
                "untracked_manifest_digest": untracked_digest,
            }
        )
        if preflight.get("baseline_snapshot_digest") != expected_snapshot:
            errors.append(
                "preflight.baseline_snapshot_digest: does not match manifests"
            )
    return sorted(set(errors))


def inspect_preflight(repository: Path, baseline_head: str) -> dict[str, object]:
    """Record the immutable baseline/index/worktree state before implementation."""
    root = _repository_root(repository)
    baseline = _baseline_commit(root, baseline_head)
    _diff, tracked, untracked, _presentation = _stable_observation(root, baseline)
    tracked_digest = _canonical_digest(tracked)
    untracked_digest = _canonical_digest(untracked)
    baseline_snapshot_digest = _canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "baseline_head": baseline,
            "tracked_manifest_digest": tracked_digest,
            "untracked_manifest_digest": untracked_digest,
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_head": baseline,
        "baseline_snapshot_digest": baseline_snapshot_digest,
        "tracked_manifest_digest": tracked_digest,
        "untracked_manifest_digest": untracked_digest,
        "tracked_files": tracked,
        "untracked_files": untracked,
        "initial_product_paths": _initial_paths(tracked, untracked),
    }


def _normalize_approval_path(value: object, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str):
        errors.append(f"{field}: must contain only paths")
        return None
    candidate = PurePosixPath(value.replace("\\", "/"))
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.parts[0].endswith(":")
    ):
        errors.append(f"{field}: contains an invalid path")
        return None
    return "/".join(candidate.parts)


def validate_preflight(
    preflight: dict[str, object], approved_existing_paths: Sequence[str]
) -> list[str]:
    """Validate immutable preflight structure, digests, and exact path approval."""
    errors = _preflight_errors(preflight)
    if errors:
        return errors
    if isinstance(approved_existing_paths, (str, bytes)):
        return ["approved_existing_paths: must be a sequence of paths"]
    try:
        approved_values = list(approved_existing_paths)
    except TypeError:
        return ["approved_existing_paths: must be a sequence of paths"]
    initial = list(preflight["initial_product_paths"])
    approved = [
        normalized
        for value in approved_values
        if (
            normalized := _normalize_approval_path(
                value, "approved_existing_paths", errors
            )
        )
        is not None
    ]
    if len(set(approved)) != len(approved):
        errors.append("approved_existing_paths: contains duplicate paths")
    initial_set = set(initial)
    approved_set = set(approved)
    for path in sorted(initial_set - approved_set):
        errors.append(f"unapproved pre-existing product path: {path}")
    for path in sorted(approved_set - initial_set):
        errors.append(
            f"approved path was not present in the initial product manifest: {path}"
        )
    return sorted(set(errors))


def _parse_presentation_changes(
    repository: Path, baseline: str
) -> list[dict[str, str]]:
    raw = run_git(
        repository,
        "-c",
        "diff.external=",
        "-c",
        "diff.renames=true",
        "diff",
        "--name-status",
        "-z",
        "-M",
        "--no-ext-diff",
        "--no-textconv",
        baseline,
        "--",
    )
    tokens = [_decode_path(item) for item in _decode_z(raw, "diff status")]
    names = {
        "A": "added",
        "C": "copied",
        "D": "deleted",
        "M": "modified",
        "R": "renamed",
        "T": "type_changed",
    }
    changes: list[dict[str, str]] = []
    position = 0
    while position < len(tokens):
        status_token = tokens[position]
        position += 1
        code = status_token[:1]
        if code == "U":
            raise SnapshotError("unmerged index entry")
        if code not in names:
            raise SnapshotError(f"unsupported Git status: {status_token}")
        count = 2 if code in {"C", "R"} else 1
        if position + count > len(tokens):
            raise SnapshotError("incomplete Git status record")
        paths = [
            _check_product_path(repository, value)
            for value in tokens[position : position + count]
        ]
        position += count
        item = {
            "path": paths[-1],
            "source": "tracked",
            "status": names[code],
        }
        if count == 2:
            item["previous_path"] = paths[0]
        changes.append(item)
    return changes


def _changed_files(
    tracked: list[dict[str, object]],
    untracked: list[dict[str, str]],
    preflight: dict[str, object],
    presentation: list[dict[str, str]],
) -> list[dict[str, object]]:
    initial = set(preflight["initial_product_paths"])
    before_tracked = {
        str(entry["path"]): entry for entry in preflight["tracked_files"]
    }
    before_untracked = {
        str(entry["path"]): entry for entry in preflight["untracked_files"]
    }
    current_tracked = {str(entry["path"]): entry for entry in tracked}
    changes: list[dict[str, object]] = []
    represented: set[str] = set()
    for item in presentation:
        path = item["path"]
        prior_path = item.get("previous_path")
        represented.add(path)
        if prior_path:
            represented.add(prior_path)
        preexisting = path in initial or (prior_path is not None and prior_path in initial)
        prior_value = before_tracked.get(path, before_untracked.get(path))
        current_value = current_tracked.get(path)
        changed = current_value != prior_value
        if prior_path is not None:
            changed = changed or (
                current_tracked.get(prior_path)
                != before_tracked.get(prior_path, before_untracked.get(prior_path))
            )
        changes.append(
            {
                **item,
                "intent": SNAPSHOT_DISCOVERY_INTENT,
                "preexisting": preexisting,
                "changed_since_preflight": changed,
            }
        )
    for entry in tracked:
        path = str(entry["path"])
        if path in represented:
            continue
        prior_value = before_tracked.get(path, before_untracked.get(path))
        changes.append(
            {
                "path": path,
                "source": "tracked",
                "status": "modified",
                "intent": SNAPSHOT_DISCOVERY_INTENT,
                "preexisting": path in initial,
                "changed_since_preflight": entry != prior_value,
            }
        )
    for entry in untracked:
        path = entry["path"]
        prior_value = before_untracked.get(path, before_tracked.get(path))
        changes.append(
            {
                "path": path,
                "source": "untracked",
                "status": "untracked",
                "content_digest": entry["content_digest"],
                "intent": SNAPSHOT_DISCOVERY_INTENT,
                "preexisting": path in initial,
                "changed_since_preflight": entry != prior_value,
            }
        )
    return sorted(
        changes,
        key=lambda item: (
            str(item["path"]),
            str(item["source"]),
            str(item["status"]),
        ),
    )


def capture_snapshot(
    repository: Path, baseline_head: str, preflight: dict[str, object]
) -> dict[str, object]:
    """Capture state bound to an immutable, validated preflight."""
    root = _repository_root(repository)
    baseline = _baseline_commit(root, baseline_head)
    structural_errors = _preflight_errors(preflight)
    if structural_errors:
        raise SnapshotError("invalid preflight: " + "; ".join(structural_errors))
    if preflight["baseline_head"] != baseline:
        raise SnapshotError("baseline does not match immutable preflight")
    tracked_diff, tracked, untracked, presentation = _stable_observation(
        root, baseline
    )
    tracked_manifest_digest = _canonical_digest(tracked)
    untracked_manifest_digest = _canonical_digest(untracked)
    snapshot_digest = _canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "baseline_head": baseline,
            "baseline_snapshot_digest": preflight["baseline_snapshot_digest"],
            "tracked_manifest_digest": tracked_manifest_digest,
            "untracked_manifest_digest": untracked_manifest_digest,
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_head": baseline,
        "preflight_digest": _canonical_digest(preflight),
        "initial_product_paths": list(preflight["initial_product_paths"]),
        "baseline_snapshot_digest": preflight["baseline_snapshot_digest"],
        "tracked_manifest_digest": tracked_manifest_digest,
        "tracked_diff_digest": _bytes_digest(tracked_diff),
        "untracked_manifest_digest": untracked_manifest_digest,
        "snapshot_digest": snapshot_digest,
        "tracked_files": tracked,
        "untracked_files": untracked,
        "changed_files": _changed_files(
            tracked, untracked, preflight, presentation
        ),
    }


def _load_json(path: Path) -> object:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SnapshotError(f"could not read JSON file: {path}") from exc
    try:
        from validate_packet import PacketValidationError, strict_json_loads

        return strict_json_loads(raw)
    except (ImportError, PacketValidationError, ValueError) as exc:
        raise SnapshotError(f"invalid JSON file: {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capture_snapshot.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect-preflight")
    inspect_parser.add_argument("repository", type=Path)
    inspect_parser.add_argument("baseline")
    validate_parser = subparsers.add_parser("validate-preflight")
    validate_parser.add_argument("preflight_json", type=Path)
    validate_parser.add_argument(
        "--approved-existing-path", action="append", default=[]
    )
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("repository", type=Path)
    capture_parser.add_argument("baseline")
    capture_parser.add_argument("--preflight", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect-preflight":
            result = inspect_preflight(args.repository, args.baseline)
        elif args.command == "validate-preflight":
            loaded = _load_json(args.preflight_json)
            errors = validate_preflight(loaded, args.approved_existing_path)
            if errors:
                raise SnapshotError("; ".join(errors))
            result = loaded
        else:
            loaded = _load_json(args.preflight)
            if not isinstance(loaded, dict):
                raise SnapshotError("preflight JSON must be an object")
            result = capture_snapshot(args.repository, args.baseline, loaded)
    except SnapshotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(_canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
