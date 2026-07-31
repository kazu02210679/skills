"""Unit tests for the GPT Pro Codex Loop packet validator."""

from __future__ import annotations

import sys
import json
import math
import re
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "gpt-pro-codex-loop"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIRECTORY))

import validate_packet as packet_validator  # noqa: E402
from validate_packet import (  # noqa: E402
    PacketValidationError,
    canonical_digest,
    extract_single_json_object,
    main,
    validate_report,
    validate_requirements,
    validate_review,
    validate_transition,
)


REQ_ENVELOPE_DIGEST = "sha256:" + "1" * 64
REQ_ENVELOPE_DIGEST_2 = "sha256:" + "6" * 64
REVIEW_ENVELOPE_DIGEST = "sha256:" + "2" * 64
REVIEW_PACKET_DIGEST = "sha256:" + "3" * 64


def valid_requirements(**overrides: object) -> dict[str, object]:
    packet: dict[str, object] = {
        "schema_version": 1,
        "requirements_revision": 1,
        "supersedes_digest": None,
        "change_reason": "initial requirements",
        "behavior_changed": False,
        "user_approval_required": False,
        "user_approval_received": False,
        "scope_changed": False,
        "public_contract_changed": False,
        "prior_evidence_invalidated": False,
        "review_round_reset": False,
        "decision": "PLAN_READY",
        "objective": "Validate the protocol.",
        "requirements": [{"id": "REQ-1", "statement": "Packets validate."}],
        "in_scope": ["validator"],
        "out_of_scope": ["deployment"],
        "constraints": ["standard library"],
        "acceptance_criteria": [
            {
                "id": "AC-1",
                "criterion": "Invalid packets fail closed.",
                "required_evidence": "unit test output",
            }
        ],
        "design_direction": ["deterministic validation"],
        "risk_items": [
            {
                "id": "RISK-1",
                "risk": "Malformed responses",
                "required_mitigation": "reject malformed JSON",
            }
        ],
        "verification_strategy": ["run unit tests"],
        "open_questions": [],
    }
    packet.update(overrides)
    return packet


def valid_report(requirements: dict[str, object], **overrides: object) -> dict[str, object]:
    packet: dict[str, object] = {
        "schema_version": 1,
        "baseline_head": "a" * 40,
        "requirements_revision": requirements["requirements_revision"],
        "requirements_digest": canonical_digest(requirements),
        "review_round": 1,
        "snapshot_digest": "sha256:" + "b" * 64,
        "tracked_diff_digest": "sha256:" + "c" * 64,
        "untracked_manifest_digest": "sha256:" + "d" * 64,
        "changed_files": [{"path": "example.py", "intent": "validate packets"}],
        "intent_summary": "Implemented packet validation.",
        "acceptance_evidence": {"AC-1": ["unit tests pass"]},
        "test_commands": [
            {
                "command": "python -m unittest",
                "outcome": "PASS",
                "output_summary": "all tests passed",
            }
        ],
        "diff_evidence": ["example.py validates packets"],
        "omissions": [],
        "unresolved_risks_or_blockers": [],
    }
    packet.update(overrides)
    return packet


def valid_review(
    requirements: dict[str, object], report: dict[str, object], **overrides: object
) -> dict[str, object]:
    packet: dict[str, object] = {
        "schema_version": 1,
        "requirements_digest": canonical_digest(requirements),
        "reviewed_snapshot_digest": report["snapshot_digest"],
        "decision": "PASS",
        "acceptance_results": {"AC-1": {"status": "PASS", "evidence": "tests"}},
        "findings": [],
        "scope_violations": [],
        "next_instruction": "Run final local verification.",
    }
    packet.update(overrides)
    return packet


def valid_snapshot(
    report: dict[str, object], **overrides: object
) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "schema_version": 1,
        "baseline_head": report["baseline_head"],
        "preflight_digest": "sha256:" + "f" * 64,
        "initial_product_paths": [],
        "snapshot_digest": report["snapshot_digest"],
        "tracked_diff_digest": report["tracked_diff_digest"],
        "untracked_manifest_digest": report["untracked_manifest_digest"],
    }
    snapshot.update(overrides)
    return snapshot


def valid_envelope(
    packet_type: str,
    payload: dict[str, object],
    **overrides: object,
) -> dict[str, object]:
    envelope: dict[str, object] = {
        "schema_version": 1,
        "packet_type": packet_type,
        "run_id": "gpc-loop-20260729-test",
        "turn_id": f"{packet_type}-01",
        "nonce": f"{packet_type}-attempt-01",
        "in_reply_to": "sha256:" + "4" * 64,
        "prompt_digest": "sha256:" + "5" * 64,
        "previous_packet_digest": (
            None if packet_type == "requirements" else REQ_ENVELOPE_DIGEST
        ),
        "payload": payload,
    }
    envelope.update(overrides)
    return envelope


def expected_envelope(envelope: dict[str, object]) -> dict[str, object]:
    return {
        key: envelope[key]
        for key in (
            "schema_version",
            "packet_type",
            "run_id",
            "turn_id",
            "nonce",
            "in_reply_to",
            "prompt_digest",
            "previous_packet_digest",
        )
    }


_UNSET_STATE_VALUE = object()


def valid_state(
    phase: str,
    review_round: int,
    *,
    latest_decision: object = None,
    latest_requirements_decision: object = None,
    required_actions: list[str] | None = None,
    unresolved_finding_ids: list[str] | None = None,
    blocker_fingerprints: list[str] | None = None,
    format_error_count: int = 0,
    browser_reconnect_count: int = 0,
    conversation_binding_state: str = "CONVERSATION_BOUND",
    bound_conversation_url: object = "https://chatgpt.com/c/test-conversation",
    model_policy: object = "PRO_CLASS",
    requested_model_label: object = None,
    visible_model_label: object = "Pro",
    active_requirements_revision: object = _UNSET_STATE_VALUE,
    active_requirements_digest: object = _UNSET_STATE_VALUE,
    approval_sequence: object = 0,
    pending_requirements_revision: object = None,
    pending_requirements_digest: object = None,
    pending_supersedes_digest: object = None,
    pending_approval_sequence: object = None,
    pending_approved_requirements_digest: object = None,
    pending_user_approval_evidence: object = None,
    behavior_changed: bool = False,
    user_approval_required: bool = False,
    scope_changed: bool = False,
    public_contract_changed: bool = False,
    prior_evidence_invalidated: bool = False,
    review_round_reset: bool = False,
    user_approval_received: bool = False,
    stop_origin_phase: object = None,
    stop_origin_category: object = None,
    stop_reason: object = None,
    stop_sequence: object = 0,
    resolution_evidence: object = None,
    resolution_stop_sequence: object = None,
    schema_version: object = 1,
    pending_requirements_envelope_digest: object = _UNSET_STATE_VALUE,
    pending_review_envelope_digest: object = _UNSET_STATE_VALUE,
    last_consumed_packet_digest: object = _UNSET_STATE_VALUE,
    last_consumed_review_envelope_digest: object = _UNSET_STATE_VALUE,
    active_report_digest: object = None,
    current_snapshot_digest: object = None,
    active_review_packet_digest: object = _UNSET_STATE_VALUE,
    reviewed_snapshot_digest: object = _UNSET_STATE_VALUE,
    baseline_head: object = "a" * 40,
    preflight_digest: object = "sha256:" + "f" * 64,
    approved_existing_paths: object = None,
) -> dict[str, object]:
    if active_requirements_revision is _UNSET_STATE_VALUE:
        active_requirements_revision = None if phase == "PREFLIGHT" else 1
    if active_requirements_digest is _UNSET_STATE_VALUE:
        active_requirements_digest = (
            None if phase == "PREFLIGHT" else "sha256:" + "a" * 64
        )
    review_consumed = (
        phase != "REVIEW_PENDING"
        and (
            latest_decision in {"PASS", "CHANGES_REQUESTED", "BLOCK"}
            or phase in {"FINAL_VERIFICATION", "COMPLETE"}
            or stop_origin_phase == "REVIEW_PENDING"
            or (
                resolution_evidence is not None
                and phase in {"IMPLEMENTING", "LOCAL_VERIFICATION"}
            )
        )
    )
    if pending_requirements_envelope_digest is _UNSET_STATE_VALUE:
        pending_requirements_envelope_digest = (
            REQ_ENVELOPE_DIGEST if phase == "REQUIREMENTS_PENDING" else None
        )
    if pending_review_envelope_digest is _UNSET_STATE_VALUE:
        pending_review_envelope_digest = (
            REVIEW_ENVELOPE_DIGEST if phase == "REVIEW_PENDING" else None
        )
    if last_consumed_packet_digest is _UNSET_STATE_VALUE:
        if phase == "PREFLIGHT":
            last_consumed_packet_digest = None
        elif review_consumed:
            last_consumed_packet_digest = REVIEW_ENVELOPE_DIGEST
        elif phase == "REQUIREMENTS_PENDING" and resolution_evidence is None:
            last_consumed_packet_digest = None
        else:
            last_consumed_packet_digest = REQ_ENVELOPE_DIGEST
    if last_consumed_review_envelope_digest is _UNSET_STATE_VALUE:
        last_consumed_review_envelope_digest = (
            REVIEW_ENVELOPE_DIGEST if review_consumed else None
        )
    if active_review_packet_digest is _UNSET_STATE_VALUE:
        active_review_packet_digest = (
            REVIEW_PACKET_DIGEST
            if phase == "REVIEW_PENDING" or review_consumed
            else None
        )
    if reviewed_snapshot_digest is _UNSET_STATE_VALUE:
        reviewed_snapshot_digest = (
            "sha256:" + "b" * 64
            if active_review_packet_digest is not None
            else None
        )
    normalized_fingerprints = [
        fingerprint
        if fingerprint.startswith("sha256:") and len(fingerprint) == 71
        else canonical_digest({"test_root_cause": fingerprint})
        for fingerprint in (blocker_fingerprints or [])
    ]
    return {
        "schema_version": schema_version,
        "phase": phase,
        "review_round": review_round,
        "latest_decision": latest_decision,
        "latest_requirements_decision": latest_requirements_decision,
        "required_actions": required_actions or [],
        "unresolved_finding_ids": unresolved_finding_ids or [],
        "blocker_fingerprints": normalized_fingerprints,
        "format_error_count": format_error_count,
        "browser_reconnect_count": browser_reconnect_count,
        "conversation_binding_state": conversation_binding_state,
        "bound_conversation_url": bound_conversation_url,
        "model_policy": model_policy,
        "requested_model_label": requested_model_label,
        "visible_model_label": visible_model_label,
        "active_requirements_revision": active_requirements_revision,
        "active_requirements_digest": active_requirements_digest,
        "approval_sequence": approval_sequence,
        "pending_requirements_revision": pending_requirements_revision,
        "pending_requirements_digest": pending_requirements_digest,
        "pending_supersedes_digest": pending_supersedes_digest,
        "pending_approval_sequence": pending_approval_sequence,
        "pending_approved_requirements_digest": pending_approved_requirements_digest,
        "pending_user_approval_evidence": pending_user_approval_evidence,
        "behavior_changed": behavior_changed,
        "user_approval_required": user_approval_required,
        "scope_changed": scope_changed,
        "public_contract_changed": public_contract_changed,
        "prior_evidence_invalidated": prior_evidence_invalidated,
        "review_round_reset": review_round_reset,
        "user_approval_received": user_approval_received,
        "stop_origin_phase": stop_origin_phase,
        "stop_origin_category": stop_origin_category,
        "stop_reason": stop_reason,
        "stop_sequence": stop_sequence,
        "resolution_evidence": resolution_evidence,
        "resolution_stop_sequence": resolution_stop_sequence,
        "pending_requirements_envelope_digest": pending_requirements_envelope_digest,
        "pending_review_envelope_digest": pending_review_envelope_digest,
        "last_consumed_packet_digest": last_consumed_packet_digest,
        "last_consumed_review_envelope_digest": last_consumed_review_envelope_digest,
        "active_report_digest": active_report_digest,
        "current_snapshot_digest": current_snapshot_digest,
        "active_review_packet_digest": active_review_packet_digest,
        "reviewed_snapshot_digest": reviewed_snapshot_digest,
        "baseline_head": baseline_head,
        "preflight_digest": preflight_digest,
        "approved_existing_paths": (
            [] if approved_existing_paths is None else approved_existing_paths
        ),
    }


