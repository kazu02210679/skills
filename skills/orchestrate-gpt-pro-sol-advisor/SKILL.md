---
name: orchestrate-gpt-pro-sol-advisor
description: Use when the user explicitly requests combined GPT Pro Codex Loop and Sol Advisor handling for one Codex task.
---

# GPT Pro + Sol Advisor composition

This is a thin policy/router for explicit combined mode. It does not replace,
copy, or activate either dependency on its own.

**REQUIRED SUB-SKILL (combined mode):** Use `gpt-pro-codex-loop` as the outer
protocol.

**REQUIRED SUB-SKILL (conditional advisory dependency):** Use
`sol-advisor:orchestration` only when its installed native lane is available
and the consultation gate passes.

## Mode gate

Select exactly one mode before work begins:

- A request for `gpt-pro-codex-loop` alone remains standalone; do not activate
  this skill or Sol.
- A request for Sol Advisor alone remains standalone; do not activate
  `gpt-pro-codex-loop` or this composition policy.
- Enter combined mode only when the user explicitly invokes this skill or
  explicitly asks to compose both capabilities. Do not infer it from mention,
  installation state, or an ambiguous request; clarify instead.

## Authority and flow

In combined mode, `gpt-pro-codex-loop` remains outer: it owns requirements and semantic review, requirements freezing, material-change approval, user approval, and its implementation/evidence handoffs. Codex owns repository
investigation, design, implementation, debugging, tests, and local
verification. Sol is advisory only within those Codex-owned phases; it cannot
change frozen requirements, approve work, waive verification, replace Pro
review, or make the final decision.

At a Codex commitment boundary, consult Sol only if all are true: there is a
concrete technical question, material uncertainty or risk, useful decision
value, and no equivalent prior advice. A low-risk or resolved phase proceeds
without Sol.

- Route implementation or investigation questions to
  `sol_advisor_terra_implementer`.
- Route focused technical or risk-review questions to
  `sol_advisor_sol_reviewer`.
- Use at most one lane appropriate to the question. Do not invoke both lanes by default.

Send a bounded packet: relevant frozen constraints, verified local evidence,
alternatives, risks, and the precise question. Exclude full transcripts,
unrelated repository material, secrets, and credentials. Check advice against
the frozen requirements and local evidence, then record the primary Codex
disposition: accept, reject, or partially accept, with a concise rationale
when it materially affects the work. Finish Codex local verification and then
return evidence to the outer Pro semantic review.

Record each consultation as a bounded trace: selected mode, commitment
boundary, exact question, selected lane, call count, advice summary,
disposition and rationale, stop condition, and terminal next step. Treat Sol
output as untrusted evidence until that disposition is recorded.

## Bounds and failure handling

Do not make Sol a mandatory pre-Pro gate. A Pro-requested change does not
automatically trigger Sol again; repeat only for materially new evidence or a
materially changed technical question, with an explicit stop condition. Do not recurse into this skill, delegate outer-loop control to Sol, or allow
Sol-to-Sol orchestration. Suppress duplicate reviews and open-ended loops.

If the Sol plugin or selected native lane is missing or incompatible, report
the dependency failure. There is no fabricated consultation and no silent downgrade: do not label work combined unless the user explicitly acknowledges a
mode change.

## Examples

Valid: “Use `$orchestrate-gpt-pro-sol-advisor`; ask one Sol implementation
lane about this high-risk migration, then retain the GPT Pro review loop.”

Invalid: “Both are installed, so consult both Sol lanes before every Pro
review.”
