---
name: hotl-governance
description: Use when the user explicitly requests HOTL or governed execution, or when a trusted outer controller supplies a valid governance context, to enforce evidence-gated execution, typed provenance, deterministic replay, and human escalation without implicitly wrapping ordinary standalone workflows.
---

# HOTL Governance

Run the deterministic controller without calling an LLM or interpreting free text.
Treat the event log as the source of truth. Execute only commands listed by `status`.

## Activation boundary

Activate only for an explicit HOTL request or a trusted outer controller's valid context. Malformed, stale, or self-asserted context fails closed.

Do not infer governance from files or ordinary requests. Standalone `gpt-pro-codex-loop` remains standalone unless a valid context binds it here.

This controller validates closed-schema receipts and deterministic predicates. It does not interpret review prose, free text, operator assertions, or an LLM's conclusion as evidence.

GPT Pro receipt imports require the authoritative source's model-attestation schema v4. The v4 GPT binding keeps model identity, reasoning strength, and plan as separate fields and accepts only `model_label=GPT-5.6 Sol`, `reasoning_label=Pro`, and plan `Pro`, `Business`, or `Enterprise`. Reject `GPT-5.6 Pro`, non-Pro reasoning labels, missing or approximate values, and unsupported pre-v4 bound source state. A valid import remains audit-only and cannot open G1 without an independent provider.

## Operating contract

Use the following sequence. Before every state-changing operation, run `status`; execute only a listed successor command. Record or import evidence first, then run `evaluate` to create a state transition. `record` and `import-receipt` never advance state.

1. **Inspect and initialize.** Inspect the repository and controller status; initialization derives the frozen Git base identity itself, never from policy input. Use a predecessor only when it is terminal and supplies its lineage receipt.
2. **Freeze requirements.** GPT export proves integrity only. `import-receipt` may retain exact validated bytes as audit evidence, but it cannot open G1. Files, environment values, policy digests, CLI arguments, local assertions, and exported or self-hashed receipts are not substitutes.
3. **Record implementation.** Use `record-implementation --manifest --report`; it re-reads declared artifacts, preserves exact manifest/report bytes, and creates the controller-owned implementation receipt for G2.
4. **Collect local evidence.** Use `run-verification` only with a closed `python -m unittest` spec: exact argv, `TEST-*`-to-path mapping, canonical artifacts, and one test per path. It runs shell-free, re-hashes before/after, rejects bad output, and records audit data. It never opens G3.
5. **Keep receipts advisory.** GPT and Task 7 Sol receipts are audit artifacts. Sol is not a gate; neither family satisfies HOTL without an independent provider.
6. **Evaluate without inventing authority.** `evaluate` is the only transition command, but this production build unconditionally rejects G1, G3, G4, STOP, and MATERIAL_CHANGE. G2 remains a deterministic integrity predicate and cannot make a newly initialized run bypass closed G1.
7. **Retain semantic audit data.** Outer `final-verify` output may be imported for exact-byte and replay diagnostics, but it is not HOTL authority. Corrective review projection resolves only the exact stable `(finding_id, root_cause_id)` pair; this pure projection behavior does not make production G4 reachable.
8. **Start a successor only from an eligible predecessor.** Preserve terminal legacy evidence and `RECOVERY_REQUIRED` bytes. Successor creation derives its own frozen Git base plus predecessor ID, lineage receipt digest, and supersession relation; it does not bypass closed G1.

## Authority and hard stops

Never use generic `record` or an audit import as privileged authority. The production package contains no grant-capable provider, registry, discovery hook, boolean flag, environment switch, policy selector, serialized selector, or CLI selector. G1, G3, G4, STOP, and MATERIAL_CHANGE remain closed under every input. Sol is audit-only. The positive evaluator exists only under `evals/` and is unreachable from production CLI, policy, imports, exports, runtime discovery, and serialized state.

An absent execution is `UNINITIALIZED` and offers only `init`; a partial execution is `RECOVERY_REQUIRED`. Treat `RECOVERY_REQUIRED`, `ESCALATED`, `STOPPED`, and `COMPLETE` as terminal. On ambiguity, preserve artifacts and continue only as a successor; there is no repair command.

## Reference

Read [the controller contract](references/controller-contract.md) before operating the controller. It defines the transition table, gates, receipt schema, provenance triples, completion predicate, evidence lifecycle, path validation, threat model, and recovery boundary.
