---
name: codex-orchestration
description: Delegate implementation from Claude Code to OpenAI Codex while Claude remains the requirements owner and acceptance reviewer. Use in Claude Code when the user asks to let Codex implement a sizeable change, have Claude direct and verify Codex, or continue a Codex run with targeted guidance after a blocker. In Codex, use only to inspect or maintain this orchestration workflow; do not recursively delegate to another Codex session unless the user explicitly requests it.
---

# Guarded Codex orchestration

Keep the orchestrator responsible for requirements, scope, independent review,
and delivery. Let Codex investigate, implement, test, and report. Treat every
Codex report as a claim until the orchestrator verifies it.

Set `SKILL_DIR` to this Skill's directory. Invoke the bundled scripts from
`SKILL_DIR/scripts/`; do not depend on a plugin root, marketplace package,
slash command, or reviewer agent.

## Plan and run tasks

Use a task plan for sizeable work. Follow this order:

1. Define plan-level requirements, constraints, and observable acceptance criteria.
2. Split the work into independently reviewable `T<N>` tasks.
3. Write a stable `plan-id`, and give every task an explicit product-file
   allowlist and test command. The run preflight refuses a plan task missing
   any of them rather than spending a Codex run first.
4. Run `codex_status.sh` to identify the next uncommitted task.
5. Run `codex_run.sh`, then independently inspect its evidence and the diff.
6. Use `codex_resume.sh` only for a targeted, bounded retry.
7. Run `codex_commit.sh` only after independent verification passes.
8. Repeat until `codex_status.sh` reports the plan complete.

Read [the task-plan contract](references/task-plan-contract.md) before creating
or running a plan. It defines the required files, frozen run contract, exit
statuses, and commit evidence.

Keep task packets precise. State the task requirement, in-scope and out-of-scope
work, acceptance checks, test policy, and a stuck protocol: document the cause
and smallest alternative, then stop instead of making an unrequested change.
Tell Codex not to modify Git history or `.codex-instructions/`.

## Run the guarded loop

Use a non-default branch with no uncommitted product changes. Metadata under
`.codex-instructions/` is an exception because it records the plan; product
files are not. Do not override the branch or dirty-tree preflight without an
explicit reason and user authorization.

```bash
"$SKILL_DIR/scripts/codex_status.sh" <plan-dir> <workdir>
"$SKILL_DIR/scripts/codex_run.sh" <plan-dir>/T<N>.md <workdir>
```

The run prints `RUNDIR`. Read the latest `attempt-N/report.md`,
`events.jsonl`, `stderr.log`, `meta.json`, and `scope.txt` there. The wrapper
freezes the task, allowlist, tests, plan identity, and baseline before Codex
runs. A changed plan or frozen contract is a failure, not a retry signal.

If review identifies a narrow, evidence-backed correction, write
`T<N>.hint-M.md` in the plan directory and resume the recorded run:

```bash
"$SKILL_DIR/scripts/codex_resume.sh" \
  <plan-dir>/T<N>.hint-M.md <workdir> <rundir>
```

The default cap is three attempts. Stop and ask the user to decide when the
same blocker persists or the cap is exhausted.

After all task checks pass, record any stable interface in `interfaces.md`,
then commit the task:

```bash
"$SKILL_DIR/scripts/codex_commit.sh" <plan-dir> T<N> <workdir> <rundir>
```

The commit gate reruns frozen tests and scope checks, verifies the plan and
baseline, and publishes one task commit to the named branch ref it pinned at
the start of publication. It adds `Codex-Plan:` and `Codex-Task:` trailers.
Do not create, amend, rebase, or publish task commits outside this gate.

## Review and finish

Read [the acceptance-review checklist](references/acceptance-review.md).
Run every task and plan-level acceptance check yourself. Re-run the scope gate
with the frozen allowlist, inspect the trailers and history, and return
`UNRESOLVED` whenever a required check cannot run.

When status reports all tasks committed, run the full plan-level acceptance
suite. This Skill ends with a verified local branch. Pushing, opening a pull
request, merging, deploying, or changing permissions requires separate user
authorization and an appropriate workflow.

## Guardrails

- Keep the sandbox at the smallest level that works; `workspace-write` is the
  default and `danger-full-access` requires an isolated environment and user authorization.
- Treat exit `1` as a failed test gate or a task that changed no product files,
  `2` as an unsafe preflight or usage failure, `3` as a scope or pending-task
  failure, `4` as plan or contract tampering, `5` as a moved HEAD or
  publication conflict, and `6` as contract drift before commit.
- Do not use this workflow for a trivial change unless the user explicitly
  wants delegation.
- Do not let a generated report replace independent verification.
