#!/usr/bin/env python3
"""Deterministic controller for the GPT Pro Codex Loop Skill."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping, Sequence

import capture_snapshot
import validate_packet


SCHEMA_VERSION = 1
TASK_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z")


class ControllerError(RuntimeError):
    """A stable, safe-to-display controller failure."""

    def __init__(
        self, code: str, message: str, details: Sequence[str] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = tuple(details)


@dataclass(frozen=True)
class RunPaths:
    repository: Path
    task_slug: str
    run: Path
    state: Path
    preflight: Path
    events: Path
    transactions: Path
    lock: Path


def _repository_root(repository: Path) -> Path:
    supplied = Path(repository).resolve()
    if not supplied.is_dir():
        raise ControllerError("INVALID_REPOSITORY", "Repository path is not a directory.")
    completed = subprocess.run(
        ["git", "-C", str(supplied), "rev-parse", "--show-toplevel"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise ControllerError("INVALID_REPOSITORY", "Repository path is not a Git repository root.")
    try:
        root = Path(completed.stdout.decode("utf-8", errors="strict").strip()).resolve()
    except UnicodeDecodeError as exc:
        raise ControllerError("INVALID_REPOSITORY", "Git returned an invalid repository path.") from exc
    if root != supplied:
        raise ControllerError("INVALID_REPOSITORY", "Repository path must be the Git repository root.")
    return root


def _is_contained(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_run(repository: Path, task_slug: str) -> RunPaths:
    """Resolve one safe, explicit run location within a repository root."""
    root = _repository_root(repository)
    if not isinstance(task_slug, str) or TASK_SLUG.fullmatch(task_slug) is None:
        raise ControllerError("INVALID_TASK_SLUG", "Invalid task slug.")
    metadata = root / ".ai-pro-loop"
    resolved_metadata = metadata.resolve(strict=False)
    run = metadata / task_slug
    resolved_run = run.resolve(strict=False)
    if not _is_contained(resolved_metadata, root) or not _is_contained(
        resolved_run, resolved_metadata
    ):
        raise ControllerError("UNSAFE_RUN_PATH", "Run path escapes the repository metadata directory.")
    return RunPaths(
        repository=root,
        task_slug=task_slug,
        run=run,
        state=run / "state.json",
        preflight=run / "preflight.json",
        events=run / "events.jsonl",
        transactions=run / "transactions",
        lock=run / ".lock",
    )


def _canonical_json_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ControllerError("INVALID_JSON_VALUE", "Value is not canonical JSON.") from exc
    return (encoded + "\n").encode("utf-8")


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    if not path.parent.is_dir():
        raise ControllerError("WRITE_FAILED", "Destination directory does not exist.")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(value)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except OSError as exc:
        raise ControllerError("WRITE_FAILED", "Could not atomically write controller artifact.") from exc
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def write_json_atomic(path: Path, value: object) -> None:
    """Write one canonical JSON value with atomic replacement."""
    _write_bytes_atomic(path, _canonical_json_bytes(value))


def write_text_atomic(path: Path, value: str) -> None:
    """Write UTF-8 text with atomic replacement and no newline translation."""
    if not isinstance(value, str):
        raise ControllerError("INVALID_TEXT", "Controller text artifact must be a string.")
    _write_bytes_atomic(path, value.encode("utf-8"))


@contextmanager
def run_lock(path: Path) -> Iterator[None]:
    """Hold one exclusive run lock without guessing whether old locks are stale."""
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ControllerError("RUN_LOCKED", "Run is already locked.") from exc
    except OSError as exc:
        raise ControllerError("LOCK_FAILED", "Could not create the run lock.") from exc
    owned_stat = os.fstat(descriptor)
    try:
        payload = _canonical_json_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "created_at_unix": int(time.time()),
            }
        )
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        yield
    finally:
        try:
            os.close(descriptor)
        finally:
            try:
                if os.path.samestat(owned_stat, path.stat()):
                    path.unlink()
            except OSError:
                pass


def load_json(path: Path) -> dict[str, object]:
    """Strictly load one object-shaped controller artifact."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ControllerError("READ_FAILED", "Could not read controller JSON artifact.") from exc
    try:
        value = validate_packet.strict_json_loads(raw)
    except ValueError as exc:
        raise ControllerError("INVALID_JSON", "Controller JSON artifact is invalid.") from exc
    if not isinstance(value, dict):
        raise ControllerError("INVALID_JSON", "Controller JSON artifact must be an object.")
    return value


