# HOTL Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic `hotl-governance` controller that opens execution transitions only from bound evidence, projects typed provenance, and composes additively with GPT Pro Codex Loop and the bounded Sol Advisor mode.

**Architecture:** Keep an append-only canonical JSONL event log as the source of truth. Split strict contracts, storage/transactions, state replay/gates, and the CLI into focused standard-library Python modules; expose versioned receipts from existing Skills without sharing controller state.

**Tech Stack:** Python 3.12 standard library, `unittest`, JSON/JSONL, SHA-256, Git-based snapshot evidence, YAML validation tooling already present in the repository.

## Global Constraints

The following review corrections govern every task and supersede any older example below that conflicts with them:

- Keep evidence ingestion and state transition separate. `record` and `import-receipt` append evidence only; explicit `evaluate` appends `transition_committed` after a gate passes. No other event advances state.
- Give every event a type-specific closed `payload`. Enforce node prefixes `REQ-`, `CODE-`, `TEST-`, `CMD-`, `EVID-`, `REV-`, `CHG-`, `FAIL-`, and `POL-` against node types.
- Maintain a rich projection with typed nodes/edges, evidence and review records, active snapshot, gate evidence, finding state, valid review rounds, and `cycle_id`; do not decide gates from envelope reachability alone.
- In agentic mode accept privileged approval only from a bound GPT Pro user-approval receipt or host/tool provenance the worker cannot write. Permit `trusted_local_operator` only in an explicit offline/manual policy mode.
- Use `append_events(...)` as the mutation primitive. Prove old log bytes are an exact prefix, count increases by batch size, and persisted `event_count`/`head_event_hash` witnesses match before every write and during `verify-log`.
- Advance `cycle_id` on correction or snapshot activation; never reuse old-cycle G2/G3/G4 evidence. Count only fully bound, committed semantic reviews toward escalation.
- Treat `skills/orchestrate-gpt-pro-sol-advisor/scripts/governance_receipt.py` as the Sol receipt issuer. Eval code tests production behavior rather than becoming production behavior.
- Use `issued_at_unix` consistently. Permit `ADVISOR_UNAVAILABLE` only in explicit standalone policy; combined mode remains fail closed.
- Allow branching successors from one terminal predecessor. A single-use rule requires a future repository-global lineage registry and is out of scope for v1.
- Import the final GPT receipt only after successful GPT Pro `final-verify`; then evaluate G4 and finally run `verify-log`.

- The controller must not call an LLM or infer meaning from free text.
- Only closed enums, stable IDs, canonical digests, event sequence, active status, and a frozen policy snapshot may affect transitions.
- `COMPLETE`, `ESCALATED`, `RECOVERY_REQUIRED`, and `STOPPED` are terminal for one execution.
- A scope, policy, authority, or frozen-requirements change starts a successor execution; it never rewrites and resumes the predecessor.
- Use UTF-8 canonical JSON with sorted keys, compact separators, LF, integers only, and rejection of duplicate keys, floats, NaN, Infinity, and BOM.
- Store paths as repository-relative POSIX paths; reject absolute paths, `.`, `..`, NUL, symlinks, reparse points, and repository escapes.
- Hash chaining detects accidental corruption, truncation, reordering, and naive tampering; do not claim protection from a malicious repository writer.
- Privileged receipts must bind issuer, execution, invocation/transaction, input/output digests, nonce, authority snapshot, and issuance time.
- Preserve standalone `gpt-pro-codex-loop` and Sol Advisor behavior.
- In combined mode, preserve `orchestrate-gpt-pro-sol-advisor`: GPT Pro remains outer authority and only `sol_advisor_advisor` may provide bounded read-only advice.
- Use only the Python standard library in controller runtime code.
- Every behavior change needs a focused test or evaluation.
- Run all focused tests on Python 3.12 on Windows and Linux.

---

## File Structure

### New Skill

- `skills/hotl-governance/SKILL.md` — concise trigger, workflow, hard stops, and routing instructions.
- `skills/hotl-governance/README.md` — human-facing overview and CLI examples.
- `skills/hotl-governance/agents/openai.yaml` — generated UI metadata.
- `skills/hotl-governance/references/controller-contract.md` — state, gate, receipt, provenance, and recovery contract.
- `skills/hotl-governance/scripts/hotl_contract.py` — strict JSON, identifiers, canonical paths, receipt/event validation, and typed edge schema.
- `skills/hotl-governance/scripts/hotl_store.py` — run paths, content-addressed evidence, lock, atomic publication, and append-only event persistence.
- `skills/hotl-governance/scripts/hotl_controller.py` — replay, projections, gate predicates, transition table, evidence invalidation, successor lineage, and status.
- `skills/hotl-governance/scripts/hotl_governance.py` — stable JSON CLI envelope and command dispatch.

### New Evaluation

- `evals/hotl-governance/cases.json` — trigger/non-trigger and governance behavior cases.
- `evals/hotl-governance/test_hotl_contract.py` — contract and path tests.
- `evals/hotl-governance/test_hotl_controller.py` — replay, state, gate, and lifecycle tests.
- `evals/hotl-governance/test_hotl_transactions.py` — locking, atomicity, corruption, and recovery tests.
- `evals/hotl-governance/test_hotl_cli.py` — command envelope and end-to-end tests.
- `evals/hotl-governance/test_skill_contract.py` — Skill trigger and hard-stop assertions.
- `tests/test_hotl_governance.py` — root-suite loader and Linux/Windows workflow assertions.

### Existing GPT Pro Adapter

