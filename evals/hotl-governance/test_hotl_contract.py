from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "hotl-governance" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hotl_contract as contract


DIGEST_ONE = "sha256:" + "1" * 64
DIGEST_TWO = "sha256:" + "2" * 64
DIGEST_THREE = "sha256:" + "3" * 64
EXECUTION_ID = "EXEC-123456789ABC"


def valid_event(**changes: object) -> dict[str, object]:
    event: dict[str, object] = {
        "schema_version": 1,
        "event_id": "EVT-123456789ABC",
        "execution_id": EXECUTION_ID,
        "sequence": 1,
        "type": "evidence_recorded",
        "payload": {
            "evidence_id": "EVID-42",
            "artifact_digest": DIGEST_ONE,
            "test_id": "TEST-42",
            "snapshot_digest": DIGEST_TWO,
            "cycle_id": 1,
        },
        "issuer": {"kind": "tool", "id": "pytest", "version": "8.0"},
        "subject_ids": ["EVID-42", "TEST-42"],
        "artifact_refs": [{"path": "evidence/test-output.txt", "sha256": DIGEST_ONE}],
        "result": "pass",
        "input_digest": DIGEST_TWO,
        "output_digest": DIGEST_THREE,
        "previous_event_hash": None,
        "timestamp": "2026-08-09T00:00:00Z",
    }
    event.update(changes)
    return event


def event_for(event_type: str) -> dict[str, object]:
    cases: dict[str, dict[str, object]] = {
        "node_declared": {
            "payload": {"node_id": "REQ-42", "node_type": "requirement"},
            "issuer": {"kind": "controller", "id": "hotl-governance", "version": "1"},
            "subject_ids": ["REQ-42"],
            "artifact_refs": [],
            "result": "pass",
        },
        "edge_declared": {
            "payload": {"source_id": "CODE-42", "edge": "implements", "target_id": "REQ-42"},
            "issuer": {"kind": "controller", "id": "hotl-governance", "version": "1"},
            "subject_ids": ["CODE-42", "REQ-42"],
            "artifact_refs": [],
            "result": "pass",
        },
        "snapshot_activated": {
            "payload": {"snapshot_digest": DIGEST_ONE, "cycle_id": 1},
            "issuer": {"kind": "controller", "id": "hotl-governance", "version": "1"},
            "subject_ids": [],
            "artifact_refs": [],
            "result": "pass",
        },
        "evidence_recorded": {
            "payload": {
                "evidence_id": "EVID-42",
                "artifact_digest": DIGEST_ONE,
                "test_id": "TEST-42",
                "snapshot_digest": DIGEST_TWO,
                "cycle_id": 1,
            },
            "issuer": {"kind": "tool", "id": "pytest", "version": "8.0"},
            "subject_ids": ["EVID-42", "TEST-42"],
            "artifact_refs": [{"path": "evidence/test-output.txt", "sha256": DIGEST_ONE}],
            "result": "pass",
        },
        "evidence_invalidated": {
            "payload": {"evidence_id": "EVID-42", "cycle_id": 1},
            "issuer": {"kind": "controller", "id": "hotl-governance", "version": "1"},
            "subject_ids": ["EVID-42"],
            "artifact_refs": [],
            "result": "pass",
        },
        "review_recorded": {
            "payload": {
                "review_id": "REV-42",
                "status": "accepted",
                "evidence_set_digest": DIGEST_ONE,
                "cycle_id": 1,
            },
            "issuer": {"kind": "skill", "id": "gpt-pro-codex-loop", "version": "1"},
            "subject_ids": ["REV-42"],
            "artifact_refs": [],
            "result": "pass",
        },
        "finding_recorded": {
            "payload": {
                "finding_id": "FIND-42",
                "root_cause_id": "ROOT-42",
                "review_id": "REV-42",
                "status": "open",
            },
            "issuer": {"kind": "skill", "id": "gpt-pro-codex-loop", "version": "1"},
            "subject_ids": ["REV-42"],
            "artifact_refs": [],
            "result": "fail",
        },
        "receipt_imported": {
            "payload": {
                "receipt_id": "RCP-42",
                "receipt_digest": DIGEST_ONE,
                "issuer_skill": "gpt-pro-codex-loop",
            },
            "issuer": {"kind": "controller", "id": "hotl-governance", "version": "1"},
            "subject_ids": [],
            "artifact_refs": [],
            "result": "pass",
        },
        "transition_committed": {
            "payload": {
                "gate": "G1",
                "from_state": "REQUIREMENTS",
                "to_state": "IMPLEMENT",
                "evidence_set_digest": DIGEST_ONE,
                "cycle_id": 1,
            },
            "issuer": {"kind": "controller", "id": "hotl-governance", "version": "1"},
            "subject_ids": [],
            "artifact_refs": [],
            "result": "pass",
        },
    }
    return valid_event(type=event_type, **cases[event_type])


