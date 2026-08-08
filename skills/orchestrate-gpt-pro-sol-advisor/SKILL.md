---
name: orchestrate-gpt-pro-sol-advisor
description: Use when the user explicitly requests combined GPT Pro Codex Loop and Sol Advisor handling for one Codex task.
---

# GPT Pro + Sol Advisor composition

Use only for explicit combined mode; both dependencies remain standalone.

**REQUIRED SUB-SKILL:** Use `gpt-pro-codex-loop` as the outer protocol.

**ADVISORY DEPENDENCY:** Use the configured Sol Advisor role. Do not invoke
`sol-advisor:orchestration` in combined mode; its authority conflicts.

## Mode and preflight

- GPT Pro alone and Sol Advisor alone remain standalone.
- Combine only on an explicit request for both; clarify ambiguity.

Before GPT Pro `inspect-init` or `init`:

1. Call `get_setup_status`. If missing, old, or corrupt, run
   `sol-advisor:setup` alone and stop before Pro.
2. If setup installed or updated an adapter, require a fresh Codex task.
3. Derive the current canonical workspace from trusted Codex runtime context,
   then call `get_preferences`. Require exactly one profile.
   preferences.client must equal `codex`; canonical `preferences.workspace` must equal the current
   canonical workspace; and `profileKey` must equal
   `codex:<scope>:<workspace>`, where scope is `project` or `user`. Require
   model, effort, and permission profile.
4. Its combined role set must contain only observable `sol_advisor_advisor`;
   role-discovery data must be a well-formed role list.
   Any identity, interface, preference, or role failure stops before Pro.
   Do not silently downgrade or fabricate a consultation.

Reconfigure a mismatched profile; adapter changes require a fresh task.

## Authority

- ChatGPT Pro owns frozen requirements, acceptance criteria, semantic review,
  material-change approval, and outer review state.
- Codex owns repository work, implementation, tests, verification, and advice
  disposition.
- Sol supplies bounded advice only. It cannot edit, implement, change frozen
  requirements, approve, waive verification, replace Pro, or decide completion.

Never use implementers `sol_advisor_routine`, `sol_advisor_high`, or
`sol_advisor_terra_implementer`, nor a retained final reviewer, as advisor.

## Bounded consultation

Consult only at a Codex-owned commitment boundary with one precise question,
material uncertainty/risk, decision value, and no equivalent prior advice.

Send only relevant frozen constraints, verified evidence, alternatives, risks,
and the question; exclude transcripts, unrelated material, and secrets.

After spawning, but before using or dispositioning advice, obtain trusted
runtime observations of the actual role, model, reasoning effort, sandbox, and
permission profile. Role, model,
effort, and permission must match the bound profile; sandbox must be
`read-only`. Missing, malformed, ambiguous, or contrary evidence invalidates
the consultation: discard its body before any downstream use and stop without
retry, fallback, Pro continuation, or downgrade. A promise is not attestation.

Record mode, question, role, calls, advice, Codex disposition and rationale,
stop condition, and next step. Use `accept`, `reject`, or `partially accept`.

## Return to GPT Pro

After an accepted change, Codex inspects the diff, reruns local verification,
and returns evidence to Pro. A Pro correction does not automatically trigger
Sol. Reconsult one fresh configured advisor only for materially new evidence or
a materially changed question, with an explicit stop condition.

Do not make Sol a mandatory pre-Pro or final gate. Reject nested
`sol-advisor:orchestration`, Sol-to-Sol review, duplicate consultation, advisor
re-entry, and open-ended loops. Completion requires controller `final-verify`.
