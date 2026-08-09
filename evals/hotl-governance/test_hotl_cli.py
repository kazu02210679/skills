from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "hotl-governance" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hotl_contract as contract
import hotl_controller as controller
import hotl_governance as cli
import hotl_store as store


EXECUTION = "EXEC-123456789ABC"
SNAPSHOT = "sha256:" + "b" * 64
NONCE = "c" * 32
GPT_BINDING = {
    "conversation_url": "https://chatgpt.com/c/hotl-fixture",
    "model_label": "GPT-5.6 Sol",
    "plan_label": "Pro",
    "reasoning_label": "Pro",
    "run_id": "gpc-loop-hotl-fixture",
    "task_slug": "hotl-fixture",
}
AUTHORITY = contract.canonical_digest(GPT_BINDING)


def snapshot_tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class HotlCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir()
        self.inputs = Path(self.temporary.name) / "inputs"
        self.inputs.mkdir()
        self.execution = EXECUTION

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, name: str, value: object) -> Path:
        path = self.inputs / name
        path.write_bytes(contract.canonical_json_bytes(value))
        return path

    def _init(
        self,
        *,
        approval_mode: str = "agentic",
        host_approval_evidence_digest: str | None = None,
        execution: str = EXECUTION,
    ) -> dict[str, object]:
        requirements = self._write(
            f"requirements-{execution}.json", {"requirements": ["REQ-1"]}
        )
        policy = self._write(
            f"policy-{execution}.json",
            {
                "active_snapshot_digest": SNAPSHOT,
                "approval_mode": approval_mode,
                "authority_snapshot_digest": AUTHORITY,
                "cycle_id": 1,
                "execution_id": execution,
                "host_approval_evidence_digest": host_approval_evidence_digest,
                "receipt_nonce": NONCE,
                "schema_version": 1,
            },
        )
        return cli.main_json(
            [
                "init",
                "--repo",
                str(self.repository),
                "--execution",
                execution,
                "--policy",
                str(policy),
                "--requirements",
                str(requirements),
            ]
        )

    def _projection(self) -> dict[str, object]:
        result = cli.main_json(
            [
                "project",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--stdout",
            ]
        )
        self.assertTrue(result["ok"], result)
        return result["result"]["projection"]

    def _receipt(
        self,
        receipt_type: str,
        receipt_id: str,
        *,
        issuer: str | None = None,
        claims: dict[str, object] | None = None,
    ) -> dict[str, object]:
        projection = self._projection()
        issuer_by_type = {
            "requirements": "gpt-pro-codex-loop",
            "approval": "gpt-pro-codex-loop",
            "implementation": "codex",
            "verification": "hotl-local-verifier",
            "semantic_review": "gpt-pro-codex-loop",
            "final": "gpt-pro-codex-loop",
            "material_change": "gpt-pro-codex-loop",
            "stop": "gpt-pro-codex-loop",
        }
        frozen = receipt_type in {"requirements", "approval"}
        receipt_issuer = issuer or issuer_by_type[receipt_type]
        gpt_external = receipt_issuer == "gpt-pro-codex-loop" and receipt_type in {
            "requirements",
            "semantic_review",
            "final",
        }
        evidence_digest = controller.evidence_set_digest(
            str(projection["requirements_digest"]),
            projection["active_snapshot_digest"],
            projection["evidence_records"],
        )
        receipt = {
            "authority_snapshot_digest": AUTHORITY,
            "claims": claims or {},
            "cycle_id": None if frozen or gpt_external else projection["cycle_id"],
            "evidence_set_digest": None if frozen or gpt_external else evidence_digest,
            "execution_id": self.execution,
            "input_digest": str(projection["requirements_digest"])
            if frozen
            else evidence_digest,
            "issued_at_unix": 1,
            "issuer_skill": receipt_issuer,
            "issuer_version": "1",
            "nonce": NONCE,
            "output_digest": "sha256:" + hashlib.sha256(receipt_id.encode()).hexdigest(),
            "receipt_id": receipt_id,
            "receipt_schema_version": 1,
            "receipt_type": receipt_type,
            "requirements_digest": projection["requirements_digest"],
            "snapshot_digest": None if frozen else projection["active_snapshot_digest"],
            "transaction_id": "TXN-" + receipt_id,
        }
        if receipt["issuer_skill"] == "gpt-pro-codex-loop":
            receipt["binding"] = dict(GPT_BINDING)
        return receipt

    def _import(self, receipt: dict[str, object], name: str = "receipt.json") -> dict[str, object]:
        path = self._write(name, receipt)
        return cli.main_json(
            [
                "import-receipt",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--receipt",
                str(path),
            ]
        )

    def _evaluate(self, gate: str) -> dict[str, object]:
        return cli.main_json(
            [
                "evaluate",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--gate",
                gate,
            ]
        )

    def _record_proof(self) -> None:
        proof = self.repository / "proof.txt"
        proof.write_bytes(b"proof\n")
        digest = "sha256:" + hashlib.sha256(proof.read_bytes()).hexdigest()
        paths = store.resolve_run(self.repository, self.execution)
        events = store.load_events(paths)
        event = {
            "artifact_refs": [{"path": "proof.txt", "sha256": digest}],
            "event_id": "EVT-00000000E001",
            "execution_id": self.execution,
            "input_digest": SNAPSHOT,
            "issuer": {"id": "pytest", "kind": "tool", "version": "8"},
            "output_digest": digest,
            "payload": {
                "artifact_digest": digest,
                "cycle_id": self._projection()["cycle_id"],
                "evidence_id": "EVID-1",
                "snapshot_digest": self._projection()["active_snapshot_digest"],
                "test_id": "TEST-1",
            },
            "previous_event_hash": contract.canonical_digest(events[-1]),
            "result": "pass",
            "schema_version": 1,
            "sequence": len(events) + 1,
            "subject_ids": ["EVID-1", "TEST-1"],
            "timestamp": "2026-08-09T00:00:00Z",
            "type": "evidence_recorded",
        }
        result = cli.main_json(
            [
                "record",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--event",
                str(self._write("proof-event.json", event)),
            ]
        )
        self.assertTrue(result["ok"], result)

    def _reach_semantic_review(self) -> None:
        self._init()
        self.assertTrue(
            self._import(
                self._receipt("requirements", "RCP-REQ-SETUP"),
                "setup-requirements.json",
            )["ok"]
        )
        self.assertTrue(
            self._import(
                self._receipt("approval", "RCP-APP-SETUP"),
                "setup-approval.json",
            )["ok"]
        )
        self.assertTrue(self._evaluate("G1")["ok"])
        implementation_claims = {
            "edges": [
                {"edge": "implements", "source_id": "CODE-1", "target_id": "REQ-1"},
                {"edge": "verifies", "source_id": "TEST-1", "target_id": "REQ-1"},
                {"edge": "executes", "source_id": "CMD-1", "target_id": "TEST-1"},
                {"edge": "produces", "source_id": "CMD-1", "target_id": "EVID-1"},
                {"edge": "included_in", "source_id": "CODE-1", "target_id": "CHG-1"},
                {"edge": "included_in", "source_id": "TEST-1", "target_id": "CHG-1"},
            ],
            "nodes": [
                {"node_id": "CHG-1", "node_type": "change"},
                {"node_id": "CMD-1", "node_type": "command"},
                {"node_id": "CODE-1", "node_type": "code"},
                {"node_id": "EVID-1", "node_type": "evidence"},
                {"node_id": "TEST-1", "node_type": "test"},
            ],
        }
        self.assertTrue(
            self._import(
                self._receipt(
                    "implementation", "RCP-IMPL-SETUP", claims=implementation_claims
                ),
                "setup-implementation.json",
            )["ok"]
        )
        self.assertTrue(self._evaluate("G2")["ok"])
        self._record_proof()
        self.assertTrue(
            self._import(
                self._receipt(
                    "verification",
                    "RCP-VERIFY-SETUP",
                    claims={
                        "edges": [
                            {
                                "edge": "proves",
                                "source_id": "EVID-1",
                                "target_id": "TEST-1",
                            }
                        ]
                    },
                ),
                "setup-verification.json",
            )["ok"]
        )
        self.assertTrue(self._evaluate("G3")["ok"])

    def test_stable_command_set_and_parser_errors_never_raise_system_exit(self) -> None:
        self.assertEqual(
            (
                "init",
                "status",
                "record",
                "approve",
                "import-receipt",
                "evaluate",
                "project",
                "verify-log",
                "start-successor",
            ),
            cli.COMMANDS,
        )
        for argv in ([], ["unknown"], ["status"], ["evaluate", "--bogus"]):
            with self.subTest(argv=argv):
                result = cli.main_json(argv)
                self.assertFalse(result["ok"])
                self.assertEqual("ARGUMENT_ERROR", result["error"]["code"])

    def test_malformed_unhashable_policy_and_review_values_return_stable_envelopes(self) -> None:
        requirements = self._write(
            "bad-policy-requirements.json", {"requirements": ["REQ-1"]}
        )
        policy = self._write(
            "bad-policy.json",
            {
                "active_snapshot_digest": SNAPSHOT,
                "approval_mode": [],
                "authority_snapshot_digest": AUTHORITY,
                "cycle_id": 1,
                "execution_id": self.execution,
                "host_approval_evidence_digest": None,
                "receipt_nonce": NONCE,
                "schema_version": 1,
            },
        )
        invalid_policy = cli.main_json(
            [
                "init",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--policy",
                str(policy),
                "--requirements",
                str(requirements),
            ]
        )
        self.assertFalse(invalid_policy["ok"])
        self.assertEqual("INVALID_POLICY", invalid_policy["error"]["code"])

        self._init()
        malformed_review = self._receipt(
            "semantic_review",
            "RCP-MALFORMED-REVIEW",
            claims={
                "edges": [],
                "findings": [],
                "review_id": "REV-MALFORMED",
                "root_cause_ids": [{}],
                "status": "rejected",
            },
        )
        result = self._import(malformed_review, "malformed-review.json")
        self.assertFalse(result["ok"])
        self.assertEqual("INVALID_REVIEW", result["error"]["code"])

        unhashable_issuer = self._receipt("approval", "RCP-BAD-ISSUER")
        unhashable_issuer["issuer_skill"] = ["gpt-pro-codex-loop"]
        issuer_result = self._import(
            unhashable_issuer, "unhashable-issuer.json"
        )
        self.assertFalse(issuer_result["ok"])
        self.assertEqual("INVALID_SCHEMA", issuer_result["error"]["code"])

        unhashable_type = self._receipt("approval", "RCP-BAD-TYPE")
        unhashable_type["receipt_type"] = {"approval": True}
        type_result = self._import(unhashable_type, "unhashable-type.json")
        self.assertFalse(type_result["ok"])
        self.assertEqual("INVALID_SCHEMA", type_result["error"]["code"])

    def test_init_atomically_reaches_requirements_with_explicit_init_transition(self) -> None:
        result = self._init()
        self.assertTrue(result["ok"], result)
        self.assertEqual("REQUIREMENTS", result["result"]["state"])
        events = store.load_events(store.resolve_run(self.repository, self.execution))
        self.assertEqual(
            ["node_declared", "transition_committed"],
            [event["type"] for event in events],
        )

    def test_init_accepts_exact_external_requirements_artifact_binding(self) -> None:
        source_artifact = {
            "acceptance_criteria": [{"id": "AC-1", "criterion": "Pass."}],
            "requirements": [{"id": "REQ-1", "statement": "Bound."}],
            "schema_version": 1,
        }
        source_bytes = contract.canonical_json_bytes(source_artifact)
        source_digest = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
        requirements = self._write(
            "external-requirements.json",
            {
                "requirements": ["REQ-1"],
                "source_artifact": source_artifact,
                "source_digest": source_digest,
            },
        )
        policy = self._write(
            "external-policy.json",
            {
                "active_snapshot_digest": SNAPSHOT,
                "approval_mode": "agentic",
                "authority_snapshot_digest": AUTHORITY,
                "cycle_id": 1,
                "execution_id": self.execution,
                "host_approval_evidence_digest": None,
                "receipt_nonce": NONCE,
                "schema_version": 1,
            },
        )

        result = cli.main_json(
            [
                "init",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--policy",
                str(policy),
                "--requirements",
                str(requirements),
            ]
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(source_digest, self._projection()["requirements_digest"])
        self.assertEqual(
            source_bytes,
            (
                store.resolve_run(self.repository, self.execution).evidence
                / source_digest[7:]
            ).read_bytes(),
        )

    def test_init_rejects_incomplete_or_mismatched_external_requirements(self) -> None:
        source = {"requirements": [{"id": "REQ-1"}], "schema_version": 1}
        digest = contract.canonical_digest(source)
        cases = (
            {"requirements": ["REQ-1"], "source_digest": digest},
            {"requirements": ["REQ-1"], "source_artifact": source},
            {
                "requirements": ["REQ-1"],
                "source_artifact": source,
                "source_digest": "sha256:" + "d" * 64,
            },
            {
                "requirements": ["REQ-1"],
                "source_artifact": source,
                "source_digest": digest,
                "unknown": True,
            },
        )
        for index, value in enumerate(cases, 1):
            with self.subTest(index=index):
                execution = f"EXEC-0000000002{index:02d}"
                requirements = self._write(f"external-bad-{index}.json", value)
                policy = self._write(
                    f"external-bad-policy-{index}.json",
                    {
                        "active_snapshot_digest": SNAPSHOT,
                        "approval_mode": "agentic",
                        "authority_snapshot_digest": AUTHORITY,
                        "cycle_id": 1,
                        "execution_id": execution,
                        "host_approval_evidence_digest": None,
                        "receipt_nonce": NONCE,
                        "schema_version": 1,
                    },
                )
                result = cli.main_json(
                    [
                        "init",
                        "--repo",
                        str(self.repository),
                        "--execution",
                        execution,
                        "--policy",
                        str(policy),
                        "--requirements",
                        str(requirements),
                    ]
                )
                self.assertFalse(result["ok"], result)
                self.assertFalse(
                    store.resolve_run(self.repository, execution).root.exists()
                )

    def test_status_is_read_only_and_lists_only_executable_safe_commands(self) -> None:
        self._init()
        before = snapshot_tree(self.repository / ".hotl")
        result = cli.main_json(
            ["status", "--repo", str(self.repository), "--execution", self.execution]
        )
        after = snapshot_tree(self.repository / ".hotl")
        self.assertEqual(before, after)
        self.assertEqual(["import-receipt"], result["result"]["next_commands"])

    def test_status_advertises_approve_only_for_a_configured_safe_channel(self) -> None:
        self._init(approval_mode="offline_manual")
        result = cli.main_json(
            ["status", "--repo", str(self.repository), "--execution", self.execution]
        )
        self.assertEqual(
            ["approve", "import-receipt"], result["result"]["next_commands"]
        )

    def test_generic_record_rejects_every_privileged_event_without_mutation(self) -> None:
        self._init()
        paths = store.resolve_run(self.repository, self.execution)
        prior = store.load_events(paths)[-1]
        before = paths.events.read_bytes()
        for index, event_type in enumerate(
            (
                "node_declared",
                "edge_declared",
                "snapshot_activated",
                "evidence_invalidated",
                "review_recorded",
                "finding_recorded",
                "receipt_imported",
                "transition_committed",
            ),
            1,
        ):
            fake = {
                "artifact_refs": [],
                "event_id": f"EVT-F{index:011X}",
                "execution_id": self.execution,
                "input_digest": AUTHORITY,
                "issuer": {"id": "human", "kind": "tool", "version": "1"},
                "output_digest": SNAPSHOT,
                "payload": {},
                "previous_event_hash": contract.canonical_digest(prior),
                "result": "pass",
                "schema_version": 1,
                "sequence": 3,
                "subject_ids": [],
                "timestamp": "now",
                "type": event_type,
            }
            result = cli.main_json(
                [
                    "record",
                    "--repo",
                    str(self.repository),
                    "--execution",
                    self.execution,
                    "--event",
                    str(self._write(f"fake-{index}.json", fake)),
                ]
            )
            self.assertEqual(
                "PRIVILEGED_EVENT_REQUIRES_RECEIPT", result["error"]["code"]
            )
        self.assertEqual(before, paths.events.read_bytes())

    def test_wrong_receipt_type_issuer_and_all_live_bindings_fail_closed(self) -> None:
        self._init()
        paths = store.resolve_run(self.repository, self.execution)
        base = self._receipt("implementation", "RCP-IMPL-BAD", claims={"edges": [], "nodes": []})
        cases = (
            {"issuer_skill": "gpt-pro-codex-loop"},
            {"issuer_version": "999"},
            {"nonce": "d" * 32},
            {"authority_snapshot_digest": "sha256:" + "d" * 64},
            {"snapshot_digest": "sha256:" + "d" * 64},
            {"evidence_set_digest": "sha256:" + "d" * 64},
            {"cycle_id": 99},
        )
        before = paths.events.read_bytes()
        for index, changed in enumerate(cases):
            with self.subTest(changed=changed):
                result = self._import(base | changed, f"bad-{index}.json")
                self.assertFalse(result["ok"])
        self.assertEqual(before, paths.events.read_bytes())

    def test_replayed_receipt_is_rejected(self) -> None:
        self._init()
        receipt = self._receipt("requirements", "RCP-REQ-1")
        self.assertTrue(self._import(receipt, "req-1.json")["ok"])
        result = self._import(receipt, "req-1-replay.json")
        self.assertFalse(result["ok"])
        self.assertEqual("REPLAYED_RECEIPT", result["error"]["code"])

    def test_gpt_receipt_binding_is_closed_and_required(self) -> None:
        self._init()
        receipt = self._receipt("requirements", "RCP-GPT-BINDING")

        missing = dict(receipt)
        del missing["binding"]
        self.assertEqual(
            "INVALID_RECEIPT_BINDING",
            self._import(missing, "gpt-binding-missing.json")["error"]["code"],
        )

        wrong_run = dict(receipt)
        wrong_run["binding"] = dict(receipt["binding"], run_id="gpc-loop-other")
        self.assertEqual(
            "INVALID_RECEIPT_BINDING",
            self._import(wrong_run, "gpt-binding-wrong-run.json")["error"]["code"],
        )

        unknown = dict(receipt)
        unknown["binding"] = dict(receipt["binding"], model_policy="PRO_CLASS")
        self.assertEqual(
            "INVALID_FIELDS",
            self._import(unknown, "gpt-binding-unknown.json")["error"]["code"],
        )

    def test_gpt_requirements_receipt_keeps_frozen_null_admission_bindings(self) -> None:
        self._init()
        requirements = self._receipt("requirements", "RCP-GPT-REQ-LIVE")
        self.assertIsNone(requirements["evidence_set_digest"])
        self.assertIsNone(requirements["cycle_id"])
        self.assertTrue(self._import(requirements, "gpt-req-live.json")["ok"])
        frozen_record = self._projection()["receipt_records"]["RCP-GPT-REQ-LIVE"]
        self.assertIsNone(frozen_record["snapshot_digest"])
        self.assertIsNone(frozen_record["evidence_set_digest"])
        self.assertIsNone(frozen_record["cycle_id"])

    def test_gpt_review_and_final_receipts_receive_current_live_admission_bindings(self) -> None:
        self._reach_semantic_review()
        before = self._projection()
        current_evidence = controller.evidence_set_digest(
            str(before["requirements_digest"]),
            before["active_snapshot_digest"],
            before["evidence_records"],
        )
        review = self._receipt(
            "semantic_review",
            "RCP-GPT-REV-LIVE",
            claims={
                "edges": [],
                "findings": [],
                "review_id": "REV-GPT-LIVE",
                "root_cause_ids": [],
                "status": "accepted",
            },
        )
        self.assertIsNone(review["evidence_set_digest"])
        self.assertIsNone(review["cycle_id"])
        self.assertTrue(self._import(review, "gpt-rev-live.json")["ok"])
        final = self._receipt("final", "RCP-GPT-FINAL-LIVE")
        self.assertTrue(self._import(final, "gpt-final-live.json")["ok"])
        records = self._projection()["receipt_records"]
        for receipt_id in ("RCP-GPT-REV-LIVE", "RCP-GPT-FINAL-LIVE"):
            self.assertEqual(before["cycle_id"], records[receipt_id]["cycle_id"])
            self.assertEqual(
                current_evidence, records[receipt_id]["evidence_set_digest"]
            )

    def test_privileged_receipt_validation_and_append_share_one_run_lock(self) -> None:
        self._init()
        receipt = self._receipt("requirements", "RCP-LOCKED-1")
        paths = store.resolve_run(self.repository, self.execution)
        real_validate = controller.contract.validate_receipt
        observed: list[str] = []

        def guarded_validate(*args: object, **kwargs: object) -> dict[str, object]:
            self.assertTrue(paths.lock.is_file())
            observed.append("validate")
            return real_validate(*args, **kwargs)

        real_append = controller.store.append_events

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
            patch.object(
                controller.contract, "validate_receipt", side_effect=guarded_validate
            ),
            patch.object(controller.store, "append_events", side_effect=guarded_append),
        ):
            result = self._import(receipt, "locked-receipt.json")
        self.assertTrue(result["ok"], result)
        self.assertEqual(["validate", "append"], observed)

    def test_approve_rejects_unsigned_local_assertion_in_agentic_mode(self) -> None:
        self._init()
        assertion = self._receipt(
            "approval", "RCP-SELF-1", issuer="trusted-local-operator"
        )
        assertion["claims"] = {"approval_mode": "offline_manual"}
        result = cli.main_json(
            [
                "approve",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--evidence",
                str(self._write("unsafe-approval.json", assertion)),
            ]
        )
        self.assertFalse(result["ok"])
        self.assertEqual("UNTRUSTED_LOCAL_APPROVAL", result["error"]["code"])

    def test_approve_requires_host_or_explicit_manual_channel_not_gpt_import(self) -> None:
        self._init()
        receipt = self._receipt("approval", "RCP-GPT-APPROVAL")
        path = self._write("gpt-approval.json", receipt)
        approval_result = cli.main_json(
            [
                "approve",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--evidence",
                str(path),
            ]
        )
        self.assertFalse(approval_result["ok"])
        self.assertEqual(
            "APPROVAL_EVIDENCE_REQUIRED", approval_result["error"]["code"]
        )
        import_result = cli.main_json(
            [
                "import-receipt",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--receipt",
                str(path),
            ]
        )
        self.assertTrue(import_result["ok"], import_result)

    def test_host_approval_requires_frozen_authority_and_target_evidence_digest(self) -> None:
        target = contract.canonical_digest({"requirements": ["REQ-1"]})
        evidence = {
            "approval_schema_version": 1,
            "authority_snapshot_digest": AUTHORITY,
            "decision": "approve",
            "execution_id": self.execution,
            "host_id": "trusted-host-tool",
            "target_digest": target,
        }
        self._init(
            host_approval_evidence_digest=contract.canonical_digest(evidence)
        )
        receipt = self._receipt(
            "approval",
            "RCP-HOST-1",
            issuer="hotl-host-approval",
            claims={"approval_evidence": evidence},
        )
        bad = dict(receipt) | {
            "claims": {
                "approval_evidence": evidence
                | {"target_digest": "sha256:" + "d" * 64}
            }
        }
        rejected = cli.main_json(
            [
                "approve",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--evidence",
                str(self._write("host-bad.json", bad)),
            ]
        )
        self.assertEqual("HOST_APPROVAL_MISMATCH", rejected["error"]["code"])
        accepted = cli.main_json(
            [
                "approve",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--evidence",
                str(self._write("host-good.json", receipt)),
            ]
        )
        self.assertTrue(accepted["ok"], accepted)

    def test_host_approval_rejects_invalid_provenance_identity_even_when_prebound(self) -> None:
        target = contract.canonical_digest({"requirements": ["REQ-1"]})
        evidence = {
            "approval_schema_version": 1,
            "authority_snapshot_digest": AUTHORITY,
            "decision": "approve",
            "execution_id": self.execution,
            "host_id": {"caller": "worker"},
            "target_digest": target,
        }
        self._init(
            host_approval_evidence_digest=contract.canonical_digest(evidence)
        )
        receipt = self._receipt(
            "approval",
            "RCP-HOST-INVALID",
            issuer="hotl-host-approval",
            claims={"approval_evidence": evidence},
        )
        result = cli.main_json(
            [
                "approve",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--evidence",
                str(self._write("host-invalid-provenance.json", receipt)),
            ]
        )
        self.assertFalse(result["ok"])
        self.assertEqual("INVALID_HOST_APPROVAL", result["error"]["code"])

    def test_offline_manual_approval_is_explicitly_policy_and_target_bound(self) -> None:
        self._init(approval_mode="offline_manual")
        receipt = self._receipt(
            "approval",
            "RCP-OFFLINE-1",
            issuer="trusted-local-operator",
            claims={"approval_mode": "offline_manual"},
        )
        wrong_target = receipt | {
            "requirements_digest": "sha256:" + "d" * 64,
            "input_digest": "sha256:" + "d" * 64,
        }
        rejected = cli.main_json(
            [
                "approve",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--evidence",
                str(self._write("offline-bad.json", wrong_target)),
            ]
        )
        self.assertEqual("REQUIREMENTS_MISMATCH", rejected["error"]["code"])
        accepted = cli.main_json(
            [
                "approve",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--evidence",
                str(self._write("offline-good.json", receipt)),
            ]
        )
        self.assertTrue(accepted["ok"], accepted)

    def test_failed_gate_emits_no_transition(self) -> None:
        self._init()
        paths = store.resolve_run(self.repository, self.execution)
        before = paths.events.read_bytes()
        result = self._evaluate("G1")
        self.assertFalse(result["ok"])
        self.assertEqual("GATE_FAILED", result["error"]["code"])
        self.assertEqual(before, paths.events.read_bytes())

    def test_all_four_gates_complete_only_after_bound_evidence(self) -> None:
        self._init()
        self.assertTrue(self._import(self._receipt("requirements", "RCP-REQ-1"), "requirements.json")["ok"])
        self.assertTrue(self._import(self._receipt("approval", "RCP-APP-1"), "approval.json")["ok"])
        self.assertEqual("IMPLEMENT", self._evaluate("G1")["result"]["state"])

        implementation_claims = {
            "edges": [
                {"edge": "implements", "source_id": "CODE-1", "target_id": "REQ-1"},
                {"edge": "verifies", "source_id": "TEST-1", "target_id": "REQ-1"},
                {"edge": "executes", "source_id": "CMD-1", "target_id": "TEST-1"},
                {"edge": "produces", "source_id": "CMD-1", "target_id": "EVID-1"},
                {"edge": "included_in", "source_id": "CODE-1", "target_id": "CHG-1"},
                {"edge": "included_in", "source_id": "TEST-1", "target_id": "CHG-1"},
            ],
            "nodes": [
                {"node_id": "CHG-1", "node_type": "change"},
                {"node_id": "CMD-1", "node_type": "command"},
                {"node_id": "CODE-1", "node_type": "code"},
                {"node_id": "EVID-1", "node_type": "evidence"},
                {"node_id": "TEST-1", "node_type": "test"},
            ],
        }
        self.assertTrue(self._import(self._receipt("implementation", "RCP-IMPL-1", claims=implementation_claims), "implementation.json")["ok"])
        self.assertEqual("LOCAL_VERIFY", self._evaluate("G2")["result"]["state"])

        self._record_proof()
        verification_claims = {
            "edges": [
                {"edge": "proves", "source_id": "EVID-1", "target_id": "TEST-1"}
            ]
        }
        self.assertTrue(self._import(self._receipt("verification", "RCP-VERIFY-1", claims=verification_claims), "verification.json")["ok"])
        self.assertEqual("SEMANTIC_REVIEW", self._evaluate("G3")["result"]["state"])

        review_claims = {
            "edges": [
                {"edge": "supports", "source_id": "EVID-1", "target_id": "REV-1"},
                {"edge": "reviews", "source_id": "REV-1", "target_id": "REQ-1"},
            ],
            "findings": [],
            "review_id": "REV-1",
            "root_cause_ids": [],
            "status": "accepted",
        }
        self.assertTrue(self._import(self._receipt("semantic_review", "RCP-REV-1", claims=review_claims), "review.json")["ok"])
        self.assertTrue(self._import(self._receipt("final", "RCP-FINAL-1"), "final.json")["ok"])
        result = self._evaluate("G4")
        self.assertTrue(result["ok"], result)
        self.assertEqual("COMPLETE", result["result"]["state"])

    def test_stale_receipt_is_rejected_after_snapshot_change(self) -> None:
        self._init()
        stale = self._receipt("verification", "RCP-STALE-1", claims={"edges": []})
        controller.activate_snapshot(
            self.repository, self.execution, "sha256:" + "e" * 64
        )
        result = self._import(stale, "stale.json")
        self.assertFalse(result["ok"])
        self.assertEqual("STALE_RECEIPT", result["error"]["code"])

    def test_null_snapshot_terminal_receipts_can_stop_after_snapshot_activation(self) -> None:
        for index, (receipt_type, gate) in enumerate(
            (("stop", "STOP"), ("material_change", "MATERIAL_CHANGE")), 1
        ):
            with self.subTest(receipt_type=receipt_type):
                self.execution = f"EXEC-00000000010{index}"
                self._init(execution=self.execution)
                receipt = self._receipt(
                    receipt_type, f"RCP-NULL-SNAPSHOT-{index}"
                )
                receipt["snapshot_digest"] = None
                imported = self._import(
                    receipt, f"null-snapshot-{receipt_type}.json"
                )
                self.assertTrue(imported["ok"], imported)
                transitioned = self._evaluate(gate)
                self.assertTrue(transitioned["ok"], transitioned)
                self.assertEqual("STOPPED", transitioned["result"]["state"])

    def test_rejected_review_receipt_roots_and_findings_are_one_atomic_batch(self) -> None:
        self._reach_semantic_review()
        receipt = self._receipt(
            "semantic_review",
            "RCP-REJECTED-1",
            claims={
                "edges": [],
                "findings": [
                    {
                        "finding_id": "FIND-1",
                        "root_cause_id": "ROOT-1",
                        "status": "open",
                    }
                ],
                "review_id": "REV-REJECTED-1",
                "root_cause_ids": ["ROOT-1"],
                "status": "rejected",
            },
        )
        real_append = controller.store.append_events
        batches: list[list[str]] = []

        def capture(
            paths: store.RunPaths,
            events: list[dict[str, object]],
            state: dict[str, object],
            artifacts: dict[str, bytes],
        ) -> None:
            self.assertTrue(paths.lock.is_file())
            batches.append([str(event["type"]) for event in events])
            real_append(paths, events, state, artifacts)

        with patch.object(controller.store, "append_events", side_effect=capture):
            result = self._import(receipt, "rejected-review.json")
        self.assertTrue(result["ok"], result)
        self.assertEqual(
            [["receipt_imported", "node_declared", "review_recorded", "finding_recorded"]],
            batches,
        )
        projection = self._projection()
        self.assertEqual(1, len(projection["valid_review_rounds"]))

        replayed = self._import(receipt, "rejected-review-replay.json")
        self.assertEqual("REPLAYED_RECEIPT", replayed["error"]["code"])

    def test_recovery_is_read_only_and_a_mutation_hard_stop(self) -> None:
        self._init()
        paths = store.resolve_run(self.repository, self.execution)
        state = json.loads(paths.state.read_text(encoding="utf-8"))
        state["event_count"] = 99
        paths.state.write_bytes(contract.canonical_json_bytes(state))
        orphan = paths.transactions / "orphan"
        orphan.mkdir()
        before = snapshot_tree(self.repository / ".hotl")
        status = cli.main_json(
            ["status", "--repo", str(self.repository), "--execution", self.execution]
        )
        after = snapshot_tree(self.repository / ".hotl")
        self.assertEqual(before, after)
        self.assertEqual("RECOVERY_REQUIRED", status["result"]["state"])
        result = self._import(
            {
                "receipt_schema_version": 1,
                "receipt_type": "requirements",
            },
            "recovery-receipt.json",
        )
        self.assertEqual("RECOVERY_REQUIRED", result["error"]["code"])
        self.assertTrue(orphan.is_dir())

    def test_successor_is_immediately_verifiable_and_can_later_advance_g1(self) -> None:
        self._init()
        self.assertTrue(
            self._import(self._receipt("stop", "RCP-STOP-1"), "stop.json")["ok"]
        )
        self.assertEqual("STOPPED", self._evaluate("STOP")["result"]["state"])
        predecessor = store.resolve_run(self.repository, self.execution)
        before_events = predecessor.events.read_bytes()
        before_state = predecessor.state.read_bytes()
        binding = {
            "predecessor_execution_id": self.execution,
            "supersedes": [{"new_id": "REQ-2", "old_id": "REQ-1"}],
        }
        digest = store.store_evidence(
            predecessor, contract.canonical_json_bytes(binding)
        )
        lineage = self._write(
            "lineage.json", binding | {"lineage_receipt_digest": digest}
        )
        successor = "EXEC-ABCDEF123456"
        successor_requirements_value = {"requirements": ["REQ-2"]}
        successor_requirements = self._write(
            "successor-requirements.json", successor_requirements_value
        )
        policy = self._write(
            "successor-policy.json",
            {
                "active_snapshot_digest": SNAPSHOT,
                "approval_mode": "agentic",
                "authority_snapshot_digest": AUTHORITY,
                "cycle_id": 1,
                "execution_id": successor,
                "host_approval_evidence_digest": None,
                "initial_state": "INIT",
                "receipt_nonce": NONCE,
                "requirements_digest": contract.canonical_digest(
                    successor_requirements_value
                ),
                "schema_version": 1,
            },
        )

        result = cli.main_json(
            [
                "start-successor",
                "--repo",
                str(self.repository),
                "--predecessor",
                self.execution,
                "--lineage",
                str(lineage),
                "--policy",
                str(policy),
                "--requirements",
                str(successor_requirements),
            ]
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual("REQUIREMENTS", result["result"]["state"])
        self.assertEqual(before_events, predecessor.events.read_bytes())
        self.assertEqual(before_state, predecessor.state.read_bytes())
        verification = cli.main_json(
            [
                "verify-log",
                "--repo",
                str(self.repository),
                "--execution",
                successor,
            ]
        )
        self.assertTrue(verification["ok"], verification)
        self.assertTrue(verification["result"]["log_integrity"])
        self.assertTrue(verification["result"]["projection_determinism"])
        self.assertTrue(verification["result"]["persisted_projection_integrity"])
        self.assertTrue(verification["result"]["immutable_evidence_integrity"])

        self.execution = successor
        self.assertTrue(
            self._import(
                self._receipt("requirements", "RCP-SUCCESSOR-REQ"),
                "successor-requirements-receipt.json",
            )["ok"]
        )
        self.assertTrue(
            self._import(
                self._receipt("approval", "RCP-SUCCESSOR-APP"),
                "successor-approval-receipt.json",
            )["ok"]
        )
        advanced = self._evaluate("G1")
        self.assertTrue(advanced["ok"], advanced)
        self.assertEqual("IMPLEMENT", advanced["result"]["state"])

    def test_project_stdout_is_deterministic_and_read_only(self) -> None:
        self._init()
        before = snapshot_tree(self.repository / ".hotl")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(
                [
                    "project",
                    "--repo",
                    str(self.repository),
                    "--execution",
                    self.execution,
                    "--stdout",
                ]
            )
        after = snapshot_tree(self.repository / ".hotl")
        self.assertEqual(0, exit_code)
        self.assertTrue(json.loads(output.getvalue())["ok"])
        self.assertEqual(before, after)

    def test_verify_log_separates_historical_observation_from_integrity(self) -> None:
        self._init()
        implementation = self._receipt(
            "implementation",
            "RCP-IMPL-HISTORY",
            claims={
                "edges": [],
                "nodes": [
                    {"node_id": "EVID-1", "node_type": "evidence"},
                    {"node_id": "TEST-1", "node_type": "test"},
                ],
            },
        )
        self.assertTrue(self._import(implementation, "history-impl.json")["ok"])
        self._record_proof()
        controller.activate_snapshot(
            self.repository, self.execution, "sha256:" + "f" * 64
        )
        (self.repository / "proof.txt").write_bytes(b"changed later\n")

        result = cli.main_json(
            [
                "verify-log",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
            ]
        )

        report = result["result"]
        self.assertTrue(report["log_integrity"])
        self.assertTrue(report["projection_determinism"])
        self.assertTrue(report["immutable_evidence_integrity"])
        self.assertTrue(report["current_snapshot_integrity"])
        self.assertEqual(1, report["historical_observations_checked"])

    def test_verify_log_detects_a_missing_referenced_immutable_receipt(self) -> None:
        self._init()
        receipt = self._receipt("requirements", "RCP-MISSING-EVIDENCE")
        self.assertTrue(self._import(receipt, "missing-evidence-source.json")["ok"])
        digest = "sha256:" + hashlib.sha256(
            contract.canonical_json_bytes(receipt)
        ).hexdigest()
        paths = store.resolve_run(self.repository, self.execution)
        (paths.evidence / digest[7:]).unlink()

        result = cli.main_json(
            [
                "verify-log",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
            ]
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["result"]["immutable_evidence_integrity"])
        self.assertIn(
            digest + ":MISSING",
            result["result"]["immutable_evidence_findings"],
        )

    def test_verify_log_detects_canonical_persisted_projection_tampering_read_only(self) -> None:
        self._init()
        paths = store.resolve_run(self.repository, self.execution)
        state = json.loads(paths.state.read_text(encoding="utf-8"))
        state["projection"]["state"] = "IMPLEMENT"
        paths.state.write_bytes(contract.canonical_json_bytes(state))
        before = snapshot_tree(self.repository / ".hotl")

        result = cli.main_json(
            [
                "verify-log",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
            ]
        )

        self.assertTrue(result["ok"], result)
        report = result["result"]
        self.assertTrue(report["log_integrity"])
        self.assertTrue(report["projection_replay_determinism"])
        self.assertFalse(report["persisted_projection_integrity"])
        self.assertFalse(report["projection_determinism"])
        self.assertIn(
            "PERSISTED_PROJECTION_MISMATCH", report["projection_findings"]
        )
        self.assertEqual(before, snapshot_tree(self.repository / ".hotl"))


if __name__ == "__main__":
    unittest.main()
