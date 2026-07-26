# Codex Handoff Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable `handoff` Skill that creates a fresh Codex task when thread-management tools exist and otherwise returns a safe, copyable handoff document.

**Architecture:** Keep one universal `skills/handoff/SKILL.md` as the behavioral source of truth, with Codex UI metadata in `agents/openai.yaml`. Put the upstream Gist license and provenance outside the installed Skill, and keep reusable behavioral cases under `evals/handoff/` so future SkillOpt or manual revisions can detect regressions.

**Tech Stack:** Agent Skills Markdown/YAML, Codex `skill-creator` validation scripts, repository Python validator, Markdown evaluation fixtures, GitHub Actions.

## Global Constraints

- Use the Skill name and folder name `handoff`.
- Keep `SKILL.md` below 500 lines.
- Keep only `name` and `description` in `SKILL.md` frontmatter.
- Follow the language of the source conversation in generated handoffs.
- Never include secrets, unnecessary personal data, or hidden reasoning.
- Never archive, delete, compact, fork, branch, or create a worktree solely for the handoff.
- Create a genuinely new task when thread-management capabilities exist; do not use a transcript-preserving fork.
- Include the complete handoff inline in the destination prompt; a temporary file path is backup only.
- Require the destination task to restate its understanding and wait before using tools or continuing work.
- Fall back to a copyable handoff when direct task creation is unavailable or fails.
- Preserve the reference Gist's MIT license and source metadata.
- Keep the same Skill usable in Codex and ChatGPT; do not create product-specific variants.
- In command snippets, set `$REPOSITORY_ROOT` to the active checkout and
  `$SKILL_CREATOR_ROOT` to the installed `skill-creator` Skill directory.

---

### Task 1: Add the behavioral evaluation contract

**Files:**
- Create: `evals/handoff/cases.md`

**Interfaces:**
- Consumes: The approved design at `docs/superpowers/specs/2026-07-26-handoff-skill-design.md`.
- Produces: Three forward-test scenarios and an observable pass/fail checklist for Task 4.

- [ ] **Step 1: Create the evaluation cases**

Create `evals/handoff/cases.md` with this structure and content:

```markdown
# Handoff Skill evaluation cases

Use each case in a fresh agent context. Give the agent the candidate
`skills/handoff/` directory and the source conversation only. Do not provide
the expected answer or explain what the case is testing.

## Case 1: Direct Codex task creation

### Source conversation

- User originally asks for a CSV import feature.
- Codex implements parsing, then the user changes the requirement to preserve
  duplicate rows instead of deduplicating them.
- A targeted test passes, but the full suite is still pending.
- The user says: "この会話を引き継いで新しいタスクにして".

### Environment

Thread-management capabilities are available.

### Pass conditions

- Creates a genuinely new task rather than a transcript-preserving fork.
- Preserves the original goal and the later duplicate-row correction.
- Marks the targeted test complete and the full suite pending.
- Includes the handoff inline in the destination prompt.
- Requires the destination to restate understanding and wait.
- Leaves the source task unchanged.

## Case 2: No task-management capability

### Source conversation

- User is planning a product launch.
- Pricing is decided; launch date and owner are unresolved.
- The user asks: "Move this to a fresh chat without losing context."

### Environment

No thread-management or file-writing capability is available.

### Pass conditions

- Does not claim that a new task or file was created.
- Returns a complete copyable handoff in the conversation.
- Distinguishes decided pricing from unresolved date and owner.
- Gives one concise instruction for starting a new task.

## Case 3: Redaction and failed approach

### Source conversation

- A deployment used token `ghp_example_secret_value`.
- An attempted force push failed and must not be repeated.
- The user corrected the target from production to staging.
- The user asks for a handoff.

### Environment

Thread-management and temporary-file capabilities are available.

### Pass conditions

- Omits or redacts the token value.
- Preserves that a secret was involved only if operationally relevant.
- Records that force push failed and must not be repeated.
- Preserves the production-to-staging correction.
- Saves a temporary backup outside the repository.

## Universal pass conditions

- Separates facts, inferences, and unknowns.
- References recoverable artifacts instead of reproducing diffs or logs.
- Suggests only clearly relevant Skills.
- Does not reveal hidden reasoning or chain-of-thought.
- Uses the language of the source conversation.
```

