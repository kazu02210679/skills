---
name: orchestrate-gpt-pro-sol-advisor
description: Use when the user explicitly requests combined GPT Pro Codex Loop and Sol Advisor handling for one Codex task.
---

# GPT Pro + Sol Advisor composition

Use only for explicit combined mode. GPT Pro alone and Sol Advisor alone remain
standalone.

**REQUIRED SUB-SKILL:** Use `gpt-pro-codex-loop` as the outer protocol.

**ADVISORY DEPENDENCY:** Use the configured Sol Advisor role. Do not invoke
`sol-advisor:orchestration` in combined mode; its authority conflicts.

## Preflight

Combine only on an explicit request for both; clarify ambiguity.

Before GPT Pro `inspect-init` or `init`:

1. Call `get_setup_status`. Missing, old, or corrupt setup runs
   `sol-advisor:setup` alone, then stops before Pro.
2. Adapter installation or update requires a fresh Codex task.
3. Derive the current canonical workspace from trusted runtime context, then
   call `get_preferences`; success returns the upstream-validated active object.
   `preferences.client` must equal `codex`. Compare workspace identity by
   canonicalizing `preferences.workspace` and the current workspace. Validate
   `profileKey` exactly as `codex:<scope>:<raw preferences.workspace>` for scope
   `project` or `user`; never rebuild it from another runtime's canonical path.
   Require the saved advisor model and effort; preferences have no permission
   profile.
4. Require a well-formed role list and only observable `sol_advisor_advisor` in
   the combined role set. Any identity, interface, preference, or role failure
   stops before Pro. Do not silently downgrade or fabricate a consultation.

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
and the question. Exclude transcripts, unrelated material, and secrets.

After spawning, require explicit invocation success and trusted observations of
actual role, model, effort, sandbox, and permission profile before disposition.
Role, model, and effort must match the bound profile; sandbox must equal
`read-only`. Permission must be non-empty, recorded exactly, and treated as
opaque audit evidence—never compared, classified, or allowlisted. Invocation
failure or missing, malformed, ambiguous, or contrary evidence discards the
body and stops without retry, fallback, Pro continuation, or downgrade. A
promise is not attestation.

Record mode, question, role, calls, exact trusted observations, advice,
disposition, rationale, stop condition, and next step. Use `accept`, `reject`,
or `partially accept`.

## Return to GPT Pro

After an accepted change, Codex inspects the diff, reruns local verification,
and returns evidence to Pro. A Pro correction does not automatically trigger
Sol. Reconsult one fresh configured advisor only for materially new evidence or
a materially changed question, with an explicit stop condition.

Do not make Sol a mandatory pre-Pro or final gate. Reject nested
`sol-advisor:orchestration`, Sol-to-Sol review, duplicate consultation, advisor
re-entry, and open-ended loops. Completion requires controller `final-verify`.
