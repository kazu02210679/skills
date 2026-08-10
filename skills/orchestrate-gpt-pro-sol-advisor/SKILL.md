---
name: orchestrate-gpt-pro-sol-advisor
description: Use when the user explicitly requests combined GPT Pro Codex Loop and Sol Advisor handling for one Codex task.
---

# GPT Pro + Sol Advisor composition

Use this Skill only for explicit combined mode. It composes the outer
`gpt-pro-codex-loop` protocol with a Codex-owned Luna-first implementation
lane; it does not activate either dependency by itself.

**REQUIRED SUB-SKILL:** Use `gpt-pro-codex-loop` as the outer protocol.

**ADVISORY DEPENDENCY:** Use only the configured `sol_advisor_advisor` role for
one bounded read-only consultation. Do not invoke `sol-advisor:orchestration` in combined mode;
its authority conflicts with this composition contract.

Read [references/luna-implementation-lane.md](references/luna-implementation-lane.md)
before creating an implementation task and
[references/verification-economy.md](references/verification-economy.md) before
adding tests or local evidence.

## Mode and authority

- GPT Pro owns frozen requirements, acceptance criteria, semantic review, and
  material-change approval.
- Codex Primary owns the repository, architecture, task packets, worker
  routing, implementation, tests, verification, and final disposition.
- Sol supplies bounded advice only. It cannot edit, implement, approve, waive
  verification, replace Pro, or decide completion.
- GPT Pro-only stays standalone; Sol-only stays standalone. Do not infer
  combined mode from a mention or installation state.

## Luna-first routing

The combined policy is `implementation_policy: luna_first`:

- Normal bounded work starts at `gpt-5.6-luna` with `thinking: max`.
- Use at most two coarse-grained independent Luna tasks. Serialize shared or
  dependent files; never create one task per file or test.
- Escalate difficult scope, a trusted repeated root cause, a stuck task,
  concurrency, security, migration, shared state, cross-workstream,
  performance, or broad-blast-radius work to
  `sol_advisor_terra_implementer` at `gpt-5.6-terra` / High.
- If trusted worker routing or execution evidence is unavailable, stop with
  `dependency-unavailable`; do not silently downgrade.
- Only a trusted Terra execution result that remains blocked on one high-impact
  decision may lead to one Sol consultation. Sol never edits.

Worker evidence comes from a native/app adapter outside the routing scenario;
a scenario field claiming `source: native-*` is not evidence. Luna requires
real `project_id`, `thread_id`, and `host_id`, and a `clientThreadId` cannot
replace them. Returned Luna model/thinking metadata is optional but must match
when present. Terra additionally requires exact role-template provenance and
matching shipped-template digest (the role template must be exact). Routing attestation and execution evidence
are separate; the details are in the lane reference.

```text
Luna / Max -> primary diff + focused verification -> one same-task correction
  -> Terra / High when escalation evidence passes
  -> Sol read-only advice only for a remaining high-impact decision
  -> primary verification -> GPT Pro -> final-verify
```

## Preflight and Sol gate

Before `inspect-init` or `init`:

1. Check `get_setup_status`; invalid setup runs setup alone and stops before Pro.
2. Adapter changes require a fresh task.
3. Load the trusted Codex profile. `preferences.client` must equal `codex`.
   Canonicalizing `preferences.workspace` and the current workspace is required;
   `profileKey` to preserve the raw upstream value:
  `codex:<scope>:<raw preferences.workspace>`. Never rebuild it from another runtime's canonical path.
4. Require the configured advisor `sol_advisor_advisor` in the observable role list;
   do not use Terra or a retained reviewer as the advisor.

Consult Sol only at a Codex-owned commitment boundary with one precise,
materially risky question, useful decision value, and no equivalent prior advice.
A follow-up requires materially new evidence and an explicit stop condition.
Send only frozen constraints,
verified local evidence, alternatives, risks, and the precise question. After
trusted runtime attestation, record `accept`, `reject`, or `partially accept`.
Do not make Sol a mandatory pre-Pro or final gate. Reject nested orchestration,
Sol-to-Sol review, advisor re-entry, duplicate consultation, and open-ended
loops. Do not fabricate a consultation or accept fabricated advice.

## Test economy and return

The local-evidence schema is closed: each `test_commands` item has only
`command`, `outcome`, and `output_summary`. Keep metrics, test delta, and the
verification-input fingerprint inside `output_summary`; do not add sibling
fields. New witnesses use one existing `primary_anchor`, optional existing
`also_proves`, and a bounded case count. The policy invokes
`scripts/verification_fingerprint.py` internally for the current tree; a
caller cannot supply, copy, or override the digest. Use the helper CLI directly
when recording a new evidence line. See the verification-economy reference for
the L0-L3 ladder and compact format.

The helper parses `git status --porcelain=v1 -z` records, never human-readable
quoted status lines. It preserves spaces and non-ASCII names and records both
sides of a rename. Its environment identity also binds the command executable,
resolved executable path, and an allowlisted toolchain version for common
Python, npm, pnpm, Cargo, Go, and .NET commands.

All tracked Gitlinks are added to the input set even when `git status` is clean.
They are bound to both the superproject pointer and the clean submodule `HEAD`,
after verifying that the submodule's independent Git top-level is the expected
path. An unavailable, deinitialized, or dirty submodule makes the fingerprint
unavailable, so the reuse policy runs verification instead of skipping it.

After implementation, the primary inspects the actual worktree, complete diff,
owned scope, and evidence; worker reports are claims. Re-verify at the lowest
sufficient level and return bounded evidence to GPT Pro. Workers never commit,
push, create PRs, deploy, change permissions, or perform destructive actions.
Completion requires the outer controller's `final-verify`.