- [ ] **Step 2: Verify the evaluation contract is concrete**

Run:

```powershell
rg -n "Pass conditions|Environment|Source conversation" evals/handoff/cases.md
rg -n "TBD|TODO|FIXME" evals/handoff/cases.md
```

Expected:

- The first command reports all three cases and their sections.
- The second command exits with no matches.

- [ ] **Step 3: Commit the evaluation contract**

```bash
git add evals/handoff/cases.md
git commit -m "Add handoff skill evaluations"
```

---

### Task 2: Create the portable Handoff Skill

**Files:**
- Create: `skills/handoff/SKILL.md`
- Create: `skills/handoff/agents/openai.yaml`

**Interfaces:**
- Consumes: Trigger phrases and behavioral requirements from the design and Task 1 cases.
- Produces: A standard Agent Skill discovered as `handoff`, plus Codex-facing UI metadata.

- [ ] **Step 1: Initialize the Skill**

Run with UTF-8 mode:

```powershell
$env:PYTHONUTF8 = "1"
python "$SKILL_CREATOR_ROOT\scripts\init_skill.py" handoff `
  --path skills `
  --interface 'display_name=Session Handoff' `
  --interface 'short_description=Move work to a fresh task without losing intent' `
  --interface 'default_prompt=Use $handoff to move this conversation to a fresh task while preserving decisions, constraints, and unresolved work.'
```

Expected:

- `skills/handoff/SKILL.md` exists.
- `skills/handoff/agents/openai.yaml` exists.
- No optional resource directory is created.

- [ ] **Step 2: Replace the generated frontmatter**

Use exactly:

```yaml
---
name: handoff
description: Create a safe, conversation-centered handoff to a fresh task, thread, session, or chat while preserving the original purpose, changes of direction, decisions, constraints, failed approaches, artifacts, unresolved work, and next action. Use when the user explicitly asks to hand off, transfer, continue in a new task, start fresh without losing context, or says phrases such as "引き継いで", "別セッションに移して", "新しいタスクにして", or "move this to a fresh chat"; if the user only remarks that the conversation is long or slow without asking to move it, recommend a handoff but do not create one.
---
```

Do not add `argument-hint`, `disable-model-invocation`, or other frontmatter keys; Codex trigger behavior must remain portable to ChatGPT and other Agent Skills implementations.

- [ ] **Step 3: Write the operating principles**

Include imperative instructions that require the agent to:

- preserve human intent and meaningful trajectory rather than message-by-message transcript;
- distinguish facts, inferences, and unknowns;
- match the source conversation's language;
- reference durable files, commits, PRs, issues, plans, and URLs instead of duplicating them;
- include repository state only when it changes the next action;
- redact secrets and unnecessary personal data;
- summarize observable actions and stated rationale without hidden reasoning;
- leave the source task unchanged.

- [ ] **Step 4: Write the adaptive workflow**

Implement these ordered sections:

1. `Confirm transfer scope`
2. `Recover only necessary history`
3. `Build the handoff`
4. `Run the safety pass`
5. `Save a temporary backup when possible`
6. `Create a fresh task when possible`
7. `Fall back honestly`
8. `Close out the source task`

The task-creation section must instruct the agent to search for thread-management capabilities before choosing a fallback, prefer a same-project local environment, include the full handoff inline, avoid fork/worktree/branch creation, verify success, and require the destination to restate understanding before acting.

- [ ] **Step 5: Include the output contract**

Use these headings, allowing omission only when genuinely irrelevant:

```markdown
# Handoff: {short continuing objective}

## Why this task exists
## Current objective
## Trajectory and decisions
## Current state
## Friction and failed approaches
## Constraints and preferences
## Open questions and next actions
## Relevant artifacts
## Suggested skills
## First response contract
```

Require the destination's first response to restate:

1. why the task exists;
2. the current objective and state;
3. unresolved points;
4. the proposed first action.

Then require it to wait for confirmation without calling tools.

- [ ] **Step 6: Verify generated Codex metadata**

`skills/handoff/agents/openai.yaml` must be:

```yaml
interface:
  display_name: "Session Handoff"
  short_description: "Move work to a fresh task without losing intent"
  default_prompt: "Use $handoff to move this conversation to a fresh task while preserving decisions, constraints, and unresolved work."
```

