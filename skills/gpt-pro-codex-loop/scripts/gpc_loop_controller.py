#!/usr/bin/env python3
"""Deterministic controller for the GPT Pro Codex Loop Skill."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlparse
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping, Sequence

import capture_snapshot
import validate_packet


SCHEMA_VERSION = 1
GOVERNANCE_RECEIPT_SCHEMA_VERSION = 1
GOVERNANCE_RECEIPT_HISTORY_DIRECTORY = "governance-receipt-history"
GOVERNANCE_RECEIPT_TYPES = {
    "requirements": "requirements",
    "review": "semantic_review",
    "final": "final",
}
GOVERNANCE_BINDING_FIELDS = {
    "task_slug",
    "run_id",
    "conversation_url",
    "model_label",
    "reasoning_label",
    "plan_label",
}
GOVERNANCE_RECEIPT_FIELDS = {
    "authority_snapshot_digest",
    "binding",
    "claims",
    "cycle_id",
    "evidence_set_digest",
    "execution_id",
    "input_digest",
    "issued_at_unix",
    "issuer_skill",
    "issuer_version",
    "nonce",
    "output_digest",
    "receipt_id",
    "receipt_schema_version",
    "receipt_type",
    "requirements_digest",
    "snapshot_digest",
    "transaction_id",
}
HOTL_GOVERNANCE_CONTEXT_FIELDS = {
    "artifact_digest",
    "artifact_type",
    "authority_snapshot_digest",
    "cycle_id",
    "execution_id",
    "policy_digest",
    "receipt_nonce",
    "requirements_digest",
    "schema_version",
    "snapshot_digest",
}
TASK_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z")
TEMPLATE_TOKEN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
ATTEMPT_NAME = re.compile(r"(?:expected|abandoned|consumed)-attempt-(\d+)\.json\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
MAX_ABANDON_EVIDENCE_BYTES = 8192
MAX_MODEL_BOUND_ITEMS = 64
MODEL_BOUND_REPORT_ITEM_LIMITS = {
    "changed_file_intents": 64,
    "acceptance_evidence": 64,
    "test_commands": 32,
    "diff_evidence": 64,
    "omissions": 32,
    "unresolved_risks_or_blockers": 32,
}
MAX_MODEL_BOUND_ITEM_BYTES = 8192
MAX_MODEL_BOUND_SECTION_BYTES = 65536
MAX_PREPARED_PROMPT_BYTES = 131072
MAX_PATH_PREVIEW = 20
INITIALIZATION_MARKER_NAME = "initialization.json"
APPROVAL_MANIFEST_FIELDS = {
    "schema_version",
    "repository",
    "task",
    "baseline_head",
    "initial_product_paths",
    "path_count",
    "path_set_digest",
}
INITIALIZATION_MARKER_FIELDS = {
    "schema_version",
    "kind",
    "repository",
    "task",
    "baseline_head",
    "pid",
    "hostname",
    "created_at_unix",
}
LOCK_FIELDS = {"schema_version", "pid", "hostname", "created_at_unix"}
EXPECTED_HEADER_FIELDS = {
    "schema_version",
    "packet_type",
    "run_id",
    "turn_id",
    "nonce",
    "in_reply_to",
    "prompt_digest",
    "previous_packet_digest",
}
ABANDONED_ATTEMPT_FIELDS = {
    "schema_version",
    "status",
    "expected_header",
    "expected_header_digest",
    "nonce",
    "prompt_digest",
    "evidence",
    "abandoned_at_unix",
}

TEMPLATE_TOKENS = {
    "Shared envelope instruction": {
        "PACKET_TYPE",
        "RUN_ID",
        "TURN_ID",
        "NONCE",
        "IN_REPLY_TO_DIGEST",
        "PROMPT_DIGEST",
        "PREVIOUS_PACKET_DIGEST_OR_NULL",
    },
    "Initial requirements": {
        "USER_REQUEST",
        "REPOSITORY_EVIDENCE",
        "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REQUIREMENTS",
    },
    "Requirements revision": {
        "PREVIOUS_REQUIREMENTS_JSON",
        "PREVIOUS_REQUIREMENTS_DIGEST",
        "CONFLICT_EVIDENCE",
        "APPROVAL_RECEIPT_OR_NULL",
        "NEXT_REVISION",
        "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REQUIREMENTS",
    },
    "Implementation review": {
        "REQUIREMENTS_JSON",
        "REQUIREMENTS_DIGEST",
        "IMPLEMENTATION_REPORT_JSON",
        "SNAPSHOT_DIGEST",
        "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REVIEW",
    },
    "Evidence-only supplementation": {
        "SNAPSHOT_DIGEST",
        "REQUIREMENTS_JSON",
        "PRIOR_REVIEW_JSON",
        "SUPPLEMENTAL_EVIDENCE",
        "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REVIEW",
    },
}


class ControllerError(RuntimeError):
    """A stable, safe-to-display controller failure."""

    def __init__(
        self, code: str, message: str, details: Sequence[str] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = tuple(details)


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def validate_model_bound_items(section: str, items: Sequence[str]) -> None:
    if len(items) > MAX_MODEL_BOUND_ITEMS:
        raise ControllerError(
            "MODEL_BOUND_ITEM_COUNT_EXCEEDED",
            f"Model-bound section {section} exceeds {MAX_MODEL_BOUND_ITEMS} items.",
        )
    for index, item in enumerate(items):
        if _utf8_size(item) > MAX_MODEL_BOUND_ITEM_BYTES:
            raise ControllerError(
                "MODEL_BOUND_ITEM_BYTES_EXCEEDED",
                f"Model-bound item {section}.{index} exceeds {MAX_MODEL_BOUND_ITEM_BYTES} UTF-8 bytes.",
            )


def validate_model_bound_report(evidence: Mapping[str, object]) -> None:
    """Apply independent field caps, then the byte cap for the complete section."""
    changed_intents = evidence.get("changed_file_intents", {})
    acceptance = evidence.get("acceptance_evidence", {})
    fields: dict[str, Sequence[str]] = {
        "changed_file_intents": [str(value) for value in changed_intents.values()],  # type: ignore[union-attr]
        "acceptance_evidence": [
            str(item)
            for entries in acceptance.values()  # type: ignore[union-attr]
            for item in entries
        ],
        "test_commands": [
            _canonical_prompt_json(item) for item in evidence.get("test_commands", [])  # type: ignore[arg-type]
        ],
        "diff_evidence": [str(item) for item in evidence.get("diff_evidence", [])],  # type: ignore[arg-type]
        "omissions": [str(item) for item in evidence.get("omissions", [])],  # type: ignore[arg-type]
        "unresolved_risks_or_blockers": [
            str(item) for item in evidence.get("unresolved_risks_or_blockers", [])  # type: ignore[arg-type]
        ],
    }
    for field, items in fields.items():
        limit = MODEL_BOUND_REPORT_ITEM_LIMITS[field]
        if len(items) > limit:
            raise ControllerError(
                "MODEL_BOUND_ITEM_COUNT_EXCEEDED",
                f"Model-bound section implementation_report.{field} exceeds {limit} items.",
            )
        validate_model_bound_items(f"implementation_report.{field}", items)
    validate_model_bound_items("implementation_report.intent_summary", [str(evidence["intent_summary"])])
    validate_model_bound_section("implementation_report", _canonical_prompt_json(evidence))


def validate_model_bound_section(section: str, value: str) -> None:
    if _utf8_size(value) > MAX_MODEL_BOUND_SECTION_BYTES:
        raise ControllerError(
            "MODEL_BOUND_SECTION_BYTES_EXCEEDED",
            f"Model-bound section {section} exceeds {MAX_MODEL_BOUND_SECTION_BYTES} UTF-8 bytes.",
        )


def validate_prepared_prompt(prompt: str) -> None:
    if _utf8_size(prompt) > MAX_PREPARED_PROMPT_BYTES:
        raise ControllerError(
            "PREPARED_PROMPT_BYTES_EXCEEDED",
            f"Prepared prompt exceeds {MAX_PREPARED_PROMPT_BYTES} UTF-8 bytes.",
        )


def _bounded_model_text(path: Path, value: str) -> str:
    """Keep the local artifact complete while sending only bounded metadata."""
    if _utf8_size(value) <= MAX_MODEL_BOUND_ITEM_BYTES:
        return value
    return _canonical_prompt_json(
        {
            "artifact": str(path),
            "digest": sha256_bytes(value.encode("utf-8")),
            "status": "oversize_local_artifact_preserved",
            "utf8_bytes": _utf8_size(value),
        }
    )


@dataclass(frozen=True)
class Token:
    name: str


@dataclass(frozen=True)
class Template:
    parts: tuple[str | Token, ...]


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


def _normalize_text(value: str) -> str:
    if not isinstance(value, str):
        raise ControllerError("INVALID_TEXT", "Prompt text must be a string.")
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_prompt(value: str) -> str:
    return _normalize_text(value).rstrip("\n") + "\n"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def governance_execution_id(task_slug: str) -> str:
    """Map one validated GPT Pro run identity to the closed HOTL execution shape."""
    if not isinstance(task_slug, str) or TASK_SLUG.fullmatch(task_slug) is None:
        raise ControllerError("INVALID_TASK_SLUG", "Invalid task slug.")
    identity = _canonical_json_bytes(
        {
            "issuer_skill": "gpt-pro-codex-loop",
            "run_id": f"gpc-loop-{task_slug}",
            "task_slug": task_slug,
        }
    )
    return "EXEC-" + hashlib.sha256(identity).hexdigest()[:12].upper()


def governance_receipt_nonce(binding: Mapping[str, object]) -> str:
    """Derive the stable outer receipt nonce without exposing the attempt nonce key."""
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "binding": dict(binding),
                "purpose": "gpt-pro-governance-receipt-nonce-v1",
            }
        )
    ).hexdigest()[:32]


def _governance_provenance_complete(state: Mapping[str, object]) -> bool:
    return state.get("conversation_binding_state") == "CONVERSATION_BOUND" and all(
        isinstance(state.get(field), str) and bool(str(state[field]).strip())
        for field in (
            "bound_conversation_url",
            "visible_model_label",
            "visible_reasoning_label",
            "visible_plan_label",
        )
    )


def _governance_binding(
    paths: RunPaths, state: Mapping[str, object]
) -> dict[str, object]:
    binding = {
        "task_slug": paths.task_slug,
        "run_id": f"gpc-loop-{paths.task_slug}",
        "conversation_url": state.get("bound_conversation_url"),
        "model_label": state.get("visible_model_label"),
        "reasoning_label": state.get("visible_reasoning_label"),
        "plan_label": state.get("visible_plan_label"),
    }
    if not _governance_provenance_complete(state):
        raise ControllerError(
            "PROVENANCE_INCOMPLETE",
            "Governance receipt requires complete Browser and model provenance.",
        )
    return binding


def _governance_authority_digest(binding: Mapping[str, object]) -> str:
    return sha256_bytes(_canonical_json_bytes(dict(binding)))


def _governance_receipt(
    paths: RunPaths,
    state: Mapping[str, object],
    receipt_type: str,
    *,
    input_digest: str,
    output_digest: str,
    requirements_digest: str,
    transaction_id: str,
    snapshot_digest: object,
    claims: Mapping[str, object],
    issued_at_unix: int,
) -> dict[str, object]:
    binding = _governance_binding(paths, state)
    authority_digest = _governance_authority_digest(binding)
    nonce = governance_receipt_nonce(binding)
    receipt_claims = dict(claims)
    hotl_context = state.get("hotl_governance_context")
    hotl_context_digest = state.get("hotl_governance_context_digest")
    if hotl_context is not None:
        if (
            not isinstance(hotl_context, dict)
            or not isinstance(hotl_context_digest, str)
            or sha256_bytes(_canonical_json_bytes(hotl_context)) != hotl_context_digest
            or hotl_context.get("execution_id") != governance_execution_id(paths.task_slug)
            or hotl_context.get("authority_snapshot_digest") != authority_digest
            or hotl_context.get("receipt_nonce") != nonce
            or hotl_context.get("requirements_digest") != requirements_digest
        ):
            raise ControllerError(
                "HOTL_CONTEXT_MISMATCH",
                "HOTL governance context does not bind the authoritative receipt.",
            )
        receipt_claims.update(
            hotl_governance_context=dict(hotl_context),
            hotl_governance_context_digest=hotl_context_digest,
        )
    receipt_id_seed = _canonical_json_bytes(
        {
            "authority_snapshot_digest": authority_digest,
            "binding": binding,
            "claims": receipt_claims,
            "execution_id": governance_execution_id(paths.task_slug),
            "input_digest": input_digest,
            "issued_at_unix": issued_at_unix,
            "nonce": nonce,
            "output_digest": output_digest,
            "receipt_type": receipt_type,
            "requirements_digest": requirements_digest,
            "snapshot_digest": snapshot_digest,
            "transaction_id": transaction_id,
        }
    )
    return {
        "authority_snapshot_digest": authority_digest,
        "binding": binding,
        "claims": receipt_claims,
        "cycle_id": None,
        "evidence_set_digest": None,
        "execution_id": governance_execution_id(paths.task_slug),
        "input_digest": input_digest,
        "issued_at_unix": issued_at_unix,
        "issuer_skill": "gpt-pro-codex-loop",
        "issuer_version": "1",
        "nonce": nonce,
        "output_digest": output_digest,
        "receipt_id": "RCP-GPC-" + hashlib.sha256(receipt_id_seed).hexdigest()[:20].upper(),
        "receipt_schema_version": GOVERNANCE_RECEIPT_SCHEMA_VERSION,
        "receipt_type": receipt_type,
        "requirements_digest": requirements_digest,
        "snapshot_digest": snapshot_digest,
        "transaction_id": transaction_id,
    }


def _parse_template(
    raw: str, required_tokens: set[str], allow_repeated: bool
) -> Template:
    normalized = _normalize_prompt(raw)
    for placeholder in re.finditer(r"\{\{[^{}\n]*\}\}", normalized):
        if TEMPLATE_TOKEN.fullmatch(placeholder.group(0)) is None:
            raise ControllerError("UNKNOWN_TEMPLATE_TOKEN", "Template contains an unknown token.")
    without_tokens = TEMPLATE_TOKEN.sub("", normalized)
    if "{{" in without_tokens or "}}" in without_tokens:
        raise ControllerError("MALFORMED_TEMPLATE_TOKEN", "Template contains malformed token braces.")
    parts: list[str | Token] = []
    present: set[str] = set()
    position = 0
    for match in TEMPLATE_TOKEN.finditer(normalized):
        name = match.group(1)
        if name not in required_tokens:
            raise ControllerError("UNKNOWN_TEMPLATE_TOKEN", "Template contains an unknown token.")
        if name in present and not allow_repeated:
            raise ControllerError("DUPLICATE_TEMPLATE_TOKEN", "Template contains a duplicate token.")
        if match.start() > position:
            parts.append(normalized[position : match.start()])
        parts.append(Token(name))
        present.add(name)
        position = match.end()
    if position < len(normalized):
        parts.append(normalized[position:])
    missing = required_tokens - present
    if missing:
        raise ControllerError("MISSING_TEMPLATE_TOKEN", "Template is missing a required token.")
    return Template(tuple(parts))


def parse_template(raw: str, required_tokens: set[str]) -> Template:
    """Parse one closed template without treating future values as syntax."""
    return _parse_template(raw, required_tokens, allow_repeated=False)


def load_template(contract: Path, heading: str) -> Template:
    """Load the first text fence immediately following one exact heading."""
    required_tokens = TEMPLATE_TOKENS.get(heading)
    if required_tokens is None:
        raise ControllerError("UNKNOWN_TEMPLATE", "Prompt template heading is not supported.")
    try:
        source = _normalize_text(Path(contract).read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ControllerError("TEMPLATE_READ_FAILED", "Could not read prompt contract.") from exc
    heading_match = re.search(rf"(?m)^## {re.escape(heading)}[ \t]*$", source)
    if heading_match is None:
        raise ControllerError("TEMPLATE_NOT_FOUND", "Prompt template fence was not found.")
    next_heading = re.search(r"(?m)^## ", source[heading_match.end() :])
    section_end = (
        heading_match.end() + next_heading.start()
        if next_heading is not None
        else len(source)
    )
    match = re.search(
        r"(?m)^```text[ \t]*\n(.*?)\n```",
        source[heading_match.end() : section_end],
        re.DOTALL,
    )
    if match is None:
        raise ControllerError("TEMPLATE_NOT_FOUND", "Prompt template fence was not found.")
    # Contract templates deliberately repeat a few bound digests in prose and
    # schema reminders. Values are still parsed only once, before rendering.
    return _parse_template(match.group(1), required_tokens, allow_repeated=True)


def _render_nodes(
    parts: Sequence[str | Token],
    values: Mapping[str, str | Template],
    prompt_digest: str,
) -> str:
    rendered: list[str] = []
    for part in parts:
        if isinstance(part, str):
            rendered.append(part)
            continue
        if part.name == "PROMPT_DIGEST":
            rendered.append(prompt_digest)
            continue
        value = values.get(part.name)
        if value is None:
            raise ControllerError("MISSING_TEMPLATE_VALUE", "Prompt value is missing for a template token.")
        if isinstance(value, Template):
            rendered.append(_render_nodes(value.parts, values, prompt_digest))
        elif isinstance(value, str):
            rendered.append(_normalize_text(value))
        else:
            raise ControllerError("INVALID_TEMPLATE_VALUE", "Prompt template value must be text or a template.")
    return "".join(rendered)


def render_prompt(
    template: Template, values: Mapping[str, str | Template]
) -> dict[str, str]:
    """Render and digest an exact UTF-8 prompt without reparsing values."""
    digest_source = _normalize_prompt(
        _render_nodes(template.parts, values, "{{PROMPT_DIGEST}}")
    )
    prompt_digest = sha256_bytes(digest_source.encode("utf-8"))
    prompt = _normalize_prompt(_render_nodes(template.parts, values, prompt_digest))
    validate_prepared_prompt(prompt)
    return {"prompt": prompt, "prompt_digest": prompt_digest}


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


def _parse_json_object_bytes(
    raw: bytes, *, code: str, message: str
) -> dict[str, object]:
    """Parse one already-read canonical artifact without touching the filesystem."""
    try:
        text = raw.decode("utf-8", errors="strict")
        value = validate_packet.strict_json_loads(text)
    except (UnicodeError, ValueError) as exc:
        raise ControllerError(code, message) from exc
    if not isinstance(value, dict):
        raise ControllerError(code, message)
    return value


def _load_mutator_state(paths: RunPaths) -> tuple[dict[str, object], str]:
    """Load canonical trusted state and bind this command to those exact bytes."""
    state = load_json(paths.state)
    digest = sha256_bytes(_canonical_json_bytes(state))
    _require_state_digest(paths, digest)
    normalized, _ = _normalize_model_attestation_state(state)
    return normalized, digest


def _normalize_model_attestation_state(
    state: dict[str, object],
) -> tuple[dict[str, object], bool]:
    """Upgrade only an unbound legacy state; never infer a bound model identity."""
    version_field = "model_attestation_schema_version"
    observation_fields = ("visible_reasoning_label", "visible_plan_label")
    current_version = validate_packet.MODEL_ATTESTATION_SCHEMA_VERSION
    has_version = version_field in state
    version = state.get(version_field)
    identity_fields = (
        "bound_conversation_url",
        "visible_model_label",
        *observation_fields,
    )
    attestation_fields = (
        "conversation_binding_state",
        "model_policy",
        "requested_model_label",
        *identity_fields,
    )
    restart_message = (
        "Legacy or partial bound model attestation cannot be inferred safely; "
        "preserve this run and restart with a new task slug."
    )

    def restart_required() -> None:
        raise ControllerError("LEGACY_STATE_RESTART_REQUIRED", restart_message)

    def nonempty_string(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def valid_policy_shape() -> bool:
        binding_state = state.get("conversation_binding_state")
        policy = state.get("model_policy")
        requested = state.get("requested_model_label")
        if not isinstance(binding_state, str) or binding_state not in {
            "CONVERSATION_UNBOUND",
            "CONVERSATION_BOUND",
        }:
            return False
        if not isinstance(policy, str) or policy not in {"PRO_CLASS", "EXACT_LABEL"}:
            return False
        if policy == "PRO_CLASS" and requested is not None:
            return False
        if policy == "EXACT_LABEL" and not nonempty_string(requested):
            return False

        if binding_state == "CONVERSATION_UNBOUND":
            return all(state.get(field) is None for field in identity_fields)

        if not nonempty_string(state.get("bound_conversation_url")):
            return False
        if policy == "PRO_CLASS":
            return (
                state.get("visible_model_label")
                == validate_packet.PRO_CLASS_MODEL_LABEL
                and state.get("visible_reasoning_label")
                == validate_packet.PRO_CLASS_REASONING_LABEL
                and isinstance(state.get("visible_plan_label"), str)
                and state.get("visible_plan_label") in validate_packet.PRO_CLASS_PLAN_LABELS
            )
        if state.get("visible_model_label") != requested:
            return False
        return all(
            value is None or nonempty_string(value)
            for value in (
                state.get("visible_reasoning_label"),
                state.get("visible_plan_label"),
            )
        )

    has_identity_fields = all(field in state for field in identity_fields)
    has_attestation_fields = all(field in state for field in attestation_fields)
    unbound = (
        has_identity_fields
        and state.get("conversation_binding_state") == "CONVERSATION_UNBOUND"
        and all(state.get(field) is None for field in identity_fields)
    )

    # A current state is trusted only when the schema version and every
    # attestation/policy field use their exact closed shapes.  In particular,
    # bool and float values must not pass Python's loose ``== int`` semantics.
    if type(version) is int and version == current_version:
        if not has_attestation_fields or not valid_policy_shape():
            restart_required()
        return state, False

    # A v2 state may be upgraded only when every identity field is explicitly
    # null and the conversation is still unbound.  A bound or partial v2 state
    # cannot be re-attested without guessing what the old Browser observed.
    coherent_v2_unbound = (
        has_version
        and type(version) is int
        and version == 2
        and has_attestation_fields
        and unbound
        and valid_policy_shape()
    )
    legacy_core_fields = (
        "conversation_binding_state",
        "bound_conversation_url",
        "model_policy",
        "requested_model_label",
        "visible_model_label",
    )
    legacy_unbound_identity = (
        state.get("conversation_binding_state") == "CONVERSATION_UNBOUND"
        and state.get("bound_conversation_url") is None
        and state.get("visible_model_label") is None
    )
    legacy_unbound = (
        not has_version
        and all(field in state for field in legacy_core_fields)
        and legacy_unbound_identity
        and not any(field in state for field in observation_fields)
        and valid_policy_shape()
    )
    if coherent_v2_unbound or legacy_unbound:
        normalized = dict(state)
        normalized[version_field] = current_version
        normalized["visible_model_label"] = None
        for field in observation_fields:
            normalized[field] = None
        return normalized, True

    restart_required()


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
    review_policy: str = validate_packet.DEFAULT_REVIEW_POLICY,
    hotl_governance_context: Mapping[str, object] | None = None,
    hotl_governance_context_digest: str | None = None,
) -> dict[str, object]:
    """Build the complete, preflight-only trusted state object."""
    state = {
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
        "review_policy": review_policy,
        "requested_model_label": requested_label,
        "visible_model_label": None,
        "visible_reasoning_label": None,
        "visible_plan_label": None,
        "model_attestation_schema_version": validate_packet.MODEL_ATTESTATION_SCHEMA_VERSION,
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
        "pending_requirements_expected_header_digest": None,
        "pending_review_envelope_digest": None,
        "pending_review_expected_header_digest": None,
        "last_consumed_packet_digest": None,
        "last_consumed_review_envelope_digest": None,
        "active_report_digest": None,
        "current_snapshot_digest": None,
        "active_review_packet_digest": None,
        "reviewed_snapshot_digest": None,
        "baseline_head": preflight["baseline_head"],
        "preflight_digest": validate_packet.canonical_digest(preflight),
        "nonce_derivation_key": secrets.token_hex(32),
        "approved_existing_paths": sorted(approved_paths),
    }
    if hotl_governance_context is not None:
        state["hotl_governance_context"] = dict(hotl_governance_context)
        state["hotl_governance_context_digest"] = hotl_governance_context_digest
    return state


def _load_hotl_governance_context(
    path: Path, task_slug: str
) -> tuple[dict[str, object], str]:
    """Read one explicit, canonical, self-digesting HOTL context artifact."""
    try:
        raw = Path(path).read_bytes()
        value = validate_packet.strict_json_loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ControllerError("INVALID_HOTL_CONTEXT", "HOTL governance context is unreadable.") from exc
    if not isinstance(value, dict) or _canonical_json_bytes(value) != raw:
        raise ControllerError("INVALID_HOTL_CONTEXT", "HOTL governance context must be canonical JSON.")
    if set(value) != HOTL_GOVERNANCE_CONTEXT_FIELDS:
        raise ControllerError("INVALID_HOTL_CONTEXT", "HOTL governance context fields are invalid.")
    body = {key: value[key] for key in value if key != "artifact_digest"}
    if value["artifact_type"] != "hotl-governance-context" or value["schema_version"] != 1:
        raise ControllerError("INVALID_HOTL_CONTEXT", "HOTL governance context schema is invalid.")
    if value["execution_id"] != governance_execution_id(task_slug):
        raise ControllerError("HOTL_CONTEXT_MISMATCH", "HOTL governance context execution does not match the task.")
    if value["artifact_digest"] != sha256_bytes(_canonical_json_bytes(body)):
        raise ControllerError("HOTL_CONTEXT_DIGEST_MISMATCH", "HOTL governance context artifact digest is invalid.")
    if any(
        not isinstance(value[field], str) or DIGEST.fullmatch(value[field]) is None
        for field in ("authority_snapshot_digest", "policy_digest", "requirements_digest", "snapshot_digest")
    ) or not isinstance(value["receipt_nonce"], str) or NONCE.fullmatch(value["receipt_nonce"]) is None:
        raise ControllerError("INVALID_HOTL_CONTEXT", "HOTL governance context bindings are invalid.")
    if not isinstance(value["cycle_id"], int) or isinstance(value["cycle_id"], bool) or value["cycle_id"] < 1:
        raise ControllerError("INVALID_HOTL_CONTEXT", "HOTL governance context cycle is invalid.")
    return dict(value), sha256_bytes(raw)


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


def _validate_review_policy(review_policy: str) -> None:
    if review_policy in validate_packet.REVIEW_POLICIES:
        return
    raise ControllerError(
        "INVALID_REVIEW_POLICY",
        "Review policy must be FINAL_ONLY or ITERATIVE.",
    )


def _review_round_limit(state: Mapping[str, object]) -> int:
    return validate_packet.review_round_limit(state)


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


def _path_set_digest(paths: Sequence[str]) -> str:
    return validate_packet.canonical_digest(
        {"schema_version": SCHEMA_VERSION, "paths": list(paths)}
    )


def _approval_manifest(
    paths: RunPaths, preflight: Mapping[str, object]
) -> dict[str, object]:
    initial = list(preflight["initial_product_paths"])
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": str(paths.repository),
        "task": paths.task_slug,
        "baseline_head": preflight["baseline_head"],
        "initial_product_paths": initial,
        "path_count": len(initial),
        "path_set_digest": _path_set_digest(initial),
    }


def _command_json(arguments: Sequence[str]) -> str:
    return json.dumps(
        list(arguments), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _suggested_approval_manifest_path(paths: RunPaths) -> Path:
    return (
        paths.repository.parent
        / f"{paths.repository.name}-{paths.task_slug}-approved-existing-paths.json"
    ).resolve()


def _init_argv(
    paths: RunPaths,
    request_path: Path,
    repository_context_path: Path,
    model_policy: str,
    requested_model_label: str | None,
    approved_existing_paths: Sequence[str] = (),
    approved_existing_path_manifest: Path | None = None,
    retry_incomplete: bool = False,
    review_policy: str = validate_packet.DEFAULT_REVIEW_POLICY,
) -> list[str]:
    arguments = [
        "python",
        "skills/gpt-pro-codex-loop/scripts/gpc_loop.py",
        "init",
        "--repo",
        str(paths.repository),
        "--task",
        paths.task_slug,
        "--request",
        str(Path(request_path).resolve()),
        "--repository-context",
        str(Path(repository_context_path).resolve()),
        "--model-policy",
        model_policy,
    ]
    if retry_incomplete:
        arguments.append("--retry-incomplete")
    if review_policy != validate_packet.DEFAULT_REVIEW_POLICY:
        arguments.extend(["--review-policy", review_policy])
    if requested_model_label is not None:
        arguments.extend(["--requested-model-label", requested_model_label])
    if approved_existing_path_manifest is not None:
        arguments.extend(
            [
                "--approved-existing-path-manifest",
                str(Path(approved_existing_path_manifest).resolve()),
            ]
        )
    else:
        for approved_path in approved_existing_paths:
            arguments.extend(["--approved-existing-path", approved_path])
    return arguments


def _approval_guidance(
    paths: RunPaths,
    preflight: Mapping[str, object],
    request_path: Path,
    repository_context_path: Path,
    model_policy: str,
    requested_model_label: str | None,
    review_policy: str = validate_packet.DEFAULT_REVIEW_POLICY,
) -> list[str]:
    initial = list(preflight["initial_product_paths"])
    preview = initial[:MAX_PATH_PREVIEW]
    manifest_path = _suggested_approval_manifest_path(paths)
    generate = [
        "python",
        "skills/gpt-pro-codex-loop/scripts/gpc_loop.py",
        "inspect-init",
        "--repo",
        str(paths.repository),
        "--task",
        paths.task_slug,
        "--write-approval-manifest",
        str(manifest_path),
    ]
    retry = _init_argv(
        paths,
        request_path,
        repository_context_path,
        model_policy,
        requested_model_label,
        approved_existing_path_manifest=manifest_path,
        review_policy=review_policy,
    )
    details = [
        f"initial_product_path_count:{len(initial)}",
        f"path_set_digest:{_path_set_digest(initial)}",
        *(f"path_preview:{path}" for path in preview),
        f"omitted_path_count:{max(0, len(initial) - len(preview))}",
        f"generate_manifest_argv:{_command_json(generate)}",
        f"retry_init_argv:{_command_json(retry)}",
    ]
    return details


def _manifest_errors(
    manifest: object, paths: RunPaths, preflight: Mapping[str, object]
) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest: must be an object"]
    errors: list[str] = []
    missing = sorted(APPROVAL_MANIFEST_FIELDS - set(manifest))
    unknown = sorted(set(manifest) - APPROVAL_MANIFEST_FIELDS)
    errors.extend(f"manifest.{field}: missing required field" for field in missing)
    errors.extend(f"manifest.{field}: unknown field" for field in unknown)
    if missing:
        return errors
    if manifest.get("schema_version") != SCHEMA_VERSION or isinstance(
        manifest.get("schema_version"), bool
    ):
        errors.append("manifest.schema_version: must be integer 1")
    if manifest.get("repository") != str(paths.repository):
        errors.append("manifest.repository: does not match the canonical repository")
    if manifest.get("task") != paths.task_slug:
        errors.append("manifest.task: does not match the requested task")
    if manifest.get("baseline_head") != preflight.get("baseline_head"):
        errors.append("manifest.baseline_head: is stale or does not match")
    values = manifest.get("initial_product_paths")
    approved: list[str] = []
    if not isinstance(values, list):
        errors.append("manifest.initial_product_paths: must be a list")
    else:
        for index, value in enumerate(values):
            if not isinstance(value, str):
                errors.append(f"manifest.initial_product_paths.{index}: must be a path")
                continue
            candidate = PurePosixPath(value)
            if (
                not value
                or "\\" in value
                or candidate.is_absolute()
                or not candidate.parts
                or candidate.parts[0].endswith(":")
                or any(part in {"", ".", ".."} for part in candidate.parts)
                or "/".join(candidate.parts) != value
            ):
                errors.append(
                    f"manifest.initial_product_paths.{index}: invalid canonical path"
                )
                continue
            approved.append(value)
        if approved != sorted(set(approved)):
            errors.append("manifest.initial_product_paths: must be sorted and unique")
    if (
        type(manifest.get("path_count")) is not int
        or manifest.get("path_count") != len(approved)
    ):
        errors.append("manifest.path_count: does not match the path list")
    if manifest.get("path_set_digest") != _path_set_digest(approved):
        errors.append("manifest.path_set_digest: does not match the path list")
    if not errors:
        errors.extend(
            capture_snapshot.validate_preflight(
                dict(preflight), approved, paths.repository
            )
        )
    return sorted(set(errors))


def _load_manifest_approval(
    manifest_path: Path,
    paths: RunPaths,
    preflight: Mapping[str, object],
    request_path: Path,
    repository_context_path: Path,
    model_policy: str,
    requested_model_label: str | None,
    review_policy: str = validate_packet.DEFAULT_REVIEW_POLICY,
) -> list[str]:
    try:
        manifest = load_json(Path(manifest_path))
    except ControllerError as exc:
        raise ControllerError(
            "APPROVAL_MANIFEST_INVALID",
            "The approved-path manifest could not be read or parsed.",
        ) from exc
    errors = _manifest_errors(manifest, paths, preflight)
    if errors:
        raise ControllerError(
            "APPROVAL_MANIFEST_INVALID",
            "The approved-path manifest is invalid, stale, or does not match the current preflight.",
            [
                *errors[:MAX_PATH_PREVIEW],
                *_approval_guidance(
                    paths,
                    preflight,
                    request_path,
                    repository_context_path,
                    model_policy,
                    requested_model_label,
                    review_policy,
                ),
            ],
        )
    return list(manifest["initial_product_paths"])


def _is_link_or_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(value.st_mode):
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(value, "st_file_attributes", 0)
    return bool(reparse and attributes & reparse)


def _windows_process_status(pid: int) -> str:
    """Probe a Windows PID without sending it a console control event."""
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    error_access_denied = 5
    error_invalid_parameter = 87
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    get_exit_code = kernel32.GetExitCodeProcess
    get_exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    get_exit_code.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = open_process(process_query_limited_information, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == error_invalid_parameter:
            return "stale"
        if error == error_access_denied:
            return "active"
        return "ambiguous"
    try:
        exit_code = wintypes.DWORD()
        if not get_exit_code(handle, ctypes.byref(exit_code)):
            return "ambiguous"
        return "active" if exit_code.value == still_active else "stale"
    finally:
        close_handle(handle)


def _lock_status(path: Path) -> str:
    if not path.exists():
        return "absent"
    if _is_link_or_reparse(path) or not path.is_file():
        return "ambiguous"
    try:
        record = load_json(path)
    except ControllerError:
        return "ambiguous"
    if set(record) != LOCK_FIELDS:
        return "ambiguous"
    if record.get("schema_version") != SCHEMA_VERSION or isinstance(
        record.get("schema_version"), bool
    ):
        return "ambiguous"
    pid = record.get("pid")
    hostname = record.get("hostname")
    created = record.get("created_at_unix")
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or hostname != socket.gethostname()
        or not isinstance(created, int)
        or isinstance(created, bool)
    ):
        return "ambiguous"
    if os.name == "nt":
        return _windows_process_status(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "stale"
    except PermissionError:
        return "active"
    except OSError:
        return "stale"
    return "active"


def _valid_initialization_marker(path: Path, paths: RunPaths) -> bool:
    try:
        marker = load_json(path)
    except ControllerError:
        return False
    return (
        set(marker) == INITIALIZATION_MARKER_FIELDS
        and marker.get("schema_version") == SCHEMA_VERSION
        and marker.get("kind") == "gpc-loop-initialization"
        and marker.get("repository") == str(paths.repository)
        and marker.get("task") == paths.task_slug
        and isinstance(marker.get("baseline_head"), str)
        and isinstance(marker.get("pid"), int)
        and not isinstance(marker.get("pid"), bool)
        and marker["pid"] > 0
        and marker.get("hostname") == socket.gethostname()
        and isinstance(marker.get("created_at_unix"), int)
        and not isinstance(marker.get("created_at_unix"), bool)
    )


def _incomplete_initialization(paths: RunPaths) -> dict[str, object]:
    if not paths.run.exists():
        return {"recognized": False, "reason": "absent", "lock_status": "absent"}
    if _is_link_or_reparse(paths.run) or not paths.run.is_dir():
        return {"recognized": False, "reason": "ambiguous", "lock_status": "ambiguous"}
    if paths.state.exists():
        return {"recognized": False, "reason": "established", "lock_status": _lock_status(paths.lock)}
    children = list(paths.run.iterdir())
    if any(_is_link_or_reparse(child) for child in children):
        return {"recognized": False, "reason": "ambiguous", "lock_status": "ambiguous"}
    names = {child.name for child in children}
    marker = paths.run / INITIALIZATION_MARKER_NAME
    marker_valid = marker.is_file() and _valid_initialization_marker(marker, paths)
    marker_temporaries = {
        name for name in names if name.startswith(f".{INITIALIZATION_MARKER_NAME}.")
    }
    legacy_allowed = {"transactions", ".lock"} | marker_temporaries
    marker_allowed = {
        "transactions",
        ".lock",
        INITIALIZATION_MARKER_NAME,
        "request.md",
        "repository-context.md",
        "preflight.json",
    } | marker_temporaries
    if not marker_valid and not names <= legacy_allowed:
        return {"recognized": False, "reason": "ambiguous", "lock_status": _lock_status(paths.lock)}
    if marker_valid and not names <= marker_allowed:
        return {"recognized": False, "reason": "ambiguous", "lock_status": _lock_status(paths.lock)}
    transaction_root = paths.transactions
    if transaction_root.exists():
        if _is_link_or_reparse(transaction_root) or not transaction_root.is_dir():
            return {"recognized": False, "reason": "ambiguous", "lock_status": "ambiguous"}
        transactions = list(transaction_root.iterdir())
        if not marker_valid and transactions:
            return {"recognized": False, "reason": "ambiguous", "lock_status": _lock_status(paths.lock)}
        if len(transactions) > 1:
            return {"recognized": False, "reason": "ambiguous", "lock_status": _lock_status(paths.lock)}
        for transaction in transactions:
            if (
                _is_link_or_reparse(transaction)
                or not transaction.is_dir()
                or not transaction.name.startswith("initialize-")
            ):
                return {"recognized": False, "reason": "ambiguous", "lock_status": "ambiguous"}
            allowed_staged = {"request.md", "repository-context.md", "preflight.json", "state.json"}
            for staged in transaction.iterdir():
                temporary = any(
                    staged.name.startswith(f".{name}.") for name in allowed_staged
                )
                if (
                    _is_link_or_reparse(staged)
                    or not staged.is_file()
                    or (staged.name not in allowed_staged and not temporary)
                ):
                    return {"recognized": False, "reason": "ambiguous", "lock_status": "ambiguous"}
    lock_state = _lock_status(paths.lock)
    if lock_state == "ambiguous":
        return {"recognized": False, "reason": "ambiguous", "lock_status": lock_state}
    return {"recognized": True, "reason": "incomplete", "lock_status": lock_state}


def _remove_verified_incomplete(paths: RunPaths) -> None:
    classification = _incomplete_initialization(paths)
    if not classification["recognized"]:
        raise ControllerError(
            "INIT_RECOVERY_REFUSED",
            "Incomplete initialization is ambiguous; no files were changed.",
        )
    if classification["lock_status"] == "active":
        raise ControllerError("RUN_LOCKED", "Incomplete initialization is still active.")
    staged_names = {"request.md", "repository-context.md", "preflight.json", "state.json"}
    if paths.transactions.is_dir():
        for transaction in list(paths.transactions.iterdir()):
            for staged in list(transaction.iterdir()):
                if staged.name not in staged_names and not any(
                    staged.name.startswith(f".{name}.") for name in staged_names
                ):
                    raise ControllerError(
                        "INIT_RECOVERY_REFUSED",
                        "Incomplete initialization changed during recovery; no foreign file was removed.",
                    )
                staged.unlink()
            transaction.rmdir()
        paths.transactions.rmdir()
    for child in list(paths.run.iterdir()):
        if child.is_file() and (
            child.name
            in {
                ".lock",
                INITIALIZATION_MARKER_NAME,
                "request.md",
                "repository-context.md",
                "preflight.json",
            }
            or child.name.startswith(f".{INITIALIZATION_MARKER_NAME}.")
        ):
            child.unlink()
    try:
        paths.run.rmdir()
    except OSError as exc:
        raise ControllerError(
            "INIT_RECOVERY_REFUSED",
            "Incomplete initialization changed during recovery; no foreign file was removed.",
        ) from exc


def _remove_stale_initialization_lock(path: Path) -> None:
    try:
        owned_stat = path.stat()
    except OSError as exc:
        raise ControllerError(
            "INIT_RECOVERY_REFUSED",
            "Initialization lock changed during recovery; no files were changed.",
        ) from exc
    status = _lock_status(path)
    if status == "active":
        raise ControllerError("RUN_LOCKED", "Initialization is already active.")
    if status != "stale":
        raise ControllerError(
            "INIT_RECOVERY_REFUSED",
            "Initialization lock is ambiguous; no files were changed.",
        )
    try:
        if not os.path.samestat(owned_stat, path.stat()):
            raise ControllerError(
                "INIT_RECOVERY_REFUSED",
                "Initialization lock changed during recovery; no files were changed.",
            )
        path.unlink()
    except ControllerError:
        raise
    except OSError as exc:
        raise ControllerError("LOCK_FAILED", "Could not remove the verified stale initialization lock.") from exc


def inspect_initialization(
    repository: Path, task_slug: str, output_path: Path | None = None
) -> dict[str, object]:
    """Inspect initial product paths without creating controller run state."""
    paths = resolve_run(repository, task_slug)
    if paths.run.exists():
        classification = _incomplete_initialization(paths)
        if not classification["recognized"]:
            raise ControllerError(
                "RUN_EXISTS", "Cannot inspect initialization for an established or ambiguous run."
            )
    preflight = capture_snapshot.inspect_preflight(
        paths.repository, _head_commit(paths.repository)
    )
    manifest = _approval_manifest(paths, preflight)
    if output_path is not None:
        write_json_atomic(Path(output_path), manifest)
    initial = list(manifest["initial_product_paths"])
    result: dict[str, object] = {
        "initial_product_path_count": len(initial),
        "path_set_digest": manifest["path_set_digest"],
        "path_preview": initial[:MAX_PATH_PREVIEW],
        "omitted_path_count": max(0, len(initial) - MAX_PATH_PREVIEW),
        "approval_manifest_path": str(Path(output_path).resolve()) if output_path else None,
    }
    return result


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
    approved_existing_path_manifest: Path | None = None,
    retry_incomplete: bool = False,
    governance_context_path: Path | None = None,
    review_policy: str = validate_packet.DEFAULT_REVIEW_POLICY,
) -> dict[str, object]:
    """Create a fully validated, conversation-unbound controller run."""
    paths = resolve_run(repository, task_slug)
    _validate_model_policy(model_policy, requested_model_label)
    _validate_review_policy(review_policy)
    request_text = _read_input(request_path, "request")
    context_text = _read_input(repository_context_path, "repository context")
    hotl_context: dict[str, object] | None = None
    hotl_context_digest: str | None = None
    if governance_context_path is not None:
        hotl_context, hotl_context_digest = _load_hotl_governance_context(
            governance_context_path, task_slug
        )
    validate_model_bound_section("user_request", request_text)
    validate_model_bound_section("repository_evidence", context_text)
    if approved_existing_path_manifest is not None and approved_existing_paths:
        raise ControllerError(
            "APPROVAL_SOURCE_CONFLICT",
            "Use either approved path arguments or one approved-path manifest, not both.",
        )
    metadata = paths.run.parent
    metadata.mkdir(parents=True, exist_ok=True)
    initialization_lock = metadata / f".{paths.task_slug}.initialize.lock"
    if retry_incomplete and initialization_lock.exists():
        _remove_stale_initialization_lock(initialization_lock)
    with run_lock(initialization_lock):
        if paths.run.exists():
            classification = _incomplete_initialization(paths)
            if retry_incomplete:
                if classification["reason"] == "established":
                    raise ControllerError(
                        "INIT_RECOVERY_REFUSED",
                        "Cannot retry an established run; no files were changed.",
                    )
                if not classification["recognized"]:
                    raise ControllerError(
                        "INIT_RECOVERY_REFUSED",
                        "Incomplete initialization is ambiguous; no files were changed.",
                    )
                _remove_verified_incomplete(paths)
            elif classification["recognized"]:
                retry_manifest = approved_existing_path_manifest
                retry_paths = approved_existing_paths
                details: list[str] = []
                if retry_manifest is None and len(retry_paths) > MAX_PATH_PREVIEW:
                    retry_manifest = _suggested_approval_manifest_path(paths)
                    retry_paths = []
                    generate_argv = [
                        "python",
                        "skills/gpt-pro-codex-loop/scripts/gpc_loop.py",
                        "inspect-init",
                        "--repo",
                        str(paths.repository),
                        "--task",
                        paths.task_slug,
                        "--write-approval-manifest",
                        str(retry_manifest),
                    ]
                    details.append(f"generate_manifest_argv:{_command_json(generate_argv)}")
                retry_argv = _init_argv(
                    paths,
                    request_path,
                    repository_context_path,
                    model_policy,
                    requested_model_label,
                    retry_paths,
                    retry_manifest,
                    retry_incomplete=True,
                    review_policy=review_policy,
                )
                details.append(f"retry_init_argv:{_command_json(retry_argv)}")
                raise ControllerError(
                    "INIT_INCOMPLETE",
                    "A recognized incomplete initialization exists; retry explicitly.",
                    details,
                )
            else:
                raise ControllerError("RUN_EXISTS", "Run already exists or is ambiguous.")
        baseline_head = _head_commit(paths.repository)
        try:
            paths.run.mkdir()
        except FileExistsError as exc:
            raise ControllerError("RUN_EXISTS", "Run already exists.") from exc
        lock_acquired = False
        initialized = False
        committed_paths: list[tuple[Path, os.stat_result]] = []
        try:
            marker_path = paths.run / INITIALIZATION_MARKER_NAME
            write_json_atomic(
                marker_path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "gpc-loop-initialization",
                    "repository": str(paths.repository),
                    "task": paths.task_slug,
                    "baseline_head": baseline_head,
                    "pid": os.getpid(),
                    "hostname": socket.gethostname(),
                    "created_at_unix": int(time.time()),
                },
            )
            committed_paths.append(_owned_path(marker_path))
            paths.transactions.mkdir()
            with run_lock(paths.lock):
                lock_acquired = True
                preflight = capture_snapshot.inspect_preflight(
                    paths.repository, baseline_head
                )
                if approved_existing_path_manifest is not None:
                    approved_existing_paths = _load_manifest_approval(
                        approved_existing_path_manifest,
                        paths,
                        preflight,
                        request_path,
                        repository_context_path,
                        model_policy,
                        requested_model_label,
                        review_policy,
                    )
                preflight_errors = capture_snapshot.validate_preflight(
                    preflight, approved_existing_paths, paths.repository
                )
                if preflight_errors:
                    message = "Preflight has unapproved or invalid product paths."
                    code = "PREFLIGHT_INVALID"
                    details = list(preflight_errors[:MAX_PATH_PREVIEW])
                    if any(
                        error.startswith("unapproved pre-existing")
                        for error in preflight_errors
                    ):
                        message = "Preflight has unapproved pre-existing product paths."
                        code = "PREFLIGHT_APPROVAL_REQUIRED"
                        details = _approval_guidance(
                            paths,
                            preflight,
                            request_path,
                            repository_context_path,
                            model_policy,
                            requested_model_label,
                            review_policy,
                        )
                    raise ControllerError(
                        code,
                        message,
                        details,
                    )
                approved_paths = _normalize_approved_paths(approved_existing_paths)
                previous = initial_state(
                    preflight,
                    approved_paths,
                    model_policy,
                    requested_model_label,
                    review_policy,
                    hotl_context,
                    hotl_context_digest,
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
                state_stage = transaction / "state.json"
                staged_paths: list[tuple[Path, os.stat_result]] = []
                try:
                    write_text_atomic(request_stage, request_text)
                    staged_paths.append(_owned_path(request_stage))
                    write_text_atomic(context_stage, context_text)
                    staged_paths.append(_owned_path(context_stage))
                    write_json_atomic(preflight_stage, preflight)
                    staged_paths.append(_owned_path(preflight_stage))
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
                        os.replace(state_stage, paths.state)
                        committed_paths.append(_owned_path(paths.state))
                    except OSError as exc:
                        raise ControllerError(
                            "WRITE_FAILED",
                            "Could not commit initialized controller artifacts.",
                        ) from exc
                    initialized = True
                    _record_events_best_effort(paths, [{
                        "schema_version": SCHEMA_VERSION,
                        "event": "RUN_INITIALIZED",
                        "at_unix": int(time.time()),
                    }])
                finally:
                    _cleanup_owned_transaction(transaction, staged_paths)
        finally:
            if not initialized and (lock_acquired or not paths.lock.exists()):
                _cleanup_failed_initialization(paths, committed_paths)
    return status_run(paths.repository, task_slug)


def _prompt_contract_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "prompt-contract.md"


def _canonical_prompt_json(value: object) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ControllerError("INVALID_PROMPT_VALUE", "Prompt value is not canonical JSON.") from exc


def _valid_expected_header(
    value: object,
    task_slug: str | None = None,
    packet_type: str | None = None,
    semantic_sequence: int | None = None,
    expected_nonce: str | None = None,
) -> bool:
    if not isinstance(value, dict) or set(value) != EXPECTED_HEADER_FIELDS:
        return False
    if type(value.get("schema_version")) is not int or value["schema_version"] != SCHEMA_VERSION:
        return False
    if value.get("packet_type") not in {"requirements", "review"}:
        return False
    if any(
        not isinstance(value.get(field), str) or not value[field]
        for field in ("run_id", "turn_id", "nonce")
    ):
        return False
    if NONCE.fullmatch(value["nonce"]) is None:
        return False
    if expected_nonce is not None and value["nonce"] != expected_nonce:
        return False
    if task_slug is not None and value["run_id"] != f"gpc-loop-{task_slug}":
        return False
    if packet_type is not None and value["packet_type"] != packet_type:
        return False
    if semantic_sequence is not None and value["turn_id"] != (
        f"{value['packet_type']}-{semantic_sequence:02d}"
    ):
        return False
    if any(
        not isinstance(value.get(field), str) or DIGEST.fullmatch(value[field]) is None
        for field in ("in_reply_to", "prompt_digest")
    ):
        return False
    previous = value.get("previous_packet_digest")
    return previous is None or (
        isinstance(previous, str) and DIGEST.fullmatch(previous) is not None
    )


def _validate_abandoned_attempt_receipt(value: object) -> None:
    valid = isinstance(value, dict) and set(value) == ABANDONED_ATTEMPT_FIELDS
    expected = value.get("expected_header") if isinstance(value, dict) else None
    valid = valid and value.get("schema_version") == SCHEMA_VERSION
    valid = valid and type(value.get("schema_version")) is int
    valid = valid and value.get("status") == "ABANDONED_NOT_SENT"
    valid = valid and _valid_expected_header(expected)
    if valid and isinstance(expected, dict):
        valid = value.get("expected_header_digest") == validate_packet.canonical_digest(
            expected
        )
        valid = valid and value.get("nonce") == expected.get("nonce")
        valid = valid and value.get("prompt_digest") == expected.get("prompt_digest")
    evidence = value.get("evidence") if isinstance(value, dict) else None
    valid = valid and isinstance(evidence, str) and bool(evidence.strip())
    valid = valid and len(evidence.encode("utf-8")) <= MAX_ABANDON_EVIDENCE_BYTES
    abandoned_at = value.get("abandoned_at_unix") if isinstance(value, dict) else None
    valid = valid and type(abandoned_at) is int and abandoned_at >= 0
    if not valid:
        raise ControllerError(
            "INVALID_ABANDONED_ATTEMPT",
            "Invalid abandoned attempt receipt.",
        )


def _attempt_number(paths: RunPaths) -> int:
    numbers: list[int] = []
    for path in paths.run.iterdir():
        match = ATTEMPT_NAME.fullmatch(path.name)
        if match is not None:
            try:
                artifact = load_json(path)
            except ControllerError as exc:
                raise ControllerError(
                    "INVALID_ABANDONED_ATTEMPT",
                    "Invalid abandoned attempt receipt.",
                ) from exc
            if path.name.startswith("abandoned-") or artifact.get("status") == "ABANDONED_NOT_SENT":
                _validate_abandoned_attempt_receipt(artifact)
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _requirements_preparation_context(
    paths: RunPaths,
    state: Mapping[str, object],
    expected: Mapping[str, object],
) -> dict[str, object]:
    """Bind an anchor replacement to the exact locally abandoned attempt."""
    previous_anchor = state.get("pending_requirements_expected_header_digest")
    abandoned: dict[str, object] | None = None
    if previous_anchor is not None:
        matches: list[dict[str, object]] = []
        for path in sorted(paths.run.glob("expected-attempt-*.json")):
            artifact = load_json(path)
            if artifact.get("status") != "ABANDONED_NOT_SENT":
                continue
            _validate_abandoned_attempt_receipt(artifact)
            header = artifact.get("expected_header")
            if (
                artifact.get("expected_header_digest") == previous_anchor
                and isinstance(header, dict)
                and header.get("packet_type") == "requirements"
            ):
                matches.append(artifact)
        if len(matches) != 1:
            raise ControllerError(
                "INVALID_ABANDONED_ATTEMPT",
                "Requirements anchor replacement requires one matching abandoned attempt.",
            )
        abandoned = matches[0]
    return {
        "expected": dict(expected),
        "abandoned_attempt": abandoned,
    }


def _expected_header(
    task_slug: str,
    packet_type: str,
    semantic_sequence: int,
    source_digest: str,
    previous_packet_digest: object,
    nonce: str,
) -> dict[str, object]:
    run_id = f"gpc-loop-{task_slug}"
    turn_id = f"{packet_type}-{semantic_sequence:02d}"
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_type": packet_type,
        "run_id": run_id,
        "turn_id": turn_id,
        "nonce": nonce,
        "in_reply_to": validate_packet.canonical_digest(
            {"run_id": run_id, "turn_id": turn_id, "source_digest": source_digest}
        ),
        "prompt_digest": "",
        "previous_packet_digest": previous_packet_digest,
    }


def _derive_attempt_nonce(
    state: Mapping[str, object],
    task_slug: str,
    packet_type: str,
    semantic_sequence: int,
    attempt_number: int,
) -> str:
    """Bind one exact attempt nonce to immutable trusted run provenance."""
    key = state.get("nonce_derivation_key")
    if not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None:
        raise ControllerError("INVALID_STATE", "Trusted nonce derivation key is invalid.")
    message = _canonical_json_bytes(
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": f"gpc-loop-{task_slug}",
            "packet_type": packet_type,
            "semantic_sequence": semantic_sequence,
            "attempt_number": attempt_number,
        }
    )
    return hmac.new(bytes.fromhex(key), message, hashlib.sha256).hexdigest()[:32]


def _save_attempt(
    paths: RunPaths, attempt_number: int, turn_id: str, prompt: str, expected: Mapping[str, object]
) -> tuple[Path, Path]:
    prompts = paths.run / "prompts"
    prompts.mkdir(exist_ok=True)
    prompt_path = prompts / f"{turn_id}-attempt-{attempt_number:02d}.md"
    expected_path = paths.run / f"expected-attempt-{attempt_number:02d}.json"
    transaction = paths.transactions / f"prepare-{os.getpid()}-{time.time_ns()}"
    transaction.mkdir()
    prompt_stage = transaction / prompt_path.name
    expected_stage = transaction / expected_path.name
    staged: list[tuple[Path, os.stat_result]] = []
    committed: list[tuple[Path, os.stat_result]] = []
    try:
        write_text_atomic(prompt_stage, prompt)
        staged.append(_owned_path(prompt_stage))
        write_json_atomic(expected_stage, dict(expected))
        staged.append(_owned_path(expected_stage))
        os.replace(prompt_stage, prompt_path)
        committed.append(_owned_path(prompt_path))
        os.replace(expected_stage, expected_path)
        committed.append(_owned_path(expected_path))
    except OSError as exc:
        _unlink_owned(committed)
        raise ControllerError("WRITE_FAILED", "Could not persist the pre-send attempt.") from exc
    finally:
        _cleanup_owned_transaction(transaction, staged)
    return prompt_path, expected_path


def _revision_prompt_values(
    paths: RunPaths, state: Mapping[str, object], conflict_evidence_path: Path
) -> tuple[dict[str, str | Template], int, str]:
    if not conflict_evidence_path.is_file():
        raise ControllerError("INPUT_READ_FAILED", "Could not read conflict evidence input.")
    conflict = _read_input(conflict_evidence_path, "conflict evidence")
    if not conflict.strip():
        raise ControllerError("INVALID_CONFLICT_EVIDENCE", "Conflict evidence must not be empty.")
    validate_model_bound_section("conflict_evidence", conflict)
    previous_digest = state.get("active_requirements_digest")
    revision = state.get("active_requirements_revision")
    if not isinstance(previous_digest, str) or not isinstance(revision, int):
        raise ControllerError("INVALID_STATE", "Requirements revision lacks active trusted requirements.")
    previous_path = paths.run / "requirements.json"
    previous = load_json(previous_path)
    next_revision = revision + 1
    approval = state.get("pending_user_approval_evidence")
    values: dict[str, str | Template] = {
        "PREVIOUS_REQUIREMENTS_JSON": _canonical_prompt_json(previous),
        "PREVIOUS_REQUIREMENTS_DIGEST": previous_digest,
        "CONFLICT_EVIDENCE": conflict,
        "APPROVAL_RECEIPT_OR_NULL": _canonical_prompt_json(approval),
        "NEXT_REVISION": str(next_revision),
    }
    source_digest = validate_packet.canonical_digest(
        {
            "previous_requirements_digest": previous_digest,
            "conflict_evidence": _normalize_text(conflict),
            "approval_receipt": approval,
        }
    )
    return values, next_revision, source_digest


def prepare_requirements(
    repository: Path,
    task_slug: str,
    conflict_evidence_path: Path | None = None,
) -> dict[str, object]:
    """Persist one correlated requirements prompt and its expected header."""
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    with run_lock(paths.lock):
        _require_manual_recovery(paths)
        state, loaded_state_digest = _load_mutator_state(paths)
        if state.get("phase") != "REQUIREMENTS_PENDING":
            raise ControllerError("INVALID_PHASE", "Requirements can be prepared only when pending.")
        attempts = _outstanding_attempts(paths)
        if attempts:
            raise ControllerError("OUTSTANDING_ATTEMPT", "A requirements attempt is already outstanding.")

        shared = load_template(_prompt_contract_path(), "Shared envelope instruction")
        if state.get("active_requirements_digest") is None:
            if conflict_evidence_path is not None:
                raise ControllerError("INVALID_PHASE", "Initial requirements do not accept conflict evidence.")
            request = _read_input(paths.run / "request.md", "request")
            repository_evidence = _read_input(
                paths.run / "repository-context.md", "repository context"
            )
            values: dict[str, str | Template] = {
                "USER_REQUEST": request,
                "REPOSITORY_EVIDENCE": repository_evidence,
            }
            template = load_template(_prompt_contract_path(), "Initial requirements")
            semantic_sequence = 1
            source_digest = validate_packet.canonical_digest(
                {
                    "user_request": _normalize_text(request),
                    "repository_evidence": _normalize_text(repository_evidence),
                }
            )
        else:
            if conflict_evidence_path is None:
                raise ControllerError("CONFLICT_EVIDENCE_REQUIRED", "Requirements revision needs conflict evidence.")
            values, semantic_sequence, source_digest = _revision_prompt_values(
                paths, state, conflict_evidence_path
            )
            template = load_template(_prompt_contract_path(), "Requirements revision")

        attempt_number = _attempt_number(paths)
        previous_packet_digest = state.get("last_consumed_packet_digest")
        if previous_packet_digest is not None and not isinstance(previous_packet_digest, str):
            raise ControllerError("INVALID_STATE", "Trusted packet-chain head is invalid.")
        expected = _expected_header(
            task_slug,
            "requirements",
            semantic_sequence,
            source_digest,
            previous_packet_digest,
            _derive_attempt_nonce(
                state,
                task_slug,
                "requirements",
                semantic_sequence,
                attempt_number,
            ),
        )
        values.update(
            {
                "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REQUIREMENTS": shared,
                "PACKET_TYPE": "requirements",
                "RUN_ID": str(expected["run_id"]),
                "TURN_ID": str(expected["turn_id"]),
                "NONCE": str(expected["nonce"]),
                "IN_REPLY_TO_DIGEST": str(expected["in_reply_to"]),
                "PREVIOUS_PACKET_DIGEST_OR_NULL": (
                    previous_packet_digest if previous_packet_digest is not None else "null"
                ),
            }
        )
        rendered = render_prompt(template, values)
        expected["prompt_digest"] = rendered["prompt_digest"]
        candidate = dict(state)
        candidate["pending_requirements_expected_header_digest"] = (
            validate_packet.canonical_digest(expected)
        )
        _raise_validation(
            "INVALID_TRANSITION",
            "Requirements preparation failed state validation.",
            validate_packet.validate_transition(
                state,
                candidate,
                requirements_preparation_context=_requirements_preparation_context(
                    paths,
                    state,
                    expected,
                ),
            ),
        )
        prompt_path = paths.run / "prompts" / f"{expected['turn_id']}-attempt-{attempt_number:02d}.md"
        expected_path = paths.run / f"expected-attempt-{attempt_number:02d}.json"
        _commit_artifacts_then_state(
            paths,
            [(prompt_path, rendered["prompt"]), (expected_path, expected)],
            candidate,
            expected_state_digest=loaded_state_digest,
        )
    return {
        "prompt_path": str(prompt_path),
        "expected_header_path": str(expected_path),
        "prompt_digest": expected["prompt_digest"],
        "nonce": expected["nonce"],
        "turn_id": expected["turn_id"],
    }


LOCAL_EVIDENCE_FIELDS = {
    "schema_version",
    "changed_file_intents",
    "intent_summary",
    "acceptance_evidence",
    "test_commands",
    "diff_evidence",
    "omissions",
    "unresolved_risks_or_blockers",
}
LOCAL_EVIDENCE_COMMAND_FIELDS = {"command", "outcome", "output_summary"}
FORBIDDEN_EVIDENCE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "password",
    "secret",
    "session",
    "session_id",
    "token",
}


def _require_nonempty_string(value: object, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field}: must be a non-empty string")


def _validate_evidence_strings(value: object, field: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{field}: must be a list of non-empty strings")
        return
    for index, item in enumerate(value):
        _require_nonempty_string(item, f"{field}.{index}", errors)


def _forbidden_evidence_schema_field_names(value: object) -> list[str]:
    """Reject secret-bearing schema fields without interpreting dynamic map keys."""
    errors: list[str] = []
    mappings: list[tuple[str, object]] = [("", value)]
    if isinstance(value, dict) and isinstance(value.get("test_commands"), list):
        mappings.extend(
            (f"test_commands.{index}.", command)
            for index, command in enumerate(value["test_commands"])
        )
    for field, mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for key in mapping:
            normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
            if normalized in FORBIDDEN_EVIDENCE_FIELD_NAMES:
                errors.append(f"{field}{key}: credential or session fields are forbidden")
    return errors


def _model_bound_report_items(evidence: Mapping[str, object]) -> list[str]:
    """Flatten report items for diagnostics only; field-specific caps remain authoritative."""
    items: list[str] = [str(evidence["intent_summary"])]
    if "changed_file_intents" in evidence:
        items.extend(str(value) for value in evidence["changed_file_intents"].values())  # type: ignore[union-attr]
    else:
        items.extend(
            str(item.get("intent", ""))
            for item in evidence["changed_files"]  # type: ignore[union-attr]
            if isinstance(item, dict)
        )
    for entries in evidence["acceptance_evidence"].values():  # type: ignore[union-attr]
        items.extend(entries)
    items.extend(_canonical_prompt_json(command) for command in evidence["test_commands"])  # type: ignore[union-attr]
    for field in ("diff_evidence", "omissions", "unresolved_risks_or_blockers"):
        items.extend(evidence[field])  # type: ignore[arg-type]
    return items


def _load_local_evidence(
    path: Path, requirements: Mapping[str, object]
) -> dict[str, object]:
    evidence = load_json(path)
    errors: list[str] = []
    if set(evidence) != LOCAL_EVIDENCE_FIELDS:
        errors.append("local evidence: contains unknown or missing fields")
    if type(evidence.get("schema_version")) is not int or evidence.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version: must be 1")
    errors.extend(_forbidden_evidence_schema_field_names(evidence))

    intents = evidence.get("changed_file_intents")
    if not isinstance(intents, dict):
        errors.append("changed_file_intents: must be an object")
    else:
        for path_name, intent in intents.items():
            _require_nonempty_string(path_name, "changed_file_intents path", errors)
            _require_nonempty_string(intent, f"changed_file_intents.{path_name}", errors)
    _require_nonempty_string(evidence.get("intent_summary"), "intent_summary", errors)

    acceptance_ids = {
        item.get("id")
        for item in requirements.get("acceptance_criteria", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    acceptance_evidence = evidence.get("acceptance_evidence")
    if not isinstance(acceptance_evidence, dict):
        errors.append("acceptance_evidence: must be an object")
    else:
        for acceptance_id in sorted(acceptance_ids - set(acceptance_evidence)):
            errors.append(f"acceptance_evidence.{acceptance_id}: missing acceptance evidence")
        for acceptance_id, entries in acceptance_evidence.items():
            if acceptance_id not in acceptance_ids:
                errors.append(f"acceptance_evidence.{acceptance_id}: unknown acceptance ID")
            if not isinstance(entries, list) or not entries:
                errors.append(
                    f"acceptance_evidence.{acceptance_id}: must be a non-empty list of non-empty strings"
                )
            else:
                _validate_evidence_strings(entries, f"acceptance_evidence.{acceptance_id}", errors)

    commands = evidence.get("test_commands")
    if not isinstance(commands, list):
        errors.append("test_commands: must be a list")
    else:
        for index, command in enumerate(commands):
            if not isinstance(command, dict) or set(command) != LOCAL_EVIDENCE_COMMAND_FIELDS:
                errors.append(f"test_commands.{index}: contains unknown or missing fields")
                continue
            for key in LOCAL_EVIDENCE_COMMAND_FIELDS:
                _require_nonempty_string(command.get(key), f"test_commands.{index}.{key}", errors)
    for field in ("diff_evidence", "omissions", "unresolved_risks_or_blockers"):
        _validate_evidence_strings(evidence.get(field), field, errors)
    schema_shape_error = "local evidence: contains unknown or missing fields" in errors
    _raise_validation(
        "INVALID_LOCAL_EVIDENCE",
        (
            "Local evidence contains unknown or missing fields."
            if schema_shape_error
            else "Local evidence is invalid."
        ),
        sorted(set(errors)),
    )
    validate_model_bound_report(evidence)
    return evidence


def _active_requirements_artifact(
    paths: RunPaths, state: Mapping[str, object]
) -> tuple[dict[str, object], bytes]:
    path = paths.run / "requirements.json"
    try:
        raw = path.read_bytes()
        value = validate_packet.strict_json_loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ControllerError(
            "INVALID_REQUIREMENTS_ARTIFACT",
            "Stored requirements artifact is invalid.",
        ) from exc
    if not isinstance(value, dict) or _canonical_json_bytes(value) != raw:
        raise ControllerError(
            "NONCANONICAL_REQUIREMENTS_ARTIFACT",
            "Stored requirements artifact must use exact canonical JSON bytes.",
        )
    requirements = value
    revision = requirements.get("requirements_revision")
    previous_requirements = (
        load_json(_requirements_revision_path(paths, revision - 1))
        if isinstance(revision, int)
        and not isinstance(revision, bool)
        and revision > 1
        else None
    )
    requirements_errors = validate_packet.validate_requirements(
        requirements, previous_requirements
    )
    _raise_validation(
        "INVALID_STATE", "Stored requirements are invalid.", requirements_errors
    )
    if validate_packet.canonical_digest(requirements) != state.get("active_requirements_digest"):
        raise ControllerError("INVALID_STATE", "Stored requirements do not match trusted state.")
    if requirements.get("requirements_revision") != state.get("active_requirements_revision"):
        raise ControllerError("INVALID_STATE", "Stored requirements revision does not match trusted state.")
    return requirements, raw


def _active_requirements(paths: RunPaths, state: Mapping[str, object]) -> dict[str, object]:
    return _active_requirements_artifact(paths, state)[0]


def _capture_snapshot(paths: RunPaths, state: Mapping[str, object]) -> dict[str, object]:
    try:
        return capture_snapshot.capture_snapshot(
            paths.repository, str(state["baseline_head"]), load_json(paths.preflight)
        )
    except (capture_snapshot.SnapshotError, KeyError) as exc:
        raise ControllerError("SNAPSHOT_FAILED", "Could not capture the implementation snapshot.") from exc


def _snapshot_changed_file_intents(
    snapshot: Mapping[str, object], evidence: Mapping[str, object]
) -> list[dict[str, object]]:
    discovered = snapshot.get("changed_files")
    intents = evidence.get("changed_file_intents")
    if not isinstance(discovered, list) or not isinstance(intents, dict):
        raise ControllerError("INVALID_LOCAL_EVIDENCE", "Local evidence is invalid.")
    paths: list[str] = []
    changed_files: list[dict[str, object]] = []
    for index, item in enumerate(discovered):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ControllerError("SNAPSHOT_FAILED", "Captured snapshot has invalid changed files.")
        path = item["path"]
        if path in paths:
            raise ControllerError("SNAPSHOT_FAILED", "Captured snapshot has duplicate changed file paths.")
        paths.append(path)
        intent = intents.get(path)
        if not isinstance(intent, str) or not intent.strip():
            continue
        changed_files.append({**item, "intent": intent})
    if set(intents) != set(paths) or len(changed_files) != len(paths):
        raise ControllerError(
            "INVALID_LOCAL_EVIDENCE",
            "changed_file_intents must match captured changed file paths exactly.",
        )
    return changed_files


def _advance_report_phase(
    state: Mapping[str, object],
) -> tuple[dict[str, object], list[tuple[str, str]]]:
    current = dict(state)
    edges: list[tuple[str, str]] = []
    routes = {
        "REQUIREMENTS_FROZEN": "IMPLEMENTING",
        "IMPLEMENTING": "LOCAL_VERIFICATION",
        "LOCAL_VERIFICATION": "REVIEW_PENDING",
    }
    while current.get("phase") in routes:
        candidate = dict(current)
        candidate["phase"] = routes[str(current["phase"])]
        candidate["resolution_evidence"] = None
        candidate["resolution_stop_sequence"] = None
        _raise_validation(
            "INVALID_TRANSITION",
            "Report construction failed state validation.",
            validate_packet.validate_transition(current, candidate),
        )
        edges.append((str(current["phase"]), str(candidate["phase"])))
        current = candidate
    if current.get("phase") != "REVIEW_PENDING":
        raise ControllerError("INVALID_PHASE", "A report can be built only before review.")
    return current, edges


def _record_events(paths: RunPaths, events: Sequence[Mapping[str, object]]) -> None:
    """Persist diagnostics only after the authoritative state commit."""
    content = _read_input(paths.events, "controller events") if paths.events.exists() else ""
    for event in events:
        content += _canonical_json_bytes(dict(event)).decode("utf-8")
    write_text_atomic(paths.events, content)


def _record_events_best_effort(
    paths: RunPaths, events: Sequence[Mapping[str, object]]
) -> None:
    try:
        _record_events(paths, events)
    except (ControllerError, OSError):
        pass


def build_report(
    repository: Path,
    task_slug: str,
    local_evidence_path: Path,
) -> dict[str, object]:
    """Build a snapshot-bound implementation report from closed local evidence."""
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    with run_lock(paths.lock):
        _require_manual_recovery(paths)
        state, loaded_state_digest = _load_mutator_state(paths)
        if state.get("review_round", 0) >= _review_round_limit(state):
            raise ControllerError(
                "REVIEW_ROUND_LIMIT",
                "The maximum number of semantic review rounds has been consumed.",
            )
        if _outstanding_attempts(paths):
            raise ControllerError("OUTSTANDING_ATTEMPT", "An attempt is already outstanding.")
        if state.get("phase") not in {
            "REQUIREMENTS_FROZEN",
            "IMPLEMENTING",
            "LOCAL_VERIFICATION",
            "REVIEW_PENDING",
            "FINAL_VERIFICATION",
        }:
            raise ControllerError("INVALID_PHASE", "A report can be built only before review.")
        requirements = _active_requirements(paths, state)
        evidence = _load_local_evidence(local_evidence_path, requirements)
        snapshot = _capture_snapshot(paths, state)
        changed_files = _snapshot_changed_file_intents(snapshot, evidence)
        report = {
            "schema_version": SCHEMA_VERSION,
            "baseline_head": state["baseline_head"],
            "requirements_revision": state["active_requirements_revision"],
            "requirements_digest": state["active_requirements_digest"],
            "review_round": state["review_round"],
            "snapshot_digest": snapshot["snapshot_digest"],
            "tracked_diff_digest": snapshot["tracked_diff_digest"],
            "untracked_manifest_digest": snapshot["untracked_manifest_digest"],
            "changed_files": changed_files,
            "intent_summary": evidence["intent_summary"],
            "acceptance_evidence": evidence["acceptance_evidence"],
            "test_commands": evidence["test_commands"],
            "diff_evidence": evidence["diff_evidence"],
            "omissions": evidence["omissions"],
            "unresolved_risks_or_blockers": evidence["unresolved_risks_or_blockers"],
        }
        validate_model_bound_section(
            "implementation_report", _canonical_prompt_json(report)
        )
        if state.get("phase") == "FINAL_VERIFICATION":
            candidate = dict(state)
            candidate.update(
                phase="REVIEW_PENDING",
                latest_decision=None,
                required_actions=[],
                unresolved_finding_ids=[],
                blocker_fingerprints=[],
                active_review_packet_digest=None,
                reviewed_snapshot_digest=None,
            )
            phase_edges = [("FINAL_VERIFICATION", "REVIEW_PENDING")]
        else:
            candidate, phase_edges = _advance_report_phase(state)
        candidate.update(
            active_report_digest=validate_packet.canonical_digest(report),
            current_snapshot_digest=snapshot["snapshot_digest"],
        )
        if state.get("phase") == "FINAL_VERIFICATION":
            _raise_validation(
                "INVALID_TRANSITION",
                "Final verification report replacement failed state validation.",
                validate_packet.validate_transition(state, candidate),
            )
        context_errors = validate_packet.validate_report_context(
            report, requirements, candidate, snapshot
        )
        _raise_validation(
            "INVALID_REPORT", "Implementation report failed context validation.", context_errors
        )
        report_path = paths.run / "implementation-report.json"
        snapshot_path = paths.run / "snapshot.json"
        _commit_artifacts_then_state(
            paths,
            [(snapshot_path, snapshot), (report_path, report)],
            candidate,
            replaceable_artifacts=frozenset({snapshot_path, report_path}),
            expected_state_digest=loaded_state_digest,
        )
        _record_events_best_effort(
            paths,
            [
                *(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "event": "REPORT_PHASE_ADVANCED",
                        "from_phase": source,
                        "to_phase": target,
                    }
                    for source, target in phase_edges
                ),
                {
                    "schema_version": SCHEMA_VERSION,
                    "event": "REPORT_BUILT",
                    "report_digest": candidate["active_report_digest"],
                    "snapshot_digest": candidate["current_snapshot_digest"],
                },
            ],
        )
    return {
        "report_path": str(report_path),
        "snapshot_path": str(snapshot_path),
        "report_digest": candidate["active_report_digest"],
        "snapshot_digest": candidate["current_snapshot_digest"],
    }


def _active_report_context(
    paths: RunPaths,
    state: Mapping[str, object],
    *,
    prior_reviewed_report: bool = False,
    allow_final_verification: bool = False,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    requirements = _active_requirements(paths, state)
    report = load_json(paths.run / "implementation-report.json")
    snapshot = load_json(paths.run / "snapshot.json")
    validation_state = dict(state)
    if allow_final_verification and validation_state.get("phase") == "FINAL_VERIFICATION":
        validation_state["phase"] = "REVIEW_PENDING"
    if prior_reviewed_report:
        report_round = report.get("review_round")
        current_round = state.get("review_round")
        if (
            not isinstance(report_round, int)
            or isinstance(report_round, bool)
            or not isinstance(current_round, int)
            or isinstance(current_round, bool)
            or current_round != report_round + 1
        ):
            raise ControllerError(
                "INVALID_REPORT",
                "Evidence-only review requires the report from the immediately prior round.",
            )
        validation_state["review_round"] = report_round
    _raise_validation(
        "INVALID_REPORT", "Active implementation report failed context validation.",
        validate_packet.validate_report_context(
            report, requirements, validation_state, snapshot
        ),
    )
    return requirements, report, snapshot


def _require_unchanged_snapshot(
    paths: RunPaths,
    state: Mapping[str, object],
    bound_snapshot: Mapping[str, object],
) -> None:
    fresh_snapshot = _capture_snapshot(paths, state)
    if fresh_snapshot != bound_snapshot:
        raise ControllerError(
            "SNAPSHOT_CHANGED",
            "Review preparation requires an unchanged bound product snapshot.",
        )


def _active_prior_review(
    paths: RunPaths,
    state: Mapping[str, object],
    requirements: dict[str, object],
    report: dict[str, object],
) -> dict[str, object]:
    review = load_json(paths.run / "review.json")
    _raise_validation(
        "INVALID_REVIEW",
        "Persisted prior review payload is invalid.",
        validate_packet.validate_review(review, requirements, report),
    )
    review_digest = validate_packet.canonical_digest(review)
    if review_digest != state.get("active_review_packet_digest"):
        raise ControllerError(
            "INVALID_REVIEW",
            "Persisted prior review payload does not match trusted state.",
        )
    if review.get("reviewed_snapshot_digest") != state.get(
        "reviewed_snapshot_digest"
    ):
        raise ControllerError(
            "INVALID_REVIEW",
            "Persisted prior review snapshot does not match trusted state.",
        )
    return review


def _save_review_attempt_with_state(
    paths: RunPaths,
    attempt_number: int,
    expected: Mapping[str, object],
    prompt: str,
    state: dict[str, object],
    expected_state_digest: str,
) -> tuple[Path, Path]:
    turn_id = expected.get("turn_id")
    if not isinstance(turn_id, str):
        raise ControllerError("INVALID_EXPECTED_ATTEMPT", "Review attempt is invalid.")
    prompt_path = paths.run / "prompts" / f"{turn_id}-attempt-{attempt_number:02d}.md"
    expected_path = paths.run / f"expected-attempt-{attempt_number:02d}.json"
    _commit_artifacts_then_state(
        paths,
        [(prompt_path, prompt), (expected_path, dict(expected))],
        state,
        expected_state_digest=expected_state_digest,
    )
    return prompt_path, expected_path


def prepare_review(
    repository: Path,
    task_slug: str,
    supplemental_evidence_path: Path | None = None,
) -> dict[str, object]:
    """Persist a correlated review prompt without using Browser interactions."""
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    with run_lock(paths.lock):
        _require_manual_recovery(paths)
        state, loaded_state_digest = _load_mutator_state(paths)
        if state.get("review_round", 0) >= _review_round_limit(state):
            raise ControllerError(
                "REVIEW_ROUND_LIMIT",
                "The maximum number of semantic review rounds has been consumed.",
            )
        if _outstanding_attempts(paths):
            raise ControllerError("OUTSTANDING_ATTEMPT", "A review attempt is already outstanding.")
        evidence_only = supplemental_evidence_path is not None
        prior_review: dict[str, object] | None = None
        if evidence_only:
            if state.get("phase") != "LOCAL_VERIFICATION" or state.get("required_actions") != ["PROVIDE_EVIDENCE"]:
                raise ControllerError("INVALID_PHASE", "Evidence-only review requires only PROVIDE_EVIDENCE.")
            supplemental = _read_input(supplemental_evidence_path, "supplemental evidence")
            if not supplemental.strip():
                raise ControllerError("INVALID_SUPPLEMENTAL_EVIDENCE", "Supplemental evidence must not be empty.")
            candidate = dict(state)
            candidate["phase"] = "REVIEW_PENDING"
            requirements, report, snapshot = _active_report_context(
                paths, candidate, prior_reviewed_report=True
            )
            prior_review = _active_prior_review(
                paths, state, requirements, report
            )
            _raise_validation(
                "INVALID_TRANSITION",
                "Evidence-only review failed state validation.",
                validate_packet.validate_transition(state, candidate),
            )
            template = load_template(_prompt_contract_path(), "Evidence-only supplementation")
            values: dict[str, str | Template] = {
                "SNAPSHOT_DIGEST": str(snapshot["snapshot_digest"]),
                "REQUIREMENTS_JSON": _canonical_prompt_json(requirements),
                "PRIOR_REVIEW_JSON": _canonical_prompt_json(prior_review),
                "SUPPLEMENTAL_EVIDENCE": _bounded_model_text(
                    supplemental_evidence_path, supplemental
                ),
            }
        else:
            if state.get("phase") != "REVIEW_PENDING":
                raise ControllerError("INVALID_PHASE", "Review can be prepared only when pending.")
            requirements, report, snapshot = _active_report_context(paths, state)
            candidate = dict(state)
            template = load_template(_prompt_contract_path(), "Implementation review")
            values = {
                "REQUIREMENTS_JSON": _canonical_prompt_json(requirements),
                "REQUIREMENTS_DIGEST": str(state["active_requirements_digest"]),
                "IMPLEMENTATION_REPORT_JSON": _canonical_prompt_json(report),
                "SNAPSHOT_DIGEST": str(snapshot["snapshot_digest"]),
            }
        _require_unchanged_snapshot(paths, state, snapshot)
        shared = load_template(_prompt_contract_path(), "Shared envelope instruction")
        attempt_number = _attempt_number(paths)
        semantic_sequence = int(state["review_round"]) + 1
        previous_packet_digest = state.get("last_consumed_packet_digest")
        if not isinstance(previous_packet_digest, str):
            raise ControllerError("INVALID_STATE", "Review requires a trusted packet-chain head.")
        source_digest = validate_packet.canonical_digest(
            {
                "requirements_digest": state["active_requirements_digest"],
                "report_digest": state["active_report_digest"],
                "snapshot_digest": snapshot["snapshot_digest"],
                "prior_review_digest": (
                    state["active_review_packet_digest"] if evidence_only else None
                ),
                "supplemental_evidence": _normalize_text(supplemental) if evidence_only else None,
            }
        )
        expected = _expected_header(
            task_slug,
            "review",
            semantic_sequence,
            source_digest,
            previous_packet_digest,
            _derive_attempt_nonce(
                state, task_slug, "review", semantic_sequence, attempt_number
            ),
        )
        values.update(
            {
                "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REVIEW": shared,
                "PACKET_TYPE": "review",
                "RUN_ID": str(expected["run_id"]),
                "TURN_ID": str(expected["turn_id"]),
                "NONCE": str(expected["nonce"]),
                "IN_REPLY_TO_DIGEST": str(expected["in_reply_to"]),
                "PREVIOUS_PACKET_DIGEST_OR_NULL": previous_packet_digest,
            }
        )
        rendered = render_prompt(template, values)
        expected["prompt_digest"] = rendered["prompt_digest"]
        candidate["pending_review_expected_header_digest"] = (
            validate_packet.canonical_digest(expected)
        )
        prompt_path, expected_path = _save_review_attempt_with_state(
            paths,
            attempt_number,
            expected,
            rendered["prompt"],
            candidate,
            loaded_state_digest,
        )
    return {
        "prompt_path": str(prompt_path),
        "expected_header_path": str(expected_path),
        "prompt_digest": expected["prompt_digest"],
        "nonce": expected["nonce"],
        "turn_id": expected["turn_id"],
        "prepared_prompt_utf8_bytes": _utf8_size(rendered["prompt"]),
        "frozen_requirements_utf8_bytes": _utf8_size(
            _canonical_prompt_json(requirements)
        ),
        "dynamic_summary_utf8_bytes": _utf8_size(
            values.get("IMPLEMENTATION_REPORT_JSON", values.get("SUPPLEMENTAL_EVIDENCE", ""))  # type: ignore[arg-type]
        ),
        "model_bound_item_count": (
            len(_model_bound_report_items(report)) if not evidence_only else 1
        ),
    }


REQUIREMENTS_TARGETS = {
    "PLAN_READY": "REQUIREMENTS_FROZEN",
    "NEED_USER_INPUT": "USER_DECISION_REQUIRED",
    "BLOCK": "BLOCKED",
}


def observed_browser_errors(
    state: Mapping[str, object],
    observed_url: str,
    observed_model_label: str,
    allow_initial_binding: bool,
    observed_reasoning_label: str | None = None,
    observed_plan_label: str | None = None,
) -> list[str]:
    """Return deterministic identity-policy errors for an observed conversation."""
    errors: list[str] = []
    if not isinstance(observed_url, str) or not observed_url:
        errors.append("conversation URL is missing")
    if not isinstance(observed_model_label, str) or not observed_model_label:
        errors.append("model label is missing")
    policy = state.get("model_policy")
    requested = state.get("requested_model_label")
    if policy == "PRO_CLASS":
        if observed_model_label != validate_packet.PRO_CLASS_MODEL_LABEL:
            errors.append("observed model family does not satisfy the requested model policy")
        if observed_reasoning_label != validate_packet.PRO_CLASS_REASONING_LABEL:
            errors.append("observed reasoning level does not satisfy the requested model policy")
        if observed_plan_label not in validate_packet.PRO_CLASS_PLAN_LABELS:
            errors.append("observed ChatGPT plan does not satisfy the requested model policy")
    elif not isinstance(requested, str) or observed_model_label != requested:
        errors.append("observed model does not satisfy the requested model policy")

    bound_url = state.get("bound_conversation_url")
    bound_label = state.get("visible_model_label")
    bound_reasoning = state.get("visible_reasoning_label")
    bound_plan = state.get("visible_plan_label")
    if state.get("conversation_binding_state") == "CONVERSATION_BOUND":
        if observed_url != bound_url:
            errors.append("observed conversation URL does not match the bound conversation")
        if observed_model_label != bound_label:
            errors.append("observed model does not match the bound model")
        if observed_reasoning_label != bound_reasoning:
            errors.append("observed reasoning level does not match the bound reasoning level")
        if observed_plan_label != bound_plan:
            errors.append("observed ChatGPT plan does not match the bound plan")
    elif allow_initial_binding:
        parsed = urlparse(observed_url) if isinstance(observed_url, str) else None
        if (
            parsed is None
            or parsed.scheme != "https"
            or parsed.netloc != "chatgpt.com"
            or not parsed.path.startswith("/c/")
            or parsed.path == "/c/"
        ):
            errors.append("initial conversation URL must be an HTTPS chatgpt.com/c/ URL")
    else:
        errors.append("conversation is not bound")
    return errors


def consumed_chain_heads(state: Mapping[str, object]) -> set[str]:
    """Return only packet identities explicitly consumed by trusted state."""
    return {
        value
        for value in (
            state.get("last_consumed_packet_digest"),
            state.get("last_consumed_review_envelope_digest"),
        )
        if isinstance(value, str)
    }


def _requirements_context(
    envelope: dict[str, object],
    expected: dict[str, object],
    consumed: set[str],
    requirements: dict[str, object],
    approval_receipt: str | None = None,
) -> dict[str, object]:
    return {
        "envelope": envelope,
        "expected": expected,
        "consumed_digests": sorted(consumed),
        "requirements": requirements,
        "approval_receipt": approval_receipt,
    }


def _raise_validation(code: str, message: str, errors: Sequence[str]) -> None:
    if errors:
        raise ControllerError(code, message, errors)


def _requirements_revision_path(paths: RunPaths, revision: int) -> Path:
    return paths.run / f"requirements-revision-{revision:02d}.json"


def _run_relative_path(paths: RunPaths, path: Path) -> str:
    resolved = Path(path).resolve(strict=False)
    run = paths.run.resolve(strict=False)
    if not _is_contained(resolved, run) or resolved == run:
        raise ControllerError("UNSAFE_ARTIFACT_PATH", "Controller artifact path escapes the run directory.")
    return resolved.relative_to(run).as_posix()


def _manifest_run_path(paths: RunPaths, value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ControllerError("INVALID_TRANSACTION", "Transaction contains an invalid run path.")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        raise ControllerError("INVALID_TRANSACTION", "Transaction contains an unsafe run path.")
    resolved = Path(paths.run, *relative.parts).resolve(strict=False)
    if not _is_contained(resolved, paths.run.resolve(strict=False)):
        raise ControllerError("INVALID_TRANSACTION", "Transaction run path escapes the run directory.")
    return resolved


def _transaction_file(transaction: Path, value: object) -> Path:
    if (
        not isinstance(value, str)
        or PurePosixPath(value).name != value
        or not re.fullmatch(r"(?:artifact|backup)-[0-9]{2}\.bin|state\.next", value)
    ):
        raise ControllerError("INVALID_TRANSACTION", "Transaction contains an invalid staged path.")
    return transaction / value


def _file_digest(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise ControllerError("TRANSACTION_RECOVERY_FAILED", "Could not read transaction artifact.") from exc


def _cleanup_transaction_files(transaction: Path, allowed: set[str]) -> None:
    try:
        present = list(transaction.iterdir())
    except OSError as exc:
        raise ControllerError("TRANSACTION_RECOVERY_FAILED", "Could not inspect transaction.") from exc
    unexpected = [path.name for path in present if not path.is_file() or path.name not in allowed]
    if unexpected:
        raise ControllerError(
            "INVALID_TRANSACTION",
            "Transaction contains unexpected recovery artifacts.",
            unexpected,
        )
    try:
        manifest_path = transaction / "manifest.json"
        for path in sorted(
            (path for path in present if path != manifest_path),
            key=lambda path: path.name,
        ):
            path.unlink()
        if manifest_path in present:
            manifest_path.unlink()
        transaction.rmdir()
    except OSError as exc:
        raise ControllerError("TRANSACTION_RECOVERY_FAILED", "Could not clean transaction.") from exc


def _recover_transaction(paths: RunPaths, transaction: Path) -> None:
    manifest_path = transaction / "manifest.json"
    if not manifest_path.is_file():
        _cleanup_transaction_files(
            transaction,
            {
                path.name
                for path in transaction.iterdir()
                if path.is_file()
                and re.fullmatch(r"artifact-[0-9]{2}\.bin|state\.next", path.name)
            },
        )
        return
    manifest = load_json(manifest_path)
    if set(manifest) != {
        "schema_version",
        "operations",
        "attempt_rename",
        "old_state_digest",
        "new_state_digest",
    } or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ControllerError("INVALID_TRANSACTION", "Transaction recovery manifest is invalid.")
    operations = manifest.get("operations")
    if not isinstance(operations, list):
        raise ControllerError("INVALID_TRANSACTION", "Transaction operations are invalid.")
    parsed: list[tuple[Path, Path, Path | None, str, str | None]] = []
    allowed = {"manifest.json", "state.next"}
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict) or set(operation) != {
            "destination",
            "stage",
            "backup",
            "new_digest",
            "old_digest",
        }:
            raise ControllerError("INVALID_TRANSACTION", "Transaction operation is invalid.")
        destination = _manifest_run_path(paths, operation["destination"])
        stage = _transaction_file(transaction, operation["stage"])
        backup_value = operation["backup"]
        backup = None if backup_value is None else _transaction_file(transaction, backup_value)
        new_digest = operation["new_digest"]
        old_digest = operation["old_digest"]
        if not isinstance(new_digest, str) or DIGEST.fullmatch(new_digest) is None:
            raise ControllerError("INVALID_TRANSACTION", "Transaction new digest is invalid.")
        if old_digest is not None and (
            not isinstance(old_digest, str) or DIGEST.fullmatch(old_digest) is None
        ):
            raise ControllerError("INVALID_TRANSACTION", "Transaction old digest is invalid.")
        if (backup is None) != (old_digest is None):
            raise ControllerError("INVALID_TRANSACTION", "Transaction backup provenance is invalid.")
        allowed.add(stage.name)
        if backup is not None:
            allowed.add(backup.name)
        parsed.append((destination, stage, backup, new_digest, old_digest))

    attempt = manifest.get("attempt_rename")
    attempt_paths: tuple[Path, Path, str] | None = None
    if attempt is not None:
        if not isinstance(attempt, dict) or set(attempt) != {"source", "destination", "digest"}:
            raise ControllerError("INVALID_TRANSACTION", "Attempt rename is invalid.")
        attempt_digest = attempt["digest"]
        if not isinstance(attempt_digest, str) or DIGEST.fullmatch(attempt_digest) is None:
            raise ControllerError("INVALID_TRANSACTION", "Attempt rename digest is invalid.")
        attempt_paths = (
            _manifest_run_path(paths, attempt["source"]),
            _manifest_run_path(paths, attempt["destination"]),
            attempt_digest,
        )
    old_state_digest = manifest.get("old_state_digest")
    new_state_digest = manifest.get("new_state_digest")
    if any(
        not isinstance(value, str) or DIGEST.fullmatch(value) is None
        for value in (old_state_digest, new_state_digest)
    ):
        raise ControllerError("INVALID_TRANSACTION", "Transaction state digests are invalid.")
    state_digest = _file_digest(paths.state)
    if state_digest == new_state_digest:
        for destination, _, _, new_digest, _ in parsed:
            if not destination.is_file() or _file_digest(destination) != new_digest:
                raise ControllerError(
                    "TRANSACTION_RECOVERY_FAILED",
                    "Committed transaction is missing a published artifact.",
                )
        if attempt_paths is not None:
            source, destination, attempt_digest = attempt_paths
            if (
                source.exists()
                or not destination.is_file()
                or _file_digest(destination) != attempt_digest
            ):
                raise ControllerError(
                    "TRANSACTION_RECOVERY_FAILED",
                    "Committed transaction has an incomplete attempt rename.",
                )
        _cleanup_transaction_files(transaction, allowed)
        return
    if state_digest != old_state_digest:
        raise ControllerError(
            "TRANSACTION_RECOVERY_FAILED",
            "Transaction state matches neither committed nor rollback provenance.",
        )

    if attempt_paths is not None:
        source, destination, attempt_digest = attempt_paths
        if destination.exists() and not source.exists():
            if _file_digest(destination) != attempt_digest:
                raise ControllerError(
                    "TRANSACTION_RECOVERY_FAILED",
                    "Foreign-modified attempt blocks transaction rollback.",
                )
            os.replace(destination, source)
        elif destination.exists() and source.exists():
            raise ControllerError(
                "TRANSACTION_RECOVERY_FAILED", "Attempt rename has two live copies."
            )
        elif not source.exists():
            raise ControllerError(
                "TRANSACTION_RECOVERY_FAILED",
                "Attempt rename provenance is missing.",
            )
    for destination, stage, backup, new_digest, old_digest in reversed(parsed):
        if backup is None:
            if stage.exists() and not destination.exists():
                continue
            if not destination.exists() or _file_digest(destination) != new_digest:
                raise ControllerError(
                    "TRANSACTION_RECOVERY_FAILED",
                    "Unowned artifact blocks transaction rollback.",
                )
            destination.unlink()
            continue
        if backup.exists():
            if not destination.exists() or _file_digest(destination) != new_digest:
                raise ControllerError(
                    "TRANSACTION_RECOVERY_FAILED",
                    "Replaceable artifact changed during transaction rollback.",
                )
            destination.unlink()
            os.replace(backup, destination)
        if not destination.is_file() or _file_digest(destination) != old_digest:
            raise ControllerError(
                "TRANSACTION_RECOVERY_FAILED",
                "Replaceable artifact backup could not be restored.",
            )
    _cleanup_transaction_files(transaction, allowed)


def _reconcile_incomplete_transactions(paths: RunPaths) -> None:
    if not paths.transactions.is_dir():
        return
    for transaction in sorted(paths.transactions.iterdir()):
        if transaction.is_dir() and transaction.name.startswith("consume-"):
            _recover_transaction(paths, transaction)


def _require_manual_recovery(paths: RunPaths) -> None:
    """Keep interrupted transactions visible; normal commands never repair them."""
    transactions = _orphan_transaction_paths(paths)
    if transactions:
        raise ControllerError(
            "RECOVERY_REQUIRED",
            "Manual recovery is required: inspect interrupted transactions and escalate before mutation.",
            _recovery_details(paths, transactions),
        )


def _orphan_transaction_paths(paths: RunPaths) -> list[Path]:
    if not paths.transactions.is_dir():
        return []
    return sorted(
        (path for path in paths.transactions.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )


def _recovery_details(paths: RunPaths, transactions: Sequence[Path]) -> list[str]:
    return [
        *(f"transaction_path:{path}" for path in transactions),
        (
            "status_command:python skills/gpt-pro-codex-loop/scripts/gpc_loop.py "
            f"status --repo {paths.repository} --task {paths.task_slug}"
        ),
        (
            "validator_command:python skills/gpt-pro-codex-loop/scripts/validate_packet.py "
            "transition PREVIOUS_STATE.json CURRENT_STATE.json --requirements-context REQUIREMENTS_CONTEXT.json"
        ),
        "preserve_artifacts:true",
        "user_escalation_required:true",
    ]


def _require_state_digest(paths: RunPaths, expected: str) -> None:
    if _file_digest(paths.state) != expected:
        raise ControllerError(
            "STATE_CHANGED",
            "Trusted state changed while this command was running.",
        )


def _rollback_uncommitted_transaction(paths: RunPaths, transaction: Path) -> None:
    """Undo only this command's published artifacts after an external state race."""
    manifest = load_json(transaction / "manifest.json")
    operations = manifest.get("operations")
    if not isinstance(operations, list):
        raise ControllerError("TRANSACTION_RECOVERY_FAILED", "Could not roll back transaction artifacts.")
    attempt = manifest.get("attempt_rename")
    if isinstance(attempt, dict):
        source = _manifest_run_path(paths, attempt.get("source"))
        destination = _manifest_run_path(paths, attempt.get("destination"))
        attempt_digest = attempt.get("digest")
        if (
            destination.exists()
            and not source.exists()
            and isinstance(attempt_digest, str)
            and _file_digest(destination) == attempt_digest
        ):
            os.replace(destination, source)
        elif destination.exists() or not source.exists():
            raise ControllerError(
                "RECOVERY_REQUIRED",
                "Manual recovery is required because a foreign-modified attempt blocks safe rollback.",
                [str(transaction)],
            )
    for operation in reversed(operations):
        if not isinstance(operation, dict):
            raise ControllerError("TRANSACTION_RECOVERY_FAILED", "Could not roll back transaction artifacts.")
        destination = _manifest_run_path(paths, operation.get("destination"))
        backup_name = operation.get("backup")
        if backup_name is None:
            if destination.exists() and _file_digest(destination) == operation.get("new_digest"):
                destination.unlink()
            else:
                raise ControllerError(
                    "RECOVERY_REQUIRED",
                    "Manual recovery is required because a foreign-modified artifact blocks safe rollback.",
                    [str(transaction), str(destination)],
                )
            continue
        backup = _transaction_file(transaction, backup_name)
        if backup.exists():
            if (
                not destination.exists()
                or _file_digest(destination) != operation.get("new_digest")
            ):
                raise ControllerError(
                    "RECOVERY_REQUIRED",
                    "Manual recovery is required because a foreign-modified artifact blocks safe rollback.",
                    [str(transaction), str(destination)],
                )
            destination.unlink()
            os.replace(backup, destination)
    _cleanup_transaction_files(
        transaction,
        {path.name for path in transaction.iterdir() if path.is_file()},
    )


