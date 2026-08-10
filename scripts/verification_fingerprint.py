"""Build a verification-input fingerprint from the current repository files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence


class FingerprintError(ValueError):
    """Raised when a verification input cannot be bound to the repository."""


def _relative_file(repo: Path, raw: str) -> tuple[str, Path]:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise FingerprintError("file path must be a non-empty string")
    candidate = Path(raw)
    if candidate.is_absolute():
        raise FingerprintError("file path must be repository-relative")
    root = repo.resolve()
    resolved = (root / candidate).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise FingerprintError("file path escapes repository") from error
    if not resolved.is_file():
        raise FingerprintError(f"file does not exist: {raw}")
    return relative.as_posix(), resolved


def _file_record(repo: Path, raw: str) -> dict[str, str]:
    relative, path = _relative_file(repo, raw)
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def compute_fingerprint(
    repo: Path,
    *,
    command: str,
    base_tree: str,
    relevant_files: Sequence[str],
    lock_config_files: Sequence[str],
    environment_identity: Mapping[str, str],
) -> str:
    """Return a stable digest for the exact inputs a verification command reads.

    The helper reads file contents itself. Callers must obtain ``base_tree`` from
    the trusted VCS adapter and pass only material environment identity fields.
    """

    if not isinstance(command, str) or not command.strip():
        raise FingerprintError("command must be non-empty")
    if not isinstance(base_tree, str) or not base_tree.strip():
        raise FingerprintError("base_tree must be non-empty")
    if not isinstance(environment_identity, Mapping) or not environment_identity:
        raise FingerprintError("environment_identity must be non-empty")
    environment: dict[str, str] = {}
    for key, value in sorted(environment_identity.items()):
        if (
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, str)
            or not value.strip()
        ):
            raise FingerprintError("environment identity must contain strings")
        environment[key] = value

    root = Path(repo).resolve()
    manifest = {
        "command": command,
        "base_tree": base_tree,
        "relevant_files": sorted(
            (_file_record(root, path) for path in relevant_files),
            key=lambda item: item["path"],
        ),
        "lock_config_files": sorted(
            (_file_record(root, path) for path in lock_config_files),
            key=lambda item: item["path"],
        ),
        "environment": environment,
    }
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit("Import compute_fingerprint from this helper; do not self-report a fingerprint.")
