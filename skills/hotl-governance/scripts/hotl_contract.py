"""Strict, deterministic primitives shared by the HOTL controller.

The controller adds issuer- and event-type-specific checks on top of these
envelope contracts.  This module deliberately accepts no best-effort aliases.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import re
from pathlib import Path, PurePosixPath


EXECUTION_ID = re.compile(r"EXEC-[0-9A-F]{12}\Z")
EVENT_ID = re.compile(r"EVT-[0-9A-F]{12}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
NODE_ID = re.compile(r"(?:REQ|CODE|TEST|CMD|EVID|REV|CHG|FAIL|POL)-[A-Za-z0-9][A-Za-z0-9._:-]*\Z")

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
    target = (root / PurePosixPath(normalized)).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ContractError("PATH_ESCAPE", "Path resolves outside the repository.") from error
    return normalized


def _validate_issuer(value: object) -> None:
    issuer = _require_exact_fields(value, ISSUER_FIELDS, "issuer")
    for field in ISSUER_FIELDS:
        _require_string(issuer[field], f"issuer.{field}")


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
    _require_string(event["type"], "event type")
    if not isinstance(event["payload"], dict):
        raise ContractError("INVALID_SCHEMA", "event payload must be an object.")
    _validate_json_tree(event["payload"])
    _validate_issuer(event["issuer"])
    _validate_subject_ids(event["subject_ids"])
    _validate_artifact_refs(event["artifact_refs"])
    _require_string(event["result"], "event result")
    _require_digest(event["input_digest"], "event input_digest")
    _require_digest(event["output_digest"], "event output_digest")
    if previous_hash is not None:
        _require_digest(previous_hash, "previous hash")
    if event["previous_event_hash"] != previous_hash:
        raise ContractError("PREVIOUS_HASH_MISMATCH", "Event previous hash does not match the chain head.")
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
