"""Build a verification fingerprint from the current repository state."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence


class FingerprintError(ValueError):
    """Raised when verification inputs cannot be bound to the repository."""


_EXCLUDED_DIRS = frozenset(
    {
        ".ai-pro-loop",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "venv",
    }
)
_CONFIG_NAMES = frozenset(
    {
        ".python-version",
        "cargo.toml",
        "jest.config.js",
        "jest.config.ts",
        "package.json",
        "pipfile",
        "pyproject.toml",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        "tsconfig.json",
        "vitest.config.js",
        "vitest.config.ts",
    }
)
_PATH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z0-9_.-]+[\\/])*[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+"
)


def _root(repo: Path) -> Path:
    root = Path(repo).resolve()
    if not root.is_dir():
        raise FingerprintError("repo must be an existing directory")
    return root


def _relative_path(
    root: Path,
    raw: str,
    *,
    require_file: bool,
) -> tuple[str, Path]:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise FingerprintError("file path must be a non-empty string")
    candidate = Path(raw)
    if candidate.is_absolute():
        raise FingerprintError("file path must be repository-relative")
    resolved = (root / candidate).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise FingerprintError("file path escapes repository") from error
    if require_file and not resolved.is_file():
        raise FingerprintError(f"file does not exist: {raw}")
    return relative.as_posix(), resolved


def _git_output(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        raise FingerprintError("git is unavailable") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FingerprintError(f"git input unavailable: {detail or 'unknown error'}")
    return result.stdout.strip()


def _git_changed_paths(root: Path) -> list[str]:
    status = _git_output(root, "status", "--porcelain=v1", "--untracked-files=all")
    paths: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.rsplit(" -> ", 1)[1]
        relative, _ = _relative_path(root, raw, require_file=False)
        if any(part.lower() in _EXCLUDED_DIRS for part in Path(relative).parts):
            continue
        paths.append(relative)
    return paths


def _command_targets(root: Path, command: str) -> list[str]:
    targets: list[str] = []
    for raw in _PATH_TOKEN.findall(command):
        try:
            relative, _ = _relative_path(root, raw, require_file=True)
        except FingerprintError:
            continue
        targets.append(relative)
    return targets


def _is_config_or_lock(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in _CONFIG_NAMES
        or name.endswith(".lock")
        or (name.startswith("requirements") and name.endswith(".txt"))
        or name in {"go.mod", "go.sum", "gemfile", "gemfile.lock", "pipfile.lock"}
    )


def _config_paths(root: Path) -> list[str]:
    paths: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part.lower() in _EXCLUDED_DIRS for part in path.parts):
            continue
        if _is_config_or_lock(path):
            relative, _ = _relative_path(
                root, path.relative_to(root).as_posix(), require_file=True
            )
            paths.append(relative)
    return paths


def _input_record(root: Path, relative: str, kinds: set[str]) -> dict[str, object]:
    _, path = _relative_path(root, relative, require_file=False)
    record: dict[str, object] = {"kinds": sorted(kinds), "path": relative}
    if path.is_file():
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        record["deleted"] = True
    return record


def _environment_identity() -> dict[str, str]:
    """Collect non-secret environment facts from the local execution host."""

    return {
        "executable": str(Path(sys.executable).resolve()),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


def compute_fingerprint(
    repo: Path,
    *,
    command: str,
    target_files: Sequence[str] = (),
) -> str:
    """Return a digest for the current tree and automatically discovered inputs.

    ``target_files`` is an optional additive hint for a CLI caller. It cannot
    remove changed files, command targets, or lock/config inputs from the
    manifest. Git identity, file contents, and environment identity are read
    here rather than supplied by the routing caller.
    """

    if not isinstance(command, str) or not command.strip():
        raise FingerprintError("command must be non-empty")
    root = _root(repo)
    base_tree = _git_output(root, "rev-parse", "--verify", "HEAD")
    if target_files is None:
        target_files = ()
    elif isinstance(target_files, str):
        target_files = [target_files]

    sources: dict[str, set[str]] = {}
    for raw in target_files:
        relative, _ = _relative_path(root, raw, require_file=True)
        sources.setdefault(relative, set()).add("explicit-target")
    for relative in _command_targets(root, command):
        sources.setdefault(relative, set()).add("command-target")
    for relative in _git_changed_paths(root):
        sources.setdefault(relative, set()).add("changed")
    for relative in _config_paths(root):
        sources.setdefault(relative, set()).add("lock-config")

    manifest = {
        "base_tree": base_tree,
        "command": command,
        "environment": _environment_identity(),
        "inputs": [
            _input_record(root, relative, sources[relative])
            for relative in sorted(sources)
        ],
        "schema": 2,
    }
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute a verification fingerprint from the current Git tree."
    )
    parser.add_argument("--repo", default=".", help="repository root (default: .)")
    parser.add_argument("--command", required=True, help="verification command")
    parser.add_argument(
        "--target-file",
        action="append",
        default=[],
        help="optional repository-relative target hint; may be repeated",
    )
    args = parser.parse_args(argv)
    try:
        print(
            compute_fingerprint(
                Path(args.repo),
                command=args.command,
                target_files=args.target_file,
            )
        )
    except FingerprintError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
