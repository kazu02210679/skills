---
name: orchestrate-gpt-pro-sol-advisor
description: Use when the user explicitly requests combined GPT Pro Codex Loop and Sol Advisor handling for one Codex task.
---

# GPT Pro + Sol Advisor composition

Use only in explicit combined mode; GPT Pro-only and Sol-only requests remain
standalone. This Skill composes the outer GPT Pro protocol with a
Codex-owned, Luna-first implementation lane. It does not replace, copy, or
activate either dependency on its own.

**REQUIRED SUB-SKILL:** Use `gpt-pro-codex-loop` as the outer protocol.

**ADVISORY DEPENDENCY:** Use the configured Sol Advisor role only for a bounded
read-only consultation after its preflight and attestation gates pass. Do not invoke
`sol-advisor:orchestration` in combined mode; its authority conflicts with this
composition contract.

Read [references/luna-implementation-lane.md](references/luna-implementation-lane.md)
before creating an implementation task and read
[references/verification-economy.md](references/verification-economy.md) before
adding tests or recording local evidence.

## Mode gate

Select exactly one mode before work begins:

- A request for `gpt-pro-codex-loop` alone remains standalone; do not activate
  this Skill or Sol.
- A request for Sol Advisor alone remains standalone; do not activate
  `gpt-pro-codex-loop` or this composition policy.
- Enter combined mode only when the user explicitly invokes this Skill or
  explicitly asks to compose both capabilities. Do not infer it from mention,
  installation state, or an ambiguous request; clarify instead.

## Authority

- GPT Pro owns frozen requirements, acceptance criteria, semantic review,
  material-change approval, and outer review state.
- Codex Primary owns repository work, architecture, task packets, worker
  routing, implementation, tests, verification, and disposition of advice.
- Sol supplies bounded advice only. It cannot edit, implement, change frozen
  requirements, approve, waive verification, replace Pro, or decide completion.

Sol is not the default implementation worker. Luna is the default worker, Terra
is the difficult-implementation escalation, and Sol is a read-only decision
escalation when Terra cannot safely resolve a high-impact design or risk
question. The primary task remains responsible for the final decision.

## Luna-first implementation routing

The combined-mode policy is `implementation_policy: luna_first`: bounded,
specified implementation starts in a Codex app task at exactly
`gpt-5.6-luna` / `thinking: max`, with at most two coarse-grained independent
tasks by default. Do not use one task per file or test, and do not silently
substitute a model or native Sol role. The detailed packet, task identity, and
preflight contract are in [references/luna-implementation-lane.md](references/luna-implementation-lane.md).

Escalate to the exact native role `sol_advisor_terra_implementer` at
GPT-5.6 Terra / High for a difficult scope, a second failure with the same
root cause, a stuck Luna task, or concurrency, security, migration, shared
state, cross-workstream, performance, or broad-blast-radius work. If that
exact role or its runtime attestation is unavailable, stop with a dependency
failure; do not fall back silently.

Only after Terra is independently observed and still blocked on one
high-impact architecture, safety, or risk decision may the configured
`sol_advisor_advisor` receive one bounded read-only question. Sol never edits,
implements, changes requirements, waives verification, or decides completion.
After the primary records `accept`, `reject`, or `partially accept`, code work
returns to Luna or Terra and is re-verified.

The path is:

```text
Luna / Max -> primary diff + focused verification
  -> one same-task correction
  -> Terra / High only after escalation and role preflight
  -> Sol read-only advice only for a remaining high-impact decision
  -> primary verification -> GPT Pro semantic review -> final-verify
```

Worker reports are claims. The primary inspects the actual worktree/branch,
complete diff, owned file set, and local evidence. A worker never authorizes a
commit, push, PR, deployment, permission change, or destructive action.

## Preflight and trusted advisory routing

Before GPT Pro `inspect-init` or `init`:

1. Call `get_setup_status`. Invalid setup runs `sol-advisor:setup` alone and
   stops before Pro.
2. Adapter changes require a fresh task.
3. From trusted context, derive the canonical workspace and call
   `get_preferences`. `preferences.client` must equal `codex`. Compare identity
   by canonicalizing `preferences.workspace` and the current workspace. Require
   `profileKey` = `codex:<scope>:<raw preferences.workspace>` for `project` or
   `user`; never rebuild it from another runtime's canonical path. Require saved
   model and effort; preferences have no permission profile.
