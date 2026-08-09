"""Deterministic HOTL replay, gate evaluation, and execution lifecycle."""

from __future__ import annotations

import hashlib
import re
import stat
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlparse

import hotl_contract as contract
import hotl_store as store


class ControllerError(RuntimeError):
    """A stable controller-boundary failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class State(str, Enum):
    INIT = "INIT"
    REQUIREMENTS = "REQUIREMENTS"
    IMPLEMENT = "IMPLEMENT"
    LOCAL_VERIFY = "LOCAL_VERIFY"
    SEMANTIC_REVIEW = "SEMANTIC_REVIEW"
    COMPLETE = "COMPLETE"
    ESCALATED = "ESCALATED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    STOPPED = "STOPPED"


TERMINAL_STATES = frozenset(
    {State.COMPLETE, State.ESCALATED, State.RECOVERY_REQUIRED, State.STOPPED}
)


@dataclass(frozen=True)
class NodeRecord:
    node_id: str
    node_type: str
    active: bool = True


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    artifact_digest: str
    test_id: str
    snapshot_digest: str
    cycle_id: int
    status: str


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    receipt_id: str
    status: str
    evidence_set_digest: str
    cycle_id: int
    input_digest: str
    valid: bool


@dataclass(frozen=True)
class FindingRecord:
    finding_id: str
    root_cause_id: str
    review_id: str
    status: str


@dataclass(frozen=True)
class ReviewRound:
    review_id: str
    status: str
    root_cause_ids: tuple[str, ...]
    cycle_id: int


@dataclass(frozen=True)
class ReceiptRecord:
    receipt_id: str
    receipt_type: str
    receipt_digest: str
    issuer_skill: str
    authority_snapshot_digest: str | None
    requirements_digest: str | None
    snapshot_digest: str | None
    evidence_set_digest: str | None
    cycle_id: int | None
    valid: bool


@dataclass(frozen=True)
class Projection:
    execution_id: str
    state: State
    active_snapshot_digest: str | None
    nodes: Mapping[str, NodeRecord]
    edges: tuple[tuple[str, str, str], ...]
    evidence_records: Mapping[str, EvidenceRecord]
    review_records: Mapping[str, ReviewRecord]
    receipt_records: Mapping[str, ReceiptRecord]
    gate_evidence: Mapping[str, tuple[str, ...]]
    finding_state: Mapping[str, FindingRecord]
    valid_review_rounds: tuple[ReviewRound, ...]
    cycle_id: int
    requirements_digest: str
    authority_snapshot_digest: str
    approval_mode: str


def _controller_error(error: Exception) -> ControllerError:
    if isinstance(error, contract.ContractError):
        return ControllerError(error.code, error.message)
    return ControllerError("INVALID_EVENT", "Event does not satisfy the controller contract.")


def _canonical_mapping(value: Mapping[str, object]) -> dict[str, object]:
    try:
        contract.canonical_json_bytes(value)
    except contract.ContractError as error:
        raise _controller_error(error) from error
    return {key: value[key] for key in sorted(value)}


def empty_projection(
    execution_id: str,
    state: State = State.INIT,
    *,
    active_snapshot_digest: str | None = None,
    nodes: Mapping[str, NodeRecord] | None = None,
    edges: Sequence[tuple[str, str, str]] = (),
    evidence_records: Mapping[str, EvidenceRecord] | None = None,
    review_records: Mapping[str, ReviewRecord] | None = None,
    receipt_records: Mapping[str, ReceiptRecord] | None = None,
    gate_evidence: Mapping[str, Sequence[str]] | None = None,
    finding_state: Mapping[str, FindingRecord] | None = None,
    valid_review_rounds: Sequence[ReviewRound] = (),
    cycle_id: int = 0,
    requirements_digest: str | None = None,
    authority_snapshot_digest: str | None = None,
    approval_mode: str = "agentic",
) -> Projection:
    """Return an empty, execution-bound projection."""
    if not isinstance(execution_id, str) or contract.EXECUTION_ID.fullmatch(execution_id) is None:
        raise ControllerError("INVALID_EXECUTION_ID", "Invalid execution ID.")
    if not isinstance(state, State):
        try:
            state = State(state)
        except (TypeError, ValueError) as error:
            raise ControllerError("INVALID_STATE", "Invalid execution state.") from error
    if not isinstance(cycle_id, int) or isinstance(cycle_id, bool) or cycle_id < 0:
        raise ControllerError("INVALID_CYCLE", "cycle_id must be a non-negative integer.")
    if active_snapshot_digest is not None and contract.DIGEST.fullmatch(active_snapshot_digest) is None:
        raise ControllerError("INVALID_DIGEST", "Invalid active snapshot digest.")
    if requirements_digest is None:
        requirements_digest = contract.canonical_digest({"requirements": []})
    if contract.DIGEST.fullmatch(requirements_digest) is None:
        raise ControllerError("INVALID_DIGEST", "Invalid requirements digest.")
    if authority_snapshot_digest is None:
        authority_snapshot_digest = contract.canonical_digest({"authority": []})
    if contract.DIGEST.fullmatch(authority_snapshot_digest) is None:
        raise ControllerError("INVALID_DIGEST", "Invalid authority snapshot digest.")
    if approval_mode not in {"agentic", "offline_manual"}:
        raise ControllerError("INVALID_POLICY", "Invalid approval mode.")
    normalized_gate_evidence = {
        gate: tuple(sorted(values)) for gate, values in sorted((gate_evidence or {}).items())
    }
    return Projection(
        execution_id=execution_id,
        state=state,
        active_snapshot_digest=active_snapshot_digest,
        nodes=dict(sorted((nodes or {}).items())),
        edges=tuple(sorted(tuple(edge) for edge in edges)),
        evidence_records=dict(sorted((evidence_records or {}).items())),
        review_records=dict(sorted((review_records or {}).items())),
        receipt_records=dict(sorted((receipt_records or {}).items())),
        gate_evidence=normalized_gate_evidence,
        finding_state=dict(sorted((finding_state or {}).items())),
        valid_review_rounds=tuple(valid_review_rounds),
        cycle_id=cycle_id,
        requirements_digest=requirements_digest,
        authority_snapshot_digest=authority_snapshot_digest,
        approval_mode=approval_mode,
    )


def _record_value(record: EvidenceRecord | Mapping[str, object], field: str) -> object:
    if isinstance(record, EvidenceRecord):
        return getattr(record, field)
    if isinstance(record, Mapping):
        return record.get(field)
    raise ControllerError("INVALID_EVIDENCE", "Evidence records must be typed records or mappings.")


def evidence_set_digest(
    requirements_digest: str,
    snapshot_digest: str | None,
    evidence_records: Mapping[str, EvidenceRecord | Mapping[str, object]]
    | Sequence[EvidenceRecord | Mapping[str, object]],
) -> str:
    """Digest the canonical current evidence set, independent of input order."""
    if not isinstance(requirements_digest, str) or contract.DIGEST.fullmatch(requirements_digest) is None:
        raise ControllerError("INVALID_DIGEST", "Invalid requirements digest.")
    if snapshot_digest is not None and (
        not isinstance(snapshot_digest, str) or contract.DIGEST.fullmatch(snapshot_digest) is None
    ):
        raise ControllerError("INVALID_DIGEST", "Invalid snapshot digest.")
    values = evidence_records.values() if isinstance(evidence_records, Mapping) else evidence_records
    records: list[dict[str, str]] = []
    for record in values:
        status = _record_value(record, "status")
        if status != "valid_current":
            continue
        evidence_id = _record_value(record, "evidence_id")
        artifact_digest = _record_value(record, "artifact_digest")
        test_id = _record_value(record, "test_id")
        if (
            not isinstance(evidence_id, str)
            or not evidence_id.startswith("EVID-")
            or not isinstance(test_id, str)
            or not test_id.startswith("TEST-")
            or not isinstance(artifact_digest, str)
            or contract.DIGEST.fullmatch(artifact_digest) is None
        ):
            raise ControllerError("INVALID_EVIDENCE", "Invalid evidence-set record.")
        records.append(
            {
                "artifact_digest": artifact_digest,
                "evidence_id": evidence_id,
                "test_id": test_id,
            }
        )
    records.sort(key=lambda item: (item["evidence_id"], item["artifact_digest"], item["test_id"]))
    return contract.canonical_digest(
        {
            "evidence_records": records,
            "requirements_digest": requirements_digest,
            "snapshot_digest": snapshot_digest,
        }
    )


def projection_evidence_set_digest(projection: Projection) -> str:
    return evidence_set_digest(
        projection.requirements_digest,
        projection.active_snapshot_digest,
        projection.evidence_records,
    )


def _validated_event(event: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(event, Mapping):
        raise ControllerError("INVALID_EVENT", "Event must be a mapping.")
    candidate = dict(event)
    try:
        sequence = candidate.get("sequence")
        previous = candidate.get("previous_event_hash") if sequence != 1 else None
        return contract.validate_event(candidate, previous, sequence)  # type: ignore[arg-type]
    except (contract.ContractError, TypeError, ValueError) as error:
        raise _controller_error(error) from error


def _copy_projection(projection: Projection, **changes: object) -> Projection:
    return replace(projection, **changes)


def _mark_superseded(
    nodes: Mapping[str, NodeRecord], source_id: str, target_id: str
) -> dict[str, NodeRecord]:
    result = dict(nodes)
    result[target_id] = replace(result[target_id], active=False)
    if source_id == target_id:
        raise ControllerError("SUPERSEDES_CYCLE", "A node cannot supersede itself.")
    return dict(sorted(result.items()))


def _review_is_current(projection: Projection, event: Mapping[str, object]) -> bool:
    payload = event["payload"]
    assert isinstance(payload, dict)
    expected = projection_evidence_set_digest(projection)
    receipt = projection.receipt_records.get(str(payload["receipt_id"]))
    return (
        projection.state == State.SEMANTIC_REVIEW
        and receipt is not None
        and _receipt_is_current(projection, receipt)
        and receipt.receipt_type == "semantic_review"
        and receipt.issuer_skill == "gpt-pro-codex-loop"
        and payload["cycle_id"] == projection.cycle_id
        and payload["evidence_set_digest"] == expected
        and event["input_digest"] == expected
    )


def _snapshot_binding_is_current(
    receipt_type: str, snapshot_digest: object, active_snapshot_digest: str
) -> bool:
    if receipt_type in {"material_change", "stop"} and snapshot_digest is None:
        return True
    return snapshot_digest == active_snapshot_digest


def project_event(projection: Projection, event: Mapping[str, object]) -> Projection:
    """Project one validated event; only a committed transition may change state."""
    candidate = _validated_event(event)
    if candidate["execution_id"] != projection.execution_id:
        raise ControllerError("EXECUTION_MISMATCH", "Event execution does not match projection.")
    event_type = candidate["type"]
    payload = candidate["payload"]
    assert isinstance(payload, dict)

    if projection.state in TERMINAL_STATES:
        raise ControllerError("TERMINAL_STATE", "Terminal executions cannot accept later events.")

    if event_type == "node_declared":
        node_id = str(payload["node_id"])
        if node_id in projection.nodes:
            raise ControllerError("DUPLICATE_NODE", "Node IDs are execution-local and unique.")
        nodes = dict(projection.nodes)
        nodes[node_id] = NodeRecord(node_id, str(payload["node_type"]))
        return _copy_projection(projection, nodes=dict(sorted(nodes.items())))

    if event_type == "edge_declared":
        source = str(payload["source_id"])
        target = str(payload["target_id"])
        edge = str(payload["edge"])
        if source not in projection.nodes or target not in projection.nodes:
            raise ControllerError("UNKNOWN_NODE", "Edges must reference declared nodes.")
        triple = (source, edge, target)
        if triple in projection.edges:
            raise ControllerError("DUPLICATE_EDGE", "Typed edges must be unique.")
        nodes = projection.nodes
        if edge == "supersedes":
            nodes = _mark_superseded(nodes, source, target)
        return _copy_projection(
            projection,
            nodes=nodes,
            edges=tuple(sorted((*projection.edges, triple))),
        )

    if event_type == "snapshot_activated":
        cycle_id = int(payload["cycle_id"])
        if cycle_id != projection.cycle_id + 1:
            raise ControllerError("STALE_CYCLE", "Snapshot activation must advance exactly one cycle.")
        evidence = {
            key: replace(value, status="historically_valid")
            if value.status == "valid_current"
            else value
            for key, value in projection.evidence_records.items()
        }
        return _copy_projection(
            projection,
            active_snapshot_digest=str(payload["snapshot_digest"]),
            evidence_records=dict(sorted(evidence.items())),
            cycle_id=cycle_id,
        )

    if event_type == "evidence_recorded":
        evidence_id = str(payload["evidence_id"])
        test_id = str(payload["test_id"])
        if evidence_id not in projection.nodes or test_id not in projection.nodes:
            raise ControllerError("UNKNOWN_NODE", "Evidence must reference declared evidence and test nodes.")
        if evidence_id in projection.evidence_records:
            raise ControllerError("DUPLICATE_EVIDENCE", "Evidence IDs are immutable and unique.")
        is_current = (
            payload["cycle_id"] == projection.cycle_id
            and payload["snapshot_digest"] == projection.active_snapshot_digest
        )
        evidence = dict(projection.evidence_records)
        evidence[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id,
            artifact_digest=str(payload["artifact_digest"]),
            test_id=test_id,
            snapshot_digest=str(payload["snapshot_digest"]),
            cycle_id=int(payload["cycle_id"]),
            status="valid_current" if is_current else "historically_valid",
        )
        return _copy_projection(projection, evidence_records=dict(sorted(evidence.items())))

    if event_type == "evidence_invalidated":
        evidence_id = str(payload["evidence_id"])
        if evidence_id not in projection.evidence_records:
            raise ControllerError("UNKNOWN_EVIDENCE", "Cannot invalidate unknown evidence.")
        evidence = dict(projection.evidence_records)
        evidence[evidence_id] = replace(evidence[evidence_id], status="historically_valid")
        return _copy_projection(projection, evidence_records=dict(sorted(evidence.items())))

    if event_type == "review_recorded":
        review_id = str(payload["review_id"])
        receipt_id = str(payload["receipt_id"])
        if review_id not in projection.nodes:
            raise ControllerError("UNKNOWN_NODE", "Reviews must reference a declared review node.")
        if review_id in projection.review_records:
            raise ControllerError("DUPLICATE_REVIEW", "Review IDs are immutable and unique.")
        if any(
            review.receipt_id == receipt_id
            for review in projection.review_records.values()
        ):
            raise ControllerError(
                "REPLAYED_RECEIPT", "A semantic receipt authorizes only one review round."
            )
        valid = _review_is_current(projection, candidate)
        review = ReviewRecord(
            review_id=review_id,
            receipt_id=receipt_id,
            status=str(payload["status"]),
            evidence_set_digest=str(payload["evidence_set_digest"]),
            cycle_id=int(payload["cycle_id"]),
            input_digest=str(candidate["input_digest"]),
            valid=valid,
        )
        reviews = dict(projection.review_records)
        reviews[review_id] = review
        rounds = projection.valid_review_rounds
        if valid:
            rounds = (
                *rounds,
                ReviewRound(
                    review_id,
                    review.status,
                    tuple(str(root) for root in payload["root_cause_ids"]),
                    review.cycle_id,
                ),
            )
        return _copy_projection(
            projection,
            review_records=dict(sorted(reviews.items())),
            valid_review_rounds=rounds,
        )

    if event_type == "finding_recorded":
        review_id = str(payload["review_id"])
        review = projection.review_records.get(review_id)
        if review is None:
            raise ControllerError("UNKNOWN_REVIEW", "Finding must reference a recorded review.")
        finding_id = str(payload["finding_id"])
        if finding_id in projection.finding_state:
            prior = projection.finding_state[finding_id]
            if prior.root_cause_id != payload["root_cause_id"] or prior.review_id != review_id:
                raise ControllerError("FINDING_MISMATCH", "Finding identity cannot be rebound.")
        findings = dict(projection.finding_state)
        findings[finding_id] = FindingRecord(
            finding_id,
            str(payload["root_cause_id"]),
            review_id,
            str(payload["status"]),
        )
        return _copy_projection(
            projection,
            finding_state=dict(sorted(findings.items())),
        )

    if event_type == "receipt_imported":
        receipt_id = str(payload["receipt_id"])
        digest = str(payload["receipt_digest"])
        if receipt_id in projection.receipt_records:
            raise ControllerError("DUPLICATE_RECEIPT", "Receipt ID was already imported.")
        if any(record.receipt_digest == digest for record in projection.receipt_records.values()):
            raise ControllerError("REPLAYED_RECEIPT", "Receipt digest was already imported.")
        receipt_type = str(payload["receipt_type"])
        current_bound = receipt_type not in {"requirements", "approval", "lineage"}
        valid = receipt_type == "lineage" or (
            payload["authority_snapshot_digest"] == projection.authority_snapshot_digest
            and payload["requirements_digest"] == projection.requirements_digest
            and (
                not current_bound
                or (
                    _snapshot_binding_is_current(
                        receipt_type,
                        payload["snapshot_digest"],
                        projection.active_snapshot_digest,
                    )
                    and payload["evidence_set_digest"]
                    == projection_evidence_set_digest(projection)
                    and payload["cycle_id"] == projection.cycle_id
                )
            )
        )
        receipts = dict(projection.receipt_records)
        receipts[receipt_id] = ReceiptRecord(
            receipt_id=receipt_id,
            receipt_type=receipt_type,
            receipt_digest=digest,
            issuer_skill=str(payload["issuer_skill"]),
            authority_snapshot_digest=payload["authority_snapshot_digest"],  # type: ignore[arg-type]
            requirements_digest=payload["requirements_digest"],  # type: ignore[arg-type]
            snapshot_digest=payload["snapshot_digest"],  # type: ignore[arg-type]
            evidence_set_digest=payload["evidence_set_digest"],  # type: ignore[arg-type]
            cycle_id=payload["cycle_id"],  # type: ignore[arg-type]
            valid=valid,
        )
        return _copy_projection(projection, receipt_records=dict(sorted(receipts.items())))

    source = State(str(payload["from_state"]))
    target = State(str(payload["to_state"]))
    gate = str(payload["gate"])
    if source != projection.state:
        raise ControllerError("STATE_MISMATCH", "Committed transition source is stale.")
    if int(payload["cycle_id"]) != projection.cycle_id:
        raise ControllerError("STALE_CYCLE", "Committed transition cycle is stale.")
    expected_digest = projection_evidence_set_digest(projection)
    if payload["evidence_set_digest"] != expected_digest or candidate["input_digest"] != expected_digest:
        raise ControllerError("EVIDENCE_SET_MISMATCH", "Committed transition evidence set is stale.")
    expected_target = _transition_target(projection, gate)
    if target != expected_target:
        raise ControllerError("INVALID_TRANSITION", "Committed transition target is not permitted.")
    next_cycle = projection.cycle_id
    evidence = projection.evidence_records
    if source == State.SEMANTIC_REVIEW and target == State.IMPLEMENT:
        next_cycle += 1
        evidence = {
            key: replace(value, status="historically_valid")
            if value.status == "valid_current"
            else value
            for key, value in evidence.items()
        }
    return _copy_projection(
        projection,
        state=target,
        cycle_id=next_cycle,
        evidence_records=dict(sorted(evidence.items())),
    )


def replay(policy: Mapping[str, object], events: Sequence[Mapping[str, object]]) -> Projection:
    """Purely replay an ordered, validated event chain under a fixed policy."""
    normalized = _canonical_mapping(policy)
    execution_id = normalized.get("execution_id")
    if not isinstance(execution_id, str):
        raise ControllerError("INVALID_POLICY", "Policy requires execution_id.")
    try:
        initial_state = State(normalized.get("initial_state", State.INIT.value))
    except (TypeError, ValueError) as error:
        raise ControllerError("INVALID_POLICY", "Policy initial_state is invalid.") from error
    projection = empty_projection(
        execution_id,
        initial_state,
        active_snapshot_digest=normalized.get("active_snapshot_digest"),  # type: ignore[arg-type]
        cycle_id=normalized.get("cycle_id", 0),  # type: ignore[arg-type]
        requirements_digest=normalized.get("requirements_digest"),  # type: ignore[arg-type]
        authority_snapshot_digest=normalized.get("authority_snapshot_digest"),  # type: ignore[arg-type]
        approval_mode=normalized.get("approval_mode", "agentic"),  # type: ignore[arg-type]
        gate_evidence=normalized.get("gate_evidence"),  # type: ignore[arg-type]
    )
    previous_hash: str | None = None
    seen_event_ids: set[str] = set()
    for sequence, raw_event in enumerate(events, 1):
        candidate = dict(raw_event)
        try:
            validated = contract.validate_event(candidate, previous_hash, sequence)
        except contract.ContractError as error:
            raise _controller_error(error) from error
        event_id = str(validated["event_id"])
        if event_id in seen_event_ids:
            raise ControllerError("DUPLICATE_EVENT", "Event IDs are execution-local and unique.")
        seen_event_ids.add(event_id)
        projection = project_event(projection, validated)
        previous_hash = contract.canonical_digest(validated)
    return projection


def _active_nodes(projection: Projection, node_type: str) -> set[str]:
    return {
        node_id
        for node_id, record in projection.nodes.items()
        if record.node_type == node_type and record.active
    }


def _has_edge(projection: Projection, source: str, edge: str, target: str) -> bool:
    return (source, edge, target) in projection.edges


def completion_errors(projection: Projection) -> tuple[str, ...]:
    """Return stable typed-provenance completion failures."""
    errors: list[str] = []
    requirements = sorted(_active_nodes(projection, "requirement"))
    codes = _active_nodes(projection, "code")
    tests = _active_nodes(projection, "test")
    commands = _active_nodes(projection, "command")
    changes = _active_nodes(projection, "change")
    reviews = _active_nodes(projection, "review")
    current_evidence = {
        evidence_id
        for evidence_id, record in projection.evidence_records.items()
        if record.status == "valid_current"
        and record.cycle_id == projection.cycle_id
        and record.snapshot_digest == projection.active_snapshot_digest
    }
    current_digest = projection_evidence_set_digest(projection)

    if not requirements:
        errors.append("missing_active_requirement")
    for requirement in requirements:
        implementing = sorted(code for code in codes if _has_edge(projection, code, "implements", requirement))
        verifying = sorted(test for test in tests if _has_edge(projection, test, "verifies", requirement))
        if not implementing:
            errors.append(f"{requirement}:missing_implementation")
        if not verifying:
            errors.append(f"{requirement}:missing_test")

        covered_tests: list[str] = []
        for test in verifying:
            for command in commands:
                if not _has_edge(projection, command, "executes", test):
                    continue
                for evidence_id in current_evidence:
                    record = projection.evidence_records[evidence_id]
                    if (
                        record.test_id == test
                        and _has_edge(projection, command, "produces", evidence_id)
                        and _has_edge(projection, evidence_id, "proves", test)
                    ):
                        covered_tests.append(test)
        if verifying and not covered_tests:
            errors.append(f"{requirement}:missing_current_evidence")

        accepted_reviews = [
            review_id
            for review_id in reviews
            if (review := projection.review_records.get(review_id)) is not None
            and review.valid
            and review.status == "accepted"
            and review.cycle_id == projection.cycle_id
            and review.evidence_set_digest == current_digest
            and review.input_digest == current_digest
            and _has_edge(projection, review_id, "reviews", requirement)
            and any(
                _has_edge(projection, evidence_id, "supports", review_id)
                for evidence_id in current_evidence
            )
        ]
        if not accepted_reviews:
            errors.append(f"{requirement}:missing_accepted_review")

        if implementing and not any(
            _has_edge(projection, code, "included_in", change)
            for code in implementing
            for change in changes
        ):
            errors.append(f"{requirement}:implementation_not_in_change")
        if verifying and not any(
            _has_edge(projection, test, "included_in", change)
            for test in verifying
            for change in changes
        ):
            errors.append(f"{requirement}:test_not_in_change")

    if any(record.status == "open" for record in projection.finding_state.values()):
        errors.append("unresolved_findings")
    return tuple(sorted(set(errors)))


def _failed_rounds(projection: Projection) -> tuple[ReviewRound, ...]:
    return tuple(round_record for round_record in projection.valid_review_rounds if round_record.status == "rejected")


def _receipt_is_current(projection: Projection, record: ReceiptRecord) -> bool:
    if not record.valid:
        return False
    if record.receipt_type == "lineage":
        return True
    if (
        record.authority_snapshot_digest != projection.authority_snapshot_digest
        or record.requirements_digest != projection.requirements_digest
    ):
        return False
    if record.receipt_type in {"requirements", "approval"}:
        return True
    return (
        _snapshot_binding_is_current(
            record.receipt_type,
            record.snapshot_digest,
            projection.active_snapshot_digest,
        )
        and record.evidence_set_digest == projection_evidence_set_digest(projection)
        and record.cycle_id == projection.cycle_id
    )


def _has_current_receipt(projection: Projection, receipt_type: str, issuer: str) -> bool:
    return any(
        _receipt_is_current(projection, record)
        and record.receipt_type == receipt_type
        and record.issuer_skill == issuer
        for record in projection.receipt_records.values()
    )


def _local_evidence_errors(projection: Projection) -> tuple[str, ...]:
    errors: list[str] = []
    requirements = sorted(_active_nodes(projection, "requirement"))
    tests = _active_nodes(projection, "test")
    commands = _active_nodes(projection, "command")
    current = {
        evidence_id
        for evidence_id, record in projection.evidence_records.items()
        if record.status == "valid_current"
        and record.cycle_id == projection.cycle_id
        and record.snapshot_digest == projection.active_snapshot_digest
    }
    if not requirements:
        errors.append("missing_active_requirement")
    for requirement in requirements:
        verifying = [test for test in tests if _has_edge(projection, test, "verifies", requirement)]
        if not verifying:
            errors.append(f"{requirement}:missing_test")
            continue
        if not any(
            _has_edge(projection, command, "executes", test)
            and _has_edge(projection, command, "produces", evidence_id)
            and _has_edge(projection, evidence_id, "proves", test)
            and projection.evidence_records[evidence_id].test_id == test
            for test in verifying
            for command in commands
            for evidence_id in current
        ):
            errors.append(f"{requirement}:missing_current_evidence")
    return tuple(errors)


def _must_escalate(projection: Projection) -> bool:
    failed = _failed_rounds(projection)
    if len(failed) >= 3:
        return True
    if len(projection.valid_review_rounds) < 2:
        return False
    previous, current = projection.valid_review_rounds[-2:]
    return (
        previous.status == "rejected"
        and current.status == "rejected"
        and bool(set(previous.root_cause_ids) & set(current.root_cause_ids))
    )


def evaluate_gate(projection: Projection, gate: str) -> tuple[bool, tuple[str, ...]]:
    """Evaluate a gate without ingesting evidence or advancing state."""
    expected_sources = {
        "G1": State.REQUIREMENTS,
        "G2": State.IMPLEMENT,
        "G3": State.LOCAL_VERIFY,
        "G4": State.SEMANTIC_REVIEW,
    }
    if gate not in expected_sources:
        return False, ("unknown_gate",)
    if projection.state != expected_sources[gate]:
        return False, (f"{gate}:invalid_state",)
    if gate == "G1":
        errors_list: list[str] = []
        if not _active_nodes(projection, "requirement"):
            errors_list.append("G1:missing_frozen_requirements")
        if not _has_current_receipt(projection, "requirements", "gpt-pro-codex-loop"):
            errors_list.append("G1:missing_requirements_receipt")
        approval_issuers = {"gpt-pro-codex-loop", "hotl-host-approval"}
        if projection.approval_mode == "offline_manual":
            approval_issuers.add("trusted-local-operator")
        if not any(
            _has_current_receipt(projection, "approval", issuer)
            for issuer in sorted(approval_issuers)
        ):
            errors_list.append("G1:missing_approval_receipt")
        errors = tuple(errors_list)
    elif gate == "G2":
        requirements = _active_nodes(projection, "requirement")
        codes = _active_nodes(projection, "code")
        linked = all(
            any(_has_edge(projection, code, "implements", requirement) for code in codes)
            for requirement in requirements
        )
        errors_list = [] if requirements and linked else ["G2:missing_implementation_links"]
        if not _has_current_receipt(projection, "implementation", "codex"):
            errors_list.append("G2:missing_implementation_receipt")
        errors = tuple(errors_list)
    elif gate == "G3":
        errors_list = list(_local_evidence_errors(projection))
        if not _has_current_receipt(projection, "verification", "hotl-local-verifier"):
            errors_list.append("G3:missing_verification_receipt")
        errors = tuple(errors_list)
    else:
        errors_list = list(completion_errors(projection))
        if not _has_current_receipt(projection, "final", "gpt-pro-codex-loop"):
            errors_list.append("G4:missing_final_receipt")
        errors = tuple(errors_list)
    return not errors, errors


def _latest_valid_round(projection: Projection) -> ReviewRound | None:
    return projection.valid_review_rounds[-1] if projection.valid_review_rounds else None


def _transition_target(projection: Projection, gate: str) -> State:
    if projection.state in TERMINAL_STATES:
        raise ControllerError("TERMINAL_STATE", "Terminal executions cannot transition.")
    if projection.state == State.INIT and gate == "INIT":
        has_requirements = bool(_active_nodes(projection, "requirement"))
        has_lineage = _has_current_receipt(
            projection, "lineage", "hotl-governance-lineage"
        )
        if not (has_requirements or has_lineage):
            raise ControllerError(
                "GATE_FAILED", "INIT requires published requirements or valid lineage."
            )
        return State.REQUIREMENTS
    direct = {
        (State.REQUIREMENTS, "G1"): State.IMPLEMENT,
        (State.IMPLEMENT, "G2"): State.LOCAL_VERIFY,
        (State.LOCAL_VERIFY, "G3"): State.SEMANTIC_REVIEW,
    }
    if (projection.state, gate) in direct:
        passed, errors = evaluate_gate(projection, gate)
        if not passed:
            raise ControllerError("GATE_FAILED", ";".join(errors))
        return direct[(projection.state, gate)]
    if gate in {"MATERIAL_CHANGE", "STOP"}:
        receipt_type = "material_change" if gate == "MATERIAL_CHANGE" else "stop"
        if not _has_current_receipt(projection, receipt_type, "gpt-pro-codex-loop"):
            raise ControllerError("GATE_FAILED", f"{gate} requires bound authority.")
        return State.STOPPED
    if projection.state != State.SEMANTIC_REVIEW:
        raise ControllerError("INVALID_TRANSITION", "Decision is not valid from the current state.")
    latest = _latest_valid_round(projection)
    if latest is None:
        raise ControllerError("GATE_FAILED", "Semantic decision requires a valid current review.")
    if gate == "CORRECTIVE":
        if latest.status != "rejected" or _must_escalate(projection):
            raise ControllerError("INVALID_TRANSITION", "Corrective decision is not permitted.")
        return State.IMPLEMENT
    if gate == "ESCALATION":
        if latest.status != "rejected" or not _must_escalate(projection):
            raise ControllerError("INVALID_TRANSITION", "Escalation decision is not required.")
        return State.ESCALATED
    if gate != "G4" or latest.status != "accepted":
        raise ControllerError("GATE_FAILED", "G4 requires an accepted current review.")
    passed, errors = evaluate_gate(projection, "G4")
    if not passed:
        raise ControllerError("GATE_FAILED", ";".join(errors))
    return State.COMPLETE


def allowed_transitions(projection: Projection) -> tuple[str, ...]:
    """Return deterministic currently permitted target states."""
    if projection.state in TERMINAL_STATES:
        return ()
    state_decisions = {
        State.INIT: ("INIT",),
        State.REQUIREMENTS: ("G1",),
        State.IMPLEMENT: ("G2",),
        State.LOCAL_VERIFY: ("G3",),
        State.SEMANTIC_REVIEW: ("CORRECTIVE", "ESCALATION", "G4"),
    }
    targets: list[str] = []
    for decision in (*state_decisions[projection.state], "STOP", "MATERIAL_CHANGE"):
        try:
            target = _transition_target(projection, decision).value
        except ControllerError:
            continue
        if target not in targets:
            targets.append(target)
    return tuple(targets)


def _json_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _projection_value(projection: Projection) -> dict[str, object]:
    value = _json_value(asdict(projection))
    assert isinstance(value, dict)
    value["state"] = projection.state.value
    return value


def _read_state(paths: store.RunPaths) -> dict[str, object]:
    try:
        raw = paths.state.read_text(encoding="utf-8")
        state = contract.strict_json_loads(raw)
    except (OSError, UnicodeError, contract.ContractError) as error:
        raise store.StoreError("RECOVERY_REQUIRED", "Persisted controller state is unreadable.") from error
    if not isinstance(state, dict):
        raise store.StoreError("RECOVERY_REQUIRED", "Persisted controller state is invalid.")
    return state


def _read_policy(paths: store.RunPaths) -> dict[str, object]:
    state = _read_state(paths)
    if not isinstance(state.get("policy"), dict):
        raise store.StoreError("RECOVERY_REQUIRED", "Persisted controller policy is missing.")
    return dict(state["policy"])


def _load_locked(paths: store.RunPaths) -> tuple[dict[str, object], list[dict[str, object]], Projection]:
    recovery = store.recovery_status(paths)
    if recovery["recovery_required"]:
        raise store.StoreError("RECOVERY_REQUIRED", "Run requires read-only recovery diagnosis.")
    policy = _read_policy(paths)
    events = store.load_events(paths)
    return policy, events, replay(policy, events)


def _state_value(
    projection: Projection,
    policy: Mapping[str, object],
    event_count: int,
    head_hash: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "execution_id": projection.execution_id,
        "state": projection.state.value,
        "event_count": event_count,
        "head_event_hash": head_hash,
        "policy": dict(policy),
        "projection": _projection_value(projection),
    }


def _event_id(seed: Mapping[str, object]) -> str:
    digest = hashlib.sha256(contract.canonical_json_bytes(seed)).hexdigest().upper()
    return "EVT-" + digest[:12]


def _generated_event(
    execution_id: str,
    sequence: int,
    previous_hash: str | None,
    event_type: str,
    payload: dict[str, object],
    *,
    subject_ids: list[str] | None = None,
    input_digest: str,
    result: str = "pass",
    issuer_skill: str = "hotl-governance",
    issuer_kind: str = "controller",
) -> dict[str, object]:
    seed = {
        "execution_id": execution_id,
        "sequence": sequence,
        "previous_event_hash": previous_hash,
        "type": event_type,
        "payload": payload,
    }
    return {
        "schema_version": 1,
        "event_id": _event_id(seed),
        "execution_id": execution_id,
        "sequence": sequence,
        "type": event_type,
        "payload": payload,
        "issuer": {"kind": issuer_kind, "id": issuer_skill, "version": "1"},
        "subject_ids": subject_ids or [],
        "artifact_refs": [],
        "result": result,
        "input_digest": input_digest,
        "output_digest": contract.canonical_digest(payload),
        "previous_event_hash": previous_hash,
        "timestamp": "1970-01-01T00:00:00Z",
    }


def _append_locked(
    paths: store.RunPaths,
    policy: Mapping[str, object],
    old_events: Sequence[dict[str, object]],
    projection: Projection,
    batch: Sequence[dict[str, object]],
    artifacts: Mapping[str, bytes],
) -> dict[str, object]:
    head = contract.canonical_digest(batch[-1])
    state = _state_value(projection, policy, len(old_events) + len(batch), head)
    store.append_events(paths, list(batch), state, artifacts)
    return {
        "execution_id": projection.execution_id,
        "state": projection.state.value,
        "event_count": len(old_events) + len(batch),
        "head_event_hash": head,
        "cycle_id": projection.cycle_id,
    }


def record_event(
    repository: Path,
    execution_id: str,
    event: Mapping[str, object],
    artifacts: Mapping[str, bytes],
) -> dict[str, object]:
    """Append evidence under one complete read/replay/build/append lock."""
    paths = store.resolve_run(repository, execution_id)
    with store.run_lock(paths.lock):
        policy, old_events, projection = _load_locked(paths)
        if projection.state in TERMINAL_STATES:
            raise ControllerError("TERMINAL_STATE", "Terminal executions cannot accept more events.")
        candidate = dict(event)
        issuer = candidate.get("issuer")
        if (
            candidate.get("type") != "evidence_recorded"
            or not isinstance(issuer, dict)
            or issuer.get("kind") != "tool"
        ):
            raise ControllerError(
                "PRIVILEGED_EVENT",
                "Generic record accepts only unprivileged tool evidence.",
            )
        projected = project_event(projection, candidate)
        return _append_locked(paths, policy, old_events, projected, [candidate], artifacts)


def activate_snapshot(
    repository: Path, execution_id: str, snapshot_digest: str
) -> dict[str, object]:
    """Activate one snapshot and invalidate all current evidence atomically."""
    if not isinstance(snapshot_digest, str) or contract.DIGEST.fullmatch(snapshot_digest) is None:
        raise ControllerError("INVALID_DIGEST", "Snapshot digest is invalid.")
    paths = store.resolve_run(repository, execution_id)
    with store.run_lock(paths.lock):
        policy, old_events, projection = _load_locked(paths)
        if projection.state in TERMINAL_STATES:
            raise ControllerError("TERMINAL_STATE", "Terminal executions cannot activate snapshots.")
        previous = contract.canonical_digest(old_events[-1])
        activation = _generated_event(
            execution_id,
            len(old_events) + 1,
            previous,
            "snapshot_activated",
            {"snapshot_digest": snapshot_digest, "cycle_id": projection.cycle_id + 1},
            input_digest=projection_evidence_set_digest(projection),
        )
        projected = project_event(projection, activation)
        batch = [activation]
        previous = contract.canonical_digest(activation)
        for evidence_id in sorted(
            key for key, value in projection.evidence_records.items() if value.status == "valid_current"
        ):
            invalidated = _generated_event(
                execution_id,
                len(old_events) + len(batch) + 1,
                previous,
                "evidence_invalidated",
                {"evidence_id": evidence_id, "cycle_id": projected.cycle_id},
                subject_ids=[evidence_id],
                input_digest=projection.evidence_records[evidence_id].artifact_digest,
            )
            projected = project_event(projected, invalidated)
            batch.append(invalidated)
            previous = contract.canonical_digest(invalidated)
        return _append_locked(paths, policy, old_events, projected, batch, {})


def commit_transition(repository: Path, execution_id: str, gate: str) -> dict[str, object]:
    """Evaluate and commit the sole normal state-advance event."""
    paths = store.resolve_run(repository, execution_id)
    with store.run_lock(paths.lock):
        policy, old_events, projection = _load_locked(paths)
        target = _transition_target(projection, gate)
        evidence_digest = projection_evidence_set_digest(projection)
        previous = contract.canonical_digest(old_events[-1])
        payload = {
            "gate": gate,
            "from_state": projection.state.value,
            "to_state": target.value,
            "evidence_set_digest": evidence_digest,
            "cycle_id": projection.cycle_id,
        }
        event = _generated_event(
            execution_id,
            len(old_events) + 1,
            previous,
            "transition_committed",
            payload,
            input_digest=evidence_digest,
        )
        projected = project_event(projection, event)
        return _append_locked(paths, policy, old_events, projected, [event], {})


def _lineage_receipt(value: Mapping[str, object], predecessor_id: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ControllerError("INVALID_LINEAGE", "Lineage receipt must be a mapping.")
    receipt = dict(value)
    expected = {"predecessor_execution_id", "lineage_receipt_digest", "supersedes"}
    if set(receipt) != expected:
        raise ControllerError("INVALID_LINEAGE", "Lineage receipt has invalid fields.")
    try:
        contract.canonical_json_bytes(receipt)
    except contract.ContractError as error:
        raise _controller_error(error) from error
    if receipt["predecessor_execution_id"] != predecessor_id:
        raise ControllerError("PREDECESSOR_MISMATCH", "Lineage predecessor does not match.")
    digest = receipt["lineage_receipt_digest"]
    if not isinstance(digest, str) or contract.DIGEST.fullmatch(digest) is None:
        raise ControllerError("INVALID_LINEAGE", "Lineage receipt digest is required.")
    supersedes = receipt["supersedes"]
    if not isinstance(supersedes, list) or not supersedes:
        raise ControllerError("INVALID_LINEAGE", "Lineage requires explicit supersedes relations.")
    seen: set[tuple[str, str]] = set()
    for relation in supersedes:
        if not isinstance(relation, dict) or set(relation) != {"new_id", "old_id"}:
            raise ControllerError("INVALID_LINEAGE", "Invalid supersedes relation.")
        new_id, old_id = relation["new_id"], relation["old_id"]
        if (
            not isinstance(new_id, str)
            or not isinstance(old_id, str)
            or not new_id.startswith("REQ-")
            or not old_id.startswith("REQ-")
            or contract.NODE_ID.fullmatch(new_id) is None
            or contract.NODE_ID.fullmatch(old_id) is None
            or new_id == old_id
            or (new_id, old_id) in seen
        ):
            raise ControllerError("INVALID_LINEAGE", "Supersedes IDs must be distinct requirements.")
        seen.add((new_id, old_id))
    return receipt


def _lineage_binding_bytes(lineage: Mapping[str, object]) -> bytes:
    return contract.canonical_json_bytes(
        {
            "predecessor_execution_id": lineage["predecessor_execution_id"],
            "supersedes": lineage["supersedes"],
        }
    )


def _verify_lineage_evidence(paths: store.RunPaths, lineage: Mapping[str, object]) -> None:
    digest = str(lineage["lineage_receipt_digest"])
    evidence = paths.evidence / digest[7:]
    try:
        metadata = evidence.lstat()
    except FileNotFoundError as error:
        raise ControllerError(
            "LINEAGE_EVIDENCE_MISSING", "Lineage receipt evidence object is missing."
        ) from error
    except OSError as error:
        raise ControllerError(
            "LINEAGE_EVIDENCE_CORRUPT", "Lineage receipt evidence cannot be inspected."
        ) from error
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    if (
        evidence.is_symlink()
        or bool(getattr(metadata, "st_file_attributes", 0) & reparse)
        or not evidence.is_file()
    ):
        raise ControllerError(
            "LINEAGE_EVIDENCE_CORRUPT", "Lineage receipt evidence is not a plain file."
        )
    try:
        content = evidence.read_bytes()
    except OSError as error:
        raise ControllerError(
            "LINEAGE_EVIDENCE_CORRUPT", "Lineage receipt evidence cannot be read."
        ) from error
    actual = "sha256:" + hashlib.sha256(content).hexdigest()
    if actual != digest or content != _lineage_binding_bytes(lineage):
        raise ControllerError(
            "LINEAGE_EVIDENCE_CORRUPT", "Lineage receipt evidence does not match its binding."
        )


def _require_material_predecessor(paths: store.RunPaths) -> None:
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    try:
        root_metadata = paths.root.lstat()
    except (FileNotFoundError, OSError) as error:
        raise ControllerError(
            "PREDECESSOR_NOT_FOUND", "Predecessor run does not exist."
        ) from error
    if (
        paths.root.is_symlink()
        or bool(getattr(root_metadata, "st_file_attributes", 0) & reparse)
        or not stat.S_ISDIR(root_metadata.st_mode)
    ):
        raise ControllerError(
            "PREDECESSOR_NOT_FOUND", "Predecessor run is not a plain directory."
        )

    for artifact in (paths.state, paths.events):
        try:
            metadata = artifact.lstat()
        except (FileNotFoundError, OSError):
            continue
        if (
            not artifact.is_symlink()
            and not bool(getattr(metadata, "st_file_attributes", 0) & reparse)
            and stat.S_ISREG(metadata.st_mode)
        ):
            return
    raise ControllerError(
        "PREDECESSOR_NOT_FOUND",
        "Predecessor run has no material state or event artifact.",
    )


def start_successor(
    repository: Path,
    predecessor_id: str,
    receipt: Mapping[str, object],
    policy: Mapping[str, object],
    requirements: Mapping[str, object],
) -> dict[str, object]:
    """Atomically create a replayable successor without mutating its predecessor."""
    predecessor_paths = store.resolve_run(repository, predecessor_id)
    lineage = _lineage_receipt(receipt, predecessor_id)
    _require_material_predecessor(predecessor_paths)
    _verify_lineage_evidence(predecessor_paths, lineage)
    execution_id = policy.get("execution_id")
    if (
        not isinstance(execution_id, str)
        or contract.EXECUTION_ID.fullmatch(execution_id) is None
        or execution_id == predecessor_id
    ):
        raise ControllerError("INVALID_EXECUTION_ID", "Successor execution ID is invalid.")
    try:
        successor_policy = _validated_base_policy(
            policy, execution_id, _SUCCESSOR_POLICY_FIELDS
        )
    except ControllerError as error:
        if error.code in {"INVALID_FIELDS", "EXECUTION_MISMATCH"}:
            raise ControllerError("INVALID_POLICY", "Successor policy fields are invalid.") from error
        raise
    if successor_policy["initial_state"] != State.INIT.value:
        raise ControllerError("INVALID_POLICY", "A successor must start in INIT.")
    requirements_value, identifiers, requirements_digest, requirement_artifacts = (
        _validated_requirements(requirements)
    )
    if successor_policy["requirements_digest"] != requirements_digest:
        raise ControllerError(
            "REQUIREMENTS_MISMATCH",
            "Successor requirements content does not match the declared digest.",
        )
    successor_policy.update(
        {
            "initial_state": State.INIT.value,
            "lineage_receipt_digest": lineage["lineage_receipt_digest"],
            "predecessor_execution_id": predecessor_id,
            "supersedes": lineage["supersedes"],
        }
    )
    successor_policy = _canonical_mapping(successor_policy)
    successor_paths = store.resolve_run(repository, execution_id)

    def publish() -> None:
        payload = {
            "receipt_id": "RCP-" + str(lineage["lineage_receipt_digest"])[7:19].upper(),
            "receipt_type": "lineage",
            "receipt_digest": lineage["lineage_receipt_digest"],
            "issuer_skill": "hotl-governance-lineage",
            "authority_snapshot_digest": None,
            "requirements_digest": None,
            "snapshot_digest": None,
            "evidence_set_digest": None,
            "cycle_id": None,
        }
        events: list[dict[str, object]] = []
        first_event = _generated_event(
            execution_id,
            1,
            None,
            "receipt_imported",
            payload,
            input_digest=str(lineage["lineage_receipt_digest"]),
        )
        events.append(first_event)
        projection = replay(successor_policy, events)
        previous = contract.canonical_digest(first_event)
        for identifier in identifiers:
            event = _generated_event(
                execution_id,
                len(events) + 1,
                previous,
                "node_declared",
                {"node_id": identifier, "node_type": "requirement"},
                subject_ids=[identifier],
                input_digest=requirements_digest,
            )
            projection = project_event(projection, event)
            events.append(event)
            previous = contract.canonical_digest(event)
        evidence_digest = projection_evidence_set_digest(projection)
        transition = _generated_event(
            execution_id,
            len(events) + 1,
            previous,
            "transition_committed",
            {
                "cycle_id": projection.cycle_id,
                "evidence_set_digest": evidence_digest,
                "from_state": State.INIT.value,
                "gate": "INIT",
                "to_state": State.REQUIREMENTS.value,
            },
            input_digest=evidence_digest,
        )
        projection = project_event(projection, transition)
        events.append(transition)
        head = contract.canonical_digest(transition)
        state = _state_value(projection, successor_policy, len(events), head)
        artifacts = {
            **requirement_artifacts,
            contract.canonical_digest(successor_policy): contract.canonical_json_bytes(
                successor_policy
            ),
        }
        store.publish_initial_events(successor_paths, state, events, artifacts)

    recovery = store.recovery_status(predecessor_paths)
    if recovery["recovery_required"]:
        publish()
    else:
        with store.run_lock(predecessor_paths.lock):
            _, _, predecessor = _load_locked(predecessor_paths)
            if predecessor.state not in TERMINAL_STATES:
                raise ControllerError(
                    "PREDECESSOR_NOT_TERMINAL", "Successor requires a terminal predecessor."
                )
            publish()
    return {
        "execution_id": execution_id,
        "predecessor_execution_id": predecessor_id,
        "state": State.REQUIREMENTS.value,
        "event_count": len(identifiers) + 2,
        "lineage_receipt_digest": lineage["lineage_receipt_digest"],
    }


_INITIAL_POLICY_FIELDS = frozenset(
    {
        "active_snapshot_digest",
        "approval_mode",
        "authority_snapshot_digest",
        "cycle_id",
        "execution_id",
        "host_approval_evidence_digest",
        "receipt_nonce",
        "schema_version",
    }
)
_SUCCESSOR_POLICY_FIELDS = _INITIAL_POLICY_FIELDS | frozenset(
    {"initial_state", "requirements_digest"}
)
_SOURCE_RECEIPT_FIELDS = frozenset(
    {
        "authority_snapshot_digest",
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
    }
)
_GPT_BINDING_FIELDS = frozenset(
    {
        "conversation_url",
        "model_label",
        "plan_label",
        "reasoning_label",
        "run_id",
        "task_slug",
    }
)
_GPT_TASK_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z")


def gpt_governance_execution_id(task_slug: str) -> str:
    """Recompute the GPT governance execution identity for the closed v1 domain."""
    if not isinstance(task_slug, str) or _GPT_TASK_SLUG.fullmatch(task_slug) is None:
        raise ControllerError("INVALID_RECEIPT_BINDING", "GPT Pro task slug is invalid.")
    identity = contract.canonical_json_bytes(
        {
            "issuer_skill": "gpt-pro-codex-loop",
            "run_id": f"gpc-loop-{task_slug}",
            "task_slug": task_slug,
        }
    )
    return "EXEC-" + hashlib.sha256(identity).hexdigest()[:12].upper()


def gpt_governance_nonce(binding: Mapping[str, object]) -> str:
    """Recompute the domain-separated GPT governance nonce for v1."""
    value = contract.canonical_json_bytes(
        {
            "binding": dict(binding),
            "purpose": "gpt-pro-governance-receipt-nonce-v1",
        }
    )
    return hashlib.sha256(value).hexdigest()[:32]


def gpt_governance_authority_digest(binding: Mapping[str, object]) -> str:
    """Recompute the GPT authority snapshot digest from its exact binding."""
    return contract.canonical_digest(dict(binding))


def _exact_mapping(value: object, fields: frozenset[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ControllerError("INVALID_FIELDS", f"{label} fields must match exactly.")
    return value


def _validated_base_policy(
    policy: Mapping[str, object], execution_id: str, fields: frozenset[str]
) -> dict[str, object]:
    supplied = _exact_mapping(dict(policy), fields, "policy")
    if supplied["schema_version"] != 1 or isinstance(supplied["schema_version"], bool):
        raise ControllerError("INVALID_POLICY", "Policy schema_version must be integer 1.")
    if supplied["execution_id"] != execution_id:
        raise ControllerError("EXECUTION_MISMATCH", "Policy execution does not match the command.")
    if not isinstance(supplied["approval_mode"], str) or supplied[
        "approval_mode"
    ] not in {"agentic", "offline_manual"}:
        raise ControllerError("INVALID_POLICY", "Policy approval_mode is invalid.")
    nonce = supplied["receipt_nonce"]
    if not isinstance(nonce, str) or contract.NONCE.fullmatch(nonce) is None:
        raise ControllerError("INVALID_NONCE", "Policy receipt_nonce is invalid.")
    for field in ("authority_snapshot_digest", "active_snapshot_digest"):
        value = supplied[field]
        if not isinstance(value, str) or contract.DIGEST.fullmatch(value) is None:
            raise ControllerError("INVALID_DIGEST", f"Policy {field} is invalid.")
    cycle_id = supplied["cycle_id"]
    if not isinstance(cycle_id, int) or isinstance(cycle_id, bool) or cycle_id < 1:
        raise ControllerError("INVALID_CYCLE", "Initial cycle_id must be a positive integer.")
    host_digest = supplied["host_approval_evidence_digest"]
    if host_digest is not None and (
        not isinstance(host_digest, str) or contract.DIGEST.fullmatch(host_digest) is None
    ):
        raise ControllerError("INVALID_DIGEST", "Host approval evidence digest is invalid.")
    return supplied


def _validated_requirements(
    requirements: Mapping[str, object],
) -> tuple[dict[str, object], list[str], str, dict[str, bytes]]:
    requirements_value = dict(requirements)
    fields = frozenset(requirements_value)
    legacy_fields = frozenset({"requirements"})
    external_fields = frozenset(
        {"requirements", "source_artifact", "source_digest"}
    )
    if fields not in {legacy_fields, external_fields}:
        raise ControllerError(
            "INVALID_FIELDS", "requirements fields must match a closed schema."
        )
    identifiers = requirements_value["requirements"]
    if not isinstance(identifiers, list) or not identifiers:
        raise ControllerError("INVALID_REQUIREMENTS", "At least one requirement is required.")
    if any(
        not isinstance(identifier, str)
        or not identifier.startswith("REQ-")
        or contract.NODE_ID.fullmatch(identifier) is None
        for identifier in identifiers
    ) or identifiers != sorted(set(identifiers)):
        raise ControllerError(
            "INVALID_REQUIREMENTS", "Requirement IDs must be unique and canonically sorted."
        )
    identifier_manifest = {"requirements": identifiers}
    identifier_bytes = contract.canonical_json_bytes(identifier_manifest)
    identifier_digest = "sha256:" + hashlib.sha256(identifier_bytes).hexdigest()
    if fields == legacy_fields:
        return identifier_manifest, identifiers, identifier_digest, {
            identifier_digest: identifier_bytes
        }
    source_digest = requirements_value["source_digest"]
    if not isinstance(source_digest, str) or contract.DIGEST.fullmatch(source_digest) is None:
        raise ControllerError(
            "INVALID_DIGEST", "External requirements source_digest is invalid."
        )
    try:
        source_bytes = contract.canonical_json_bytes(requirements_value["source_artifact"])
    except contract.ContractError as error:
        raise ControllerError(
            "INVALID_REQUIREMENTS", "External requirements artifact is not canonical JSON."
        ) from error
    actual_digest = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    if actual_digest != source_digest:
        raise ControllerError(
            "DIGEST_MISMATCH", "External requirements artifact does not match source_digest."
        )
    source_artifact = requirements_value["source_artifact"]
    source_items = (
        source_artifact.get("requirements")
        if isinstance(source_artifact, dict)
        else None
    )
    if not isinstance(source_items, list) or not source_items:
        raise ControllerError(
            "INVALID_REQUIREMENTS",
            "External GPT requirements artifact requires typed requirement items.",
        )
    source_identifiers: list[str] = []
    for item in source_items:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "statement"}
            or not isinstance(item.get("id"), str)
            or contract.NODE_ID.fullmatch(item["id"]) is None
            or not item["id"].startswith("REQ-")
            or not isinstance(item.get("statement"), str)
            or not item["statement"].strip()
        ):
            raise ControllerError(
                "INVALID_REQUIREMENTS",
                "External GPT requirement items must be exact nonempty id/statement objects.",
            )
        source_identifiers.append(item["id"])
    if (
        source_identifiers != sorted(set(source_identifiers))
        or source_identifiers != identifiers
    ):
        raise ControllerError(
            "INVALID_REQUIREMENTS",
            "External GPT requirement IDs do not match the typed ID manifest.",
        )
    return requirements_value, identifiers, source_digest, {
        identifier_digest: identifier_bytes,
        source_digest: source_bytes,
    }


def initialize_execution(
    repository: Path,
    execution_id: str,
    policy: Mapping[str, object],
    requirements: Mapping[str, object],
) -> dict[str, object]:
    """Atomically publish requirements and the explicit INIT lifecycle transition."""
    supplied = _validated_base_policy(policy, execution_id, _INITIAL_POLICY_FIELDS)
    requirements_value, identifiers, requirements_digest, requirement_artifacts = (
        _validated_requirements(requirements)
    )
    normalized_policy = dict(supplied)
    normalized_policy.update(
        {
            "initial_state": State.INIT.value,
            "requirements_digest": requirements_digest,
        }
    )
    normalized_policy = _canonical_mapping(normalized_policy)
    events: list[dict[str, object]] = []
    projection = replay(normalized_policy, [])
    previous: str | None = None
    for identifier in identifiers:
        event = _generated_event(
            execution_id,
            len(events) + 1,
            previous,
            "node_declared",
            {"node_id": identifier, "node_type": "requirement"},
            subject_ids=[identifier],
            input_digest=requirements_digest,
        )
        projection = project_event(projection, event)
        events.append(event)
        previous = contract.canonical_digest(event)
    evidence_digest = projection_evidence_set_digest(projection)
    transition = _generated_event(
        execution_id,
        len(events) + 1,
        previous,
        "transition_committed",
        {
            "cycle_id": projection.cycle_id,
            "evidence_set_digest": evidence_digest,
            "from_state": State.INIT.value,
            "gate": "INIT",
            "to_state": State.REQUIREMENTS.value,
        },
        input_digest=evidence_digest,
    )
    projection = project_event(projection, transition)
    events.append(transition)
    head = contract.canonical_digest(transition)
    state = _state_value(projection, normalized_policy, len(events), head)
    artifacts = {
        **requirement_artifacts,
        contract.canonical_digest(normalized_policy): contract.canonical_json_bytes(
            normalized_policy
        ),
    }
    paths = store.resolve_run(repository, execution_id)
    store.publish_initial_events(paths, state, events, artifacts)
    return {
        "cycle_id": projection.cycle_id,
        "event_count": len(events),
        "execution_id": execution_id,
        "head_event_hash": head,
        "state": projection.state.value,
    }


def project_execution(repository: Path, execution_id: str) -> dict[str, object]:
    """Return a read-only projection reconstructed from the event log."""
    paths = store.resolve_run(repository, execution_id)
    recovery = store.recovery_status(paths)
    if recovery["recovery_required"]:
        raise store.StoreError("RECOVERY_REQUIRED", "Run requires read-only diagnosis.")
    policy = _read_policy(paths)
    events = store.load_events(paths)
    return {
        "event_count": len(events),
        "projection": _projection_value(replay(policy, events)),
    }


def _canonical_source_receipt(raw: bytes) -> dict[str, object]:
    if not isinstance(raw, bytes):
        raise ControllerError("INVALID_RECEIPT", "Receipt source must be bytes.")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = contract.strict_json_loads(text)
    except (UnicodeError, contract.ContractError) as error:
        if isinstance(error, contract.ContractError):
            raise _controller_error(error) from error
        raise ControllerError("INVALID_JSON", "Receipt source must be UTF-8 JSON.") from error
    if not isinstance(value, dict) or contract.canonical_json_bytes(value) != raw:
        raise ControllerError("NONCANONICAL_JSON", "Receipt source must use canonical JSON.")
    identity = {"transaction_id", "invocation_id"} & set(value)
    if len(identity) != 1:
        raise ControllerError(
            "INVALID_RECEIPT_IDENTITY", "Receipt requires one transaction or invocation ID."
        )
    optional_binding = {"binding"} if "binding" in value else set()
    return _exact_mapping(
        value, _SOURCE_RECEIPT_FIELDS | identity | optional_binding, "source receipt"
    )


def _validate_gpt_binding(
    source: Mapping[str, object], *, recompute_governance_identity: bool
) -> None:
    binding = source.get("binding")
    if not isinstance(binding, dict):
        raise ControllerError(
            "INVALID_RECEIPT_BINDING", "GPT Pro receipt requires a provenance binding."
        )
    _exact_mapping(binding, _GPT_BINDING_FIELDS, "GPT Pro receipt binding")
    task_slug = binding.get("task_slug")
    run_id = binding.get("run_id")
    if (
        not isinstance(task_slug, str)
        or _GPT_TASK_SLUG.fullmatch(task_slug) is None
        or run_id != f"gpc-loop-{task_slug}"
    ):
        raise ControllerError(
            "INVALID_RECEIPT_BINDING", "GPT Pro receipt run/task binding is invalid."
        )
    conversation_url = binding.get("conversation_url")
    parsed = urlparse(conversation_url) if isinstance(conversation_url, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or parsed.netloc != "chatgpt.com"
        or not parsed.path.startswith("/c/")
        or parsed.path == "/c/"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
    ):
        raise ControllerError(
            "INVALID_RECEIPT_BINDING", "GPT Pro conversation binding is invalid."
        )
    model = binding.get("model_label")
    reasoning = binding.get("reasoning_label")
    plan = binding.get("plan_label")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (model, reasoning, plan)
    ):
        raise ControllerError(
            "INVALID_RECEIPT_BINDING",
            "GPT Pro model, reasoning, and plan bindings must be nonempty.",
        )
    if model == "GPT-5.6 Sol" and (
        reasoning != "Pro" or plan not in {"Pro", "Business", "Enterprise"}
    ):
        raise ControllerError(
            "INVALID_RECEIPT_BINDING", "GPT Pro model attestation is not canonical."
        )
    expected_execution = gpt_governance_execution_id(task_slug)
    expected_nonce = gpt_governance_nonce(binding)
    expected_authority = gpt_governance_authority_digest(binding)
    if source.get("authority_snapshot_digest") != expected_authority or (
        recompute_governance_identity
        and (
            source.get("execution_id") != expected_execution
            or source.get("nonce") != expected_nonce
        )
    ):
        raise ControllerError(
            "GPT_IDENTITY_MISMATCH",
            "GPT Pro identity does not match its deterministic provenance binding.",
        )


def _validate_claim_edges(claims: dict[str, object], fields: frozenset[str]) -> None:
    _exact_mapping(claims, fields, "receipt claims")
    edges = claims.get("edges", [])
    if not isinstance(edges, list):
        raise ControllerError("INVALID_RECEIPT", "Receipt edges must be a list.")
    for edge in edges:
        _exact_mapping(
            edge,
            frozenset({"edge", "source_id", "target_id"}),
            "receipt edge",
        )


def _validate_source_receipt(
    source: dict[str, object],
    raw: bytes,
    policy: Mapping[str, object],
    projection: Projection,
    expected_type: str | None,
) -> tuple[str, dict[str, object]]:
    receipt_type = source.get("receipt_type")
    if not isinstance(receipt_type, str):
        raise ControllerError("INVALID_SCHEMA", "Receipt type must be a string.")
    if receipt_type not in contract.RECEIPT_TYPE_ISSUERS:
        raise ControllerError("UNKNOWN_RECEIPT_TYPE", "Receipt type is not supported.")
    if receipt_type == "lineage":
        raise ControllerError("INVALID_RECEIPT_TYPE", "Lineage uses start-successor.")
    if expected_type is not None and receipt_type != expected_type:
        raise ControllerError("RECEIPT_TYPE_MISMATCH", "Receipt type does not match the command.")
    issuer = source.get("issuer_skill")
    if not isinstance(issuer, str):
        raise ControllerError("INVALID_SCHEMA", "Receipt issuer must be a string.")
    allowed = contract.RECEIPT_TYPE_ISSUERS[receipt_type]
    if issuer not in allowed:
        raise ControllerError("ISSUER_MISMATCH", "Receipt issuer is not allowed for its type.")
    if issuer == "gpt-pro-codex-loop":
        _validate_gpt_binding(
            source,
            recompute_governance_identity=receipt_type
            in {"requirements", "semantic_review", "final"},
        )
    elif "binding" in source:
        raise ControllerError(
            "INVALID_RECEIPT_BINDING",
            "Receipt binding is not defined for this issuer.",
        )
    base_fields = contract.RECEIPT_BASE_FIELDS | (
        {"transaction_id"} if "transaction_id" in source else {"invocation_id"}
    )
    base = {field: source[field] for field in base_fields}
    try:
        contract.validate_receipt(
            base,
            issuer,
            projection.execution_id,
            projection.authority_snapshot_digest,
        )
    except contract.ContractError as error:
        raise _controller_error(error) from error
    if source["issuer_version"] != "1":
        raise ControllerError(
            "ISSUER_VERSION_MISMATCH", "Receipt issuer version is not supported."
        )
    if source["nonce"] != policy.get("receipt_nonce"):
        raise ControllerError("NONCE_MISMATCH", "Receipt nonce is not bound to this execution.")
    if source["requirements_digest"] != projection.requirements_digest:
        raise ControllerError(
            "REQUIREMENTS_MISMATCH", "Receipt requirements binding is stale."
        )
    frozen = receipt_type in {"requirements", "approval"}
    current_digest = projection_evidence_set_digest(projection)
    gpt_external = issuer == "gpt-pro-codex-loop" and receipt_type in {
        "requirements",
        "semantic_review",
        "final",
    }
    if gpt_external and receipt_type == "requirements":
        if any(
            source[field] is not None
            for field in ("snapshot_digest", "evidence_set_digest", "cycle_id")
        ):
            raise ControllerError(
                "INVALID_RECEIPT_BINDING",
                "GPT Pro requirements receipt has live HOTL bindings.",
            )
    elif gpt_external:
        if (
            source["snapshot_digest"] != projection.active_snapshot_digest
            or source["evidence_set_digest"] is not None
            or source["cycle_id"] is not None
        ):
            raise ControllerError(
                "STALE_RECEIPT", "GPT Pro receipt snapshot binding is stale."
            )
    elif frozen:
        if any(source[field] is not None for field in ("snapshot_digest", "evidence_set_digest", "cycle_id")):
            raise ControllerError("INVALID_RECEIPT_BINDING", "Frozen receipt has live bindings.")
        if source["input_digest"] != projection.requirements_digest:
            raise ControllerError("DIGEST_MISMATCH", "Frozen receipt target digest is wrong.")
    elif (
        not _snapshot_binding_is_current(
            receipt_type,
            source["snapshot_digest"],
            projection.active_snapshot_digest,
        )
        or source["evidence_set_digest"] != current_digest
        or source["cycle_id"] != projection.cycle_id
        or source["input_digest"] != current_digest
    ):
        raise ControllerError("STALE_RECEIPT", "Receipt live bindings are stale.")
    claims = source["claims"]
    if not isinstance(claims, dict):
        raise ControllerError("INVALID_RECEIPT", "Receipt claims must be an object.")
    if receipt_type in {"requirements", "final", "material_change", "stop"}:
        _exact_mapping(claims, frozenset(), "receipt claims")
    elif receipt_type == "approval":
        if issuer == "gpt-pro-codex-loop":
            _exact_mapping(claims, frozenset(), "approval claims")
        elif issuer == "trusted-local-operator":
            _exact_mapping(claims, frozenset({"approval_mode"}), "approval claims")
            if (
                claims["approval_mode"] != "offline_manual"
                or policy.get("approval_mode") != "offline_manual"
            ):
                raise ControllerError(
                    "UNTRUSTED_LOCAL_APPROVAL",
                    "Trusted local approval requires frozen offline_manual mode.",
                )
        else:
            _exact_mapping(
                claims, frozenset({"approval_evidence"}), "approval claims"
            )
            evidence = _exact_mapping(
                claims["approval_evidence"],
                frozenset(
                    {
                        "approval_schema_version",
                        "authority_snapshot_digest",
                        "decision",
                        "execution_id",
                        "host_id",
                        "target_digest",
                    }
                ),
                "host approval evidence",
            )
            expected = policy.get("host_approval_evidence_digest")
            if (
                evidence["approval_schema_version"] != 1
                or not isinstance(evidence["host_id"], str)
                or not evidence["host_id"]
                or evidence["decision"] != "approve"
                or evidence["execution_id"] != projection.execution_id
                or evidence["authority_snapshot_digest"]
                != projection.authority_snapshot_digest
                or evidence["target_digest"] != projection.requirements_digest
                or expected is None
                or contract.canonical_digest(evidence) != expected
            ):
                if not isinstance(evidence["host_id"], str) or not evidence["host_id"]:
                    raise ControllerError(
                        "INVALID_HOST_APPROVAL", "Host approval identity is invalid."
                    )
                raise ControllerError(
                    "HOST_APPROVAL_MISMATCH", "Host approval is not bound to the frozen target."
                )
    elif receipt_type == "implementation":
        _validate_claim_edges(claims, frozenset({"edges", "nodes"}))
        nodes = claims["nodes"]
        if not isinstance(nodes, list):
            raise ControllerError("INVALID_RECEIPT", "Implementation nodes must be a list.")
        for node in nodes:
            _exact_mapping(node, frozenset({"node_id", "node_type"}), "receipt node")
    elif receipt_type == "verification":
        _validate_claim_edges(claims, frozenset({"edges"}))
    else:
        _validate_claim_edges(
            claims,
            frozenset(
                {"edges", "findings", "review_id", "root_cause_ids", "status"}
            ),
        )
        if not isinstance(claims["status"], str) or claims["status"] not in {
            "accepted",
            "rejected",
        }:
            raise ControllerError("INVALID_REVIEW", "Review status is invalid.")
        roots = claims["root_cause_ids"]
        findings = claims["findings"]
        if not isinstance(roots, list) or not isinstance(findings, list):
            raise ControllerError("INVALID_REVIEW", "Review roots and findings must be lists.")
        if any(
            not isinstance(root, str) or contract.STABLE_ID.fullmatch(root) is None
            for root in roots
        ):
            raise ControllerError("INVALID_REVIEW", "Review roots are invalid.")
        if roots != sorted(set(roots)) or (
            claims["status"] == "accepted" and (roots or findings)
        ) or (claims["status"] == "rejected" and not roots):
            raise ControllerError("INVALID_REVIEW", "Review roots do not match its status.")
        for finding in findings:
            validated_finding = _exact_mapping(
                finding,
                frozenset({"finding_id", "root_cause_id", "status"}),
                "review finding",
            )
            if (
                not isinstance(validated_finding["finding_id"], str)
                or contract.STABLE_ID.fullmatch(validated_finding["finding_id"])
                is None
                or not isinstance(validated_finding["root_cause_id"], str)
                or contract.STABLE_ID.fullmatch(
                    validated_finding["root_cause_id"]
                )
                is None
                or not isinstance(validated_finding["status"], str)
                or validated_finding["status"] not in {"open", "resolved"}
            ):
                raise ControllerError("INVALID_REVIEW", "Review finding is invalid.")
        if claims["status"] == "rejected" and sorted(
            {finding["root_cause_id"] for finding in findings}
        ) != roots:
            raise ControllerError("INVALID_REVIEW", "Findings do not match committed roots.")
    return "sha256:" + hashlib.sha256(raw).hexdigest(), claims


def _admitted_receipt_events(
    projection: Projection,
    old_events: Sequence[dict[str, object]],
    source: Mapping[str, object],
    receipt_digest: str,
    claims: Mapping[str, object],
) -> tuple[list[dict[str, object]], Projection]:
    batch: list[dict[str, object]] = []
    previous = contract.canonical_digest(old_events[-1])

    def add(
        event_type: str,
        payload: dict[str, object],
        *,
        subjects: list[str] | None = None,
        input_digest: str,
        result: str = "pass",
        issuer_kind: str = "controller",
        issuer_skill: str = "hotl-governance",
    ) -> None:
        nonlocal previous, projection
        event = _generated_event(
            projection.execution_id,
            len(old_events) + len(batch) + 1,
            previous,
            event_type,
            payload,
            subject_ids=subjects,
            input_digest=input_digest,
            result=result,
            issuer_kind=issuer_kind,
            issuer_skill=issuer_skill,
        )
        projection = project_event(projection, event)
        batch.append(event)
        previous = contract.canonical_digest(event)

    receipt_type = str(source["receipt_type"])
    bind_live_on_admission = (
        source["issuer_skill"] == "gpt-pro-codex-loop"
        and receipt_type in {"semantic_review", "final"}
    )
    admitted_evidence_digest = (
        projection_evidence_set_digest(projection)
        if bind_live_on_admission
        else source["evidence_set_digest"]
    )
    admitted_cycle_id = (
        projection.cycle_id if bind_live_on_admission else source["cycle_id"]
    )
    add(
        "receipt_imported",
        {
            "authority_snapshot_digest": source["authority_snapshot_digest"],
            "cycle_id": admitted_cycle_id,
            "evidence_set_digest": admitted_evidence_digest,
            "issuer_skill": source["issuer_skill"],
            "receipt_digest": receipt_digest,
            "receipt_id": source["receipt_id"],
            "receipt_type": receipt_type,
            "requirements_digest": source["requirements_digest"],
            "snapshot_digest": source["snapshot_digest"],
        },
        input_digest=receipt_digest,
    )
    if receipt_type == "implementation":
        for node in claims["nodes"]:  # type: ignore[index]
            add(
                "node_declared",
                dict(node),
                subjects=[str(node["node_id"])],  # type: ignore[index]
                input_digest=receipt_digest,
            )
    if receipt_type == "semantic_review":
        review_id = str(claims["review_id"])
        add(
            "node_declared",
            {"node_id": review_id, "node_type": "review"},
            subjects=[review_id],
            input_digest=receipt_digest,
        )
        add(
            "review_recorded",
            {
                "cycle_id": admitted_cycle_id,
                "evidence_set_digest": admitted_evidence_digest,
                "receipt_id": source["receipt_id"],
                "review_id": review_id,
                "root_cause_ids": claims["root_cause_ids"],
                "status": claims["status"],
            },
            subjects=[review_id],
            input_digest=str(admitted_evidence_digest),
            result="pass" if claims["status"] == "accepted" else "fail",
            issuer_kind="skill",
            issuer_skill=str(source["issuer_skill"]),
        )
        for finding in claims["findings"]:  # type: ignore[index]
            add(
                "finding_recorded",
                dict(finding) | {"review_id": review_id},
                subjects=[review_id],
                input_digest=receipt_digest,
                result="pass" if finding["status"] == "resolved" else "fail",  # type: ignore[index]
                issuer_kind="skill",
                issuer_skill=str(source["issuer_skill"]),
            )
    if receipt_type in {"implementation", "verification", "semantic_review"}:
        for edge in claims["edges"]:  # type: ignore[index]
            add(
                "edge_declared",
                dict(edge),
                subjects=[str(edge["source_id"]), str(edge["target_id"])],  # type: ignore[index]
                input_digest=receipt_digest,
            )
    return batch, projection


def _import_receipt_boundary(
    repository: Path,
    execution_id: str,
    source_bytes: bytes,
    *,
    expected_type: str | None = None,
    approval_command: bool = False,
) -> dict[str, object]:
    paths = store.resolve_run(repository, execution_id)
    with store.run_lock(paths.lock):
        policy, old_events, projection = _load_locked(paths)
        source = _canonical_source_receipt(source_bytes)
        if approval_command and source.get("issuer_skill") == "gpt-pro-codex-loop":
            raise ControllerError(
                "APPROVAL_EVIDENCE_REQUIRED",
                "approve accepts host evidence or explicit offline manual authority; use import-receipt for GPT Pro receipts.",
            )
        receipt_digest, claims = _validate_source_receipt(
            source, source_bytes, policy, projection, expected_type
        )
        if any(
            record.receipt_id == source["receipt_id"]
            or record.receipt_digest == receipt_digest
            for record in projection.receipt_records.values()
        ):
            raise ControllerError("REPLAYED_RECEIPT", "Receipt was already imported.")
        batch, projected = _admitted_receipt_events(
            projection, old_events, source, receipt_digest, claims
        )
        return _append_locked(
            paths,
            policy,
            old_events,
            projected,
            batch,
            {receipt_digest: source_bytes},
        )


def import_receipt(
    repository: Path,
    execution_id: str,
    source_bytes: bytes,
    *,
    expected_type: str | None = None,
) -> dict[str, object]:
    """Validate one closed issuer source and atomically append its admitted batch."""
    return _import_receipt_boundary(
        repository,
        execution_id,
        source_bytes,
        expected_type=expected_type,
    )


def approve_execution(
    repository: Path, execution_id: str, source_bytes: bytes
) -> dict[str, object]:
    """Admit only host-bound or explicitly policy-bound offline approval evidence."""
    return _import_receipt_boundary(
        repository,
        execution_id,
        source_bytes,
        expected_type="approval",
        approval_command=True,
    )


def verify_execution(repository: Path, execution_id: str) -> dict[str, object]:
    """Return separated read-only integrity and historical-observation findings."""
    paths = store.resolve_run(repository, execution_id)
    recovery = store.recovery_status(paths)
    report: dict[str, object] = {
        "current_snapshot_findings": [],
        "current_snapshot_integrity": False,
        "historical_observation_findings": [],
        "historical_observations_checked": 0,
        "immutable_evidence_findings": [],
        "immutable_evidence_integrity": False,
        "log_findings": list(recovery["reasons"]),
        "log_integrity": not recovery["recovery_required"],
        "persisted_projection_integrity": False,
        "persisted_projection_findings": [],
        "projection_determinism": False,
        "projection_findings": [],
        "projection_replay_determinism": False,
    }
    if recovery["recovery_required"]:
        return report
    persisted_state = _read_state(paths)
    policy_value = persisted_state.get("policy")
    if not isinstance(policy_value, dict):
        raise store.StoreError("RECOVERY_REQUIRED", "Persisted controller policy is missing.")
    policy = dict(policy_value)
    events = store.load_events(paths)
    left = replay(policy, events)
    right = replay(policy, events)
    deterministic = contract.canonical_json_bytes(_projection_value(left)) == contract.canonical_json_bytes(
        _projection_value(right)
    )
    report["projection_replay_determinism"] = deterministic
    persisted_matches = False
    try:
        persisted_matches = contract.canonical_json_bytes(
            persisted_state.get("projection")
        ) == contract.canonical_json_bytes(_projection_value(left))
    except contract.ContractError:
        persisted_matches = False
    report["persisted_projection_integrity"] = persisted_matches
    if not persisted_matches:
        report["persisted_projection_findings"] = ["PERSISTED_PROJECTION_MISMATCH"]
    report["projection_determinism"] = deterministic and persisted_matches
    projection_findings: list[str] = []
    if not deterministic:
        projection_findings.append("PROJECTION_REPLAY_MISMATCH")
    if not persisted_matches:
        projection_findings.append("PERSISTED_PROJECTION_MISMATCH")
    report["projection_findings"] = projection_findings
    immutable_findings: list[str] = []
    try:
        evidence_objects = sorted(paths.evidence.iterdir(), key=lambda path: path.name)
    except OSError:
        evidence_objects = []
        immutable_findings.append("EVIDENCE_ROOT_UNREADABLE")
    for evidence_object in evidence_objects:
        try:
            content = evidence_object.read_bytes()
        except OSError:
            immutable_findings.append(evidence_object.name + ":UNREADABLE")
            continue
        if hashlib.sha256(content).hexdigest() != evidence_object.name:
            immutable_findings.append(evidence_object.name + ":DIGEST_MISMATCH")
    referenced_digests = {
        record.receipt_digest for record in left.receipt_records.values()
    }
    referenced_digests.add(left.requirements_digest)
    referenced_digests.add(contract.canonical_digest(policy))
    referenced_digests.update(
        str(ref["sha256"])
        for event in events
        for ref in event["artifact_refs"]
    )
    for digest in sorted(referenced_digests):
        if not (paths.evidence / digest[7:]).is_file():
            immutable_findings.append(digest + ":MISSING")
    report["immutable_evidence_findings"] = immutable_findings
    report["immutable_evidence_integrity"] = not immutable_findings
    current_findings: list[str] = []
    historical = 0
    for event in events:
        if event["type"] != "evidence_recorded":
            continue
        payload = event["payload"]
        assert isinstance(payload, dict)
        record = left.evidence_records.get(str(payload["evidence_id"]))
        if record is None or record.status != "valid_current":
            historical += len(event["artifact_refs"])
            continue
        for ref in event["artifact_refs"]:
            try:
                content = store.read_repository_artifact(repository, ref["path"])
            except (store.StoreError, TypeError):
                current_findings.append(str(ref["path"]) + ":UNREADABLE")
                continue
            if "sha256:" + hashlib.sha256(content).hexdigest() != ref["sha256"]:
                current_findings.append(str(ref["path"]) + ":DIGEST_MISMATCH")
    report["historical_observations_checked"] = historical
    report["current_snapshot_findings"] = current_findings
    report["current_snapshot_integrity"] = not current_findings
    return report


def status_execution(repository: Path, execution_id: str) -> dict[str, object]:
    """Return deterministic status, or a read-only recovery hard stop."""
    paths = store.resolve_run(repository, execution_id)
    recovery = store.recovery_status(paths)
    if recovery["recovery_required"]:
        return {
            "execution_id": execution_id,
            "state": State.RECOVERY_REQUIRED.value,
            "event_count": 0,
            "cycle_id": 0,
            "allowed_transitions": [],
            "recovery": recovery,
        }
    policy = _read_policy(paths)
    events = store.load_events(paths)
    projection = replay(policy, events)
    return {
        "execution_id": execution_id,
        "state": projection.state.value,
        "event_count": len(events),
        "cycle_id": projection.cycle_id,
        "active_snapshot_digest": projection.active_snapshot_digest,
        "allowed_transitions": list(allowed_transitions(projection)),
        "completion_errors": list(completion_errors(projection)),
        "approval_mode": projection.approval_mode,
        "host_approval_configured": policy.get("host_approval_evidence_digest")
        is not None,
        "recovery": recovery,
    }
