# Codex Orchestration

Use this portable Skill to run a guarded implementation loop: define a plan,
delegate one scoped task to Codex, review its evidence, commit through the
gate, and repeat. The portable runtime replaces the retired Claude Code plugin
interfaces; it does not require a marketplace manifest, slash commands, or a
dedicated reviewer agent.

## Workflow

1. Create `.codex-instructions/<plan>/` with a stable `plan-id`, plan packet,
   task packets, allowlists, and test commands.
2. Ask status for the next task.
3. Run one task and inspect its report, logs, scope result, and diff.
4. Resume only with a narrow, evidence-backed hint and within the attempt cap.
5. Independently verify the task, record its interface additions, and commit it
   through the gate.
6. Repeat until status reports the plan complete, then run plan-level checks.

Read [the task-plan contract](references/task-plan-contract.md) for file
layouts, exits, and guardrails. Read [the acceptance-review checklist](references/acceptance-review.md)
before declaring delivery.

## Bundled scripts

| Script | Use |
|---|---|
| `scripts/codex_status.sh` | Report committed and pending tasks from Git trailers. |
| `scripts/codex_run.sh` | Freeze a task contract, run Codex, and capture attempt evidence. |
| `scripts/codex_resume.sh` | Add an immutable retry attempt to the recorded run. |
| `scripts/codex_scope_check.sh` | Check product changes against the frozen allowlist. |
| `scripts/codex_commit.sh` | Recheck scope and tests, then publish one guarded task commit. |
| `scripts/codex_lib.sh` | Provide shared helpers for the five executable scripts. |

Run scripts by their Skill-relative path:

```bash
skills/codex-orchestration/scripts/codex_status.sh \
  .codex-instructions/add-export /path/to/repository

skills/codex-orchestration/scripts/codex_run.sh \
  .codex-instructions/add-export/T1.md /path/to/repository
```

Use a non-default branch with no uncommitted product files. The commit gate
creates one commit per task with `Codex-Plan:` and `Codex-Task:` trailers and
does not publish to a remote.

## Retired interfaces

The plugin-only manifest, slash-command files, and dedicated reviewer agent are
intentionally retired. The six portable scripts and this Skill's references
retain the supported workflow, so no live plugin dependency remains before the
legacy plugin repository is retired or deleted.
