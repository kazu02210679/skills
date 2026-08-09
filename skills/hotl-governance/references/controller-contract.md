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
| G1 | REQUIREMENTS | active frozen requirements plus current `requirements` and `approval` receipts from `gpt-pro-codex-loop`, bound to the policy authority and requirements digest | IMPLEMENT |
| G2 | IMPLEMENT | implementation links exist and a current `implementation` receipt from `codex` binds authority, requirements, snapshot, evidence set, and cycle | LOCAL_VERIFY |
| G3 | LOCAL_VERIFY | exact typed current-cycle local evidence exists and a current `verification` receipt from `hotl-local-verifier` binds the same authority, requirements, snapshot, evidence set, and cycle | SEMANTIC_REVIEW |
| G4 | SEMANTIC_REVIEW | a current accepted review backed by a current `semantic_review` receipt, a current `final` receipt from `gpt-pro-codex-loop`, and complete active-requirement coverage | COMPLETE |

Only `evaluate` may advance a gate. `record` and `import-receipt` append validated evidence but leave state unchanged. A failed predicate emits no transition; it never creates an implicit repair path.

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
`gpt-pro-codex-loop`; `implementation` by `codex`; `verification` by
`hotl-local-verifier`; and `lineage` by `hotl-governance-lineage`.
Requirements and approval receipts bind authority and requirements only.
Implementation, verification, review, and final receipts bind authority,
requirements, snapshot, evidence set, and cycle. Material-change and stop
receipts also bind the evidence set and cycle, while their snapshot is optional
so they can terminate an execution before snapshot activation. Lineage uses
null lifecycle bindings because its immutable evidence object carries the
predecessor and supersedes bindings.

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

For every active requirement, require an active code node that implements it, an active test node that verifies it, and a command that executes the test and produces valid current evidence proving it. Require an accepted review that reviews the requirement and is bound to the current evidence set. Require the active code and test to be included in an active change.

For a bound outer protocol, run the GPT Pro controller's `final-verify`, export its final governance receipt, import that receipt into HOTL, and only then evaluate G4. G4 may commit only when all active requirements meet this predicate and no unresolved findings remain. After `COMPLETE`, run `verify-log` to revalidate the event chain, witness, projection, and artifact integrity.

## Evidence lifecycle

Store immutable events, receipts, and command outputs content-addressably at `.hotl/evidence/<sha256>`. An event is append-only and includes schema version, event ID, execution ID, sequence, type, closed payload, issuer, subject IDs, artifact references, result, input/output digests, previous event hash, and timestamp. Replay rejects every event after a terminal transition, including evidence-only events.

Canonical event bytes, `execution_id + sequence + previous_event_hash`, and the state witness (`event_count`, `head_event_hash`) make replay deterministic and detect truncation. Publish an atomic batch only after validating the complete candidate log; `verify-log` checks the chain, witness, projection, and artifact integrity.

When code, tests, or the active snapshot change, append `evidence_invalidated` and mark the related projection record `historically_valid`. Preserve it for audit but exclude it from G3/G4 current coverage. A new validation produces `valid_current` evidence in the current `cycle_id`; corrective edges and snapshot activation increment the cycle.

## Path rules

Artifact references are repository-relative canonical POSIX paths. Reject absolute paths, empty paths, `.` or `..` segments, NUL, repository escapes, symlink/reparse-point escapes, and non-canonical aliases. Bind every artifact reference to a SHA-256 digest. Treat historical observations as immutable even when the current mutable file later changes.

Canonical JSON uses UTF-8, sorted object keys, no BOM, finite integers only, and no duplicate or unknown fields. Timestamps, display labels, and diagnostics cannot affect transitions or replay.

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
