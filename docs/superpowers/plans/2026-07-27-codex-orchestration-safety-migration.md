# Codex Orchestration Safety Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port every reusable safety gate and regression test from legacy PR #3 into the canonical portable `codex-orchestration` Skill so the legacy repository can be deleted safely.

**Architecture:** Keep the Skill entrypoint concise and place deterministic behavior in six focused shell scripts. Exercise those scripts through black-box shell evaluations launched by the repository's Python unittest suite, so the same checks run on Windows with Git Bash and in GitHub Actions on Ubuntu.

**Tech Stack:** Bash 4.4+, Git, Python 3.12 unittest, PyYAML validation, GitHub Actions.

## Global Constraints

- Use legacy source `kazu02210679/Codex-plugin-Claude-Code` PR #3 at head commit `38365c178ae98ff7a78f88683df3c89333f9f9cf`.
- Preserve portable Skill-relative paths; never depend on `${CLAUDE_PLUGIN_ROOT}`.
- Do not add Claude marketplace metadata, slash commands, or the `codex-reviewer` subagent.
- Fail closed when Git state, scope, plan integrity, hash availability, or test status cannot be established.
- Keep `.codex-instructions/` as auditable plan metadata and `.codex-runs/` as ignored local evidence.
- Follow strict red-green-refactor cycles and commit only green states.
- Leave Graph Engineering and Loop Engineering out of scope.

---

## File map

### Canonical runtime

- `skills/codex-orchestration/scripts/codex_lib.sh`: shared Git, hashing, plan, path, process, and artifact helpers.
- `skills/codex-orchestration/scripts/codex_scope_check.sh`: allowlist enforcement for tracked, untracked, deleted, and renamed paths.
- `skills/codex-orchestration/scripts/codex_run.sh`: safe preflight, frozen contract, first Codex attempt, scope and integrity checks.
- `skills/codex-orchestration/scripts/codex_resume.sh`: exact-session resume with immutable attempt directories and a bounded retry count.
- `skills/codex-orchestration/scripts/codex_commit.sh`: frozen-contract, test, scope, and single-task commit gate.
- `skills/codex-orchestration/scripts/codex_status.sh`: plan progress derived from Git trailers.

### Regression surface

- `evals/codex-orchestration/lib.sh`: disposable repository and assertion helpers.
- `evals/codex-orchestration/fixtures/codex`: deterministic fake external Codex CLI.
- `evals/codex-orchestration/test_scope_check.sh`: scope and fail-closed behavior.
- `evals/codex-orchestration/test_run_resume.sh`: preflight, contract, evidence, thread, and retry behavior.
- `evals/codex-orchestration/test_commit_status.sh`: test gate, commit boundary, and status behavior.
- `evals/codex-orchestration/run_all.sh`: focused evaluation entrypoint.
- `tests/test_codex_orchestration_evals.py`: cross-platform unittest bridge that makes the shell suite part of CI.

### Agent instructions and documentation

- `skills/codex-orchestration/SKILL.md`: concise plan/task workflow and mandatory gates.
- `skills/codex-orchestration/references/task-plan-contract.md`: plan layout, allowlist, artifacts, environment, exit codes, and commit trailers.
- `skills/codex-orchestration/references/acceptance-review.md`: scope and history checks added to independent acceptance review.
- `skills/codex-orchestration/README.md`: human usage without the legacy marketplace.
- `README.md`, `docs/host-compatibility.md`: remove live legacy-repository dependency.
- `evals/co-create-plan/cases.json`: replace plugin/slash-command handoff with portable Skill handoff.

---

### Task 1: Add the shell evaluation bridge and scope gate

**Files:**

- Create: `evals/codex-orchestration/lib.sh`
- Create: `evals/codex-orchestration/test_scope_check.sh`
- Create: `tests/test_codex_orchestration_evals.py`
- Create: `skills/codex-orchestration/scripts/codex_lib.sh`
- Create: `skills/codex-orchestration/scripts/codex_scope_check.sh`