def _normalize_approved_paths(approved_existing_paths: Sequence[str]) -> list[str]:
    if isinstance(approved_existing_paths, (str, bytes)):
        return []
    try:
        values = list(approved_existing_paths)
    except TypeError:
        return []
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            return []
        normalized.append("/".join(PurePosixPath(value.replace("\\", "/")).parts))
    return sorted(normalized)


def initial_state(
    preflight: Mapping[str, object],
    approved_paths: Sequence[str],
    model_policy: str,
    requested_label: str | None,
) -> dict[str, object]:
    """Build the complete, preflight-only trusted state object."""
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": "PREFLIGHT",
        "review_round": 0,
        "latest_decision": None,
        "latest_requirements_decision": None,
        "required_actions": [],
        "unresolved_finding_ids": [],
        "blocker_fingerprints": [],
        "format_error_count": 0,
        "browser_reconnect_count": 0,
        "conversation_binding_state": "CONVERSATION_UNBOUND",
        "bound_conversation_url": None,
        "model_policy": model_policy,
        "requested_model_label": requested_label,
        "visible_model_label": None,
        "active_requirements_revision": None,
        "active_requirements_digest": None,
        "approval_sequence": 0,
        "pending_requirements_revision": None,
        "pending_requirements_digest": None,
        "pending_supersedes_digest": None,
        "pending_approval_sequence": None,
        "pending_approved_requirements_digest": None,
        "pending_user_approval_evidence": None,
        "behavior_changed": False,
        "user_approval_required": False,
        "scope_changed": False,
        "public_contract_changed": False,
        "prior_evidence_invalidated": False,
        "review_round_reset": False,
        "user_approval_received": False,
        "stop_origin_phase": None,
        "stop_origin_category": None,
        "stop_reason": None,
        "stop_sequence": 0,
        "resolution_evidence": None,
        "resolution_stop_sequence": None,
        "pending_requirements_envelope_digest": None,
        "pending_review_envelope_digest": None,
        "last_consumed_packet_digest": None,
        "last_consumed_review_envelope_digest": None,
        "active_report_digest": None,
        "current_snapshot_digest": None,
        "active_review_packet_digest": None,
        "reviewed_snapshot_digest": None,
        "baseline_head": preflight["baseline_head"],
        "preflight_digest": validate_packet.canonical_digest(preflight),
        "approved_existing_paths": sorted(approved_paths),
    }


def _validate_model_policy(model_policy: str, requested_label: str | None) -> None:
    if model_policy == "PRO_CLASS" and requested_label is None:
        return
    if (
        model_policy == "EXACT_LABEL"
        and isinstance(requested_label, str)
        and bool(requested_label.strip())
    ):
        return
    raise ControllerError(
        "INVALID_MODEL_POLICY",
        "Model policy must be PRO_CLASS with no label or EXACT_LABEL with a label.",
    )