def valid_receipt(**changes: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "receipt_schema_version": 1,
        "receipt_id": "RCP-123456789ABC",
        "issuer_skill": "gpt-pro-codex-loop",
        "issuer_version": "1",
        "execution_id": EXECUTION_ID,
        "transaction_id": "TXN-1",
        "nonce": "a" * 32,
        "issued_at_unix": 1,
        "input_digest": DIGEST_ONE,
        "output_digest": DIGEST_TWO,
        "authority_snapshot_digest": DIGEST_THREE,
    }
    receipt.update(changes)
    return receipt


class CanonicalJsonTests(unittest.TestCase):
    def test_canonical_json_is_stable(self) -> None:
        left = {"b": 2, "a": ["x", 1]}
        right = {"a": ["x", 1], "b": 2}
        self.assertEqual(contract.canonical_json_bytes(left), contract.canonical_json_bytes(right))
        self.assertEqual(b'{"a":["x",1],"b":2}\n', contract.canonical_json_bytes(left))

    def test_digest_is_sha256_of_canonical_bytes(self) -> None:
        self.assertEqual(
            "sha256:e346432021b04179518d9614f3560ccd71354a4ee101ddcb893d6959a9d6301c",
            contract.canonical_digest({"a": 1}),
        )

    def test_rejects_noncanonical_number_and_duplicate_key(self) -> None:
        for raw in ('{"x":1.5}', '{"x":NaN}', '{"x":1,"x":2}', '\ufeff{"x":1}'):
            with self.subTest(raw=raw), self.assertRaises(contract.ContractError):
                contract.strict_json_loads(raw)

    def test_canonical_json_rejects_non_json_runtime_values(self) -> None:
        for value in ({"x": 1.0}, {1: "x"}, ("x",), {"x": {"y": object()}}):
            with self.subTest(value=repr(value)), self.assertRaises(contract.ContractError):
                contract.canonical_json_bytes(value)


class RepositoryPathTests(unittest.TestCase):
    def test_normalizes_backslashes_to_a_canonical_posix_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                "evidence/test-output.txt",
                contract.normalize_repo_path(Path(directory), "evidence\\test-output.txt"),
            )

    def test_rejects_noncanonical_or_escaping_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for raw in ("", ".", "..", "a/../b", "a//b", "/tmp/outside", "C:\\outside", "\\\\server\\share", "a\x00b"):
                with self.subTest(raw=repr(raw)), self.assertRaises(contract.ContractError):
                    contract.normalize_repo_path(Path(directory), raw)

    def test_rejects_symlink_or_reparse_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            outside = root / "outside"
            repository.mkdir()
            outside.mkdir()
            link = repository / "escape"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            with self.assertRaises(contract.ContractError):
                contract.normalize_repo_path(repository, "escape/secret.txt")

    def test_rejects_in_repository_symlink_or_reparse_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            target = repository / "target"
            repository.mkdir()
            target.mkdir()
            link = repository / "inside"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            with self.assertRaises(contract.ContractError):
                contract.normalize_repo_path(repository, "inside/secret.txt")