def _commit_artifacts_then_state(
    paths: RunPaths,
    artifacts: Sequence[tuple[Path, str | dict[str, object]]],
    state: dict[str, object],
    consumed_attempt: Path | None = None,
    replaceable_artifacts: frozenset[Path] = frozenset(),
    *,
    expected_state_digest: str,
) -> None:
    """Publish a recoverable artifact transaction with trusted state last."""
    if not isinstance(expected_state_digest, str) or DIGEST.fullmatch(expected_state_digest) is None:
        raise ControllerError("INVALID_STATE_DIGEST", "Loaded state digest is invalid.")
    transaction = paths.transactions / f"consume-{os.getpid()}-{time.time_ns()}"
    transaction.mkdir()
    operations: list[dict[str, object]] = []
    publication_started = False
    try:
        for index, (destination, value) in enumerate(artifacts):
            destination_relative = _run_relative_path(paths, destination)
            if destination.exists() and destination not in replaceable_artifacts:
                raise ControllerError("ARTIFACT_EXISTS", "Controller artifact already exists.")
            destination.parent.mkdir(exist_ok=True)
            stage = transaction / f"artifact-{index:02d}.bin"
            if isinstance(value, str):
                write_text_atomic(stage, value)
            else:
                write_json_atomic(stage, value)
            existed = destination.is_file()
            backup = f"backup-{index:02d}.bin" if existed else None
            operations.append(
                {
                    "destination": destination_relative,
                    "stage": stage.name,
                    "backup": backup,
                    "new_digest": _file_digest(stage),
                    "old_digest": _file_digest(destination) if existed else None,
                }
            )
        state_stage = transaction / "state.next"
        write_json_atomic(state_stage, state)
        attempt_rename = None
        if consumed_attempt is not None:
            source_relative = _run_relative_path(paths, consumed_attempt)
            consumed_name = consumed_attempt.name.replace("expected-", "consumed-")
            consumed_destination = paths.run / consumed_name
            destination_relative = _run_relative_path(paths, consumed_destination)
            if consumed_destination.exists():
                raise ControllerError("ARTIFACT_EXISTS", "Consumed attempt receipt already exists.")
            attempt_rename = {
                "source": source_relative,
                "destination": destination_relative,
                "digest": _file_digest(consumed_attempt),
            }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "operations": operations,
            "attempt_rename": attempt_rename,
            "old_state_digest": expected_state_digest,
            "new_state_digest": _file_digest(state_stage),
        }
        write_json_atomic(transaction / "manifest.json", manifest)
        _require_state_digest(paths, expected_state_digest)
        publication_started = True
        for operation in operations:
            destination = _manifest_run_path(paths, operation["destination"])
            stage = _transaction_file(transaction, operation["stage"])
            if operation["backup"] is not None:
                backup = _transaction_file(transaction, operation["backup"])
                os.replace(destination, backup)
            os.replace(stage, destination)
        if attempt_rename is not None:
            os.replace(
                _manifest_run_path(paths, attempt_rename["source"]),
                _manifest_run_path(paths, attempt_rename["destination"]),
            )
        _require_state_digest(paths, expected_state_digest)
        os.replace(state_stage, paths.state)
    except OSError as exc:
        _recover_transaction(paths, transaction)
        raise ControllerError("WRITE_FAILED", "Could not commit controller acceptance artifacts.") from exc
    except ControllerError as exc:
        if exc.code == "STATE_CHANGED":
            if publication_started:
                _rollback_uncommitted_transaction(paths, transaction)
            else:
                _cleanup_transaction_files(
                    transaction,
                    {path.name for path in transaction.iterdir() if path.is_file()},
                )
        else:
            _recover_transaction(paths, transaction)
        raise
    _recover_transaction(paths, transaction)