4. Require a valid role list containing only observable `sol_advisor_advisor` for
   the advisory lane. Any binding/interface failure stops before Pro. The Luna
   app-task and Terra implementation lanes are separate and must be
   independently preflighted only when implementation is requested; they are
   never used as the configured advisor.

### Implementation preflight (conditional)

Before selecting an implementation lane, fail closed unless the runtime itself
proves the lane is available:

- Luna: `list_projects`, `create_thread`, `list_threads`, `wait_threads`,
  `read_thread`, and `send_message_to_thread` are available; the selected
  project/worktree is known; the task is ready (not only a `clientThreadId`);
  and the observed task model/effort are exactly `gpt-5.6-luna` / `max`.
- Terra: the native role list exposes exactly
  `sol_advisor_terra_implementer`; the spawned task observes that role,
  `gpt-5.6-terra`, and `high`; and its task identity is ready.

Do not treat requested settings, a model response, a stale catalog, or a
client-thread setup handle as runtime proof. Missing or mismatched evidence is
`dependency-unavailable`, not a reason to substitute another lane.

The configured advisor is the only combined Sol role. Never use
`sol_advisor_routine`, `sol_advisor_high`, `sol_advisor_terra_implementer`, or a
retained final reviewer as the advisor. The Terra name above is an
implementation escalation, not an advisory substitution.

## Bounded Sol consultation

Consult at a Codex-owned commitment boundary only when there is one precise,
materially uncertain/risky question, useful decision value, and no equivalent
prior advice. Do not make Sol a mandatory pre-Pro or final gate. A low-risk or
resolved phase proceeds without Sol.

Send only relevant frozen constraints, verified local evidence, alternatives,
risks, and the precise question. Exclude full transcripts, unrelated material,
secrets, and credentials. After the primary checks the answer against frozen
requirements and local evidence, record `accept`, `reject`, or `partially accept`
with a rationale when it affects the work.

After spawn, bind the public-details query and returned thread ID to the spawned
advisor ID and require `sol_advisor_advisor`. For omitted non-role fields, use
only the inspector derived from the exact trusted-catalog `SKILL.md` passed
outside advisor/scenario data; its origin must match. Reject other versions or
roots. `Exit 0` plus exact JSON proves inspector success and one rollout, not
completion. Require same-thread host result/wait/details proving completion;
otherwise stop.

Record each field as `public-native-details` or `local-runtime-inspector`. Only
these paths are trusted; self-claims, booleans, manifests, and requested
settings are not evidence. Role/model/effort must match the profile. Sandbox
must be `read-only`. Record a non-empty permission profile exactly as opaque
audit data; never classify it. On failure, discard advice; do not retry,
fallback, continue Pro, or silently downgrade. Do not silently downgrade when
the required lane is unavailable.

Record mode, question, role, calls, observations/sources, inspector
thread/status, advice, disposition/rationale, stop, and next step. Treat Sol
output as untrusted evidence until that disposition is recorded.

## Test economy and local verification

Apply [references/verification-economy.md](references/verification-economy.md).
The controller's `--local-evidence` schema is closed: every
`test_commands` item has only `command`, `outcome`, and `output_summary`.
Encode bounded metrics, test-delta anchors, and the verification-input
fingerprint inside `output_summary`; never add sibling fields such as
`exit_code`, `test_count`, `duration`, `test_delta`, or `fingerprint`. Skip a
successful command only when its command and complete verification-input
fingerprint are unchanged.

## Return to GPT Pro

After accepted implementation, Codex inspects the diff, re-verifies at the
lowest sufficient level, and returns bounded evidence to GPT Pro. Pro
corrections do not trigger Sol automatically. Reconsult one fresh configured
advisor only for materially new evidence or a materially changed question,
with an explicit stop condition.

Reject nested orchestration, Sol-to-Sol review, advisor re-entry, duplicate
consultation, and open-ended loops. Do not fabricate a consultation or silently
downgrade when a required lane is missing. Completion requires the outer
controller's `final-verify`.