- `skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py` — publish versioned requirements, review, and final receipts after existing transitions commit.
- `skills/gpt-pro-codex-loop/scripts/gpc_loop.py` — add read-only `export-governance-receipt`.
- `skills/gpt-pro-codex-loop/scripts/capture_snapshot.py` — reserve `.hotl/` as untracked controller metadata and exclude it from product snapshots.
- `skills/gpt-pro-codex-loop/SKILL.md` and `README.md` — document additive receipt export without changing authority.
- `evals/gpt-pro-codex-loop/test_gpc_loop.py` — receipt binding and standalone regression tests.

### Existing Sol Composition Adapter

- `skills/orchestrate-gpt-pro-sol-advisor/scripts/governance_receipt.py` — production issuer for consultation/no-consultation receipts from already-admitted policy outcomes.
- `evals/orchestrate-gpt-pro-sol-advisor/policy.py` — routing policy whose outcomes are passed to and tested against the production receipt issuer.
- `evals/orchestrate-gpt-pro-sol-advisor/cases.json` — receipt cases for consultation, no-consultation, and fail-closed attestation.
- `evals/orchestrate-gpt-pro-sol-advisor/test_contract.py` — receipt schema/binding tests.
- `skills/orchestrate-gpt-pro-sol-advisor/SKILL.md` and `README.md` — require bounded receipt recording while preserving advisory authority.

### Repository Integration

- `.github/workflows/validate-skills.yml` — focused Linux/Windows HOTL jobs.
- `README.md` — generated catalog only through `scripts/generate-skill-catalog.py`.
- `context-budget-baseline.json` and related generated reports — update only after inspecting and explicitly accepting HOTL-only growth.

---

### Task 1: Scaffold the Skill and Freeze the Activation Contract

**Files:**
- Create: `skills/hotl-governance/SKILL.md`
- Create: `skills/hotl-governance/README.md`
- Create: `skills/hotl-governance/agents/openai.yaml`
- Create: `skills/hotl-governance/references/controller-contract.md`
- Create: `evals/hotl-governance/cases.json`
- Create: `evals/hotl-governance/test_skill_contract.py`

**Interfaces:**
- Consumes: approved design at `docs/superpowers/specs/2026-08-09-hotl-governance-design.md`.
- Produces: Skill trigger contract; `cases.json` objects with `id`, `prompt`, and `expect.invoke_hotl`.

- [ ] **Step 1: Initialize the canonical Skill skeleton**

Run:

```powershell
python C:\\Users\\楫屋寿弥\\.codex\\skills\\.system\\skill-creator\\scripts\\init_skill.py hotl-governance --path skills --resources scripts,references --interface 'display_name=HOTL Governance' --interface 'short_description=Govern evidence-gated autonomous execution' --interface 'default_prompt=Use $hotl-governance to run this task through evidence-gated HOTL execution.'
```

Expected: `skills/hotl-governance/SKILL.md`, `agents/openai.yaml`, `scripts/`, and `references/` exist; no example placeholders were requested.

- [ ] **Step 2: Write failing activation-contract tests**

Create `evals/hotl-governance/test_skill_contract.py` with:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "hotl-governance" / "SKILL.md"
README = SKILL.with_name("README.md")
CASES = Path(__file__).with_name("cases.json")