def bind_review_transition_context(
    previous: dict[str, object],
    current: dict[str, object],
) -> dict[str, object]:
    """Attach a coherent validated-review context to test transition states."""
    requirements = valid_requirements()
    requirements_digest = canonical_digest(requirements)
    report = valid_report(
        requirements,
        review_round=previous["review_round"],
    )
    snapshot = valid_snapshot(report)
    decision = current.get("latest_decision")
    actions = current.get("required_actions")
    existing_ids = current.get("unresolved_finding_ids")
    existing_fingerprints = current.get("blocker_fingerprints")
    legacy_findings = current.get("unresolved_findings")
    if "unresolved_finding_ids" not in current and isinstance(
        legacy_findings,
        list,
    ):
        existing_ids = [
            finding.get("id")
            for finding in legacy_findings
            if isinstance(finding, dict)
            and isinstance(finding.get("id"), str)
        ]
    if "blocker_fingerprints" not in current and isinstance(
        legacy_findings,
        list,
    ):
        existing_fingerprints = [
            finding.get(
                "fingerprint",
                finding.get("root_cause_fingerprint"),
            )
            for finding in legacy_findings
            if isinstance(finding, dict)
            and isinstance(
                finding.get(
                    "fingerprint",
                    finding.get("root_cause_fingerprint"),
                ),
                str,
            )
        ]
    action_values = actions if isinstance(actions, list) else []
    id_values = existing_ids if isinstance(existing_ids, list) else []
    fingerprint_values = (
        existing_fingerprints
        if isinstance(existing_fingerprints, list)
        else []
    )
    finding_count = max(
        len(action_values),
        len(id_values),
        len(fingerprint_values),
    )
    findings = []
    for index in range(1, finding_count + 1):
        action = (
            action_values[index - 1]
            if index <= len(action_values)
            else "PROVIDE_EVIDENCE"
        )
        root_cause_key = (
            fingerprint_values[index - 1]
            if index <= len(fingerprint_values)
            else f"context-{index}"
        )
        finding = {
            "id": (
                id_values[index - 1]
                if index <= len(id_values)
                else f"F-CONTEXT-{index}"
            ),
            "acceptance_id": "AC-1",
            "root_cause_key": root_cause_key,
            "severity": "HIGH",
            "category": "context",
            "required_action": action,
            "evidence": "Transition context fixture.",
        }
        findings.append(finding)
    review = valid_review(
        requirements,
        report,
        decision=decision,
        findings=findings,
    )
    chain_head = previous.get("last_consumed_packet_digest")
    envelope = valid_envelope(
        "review",
        review,
        previous_packet_digest=chain_head,
    )
    envelope_digest = canonical_digest(envelope)
    prior_active_digest = previous.get("active_requirements_digest")
    prior_review_digest = previous.get("last_consumed_review_envelope_digest")
    finding_ids = sorted(
        finding["id"] for finding in findings
    )
    finding_fingerprints = sorted(
        fingerprint
        for finding in findings
        for fingerprint in (
            packet_validator.derive_root_cause_fingerprint(finding),
            packet_validator.derive_root_cause_route_fingerprint(finding),
        )
    )
    previous_fingerprint_values = previous.get("blocker_fingerprints")
    if isinstance(previous_fingerprint_values, list):
        previous["blocker_fingerprints"] = [
            packet_validator.derive_root_cause_fingerprint(
                {
                    "acceptance_id": "AC-1",
                    "category": "context",
                    "required_action": (
                        action_values[index]
                        if index < len(action_values)
                        else "PROVIDE_EVIDENCE"
                    ),
                    "root_cause_key": value,
                }
            )
            for index, value in enumerate(previous_fingerprint_values)
        ]
    previous_legacy = previous.get("unresolved_findings")
    if isinstance(previous_legacy, list):
        for index, item in enumerate(previous_legacy):
            if not isinstance(item, dict):
                continue
            value = item.get(
                "fingerprint",
                item.get("root_cause_fingerprint"),
            )
            if isinstance(value, str):
                item["root_cause_fingerprint"] = (
                    packet_validator.derive_root_cause_fingerprint(
                        {
                            "acceptance_id": "AC-1",
                            "category": "context",
                            "required_action": (
                                action_values[index]
                                if index < len(action_values)
                                else "PROVIDE_EVIDENCE"
                            ),
                            "root_cause_key": value,
                        }
                    )
                )

    previous.update(
        active_requirements_revision=requirements["requirements_revision"],
        active_requirements_digest=requirements_digest,
        pending_review_envelope_digest=envelope_digest,
        active_report_digest=canonical_digest(report),
        current_snapshot_digest=snapshot["snapshot_digest"],
        active_review_packet_digest=canonical_digest(review),
        reviewed_snapshot_digest=review["reviewed_snapshot_digest"],
    )
    current.update(
        active_requirements_revision=requirements["requirements_revision"],
        active_requirements_digest=requirements_digest,
        pending_review_envelope_digest=None,
        last_consumed_packet_digest=envelope_digest,
        last_consumed_review_envelope_digest=envelope_digest,
        active_report_digest=previous["active_report_digest"],
        current_snapshot_digest=previous["current_snapshot_digest"],
        active_review_packet_digest=previous["active_review_packet_digest"],
        reviewed_snapshot_digest=previous["reviewed_snapshot_digest"],
    )
    if "unresolved_finding_ids" in current:
        current["unresolved_finding_ids"] = finding_ids
    if "blocker_fingerprints" in current:
        current["blocker_fingerprints"] = finding_fingerprints
    if current.get("pending_supersedes_digest") == prior_active_digest:
        current["pending_supersedes_digest"] = requirements_digest
    consumed_digests = {
        digest
        for digest in (chain_head, prior_review_digest)
        if isinstance(digest, str)
    }
    return {
        "envelope": envelope,
        "expected": expected_envelope(envelope),
        "consumed_digests": consumed_digests,
        "requirements": requirements,
        "report": report,
        "snapshot": snapshot,
    }


def validate_bound_review_transition(
    previous: dict[str, object],
    current: dict[str, object],
) -> list[str]:
    context = bind_review_transition_context(previous, current)
    return validate_transition(
        previous,
        current,
        review_context=context,
    )


def bind_requirements_transition_context(
    previous: dict[str, object],
    current: dict[str, object],
) -> dict[str, object]:
    """Attach a coherent validated-requirements context to test states."""
    pending_revision = previous.get("pending_requirements_revision")
    has_pending_revision = isinstance(pending_revision, int) and not isinstance(
        pending_revision,
        bool,
    )
    revision = (
        pending_revision
        if has_pending_revision
        else previous.get("active_requirements_revision")
    )
    if not isinstance(revision, int) or isinstance(revision, bool):
        revision = 1
    supersedes_digest = (
        previous.get("active_requirements_digest")
        if has_pending_revision
        else None
    )
    requirements = valid_requirements(
        requirements_revision=revision,
        supersedes_digest=supersedes_digest,
        change_reason=(
            "validated requirements revision"
            if has_pending_revision
            else "initial validated requirements"
        ),
        behavior_changed=previous.get("behavior_changed"),
        user_approval_required=previous.get("user_approval_required"),
        user_approval_received=previous.get("user_approval_received"),
        scope_changed=previous.get("scope_changed"),
        public_contract_changed=previous.get("public_contract_changed"),
        prior_evidence_invalidated=previous.get(
            "prior_evidence_invalidated"
        ),
        review_round_reset=previous.get("review_round_reset"),
        decision=current.get("latest_requirements_decision"),
    )
    requirements_digest = canonical_digest(requirements)
    chain_head = previous.get("last_consumed_packet_digest")
    envelope = valid_envelope(
        "requirements",
        requirements,
        previous_packet_digest=chain_head,
    )
    envelope_digest = canonical_digest(envelope)
    previous["pending_requirements_envelope_digest"] = envelope_digest
    current.update(
        pending_requirements_envelope_digest=None,
        last_consumed_packet_digest=envelope_digest,
    )
    if has_pending_revision:
        previous.update(
            pending_requirements_digest=requirements_digest,
            pending_supersedes_digest=supersedes_digest,
        )
        if (
            previous.get("user_approval_required") is True
            and previous.get("user_approval_received") is True
        ):
            previous[
                "pending_approved_requirements_digest"
            ] = requirements_digest
        if current.get("phase") == "USER_DECISION_REQUIRED":
            for field in packet_validator.PENDING_REVISION_PROVENANCE_FIELDS:
                current[field] = previous[field]
        if current.get("phase") == "REQUIREMENTS_FROZEN":
            current.update(
                active_requirements_revision=revision,
                active_requirements_digest=requirements_digest,
            )
    else:
        previous.update(
            active_requirements_revision=revision,
            active_requirements_digest=requirements_digest,
        )
        current.update(
            active_requirements_revision=revision,
            active_requirements_digest=requirements_digest,
        )
    return {
        "envelope": envelope,
        "expected": expected_envelope(envelope),
        "consumed_digests": (
            {chain_head} if isinstance(chain_head, str) else set()
        ),
        "requirements": requirements,
        "approval_receipt": (
            previous.get("pending_user_approval_evidence")
            if previous.get("user_approval_required") is True
            else None
        ),
    }


def validate_bound_requirements_transition(
    previous: dict[str, object],
    current: dict[str, object],
) -> list[str]:
    context = bind_requirements_transition_context(previous, current)
    return validate_transition(
        previous,
        current,
        requirements_context=context,
    )