def accept_requirements(
    repository: Path,
    task_slug: str,
    raw_response_path: Path,
    observed_conversation_url: str,
    observed_model_label: str,
    observed_reasoning_label: str | None = None,
    observed_plan_label: str | None = None,
) -> dict[str, object]:
    """Validate, consume, and route one correlated requirements response."""
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    with run_lock(paths.lock):
        _require_manual_recovery(paths)
        state, loaded_state_digest = _load_mutator_state(paths)
        if state.get("phase") != "REQUIREMENTS_PENDING":
            raise ControllerError("INVALID_PHASE", "Requirements can be accepted only when pending.")
        browser_errors = observed_browser_errors(
            state,
            observed_conversation_url,
            observed_model_label,
            allow_initial_binding=True,
            observed_reasoning_label=observed_reasoning_label,
            observed_plan_label=observed_plan_label,
        )
        _raise_validation(
            "BROWSER_IDENTITY_MISMATCH",
            "Observed browser or model identity is invalid.",
            browser_errors,
        )
        attempts = _outstanding_attempts(paths)
        if len(attempts) != 1:
            raise ControllerError("OUTSTANDING_ATTEMPT_REQUIRED", "Exactly one outstanding attempt is required.")
        expected_path = paths.run / str(attempts[0]["name"])
        expected = attempts[0]["expected_header"]
        attempt_match = ATTEMPT_NAME.fullmatch(expected_path.name)
        if attempt_match is None:
            raise ControllerError(
                "INVALID_EXPECTED_ATTEMPT",
                "Outstanding requirements attempt name is invalid.",
            )
        active_revision = state.get("active_requirements_revision")
        semantic_sequence = (
            1
            if active_revision is None
            else active_revision + 1
            if isinstance(active_revision, int) and not isinstance(active_revision, bool)
            else -1
        )
        if not _valid_expected_header(
            expected,
            task_slug=task_slug,
            packet_type="requirements",
            semantic_sequence=semantic_sequence,
            expected_nonce=_derive_attempt_nonce(
                state,
                task_slug,
                "requirements",
                semantic_sequence,
                int(attempt_match.group(1)),
            ),
        ):
            raise ControllerError("INVALID_EXPECTED_ATTEMPT", "Outstanding requirements attempt is invalid.")
        if (
            validate_packet.canonical_digest(expected)
            != state.get("pending_requirements_expected_header_digest")
        ):
            raise ControllerError("INVALID_EXPECTED_ATTEMPT", "Outstanding requirements attempt is invalid.")
        raw = _read_input(raw_response_path, "requirements response")
        try:
            envelope = validate_packet.extract_single_json_object(raw)
        except ValueError as exc:
            raise ControllerError("INVALID_RESPONSE", "Requirements response is not one strict JSON envelope.") from exc
        transport_errors = validate_packet.validate_transport_envelope(
            envelope, expected, consumed_chain_heads(state)
        )
        _raise_validation("INVALID_RESPONSE", "Requirements response envelope is invalid.", transport_errors)
        requirements = envelope.get("payload")
        if not isinstance(requirements, dict):
            raise ControllerError("INVALID_RESPONSE", "Requirements response payload is invalid.")
        previous_requirements = None
        if state.get("active_requirements_digest") is not None:
            previous_requirements = load_json(paths.run / "requirements.json")
        requirements_errors = validate_packet.validate_requirements(
            requirements, previous_requirements
        )
        _raise_validation("INVALID_RESPONSE", "Requirements response payload is invalid.", requirements_errors)
        validate_model_bound_section("requirements", _canonical_prompt_json(requirements))
        decision = requirements["decision"]
        target = REQUIREMENTS_TARGETS.get(decision)
        if target is None:
            raise ControllerError("INVALID_RESPONSE", "Requirements response has an invalid decision.")

        envelope_digest = validate_packet.canonical_digest(envelope)
        requirements_digest = validate_packet.canonical_digest(requirements)
        staged_previous = dict(state)
        staged_previous["pending_requirements_envelope_digest"] = envelope_digest
        is_revision = state.get("active_requirements_digest") is not None
        if is_revision or decision == "NEED_USER_INPUT":
            staged_previous.update(
                pending_requirements_revision=requirements["requirements_revision"],
                pending_requirements_digest=requirements_digest,
                pending_supersedes_digest=requirements["supersedes_digest"],
                **{
                    field: requirements[field]
                    for field in validate_packet.MATERIAL_REVISION_FLAGS
                },
            )
        candidate = dict(staged_previous)
        candidate.update(
            phase=target,
            latest_requirements_decision=decision,
            pending_requirements_envelope_digest=None,
            pending_requirements_expected_header_digest=None,
            last_consumed_packet_digest=envelope_digest,
        )
        if state.get("conversation_binding_state") == "CONVERSATION_UNBOUND":
            candidate.update(
                conversation_binding_state="CONVERSATION_BOUND",
                bound_conversation_url=observed_conversation_url,
                visible_model_label=observed_model_label,
                visible_reasoning_label=observed_reasoning_label,
                visible_plan_label=observed_plan_label,
            )
            staged_previous.update(
                conversation_binding_state="CONVERSATION_BOUND",
                bound_conversation_url=observed_conversation_url,
                visible_model_label=observed_model_label,
                visible_reasoning_label=observed_reasoning_label,
                visible_plan_label=observed_plan_label,
            )
        if target in {"USER_DECISION_REQUIRED", "BLOCKED"}:
            candidate.update(
                stop_origin_phase="REQUIREMENTS_PENDING",
                stop_origin_category=(
                    "REQUIREMENTS_NEED_USER_INPUT"
                    if decision == "NEED_USER_INPUT"
                    else "REQUIREMENTS_BLOCK"
                ),
                stop_reason=requirements["change_reason"],
                stop_sequence=state["stop_sequence"] + 1,
            )
        if target == "BLOCKED" and is_revision:
            candidate.update(
                pending_requirements_revision=None,
                pending_requirements_digest=None,
                pending_supersedes_digest=None,
                pending_approval_sequence=None,
                pending_approved_requirements_digest=None,
                pending_user_approval_evidence=None,
                **{field: False for field in validate_packet.MATERIAL_REVISION_FLAGS},
            )
        if target == "REQUIREMENTS_FROZEN":
            candidate.update(
                active_requirements_revision=requirements["requirements_revision"],
                active_requirements_digest=requirements_digest,
                pending_requirements_revision=None,
                pending_requirements_digest=None,
                pending_supersedes_digest=None,
                pending_approval_sequence=None,
                pending_approved_requirements_digest=None,
                pending_user_approval_evidence=None,
                **{field: False for field in validate_packet.MATERIAL_REVISION_FLAGS},
            )
        context = _requirements_context(
            envelope, expected, consumed_chain_heads(state), requirements
        )
        transition_errors = validate_packet.validate_transition(
            staged_previous, candidate, requirements_context=context
        )
        _raise_validation("INVALID_TRANSITION", "Requirements acceptance failed state validation.", transition_errors)
        revision = requirements["requirements_revision"]
        trusted_turn_id = f"requirements-{semantic_sequence:02d}"
        artifacts: list[tuple[Path, str | dict[str, object]]] = [
            (paths.run / "responses" / f"{trusted_turn_id}.raw.md", raw),
            (paths.run / f"envelope-{revision:02d}.json", envelope),
            (_requirements_revision_path(paths, revision), requirements),
        ]
        replaceable = (
            {paths.run / "requirements.json"}
            if target == "REQUIREMENTS_FROZEN"
            else set()
        )
        if target == "REQUIREMENTS_FROZEN":
            artifacts.append((paths.run / "requirements.json", requirements))
            receipt_path = paths.run / "governance-receipt-requirements.json"
            if _governance_provenance_complete(candidate):
                requirements_receipt = _governance_receipt(
                    paths,
                    candidate,
                    "requirements",
                    input_digest=validate_packet.canonical_digest(expected),
                    output_digest=requirements_digest,
                    requirements_digest=sha256_bytes(
                        _canonical_json_bytes(requirements)
                    ),
                    transaction_id=(
                        f"gpc-loop-{task_slug}:requirements-{revision:02d}"
                    ),
                    snapshot_digest=None,
                    claims={},
                    issued_at_unix=int(time.time()),
                )
                artifacts.extend(
                    _requirements_receipt_artifacts(paths, requirements_receipt)
                )
                if receipt_path.exists():
                    replaceable.add(receipt_path)
        _commit_artifacts_then_state(
            paths,
            artifacts,
            candidate,
            expected_path,
            frozenset(replaceable),
            expected_state_digest=loaded_state_digest,
        )
        _record_events_best_effort(paths, [{
            "schema_version": SCHEMA_VERSION,
            "event": "REQUIREMENTS_ACCEPTED",
            "requirements_digest": requirements_digest,
            "envelope_digest": envelope_digest,
            "decision": decision,
            "target_phase": target,
        }])
    return status_run(paths.repository, task_slug)


