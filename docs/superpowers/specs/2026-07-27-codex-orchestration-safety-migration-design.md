# Codex Orchestration Safety Migration

## Goal

Move the useful, unmerged safety work from
`kazu02210679/Codex-plugin-Claude-Code` PR #3 into the canonical
`skills/codex-orchestration` Skill so the legacy repository can be deleted
without losing runtime behavior or regression coverage.

The result remains a portable Skill. It does not preserve the Claude Code
marketplace package, plugin manifest, custom agent, or `/codex-*` slash-command
files.

## Scope

### In scope

- Port the task-level safety gates from legacy PR #3:
  - refuse unsafe default-branch and dirty-worktree starts;
  - freeze the task packet, allowlist, test commands, and plan identity;
  - reject changes outside a per-task file allowlist;
  - detect plan changes during or after a Codex run;
  - preserve isolated attempt evidence and resume the recorded Codex thread;
  - enforce an attempt cap;
  - run task tests and create one scoped commit;
  - derive plan progress from commit trailers.
- Port the reusable shell modules:
  - `codex_lib.sh`;
  - `codex_scope_check.sh`;
  - `codex_commit.sh`;
  - `codex_status.sh`;
  - hardened `codex_run.sh` and `codex_resume.sh`.
- Port the legacy shell test suite into
  `evals/codex-orchestration/`, adapting paths so tests execute the canonical
  Skill resources.
- Update `SKILL.md`, its human-facing README, and references to describe the
  task-plan contract and safety gates.
- Remove live links and instructions that require the legacy repository.
- Record the legacy PR number and head commit in durable migration
  documentation and the GitHub PR description.

### Out of scope

- Claude Code marketplace metadata.
- `.claude-plugin/plugin.json`.
- `/codex-spec`, `/codex-run`, and `/codex-accept` command files.
- The `codex-reviewer` Claude subagent definition.
- Graph Engineering or Loop Engineering Skills.
- Deleting the legacy repository itself.

The portable Skill replaces the command behavior through `SKILL.md`, bundled
scripts, and references. Users invoke it by name or natural language.

## Architecture

Keep `SKILL.md` as the concise workflow entrypoint and move detailed contracts
into one-level references.

```text
skills/codex-orchestration/
├── SKILL.md
├── README.md
├── agents/openai.yaml
├── references/
│   ├── acceptance-review.md
│   └── task-plan-contract.md
└── scripts/
    ├── codex_lib.sh
    ├── codex_run.sh
    ├── codex_resume.sh
    ├── codex_scope_check.sh
    ├── codex_commit.sh
    └── codex_status.sh

evals/codex-orchestration/
├── fixtures/codex
├── lib.sh
├── run_all.sh
├── test_run_resume.sh
├── test_scope_check.sh
└── test_commit_status.sh
```

`codex_lib.sh` owns shared path, hashing, Git, plan-identity, and process
helpers. Each executable script exposes one boundary:

- `codex_run.sh`: preflight, freeze contract, invoke Codex, capture evidence,
  run the scope and plan-integrity checks.
- `codex_resume.sh`: append a new attempt and resume the exact recorded thread
  without overwriting prior evidence.
- `codex_scope_check.sh`: compare tracked, untracked, deleted, and renamed
  product paths against the allowlist.
- `codex_commit.sh`: verify the frozen contract, run test commands, recheck
  scope, and create exactly one task commit.
- `codex_status.sh`: read `Codex-Plan:` and `Codex-Task:` trailers to report
  committed and pending tasks.

## Data flow

1. The orchestrator writes a versioned plan directory containing `plan-id`,
   plan acceptance criteria, task packets, allowlists, and test commands.
2. `codex_run.sh` performs Git preflight and copies the active task contract to
   a unique ignored run directory.
3. Codex executes against the target worktree. Reports, events, stderr, and
   metadata are stored under `attempt-1/`.
4. The wrapper rejects plan tampering or out-of-scope product changes.
5. The orchestrator independently verifies the result. A targeted hint can
   create `attempt-2/` or `attempt-3/` through `codex_resume.sh`.
6. `codex_commit.sh` checks the frozen contract, runs task tests, repeats the
   scope check, and commits only the cleared product paths plus that task's
   plan metadata.
7. `codex_status.sh` derives the next task from Git history instead of a
   mutable status file.

## Failure behavior

- Exit `2`: usage or unsafe preflight; no Codex run or commit.
- Exit `3`: file-scope violation or tasks still pending, depending on command.
- Exit `4`: Codex changed the active plan directory.
- Exit `5`: `HEAD` moved during the task.
- Exit `6`: the frozen contract changed before commit.
- Other run/resume exits propagate the Codex CLI result.
- A missing hash implementation, unresolved Git base, missing tests, exhausted
  attempt cap, or reused non-empty run directory fails closed.

Metadata under `.codex-instructions/` and evidence under `.codex-runs/` are
handled separately from product paths. The active plan is protected by
fingerprint; run evidence is ignored by Git; neither may silently widen the
product allowlist.

## Testing strategy

Use strict TDD for the migration:

1. Port the legacy black-box shell tests first, pointing them at the current
   two-script implementation.
2. Run them and confirm failures caused by the missing gates and scripts.
3. Add the shared library and one production script at a time until the focused
   tests pass.
4. Preserve tests for:
   - default branch and dirty-tree refusal;
   - tracked, untracked, deleted, and renamed scope violations;
   - frozen allowlist and test commands;
   - plan tampering and `HEAD` movement;
   - unique run directories and immutable attempts;
   - exact-thread resume and attempt caps;
   - test-gated, task-scoped commits;
   - plan-aware status trailers;
   - macOS/Linux hash backends and shell portability.
5. Run Skill validation, catalog checks, installer tests, the complete Python
   suite, shellcheck when available, and the migrated evaluation suite.

The migrated tests must execute real shell scripts against disposable Git
repositories and a fake external `codex` executable. They must assert exit
codes and filesystem/Git effects rather than source text.

## Legacy deletion readiness

After the migration is merged:

- the canonical repository contains every reusable script and regression test
  from legacy PR #3;
- plugin-only manifests, commands, and agent files are intentionally retired;
- current documentation contains no live dependency on
  `kazu02210679/Codex-plugin-Claude-Code`;
- legacy PR #3 is closed with a link to the migration PR;
- the old repository can be deleted without removing a supported installation
  path or losing unmerged safety behavior.

Legacy source for audit during migration:

- repository: `kazu02210679/Codex-plugin-Claude-Code`
- pull request: `#3`
- head commit: `38365c178ae98ff7a78f88683df3c89333f9f9cf`