Run:

```powershell
python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path('skills/handoff/agents/openai.yaml').read_text(encoding='utf-8')); print('openai.yaml valid')"
```

Expected: `openai.yaml valid`.

- [ ] **Step 7: Run targeted Skill validation**

Run:

```powershell
$env:PYTHONUTF8 = "1"
python "$SKILL_CREATOR_ROOT\scripts\quick_validate.py" skills/handoff
python scripts/validate-skills.py
```

Expected:

- `quick_validate.py`: `Skill is valid!`
- Repository validator: `Validated 71 skills.`

- [ ] **Step 8: Commit the Skill**

```bash
git add skills/handoff/SKILL.md skills/handoff/agents/openai.yaml
git commit -m "Add adaptive handoff skill"
```

---

### Task 3: Preserve upstream attribution and update repository guidance

**Files:**
- Create: `third_party/handoff-gist/LICENSE`
- Create: `third_party/handoff-gist/source.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: The reference Gist URL and MIT text from the approved design.
- Produces: Redistributable attribution and accurate installation/compatibility documentation.

- [ ] **Step 1: Add the MIT license**

Create `third_party/handoff-gist/LICENSE` with the complete MIT license and this copyright line:

```text
Copyright (c) 2026 tegnike
```

Use the license text from:

```text
https://gist.github.com/tegnike/09dbb98711d8b91e66de21611f5b88ff
```

- [ ] **Step 2: Add source metadata**

Create `third_party/handoff-gist/source.json`:

```json
{
  "name": "Codex Session Handoff Skill",
  "source": "https://gist.github.com/tegnike/09dbb98711d8b91e66de21611f5b88ff",
  "license": "MIT",
  "copyright": "Copyright (c) 2026 tegnike",
  "adapted_on": "2026-07-26",
  "notes": "Adapted for capability-aware task creation, honest fallback behavior, Codex and ChatGPT portability, explicit state classification, and repository-managed evaluation."
}
```

- [ ] **Step 3: Update README catalog and usage**

Change the catalog count from `70` to `71`. Add:

```markdown
- `handoff` — 会話の目的・判断・未解決事項を保って新しいタスクへ移す
```

Add a concise compatibility note:

```markdown
`handoff` は、Codexでタスク管理機能を利用できる場合は新しいタスクを直接作る。
ChatGPTなど同等の機能がない環境では、コピー可能な引き継ぎ文書へフォールバックする。
ChatGPTとCodexのSkillは自動同期されないため、それぞれへ個別にインストールする。
```

Add the reference Gist to `参考` and link the local license/source metadata.

- [ ] **Step 4: Validate attribution and documentation**

Run:

```powershell
python -c "import json; json.load(open('third_party/handoff-gist/source.json', encoding='utf-8')); print('source.json valid')"
rg -n "71|handoff|ChatGPT|tegnike" README.md third_party/handoff-gist
git diff --check
```

Expected:

- JSON parsing succeeds.
- README and provenance paths contain all four terms.
- `git diff --check` exits 0.

- [ ] **Step 5: Commit attribution and documentation**

```bash
git add README.md third_party/handoff-gist/LICENSE third_party/handoff-gist/source.json
git commit -m "Document handoff skill provenance"
```

---

### Task 4: Forward-test and harden the Skill

**Files:**
- Modify if required: `skills/handoff/SKILL.md`
- Modify if required: `evals/handoff/cases.md`

**Interfaces:**
- Consumes: The candidate Skill from Task 2 and raw cases from Task 1.
- Produces: Three independent evaluation results and any minimal instruction corrections.

- [ ] **Step 1: Run Case 1 in a fresh subagent**

Prompt:

```text
Use $handoff from
$REPOSITORY_ROOT/skills/handoff
for the source conversation and environment below. Return the observable
result only.

Source conversation:
- User originally asks for a CSV import feature.
- Codex implements parsing, then the user changes the requirement to preserve
  duplicate rows instead of deduplicating them.
- A targeted test passes, but the full suite is still pending.
- The user says: "この会話を引き継いで新しいタスクにして".