def review_target(decision: str, actions: Sequence[str]) -> str:
    """Route a validated review decision without authorizing extra work."""
    action_set = set(actions)
    if decision == "PASS":
        return "FINAL_VERIFICATION"
    if decision == "BLOCK" or "USER_DECISION" in action_set:
        return "USER_DECISION_REQUIRED"
    if "REQUIREMENTS_REVISION" in action_set:
        return "REQUIREMENTS_PENDING"
    if action_set & {"CODE_CHANGE", "TEST_CHANGE"}:
        return "IMPLEMENTING"
    if action_set == {"PROVIDE_EVIDENCE"}:
        return "LOCAL_VERIFICATION"
    raise ControllerError("INVALID_REVIEW_ROUTE", "Review has no valid route.")


def _review_context(
    envelope: dict[str, object],
    expected: dict[str, object],
    consumed: set[str],
    requirements: dict[str, object],
    report: dict[str, object],
    snapshot: dict[str, object],
) -> dict[str, object]:
    return {
        "envelope": envelope,
        "expected": expected,
        "consumed_digests": sorted(consumed),
        "requirements": requirements,
        "report": report,
        "snapshot": snapshot,
    }


def _review_stop_provenance(
    state: Mapping[str, object],
    decision: str,
    actions: Sequence[str],
    reason: object,
) -> dict[str, object]:
    if decision != "BLOCK" and "USER_DECISION" not in set(actions):
        return {}
    if not isinstance(reason, str) or not reason.strip():
        raise ControllerError("INVALID_RESPONSE", "Review stop requires a non-empty instruction.")
    return {
        "stop_origin_phase": "REVIEW_PENDING",
        "stop_origin_category": (
            "REVIEW_BLOCK" if decision == "BLOCK" else "REVIEW_USER_DECISION"
        ),
        "stop_reason": reason,
        "stop_sequence": state["stop_sequence"] + 1,
    }


