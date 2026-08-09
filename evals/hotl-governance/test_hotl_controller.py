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
    digest: str | None = None,
    cycle_id: int | None = None,
) -> dict[str, object]:
    evidence_digest = digest or controller.projection_evidence_set_digest(projection)
    return fixture_event(
        "review_recorded",
        {
            "review_id": review_id,
            "status": status,
            "evidence_set_digest": evidence_digest,
            "cycle_id": projection.cycle_id if cycle_id is None else cycle_id,
        },
        issuer={"kind": "skill", "id": "gpt-pro-codex-loop", "version": "1"},
        subject_ids=[review_id],
        result="pass" if status == "accepted" else "fail",
        input_digest=evidence_digest,
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
    def test_evidence_event_never_advances_state(self) -> None:
        projection = fixture_projection("REQUIREMENTS")
        event = fixture_event(
            "receipt_imported",
            {
                "receipt_id": "RCP-1",
                "receipt_digest": DIGEST_ONE,
                "issuer_skill": "gpt-pro-codex-loop",
            },
        )

        result = controller.project_event(projection, event)

        self.assertEqual("REQUIREMENTS", result.state.value)

    def test_only_valid_transition_committed_advances_state(self) -> None:
        projection = fixture_projection(
            "REQUIREMENTS", gate_evidence={"G1": (DIGEST_ONE,)}
        )

        result = controller.project_event(
            projection,
            fixture_transition(
                projection, gate="G1", source="REQUIREMENTS", target="IMPLEMENT"
            ),
        )

        self.assertEqual("IMPLEMENT", result.state.value)

    def test_invalid_transition_bindings_are_rejected(self) -> None:
        projection = fixture_projection(
            "REQUIREMENTS", gate_evidence={"G1": (DIGEST_ONE,)}
        )
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
        }
        receipt = fixture_event(
            "receipt_imported",
            {
                "receipt_id": "RCP-1",
                "receipt_digest": DIGEST_TWO,
                "issuer_skill": "gpt-pro-codex-loop",
            },
        )
        seed = controller.replay(policy, [receipt])
        transition = chained(
            fixture_transition(seed, gate="G1", source="REQUIREMENTS", target="IMPLEMENT"),
            receipt,
            2,
            "EVT-ABCDEF123456",
        )

        left = controller.replay(policy, [receipt, transition])
        right = controller.replay(dict(reversed(tuple(policy.items()))), [receipt, transition])

        self.assertEqual(projection_bytes(left), projection_bytes(right))

    def test_free_text_metadata_does_not_change_transition(self) -> None:
        policy = {
            "execution_id": EXECUTION_ID,
            "initial_state": "REQUIREMENTS",
            "requirements_digest": DIGEST_ONE,
        }
        first = fixture_event(
            "receipt_imported",
            {
                "receipt_id": "RCP-1",
                "receipt_digest": DIGEST_TWO,
                "issuer_skill": "gpt-pro-codex-loop",
            },
        )
        alternate = first | {"timestamp": "a completely different display label"}
        first_projection = controller.replay(policy, [first])
        left_transition = chained(
            fixture_transition(
                first_projection, gate="G1", source="REQUIREMENTS", target="IMPLEMENT"
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

        result = controller.project_event(
            projection,
            fixture_review(projection, "REV-1", "rejected", cycle_id=1),
        )

        self.assertEqual((), result.valid_review_rounds)
        self.assertFalse(result.review_records["REV-1"].valid)

    def test_malformed_review_is_rejected_without_a_round(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        projection = controller.project_event(projection, fixture_node("REV-1", "review"))
        malformed = fixture_review(projection, "REV-1", "rejected")
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
        first_review = controller.project_event(
            projection, fixture_review(projection, "REV-1", "rejected")
        )
        first_finding = controller.project_event(
            first_review, fixture_finding("REV-1", "ROOT-stable", prose_digest=DIGEST_ONE)
        )
        second_review = controller.project_event(
            first_finding, fixture_review(first_finding, "REV-2", "rejected")
        )
        second_finding = controller.project_event(
            second_review, fixture_finding("REV-2", "ROOT-stable", prose_digest=DIGEST_THREE)
        )

        self.assertEqual(("IMPLEMENT",), controller.allowed_transitions(first_finding))
        self.assertEqual(("ESCALATED",), controller.allowed_transitions(second_finding))

    def test_third_valid_failed_review_escalates_even_with_distinct_roots(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for review_id in ("REV-1", "REV-2", "REV-3"):
            projection = controller.project_event(projection, fixture_node(review_id, "review"))
        for index in range(1, 4):
            projection = controller.project_event(
                projection, fixture_review(projection, f"REV-{index}", "rejected")
            )
            projection = controller.project_event(
                projection,
                fixture_finding(f"REV-{index}", f"ROOT-{index}", prose_digest=DIGEST_ONE),
            )

        self.assertEqual(("ESCALATED",), controller.allowed_transitions(projection))

    def test_accepted_review_breaks_consecutive_root_cause_failures(self) -> None:
        projection = fixture_projection(
            "SEMANTIC_REVIEW", active_snapshot_digest=DIGEST_TWO, cycle_id=1
        )
        for review_id in ("REV-1", "REV-2", "REV-3"):
            projection = controller.project_event(projection, fixture_node(review_id, "review"))
        projection = controller.project_event(
            projection, fixture_review(projection, "REV-1", "rejected")
        )
        projection = controller.project_event(
            projection, fixture_finding("REV-1", "ROOT-stable", prose_digest=DIGEST_ONE)
        )
        projection = controller.project_event(
            projection, fixture_review(projection, "REV-2", "accepted")
        )
        projection = controller.project_event(
            projection, fixture_review(projection, "REV-3", "rejected")
        )
        projection = controller.project_event(
            projection, fixture_finding("REV-3", "ROOT-stable", prose_digest=DIGEST_TWO)
        )

        self.assertEqual(("IMPLEMENT",), controller.allowed_transitions(projection))

    def test_terminal_states_have_no_allowed_transitions(self) -> None:
        for state in ("COMPLETE", "ESCALATED", "RECOVERY_REQUIRED", "STOPPED"):
            with self.subTest(state=state):
                self.assertEqual((), controller.allowed_transitions(fixture_projection(state)))


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
        projection = controller.project_event(
            projection, fixture_review(projection, "REV-1", "accepted")
        )
        for source, edge, target in (
            ("EVID-1", "supports", "REV-1"),
            ("REV-1", "reviews", "REQ-1"),
        ):
            projection = controller.project_event(projection, fixture_edge(source, edge, target))
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


class RepositoryControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _initialize(self, state: str, *, execution_id: str = EXECUTION_ID) -> tuple[store.RunPaths, dict[str, object]]:
        policy = {
            "execution_id": execution_id,
            "initial_state": state,
            "requirements_digest": DIGEST_ONE,
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
        return paths, first

    def _next_event(
        self,
        first: dict[str, object],
        event: dict[str, object],
        *,
        sequence: int = 2,
        event_id: str = "EVT-ABCDEF123456",
    ) -> dict[str, object]:
        return chained(event, first, sequence, event_id)

    def test_mutation_holds_one_run_lock_across_load_replay_and_append(self) -> None:
        paths, first = self._initialize("REQUIREMENTS")
        event = self._next_event(
            first,
            fixture_event(
                "receipt_imported",
                {
                    "receipt_id": "RCP-1",
                    "receipt_digest": DIGEST_TWO,
                    "issuer_skill": "gpt-pro-codex-loop",
                },
            ),
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
            controller.record_event(self.repository, EXECUTION_ID, event, {})

        self.assertEqual(["load", "append"], observed)
        self.assertFalse(paths.lock.exists())

    def test_commit_transition_is_the_locked_state_advance_path(self) -> None:
        paths, first = self._initialize("REQUIREMENTS")
        receipt = self._next_event(
            first,
            fixture_event(
                "receipt_imported",
                {
                    "receipt_id": "RCP-1",
                    "receipt_digest": DIGEST_TWO,
                    "issuer_skill": "gpt-pro-codex-loop",
                },
            ),
        )
        controller.record_event(self.repository, EXECUTION_ID, receipt, {})
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

    def test_snapshot_activation_and_all_invalidations_use_one_atomic_batch(self) -> None:
        paths, first = self._initialize("LOCAL_VERIFY")
        test_node = self._next_event(first, fixture_node("TEST-1", "test"))
        controller.record_event(self.repository, EXECUTION_ID, test_node, {})
        evidence_node = chained(
            fixture_node("EVID-1", "evidence"),
            test_node,
            3,
            "EVT-111111111111",
        )
        controller.record_event(self.repository, EXECUTION_ID, evidence_node, {})
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
        activation = chained(
            fixture_event(
                "snapshot_activated",
                {"snapshot_digest": DIGEST_THREE, "cycle_id": 2},
            ),
            evidence,
            5,
            "EVT-FEDCBA654321",
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
            controller.record_event(self.repository, EXECUTION_ID, activation, {})

        self.assertEqual([["snapshot_activated", "evidence_invalidated"]], batches)
        projected = controller.status_execution(self.repository, EXECUTION_ID)
        self.assertEqual(6, projected["event_count"])
        self.assertEqual(2, projected["cycle_id"])

    def test_stale_review_binding_is_rejected_before_append(self) -> None:
        paths, first = self._initialize("SEMANTIC_REVIEW")
        review_node = self._next_event(first, fixture_node("REV-1", "review"))
        controller.record_event(self.repository, EXECUTION_ID, review_node, {})
        projection = controller.replay(
            {
                "execution_id": EXECUTION_ID,
                "initial_state": "SEMANTIC_REVIEW",
                "requirements_digest": DIGEST_ONE,
                "active_snapshot_digest": DIGEST_TWO,
                "cycle_id": 1,
            },
            [first, review_node],
        )
        stale = chained(
            fixture_review(projection, "REV-1", "rejected", digest=DIGEST_THREE),
            review_node,
            3,
            "EVT-222222222222",
        )

        with self.assertRaises(controller.ControllerError) as raised:
            controller.record_event(self.repository, EXECUTION_ID, stale, {})

        self.assertEqual("STALE_REVIEW_BINDING", raised.exception.code)
        self.assertEqual(2, len(store.load_events(paths)))

    def test_recovery_ambiguity_is_a_mutation_hard_stop(self) -> None:
        paths, first = self._initialize("REQUIREMENTS")
        persisted = json.loads(paths.state.read_text(encoding="utf-8"))
        persisted["event_count"] = 9
        paths.state.write_bytes(contract.canonical_json_bytes(persisted))
        event = self._next_event(
            first,
            fixture_event(
                "receipt_imported",
                {
                    "receipt_id": "RCP-1",
                    "receipt_digest": DIGEST_TWO,
                    "issuer_skill": "gpt-pro-codex-loop",
                },
            ),
        )

        with self.assertRaises(store.StoreError) as raised:
            controller.record_event(self.repository, EXECUTION_ID, event, {})

        self.assertEqual("RECOVERY_REQUIRED", raised.exception.code)
        self.assertEqual(1, paths.events.read_bytes().count(b"\n"))

    def test_stopped_execution_cannot_resume(self) -> None:
        _, first = self._initialize("STOPPED")
        event = self._next_event(first, fixture_node("REQ-2", "requirement"))

        with self.assertRaises(controller.ControllerError) as raised:
            controller.record_event(self.repository, EXECUTION_ID, event, {})

        self.assertEqual("TERMINAL_STATE", raised.exception.code)

    def test_successor_requires_terminal_predecessor_and_lineage(self) -> None:
        self._initialize("REQUIREMENTS")
        policy = {
            "execution_id": SUCCESSOR_ONE,
            "initial_state": "INIT",
            "requirements_digest": DIGEST_TWO,
        }
        valid = {
            "predecessor_execution_id": EXECUTION_ID,
            "lineage_receipt_digest": DIGEST_THREE,
            "supersedes": [{"new_id": "REQ-2", "old_id": "REQ-1"}],
        }

        for receipt in (valid, valid | {"lineage_receipt_digest": ""}):
            with self.subTest(receipt=receipt), self.assertRaises(controller.ControllerError):
                controller.start_successor(self.repository, EXECUTION_ID, receipt, policy)

    def test_successor_preserves_predecessor_and_allows_branching(self) -> None:
        paths, _ = self._initialize("ESCALATED")
        before_events = paths.events.read_bytes()
        before_state = paths.state.read_bytes()
        receipt = {
            "predecessor_execution_id": EXECUTION_ID,
            "lineage_receipt_digest": DIGEST_THREE,
            "supersedes": [{"new_id": "REQ-2", "old_id": "REQ-1"}],
        }

        first = controller.start_successor(
            self.repository,
            EXECUTION_ID,
            receipt,
            {
                "execution_id": SUCCESSOR_ONE,
                "initial_state": "INIT",
                "requirements_digest": DIGEST_TWO,
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


if __name__ == "__main__":
    unittest.main()