**Interfaces:**

- Consumes: Git repository path, allowlist path, optional base ref.
- Produces: `codex_scope_check.sh <allowlist_file> <workdir> [base_ref]`, returning `0` for clean scope, `1` for a violation, and `2` when no reliable verdict is possible.

- [ ] **Step 1: Port the focused failing scope evaluation**

Copy these exact blobs from legacy commit `38365c178ae98ff7a78f88683df3c89333f9f9cf`:

```text
codex-plugin/tests/lib.sh
  -> evals/codex-orchestration/lib.sh
codex-plugin/tests/test_scope_check.sh
  -> evals/codex-orchestration/test_scope_check.sh
```

In `lib.sh`, replace the plugin-root script resolution with the canonical path:

```bash
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
S="$REPO_ROOT/skills/codex-orchestration/scripts"
```

Create `tests/test_codex_orchestration_evals.py` with a real process boundary:

```python
from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals" / "codex-orchestration"


def find_bash() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    candidates = (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Git" / "usr" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Git" / "bin" / "bash.exe",
    )
    return next((str(path) for path in candidates if path.is_file()), None)


BASH = find_bash()


@unittest.skipUnless(BASH, "Bash 4.4+ is required")
class CodexOrchestrationShellEvaluations(unittest.TestCase):
    def run_eval(self, name: str) -> None:
        result = subprocess.run(
            [BASH, str(EVAL_DIR / name)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        self.assertEqual(
            0,
            result.returncode,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_scope_check(self) -> None:
        self.run_eval("test_scope_check.sh")
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m unittest tests.test_codex_orchestration_evals.CodexOrchestrationShellEvaluations.test_scope_check -v
```

Expected: FAIL because `codex_scope_check.sh` and its shared library do not exist.

- [ ] **Step 3: Port the minimal shared library and scope checker**

Copy the legacy PR #3 blobs:

```text
codex-plugin/scripts/codex_lib.sh
  -> skills/codex-orchestration/scripts/codex_lib.sh
codex-plugin/scripts/codex_scope_check.sh
  -> skills/codex-orchestration/scripts/codex_scope_check.sh
```

Replace plugin-root assumptions with:

```bash
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/codex_lib.sh"
```

Keep the legacy behavior for empty allowlists, unresolved bases, rename source
and destination checks, untracked files, and `.codex-instructions/` /
`.codex-runs/` metadata exemptions.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```powershell
python -m unittest tests.test_codex_orchestration_evals.CodexOrchestrationShellEvaluations.test_scope_check -v
```

Expected: PASS with all black-box scope assertions green.

- [ ] **Step 5: Commit**

```powershell
git add evals/codex-orchestration/lib.sh evals/codex-orchestration/test_scope_check.sh tests/test_codex_orchestration_evals.py skills/codex-orchestration/scripts/codex_lib.sh skills/codex-orchestration/scripts/codex_scope_check.sh
git commit -m "Add codex orchestration scope gate"
```

---

### Task 2: Harden run and resume behavior

**Files:**

- Create: `evals/codex-orchestration/fixtures/codex`
- Create: `evals/codex-orchestration/test_run_resume.sh`
- Modify: `tests/test_codex_orchestration_evals.py`
- Modify: `skills/codex-orchestration/scripts/codex_run.sh`
- Modify: `skills/codex-orchestration/scripts/codex_resume.sh`

**Interfaces:**

- Consumes: task packet, workdir, optional run directory, hint, frozen contract, recorded thread id.
- Produces: unique `.codex-runs/<timestamp>-<suffix>/` directories with `attempt-N/` evidence; exit `3` on scope violation and `4` on active-plan tampering.

- [ ] **Step 1: Port the failing run/resume evaluation**

Copy:

```text
codex-plugin/tests/fixtures/codex
  -> evals/codex-orchestration/fixtures/codex
codex-plugin/tests/test_run_resume.sh
  -> evals/codex-orchestration/test_run_resume.sh
```

