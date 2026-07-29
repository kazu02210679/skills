"""Unit tests for the GPT Pro Codex Loop packet validator."""

from __future__ import annotations

import sys
import json
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
) -> dict[str, object]:
    if active_requirements_revision is _UNSET_STATE_VALUE:
        active_requirements_revision = None if phase == "PREFLIGHT" else 1
    if active_requirements_digest is _UNSET_STATE_VALUE:
        active_requirements_digest = (
            None if phase == "PREFLIGHT" else "sha256:" + "a" * 64
        )
    return {
        "phase": phase,
        "review_round": review_round,
        "latest_decision": latest_decision,
        "latest_requirements_decision": latest_requirements_decision,
        "required_actions": required_actions or [],
        "unresolved_finding_ids": unresolved_finding_ids or [],
        "blocker_fingerprints": blocker_fingerprints or [],
        "format_error_count": format_error_count,
        "browser_reconnect_count": browser_reconnect_count,
        "conversation_binding_state": conversation_binding_state,
        "bound_conversation_url": bound_conversation_url,
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
    }


class PacketTransportTests(unittest.TestCase):
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


class RequirementsPacketTests(unittest.TestCase):
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
                    "root_cause_fingerprint": "sha256:" + "f" * 64,
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
                    "root_cause_fingerprint": "sha256:" + "f" * 64,
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
                    "root_cause_fingerprint": "sha256:" + "f" * 64,
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


class TransitionTests(unittest.TestCase):
    def test_approved_material_revision_promotes_and_consumes_provenance(self) -> None:
        review_pending = valid_state("REVIEW_PENDING", 1)
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
        self.assertEqual(validate_transition(review_pending, pending), [])

        frozen = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            latest_decision="CHANGES_REQUESTED",
            latest_requirements_decision="PLAN_READY",
            required_actions=["REQUIREMENTS_REVISION"],
            active_requirements_revision=2,
            active_requirements_digest="sha256:" + "b" * 64,
            approval_sequence=1,
        )
        self.assertEqual(validate_transition(pending, frozen), [])

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
        self.assertEqual(validate_transition(pending, frozen), [])

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
            "current.pending_requirements: revision provenance is allowed only while requirements are pending",
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
                self.assertEqual(validate_transition(previous, stopped), [])
                resumed = valid_state(
                    "REQUIREMENTS_PENDING",
                    2,
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
                valid_state("REVIEW_PENDING", 1),
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
                valid_state("REVIEW_PENDING", 1),
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
                self.assertEqual(validate_transition(previous, stopped), [])

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
        )
        self.assertEqual(validate_transition(pending, first_stop), [])
        self.assertEqual(validate_transition(first_stop, first_resume), [])
        self.assertEqual(validate_transition(first_resume, second_stop), [])

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
                self.assertIn(
                    f"{field}: must match the bound conversation state",
                    validate_transition(
                        valid_state("IMPLEMENTING", 0),
                        mismatched,
                    ),
                )

        missing_identity = valid_state("LOCAL_VERIFICATION", 0)
        del missing_identity["bound_conversation_url"]
        self.assertIn(
            "current.bound_conversation_url: missing required field",
            validate_transition(
                valid_state("IMPLEMENTING", 0),
                missing_identity,
            ),
        )

    def test_transition_requires_complete_structured_state_packets(self) -> None:
        shorthand_errors = validate_transition(
            "PREFLIGHT",
            "REQUIREMENTS_PENDING",
        )
        self.assertIn("previous: must be a state object", shorthand_errors)
        self.assertIn("current: must be a state object", shorthand_errors)

        required_fields = (
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
        previous = valid_state("REVIEW_PENDING", 0)
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
                current = valid_state(
                    phase,
                    1,
                    latest_decision=decision,
                    required_actions=actions,
                    **stop_provenance,
                )
                self.assertEqual(validate_transition(previous, current), [])
        missing_decision = valid_state("FINAL_VERIFICATION", 1)
        self.assertIn(
            "latest_decision: a valid review transition requires PASS, CHANGES_REQUESTED, or BLOCK",
            validate_transition(previous, missing_decision),
        )
        wrong_route = valid_state(
            "IMPLEMENTING", 1, latest_decision="PASS", required_actions=[]
        )
        self.assertIn(
            "phase: review routing requires transition to FINAL_VERIFICATION, not IMPLEMENTING",
            validate_transition(previous, wrong_route),
        )

    def test_valid_review_consumption_increments_round_exactly_once(self) -> None:
        previous = valid_state("REVIEW_PENDING", 1)
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
        previous = valid_state("REVIEW_PENDING", 1)
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
        self.assertEqual(validate_transition(previous, current), [])

    def test_second_consecutive_blocker_finding_id_requires_stopping(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            1,
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
            validate_transition(previous, current),
        )

    def test_second_consecutive_blocker_fingerprint_requires_stopping(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            1,
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
            validate_transition(previous, current),
        )

    def test_nonconsecutive_blocker_occurrence_resets_continuity(self) -> None:
        previous = valid_state(
            "REVIEW_PENDING",
            2,
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
        self.assertEqual(validate_transition(previous, current), [])

    def test_explicit_empty_authoritative_history_clears_stale_legacy_history(self) -> None:
        stale_legacy = [
            {"id": "F-OLD", "root_cause_fingerprint": "stale-cause"}
        ]
        previous = valid_state("REVIEW_PENDING", 1)
        previous["unresolved_findings"] = stale_legacy
        current = valid_state(
            "IMPLEMENTING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
        )
        current["unresolved_findings"] = stale_legacy
        self.assertEqual(validate_transition(previous, current), [])

    def test_absent_authoritative_history_uses_legacy_history(self) -> None:
        legacy = [{"id": "F-1", "root_cause_fingerprint": "same-cause"}]
        previous = valid_state("REVIEW_PENDING", 1)
        current = valid_state(
            "IMPLEMENTING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["CODE_CHANGE"],
        )
        for state in (previous, current):
            del state["unresolved_finding_ids"]
            del state["blocker_fingerprints"]
            state["unresolved_findings"] = legacy
        self.assertIn(
            "unresolved_findings: blocker persisted across two consecutive valid review rounds",
            validate_transition(previous, current),
        )


if __name__ == "__main__":
    unittest.main()
