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

1. **Inspect and initialize.** Inspect the repository and controller status; initialization derives the frozen Git base identity itself, never from policy input. Use a predecessor only when it is terminal and supplies its lineage receipt.
2. **Freeze requirements.** Publish frozen requirements and the exact accepted GPT Pro requirements receipt. In agentic mode that receipt is the G1 approval boundary; a repository-local host assertion is never authority.
3. **Record implementation.** Use `record-implementation --manifest --report`; it re-reads declared artifacts, preserves exact manifest/report bytes, and creates the controller-owned implementation receipt for G2.
4. **Collect local evidence.** Use `run-verification --argv` only with one closed policy verification spec: exact argv, explicit `TEST-*` IDs, and canonical code/test paths. It executes without a shell, re-hashes those paths before and after execution, rejects nonzero status, and records exact outputs for G3.
5. **Import semantic receipts.** Import the closed GPT Pro review and one exact Task 7 Sol consultation/disposition or closed no-consultation receipt with `import-sol-receipt` before G4. Use stable `finding_id` and `root_cause_id`, never prose.
6. **Evaluate gates G1-G3.** Let `evaluate` append the only state-changing `transition_committed` event when the complete gate predicate passes. Missing, mismatched, stale, malformed, or replayed evidence cannot advance the execution.
7. **Final verify and evaluate G4.** When an outer `gpt-pro-codex-loop` protocol is bound, first run its `final-verify`, then export its final governance receipt, import that receipt into HOTL, and evaluate G4. After `COMPLETE`, verify the log, witness, projection, and artifact integrity.
8. **Start a successor when required.** A material frozen-artifact change, an escalation, or `RECOVERY_REQUIRED` terminates the same execution. Preserve evidence and initialize a successor with the predecessor execution ID, lineage receipt digest, and explicit supersession relation.

## Authority and hard stops

Never use generic `record` or `import-receipt` for privileged implementation or verification receipts. G1 consumes the accepted GPT requirements receipt; `approve` fails closed without a non-worker-writable provider. Sol audit uses only `import-sol-receipt`; a local worker assertion is not approval.

An absent execution is `UNINITIALIZED` and offers only `init`; a partial execution is `RECOVERY_REQUIRED`. Treat `RECOVERY_REQUIRED`, `ESCALATED`, `STOPPED`, and `COMPLETE` as terminal. On ambiguity, preserve artifacts and continue only as a successor; there is no repair command.

## Reference

Read [the controller contract](references/controller-contract.md) before operating the controller. It defines the transition table, gates, receipt schema, provenance triples, completion predicate, evidence lifecycle, path validation, threat model, and recovery boundary.
