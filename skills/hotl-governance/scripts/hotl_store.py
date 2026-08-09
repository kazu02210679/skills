"""Transactional persistence for HOTL event logs and immutable evidence."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import socket
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterator, Mapping, Sequence

from hotl_contract import (
    ContractError,
    canonical_digest,
    canonical_json_bytes,
    normalize_repo_path,
    validate_event,
)


EXECUTION_ID = re.compile(r"EXEC-[0-9A-F]{12}\Z")
EVIDENCE_NAME = re.compile(r"[0-9a-f]{64}\Z")


class StoreError(RuntimeError):
    """A stable storage-boundary failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RunPaths:
    root: Path
    state: Path
    events: Path
    evidence: Path
    transactions: Path
    lock: Path


class _RecoveryIssue(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise StoreError("RECOVERY_REQUIRED", "Could not inspect a managed path.") from error
    if stat.S_ISLNK(metadata.st_mode):
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse)


def _artifact_error(error: BaseException | None = None) -> StoreError:
    failure = StoreError(
        "UNSAFE_ARTIFACT",
        "Artifact path could not be opened as a stable plain repository file.",
    )
    if error is not None:
        failure.__cause__ = error
    return failure


def _read_open_file(fd: int) -> bytes:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise _artifact_error()
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    after = os.fstat(fd)
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        getattr(value, "st_mtime_ns", None),
        getattr(value, "st_ctime_ns", None),
    )
    if identity(before) != identity(after):
        raise _artifact_error()
    return b"".join(chunks)


def _windows_final_path(fd: int) -> Path:
    import ctypes
    import msvcrt

    handle = msvcrt.get_osfhandle(fd)
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetFinalPathNameByHandleW(
        ctypes.c_void_p(handle), buffer, len(buffer), 0
    )
    if length == 0 or length >= len(buffer):
        raise _artifact_error()
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


def _read_repository_artifact_windows(repository: Path, normalized: str) -> bytes:
    supplied = repository.absolute()
    if _is_link_or_reparse(supplied) or not supplied.is_dir():
        raise _artifact_error()
    root = supplied.resolve(strict=True)
    candidate = root
    for part in PurePosixPath(normalized).parts:
        candidate = candidate / part
        if _is_link_or_reparse(candidate):
            raise _artifact_error()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(candidate, flags)
    try:
        opened = _windows_final_path(fd)
        try:
            common = os.path.commonpath((str(root), str(opened)))
            if os.path.normcase(common) != os.path.normcase(str(root)):
                raise _artifact_error()
        except ValueError as error:
            raise _artifact_error(error) from error
        content = _read_open_file(fd)
        common = os.path.commonpath((str(root), str(_windows_final_path(fd))))
        if os.path.normcase(common) != os.path.normcase(str(root)):
            raise _artifact_error()
        return content
    finally:
        os.close(fd)


def _read_repository_artifact_posix(repository: Path, normalized: str) -> bytes:
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        current = os.open(repository, root_flags)
        descriptors.append(current)
        root_metadata = os.fstat(current)
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise _artifact_error()
        parts = PurePosixPath(normalized).parts
        for part in parts[:-1]:
            current = os.open(part, root_flags, dir_fd=current)
            descriptors.append(current)
            if not stat.S_ISDIR(os.fstat(current).st_mode):
                raise _artifact_error()
        artifact = os.open(parts[-1], file_flags, dir_fd=current)
        descriptors.append(artifact)
        return _read_open_file(artifact)
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def read_repository_artifact(repository: Path, raw_path: str) -> bytes:
    """Read a repository artifact through one link-safe, handle-bound operation."""
    try:
        normalized = normalize_repo_path(repository, raw_path)
        if os.name == "nt":
            return _read_repository_artifact_windows(Path(repository), normalized)
        return _read_repository_artifact_posix(Path(repository), normalized)
    except StoreError:
        raise
    except (ContractError, OSError, ValueError, TypeError) as error:
        raise _artifact_error(error) from error


