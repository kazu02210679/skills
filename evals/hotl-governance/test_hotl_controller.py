from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "hotl-governance" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hotl_contract as contract
import hotl_controller as controller
import hotl_store as store


EXECUTION_ID = "EXEC-123456789ABC"
SUCCESSOR_ONE = "EXEC-ABCDEF123456"
SUCCESSOR_TWO = "EXEC-FEDCBA654321"
DIGEST_ONE = "sha256:" + "1" * 64
DIGEST_TWO = "sha256:" + "2" * 64
DIGEST_THREE = "sha256:" + "3" * 64


def fixture_projection(state: str, **changes: object) -> controller.Projection:
    return controller.empty_projection(
        execution_id=EXECUTION_ID,
        state=controller.State(state),
        requirements_digest=DIGEST_ONE,
        authority_snapshot_digest=DIGEST_THREE,
        **changes,
    )


def fixture_event(
    event_type: str,
    payload: dict[str, object],
    *,
    sequence: int = 1,
    previous_hash: str | None = None,
    event_id: str = "EVT-123456789ABC",
    issuer: dict[str, object] | None = None,
    subject_ids: list[str] | None = None,
    artifact_refs: list[dict[str, str]] | None = None,
    result: str = "pass",
    input_digest: str = DIGEST_ONE,
    timestamp: str = "2026-08-09T00:00:00Z",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "execution_id": EXECUTION_ID,
        "sequence": sequence,
        "type": event_type,
        "payload": payload,
        "issuer": issuer
        or {"kind": "controller", "id": "hotl-governance", "version": "1"},
        "subject_ids": subject_ids or [],
        "artifact_refs": artifact_refs or [],
        "result": result,
        "input_digest": input_digest,
        "output_digest": DIGEST_TWO,
        "previous_event_hash": previous_hash,
        "timestamp": timestamp,
    }


def fixture_node(node_id: str, node_type: str) -> dict[str, object]:
    return fixture_event(
        "node_declared",
        {"node_id": node_id, "node_type": node_type},
        subject_ids=[node_id],
    )


def fixture_edge(source_id: str, edge: str, target_id: str) -> dict[str, object]:
    return fixture_event(
        "edge_declared",
        {"source_id": source_id, "edge": edge, "target_id": target_id},
        subject_ids=[source_id, target_id],
    )


def fixture_transition(
    projection: controller.Projection,
    *,
    gate: str,
    source: str,
    target: str,
    cycle_id: int | None = None,
    digest: str | None = None,
    sequence: int = 1,
    previous_hash: str | None = None,
) -> dict[str, object]:
    evidence_digest = digest or controller.projection_evidence_set_digest(projection)
    return fixture_event(
        "transition_committed",
        {
            "gate": gate,
            "from_state": source,
            "to_state": target,
            "evidence_set_digest": evidence_digest,
            "cycle_id": projection.cycle_id if cycle_id is None else cycle_id,
        },
        sequence=sequence,
        previous_hash=previous_hash,
        input_digest=evidence_digest,
    )


def fixture_review(
    projection: controller.Projection,
    review_id: str,
    status: str,
    *,
    receipt_id: str | None = None,
    root_cause_ids: list[str] | None = None,
    digest: str | None = None,
    cycle_id: int | None = None,
) -> dict[str, object]:
    evidence_digest = digest or controller.projection_evidence_set_digest(projection)
    return fixture_event(
        "review_recorded",
        {
            "review_id": review_id,
            "receipt_id": receipt_id or "RCP-" + review_id,
            "status": status,
            "evidence_set_digest": evidence_digest,
            "cycle_id": projection.cycle_id if cycle_id is None else cycle_id,
            "root_cause_ids": root_cause_ids
            if root_cause_ids is not None
            else ([] if status == "accepted" else ["ROOT-" + review_id]),
        },
        issuer={"kind": "skill", "id": "gpt-pro-codex-loop", "version": "1"},
        subject_ids=[review_id],
        result="pass" if status == "accepted" else "fail",
        input_digest=evidence_digest,
    )


def fixture_receipt(
    projection: controller.Projection,
    receipt_type: str,
    receipt_id: str,
    *,
    issuer_skill: str | None = None,
    receipt_digest: str = DIGEST_TWO,
    stale: bool = False,
) -> dict[str, object]:
    default_issuers = {
        "requirements": "gpt-pro-codex-loop",
        "approval": "gpt-pro-codex-loop",
        "implementation": "codex",
        "verification": "hotl-local-verifier",
        "semantic_review": "gpt-pro-codex-loop",
        "final": "gpt-pro-codex-loop",
        "material_change": "gpt-pro-codex-loop",
        "stop": "gpt-pro-codex-loop",
        "lineage": "hotl-governance-lineage",
    }
    current_bound = receipt_type not in {"requirements", "approval", "lineage"}
    return fixture_event(
        "receipt_imported",
        {
            "receipt_id": receipt_id,
            "receipt_type": receipt_type,
            "receipt_digest": receipt_digest,
            "issuer_skill": issuer_skill or default_issuers[receipt_type],
            "authority_snapshot_digest": None
            if receipt_type == "lineage"
            else projection.authority_snapshot_digest,
            "requirements_digest": None
            if receipt_type == "lineage"
            else projection.requirements_digest,
            "snapshot_digest": DIGEST_ONE
            if stale and current_bound
            else (projection.active_snapshot_digest if current_bound else None),
            "evidence_set_digest": controller.projection_evidence_set_digest(projection)
            if current_bound
            else None,
            "cycle_id": projection.cycle_id if current_bound else None,
        },
        input_digest=receipt_digest,
    )


def admit_review(
    projection: controller.Projection,
    review_id: str,
    status: str,
    *,
    root_cause_ids: list[str] | None = None,
    stale: bool = False,
) -> controller.Projection:
    receipt_id = "RCP-" + review_id
    receipt = fixture_receipt(
        projection,
        "semantic_review",
        receipt_id,
        receipt_digest="sha256:" + hashlib.sha256(receipt_id.encode()).hexdigest(),
        stale=stale,
    )
    with_receipt = controller.project_event(projection, receipt)
    return controller.project_event(
        with_receipt,
        fixture_review(
            with_receipt,
            review_id,
            status,
            receipt_id=receipt_id,
            root_cause_ids=root_cause_ids,
        ),
    )