def _read_input(path: Path, name: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ControllerError("INPUT_READ_FAILED", f"Could not read {name} input.") from exc


def _head_commit(repository: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--verify", "HEAD^{commit}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise ControllerError("PREFLIGHT_FAILED", "Repository has no valid baseline commit.")
    try:
        return completed.stdout.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise ControllerError("PREFLIGHT_FAILED", "Git returned an invalid baseline commit.") from exc


def _owned_path(path: Path) -> tuple[Path, os.stat_result]:
    return path, path.stat()


def _unlink_owned(owned_paths: Sequence[tuple[Path, os.stat_result]]) -> None:
    for path, owned_stat in reversed(owned_paths):
        try:
            if os.path.samestat(owned_stat, path.stat()):
                path.unlink()
        except OSError:
            pass


def _cleanup_owned_transaction(
    transaction: Path, staged_paths: Sequence[tuple[Path, os.stat_result]]
) -> None:
    """Remove only artifacts staged by this invocation, leaving foreign leftovers visible."""
    _unlink_owned(staged_paths)
    try:
        transaction.rmdir()
    except OSError:
        pass


def _cleanup_failed_initialization(
    paths: RunPaths, committed_paths: Sequence[tuple[Path, os.stat_result]]
) -> None:
    """Remove this invocation's untrusted artifacts without touching foreign leftovers."""
    _unlink_owned(committed_paths)
    try:
        paths.transactions.rmdir()
    except OSError:
        pass
    try:
        paths.run.rmdir()
    except OSError:
        pass


def initialize_run(
    repository: Path,
    task_slug: str,
    request_path: Path,
    repository_context_path: Path,
    approved_existing_paths: Sequence[str],
    model_policy: str,
    requested_model_label: str | None,
) -> dict[str, object]:
    """Create a fully validated, conversation-unbound controller run."""
    paths = resolve_run(repository, task_slug)
    _validate_model_policy(model_policy, requested_model_label)
    request_text = _read_input(request_path, "request")
    context_text = _read_input(repository_context_path, "repository context")
    metadata = paths.run.parent
    metadata.mkdir(parents=True, exist_ok=True)
    initialization_lock = metadata / f".{paths.task_slug}.initialize.lock"
    with run_lock(initialization_lock):
        if paths.run.exists():
            raise ControllerError("RUN_EXISTS", "Run already exists.")
        try:
            paths.run.mkdir()
        except FileExistsError as exc:
            raise ControllerError("RUN_EXISTS", "Run already exists.") from exc
        lock_acquired = False
        initialized = False
        committed_paths: list[tuple[Path, os.stat_result]] = []
        try:
            paths.transactions.mkdir()
            with run_lock(paths.lock):
                lock_acquired = True
                preflight = capture_snapshot.inspect_preflight(
                    paths.repository, _head_commit(paths.repository)
                )
                preflight_errors = capture_snapshot.validate_preflight(
                    preflight, approved_existing_paths, paths.repository
                )
                if preflight_errors:
                    message = "Preflight has unapproved or invalid product paths."
                    if any(
                        error.startswith("unapproved pre-existing")
                        for error in preflight_errors
                    ):
                        message = "Preflight has unapproved pre-existing product paths."
                    raise ControllerError(
                        "PREFLIGHT_INVALID",
                        message,
                        preflight_errors,
                    )
                approved_paths = _normalize_approved_paths(approved_existing_paths)
                previous = initial_state(
                    preflight, approved_paths, model_policy, requested_model_label
                )
                candidate = dict(previous)
                candidate["phase"] = "REQUIREMENTS_PENDING"
                transition_errors = validate_packet.validate_transition(previous, candidate)
                if transition_errors:
                    raise ControllerError(
                        "INVALID_INITIAL_STATE",
                        "Initial controller state failed transition validation.",
                        transition_errors,
                    )

                transaction = paths.transactions / f"initialize-{os.getpid()}-{time.time_ns()}"
                transaction.mkdir()
                request_stage = transaction / "request.md"
                context_stage = transaction / "repository-context.md"
                preflight_stage = transaction / "preflight.json"
                events_stage = transaction / "events.jsonl"
                state_stage = transaction / "state.json"
                staged_paths: list[tuple[Path, os.stat_result]] = []
                try:
                    write_text_atomic(request_stage, request_text)
                    staged_paths.append(_owned_path(request_stage))
                    write_text_atomic(context_stage, context_text)
                    staged_paths.append(_owned_path(context_stage))
                    write_json_atomic(preflight_stage, preflight)
                    staged_paths.append(_owned_path(preflight_stage))
                    write_text_atomic(
                        events_stage,
                        _canonical_json_bytes(
                            {
                                "schema_version": SCHEMA_VERSION,
                                "event": "RUN_INITIALIZED",
                                "at_unix": int(time.time()),
                            }
                        ).decode("utf-8"),
                    )
                    staged_paths.append(_owned_path(events_stage))
                    write_json_atomic(state_stage, candidate)
                    staged_paths.append(_owned_path(state_stage))
                    try:
                        os.replace(request_stage, paths.run / "request.md")
                        committed_paths.append(_owned_path(paths.run / "request.md"))
                        os.replace(context_stage, paths.run / "repository-context.md")
                        committed_paths.append(
                            _owned_path(paths.run / "repository-context.md")
                        )
                        os.replace(preflight_stage, paths.preflight)
                        committed_paths.append(_owned_path(paths.preflight))
                        os.replace(events_stage, paths.events)
                        committed_paths.append(_owned_path(paths.events))
                        os.replace(state_stage, paths.state)
                        committed_paths.append(_owned_path(paths.state))
                    except OSError as exc:
                        raise ControllerError(
                            "WRITE_FAILED",
                            "Could not commit initialized controller artifacts.",
                        ) from exc
                    initialized = True
                finally:
                    _cleanup_owned_transaction(transaction, staged_paths)
        finally:
            if not initialized and (lock_acquired or not paths.lock.exists()):
                _cleanup_failed_initialization(paths, committed_paths)
    return status_run(paths.repository, task_slug)


def next_commands(
    state: Mapping[str, object],
    outstanding_attempt: Mapping[str, object] | None,
) -> list[str]:
    """Return only commands valid for the current phase and pre-send attempt."""
    if outstanding_attempt is not None:
        expected = outstanding_attempt.get("expected_header")
        packet_type = expected.get("packet_type") if isinstance(expected, Mapping) else None
        if packet_type == "requirements" and state["phase"] == "REQUIREMENTS_PENDING":
            return ["accept-requirements", "abandon-attempt"]
        if packet_type == "review" and state["phase"] == "REVIEW_PENDING":
            return ["accept-review", "abandon-attempt"]
        return []
    if state["phase"] == "USER_DECISION_REQUIRED":
        return (
            ["approve-requirements"]
            if state["stop_origin_category"] == "REQUIREMENTS_NEED_USER_INPUT"
            else []
        )
    return {
        "REQUIREMENTS_PENDING": ["prepare-requirements"],
        "REQUIREMENTS_FROZEN": ["build-report"],
        "IMPLEMENTING": ["build-report"],
        "LOCAL_VERIFICATION": ["build-report", "prepare-review"],
        "REVIEW_PENDING": ["prepare-review"],
        "FINAL_VERIFICATION": ["final-verify"],
        "COMPLETE": [],
        "BLOCKED": [],
        "PREFLIGHT": [],
    }[str(state["phase"])]


def _outstanding_attempts(paths: RunPaths) -> list[dict[str, object]]:
    attempts: list[dict[str, object]] = []
    for path in sorted(paths.run.glob("expected-attempt-*.json")):
        if not path.is_file():
            continue
        try:
            artifact = load_json(path)
        except ControllerError:
            attempts.append({"name": path.name, "expected_header": {}})
            continue
        expected = artifact.get("expected_header", artifact)
        attempts.append(
            {
                "name": path.name,
                "expected_header": expected if isinstance(expected, dict) else {},
            }
        )
    return attempts


def _unreachable_artifacts(
    paths: RunPaths, state: Mapping[str, object]
) -> list[str]:
    allowed_names = {
        "request.md",
        "repository-context.md",
        "preflight.json",
        "state.json",
        "events.jsonl",
        "transactions",
        ".lock",
        "prompts",
        "responses",
    }
    reachable_digests = {
        value
        for value in state.values()
        if isinstance(value, str) and value.startswith("sha256:")
    }
    unreachable: list[str] = []
    for path in paths.run.iterdir():
        if path.name in allowed_names or path.name.startswith("expected-attempt-"):
            continue
        if path.is_file() and path.suffix == ".json":
            try:
                artifact = load_json(path)
            except ControllerError:
                unreachable.append(path.name)
                continue
            if validate_packet.canonical_digest(artifact) in reachable_digests:
                continue
        unreachable.append(path.name)
    return sorted(unreachable)


def status_run(repository: Path, task_slug: str) -> dict[str, object]:
    """Report controller progress without modifying run artifacts or locks."""
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    state = load_json(paths.state)
    attempts = _outstanding_attempts(paths)
    outstanding = attempts[0] if len(attempts) == 1 else None
    orphan_transactions = (
        sorted(path.name for path in paths.transactions.iterdir() if path.is_dir())
        if paths.transactions.is_dir()
        else []
    )
    return {
        "phase": state.get("phase"),
        "active_requirements_revision": state.get("active_requirements_revision"),
        "review_round": state.get("review_round"),
        "conversation": {
            "binding_state": state.get("conversation_binding_state"),
            "url": state.get("bound_conversation_url"),
        },
        "model": {
            "policy": state.get("model_policy"),
            "requested_label": state.get("requested_model_label"),
            "visible_label": state.get("visible_model_label"),
        },
        "required_actions": state.get("required_actions"),
        "stop_origin_category": state.get("stop_origin_category"),
        "outstanding_attempts": [attempt["name"] for attempt in attempts],
        "lock_present": paths.lock.exists(),
        "orphan_transactions": orphan_transactions,
        "unreachable_artifacts": _unreachable_artifacts(paths, state),
        "next_commands": next_commands(state, outstanding),
    }
