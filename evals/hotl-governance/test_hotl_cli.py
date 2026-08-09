from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "hotl-governance" / "scripts"
GPT_SCRIPTS = ROOT / "skills" / "gpt-pro-codex-loop" / "scripts"
SOL_SCRIPTS = ROOT / "skills" / "orchestrate-gpt-pro-sol-advisor" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(GPT_SCRIPTS))
sys.path.insert(0, str(SOL_SCRIPTS))

import gpc_loop_controller as gpt_controller
import hotl_contract as contract
import hotl_controller as controller
import hotl_governance as cli
import hotl_store as store
import governance_receipt as sol_receipts


EXECUTION = "EXEC-C6EBD51734DE"
SNAPSHOT = "sha256:" + "b" * 64
NONCE = "d6869e970ce7ce7dec3b0ca23b9e282e"
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
        self.authority_snapshot_digest = AUTHORITY
        self.receipt_nonce = NONCE
        self.gpt_binding = dict(GPT_BINDING)
        self.gpt_repository: Path | None = None
        self.gpt_task_slug: str | None = None

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, name: str, value: object) -> Path:
        path = self.inputs / name
        path.write_bytes(contract.canonical_json_bytes(value))
        return path

    def _export_frozen_gpt_requirements(
        self,
    ) -> tuple[dict[str, object], dict[str, object], bytes]:
        gpt_repository = Path(self.temporary.name) / "gpt-repository"
        gpt_repository.mkdir()
        for arguments in (
            ("init",),
            ("config", "user.email", "hotl-e2e@example.invalid"),
            ("config", "user.name", "HOTL E2E"),
            ("config", "core.autocrlf", "false"),
            (
                "config",
                "core.excludesFile",
                str(gpt_repository / ".git" / "info" / "exclude"),
            ),
        ):
            subprocess.run(
                ["git", *arguments],
                cwd=gpt_repository,
                check=True,
                capture_output=True,
            )
        (gpt_repository / "README.md").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=gpt_repository, check=True)
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=gpt_repository,
            check=True,
            capture_output=True,
        )

        task_slug = "hotl-e2e"
        request = self.inputs / "gpt-request.txt"
        context = self.inputs / "gpt-context.txt"
        request.write_text("Implement deterministic behavior.\n", encoding="utf-8")
        context.write_text("The repository uses Python.\n", encoding="utf-8")
        gpt_controller.initialize_run(
            gpt_repository,
            task_slug,
            request,
            context,
            [],
            "PRO_CLASS",
            None,
        )
        attempt = gpt_controller.prepare_requirements(gpt_repository, task_slug)
        expected = gpt_controller.load_json(Path(attempt["expected_header_path"]))
        requirements = {
            "acceptance_criteria": [
                {
                    "criterion": "The focused test passes.",
                    "id": "AC-1",
                    "required_evidence": "Focused unittest output.",
                }
            ],
            "behavior_changed": False,
            "change_reason": "Initial requirements.",
            "constraints": ["standard library"],
            "decision": "PLAN_READY",
            "design_direction": ["Keep the implementation small."],
            "in_scope": ["example.py"],
            "objective": "Implement deterministic behavior.",
            "open_questions": [],
            "out_of_scope": ["deployment"],
            "prior_evidence_invalidated": False,
            "public_contract_changed": False,
            "requirements": [
                {"id": "REQ-1", "statement": "Behavior is deterministic."}
            ],
            "requirements_revision": 1,
            "review_round_reset": False,
            "risk_items": [
                {
                    "required_mitigation": "Require AC-1 evidence.",
                    "id": "RISK-1",
                    "risk": "Evidence may be incomplete.",
                }
            ],
            "schema_version": 1,
            "scope_changed": False,
            "supersedes_digest": None,
            "user_approval_received": False,
            "user_approval_required": False,
            "verification_strategy": ["Run the focused unittest."],
        }
        response = self.inputs / "gpt-requirements.raw.md"
        response.write_text(
            "```json\n"
            + json.dumps(
                {**expected, "payload": requirements},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n```\n",
            encoding="utf-8",
        )
        gpt_controller.accept_requirements(
            gpt_repository,
            task_slug,
            response,
            "https://chatgpt.com/c/hotl-e2e",
            "GPT-5.6 Sol",
            "Pro",
            "Pro",
        )
        receipt = gpt_controller.export_governance_receipt(
            gpt_repository, task_slug, "requirements"
        )
        run = gpt_repository / ".ai-pro-loop" / task_slug
        receipt_bytes = (run / "governance-receipt-requirements.json").read_bytes()
        requirements_bytes = (run / "requirements.json").read_bytes()
        requirements_artifact = gpt_controller.validate_packet.strict_json_loads(
            requirements_bytes.decode("utf-8")
        )
        self.assertIsInstance(requirements_artifact, dict)
        self.assertEqual(contract.canonical_json_bytes(receipt), receipt_bytes)
        self.assertEqual(
            receipt["requirements_digest"],
            "sha256:" + hashlib.sha256(requirements_bytes).hexdigest(),
        )
        self.gpt_repository = gpt_repository
        self.gpt_task_slug = task_slug
        return receipt, requirements_artifact, receipt_bytes

    def _export_authoritative_gpt_review_and_final(
        self,
    ) -> tuple[dict[str, object], bytes, dict[str, object], bytes]:
        self.assertIsNotNone(self.gpt_repository)
        self.assertIsNotNone(self.gpt_task_slug)
        repository = self.gpt_repository
        task_slug = self.gpt_task_slug
        assert repository is not None
        assert task_slug is not None
        (repository / "example.py").write_text("value = 1\n", encoding="utf-8")
        evidence = self.inputs / "gpt-local-evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "acceptance_evidence": {"AC-1": ["Focused unittest passed."]},
                    "changed_file_intents": {
                        "example.py": "Implement deterministic behavior."
                    },
                    "diff_evidence": ["example.py implements AC-1."],
                    "intent_summary": "Implement AC-1.",
                    "omissions": [],
                    "schema_version": 1,
                    "test_commands": [
                        {
                            "command": "python -m unittest test_example.py -v",
                            "outcome": "PASS",
                            "output_summary": "1 test passed.",
                        }
                    ],
                    "unresolved_risks_or_blockers": [],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        report = gpt_controller.build_report(repository, task_slug, evidence)
        attempt = gpt_controller.prepare_review(repository, task_slug)
        expected = gpt_controller.load_json(Path(attempt["expected_header_path"]))
        state = gpt_controller.load_json(
            repository / ".ai-pro-loop" / task_slug / "state.json"
        )
        review_response = self.inputs / "gpt-review.raw.md"
        review_response.write_text(
            "```json\n"
            + json.dumps(
                {
                    **expected,
                    "payload": {
                        "acceptance_results": {
                            "AC-1": {
                                "evidence": "Focused unittest passed.",
                                "status": "PASS",
                            }
                        },
                        "decision": "PASS",
                        "findings": [],
                        "next_instruction": "Run final verification.",
                        "requirements_digest": state["active_requirements_digest"],
                        "reviewed_snapshot_digest": report["snapshot_digest"],
                        "schema_version": 1,
                        "scope_violations": [],
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n```\n",
            encoding="utf-8",
        )
        gpt_controller.accept_review(
            repository,
            task_slug,
            review_response,
            str(state["bound_conversation_url"]),
            "GPT-5.6 Sol",
            "Pro",
            "Pro",
        )
        review = gpt_controller.export_governance_receipt(
            repository, task_slug, "review"
        )
        run = repository / ".ai-pro-loop" / task_slug
        review_bytes = (run / "governance-receipt-review.json").read_bytes()
        self.assertEqual(contract.canonical_json_bytes(review), review_bytes)

        verified = gpt_controller.final_verify(repository, task_slug)
        self.assertEqual("COMPLETE", verified["phase"])
        final = gpt_controller.export_governance_receipt(
            repository, task_slug, "final"
        )
        final_bytes = (run / "governance-receipt-final.json").read_bytes()
        self.assertEqual(contract.canonical_json_bytes(final), final_bytes)
        self.assertEqual(review["snapshot_digest"], final["snapshot_digest"])
        return review, review_bytes, final, final_bytes

    def _init_from_gpt_requirements(
        self,
        exported: tuple[dict[str, object], dict[str, object], bytes] | None = None,
        *,
        active_snapshot_digest: str = SNAPSHOT,
    ) -> dict[str, object]:
        receipt, requirements_artifact, receipt_bytes = (
            exported or self._export_frozen_gpt_requirements()
        )
        self.execution = str(receipt["execution_id"])
        self.authority_snapshot_digest = str(receipt["authority_snapshot_digest"])
        self.receipt_nonce = str(receipt["nonce"])
        self.gpt_binding = dict(receipt["binding"])
        requirements = self._write(
            "gpt-requirements.json",
            {
                "requirements": sorted(
                    item["id"] for item in requirements_artifact["requirements"]
                ),
                "source_artifact": requirements_artifact,
                "source_digest": receipt["requirements_digest"],
            },
        )
        policy = self._write(
            "gpt-policy.json",
            {
                "active_snapshot_digest": active_snapshot_digest,
                "approval_mode": "agentic",
                "authority_snapshot_digest": self.authority_snapshot_digest,
                "cycle_id": 1,
                "execution_id": self.execution,
                "host_approval_evidence_digest": None,
                "receipt_nonce": self.receipt_nonce,
                "required_verification_argv": [[sys.executable, "-c", "print('verified')"]],
                "schema_version": 1,
            },
        )
        initialized = cli.main_json(
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
        self.assertTrue(initialized["ok"], initialized)
        receipt_path = self.inputs / "gpt-requirements-receipt.json"
        receipt_path.write_bytes(receipt_bytes)
        paths = store.resolve_run(self.repository, self.execution)
        events = store.load_events(paths)
        privileged_attempt = self._write(
            "generic-receipt-attempt.json",
            {
                "artifact_refs": [],
                "event_id": "EVT-00000000E2E0",
                "execution_id": self.execution,
                "input_digest": "sha256:" + hashlib.sha256(receipt_bytes).hexdigest(),
                "issuer": {
                    "id": "gpt-pro-codex-loop",
                    "kind": "skill",
                    "version": "1",
                },
                "output_digest": str(receipt["output_digest"]),
                "payload": {"receipt_id": receipt["receipt_id"]},
                "previous_event_hash": contract.canonical_digest(events[-1]),
                "result": "pass",
                "schema_version": 1,
                "sequence": len(events) + 1,
                "subject_ids": [receipt["receipt_id"]],
                "timestamp": "2026-08-09T00:00:00Z",
                "type": "receipt_imported",
            },
        )
        rejected_generic = cli.main_json(
            [
                "record",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--event",
                str(privileged_attempt),
            ]
        )
        self.assertFalse(rejected_generic["ok"], rejected_generic)
        self.assertEqual(
            "PRIVILEGED_EVENT_REQUIRES_RECEIPT",
            rejected_generic["error"]["code"],
        )
        imported = cli.main_json(
            [
                "import-receipt",
                "--repo",
                str(self.repository),
                "--execution",
                self.execution,
                "--receipt",
                str(receipt_path),
            ]
        )
        self.assertTrue(imported["ok"], imported)
        return receipt

    def _init(
        self,
        *,
        approval_mode: str = "agentic",
        host_approval_evidence_digest: str | None = None,
        required_verification_argv: list[list[str]] | None = None,
        execution: str = EXECUTION,
    ) -> dict[str, object]:
        requirements = self._write(
            f"requirements-{execution}.json", {"requirements": ["REQ-1"]}
        )
        policy_value = {
            "active_snapshot_digest": SNAPSHOT,
            "approval_mode": approval_mode,
            "authority_snapshot_digest": AUTHORITY,
            "cycle_id": 1,
            "execution_id": execution,
            "host_approval_evidence_digest": host_approval_evidence_digest,
            "receipt_nonce": NONCE,
            "schema_version": 1,
        }
        if required_verification_argv is not None:
            policy_value["required_verification_argv"] = required_verification_argv
        policy = self._write(
            f"policy-{execution}.json",
            policy_value,
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
            "authority_snapshot_digest": self.authority_snapshot_digest,
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
            "nonce": self.receipt_nonce,
            "output_digest": "sha256:" + hashlib.sha256(receipt_id.encode()).hexdigest(),
            "receipt_id": receipt_id,
            "receipt_schema_version": 1,
            "receipt_type": receipt_type,
            "requirements_digest": projection["requirements_digest"],
            "snapshot_digest": None if frozen else projection["active_snapshot_digest"],
            "transaction_id": "TXN-" + receipt_id,
        }
        if receipt["issuer_skill"] == "gpt-pro-codex-loop":
            receipt["binding"] = dict(self.gpt_binding)
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

    def _record_proof(
        self,
        *,
        evidence_id: str = "EVID-1",
        test_id: str = "TEST-1",
        proof_name: str = "proof.txt",
    ) -> None:
        projection = self._projection()
        proof = self.repository / proof_name
        proof.write_bytes(b"proof\n")
        digest = "sha256:" + hashlib.sha256(proof.read_bytes()).hexdigest()
        paths = store.resolve_run(self.repository, self.execution)
        events = store.load_events(paths)
        event = {
            "artifact_refs": [{"path": proof_name, "sha256": digest}],
            "event_id": "EVT-"
            + hashlib.sha256(evidence_id.encode()).hexdigest()[:12].upper(),
            "execution_id": self.execution,
            "input_digest": projection["active_snapshot_digest"],
            "issuer": {"id": "pytest", "kind": "tool", "version": "8"},
            "output_digest": digest,
            "payload": {
                "artifact_digest": digest,
                "cycle_id": projection["cycle_id"],
                "evidence_id": evidence_id,
                "snapshot_digest": projection["active_snapshot_digest"],
                "test_id": test_id,
            },
            "previous_event_hash": contract.canonical_digest(events[-1]),
            "result": "pass",
            "schema_version": 1,
            "sequence": len(events) + 1,
            "subject_ids": [evidence_id, test_id],
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
        self._init(required_verification_argv=[[sys.executable, "-c", "print('verified')"]])
        self.assertTrue(
            self._import(
                self._receipt("requirements", "RCP-REQ-SETUP"),
                "setup-requirements.json",
            )["ok"]
        )
        self.assertTrue(self._evaluate("G1")["ok"])
        self._record_controller_implementation()
        self.assertTrue(self._evaluate("G2")["ok"])
        self._record_proof()
        self._run_current_verification()
        self.assertTrue(self._evaluate("G3")["ok"])

    @staticmethod
    def _implementation_claims(
        *, evidence_id: str = "EVID-1", include_core: bool = True
    ) -> dict[str, object]:
        nodes = [{"node_id": evidence_id, "node_type": "evidence"}]
        edges = [
            {"edge": "produces", "source_id": "CMD-1", "target_id": evidence_id}
        ]
        if include_core:
            nodes.extend(
                [
                    {"node_id": "CHG-1", "node_type": "change"},
                    {"node_id": "CMD-1", "node_type": "command"},
                    {"node_id": "CODE-1", "node_type": "code"},
                    {"node_id": "TEST-1", "node_type": "test"},
                ]
            )
            edges.extend(
                [
                    {
                        "edge": "implements",
                        "source_id": "CODE-1",
                        "target_id": "REQ-1",
                    },
                    {
                        "edge": "verifies",
                        "source_id": "TEST-1",
                        "target_id": "REQ-1",
                    },
                    {
                        "edge": "executes",
                        "source_id": "CMD-1",
                        "target_id": "TEST-1",
                    },
                    {
                        "edge": "included_in",
                        "source_id": "CODE-1",
                        "target_id": "CHG-1",
                    },
                    {
                        "edge": "included_in",
                        "source_id": "TEST-1",
                        "target_id": "CHG-1",
                    },
                ]
            )
        return {
            "edges": sorted(
                edges,
                key=lambda edge: (
                    str(edge["source_id"]),
                    str(edge["edge"]),
                    str(edge["target_id"]),
                ),
            ),
            "nodes": sorted(nodes, key=lambda node: str(node["node_id"])),
        }

    def _record_controller_implementation(self, *, evidence_id: str = "EVID-1") -> None:
        """Use the controller-owned manifest ingress, never a worker receipt."""
        code = self.repository / "example.py"
        test = self.repository / "test_example.py"
        code.write_bytes(b"value = 1\n")
        test.write_bytes(b"assert True\n")
        projection = self._projection()
        claims = self._implementation_claims(evidence_id=evidence_id)
        if evidence_id != "EVID-1":
            claims = {
                "nodes": [
                    {"node_id": "CHG-2", "node_type": "change"},
                    {"node_id": "CMD-2", "node_type": "command"},
                    {"node_id": "CODE-2", "node_type": "code"},
                    {"node_id": evidence_id, "node_type": "evidence"},
                    {"node_id": "TEST-2", "node_type": "test"},
                ],
                "edges": [
                    {"edge": "implements", "source_id": "CODE-2", "target_id": "REQ-1"},
                    {"edge": "verifies", "source_id": "TEST-2", "target_id": "REQ-1"},
                    {"edge": "executes", "source_id": "CMD-2", "target_id": "TEST-1"},
                    {"edge": "produces", "source_id": "CMD-2", "target_id": evidence_id},
                    {"edge": "included_in", "source_id": "CODE-2", "target_id": "CHG-2"},
                    {"edge": "included_in", "source_id": "TEST-2", "target_id": "CHG-2"},
                ],
            }
        manifest = {
            "artifacts": [
                {"path": "example.py", "sha256": "sha256:" + hashlib.sha256(code.read_bytes()).hexdigest()},
                {"path": "test_example.py", "sha256": "sha256:" + hashlib.sha256(test.read_bytes()).hexdigest()},
            ],
            "base_snapshot_digest": SNAPSHOT,
            "edges": claims["edges"],
            "nodes": claims["nodes"],
            "requirements_digest": projection["requirements_digest"],
            "schema_version": 1,
            "snapshot_digest": projection["active_snapshot_digest"],
        }
        report = {
            "base_snapshot_digest": SNAPSHOT,
            "manifest_digest": contract.canonical_digest(manifest),
            "requirements_digest": projection["requirements_digest"],
            "schema_version": 1,
            "snapshot_digest": projection["active_snapshot_digest"],
        }
        result = cli.main_json([
            "record-implementation", "--repo", str(self.repository), "--execution", self.execution,
            "--manifest", str(self._write("controller-implementation-manifest.json", manifest)),
            "--report", str(self._write("controller-implementation-report.json", report)),
        ])
        self.assertTrue(result["ok"], result)

    def _run_current_verification(self) -> None:
        argv = [sys.executable, "-c", "print('verified')"]
        result = cli.main_json([
            "run-verification", "--repo", str(self.repository), "--execution", self.execution,
            "--argv", str(self._write("controller-verification-argv.json", argv)),
        ])
        self.assertTrue(result["ok"], result)

    def _host_approval_receipt(self) -> dict[str, object]:
        projection = self._projection()
        evidence = self.host_approval_evidence
        return {
            "authority_snapshot_digest": self.authority_snapshot_digest,
            "claims": {"approval_evidence": evidence},
            "cycle_id": None,
            "evidence_set_digest": None,
            "execution_id": self.execution,
            "input_digest": projection["requirements_digest"],
            "issued_at_unix": 1,
            "issuer_skill": "hotl-host-approval",
            "issuer_version": "1",
            "nonce": self.receipt_nonce,
            "output_digest": contract.canonical_digest(evidence),
            "receipt_id": "RCP-HOST-E2E",
            "receipt_schema_version": 1,
            "receipt_type": "approval",
            "requirements_digest": projection["requirements_digest"],
            "snapshot_digest": None,
            "transaction_id": "TXN-HOST-E2E",
        }

    def _begin_real_cross_adapter_chain(
        self,
        exported: tuple[dict[str, object], dict[str, object], bytes] | None = None,
        *,
        active_snapshot_digest: str = SNAPSHOT,
    ) -> dict[str, object]:
        requirements_receipt = self._init_from_gpt_requirements(
            exported, active_snapshot_digest=active_snapshot_digest
        )
        self.assertEqual("requirements", requirements_receipt["receipt_type"])
        self.assertIsNone(requirements_receipt["snapshot_digest"])
        self.assertIsNone(requirements_receipt["evidence_set_digest"])
        self.assertIsNone(requirements_receipt["cycle_id"])
        gate_one = self._evaluate("G1")
        self.assertTrue(gate_one["ok"], gate_one)
        self._record_controller_implementation()
        gate_two = self._evaluate("G2")
        self.assertTrue(gate_two["ok"], gate_two)
        return requirements_receipt

    def _import_receipt_bytes(
        self, raw: bytes, name: str
    ) -> dict[str, object]:
        source = contract.strict_json_loads(raw.decode("utf-8"))
        self.assertIsInstance(source, dict)
        self.assertEqual(contract.canonical_json_bytes(source), raw)
        path = self.inputs / name
        path.write_bytes(raw)
        imported = cli.main_json(
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
        self.assertTrue(imported["ok"], imported)
        record = self._projection()["receipt_records"][source["receipt_id"]]
        stored = (
            store.resolve_run(self.repository, self.execution).evidence
            / str(record["receipt_digest"])[7:]
        ).read_bytes()
        self.assertEqual(raw, stored)
        return source

    def _import_authoritative_gpt_review_and_final(
        self,
        bundle: tuple[dict[str, object], bytes, dict[str, object], bytes],
        *,
        evidence_id: str,
    ) -> None:
        review, review_bytes, final, final_bytes = bundle
        imported_review = self._import_receipt_bytes(
            review_bytes, f"{evidence_id.lower()}-gpt-review.json"
        )
        self.assertEqual(review, imported_review)
        imported_final = self._import_receipt_bytes(
            final_bytes, f"{evidence_id.lower()}-gpt-final.json"
        )
        self.assertEqual(final, imported_final)
        scenario = {
            "authority_snapshot_digest": self.authority_snapshot_digest,
            "execution_id": self.execution,
            "input_digest": str(final["input_digest"]),
            "intent": "gpt-pro-only",
            "invocation_id": "INV-" + evidence_id,
            "nonce": self.receipt_nonce,
            "output_digest": str(final["output_digest"]),
        }
        sol = sol_receipts.governance_receipt(scenario, sol_receipts.route(scenario), None)
        path = self.inputs / f"{evidence_id.lower()}-sol.json"
        path.write_bytes(json.dumps(sol, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        result = cli.main_json(["import-sol-receipt", "--repo", str(self.repository), "--execution", self.execution, "--receipt", str(path)])
        self.assertTrue(result["ok"], result)

    def _record_current_verification(
        self,
        *,
        evidence_id: str = "EVID-1",
        proof_name: str = "proof.txt",
    ) -> None:
        self._record_proof(evidence_id=evidence_id, proof_name=proof_name)
        self._run_current_verification()

    def _imported_source_receipts(self) -> list[dict[str, object]]:
        paths = store.resolve_run(self.repository, self.execution)
        projection = self._projection()
        sources: list[dict[str, object]] = []
        for record in projection["receipt_records"].values():
            digest = record["receipt_digest"]
            source = contract.strict_json_loads(
                (paths.evidence / str(digest)[7:]).read_text(encoding="utf-8")
            )
            self.assertIsInstance(source, dict)
            sources.append(source)
        return sources

    def _assert_authoritative_privileged_ingress(self) -> None:
        sources = self._imported_source_receipts()
        review = next(
            source
            for source in sources
            if source["receipt_type"] == "semantic_review"
        )
        final = next(source for source in sources if source["receipt_type"] == "final")
        self.assertFalse(any(source["receipt_type"] == "approval" for source in sources))
        self.assertEqual(
            "gpc-loop-hotl-e2e:review-01", review["transaction_id"]
        )
        self.assertEqual(
            "gpc-loop-hotl-e2e:final-verify-01", final["transaction_id"]
        )

    def test_stable_command_set_and_parser_errors_never_raise_system_exit(self) -> None:
        self.assertEqual(
            (
                "init", "status", "record", "approve", "import-receipt",
                "record-implementation", "run-verification", "import-sol-receipt",
                "export-governance-context", "evaluate", "project", "verify-log", "start-successor",
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

    def test_external_requirements_typed_ids_must_match_exact_gpt_items(self) -> None:
        cases = (
            (["REQ-2"], {"requirements": [{"id": "REQ-1", "statement": "One."}]}),
            (["REQ-1"], {"schema_version": 1}),
            (["REQ-1"], {"requirements": [{"id": "REQ-1"}]}),
            (
                ["REQ-1"],
                {
                    "requirements": [
                        {"id": "REQ-1", "statement": "One.", "unknown": True}
                    ]
                },
            ),
            (
                ["REQ-1"],
                {
                    "requirements": [
                        {"id": "REQ-1", "statement": "One."},
                        {"id": "REQ-1", "statement": "Duplicate."},
                    ]
                },
            ),
        )
        for index, (identifiers, source) in enumerate(cases, 1):
            with self.subTest(index=index):
                execution = f"EXEC-0000000003{index:02d}"
                source_bytes = contract.canonical_json_bytes(source)
                source_digest = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
                requirements = self._write(
                    f"external-typed-bad-{index}.json",
                    {
                        "requirements": identifiers,
                        "source_artifact": source,
                        "source_digest": source_digest,
                    },
                )
                policy = self._write(
                    f"external-typed-policy-{index}.json",
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
                self.assertEqual("INVALID_REQUIREMENTS", result["error"]["code"])
                self.assertFalse(store.resolve_run(self.repository, execution).root.exists())

    def test_status_is_read_only_and_lists_only_executable_safe_commands(self) -> None:
        self._init()
        before = snapshot_tree(self.repository / ".hotl")
        result = cli.main_json(
            ["status", "--repo", str(self.repository), "--execution", self.execution]
        )
        after = snapshot_tree(self.repository / ".hotl")
        self.assertEqual(before, after)
        self.assertEqual(["import-receipt"], result["result"]["next_commands"])

    def test_absent_execution_status_advertises_init_not_recovery(self) -> None:
        """Changing absence handling back to recovery must make this fail."""
        result = cli.main_json(
            ["status", "--repo", str(self.repository), "--execution", self.execution]
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual("UNINITIALIZED", result["result"]["state"])
        self.assertEqual(["init"], result["result"]["next_commands"])

    def test_export_governance_context_writes_a_closed_execution_bound_artifact(self) -> None:
        """Removing controller export must make the explicit context command unavailable."""
        self._init()
        output = self.inputs / "hotl-governance-context.json"
        result = cli.main_json([
            "export-governance-context", "--repo", str(self.repository),
            "--execution", self.execution, "--output", str(output),
        ])
        self.assertTrue(result["ok"], result)
        context = contract.strict_json_loads(output.read_text(encoding="utf-8"))
        self.assertIsInstance(context, dict)
        assert isinstance(context, dict)
        body = {key: context[key] for key in context if key != "artifact_digest"}
        self.assertEqual("hotl-governance-context", context["artifact_type"])
        self.assertEqual(self.execution, context["execution_id"])
        self.assertEqual(
            contract.canonical_digest(body), context["artifact_digest"]
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(output.read_bytes()).hexdigest(),
            result["result"]["context_file_digest"],
        )

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

        incomplete = dict(receipt)
        incomplete_binding = dict(
            receipt["binding"],
            model_label="Legacy Exact",
            reasoning_label=None,
            plan_label=None,
        )
        incomplete.update(
            binding=incomplete_binding,
            authority_snapshot_digest=controller.gpt_governance_authority_digest(
                incomplete_binding
            ),
            nonce=controller.gpt_governance_nonce(incomplete_binding),
        )
        self.assertEqual(
            "INVALID_RECEIPT_BINDING",
            self._import(incomplete, "gpt-binding-incomplete.json")["error"]["code"],
        )

    def test_gpt_identity_derivation_is_domain_separated_and_recomputed(self) -> None:
        self.assertEqual(
            "EXEC-C6EBD51734DE",
            controller.gpt_governance_execution_id("hotl-fixture"),
        )
        self.assertEqual(
            "d6869e970ce7ce7dec3b0ca23b9e282e",
            controller.gpt_governance_nonce(GPT_BINDING),
        )
        self.assertEqual(AUTHORITY, controller.gpt_governance_authority_digest(GPT_BINDING))
        changed = dict(
            GPT_BINDING,
            task_slug="hotl-fixture-2",
            run_id="gpc-loop-hotl-fixture-2",
        )
        self.assertEqual(
            "EXEC-595E64A78060",
            controller.gpt_governance_execution_id("hotl-fixture-2"),
        )
        self.assertEqual(
            "58576b717cadf982dd1131f9604cfd14",
            controller.gpt_governance_nonce(changed),
        )
        self.assertNotEqual(
            controller.gpt_governance_execution_id("hotl-fixture")[5:].lower(),
            controller.gpt_governance_nonce(GPT_BINDING)[:12],
        )

        relabeled = "EXEC-000000000BAD"
        self.execution = relabeled
        initialized = self._init(execution=relabeled)
        self.assertTrue(initialized["ok"], initialized)
        receipt = self._receipt("requirements", "RCP-GPT-RELABEL")
        rejected = self._import(receipt, "gpt-relabeled.json")
        self.assertFalse(rejected["ok"], rejected)
        self.assertEqual("GPT_IDENTITY_MISMATCH", rejected["error"]["code"])

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
        self.assertEqual("UNTRUSTED_APPROVAL", result["error"]["code"])

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
            "UNTRUSTED_APPROVAL", approval_result["error"]["code"]
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

    def test_approve_rejects_worker_created_host_evidence_in_agentic_mode(self) -> None:
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
        rejected = cli.main_json(
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
        self.assertFalse(rejected["ok"], rejected)
        self.assertEqual("UNTRUSTED_APPROVAL", rejected["error"]["code"])

    def test_public_receipt_import_cannot_mint_worker_verification_authority(self) -> None:
        """Replacing the closed ingress check with generic import must fail."""
        self._init()
        self.assertTrue(self._import(self._receipt("requirements", "RCP-REQ-CLOSED"))["ok"])
        self.assertTrue(self._evaluate("G1")["ok"])
        forged = self._import(
            self._receipt(
                "verification",
                "RCP-FORGED-VERIFY",
                claims={"edges": []},
            ),
            "forged-verification.json",
        )
        self.assertFalse(forged["ok"], forged)
        self.assertEqual("PRIVILEGED_RECEIPT_REQUIRES_CONTROLLER", forged["error"]["code"])

    def test_controller_records_content_addressed_implementation_manifest_and_report(self) -> None:
        """Replacing controller ingress with public receipt import must fail this gate."""
        self._init()
        self.assertTrue(self._import(self._receipt("requirements", "RCP-REQ-IMPL"))["ok"])
        self.assertTrue(self._evaluate("G1")["ok"])
        code = self.repository / "example.py"
        test = self.repository / "test_example.py"
        code.write_bytes(b"value = 1\n")
        test.write_bytes(b"assert True\n")
        code_digest = "sha256:" + hashlib.sha256(code.read_bytes()).hexdigest()
        test_digest = "sha256:" + hashlib.sha256(test.read_bytes()).hexdigest()
        projection = self._projection()
        manifest = {
            "artifacts": [
                {"path": "example.py", "sha256": code_digest},
                {"path": "test_example.py", "sha256": test_digest},
            ],
            "base_snapshot_digest": SNAPSHOT,
            "edges": [
                {"edge": "implements", "source_id": "CODE-1", "target_id": "REQ-1"},
                {"edge": "verifies", "source_id": "TEST-1", "target_id": "REQ-1"},
                {"edge": "included_in", "source_id": "CODE-1", "target_id": "CHG-1"},
                {"edge": "included_in", "source_id": "TEST-1", "target_id": "CHG-1"},
            ],
            "nodes": [
                {"node_id": "CHG-1", "node_type": "change"},
                {"node_id": "CODE-1", "node_type": "code"},
                {"node_id": "TEST-1", "node_type": "test"},
            ],
            "requirements_digest": projection["requirements_digest"],
            "schema_version": 1,
            "snapshot_digest": SNAPSHOT,
        }
        manifest_path = self._write("implementation-manifest.json", manifest)
        report_path = self._write(
            "implementation-report.json",
            {
                "base_snapshot_digest": SNAPSHOT,
                "manifest_digest": contract.canonical_digest(manifest),
                "requirements_digest": projection["requirements_digest"],
                "schema_version": 1,
                "snapshot_digest": SNAPSHOT,
            },
        )
        recorded = cli.main_json(
            [
                "record-implementation",
                "--repo", str(self.repository), "--execution", self.execution,
                "--manifest", str(manifest_path), "--report", str(report_path),
            ]
        )
        self.assertTrue(recorded["ok"], recorded)
        self.assertTrue(self._evaluate("G2")["ok"])
        paths = store.resolve_run(self.repository, self.execution)
        self.assertEqual(contract.canonical_json_bytes(manifest), (paths.evidence / contract.canonical_digest(manifest)[7:]).read_bytes())
        self.assertEqual(report_path.read_bytes(), (paths.evidence / contract.canonical_digest(contract.strict_json_loads(report_path.read_text(encoding="utf-8")))[7:]).read_bytes())

    def test_init_freezes_canonical_verification_argv_policy(self) -> None:
        """Dropping the frozen argv field must make init reject this policy."""
        requirements = self._write("argv-requirements.json", {"requirements": ["REQ-1"]})
        policy = self._write(
            "argv-policy.json",
            {
                "active_snapshot_digest": SNAPSHOT,
                "approval_mode": "agentic",
                "authority_snapshot_digest": AUTHORITY,
                "cycle_id": 1,
                "execution_id": self.execution,
                "host_approval_evidence_digest": None,
                "receipt_nonce": NONCE,
                "required_verification_argv": [[sys.executable, "-c", "print('verified')"]],
                "schema_version": 1,
            },
        )
        result = cli.main_json(
            ["init", "--repo", str(self.repository), "--execution", self.execution, "--policy", str(policy), "--requirements", str(requirements)]
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual([[sys.executable, "-c", "print('verified')"]], self._projection().get("required_verification_argv"))

    def test_controller_runs_only_exact_frozen_argv_without_a_shell(self) -> None:
        """Removing controller argv execution must turn this into an argument error."""
        argv = [sys.executable, "-c", "print('verified')"]
        self._init(required_verification_argv=[argv])
        result = cli.main_json(
            [
                "run-verification", "--repo", str(self.repository), "--execution", self.execution,
                "--argv", str(self._write("verify-argv.json", argv)),
            ]
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual("REQUIREMENTS", result["result"]["state"])

    def test_import_sol_receipt_accepts_exact_task7_no_consultation_bytes(self) -> None:
        """Replacing this closed adapter with generic receipt import must fail."""
        self._init()
        scenario = {
            "authority_snapshot_digest": AUTHORITY, "execution_id": self.execution,
            "input_digest": SNAPSHOT, "intent": "gpt-pro-only", "invocation_id": "INV-HOTL",
            "nonce": NONCE, "output_digest": SNAPSHOT,
        }
        receipt = sol_receipts.governance_receipt(scenario, sol_receipts.route(scenario), None)
        receipt_path = self.inputs / "task7-sol.json"
        receipt_path.write_bytes(json.dumps(receipt, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        result = cli.main_json([
            "import-sol-receipt", "--repo", str(self.repository), "--execution", self.execution,
            "--receipt", str(receipt_path),
        ])
        self.assertTrue(result["ok"], result)

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
        self.assertEqual("UNTRUSTED_APPROVAL", result["error"]["code"])

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
        self.assertEqual("UNTRUSTED_APPROVAL", rejected["error"]["code"])
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
        self.assertFalse(accepted["ok"], accepted)
        self.assertEqual("UNTRUSTED_APPROVAL", accepted["error"]["code"])

    def test_failed_gate_emits_no_transition(self) -> None:
        self._init()
        paths = store.resolve_run(self.repository, self.execution)
        before = paths.events.read_bytes()
        result = self._evaluate("G1")
        self.assertFalse(result["ok"])
        self.assertEqual("GATE_FAILED", result["error"]["code"])
        self.assertEqual(before, paths.events.read_bytes())

    def test_all_four_gates_complete_only_after_bound_evidence(self) -> None:
        self._init(required_verification_argv=[[sys.executable, "-c", "print('verified')"]])
        self.assertTrue(self._import(self._receipt("requirements", "RCP-REQ-1"), "requirements.json")["ok"])
        self.assertEqual("IMPLEMENT", self._evaluate("G1")["result"]["state"])
        self._record_controller_implementation()
        self.assertEqual("LOCAL_VERIFY", self._evaluate("G2")["result"]["state"])

        self._record_proof()
        self._run_current_verification()
        self.assertEqual("SEMANTIC_REVIEW", self._evaluate("G3")["result"]["state"])

        review_claims = {
            "edges": [
                {"edge": "reviews", "source_id": "REV-1", "target_id": "REQ-1"},
            ],
            "findings": [],
            "review_id": "REV-1",
            "root_cause_ids": [],
            "status": "accepted",
        }
        self.assertTrue(self._import(self._receipt("semantic_review", "RCP-REV-1", claims=review_claims), "review.json")["ok"])
        self.assertTrue(self._import(self._receipt("final", "RCP-FINAL-1"), "final.json")["ok"])
        scenario = {"authority_snapshot_digest": self.authority_snapshot_digest, "execution_id": self.execution, "input_digest": SNAPSHOT, "intent": "gpt-pro-only", "invocation_id": "INV-ALL-GATES", "nonce": self.receipt_nonce, "output_digest": SNAPSHOT}
        receipt = sol_receipts.governance_receipt(scenario, sol_receipts.route(scenario), None)
        path = self.inputs / "all-gates-sol.json"
        path.write_bytes(json.dumps(receipt, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        imported_sol = cli.main_json(["import-sol-receipt", "--repo", str(self.repository), "--execution", self.execution, "--receipt", str(path)])
        self.assertTrue(imported_sol["ok"], imported_sol)
        result = self._evaluate("G4")
        self.assertTrue(result["ok"], result)
        self.assertEqual("COMPLETE", result["result"]["state"])

    def test_real_gpt_requirements_receipt_completes_and_replays_byte_identically(
        self,
    ) -> None:
        exported = self._export_frozen_gpt_requirements()
        authoritative = self._export_authoritative_gpt_review_and_final()
        self._begin_real_cross_adapter_chain(
            exported,
            active_snapshot_digest=str(authoritative[0]["snapshot_digest"]),
        )
        self._record_current_verification()
        gate_three = self._evaluate("G3")
        self.assertTrue(gate_three["ok"], gate_three)

        self._import_authoritative_gpt_review_and_final(
            authoritative, evidence_id="EVID-1"
        )
        gate_four = self._evaluate("G4")
        self.assertTrue(gate_four["ok"], gate_four)
        self.assertEqual("COMPLETE", gate_four["result"]["state"])

        paths = store.resolve_run(self.repository, self.execution)
        persisted = contract.strict_json_loads(paths.state.read_text(encoding="utf-8"))
        self.assertIsInstance(persisted, dict)
        first = self._projection()
        second = self._projection()
        self.assertEqual(
            contract.canonical_json_bytes(persisted["projection"]),
            contract.canonical_json_bytes(first),
        )
        self.assertEqual(
            contract.canonical_json_bytes(first),
            contract.canonical_json_bytes(second),
        )
        self._assert_authoritative_privileged_ingress()

    def test_snapshot_change_closes_g4_until_replacement_evidence_and_review(
        self,
    ) -> None:
        exported = self._export_frozen_gpt_requirements()
        self._begin_real_cross_adapter_chain(exported)
        self._record_current_verification()
        gate_three = self._evaluate("G3")
        self.assertTrue(gate_three["ok"], gate_three)

        authoritative = self._export_authoritative_gpt_review_and_final()
        replacement_snapshot = str(authoritative[0]["snapshot_digest"])
        controller.activate_snapshot(
            self.repository, self.execution, replacement_snapshot
        )
        invalidated = self._projection()
        self.assertEqual(replacement_snapshot, invalidated["active_snapshot_digest"])
        self.assertEqual(
            "historically_valid",
            invalidated["evidence_records"]["EVID-1"]["status"],
        )
        closed_after_change = self._evaluate("G4")
        self.assertFalse(closed_after_change["ok"], closed_after_change)
        self.assertEqual("GATE_FAILED", closed_after_change["error"]["code"])

        self._record_controller_implementation(evidence_id="EVID-2")
        self._record_proof(evidence_id="EVID-2", proof_name="replacement-proof.txt")
        self._run_current_verification()
        closed_without_review = self._evaluate("G4")
        self.assertFalse(closed_without_review["ok"], closed_without_review)
        self.assertEqual("GATE_FAILED", closed_without_review["error"]["code"])

        self._import_authoritative_gpt_review_and_final(
            authoritative, evidence_id="EVID-2"
        )
        completed = self._evaluate("G4")
        self.assertTrue(completed["ok"], completed)
        self.assertEqual("COMPLETE", completed["result"]["state"])
        self._assert_authoritative_privileged_ingress()

    def test_stale_receipt_is_rejected_after_snapshot_change(self) -> None:
        self._init()
        stale = self._receipt("verification", "RCP-STALE-1", claims={"edges": []})
        controller.activate_snapshot(
            self.repository, self.execution, "sha256:" + "e" * 64
        )
        result = self._import(stale, "stale.json")
        self.assertFalse(result["ok"])
        self.assertEqual("PRIVILEGED_RECEIPT_REQUIRES_CONTROLLER", result["error"]["code"])

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
            [["receipt_imported", "node_declared", "review_recorded", "edge_declared", "finding_recorded"]],
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
        successor_binding = {
            "conversation_url": "https://chatgpt.com/c/hotl-successor",
            "model_label": "GPT-5.6 Sol",
            "plan_label": "Pro",
            "reasoning_label": "Pro",
            "run_id": "gpc-loop-hotl-successor",
            "task_slug": "hotl-successor",
        }
        successor = "EXEC-94B3AC020EA0"
        successor_authority = "sha256:e02da02689a97dd32d198c7565e41e791507f04262c0f8fbc1971cdb3aa967fc"
        successor_nonce = "17f5b236848290e9d4bfd815fa339e4b"
        successor_requirements_value = {"requirements": ["REQ-2"]}
        successor_requirements = self._write(
            "successor-requirements.json", successor_requirements_value
        )
        policy = self._write(
            "successor-policy.json",
            {
                "active_snapshot_digest": SNAPSHOT,
                "approval_mode": "agentic",
                "authority_snapshot_digest": successor_authority,
                "cycle_id": 1,
                "execution_id": successor,
                "host_approval_evidence_digest": None,
                "initial_state": "INIT",
                "receipt_nonce": successor_nonce,
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
        requirements_receipt = self._receipt(
            "requirements", "RCP-SUCCESSOR-REQ"
        )
        requirements_receipt.update(
            authority_snapshot_digest=successor_authority,
            binding=successor_binding,
            nonce=successor_nonce,
        )
        self.assertTrue(
            self._import(
                requirements_receipt,
                "successor-requirements-receipt.json",
            )["ok"]
        )
        approval_receipt = self._receipt("approval", "RCP-SUCCESSOR-APP")
        approval_receipt.update(
            authority_snapshot_digest=successor_authority,
            binding=successor_binding,
            nonce=successor_nonce,
        )
        self.assertTrue(
            self._import(
                approval_receipt,
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
        self._record_controller_implementation()
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