def _terminal_review_stop_provenance(
    state: Mapping[str, object],
    category: str | None,
) -> dict[str, object]:
    if category is None:
        return {}
    reasons = {
        "REVIEW_REPEATED_BLOCKER": (
            "A blocker persisted across two consecutive valid review rounds."
        ),
        "REVIEW_ROUND_LIMIT": (
            "The maximum number of semantic review rounds was consumed."
        ),
    }
    return {
        "stop_origin_phase": "REVIEW_PENDING",
        "stop_origin_category": category,
        "stop_reason": reasons[category],
        "stop_sequence": state["stop_sequence"] + 1,
    }


def _is_evidence_only_review(
    paths: RunPaths,
    state: Mapping[str, object],
) -> bool:
    review_round = state.get("review_round")
    if (
        not isinstance(review_round, int)
        or isinstance(review_round, bool)
        or review_round < 1
        or state.get("latest_decision") != "CHANGES_REQUESTED"
        or state.get("required_actions") != ["PROVIDE_EVIDENCE"]
        or not isinstance(state.get("active_review_packet_digest"), str)
    ):
        return False
    report = load_json(paths.run / "implementation-report.json")
    return (
        report.get("review_round") == review_round - 1
        and validate_packet.canonical_digest(report)
        == state.get("active_report_digest")
    )


