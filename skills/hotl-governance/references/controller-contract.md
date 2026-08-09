# Controller Contract

This reference is the normative model for `hotl-governance`. The controller is deterministic: a fixed policy snapshot and ordered event log yield the same state, provenance projection, and allowed next commands. It validates closed-schema values, stable identifiers, and canonical digests; it does not interpret free text.

## State machine

```text
INIT -> REQUIREMENTS -> IMPLEMENT -> LOCAL_VERIFY -> SEMANTIC_REVIEW -> COMPLETE
SEMANTIC_REVIEW -> IMPLEMENT  (corrective edge only)

INIT | REQUIREMENTS | IMPLEMENT | LOCAL_VERIFY | SEMANTIC_REVIEW
  -> ESCALATED | RECOVERY_REQUIRED | STOPPED
```

`COMPLETE`, `ESCALATED`, `RECOVERY_REQUIRED`, and `STOPPED` are terminal for the same execution. An unlisted transition is rejected. A material change to scope, policy, authority snapshot, or frozen requirements is not an in-place edit: terminate the execution and create a successor that records `predecessor_execution_id`, `lineage_receipt_digest`, and an explicit `supersedes` relation.

## Transition table

| From | Condition | To |
| --- | --- | --- |
| none | valid policy snapshot and execution identity are published | `INIT` |
| `INIT` | `INIT`: requirements are published, or a successor has validated lineage | `REQUIREMENTS` |
| `REQUIREMENTS` | G1 passes | `IMPLEMENT` |
| `IMPLEMENT` | G2 passes | `LOCAL_VERIFY` |
| `LOCAL_VERIFY` | G3 passes | `SEMANTIC_REVIEW` |
| `SEMANTIC_REVIEW` | `CORRECTIVE`: current rejected review is correctable | `IMPLEMENT` |
| `SEMANTIC_REVIEW` | `ESCALATION`: stable-root or round limit is reached | `ESCALATED` |
| `SEMANTIC_REVIEW` | G4 passes for the current accepted review | `COMPLETE` |
| mutable state | `MATERIAL_CHANGE`: current bound authority requires replacement | `STOPPED` |
| mutable state | `STOP`: current bound stop authority explicitly stops | `STOPPED` |
| mutable state | transaction or integrity ambiguity | `RECOVERY_REQUIRED` |

Reject every transition not listed in this table.

`transition_committed.gate` is a compatibility name for a closed lifecycle
decision discriminator. Its values are `INIT`, `G1`, `G2`, `G3`, `G4`,
`CORRECTIVE`, `ESCALATION`, `MATERIAL_CHANGE`, and `STOP`. Only G1 through G4
are gates. Evidence events never advance state. A failed gate or lifecycle
predicate emits no transition.

## Gate table

| Gate | From | Required predicate | To |
| --- | --- | --- | --- |
| G1 | REQUIREMENTS | active frozen requirements plus the exact accepted GPT Pro `requirements` receipt, bound to policy authority and requirements digest | IMPLEMENT |
| G2 | IMPLEMENT | controller-owned `record-implementation` receipt binds a re-read change manifest, worker report, base identity, snapshot, requirements, code/test/change graph, and exact artifact digests | LOCAL_VERIFY |
| G3 | LOCAL_VERIFY | exact current-cycle local evidence plus controller-owned zero-exit receipts for every closed verification spec (exact argv, test IDs, and artifact paths), each shell-free and re-hashed before/after execution | SEMANTIC_REVIEW |
| G4 | SEMANTIC_REVIEW | current accepted review, GPT Pro final receipt, exact Task 7 Sol consultation/disposition or no-consultation audit receipt, and complete active-requirement coverage | COMPLETE |

Only `evaluate` may advance a gate. `record` and `import-receipt` append validated evidence but leave state unchanged. A failed predicate emits no transition; it never creates an implicit repair path.

## Requirements input binding

Initialization and successor creation accept two exact closed requirements
inputs. The legacy form, `{requirements: [sorted IDs]}`, preserves the digest
of that canonical ID manifest. The external-bound form is exactly
`{requirements: [sorted IDs], source_digest: "sha256:...", source_artifact:
VALUE}`. HOTL must canonicalize `source_artifact`, prove its SHA-256 equals
`source_digest`, store those exact canonical bytes content-addressed, and use
`source_digest` as the projection requirements digest before publishing the
run. The ID manifest remains independently stored for typed requirement-node
audit. A missing counterpart, unknown field, unrepresentable value, or digest
mismatch fails before run creation.