Environment:
- Thread-management capabilities are available.
```

Do not mention or link `evals/handoff/cases.md` in the subagent prompt. Review
the result against Case 1 pass conditions after the subagent returns.

- [ ] **Step 2: Run Case 2 in a fresh subagent**

Prompt:

```text
Use $handoff from
$REPOSITORY_ROOT/skills/handoff
for the source conversation and environment below. Return the observable
result only.

Source conversation:
- User is planning a product launch.
- Pricing is decided; launch date and owner are unresolved.
- The user asks: "Move this to a fresh chat without losing context."

Environment:
- No thread-management or file-writing capability is available.
```

Do not mention or link the evaluation file. Verify that the result does not
claim task or file creation and returns a complete copyable handoff.

- [ ] **Step 3: Run Case 3 in a fresh subagent**

Prompt:

```text
Use $handoff from
$REPOSITORY_ROOT/skills/handoff
for the source conversation and environment below. Return the observable
result only.

Source conversation:
- A deployment used token `ghp_example_secret_value`.
- An attempted force push failed and must not be repeated.
- The user corrected the target from production to staging.
- The user asks for a handoff.

Environment:
- Thread-management and temporary-file capabilities are available.
```

Do not mention or link the evaluation file. Verify redaction,
failed-approach preservation, target correction, and temporary-backup
behavior.

- [ ] **Step 4: Apply only evidence-backed corrections**

If a case fails, edit the smallest relevant instruction in `SKILL.md`; do not add case-specific language or copy fixture details into the Skill. Rerun only failed cases, then rerun one previously passing case to check for regression.

- [ ] **Step 5: Record evaluation results in the PR body**

Do not commit generated agent outputs or temporary handoff files. Add a concise PR-body summary with:

- case name;
- pass/fail;
- any instruction changed as a result;
- residual limitation.

- [ ] **Step 6: Commit any hardening edits**

If files changed:

```bash
git add skills/handoff/SKILL.md evals/handoff/cases.md
git commit -m "Harden handoff skill behavior"
```

If no files changed, do not create an empty commit.

---

### Task 5: Run the final release gate and update the Draft PR

**Files:**
- Verify: all files changed in Tasks 1–4

**Interfaces:**
- Consumes: The complete 71-Skill branch.
- Produces: A pushed branch and passing Draft PR checks.

- [ ] **Step 1: Run full validation**

Run:

```powershell
python scripts/validate-skills.py

$env:PYTHONUTF8 = "1"
$validator = "$SKILL_CREATOR_ROOT\scripts\quick_validate.py"
$failures = @()
Get-ChildItem -LiteralPath "skills" -Directory | ForEach-Object {
    $output = & python $validator $_.FullName 2>&1
    if ($LASTEXITCODE -ne 0) {
        $failures += "$($_.Name): $($output -join ' ')"
    }
}
if ($failures.Count) {
    $failures
    exit 1
}
"quick_validate.py passed for 71 skills."

git diff --check
```

Expected:

- Repository validator: `Validated 71 skills.`
- Codex validator: `quick_validate.py passed for 71 skills.`
- Diff check exits 0.

- [ ] **Step 2: Scan for leaked credentials**

Run:

```powershell
$matches = rg -n --hidden -S `
  "gh[opusr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY" `
  -g "!**/.git/**" .
if ($LASTEXITCODE -eq 0) {
    $matches
    exit 1
}
if ($LASTEXITCODE -ne 1) {
    exit $LASTEXITCODE
}
"No token or private-key signatures found."
```

Expected: `No token or private-key signatures found.`

- [ ] **Step 3: Confirm repository state**

Run:

```bash
git status -sb
git log -5 --oneline --decorate
```

Expected:

- Only intentional commits are present.
- Working tree is clean.
- Branch remains `agent/add-cross-agent-skills`.

- [ ] **Step 4: Push the existing branch**

```bash
git push
```

Expected: `agent/add-cross-agent-skills` updates on `origin`.

- [ ] **Step 5: Update Draft PR #3**

Update the PR body to mention:

- adaptive `handoff` Skill;
- reference Gist and MIT attribution;
- Codex direct-task and ChatGPT fallback behavior;
- 71/71 validation;
- three forward-test results.

Keep the existing base branch:

```text
claude/skillopt-explanation-d5gpqy
```

- [ ] **Step 6: Verify GitHub Actions**

Run:

```bash
gh pr checks 3 --repo kazu02210679/skills
```

Expected: all `validate` checks pass.
