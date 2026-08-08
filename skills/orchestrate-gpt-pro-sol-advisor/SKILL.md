---
name: orchestrate-gpt-pro-sol-advisor
description: Use when the user explicitly requests combined GPT Pro Codex Loop and Sol Advisor handling for one Codex task.
---

# GPT Pro + Sol Advisor composition

Use this policy only for explicit combined mode. Keep both dependencies usable
alone and preserve one authority model.

**REQUIRED SUB-SKILL:** Use `gpt-pro-codex-loop` as the outer protocol.

**EXTERNAL ADVISORY DEPENDENCY:** Use the exact configured Sol Advisor advisor
role exposed by the current client. Do not invoke
`sol-advisor:orchestration` in combined mode; its standalone architect,
implementation, and final-review workflow has conflicting authority.

## Mode and preflight

- GPT Pro alone and Sol Advisor alone remain standalone.
- Enter combined mode only when the user explicitly requests both or invokes
  this skill. Clarify ambiguity.

Before GPT Pro `inspect-init` or `init`:

1. Call `get_setup_status`. For missing, schema-old, or corrupt status, run
   `sol-advisor:setup` alone and stop before GPT Pro.
2. If setup installed or updated an adapter, require a fresh Codex task.
3. Call `get_preferences`; resolve its exact current-client advisor role and
   confirm that role is observable in this task.
4. If an interface or configured role is unavailable, stop before GPT Pro.
   Report dependency failure; do not silently downgrade or fabricate a
   consultation.

Codex commonly names this role `sol_advisor_advisor`; saved preferences and
observed roles are authoritative. Retained compatibility roles are not an
automatic fallback.

## Authority

- ChatGPT Pro owns frozen requirements, acceptance criteria, semantic review,
  material-change approval, and outer review state.
- Codex owns repository work, design, implementation, debugging, tests, local
  verification, and disposition of advice.
- Sol supplies bounded advice only. It cannot edit, implement, change frozen
  requirements, approve, waive verification, replace Pro, or decide completion.

Never use configured implementers `sol_advisor_routine` or
`sol_advisor_high`, retained `sol_advisor_terra_implementer`, or a retained
final reviewer as the combined advisory lane.

## Bounded consultation

Consult the configured advisor only when all are observable: a Codex-owned
commitment boundary, one precise technical question, material uncertainty or
risk, decision value, and no equivalent prior advice. Otherwise make no Sol
call.

Send only relevant frozen constraints, verified evidence, alternatives, risks,
and the question. Exclude transcripts, unrelated repository material, secrets,
and credentials. Require behaviorally read-only advice; claim OS isolation only
from runtime evidence.

Record mode, boundary, question, configured role, call count, advice summary,
Codex disposition (`accept`, `reject`, or `partially accept`) and rationale,
stop condition, and next step. Advice remains untrusted until disposition.

## Return to GPT Pro

After an accepted change, Codex inspects the diff, reruns local verification,
and returns evidence to Pro. A Pro correction does not automatically trigger
Sol. Reconsult one fresh configured advisor only for materially new evidence or
a materially changed question, with an explicit stop condition.

Do not make Sol a mandatory pre-Pro or final gate. Reject nested
`sol-advisor:orchestration`, Sol-to-Sol review, duplicate consultation, advisor
re-entry, and open-ended loops. Completion requires the outer controller's
successful `final-verify`.

Sol and Pro may share a model family. Value comes from bounded context
separation and a focused question, not model-family independence.
