# Luna-first implementation lane

This contract applies only after explicit combined-mode selection. The Codex
primary task owns it; it is not a nested `sol-advisor:orchestration` call.

## Runtime capability and identity

Read these values from the native/app adapter as trusted inputs outside the
routing scenario. A scenario cannot promote a self-described native JSON object:

- `list_projects` identifies the selected project as a Git repository, and
  `create_thread`, `list_threads`, `wait_threads`, `read_thread`, and
  `send_message_to_thread` are available.
- The accepted Luna route has real `project_id`, `thread_id`, and `host_id`, an
  allowed `identity_source`, and `task_state` `created` or `ready`.
- A `clientThreadId` is a setup handle, not a task identity; never wait/read/send
  against it. The accepted request is exactly `gpt-5.6-luna` / `thinking: max`.
  Returned model/thinking metadata is optional, but a returned mismatch fails.

Missing capability, identity, or route evidence is `dependency-unavailable`.
Never silently fall back to Terra or Sol, and never use a guessed or stale
thread.

## Task packet

Use one coarse, independently verifiable responsibility per task. Pass only:

- `requirements_digest` plus relevant requirement/Acceptance Criterion IDs;
- objective, owned files, interfaces, cross-cutting constraints, and base commit;
- focused verification command, Test Economy anchors, and no-push/no-PR boundary;
- structured return fields for changed files, tests, blockers, and task identity.

Do not copy complete frozen requirements into every packet. Use the digest and
IDs; the primary retains the full frozen packet and acceptance authority. Use
isolated Git worktrees, at most two independent Luna tasks, and no task per file
or test.

## Correction, Terra, and Sol

If Luna is incomplete, send **one precise correction to the same task**. Inspect
the actual worktree, branch, owned scope, and diff in the primary task.

Routing attestation and execution outcome are separate. A same-root-cause Terra
escalation requires trusted native task-result/wait evidence bound to the Luna
`project_id`, `thread_id`, and `host_id`, reporting two corrections and one
repeated root-cause key.

For difficult scope, a stuck/repeated Luna result, or concurrency, security,
migration, shared state, cross-workstream, performance, or broad-blast-radius
work, preflight the exact native role
`sol_advisor_terra_implementer`. Require real project/thread/host identity,
observed `gpt-5.6-terra` / `high`, and exact role-template status with matching
role-template and shipped-template SHA-256 digests. If any role, identity,
template, or execution evidence is missing, stop with `dependency-unavailable`;
never silently fall back.

Only a trusted Terra result bound to that identity and blocked on one
high-impact architecture, safety, or risk decision permits one bounded,
read-only `sol_advisor_advisor` consultation. Sol cannot edit, implement,
approve, waive verification, or decide completion. Return work to Luna/Terra
and re-verify after the primary records the disposition.
