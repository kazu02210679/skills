# Luna-first implementation lane

This contract applies only after the user explicitly selects combined mode.
It is owned by the Codex primary task; it is not a nested invocation of
`sol-advisor:orchestration` and it does not transfer authority to Luna.

## Default worker

Use a Codex app task at exactly:

```text
model: gpt-5.6-luna
thinking: max
```

Luna / Max is the default implementation worker for bounded, specified work:
features, UI, CRUD, API wiring, boilerplate, repository-pattern refactors,
test corrections, and clearly specified algorithms. The parent writes the
complete task packet and remains responsible for the actual diff, verification,
and acceptance.

Use the app task surface with the returned project identity. Call
`list_projects` before `create_thread`; for Git projects use the app's default
isolated worktree and for non-Git projects use the project's local environment.
The creation response and returned task identity are routing evidence. A
pending `clientThreadId` is only a setup handle; discover the real task before
calling `wait_threads`, `read_thread`, or `send_message_to_thread`.

## Packet and task size

Give one coarse-grained, independently verifiable responsibility to each task.
Include the frozen requirements, owned scope, interfaces, acceptance criteria,
allowed files, focused verification command, test-economy constraints, and the
instruction not to create a PR or push changes. Do not split a stack into one
task per file or one task per test. Default to at most two concurrent Luna
tasks; use three or more only for clearly independent workstreams. Serialize
shared files, dependent stacks, and integration work.

Monitor the same real task with `wait_threads` and `read_thread`, then inspect
the actual branch/worktree and diff in the primary task. Worker reports are
claims, not acceptance evidence.

## Bounded correction and escalation

If the first Luna result is incomplete, send one precise correction to the same task.
Do not create a replacement task merely to avoid a correction. Escalate
to the exact native implementation role `sol_advisor_terra_implementer` pinned
to GPT-5.6 Terra / High when any of the following holds:

- Luna fails again for the same root cause or the task remains stuck.
- The work needs concurrency, security-sensitive logic, a migration, shared
  state, cross-stack integration, difficult performance debugging, or a
  repository-wide/broad-blast-radius change.
- Multiple Luna worktrees must be integrated or the primary cannot establish a
  safe bounded implementation plan.

Observe the selected Terra role and its model/effort before accepting work. Do
not add per-spawn model overrides, silently substitute a role, or fall back to
Sol as an implementation worker. If the exact Terra lane is unavailable,
stop and report the dependency failure.

When Terra still cannot resolve a high-impact design or safety question, ask
the configured `sol_advisor_advisor` one precise, bounded, read-only question.
Sol may advise on architecture, risk, or alternatives; it must not edit,
implement, approve, waive verification, or decide completion. After the
primary records `accept`, `reject`, or `partially accept`, implementation
returns to the appropriate Luna/Terra lane and the primary re-verifies.

Never run an unbounded Luna→Luna loop, use Sol to write code, or invoke both
Terra and Sol by default.

## Acceptance path

```text
Luna / Max
  -> focused verification in the child task
  -> primary diff/scope inspection
  -> one primary focused rerun when the relevant inputs changed
  -> Terra / High only when escalation criteria hold
  -> Sol read-only advice only for a remaining high-impact decision
  -> return evidence to GPT Pro semantic review
```

The primary task owns the final `final-verify` transition. A Luna or Terra
result never authorizes a commit, push, PR, deployment, or destructive action.