For GPT Pro requirements, the external artifact is the exact persisted
canonical `requirements.json` value. Its artifact `requirements_digest` is
intentionally distinct from the receipt's semantic-transition `output_digest`
(`active_requirements_digest`). The receipt's `input_digest` independently
binds the GPT pre-transition input; HOTL does not reinterpret it as its own
requirements or evidence digest.

## Receipt contract

Each privileged source receipt is issuer-specific and closed-schema. After its
issuer-specific validator admits it, `receipt_imported` records this exact
closed projection:

- `receipt_id`, `receipt_type`, `receipt_digest`, and `issuer_skill`;
- `authority_snapshot_digest` and `requirements_digest`;
- `snapshot_digest`, `evidence_set_digest`, and `cycle_id` when the receipt is
  current-cycle authority.

The type-to-issuer allowlist is exact: `requirements`, `approval`,
`semantic_review`, `final`, `material_change`, and `stop` are issued by
`gpt-pro-codex-loop`; controller-owned `implementation` by `codex` and
`verification` by `hotl-local-verifier`; `sol_audit` by
`orchestrate-gpt-pro-sol-advisor`; and `lineage` by `hotl-governance-lineage`.
Agentic G1 uses the requirements receipt as its approval boundary; `approve`
fails closed unless a non-worker-writable provider exists. Requirements and
approval receipts bind authority and requirements only.
Implementation, verification, review, and final receipts bind authority,
requirements, snapshot, evidence set, and cycle. Material-change and stop
receipts also bind the evidence set and cycle, while their snapshot is optional
so they can terminate an execution before snapshot activation. Lineage uses
null lifecycle bindings because its immutable evidence object carries the
predecessor and supersedes bindings.

An external `gpt-pro-codex-loop` source receipt also has an exact issuer
provenance binding: task slug, deterministic run ID, attested conversation URL,
model label, reasoning label, and plan label. That source binding is distinct
from the outer controller's live lifecycle binding. GPT requirements receipts
arrive with null snapshot/evidence/cycle fields and remain frozen-null after
admission. GPT semantic-review and final receipts arrive with the GPT-reviewed
snapshot but null external evidence/cycle fields; after validating issuer
provenance and current execution, authority, requirements, and snapshot, HOTL
stamps the admitted event with its current evidence-set digest and cycle under
the caller-held lock. Later lifecycle changes still make that admitted receipt
non-current. Other issuers retain their existing closed schemas and binding
rules.

The deterministic GPT governance identity algorithm is closed as v1. Canonical
JSON means UTF-8, sorted keys, compact separators, and exactly one terminal LF.
For task slug `T`, `run_id` is the literal `gpc-loop-` + `T`.
`execution_id` is `EXEC-` plus the first 12 uppercase hexadecimal characters of
SHA-256 over the canonical bytes of
`{"issuer_skill":"gpt-pro-codex-loop","run_id":RUN_ID,"task_slug":T}`.
`authority_snapshot_digest` is `sha256:` plus SHA-256 over the canonical bytes
of the exact six-field provenance binding. `nonce` is the first 32 lowercase
hexadecimal characters of SHA-256 over the canonical bytes of
`{"binding":BINDING,"purpose":"gpt-pro-governance-receipt-nonce-v1"}`.
The distinct identity object and nonce purpose string provide domain
separation. HOTL recomputes all three values from the binding before comparing
them with its outer policy; a caller cannot make a relabeled receipt valid by
changing the policy to match the relabeling.

Generic `record` accepts only `evidence_recorded` from a tool issuer. It rejects
all receipts, reviews, findings, transitions, snapshot changes, invalidations,
nodes, and edges as privileged/controller-authored events. Task 4 deliberately
exposes no generic receipt-import boundary: an issuer-specific importer must
validate the complete source receipt before constructing the closed admitted
projection. Replay accepts already-admitted events and never treats a caller's
issuer label as proof of authority.

Semantic review findings use stable `finding_id` and `root_cause_id`; the controller never compares finding prose. A rejected `review_recorded` atomically commits its unique, sorted, non-empty `root_cause_ids`; an accepted review commits an empty set. Later `finding_recorded` events cannot alter a counted round. Each review binds a current authorized semantic-review receipt. Receipts must match the execution, authority, requirements, current snapshot, current evidence-set digest, cycle, issuer schema, and replay protections as applicable. Malformed, mismatched, stale, wrong-issuer, duplicate-ID, or duplicate-digest receipts fail closed and do not consume a valid review round.

## Typed provenance triples

The projection accepts only these completion-relevant triples:

| Source | Edge | Target |
| --- | --- | --- |
| code | implements | requirement |
| test | verifies | requirement |
| command | executes | test |
| command | produces | evidence |
| evidence | proves | test |
| evidence | supports | review |
| review | reviews | requirement |
| code | included_in | change |
| test | included_in | change |
| failure | violates | requirement |
| change | fixes | failure |
| evidence | derived_from | evidence |
| review | derived_from | review |
| change | derived_from | change |
| requirement | supersedes | requirement |
| policy | supersedes | policy |

Reject every triple not listed in this table. `derived_from` is audit lineage and does not satisfy completion coverage on its own.

Node IDs are execution-local and typed (`REQ-`, `CODE-`, `TEST-`, `CMD-`, `EVID-`, `REV-`, `CHG-`, `FAIL-`, and `POL-`). Unknown types, invalid IDs, or unsupported edges are rejected.

## Completion predicate

For every active requirement, require active code that implements it and active test that verifies it in the *same* active change, plus a command that executes the test and produces valid current evidence proving it. Require an accepted review bound to the current evidence set.

For a bound outer protocol, run the GPT Pro controller's `final-verify`, export its final governance receipt, import that receipt into HOTL, and only then evaluate G4. G4 may commit only when all active requirements meet this predicate and no unresolved findings remain. After `COMPLETE`, run `verify-log` to revalidate the event chain, witness, projection, and artifact integrity.

## Evidence lifecycle

Store immutable events, receipts, and command outputs content-addressably at `.hotl/evidence/<sha256>`. An event is append-only and includes schema version, event ID, execution ID, sequence, type, closed payload, issuer, subject IDs, artifact references, result, input/output digests, previous event hash, and timestamp. Replay rejects every event after a terminal transition, including evidence-only events.

Canonical event bytes, `execution_id + sequence + previous_event_hash`, and the state witness (`event_count`, `head_event_hash`) make replay deterministic and detect truncation. Publish an atomic batch only after validating the complete candidate log; `verify-log` checks the chain, witness, projection, and artifact integrity.

When code, tests, or the active snapshot change, append `evidence_invalidated` and mark the related projection record `historically_valid`. Preserve it for audit but exclude it from G3/G4 current coverage. A new validation produces `valid_current` evidence in the current `cycle_id`; corrective edges and snapshot activation increment the cycle.

## Path rules

Artifact references are repository-relative canonical POSIX paths. Reject absolute paths, empty paths, `.` or `..` segments, NUL, repository escapes, symlink/reparse-point escapes, and non-canonical aliases. Bind every artifact reference to a SHA-256 digest. Treat historical observations as immutable even when the current mutable file later changes.

Canonical JSON uses UTF-8, sorted object keys, no BOM, finite integers only, no lone Unicode surrogates, and no duplicate or unknown fields. Timestamps, display labels, and diagnostics cannot affect transitions or replay.

## Threat model

The hash chain detects accidental corruption, partial modification, truncation, and naive tampering. It does not make a repository writable by an adversary tamper-proof: an attacker with full write access can rewrite the log and state together. Use an external signed checkpoint, repository secret, or remote transparency log for that stronger threat model.

Do not treat an LLM response, generic event, local CLI assertion, mutable working-tree file, or free-text review as privileged authority. The controller accepts only the required closed-schema receipt and current evidence bindings.

## Recovery

On transaction or integrity ambiguity, enter `RECOVERY_REQUIRED` and stop the same execution. Do not delete, rewrite, reparent, or otherwise repair the event chain. Preserve all artifacts and perform read-only diagnosis of the state witness, event head, orphan transaction, and logs.

v1 has no repair command. An authorized operator may establish a known-good source outside the controller and start a new successor that records lineage to the terminal predecessor. A `RECOVERY_REQUIRED` predecessor is classified read-only and is never repaired or rewritten. The successor, not the compromised execution, receives any further state transitions.

The lineage digest must identify an existing immutable evidence object whose
bytes are exactly the canonical predecessor/supersedes binding. Missing,
corrupt, symlink/reparse, self-referential, duplicate, wrong-predecessor, and
nonterminal lineage fail closed. Valid branches may share one predecessor. The
successor is published as one atomic initial batch containing the validated
`receipt_imported` lineage event, active requirement nodes and canonical requirement
content, an explicit `INIT` lifecycle transition, and immutable canonical policy and
requirements evidence under their declared digests. A healthy successor therefore
begins at `REQUIREMENTS`; no later privileged backdoor is needed to establish its G1
completion graph.
