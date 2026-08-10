"""Build a verification fingerprint from the current repository state."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shlex
import shutil
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
_TOOLCHAIN_VERSION_ARGS = {
    "cargo": ("--version",),
    "dotnet": ("--version",),
    "go": ("version",),
    "npm": ("--version",),
    "pnpm": ("--version",),
    "python": ("--version",),
    "pytest": ("--version",),
    "ruby": ("--version",),
    "yarn": ("--version",),
}


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
    return result.stdout if "-z" in args else result.stdout.strip()


def _git_changed_paths(root: Path) -> list[str]:
    status = _git_output(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    paths: set[str] = set()
    records = status.split("\x00")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if len(record) < 4:
            continue
        raw_paths = [record[3:]]
        if "R" in record[:2] or "C" in record[:2]:
            if index < len(records):
                raw_paths.append(records[index])
                index += 1
        for raw in raw_paths:
            if not raw:
                continue
            relative, _ = _relative_path(root, raw, require_file=False)
            if any(part.lower() in _EXCLUDED_DIRS for part in Path(relative).parts):
                continue
            paths.add(relative)
    return sorted(paths)


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


def _command_executable(command: str) -> str:
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return "unknown"
    token = tokens[0].strip("\"'")
    name = Path(token).name.lower()
    for suffix in (".cmd", ".exe", ".bat", ".com"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name or "unknown"


def _toolchain_identity(executable: str) -> tuple[str, str]:
    version_args = _TOOLCHAIN_VERSION_ARGS.get(executable)
    resolved = shutil.which(executable) if version_args else None
    if resolved is None:
        return "unavailable", "unavailable"
    try:
        result = subprocess.run(
            [resolved, *version_args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return str(Path(resolved).resolve()), "unavailable"
    output = (result.stdout.strip() or result.stderr.strip()).splitlines()
    version = re.sub(r"\s+", " ", output[0]).strip()[:256] if output else "unavailable"
    if result.returncode != 0:
        version = "unavailable"
    return str(Path(resolved).resolve()), version or "unavailable"


def _environment_identity(command: str) -> dict[str, str]:
    """Collect non-secret environment facts from the local execution host."""

    command_executable = _command_executable(command)
    command_path, command_toolchain = _toolchain_identity(command_executable)
    return {
        "command_executable": command_executable,
        "command_executable_path": command_path,
        "command_toolchain": command_toolchain,
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
        "environment": _environment_identity(command),
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
