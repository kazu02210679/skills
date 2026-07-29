#!/usr/bin/env python3
"""Fail-closed validation for GPT Pro Codex Loop JSON packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


FENCE_PATTERN = re.compile(
    r"```json[ \t]*\r?\n(?P<body>.*?)\r?\n```",
    re.DOTALL,
)

SCHEMA_VERSION = 1
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
TRANSPORT_HEADER_FIELDS = (
    "schema_version",
    "packet_type",
    "run_id",
    "turn_id",
    "nonce",
    "in_reply_to",
    "prompt_digest",
    "previous_packet_digest",
)
TRANSPORT_ENVELOPE_FIELDS = (*TRANSPORT_HEADER_FIELDS, "payload")
TRANSPORT_PACKET_TYPES = frozenset({"requirements", "review"})
REQUIREMENTS_DECISIONS = frozenset({"PLAN_READY", "NEED_USER_INPUT", "BLOCK"})
REVIEW_DECISIONS = frozenset({"PASS", "CHANGES_REQUESTED", "BLOCK"})
ACCEPTANCE_STATUSES = frozenset({"PASS", "FAIL", "UNVERIFIED"})
REQUIRED_ACTIONS = frozenset(
    {
        "CODE_CHANGE",
        "TEST_CHANGE",
        "PROVIDE_EVIDENCE",
        "REQUIREMENTS_REVISION",
        "USER_DECISION",
    }
)
FINDING_SEVERITIES = frozenset({"BLOCKER", "HIGH", "MEDIUM", "LOW"})
MATERIAL_CHANGE_FIELDS = (
    "behavior_changed",
    "scope_changed",
    "public_contract_changed",
)
MATERIAL_REVISION_FLAGS = (
    "behavior_changed",
    "user_approval_required",
    "user_approval_received",
    "scope_changed",
    "public_contract_changed",
    "prior_evidence_invalidated",
    "review_round_reset",
)
MATERIAL_RESET_SIGNALS = (
    *MATERIAL_CHANGE_FIELDS,
    "user_approval_required",
    "user_approval_received",
    "review_round_reset",
)
PENDING_REVISION_PROVENANCE_FIELDS = (
    "pending_requirements_revision",
    "pending_requirements_digest",
    "pending_supersedes_digest",
    "pending_approval_sequence",
    "pending_approved_requirements_digest",
    "pending_user_approval_evidence",
    *MATERIAL_REVISION_FLAGS,
)
STOP_PHASES = frozenset({"USER_DECISION_REQUIRED", "BLOCKED"})
STOP_ORIGIN_CATEGORIES = frozenset(
    {
        "REQUIREMENTS_NEED_USER_INPUT",
        "REQUIREMENTS_BLOCK",
        "REVIEW_USER_DECISION",
        "REVIEW_BLOCK",
        "FINAL_VERIFICATION_BLOCK",
    }
)
STOP_CATEGORY_ORIGINS = {
    "REQUIREMENTS_NEED_USER_INPUT": "REQUIREMENTS_PENDING",
    "REQUIREMENTS_BLOCK": "REQUIREMENTS_PENDING",
    "REVIEW_USER_DECISION": "REVIEW_PENDING",
    "REVIEW_BLOCK": "REVIEW_PENDING",
    "FINAL_VERIFICATION_BLOCK": "FINAL_VERIFICATION",
}
STOP_CATEGORY_PHASES = {
    "REQUIREMENTS_NEED_USER_INPUT": "USER_DECISION_REQUIRED",
    "REQUIREMENTS_BLOCK": "BLOCKED",
    "REVIEW_USER_DECISION": "USER_DECISION_REQUIRED",
    "REVIEW_BLOCK": "USER_DECISION_REQUIRED",
    "FINAL_VERIFICATION_BLOCK": "BLOCKED",
}
STOP_RESUME_TARGETS = {
    "REQUIREMENTS_NEED_USER_INPUT": ("REQUIREMENTS_PENDING",),
    "REQUIREMENTS_BLOCK": ("REQUIREMENTS_PENDING",),
    "REVIEW_USER_DECISION": ("IMPLEMENTING", "REVIEW_PENDING"),
    "REVIEW_BLOCK": ("IMPLEMENTING", "REVIEW_PENDING"),
    "FINAL_VERIFICATION_BLOCK": ("FINAL_VERIFICATION", "IMPLEMENTING"),
}
REQUIRED_REQUIREMENTS_FIELDS = (
    "schema_version",
    "requirements_revision",
    "supersedes_digest",
    "change_reason",
    "behavior_changed",
    "user_approval_required",
    "user_approval_received",
    "scope_changed",
    "public_contract_changed",
    "prior_evidence_invalidated",
    "review_round_reset",
    "decision",
    "objective",
    "requirements",
    "in_scope",
    "out_of_scope",
    "constraints",
    "acceptance_criteria",
    "design_direction",
    "risk_items",
    "verification_strategy",
    "open_questions",
)
REQUIRED_REPORT_FIELDS = (
    "schema_version",
    "baseline_head",
    "requirements_revision",
    "requirements_digest",
    "review_round",
    "snapshot_digest",
    "tracked_diff_digest",
    "untracked_manifest_digest",
    "changed_files",
    "intent_summary",
    "acceptance_evidence",
    "test_commands",
    "diff_evidence",
    "omissions",
    "unresolved_risks_or_blockers",
)
REQUIRED_REVIEW_FIELDS = (
    "schema_version",
    "requirements_digest",
    "reviewed_snapshot_digest",
    "decision",
    "acceptance_results",
    "findings",
    "scope_violations",
    "next_instruction",
)
REQUIRED_STATE_FIELDS = (
    "schema_version",
    "phase",
    "review_round",
    "latest_decision",
    "latest_requirements_decision",
    "required_actions",
    "unresolved_finding_ids",
    "blocker_fingerprints",
    "format_error_count",
    "browser_reconnect_count",
    "conversation_binding_state",
    "bound_conversation_url",
    "model_policy",
    "requested_model_label",
    "visible_model_label",
    "active_requirements_revision",
    "active_requirements_digest",
    "approval_sequence",
    "pending_requirements_revision",
    "pending_requirements_digest",
    "pending_supersedes_digest",
    "pending_approval_sequence",
    "pending_approved_requirements_digest",
    "pending_user_approval_evidence",
    "behavior_changed",
    "user_approval_required",
    "scope_changed",
    "public_contract_changed",
    "prior_evidence_invalidated",
    "review_round_reset",
    "user_approval_received",
    "stop_origin_phase",
    "stop_origin_category",
    "stop_reason",
    "stop_sequence",
    "resolution_evidence",
    "resolution_stop_sequence",
    "pending_requirements_envelope_digest",
    "pending_review_envelope_digest",
    "last_consumed_packet_digest",
    "last_consumed_review_envelope_digest",
    "active_report_digest",
    "current_snapshot_digest",
    "active_review_packet_digest",
    "reviewed_snapshot_digest",
)
OPTIONAL_STATE_FIELDS: tuple[str, ...] = ()
FINAL_GATE_FIELDS = (
    "schema_version",
    "requirements_digest",
    "review_packet_digest",
    "reviewed_snapshot_digest",
    "current_snapshot_digest",
    "acceptance_gate_passed",
    "local_checks_passed",
    "scope_gate_passed",
    "artifact_hygiene_passed",
)
REVIEW_TRANSITION_CONTEXT_FIELDS = (
    "envelope",
    "expected",
    "consumed_digests",
    "requirements",
    "report",
    "snapshot",
)
REQUIREMENTS_TRANSITION_CONTEXT_FIELDS = (
    "envelope",
    "expected",
    "consumed_digests",
    "requirements",
    "approval_receipt",
)
STATE_TRANSITIONS = {
    "PREFLIGHT": frozenset({"REQUIREMENTS_PENDING"}),
    "REQUIREMENTS_PENDING": frozenset(
        {"REQUIREMENTS_FROZEN", "USER_DECISION_REQUIRED", "BLOCKED"}
    ),
    "REQUIREMENTS_FROZEN": frozenset({"IMPLEMENTING"}),
    "IMPLEMENTING": frozenset({"LOCAL_VERIFICATION"}),
    "LOCAL_VERIFICATION": frozenset({"REVIEW_PENDING"}),
    "REVIEW_PENDING": frozenset(
        {
            "IMPLEMENTING",
            "LOCAL_VERIFICATION",
            "REQUIREMENTS_PENDING",
            "USER_DECISION_REQUIRED",
            "FINAL_VERIFICATION",
        }
    ),
    "USER_DECISION_REQUIRED": frozenset(
        {"REQUIREMENTS_PENDING", "IMPLEMENTING", "REVIEW_PENDING"}
    ),
    "FINAL_VERIFICATION": frozenset({"COMPLETE", "REVIEW_PENDING", "BLOCKED"}),
    "COMPLETE": frozenset(),
    "BLOCKED": frozenset(
        {"REQUIREMENTS_PENDING", "FINAL_VERIFICATION", "IMPLEMENTING"}
    ),
}
MAX_REVIEW_ROUNDS = 3
MAX_FORMAT_ERRORS = 1


class PacketValidationError(ValueError):
    """Raised when untrusted Browser or file JSON fails strict decoding."""


def _reject_constant(value: str) -> None:
    raise PacketValidationError(f"non-standard JSON constant: {value}")


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PacketValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(raw: str) -> object:
    """Decode one untrusted protocol JSON object with fail-closed JSON rules."""
    if raw.startswith("\ufeff"):
        raise PacketValidationError("JSON must not start with a BOM")
    try:
        value = json.loads(
            raw,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except PacketValidationError:
        raise
    except json.JSONDecodeError as exc:
        raise PacketValidationError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise PacketValidationError("packet must be a JSON object")
    return value


def extract_single_json_object(raw: str) -> dict[str, object]:
    if raw.startswith("\ufeff"):
        raise PacketValidationError("response must not start with a BOM")
    if raw.count("```") != 2:
        raise PacketValidationError(
            "response must contain one unnested JSON fence"
        )
    matches = list(FENCE_PATTERN.finditer(raw))
    if len(matches) != 1 or raw.strip() != matches[0].group(0):
        raise PacketValidationError("response must contain exactly one JSON fence")
    value = strict_json_loads(matches[0].group("body"))
    return value


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _errors_sorted(errors: list[str]) -> list[str]:
    return sorted(set(errors), key=lambda error: (error.split(":", 1)[0], error))


def _as_mapping(value: object, path: str, errors: list[str]) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    errors.append(f"{path}: must be an object")
    return {}


def _require_fields(packet: dict[str, object], fields: tuple[str, ...], errors: list[str]) -> None:
    for field in fields:
        if field not in packet:
            errors.append(f"{field}: missing required field")


def _reject_unknown_fields(
    packet: dict[str, object],
    fields: tuple[str, ...],
    errors: list[str],
    *,
    path: str = "",
) -> None:
    allowed = set(fields)
    for field in packet:
        if field not in allowed:
            prefix = f"{path}." if path else ""
            errors.append(f"{prefix}{field}: unknown field")


def _require_schema_version(
    packet: dict[str, object],
    errors: list[str],
    *,
    path: str = "",
) -> None:
    value = packet.get("schema_version")
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value != SCHEMA_VERSION
    ):
        prefix = f"{path}." if path else ""
        errors.append(f"{prefix}schema_version: must be integer {SCHEMA_VERSION}")


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_nonempty_string(packet: dict[str, object], field: str, errors: list[str]) -> None:
    if field in packet and not _is_nonempty_string(packet[field]):
        errors.append(f"{field}: must be a non-empty string")


def _require_list(packet: dict[str, object], field: str, errors: list[str]) -> list[object]:
    value = packet.get(field)
    if field in packet and not isinstance(value, list):
        errors.append(f"{field}: must be a list")
        return []
    return value if isinstance(value, list) else []


def _require_digest(value: object, path: str, errors: list[str], *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value):
        errors.append(f"{path}: must be a sha256 digest")


def _canonical_digest_checked(
    value: object,
    path: str,
    errors: list[str],
) -> str | None:
    try:
        return canonical_digest(value)
    except (TypeError, ValueError):
        errors.append(f"{path}: must contain canonical finite JSON values")
        return None


def _validate_transport_envelope_shape(
    envelope: object,
) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    packet = _as_mapping(envelope, "envelope", errors)
    _require_fields(packet, TRANSPORT_ENVELOPE_FIELDS, errors)
    _reject_unknown_fields(packet, TRANSPORT_ENVELOPE_FIELDS, errors)
    _require_schema_version(packet, errors)
    if (
        not isinstance(packet.get("packet_type"), str)
        or packet.get("packet_type") not in TRANSPORT_PACKET_TYPES
    ):
        errors.append("packet_type: must be requirements or review")
    for field in ("run_id", "turn_id", "nonce"):
        _require_nonempty_string(packet, field, errors)
    for field in ("in_reply_to", "prompt_digest"):
        _require_digest(packet.get(field), field, errors)
    _require_digest(
        packet.get("previous_packet_digest"),
        "previous_packet_digest",
        errors,
        nullable=True,
    )
    payload = _as_mapping(packet.get("payload"), "payload", errors)
    packet_type = packet.get("packet_type")
    if packet_type == "requirements":
        errors.extend(
            f"payload.{error}"
            for error in _validate_requirements(
                payload,
                require_initial=False,
            )
        )
    elif packet_type == "review":
        _require_fields(payload, REQUIRED_REVIEW_FIELDS, errors)
        _reject_unknown_fields(
            payload,
            REQUIRED_REVIEW_FIELDS,
            errors,
            path="payload",
        )
        if "schema_version" in payload:
            _require_schema_version(payload, errors, path="payload")
    return packet, _errors_sorted(errors)


def validate_transport_envelope(
    envelope,
    expected,
    consumed_digests,
) -> list[str]:
    """Validate an untrusted Pro response against one trusted send attempt.

    ``expected`` and ``consumed_digests`` are trusted local controller state.
    The Browser response is never allowed to select its own correlation values.
    """
    packet, errors = _validate_transport_envelope_shape(envelope)
    trusted = _as_mapping(expected, "expected", errors)
    for field in TRANSPORT_HEADER_FIELDS:
        if field not in trusted:
            errors.append(f"expected.{field}: missing required field")
    _reject_unknown_fields(
        trusted,
        TRANSPORT_HEADER_FIELDS,
        errors,
        path="expected",
    )
    for field in TRANSPORT_HEADER_FIELDS:
        if field in trusted and packet.get(field) != trusted.get(field):
            errors.append(
                f"{field}: does not match expected transport context"
            )
    if not isinstance(
        consumed_digests,
        (set, frozenset, list, tuple),
    ) or any(
        not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value)
        for value in consumed_digests
    ):
        errors.append("consumed_digests: must be a collection of digest strings")
    else:
        envelope_digest = _canonical_digest_checked(packet, "envelope", errors)
        if envelope_digest is not None and envelope_digest in consumed_digests:
            errors.append("envelope_digest: response has already been consumed")
    return _errors_sorted(errors)


def validate_format_correction(
    original_payload,
    corrected_envelope,
) -> list[str]:
    """Require a safely recovered original payload to remain byte-semantically equal."""
    errors: list[str] = []
    original = _as_mapping(original_payload, "original_payload", errors)
    corrected, shape_errors = _validate_transport_envelope_shape(
        corrected_envelope
    )
    errors.extend(shape_errors)
    payload = _as_mapping(corrected.get("payload"), "payload", errors)
    original_digest = _canonical_digest_checked(
        original,
        "original_payload",
        errors,
    )
    corrected_digest = _canonical_digest_checked(payload, "payload", errors)
    if (
        original_digest is not None
        and corrected_digest is not None
        and original_digest != corrected_digest
    ):
        errors.append(
            "payload: format correction must preserve the recovered payload exactly"
        )
    return _errors_sorted(errors)


def _stable_ids(
    items: list[object],
    path: str,
    required_fields: tuple[str, ...],
    errors: list[str],
) -> set[str]:
    ids: set[str] = set()
    for index, value in enumerate(items):
        item_path = f"{path}.{index}"
        item = _as_mapping(value, item_path, errors)
        for field in required_fields:
            if field not in item:
                errors.append(f"{item_path}.{field}: missing required field")
            elif not _is_nonempty_string(item[field]):
                errors.append(f"{item_path}.{field}: must be a non-empty string")
        _reject_unknown_fields(
            item,
            required_fields,
            errors,
            path=item_path,
        )
        identifier = item.get("id")
        if _is_nonempty_string(identifier):
            if identifier in ids:
                errors.append(f"{item_path}.id: duplicate stable ID {identifier}")
            ids.add(identifier)
    return ids


def _acceptance_ids(requirements: dict[str, object], errors: list[str]) -> set[str]:
    criteria = _require_list(requirements, "acceptance_criteria", errors)
    return _stable_ids(
        criteria,
        "acceptance_criteria",
        ("id", "criterion", "required_evidence"),
        errors,
    )


def _validate_requirements(packet, previous=None, *, require_initial: bool):
    """Return all deterministic requirements-packet validation errors."""
    errors: list[str] = []
    current = _as_mapping(packet, "packet", errors)
    _require_fields(current, REQUIRED_REQUIREMENTS_FIELDS, errors)
    _reject_unknown_fields(current, REQUIRED_REQUIREMENTS_FIELDS, errors)
    _require_schema_version(current, errors)
    revision = current.get("requirements_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        errors.append("requirements_revision: must be a positive integer")
    _require_digest(current.get("supersedes_digest"), "supersedes_digest", errors, nullable=True)
    _require_nonempty_string(current, "change_reason", errors)
    for field in (
        "behavior_changed",
        "user_approval_required",
        "user_approval_received",
        "scope_changed",
        "public_contract_changed",
        "prior_evidence_invalidated",
        "review_round_reset",
    ):
        if field in current and not isinstance(current[field], bool):
            errors.append(f"{field}: must be a boolean")
    material_change = any(
        current.get(field) is True
        for field in ("behavior_changed", "scope_changed", "public_contract_changed")
    )
    if current.get("behavior_changed") is True and current.get("user_approval_required") is not True:
        errors.append("behavior changes require user approval")
    if current.get("scope_changed") is True or current.get("public_contract_changed") is True:
        if current.get("behavior_changed") is not True:
            errors.append(
                "behavior_changed: material scope or public-contract changes require behavior_changed"
            )
    if material_change and current.get("user_approval_required") is not True:
        errors.append("material changes require user approval")
    if material_change and current.get("user_approval_received") is not True:
        errors.append("material changes require explicit user approval")
    if material_change and current.get("prior_evidence_invalidated") is not True:
        errors.append("prior_evidence_invalidated: material changes must invalidate prior evidence")
    if material_change and current.get("review_round_reset") is not True:
        errors.append("review_round_reset: material changes must reset review round")
    if (
        not isinstance(current.get("decision"), str)
        or current.get("decision") not in REQUIREMENTS_DECISIONS
    ):
        errors.append("decision: must be PLAN_READY, NEED_USER_INPUT, or BLOCK")
    _require_nonempty_string(current, "objective", errors)

    requirements = _require_list(current, "requirements", errors)
    _stable_ids(requirements, "requirements", ("id", "statement"), errors)
    for field in ("in_scope", "out_of_scope", "constraints", "design_direction", "verification_strategy"):
        _require_list(current, field, errors)
    _acceptance_ids(current, errors)
    risks = _require_list(current, "risk_items", errors)
    _stable_ids(risks, "risk_items", ("id", "risk", "required_mitigation"), errors)
    open_questions = _require_list(current, "open_questions", errors)
    if current.get("decision") == "PLAN_READY" and open_questions:
        errors.append("open_questions: PLAN_READY requires no material open questions")

    if previous is None:
        if require_initial and revision != 1:
            errors.append("requirements_revision: initial requirements revision must be 1")
        if revision == 1 and current.get("supersedes_digest") is not None:
            errors.append("supersedes_digest: initial requirements must not supersede a digest")
        if not require_initial and isinstance(revision, int) and revision > 1:
            if current.get("supersedes_digest") is None:
                errors.append("supersedes_digest: revised requirements must supersede a digest")
    else:
        prior = _as_mapping(previous, "previous", errors)
        prior_revision = prior.get("requirements_revision")
        if not isinstance(prior_revision, int) or isinstance(prior_revision, bool):
            errors.append("previous.requirements_revision: must be a positive integer")
        elif revision != prior_revision + 1:
            errors.append("requirements_revision: must increment the previous revision by one")
        prior_digest = _canonical_digest_checked(prior, "previous", errors)
        if (
            prior_digest is not None
            and current.get("supersedes_digest") != prior_digest
        ):
            errors.append("supersedes_digest: must equal the previous requirements digest")

    return _errors_sorted(errors)


def validate_requirements(packet, previous=None):
    """Return all deterministic requirements-packet validation errors."""
    return _validate_requirements(packet, previous, require_initial=True)


def validate_report(packet, requirements):
    """Return all deterministic implementation-report validation errors."""
    errors: list[str] = []
    report = _as_mapping(packet, "packet", errors)
    req = _as_mapping(requirements, "requirements", errors)
    errors.extend(
        f"requirements.{error}"
        for error in _validate_requirements(req, require_initial=False)
    )
    _require_fields(report, REQUIRED_REPORT_FIELDS, errors)
    _reject_unknown_fields(report, REQUIRED_REPORT_FIELDS, errors)
    _require_schema_version(report, errors)
    _require_nonempty_string(report, "baseline_head", errors)
    if report.get("requirements_revision") != req.get("requirements_revision"):
        errors.append("requirements_revision: does not match requirements revision")
    requirements_digest = _canonical_digest_checked(
        req,
        "requirements",
        errors,
    )
    if (
        requirements_digest is not None
        and report.get("requirements_digest") != requirements_digest
    ):
        errors.append("requirements_digest: does not match requirements digest")
    review_round = report.get("review_round")
    if not isinstance(review_round, int) or isinstance(review_round, bool) or review_round < 0:
        errors.append("review_round: must be a non-negative integer")
    elif review_round > MAX_REVIEW_ROUNDS:
        errors.append(f"review_round: exceeds maximum of {MAX_REVIEW_ROUNDS}")
    if req.get("review_round_reset") is True and review_round != 0:
        errors.append("review_round: material revision requires reset to zero")
    for field in ("snapshot_digest", "tracked_diff_digest", "untracked_manifest_digest"):
        _require_digest(report.get(field), field, errors)
    changed_files = _require_list(report, "changed_files", errors)
    for index, changed_file in enumerate(changed_files):
        item = _as_mapping(changed_file, f"changed_files.{index}", errors)
        for field in ("path", "intent"):
            if field not in item:
                errors.append(f"changed_files.{index}.{field}: missing required field")
            elif not _is_nonempty_string(item[field]):
                errors.append(f"changed_files.{index}.{field}: must be a non-empty string")
    _require_nonempty_string(report, "intent_summary", errors)
    evidence = report.get("acceptance_evidence")
    if not isinstance(evidence, dict):
        errors.append("acceptance_evidence: must be an object keyed by acceptance ID")
        evidence = {}
    acceptance_ids = _acceptance_ids(req, errors)
    for acceptance_id in acceptance_ids:
        if acceptance_id not in evidence or not evidence[acceptance_id]:
            errors.append(f"acceptance_evidence.{acceptance_id}: missing acceptance evidence")
    for acceptance_id in evidence:
        if acceptance_id not in acceptance_ids:
            errors.append(f"acceptance_evidence.{acceptance_id}: unknown acceptance ID")
    test_commands = _require_list(report, "test_commands", errors)
    for index, command in enumerate(test_commands):
        item = _as_mapping(command, f"test_commands.{index}", errors)
        for field in ("command", "outcome", "output_summary"):
            if field not in item:
                errors.append(f"test_commands.{index}.{field}: missing required field")
            elif not _is_nonempty_string(item[field]):
                errors.append(f"test_commands.{index}.{field}: must be a non-empty string")
        _reject_unknown_fields(
            item,
            ("command", "outcome", "output_summary"),
            errors,
            path=f"test_commands.{index}",
        )
    for field in ("diff_evidence", "omissions", "unresolved_risks_or_blockers"):
        _require_list(report, field, errors)
    return _errors_sorted(errors)


def _result_statuses(results: object, errors: list[str]) -> dict[str, dict[str, object]]:
    if not isinstance(results, dict):
        errors.append("acceptance_results: must be an object keyed by acceptance ID")
        return {}
    normalized: dict[str, dict[str, object]] = {}
    for acceptance_id, value in results.items():
        path = f"acceptance_results.{acceptance_id}"
        item = _as_mapping(value, path, errors)
        if "status" not in item:
            errors.append(f"{path}.status: missing required field")
        elif (
            not isinstance(item.get("status"), str)
            or item.get("status") not in ACCEPTANCE_STATUSES
        ):
            errors.append(f"{path}.status: must be PASS, FAIL, or UNVERIFIED")
        if "evidence" not in item:
            errors.append(f"{path}.evidence: missing required field")
        elif not _is_nonempty_string(item.get("evidence")):
            errors.append(f"{path}.evidence: must be a non-empty string")
        _reject_unknown_fields(
            item,
            ("status", "evidence"),
            errors,
            path=path,
        )
        normalized[str(acceptance_id)] = item
    return normalized


def _finding_requests_code_change(required_change: object) -> bool:
    if isinstance(required_change, str):
        return "CODE_CHANGE" in required_change
    if isinstance(required_change, dict):
        return any(
            isinstance(value, str) and "CODE_CHANGE" in value
            for value in required_change.values()
        )
    return False


def derive_root_cause_fingerprint(finding: dict[str, object]) -> str:
    """Derive the controller-owned root-cause fingerprint from Pro source fields."""
    return canonical_digest(
        {
            "acceptance_id": finding.get("acceptance_id"),
            "category": finding.get("category"),
            "required_action": finding.get("required_action"),
            "root_cause_key": finding.get("root_cause_key"),
        }
    )


def derive_root_cause_route_fingerprint(finding: dict[str, object]) -> str:
    """Derive a rename-resistant continuity key for one acceptance route."""
    return canonical_digest(
        {
            "acceptance_id": finding.get("acceptance_id"),
            "category": finding.get("category"),
            "required_action": finding.get("required_action"),
        }
    )


def validate_review(packet, requirements, report):
    """Return all deterministic review-packet validation errors."""
    errors: list[str] = []
    review = _as_mapping(packet, "packet", errors)
    req = _as_mapping(requirements, "requirements", errors)
    implementation_report = _as_mapping(report, "report", errors)
    errors.extend(
        f"requirements.{error}"
        for error in _validate_requirements(req, require_initial=False)
    )
    for report_error in validate_report(implementation_report, req):
        if not report_error.startswith("requirements."):
            errors.append(f"report.{report_error}")
    _require_fields(review, REQUIRED_REVIEW_FIELDS, errors)
    _reject_unknown_fields(review, REQUIRED_REVIEW_FIELDS, errors)
    _require_schema_version(review, errors)
    requirements_digest = _canonical_digest_checked(
        req,
        "requirements",
        errors,
    )
    if (
        requirements_digest is not None
        and review.get("requirements_digest") != requirements_digest
    ):
        errors.append("requirements_digest: does not match requirements digest")
    if review.get("reviewed_snapshot_digest") != implementation_report.get("snapshot_digest"):
        errors.append("reviewed_snapshot_digest: does not match report snapshot_digest")
    if (
        not isinstance(review.get("decision"), str)
        or review.get("decision") not in REVIEW_DECISIONS
    ):
        errors.append("decision: must be PASS, CHANGES_REQUESTED, or BLOCK")
    acceptance_ids = _acceptance_ids(req, errors)
    results = _result_statuses(review.get("acceptance_results"), errors)
    for acceptance_id in acceptance_ids:
        if acceptance_id not in results:
            errors.append(f"acceptance_results.{acceptance_id}: missing acceptance result")
    for acceptance_id in results:
        if acceptance_id not in acceptance_ids:
            errors.append(f"acceptance_results.{acceptance_id}: unknown acceptance ID")
    if review.get("decision") == "PASS" and any(
        result.get("status") != "PASS" for result in results.values()
    ):
        errors.append("decision: PASS requires every acceptance result to be PASS")

    findings = _require_list(review, "findings", errors)
    if review.get("decision") == "PASS" and findings:
        errors.append("decision: PASS requires findings to be empty")
    seen_finding_ids: set[str] = set()
    for index, finding_value in enumerate(findings):
        path = f"findings.{index}"
        finding = _as_mapping(finding_value, path, errors)
        for field in (
            "id",
            "acceptance_id",
            "root_cause_key",
            "severity",
            "category",
            "required_action",
            "evidence",
        ):
            if field not in finding:
                errors.append(f"{path}.{field}: missing required field")
            elif not _is_nonempty_string(finding[field]):
                errors.append(f"{path}.{field}: must be a non-empty string")
        _reject_unknown_fields(
            finding,
            (
                "id",
                "acceptance_id",
                "root_cause_key",
                "severity",
                "category",
                "required_action",
                "evidence",
                "required_change",
            ),
            errors,
            path=path,
        )
        finding_id = finding.get("id")
        if _is_nonempty_string(finding_id):
            if finding_id in seen_finding_ids:
                errors.append(f"{path}.id: duplicate stable ID {finding_id}")
            seen_finding_ids.add(finding_id)
        if (
            not isinstance(finding.get("severity"), str)
            or finding.get("severity") not in FINDING_SEVERITIES
        ):
            errors.append(f"{path}.severity: must be BLOCKER, HIGH, MEDIUM, or LOW")
        acceptance_id = finding.get("acceptance_id")
        if (
            isinstance(acceptance_id, str)
            and acceptance_id not in acceptance_ids
        ):
            errors.append(f"{path}.acceptance_id: unknown acceptance ID")
        action = finding.get("required_action")
        if not isinstance(action, str) or action not in REQUIRED_ACTIONS:
            errors.append(f"{path}.required_action: invalid required action")
        if action == "PROVIDE_EVIDENCE" and _finding_requests_code_change(finding.get("required_change")):
            errors.append(f"{path}.required_change: PROVIDE_EVIDENCE cannot request a code change")
        if review.get("decision") == "PASS" and finding.get("severity") == "BLOCKER":
            errors.append("decision: PASS cannot leave a blocking finding")
    scope_violations = _require_list(review, "scope_violations", errors)
    if review.get("decision") == "PASS" and scope_violations:
        errors.append("decision: PASS requires scope_violations to be empty")
    _require_nonempty_string(review, "next_instruction", errors)
    return _errors_sorted(errors)


def validate_report_context(
    report,
    requirements,
    state,
    snapshot,
) -> list[str]:
    """Bind a local report to trusted active state and a captured snapshot.

    ``report`` and ``snapshot`` are local artifacts, while ``state`` is trusted
    controller state. This function does not make Browser payloads trusted.
    """
    errors = list(validate_report(report, requirements))
    implementation_report = _as_mapping(report, "report", errors)
    req = _as_mapping(requirements, "requirements", errors)
    trusted_state = _as_mapping(state, "state", errors)
    captured = _as_mapping(snapshot, "snapshot", errors)
    if isinstance(state, dict):
        _validate_state_fields(trusted_state, "state", errors)
        phase = _phase(trusted_state, "state", errors)
        if phase not in {"LOCAL_VERIFICATION", "REVIEW_PENDING"}:
            errors.append(
                "state.phase: report context requires LOCAL_VERIFICATION or REVIEW_PENDING"
            )

    if req.get("decision") != "PLAN_READY":
        errors.append("requirements: report requires PLAN_READY requirements")
    if (
        req.get("user_approval_required") is True
        and (
            req.get("user_approval_received") is not True
            or not isinstance(trusted_state.get("approval_sequence"), int)
            or isinstance(trusted_state.get("approval_sequence"), bool)
            or trusted_state.get("approval_sequence", 0) < 1
        )
    ):
        errors.append("requirements: required user approval is not recorded")
    if (
        trusted_state.get("active_requirements_revision")
        != req.get("requirements_revision")
    ):
        errors.append(
            "requirements_revision: does not match active trusted requirements"
        )
    requirements_digest = _canonical_digest_checked(
        req,
        "requirements",
        errors,
    )
    if (
        requirements_digest is not None
        and trusted_state.get("active_requirements_digest")
        != requirements_digest
    ):
        errors.append(
            "requirements_digest: does not match active trusted requirements"
        )
    if implementation_report.get("review_round") != trusted_state.get(
        "review_round"
    ):
        errors.append("review_round: does not match active workflow state")

    report_digest = _canonical_digest_checked(
        implementation_report,
        "report",
        errors,
    )
    if (
        report_digest is not None
        and trusted_state.get("active_report_digest") != report_digest
    ):
        errors.append("active_report_digest: does not match implementation report")

    _require_schema_version(captured, errors, path="snapshot")
    for field in (
        "baseline_head",
        "snapshot_digest",
        "tracked_diff_digest",
        "untracked_manifest_digest",
    ):
        if captured.get(field) != implementation_report.get(field):
            errors.append(
                f"snapshot.{field}: does not match implementation report"
            )
    if trusted_state.get("current_snapshot_digest") != captured.get(
        "snapshot_digest"
    ):
        errors.append(
            "current_snapshot_digest: does not match captured snapshot"
        )
    return _errors_sorted(errors)


def _review_required_actions(review: dict[str, object]) -> list[str]:
    findings = review.get("findings")
    if not isinstance(findings, list):
        return []
    return sorted(
        {
            action
            for finding in findings
            if isinstance(finding, dict)
            for action in (finding.get("required_action"),)
            if isinstance(action, str) and action in REQUIRED_ACTIONS
        }
    )


def _review_finding_history(
    review: dict[str, object],
) -> tuple[list[str], list[str]]:
    findings = review.get("findings")
    if not isinstance(findings, list):
        return [], []
    identifiers: list[str] = []
    fingerprints: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        identifier = finding.get("id")
        try:
            fingerprint = derive_root_cause_fingerprint(finding)
            route_fingerprint = derive_root_cause_route_fingerprint(finding)
        except (TypeError, ValueError):
            fingerprint = None
            route_fingerprint = None
        if isinstance(identifier, str):
            identifiers.append(identifier)
        if isinstance(fingerprint, str):
            fingerprints.append(fingerprint)
        if isinstance(route_fingerprint, str):
            fingerprints.append(route_fingerprint)
    return sorted(set(identifiers)), sorted(set(fingerprints))


def validate_review_context(
    envelope,
    requirements,
    report,
    state,
    snapshot,
) -> list[str]:
    """Bind one untrusted review envelope to its trusted local review state.

    The controller must record ``pending_review_envelope_digest`` only after
    ``validate_transport_envelope`` succeeds against the trusted send attempt
    and the complete consumed-digest set.
    """
    packet, errors = _validate_transport_envelope_shape(envelope)
    trusted_state = _as_mapping(state, "state", errors)
    if isinstance(state, dict):
        _validate_state_fields(trusted_state, "state", errors)
        phase = _phase(trusted_state, "state", errors)
        if phase != "REVIEW_PENDING":
            errors.append("state.phase: review context requires REVIEW_PENDING")
    payload = _as_mapping(packet.get("payload"), "payload", errors)
    if packet.get("packet_type") != "review":
        errors.append("packet_type: review context requires a review envelope")

    errors.extend(
        validate_report_context(report, requirements, trusted_state, snapshot)
    )
    errors.extend(validate_review(payload, requirements, report))

    envelope_digest = _canonical_digest_checked(packet, "envelope", errors)
    pending_digest = trusted_state.get("pending_review_envelope_digest")
    if (
        envelope_digest is None
        or pending_digest is None
        or pending_digest != envelope_digest
    ):
        errors.append(
            "pending_review_envelope_digest: review envelope was not prevalidated"
        )
    if pending_digest is not None and (
        pending_digest == trusted_state.get("last_consumed_packet_digest")
        or pending_digest
        == trusted_state.get("last_consumed_review_envelope_digest")
    ):
        errors.append(
            "pending_review_envelope_digest: review envelope is not fresh"
        )
    if packet.get("previous_packet_digest") != trusted_state.get(
        "last_consumed_packet_digest"
    ):
        errors.append(
            "previous_packet_digest: does not match the trusted packet chain"
        )
    _require_digest(
        trusted_state.get("last_consumed_packet_digest"),
        "state.last_consumed_packet_digest",
        errors,
    )

    review_digest = _canonical_digest_checked(payload, "review", errors)
    if (
        review_digest is not None
        and trusted_state.get("active_review_packet_digest") != review_digest
    ):
        errors.append(
            "active_review_packet_digest: does not match validated review payload"
        )
    if trusted_state.get("reviewed_snapshot_digest") != payload.get(
        "reviewed_snapshot_digest"
    ):
        errors.append(
            "reviewed_snapshot_digest: does not match trusted review state"
        )
    if trusted_state.get("latest_decision") != payload.get("decision"):
        errors.append(
            "latest_decision: does not match the validated review payload"
        )
    state_actions = trusted_state.get("required_actions")
    if (
        not isinstance(state_actions, list)
        or any(not isinstance(action, str) for action in state_actions)
        or sorted(set(state_actions)) != _review_required_actions(payload)
    ):
        errors.append(
            "required_actions: do not match the validated review payload"
        )
    finding_ids, finding_fingerprints = _review_finding_history(payload)
    if sorted(_finding_ids(trusted_state)) != finding_ids:
        errors.append(
            "unresolved_finding_ids: do not match the validated review payload"
        )
    if sorted(_fingerprints(trusted_state)) != finding_fingerprints:
        errors.append(
            "blocker_fingerprints: do not match the validated review payload"
        )
    return _errors_sorted(errors)


def validate_final_gate(evidence, state) -> list[str]:
    """Validate explicit completion evidence against trusted local state."""
    errors: list[str] = []
    gate = _as_mapping(evidence, "final_gate", errors)
    trusted_state = _as_mapping(state, "state", errors)
    if isinstance(state, dict):
        _validate_state_fields(trusted_state, "state", errors)
        _phase(trusted_state, "state", errors)
    _require_fields(gate, FINAL_GATE_FIELDS, errors)
    _reject_unknown_fields(gate, FINAL_GATE_FIELDS, errors)
    _require_schema_version(gate, errors)
    digest_bindings = (
        ("requirements_digest", "active_requirements_digest"),
        ("review_packet_digest", "active_review_packet_digest"),
        ("reviewed_snapshot_digest", "reviewed_snapshot_digest"),
        ("current_snapshot_digest", "current_snapshot_digest"),
    )
    for evidence_field, state_field in digest_bindings:
        _require_digest(gate.get(evidence_field), evidence_field, errors)
        if gate.get(evidence_field) != trusted_state.get(state_field):
            errors.append(
                f"{evidence_field}: does not match trusted {state_field}"
            )
    for field in (
        "acceptance_gate_passed",
        "local_checks_passed",
        "scope_gate_passed",
        "artifact_hygiene_passed",
    ):
        if gate.get(field) is not True:
            errors.append(f"{field}: must be JSON boolean true")
    if gate.get("reviewed_snapshot_digest") != gate.get(
        "current_snapshot_digest"
    ):
        errors.append(
            "current_snapshot_digest: must equal the reviewed snapshot digest"
        )
    if trusted_state.get("phase") != "FINAL_VERIFICATION":
        errors.append("state.phase: final gate requires FINAL_VERIFICATION")
    if trusted_state.get("latest_decision") != "PASS":
        errors.append("state.latest_decision: final gate requires validated PASS")
    if trusted_state.get("required_actions") != []:
        errors.append("state.required_actions: final gate requires no pending actions")
    _require_digest(
        trusted_state.get("active_report_digest"),
        "state.active_report_digest",
        errors,
    )
    if trusted_state.get("pending_review_envelope_digest") is not None:
        errors.append(
            "state.pending_review_envelope_digest: final gate requires consumed review identity"
        )
    if (
        trusted_state.get("last_consumed_review_envelope_digest") is None
        or trusted_state.get("last_consumed_review_envelope_digest")
        != trusted_state.get("last_consumed_packet_digest")
    ):
        errors.append(
            "state.last_consumed_review_envelope_digest: final gate requires the active consumed review"
        )
    return _errors_sorted(errors)


def _phase(value: object, name: str, errors: list[str]) -> str | None:
    if not isinstance(value, dict):
        errors.append(f"{name}: must be a state object")
        return None
    phase = value.get("phase")
    if not isinstance(phase, str) or phase not in STATE_TRANSITIONS:
        errors.append(f"{name}.phase: unknown workflow phase")
        return None
    return phase


def _state_mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _has_pending_requirements_provenance(state: dict[str, object]) -> bool:
    return (
        any(
            state.get(field) is not None
            for field in (
                "pending_requirements_revision",
                "pending_requirements_digest",
                "pending_supersedes_digest",
                "pending_approval_sequence",
                "pending_approved_requirements_digest",
                "pending_user_approval_evidence",
            )
        )
        or any(state.get(field) is True for field in MATERIAL_REVISION_FLAGS)
    )


def _validate_conversation_binding(
    state: dict[str, object], name: str, errors: list[str]
) -> bool:
    fields = (
        "conversation_binding_state",
        "bound_conversation_url",
        "model_policy",
        "requested_model_label",
        "visible_model_label",
    )
    if any(field not in state for field in fields):
        return False
    complete = True
    binding_state = state.get("conversation_binding_state")
    if (
        not isinstance(binding_state, str)
        or binding_state
        not in {"CONVERSATION_UNBOUND", "CONVERSATION_BOUND"}
    ):
        errors.append(
            f"{name}.conversation_binding_state: must be CONVERSATION_UNBOUND or CONVERSATION_BOUND"
        )
        return False
    if binding_state == "CONVERSATION_UNBOUND":
        for field in ("bound_conversation_url", "visible_model_label"):
            if state.get(field) is not None:
                errors.append(f"{name}.{field}: must be null before conversation binding")
                complete = False
    else:
        for field in ("bound_conversation_url", "visible_model_label"):
            if not _is_nonempty_string(state.get(field)):
                errors.append(f"{name}.{field}: must be a non-empty string after binding")
                complete = False
    model_policy = state.get("model_policy")
    requested_label = state.get("requested_model_label")
    visible_label = state.get("visible_model_label")
    if model_policy not in {"PRO_CLASS", "EXACT_LABEL"}:
        errors.append(f"{name}.model_policy: must be PRO_CLASS or EXACT_LABEL")
        complete = False
    elif model_policy == "PRO_CLASS":
        if requested_label is not None:
            errors.append(
                f"{name}.requested_model_label: must be null for PRO_CLASS"
            )
            complete = False
        if (
            binding_state == "CONVERSATION_BOUND"
            and visible_label != "Pro"
        ):
            errors.append(
                f"{name}.visible_model_label: must equal the controlled Pro-class label Pro"
            )
            complete = False
    elif not _is_nonempty_string(requested_label):
        errors.append(
            f"{name}.requested_model_label: must be a non-empty string for EXACT_LABEL"
        )
        complete = False
    elif (
        binding_state == "CONVERSATION_BOUND"
        and visible_label != requested_label
    ):
        errors.append(
            f"{name}.visible_model_label: must exactly match requested_model_label"
        )
        complete = False
    return complete


def _validate_state_fields(
    state: dict[str, object], name: str, errors: list[str]
) -> None:
    for field in REQUIRED_STATE_FIELDS:
        if field not in state:
            errors.append(f"{name}.{field}: missing required field")
    _reject_unknown_fields(
        state,
        (*REQUIRED_STATE_FIELDS, *OPTIONAL_STATE_FIELDS),
        errors,
        path=name,
    )
    _require_schema_version(state, errors, path=name)
    requirements_decision = state.get("latest_requirements_decision")
    if (
        "latest_requirements_decision" in state
        and requirements_decision is not None
        and (
            not isinstance(requirements_decision, str)
            or requirements_decision not in REQUIREMENTS_DECISIONS
        )
    ):
        errors.append(
            f"{name}.latest_requirements_decision: must be PLAN_READY, NEED_USER_INPUT, BLOCK, or null"
        )
    actions = state.get("required_actions")
    if "required_actions" in state and (
        not isinstance(actions, list)
        or any(not _is_nonempty_string(action) for action in actions)
        or not set(actions) <= REQUIRED_ACTIONS
    ):
        errors.append(
            f"{name}.required_actions: must be a list of valid required actions"
        )
    for field in ("format_error_count", "browser_reconnect_count"):
        value = state.get(field)
        if field in state and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            errors.append(f"{name}.{field}: must be a non-negative integer")
    for field in MATERIAL_REVISION_FLAGS:
        if field in state and not isinstance(state.get(field), bool):
            errors.append(f"{name}.{field}: must be a boolean")
    for field in (
        "active_requirements_revision",
        "pending_requirements_revision",
    ):
        value = state.get(field)
        if field in state and value is not None and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
        ):
            errors.append(f"{name}.{field}: must be a positive integer or null")
    approval_sequence = state.get("approval_sequence")
    if "approval_sequence" in state and (
        not isinstance(approval_sequence, int)
        or isinstance(approval_sequence, bool)
        or approval_sequence < 0
    ):
        errors.append(f"{name}.approval_sequence: must be a non-negative integer")
    pending_approval_sequence = state.get("pending_approval_sequence")
    if "pending_approval_sequence" in state and (
        pending_approval_sequence is not None
        and (
            not isinstance(pending_approval_sequence, int)
            or isinstance(pending_approval_sequence, bool)
            or pending_approval_sequence < 1
        )
    ):
        errors.append(
            f"{name}.pending_approval_sequence: must be a positive integer or null"
        )
    for field in (
        "active_requirements_digest",
        "pending_requirements_digest",
        "pending_supersedes_digest",
        "pending_approved_requirements_digest",
        "pending_requirements_envelope_digest",
        "pending_review_envelope_digest",
        "last_consumed_packet_digest",
        "last_consumed_review_envelope_digest",
        "active_report_digest",
        "current_snapshot_digest",
        "active_review_packet_digest",
        "reviewed_snapshot_digest",
    ):
        if field in state:
            _require_digest(
                state.get(field),
                f"{name}.{field}",
                errors,
                nullable=True,
            )
    blocker_fingerprints = state.get("blocker_fingerprints")
    if "blocker_fingerprints" in state and (
        not isinstance(blocker_fingerprints, list)
        or any(
            not isinstance(fingerprint, str)
            or not DIGEST_PATTERN.fullmatch(fingerprint)
            for fingerprint in blocker_fingerprints
        )
    ):
        errors.append(
            f"{name}.blocker_fingerprints: must be a list of lowercase sha256 digests"
        )
    unresolved_ids = state.get("unresolved_finding_ids")
    if "unresolved_finding_ids" in state and (
        not isinstance(unresolved_ids, list)
        or any(not _is_nonempty_string(identifier) for identifier in unresolved_ids)
    ):
        errors.append(
            f"{name}.unresolved_finding_ids: must be a list of strings"
        )
    active_review_digest = state.get("active_review_packet_digest")
    reviewed_snapshot_digest = state.get("reviewed_snapshot_digest")
    if (active_review_digest is None) != (reviewed_snapshot_digest is None):
        errors.append(
            f"{name}.active_review: review packet and reviewed snapshot digests must both be set or null"
        )
    if (
        state.get("phase") != "REQUIREMENTS_PENDING"
        and state.get("pending_requirements_envelope_digest") is not None
    ):
        errors.append(
            f"{name}.pending_requirements_envelope_digest: is allowed only while requirements are pending"
        )
    if (
        state.get("phase") != "REVIEW_PENDING"
        and state.get("pending_review_envelope_digest") is not None
    ):
        errors.append(
            f"{name}.pending_review_envelope_digest: is allowed only while review is pending"
        )
    active_revision = state.get("active_requirements_revision")
    active_digest = state.get("active_requirements_digest")
    if (
        "active_requirements_revision" in state
        and "active_requirements_digest" in state
        and (active_revision is None) != (active_digest is None)
    ):
        errors.append(
            f"{name}.active_requirements: revision and digest must both be set or null"
        )
    if state.get("phase") == "PREFLIGHT":
        if active_revision is not None or active_digest is not None:
            errors.append(
                f"{name}.active_requirements: must be null during preflight"
            )
    elif (
        not isinstance(active_revision, int)
        or isinstance(active_revision, bool)
        or active_revision < 1
        or not isinstance(active_digest, str)
        or not DIGEST_PATTERN.fullmatch(active_digest)
    ):
        errors.append(
            f"{name}.active_requirements: revision and digest are required after preflight"
        )
    pending_revision = state.get("pending_requirements_revision")
    pending_digest = state.get("pending_requirements_digest")
    if (
        "pending_requirements_revision" in state
        and "pending_requirements_digest" in state
        and (pending_revision is None) != (pending_digest is None)
    ):
        errors.append(
            f"{name}.pending_requirements: revision and digest must both be set or null"
        )
    if (
        pending_revision is None
        and state.get("pending_supersedes_digest") is not None
    ):
        errors.append(
            f"{name}.pending_supersedes_digest: must be null without pending requirements"
        )
    pending_approval_values = (
        pending_approval_sequence,
        state.get("pending_approved_requirements_digest"),
        state.get("pending_user_approval_evidence"),
    )
    if any(value is not None for value in pending_approval_values) and not all(
        value is not None for value in pending_approval_values
    ):
        errors.append(
            f"{name}.pending_approval: sequence, approved digest, and evidence must all be set or null"
        )
    pending_approval_evidence = state.get("pending_user_approval_evidence")
    if (
        "pending_user_approval_evidence" in state
        and pending_approval_evidence is not None
        and not _is_nonempty_string(pending_approval_evidence)
    ):
        errors.append(
            f"{name}.pending_user_approval_evidence: must be a non-empty string or null"
        )
    if (
        state.get("phase") == "REQUIREMENTS_PENDING"
        and state.get("user_approval_received") is True
        and not all(value is not None for value in pending_approval_values)
    ):
        errors.append(
            f"{name}.pending_approval: explicit user approval requires bound approval provenance"
        )
    if (
        all(value is not None for value in pending_approval_values)
        and state.get("user_approval_received") is not True
    ):
        errors.append(
            f"{name}.user_approval_received: bound approval provenance requires explicit approval"
        )
    if (
        state.get("scope_changed") is True
        or state.get("public_contract_changed") is True
    ) and state.get("behavior_changed") is not True:
        errors.append(
            f"{name}.behavior_changed: material scope or public-contract changes require behavior_changed"
        )
    if (
        state.get("phase") != "REQUIREMENTS_PENDING"
        and _has_pending_requirements_provenance(state)
    ):
        errors.append(
            f"{name}.pending_requirements: revision provenance is allowed only while requirements are pending"
        )
    stop_origin_phase = state.get("stop_origin_phase")
    if (
        "stop_origin_phase" in state
        and stop_origin_phase is not None
        and (
            not isinstance(stop_origin_phase, str)
            or stop_origin_phase not in STATE_TRANSITIONS
        )
    ):
        errors.append(
            f"{name}.stop_origin_phase: must be a workflow phase or null"
        )
    stop_origin_category = state.get("stop_origin_category")
    if (
        "stop_origin_category" in state
        and stop_origin_category is not None
        and (
            not isinstance(stop_origin_category, str)
            or stop_origin_category not in STOP_ORIGIN_CATEGORIES
        )
    ):
        errors.append(
            f"{name}.stop_origin_category: must be a valid stop category or null"
        )
    for field in ("stop_reason", "resolution_evidence"):
        value = state.get(field)
        if (
            field in state
            and value is not None
            and not _is_nonempty_string(value)
        ):
            errors.append(f"{name}.{field}: must be a non-empty string or null")
    stop_sequence = state.get("stop_sequence")
    if "stop_sequence" in state and (
        not isinstance(stop_sequence, int)
        or isinstance(stop_sequence, bool)
        or stop_sequence < 0
    ):
        errors.append(f"{name}.stop_sequence: must be a non-negative integer")
    resolution_stop_sequence = state.get("resolution_stop_sequence")
    if "resolution_stop_sequence" in state and (
        resolution_stop_sequence is not None
        and (
            not isinstance(resolution_stop_sequence, int)
            or isinstance(resolution_stop_sequence, bool)
            or resolution_stop_sequence < 1
        )
    ):
        errors.append(
            f"{name}.resolution_stop_sequence: must be a positive integer or null"
        )
    if (
        "resolution_evidence" in state
        and "resolution_stop_sequence" in state
        and (state.get("resolution_evidence") is None)
        != (resolution_stop_sequence is None)
    ):
        errors.append(
            f"{name}.resolution: evidence and stop sequence must both be set or null"
        )


def _state_string_set(state: dict[str, object], field: str) -> set[str]:
    values = state.get(field)
    if not isinstance(values, list):
        return set()
    return {value for value in values if _is_nonempty_string(value)}


def _validate_state_string_list(
    state: dict[str, object], name: str, field: str, errors: list[str]
) -> bool:
    values = state.get(field)
    valid = isinstance(values, list) and all(
        _is_nonempty_string(value) for value in values
    )
    if not valid:
        errors.append(f"{name}.{field}: must be a list of strings")
        return False
    return True


def _finding_ids(state: dict[str, object]) -> set[str]:
    return _state_string_set(state, "unresolved_finding_ids")


def _fingerprints(state: dict[str, object]) -> set[str]:
    return _state_string_set(state, "blocker_fingerprints")


def _expected_review_target(state: dict[str, object], errors: list[str]) -> str | None:
    decision = state.get("latest_decision")
    if decision == "PASS":
        return "FINAL_VERIFICATION"
    if decision == "BLOCK":
        return "USER_DECISION_REQUIRED"
    if decision != "CHANGES_REQUESTED":
        return None
    actions = state.get("required_actions")
    if (
        not isinstance(actions, list)
        or not actions
        or any(not _is_nonempty_string(action) for action in actions)
    ):
        errors.append("required_actions: CHANGES_REQUESTED requires at least one valid action")
        return None
    action_set = set(actions)
    if not action_set <= REQUIRED_ACTIONS:
        errors.append("required_actions: contains an invalid required action")
        return None
    if "USER_DECISION" in action_set:
        return "USER_DECISION_REQUIRED"
    if "REQUIREMENTS_REVISION" in action_set:
        return "REQUIREMENTS_PENDING"
    if action_set & {"CODE_CHANGE", "TEST_CHANGE"}:
        return "IMPLEMENTING"
    if action_set == {"PROVIDE_EVIDENCE"}:
        return "LOCAL_VERIFICATION"
    return None


def _expected_requirements_target(
    state: dict[str, object], errors: list[str]
) -> str | None:
    decision = state.get("latest_requirements_decision")
    targets = {
        "PLAN_READY": "REQUIREMENTS_FROZEN",
        "NEED_USER_INPUT": "USER_DECISION_REQUIRED",
        "BLOCK": "BLOCKED",
    }
    target = targets.get(decision) if isinstance(decision, str) else None
    if target is None:
        errors.append(
            "latest_requirements_decision: a requirements transition requires PLAN_READY, NEED_USER_INPUT, or BLOCK"
        )
    return target


def _expected_stop_category(
    previous_phase: str,
    current_phase: str,
    current_state: dict[str, object],
) -> str | None:
    if previous_phase == "REQUIREMENTS_PENDING":
        decision = current_state.get("latest_requirements_decision")
        if decision == "NEED_USER_INPUT" and current_phase == "USER_DECISION_REQUIRED":
            return "REQUIREMENTS_NEED_USER_INPUT"
        if decision == "BLOCK" and current_phase == "BLOCKED":
            return "REQUIREMENTS_BLOCK"
    if previous_phase == "REVIEW_PENDING" and current_phase == "USER_DECISION_REQUIRED":
        decision = current_state.get("latest_decision")
        actions = current_state.get("required_actions")
        if (
            decision == "CHANGES_REQUESTED"
            and isinstance(actions, list)
            and "USER_DECISION" in actions
        ):
            return "REVIEW_USER_DECISION"
        if decision == "BLOCK":
            return "REVIEW_BLOCK"
    if previous_phase == "FINAL_VERIFICATION" and current_phase == "BLOCKED":
        return "FINAL_VERIFICATION_BLOCK"
    return None


def _validate_stop_state_shape(
    state: dict[str, object],
    name: str,
    errors: list[str],
) -> None:
    phase = state.get("phase")
    provenance = (
        state.get("stop_origin_phase"),
        state.get("stop_origin_category"),
        state.get("stop_reason"),
    )
    if isinstance(phase, str) and phase in STOP_PHASES:
        if state.get("stop_origin_phase") is None:
            errors.append(f"{name}.stop_origin_phase: stop state requires an origin")
        if state.get("stop_origin_category") is None:
            errors.append(f"{name}.stop_origin_category: stop state requires a category")
        if not _is_nonempty_string(state.get("stop_reason")):
            errors.append(f"{name}.stop_reason: stop state requires a reason")
        if state.get("resolution_evidence") is not None:
            errors.append(
                f"{name}.resolution_evidence: unresolved stop state must be null"
            )
        if state.get("resolution_stop_sequence") is not None:
            errors.append(
                f"{name}.resolution_stop_sequence: unresolved stop state must be null"
            )
    elif any(value is not None for value in provenance):
        errors.append(
            f"{name}.stop_provenance: origin phase, category, and reason are allowed only in stop states"
        )


def _validate_stop_entry(
    previous_phase: str,
    current_phase: str,
    previous_state: dict[str, object],
    current_state: dict[str, object],
    errors: list[str],
) -> None:
    expected_category = _expected_stop_category(
        previous_phase,
        current_phase,
        current_state,
    )
    if current_state.get("stop_origin_phase") != previous_phase:
        errors.append(
            "stop_origin_phase: must match the actual stop origin "
            f"{previous_phase}"
        )
    if (
        expected_category is None
        or current_state.get("stop_origin_category") != expected_category
    ):
        errors.append("stop_origin_category: does not match the stop route")
    if not _is_nonempty_string(current_state.get("stop_reason")):
        errors.append("stop_reason: stop entry requires a non-empty reason")
    if current_state.get("resolution_evidence") is not None:
        errors.append(
            "resolution_evidence: must be null when entering a stop state"
        )
    previous_sequence = previous_state.get("stop_sequence")
    if (
        not isinstance(previous_sequence, int)
        or isinstance(previous_sequence, bool)
        or current_state.get("stop_sequence") != previous_sequence + 1
    ):
        errors.append("stop_sequence: stop entry must increment exactly once")
    if current_state.get("resolution_stop_sequence") is not None:
        errors.append(
            "resolution_stop_sequence: must be null when entering a stop state"
        )


def _resume_target_description(targets: tuple[str, ...]) -> str:
    if len(targets) == 1:
        return targets[0]
    return " or ".join(targets)


def _validate_stop_resume(
    previous_phase: str,
    current_phase: str,
    previous_state: dict[str, object],
    current_state: dict[str, object],
    errors: list[str],
) -> None:
    category = previous_state.get("stop_origin_category")
    targets = STOP_RESUME_TARGETS.get(category) if isinstance(category, str) else None
    expected_origin = (
        STOP_CATEGORY_ORIGINS.get(category) if isinstance(category, str) else None
    )
    expected_stop_phase = (
        STOP_CATEGORY_PHASES.get(category) if isinstance(category, str) else None
    )
    if targets is None:
        errors.append("stop_origin_category: stop resume requires a valid category")
    else:
        if current_phase not in targets:
            errors.append(
                f"phase: {category} stop may resume only to "
                f"{_resume_target_description(targets)}, not {current_phase}"
            )
        if previous_state.get("stop_origin_phase") != expected_origin:
            errors.append("stop_origin_phase: does not match the stop category")
        if previous_phase != expected_stop_phase:
            errors.append("stop_origin_category: does not match the stop phase")
    if not _is_nonempty_string(previous_state.get("stop_reason")):
        errors.append("stop_reason: stop resume requires the recorded reason")
    if not _is_nonempty_string(current_state.get("resolution_evidence")):
        errors.append(
            "resolution_evidence: stop resume requires explicit resolution evidence"
        )
    if (
        current_state.get("resolution_stop_sequence")
        != previous_state.get("stop_sequence")
    ):
        errors.append(
            "resolution_stop_sequence: must match the current stop sequence"
        )
    if current_state.get("stop_sequence") != previous_state.get("stop_sequence"):
        errors.append("stop_sequence: stop resume must preserve the stop sequence")
    if any(
        current_state.get(field) is not None
        for field in (
            "stop_origin_phase",
            "stop_origin_category",
            "stop_reason",
        )
    ):
        errors.append(
            "stop_provenance: resume must consume origin phase, category, and reason"
        )
    if (
        isinstance(category, str)
        and category in {"REQUIREMENTS_NEED_USER_INPUT", "REQUIREMENTS_BLOCK"}
        and current_state.get("latest_requirements_decision") is not None
    ):
        errors.append(
            "latest_requirements_decision: resume must clear the prior requirements decision"
        )
    if isinstance(category, str) and category in {
        "REVIEW_USER_DECISION",
        "REVIEW_BLOCK",
    }:
        if current_state.get("latest_decision") is not None:
            errors.append(
                "latest_decision: review-stop resume must clear the consumed decision"
            )
        if current_state.get("required_actions") != []:
            errors.append(
                "required_actions: review-stop resume must clear consumed actions"
            )
        if current_state.get("pending_review_envelope_digest") is not None:
            errors.append(
                "pending_review_envelope_digest: review-stop resume must clear pending review identity"
            )


def _validate_resolution_lifecycle(
    previous_phase: str,
    current_phase: str,
    previous_state: dict[str, object],
    current_state: dict[str, object],
    errors: list[str],
) -> None:
    if previous_phase in STOP_PHASES:
        return
    current_resolution = (
        current_state.get("resolution_evidence"),
        current_state.get("resolution_stop_sequence"),
    )
    if current_resolution == (None, None):
        return
    if (
        previous_state.get("resolution_evidence") is not None
        or previous_state.get("resolution_stop_sequence") is not None
    ):
        errors.append(
            "resolution_evidence: must be cleared after the resumed transition"
        )
    elif current_phase not in STOP_PHASES:
        errors.append(
            "resolution_evidence: is allowed only on the immediate stop resume"
        )


def _validate_requirements_promotion(
    previous_state: dict[str, object],
    current_state: dict[str, object],
    previous_round: object,
    current_round: object,
    errors: list[str],
) -> tuple[bool, bool]:
    pending_fields = (
        "pending_requirements_revision",
        "pending_requirements_digest",
        "pending_supersedes_digest",
    )
    pending_approval_fields = (
        "pending_approval_sequence",
        "pending_approved_requirements_digest",
        "pending_user_approval_evidence",
    )
    pending_present = any(
        previous_state.get(field) is not None for field in pending_fields
    )
    reset_attempt = (
        previous_state.get("review_round_reset") is True
        or current_state.get("review_round_reset") is True
        or any(previous_state.get(field) is True for field in MATERIAL_RESET_SIGNALS)
        or any(current_state.get(field) is True for field in MATERIAL_RESET_SIGNALS)
        or (
            isinstance(previous_round, int)
            and not isinstance(previous_round, bool)
            and isinstance(current_round, int)
            and not isinstance(current_round, bool)
            and current_round != previous_round
        )
    )
    promotion_attempt = (
        pending_present
        or reset_attempt
        or previous_state.get("prior_evidence_invalidated") is True
        or any(current_state.get(field) is True for field in MATERIAL_REVISION_FLAGS)
    )
    if not promotion_attempt:
        return False, False

    active_revision = previous_state.get("active_requirements_revision")
    pending_revision = previous_state.get("pending_requirements_revision")
    if (
        not isinstance(active_revision, int)
        or isinstance(active_revision, bool)
        or pending_revision != active_revision + 1
    ):
        errors.append(
            "pending_requirements_revision: material reset requires the next requirements revision"
        )
    active_digest = previous_state.get("active_requirements_digest")
    pending_digest = previous_state.get("pending_requirements_digest")
    if (
        not isinstance(pending_digest, str)
        or not DIGEST_PATTERN.fullmatch(pending_digest)
        or pending_digest == active_digest
    ):
        errors.append(
            "pending_requirements_digest: material reset requires a new requirements digest"
        )
    if previous_state.get("pending_supersedes_digest") != active_digest:
        errors.append(
            "pending_supersedes_digest: must equal the active requirements digest"
        )
    if current_state.get("active_requirements_revision") != pending_revision:
        errors.append(
            "active_requirements_revision: frozen state must promote the pending revision"
        )
    if current_state.get("active_requirements_digest") != pending_digest:
        errors.append(
            "active_requirements_digest: frozen state must promote the pending digest"
        )
    for field in pending_fields:
        if current_state.get(field) is not None:
            errors.append(
                f"{field}: frozen state must consume pending requirements provenance"
            )
    for field in pending_approval_fields:
        if current_state.get(field) is not None:
            errors.append(
                f"{field}: frozen state must consume pending approval provenance"
            )
    for field in MATERIAL_REVISION_FLAGS:
        if current_state.get(field) is not False:
            errors.append(
                f"{field}: frozen state must consume pending revision flags"
            )

    if reset_attempt:
        actions = previous_state.get("required_actions")
        if (
            not isinstance(actions, list)
            or "REQUIREMENTS_REVISION" not in actions
        ):
            errors.append(
                "required_actions: material reset requires prior REQUIREMENTS_REVISION routing"
            )
        if not any(
            previous_state.get(field) is True
            for field in MATERIAL_CHANGE_FIELDS
        ):
            errors.append(
                "behavior_changed: material reset requires a behavior, scope, or public-contract change"
            )
        if (
            previous_state.get("scope_changed") is True
            or previous_state.get("public_contract_changed") is True
        ) and previous_state.get("behavior_changed") is not True:
            errors.append(
                "behavior_changed: material scope or public-contract changes require behavior_changed"
            )
        if previous_state.get("user_approval_required") is not True:
            errors.append(
                "user_approval_required: material reset requires user approval"
            )
        if previous_state.get("user_approval_received") is not True:
            errors.append(
                "user_approval_received: material reset requires explicit user approval"
            )
        active_approval_sequence = previous_state.get("approval_sequence")
        pending_approval_sequence = previous_state.get(
            "pending_approval_sequence"
        )
        if (
            not isinstance(active_approval_sequence, int)
            or isinstance(active_approval_sequence, bool)
            or pending_approval_sequence != active_approval_sequence + 1
        ):
            errors.append(
                "pending_approval_sequence: material reset requires a fresh approval event"
            )
        if (
            previous_state.get("pending_approved_requirements_digest")
            != pending_digest
        ):
            errors.append(
                "pending_approved_requirements_digest: must equal the pending requirements digest"
            )
        if not _is_nonempty_string(
            previous_state.get("pending_user_approval_evidence")
        ):
            errors.append(
                "pending_user_approval_evidence: material reset requires explicit approval evidence"
            )
        if current_state.get("approval_sequence") != pending_approval_sequence:
            errors.append(
                "approval_sequence: frozen state must consume the pending approval event"
            )
        if previous_state.get("prior_evidence_invalidated") is not True:
            errors.append(
                "prior_evidence_invalidated: material reset must invalidate prior evidence"
            )
        if previous_state.get("review_round_reset") is not True:
            errors.append(
                "review_round_reset: material revision must require a reset"
            )
        if current_round != 0:
            errors.append(
                "review_round: approved material revision must reset the review round to zero"
            )
    elif (
        current_state.get("approval_sequence")
        != previous_state.get("approval_sequence")
    ):
        errors.append(
            "approval_sequence: non-material revision must preserve approval history"
        )
    return promotion_attempt, reset_attempt


def _validate_requirements_envelope_consumption(
    previous_state: dict[str, object],
    current_state: dict[str, object],
    errors: list[str],
) -> None:
    pending = previous_state.get("pending_requirements_envelope_digest")
    _require_digest(
        pending,
        "pending_requirements_envelope_digest",
        errors,
    )
    if pending == previous_state.get("last_consumed_packet_digest"):
        errors.append(
            "pending_requirements_envelope_digest: requirements response must be fresh"
        )
    if current_state.get("last_consumed_packet_digest") != pending:
        errors.append(
            "last_consumed_packet_digest: must consume the validated requirements envelope"
        )
    if current_state.get("pending_requirements_envelope_digest") is not None:
        errors.append(
            "pending_requirements_envelope_digest: must clear after requirements consumption"
        )


def _validate_review_envelope_consumption(
    previous_state: dict[str, object],
    current_state: dict[str, object],
    errors: list[str],
) -> None:
    pending = previous_state.get("pending_review_envelope_digest")
    _require_digest(
        pending,
        "pending_review_envelope_digest",
        errors,
    )
    _require_digest(
        previous_state.get("last_consumed_packet_digest"),
        "last_consumed_packet_digest",
        errors,
    )
    if (
        pending == previous_state.get("last_consumed_packet_digest")
        or pending
        == previous_state.get("last_consumed_review_envelope_digest")
    ):
        errors.append(
            "pending_review_envelope_digest: review response must be fresh"
        )
    if current_state.get("last_consumed_packet_digest") != pending:
        errors.append(
            "last_consumed_packet_digest: must consume the validated review envelope"
        )
    if current_state.get("last_consumed_review_envelope_digest") != pending:
        errors.append(
            "last_consumed_review_envelope_digest: must promote the validated review envelope"
        )
    if current_state.get("pending_review_envelope_digest") is not None:
        errors.append(
            "pending_review_envelope_digest: must clear after review consumption"
        )
    for field in ("active_review_packet_digest", "reviewed_snapshot_digest"):
        if previous_state.get(field) is None:
            errors.append(
                f"{field}: validated review context must bind this digest before consumption"
            )
        if current_state.get(field) != previous_state.get(field):
            errors.append(
                f"{field}: review consumption must preserve validated review context"
            )
    for field in ("active_report_digest", "current_snapshot_digest"):
        if current_state.get(field) != previous_state.get(field):
            errors.append(
                f"{field}: review consumption must preserve report context"
            )
    if current_state.get("latest_decision") != previous_state.get(
        "latest_decision"
    ):
        errors.append(
            "latest_decision: review consumption must use the validated pending decision"
        )
    if current_state.get("required_actions") != previous_state.get(
        "required_actions"
    ):
        errors.append(
            "required_actions: review consumption must use validated pending actions"
        )


def _validate_review_transition_context(
    context: object,
    state: dict[str, object],
    consumed_state: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(context, dict):
        return [
            "review_context: explicit composed context is required for review consumption"
        ]
    _require_fields(context, REVIEW_TRANSITION_CONTEXT_FIELDS, errors)
    _reject_unknown_fields(
        context,
        REVIEW_TRANSITION_CONTEXT_FIELDS,
        errors,
        path="review_context",
    )
    if errors:
        return _errors_sorted(errors)
    transport_errors = validate_transport_envelope(
        context["envelope"],
        context["expected"],
        context["consumed_digests"],
    )
    errors.extend(
        f"review_context.transport.{error}" for error in transport_errors
    )
    review_state = dict(state)
    for field in (
        "latest_decision",
        "required_actions",
        "unresolved_finding_ids",
        "blocker_fingerprints",
        "unresolved_findings",
    ):
        if field in consumed_state:
            review_state[field] = consumed_state[field]
        else:
            review_state.pop(field, None)
    review_errors = validate_review_context(
        context["envelope"],
        context["requirements"],
        context["report"],
        review_state,
        context["snapshot"],
    )
    errors.extend(f"review_context.{error}" for error in review_errors)
    consumed = context.get("consumed_digests")
    last_consumed = state.get("last_consumed_packet_digest")
    if (
        isinstance(consumed, (set, frozenset, list, tuple))
        and isinstance(last_consumed, str)
        and last_consumed not in consumed
    ):
        errors.append(
            "review_context.consumed_digests: must contain the trusted packet-chain head"
        )
    return _errors_sorted(errors)


def _validate_requirements_transition_context(
    context: object,
    previous_state: dict[str, object],
    current_state: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(context, dict):
        return [
            "requirements_context: explicit composed context is required for requirements consumption"
        ]
    _require_fields(context, REQUIREMENTS_TRANSITION_CONTEXT_FIELDS, errors)
    _reject_unknown_fields(
        context,
        REQUIREMENTS_TRANSITION_CONTEXT_FIELDS,
        errors,
        path="requirements_context",
    )
    if errors:
        return _errors_sorted(errors)

    envelope = context["envelope"]
    requirements = context["requirements"]
    transport_errors = validate_transport_envelope(
        envelope,
        context["expected"],
        context["consumed_digests"],
    )
    errors.extend(
        f"requirements_context.transport.{error}"
        for error in transport_errors
    )
    packet, envelope_errors = _validate_transport_envelope_shape(envelope)
    errors.extend(
        f"requirements_context.{error}" for error in envelope_errors
    )
    requirements_packet = _as_mapping(
        requirements,
        "requirements_context.requirements",
        errors,
    )
    errors.extend(
        f"requirements_context.requirements.{error}"
        for error in _validate_requirements(
            requirements_packet,
            require_initial=False,
        )
    )
    if packet.get("packet_type") != "requirements":
        errors.append(
            "requirements_context.packet_type: requirements consumption requires a requirements envelope"
        )
    if packet.get("payload") != requirements_packet:
        errors.append(
            "requirements_context.payload: does not match the requirements packet"
        )

    envelope_digest = _canonical_digest_checked(
        packet,
        "requirements_context.envelope",
        errors,
    )
    if (
        envelope_digest is not None
        and previous_state.get("pending_requirements_envelope_digest")
        != envelope_digest
    ):
        errors.append(
            "requirements_context.pending_requirements_envelope_digest: envelope was not prevalidated"
        )
    if packet.get("previous_packet_digest") != previous_state.get(
        "last_consumed_packet_digest"
    ):
        errors.append(
            "requirements_context.previous_packet_digest: does not match the trusted packet chain"
        )
    consumed = context.get("consumed_digests")
    last_consumed = previous_state.get("last_consumed_packet_digest")
    if (
        isinstance(consumed, (set, frozenset, list, tuple))
        and isinstance(last_consumed, str)
        and last_consumed not in consumed
    ):
        errors.append(
            "requirements_context.consumed_digests: must contain the trusted packet-chain head"
        )

    requirements_digest = _canonical_digest_checked(
        requirements_packet,
        "requirements_context.requirements",
        errors,
    )
    pending_revision = previous_state.get("pending_requirements_revision")
    pending_digest = previous_state.get("pending_requirements_digest")
    has_pending_revision = (
        pending_revision is not None or pending_digest is not None
    )
    if has_pending_revision:
        if requirements_packet.get("requirements_revision") != pending_revision:
            errors.append(
                "requirements_context.requirements_revision: does not match the pending trusted revision"
            )
        if (
            requirements_digest is not None
            and requirements_digest != pending_digest
        ):
            errors.append(
                "requirements_context.requirements_digest: does not match the pending trusted requirements"
            )
        if requirements_packet.get(
            "supersedes_digest"
        ) != previous_state.get("pending_supersedes_digest"):
            errors.append(
                "requirements_context.supersedes_digest: does not match pending requirements provenance"
            )
        for field in MATERIAL_REVISION_FLAGS:
            if requirements_packet.get(field) != previous_state.get(field):
                errors.append(
                    f"requirements_context.{field}: does not match pending requirements provenance"
                )
    else:
        if (
            requirements_packet.get("requirements_revision")
            != previous_state.get("active_requirements_revision")
        ):
            errors.append(
                "requirements_context.requirements_revision: does not match the active trusted revision"
            )
        if (
            requirements_digest is not None
            and requirements_digest
            != previous_state.get("active_requirements_digest")
        ):
            errors.append(
                "requirements_context.requirements_digest: does not match the active trusted requirements"
            )

    if current_state.get(
        "latest_requirements_decision"
    ) != requirements_packet.get("decision"):
        errors.append(
            "requirements_context.decision: does not match the consumed requirements decision"
        )
    if current_state.get("phase") == "REQUIREMENTS_FROZEN":
        if (
            current_state.get("active_requirements_revision")
            != requirements_packet.get("requirements_revision")
        ):
            errors.append(
                "requirements_context.active_requirements_revision: frozen state does not promote the validated requirements"
            )
        if (
            requirements_digest is not None
            and current_state.get("active_requirements_digest")
            != requirements_digest
        ):
            errors.append(
                "requirements_context.active_requirements_digest: frozen state does not promote the validated requirements"
            )

    approval_receipt = context.get("approval_receipt")
    if requirements_packet.get("user_approval_required") is True:
        if not _is_nonempty_string(approval_receipt):
            errors.append(
                "requirements_context.approval_receipt: required user approval receipt is missing"
            )
        if requirements_packet.get("user_approval_received") is not True:
            errors.append(
                "requirements_context.user_approval_received: required approval is not recorded in the requirements packet"
            )
        if (
            approval_receipt
            != previous_state.get("pending_user_approval_evidence")
        ):
            errors.append(
                "requirements_context.approval_receipt: does not match trusted pending approval evidence"
            )
        if (
            requirements_digest is not None
            and previous_state.get(
                "pending_approved_requirements_digest"
            )
            != requirements_digest
        ):
            errors.append(
                "requirements_context.pending_approved_requirements_digest: does not approve the validated requirements"
            )
    elif approval_receipt is not None:
        errors.append(
            "requirements_context.approval_receipt: must be null when approval is not required"
        )
    return _errors_sorted(errors)


def validate_transition(
    previous,
    current,
    *,
    requirements_context=None,
    review_context=None,
    final_gate_evidence=None,
):
    """Validate trusted local state movement and explicit packet receipts."""
    errors: list[str] = []
    previous_phase = _phase(previous, "previous", errors)
    current_phase = _phase(current, "current", errors)
    previous_state = _state_mapping(previous)
    current_state = _state_mapping(current)
    _validate_state_fields(previous_state, "previous", errors)
    _validate_state_fields(current_state, "current", errors)
    _validate_stop_state_shape(previous_state, "previous", errors)
    _validate_stop_state_shape(current_state, "current", errors)
    previous_binding_valid = _validate_conversation_binding(
        previous_state, "previous", errors
    )
    current_binding_valid = _validate_conversation_binding(
        current_state, "current", errors
    )
    for name, value, state in (
        ("previous", previous, previous_state),
        ("current", current, current_state),
    ):
        if isinstance(value, dict):
            if "latest_decision" in state and state.get("latest_decision") is not None and (
                not isinstance(state.get("latest_decision"), str)
                or state.get("latest_decision") not in REVIEW_DECISIONS
            ):
                errors.append(
                    f"{name}.latest_decision: must be PASS, CHANGES_REQUESTED, BLOCK, or null"
                )

    previous_round = previous_state.get("review_round")
    current_round = current_state.get("review_round")
    previous_round_valid = (
        isinstance(previous_round, int)
        and not isinstance(previous_round, bool)
        and 0 <= previous_round <= MAX_REVIEW_ROUNDS
    )
    current_round_valid = (
        isinstance(current_round, int)
        and not isinstance(current_round, bool)
        and 0 <= current_round <= MAX_REVIEW_ROUNDS
    )
    if not previous_round_valid:
        errors.append("previous.review_round: must be an integer within the review limit")
    if not current_round_valid:
        errors.append("review_round: must be an integer within the review limit")

    valid_review_consumption = False
    if previous_phase and current_phase:
        initial_binding_transition = (
            previous_binding_valid
            and current_binding_valid
            and previous_state.get("conversation_binding_state")
            == "CONVERSATION_UNBOUND"
            and current_state.get("conversation_binding_state")
            == "CONVERSATION_BOUND"
            and previous_phase in {"PREFLIGHT", "REQUIREMENTS_PENDING"}
            and current_phase == "REQUIREMENTS_PENDING"
        )
        if previous_binding_valid and current_binding_valid:
            previous_binding = previous_state.get("conversation_binding_state")
            current_binding = current_state.get("conversation_binding_state")
            if previous_binding == "CONVERSATION_BOUND":
                if current_binding != "CONVERSATION_BOUND":
                    errors.append(
                        "conversation_binding_state: a bound conversation cannot become unbound"
                    )
                else:
                    for field in (
                        "bound_conversation_url",
                        "visible_model_label",
                    ):
                        if current_state.get(field) != previous_state.get(field):
                            errors.append(
                                f"{field}: must match the bound conversation state"
                            )
            elif current_binding == "CONVERSATION_BOUND" and not initial_binding_transition:
                errors.append(
                    "conversation_binding_state: binding is allowed only for the initial requirements conversation"
                )
        format_errors = current_state.get("format_error_count")
        if not isinstance(format_errors, int) or isinstance(format_errors, bool) or format_errors < 0:
            errors.append("format_error_count: must be a non-negative integer")
        elif format_errors > MAX_FORMAT_ERRORS:
            errors.append("format_error_count: repeated malformed response blocks the loop")
        same_phase_format_correction = (
            previous_phase == current_phase
            and isinstance(previous_state.get("format_error_count"), int)
            and format_errors == previous_state.get("format_error_count") + 1
        )
        reconnects = current_state.get("browser_reconnect_count")
        previous_reconnects = previous_state.get("browser_reconnect_count")
        same_phase_browser_reconnect = (
            previous_phase == current_phase
            and isinstance(reconnects, int)
            and not isinstance(reconnects, bool)
            and isinstance(previous_reconnects, int)
            and not isinstance(previous_reconnects, bool)
            and reconnects == previous_reconnects + 1
        )
        same_phase_maintenance = (
            same_phase_format_correction
            or same_phase_browser_reconnect
            or initial_binding_transition
        )
        if same_phase_format_correction:
            for field in (*REQUIRED_STATE_FIELDS, *OPTIONAL_STATE_FIELDS):
                if (
                    field != "format_error_count"
                    and current_state.get(field) != previous_state.get(field)
                ):
                    errors.append(
                        f"{field}: format correction must preserve domain state"
                    )
        if same_phase_browser_reconnect:
            for field in (*REQUIRED_STATE_FIELDS, *OPTIONAL_STATE_FIELDS):
                if (
                    field != "browser_reconnect_count"
                    and current_state.get(field) != previous_state.get(field)
                ):
                    errors.append(
                        f"{field}: browser reconnect must preserve domain state"
                    )
        if (
            previous_phase == "REQUIREMENTS_PENDING"
            and current_phase == "REQUIREMENTS_PENDING"
            and same_phase_maintenance
            and any(
                current_state.get(field) != previous_state.get(field)
                for field in PENDING_REVISION_PROVENANCE_FIELDS
            )
        ):
            errors.append(
                "pending_requirements: maintenance transitions must preserve revision provenance"
            )
        if (
            not _has_pending_requirements_provenance(previous_state)
            and _has_pending_requirements_provenance(current_state)
        ):
            current_actions = current_state.get("required_actions")
            review_revision_route = (
                previous_phase == "REVIEW_PENDING"
                and current_phase == "REQUIREMENTS_PENDING"
                and current_state.get("latest_decision")
                == "CHANGES_REQUESTED"
                and isinstance(current_actions, list)
                and "REQUIREMENTS_REVISION" in current_actions
            )
            resolved_requirements_stop = (
                previous_phase in STOP_PHASES
                and current_phase == "REQUIREMENTS_PENDING"
                and previous_state.get("stop_origin_category")
                in {
                    "REQUIREMENTS_NEED_USER_INPUT",
                    "REQUIREMENTS_BLOCK",
                }
                and _is_nonempty_string(current_state.get("resolution_evidence"))
            )
            if not review_revision_route and not resolved_requirements_stop:
                errors.append(
                    "pending_requirements: provenance may be introduced only by requirements revision routing or a resolved requirements stop"
                )
        if current_phase not in STATE_TRANSITIONS[previous_phase] and not same_phase_maintenance:
            errors.append(f"phase: illegal transition from {previous_phase} to {current_phase}")
        if current_phase in STOP_PHASES and previous_phase not in STOP_PHASES:
            _validate_stop_entry(
                previous_phase,
                current_phase,
                previous_state,
                current_state,
                errors,
            )
        if previous_phase in STOP_PHASES and current_phase not in STOP_PHASES:
            _validate_stop_resume(
                previous_phase,
                current_phase,
                previous_state,
                current_state,
                errors,
            )
        if (
            not (
                current_phase in STOP_PHASES
                and previous_phase not in STOP_PHASES
            )
            and current_state.get("stop_sequence")
            != previous_state.get("stop_sequence")
        ):
            errors.append(
                "stop_sequence: non-entry transitions must preserve the stop sequence"
            )
        if (
            previous_phase in STOP_PHASES
            and current_phase == previous_phase
            and same_phase_maintenance
            and any(
                current_state.get(field) != previous_state.get(field)
                for field in (
                    "stop_origin_phase",
                    "stop_origin_category",
                    "stop_reason",
                    "stop_sequence",
                )
            )
        ):
            errors.append(
                "stop_provenance: maintenance transitions must preserve the active stop"
            )
        _validate_resolution_lifecycle(
            previous_phase,
            current_phase,
            previous_state,
            current_state,
            errors,
        )
        consumes_requirements = (
            previous_phase == "REQUIREMENTS_PENDING"
            and current_phase != previous_phase
        )
        if consumes_requirements:
            errors.extend(
                _validate_requirements_transition_context(
                    requirements_context,
                    previous_state,
                    current_state,
                )
            )
            _validate_requirements_envelope_consumption(
                previous_state,
                current_state,
                errors,
            )
            expected_requirements_target = _expected_requirements_target(
                current_state, errors
            )
            if (
                expected_requirements_target
                and current_phase != expected_requirements_target
            ):
                errors.append(
                    "phase: requirements routing requires transition to "
                    f"{expected_requirements_target}, not {current_phase}"
                )
        promotion_attempt = False
        reset_attempt = False
        if (
            previous_phase == "REQUIREMENTS_PENDING"
            and current_phase == "REQUIREMENTS_FROZEN"
        ):
            promotion_attempt, reset_attempt = _validate_requirements_promotion(
                previous_state,
                current_state,
                previous_round,
                current_round,
                errors,
            )
        previous_active_revision = previous_state.get(
            "active_requirements_revision"
        )
        previous_active_digest = previous_state.get(
            "active_requirements_digest"
        )
        current_active_revision = current_state.get(
            "active_requirements_revision"
        )
        current_active_digest = current_state.get("active_requirements_digest")
        initial_active_binding = (
            previous_phase == "PREFLIGHT"
            and current_phase == "REQUIREMENTS_PENDING"
            and previous_active_revision is None
            and previous_active_digest is None
            and current_active_revision == 1
            and isinstance(current_active_digest, str)
            and bool(DIGEST_PATTERN.fullmatch(current_active_digest))
        )
        if not promotion_attempt and not initial_active_binding:
            if (
                previous_active_revision is None
                and previous_active_digest is None
                and (
                    current_active_revision is not None
                    or current_active_digest is not None
                )
            ):
                errors.append(
                    "active_requirements: may be initialized only when preflight enters requirements pending"
                )
            if (
                current_active_revision
                != previous_active_revision
            ):
                errors.append(
                    "active_requirements_revision: must preserve active requirements provenance"
                )
            if (
                current_active_digest
                != previous_active_digest
            ):
                errors.append(
                    "active_requirements_digest: must preserve active requirements provenance"
                )
        if (
            not promotion_attempt
            and current_state.get("approval_sequence")
            != previous_state.get("approval_sequence")
        ):
            errors.append(
                "approval_sequence: must preserve consumed approval history"
            )
        consumes_review = previous_phase == "REVIEW_PENDING" and current_phase != previous_phase
        review_context_valid = False
        if consumes_review:
            review_context_errors = _validate_review_transition_context(
                review_context,
                previous_state,
                current_state,
            )
            errors.extend(review_context_errors)
            review_context_valid = not review_context_errors
            _validate_review_envelope_consumption(
                previous_state,
                current_state,
                errors,
            )
            history_results = [
                _validate_state_string_list(state, name, field, errors)
                for name, state in (
                    ("previous", previous_state),
                    ("current", current_state),
                )
                for field in ("unresolved_finding_ids", "blocker_fingerprints")
            ]
            history_valid = all(history_results)
            decision = previous_state.get("latest_decision")
            if (
                not isinstance(decision, str)
                or decision not in REVIEW_DECISIONS
            ):
                errors.append(
                    "latest_decision: a valid review transition requires PASS, CHANGES_REQUESTED, or BLOCK"
                )
                expected_target = None
            else:
                expected_target = _expected_review_target(previous_state, errors)
            if expected_target and current_phase != expected_target:
                errors.append(
                    f"phase: review routing requires transition to {expected_target}, not {current_phase}"
                )
            if previous_round_valid and current_round_valid and current_round != previous_round + 1:
                errors.append("review_round: valid review consumption must increment exactly once")
            valid_review_consumption = (
                isinstance(decision, str)
                and decision in REVIEW_DECISIONS
                and expected_target == current_phase
                and previous_round_valid
                and current_round_valid
                and current_round == previous_round + 1
                and history_valid
                and review_context_valid
            )
        elif previous_round_valid and current_round_valid:
            if current_round != previous_round and not reset_attempt:
                errors.append(
                    "review_round: non-review transitions must preserve the review round"
                )
        if same_phase_maintenance and current_state.get("latest_decision") != previous_state.get(
            "latest_decision"
        ):
            errors.append("latest_decision: maintenance transitions cannot consume a review")
        if previous_phase == "FINAL_VERIFICATION" and current_phase == "COMPLETE":
            for field in (
                "latest_decision",
                "required_actions",
                "last_consumed_packet_digest",
                "last_consumed_review_envelope_digest",
                "active_report_digest",
                "current_snapshot_digest",
                "active_review_packet_digest",
                "reviewed_snapshot_digest",
            ):
                if current_state.get(field) != previous_state.get(field):
                    errors.append(
                        f"{field}: COMPLETE must preserve final-gate bindings"
                    )
            if final_gate_evidence is None:
                errors.append(
                    "final_gate: explicit validated evidence is required for COMPLETE"
                )
            else:
                errors.extend(
                    validate_final_gate(final_gate_evidence, previous_state)
                )
        elif final_gate_evidence is not None:
            errors.append(
                "final_gate: evidence is allowed only for FINAL_VERIFICATION to COMPLETE"
            )

    if valid_review_consumption and previous_round >= 1 and (
        _finding_ids(previous_state) & _finding_ids(current_state)
        or _fingerprints(previous_state) & _fingerprints(current_state)
    ):
        errors.append(
            "unresolved_findings: blocker persisted across two consecutive valid review rounds"
        )
    return _errors_sorted(errors)


def _load_json(path: str) -> Any:
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("response")
    requirements_parser = subparsers.add_parser("requirements")
    requirements_parser.add_argument("packet")
    requirements_parser.add_argument("--previous")
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("packet")
    report_parser.add_argument("--requirements", required=True)
    review_parser = subparsers.add_parser("review")
    review_parser.add_argument("packet")
    review_parser.add_argument("--requirements", required=True)
    review_parser.add_argument("--report", required=True)
    envelope_parser = subparsers.add_parser("envelope")
    envelope_parser.add_argument("packet")
    envelope_parser.add_argument("--expected", required=True)
    envelope_parser.add_argument("--consumed", required=True)
    correction_parser = subparsers.add_parser("format-correction")
    correction_parser.add_argument("packet")
    correction_parser.add_argument("--original-payload", required=True)
    report_context_parser = subparsers.add_parser("report-context")
    report_context_parser.add_argument("packet")
    report_context_parser.add_argument("--requirements", required=True)
    report_context_parser.add_argument("--state", required=True)
    report_context_parser.add_argument("--snapshot", required=True)
    review_context_parser = subparsers.add_parser("review-context")
    review_context_parser.add_argument("packet")
    review_context_parser.add_argument("--requirements", required=True)
    review_context_parser.add_argument("--report", required=True)
    review_context_parser.add_argument("--state", required=True)
    review_context_parser.add_argument("--snapshot", required=True)
    final_gate_parser = subparsers.add_parser("final-gate")
    final_gate_parser.add_argument("evidence")
    final_gate_parser.add_argument("--state", required=True)
    transition_parser = subparsers.add_parser("transition")
    transition_parser.add_argument("previous")
    transition_parser.add_argument("current")
    transition_parser.add_argument("--requirements-context")
    transition_parser.add_argument("--review-context")
    transition_parser.add_argument("--final-gate")
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            value = extract_single_json_object(Path(args.response).read_text(encoding="utf-8"))
            errors: list[str] = []
        elif args.command == "requirements":
            value = _load_json(args.packet)
            errors = validate_requirements(value, _load_json(args.previous) if args.previous else None)
        elif args.command == "report":
            value = _load_json(args.packet)
            errors = validate_report(value, _load_json(args.requirements))
        elif args.command == "review":
            value = _load_json(args.packet)
            errors = validate_review(value, _load_json(args.requirements), _load_json(args.report))
        elif args.command == "envelope":
            value = _load_json(args.packet)
            consumed = _load_json(args.consumed)
            if not isinstance(consumed, dict) or set(consumed) != {"consumed_digests"}:
                raise PacketValidationError(
                    "consumed file must be an object with only consumed_digests"
                )
            errors = validate_transport_envelope(
                value,
                _load_json(args.expected),
                consumed["consumed_digests"],
            )
        elif args.command == "format-correction":
            value = _load_json(args.packet)
            errors = validate_format_correction(
                _load_json(args.original_payload),
                value,
            )
        elif args.command == "report-context":
            value = _load_json(args.packet)
            errors = validate_report_context(
                value,
                _load_json(args.requirements),
                _load_json(args.state),
                _load_json(args.snapshot),
            )
        elif args.command == "review-context":
            value = _load_json(args.packet)
            errors = validate_review_context(
                value,
                _load_json(args.requirements),
                _load_json(args.report),
                _load_json(args.state),
                _load_json(args.snapshot),
            )
        elif args.command == "final-gate":
            value = _load_json(args.evidence)
            errors = validate_final_gate(value, _load_json(args.state))
        else:
            value = {"previous": _load_json(args.previous), "current": _load_json(args.current)}
            errors = validate_transition(
                value["previous"],
                value["current"],
                requirements_context=(
                    _load_json(args.requirements_context)
                    if args.requirements_context
                    else None
                ),
                review_context=(
                    _load_json(args.review_context)
                    if args.review_context
                    else None
                ),
                final_gate_evidence=(
                    _load_json(args.final_gate)
                    if args.final_gate
                    else None
                ),
            )
    except (OSError, PacketValidationError, TypeError, ValueError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 1
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False))
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