def fixture_finding(review_id: str, root_cause_id: str, *, prose_digest: str) -> dict[str, object]:
    return fixture_event(
        "finding_recorded",
        {
            "finding_id": "FIND-" + review_id.removeprefix("REV-"),
            "root_cause_id": root_cause_id,
            "review_id": review_id,
            "status": "open",
        },
        issuer={"kind": "skill", "id": "gpt-pro-codex-loop", "version": "1"},
        subject_ids=[review_id],
        result="fail",
        input_digest=prose_digest,
    )


def chained(event: dict[str, object], prior: dict[str, object], sequence: int, event_id: str) -> dict[str, object]:
    return event | {
        "event_id": event_id,
        "sequence": sequence,
        "previous_event_hash": contract.canonical_digest(prior),
    }


def chain_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    previous: dict[str, object] | None = None
    for sequence, event in enumerate(events, 1):
        current = event | {
            "event_id": f"EVT-{sequence:012X}",
            "sequence": sequence,
            "previous_event_hash": contract.canonical_digest(previous)
            if previous is not None
            else None,
        }
        result.append(current)
        previous = current
    return result


def g1_projection() -> controller.Projection:
    projection = fixture_projection("REQUIREMENTS")
    projection = controller.project_event(projection, fixture_node("REQ-1", "requirement"))
    projection = controller.project_event(
        projection,
        fixture_receipt(
            projection, "requirements", "RCP-REQ-1", receipt_digest=DIGEST_ONE
        ),
    )
    return controller.project_event(
        projection,
        fixture_receipt(
            projection, "approval", "RCP-APPROVAL-1", receipt_digest=DIGEST_TWO
        ),
    )


def projection_bytes(projection: controller.Projection) -> bytes:
    value = asdict(projection)
    value["state"] = projection.state.value
    value["edges"] = [list(edge) for edge in projection.edges]
    value["valid_review_rounds"] = [
        {
            "review_id": round_record.review_id,
            "status": round_record.status,
            "root_cause_ids": list(round_record.root_cause_ids),
            "cycle_id": round_record.cycle_id,
        }
        for round_record in projection.valid_review_rounds
    ]
    value["gate_evidence"] = {
        gate: list(records) for gate, records in projection.gate_evidence.items()
    }
    return contract.canonical_json_bytes(value)