Add this independent test method:

```python
def test_run_resume(self) -> None:
    self.run_eval("test_run_resume.sh")
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m unittest tests.test_codex_orchestration_evals.CodexOrchestrationShellEvaluations.test_run_resume -v
```

Expected: FAIL because the current wrappers do not implement Git preflight,
frozen contracts, plan fingerprints, unique attempt directories, exact-thread
resume, or an enforced attempt cap.

- [ ] **Step 3: Replace the wrappers with the hardened implementations**

Port the legacy PR #3 versions of:

```text
codex-plugin/scripts/codex_run.sh
codex-plugin/scripts/codex_resume.sh
```

Make only portability changes:

```bash
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/codex_lib.sh"
```

Do not retain `${CLAUDE_PLUGIN_ROOT}`. Preserve closed stdin, exec-level option
ordering before `resume`, `CODEX_RESUME_MODE=auto`, exact recorded thread
selection, the fresh-run fallback, unique run-directory suffixes, frozen task /
allowlist / test files, and immutable `attempt-N/` evidence.

- [ ] **Step 4: Run scope and run/resume tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_codex_orchestration_evals -v
```

Expected: both methods PASS.

- [ ] **Step 5: Commit**

```powershell
git add evals/codex-orchestration/fixtures/codex evals/codex-orchestration/test_run_resume.sh tests/test_codex_orchestration_evals.py skills/codex-orchestration/scripts/codex_run.sh skills/codex-orchestration/scripts/codex_resume.sh
git commit -m "Harden codex orchestration runs"
```

---

### Task 3: Add the commit and status gates

**Files:**

- Create: `evals/codex-orchestration/test_commit_status.sh`
- Create: `evals/codex-orchestration/run_all.sh`
- Modify: `tests/test_codex_orchestration_evals.py`
- Create: `skills/codex-orchestration/scripts/codex_commit.sh`
- Create: `skills/codex-orchestration/scripts/codex_status.sh`

**Interfaces:**

- Consumes: plan directory, task id, workdir, frozen run directory.
- Produces: one scoped commit with `Codex-Plan:` and `Codex-Task:` trailers; plan-aware status with exit `3` while tasks remain and `0` when complete.

- [ ] **Step 1: Port the failing commit/status evaluation**

Copy:

```text
codex-plugin/tests/test_commit_status.sh
  -> evals/codex-orchestration/test_commit_status.sh
codex-plugin/tests/run_all.sh
  -> evals/codex-orchestration/run_all.sh
```

Add:

```python
def test_commit_status(self) -> None:
    self.run_eval("test_commit_status.sh")
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```powershell
python -m unittest tests.test_codex_orchestration_evals.CodexOrchestrationShellEvaluations.test_commit_status -v
```

Expected: FAIL because `codex_commit.sh` and `codex_status.sh` do not exist.

- [ ] **Step 3: Port the minimal commit and status implementations**

Copy:

```text
codex-plugin/scripts/codex_commit.sh
  -> skills/codex-orchestration/scripts/codex_commit.sh
codex-plugin/scripts/codex_status.sh
  -> skills/codex-orchestration/scripts/codex_status.sh
```

Source the Skill-relative `codex_lib.sh`. Preserve these gates:

```text
frozen plan identity -> frozen allowlist -> frozen test commands
-> tests pass -> scope recheck -> HEAD unchanged
-> stage cleared product files plus the active task plan
-> exactly one commit with Codex-Plan and Codex-Task trailers
```

- [ ] **Step 4: Run all migrated shell evaluations and verify GREEN**

Run:

```powershell
python -m unittest tests.test_codex_orchestration_evals -v
```

Expected: three methods PASS and `run_all.sh` also exits `0` when invoked with
Git Bash.

- [ ] **Step 5: Commit**