class PacketTransportTests(unittest.TestCase):
    def test_every_documented_packet_json_example_validates(self) -> None:
        contract = (
            Path(__file__).resolve().parents[2]
            / "skills"
            / "gpt-pro-codex-loop"
            / "references"
            / "packet-contract.md"
        ).read_text(encoding="utf-8")
        examples = [
            packet_validator.strict_json_loads(body)
            for body in re.findall(r"```json\n(.*?)\n```", contract, re.DOTALL)
        ]
        self.assertEqual(5, len(examples))
        (
            requirements_envelope,
            documented_report,
            review_envelope,
            staged_review_state,
            final_gate,
        ) = examples
        requirements = requirements_envelope["payload"]
        self.assertEqual(
            [],
            packet_validator.validate_transport_envelope(
                requirements_envelope,
                expected_envelope(requirements_envelope),
                set(),
            ),
        )
        self.assertEqual(
            "sha256:93b668942c44346dda2d59fa8b77b83093f035de6f2f0d6dcdff536ec6232944",
            canonical_digest(requirements),
        )
        report = documented_report
        self.assertEqual([], validate_report(report, requirements))
        self.assertEqual(
            [],
            packet_validator.validate_transport_envelope(
                review_envelope,
                expected_envelope(review_envelope),
                set(),
            ),
        )
        self.assertEqual(
            [],
            validate_review(
                review_envelope["payload"],
                requirements,
                report,
            ),
        )
        snapshot = valid_snapshot(report)
        snapshot["baseline_head"] = report["baseline_head"]
        snapshot["tracked_diff_digest"] = report["tracked_diff_digest"]
        snapshot["untracked_manifest_digest"] = report[
            "untracked_manifest_digest"
        ]
        snapshot["snapshot_digest"] = report["snapshot_digest"]
        self.assertEqual(
            [],
            packet_validator.validate_review_context(
                review_envelope,
                requirements,
                report,
                staged_review_state,
                snapshot,
            ),
        )
        state = valid_state(
            "FINAL_VERIFICATION",
            1,
            latest_decision="PASS",
            active_requirements_digest=canonical_digest(requirements),
            active_requirements_revision=1,
            pending_review_envelope_digest=None,
            last_consumed_packet_digest="sha256:" + "5" * 64,
            last_consumed_review_envelope_digest="sha256:" + "5" * 64,
            active_report_digest=canonical_digest(report),
            current_snapshot_digest="sha256:" + "a" * 64,
            active_review_packet_digest="sha256:" + "6" * 64,
            reviewed_snapshot_digest="sha256:" + "a" * 64,
        )
        self.assertEqual(
            [],
            packet_validator.validate_final_gate(final_gate, state),
        )

    def test_extract_requires_exactly_one_json_fence(self) -> None:
        self.assertEqual(
            extract_single_json_object('```json\n{"schema_version": 1}\n```'),
            {"schema_version": 1},
        )
        for raw in ("{}", "```json\n{}\n```\n```json\n{}\n```"):
            with self.subTest(raw=raw), self.assertRaises(PacketValidationError):
                extract_single_json_object(raw)

    def test_canonical_digest_is_stable_across_key_order(self) -> None:
        self.assertEqual(canonical_digest({"a": 1, "b": 2}), canonical_digest({"b": 2, "a": 1}))

    def test_strict_json_rejects_duplicate_keys_at_every_depth(self) -> None:
        for raw in (
            '{"schema_version":1,"schema_version":1}',
            '{"schema_version":1,"payload":{"id":"first","id":"second"}}',
        ):
            with self.subTest(raw=raw), self.assertRaisesRegex(
                PacketValidationError, "duplicate JSON key"
            ):
                packet_validator.strict_json_loads(raw)

    def test_strict_json_rejects_nonstandard_numeric_constants(self) -> None:
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant), self.assertRaisesRegex(
                PacketValidationError, "non-standard JSON constant"
            ):
                packet_validator.strict_json_loads(
                    f'{{"schema_version":1,"value":{constant}}}'
                )
        with self.assertRaises(ValueError):
            canonical_digest({"value": math.nan})

    def test_transport_rejects_bom_nested_and_multiple_fences(self) -> None:
        invalid_responses = (
            '\ufeff```json\n{"schema_version":1}\n```',
            '```json\n{"note":"```json\\n{}\\n```"}\n```',
            "```json\n{}\n```\n```json\n{}\n```",
        )
        for raw in invalid_responses:
            with self.subTest(raw=raw), self.assertRaises(PacketValidationError):
                extract_single_json_object(raw)

    def test_file_loading_uses_the_strict_decoder(self) -> None:
        requirements = json.dumps(valid_requirements(), separators=(",", ":"))
        duplicate = requirements.replace(
            '"objective":"Validate the protocol."',
            '"objective":"Validate the protocol.","objective":"shadowed"',
        )
        with TemporaryDirectory() as directory:
            packet_path = Path(directory) / "requirements.json"
            packet_path.write_text(duplicate, encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(["requirements", str(packet_path)])
        self.assertEqual(result, 1)
        self.assertIn("duplicate JSON key: objective", stdout.getvalue())

    def test_wrong_container_enum_values_fail_closed_without_type_errors(self) -> None:
        envelope = valid_envelope("requirements", valid_requirements())
        expected = expected_envelope(envelope)
        envelope["packet_type"] = []
        self.assertIn(
            "packet_type: must be requirements or review",
            packet_validator.validate_transport_envelope(
                envelope,
                expected,
                set(),
            ),
        )
        self.assertIn(
            "decision: must be PLAN_READY, NEED_USER_INPUT, or BLOCK",
            validate_requirements(valid_requirements(decision=[])),
        )
        malformed_state = valid_state(
            "IMPLEMENTING",
            0,
            conversation_binding_state=[],
        )
        self.assertIn(
            "previous.conversation_binding_state: must be CONVERSATION_UNBOUND or CONVERSATION_BOUND",
            validate_transition(
                malformed_state,
                valid_state("LOCAL_VERIFICATION", 0),
            ),
        )

        requirements = valid_requirements()
        report = valid_report(requirements)
        review = valid_review(
            requirements,
            report,
            decision="CHANGES_REQUESTED",
            acceptance_results={
                "AC-1": {"status": [], "evidence": "invalid enum container"}
            },
            findings=[
                {
                    "id": "F-1",
                    "acceptance_id": "AC-1",
                    "root_cause_key": "invalid-enum-containers",
                    "severity": [],
                    "category": "correctness",
                    "required_action": [],
                    "evidence": "Invalid enum containers.",
                }
            ],
        )
        errors = validate_review(review, requirements, report)
        self.assertIn(
            "acceptance_results.AC-1.status: must be PASS, FAIL, or UNVERIFIED",
            errors,
        )
        self.assertIn(
            "findings.0.required_action: invalid required action",
            errors,
        )


class TransportEnvelopeTests(unittest.TestCase):
    def test_format_correction_requires_identical_recovered_payload(self) -> None:
        original = valid_requirements()
        corrected = valid_envelope("requirements", original)
        self.assertEqual(
            [],
            packet_validator.validate_format_correction(original, corrected),
        )
        corrected["payload"] = valid_requirements(
            objective="A semantically changed objective."
        )
        self.assertIn(
            "payload: format correction must preserve the recovered payload exactly",
            packet_validator.validate_format_correction(original, corrected),
        )

    def test_envelope_cli_uses_expected_attempt_and_consumed_receipts(self) -> None:
        envelope = valid_envelope("requirements", valid_requirements())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            envelope_path = root / "envelope.json"
            expected_path = root / "expected.json"
            consumed_path = root / "consumed.json"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
            expected_path.write_text(
                json.dumps(expected_envelope(envelope)),
                encoding="utf-8",
            )
            consumed_path.write_text(
                json.dumps({"consumed_digests": []}),
                encoding="utf-8",
            )
            with redirect_stdout(StringIO()):
                result = main(
                    [
                        "envelope",
                        str(envelope_path),
                        "--expected",
                        str(expected_path),
                        "--consumed",
                        str(consumed_path),
                    ]
                )
        self.assertEqual(0, result)

    def test_transport_envelope_matches_every_expected_header(self) -> None:
        envelope = valid_envelope("requirements", valid_requirements())
        expected = expected_envelope(envelope)
        self.assertEqual(
            packet_validator.validate_transport_envelope(envelope, expected, set()),
            [],
        )
        replacements = {
            "run_id": "gpc-loop-stale",
            "turn_id": "requirements-stale",
            "nonce": "stale-attempt",
            "in_reply_to": "sha256:" + "6" * 64,
            "prompt_digest": "sha256:" + "7" * 64,
            "previous_packet_digest": "sha256:" + "8" * 64,
        }
        for field, value in replacements.items():
            with self.subTest(field=field):
                stale = dict(envelope)
                stale[field] = value
                self.assertIn(
                    f"{field}: does not match expected transport context",
                    packet_validator.validate_transport_envelope(
                        stale, expected, set()
                    ),
                )

    def test_transport_envelope_is_exact_closed_and_not_reusable(self) -> None:
        envelope = valid_envelope("review", {"schema_version": 1})
        expected = expected_envelope(envelope)
        envelope_digest = canonical_digest(envelope)
        self.assertIn(
            "envelope_digest: response has already been consumed",
            packet_validator.validate_transport_envelope(
                envelope, expected, {envelope_digest}
            ),
        )
        unexpected = dict(envelope)
        unexpected["routing_hint"] = "trust me"
        self.assertIn(
            "routing_hint: unknown field",
            packet_validator.validate_transport_envelope(
                unexpected, expected, set()
            ),
        )

    def test_transport_envelope_rejects_boolean_version_and_header_duplication(self) -> None:
        envelope = valid_envelope("requirements", valid_requirements())
        expected = expected_envelope(envelope)
        envelope["schema_version"] = True
        self.assertIn(
            "schema_version: must be integer 1",
            packet_validator.validate_transport_envelope(
                envelope, expected, set()
            ),
        )
        duplicated = valid_envelope(
            "requirements",
            valid_requirements(run_id="payload-must-not-carry-transport"),
        )
        self.assertIn(
            "payload.run_id: unknown field",
            packet_validator.validate_transport_envelope(
                duplicated, expected_envelope(duplicated), set()
            ),
        )


class RequirementsPacketTests(unittest.TestCase):
    def test_unapproved_material_revision_can_request_user_input(self) -> None:
        previous = valid_requirements()
        revised = valid_requirements(
            requirements_revision=2,
            supersedes_digest=canonical_digest(previous),
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=False,
            prior_evidence_invalidated=True,
            review_round_reset=True,
            decision="NEED_USER_INPUT",
            open_questions=["Approve the proposed observable behavior change?"],
        )
        self.assertEqual(validate_requirements(revised, previous=previous), [])

    def test_plan_ready_requires_nonempty_requirements_and_acceptance(self) -> None:
        empty_requirements = valid_requirements(requirements=[])
        self.assertIn(
            "requirements: PLAN_READY requires at least one requirement",
            validate_requirements(empty_requirements),
        )
        empty_acceptance = valid_requirements(acceptance_criteria=[])
        self.assertIn(
            "acceptance_criteria: PLAN_READY requires at least one criterion",
            validate_requirements(empty_acceptance),
        )

    def test_closed_packets_reject_boolean_versions_and_unknown_fields(self) -> None:
        boolean_version = valid_requirements(schema_version=True)
        self.assertIn(
            "schema_version: must be integer 1",
            validate_requirements(boolean_version),
        )
        unknown = valid_requirements(transport_nonce="not-a-domain-field")
        self.assertIn("transport_nonce: unknown field", validate_requirements(unknown))
        nested_unknown = valid_requirements()
        nested_unknown["requirements"][0]["routing_hint"] = "untrusted"
        self.assertIn(
            "requirements.0.routing_hint: unknown field",
            validate_requirements(nested_unknown),
        )

    def test_initial_requirements_must_be_revision_one_without_a_supersedes_digest(self) -> None:
        self.assertIn(
            "requirements_revision: initial requirements revision must be 1",
            validate_requirements(
                valid_requirements(
                    requirements_revision=2,
                    supersedes_digest="sha256:" + "a" * 64,
                )
            ),
        )
        self.assertIn(
            "supersedes_digest: initial requirements must not supersede a digest",
            validate_requirements(
                valid_requirements(supersedes_digest="sha256:" + "a" * 64)
            ),
        )

    def test_behavior_change_requires_user_approval(self) -> None:
        revised = valid_requirements(
            requirements_revision=2,
            supersedes_digest="sha256:" + "a" * 64,
            behavior_changed=True,
            user_approval_required=False,
        )
        self.assertIn(
            "behavior changes require user approval",
            validate_requirements(revised, previous=valid_requirements()),
        )

    def test_revision_must_supersede_the_previous_digest(self) -> None:
        revised = valid_requirements(
            requirements_revision=2,
            supersedes_digest="sha256:" + "a" * 64,
        )
        self.assertIn(
            "supersedes_digest: must equal the previous requirements digest",
            validate_requirements(revised, previous=valid_requirements()),
        )

    def test_nonfinite_dependencies_return_validation_errors(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        review = valid_review(requirements, report)
        requirements["objective"] = math.nan
        self.assertIn(
            "requirements: must contain canonical finite JSON values",
            validate_report(report, requirements),
        )
        self.assertIn(
            "requirements: must contain canonical finite JSON values",
            validate_review(review, requirements, report),
        )

        previous = valid_requirements()
        previous["objective"] = math.inf
        revised = valid_requirements(
            requirements_revision=2,
            supersedes_digest="sha256:" + "a" * 64,
        )
        self.assertIn(
            "previous: must contain canonical finite JSON values",
            validate_requirements(revised, previous=previous),
        )

    def test_material_scope_change_requires_approval_and_revision_reset(self) -> None:
        previous = valid_requirements()
        revised = valid_requirements(
            requirements_revision=2,
            supersedes_digest=canonical_digest(previous),
            scope_changed=True,
        )
        errors = validate_requirements(revised, previous=previous)
        self.assertIn(
            "behavior_changed: material scope or public-contract changes require behavior_changed",
            errors,
        )
        self.assertIn("material changes require user approval", errors)
        self.assertIn("material changes require explicit user approval", errors)
        self.assertIn(
            "prior_evidence_invalidated: material changes must invalidate prior evidence",
            errors,
        )
        self.assertIn(
            "review_round_reset: material changes must reset review round",
            errors,
        )

    def test_material_public_contract_change_requires_zero_report_round(self) -> None:
        previous = valid_requirements()
        revised = valid_requirements(
            requirements_revision=2,
            supersedes_digest=canonical_digest(previous),
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            public_contract_changed=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        self.assertEqual(validate_requirements(revised, previous=previous), [])
        self.assertIn(
            "review_round: material revision requires reset to zero",
            validate_report(valid_report(revised), revised),
        )
        self.assertEqual(
            validate_report(valid_report(revised, review_round=0), revised), []
        )


class ReportPacketTests(unittest.TestCase):
    def test_acceptance_evidence_is_a_nonempty_string_list(self) -> None:
        requirements = valid_requirements()
        for invalid in (
            {"password": "hunter2"},
            ["valid", ""],
            "unit tests pass",
            [],
        ):
            with self.subTest(invalid=invalid):
                report = valid_report(
                    requirements,
                    acceptance_evidence={"AC-1": invalid},
                )
                self.assertIn(
                    "acceptance_evidence.AC-1: must be a non-empty list of non-empty strings",
                    validate_report(report, requirements),
                )

    def test_report_is_versioned_and_closed(self) -> None:
        requirements = valid_requirements()
        boolean_version = valid_report(requirements, schema_version=True)
        self.assertIn(
            "schema_version: must be integer 1",
            validate_report(boolean_version, requirements),
        )
        unknown = valid_report(requirements, routing_hint="untrusted")
        self.assertIn(
            "routing_hint: unknown field", validate_report(unknown, requirements)
        )
        nested_unknown = valid_report(requirements)
        nested_unknown["test_commands"][0]["routing_hint"] = "untrusted"
        self.assertIn(
            "test_commands.0.routing_hint: unknown field",
            validate_report(nested_unknown, requirements),
        )

    def test_report_requires_evidence_for_every_acceptance_id(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements, acceptance_evidence={})
        self.assertIn(
            "acceptance_evidence.AC-1: missing acceptance evidence",
            validate_report(report, requirements),
        )

    def test_report_requires_matching_requirements_digest(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements, requirements_digest="sha256:" + "e" * 64)
        self.assertIn(
            "requirements_digest: does not match requirements digest",
            validate_report(report, requirements),
        )

    def test_report_rejects_a_malformed_requirements_dependency(self) -> None:
        requirements = valid_requirements()
        del requirements["objective"]
        report = valid_report(requirements)
        self.assertIn(
            "requirements.objective: missing required field",
            validate_report(report, requirements),
        )

    def test_report_cli_rejects_a_malformed_requirements_dependency(self) -> None:
        requirements = valid_requirements()
        del requirements["objective"]
        report = valid_report(requirements)
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            requirements_path = directory_path / "requirements.json"
            report_path = directory_path / "report.json"
            requirements_path.write_text(json.dumps(requirements), encoding="utf-8")
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with redirect_stdout(StringIO()):
                result = main(
                    ["report", str(report_path), "--requirements", str(requirements_path)]
                )
        self.assertEqual(result, 1)


class ReviewPacketTests(unittest.TestCase):
    def test_pass_rejects_an_empty_acceptance_set(self) -> None:
        requirements = valid_requirements(acceptance_criteria=[])
        report = valid_report(requirements, acceptance_evidence={})
        review = valid_review(
            requirements,
            report,
            acceptance_results={},
        )
        self.assertIn(
            "decision: PASS requires at least one active acceptance criterion",
            validate_review(review, requirements, report),
        )

    def test_review_is_closed_and_rejects_a_model_selected_fingerprint(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        finding = {
            "id": "F-1",
            "root_cause_fingerprint": "sha256:" + "A" * 64,
            "acceptance_id": "AC-1",
            "root_cause_key": "incorrect-behavior",
            "severity": "HIGH",
            "category": "correctness",
            "required_action": "CODE_CHANGE",
            "evidence": "The behavior is incorrect.",
        }
        review = valid_review(
            requirements,
            report,
            decision="CHANGES_REQUESTED",
            findings=[finding],
        )
        self.assertIn(
            "findings.0.root_cause_fingerprint: unknown field",
            validate_review(review, requirements, report),
        )
        review["routing_hint"] = "untrusted"
        self.assertIn(
            "routing_hint: unknown field",
            validate_review(review, requirements, report),
        )
        nested_unknown = valid_review(requirements, report)
        nested_unknown["acceptance_results"]["AC-1"]["routing_hint"] = "untrusted"
        self.assertIn(
            "acceptance_results.AC-1.routing_hint: unknown field",
            validate_review(nested_unknown, requirements, report),
        )

    def test_review_derives_root_cause_fingerprint_from_stable_source_fields(
        self,
    ) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        source = {
            "acceptance_id": "AC-1",
            "category": "INSUFFICIENT_EVIDENCE",
            "required_action": "PROVIDE_EVIDENCE",
            "root_cause_key": "missing-focused-test-output",
        }
        expected = canonical_digest(source)
        finding = {
            "id": "F-1",
            **source,
            "severity": "HIGH",
            "evidence": "The report omits the focused test output.",
        }
        review = valid_review(
            requirements,
            report,
            decision="CHANGES_REQUESTED",
            findings=[finding],
        )

        self.assertEqual(
            expected,
            packet_validator.derive_root_cause_fingerprint(finding),
        )
        self.assertEqual([], validate_review(review, requirements, report))

        review["findings"] = [dict(finding, root_cause_fingerprint=expected)]
        self.assertIn(
            "findings.0.root_cause_fingerprint: unknown field",
            validate_review(review, requirements, report),
        )

    def test_root_cause_key_rename_cannot_evade_route_continuity(self) -> None:
        base = {
            "id": "F-1",
            "acceptance_id": "AC-1",
            "root_cause_key": "first-name",
            "severity": "HIGH",
            "category": "correctness",
            "required_action": "CODE_CHANGE",
            "evidence": "The same routed defect remains.",
        }
        renamed = dict(
            base,
            id="F-RENAMED",
            root_cause_key="second-name",
        )
        self.assertNotEqual(
            packet_validator.derive_root_cause_fingerprint(base),
            packet_validator.derive_root_cause_fingerprint(renamed),
        )
        self.assertEqual(
            packet_validator.derive_root_cause_route_fingerprint(base),
            packet_validator.derive_root_cause_route_fingerprint(renamed),
        )

    def test_pass_cannot_include_failed_or_unverified_acceptance(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        for status in ("FAIL", "UNVERIFIED"):
            review = valid_review(
                requirements,
                report,
                acceptance_results={"AC-1": {"status": status, "evidence": "missing"}},
            )
            with self.subTest(status=status):
                self.assertIn(
                    "decision: PASS requires every acceptance result to be PASS",
                    validate_review(review, requirements, report),
                )

    def test_review_requires_matching_snapshot_digest(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        review = valid_review(
            requirements, report, reviewed_snapshot_digest="sha256:" + "e" * 64
        )
        self.assertIn(
            "reviewed_snapshot_digest: does not match report snapshot_digest",
            validate_review(review, requirements, report),
        )

    def test_finding_requires_an_action(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        review = valid_review(
            requirements,
            report,
            decision="CHANGES_REQUESTED",
            findings=[
                {
                    "id": "F-1",
                    "acceptance_id": "AC-1",
                    "root_cause_key": "failing-test",
                    "severity": "HIGH",
                    "category": "correctness",
                    "evidence": "The test fails.",
                }
            ],
        )
        self.assertIn(
            "findings.0.required_action: missing required field",
            validate_review(review, requirements, report),
        )

    def test_evidence_action_cannot_request_a_code_change(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        review = valid_review(
            requirements,
            report,
            decision="CHANGES_REQUESTED",
            findings=[
                {
                    "id": "F-1",
                    "acceptance_id": "AC-1",
                    "root_cause_key": "omitted-output",
                    "severity": "LOW",
                    "category": "evidence",
                    "required_action": "PROVIDE_EVIDENCE",
                    "evidence": "Test output is omitted.",
                    "required_change": {"kind": "CODE_CHANGE", "description": "Rewrite code."},
                }
            ],
        )
        self.assertIn(
            "findings.0.required_change: PROVIDE_EVIDENCE cannot request a code change",
            validate_review(review, requirements, report),
        )

    def test_review_rejects_malformed_requirements_and_report_dependencies(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        review = valid_review(requirements, report)
        del requirements["constraints"]
        del report["snapshot_digest"]
        errors = validate_review(review, requirements, report)
        self.assertIn("requirements.constraints: missing required field", errors)
        self.assertIn("report.snapshot_digest: missing required field", errors)

    def test_pass_rejects_scope_violations(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        review = valid_review(
            requirements,
            report,
            scope_violations=[{"path": "deployment", "reason": "out of scope"}],
        )
        self.assertIn(
            "decision: PASS requires scope_violations to be empty",
            validate_review(review, requirements, report),
        )

    def test_pass_rejects_any_action_finding(self) -> None:
        requirements = valid_requirements()
        report = valid_report(requirements)
        review = valid_review(
            requirements,
            report,
            findings=[
                {
                    "id": "F-1",
                    "acceptance_id": "AC-1",
                    "root_cause_key": "missing-more-output",
                    "severity": "LOW",
                    "category": "evidence",
                    "required_action": "PROVIDE_EVIDENCE",
                    "evidence": "More output is needed.",
                }
            ],
        )
        self.assertIn(
            "decision: PASS requires findings to be empty",
            validate_review(review, requirements, report),
        )


class ContextValidationTests(unittest.TestCase):
    def _valid_report_context(
        self,
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
    ]:
        requirements = valid_requirements()
        report = valid_report(requirements)
        snapshot = valid_snapshot(report)
        state = valid_state(
            "REVIEW_PENDING",
            1,
            active_requirements_revision=1,
            active_requirements_digest=canonical_digest(requirements),
            active_report_digest=canonical_digest(report),
            current_snapshot_digest=snapshot["snapshot_digest"],
        )
        return report, requirements, state, snapshot

    def test_report_context_requires_active_approved_requirements(self) -> None:
        report, requirements, state, snapshot = self._valid_report_context()
        self.assertEqual(
            packet_validator.validate_report_context(
                report, requirements, state, snapshot
            ),
            [],
        )

        inactive = dict(state)
        inactive["active_requirements_digest"] = "sha256:" + "9" * 64
        self.assertIn(
            "requirements_digest: does not match active trusted requirements",
            packet_validator.validate_report_context(
                report, requirements, inactive, snapshot
            ),
        )

        unapproved_requirements = valid_requirements(
            user_approval_required=True,
            user_approval_received=False,
        )
        unapproved_report = valid_report(unapproved_requirements)
        unapproved_snapshot = valid_snapshot(unapproved_report)
        unapproved_state = dict(state)
        unapproved_state.update(
            active_requirements_digest=canonical_digest(unapproved_requirements),
            active_report_digest=canonical_digest(unapproved_report),
            current_snapshot_digest=unapproved_snapshot["snapshot_digest"],
        )
        self.assertIn(
            "requirements: required user approval is not recorded",
            packet_validator.validate_report_context(
                unapproved_report,
                unapproved_requirements,
                unapproved_state,
                unapproved_snapshot,
            ),
        )

    def test_report_context_binds_round_snapshot_and_components(self) -> None:
        report, requirements, state, snapshot = self._valid_report_context()
        wrong_round = dict(state)
        wrong_round["review_round"] = 0
        self.assertIn(
            "review_round: does not match active workflow state",
            packet_validator.validate_report_context(
                report, requirements, wrong_round, snapshot
            ),
        )
        for field in (
            "baseline_head",
            "snapshot_digest",
            "tracked_diff_digest",
            "untracked_manifest_digest",
        ):
            with self.subTest(field=field):
                mismatched = dict(snapshot)
                mismatched[field] = (
                    "f" * 40
                    if field == "baseline_head"
                    else "sha256:" + "f" * 64
                )
                self.assertIn(
                    f"snapshot.{field}: does not match implementation report",
                    packet_validator.validate_report_context(
                        report, requirements, state, mismatched
                    ),
                )

        wrong_baseline = dict(state)
        wrong_baseline["baseline_head"] = "9" * 40
        self.assertIn(
            "baseline_head: does not match trusted workflow baseline",
            packet_validator.validate_report_context(
                report, requirements, wrong_baseline, snapshot
            ),
        )
        wrong_preflight = dict(snapshot)
        wrong_preflight["preflight_digest"] = "sha256:" + "8" * 64
        self.assertIn(
            "snapshot.preflight_digest: does not match trusted preflight",
            packet_validator.validate_report_context(
                report, requirements, state, wrong_preflight
            ),
        )

    def test_review_context_requires_a_fresh_prevalidated_envelope(self) -> None:
        report, requirements, state, snapshot = self._valid_report_context()
        review = valid_review(requirements, report)
        envelope = valid_envelope("review", review)
        envelope_digest = canonical_digest(envelope)
        state.update(
            pending_review_envelope_digest=envelope_digest,
            last_consumed_packet_digest=REQ_ENVELOPE_DIGEST,
            active_review_packet_digest=canonical_digest(review),
            reviewed_snapshot_digest=review["reviewed_snapshot_digest"],
            latest_decision="PASS",
            required_actions=[],
        )
        self.assertEqual(
            packet_validator.validate_review_context(
                envelope, requirements, report, state, snapshot
            ),
            [],
        )

        not_validated = dict(state)
        not_validated["pending_review_envelope_digest"] = None
        self.assertIn(
            "pending_review_envelope_digest: review envelope was not prevalidated",
            packet_validator.validate_review_context(
                envelope, requirements, report, not_validated, snapshot
            ),
        )
        consumed = dict(state)
        consumed["last_consumed_packet_digest"] = envelope_digest
        self.assertIn(
            "pending_review_envelope_digest: review envelope is not fresh",
            packet_validator.validate_review_context(
                envelope, requirements, report, consumed, snapshot
            ),
        )

    def test_review_context_binds_finding_history_to_validated_payload(self) -> None:
        report, requirements, state, snapshot = self._valid_report_context()
        fingerprint = canonical_digest(
            {
                "acceptance_id": "AC-1",
                "category": "correctness",
                "required_action": "CODE_CHANGE",
                "root_cause_key": "context-bound",
            }
        )
        review = valid_review(
            requirements,
            report,
            decision="CHANGES_REQUESTED",
            findings=[
                {
                    "id": "F-CONTEXT",
                    "acceptance_id": "AC-1",
                    "root_cause_key": "context-bound",
                    "severity": "HIGH",
                    "category": "correctness",
                    "required_action": "CODE_CHANGE",
                    "evidence": "The validated finding remains unresolved.",
                }
            ],
        )
        envelope = valid_envelope("review", review)
        state.update(
            pending_review_envelope_digest=canonical_digest(envelope),
            last_consumed_packet_digest=REQ_ENVELOPE_DIGEST,
            active_review_packet_digest=canonical_digest(review),
            reviewed_snapshot_digest=review["reviewed_snapshot_digest"],
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-CONTEXT"],
            blocker_fingerprints=[
                fingerprint,
                packet_validator.derive_root_cause_route_fingerprint(
                    review["findings"][0]
                ),
            ],
        )
        self.assertEqual(
            packet_validator.validate_review_context(
                envelope,
                requirements,
                report,
                state,
                snapshot,
            ),
            [],
        )
        for field, forged, expected in (
            (
                "unresolved_finding_ids",
                [],
                "unresolved_finding_ids: do not match the validated review payload",
            ),
            (
                "blocker_fingerprints",
                [],
                "blocker_fingerprints: do not match the validated review payload",
            ),
        ):
            with self.subTest(field=field):
                tampered = dict(state)
                tampered[field] = forged
                self.assertIn(
                    expected,
                    packet_validator.validate_review_context(
                        envelope,
                        requirements,
                        report,
                        tampered,
                        snapshot,
                    ),
                )

class TransitionTests(unittest.TestCase):
    def test_state_is_versioned_and_closed(self) -> None:
        previous = valid_state("IMPLEMENTING", 0, schema_version=True)
        current = valid_state("LOCAL_VERIFICATION", 0)
        self.assertIn(
            "previous.schema_version: must be integer 1",
            validate_transition(previous, current),
        )
        previous["routing_hint"] = "untrusted"
        self.assertIn(
            "previous.routing_hint: unknown field",
            validate_transition(previous, current),
        )
        missing_preflight = valid_state(
            "IMPLEMENTING",
            0,
            preflight_digest=None,
        )
        self.assertIn(
            "previous.preflight_digest: must be a sha256 digest",
            validate_transition(
                missing_preflight,
                valid_state("LOCAL_VERIFICATION", 0),
            ),
        )

    def test_format_correction_cannot_mutate_domain_state(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            1,
            active_report_digest="sha256:" + "a" * 64,
            current_snapshot_digest="sha256:" + "b" * 64,
        )
        for field, value in (
            ("required_actions", ["CODE_CHANGE"]),
            ("active_report_digest", "sha256:" + "c" * 64),
            ("current_snapshot_digest", "sha256:" + "d" * 64),
            ("baseline_head", "9" * 40),
            ("approved_existing_paths", ["unexpected.py"]),
        ):
            with self.subTest(field=field):
                current = dict(previous)
                current["format_error_count"] = 1
                current[field] = value
                self.assertIn(
                    f"{field}: format correction must preserve domain state",
                    validate_transition(previous, current),
                )

    def test_review_stop_resume_clears_consumed_routing_data(self) -> None:
        stopped = valid_state(
            "USER_DECISION_REQUIRED",
            1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["USER_DECISION"],
            pending_review_envelope_digest=REVIEW_ENVELOPE_DIGEST,
            last_consumed_packet_digest=REVIEW_ENVELOPE_DIGEST,
            last_consumed_review_envelope_digest=REVIEW_ENVELOPE_DIGEST,
            stop_origin_phase="REVIEW_PENDING",
            stop_origin_category="REVIEW_USER_DECISION",
            stop_reason="The review requires a user decision.",
            stop_sequence=1,
        )
        resumed = valid_state(
            "IMPLEMENTING",
            1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["USER_DECISION"],
            pending_review_envelope_digest=REVIEW_ENVELOPE_DIGEST,
            last_consumed_packet_digest=REVIEW_ENVELOPE_DIGEST,
            last_consumed_review_envelope_digest=REVIEW_ENVELOPE_DIGEST,
            stop_sequence=1,
            resolution_evidence="The user resolved the decision.",
            resolution_stop_sequence=1,
        )
        errors = validate_transition(stopped, resumed)
        self.assertIn(
            "latest_decision: review-stop resume must clear the consumed decision",
            errors,
        )
        self.assertIn(
            "required_actions: review-stop resume must clear consumed actions",
            errors,
        )
        self.assertIn(
            "pending_review_envelope_digest: review-stop resume must clear pending review identity",
            errors,
        )

    def test_review_consumption_requires_and_promotes_fresh_envelope_identity(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            1,
            latest_decision="PASS",
            pending_review_envelope_digest=REVIEW_ENVELOPE_DIGEST,
            last_consumed_packet_digest=REQ_ENVELOPE_DIGEST,
            active_review_packet_digest=REVIEW_PACKET_DIGEST,
            reviewed_snapshot_digest="sha256:" + "b" * 64,
        )
        current = valid_state(
            "FINAL_VERIFICATION",
            2,
            latest_decision="PASS",
            last_consumed_packet_digest=REVIEW_ENVELOPE_DIGEST,
            last_consumed_review_envelope_digest=REVIEW_ENVELOPE_DIGEST,
            active_review_packet_digest=REVIEW_PACKET_DIGEST,
            reviewed_snapshot_digest="sha256:" + "b" * 64,
        )
        self.assertIn(
            "review_context: explicit composed context is required for review consumption",
            validate_transition(previous, current),
        )
        context = bind_review_transition_context(previous, current)
        self.assertEqual(
            validate_transition(
                previous,
                current,
                review_context=context,
            ),
            [],
        )
        forged_history = dict(current)
        forged_history["unresolved_finding_ids"] = ["F-FORGED"]
        self.assertIn(
            "review_context.unresolved_finding_ids: do not match the validated review payload",
            validate_transition(
                previous,
                forged_history,
                review_context=context,
            ),
        )
        replayed = dict(previous)
        replayed["last_consumed_packet_digest"] = previous[
            "pending_review_envelope_digest"
        ]
        self.assertIn(
            "pending_review_envelope_digest: review response must be fresh",
            validate_transition(
                replayed,
                current,
                review_context=context,
            ),
        )

    def test_complete_requires_explicit_bound_final_gate_evidence(self) -> None:
        state_fields = {
            "active_requirements_digest": "sha256:" + "a" * 64,
            "active_report_digest": "sha256:" + "e" * 64,
            "active_review_packet_digest": REVIEW_PACKET_DIGEST,
            "reviewed_snapshot_digest": "sha256:" + "b" * 64,
            "current_snapshot_digest": "sha256:" + "b" * 64,
            "last_consumed_packet_digest": REVIEW_ENVELOPE_DIGEST,
            "last_consumed_review_envelope_digest": REVIEW_ENVELOPE_DIGEST,
        }
        previous = valid_state(
            "FINAL_VERIFICATION",
            2,
            latest_decision="PASS",
            **state_fields,
        )
        current = valid_state(
            "COMPLETE",
            2,
            latest_decision="PASS",
            **state_fields,
        )
        self.assertIn(
            "final_gate: explicit validated evidence is required for COMPLETE",
            validate_transition(previous, current),
        )
        evidence = {
            "schema_version": 1,
            "requirements_digest": state_fields["active_requirements_digest"],
            "review_packet_digest": state_fields["active_review_packet_digest"],
            "reviewed_snapshot_digest": state_fields["reviewed_snapshot_digest"],
            "current_snapshot_digest": state_fields["current_snapshot_digest"],
            "acceptance_gate_passed": True,
            "local_checks_passed": True,
            "scope_gate_passed": True,
            "artifact_hygiene_passed": True,
        }
        self.assertEqual(
            packet_validator.validate_final_gate(evidence, previous),
            [],
        )
        self.assertEqual(
            validate_transition(
                previous,
                current,
                final_gate_evidence=evidence,
            ),
            [],
        )
        tampered_complete = dict(current)
        tampered_complete["active_review_packet_digest"] = (
            "sha256:" + "f" * 64
        )
        self.assertIn(
            "active_review_packet_digest: COMPLETE must preserve final-gate bindings",
            validate_transition(
                previous,
                tampered_complete,
                final_gate_evidence=evidence,
            ),
        )

    def test_approved_material_revision_promotes_and_consumes_provenance(self) -> None:
        review_pending = valid_state(
            "REVIEW_PENDING",
            1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
        )
        pending = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            pending_approval_sequence=1,
            pending_approved_requirements_digest="sha256:" + "b" * 64,
            pending_user_approval_evidence="The user approved revision 2.",
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        self.assertEqual(
            validate_bound_review_transition(review_pending, pending),
            [],
        )

        frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            latest_decision="CHANGES_REQUESTED",
            latest_requirements_decision="PLAN_READY",
            required_actions=["REQUIREMENTS_REVISION"],
            active_requirements_revision=2,
            active_requirements_digest="sha256:" + "b" * 64,
            approval_sequence=1,
            last_consumed_packet_digest=REQ_ENVELOPE_DIGEST,
        )
        self.assertIn(
            "requirements_context: explicit composed context is required for requirements consumption",
            validate_transition(pending, frozen),
        )
        requirements_context = bind_requirements_transition_context(
            pending,
            frozen,
        )
        self.assertEqual(
            validate_transition(
                pending,
                frozen,
                requirements_context=requirements_context,
            ),
            [],
        )
        forged_approval = dict(requirements_context)
        forged_approval["approval_receipt"] = "Approval for another packet."
        self.assertIn(
            "requirements_context.approval_receipt: does not match trusted pending approval evidence",
            validate_transition(
                pending,
                frozen,
                requirements_context=forged_approval,
            ),
        )

    def test_nonmaterial_revision_promotes_without_resetting_review_round(self) -> None:
        pending = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            prior_evidence_invalidated=True,
        )
        frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            2,
            latest_requirements_decision="PLAN_READY",
            active_requirements_revision=2,
            active_requirements_digest="sha256:" + "b" * 64,
        )
        self.assertEqual(
            validate_bound_requirements_transition(pending, frozen),
            [],
        )

    def test_material_reset_rejects_self_asserted_or_unapproved_authority(self) -> None:
        no_pending_provenance = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
        )
        self_asserted = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            latest_decision="CHANGES_REQUESTED",
            latest_requirements_decision="PLAN_READY",
            required_actions=["REQUIREMENTS_REVISION"],
            review_round_reset=True,
            user_approval_received=True,
        )
        self.assertIn(
            "pending_requirements_revision: material reset requires the next requirements revision",
            validate_transition(no_pending_provenance, self_asserted),
        )

        unapproved = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            pending_approval_sequence=1,
            pending_approved_requirements_digest="sha256:" + "b" * 64,
            pending_user_approval_evidence="The user approved revision 2.",
            behavior_changed=True,
            user_approval_required=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        self.assertIn(
            "user_approval_received: material reset requires explicit user approval",
            validate_transition(
                unapproved,
                valid_state(
                    "REQUIREMENTS_FROZEN",
                    0,
                    latest_requirements_decision="PLAN_READY",
                    active_requirements_revision=2,
                    active_requirements_digest="sha256:" + "b" * 64,
                ),
            ),
        )

    def test_material_reset_rejects_mismatched_revision_and_digest_provenance(self) -> None:
        valid_pending = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            pending_approval_sequence=1,
            pending_approved_requirements_digest="sha256:" + "b" * 64,
            pending_user_approval_evidence="The user approved revision 2.",
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        valid_frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            latest_requirements_decision="PLAN_READY",
            active_requirements_revision=2,
            active_requirements_digest="sha256:" + "b" * 64,
            approval_sequence=1,
        )
        cases = (
            (
                dict(valid_pending, pending_requirements_revision=3),
                valid_frozen,
                "pending_requirements_revision: material reset requires the next requirements revision",
            ),
            (
                dict(
                    valid_pending,
                    pending_requirements_digest="sha256:" + "a" * 64,
                ),
                valid_frozen,
                "pending_requirements_digest: material reset requires a new requirements digest",
            ),
            (
                dict(
                    valid_pending,
                    pending_supersedes_digest="sha256:" + "c" * 64,
                ),
                valid_frozen,
                "pending_supersedes_digest: must equal the active requirements digest",
            ),
            (
                valid_pending,
                dict(valid_frozen, active_requirements_revision=1),
                "active_requirements_revision: frozen state must promote the pending revision",
            ),
            (
                valid_pending,
                dict(
                    valid_frozen,
                    active_requirements_digest="sha256:" + "c" * 64,
                ),
                "active_requirements_digest: frozen state must promote the pending digest",
            ),
        )
        for pending, frozen, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, validate_transition(pending, frozen))

    def test_material_reset_requires_and_consumes_every_authorization_field(self) -> None:
        valid_pending = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            pending_approval_sequence=1,
            pending_approved_requirements_digest="sha256:" + "b" * 64,
            pending_user_approval_evidence="The user approved revision 2.",
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        valid_frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            latest_requirements_decision="PLAN_READY",
            active_requirements_revision=2,
            active_requirements_digest="sha256:" + "b" * 64,
            approval_sequence=1,
        )
        cases = (
            (
                dict(valid_pending, required_actions=[]),
                valid_frozen,
                "required_actions: material reset requires prior REQUIREMENTS_REVISION routing",
            ),
            (
                dict(valid_pending, behavior_changed=False),
                valid_frozen,
                "behavior_changed: material reset requires a behavior, scope, or public-contract change",
            ),
            (
                dict(valid_pending, user_approval_required=False),
                valid_frozen,
                "user_approval_required: material reset requires user approval",
            ),
            (
                dict(valid_pending, user_approval_received=False),
                valid_frozen,
                "user_approval_received: material reset requires explicit user approval",
            ),
            (
                dict(valid_pending, prior_evidence_invalidated=False),
                valid_frozen,
                "prior_evidence_invalidated: material reset must invalidate prior evidence",
            ),
            (
                dict(valid_pending, review_round_reset=False),
                valid_frozen,
                "review_round_reset: material revision must require a reset",
            ),
            (
                valid_pending,
                dict(valid_frozen, user_approval_received=True),
                "user_approval_received: frozen state must consume pending revision flags",
            ),
            (
                valid_pending,
                dict(valid_frozen, pending_requirements_revision=2),
                "pending_requirements_revision: frozen state must consume pending requirements provenance",
            ),
        )
        for pending, frozen, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, validate_transition(pending, frozen))

    def test_material_reset_authorization_cannot_be_replayed(self) -> None:
        replayed_pending = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            active_requirements_revision=2,
            active_requirements_digest="sha256:" + "b" * 64,
            approval_sequence=1,
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            pending_approval_sequence=1,
            pending_approved_requirements_digest="sha256:" + "b" * 64,
            pending_user_approval_evidence="The user approved revision 2.",
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
        )
        replayed_frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            active_requirements_revision=2,
            active_requirements_digest="sha256:" + "b" * 64,
            approval_sequence=1,
            latest_requirements_decision="PLAN_READY",
        )
        errors = validate_transition(replayed_pending, replayed_frozen)
        self.assertIn(
            "pending_requirements_revision: material reset requires the next requirements revision",
            errors,
        )
        self.assertIn(
            "pending_requirements_digest: material reset requires a new requirements digest",
            errors,
        )

    def test_material_reset_rejects_replayed_approval_event(self) -> None:
        stale_approval = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            active_requirements_revision=2,
            active_requirements_digest="sha256:" + "b" * 64,
            approval_sequence=1,
            pending_requirements_revision=3,
            pending_requirements_digest="sha256:" + "c" * 64,
            pending_supersedes_digest="sha256:" + "b" * 64,
            pending_approval_sequence=1,
            pending_approved_requirements_digest="sha256:" + "b" * 64,
            pending_user_approval_evidence="The user approved revision 2.",
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
        )
        frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            active_requirements_revision=3,
            active_requirements_digest="sha256:" + "c" * 64,
            approval_sequence=1,
            latest_requirements_decision="PLAN_READY",
        )
        errors = validate_transition(stale_approval, frozen)
        self.assertIn(
            "pending_approval_sequence: material reset requires a fresh approval event",
            errors,
        )
        self.assertIn(
            "pending_approved_requirements_digest: must equal the pending requirements digest",
            errors,
        )

    def test_maintenance_cannot_inject_material_reset_provenance(self) -> None:
        pending_without_revision = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
        )
        injected = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
            browser_reconnect_count=1,
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        self.assertIn(
            "pending_requirements: maintenance transitions must preserve revision provenance",
            validate_transition(pending_without_revision, injected),
        )

    def test_material_reset_provenance_exists_only_while_requirements_are_pending(self) -> None:
        injected = valid_state(
            "LOCAL_VERIFICATION",
            2,
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        self.assertIn(
            "current.pending_requirements: revision provenance is allowed only while requirements are pending or awaiting approval",
            validate_transition(valid_state("IMPLEMENTING", 2), injected),
        )

    def test_preflight_cannot_self_assert_material_reset_provenance(self) -> None:
        injected = valid_state(
            "REQUIREMENTS_PENDING",
            0,
            pending_requirements_revision=2,
            pending_requirements_digest="sha256:" + "b" * 64,
            pending_supersedes_digest="sha256:" + "a" * 64,
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=True,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        self.assertIn(
            "pending_requirements: provenance may be introduced only by requirements revision routing or a resolved requirements stop",
            validate_transition(valid_state("PREFLIGHT", 0), injected),
        )

    def test_active_requirements_provenance_is_initialized_once_after_preflight(self) -> None:
        self.assertEqual(
            validate_transition(
                valid_state("PREFLIGHT", 0),
                valid_state("REQUIREMENTS_PENDING", 0),
            ),
            [],
        )

        null_pending = valid_state(
            "REQUIREMENTS_PENDING",
            0,
            active_requirements_revision=None,
            active_requirements_digest=None,
        )
        null_frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            latest_requirements_decision="PLAN_READY",
            active_requirements_revision=None,
            active_requirements_digest=None,
        )
        self.assertIn(
            "current.active_requirements: revision and digest are required after preflight",
            validate_transition(null_pending, null_frozen),
        )

        late_source = valid_state(
            "IMPLEMENTING",
            1,
            active_requirements_revision=None,
            active_requirements_digest=None,
        )
        late_injection = valid_state(
            "LOCAL_VERIFICATION",
            1,
            active_requirements_revision=99,
            active_requirements_digest="sha256:" + "b" * 64,
        )
        self.assertIn(
            "active_requirements: may be initialized only when preflight enters requirements pending",
            validate_transition(late_source, late_injection),
        )

    def test_requirements_stops_resume_with_provenance_without_consuming_round(self) -> None:
        previous = valid_state("REQUIREMENTS_PENDING", 2)
        routes = (
            (
                "NEED_USER_INPUT",
                "USER_DECISION_REQUIRED",
                "REQUIREMENTS_NEED_USER_INPUT",
            ),
            ("BLOCK", "BLOCKED", "REQUIREMENTS_BLOCK"),
        )
        for decision, target, category in routes:
            with self.subTest(decision=decision):
                stopped = valid_state(
                    target,
                    2,
                    latest_requirements_decision=decision,
                    stop_origin_phase="REQUIREMENTS_PENDING",
                    stop_origin_category=category,
                    stop_reason="Requirements need explicit user resolution.",
                    stop_sequence=1,
                )
                self.assertEqual(
                    validate_bound_requirements_transition(
                        previous,
                        stopped,
                    ),
                    [],
                )
                resumed = valid_state(
                    "REQUIREMENTS_PENDING",
                    2,
                    active_requirements_revision=stopped[
                        "active_requirements_revision"
                    ],
                    active_requirements_digest=stopped[
                        "active_requirements_digest"
                    ],
                    stop_sequence=1,
                    resolution_evidence="The user supplied the required decision.",
                    resolution_stop_sequence=1,
                )
                self.assertEqual(validate_transition(stopped, resumed), [])

        wrong_route = valid_state(
            "REQUIREMENTS_FROZEN",
            2,
            latest_requirements_decision="NEED_USER_INPUT",
        )
        self.assertIn(
            "phase: requirements routing requires transition to USER_DECISION_REQUIRED, not REQUIREMENTS_FROZEN",
            validate_transition(previous, wrong_route),
        )

    def test_unapproved_material_revision_is_approved_and_promoted_exactly(self) -> None:
        active_digest = canonical_digest(valid_requirements())
        proposal_digest = "sha256:" + "6" * 64
        previous = valid_state(
            "REQUIREMENTS_PENDING",
            1,
            required_actions=["REQUIREMENTS_REVISION"],
            active_requirements_revision=1,
            active_requirements_digest=active_digest,
            pending_requirements_revision=2,
            pending_requirements_digest=proposal_digest,
            pending_supersedes_digest=active_digest,
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=False,
            prior_evidence_invalidated=True,
            review_round_reset=True,
        )
        stopped = valid_state(
            "USER_DECISION_REQUIRED",
            1,
            latest_requirements_decision="NEED_USER_INPUT",
            required_actions=["REQUIREMENTS_REVISION"],
            active_requirements_revision=1,
            active_requirements_digest=active_digest,
            pending_requirements_revision=2,
            pending_requirements_digest=proposal_digest,
            pending_supersedes_digest=active_digest,
            behavior_changed=True,
            user_approval_required=True,
            user_approval_received=False,
            prior_evidence_invalidated=True,
            review_round_reset=True,
            stop_origin_phase="REQUIREMENTS_PENDING",
            stop_origin_category="REQUIREMENTS_NEED_USER_INPUT",
            stop_reason="The proposed material revision needs user approval.",
            stop_sequence=1,
        )
        requirements_context = bind_requirements_transition_context(
            previous,
            stopped,
        )
        self.assertEqual(
            validate_transition(
                previous,
                stopped,
                requirements_context=requirements_context,
            ),
            [],
        )
        approved_proposal = requirements_context["requirements"]
        proposal_digest = stopped["pending_requirements_digest"]
        approval_receipt = f"user-approval:stop-1:{proposal_digest}"
        frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            active_requirements_revision=2,
            active_requirements_digest=proposal_digest,
            approval_sequence=1,
            stop_sequence=1,
            resolution_evidence=approval_receipt,
            resolution_stop_sequence=1,
        )
        self.assertEqual(validate_transition(stopped, frozen), [])
        implementation_state = valid_state(
            "LOCAL_VERIFICATION",
            0,
            active_requirements_revision=2,
            active_requirements_digest=proposal_digest,
            approval_sequence=1,
        )
        report = valid_report(approved_proposal, review_round=0)
        snapshot = valid_snapshot(report)
        implementation_state.update(
            active_report_digest=canonical_digest(report),
            current_snapshot_digest=report["snapshot_digest"],
        )
        self.assertEqual(
            packet_validator.validate_report_context(
                report,
                approved_proposal,
                implementation_state,
                snapshot,
            ),
            [],
        )

        swapped = dict(frozen)
        swapped["active_requirements_digest"] = "sha256:" + "7" * 64
        self.assertIn(
            "active_requirements_digest: frozen state must promote the pending digest",
            validate_transition(stopped, swapped),
        )

        unbound_receipt = dict(frozen)
        unbound_receipt["resolution_evidence"] = "The user approved revision 2."
        self.assertIn(
            "resolution_evidence: material approval must bind the stop sequence and pending requirements digest",
            validate_transition(stopped, unbound_receipt),
        )

    def test_stop_entry_requires_actual_origin_category_and_reason(self) -> None:
        previous = valid_state("REQUIREMENTS_PENDING", 2)
        base = valid_state(
            "USER_DECISION_REQUIRED",
            2,
            latest_requirements_decision="NEED_USER_INPUT",
            stop_origin_phase="REQUIREMENTS_PENDING",
            stop_origin_category="REQUIREMENTS_NEED_USER_INPUT",
            stop_reason="A product choice remains open.",
            stop_sequence=1,
        )
        cases = (
            (
                dict(base, stop_origin_phase="REVIEW_PENDING"),
                "stop_origin_phase: must match the actual stop origin REQUIREMENTS_PENDING",
            ),
            (
                dict(base, stop_origin_category="REVIEW_USER_DECISION"),
                "stop_origin_category: does not match the stop route",
            ),
            (
                dict(base, stop_reason=None),
                "stop_reason: stop entry requires a non-empty reason",
            ),
            (
                dict(base, resolution_evidence="Forged early resolution."),
                "resolution_evidence: must be null when entering a stop state",
            ),
            (
                dict(base, stop_sequence=0),
                "stop_sequence: stop entry must increment exactly once",
            ),
        )
        for stopped, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, validate_transition(previous, stopped))

    def test_review_and_final_verification_stops_record_route_provenance(self) -> None:
        cases = (
            (
                valid_state(
                    "REVIEW_PENDING",
                    1,
                    latest_decision="CHANGES_REQUESTED",
                    required_actions=["USER_DECISION"],
                ),
                valid_state(
                    "USER_DECISION_REQUIRED",
                    2,
                    latest_decision="CHANGES_REQUESTED",
                    required_actions=["USER_DECISION"],
                    stop_origin_phase="REVIEW_PENDING",
                    stop_origin_category="REVIEW_USER_DECISION",
                    stop_reason="The review requires a user decision.",
                    stop_sequence=1,
                ),
            ),
            (
                valid_state(
                    "REVIEW_PENDING",
                    1,
                    latest_decision="BLOCK",
                ),
                valid_state(
                    "USER_DECISION_REQUIRED",
                    2,
                    latest_decision="BLOCK",
                    stop_origin_phase="REVIEW_PENDING",
                    stop_origin_category="REVIEW_BLOCK",
                    stop_reason="The review reported a blocker.",
                    stop_sequence=1,
                ),
            ),
            (
                valid_state("FINAL_VERIFICATION", 2, latest_decision="PASS"),
                valid_state(
                    "BLOCKED",
                    2,
                    latest_decision="PASS",
                    stop_origin_phase="FINAL_VERIFICATION",
                    stop_origin_category="FINAL_VERIFICATION_BLOCK",
                    stop_reason="A final local gate cannot proceed.",
                    stop_sequence=1,
                ),
            ),
        )
        for previous, stopped in cases:
            with self.subTest(category=stopped["stop_origin_category"]):
                errors = (
                    validate_bound_review_transition(previous, stopped)
                    if previous["phase"] == "REVIEW_PENDING"
                    else validate_transition(previous, stopped)
                )
                self.assertEqual(errors, [])

    def test_stop_resume_target_is_bound_to_origin_not_stale_decision_labels(self) -> None:
        review_stop = valid_state(
            "USER_DECISION_REQUIRED",
            2,
            latest_decision="CHANGES_REQUESTED",
            latest_requirements_decision="NEED_USER_INPUT",
            required_actions=["USER_DECISION"],
            stop_origin_phase="REVIEW_PENDING",
            stop_origin_category="REVIEW_USER_DECISION",
            stop_reason="The review requires a user decision.",
            stop_sequence=1,
        )
        self.assertIn(
            "phase: REVIEW_USER_DECISION stop may resume only to IMPLEMENTING or REVIEW_PENDING, not REQUIREMENTS_PENDING",
            validate_transition(
                review_stop,
                valid_state(
                    "REQUIREMENTS_PENDING",
                    2,
                    stop_sequence=1,
                    resolution_evidence="A stale requirements label was forged.",
                    resolution_stop_sequence=1,
                ),
            ),
        )

        final_stop = valid_state(
            "BLOCKED",
            2,
            latest_requirements_decision="BLOCK",
            stop_origin_phase="FINAL_VERIFICATION",
            stop_origin_category="FINAL_VERIFICATION_BLOCK",
            stop_reason="A final local gate cannot proceed.",
            stop_sequence=1,
        )
        self.assertIn(
            "phase: FINAL_VERIFICATION_BLOCK stop may resume only to FINAL_VERIFICATION or IMPLEMENTING, not REQUIREMENTS_PENDING",
            validate_transition(
                final_stop,
                valid_state(
                    "REQUIREMENTS_PENDING",
                    2,
                    stop_sequence=1,
                    resolution_evidence="A stale requirements label was forged.",
                    resolution_stop_sequence=1,
                ),
            ),
        )

    def test_review_and_final_stops_resume_only_with_resolution_evidence(self) -> None:
        review_stop = valid_state(
            "USER_DECISION_REQUIRED",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["USER_DECISION"],
            stop_origin_phase="REVIEW_PENDING",
            stop_origin_category="REVIEW_USER_DECISION",
            stop_reason="The review requires a user decision.",
            stop_sequence=1,
        )
        self.assertEqual(
            validate_transition(
                review_stop,
                valid_state(
                    "IMPLEMENTING",
                    2,
                    stop_sequence=1,
                    resolution_evidence="The user selected the implementation behavior.",
                    resolution_stop_sequence=1,
                ),
            ),
            [],
        )
        self.assertIn(
            "resolution_evidence: stop resume requires explicit resolution evidence",
            validate_transition(
                review_stop,
                valid_state("IMPLEMENTING", 2, stop_sequence=1),
            ),
        )

        final_stop = valid_state(
            "BLOCKED",
            2,
            stop_origin_phase="FINAL_VERIFICATION",
            stop_origin_category="FINAL_VERIFICATION_BLOCK",
            stop_reason="A final local gate cannot proceed.",
            stop_sequence=1,
        )
        self.assertEqual(
            validate_transition(
                final_stop,
                valid_state(
                    "FINAL_VERIFICATION",
                    2,
                    stop_sequence=1,
                    resolution_evidence="The unavailable local gate is restored.",
                    resolution_stop_sequence=1,
                ),
            ),
            [],
        )

    def test_resume_consumes_stop_provenance_and_resolution_is_one_shot(self) -> None:
        stopped = valid_state(
            "USER_DECISION_REQUIRED",
            1,
            latest_requirements_decision="NEED_USER_INPUT",
            stop_origin_phase="REQUIREMENTS_PENDING",
            stop_origin_category="REQUIREMENTS_NEED_USER_INPUT",
            stop_reason="A product choice remains open.",
            stop_sequence=1,
        )
        retained = valid_state(
            "REQUIREMENTS_PENDING",
            1,
            stop_origin_phase="REQUIREMENTS_PENDING",
            stop_origin_category="REQUIREMENTS_NEED_USER_INPUT",
            stop_reason="A product choice remains open.",
            stop_sequence=1,
            resolution_evidence="The user resolved the choice.",
            resolution_stop_sequence=1,
        )
        self.assertIn(
            "stop_provenance: resume must consume origin phase, category, and reason",
            validate_transition(stopped, retained),
        )

        resumed = valid_state(
            "REQUIREMENTS_PENDING",
            1,
            stop_sequence=1,
            resolution_evidence="The user resolved the choice.",
            resolution_stop_sequence=1,
        )
        replayed = valid_state(
            "REQUIREMENTS_FROZEN",
            1,
            latest_requirements_decision="PLAN_READY",
            stop_sequence=1,
            resolution_evidence="The user resolved the choice.",
            resolution_stop_sequence=1,
        )
        self.assertIn(
            "resolution_evidence: must be cleared after the resumed transition",
            validate_transition(resumed, replayed),
        )

    def test_resolution_evidence_is_bound_to_the_current_stop_sequence(self) -> None:
        pending = valid_state("REQUIREMENTS_PENDING", 1)
        first_stop = valid_state(
            "USER_DECISION_REQUIRED",
            1,
            latest_requirements_decision="NEED_USER_INPUT",
            stop_origin_phase="REQUIREMENTS_PENDING",
            stop_origin_category="REQUIREMENTS_NEED_USER_INPUT",
            stop_reason="A product choice remains open.",
            stop_sequence=1,
        )
        first_resume = valid_state(
            "REQUIREMENTS_PENDING",
            1,
            pending_requirements_envelope_digest=REQ_ENVELOPE_DIGEST_2,
            stop_sequence=1,
            resolution_evidence="The user resolved the choice.",
            resolution_stop_sequence=1,
        )
        second_stop = valid_state(
            "USER_DECISION_REQUIRED",
            1,
            latest_requirements_decision="NEED_USER_INPUT",
            stop_origin_phase="REQUIREMENTS_PENDING",
            stop_origin_category="REQUIREMENTS_NEED_USER_INPUT",
            stop_reason="A later product choice remains open.",
            stop_sequence=2,
            last_consumed_packet_digest=REQ_ENVELOPE_DIGEST_2,
        )
        self.assertEqual(
            validate_bound_requirements_transition(pending, first_stop),
            [],
        )
        first_resume["last_consumed_packet_digest"] = first_stop[
            "last_consumed_packet_digest"
        ]
        first_resume["active_requirements_revision"] = first_stop[
            "active_requirements_revision"
        ]
        first_resume["active_requirements_digest"] = first_stop[
            "active_requirements_digest"
        ]
        self.assertEqual(validate_transition(first_stop, first_resume), [])
        self.assertEqual(
            validate_bound_requirements_transition(first_resume, second_stop),
            [],
        )

        replayed_resolution = valid_state(
            "REQUIREMENTS_PENDING",
            1,
            stop_sequence=2,
            resolution_evidence="The user resolved the choice.",
            resolution_stop_sequence=1,
        )
        self.assertIn(
            "resolution_stop_sequence: must match the current stop sequence",
            validate_transition(second_stop, replayed_resolution),
        )

    def test_conversation_is_bound_once_then_preserved_with_visible_model(self) -> None:
        unbound = valid_state(
            "PREFLIGHT",
            0,
            conversation_binding_state="CONVERSATION_UNBOUND",
            bound_conversation_url=None,
            visible_model_label=None,
        )
        bound = valid_state("REQUIREMENTS_PENDING", 0)
        self.assertEqual(validate_transition(unbound, bound), [])

        for field, value in (
            ("bound_conversation_url", "https://chatgpt.com/c/other-conversation"),
            ("visible_model_label", "Free"),
        ):
            with self.subTest(field=field):
                mismatched = valid_state("LOCAL_VERIFICATION", 0)
                mismatched[field] = value
                errors = validate_transition(
                    valid_state("IMPLEMENTING", 0),
                    mismatched,
                )
                expected = (
                    f"{field}: must match the bound conversation state"
                    if field == "bound_conversation_url"
                    else "current.visible_model_label: must equal the controlled Pro-class label Pro"
                )
                self.assertIn(expected, errors)

        missing_identity = valid_state("LOCAL_VERIFICATION", 0)
        del missing_identity["bound_conversation_url"]
        self.assertIn(
            "current.bound_conversation_url: missing required field",
            validate_transition(
                valid_state("IMPLEMENTING", 0),
                missing_identity,
            ),
        )

    def test_model_policy_rejects_silent_downgrade_or_wrong_exact_label(self) -> None:
        previous = valid_state("PREFLIGHT", 0)
        wrong_class = valid_state(
            "REQUIREMENTS_PENDING",
            0,
            visible_model_label="Standard",
        )
        self.assertIn(
            "current.visible_model_label: must equal the controlled Pro-class label Pro",
            validate_transition(previous, wrong_class),
        )

        exact_previous = valid_state(
            "PREFLIGHT",
            0,
            model_policy="EXACT_LABEL",
            requested_model_label="GPT-X Pro",
            visible_model_label="GPT-X Pro",
        )
        wrong_exact = valid_state(
            "REQUIREMENTS_PENDING",
            0,
            model_policy="EXACT_LABEL",
            requested_model_label="GPT-X Pro",
            visible_model_label="GPT-Y Pro",
        )
        self.assertIn(
            "current.visible_model_label: must exactly match requested_model_label",
            validate_transition(exact_previous, wrong_exact),
        )

    def test_transition_requires_complete_structured_state_packets(self) -> None:
        shorthand_errors = validate_transition(
            "PREFLIGHT",
            "REQUIREMENTS_PENDING",
        )
        self.assertIn("previous: must be a state object", shorthand_errors)
        self.assertIn("current: must be a state object", shorthand_errors)

        required_fields = (
            "schema_version",
            "review_round",
            "latest_decision",
            "latest_requirements_decision",
            "required_actions",
            "format_error_count",
            "browser_reconnect_count",
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
        for field in required_fields:
            with self.subTest(field=field):
                incomplete = valid_state("IMPLEMENTING", 0)
                del incomplete[field]
                self.assertIn(
                    f"previous.{field}: missing required field",
                    validate_transition(
                        incomplete,
                        valid_state("LOCAL_VERIFICATION", 0),
                    ),
                )

    def test_transition_rejects_an_illegal_edge(self) -> None:
        self.assertIn(
            "phase: illegal transition from PREFLIGHT to IMPLEMENTING",
            validate_transition(
                valid_state("PREFLIGHT", 0), valid_state("IMPLEMENTING", 0)
            ),
        )

    def test_transition_blocks_the_second_format_error(self) -> None:
        self.assertIn(
            "format_error_count: repeated malformed response blocks the loop",
            validate_transition(
                valid_state("REQUIREMENTS_PENDING", 0, format_error_count=1),
                valid_state("REQUIREMENTS_PENDING", 0, format_error_count=2),
            ),
        )

    def test_review_routing_uses_required_latest_decision(self) -> None:
        cases = (
            ("PASS", [], "FINAL_VERIFICATION", {}),
            ("CHANGES_REQUESTED", ["CODE_CHANGE"], "IMPLEMENTING", {}),
            (
                "BLOCK",
                [],
                "USER_DECISION_REQUIRED",
                {
                    "stop_origin_phase": "REVIEW_PENDING",
                    "stop_origin_category": "REVIEW_BLOCK",
                    "stop_reason": "The review reported a blocker.",
                    "stop_sequence": 1,
                },
            ),
        )
        for decision, actions, phase, stop_provenance in cases:
            with self.subTest(decision=decision):
                previous = valid_state(
                    "REVIEW_PENDING",
                    0,
                    latest_decision=decision,
                    required_actions=actions,
                )
                current = valid_state(
                    phase,
                    1,
                    latest_decision=decision,
                    required_actions=actions,
                    **stop_provenance,
                )
                self.assertEqual(
                    validate_bound_review_transition(previous, current),
                    [],
                )
        previous = valid_state("REVIEW_PENDING", 0)
        missing_decision = valid_state("FINAL_VERIFICATION", 1)
        self.assertIn(
            "latest_decision: a valid review transition requires PASS, CHANGES_REQUESTED, or BLOCK",
            validate_transition(previous, missing_decision),
        )
        wrong_route = valid_state(
            "IMPLEMENTING", 1, latest_decision="PASS", required_actions=[]
        )
        pass_pending = valid_state(
            "REVIEW_PENDING",
            0,
            latest_decision="PASS",
        )
        self.assertIn(
            "phase: review routing requires transition to FINAL_VERIFICATION, not IMPLEMENTING",
            validate_transition(pass_pending, wrong_route),
        )

    def test_valid_review_consumption_increments_round_exactly_once(self) -> None:
        previous = valid_state("REVIEW_PENDING", 1, latest_decision="PASS")
        for invalid_round in (1, 3):
            with self.subTest(review_round=invalid_round):
                current = valid_state(
                    "FINAL_VERIFICATION",
                    invalid_round,
                    latest_decision="PASS",
                )
                self.assertIn(
                    "review_round: valid review consumption must increment exactly once",
                    validate_transition(previous, current),
                )

    def test_valid_review_consumption_requires_explicit_blocker_history(self) -> None:
        previous = valid_state("REVIEW_PENDING", 1, latest_decision="PASS")
        current = valid_state(
            "FINAL_VERIFICATION", 2, latest_decision="PASS"
        )
        del previous["unresolved_finding_ids"]
        del current["blocker_fingerprints"]
        errors = validate_transition(previous, current)
        self.assertIn(
            "previous.unresolved_finding_ids: must be a list of strings", errors
        )
        self.assertIn(
            "current.blocker_fingerprints: must be a list of strings", errors
        )

    def test_non_review_events_do_not_increment_round(self) -> None:
        evidence_previous = valid_state(
            "LOCAL_VERIFICATION",
            1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["PROVIDE_EVIDENCE"],
        )
        self.assertEqual(
            validate_transition(
                evidence_previous,
                valid_state("REVIEW_PENDING", 1, required_actions=["PROVIDE_EVIDENCE"]),
            ),
            [],
        )
        reconnect_previous = valid_state("REVIEW_PENDING", 1)
        self.assertEqual(
            validate_transition(
                reconnect_previous,
                valid_state("REVIEW_PENDING", 1, browser_reconnect_count=1),
            ),
            [],
        )
        format_previous = valid_state("REVIEW_PENDING", 1)
        self.assertEqual(
            validate_transition(
                format_previous,
                valid_state("REVIEW_PENDING", 1, format_error_count=1),
            ),
            [],
        )
        self.assertIn(
            "review_round: non-review transitions must preserve the review round",
            validate_transition(
                valid_state("LOCAL_VERIFICATION", 1),
                valid_state("REVIEW_PENDING", 2),
            ),
        )

    def test_first_blocker_occurrence_is_allowed(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            0,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-1"],
            blocker_fingerprints=["cause-1"],
        )
        current = valid_state(
            "IMPLEMENTING",
            1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-1"],
            blocker_fingerprints=["cause-1"],
        )
        self.assertEqual(
            validate_bound_review_transition(previous, current),
            [],
        )

    def test_second_consecutive_blocker_finding_id_requires_stopping(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-1"],
            blocker_fingerprints=["cause-1"],
        )
        current = valid_state(
            "IMPLEMENTING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-1"],
            blocker_fingerprints=["cause-2"],
        )
        self.assertIn(
            "unresolved_findings: blocker persisted across two consecutive valid review rounds",
            validate_bound_review_transition(previous, current),
        )

    def test_second_consecutive_blocker_fingerprint_requires_stopping(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-1"],
            blocker_fingerprints=["same-cause"],
        )
        current = valid_state(
            "IMPLEMENTING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-2"],
            blocker_fingerprints=["same-cause"],
        )
        self.assertIn(
            "unresolved_findings: blocker persisted across two consecutive valid review rounds",
            validate_bound_review_transition(previous, current),
        )

    def test_nonconsecutive_blocker_occurrence_resets_continuity(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-2"],
            blocker_fingerprints=["cause-2"],
        )
        current = valid_state(
            "IMPLEMENTING",
            3,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
            unresolved_finding_ids=["F-1"],
            blocker_fingerprints=["cause-1"],
        )
        self.assertEqual(
            validate_bound_review_transition(previous, current),
            [],
        )

    def test_legacy_model_selected_finding_history_is_rejected(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            1,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
        )
        previous["unresolved_findings"] = [
            {
                "id": "F-OLD",
                "root_cause_fingerprint": "sha256:" + "f" * 64,
            }
        ]
        current = valid_state(
            "IMPLEMENTING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
        )
        self.assertIn(
            "previous.unresolved_findings: unknown field",
            validate_bound_review_transition(previous, current),
        )

    def test_prompt_contract_spells_out_closed_nested_shapes_and_enums(self) -> None:
        prompt_contract = (
            Path(__file__).resolve().parents[2]
            / "skills"
            / "gpt-pro-codex-loop"
            / "references"
            / "prompt-contract.md"
        ).read_text(encoding="utf-8")

        required_fragments = (
            "Each requirements item is exactly {id, statement}.",
            "Each acceptance_criteria item is exactly {id, criterion, required_evidence}.",
            "Each risk_items item is exactly {id, risk, required_mitigation}.",
            "evidence is one non-empty string, never an array or object.",
            "severity is exactly BLOCKER, HIGH, MEDIUM, or LOW.",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, prompt_contract)


if __name__ == "__main__":
    unittest.main()