def accept_review(
    repository: Path,
    task_slug: str,
    raw_response_path: Path,
    observed_conversation_url: str,
    observed_model_label: str,
    observed_reasoning_label: str | None = None,
    observed_plan_label: str | None = None,
) -> dict[str, object]:
    """Validate, consume, and deterministically route one review response."""
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    with run_lock(paths.lock):
        _require_manual_recovery(paths)
        state, loaded_state_digest = _load_mutator_state(paths)
        if state.get("phase") != "REVIEW_PENDING":
            raise ControllerError("INVALID_PHASE", "Review can be accepted only when pending.")
        _raise_validation(
            "BROWSER_IDENTITY_MISMATCH",
            "Observed browser or model identity is invalid.",
            observed_browser_errors(
                state,
                observed_conversation_url,
                observed_model_label,
                allow_initial_binding=False,
                observed_reasoning_label=observed_reasoning_label,
                observed_plan_label=observed_plan_label,
            ),
        )
        attempts = _outstanding_attempts(paths)
        if len(attempts) != 1:
            raise ControllerError("OUTSTANDING_ATTEMPT_REQUIRED", "Exactly one outstanding attempt is required.")
        expected_path = paths.run / str(attempts[0]["name"])
        expected = attempts[0]["expected_header"]
        match = ATTEMPT_NAME.fullmatch(expected_path.name)
        review_round = state.get("review_round")
        if (
            match is None
            or not isinstance(review_round, int)
            or isinstance(review_round, bool)
            or not _valid_expected_header(
                expected,
                task_slug=task_slug,
                packet_type="review",
                semantic_sequence=review_round + 1,
                expected_nonce=_derive_attempt_nonce(
                    state,
                    task_slug,
                    "review",
                    review_round + 1,
                    int(match.group(1)) if match is not None else -1,
                ),
            )
        ):
            raise ControllerError("INVALID_EXPECTED_ATTEMPT", "Outstanding review attempt is invalid.")
        if (
            validate_packet.canonical_digest(expected)
            != state.get("pending_review_expected_header_digest")
        ):
            raise ControllerError(
                "INVALID_EXPECTED_ATTEMPT",
                "Outstanding review attempt is invalid.",
            )
        raw = _read_input(raw_response_path, "review response")
        try:
            envelope = validate_packet.extract_single_json_object(raw)
        except ValueError as exc:
            raise ControllerError("INVALID_RESPONSE", "Review response is not one strict JSON envelope.") from exc
        consumed = consumed_chain_heads(state)
        _raise_validation(
            "INVALID_RESPONSE",
            "Review response envelope is invalid.",
            validate_packet.validate_transport_envelope(envelope, expected, consumed),
        )
        review = envelope.get("payload")
        if not isinstance(review, dict):
            raise ControllerError("INVALID_RESPONSE", "Review response payload is invalid.")
        evidence_only = _is_evidence_only_review(paths, state)
        requirements, report, snapshot = _active_report_context(
            paths,
            state,
            prior_reviewed_report=evidence_only,
        )
        if evidence_only:
            _active_prior_review(paths, state, requirements, report)
        _raise_validation(
            "INVALID_RESPONSE",
            "Review response payload is invalid.",
            validate_packet.validate_review(review, requirements, report),
        )
        actions = sorted(
            {
                finding["required_action"]
                for finding in review["findings"]
                if isinstance(finding, dict) and isinstance(finding.get("required_action"), str)
            }
        )
        finding_ids = sorted(
            {
                finding["id"]
                for finding in review["findings"]
                if isinstance(finding, dict) and isinstance(finding.get("id"), str)
            }
        )
        fingerprints = sorted(
            {
                fingerprint
                for finding in review["findings"]
                if isinstance(finding, dict)
                for fingerprint in (
                    validate_packet.derive_root_cause_fingerprint(finding),
                    validate_packet.derive_root_cause_route_fingerprint(finding),
                )
            }
        )
        decision = review["decision"]
        if not isinstance(decision, str):
            raise ControllerError("INVALID_RESPONSE", "Review response decision is invalid.")
        target = review_target(decision, actions)
        envelope_digest = validate_packet.canonical_digest(envelope)
        review_digest = validate_packet.canonical_digest(review)
        staged = dict(state)
        staged.update(
            pending_review_envelope_digest=envelope_digest,
            active_review_packet_digest=review_digest,
            reviewed_snapshot_digest=review["reviewed_snapshot_digest"],
            latest_decision=decision,
            required_actions=actions,
            unresolved_finding_ids=finding_ids,
            blocker_fingerprints=fingerprints,
        )
        context = _review_context(
            envelope, expected, consumed, requirements, report, snapshot
        )
        review_context_state = dict(staged)
        if evidence_only:
            review_context_state["review_round"] = review_round - 1
        _raise_validation(
            "INVALID_REVIEW_CONTEXT",
            "Review response failed context validation.",
            validate_packet.validate_review_context(
                envelope, requirements, report, review_context_state, snapshot
            ),
        )
        transition_previous = dict(staged)
        transition_previous.update(
            unresolved_finding_ids=state["unresolved_finding_ids"],
            blocker_fingerprints=state["blocker_fingerprints"],
        )
        repeated_blocker = review_round >= 1 and (
            set(state["unresolved_finding_ids"]) & set(finding_ids)
            or set(state["blocker_fingerprints"]) & set(fingerprints)
        )
        terminal_category = (
            "REVIEW_REPEATED_BLOCKER"
            if repeated_blocker
            else (
                "REVIEW_ROUND_LIMIT"
                if decision == "CHANGES_REQUESTED"
                and (
                    validate_packet.review_policy(state) == "FINAL_ONLY"
                    or review_round + 1 >= _review_round_limit(state)
                )
                else None
            )
        )
        if terminal_category is not None:
            target = "BLOCKED"
        candidate = dict(staged)
        candidate.update(
            phase=target,
            review_round=review_round + 1,
            pending_review_envelope_digest=None,
            pending_review_expected_header_digest=None,
            last_consumed_packet_digest=envelope_digest,
            last_consumed_review_envelope_digest=envelope_digest,
            **_review_stop_provenance(
                state, decision, actions, review.get("next_instruction")
            ),
            **_terminal_review_stop_provenance(state, terminal_category),
        )
        _raise_validation(
            "INVALID_TRANSITION",
            "Review acceptance failed state validation.",
            validate_packet.validate_transition(
                transition_previous, candidate, review_context=context
            ),
        )
        turn_id = expected.get("turn_id")
        if not isinstance(turn_id, str):
            raise ControllerError("INVALID_EXPECTED_ATTEMPT", "Outstanding review attempt is invalid.")
        artifacts: list[tuple[Path, str | dict[str, object]]] = [
            (paths.run / "responses" / f"{turn_id}.raw.md", raw),
            (paths.run / f"review-envelope-{review_round + 1:02d}.json", envelope),
            (paths.run / "review.json", review),
        ]
        if decision == "PASS" and _governance_provenance_complete(candidate):
            artifacts.append(
                (
                    paths.run / "governance-receipt-review.json",
                    _governance_receipt(
                        paths,
                        candidate,
                        "semantic_review",
                        input_digest=str(state["active_report_digest"]),
                        output_digest=review_digest,
                        requirements_digest=sha256_bytes(
                            _active_requirements_artifact(paths, state)[1]
                        ),
                        transaction_id=f"gpc-loop-{task_slug}:{turn_id}",
                        snapshot_digest=review["reviewed_snapshot_digest"],
                        claims=_review_receipt_claims(requirements, review_digest),
                        issued_at_unix=int(time.time()),
                    ),
                )
            )
        _commit_artifacts_then_state(
            paths,
            artifacts,
            candidate,
            expected_path,
            frozenset({paths.run / "review.json"}),
            expected_state_digest=loaded_state_digest,
        )
        _record_events_best_effort(paths, [{
            "schema_version": SCHEMA_VERSION,
            "event": "REVIEW_ACCEPTED",
            "review_digest": review_digest,
            "envelope_digest": envelope_digest,
            "decision": decision,
            "target_phase": target,
        }])
    return status_run(paths.repository, task_slug)


