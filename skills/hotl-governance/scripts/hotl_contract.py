"""Strict, deterministic primitives shared by the HOTL controller.

The controller adds issuer- and event-type-specific checks on top of these
envelope contracts.  This module deliberately accepts no best-effort aliases.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import re
import stat
from pathlib import Path, PurePosixPath


EXECUTION_ID = re.compile(r"EXEC-[0-9A-F]{12}\Z")
EVENT_ID = re.compile(r"EVT-[0-9A-F]{12}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
NODE_ID = re.compile(r"(?:REQ|CODE|TEST|CMD|EVID|REV|CHG|FAIL|POL)-[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
STABLE_ID = re.compile(r"[A-Za-z][A-Za-z0-9._:-]*\Z")

NODE_TYPE_PREFIXES = {
    "requirement": "REQ-",
    "code": "CODE-",
    "test": "TEST-",
    "command": "CMD-",
    "evidence": "EVID-",
    "review": "REV-",
    "change": "CHG-",
    "failure": "FAIL-",
    "policy": "POL-",
}
EVENT_TYPES = frozenset(
    {
        "node_declared",
        "edge_declared",
        "snapshot_activated",
        "evidence_recorded",
        "evidence_invalidated",
        "review_recorded",
        "finding_recorded",
        "receipt_imported",
        "transition_committed",
    }
)
RECEIPT_TYPE_ISSUERS = {
    "requirements": frozenset({"gpt-pro-codex-loop"}),
    "approval": frozenset({"gpt-pro-codex-loop"}),
    "implementation": frozenset({"codex"}),
    "verification": frozenset({"hotl-local-verifier"}),
    "semantic_review": frozenset({"gpt-pro-codex-loop"}),
    "final": frozenset({"gpt-pro-codex-loop"}),
    "material_change": frozenset({"gpt-pro-codex-loop"}),
    "stop": frozenset({"gpt-pro-codex-loop"}),
    "lineage": frozenset({"hotl-governance-lineage"}),
}
TRANSITION_DECISIONS = frozenset(
    {
        "INIT",
        "G1",
        "G2",
        "G3",
        "G4",
        "CORRECTIVE",
        "ESCALATION",
        "MATERIAL_CHANGE",
        "STOP",
    }
)
STATES = frozenset(
    {
        "INIT",
        "REQUIREMENTS",
        "IMPLEMENT",
        "LOCAL_VERIFY",
        "SEMANTIC_REVIEW",
        "COMPLETE",
        "ESCALATED",
        "RECOVERY_REQUIRED",
        "STOPPED",
    }
)

ALLOWED_EDGE_TRIPLES = frozenset(
    {
        ("code", "implements", "requirement"),
        ("test", "verifies", "requirement"),
        ("command", "executes", "test"),
        ("command", "produces", "evidence"),
        ("evidence", "proves", "test"),
        ("evidence", "supports", "review"),
        ("review", "reviews", "requirement"),
        ("code", "included_in", "change"),
        ("test", "included_in", "change"),
        ("failure", "violates", "requirement"),
        ("change", "fixes", "failure"),
        ("evidence", "derived_from", "evidence"),
        ("review", "derived_from", "review"),
        ("change", "derived_from", "change"),
        ("requirement", "supersedes", "requirement"),
        ("policy", "supersedes", "policy"),
    }
)

EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "execution_id",
        "sequence",
        "type",
        "payload",
        "issuer",
        "subject_ids",
        "artifact_refs",
        "result",
        "input_digest",
        "output_digest",
        "previous_event_hash",
        "timestamp",
    }
)
ISSUER_FIELDS = frozenset({"kind", "id", "version"})
ARTIFACT_REF_FIELDS = frozenset({"path", "sha256"})
RECEIPT_BASE_FIELDS = frozenset(
    {
        "receipt_schema_version",
        "receipt_id",
        "issuer_skill",
        "issuer_version",
        "execution_id",
        "nonce",
        "issued_at_unix",
        "input_digest",
        "output_digest",
        "authority_snapshot_digest",
    }
)


class ContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_constant(value: str) -> None:
    raise ContractError("NON_FINITE_NUMBER", f"Forbidden JSON constant: {value}")


def _reject_float(_: str) -> object:
    raise ContractError("FLOAT_FORBIDDEN", "Floating-point values are forbidden.")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("DUPLICATE_KEY", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(raw: str) -> object:
    if not isinstance(raw, str):
        raise ContractError("INVALID_JSON", "JSON input must be text.")
    if raw.startswith("\ufeff"):
        raise ContractError("BOM_FORBIDDEN", "UTF-8 BOM is forbidden.")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise ContractError("INVALID_JSON", f"Invalid JSON: {error.msg}") from error


def _validate_json_tree(value: object) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        raise ContractError("FLOAT_FORBIDDEN", "Floating-point values are forbidden.")
    if isinstance(value, list):
        for item in value:
            _validate_json_tree(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError("NON_STRING_KEY", "JSON object keys must be strings.")
            _validate_json_tree(item)
        return
    raise ContractError("INVALID_JSON_VALUE", f"Unsupported JSON value: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    _validate_json_tree(value)
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def canonical_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_exact_fields(value: object, fields: frozenset[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ContractError("INVALID_SCHEMA", f"{label} must be an object.")
    actual = set(value)
    if actual != fields:
        missing = sorted(fields - actual)
        unknown = sorted(actual - fields)
        raise ContractError(
            "INVALID_FIELDS",
            f"{label} fields must match exactly; missing={missing}, unknown={unknown}.",
        )
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError("INVALID_VALUE", f"{label} must be a non-empty string.")
    if "\x00" in value:
        raise ContractError("INVALID_VALUE", f"{label} must not contain NUL.")
    return value


def _require_digest(value: object, label: str) -> str:
    result = _require_string(value, label)
    if not DIGEST.fullmatch(result):
        raise ContractError("INVALID_DIGEST", f"{label} must be a canonical SHA-256 digest.")
    return result


def _canonical_repo_path_text(raw: object) -> str:
    raw = _require_string(raw, "path")
    if "\x00" in raw:
        raise ContractError("INVALID_PATH", "Path must not contain NUL.")
    if raw.startswith(("/", "\\")) or ntpath.isabs(raw) or ntpath.splitdrive(raw)[0]:
        raise ContractError("INVALID_PATH", "Path must be repository-relative.")
    normalized = raw.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ContractError("INVALID_PATH", "Path contains a forbidden segment.")
    return str(PurePosixPath(*parts))


def normalize_repo_path(repository: Path, raw: str) -> str:
    normalized = _canonical_repo_path_text(raw)
    root = Path(repository).resolve(strict=False)
    candidate = root
    for part in PurePosixPath(normalized).parts:
        candidate = candidate / part
        if _is_link_or_reparse_point(candidate):
            raise ContractError("LINK_FORBIDDEN", "Path must not traverse a symlink or reparse point.")
    target = candidate.resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ContractError("PATH_ESCAPE", "Path resolves outside the repository.") from error
    return normalized


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    if path.is_symlink():
        return True
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse_attribute)


def _validate_issuer(value: object) -> dict[str, object]:
    issuer = _require_exact_fields(value, ISSUER_FIELDS, "issuer")
    for field in ISSUER_FIELDS:
        _require_string(issuer[field], f"issuer.{field}")
    return issuer


def _validate_subject_ids(value: object) -> None:
    if not isinstance(value, list):
        raise ContractError("INVALID_SCHEMA", "subject_ids must be a list.")
    for subject_id in value:
        if not isinstance(subject_id, str) or not NODE_ID.fullmatch(subject_id):
            raise ContractError("INVALID_NODE_ID", "subject_ids must contain known typed node IDs.")
    if len(set(value)) != len(value):
        raise ContractError("DUPLICATE_SUBJECT", "subject_ids must not contain duplicates.")


def _validate_artifact_refs(value: object) -> None:
    if not isinstance(value, list):
        raise ContractError("INVALID_SCHEMA", "artifact_refs must be a list.")
    for ref in value:
        artifact = _require_exact_fields(ref, ARTIFACT_REF_FIELDS, "artifact reference")
        path = _canonical_repo_path_text(artifact["path"])
        if artifact["path"] != path:
            raise ContractError("NONCANONICAL_PATH", "Artifact paths must use canonical POSIX form.")
        _require_digest(artifact["sha256"], "artifact reference sha256")


def _require_nonnegative_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContractError("INVALID_VALUE", f"{label} must be a non-negative integer.")
    return value


def _require_optional_digest(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_digest(value, label)


def _require_optional_nonnegative_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _require_nonnegative_integer(value, label)


def _require_enum(value: object, allowed: frozenset[str], label: str) -> str:
    result = _require_string(value, label)
    if result not in allowed:
        raise ContractError("INVALID_VALUE", f"{label} is not an allowed value.")
    return result


def _node_type_for_id(value: object, label: str) -> str:
    node_id = _require_string(value, label)
    if not NODE_ID.fullmatch(node_id):
        raise ContractError("INVALID_NODE_ID", f"{label} must be a known typed node ID.")
    for node_type, prefix in NODE_TYPE_PREFIXES.items():
        if node_id.startswith(prefix):
            return node_type
    raise ContractError("INVALID_NODE_ID", f"{label} has an unsupported node type.")


def _require_subjects(value: object, expected: list[str]) -> None:
    if value != expected:
        raise ContractError("SUBJECT_MISMATCH", "Event subject_ids do not match its typed payload.")


def _require_event_issuer(event: dict[str, object], kind: str, identifier: str | None = None) -> None:
    issuer = _validate_issuer(event["issuer"])
    if issuer["kind"] != kind or (identifier is not None and issuer["id"] != identifier):
        raise ContractError("ISSUER_MISMATCH", "Event issuer is not permitted for this event type.")


def _require_event_result(event: dict[str, object], expected: str) -> None:
    if event["result"] != expected:
        raise ContractError("RESULT_MISMATCH", "Event result is not permitted for this event type.")


def _require_empty_artifacts(event: dict[str, object]) -> None:
    if event["artifact_refs"] != []:
        raise ContractError("ARTIFACT_MISMATCH", "This event type must not include artifact references.")


def _require_payload(value: object, fields: frozenset[str], event_type: str) -> dict[str, object]:
    return _require_exact_fields(value, fields, f"{event_type} payload")


def _validate_event_contract(event: dict[str, object]) -> None:
    event_type = event["type"]
    if not isinstance(event_type, str) or event_type not in EVENT_TYPES:
        raise ContractError("UNKNOWN_EVENT_TYPE", "Event type is not supported by the v1 contract.")

    if event_type == "node_declared":
        payload = _require_payload(event["payload"], frozenset({"node_id", "node_type"}), event_type)
        node_type = _require_string(payload["node_type"], "node_type")
        if node_type not in NODE_TYPE_PREFIXES:
            raise ContractError("INVALID_NODE_TYPE", "node_type is not supported.")
        node_id = _require_string(payload["node_id"], "node_id")
        if not node_id.startswith(NODE_TYPE_PREFIXES[node_type]) or not NODE_ID.fullmatch(node_id):
            raise ContractError("NODE_TYPE_MISMATCH", "node_id prefix does not match node_type.")
        _require_subjects(event["subject_ids"], [node_id])
        _require_event_issuer(event, "controller", "hotl-governance")
        _require_event_result(event, "pass")
        _require_empty_artifacts(event)
        return

    if event_type == "edge_declared":
        payload = _require_payload(event["payload"], frozenset({"source_id", "edge", "target_id"}), event_type)
        source_id = _require_string(payload["source_id"], "source_id")
        target_id = _require_string(payload["target_id"], "target_id")
        source_type = _node_type_for_id(source_id, "source_id")
        target_type = _node_type_for_id(target_id, "target_id")
        validate_edge(source_type, _require_string(payload["edge"], "edge"), target_type)
        _require_subjects(event["subject_ids"], [source_id, target_id])
        _require_event_issuer(event, "controller", "hotl-governance")
        _require_event_result(event, "pass")
        _require_empty_artifacts(event)
        return

    if event_type == "snapshot_activated":
        payload = _require_payload(event["payload"], frozenset({"snapshot_digest", "cycle_id"}), event_type)
        _require_digest(payload["snapshot_digest"], "snapshot_digest")
        _require_nonnegative_integer(payload["cycle_id"], "cycle_id")
        _require_subjects(event["subject_ids"], [])
        _require_event_issuer(event, "controller", "hotl-governance")
        _require_event_result(event, "pass")
        _require_empty_artifacts(event)
        return

    if event_type == "evidence_recorded":
        payload = _require_payload(
            event["payload"],
            frozenset({"evidence_id", "artifact_digest", "test_id", "snapshot_digest", "cycle_id"}),
            event_type,
        )
        if _node_type_for_id(payload["evidence_id"], "evidence_id") != "evidence":
            raise ContractError("NODE_TYPE_MISMATCH", "evidence_id must use the EVID- prefix.")
        if _node_type_for_id(payload["test_id"], "test_id") != "test":
            raise ContractError("NODE_TYPE_MISMATCH", "test_id must use the TEST- prefix.")
        _require_digest(payload["artifact_digest"], "artifact_digest")
        _require_digest(payload["snapshot_digest"], "snapshot_digest")
        _require_nonnegative_integer(payload["cycle_id"], "cycle_id")
        _require_subjects(event["subject_ids"], [payload["evidence_id"], payload["test_id"]])
        if not any(ref["sha256"] == payload["artifact_digest"] for ref in event["artifact_refs"]):
            raise ContractError("ARTIFACT_MISMATCH", "Evidence event must bind its artifact digest.")
        _require_event_issuer(event, "tool")
        _require_event_result(event, "pass")
        return

    if event_type == "evidence_invalidated":
        payload = _require_payload(event["payload"], frozenset({"evidence_id", "cycle_id"}), event_type)
        if _node_type_for_id(payload["evidence_id"], "evidence_id") != "evidence":
            raise ContractError("NODE_TYPE_MISMATCH", "evidence_id must use the EVID- prefix.")
        _require_nonnegative_integer(payload["cycle_id"], "cycle_id")
        _require_subjects(event["subject_ids"], [payload["evidence_id"]])
        _require_event_issuer(event, "controller", "hotl-governance")
        _require_event_result(event, "pass")
        _require_empty_artifacts(event)
        return

    if event_type == "review_recorded":
        payload = _require_payload(
            event["payload"],
            frozenset(
                {
                    "review_id",
                    "receipt_id",
                    "status",
                    "evidence_set_digest",
                    "cycle_id",
                    "root_cause_ids",
                }
            ),
            event_type,
        )
        if _node_type_for_id(payload["review_id"], "review_id") != "review":
            raise ContractError("NODE_TYPE_MISMATCH", "review_id must use the REV- prefix.")
        status = _require_enum(
            payload["status"], frozenset({"accepted", "rejected"}), "review status"
        )
        _require_string(payload["receipt_id"], "receipt_id")
        _require_digest(payload["evidence_set_digest"], "evidence_set_digest")
        _require_nonnegative_integer(payload["cycle_id"], "cycle_id")
        roots = payload["root_cause_ids"]
        if not isinstance(roots, list):
            raise ContractError("INVALID_SCHEMA", "root_cause_ids must be a list.")
        for root in roots:
            if not isinstance(root, str) or STABLE_ID.fullmatch(root) is None:
                raise ContractError("INVALID_FINDING_ID", "root_cause_ids must be stable IDs.")
        if roots != sorted(set(roots)):
            raise ContractError(
                "INVALID_REVIEW_ROOTS", "root_cause_ids must be unique and canonically sorted."
            )
        if (status == "accepted" and roots) or (status == "rejected" and not roots):
            raise ContractError(
                "INVALID_REVIEW_ROOTS",
                "Accepted reviews have no roots; rejected reviews require fixed roots.",
            )
        _require_subjects(event["subject_ids"], [payload["review_id"]])
        _require_event_issuer(event, "skill")
        _require_event_result(event, "pass" if status == "accepted" else "fail")
        _require_empty_artifacts(event)
        return

    if event_type == "finding_recorded":
        payload = _require_payload(
            event["payload"], frozenset({"finding_id", "root_cause_id", "review_id", "status"}), event_type
        )
        for field in ("finding_id", "root_cause_id"):
            identifier = _require_string(payload[field], field)
            if not STABLE_ID.fullmatch(identifier):
                raise ContractError("INVALID_FINDING_ID", f"{field} is not a stable identifier.")
        if _node_type_for_id(payload["review_id"], "review_id") != "review":
            raise ContractError("NODE_TYPE_MISMATCH", "review_id must use the REV- prefix.")
        status = _require_enum(
            payload["status"], frozenset({"open", "resolved"}), "finding status"
        )
        _require_subjects(event["subject_ids"], [payload["review_id"]])
        _require_event_issuer(event, "skill")
        _require_event_result(event, "fail" if status == "open" else "pass")
        _require_empty_artifacts(event)
        return

    if event_type == "receipt_imported":
        payload = _require_payload(
            event["payload"],
            frozenset(
                {
                    "receipt_id",
                    "receipt_type",
                    "receipt_digest",
                    "issuer_skill",
                    "authority_snapshot_digest",
                    "requirements_digest",
                    "snapshot_digest",
                    "evidence_set_digest",
                    "cycle_id",
                }
            ),
            event_type,
        )
        for field in ("receipt_id", "issuer_skill"):
            _require_string(payload[field], field)
        receipt_type = _require_enum(
            payload["receipt_type"], frozenset(RECEIPT_TYPE_ISSUERS), "receipt_type"
        )
        if payload["issuer_skill"] not in RECEIPT_TYPE_ISSUERS[receipt_type]:
            raise ContractError(
                "ISSUER_MISMATCH", "Receipt type is not allowed from the declared issuer."
            )
        _require_digest(payload["receipt_digest"], "receipt_digest")
        authority = _require_optional_digest(
            payload["authority_snapshot_digest"], "authority_snapshot_digest"
        )
        requirements = _require_optional_digest(
            payload["requirements_digest"], "requirements_digest"
        )
        snapshot = _require_optional_digest(payload["snapshot_digest"], "snapshot_digest")
        evidence_set = _require_optional_digest(
            payload["evidence_set_digest"], "evidence_set_digest"
        )
        cycle = _require_optional_nonnegative_integer(payload["cycle_id"], "cycle_id")
        if receipt_type == "lineage":
            if any(value is not None for value in (authority, requirements, snapshot, evidence_set, cycle)):
                raise ContractError("INVALID_RECEIPT_BINDING", "Lineage receipt bindings must be null.")
        elif receipt_type in {"requirements", "approval"}:
            if authority is None or requirements is None or any(
                value is not None for value in (snapshot, evidence_set, cycle)
            ):
                raise ContractError(
                    "INVALID_RECEIPT_BINDING",
                    "Requirements and approval receipts bind authority and requirements only.",
                )
        elif receipt_type in {"material_change", "stop"}:
            if any(value is None for value in (authority, requirements, evidence_set, cycle)):
                raise ContractError(
                    "INVALID_RECEIPT_BINDING",
                    "Terminal authority receipts bind authority, requirements, evidence, and cycle.",
                )
        elif any(value is None for value in (authority, requirements, snapshot, evidence_set, cycle)):
            raise ContractError(
                "INVALID_RECEIPT_BINDING", "Current lifecycle receipts require every binding."
            )
        if event["input_digest"] != payload["receipt_digest"]:
            raise ContractError("DIGEST_MISMATCH", "Receipt event input must bind its receipt digest.")
        _require_subjects(event["subject_ids"], [])
        _require_event_issuer(event, "controller", "hotl-governance")
        _require_event_result(event, "pass")
        _require_empty_artifacts(event)
        return

    payload = _require_payload(
        event["payload"],
        frozenset({"gate", "from_state", "to_state", "evidence_set_digest", "cycle_id"}),
        event_type,
    )
    gate = _require_enum(payload["gate"], TRANSITION_DECISIONS, "transition decision")
    from_state = _require_enum(payload["from_state"], STATES, "transition from_state")
    to_state = _require_enum(payload["to_state"], STATES, "transition to_state")
    if from_state == to_state:
        raise ContractError("INVALID_STATE", "Transition states must differ.")
    _require_digest(payload["evidence_set_digest"], "evidence_set_digest")
    _require_nonnegative_integer(payload["cycle_id"], "cycle_id")
    _require_subjects(event["subject_ids"], [])
    _require_event_issuer(event, "controller", "hotl-governance")
    _require_event_result(event, "pass")
    _require_empty_artifacts(event)


def validate_event(
    value: object, previous_hash: str | None, expected_sequence: int
) -> dict[str, object]:
    event = _require_exact_fields(value, EVENT_FIELDS, "event")
    if not isinstance(expected_sequence, int) or isinstance(expected_sequence, bool) or expected_sequence < 1:
        raise ContractError("INVALID_SEQUENCE", "Expected sequence must be a positive integer.")
    if event["schema_version"] != 1 or isinstance(event["schema_version"], bool):
        raise ContractError("INVALID_SCHEMA_VERSION", "event schema_version must be integer 1.")
    if not isinstance(event["sequence"], int) or isinstance(event["sequence"], bool):
        raise ContractError("INVALID_SEQUENCE", "event sequence must be an integer.")
    if event["sequence"] != expected_sequence:
        raise ContractError("SEQUENCE_MISMATCH", "Event sequence does not match the expected sequence.")
    if not isinstance(event["event_id"], str) or not EVENT_ID.fullmatch(event["event_id"]):
        raise ContractError("INVALID_EVENT_ID", "Invalid event ID.")
    if not isinstance(event["execution_id"], str) or not EXECUTION_ID.fullmatch(event["execution_id"]):
        raise ContractError("INVALID_EXECUTION_ID", "Invalid execution ID.")
    if not isinstance(event["payload"], dict):
        raise ContractError("INVALID_SCHEMA", "event payload must be an object.")
    _validate_issuer(event["issuer"])
    _validate_subject_ids(event["subject_ids"])
    _validate_artifact_refs(event["artifact_refs"])
    _require_digest(event["input_digest"], "event input_digest")
    _require_digest(event["output_digest"], "event output_digest")
    if expected_sequence == 1:
        if previous_hash is not None or event["previous_event_hash"] is not None:
            raise ContractError("PREVIOUS_HASH_MISMATCH", "The first event must not have a predecessor hash.")
    else:
        _require_digest(previous_hash, "previous hash")
        _require_digest(event["previous_event_hash"], "event previous_event_hash")
        if event["previous_event_hash"] != previous_hash:
            raise ContractError("PREVIOUS_HASH_MISMATCH", "Event previous hash does not match the chain head.")
    _validate_event_contract(event)
    _require_string(event["timestamp"], "event timestamp")
    return event


def validate_receipt(
    value: object, expected_issuer: str, execution_id: str, authority_digest: str
) -> dict[str, object]:
    if not isinstance(expected_issuer, str) or not expected_issuer:
        raise ContractError("INVALID_EXPECTATION", "Expected issuer must be a non-empty string.")
    if not isinstance(execution_id, str) or not EXECUTION_ID.fullmatch(execution_id):
        raise ContractError("INVALID_EXPECTATION", "Expected execution ID is invalid.")
    _require_digest(authority_digest, "expected authority digest")
    if not isinstance(value, dict):
        raise ContractError("INVALID_SCHEMA", "receipt must be an object.")
    identity_fields = {"transaction_id", "invocation_id"}
    present_identity_fields = identity_fields & set(value)
    if len(present_identity_fields) != 1:
        raise ContractError(
            "INVALID_RECEIPT_IDENTITY", "Receipt requires exactly one transaction or invocation ID."
        )
    receipt = _require_exact_fields(
        value, RECEIPT_BASE_FIELDS | present_identity_fields, "receipt"
    )
    if receipt["receipt_schema_version"] != 1 or isinstance(
        receipt["receipt_schema_version"], bool
    ):
        raise ContractError("INVALID_SCHEMA_VERSION", "receipt_schema_version must be integer 1.")
    for field in ("receipt_id", "issuer_skill", "issuer_version"):
        _require_string(receipt[field], field)
    if receipt["issuer_skill"] != expected_issuer:
        raise ContractError("ISSUER_MISMATCH", "Receipt issuer does not match the expected issuer.")
    if receipt["execution_id"] != execution_id:
        raise ContractError("EXECUTION_MISMATCH", "Receipt execution does not match the expected execution.")
    if not isinstance(receipt["execution_id"], str) or not EXECUTION_ID.fullmatch(
        receipt["execution_id"]
    ):
        raise ContractError("INVALID_EXECUTION_ID", "Invalid receipt execution ID.")
    _require_string(receipt[next(iter(present_identity_fields))], "receipt identity")
    if not isinstance(receipt["nonce"], str) or not NONCE.fullmatch(receipt["nonce"]):
        raise ContractError("INVALID_NONCE", "Receipt nonce must be 32 lowercase hexadecimal characters.")
    issued_at = receipt["issued_at_unix"]
    if not isinstance(issued_at, int) or isinstance(issued_at, bool) or issued_at < 0:
        raise ContractError("INVALID_TIMESTAMP", "issued_at_unix must be a non-negative integer.")
    _require_digest(receipt["input_digest"], "receipt input_digest")
    _require_digest(receipt["output_digest"], "receipt output_digest")
    if receipt["authority_snapshot_digest"] != authority_digest:
        raise ContractError("AUTHORITY_MISMATCH", "Receipt authority digest does not match.")
    _require_digest(receipt["authority_snapshot_digest"], "receipt authority_snapshot_digest")
    return receipt


def validate_edge(source_type: str, edge: str, target_type: str) -> None:
    if (source_type, edge, target_type) not in ALLOWED_EDGE_TRIPLES:
        raise ContractError(
            "INVALID_EDGE", f"Unsupported typed edge: {source_type} {edge} {target_type}."
        )