class ProjectionTests(unittest.TestCase):
    def test_offline_approval_is_gate_eligible_only_in_frozen_manual_mode(self) -> None:
        for approval_mode, expected in (("agentic", False), ("offline_manual", True)):
            with self.subTest(approval_mode=approval_mode):
                projection = fixture_projection(
                    "REQUIREMENTS", approval_mode=approval_mode
                )
                projection = controller.project_event(
                    projection, fixture_node("REQ-1", "requirement")
                )
                projection = controller.project_event(
                    projection,
                    fixture_receipt(
                        projection,
                        "requirements",
                        "RCP-REQ-1",
                        receipt_digest=DIGEST_ONE,
                    ),
                )
                approval = fixture_receipt(
                    projection,
                    "approval",
                    "RCP-OFFLINE-1",
                    issuer_skill="trusted-local-operator",
                    receipt_digest=DIGEST_TWO,
                )
                projection = controller.project_event(projection, approval)
                self.assertEqual(expected, controller.evaluate_gate(projection, "G1")[0])

    def test_host_approval_is_a_distinct_exact_gate_authority(self) -> None:
        projection = fixture_projection("REQUIREMENTS")
        projection = controller.project_event(
            projection, fixture_node("REQ-1", "requirement")
        )
        projection = controller.project_event(
            projection,
            fixture_receipt(
                projection, "requirements", "RCP-REQ-1", receipt_digest=DIGEST_ONE
            ),
        )
        projection = controller.project_event(
            projection,
            fixture_receipt(
                projection,
                "approval",
                "RCP-HOST-1",
                issuer_skill="hotl-host-approval",
                receipt_digest=DIGEST_TWO,
            ),
        )
        self.assertTrue(controller.evaluate_gate(projection, "G1")[0])

    def test_evidence_event_never_advances_state(self) -> None:
        projection = fixture_projection("REQUIREMENTS")
        event = fixture_receipt(
            projection, "requirements", "RCP-REQ-1", receipt_digest=DIGEST_ONE
        )

        result = controller.project_event(projection, event)

        self.assertEqual("REQUIREMENTS", result.state.value)

    def test_only_valid_transition_committed_advances_state(self) -> None:
        projection = g1_projection()

        result = controller.project_event(
            projection,
            fixture_transition(
                projection, gate="G1", source="REQUIREMENTS", target="IMPLEMENT"
            ),
        )

        self.assertEqual("IMPLEMENT", result.state.value)

    def test_invalid_transition_bindings_are_rejected(self) -> None:
        projection = g1_projection()
        cases = (
            {"source": "INIT", "target": "IMPLEMENT"},
            {"source": "REQUIREMENTS", "target": "COMPLETE"},
            {"source": "REQUIREMENTS", "target": "IMPLEMENT", "cycle_id": 9},
            {"source": "REQUIREMENTS", "target": "IMPLEMENT", "digest": DIGEST_THREE},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(controller.ControllerError):
                controller.project_event(
                    projection,
                    fixture_transition(projection, gate="G1", **changes),
                )

    def test_same_policy_and_events_yield_byte_identical_projection(self) -> None:
        policy = {
            "execution_id": EXECUTION_ID,
            "initial_state": "REQUIREMENTS",
            "requirements_digest": DIGEST_ONE,
            "authority_snapshot_digest": DIGEST_THREE,
        }
        events = chain_events([fixture_node("REQ-1", "requirement")])

        left = controller.replay(policy, events)
        right = controller.replay(dict(reversed(tuple(policy.items()))), events)

        self.assertEqual(projection_bytes(left), projection_bytes(right))

    def test_free_text_metadata_does_not_change_transition(self) -> None:
        policy = {
            "execution_id": EXECUTION_ID,
            "initial_state": "INIT",
            "requirements_digest": DIGEST_ONE,
            "authority_snapshot_digest": DIGEST_THREE,
        }
        first = fixture_node("REQ-1", "requirement")
        alternate = first | {"timestamp": "a completely different display label"}
        first_projection = controller.replay(policy, [first])
        left_transition = chained(
            fixture_transition(
                first_projection, gate="INIT", source="INIT", target="REQUIREMENTS"
            ),
            first,
            2,
            "EVT-ABCDEF123456",
        )
        right_transition = left_transition | {
            "previous_event_hash": contract.canonical_digest(alternate),
            "timestamp": "unrelated prose",
        }

        self.assertEqual(
            controller.replay(policy, [first, left_transition]).state,
            controller.replay(policy, [alternate, right_transition]).state,
        )

    def test_stale_review_does_not_consume_a_round(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=2
        )
        projection = controller.project_event(projection, fixture_node("REV-1", "review"))

        result = admit_review(projection, "REV-1", "rejected", stale=True)

        self.assertEqual((), result.valid_review_rounds)
        self.assertFalse(result.review_records["REV-1"].valid)

    def test_malformed_review_is_rejected_without_a_round(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        projection = controller.project_event(projection, fixture_node("REV-1", "review"))
        receipt = fixture_receipt(projection, "semantic_review", "RCP-REV-1")
        projection = controller.project_event(projection, receipt)
        malformed = fixture_review(
            projection, "REV-1", "rejected", receipt_id="RCP-REV-1"
        )
        malformed["payload"] = dict(malformed["payload"]) | {"unknown": True}

        with self.assertRaises(controller.ControllerError):
            controller.project_event(projection, malformed)

        self.assertEqual((), projection.valid_review_rounds)

    def test_second_consecutive_stable_root_cause_requires_escalation(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for review_id in ("REV-1", "REV-2"):
            projection = controller.project_event(projection, fixture_node(review_id, "review"))
        first_review = admit_review(
            projection, "REV-1", "rejected", root_cause_ids=["ROOT-stable"]
        )
        second_review = admit_review(
            first_review, "REV-2", "rejected", root_cause_ids=["ROOT-stable"]
        )

        self.assertEqual(("IMPLEMENT",), controller.allowed_transitions(first_review))
        self.assertEqual(("ESCALATED",), controller.allowed_transitions(second_review))

    def test_third_valid_failed_review_escalates_even_with_distinct_roots(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for review_id in ("REV-1", "REV-2", "REV-3"):
            projection = controller.project_event(projection, fixture_node(review_id, "review"))
        for index in range(1, 4):
            projection = admit_review(
                projection,
                f"REV-{index}",
                "rejected",
                root_cause_ids=[f"ROOT-{index}"],
            )

        self.assertEqual(("ESCALATED",), controller.allowed_transitions(projection))

    def test_accepted_review_breaks_consecutive_root_cause_failures(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for review_id in ("REV-1", "REV-2", "REV-3"):
            projection = controller.project_event(projection, fixture_node(review_id, "review"))
        projection = admit_review(
            projection, "REV-1", "rejected", root_cause_ids=["ROOT-stable"]
        )
        projection = admit_review(projection, "REV-2", "accepted")
        projection = admit_review(
            projection, "REV-3", "rejected", root_cause_ids=["ROOT-stable"]
        )

        self.assertEqual(("IMPLEMENT",), controller.allowed_transitions(projection))

    def test_late_finding_cannot_change_committed_review_roots(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for review_id in ("REV-1", "REV-2"):
            projection = controller.project_event(projection, fixture_node(review_id, "review"))
        projection = admit_review(
            projection, "REV-1", "rejected", root_cause_ids=["ROOT-original"]
        )
        projection = controller.project_event(
            projection,
            fixture_finding("REV-1", "ROOT-late", prose_digest=DIGEST_ONE),
        )
        projection = admit_review(
            projection, "REV-2", "rejected", root_cause_ids=["ROOT-late"]
        )
        self.assertEqual(("ROOT-original",), projection.valid_review_rounds[0].root_cause_ids)
        corrective = fixture_transition(
            projection,
            gate="CORRECTIVE",
            source="SEMANTIC_REVIEW",
            target="IMPLEMENT",
        )
        self.assertEqual("IMPLEMENT", controller.project_event(projection, corrective).state.value)

    def test_post_terminal_evidence_is_rejected_by_replay(self) -> None:
        projection = fixture_projection(
            "INIT", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        projection = controller.project_event(projection, fixture_node("REQ-1", "requirement"))
        projection = controller.project_event(
            projection, fixture_receipt(projection, "stop", "RCP-STOP-1")
        )
        terminal = fixture_transition(
            projection, gate="STOP", source="INIT", target="STOPPED"
        )
        stopped = controller.project_event(projection, terminal)
        with self.assertRaises(controller.ControllerError) as raised:
            controller.project_event(stopped, fixture_node("REQ-2", "requirement"))
        self.assertEqual("TERMINAL_STATE", raised.exception.code)

    def test_bound_stop_authority_can_terminate_before_snapshot_activation(self) -> None:
        projection = fixture_projection("INIT")
        projection = controller.project_event(
            projection, fixture_receipt(projection, "stop", "RCP-STOP-INIT")
        )
        stopped = controller.project_event(
            projection,
            fixture_transition(
                projection, gate="STOP", source="INIT", target="STOPPED"
            ),
        )
        self.assertEqual("STOPPED", stopped.state.value)

    def test_terminal_states_have_no_allowed_transitions(self) -> None:
        for state in ("COMPLETE", "ESCALATED", "RECOVERY_REQUIRED", "STOPPED"):
            with self.subTest(state=state):
                self.assertEqual((), controller.allowed_transitions(fixture_projection(state)))

    def test_init_is_allowed_only_after_requirements_or_lineage_publication(self) -> None:
        empty = fixture_projection("INIT")
        self.assertEqual((), controller.allowed_transitions(empty))

        requirements = controller.project_event(
            empty, fixture_node("REQ-1", "requirement")
        )
        self.assertEqual(("REQUIREMENTS",), controller.allowed_transitions(requirements))

        lineage = controller.project_event(
            empty, fixture_receipt(empty, "lineage", "RCP-LINEAGE-1")
        )
        self.assertEqual(("REQUIREMENTS",), controller.allowed_transitions(lineage))

    def test_duplicate_receipt_id_or_digest_is_rejected(self) -> None:
        projection = fixture_projection("REQUIREMENTS")
        first = fixture_receipt(
            projection, "requirements", "RCP-REQ-1", receipt_digest=DIGEST_ONE
        )
        projection = controller.project_event(projection, first)
        for replayed in (
            fixture_receipt(
                projection, "approval", "RCP-REQ-1", receipt_digest=DIGEST_TWO
            ),
            fixture_receipt(
                projection, "approval", "RCP-APPROVAL-1", receipt_digest=DIGEST_ONE
            ),
        ):
            with self.subTest(payload=replayed["payload"]), self.assertRaises(
                controller.ControllerError
            ):
                controller.project_event(projection, replayed)

    def test_snapshot_advance_invalidates_prior_gate_receipt_authority(self) -> None:
        projection = fixture_projection(
            "LOCAL_VERIFY", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        projection = controller.project_event(
            projection,
            fixture_receipt(projection, "verification", "RCP-VERIFY-1"),
        )
        self.assertNotIn(
            "G3:missing_verification_receipt",
            controller.evaluate_gate(projection, "G3")[1],
        )

        projection = controller.project_event(
            projection,
            fixture_event(
                "snapshot_activated",
                {"snapshot_digest": DIGEST_THREE, "cycle_id": 2},
            ),
        )
        self.assertIn(
            "G3:missing_verification_receipt",
            controller.evaluate_gate(projection, "G3")[1],
        )

    def test_snapshot_advance_prevents_reuse_of_prior_review_receipt(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        projection = controller.project_event(
            projection, fixture_node("REV-1", "review")
        )
        projection = controller.project_event(
            projection,
            fixture_receipt(projection, "semantic_review", "RCP-REV-1"),
        )
        projection = controller.project_event(
            projection,
            fixture_event(
                "snapshot_activated",
                {"snapshot_digest": DIGEST_THREE, "cycle_id": 2},
            ),
        )
        projection = controller.project_event(
            projection,
            fixture_review(
                projection, "REV-1", "accepted", receipt_id="RCP-REV-1"
            ),
        )
        self.assertFalse(projection.review_records["REV-1"].valid)
        self.assertEqual((), projection.valid_review_rounds)

    def test_semantic_receipt_cannot_authorize_multiple_review_rounds(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for review_id in ("REV-1", "REV-2"):
            projection = controller.project_event(
                projection, fixture_node(review_id, "review")
            )
        projection = controller.project_event(
            projection,
            fixture_receipt(projection, "semantic_review", "RCP-REVIEW-1"),
        )
        projection = controller.project_event(
            projection,
            fixture_review(
                projection,
                "REV-1",
                "rejected",
                receipt_id="RCP-REVIEW-1",
                root_cause_ids=["ROOT-1"],
            ),
        )

        with self.assertRaises(controller.ControllerError) as raised:
            controller.project_event(
                projection,
                fixture_review(
                    projection,
                    "REV-2",
                    "accepted",
                    receipt_id="RCP-REVIEW-1",
                ),
            )
        self.assertEqual("REPLAYED_RECEIPT", raised.exception.code)


class CompletionTests(unittest.TestCase):
    def _complete_projection(self) -> controller.Projection:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for node_id, node_type in (
            ("REQ-1", "requirement"),
            ("CODE-1", "code"),
            ("TEST-1", "test"),
            ("CMD-1", "command"),
            ("EVID-1", "evidence"),
            ("REV-1", "review"),
            ("CHG-1", "change"),
        ):
            projection = controller.project_event(projection, fixture_node(node_id, node_type))
        artifact_digest = "sha256:" + hashlib.sha256(b"proof\n").hexdigest()
        projection = controller.project_event(
            projection,
            fixture_event(
                "evidence_recorded",
                {
                    "evidence_id": "EVID-1",
                    "artifact_digest": artifact_digest,
                    "test_id": "TEST-1",
                    "snapshot_digest": DIGEST_TWO,
                    "cycle_id": 1,
                },
                issuer={"kind": "tool", "id": "pytest", "version": "8"},
                subject_ids=["EVID-1", "TEST-1"],
                artifact_refs=[{"path": "evidence/proof.txt", "sha256": artifact_digest}],
            ),
        )
        for source, edge, target in (
            ("CODE-1", "implements", "REQ-1"),
            ("TEST-1", "verifies", "REQ-1"),
            ("CMD-1", "executes", "TEST-1"),
            ("CMD-1", "produces", "EVID-1"),
            ("EVID-1", "proves", "TEST-1"),
            ("CODE-1", "included_in", "CHG-1"),
            ("TEST-1", "included_in", "CHG-1"),
        ):
            projection = controller.project_event(projection, fixture_edge(source, edge, target))
        projection = admit_review(projection, "REV-1", "accepted")
        for source, edge, target in (
            ("EVID-1", "supports", "REV-1"),
            ("REV-1", "reviews", "REQ-1"),
        ):
            projection = controller.project_event(projection, fixture_edge(source, edge, target))
        projection = controller.project_event(
            projection,
            fixture_receipt(
                projection,
                "verification",
                "RCP-VERIFY-1",
                receipt_digest="sha256:" + hashlib.sha256(b"verify").hexdigest(),
            ),
        )
        projection = controller.project_event(
            projection,
            fixture_receipt(
                projection, "final", "RCP-FINAL-1", receipt_digest=DIGEST_THREE
            ),
        )
        return projection

    def test_incomplete_typed_provenance_cannot_satisfy_g4(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        projection = controller.project_event(
            projection, fixture_node("REQ-1", "requirement")
        )

        passed, errors = controller.evaluate_gate(projection, "G4")

        self.assertFalse(passed)
        self.assertIn("REQ-1:missing_implementation", errors)

    def test_complete_current_typed_provenance_satisfies_g4(self) -> None:
        projection = self._complete_projection()

        self.assertEqual((), controller.completion_errors(projection))
        self.assertEqual((True, ()), controller.evaluate_gate(projection, "G4"))

    def test_prior_cycle_evidence_is_historical_and_cannot_satisfy_g4(self) -> None:
        projection = self._complete_projection()
        activated = controller.project_event(
            projection,
            fixture_event(
                "snapshot_activated",
                {"snapshot_digest": DIGEST_THREE, "cycle_id": 2},
            ),
        )

        self.assertEqual("historically_valid", activated.evidence_records["EVID-1"].status)
        self.assertFalse(controller.evaluate_gate(activated, "G4")[0])

    def test_evidence_set_digest_sorts_records_and_ignores_free_text(self) -> None:
        left = {
            "EVID-2": controller.EvidenceRecord(
                "EVID-2", DIGEST_TWO, "TEST-2", DIGEST_THREE, 1, "valid_current"
            ),
            "EVID-1": controller.EvidenceRecord(
                "EVID-1", DIGEST_ONE, "TEST-1", DIGEST_THREE, 1, "valid_current"
            ),
        }
        right = dict(reversed(tuple(left.items())))

        self.assertEqual(
            controller.evidence_set_digest(DIGEST_ONE, DIGEST_THREE, left),
            controller.evidence_set_digest(DIGEST_ONE, DIGEST_THREE, right),
        )

    def test_g2_g3_and_g4_require_exact_bound_receipt_types(self) -> None:
        implement = fixture_projection(
            "IMPLEMENT", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for node_id, node_type in (("REQ-1", "requirement"), ("CODE-1", "code")):
            implement = controller.project_event(implement, fixture_node(node_id, node_type))
        implement = controller.project_event(
            implement, fixture_edge("CODE-1", "implements", "REQ-1")
        )
        self.assertFalse(controller.evaluate_gate(implement, "G2")[0])
        wrong_g2 = controller.project_event(
            implement,
            fixture_receipt(implement, "requirements", "RCP-WRONG-G2"),
        )
        self.assertFalse(controller.evaluate_gate(wrong_g2, "G2")[0])
        correct_g2 = controller.project_event(
            implement,
            fixture_receipt(implement, "implementation", "RCP-G2"),
        )
        self.assertTrue(controller.evaluate_gate(correct_g2, "G2")[0])

        complete = self._complete_projection()
        local_without_verification = controller.empty_projection(
            execution_id=complete.execution_id,
            state=controller.State.LOCAL_VERIFY,
            active_snapshot_digest=complete.active_snapshot_digest,
            nodes=complete.nodes,
            edges=complete.edges,
            evidence_records=complete.evidence_records,
            review_records=complete.review_records,
            receipt_records={
                key: value
                for key, value in complete.receipt_records.items()
                if value.receipt_type != "verification"
            },
            gate_evidence=complete.gate_evidence,
            finding_state=complete.finding_state,
            valid_review_rounds=complete.valid_review_rounds,
            cycle_id=complete.cycle_id,
            requirements_digest=complete.requirements_digest,
            authority_snapshot_digest=complete.authority_snapshot_digest,
        )
        self.assertFalse(controller.evaluate_gate(local_without_verification, "G3")[0])
        local_with_verification = controller.project_event(
            local_without_verification,
            fixture_receipt(
                local_without_verification,
                "verification",
                "RCP-VERIFY-2",
                receipt_digest="sha256:" + hashlib.sha256(b"verify-2").hexdigest(),
            ),
        )
        self.assertTrue(controller.evaluate_gate(local_with_verification, "G3")[0])
        without_final = controller.empty_projection(
            execution_id=complete.execution_id,
            state=complete.state,
            active_snapshot_digest=complete.active_snapshot_digest,
            nodes=complete.nodes,
            edges=complete.edges,
            evidence_records=complete.evidence_records,
            review_records=complete.review_records,
            receipt_records={
                key: value
                for key, value in complete.receipt_records.items()
                if value.receipt_type != "final"
            },
            gate_evidence=complete.gate_evidence,
            finding_state=complete.finding_state,
            valid_review_rounds=complete.valid_review_rounds,
            cycle_id=complete.cycle_id,
            requirements_digest=complete.requirements_digest,
            authority_snapshot_digest=complete.authority_snapshot_digest,
        )
        self.assertFalse(controller.evaluate_gate(without_final, "G4")[0])
        self.assertTrue(controller.evaluate_gate(complete, "G4")[0])


class RepositoryControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _initialize(
        self, state: str, *, execution_id: str = EXECUTION_ID
    ) -> tuple[store.RunPaths, dict[str, object], dict[str, object]]:
        policy = {
            "execution_id": execution_id,
            "initial_state": state,
            "requirements_digest": DIGEST_ONE,
            "authority_snapshot_digest": DIGEST_THREE,
            "active_snapshot_digest": DIGEST_TWO,
            "cycle_id": 1,
        }
        first = fixture_node("REQ-1", "requirement") | {"execution_id": execution_id}
        paths = store.resolve_run(self.repository, execution_id)
        state_value = {
            "schema_version": 1,
            "execution_id": execution_id,
            "state": state,
            "event_count": 1,
            "head_event_hash": contract.canonical_digest(first),
            "policy": policy,
        }
        store.publish_initial_run(paths, state_value, first)
        return paths, first, policy

    def _next_event(
        self,
        first: dict[str, object],
        event: dict[str, object],
        *,
        sequence: int = 2,
        event_id: str = "EVT-ABCDEF123456",
    ) -> dict[str, object]:
        return chained(event, first, sequence, event_id)

    def _admit(
        self,
        paths: store.RunPaths,
        policy: dict[str, object],
        events: list[dict[str, object]],
        event: dict[str, object],
    ) -> dict[str, object]:
        admitted = chained(
            event,
            events[-1],
            len(events) + 1,
            f"EVT-{len(events) + 1:012X}",
        )
        projected = controller.replay(policy, [*events, admitted])
        state = {
            "schema_version": 1,
            "execution_id": paths.root.name,
            "state": projected.state.value,
            "event_count": len(events) + 1,
            "head_event_hash": contract.canonical_digest(admitted),
            "policy": policy,
        }
        store.append_events(paths, [admitted], state, {})
        events.append(admitted)
        return admitted

    def _lineage(self, paths: store.RunPaths) -> dict[str, object]:
        binding = {
            "predecessor_execution_id": paths.root.name,
            "supersedes": [{"new_id": "REQ-2", "old_id": "REQ-1"}],
        }
        digest = store.store_evidence(paths, contract.canonical_json_bytes(binding))
        return binding | {"lineage_receipt_digest": digest}

    def _terminal_predecessor(self) -> tuple[store.RunPaths, dict[str, object]]:
        paths, first, policy = self._initialize("REQUIREMENTS")
        events = [first]
        projection = controller.replay(policy, events)
        self._admit(
            paths,
            policy,
            events,
            fixture_receipt(
                projection,
                "material_change",
                "RCP-MATERIAL-1",
                receipt_digest="sha256:" + hashlib.sha256(b"material").hexdigest(),
            ),
        )
        result = controller.commit_transition(self.repository, EXECUTION_ID, "MATERIAL_CHANGE")
        self.assertEqual("STOPPED", result["state"])
        return paths, policy

    def test_mutation_holds_one_run_lock_across_load_replay_and_append(self) -> None:
        paths, first, policy = self._initialize("LOCAL_VERIFY")
        events = [first]
        self._admit(paths, policy, events, fixture_node("TEST-1", "test"))
        prior = self._admit(paths, policy, events, fixture_node("EVID-1", "evidence"))
        artifact = b"proof\n"
        artifact_digest = "sha256:" + hashlib.sha256(artifact).hexdigest()
        event = self._next_event(
            prior,
            fixture_event(
                "evidence_recorded",
                {
                    "evidence_id": "EVID-1",
                    "artifact_digest": artifact_digest,
                    "test_id": "TEST-1",
                    "snapshot_digest": DIGEST_TWO,
                    "cycle_id": 1,
                },
                issuer={"kind": "tool", "id": "pytest", "version": "8"},
                subject_ids=["EVID-1", "TEST-1"],
                artifact_refs=[{"path": "evidence/proof.txt", "sha256": artifact_digest}],
            ),
            sequence=4,
            event_id="EVT-000000000004",
        )
        real_load = store.load_events
        real_append = store.append_events
        observed: list[str] = []

        def guarded_load(run_paths: store.RunPaths) -> list[dict[str, object]]:
            self.assertTrue(run_paths.lock.is_file())
            observed.append("load")
            return real_load(run_paths)

        def guarded_append(
            run_paths: store.RunPaths,
            events: list[dict[str, object]],
            state: dict[str, object],
            artifacts: dict[str, bytes],
        ) -> None:
            self.assertTrue(run_paths.lock.is_file())
            observed.append("append")
            real_append(run_paths, events, state, artifacts)

        with (
            patch.object(controller.store, "load_events", side_effect=guarded_load),
            patch.object(controller.store, "append_events", side_effect=guarded_append),
        ):
            controller.record_event(
                self.repository, EXECUTION_ID, event, {artifact_digest: artifact}
            )

        self.assertEqual(["load", "append"], observed)
        self.assertFalse(paths.lock.exists())

    def test_commit_transition_is_the_locked_state_advance_path(self) -> None:
        paths, first, policy = self._initialize("REQUIREMENTS")
        events = [first]
        projection = controller.replay(policy, events)
        self._admit(
            paths,
            policy,
            events,
            fixture_receipt(
                projection, "requirements", "RCP-REQ-1", receipt_digest=DIGEST_ONE
            ),
        )
        projection = controller.replay(policy, events)
        self._admit(
            paths,
            policy,
            events,
            fixture_receipt(
                projection, "approval", "RCP-APPROVAL-1", receipt_digest=DIGEST_TWO
            ),
        )
        real_append = store.append_events

        def guarded_append(
            run_paths: store.RunPaths,
            events: list[dict[str, object]],
            state: dict[str, object],
            artifacts: dict[str, bytes],
        ) -> None:
            self.assertTrue(run_paths.lock.is_file())
            self.assertEqual(["transition_committed"], [event["type"] for event in events])
            real_append(run_paths, events, state, artifacts)

        with patch.object(controller.store, "append_events", side_effect=guarded_append):
            result = controller.commit_transition(self.repository, EXECUTION_ID, "G1")

        self.assertEqual("IMPLEMENT", result["state"])
        self.assertEqual("IMPLEMENT", controller.status_execution(self.repository, EXECUTION_ID)["state"])
        self.assertFalse(paths.lock.exists())

    def test_init_transition_is_executable(self) -> None:
        _, _, _ = self._initialize("INIT")

        result = controller.commit_transition(self.repository, EXECUTION_ID, "INIT")

        self.assertEqual("REQUIREMENTS", result["state"])
        self.assertEqual(
            "REQUIREMENTS", controller.status_execution(self.repository, EXECUTION_ID)["state"]
        )

    def test_init_status_advertises_exact_unauthorized_transition_targets(self) -> None:
        _, first, policy = self._initialize("INIT")
        projection = controller.replay(policy, [first])

        self.assertEqual(("REQUIREMENTS",), controller.allowed_transitions(projection))
        self.assertEqual(
            ["REQUIREMENTS"],
            controller.status_execution(self.repository, EXECUTION_ID)[
                "allowed_transitions"
            ],
        )
        for decision in ("STOP", "MATERIAL_CHANGE"):
            with self.subTest(decision=decision), self.assertRaises(
                controller.ControllerError
            ) as raised:
                controller.commit_transition(self.repository, EXECUTION_ID, decision)
            self.assertEqual("GATE_FAILED", raised.exception.code)
        self.assertEqual(
            "REQUIREMENTS",
            controller.commit_transition(self.repository, EXECUTION_ID, "INIT")["state"],
        )

    def test_init_status_advertises_authorized_terminal_target_commit_accepts(self) -> None:
        cases = (
            ("STOP", "stop", "EXEC-000000000001"),
            ("MATERIAL_CHANGE", "material_change", "EXEC-000000000002"),
        )
        for decision, receipt_type, execution_id in cases:
            with self.subTest(decision=decision):
                paths, first, policy = self._initialize(
                    "INIT", execution_id=execution_id
                )
                events = [first]
                projection = controller.replay(policy, events)
                self._admit(
                    paths,
                    policy,
                    events,
                    fixture_receipt(
                        projection,
                        receipt_type,
                        f"RCP-{decision}-INIT",
                        receipt_digest="sha256:"
                        + hashlib.sha256(decision.encode()).hexdigest(),
                    )
                    | {"execution_id": execution_id},
                )
                projection = controller.replay(policy, events)

                self.assertEqual(
                    ("REQUIREMENTS", "STOPPED"),
                    controller.allowed_transitions(projection),
                )
                self.assertEqual(
                    ["REQUIREMENTS", "STOPPED"],
                    controller.status_execution(self.repository, execution_id)[
                        "allowed_transitions"
                    ],
                )
                self.assertEqual(
                    "STOPPED",
                    controller.commit_transition(
                        self.repository, execution_id, decision
                    )["state"],
                )

    def test_generic_record_rejects_every_privileged_or_controller_event(self) -> None:
        paths, first, policy = self._initialize("REQUIREMENTS")
        projection = controller.replay(policy, [first])
        privileged = (
            fixture_receipt(projection, "requirements", "RCP-REQ-1"),
            fixture_node("REQ-2", "requirement"),
            fixture_event(
                "snapshot_activated", {"snapshot_digest": DIGEST_ONE, "cycle_id": 2}
            ),
            fixture_review(projection, "REV-1", "accepted", receipt_id="RCP-REV-1"),
            fixture_finding("REV-1", "ROOT-1", prose_digest=DIGEST_ONE),
            fixture_transition(
                projection, gate="INIT", source="INIT", target="REQUIREMENTS"
            ),
        )
        before = paths.events.read_bytes()
        for index, raw in enumerate(privileged, 2):
            event = self._next_event(
                first, raw, sequence=2, event_id=f"EVT-{index:012X}"
            )
            with self.subTest(event_type=raw["type"]), self.assertRaises(
                controller.ControllerError
            ) as raised:
                controller.record_event(self.repository, EXECUTION_ID, event, {})
            self.assertEqual("PRIVILEGED_EVENT", raised.exception.code)
        self.assertEqual(before, paths.events.read_bytes())

    def test_snapshot_activation_and_all_invalidations_use_one_atomic_batch(self) -> None:
        paths, first, policy = self._initialize("LOCAL_VERIFY")
        events = [first]
        self._admit(paths, policy, events, fixture_node("TEST-1", "test"))
        evidence_node = self._admit(
            paths, policy, events, fixture_node("EVID-1", "evidence")
        )
        artifact = b"proof\n"
        artifact_digest = "sha256:" + hashlib.sha256(artifact).hexdigest()
        evidence = chained(
            fixture_event(
                "evidence_recorded",
                {
                    "evidence_id": "EVID-1",
                    "artifact_digest": artifact_digest,
                    "test_id": "TEST-1",
                    "snapshot_digest": DIGEST_TWO,
                    "cycle_id": 1,
                },
                issuer={"kind": "tool", "id": "pytest", "version": "8"},
                subject_ids=["EVID-1", "TEST-1"],
                artifact_refs=[{"path": "evidence/proof.txt", "sha256": artifact_digest}],
            ),
            evidence_node,
            4,
            "EVT-222222222222",
        )
        controller.record_event(
            self.repository, EXECUTION_ID, evidence, {artifact_digest: artifact}
        )
        real_append = store.append_events
        batches: list[list[str]] = []

        def capture_batch(
            run_paths: store.RunPaths,
            events: list[dict[str, object]],
            state: dict[str, object],
            artifacts: dict[str, bytes],
        ) -> None:
            self.assertTrue(run_paths.lock.is_file())
            batches.append([str(event["type"]) for event in events])
            real_append(run_paths, events, state, artifacts)

        with patch.object(controller.store, "append_events", side_effect=capture_batch):
            controller.activate_snapshot(self.repository, EXECUTION_ID, DIGEST_THREE)

        self.assertEqual([["snapshot_activated", "evidence_invalidated"]], batches)
        projected = controller.status_execution(self.repository, EXECUTION_ID)
        self.assertEqual(6, projected["event_count"])
        self.assertEqual(2, projected["cycle_id"])

    def test_recovery_ambiguity_is_a_mutation_hard_stop(self) -> None:
        paths, first, _ = self._initialize("REQUIREMENTS")
        persisted = json.loads(paths.state.read_text(encoding="utf-8"))
        persisted["event_count"] = 9
        paths.state.write_bytes(contract.canonical_json_bytes(persisted))
        event = self._next_event(first, fixture_node("REQ-2", "requirement"))

        with self.assertRaises(store.StoreError) as raised:
            controller.record_event(self.repository, EXECUTION_ID, event, {})

        self.assertEqual("RECOVERY_REQUIRED", raised.exception.code)
        self.assertEqual(1, paths.events.read_bytes().count(b"\n"))

    def test_stopped_execution_cannot_resume(self) -> None:
        _, first, _ = self._initialize("STOPPED")
        event = self._next_event(first, fixture_node("REQ-2", "requirement"))

        with self.assertRaises(controller.ControllerError) as raised:
            controller.record_event(self.repository, EXECUTION_ID, event, {})

        self.assertEqual("TERMINAL_STATE", raised.exception.code)

    def test_successor_requires_terminal_predecessor_and_lineage(self) -> None:
        paths, _, _ = self._initialize("REQUIREMENTS")
        policy = {
            "execution_id": SUCCESSOR_ONE,
            "initial_state": "INIT",
            "requirements_digest": DIGEST_TWO,
            "authority_snapshot_digest": DIGEST_THREE,
        }
        valid = self._lineage(paths)

        for receipt in (
            valid,
            valid | {"lineage_receipt_digest": DIGEST_THREE},
            valid | {"supersedes": [valid["supersedes"][0], valid["supersedes"][0]]},
            valid | {"supersedes": [{"new_id": "REQ-1", "old_id": "REQ-1"}]},
        ):
            with self.subTest(receipt=receipt), self.assertRaises(controller.ControllerError):
                controller.start_successor(self.repository, EXECUTION_ID, receipt, policy)

    def test_successor_preserves_predecessor_and_allows_branching(self) -> None:
        paths, _ = self._terminal_predecessor()
        receipt = self._lineage(paths)
        before_events = paths.events.read_bytes()
        before_state = paths.state.read_bytes()

        first = controller.start_successor(
            self.repository,
            EXECUTION_ID,
            receipt,
            {
                "execution_id": SUCCESSOR_ONE,
                "initial_state": "INIT",
                "requirements_digest": DIGEST_TWO,
                "authority_snapshot_digest": DIGEST_THREE,
            },
        )
        second = controller.start_successor(
            self.repository,
            EXECUTION_ID,
            receipt,
            {
                "execution_id": SUCCESSOR_TWO,
                "initial_state": "INIT",
                "requirements_digest": DIGEST_TWO,
                "authority_snapshot_digest": DIGEST_THREE,
            },
        )

        self.assertEqual(SUCCESSOR_ONE, first["execution_id"])
        self.assertEqual(SUCCESSOR_TWO, second["execution_id"])
        self.assertEqual(before_events, paths.events.read_bytes())
        self.assertEqual(before_state, paths.state.read_bytes())
        self.assertEqual("INIT", controller.status_execution(self.repository, SUCCESSOR_ONE)["state"])
        successor_paths = store.resolve_run(self.repository, SUCCESSOR_ONE)
        successor_state = json.loads(successor_paths.state.read_text(encoding="utf-8"))
        successor_events = store.load_events(successor_paths)
        self.assertEqual(["receipt_imported"], [event["type"] for event in successor_events])
        self.assertEqual(
            {},
            controller.replay(successor_state["policy"], successor_events).gate_evidence,
        )
        self.assertEqual(
            "REQUIREMENTS",
            controller.commit_transition(self.repository, SUCCESSOR_ONE, "INIT")["state"],
        )

    def test_successor_requires_bound_policy_digests(self) -> None:
        paths, _ = self._terminal_predecessor()
        receipt = self._lineage(paths)
        base_policy = {
            "execution_id": SUCCESSOR_ONE,
            "initial_state": "INIT",
            "requirements_digest": DIGEST_TWO,
            "authority_snapshot_digest": DIGEST_THREE,
        }
        for missing in ("requirements_digest", "authority_snapshot_digest"):
            policy = dict(base_policy)
            policy.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(
                controller.ControllerError
            ) as raised:
                controller.start_successor(
                    self.repository, EXECUTION_ID, receipt, policy
                )
            self.assertEqual("INVALID_POLICY", raised.exception.code)

    def test_material_change_receipt_then_lifecycle_commit_stops_predecessor(self) -> None:
        paths, _ = self._terminal_predecessor()

        self.assertEqual("STOPPED", controller.status_execution(self.repository, EXECUTION_ID)["state"])
        self.assertEqual((), controller.allowed_transitions(fixture_projection("STOPPED")))
        self.assertGreater(paths.events.read_bytes().count(b"\n"), 1)

    def test_missing_or_corrupt_lineage_evidence_is_rejected(self) -> None:
        paths, _ = self._terminal_predecessor()
        valid = self._lineage(paths)
        policy = {
            "execution_id": SUCCESSOR_ONE,
            "initial_state": "INIT",
            "requirements_digest": DIGEST_TWO,
            "authority_snapshot_digest": DIGEST_THREE,
        }
        missing = valid | {"lineage_receipt_digest": DIGEST_THREE}
        with self.assertRaises(controller.ControllerError) as raised:
            controller.start_successor(self.repository, EXECUTION_ID, missing, policy)
        self.assertEqual("LINEAGE_EVIDENCE_MISSING", raised.exception.code)

        evidence_path = paths.evidence / str(valid["lineage_receipt_digest"])[7:]
        evidence_path.write_bytes(b"corrupt\n")
        with self.assertRaises(controller.ControllerError) as raised:
            controller.start_successor(self.repository, EXECUTION_ID, valid, policy)
        self.assertEqual("LINEAGE_EVIDENCE_CORRUPT", raised.exception.code)

    def test_recovery_required_predecessor_can_start_successor_without_mutation(self) -> None:
        paths, _, _ = self._initialize("REQUIREMENTS")
        receipt = self._lineage(paths)
        persisted = json.loads(paths.state.read_text(encoding="utf-8"))
        persisted["event_count"] = 99
        paths.state.write_bytes(contract.canonical_json_bytes(persisted))
        before_events = paths.events.read_bytes()
        before_state = paths.state.read_bytes()

        result = controller.start_successor(
            self.repository,
            EXECUTION_ID,
            receipt,
            {
                "execution_id": SUCCESSOR_ONE,
                "initial_state": "INIT",
                "requirements_digest": DIGEST_TWO,
                "authority_snapshot_digest": DIGEST_THREE,
            },
        )

        self.assertEqual(SUCCESSOR_ONE, result["execution_id"])
        self.assertEqual(before_events, paths.events.read_bytes())
        self.assertEqual(before_state, paths.state.read_bytes())

    def test_absent_predecessor_cannot_be_reclassified_by_shared_lineage_evidence(
        self,
    ) -> None:
        absent_paths = store.resolve_run(self.repository, EXECUTION_ID)
        receipt = self._lineage(absent_paths)
        self.assertFalse(absent_paths.root.exists())

        with self.assertRaises(controller.ControllerError) as raised:
            controller.start_successor(
                self.repository,
                EXECUTION_ID,
                receipt,
                {
                    "execution_id": SUCCESSOR_ONE,
                    "initial_state": "INIT",
                    "requirements_digest": DIGEST_TWO,
                    "authority_snapshot_digest": DIGEST_THREE,
                },
            )

        self.assertEqual("PREDECESSOR_NOT_FOUND", raised.exception.code)
        self.assertFalse(store.resolve_run(self.repository, SUCCESSOR_ONE).root.exists())


if __name__ == "__main__":
    unittest.main()
