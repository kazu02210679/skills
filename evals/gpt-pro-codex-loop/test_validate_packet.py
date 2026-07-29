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
    review_round_reset: bool = False,
    user_approval_received: bool = False,
) -> dict[str, object]:
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
        "review_round_reset": review_round_reset,
        "user_approval_received": user_approval_received,
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
    def test_only_approved_material_revision_resets_round_on_freeze(self) -> None:
        review_pending = valid_state("REVIEW_PENDING", 1)
        previous = valid_state(
            "REQUIREMENTS_PENDING",
            2,
            latest_decision="CHANGES_REQUESTED",
            required_actions=["REQUIREMENTS_REVISION"],
        )
        self.assertEqual(validate_transition(review_pending, previous), [])

        approved = valid_state(
            "REQUIREMENTS_FROZEN",
            0,
            latest_decision="CHANGES_REQUESTED",
            latest_requirements_decision="PLAN_READY",
            required_actions=["REQUIREMENTS_REVISION"],
            review_round_reset=True,
            user_approval_received=True,
        )
        self.assertEqual(validate_transition(previous, approved), [])

        unapproved = dict(approved, user_approval_received=False)
        self.assertIn(
            "review_round: reset requires an approved material revision",
            validate_transition(previous, unapproved),
        )

        arbitrary = dict(
            approved,
            review_round_reset=False,
            user_approval_received=False,
        )
        self.assertIn(
            "review_round: non-review transitions must preserve the review round",
            validate_transition(previous, arbitrary),
        )

    def test_requirements_decisions_route_and_resume_without_consuming_round(self) -> None:
        previous = valid_state("REQUIREMENTS_PENDING", 2)
        routes = (
            ("NEED_USER_INPUT", "USER_DECISION_REQUIRED"),
            ("BLOCK", "BLOCKED"),
        )
        for decision, target in routes:
            with self.subTest(decision=decision):
                stopped = valid_state(
                    target,
                    2,
                    latest_requirements_decision=decision,
                )
                self.assertEqual(validate_transition(previous, stopped), [])
                resumed = valid_state("REQUIREMENTS_PENDING", 2)
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
        unrelated_block = valid_state("BLOCKED", 2)
        self.assertIn(
            "phase: requirements resume requires a prior NEED_USER_INPUT or BLOCK decision",
            validate_transition(
                unrelated_block,
                valid_state("REQUIREMENTS_PENDING", 2),
            ),
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
            "review_round_reset",
            "user_approval_received",
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
            ("PASS", [], "FINAL_VERIFICATION"),
            ("CHANGES_REQUESTED", ["CODE_CHANGE"], "IMPLEMENTING"),
            ("BLOCK", [], "USER_DECISION_REQUIRED"),
        )
        for decision, actions, phase in cases:
            with self.subTest(decision=decision):
                current = valid_state(
                    phase,
                    1,
                    latest_decision=decision,
                    required_actions=actions,
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
