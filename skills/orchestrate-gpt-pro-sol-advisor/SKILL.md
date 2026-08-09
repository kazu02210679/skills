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

1. Call `get_setup_status`. Invalid setup runs `sol-advisor:setup` alone
   and stops before Pro.
2. Adapter changes require a fresh Codex task.
3. From trusted context, derive the canonical workspace and call
   `get_preferences`. `preferences.client` must equal `codex`. Compare
   identity by canonicalizing `preferences.workspace` and the current
   workspace. Require `profileKey` =
   `codex:<scope>:<raw preferences.workspace>` for `project` or `user`;
   never rebuild it from another runtime's canonical path. Require saved model
   and effort; preferences have no permission profile.
4. Require a valid role list containing only observable
   `sol_advisor_advisor`. Any binding/interface failure stops before Pro.
   Do not silently downgrade or fabricate a consultation.

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

Consult at a Codex-owned commitment boundary only for one precise, materially
uncertain/risky, valuable question without equivalent prior advice. Send only
relevant frozen constraints, evidence, alternatives, risks, and the question;
exclude transcripts, unrelated material, and secrets.

After spawn, public details must identify `sol_advisor_advisor`. For
omitted non-role fields only, resolve and run the installed
`scripts/inspect-agent-runtime.sh` once for that thread. Require one rollout,
complete allowlisted output, and matching overlaps; fill omissions only.
Missing public role, inspector failure/ambiguity, bad output, wrong thread, or
conflict fails closed.

Record each field as `public-native-details` or `local-runtime-inspector`.
Only these paths are trusted; self-claims, Booleans, manifests, and requested
settings are not evidence. Role/model/effort must match the profile; sandbox
must be `read-only`. Record non-empty permission exactly as opaque audit data,
never classify it. On failure, discard advice; do not retry, fallback,
continue Pro, or silently downgrade.

Record mode, question, role, calls, observations/sources, inspector
thread/status, advice, disposition/rationale, stop, and next step. Use
`accept`, `reject`, or `partially accept`.

## Return to GPT Pro

After accepted changes, Codex inspects the diff, re-verifies, and returns
evidence to Pro. Pro corrections do not trigger Sol automatically. Reconsult
one fresh configured advisor only for materially new evidence or a materially
changed question, with an explicit stop condition.

Do not make Sol a mandatory pre-Pro or final gate. Reject nested
`sol-advisor:orchestration`, Sol-to-Sol review, duplicate consultation, advisor
re-entry, and open-ended loops. Completion requires controller `final-verify`.
