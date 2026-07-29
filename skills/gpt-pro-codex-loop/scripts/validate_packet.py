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
STATE_TRANSITIONS = {
    "PREFLIGHT": frozenset({"REQUIREMENTS_PENDING"}),
    "REQUIREMENTS_PENDING": frozenset({"REQUIREMENTS_FROZEN"}),
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
    "USER_DECISION_REQUIRED": frozenset(),
    "FINAL_VERIFICATION": frozenset({"COMPLETE", "REVIEW_PENDING", "BLOCKED"}),
    "COMPLETE": frozenset(),
    "BLOCKED": frozenset(),
}
MAX_REVIEW_ROUNDS = 3
MAX_FORMAT_ERRORS = 1


class PacketValidationError(ValueError):
    """Raised when a browser response is not exactly one JSON object fence."""


def extract_single_json_object(raw: str) -> dict[str, object]:
    matches = list(FENCE_PATTERN.finditer(raw))
    if len(matches) != 1 or raw.strip() != matches[0].group(0):
        raise PacketValidationError("response must contain exactly one JSON fence")
    try:
        value = json.loads(matches[0].group("body"))
    except json.JSONDecodeError as exc:
        raise PacketValidationError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise PacketValidationError("packet must be a JSON object")
    return value


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
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
    if current.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: must equal {SCHEMA_VERSION}")
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
    if current.get("decision") not in REQUIREMENTS_DECISIONS:
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
        if current.get("supersedes_digest") != canonical_digest(prior):
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
    _require_nonempty_string(report, "baseline_head", errors)
    if report.get("requirements_revision") != req.get("requirements_revision"):
        errors.append("requirements_revision: does not match requirements revision")
    if report.get("requirements_digest") != canonical_digest(req):
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
        elif item.get("status") not in ACCEPTANCE_STATUSES:
            errors.append(f"{path}.status: must be PASS, FAIL, or UNVERIFIED")
        if "evidence" not in item:
            errors.append(f"{path}.evidence: missing required field")
        elif not _is_nonempty_string(item.get("evidence")):
            errors.append(f"{path}.evidence: must be a non-empty string")
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
    if review.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: must equal {SCHEMA_VERSION}")
    if review.get("requirements_digest") != canonical_digest(req):
        errors.append("requirements_digest: does not match requirements digest")
    if review.get("reviewed_snapshot_digest") != implementation_report.get("snapshot_digest"):
        errors.append("reviewed_snapshot_digest: does not match report snapshot_digest")
    if review.get("decision") not in REVIEW_DECISIONS:
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
        for field in ("id", "root_cause_fingerprint", "severity", "category", "required_action", "evidence"):
            if field not in finding:
                errors.append(f"{path}.{field}: missing required field")
            elif not _is_nonempty_string(finding[field]):
                errors.append(f"{path}.{field}: must be a non-empty string")
        finding_id = finding.get("id")
        if _is_nonempty_string(finding_id):
            if finding_id in seen_finding_ids:
                errors.append(f"{path}.id: duplicate stable ID {finding_id}")
            seen_finding_ids.add(finding_id)
        if finding.get("severity") not in FINDING_SEVERITIES:
            errors.append(f"{path}.severity: must be BLOCKER, HIGH, MEDIUM, or LOW")
        action = finding.get("required_action")
        if action not in REQUIRED_ACTIONS:
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


def _phase(value: object, name: str, errors: list[str]) -> str | None:
    if isinstance(value, str):
        phase = value
    elif isinstance(value, dict):
        phase = value.get("phase")
    else:
        errors.append(f"{name}: must be a phase string or state object")
        return None
    if phase not in STATE_TRANSITIONS:
        errors.append(f"{name}.phase: unknown workflow phase")
        return None
    return phase


def _state_mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _state_string_set(state: dict[str, object], field: str) -> set[str]:
    values = state.get(field)
    if not isinstance(values, list):
        return set()
    return {value for value in values if _is_nonempty_string(value)}


def _validate_state_string_list(
    state: dict[str, object], name: str, field: str, errors: list[str]
) -> bool:
    values = state.get(field)
    if not isinstance(values, list) or any(
        not _is_nonempty_string(value) for value in values
    ):
        errors.append(f"{name}.{field}: must be a list of strings")
        return False
    return True


def _finding_ids(state: dict[str, object]) -> set[str]:
    identifiers = _state_string_set(state, "unresolved_finding_ids")
    if identifiers:
        return identifiers
    findings = state.get("unresolved_findings")
    if not isinstance(findings, list):
        return set()
    return {
        identifier
        for item in findings
        if isinstance(item, dict)
        for identifier in (item.get("id"),)
        if _is_nonempty_string(identifier)
    }


