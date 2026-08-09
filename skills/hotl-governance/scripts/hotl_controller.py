"""Deterministic HOTL replay, gate evaluation, and execution lifecycle."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

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
class Projection:
    execution_id: str
    state: State
    active_snapshot_digest: str | None
    nodes: Mapping[str, NodeRecord]
    edges: tuple[tuple[str, str, str], ...]
    evidence_records: Mapping[str, EvidenceRecord]
    review_records: Mapping[str, ReviewRecord]
    gate_evidence: Mapping[str, tuple[str, ...]]
    finding_state: Mapping[str, FindingRecord]
    valid_review_rounds: tuple[ReviewRound, ...]
    cycle_id: int
    requirements_digest: str


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
    gate_evidence: Mapping[str, Sequence[str]] | None = None,
    finding_state: Mapping[str, FindingRecord] | None = None,
    valid_review_rounds: Sequence[ReviewRound] = (),
    cycle_id: int = 0,
    requirements_digest: str | None = None,
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
        gate_evidence=normalized_gate_evidence,
        finding_state=dict(sorted((finding_state or {}).items())),
        valid_review_rounds=tuple(valid_review_rounds),
        cycle_id=cycle_id,
        requirements_digest=requirements_digest,
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
    return (
        projection.state == State.SEMANTIC_REVIEW
        and payload["cycle_id"] == projection.cycle_id
        and payload["evidence_set_digest"] == expected
        and event["input_digest"] == expected
    )


def project_event(projection: Projection, event: Mapping[str, object]) -> Projection:
    """Project one validated event; only a committed transition may change state."""
    candidate = _validated_event(event)
    if candidate["execution_id"] != projection.execution_id:
        raise ControllerError("EXECUTION_MISMATCH", "Event execution does not match projection.")
    event_type = candidate["type"]
    payload = candidate["payload"]
    assert isinstance(payload, dict)

    if projection.state in TERMINAL_STATES and event_type == "transition_committed":
        raise ControllerError("TERMINAL_STATE", "Terminal executions cannot transition.")

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
        if review_id not in projection.nodes:
            raise ControllerError("UNKNOWN_NODE", "Reviews must reference a declared review node.")
        if review_id in projection.review_records:
            raise ControllerError("DUPLICATE_REVIEW", "Review IDs are immutable and unique.")
        valid = _review_is_current(projection, candidate)
        review = ReviewRecord(
            review_id=review_id,
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
            rounds = (*rounds, ReviewRound(review_id, review.status, (), review.cycle_id))
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
        rounds = list(projection.valid_review_rounds)
        if review.valid:
            for index, round_record in enumerate(rounds):
                if round_record.review_id == review_id:
                    roots = tuple(sorted(set((*round_record.root_cause_ids, str(payload["root_cause_id"])))))
                    rounds[index] = replace(round_record, root_cause_ids=roots)
                    break
        return _copy_projection(
            projection,
            finding_state=dict(sorted(findings.items())),
            valid_review_rounds=tuple(rounds),
        )

    if event_type == "receipt_imported":
        gate_evidence = {gate: tuple(values) for gate, values in projection.gate_evidence.items()}
        digest = str(payload["receipt_digest"])
        issuer = str(payload["issuer_skill"])
        gates = {
            "gpt-pro-codex-loop": ("G1", "G4"),
            "codex": ("G2",),
            "hotl-local-verifier": ("G3",),
        }.get(issuer, ())
        for gate in gates:
            gate_evidence[gate] = tuple(sorted(set((*gate_evidence.get(gate, ()), digest))))
        return _copy_projection(projection, gate_evidence=dict(sorted(gate_evidence.items())))

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
        errors = () if projection.gate_evidence.get("G1") else ("G1:missing_requirements_receipt",)
    elif gate == "G2":
        requirements = _active_nodes(projection, "requirement")
        codes = _active_nodes(projection, "code")
        linked = all(
            any(_has_edge(projection, code, "implements", requirement) for code in codes)
            for requirement in requirements
        )
        errors = () if requirements and linked else ("G2:missing_implementation_links",)
    elif gate == "G3":
        current = [
            record
            for record in projection.evidence_records.values()
            if record.status == "valid_current"
            and record.cycle_id == projection.cycle_id
            and record.snapshot_digest == projection.active_snapshot_digest
        ]
        errors = () if current else ("G3:missing_current_evidence",)
    else:
        errors = completion_errors(projection)
    return not errors, errors


def _latest_valid_round(projection: Projection) -> ReviewRound | None:
    return projection.valid_review_rounds[-1] if projection.valid_review_rounds else None


def _transition_target(projection: Projection, gate: str) -> State:
    if projection.state in TERMINAL_STATES:
        raise ControllerError("TERMINAL_STATE", "Terminal executions cannot transition.")
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
    if projection.state != State.SEMANTIC_REVIEW or gate != "G4":
        raise ControllerError("INVALID_TRANSITION", "Gate is not valid from the current state.")
    latest = _latest_valid_round(projection)
    if latest is None:
        raise ControllerError("GATE_FAILED", "G4 requires a valid current semantic review.")
    if latest.status == "rejected":
        return State.ESCALATED if _must_escalate(projection) else State.IMPLEMENT
    passed, errors = evaluate_gate(projection, gate)
    if not passed:
        raise ControllerError("GATE_FAILED", ";".join(errors))
    return State.COMPLETE


def allowed_transitions(projection: Projection) -> tuple[str, ...]:
    """Return deterministic currently permitted target states."""
    if projection.state in TERMINAL_STATES:
        return ()
    if projection.state == State.INIT:
        return (State.REQUIREMENTS.value,)
    gate = {
        State.REQUIREMENTS: "G1",
        State.IMPLEMENT: "G2",
        State.LOCAL_VERIFY: "G3",
        State.SEMANTIC_REVIEW: "G4",
    }[projection.state]
    try:
        return (_transition_target(projection, gate).value,)
    except ControllerError:
        return ()


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


def _read_policy(paths: store.RunPaths) -> dict[str, object]:
    try:
        raw = paths.state.read_text(encoding="utf-8")
        state = contract.strict_json_loads(raw)
    except (OSError, UnicodeError, contract.ContractError) as error:
        raise store.StoreError("RECOVERY_REQUIRED", "Persisted controller state is unreadable.") from error
    if not isinstance(state, dict) or not isinstance(state.get("policy"), dict):
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
        "issuer": {"kind": "controller", "id": issuer_skill, "version": "1"},
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
        if candidate.get("type") == "transition_committed":
            raise ControllerError("TRANSITION_REQUIRES_EVALUATE", "Use commit_transition for state changes.")
        projected = project_event(projection, candidate)
        if candidate.get("type") == "review_recorded":
            review_id = candidate.get("payload", {}).get("review_id") if isinstance(candidate.get("payload"), dict) else None
            review = projected.review_records.get(str(review_id))
            if review is None or not review.valid:
                raise ControllerError("STALE_REVIEW_BINDING", "Review is not bound to current evidence.")
        batch = [candidate]
        if candidate.get("type") == "snapshot_activated":
            previous = contract.canonical_digest(candidate)
            sequence = int(candidate["sequence"])
            for evidence_id in sorted(
                key for key, value in projection.evidence_records.items() if value.status == "valid_current"
            ):
                sequence += 1
                invalidated = _generated_event(
                    execution_id,
                    sequence,
                    previous,
                    "evidence_invalidated",
                    {"evidence_id": evidence_id, "cycle_id": projected.cycle_id},
                    subject_ids=[evidence_id],
                    input_digest=projection.evidence_records[evidence_id].artifact_digest,
                )
                projected = project_event(projected, invalidated)
                batch.append(invalidated)
                previous = contract.canonical_digest(invalidated)
        return _append_locked(paths, policy, old_events, projected, batch, artifacts)


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


def start_successor(
    repository: Path,
    predecessor_id: str,
    receipt: Mapping[str, object],
    policy: Mapping[str, object],
) -> dict[str, object]:
    """Create an INIT successor without mutating its terminal predecessor."""
    predecessor_paths = store.resolve_run(repository, predecessor_id)
    lineage = _lineage_receipt(receipt, predecessor_id)
    successor_policy = _canonical_mapping(policy)
    execution_id = successor_policy.get("execution_id")
    if (
        not isinstance(execution_id, str)
        or contract.EXECUTION_ID.fullmatch(execution_id) is None
        or execution_id == predecessor_id
    ):
        raise ControllerError("INVALID_EXECUTION_ID", "Successor execution ID is invalid.")
    if successor_policy.get("initial_state", State.INIT.value) != State.INIT.value:
        raise ControllerError("INVALID_POLICY", "A successor must start in INIT.")
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

    with store.run_lock(predecessor_paths.lock):
        _, _, predecessor = _load_locked(predecessor_paths)
        if predecessor.state not in TERMINAL_STATES:
            raise ControllerError("PREDECESSOR_NOT_TERMINAL", "Successor requires a terminal predecessor.")
        payload = {
            "receipt_id": "RCP-" + str(lineage["lineage_receipt_digest"])[7:19].upper(),
            "receipt_digest": lineage["lineage_receipt_digest"],
            "issuer_skill": "hotl-governance-lineage",
        }
        first_event = _generated_event(
            execution_id,
            1,
            None,
            "receipt_imported",
            payload,
            input_digest=str(lineage["lineage_receipt_digest"]),
        )
        projection = replay(successor_policy, [first_event])
        state = _state_value(
            projection, successor_policy, 1, contract.canonical_digest(first_event)
        )
        store.publish_initial_run(successor_paths, state, first_event)
    return {
        "execution_id": execution_id,
        "predecessor_execution_id": predecessor_id,
        "state": State.INIT.value,
        "event_count": 1,
        "lineage_receipt_digest": lineage["lineage_receipt_digest"],
    }


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
        "recovery": recovery,
    }