def _receipt_path(paths: RunPaths, receipt_type: str) -> Path:
    if receipt_type not in GOVERNANCE_RECEIPT_TYPES:
        raise ControllerError(
            "INVALID_RECEIPT_TYPE",
            "Governance receipt type must be requirements, review, or final.",
        )
    return paths.run / f"governance-receipt-{receipt_type}.json"


def _requirements_receipt_history_path(
    paths: RunPaths, receipt: Mapping[str, object]
) -> Path:
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise ControllerError(
            "INVALID_GOVERNANCE_RECEIPT", "Governance receipt ID is invalid."
        )
    return (
        paths.run
        / GOVERNANCE_RECEIPT_HISTORY_DIRECTORY
        / f"requirements-{receipt_id}.json"
    )


def _requirements_receipt_artifacts(
    paths: RunPaths, receipt: dict[str, object]
) -> list[tuple[Path, dict[str, object]]]:
    """Return current plus append-only history publication for one issuance."""
    history = _requirements_receipt_history_path(paths, receipt)
    expected = _canonical_json_bytes(receipt)
    if history.exists():
        try:
            actual = history.read_bytes()
        except OSError as exc:
            raise ControllerError(
                "GOVERNANCE_RECEIPT_HISTORY_COLLISION",
                "Could not verify immutable governance receipt history.",
            ) from exc
        if actual != expected:
            raise ControllerError(
                "GOVERNANCE_RECEIPT_HISTORY_COLLISION",
                "Immutable governance receipt history collides with different bytes.",
            )
        return [(paths.run / "governance-receipt-requirements.json", receipt)]
    return [
        (paths.run / "governance-receipt-requirements.json", receipt),
        (history, receipt),
    ]


