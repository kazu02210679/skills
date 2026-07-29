"""Unit tests for the GPT Pro Codex Loop packet validator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


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


class TransitionTests(unittest.TestCase):
    def test_transition_rejects_an_illegal_edge(self) -> None:
        self.assertIn(
            "phase: illegal transition from PREFLIGHT to IMPLEMENTING",
            validate_transition({"phase": "PREFLIGHT"}, {"phase": "IMPLEMENTING"}),
        )

    def test_transition_blocks_the_second_format_error(self) -> None:
        self.assertIn(
            "format_error_count: repeated malformed response blocks the loop",
            validate_transition(
                {"phase": "REQUIREMENTS_PENDING", "format_error_count": 1},
                {"phase": "REQUIREMENTS_PENDING", "format_error_count": 2},
            ),
        )

    def test_transition_detects_repeated_fingerprint_despite_new_finding_id(self) -> None:
        self.assertIn(
            "blocker_fingerprints: repeated blocker fingerprint requires stopping",
            validate_transition(
                {
                    "phase": "REVIEW_PENDING",
                    "unresolved_findings": [{"id": "F-1", "fingerprint": "same-cause"}],
                },
                {
                    "phase": "IMPLEMENTING",
                    "unresolved_findings": [{"id": "F-2", "fingerprint": "same-cause"}],
                },
            ),
        )


if __name__ == "__main__":
    unittest.main()