def _fingerprints(state: dict[str, object]) -> set[str]:
    fingerprints = _state_string_set(state, "blocker_fingerprints")
    if fingerprints:
        return fingerprints
    findings = state.get("unresolved_findings")
    if not isinstance(findings, list):
        return set()
    return {
        fingerprint
        for item in findings
        if isinstance(item, dict)
        for fingerprint in (item.get("fingerprint", item.get("root_cause_fingerprint")),)
        if _is_nonempty_string(fingerprint)
    }


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


def validate_transition(previous, current):
    """Return all deterministic workflow-state transition validation errors."""
    errors: list[str] = []
    previous_phase = _phase(previous, "previous", errors)
    current_phase = _phase(current, "current", errors)
    previous_state = _state_mapping(previous)
    current_state = _state_mapping(current)
    for name, value, state in (
        ("previous", previous, previous_state),
        ("current", current, current_state),
    ):
        if isinstance(value, dict):
            if "latest_decision" not in state:
                errors.append(f"{name}.latest_decision: missing required field")
            elif state.get("latest_decision") is not None and (
                not isinstance(state.get("latest_decision"), str)
                or state.get("latest_decision") not in REVIEW_DECISIONS
            ):
                errors.append(
                    f"{name}.latest_decision: must be PASS, CHANGES_REQUESTED, BLOCK, or null"
                )

    previous_round = previous_state.get("review_round", 0)
    current_round = current_state.get("review_round", 0)
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
        format_errors = current_state.get("format_error_count", 0)
        if not isinstance(format_errors, int) or isinstance(format_errors, bool) or format_errors < 0:
            errors.append("format_error_count: must be a non-negative integer")
        elif format_errors > MAX_FORMAT_ERRORS:
            errors.append("format_error_count: repeated malformed response blocks the loop")
        same_phase_format_correction = (
            previous_phase == current_phase
            and isinstance(previous_state.get("format_error_count", 0), int)
            and format_errors == previous_state.get("format_error_count", 0) + 1
        )
        reconnects = current_state.get("browser_reconnect_count", 0)
        previous_reconnects = previous_state.get("browser_reconnect_count", 0)
        same_phase_browser_reconnect = (
            previous_phase == current_phase
            and isinstance(reconnects, int)
            and not isinstance(reconnects, bool)
            and isinstance(previous_reconnects, int)
            and not isinstance(previous_reconnects, bool)
            and reconnects == previous_reconnects + 1
        )
        same_phase_maintenance = same_phase_format_correction or same_phase_browser_reconnect
        if current_phase not in STATE_TRANSITIONS[previous_phase] and not same_phase_maintenance:
            errors.append(f"phase: illegal transition from {previous_phase} to {current_phase}")
        consumes_review = previous_phase == "REVIEW_PENDING" and current_phase != previous_phase
        if consumes_review:
            history_results = [
                _validate_state_string_list(state, name, field, errors)
                for name, state in (
                    ("previous", previous_state),
                    ("current", current_state),
                )
                for field in ("unresolved_finding_ids", "blocker_fingerprints")
            ]
            history_valid = all(history_results)
            decision = current_state.get("latest_decision")
            if decision not in REVIEW_DECISIONS:
                errors.append(
                    "latest_decision: a valid review transition requires PASS, CHANGES_REQUESTED, or BLOCK"
                )
                expected_target = None
            else:
                expected_target = _expected_review_target(current_state, errors)
            if expected_target and current_phase != expected_target:
                errors.append(
                    f"phase: review routing requires transition to {expected_target}, not {current_phase}"
                )
            if previous_round_valid and current_round_valid and current_round != previous_round + 1:
                errors.append("review_round: valid review consumption must increment exactly once")
            valid_review_consumption = (
                decision in REVIEW_DECISIONS
                and expected_target == current_phase
                and previous_round_valid
                and current_round_valid
                and current_round == previous_round + 1
                and history_valid
            )
        elif previous_round_valid and current_round_valid and current_round != previous_round:
            errors.append("review_round: non-review transitions must preserve the review round")
        if same_phase_maintenance and current_state.get("latest_decision") != previous_state.get(
            "latest_decision"
        ):
            errors.append("latest_decision: maintenance transitions cannot consume a review")

    if valid_review_consumption and previous_round >= 1 and (
        _finding_ids(previous_state) & _finding_ids(current_state)
        or _fingerprints(previous_state) & _fingerprints(current_state)
    ):
        errors.append(
            "unresolved_findings: blocker persisted across two consecutive valid review rounds"
        )
    return _errors_sorted(errors)


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
    transition_parser = subparsers.add_parser("transition")
    transition_parser.add_argument("previous")
    transition_parser.add_argument("current")
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
        else:
            value = {"previous": _load_json(args.previous), "current": _load_json(args.current)}
            errors = validate_transition(value["previous"], value["current"])
    except (OSError, json.JSONDecodeError, PacketValidationError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 1
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False))
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