def _requirements_receipt_input(
    paths: RunPaths,
    state: Mapping[str, object],
    requirements: Mapping[str, object],
) -> tuple[str, str]:
    revision = state.get("active_requirements_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ControllerError("INVALID_STATE", "Active requirements revision is invalid.")
    envelope = load_json(paths.run / f"envelope-{revision:02d}.json")
    if envelope.get("payload") != requirements:
        raise ControllerError(
            "INVALID_STATE", "Requirements envelope does not match active requirements."
        )
    if requirements.get("decision") == "NEED_USER_INPUT":
        stop_sequence = state.get("resolution_stop_sequence")
        if not isinstance(stop_sequence, int) or isinstance(stop_sequence, bool):
            raise ControllerError(
                "INVALID_STATE", "Approved requirements lack stop provenance."
            )
        return (
            validate_packet.canonical_digest(envelope),
            f"gpc-loop-{paths.task_slug}:approval-stop-{stop_sequence:02d}",
        )
    expected = {field: envelope.get(field) for field in EXPECTED_HEADER_FIELDS}
    return (
        validate_packet.canonical_digest(expected),
        f"gpc-loop-{paths.task_slug}:requirements-{revision:02d}",
    )


def _review_receipt_claims(
    requirements: Mapping[str, object], review_digest: str
) -> dict[str, object]:
    review_id = "REV-GPC-" + review_digest[7:19].upper()
    identifiers = sorted(
        item["id"]
        for item in requirements.get("requirements", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    return {
        "edges": [
            {"edge": "reviews", "source_id": review_id, "target_id": identifier}
            for identifier in identifiers
        ],
        "findings": [],
        "review_id": review_id,
        "root_cause_ids": [],
        "status": "accepted",
    }


def _expected_governance_receipt(
    receipt: Mapping[str, object],
    state: Mapping[str, object],
    paths: RunPaths,
    receipt_type: str,
) -> dict[str, object]:
    issued_at = receipt.get("issued_at_unix")
    if not isinstance(issued_at, int) or isinstance(issued_at, bool) or issued_at < 0:
        raise ControllerError(
            "INVALID_GOVERNANCE_RECEIPT", "Governance receipt timestamp is invalid."
        )
    requirements, requirements_bytes = _active_requirements_artifact(paths, state)
    if receipt_type == "requirements":
        input_digest, transaction_id = _requirements_receipt_input(
            paths, state, requirements
        )
        return _governance_receipt(
            paths,
            state,
            "requirements",
            input_digest=input_digest,
            output_digest=str(state["active_requirements_digest"]),
            requirements_digest=sha256_bytes(requirements_bytes),
            transaction_id=transaction_id,
            snapshot_digest=None,
            claims={},
            issued_at_unix=issued_at,
        )
    report = load_json(paths.run / "implementation-report.json")
    report_errors = validate_packet.validate_report(report, requirements)
    _raise_validation(
        "INVALID_STATE", "Stored implementation report is invalid.", report_errors
    )
    report_digest = validate_packet.canonical_digest(report)
    if report_digest != state.get("active_report_digest"):
        raise ControllerError(
            "INVALID_STATE", "Stored implementation report does not match trusted state."
        )
    review = load_json(paths.run / "review.json")
    review_errors = validate_packet.validate_review(review, requirements, report)
    _raise_validation("INVALID_STATE", "Stored review is invalid.", review_errors)
    review_digest = validate_packet.canonical_digest(review)
    if (
        review_digest != state.get("active_review_packet_digest")
        or review.get("decision") != "PASS"
        or review.get("reviewed_snapshot_digest")
        != state.get("reviewed_snapshot_digest")
    ):
        raise ControllerError(
            "INVALID_STATE", "Stored accepted review does not match trusted state."
        )
    review_round = state.get("review_round")
    if not isinstance(review_round, int) or isinstance(review_round, bool) or review_round < 1:
        raise ControllerError("INVALID_STATE", "Trusted review round is invalid.")
    if receipt_type == "review":
        if state.get("phase") not in {"FINAL_VERIFICATION", "COMPLETE"}:
            raise ControllerError(
                "RECEIPT_WRONG_STATE", "Review receipt is not valid in the current state."
            )
        return _governance_receipt(
            paths,
            state,
            "semantic_review",
            input_digest=report_digest,
            output_digest=review_digest,
            requirements_digest=sha256_bytes(requirements_bytes),
            transaction_id=f"gpc-loop-{paths.task_slug}:review-{review_round:02d}",
            snapshot_digest=review["reviewed_snapshot_digest"],
            claims=_review_receipt_claims(requirements, review_digest),
            issued_at_unix=issued_at,
        )
    if state.get("phase") != "COMPLETE":
        raise ControllerError(
            "RECEIPT_WRONG_STATE", "Final receipt requires successful final verification."
        )
    snapshot = load_json(paths.run / "snapshot.json")
    snapshot_digest = snapshot.get("snapshot_digest")
    if snapshot_digest != state.get("current_snapshot_digest"):
        raise ControllerError(
            "INVALID_STATE", "Stored final snapshot does not match trusted state."
        )
    gate = load_json(paths.run / "final-gate.json")
    final_validation_state = dict(state)
    final_validation_state["phase"] = "FINAL_VERIFICATION"
    gate_errors = validate_packet.validate_final_gate(
        gate, final_validation_state, report, requirements
    )
    _raise_validation("INVALID_STATE", "Stored final gate is invalid.", gate_errors)
    final_input_digest = validate_packet.canonical_digest(
        {
            "current_snapshot_digest": snapshot_digest,
            "report_digest": report_digest,
            "requirements_digest": state["active_requirements_digest"],
            "review_digest": review_digest,
            "reviewed_snapshot_digest": state["reviewed_snapshot_digest"],
        }
    )
    return _governance_receipt(
        paths,
        state,
        "final",
        input_digest=final_input_digest,
        output_digest=validate_packet.canonical_digest(gate),
        requirements_digest=sha256_bytes(requirements_bytes),
        transaction_id=f"gpc-loop-{paths.task_slug}:final-verify-{review_round:02d}",
        snapshot_digest=snapshot_digest,
        claims={},
        issued_at_unix=issued_at,
    )


def _validate_governance_receipt(
    receipt: dict[str, object],
    state: Mapping[str, object],
    paths: RunPaths,
    receipt_type: str,
) -> dict[str, object]:
    if set(receipt) != GOVERNANCE_RECEIPT_FIELDS:
        raise ControllerError(
            "INVALID_GOVERNANCE_RECEIPT", "Governance receipt fields are invalid."
        )
    binding = receipt.get("binding")
    if not isinstance(binding, dict) or set(binding) != GOVERNANCE_BINDING_FIELDS:
        raise ControllerError(
            "INVALID_GOVERNANCE_RECEIPT", "Governance receipt binding is invalid."
        )
    expected = _expected_governance_receipt(receipt, state, paths, receipt_type)
    provenance_fields = {
        "authority_snapshot_digest",
        "binding",
        "execution_id",
        "issuer_skill",
        "issuer_version",
        "nonce",
        "receipt_id",
        "receipt_schema_version",
        "receipt_type",
        "transaction_id",
    }
    if any(receipt.get(field) != expected.get(field) for field in provenance_fields):
        raise ControllerError(
            "GOVERNANCE_RECEIPT_PROVENANCE_MISMATCH",
            "Governance receipt provenance does not match the authoritative run.",
        )
    if receipt != expected:
        raise ControllerError(
            "STALE_GOVERNANCE_RECEIPT",
            "Governance receipt does not match current trusted state and artifacts.",
        )
    if receipt_type == "requirements":
        history = _requirements_receipt_history_path(paths, receipt)
        try:
            history_bytes = history.read_bytes()
        except OSError as exc:
            raise ControllerError(
                "GOVERNANCE_RECEIPT_HISTORY_COLLISION",
                "Immutable requirements receipt history is unavailable.",
            ) from exc
        if history_bytes != _canonical_json_bytes(receipt):
            raise ControllerError(
                "GOVERNANCE_RECEIPT_HISTORY_COLLISION",
                "Immutable requirements receipt history differs from the active receipt.",
            )
    return dict(receipt)


def _governance_export_artifact_paths(
    paths: RunPaths,
    state: Mapping[str, object],
    receipt: Mapping[str, object],
    receipt_type: str,
) -> tuple[Path, ...]:
    revision = state.get("active_requirements_revision")
    artifacts = [
        paths.state,
        _receipt_path(paths, receipt_type),
        paths.run / "requirements.json",
    ]
    if isinstance(revision, int) and not isinstance(revision, bool) and revision > 0:
        artifacts.append(paths.run / f"envelope-{revision:02d}.json")
        artifacts.append(_requirements_revision_path(paths, revision))
        if revision > 1:
            artifacts.append(_requirements_revision_path(paths, revision - 1))
    if receipt_type == "requirements":
        artifacts.append(_requirements_receipt_history_path(paths, receipt))
    else:
        artifacts.extend(
            [
                paths.run / "implementation-report.json",
                paths.run / "review.json",
                paths.run / "snapshot.json",
            ]
        )
        if receipt_type == "final":
            artifacts.append(paths.run / "final-gate.json")
    return tuple(dict.fromkeys(artifacts))


def _read_governance_export_snapshot(paths: Sequence[Path]) -> dict[Path, bytes]:
    try:
        return {path: path.read_bytes() for path in paths}
    except OSError as exc:
        raise ControllerError(
            "RECOVERY_REQUIRED",
            "Governance export artifacts are missing or unstable; preserve the run.",
        ) from exc


def export_governance_receipt(
    repository: Path, task_slug: str, receipt_type: str
) -> dict[str, object]:
    """Return one persisted canonical receipt after read-only authoritative validation."""
    paths = resolve_run(repository, task_slug)
    receipt_path = _receipt_path(paths, receipt_type)
    if not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    # Exports are read-only, but they must enforce the same attestation trust
    # boundary as status and mutating commands.  In particular, do not let an
    # old bound/partial state bypass the restart-required classification simply
    # because a persisted receipt happens to exist.
    _require_manual_recovery(paths)
    # Read the state bytes once as the initial artifact snapshot.  Classify
    # that exact state before checking receipt availability so an untrusted
    # legacy state cannot turn into a mere "receipt unavailable" response for
    # another receipt type.  A later full snapshot detects any replacement.
    initial_state = _read_governance_export_snapshot((paths.state,))
    state_bytes = initial_state[paths.state]
    state = _parse_json_object_bytes(
        state_bytes,
        code="INVALID_JSON",
        message="Controller JSON artifact is invalid.",
    )
    state, _ = _normalize_model_attestation_state(state)
    if not receipt_path.is_file():
        raise ControllerError(
            "RECEIPT_NOT_AVAILABLE", "Governance receipt is not available."
        )
    raw = _read_governance_export_snapshot((receipt_path,))[receipt_path]
    value = _parse_json_object_bytes(
        raw,
        code="INVALID_GOVERNANCE_RECEIPT",
        message="Governance receipt is invalid JSON.",
    )
    if _canonical_json_bytes(value) != raw:
        raise ControllerError(
            "NONCANONICAL_GOVERNANCE_RECEIPT",
            "Governance receipt must use canonical JSON bytes.",
        )
    artifact_paths = _governance_export_artifact_paths(
        paths, state, value, receipt_type
    )
    before = _read_governance_export_snapshot(artifact_paths)
    if before.get(paths.state) != state_bytes or before.get(receipt_path) != raw:
        raise ControllerError(
            "RECOVERY_REQUIRED",
            "Governance export artifacts changed during the initial read.",
        )
    validated = _validate_governance_receipt(value, state, paths, receipt_type)
    _require_manual_recovery(paths)
    after = _read_governance_export_snapshot(artifact_paths)
    if after != before:
        raise ControllerError(
            "RECOVERY_REQUIRED",
            "Governance export artifacts changed between stability reads.",
        )
    return validated


def metadata_hygiene_is_clean(repository: Path) -> bool:
    """Return whether controller metadata is neither tracked nor staged by Git."""
    for metadata_root in (".ai-pro-loop", ".hotl"):
        for command in (
            ["git", "-C", str(repository), "ls-files", "--", metadata_root],
            [
                "git",
                "-C",
                str(repository),
                "diff",
                "--cached",
                "--name-only",
                "--",
                metadata_root,
            ],
        ):
            completed = subprocess.run(
                command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if completed.returncode:
                raise ControllerError(
                    "GIT_CHECK_FAILED", "Could not verify controller metadata hygiene."
                )
            if completed.stdout.strip():
                return False
    return True


def final_verify(repository: Path, task_slug: str) -> dict[str, object]:
    """Derive and validate the final gate from trusted artifacts and Git state."""
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    with run_lock(paths.lock):
        _require_manual_recovery(paths)
        state, loaded_state_digest = _load_mutator_state(paths)
        if state.get("phase") != "FINAL_VERIFICATION":
            raise ControllerError("INVALID_PHASE", "Final verification is available only after PASS review.")
        requirements, report, _bound_snapshot = _active_report_context(
            paths,
            state,
            prior_reviewed_report=True,
            allow_final_verification=True,
        )
        review = _active_prior_review(paths, state, requirements, report)
        current_snapshot = _capture_snapshot(paths, state)
        test_commands = report.get("test_commands")
        gate = {
            "schema_version": SCHEMA_VERSION,
            "requirements_digest": state["active_requirements_digest"],
            "review_packet_digest": state["active_review_packet_digest"],
            "reviewed_snapshot_digest": state["reviewed_snapshot_digest"],
            "current_snapshot_digest": current_snapshot["snapshot_digest"],
            "acceptance_gate_passed": (
                review.get("decision") == "PASS"
                and isinstance(review.get("acceptance_results"), dict)
                and all(
                    isinstance(item, dict) and item.get("status") == "PASS"
                    for item in review["acceptance_results"].values()
                )
            ),
            "local_checks_passed": (
                isinstance(test_commands, list)
                and bool(test_commands)
                and all(
                    isinstance(item, dict) and item.get("outcome") == "PASS"
                    for item in test_commands
                )
                and report.get("omissions") == []
                and report.get("unresolved_risks_or_blockers") == []
            ),
            "scope_gate_passed": review.get("scope_violations") == [],
            "artifact_hygiene_passed": metadata_hygiene_is_clean(paths.repository),
        }
        candidate = dict(state)
        candidate["phase"] = "COMPLETE"
        _raise_validation(
            "FINAL_GATE_REJECTED",
            "Final verification gate did not pass.",
            validate_packet.validate_final_gate(gate, state, report, requirements),
        )
        _raise_validation(
            "INVALID_TRANSITION",
            "Final verification failed state validation.",
            validate_packet.validate_transition(
                state,
                candidate,
                final_gate_evidence=gate,
                final_gate_report=report,
                final_gate_requirements=requirements,
            ),
        )
        final_input_digest = validate_packet.canonical_digest(
            {
                "current_snapshot_digest": current_snapshot["snapshot_digest"],
                "report_digest": state["active_report_digest"],
                "requirements_digest": state["active_requirements_digest"],
                "review_digest": state["active_review_packet_digest"],
                "reviewed_snapshot_digest": state["reviewed_snapshot_digest"],
            }
        )
        final_gate_digest = validate_packet.canonical_digest(gate)
        final_artifacts: list[tuple[Path, str | dict[str, object]]] = [
            (paths.run / "snapshot.json", current_snapshot),
            (paths.run / "final-gate.json", gate),
        ]
        if _governance_provenance_complete(candidate):
            final_artifacts.append(
                (
                    paths.run / "governance-receipt-final.json",
                    _governance_receipt(
                        paths,
                        candidate,
                        "final",
                        input_digest=final_input_digest,
                        output_digest=final_gate_digest,
                        requirements_digest=sha256_bytes(
                            _active_requirements_artifact(paths, state)[1]
                        ),
                        transaction_id=(
                            f"gpc-loop-{task_slug}:final-verify-"
                            f"{state['review_round']:02d}"
                        ),
                        snapshot_digest=current_snapshot["snapshot_digest"],
                        claims={},
                        issued_at_unix=int(time.time()),
                    ),
                )
            )
        _commit_artifacts_then_state(
            paths,
            final_artifacts,
            candidate,
            replaceable_artifacts=frozenset({paths.run / "snapshot.json"}),
            expected_state_digest=loaded_state_digest,
        )
        _record_events_best_effort(paths, [{
            "schema_version": SCHEMA_VERSION,
            "event": "FINAL_VERIFIED",
            "final_gate_digest": final_gate_digest,
            "snapshot_digest": current_snapshot["snapshot_digest"],
        }])
    return status_run(paths.repository, task_slug)


def approve_requirements(
    repository: Path,
    task_slug: str,
    approval_evidence_path: Path,
) -> dict[str, object]:
    """Promote one exact stopped material proposal with local approval evidence."""
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    with run_lock(paths.lock):
        _require_manual_recovery(paths)
        state, loaded_state_digest = _load_mutator_state(paths)
        if (
            state.get("phase") != "USER_DECISION_REQUIRED"
            or state.get("stop_origin_category") != "REQUIREMENTS_NEED_USER_INPUT"
        ):
            raise ControllerError(
                "INVALID_PHASE", "Requirements approval is available only for a stopped proposal."
            )
        evidence = _read_input(approval_evidence_path, "approval evidence")
        if not evidence.strip():
            raise ControllerError("INVALID_APPROVAL", "Approval evidence must not be empty.")
        revision = state.get("pending_requirements_revision")
        digest = state.get("pending_requirements_digest")
        if not isinstance(revision, int) or isinstance(revision, bool) or not isinstance(digest, str):
            raise ControllerError("INVALID_STATE", "Stopped proposal lacks trusted requirements provenance.")
        proposal = load_json(_requirements_revision_path(paths, revision))
        if validate_packet.canonical_digest(proposal) != digest:
            raise ControllerError("INVALID_STATE", "Stored proposal does not match trusted requirements digest.")
        envelope = load_json(paths.run / f"envelope-{revision:02d}.json")
        if envelope.get("payload") != proposal or validate_packet.canonical_digest(envelope) != state.get(
            "last_consumed_packet_digest"
        ):
            raise ControllerError("INVALID_STATE", "Stored proposal envelope does not match trusted state.")
        receipt = f"user-approval:stop-{state['stop_sequence']}:{digest}"
        candidate = dict(state)
        candidate.update(
            phase="REQUIREMENTS_FROZEN",
            latest_decision=None,
            latest_requirements_decision=None,
            required_actions=[],
            unresolved_finding_ids=[],
            blocker_fingerprints=[],
            active_requirements_revision=revision,
            active_requirements_digest=digest,
            approval_sequence=state["approval_sequence"] + 1,
            pending_requirements_revision=None,
            pending_requirements_digest=None,
            pending_supersedes_digest=None,
            pending_approval_sequence=None,
            pending_approved_requirements_digest=None,
            pending_user_approval_evidence=None,
            **{field: False for field in validate_packet.MATERIAL_REVISION_FLAGS},
            stop_origin_phase=None,
            stop_origin_category=None,
            stop_reason=None,
            resolution_evidence=receipt,
            resolution_stop_sequence=state["stop_sequence"],
            review_round=0,
            pending_review_envelope_digest=None,
            pending_review_expected_header_digest=None,
            active_report_digest=None,
            current_snapshot_digest=None,
            active_review_packet_digest=None,
            reviewed_snapshot_digest=None,
        )
        context = _requirements_context(
            envelope,
            {key: envelope[key] for key in EXPECTED_HEADER_FIELDS},
            consumed_chain_heads(state),
            proposal,
            receipt,
        )
        transition_errors = validate_packet.validate_transition(
            state, candidate, requirements_context=context
        )
        _raise_validation("INVALID_TRANSITION", "Requirements approval failed state validation.", transition_errors)
        approval_artifacts: list[tuple[Path, str | dict[str, object]]] = [
            (paths.run / f"approval-stop-{state['stop_sequence']:02d}.txt", evidence),
            (paths.run / "requirements.json", proposal),
        ]
        if _governance_provenance_complete(candidate):
            requirements_receipt = _governance_receipt(
                paths,
                candidate,
                "requirements",
                input_digest=validate_packet.canonical_digest(envelope),
                output_digest=digest,
                requirements_digest=sha256_bytes(_canonical_json_bytes(proposal)),
                transaction_id=(
                    f"gpc-loop-{task_slug}:approval-stop-"
                    f"{state['stop_sequence']:02d}"
                ),
                snapshot_digest=None,
                claims={},
                issued_at_unix=int(time.time()),
            )
            approval_artifacts.extend(
                _requirements_receipt_artifacts(paths, requirements_receipt)
            )
        _commit_artifacts_then_state(
            paths,
            approval_artifacts,
            candidate,
            replaceable_artifacts=frozenset(
                {
                    paths.run / "requirements.json",
                    paths.run / "governance-receipt-requirements.json",
                }
            ),
            expected_state_digest=loaded_state_digest,
        )
        _record_events_best_effort(paths, [{
            "schema_version": SCHEMA_VERSION,
            "event": "MATERIAL_REQUIREMENTS_APPROVED",
            "requirements_digest": digest,
            "stop_sequence": state["stop_sequence"],
        }])
    return status_run(paths.repository, task_slug)


def _matches_sent_artifact(paths: RunPaths, expected: Mapping[str, object]) -> bool:
    nonce = expected.get("nonce")
    turn_id = expected.get("turn_id")
    if not isinstance(nonce, str) or not isinstance(turn_id, str):
        return True
    response_directory = paths.run / "responses"
    if response_directory.exists():
        if not response_directory.is_dir():
            return True
        for response in response_directory.iterdir():
            if not response.is_file():
                return True
            try:
                text = response.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return True
            if nonce in text or turn_id in text:
                return True
    for envelope_path in paths.run.glob("envelope-*.json"):
        try:
            envelope = load_json(envelope_path)
        except ControllerError:
            return True
        if envelope.get("nonce") == nonce or envelope.get("turn_id") == turn_id:
            return True
    return False


def abandon_attempt(
    repository: Path,
    task_slug: str,
    send_status: str,
    evidence_path: Path,
) -> dict[str, object]:
    """Close an unambiguously unsent expected attempt without changing state."""
    if send_status != "NOT_SENT":
        raise ControllerError("SEND_STATUS_REQUIRED", "Attempt abandonment requires NOT_SENT status.")
    paths = resolve_run(repository, task_slug)
    if not paths.run.is_dir() or not paths.state.is_file():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    evidence = _read_input(evidence_path, "not-sent evidence")
    evidence = _normalize_prompt(evidence)
    if not evidence.strip():
        raise ControllerError("EMPTY_EVIDENCE", "Not-sent evidence must not be empty.")
    bounded_evidence = evidence.encode("utf-8")[:MAX_ABANDON_EVIDENCE_BYTES].decode(
        "utf-8", errors="ignore"
    )
    with run_lock(paths.lock):
        _require_manual_recovery(paths)
        state, loaded_state_digest = _load_mutator_state(paths)
        attempts = _outstanding_attempts(paths)
        if len(attempts) != 1:
            raise ControllerError("OUTSTANDING_ATTEMPT_REQUIRED", "Exactly one outstanding attempt is required.")
        expected_path = paths.run / str(attempts[0]["name"])
        expected = attempts[0]["expected_header"]
        if not _valid_expected_header(expected):
            raise ControllerError("INVALID_EXPECTED_ATTEMPT", "Outstanding attempt header is invalid.")
        expected_digest = validate_packet.canonical_digest(expected)
        anchor_field = (
            "pending_requirements_expected_header_digest"
            if expected.get("packet_type") == "requirements"
            else "pending_review_expected_header_digest"
        )
        if state.get(anchor_field) != expected_digest:
            raise ControllerError(
                "INVALID_EXPECTED_ATTEMPT",
                "Outstanding attempt does not match trusted state.",
            )
        if _matches_sent_artifact(paths, expected):
            raise ControllerError("AMBIGUOUS_SEND", "Attempt may have been sent or received.")
        match = ATTEMPT_NAME.fullmatch(expected_path.name)
        if match is None:
            raise ControllerError("INVALID_EXPECTED_ATTEMPT", "Outstanding attempt name is invalid.")
        abandoned_path = expected_path
        abandoned = {
            "schema_version": SCHEMA_VERSION,
            "status": "ABANDONED_NOT_SENT",
            "expected_header": expected,
            "expected_header_digest": expected_digest,
            "nonce": expected["nonce"],
            "prompt_digest": expected["prompt_digest"],
            "evidence": bounded_evidence,
            "abandoned_at_unix": int(time.time()),
        }
        transaction = paths.transactions / f"abandon-{os.getpid()}-{time.time_ns()}"
        transaction.mkdir()
        staged = transaction / abandoned_path.name
        staged_paths: list[tuple[Path, os.stat_result]] = []
        try:
            write_json_atomic(staged, abandoned)
            staged_paths.append(_owned_path(staged))
            _require_state_digest(paths, loaded_state_digest)
            os.replace(staged, abandoned_path)
        except OSError as exc:
            raise ControllerError("WRITE_FAILED", "Could not atomically abandon the attempt.") from exc
        finally:
            _cleanup_owned_transaction(transaction, staged_paths)
    return {
        "abandoned_attempt_path": str(abandoned_path),
        "nonce": expected["nonce"],
        "prompt_digest": expected["prompt_digest"],
    }


def next_commands(
    state: Mapping[str, object],
    outstanding_attempt: Mapping[str, object] | None,
) -> list[str]:
    """Return only commands valid for the current phase and pre-send attempt."""
    if (
        isinstance(state.get("review_round"), int)
        and state.get("review_round") >= _review_round_limit(state)
        and state.get("phase") not in {"FINAL_VERIFICATION", "COMPLETE"}
    ):
        return []
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
            and state.get("user_approval_required") is True
            else []
        )
    return {
        "REQUIREMENTS_PENDING": ["prepare-requirements"],
        "REQUIREMENTS_FROZEN": ["build-report"],
        "IMPLEMENTING": ["build-report"],
        "LOCAL_VERIFICATION": ["build-report", "prepare-review"],
        "REVIEW_PENDING": ["build-report", "prepare-review"],
        "FINAL_VERIFICATION": (
            ["final-verify"]
            if state.get("review_round") == validate_packet.MAX_REVIEW_ROUNDS
            else ["build-report", "final-verify"]
        ),
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
        if artifact.get("status") == "ABANDONED_NOT_SENT":
            try:
                _validate_abandoned_attempt_receipt(artifact)
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
        INITIALIZATION_MARKER_NAME,
        "prompts",
        "responses",
        "governance-receipt-requirements.json",
        "governance-receipt-review.json",
        "governance-receipt-final.json",
        GOVERNANCE_RECEIPT_HISTORY_DIRECTORY,
    }
    reachable_digests = {
        value
        for value in state.values()
        if isinstance(value, str) and value.startswith("sha256:")
    }
    unreachable: list[str] = []
    for path in paths.run.iterdir():
        if path.name in allowed_names or path.name.startswith(
            ("expected-attempt-", "consumed-attempt-", "approval-stop-")
        ):
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
    if not paths.run.exists():
        raise ControllerError("RUN_NOT_FOUND", "Run state does not exist.")
    if not paths.state.is_file():
        classification = _incomplete_initialization(paths)
        if classification["recognized"]:
            active = classification["lock_status"] == "active"
            retry_argv = [
                "python",
                "skills/gpt-pro-codex-loop/scripts/gpc_loop.py",
                "init",
                "--repo",
                str(paths.repository),
                "--task",
                paths.task_slug,
                "--retry-incomplete",
                "--request",
                "REQUEST.md",
                "--repository-context",
                "CONTEXT.md",
                "--model-policy",
                "PRO_CLASS",
                "--review-policy",
                validate_packet.DEFAULT_REVIEW_POLICY,
            ]
            return {
                "phase": "INIT_INCOMPLETE",
                "active_requirements_revision": None,
                "review_round": 0,
                "review_policy": validate_packet.DEFAULT_REVIEW_POLICY,
                "review_round_limit": 1,
                "conversation": {"binding_state": "CONVERSATION_UNBOUND", "url": None},
                "model": {"policy": None, "requested_label": None, "visible_label": None},
                "required_actions": [],
                "unresolved_finding_ids": [],
                "blocker_fingerprints": [],
                "stop_origin_category": "INITIALIZATION",
                "outstanding_attempts": [],
                "lock_present": paths.lock.exists(),
                "orphan_transactions": [],
                "recovery_required": True,
                "recovery_transaction_paths": [],
                "recovery_guidance": f"retry_init_argv:{_command_json(retry_argv)}",
                "unreachable_artifacts": [],
                "next_commands": [] if active else ["init --retry-incomplete"],
            }
        raise ControllerError(
            "INIT_RECOVERY_REQUIRED",
            "Run state is missing and initialization artifacts are ambiguous; no automatic recovery is allowed.",
        )
    raw_state = load_json(paths.state)
    try:
        state, legacy_upgrade_pending = _normalize_model_attestation_state(raw_state)
    except ControllerError as exc:
        if exc.code != "LEGACY_STATE_RESTART_REQUIRED":
            raise
        return {
            "phase": "LEGACY_STATE_RESTART_REQUIRED",
            "active_requirements_revision": raw_state.get("active_requirements_revision"),
            "review_round": raw_state.get("review_round"),
            "review_policy": validate_packet.review_policy(raw_state),
            "review_round_limit": validate_packet.review_round_limit(raw_state),
            "conversation": {
                "binding_state": raw_state.get("conversation_binding_state"),
                "url": raw_state.get("bound_conversation_url"),
            },
            "model": {
                "policy": raw_state.get("model_policy"),
                "requested_label": raw_state.get("requested_model_label"),
                "visible_label": raw_state.get("visible_model_label"),
                "visible_reasoning_label": raw_state.get("visible_reasoning_label"),
                "visible_plan_label": raw_state.get("visible_plan_label"),
            },
            "required_actions": [],
            "unresolved_finding_ids": raw_state.get("unresolved_finding_ids", []),
            "blocker_fingerprints": raw_state.get("blocker_fingerprints", []),
            "stop_origin_category": "LEGACY_MODEL_ATTESTATION",
            "outstanding_attempts": [],
            "lock_present": paths.lock.exists(),
            "orphan_transactions": [],
            "recovery_required": True,
            "recovery_transaction_paths": [],
            "recovery_guidance": exc.message,
            "unreachable_artifacts": _unreachable_artifacts(paths, raw_state),
            "legacy_model_attestation_upgrade_pending": False,
            "next_commands": [],
        }
    attempts = _outstanding_attempts(paths)
    outstanding = attempts[0] if len(attempts) == 1 else None
    orphan_transaction_paths = _orphan_transaction_paths(paths)
    orphan_transactions = [path.name for path in orphan_transaction_paths]
    recovery_required = bool(orphan_transaction_paths)
    recovery_details = _recovery_details(paths, orphan_transaction_paths) if recovery_required else []
    return {
        "phase": state.get("phase"),
        "active_requirements_revision": state.get("active_requirements_revision"),
        "review_round": state.get("review_round"),
        "review_policy": validate_packet.review_policy(state),
        "review_round_limit": _review_round_limit(state),
        "conversation": {
            "binding_state": state.get("conversation_binding_state"),
            "url": state.get("bound_conversation_url"),
        },
        "model": {
            "policy": state.get("model_policy"),
            "requested_label": state.get("requested_model_label"),
            "visible_label": state.get("visible_model_label"),
            "visible_reasoning_label": state.get("visible_reasoning_label"),
            "visible_plan_label": state.get("visible_plan_label"),
        },
        "required_actions": state.get("required_actions"),
        "unresolved_finding_ids": state.get("unresolved_finding_ids"),
        "blocker_fingerprints": state.get("blocker_fingerprints"),
        "stop_origin_category": state.get("stop_origin_category"),
        "outstanding_attempts": [attempt["name"] for attempt in attempts],
        "lock_present": paths.lock.exists(),
        "orphan_transactions": orphan_transactions,
        "recovery_required": recovery_required,
        "recovery_transaction_paths": [str(path) for path in orphan_transaction_paths],
        "recovery_guidance": " ".join(recovery_details),
        "unreachable_artifacts": _unreachable_artifacts(paths, state),
        "legacy_model_attestation_upgrade_pending": legacy_upgrade_pending,
        "next_commands": [] if recovery_required else next_commands(state, outstanding),
    }