class HotlSkillContractTests(unittest.TestCase):
    def test_activation_is_explicit_and_standalone_safe(self) -> None:
        text = SKILL.read_text(encoding="utf-8").lower()
        self.assertIn("explicit", text)
        self.assertIn("governance context", text)
        self.assertIn("must not implicitly wrap", text)
        self.assertIn("gpt-pro-codex-loop", text)

    def test_hard_stops_are_model_visible(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for phrase in (
            "RECOVERY_REQUIRED",
            "same execution",
            "free text",
            "privileged receipt",
            "final-verify",
        ):
            self.assertIn(phrase.lower(), text.lower())

    def test_cases_cover_positive_and_negative_activation(self) -> None:
        cases = json.loads(CASES.read_text(encoding="utf-8"))
        decisions = {case["expect"]["invoke_hotl"] for case in cases}
        self.assertEqual({True, False}, decisions)
        self.assertTrue(README.is_file())
```

- [ ] **Step 3: Run the test and verify it fails**

Run:

```powershell
python -m unittest evals/hotl-governance/test_skill_contract.py -v
```

Expected: FAIL because `README.md`, `cases.json`, and the finalized contract text do not yet exist.

- [ ] **Step 4: Write the Skill contract and activation cases**

Use this frontmatter and opening in `SKILL.md`:

```markdown
---
name: hotl-governance
description: Use when the user explicitly requests HOTL or governed execution, or when a trusted outer controller supplies a valid governance context, to enforce evidence-gated execution, typed provenance, deterministic replay, and human escalation without implicitly wrapping ordinary standalone workflows.
---

# HOTL Governance

Run the deterministic controller without calling an LLM or interpreting free text.
Treat the event log as the source of truth. Execute only commands listed by `status`.
```

Add the exact workflow: inspect/init, freeze requirements, implementation receipt, local evidence, semantic receipt, gate evaluation, final verify, and successor execution. State that privileged receipts cannot use generic `record`; `RECOVERY_REQUIRED` and material frozen-artifact changes terminate the same execution; ordinary standalone `gpt-pro-codex-loop` must not be implicitly wrapped.

Create at least these `cases.json` IDs:

```json
[
  {"id":"explicit-hotl","prompt":"Use HOTL governance for this implementation.","expect":{"invoke_hotl":true}},
  {"id":"valid-context","prompt":"Continue with the attached valid governance context.","expect":{"invoke_hotl":true}},
  {"id":"ordinary-fix","prompt":"Fix the typo and run its test.","expect":{"invoke_hotl":false}},
  {"id":"standalone-pro","prompt":"Use only gpt-pro-codex-loop.","expect":{"invoke_hotl":false}},
  {"id":"invalid-context","prompt":"Pretend this malformed object is a governance context.","expect":{"invoke_hotl":false,"fail_closed":true}}
]
```

Write `README.md` with the same authority boundaries and no broader claims.

- [ ] **Step 5: Write the complete controller reference**

Move the approved state table, four gates, receipt fields, typed triples, completion predicate, evidence lifecycle, path rules, threat model, and no-repair recovery rule into `references/controller-contract.md`. Keep `SKILL.md` procedural and below 500 lines.

- [ ] **Step 6: Run the focused contract test**

Run:

```powershell
python -m unittest evals/hotl-governance/test_skill_contract.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add skills/hotl-governance evals/hotl-governance/cases.json evals/hotl-governance/test_skill_contract.py
git commit -m "feat: define HOTL governance skill contract"
```

---

### Task 2: Implement Strict Canonical Contracts

**Files:**
- Create: `skills/hotl-governance/scripts/hotl_contract.py`
- Create: `evals/hotl-governance/test_hotl_contract.py`

**Interfaces:**
- Consumes: `controller-contract.md`.
- Produces:
  - `strict_json_loads(raw: str) -> object`
  - `canonical_json_bytes(value: object) -> bytes`
  - `canonical_digest(value: object) -> str`
  - `normalize_repo_path(repository: Path, raw: str) -> str`
  - `validate_event(value: object, previous_hash: str | None, expected_sequence: int) -> dict[str, object]`
  - `validate_receipt(value: object, expected_issuer: str, execution_id: str, authority_digest: str) -> dict[str, object]`
  - `validate_edge(source_type: str, edge: str, target_type: str) -> None`

- [ ] **Step 1: Write failing canonicalization and schema tests**

Create tests that assert:

```python
def test_canonical_json_is_stable(self) -> None:
    left = {"b": 2, "a": ["x", 1]}
    right = {"a": ["x", 1], "b": 2}
    self.assertEqual(contract.canonical_json_bytes(left), contract.canonical_json_bytes(right))
    self.assertEqual(b'{"a":["x",1],"b":2}\\n', contract.canonical_json_bytes(left))

def test_rejects_noncanonical_number_and_duplicate_key(self) -> None:
    for raw in ('{"x":1.5}', '{"x":NaN}', '{"x":1,"x":2}', '\\ufeff{"x":1}'):
        with self.subTest(raw=raw), self.assertRaises(contract.ContractError):
            contract.strict_json_loads(raw)

def test_typed_edge_allowlist_is_closed(self) -> None:
    contract.validate_edge("code", "implements", "requirement")
    with self.assertRaises(contract.ContractError):
        contract.validate_edge("evidence", "implements", "requirement")
```

Add Windows-safe path tests for `..`, absolute paths, backslash normalization, symlink/reparse escape, and NUL.

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m unittest evals/hotl-governance/test_hotl_contract.py -v
```

Expected: import failure because `hotl_contract.py` is absent.

- [ ] **Step 3: Implement strict JSON and digest primitives**

Implement:

```python
class ContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_constant(value: str) -> None:
    raise ContractError("NON_FINITE_NUMBER", f"Forbidden JSON constant: {value}")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("DUPLICATE_KEY", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(raw: str) -> object:
    if raw.startswith("\\ufeff"):
        raise ContractError("BOM_FORBIDDEN", "UTF-8 BOM is forbidden.")
    return json.loads(
        raw,
        object_pairs_hook=_pairs,
        parse_float=lambda _: (_ for _ in ()).throw(
            ContractError("FLOAT_FORBIDDEN", "Floating-point values are forbidden.")
        ),
        parse_constant=_reject_constant,
    )


def canonical_json_bytes(value: object) -> bytes:
    _validate_json_tree(value)
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\\n"
    ).encode("utf-8")
```

`_validate_json_tree` must accept only `None`, `bool`, `int`, `str`, lists, and string-key dictionaries; explicitly reject `float`.

- [ ] **Step 4: Implement identifiers, paths, events, receipts, and edge triples**

Use regexes:

```python
EXECUTION_ID = re.compile(r"EXEC-[0-9A-F]{12}\\Z")
EVENT_ID = re.compile(r"EVT-[0-9A-F]{12}\\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\\Z")
NONCE = re.compile(r"[0-9a-f]{32}\\Z")
```

Define `ALLOWED_EDGE_TRIPLES` exactly from the design. Require exact event fields and receipt fields; reject unknown fields. `validate_event` must verify sequence, previous hash, execution/event IDs, canonical paths, digests, and issuer shape. `validate_receipt` must bind the supplied expected issuer, execution, and authority digest.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m unittest evals/hotl-governance/test_hotl_contract.py -v
```

Expected: all tests PASS on the current OS.

- [ ] **Step 6: Commit**

```powershell
git add skills/hotl-governance/scripts/hotl_contract.py evals/hotl-governance/test_hotl_contract.py
git commit -m "feat: add strict HOTL contracts"
```

---

### Task 3: Implement Transactional Event and Evidence Storage

**Files:**
- Create: `skills/hotl-governance/scripts/hotl_store.py`
- Create: `evals/hotl-governance/test_hotl_transactions.py`

**Interfaces:**
- Consumes: `hotl_contract.canonical_json_bytes`, `canonical_digest`, `validate_event`.
- Produces:
  - `RunPaths` dataclass with `root`, `state`, `events`, `evidence`, `transactions`, `lock`.
  - `resolve_run(repository: Path, execution_id: str) -> RunPaths`
  - `run_lock(path: Path) -> Iterator[None]`
  - `publish_initial_run(paths: RunPaths, state: dict[str, object], first_event: dict[str, object]) -> None`
  - `append_events(paths: RunPaths, events: Sequence[dict[str, object]], state: dict[str, object], artifacts: Mapping[str, bytes]) -> None`
  - `append_event(...) -> None` as the one-item wrapper around `append_events`
  - `load_events(paths: RunPaths) -> list[dict[str, object]]`
  - `store_evidence(paths: RunPaths, content: bytes) -> str`
  - `recovery_status(paths: RunPaths) -> dict[str, object]`

- [ ] **Step 1: Write failing transaction tests**

Cover:

```python
def test_content_addressed_evidence_is_idempotent(self) -> None:
    digest1 = store.store_evidence(self.paths, b"proof\\n")
    digest2 = store.store_evidence(self.paths, b"proof\\n")
    self.assertEqual(digest1, digest2)
    self.assertEqual(b"proof\\n", (self.paths.evidence / digest1.removeprefix("sha256:")).read_bytes())

def test_orphan_transaction_forces_recovery_required(self) -> None:
    orphan = self.paths.transactions / "append-orphan"
    orphan.mkdir(parents=True)
    status = store.recovery_status(self.paths)
    self.assertTrue(status["recovery_required"])
    self.assertEqual([], status["next_commands"])
```

Also test concurrent lock exclusion, interrupted publication leaving prior state untouched, hash-chain truncation, symlink/reparse rejection, and no automatic cleanup.

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m unittest evals/hotl-governance/test_hotl_transactions.py -v
```

Expected: import failure because `hotl_store.py` is absent.

- [ ] **Step 3: Implement paths, lock, and atomic writers**

Use `.hotl/runs/<execution-id>/` with sibling `.hotl/evidence/<sha256>`. Mirror the existing controller's ownership checks, exclusive lock file, temporary transaction directory, fsync, and `os.replace`, but do not import private functions from `gpc_loop_controller.py`.

The publication order must be:

```text
1. validate complete candidate in transaction directory
2. publish new immutable evidence objects
3. publish replacement events.jsonl
4. publish replacement projection/state.json last
5. remove only the owned, fully verified transaction directory
```

- [ ] **Step 4: Implement event replay loading and recovery classification**

`load_events` must validate every sequence and previous hash. Any malformed log, orphan transaction, missing state, non-directory evidence root, or link/reparse point returns or raises a stable `RECOVERY_REQUIRED` error. Do not add repair or cleanup commands.

- [ ] **Step 5: Run focused transaction tests**

Run:

```powershell
python -m unittest evals/hotl-governance/test_hotl_transactions.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add skills/hotl-governance/scripts/hotl_store.py evals/hotl-governance/test_hotl_transactions.py
git commit -m "feat: persist HOTL events atomically"
```

---

### Task 4: Implement Deterministic Replay, Gates, and Successor Executions

**Files:**
- Create: `skills/hotl-governance/scripts/hotl_controller.py`
- Create: `evals/hotl-governance/test_hotl_controller.py`

**Interfaces:**
- Consumes: validated event list and storage APIs.
- Produces:
  - `State(str, Enum)` values from the approved state set.
  - `replay(policy: Mapping[str, object], events: Sequence[Mapping[str, object]]) -> Projection`
  - `project_event(projection: Projection, event: Mapping[str, object]) -> Projection` (evidence projection only; evidence events never advance state)
  - `allowed_transitions(projection: Projection) -> tuple[str, ...]`
  - `evaluate_gate(projection: Projection, gate: str) -> tuple[bool, tuple[str, ...]]`
  - `commit_transition(repository: Path, execution_id: str, gate: str) -> dict[str, object]` (the only normal state-advance path)
  - `record_event(repository: Path, execution_id: str, event: Mapping[str, object], artifacts: Mapping[str, bytes]) -> dict[str, object]`
  - `start_successor(repository: Path, predecessor_id: str, receipt: Mapping[str, object], policy: Mapping[str, object]) -> dict[str, object]`
  - `status_execution(repository: Path, execution_id: str) -> dict[str, object]`

- [ ] **Step 1: Write failing transition and completion tests**

Use a table-driven test proving ingestion and transition evaluation are separate:

```python
def fixture_projection(state: str) -> controller.Projection:
    return controller.empty_projection(
        execution_id="EXEC-123456789ABC",
        state=controller.State(state),
    )


def fixture_event(event_type: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": "EVT-123456789ABC",
        "execution_id": "EXEC-123456789ABC",
        "sequence": 1,
        "type": event_type,
        "payload": valid_payload_for(event_type),
        "issuer": {"kind": "controller", "id": "hotl-governance", "version": "1"},
        "subject_ids": [],
        "artifact_refs": [],
        "result": "pass",
        "input_digest": "sha256:" + "1" * 64,
        "output_digest": "sha256:" + "2" * 64,
        "previous_event_hash": None,
        "timestamp": "2026-08-09T00:00:00Z",
    }


def test_evidence_event_never_advances_state(self) -> None:
    projection = fixture_projection("REQUIREMENTS")
    result = controller.project_event(
        projection, fixture_event("receipt_imported")
    )
    self.assertEqual("REQUIREMENTS", result.state.value)


def test_only_transition_committed_advances_state(self) -> None:
    projection = fixture_projection("REQUIREMENTS")
    result = controller.project_event(
        projection,
        fixture_transition(gate="G1", source="REQUIREMENTS", target="IMPLEMENT"),
    )
    self.assertEqual("IMPLEMENT", result.state.value)
```

Add tests proving:

- same policy + same events yields byte-identical projection;
- repeated stable `root_cause_id` escalates on the second consecutive valid failed review;
- a malformed or stale review does not consume a review round;
- different free text with identical IDs produces the same transition;
- any frozen scope/policy/authority change terminates the predecessor;
- successor requires terminal predecessor and lineage receipt;
- `RECOVERY_REQUIRED` and `STOPPED` cannot resume;
- incomplete typed provenance cannot satisfy G4;
- complete typed provenance with current evidence does satisfy G4.

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m unittest evals/hotl-governance/test_hotl_controller.py -v
```

Expected: import failure because `hotl_controller.py` is absent.

- [ ] **Step 3: Implement projection types and pure replay**

Define:

```python
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
```

`replay` must be pure: no filesystem, clock, random, or environment access.

`project_event` must reject any state-changing evidence event. Only a closed-schema `transition_committed` payload whose from-state, gate, evidence-set digest, and cycle match the projection may advance state.

- [ ] **Step 4: Implement typed completion and evidence invalidation**

Implement `completion_errors(projection) -> tuple[str, ...]` that checks, per active requirement, code implementation, test verification, command execution, evidence production/proof/current snapshot, accepted review input digest, and change inclusion.

On `snapshot_activated`, increment `cycle_id` and append the activation plus all required `evidence_invalidated` events in one `append_events(...)` transaction. Keep historical evidence in projection but exclude prior-cycle evidence from G2/G3/G4. Implement the public `evidence_set_digest(requirements_digest, snapshot_digest, evidence_records)` contract using sorted `(evidence_id, artifact_digest, test_id)` records.

Count a review round only when its schema, execution, current snapshot, current evidence-set binding, and semantic-review commit are valid. Malformed or stale receipts consume no round. Escalate when the same stable root-cause ID appears in two consecutive valid failed reviews, or on the third valid failed review.

- [ ] **Step 5: Implement terminal and successor behavior**

`start_successor` must require:

```python
{
    "predecessor_execution_id": "EXEC-...",
    "lineage_receipt_digest": "sha256:...",
    "supersedes": [{"new_id": "REQ-2", "old_id": "REQ-1"}],
}
```

Reject a nonterminal predecessor, missing lineage digest, or mutation of the predecessor log. Allow multiple successors to branch from one terminal predecessor; v1 has no repository-global lineage registry.

- [ ] **Step 6: Run focused controller tests**

Run:

```powershell
python -m unittest evals/hotl-governance/test_hotl_controller.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add skills/hotl-governance/scripts/hotl_controller.py evals/hotl-governance/test_hotl_controller.py
git commit -m "feat: enforce HOTL gates and replay"
```

---

### Task 5: Implement the Stable CLI and Privileged Receipt Paths

**Files:**
- Create: `skills/hotl-governance/scripts/hotl_governance.py`
- Create: `evals/hotl-governance/test_hotl_cli.py`

**Interfaces:**
- Consumes: controller command functions.
- Produces commands: `init`, `status`, `record`, `approve`, `import-receipt`, `evaluate`, `project`, `verify-log`, `start-successor`.
- Every success emits `{"ok":true,"command":"...","result":{...}}`; every failure emits `{"ok":false,"command":"...","error":{"code":"...","message":"..."}}`.

- [ ] **Step 1: Write failing CLI tests**

Add:

```python
def snapshot_tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_status_is_read_only_and_lists_only_allowed_commands(self) -> None:
    before = snapshot_tree(self.repository / ".hotl")
    result = cli.main_json(["status", "--repo", str(self.repository), "--execution", self.execution])
    after = snapshot_tree(self.repository / ".hotl")
    self.assertEqual(before, after)
    self.assertEqual(["import-receipt"], result["result"]["next_commands"])

def test_generic_record_cannot_claim_privileged_actor(self) -> None:
    result = cli.main_json([
        "record", "--repo", str(self.repository), "--execution", self.execution,
        "--event", str(self.inputs / "fake-human-approval.json"),
    ])
    self.assertFalse(result["ok"])
    self.assertEqual("PRIVILEGED_EVENT_REQUIRES_RECEIPT", result["error"]["code"])
```

Add end-to-end tests for all four gates, stale receipt, wrong nonce, wrong authority digest, recovery hard stop, and `project --stdout`.

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m unittest evals/hotl-governance/test_hotl_cli.py -v
```

Expected: import failure because `hotl_governance.py` is absent.

- [ ] **Step 3: Implement parser and stable envelope**

Use an `argparse.ArgumentParser` subclass that raises instead of exiting. Add `main_json(argv: Sequence[str]) -> dict[str, object]` for tests and `main()` for CLI output.

`record` accepts only nonprivileged event types. `approve` requires a host approval evidence JSON file and binds its digest to the pending approval target. `import-receipt` selects a closed issuer validator; it never trusts an arbitrary `issuer_skill` without the matching validator.

- [ ] **Step 4: Implement verification report separation**

`verify-log` must emit separate booleans and findings for:

```json
{
  "log_integrity": true,
  "projection_determinism": true,
  "immutable_evidence_integrity": true,
  "current_snapshot_integrity": true,
  "historical_observations_checked": 3
}
```

Do not compare historical mutable repository paths to current hashes as a failure condition.

- [ ] **Step 5: Run CLI and all new controller tests**

Run:

```powershell
python -m unittest discover -s evals/hotl-governance -p "test_hotl_*.py" -v
```

Expected: all contract, transaction, controller, and CLI tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add skills/hotl-governance/scripts/hotl_governance.py evals/hotl-governance/test_hotl_cli.py
git commit -m "feat: add HOTL governance CLI"
```

---

### Task 6: Publish and Export Bound GPT Pro Governance Receipts

**Files:**
- Modify: `skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py`
- Modify: `skills/gpt-pro-codex-loop/scripts/gpc_loop.py`
- Modify: `skills/gpt-pro-codex-loop/scripts/capture_snapshot.py`
- Modify: `skills/gpt-pro-codex-loop/SKILL.md`
- Modify: `skills/gpt-pro-codex-loop/README.md`
- Modify: `evals/gpt-pro-codex-loop/test_gpc_loop.py`
- Modify: `evals/gpt-pro-codex-loop/test_capture_snapshot.py`

**Interfaces:**
- Consumes: existing trusted GPT Pro state and artifacts; no HOTL module imports.
- Produces:
  - `export_governance_receipt(repository: Path, task_slug: str, receipt_type: str) -> dict[str, object]`
  - CLI `export-governance-receipt --type requirements|review|final`
  - receipt fields required by the HOTL contract.
  - immutable `governance-receipt-requirements.json`, `governance-receipt-review.json`, and `governance-receipt-final.json` artifacts created by their authoritative transitions.

- [ ] **Step 1: Write failing receipt export tests**

Extend `ControllerCase`:

```python
def test_requirements_receipt_binds_frozen_state(self) -> None:
    self._freeze_initial_requirements()
    receipt = controller.export_governance_receipt(
        self.repository, "controller-test", "requirements"
    )
    state = self._state()
    self.assertEqual("gpt-pro-codex-loop", receipt["issuer_skill"])
    self.assertEqual(state["active_requirements_digest"], receipt["output_digest"])
    self.assertEqual(state["bound_conversation_url"], receipt["binding"]["conversation_url"])
    self.assertEqual(state["visible_model_label"], receipt["binding"]["model_label"])

def test_final_receipt_is_unavailable_before_final_verify(self) -> None:
    self._build_valid_report()
    with self.assertRaises(controller.ControllerError) as caught:
        controller.export_governance_receipt(
            self.repository, "controller-test", "final"
        )
    self.assertEqual("RECEIPT_NOT_AVAILABLE", caught.exception.code)
```

Add replay/stale tests and a byte-for-byte state-tree assertion showing export is read-only.

Add snapshot tests proving untracked `.hotl/` metadata does not enter the product snapshot, while tracked or staged `.hotl/` content fails metadata hygiene.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
python -m unittest evals/gpt-pro-codex-loop/test_gpc_loop.py -k governance_receipt -v
```

Expected: FAIL because the export function and command do not exist.

- [ ] **Step 3: Publish receipts inside the authoritative transitions**

Create the requirements receipt when requirements become frozen and the review receipt when an accepted review is committed. Create the final receipt only after the controller's successful `final-verify`, in the authoritative transaction that publishes `final-gate.json`. Set `issued_at_unix` once from `int(time.time())` during each authoritative mutation and persist it in the immutable receipt artifact.

Build each receipt from the candidate state and the exact artifacts already validated for that transition. Do not add a second state transition or a best-effort receipt write.

- [ ] **Step 4: Implement read-only receipt export**

Read and revalidate the stored receipt against current trusted state and artifacts. Use:

```python
GOVERNANCE_RECEIPT_SCHEMA_VERSION = 1

def export_governance_receipt(
    repository: Path, task_slug: str, receipt_type: str
) -> dict[str, object]:
    paths = resolve_run(repository, task_slug)
    state = load_json(paths.state)
    receipt_path = paths.run / f"governance-receipt-{receipt_type}.json"
    receipt = load_json(receipt_path)
    return _validate_governance_receipt(receipt, state, paths, receipt_type)
```

Required binding includes run/task identity, receipt type, transition input-state digest, transaction or turn identity, nonce, input/output digest, authority snapshot digest, model/plan/reasoning labels, conversation URL, snapshot digest where applicable, and persisted `issued_at_unix`. Repeated export must be byte-identical and must not use the current clock.

- [ ] **Step 5: Add the CLI command**

Add `export-governance-receipt` to `COMMANDS`, parser choices, and dispatch. Its output uses the existing stable CLI envelope and never appears in `next_commands` as a mutation.

Update `capture_snapshot.py` to treat both `.ai-pro-loop` and `.hotl` as reserved metadata roots. Reject tracked or staged content under either root before excluding it from snapshot manifests. Extend `metadata_hygiene_is_clean` to check both roots.

- [ ] **Step 6: Document additive behavior**

State explicitly in `SKILL.md` and `README.md`:

- normal standalone workflow is unchanged;
- export is read-only;
- exported receipts do not authorize commit, push, PR, deploy, or requirement changes;
- outer HOTL validation may consume the receipt.

- [ ] **Step 7: Run GPT Pro regression suites**

Run:

```powershell
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_*.py" -v
```

Expected: all existing and new tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add skills/gpt-pro-codex-loop evals/gpt-pro-codex-loop/test_gpc_loop.py
git commit -m "feat: export GPT Pro governance receipts"
```

---

### Task 7: Normalize Bounded Sol Consultation Receipts

**Files:**
- Create: `skills/orchestrate-gpt-pro-sol-advisor/scripts/governance_receipt.py`
- Modify: `evals/orchestrate-gpt-pro-sol-advisor/policy.py`
- Modify: `evals/orchestrate-gpt-pro-sol-advisor/cases.json`
- Modify: `evals/orchestrate-gpt-pro-sol-advisor/test_contract.py`
- Modify: `skills/orchestrate-gpt-pro-sol-advisor/SKILL.md`
- Modify: `skills/orchestrate-gpt-pro-sol-advisor/README.md`

**Interfaces:**
- Consumes: already-attested `route()` result and Codex disposition.
- Produces:
  - production `governance_receipt(scenario: dict[str, Any], route_result: dict[str, Any], disposition: dict[str, str] | None) -> dict[str, Any]`
  - `consultation` receipt or `no-consultation` receipt with a closed reason.

- [ ] **Step 1: Write failing policy receipt tests**

Add:

```python
def test_attested_consultation_receipt_is_bound_and_dispositioned(self) -> None:
    scenario = attested_combined(
        execution_id="EXEC-123456789ABC",
        invocation_id="INV-1",
        input_digest="sha256:" + "1" * 64,
        output_digest="sha256:" + "2" * 64,
        authority_snapshot_digest="sha256:" + "3" * 64,
        nonce="a" * 32,
        codex_commitment_boundary=True,
        concrete_question=True,
        precise_question="Does this boundary hold?",
        material_risk=True,
        decision_value=True,
    )
    routed = POLICY.route(scenario)
    receipt = POLICY.governance_receipt(
        scenario, routed, {"disposition": "accept", "rationale": "Compatible."}
    )
    self.assertEqual("consultation", receipt["receipt_type"])
    self.assertEqual("sol_advisor_advisor", receipt["binding"]["role"])
    self.assertEqual("read-only", receipt["binding"]["sandbox"])

def test_unavailable_advisor_cannot_be_downgraded_to_no_consultation(self) -> None:
    scenario = attested_combined(advisor_invocation_succeeded=False)
    routed = POLICY.route(scenario)
    with self.assertRaises(POLICY.ReceiptError):
        POLICY.governance_receipt(scenario, routed, None)
```

Add low-risk `NO_MATERIAL_UNCERTAINTY` and standalone `NOT_APPLICABLE` cases.

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m unittest evals/orchestrate-gpt-pro-sol-advisor/test_contract.py -k receipt -v
```

Expected: FAIL because `governance_receipt` does not exist.

- [ ] **Step 3: Implement closed receipt normalization**

Implement `governance_receipt` in the production script; eval policy imports or invokes that issuer instead of owning an eval-only implementation. It may emit consultation only when `advice_admitted == 1`, runtime observations are trusted, and disposition is one of `accept`, `reject`, `partially accept`.

It may emit no-consultation only for:

```python
NO_CONSULTATION_REASONS = {
    "NOT_APPLICABLE",
    "NO_MATERIAL_UNCERTAINTY",
    "POLICY_NOT_REQUIRED",
    "ADVISOR_UNAVAILABLE",
}
```

Allow `ADVISOR_UNAVAILABLE` only when an explicit standalone policy says advisor availability is not a runtime dependency. Do not emit it for combined-mode preflight, invocation, or attestation failure; those remain hard stops.

- [ ] **Step 4: Update Skill and cases**

Document that receipt recording is audit output, not Sol approval or final review. Add case IDs:

- `attested-advice-emits-bound-receipt`
- `low-risk-emits-no-consultation`
- `invocation-failure-emits-no-receipt`
- `attestation-failure-emits-no-receipt`

- [ ] **Step 5: Run composition regression**

Run:

```powershell
python -m unittest evals/orchestrate-gpt-pro-sol-advisor/test_contract.py -v
python -m unittest tests/test_orchestrate_gpt_pro_sol_advisor.py -v
```

Expected: all tests PASS and existing routing results remain unchanged.

- [ ] **Step 6: Commit**

```powershell
git add skills/orchestrate-gpt-pro-sol-advisor evals/orchestrate-gpt-pro-sol-advisor
git commit -m "feat: record bounded Sol advice receipts"
```

---

### Task 8: Add Root-Suite and Cross-Adapter End-to-End Coverage

**Files:**
- Create: `tests/test_hotl_governance.py`
- Modify: `.github/workflows/validate-skills.yml`
- Modify: `evals/hotl-governance/test_hotl_cli.py`

**Interfaces:**
- Consumes: all controller and adapter public interfaces.
- Produces: CI-enforced Linux/Windows execution and one full evidence chain fixture.

- [ ] **Step 1: Write the root-suite loader and workflow assertion**

```python
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals" / "hotl-governance"
WORKFLOW = ROOT / ".github" / "workflows" / "validate-skills.yml"
FOCUSED_COMMAND = 'python -m unittest discover -s evals/hotl-governance -p "test_*.py" -v'


class HotlWorkflowTests(unittest.TestCase):
    def test_linux_and_windows_jobs_run_hotl_suite(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        for name, runner in (
            ("hotl-governance-ubuntu", "ubuntu-latest"),
            ("hotl-governance-windows", "windows-latest"),
        ):
            with self.subTest(name=name):
                job = workflow["jobs"][name]
                self.assertEqual(runner, job["runs-on"])
                self.assertTrue(
                    any(step.get("run") == FOCUSED_COMMAND for step in job["steps"])
                )


def load_tests(
    loader: unittest.TestLoader,
    _: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for path in sorted(EVAL_ROOT.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(f"hotl_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    suite.addTests(loader.loadTestsFromTestCase(HotlWorkflowTests))
    return suite
```

- [ ] **Step 2: Run and verify workflow test failure**

Run:

```powershell
python -m unittest tests/test_hotl_governance.py -v
```

Expected: FAIL because the workflow job does not exist.

- [ ] **Step 3: Add Linux and Windows focused jobs**

Use Python 3.12, install `requirements-validation.txt`, and run exactly:

```yaml
- run: python -m unittest discover -s evals/hotl-governance -p "test_*.py" -v
```

Name jobs `hotl-governance-ubuntu` and `hotl-governance-windows`.

- [ ] **Step 4: Add full-chain and invalidation end-to-end tests**

Build a fixture that:

1. initializes policy and authority;
2. imports a frozen requirements receipt;
3. records code/test/change nodes and typed edges;
4. records current snapshot and successful command evidence;
5. imports semantic review and optional no-consultation receipt;
6. reaches `COMPLETE`;
7. replays to byte-identical projection.

Add a second fixture that changes the snapshot after local verification and asserts G4 is closed until replacement evidence and review are imported.

- [ ] **Step 5: Run focused and root suites**

Run:

```powershell
python -m unittest discover -s evals/hotl-governance -p "test_*.py" -v
python -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_hotl_governance.py .github/workflows/validate-skills.yml evals/hotl-governance/test_hotl_cli.py
git commit -m "test: validate HOTL governance on Windows and Linux"
```

---

### Task 9: Validate the Catalog, Context Budget, and Installable Skill

**Files:**
- Modify: generated catalog section in `README.md`
- Modify only after explicit inspected approval: `context-budget-baseline.json`, `context-budget-comparison.json`, `context-budget-manifest.json`

**Interfaces:**
- Consumes: finished change set.
- Produces: repository-wide validation evidence and an installable canonical Skill.

- [ ] **Step 1: Validate the Skill package**

Run:

```powershell
python C:\\Users\\楫屋寿弥\\.codex\\skills\\.system\\skill-creator\\scripts\\quick_validate.py skills/hotl-governance
python scripts/validate-skills.py
```

Expected: both commands PASS with no metadata, reference, or frontmatter errors.

- [ ] **Step 2: Regenerate and inspect the catalog**

Run:

```powershell
python scripts/generate-skill-catalog.py
git diff -- README.md
```

Expected: only the generated `hotl-governance` catalog entry changes.

- [ ] **Step 3: Run the unchanged context-budget baseline**

Run:

```powershell
python scripts/context_budget_report.py --repo . --manifest context-budget-manifest.json --baseline context-budget-baseline.json --max-growth-bytes 0
```

Expected: either PASS with zero growth or a precise HOTL-only growth report. Do not update the baseline merely because this command fails.

- [ ] **Step 4: Inspect and, only if authorized, update intentional growth**

Inspect:

```powershell
git diff -- context-budget-manifest.json context-budget-baseline.json context-budget-comparison.json
```

Success: every increased byte is attributable to the approved HOTL Skill or additive adapter text. Obtain explicit approval before accepting updated baseline files, then rerun the Step 3 command and require PASS.

- [ ] **Step 5: Run the complete verification set**

Run:

```powershell
python -m unittest discover -s evals/hotl-governance -p "test_*.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_*.py" -v
python -m unittest evals/orchestrate-gpt-pro-sol-advisor/test_contract.py -v
python -m unittest discover -s tests -v
python scripts/validate-skills.py
python scripts/context_budget_report.py --repo . --manifest context-budget-manifest.json --baseline context-budget-baseline.json --max-growth-bytes 0
git diff --check
```

Expected: every command PASS; `git diff --check` produces no output.

- [ ] **Step 6: Inspect the final diff and scope**

Run:

Capture the comparison base during implementation preflight:

```powershell
$BASE_SHA = git rev-parse HEAD
```

Then use the captured value:

```powershell
git status --short
git diff --stat "$BASE_SHA...HEAD"
git diff "$BASE_SHA...HEAD" -- skills/hotl-governance skills/gpt-pro-codex-loop skills/orchestrate-gpt-pro-sol-advisor evals/hotl-governance evals/gpt-pro-codex-loop evals/orchestrate-gpt-pro-sol-advisor tests/test_hotl_governance.py .github/workflows/validate-skills.yml README.md
```

Success: no files outside the approved plan changed. The HOTL runtime performed no commit, push, PR, or deploy; the development plan's explicit checkpoint commits are intentional and separate from runtime behavior.

- [ ] **Step 7: Commit generated integration changes**

```powershell
git add README.md context-budget-baseline.json context-budget-comparison.json context-budget-manifest.json
git commit -m "chore: register HOTL governance skill"
```

If context files did not intentionally change, omit them from `git add`.

---

## Final Protocol Verification

Before implementation in combined mode:

1. Observe `get_setup_status`, `get_preferences`, and the exact `sol_advisor_advisor` role in a fresh Codex task.
2. Stop before GPT Pro initialization if any combined-mode preflight fails.
3. Run `gpt-pro-codex-loop` as the outer protocol.
4. Use one bounded Sol consultation only at a real Codex commitment boundary; never invoke `sol-advisor:orchestration` inside combined mode.
5. Import bound requirements, review, and applicable Sol receipts into HOTL; ingestion must not advance state.
6. Require the GPT Pro controller's successful `final-verify`, then export its final receipt.
7. Import the final receipt, explicitly evaluate G4, and require a valid `transition_committed` event to reach `COMPLETE`.
8. Run HOTL `verify-log` and require the hash-chain witness, projection, artifacts, and G4 integrity to pass.
9. Inspect the complete diff and rerun the verification commands from the primary session before accepting completion.
