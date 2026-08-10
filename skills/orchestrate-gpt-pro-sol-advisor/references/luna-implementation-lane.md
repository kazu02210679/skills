# Luna-first implementation lane

This contract applies only after the user explicitly selects combined mode.
It is owned by the Codex primary task; it is not a nested invocation of
`sol-advisor:orchestration` and it does not transfer authority to Luna.

## Runtime capability preflight

Before routing, observe the app surface rather than trusting requested settings
or model output. For a Git project, require all of these:

- `list_projects` identifies the target project as a Git repository.
- `create_thread`, `list_threads`, `wait_threads`, `read_thread`, and
  `send_message_to_thread` are available.
- The creation result resolves to a real task/thread identity. A pending
  `clientThreadId` is only a setup handle; do not call wait/read/send against it.
- The task observes exactly `gpt-5.6-luna` with `thinking: max`, and the
  preflight record contains `task_status: ready` before work is accepted.

If any check fails, stop with `dependency-unavailable`. Never silently fall back
to Terra or Sol and never call a stale or guessed thread.

## Task packet

Use one coarse-grained, independently verifiable responsibility per task. Keep
the packet bounded. Pass:

- `requirements_digest` and only the relevant requirement/Acceptance Criterion IDs
- the objective, owned file scope, interfaces, cross-cutting constraints, and base commit
- the focused verification command and the Test Economy anchors
- the no-push/no-PR boundary and a structured return contract

Do not copy the complete frozen requirements into every task. The digest, relevant
IDs, and task-specific constraints preserve the boundary with less context. The
primary task retains the complete frozen packet and owns acceptance.

Use the app's default isolated worktree for Git projects. Keep at most two
independent Luna tasks in parallel by default. Serialize shared files, dependent
stacks, and integration work; do not spawn one task per file or test.

## Correction and Terra escalation

If the first Luna result is incomplete, send one precise correction to the same
task. Inspect the actual worktree, branch, owned scope, and diff in the
primary task; a worker report is not acceptance evidence.

Escalate to the exact native role `sol_advisor_terra_implementer` only when:

- Luna fails again for the same root cause or remains stuck;
- the work needs concurrency, security-sensitive logic, a migration, shared
  state, cross-workstream integration, difficult performance debugging, or a
  broad-blast-radius change; or
- multiple Luna worktrees need integration and the primary cannot establish a
  safe bounded plan.

Before accepting Terra, independently preflight that the native role is exposed,
the task is ready, and the observed role/model/effort are exactly
`sol_advisor_terra_implementer` / `gpt-5.6-terra` / `high`. If the exact role is
missing or mismatched, stop with `dependency-unavailable`; do not substitute a
role, add per-spawn overrides, or fall back silently.

If Terra still cannot resolve one high-impact architecture, safety, or risk
question, consult `sol_advisor_advisor` once with a bounded read-only packet.
Sol cannot edit, implement, approve, waive verification, or decide completion.
After the primary records `accept`, `reject`, or `partially accept`, return code
work to Luna/Terra and re-verify.
