# Task-plan contract

Use this contract for a guarded multi-task implementation plan. Plan and task
files are intended to become auditable in Git, but may be untracked during an
active run. `codex_run.sh` freezes them into run evidence before delegation.
Keep run evidence local and ignored. When the plan directory is inside the
worktree, `codex_commit.sh` stages the active plan directory with its task
commit.

## Plan layout

Create this layout under the target worktree:

```text
.codex-instructions/<plan>/
├── plan-id
├── packet.md
├── test
├── interfaces.md
├── T1.md
├── T1.allowlist
├── T1.test
└── T1.hint-1.md
```

`plan-id` is a stable, non-empty identity; do not use the directory name as a
substitute. `packet.md` defines the plan-level requirements and full acceptance
criteria. `test` contains default test commands, one shell command per line.
`interfaces.md` records stable contracts completed tasks establish. Each
`T<N>.md` is a task packet; each `T<N>.allowlist` and optional `T<N>.test`
overrides the plan default. Hints are orchestrator-written, targeted retry
instructions.

Every task packet must state the task boundary, acceptance criteria, test
policy, and stuck protocol. Every task needs a non-empty allowlist and at least
one test command unless an explicit, reviewed exception is authorized.

`codex_run.sh` enforces the first three for any packet inside `CODEX_META_DIR`:
it refuses to start without a non-empty `plan-id` and an allowlist holding at
least one pattern, and warns when no test command resolves. A packet kept
outside that directory has no plan to protect and runs unguarded, but the
commit gate will not publish it.

## Allowlists and product scope

Write one Bash glob per line. Ignore blank lines and lines beginning with `#`.
The matcher uses `[[ path == glob ]]`: `*` matches `/`, so `src/*` covers the
entire `src` subtree and `*.py` covers Python files anywhere in the repository.
Use full paths when scope must be narrow. Renames check both the source and
destination. The check also includes untracked and deleted product files.

`.codex-instructions/` and `.codex-runs/` are orchestration metadata, not
product files. The scope check excludes them; a plan fingerprint prevents Codex
from editing the active plan. Do not use that exemption to place product work
in metadata directories.

## Frozen run evidence

`codex_run.sh` creates a unique directory and freezes the task contract before
it calls Codex:

```text
.codex-runs/<unique>/
├── .gitignore
├── base_commit
├── workdir
├── task.md
├── allowlist
├── allowlist_source
├── test
├── plan_dir
├── plan-id
├── test_source
├── thread_id
└── attempt-N/
    ├── report.md
    ├── events.jsonl
    ├── stderr.log
    ├── meta.json
    └── scope.txt
```

The exact run may also contain a frozen-contract manifest, a `commit.log`, a
`commit.ref`, and other gate evidence. Treat the frozen copies and their
Git-anchored manifest as immutable. A later attempt always creates a new
`attempt-N` directory; it never overwrites earlier evidence. Resume the exact
recorded `thread_id` when supported, or use the explicit fresh fallback.
Before reserving an attempt or starting Codex, resume verifies that the
recorded live allowlist source still exists at the same pathname and matches
the frozen allowlist bytes. A missing or changed source returns `4`; restore
the recorded source to retry from the same run evidence.

## Commands and prerequisites

Run the scripts from the installed Skill directory:

```bash
"<skill-dir>/scripts/codex_status.sh" <plan-dir> <workdir>
"<skill-dir>/scripts/codex_run.sh" <plan-dir>/T<N>.md <workdir>
"<skill-dir>/scripts/codex_resume.sh" <hint-file> <workdir> <rundir>
"<skill-dir>/scripts/codex_scope_check.sh" <rundir>/allowlist <workdir> <base-commit>
"<skill-dir>/scripts/codex_commit.sh" <plan-dir> T<N> <workdir> <rundir>
```

Require Bash 4.4 or later, Git, the `codex` CLI for run and resume, and one
SHA-256 backend: `sha256sum`, `shasum -a 256`, or `openssl dgst -sha256 -r`.
Set `CODEX_HASH_CMD` only to select a compatible backend deliberately. A `sort`
that accepts `-z` is used when present and is a performance path only; the
scripts fall back to an in-shell sort without it.

The frozen contract's trusted copy lives under the Git common directory, so
every verdict these gates return depends on the delegated run being unable to
write there. Confirm that the Codex CLI's `workspace-write` sandbox excludes
Git metadata before relying on them, and treat `danger-full-access` as
offering no integrity guarantee at all. The anchors are small and are never
pruned automatically; delete
`<git-common-dir>/codex-orchestration-contracts/` entries along with the run
directories they describe.

Common controls are `CODEX_MODEL`, `CODEX_SANDBOX`, `CODEX_EXTRA_ARGS`,
`CODEX_TIMEOUT`, `CODEX_ALLOWLIST`, `CODEX_INTERFACES`, and `CODEX_META_DIR`.
Run preflight overrides are `CODEX_ALLOW_DIRTY=1` and
`CODEX_ALLOW_DEFAULT_BRANCH=1`; use them only with a documented reason.
`CODEX_RESUME_MODE` selects `auto`, `resume`, `last`, or `fresh`, and
`CODEX_MAX_ATTEMPTS` defaults to `3`. Commit controls include
`CODEX_TEST_TIMEOUT`, `CODEX_ALLOW_NO_TESTS=1`, and `CODEX_COMMIT_MESSAGE`.

## Exit statuses and publication

The run and resume wrappers return `0` for a clean run, `2` for usage or
preflight failure, `3` for a successful Codex run with an out-of-scope change,
and `4` when the plan or frozen contract changed. Otherwise they propagate the
Codex exit status. The scope checker returns `0` for allowed scope, `1` for a
violation, and `2` when it cannot make a reliable verdict. Status returns `0`
when all tasks are committed, `3` while tasks remain, and `2` for an unsafe
input or history error.

The commit gate returns `0` only after tests and both scope checks pass. It
returns `1` for failed tests or no product changes, `2` for usage or unsafe
state, `3` for scope violations, `5` when `HEAD` moved or publication conflicts,
and `6` when the frozen contract or live plan drifted. It pins the current named
branch ref, creates one candidate commit, and updates that same ref with a
compare-and-swap against the recorded base commit. This prevents a symbolic
`HEAD` change from publishing the task on another branch. A refused publication
leaves the index as it found it, so the same command can be retried once the
conflicting ref is resolved.

Each successful task commit carries these trailers:

```text
Codex-Plan: <plan-id>
Codex-Task: T<N>
```

`codex_status.sh` derives progress from those trailers. Do not maintain a
separate mutable status file or hand-create a completion trailer.
