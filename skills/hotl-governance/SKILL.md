---
name: hotl-governance
description: Use when the user explicitly requests HOTL or governed execution, or when a trusted outer controller supplies a valid governance context, to enforce evidence-gated execution, typed provenance, deterministic replay, and human escalation without implicitly wrapping ordinary standalone workflows.
---

# HOTL Governance

Run the deterministic controller without calling an LLM or interpreting free text.
Treat the event log as the source of truth. Execute only commands listed by `status`.

## Activation boundary

Activate only for an explicit HOTL/governed-execution request or a trusted outer controller's valid, schema-bound governance context. Validate that context before use; malformed, incomplete, stale, or self-asserted context fails closed and does not activate the controller.

Do not infer governance from a filename, an ambient object, or an ordinary implementation request. Do not implicitly wrap a standalone workflow: `gpt-pro-codex-loop` used on its own remains standalone unless a valid governance context explicitly binds it to this controller.

This controller validates closed-schema receipts and deterministic predicates. It does not interpret review prose, free text, operator assertions, or an LLM's conclusion as evidence.

## Operating contract

Use the following sequence. Before every state-changing operation, run `status`; execute only a listed successor command. Record or import evidence first, then run `evaluate` to create a state transition. `record` and `import-receipt` never advance state.

1. **Inspect and initialize.** Inspect the repository and controller status; initialize the execution with identity, scope, authority snapshot, policy, and frozen-artifact locations. Use a predecessor only when it is terminal and supplies its lineage receipt.
2. **Freeze requirements.** Publish requirements, acceptance criteria, scope digest, policy/authority snapshot, required approval, and required GPT Pro packet attestation. Evaluate G1 before implementation.
3. **Record implementation.** Produce an implementation receipt with a change manifest, requirement-to-code links, worker report, base snapshot identity, and bound input/output digests. Evaluate G2.
4. **Collect local evidence.** Run the exact verification commands, preserve their exit status, output artifacts, SHA-256 hashes, test-to-requirement links, and repository snapshot digest. Evaluate G3 only against current-cycle evidence.
5. **Import semantic receipt.** Import the closed-schema GPT Pro review receipt; in combined mode also import the required Sol advice/disposition receipt, or the policy-allowed no-consultation event. Do not compare free-text findings: use stable `finding_id` and `root_cause_id` values.
6. **Evaluate gates G1-G3.** Let `evaluate` append the only state-changing `transition_committed` event when the complete gate predicate passes. Missing, mismatched, stale, malformed, or replayed evidence cannot advance the execution.
7. **Final verify and evaluate G4.** When an outer `gpt-pro-codex-loop` protocol is bound, first run its `final-verify`, then export its final governance receipt, import that receipt into HOTL, and evaluate G4. After `COMPLETE`, verify the log, witness, projection, and artifact integrity.
8. **Start a successor when required.** A material frozen-artifact change, an escalation, or `RECOVERY_REQUIRED` terminates the same execution. Preserve evidence and initialize a successor with the predecessor execution ID, lineage receipt digest, and explicit supersession relation.

## Authority and hard stops

Never use generic `record` for privileged receipts. Human approval, GPT Pro packets, Sol advice, completion, and stop receipts must arrive through their issuer-specific import or approval command and pass the closed schema. A local worker assertion such as `record --actor human` is not approval.

Treat `RECOVERY_REQUIRED`, `ESCALATED`, `STOPPED`, and `COMPLETE` as terminal for the same execution. On transaction ambiguity, log/head mismatch, malformed privileged receipt, authority conflict, or an unapproved material change, stop state changes and preserve the artifacts. There is no repair command: investigation is read-only, and authorized work continues as a successor execution.

## Reference

Read [the controller contract](references/controller-contract.md) before operating the controller. It defines the transition table, gates, receipt schema, provenance triples, completion predicate, evidence lifecycle, path validation, threat model, and recovery boundary.