def _require_plain_directory(path: Path, *, recovery: bool = True) -> None:
    if _is_link_or_reparse(path) or not path.is_dir():
        code = "RECOVERY_REQUIRED" if recovery else "INVALID_REPOSITORY"
        raise StoreError(code, "Managed directory is not a plain directory.")


def _ensure_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        _require_plain_directory(path)
        return
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StoreError("WRITE_FAILED", "Could not create a managed directory.") from error
    _require_plain_directory(path)


def _metadata_root(paths: RunPaths) -> Path:
    return paths.root.parent.parent


def _validate_layout(paths: RunPaths) -> None:
    metadata = _metadata_root(paths)
    if paths.root.parent != metadata / "runs":
        raise StoreError("UNSAFE_RUN_PATH", "Run path is outside the HOTL runs directory.")
    expected = RunPaths(
        root=paths.root,
        state=paths.root / "state.json",
        events=paths.root / "events.jsonl",
        evidence=metadata / "evidence",
        transactions=paths.root / "transactions",
        lock=paths.root / ".lock",
    )
    if paths != expected:
        raise StoreError("UNSAFE_RUN_PATH", "Run paths do not use the canonical HOTL layout.")


def resolve_run(repository: Path, execution_id: str) -> RunPaths:
    """Resolve one execution under ``.hotl/runs`` without creating it."""
    supplied = Path(repository).absolute()
    if not supplied.is_dir() or _is_link_or_reparse(supplied):
        raise StoreError("INVALID_REPOSITORY", "Repository path must be a plain directory.")
    repository_root = supplied.resolve()
    if not isinstance(execution_id, str) or EXECUTION_ID.fullmatch(execution_id) is None:
        raise StoreError("INVALID_EXECUTION_ID", "Invalid execution ID.")
    metadata = repository_root / ".hotl"
    root = metadata / "runs" / execution_id
    return RunPaths(
        root=root,
        state=root / "state.json",
        events=root / "events.jsonl",
        evidence=metadata / "evidence",
        transactions=root / "transactions",
        lock=root / ".lock",
    )


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(descriptor, value[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        windows_directory_open_unsupported = (
            os.name == "nt"
            and error.errno == errno.EACCES
            and getattr(error, "winerror", None) in (None, 5)
        )
        if windows_directory_open_unsupported:
            return
        raise
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def run_lock(path: Path) -> Iterator[None]:
    """Hold one exclusive lock and remove it only while it is still owned."""
    path = Path(path)
    _require_plain_directory(path.parent)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise StoreError("RUN_LOCKED", "Run is already locked.") from error
    except OSError as error:
        raise StoreError("LOCK_FAILED", "Could not create the run lock.") from error
    owned = os.fstat(descriptor)
    try:
        payload = canonical_json_bytes(
            {
                "created_at_unix": int(time.time()),
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "schema_version": 1,
            }
        )
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        finally:
            try:
                if os.path.samestat(owned, path.lstat()):
                    path.unlink()
            except OSError:
                pass


def _reject_float(_: str) -> object:
    raise ValueError("floating-point values are forbidden")


def _reject_constant(_: str) -> object:
    raise ValueError("non-finite values are forbidden")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _load_canonical_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise _RecoveryIssue("MALFORMED_LOG", f"{label} is not valid canonical JSON.") from error
    if not isinstance(value, dict):
        raise _RecoveryIssue("MALFORMED_LOG", f"{label} must be a JSON object.")
    try:
        canonical = canonical_json_bytes(value)
    except ContractError as error:
        raise _RecoveryIssue("MALFORMED_LOG", f"{label} is not canonical JSON.") from error
    if canonical != raw:
        raise _RecoveryIssue("MALFORMED_LOG", f"{label} is not canonically encoded.")
    return value


def _validated_log(raw: bytes, execution_id: str) -> tuple[list[dict[str, object]], str]:
    if not raw:
        raise _RecoveryIssue("MALFORMED_LOG", "Event log is empty.")
    lines = raw.splitlines(keepends=True)
    events: list[dict[str, object]] = []
    previous_hash: str | None = None
    for sequence, line in enumerate(lines, 1):
        if not line.endswith(b"\n"):
            raise _RecoveryIssue("MALFORMED_LOG", "Event log has an incomplete final record.")
        event = _load_canonical_object(line, f"event {sequence}")
        try:
            validate_event(event, previous_hash, sequence)
        except ContractError as error:
            raise _RecoveryIssue("MALFORMED_LOG", "Event chain validation failed.") from error
        if event["execution_id"] != execution_id:
            raise _RecoveryIssue("MALFORMED_LOG", "Event execution identity does not match its run.")
        previous_hash = canonical_digest(event)
        events.append(event)
    assert previous_hash is not None
    return events, previous_hash


def _validated_state(raw: bytes, execution_id: str) -> dict[str, object]:
    try:
        state = _load_canonical_object(raw, "state")
    except _RecoveryIssue as error:
        raise _RecoveryIssue("INVALID_STATE", "State is not valid canonical JSON.") from error
    if state.get("execution_id") != execution_id:
        raise _RecoveryIssue("INVALID_STATE", "State execution identity does not match its run.")
    return state


def _validate_witness(
    state: Mapping[str, object], count: int, head_hash: str, *, candidate: bool
) -> None:
    if state.get("event_count") != count or state.get("head_event_hash") != head_hash:
        if candidate:
            raise StoreError(
                "INVALID_STATE_WITNESS",
                "State event_count and head_event_hash must match the candidate log.",
            )
        raise _RecoveryIssue(
            "LOG_WITNESS_MISMATCH",
            "Persisted state witness does not match the event log.",
        )


def _validate_candidate(
    raw: bytes, state: dict[str, object], execution_id: str
) -> list[dict[str, object]]:
    try:
        events, head_hash = _validated_log(raw, execution_id)
        canonical_state = canonical_json_bytes(state)
        _validated_state(canonical_state, execution_id)
    except (_RecoveryIssue, ContractError) as error:
        raise StoreError("INVALID_TRANSACTION", "Candidate transaction is invalid.") from error
    _validate_witness(state, len(events), head_hash, candidate=True)
    return events


def _read_bytes(path: Path, reason: str, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise _RecoveryIssue(reason, f"Could not read {label}.") from error


def _load_persisted(paths: RunPaths) -> tuple[list[dict[str, object]], bytes, dict[str, object]]:
    raw_events = _read_bytes(paths.events, "MALFORMED_LOG", "event log")
    raw_state = _read_bytes(paths.state, "INVALID_STATE", "state")
    events, head_hash = _validated_log(raw_events, paths.root.name)
    state = _validated_state(raw_state, paths.root.name)
    _validate_witness(state, len(events), head_hash, candidate=False)
    return events, raw_events, state


def _diagnose(paths: RunPaths) -> tuple[list[str], list[str]]:
    _validate_layout(paths)
    reasons: list[str] = []
    orphan_names: list[str] = []

    metadata = _metadata_root(paths)
    managed_ancestor_blocked = False
    for path in (metadata, metadata / "runs", paths.root):
        if not (path.exists() or path.is_symlink()):
            break
        if _is_link_or_reparse(path):
            reasons.append("LINK_OR_REPARSE_POINT")
            managed_ancestor_blocked = True
            break
        if not path.is_dir():
            reasons.append("INVALID_RUN_ROOT")
            managed_ancestor_blocked = True
            break

    if not managed_ancestor_blocked:
        if paths.evidence.exists() or paths.evidence.is_symlink():
            if _is_link_or_reparse(paths.evidence):
                reasons.append("LINK_OR_REPARSE_POINT")
            elif not paths.evidence.is_dir():
                reasons.append("INVALID_EVIDENCE_ROOT")
            else:
                try:
                    evidence_objects = list(paths.evidence.iterdir())
                except OSError:
                    reasons.append("INVALID_EVIDENCE_ROOT")
                else:
                    for evidence_object in evidence_objects:
                        if _is_link_or_reparse(evidence_object):
                            reasons.append("LINK_OR_REPARSE_POINT")
                        elif (
                            not evidence_object.is_file()
                            or EVIDENCE_NAME.fullmatch(evidence_object.name) is None
                        ):
                            reasons.append("INVALID_EVIDENCE_OBJECT")
        elif paths.root.exists():
            reasons.append("MISSING_EVIDENCE_ROOT")

        if paths.transactions.exists() or paths.transactions.is_symlink():
            if _is_link_or_reparse(paths.transactions):
                reasons.append("LINK_OR_REPARSE_POINT")
            elif not paths.transactions.is_dir():
                reasons.append("INVALID_TRANSACTIONS_ROOT")
            else:
                try:
                    children = sorted(paths.transactions.iterdir(), key=lambda child: child.name)
                except OSError:
                    reasons.append("INVALID_TRANSACTIONS_ROOT")
                else:
                    orphan_names = [child.name for child in children]
                    if children:
                        reasons.append("ORPHAN_TRANSACTION")
                    if any(_is_link_or_reparse(child) for child in children):
                        reasons.append("LINK_OR_REPARSE_POINT")

        for managed_file in (paths.state, paths.events, paths.lock):
            if (managed_file.exists() or managed_file.is_symlink()) and _is_link_or_reparse(
                managed_file
            ):
                reasons.append("LINK_OR_REPARSE_POINT")

        if _is_link_or_reparse(paths.state) or not paths.state.is_file():
            reasons.append("MISSING_STATE")
        if _is_link_or_reparse(paths.events) or not paths.events.is_file():
            reasons.append("MISSING_EVENTS")

    structural = {
        "LINK_OR_REPARSE_POINT",
        "INVALID_RUN_ROOT",
        "INVALID_EVIDENCE_ROOT",
        "INVALID_EVIDENCE_OBJECT",
        "MISSING_EVIDENCE_ROOT",
        "INVALID_TRANSACTIONS_ROOT",
        "MISSING_STATE",
        "MISSING_EVENTS",
    }
    if not structural.intersection(reasons):
        try:
            _load_persisted(paths)
        except _RecoveryIssue as error:
            reasons.append(error.reason)

    order = (
        "LINK_OR_REPARSE_POINT",
        "INVALID_RUN_ROOT",
        "INVALID_EVIDENCE_ROOT",
        "INVALID_EVIDENCE_OBJECT",
        "MISSING_EVIDENCE_ROOT",
        "INVALID_TRANSACTIONS_ROOT",
        "MISSING_STATE",
        "MISSING_EVENTS",
        "ORPHAN_TRANSACTION",
        "MALFORMED_LOG",
        "INVALID_STATE",
        "LOG_WITNESS_MISMATCH",
    )
    unique = set(reasons)
    return [reason for reason in order if reason in unique], orphan_names


def recovery_status(paths: RunPaths) -> dict[str, object]:
    """Return a read-only recovery classification and never repair artifacts."""
    reasons, orphans = _diagnose(paths)
    return {
        "recovery_required": bool(reasons),
        "reasons": reasons,
        "orphan_transactions": orphans,
        "next_commands": [],
    }


def _require_healthy_run(paths: RunPaths) -> tuple[list[dict[str, object]], bytes, dict[str, object]]:
    reasons, _ = _diagnose(paths)
    if reasons:
        raise StoreError("RECOVERY_REQUIRED", "Run requires read-only recovery diagnosis.")
    try:
        return _load_persisted(paths)
    except _RecoveryIssue as error:
        raise StoreError("RECOVERY_REQUIRED", "Run integrity validation failed.") from error


def load_events(paths: RunPaths) -> list[dict[str, object]]:
    """Load and validate the complete event chain and persisted state witness."""
    events, _, _ = _require_healthy_run(paths)
    return events


def _create_owned_file(path: Path, content: bytes) -> os.stat_result:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        _write_all(descriptor, content)
        os.fsync(descriptor)
        return os.fstat(descriptor)
    finally:
        os.close(descriptor)


def _unlink_if_owned(path: Path, owned: os.stat_result) -> None:
    try:
        if os.path.samestat(owned, path.lstat()):
            path.unlink()
    except OSError:
        pass


def _evidence_digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _verify_evidence_destination(destination: Path, content: bytes) -> None:
    if _is_link_or_reparse(destination) or not destination.is_file():
        raise StoreError("RECOVERY_REQUIRED", "Evidence object is not a plain file.")
    try:
        persisted = destination.read_bytes()
    except OSError as error:
        raise StoreError("RECOVERY_REQUIRED", "Could not read an evidence object.") from error
    if persisted != content or _evidence_digest(persisted)[7:] != destination.name:
        raise StoreError("RECOVERY_REQUIRED", "Evidence object does not match its content address.")


def _ensure_evidence_root(paths: RunPaths) -> None:
    _validate_layout(paths)
    metadata = _metadata_root(paths)
    if metadata.exists() and (_is_link_or_reparse(metadata) or not metadata.is_dir()):
        raise StoreError("RECOVERY_REQUIRED", "HOTL metadata root is not a plain directory.")
    _ensure_directory(metadata)
    if paths.evidence.exists() and (
        _is_link_or_reparse(paths.evidence) or not paths.evidence.is_dir()
    ):
        raise StoreError("RECOVERY_REQUIRED", "Evidence root is not a plain directory.")
    _ensure_directory(paths.evidence)


def store_evidence(paths: RunPaths, content: bytes) -> str:
    """Store immutable bytes once at their SHA-256 content address."""
    if not isinstance(content, bytes):
        raise StoreError("INVALID_EVIDENCE", "Evidence content must be bytes.")
    _validate_layout(paths)
    if paths.root.exists():
        reasons, _ = _diagnose(paths)
        if reasons:
            raise StoreError("RECOVERY_REQUIRED", "Run requires read-only recovery diagnosis.")
    _ensure_evidence_root(paths)
    digest = _evidence_digest(content)
    destination = paths.evidence / digest[7:]
    if destination.exists() or destination.is_symlink():
        _verify_evidence_destination(destination, content)
        return digest

    temporary = paths.evidence / f".{digest[7:]}.{os.getpid()}.{time.time_ns()}"
    owned: os.stat_result | None = None
    try:
        owned = _create_owned_file(temporary, content)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            _verify_evidence_destination(destination, content)
        _fsync_directory(paths.evidence)
        _verify_evidence_destination(destination, content)
    except StoreError:
        raise
    except OSError as error:
        raise StoreError("WRITE_FAILED", "Could not publish evidence atomically.") from error
    finally:
        if owned is not None:
            _unlink_if_owned(temporary, owned)
    return digest


def _create_transaction(paths: RunPaths, operation: str) -> tuple[Path, os.stat_result]:
    transaction = paths.transactions / f"{operation}-{os.getpid()}-{time.time_ns()}"
    try:
        transaction.mkdir()
        owned = transaction.lstat()
    except OSError as error:
        raise StoreError("WRITE_FAILED", "Could not create transaction directory.") from error
    return transaction, owned


def _stage_transaction(
    transaction: Path,
    event_bytes: bytes,
    state_bytes: bytes,
    artifacts: Mapping[str, bytes],
) -> tuple[Path, Path, list[tuple[Path, os.stat_result]], tuple[Path, os.stat_result] | None]:
    owned_files: list[tuple[Path, os.stat_result]] = []
    evidence_stage: tuple[Path, os.stat_result] | None = None
    events_stage = transaction / "events.jsonl"
    state_stage = transaction / "state.json"
    try:
        owned_files.append((events_stage, _create_owned_file(events_stage, event_bytes)))
        owned_files.append((state_stage, _create_owned_file(state_stage, state_bytes)))
        if artifacts:
            directory = transaction / "evidence"
            directory.mkdir()
            evidence_stage = (directory, directory.lstat())
            for digest, content in artifacts.items():
                staged = directory / digest[7:]
                owned_files.append((staged, _create_owned_file(staged, content)))
            _fsync_directory(directory)
        _fsync_directory(transaction)
    except OSError as error:
        raise StoreError("WRITE_FAILED", "Could not stage transaction files.") from error
    return events_stage, state_stage, owned_files, evidence_stage


def _validated_artifacts(artifacts: Mapping[str, bytes]) -> dict[str, bytes]:
    if not isinstance(artifacts, Mapping):
        raise StoreError("INVALID_EVIDENCE", "Artifacts must be a digest-to-bytes mapping.")
    result: dict[str, bytes] = {}
    for digest, content in artifacts.items():
        if (
            not isinstance(digest, str)
            or not digest.startswith("sha256:")
            or EVIDENCE_NAME.fullmatch(digest[7:]) is None
            or not isinstance(content, bytes)
            or _evidence_digest(content) != digest
        ):
            raise StoreError("INVALID_EVIDENCE", "Artifact content must match its canonical digest.")
        result[digest] = content
    return result


def _publish_staged_evidence(paths: RunPaths, staged: Path, digest: str, content: bytes) -> None:
    destination = paths.evidence / digest[7:]
    if destination.exists() or destination.is_symlink():
        _verify_evidence_destination(destination, content)
        return
    try:
        os.link(staged, destination)
    except FileExistsError:
        _verify_evidence_destination(destination, content)
    except OSError as error:
        raise StoreError("WRITE_FAILED", "Could not publish transaction evidence.") from error
    _fsync_directory(paths.evidence)
    _verify_evidence_destination(destination, content)


def _cleanup_transaction(
    transaction: Path,
    transaction_owned: os.stat_result,
    owned_files: Sequence[tuple[Path, os.stat_result]],
    evidence_stage: tuple[Path, os.stat_result] | None,
) -> None:
    for path, owned in reversed(owned_files):
        _unlink_if_owned(path, owned)
    if evidence_stage is not None:
        directory, owned = evidence_stage
        try:
            if os.path.samestat(owned, directory.lstat()):
                directory.rmdir()
        except OSError:
            return
    try:
        if os.path.samestat(transaction_owned, transaction.lstat()):
            transaction.rmdir()
    except OSError:
        pass


def _publish_transaction(
    paths: RunPaths,
    operation: str,
    event_bytes: bytes,
    state: dict[str, object],
    artifacts: Mapping[str, bytes],
) -> None:
    state_bytes = canonical_json_bytes(state)
    transaction, transaction_owned = _create_transaction(paths, operation)
    events_stage, state_stage, owned_files, evidence_stage = _stage_transaction(
        transaction, event_bytes, state_bytes, artifacts
    )

    try:
        staged_event_bytes = events_stage.read_bytes()
        staged_state = _load_canonical_object(state_stage.read_bytes(), "candidate state")
        _validate_candidate(staged_event_bytes, staged_state, paths.root.name)
        if staged_event_bytes != event_bytes or canonical_json_bytes(staged_state) != state_bytes:
            raise StoreError("INVALID_TRANSACTION", "Staged transaction bytes changed before publication.")

        for digest, content in artifacts.items():
            staged = transaction / "evidence" / digest[7:]
            if staged.read_bytes() != content:
                raise StoreError("INVALID_TRANSACTION", "Staged evidence changed before publication.")
            _publish_staged_evidence(paths, staged, digest, content)

        os.replace(events_stage, paths.events)
        _fsync_directory(paths.root)
        os.replace(state_stage, paths.state)
        _fsync_directory(paths.root)
    except StoreError:
        raise
    except ContractError as error:
        raise StoreError("INVALID_TRANSACTION", "Transaction contains invalid canonical JSON.") from error
    except OSError as error:
        raise StoreError("WRITE_FAILED", "Could not publish transaction atomically.") from error
    else:
        _cleanup_transaction(
            transaction, transaction_owned, owned_files, evidence_stage
        )


def publish_initial_events(
    paths: RunPaths,
    state: dict[str, object],
    events: Sequence[dict[str, object]],
    artifacts: Mapping[str, bytes],
) -> None:
    """Atomically publish one complete, non-empty initial event batch."""
    _validate_layout(paths)
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)) or not events:
        raise StoreError("EMPTY_BATCH", "Initial event batch must not be empty.")
    if not all(isinstance(event, dict) for event in events):
        raise StoreError("INVALID_TRANSACTION", "Every initial event must be an object.")
    event_bytes = b"".join(canonical_json_bytes(event) for event in events)
    _validate_candidate(event_bytes, state, paths.root.name)
    validated_artifacts = _validated_artifacts(artifacts)
    if paths.root.exists() or paths.root.is_symlink():
        raise StoreError("RUN_EXISTS", "Execution run already exists.")
    metadata = _metadata_root(paths)
    _ensure_directory(metadata)
    _ensure_directory(metadata / "runs")
    _ensure_directory(paths.evidence)
    try:
        paths.root.mkdir()
    except FileExistsError as error:
        raise StoreError("RUN_EXISTS", "Execution run already exists.") from error
    except OSError as error:
        raise StoreError("WRITE_FAILED", "Could not create execution run.") from error
    _require_plain_directory(paths.root)
    _ensure_directory(paths.transactions)
    _publish_transaction(paths, "initialize", event_bytes, state, validated_artifacts)


def publish_initial_run(
    paths: RunPaths, state: dict[str, object], first_event: dict[str, object]
) -> None:
    """Compatibility wrapper for a one-event initial publication."""
    publish_initial_events(paths, state, [first_event], {})


def append_events(
    paths: RunPaths,
    events: Sequence[dict[str, object]],
    state: dict[str, object],
    artifacts: Mapping[str, bytes],
) -> None:
    """Append one validated atomic event batch and publish its projection last."""
    _validate_layout(paths)
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)) or not events:
        raise StoreError("EMPTY_BATCH", "Event batch must contain at least one event.")
    old_events, old_bytes, _ = _require_healthy_run(paths)
    new_events = list(events)
    if not all(isinstance(event, dict) for event in new_events):
        raise StoreError("INVALID_TRANSACTION", "Every event must be an object.")
    candidate_bytes = old_bytes + b"".join(canonical_json_bytes(event) for event in new_events)
    candidate = _validate_candidate(candidate_bytes, state, paths.root.name)
    if candidate_bytes[: len(old_bytes)] != old_bytes:
        raise StoreError("INVALID_TRANSACTION", "Candidate log does not preserve the old log prefix.")
    if len(candidate) != len(old_events) + len(new_events):
        raise StoreError("INVALID_TRANSACTION", "Candidate event count does not match the batch size.")
    validated_artifacts = _validated_artifacts(artifacts)
    _ensure_evidence_root(paths)
    _publish_transaction(paths, "append", candidate_bytes, state, validated_artifacts)


def append_event(
    paths: RunPaths,
    event: dict[str, object],
    state: dict[str, object],
    artifacts: Mapping[str, bytes],
) -> None:
    """Append exactly one event through the atomic batch primitive."""
    append_events(paths, [event], state, artifacts)
