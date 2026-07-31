# Agent Engineering Skills

This repository is the canonical catalog for ten independent reusable Skills.
The catalog is generated from each Skill's frontmatter; regenerate it with
`python scripts/generate-skill-catalog.py` after changing a description.

<!-- BEGIN SKILL CATALOG -->
| Skill | 説明 |
|---|---|
| [`claude-code-discord-bot`](skills/claude-code-discord-bot/README.md) | Set up a Discord bridge in front of Claude Code so the user can send instructions from Discord, receive progress and completion notifications, and approve or deny tool use from a phone. Use when the user asks to turn Claude Code into a Discord bot, drive Claude Code from Discord or a phone, get a Discord ping when Claude Code finishes or needs input, or add a human-in-the-loop approval channel for an agent running on their own machine. Does not apply to Slack or other chat platforms, to chat bots unrelated to Claude Code, or to hosting one bot for other people to share. |
| [`co-create-plan`](skills/co-create-plan/README.md) | Have Claude Code and OpenAI Codex jointly create an evidence-backed implementation plan as equal planning peers. Use when the user asks Claude and Codex to discuss, debate, challenge assumptions, reach consensus, or make a plan together; when a second-model planning review is wanted before implementation; or when a plan must be handed directly to the codex-orchestration workflow without rerunning specification phases. |
| [`codex-orchestration`](skills/codex-orchestration/README.md) | Delegate implementation from Claude Code to OpenAI Codex while Claude remains the requirements owner and acceptance reviewer. Use in Claude Code when the user asks to let Codex implement a sizeable change, have Claude direct and verify Codex, or continue a Codex run with targeted guidance after a blocker. In Codex, use only to inspect or maintain this orchestration workflow; do not recursively delegate to another Codex session unless the user explicitly requests it. |
| [`complexity-aware-execution`](skills/complexity-aware-execution/README.md) | Use for code edits, bug fixes, tests, repository exploration, and local configuration or build changes when the agent should right-size its effort. Apply Estimate / Execute / Expand: estimate task complexity and the minimum evidence needed, take the smallest reliable path, verify early, and expand investigation only when verification fails or evidence contradicts the hypothesis. Do not minimize exploration for security, authentication, permissions, secrets, destructive operations, production changes, broad refactors, or explicitly exhaustive audits. |
| [`create-project-map`](skills/create-project-map/README.md) | Create or update a living interactive project architecture map as architecture-map.html plus machine-readable architecture-map.json. Use after a plan or specification is approved, or when the user asks for a project map, architecture map, dependency map, implementation map, module map, system flow visualization, or reusable visual context for later agents. |
| [`gpt-pro-codex-loop`](skills/gpt-pro-codex-loop/README.md) | Use when the user explicitly asks Codex Desktop to use ChatGPT Pro through the Browser to define or freeze requirements and iteratively review a Codex implementation until both semantic and local verification gates pass. |
| [`handoff`](skills/handoff/README.md) | Create a safe, conversation-centered handoff to a fresh task, thread, session, or chat while preserving the original purpose, changes of direction, decisions, constraints, failed approaches, artifacts, unresolved work, and next action. Use when the user explicitly asks to hand off, transfer, continue in a new task, start fresh without losing context, or says phrases such as "引き継いで", "別セッションに移して", "新しいタスクにして", or "move this to a fresh chat"; if the user only remarks that the conversation is long or slow without asking to move it, recommend a handoff but do not create one. |
| [`open-pull-request`](skills/open-pull-request/README.md) | Use when a completed and verified local branch should be published as a pull request. Triggers on requests such as "PRを作って", "プルリクを出して", "open a pull request", "push this and open a PR", or when finished work must be shared for review. Does not apply when the implementation is unfinished, when tracked files have uncommitted changes, or when the current branch is the repository default branch. |
| [`review-implementation-html`](skills/review-implementation-html/README.md) | Review a completed implementation in separate plan-blind and plan-aware passes, group the diff by intent and risk, and generate a local interactive HTML report with persistent reviewer comments, JSON export, and a copyable correction prompt. Use after implementation when a user asks for an explained diff, visual code review, review screen, or HTML review artifact. |
| [`writing-style`](skills/writing-style/README.md) | Use when drafting or revising Japanese explanatory prose, technical articles, essays, or chapters; when accurate, information-dense writing feels flat, monotonous, mechanical, or difficult to keep reading; or when openings, paragraph rhythm, section transitions, lists, and conclusions need stylistic diagnosis. |
<!-- END SKILL CATALOG -->

## What this catalog contains

Each catalog entry has a canonical `skills/<name>/SKILL.md` and a concise
human-facing README. Install only the Skills needed for the host and project.
The portable `codex-orchestration` Skill contains the guarded runtime formerly
provided by a Claude Code plugin; no live legacy repository dependency remains.

PM Skills are external and are neither vendored nor cataloged here. Install an
individual PM Skill on demand from
[`phuryn/pm-skills`](https://github.com/phuryn/pm-skills), then keep it
separate from this canonical catalog.

## Install

| Host | Project location | User location |
|---|---|---|
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Codex | `.agents/skills/` | `~/.agents/skills/` |

On Windows, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-skills.ps1 `
  -Agent both -Scope user
```

On macOS or Linux, run:

```bash
./scripts/install-skills.sh --agent both --scope user
```

Use `-Scope project -ProjectRoot <path>` or `--scope project --project-root
<path>` for a project install. Add `-Force` or `--force` only when replacing an
existing installation is intended.

Read [host compatibility](docs/host-compatibility.md) before relying on a
host-specific behavior.

## Maintain a Skill

1. Update `skills/<skill-name>/SKILL.md` with only `name` and `description` in
   frontmatter.
2. Keep its README concise and add only necessary scripts, references, assets,
   or host metadata.
3. Add or update a focused evaluation when behavior changes.
4. Regenerate the catalog and run validation.

## Verify

```bash
python -m pip install -r requirements-validation.txt
python scripts/generate-skill-catalog.py --check
python scripts/validate-skills.py
python -m unittest discover -s tests -v
```

## Repository layout

```text
skills/       canonical Skills
evals/        Skill evaluations
scripts/      installation, catalog, and validation tools
docs/         compatibility and design records
third_party/  redistributed third-party artifacts and licenses
```
