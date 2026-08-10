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
read-only consultation after its preflight and attestation gates pass. Do not
invoke `sol-advisor:orchestration` in combined mode; its authority conflicts
with this composition contract.

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

The combined-mode implementation policy is:

```yaml
implementation_policy: luna_first
luna:
  model: gpt-5.6-luna
  thinking: max
  default: true
  max_parallel_tasks: 2
terra:
  role: sol_advisor_terra_implementer
  model: gpt-5.6-terra
  effort: high
  trigger: difficult_or_stuck_implementation
sol:
  role: sol_advisor_advisor
  mode: read_only_advice
  trigger: terra_cannot_resolve_high_impact_decision
```

Use Luna / Max for bounded, sufficiently specified work: feature
implementation, UI, CRUD, API wiring, boilerplate, repository-pattern
refactors, test corrections, clearly specified algorithms, and isolated
worktree tasks. The primary creates a Codex app task with `model:
gpt-5.6-luna` and `thinking: max`; do not make Luna an implicit native Sol
role or silently substitute another model.

Use coarse-grained bounded tasks. Do not spawn one task per file or one task
per test. Run at most two independent Luna tasks in parallel by default; use
more only for clearly independent workstreams. Serialize shared files,
dependent stacks, and integration work.

If a Luna result is incomplete, send one precise correction to the same task.
If Luna fails again for the same root cause, remains stuck, or the task needs
concurrency, security-sensitive logic, a migration, shared state,
cross-workstream integration, difficult performance debugging, or a broad
blast-radius change, escalate to the exact native Terra implementation role
`sol_advisor_terra_implementer` at GPT-5.6 Terra / High. Observe the role,
model, and effort before accepting work; never add per-spawn overrides, silently
substitute a role, or retry an unbounded Luna loop.

If Terra is still blocked on a high-impact architecture, safety, or risk
decision, consult the configured `sol_advisor_advisor` with one precise, bounded packet.
Sol must remain read-only and must not become the implementation
worker. After Codex records `accept`, `reject`, or `partially accept`, return
implementation to Luna or Terra and re-verify. Do not invoke both Terra and Sol
by default.

The implementation path is therefore:

```text
Luna / Max -> focused verification -> primary diff inspection
  -> one same-task correction if needed
  -> Terra / High for difficult or stuck implementation
  -> Sol read-only advice only for a remaining high-impact decision
  -> primary verification -> GPT Pro semantic review -> final-verify
```

Worker reports are claims. The primary must inspect the actual worktree/branch,
complete diff, in-scope file set, and verification evidence. A worker never
authorizes a commit, push, PR, deployment, permission change, or destructive
action.

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
   the advisory lane. Any binding/interface failure stops before Pro. The Terra
   implementation lane is separate and must be independently observable when
   escalation is needed; it is never used as the configured advisor.

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

Apply [references/verification-economy.md](references/verification-economy.md):

- Every new test maps to an acceptance criterion, material risk, or bug root
  cause; otherwise do not add it.
- Default `new_test_files = 0`; add a file only with a recorded reason that an
  existing test file cannot express the contract.
- Use one regression test per bug root cause by default, table-driven when
  several inputs prove the same behavior, and test observable contracts rather
  than implementation details.
- Use L0 diff/static inspection, L1 affected focused test by default, L2 for
  shared/API/dependency changes, and L3 full-suite only for dependency/build/
  schema/shared-core/release-critical changes.
- Do not rerun an unchanged successful verification command unless relevant
  code, test, or configuration changed. Do not return successful full logs to
  the next model context.

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
