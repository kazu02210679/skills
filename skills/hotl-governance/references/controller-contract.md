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

## Gate table

| Gate | From | Required predicate | To |
| --- | --- | --- | --- |
| G1 | REQUIREMENTS | requirements are frozen, approved, and bound to scope/policy/authority and GPT Pro packet identity | IMPLEMENT |
| G2 | IMPLEMENT | implementation receipt binds the change manifest, links, worker report, base snapshot, and input/output digests | LOCAL_VERIFY |
| G3 | LOCAL_VERIFY | current-cycle local evidence binds exact commands, exit status, hashes, test links, and snapshot digest | SEMANTIC_REVIEW |
| G4 | SEMANTIC_REVIEW | accepted semantic receipt and all active requirements satisfy the completion predicate | COMPLETE |

Only `evaluate` may advance a gate. `record` and `import-receipt` append validated evidence but leave state unchanged. A failed predicate emits no transition; it never creates an implicit repair path.

## Receipt contract

Each privileged receipt is issuer-specific and closed-schema. It includes at least:

- `receipt_schema_version`, `receipt_id`, `issuer_skill`, and `issuer_version`;
- `execution_id`, `transaction_id` or `invocation_id`, nonce, and `issued_at_unix`;
- `input_digest`, `output_digest`, and authority snapshot digest; and
- the issuer's required subject, attestation, and artifact bindings.

Human approvals, GPT Pro requirement/review/final receipts, Sol advice, completion, and stop receipts cannot be produced through generic `record`. In agentic mode, accept only a bound user-approval receipt or worker-inaccessible host/tool provenance; `trusted_local_operator` is limited to an explicit policy-bound offline/manual mode. Reject self-declared human approval.

Semantic review findings use stable `finding_id` and `root_cause_id`; the controller never compares finding prose. Receipts must match the execution, current snapshot, current evidence-set digest, issuer schema, and replay protections. Malformed, mismatched, stale, or replayed receipts fail closed and do not consume a valid review round.

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
| code or test | included_in | change |
| failure | violates | requirement |
| change | fixes | failure |
| requirement, review, change, or evidence | derived_from or supersedes | same typed lineage target |

Node IDs are execution-local and typed (`REQ-`, `CODE-`, `TEST-`, `CMD-`, `EVID-`, `REV-`, `CHG-`, `FAIL-`, and `POL-`). Unknown types, invalid IDs, or unsupported edges are rejected.

## Completion predicate

For every active requirement, require an active code node that implements it, an active test node that verifies it, and a command that executes the test and produces valid current evidence proving it. Require an accepted review that reviews the requirement and is bound to the current evidence set. Require the active code and test to be included in an active change.

For a bound outer protocol, also require its imported final governance receipt and successful `final-verify`. G4 may commit only when all active requirements meet this predicate and no unresolved findings remain.

## Evidence lifecycle

Store immutable events, receipts, and command outputs content-addressably at `.hotl/evidence/<sha256>`. An event is append-only and includes schema version, event ID, execution ID, sequence, type, closed payload, issuer, subject IDs, artifact references, result, input/output digests, previous event hash, and timestamp.

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

v1 has no repair command. An authorized operator may establish a known-good source outside the controller and start a new successor that records lineage to the terminal predecessor. The successor, not the compromised execution, receives any further state transitions.