class EnvelopeValidationTests(unittest.TestCase):
    def test_event_requires_the_exact_closed_envelope_and_chain_position(self) -> None:
        event = valid_event()
        self.assertEqual(event, contract.validate_event(event, None, 1))
        for changed in (
            {"unknown": True},
            {"sequence": 2},
            {"previous_event_hash": DIGEST_ONE},
            {"event_id": "EVT-lowercase"},
            {"artifact_refs": [{"path": "evidence\\output.txt", "sha256": DIGEST_ONE}]},
        ):
            with self.subTest(changed=changed), self.assertRaises(contract.ContractError):
                contract.validate_event(valid_event(**changed), None, 1)

    def test_event_requires_valid_issuer_subject_ids_and_digests(self) -> None:
        for changed in (
            {"issuer": {"kind": "tool", "id": "pytest"}},
            {"subject_ids": ["UNKNOWN-42"]},
            {"subject_ids": [{}]},
            {"input_digest": "sha256:" + "A" * 64},
            {"artifact_refs": [{"path": "evidence/output.txt", "sha256": "not-a-digest"}]},
        ):
            with self.subTest(changed=changed), self.assertRaises(contract.ContractError):
                contract.validate_event(valid_event(**changed), None, 1)

    def test_event_accepts_only_the_supplied_previous_hash(self) -> None:
        event = valid_event(sequence=2, previous_event_hash=DIGEST_ONE)
        self.assertEqual(event, contract.validate_event(event, DIGEST_ONE, 2))

    def test_event_requires_a_predecessor_hash_after_sequence_one(self) -> None:
        with self.assertRaises(contract.ContractError):
            contract.validate_event(valid_event(sequence=2), None, 2)

    def test_event_types_have_closed_payload_and_typed_subject_contracts(self) -> None:
        for event_type in (
            "node_declared",
            "edge_declared",
            "snapshot_activated",
            "evidence_recorded",
            "evidence_invalidated",
            "review_recorded",
            "finding_recorded",
            "receipt_imported",
            "transition_committed",
        ):
            with self.subTest(event_type=event_type):
                event = event_for(event_type)
                self.assertEqual(event, contract.validate_event(event, None, 1))

        with self.assertRaises(contract.ContractError):
            contract.validate_event(valid_event(type="unrecognized", payload={}), None, 1)
        with self.assertRaises(contract.ContractError):
            contract.validate_event(
                event_for("transition_committed") | {"payload": {"gate": "G1", "extra": True}},
                None,
                1,
            )
        with self.assertRaises(contract.ContractError):
            contract.validate_event(
                event_for("evidence_recorded") | {"subject_ids": ["EVID-42", "REQ-42"]},
                None,
                1,
            )

    def test_receipt_is_closed_and_bound_to_issuer_execution_and_authority(self) -> None:
        receipt = valid_receipt()
        self.assertEqual(
            receipt,
            contract.validate_receipt(receipt, "gpt-pro-codex-loop", EXECUTION_ID, DIGEST_THREE),
        )
        for changed in (
            {"unknown": True},
            {"issuer_skill": "other"},
            {"execution_id": "EXEC-ABCDEF123456"},
            {"authority_snapshot_digest": DIGEST_ONE},
            {"nonce": "a" * 31},
            {"issued_at_unix": True},
        ):
            with self.subTest(changed=changed), self.assertRaises(contract.ContractError):
                contract.validate_receipt(
                    valid_receipt(**changed), "gpt-pro-codex-loop", EXECUTION_ID, DIGEST_THREE
                )

    def test_receipt_requires_exactly_one_transaction_or_invocation_identity(self) -> None:
        invocation_receipt = valid_receipt()
        invocation_receipt.pop("transaction_id")
        invocation_receipt["invocation_id"] = "INV-1"
        self.assertEqual(
            invocation_receipt,
            contract.validate_receipt(
                invocation_receipt, "gpt-pro-codex-loop", EXECUTION_ID, DIGEST_THREE
            ),
        )
        for changed in ({"invocation_id": "INV-1"}, {"transaction_id": ""}):
            with self.subTest(changed=changed), self.assertRaises(contract.ContractError):
                contract.validate_receipt(
                    valid_receipt(**changed), "gpt-pro-codex-loop", EXECUTION_ID, DIGEST_THREE
                )

    def test_typed_edge_allowlist_is_closed(self) -> None:
        contract.validate_edge("code", "implements", "requirement")
        with self.assertRaises(contract.ContractError):
            contract.validate_edge("evidence", "implements", "requirement")


if __name__ == "__main__":
    unittest.main()