```powershell
git add evals/codex-orchestration/test_commit_status.sh evals/codex-orchestration/run_all.sh tests/test_codex_orchestration_evals.py skills/codex-orchestration/scripts/codex_commit.sh skills/codex-orchestration/scripts/codex_status.sh
git commit -m "Add codex orchestration commit gates"
```

---

### Task 4: Update the portable Skill contract and remove legacy interfaces

**Files:**

- Modify: `skills/codex-orchestration/SKILL.md`
- Create: `skills/codex-orchestration/references/task-plan-contract.md`
- Modify: `skills/codex-orchestration/references/acceptance-review.md`
- Modify: `skills/codex-orchestration/README.md`
- Modify: `README.md`
- Modify: `docs/host-compatibility.md`
- Modify: `evals/co-create-plan/cases.json`

**Interfaces:**

- Consumes: the six bundled scripts and plan-directory contract from Tasks 1-3.
- Produces: a concise natural-language Skill workflow with no marketplace or slash-command dependency.

- [ ] **Step 1: Update `SKILL.md` around task-level execution**

Keep the existing trigger semantics. Replace the single-packet run section with
this ordered contract:

```markdown
1. Define plan-level requirements and acceptance criteria.
2. Split sizeable work into reviewable `T<N>` tasks.
3. Give every task an explicit product-file allowlist and test command.
4. Run `codex_status.sh` to select the next task.
5. Run `codex_run.sh`; independently inspect the evidence and diff.
6. Use `codex_resume.sh` only for a targeted bounded retry.
7. Run `codex_commit.sh` only after independent verification.
8. Repeat until `codex_status.sh` reports the plan complete.
```

Link directly to `references/task-plan-contract.md` and
`references/acceptance-review.md`. Keep the body below 500 lines.

- [ ] **Step 2: Write the detailed task-plan reference**

Document literal layouts and contracts:

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

.codex-runs/<unique>/
├── .gitignore
├── base_commit
├── task.md
├── allowlist
├── test
├── plan_dir
├── thread_id
└── attempt-N/{report.md,events.jsonl,stderr.log,meta.json,scope.txt}
```

Include allowlist glob semantics, environment variables, exit codes, hash and
Bash prerequisites, immutable attempt behavior, and the two Git trailers.

- [ ] **Step 3: Extend independent acceptance review**

Require the reviewer to run the frozen scope check, inspect task commit
trailers, verify one task per commit, and return `UNRESOLVED` when a check
cannot run.

- [ ] **Step 4: Remove legacy live interfaces from user documentation**

Make these exact semantic changes:

```text
README.md:
  replace the linked legacy repository name with “旧Claude Code plugin”
skills/codex-orchestration/README.md:
  remove /codex-spec, /codex-run, /codex-accept mapping
  document the six Skill-relative scripts
docs/host-compatibility.md:
  describe slash commands as intentionally retired, not an alternate interface
evals/co-create-plan/cases.json:
  prompt -> approved plan handed to codex-orchestration
  packet_path -> .codex-instructions/<plan>/packet.md
  next_action -> skills/codex-orchestration/scripts/codex_status.sh
```

Keep historical design records as plain audit history; do not add a live
installation dependency.

- [ ] **Step 5: Regenerate and validate documentation**

Run:

```powershell
python scripts/generate-skill-catalog.py
python scripts/generate-skill-catalog.py --check
python scripts/validate-skills.py
python -m unittest discover -s evals/co-create-plan -p 'test_*.py' -v
```

Expected: catalog current, 8 Skills valid, 23 co-create-plan tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add README.md docs/host-compatibility.md evals/co-create-plan/cases.json skills/codex-orchestration
git commit -m "Document guarded codex orchestration"
```

---

### Task 5: Complete repository verification and migration audit

**Files:**

- Modify only when a failing check demonstrates an integration defect.

**Interfaces:**

- Consumes: complete migrated Skill and repository validation system.
- Produces: a green branch with no supported dependency on the legacy repository.

- [ ] **Step 1: Validate the Skill with the system validator**

Run:

```powershell
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/codex-orchestration
```

Expected: valid Skill.

- [ ] **Step 2: Run shell syntax and focused evaluations**

Run with Git for Windows Bash:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -n `
  skills/codex-orchestration/scripts/codex_lib.sh `
  skills/codex-orchestration/scripts/codex_run.sh `
  skills/codex-orchestration/scripts/codex_resume.sh `
  skills/codex-orchestration/scripts/codex_scope_check.sh `
  skills/codex-orchestration/scripts/codex_commit.sh `
  skills/codex-orchestration/scripts/codex_status.sh `
  evals/codex-orchestration/lib.sh `
  evals/codex-orchestration/run_all.sh `
  evals/codex-orchestration/test_scope_check.sh `
  evals/codex-orchestration/test_run_resume.sh `
  evals/codex-orchestration/test_commit_status.sh

& 'C:\Program Files\Git\bin\bash.exe' `
  evals/codex-orchestration/run_all.sh
```

Expected: syntax exit `0`; all shell assertions PASS.

- [ ] **Step 3: Run the complete repository suite**

Run:

```powershell
python scripts/generate-skill-catalog.py --check
python scripts/validate-skills.py
python -m unittest discover -s tests -v
```

Expected: catalog current, 8 Skills valid, all tests PASS with no generated
tracked files.

- [ ] **Step 4: Audit legacy references**

Run:

```powershell
rg -n "github\.com/kazu02210679/Codex-plugin-Claude-Code|/codex-(spec|run|accept)" `
  README.md skills docs evals
```

Expected: no current installation link or active slash-command instruction.
Historical design records may mention the retired name without linking to it.

- [ ] **Step 5: Inspect the final diff**

Run:

```powershell
git diff --check origin/main...HEAD
git status -sb
git diff --stat origin/main...HEAD
```

Expected: no whitespace errors, clean worktree, only migration-scope files.

- [ ] **Step 6: Commit any test-proven integration fix**

If Step 1-5 required a fix, first add the focused failing regression test, watch
it fail, apply the minimal fix, rerun the focused and full suites, then commit:

```powershell
git add skills/codex-orchestration evals/codex-orchestration `
  tests/test_codex_orchestration_evals.py README.md `
  docs/host-compatibility.md evals/co-create-plan/cases.json
git commit -m "Fix codex orchestration migration integration"
```

If no fix was required, do not create an empty commit.

---

### Task 6: Publish, merge, and retire the legacy PR

**Files:**

- No local source changes.

**Interfaces:**

- Consumes: verified branch and GitHub repository access.
- Produces: merged migration PR and closed legacy PR #3 with an audit link.

- [ ] **Step 1: Push the branch**

```powershell
git push -u origin agent/migrate-codex-orchestration-guards
```

- [ ] **Step 2: Open a ready-for-review PR to `main`**

The title must be:

```text
Migrate codex orchestration safety gates
```

The body must list the legacy PR #3 head SHA, migrated scripts, retired
plugin-only interfaces, focused evaluations, full tests, and deletion-readiness
audit.

- [ ] **Step 3: Wait for GitHub Actions**

Run:

```powershell
gh pr checks --watch --interval 10
```

Expected: every required check PASS.

- [ ] **Step 4: Merge with the checked head SHA**

Use a merge commit and reject the operation if the head SHA moved after
verification.

- [ ] **Step 5: Close legacy PR #3**

Close
`kazu02210679/Codex-plugin-Claude-Code#3` with a comment that links to the
merged migration PR and states:

```text
The portable runtime scripts, safety gates, and regression tests were migrated.
Claude marketplace metadata, slash commands, and the dedicated reviewer agent
were intentionally retired.
```

- [ ] **Step 6: Verify deletion readiness**

Confirm:

```text
new main contains six orchestration scripts
new main runs the migrated shell suite through unittest
new documentation has no live legacy installation link
legacy PR #3 is closed with the migration link
legacy repository itself still exists and was not deleted
```
