# Agent Engineering Skills

Claude CodeとCodexで再利用する、独自Agent Skillの正本リポジトリです。

ここで管理するのは、自分で設計・評価・改善するSkillだけです。外部のPM Skill集は正本へ複製せず、必要な環境へ配布元から直接インストールします。旧 [`Codex-plugin-Claude-Code`](https://github.com/kazu02210679/Codex-plugin-Claude-Code) の中核も `codex-orchestration` として統合しました。

## Skill一覧

この表は各 `SKILL.md` のYAML frontmatterから生成します。説明を変えたときやSkillを追加したときは、表を手編集せず `python scripts/generate-skill-catalog.py` を実行してください。

<!-- BEGIN SKILL CATALOG -->
| Skill | 説明 |
|---|---|
| [`co-create-plan`](skills/co-create-plan/README.md) | Have Claude Code and OpenAI Codex jointly create an evidence-backed implementation plan as equal planning peers. Use when the user asks Claude and Codex to discuss, debate, challenge assumptions, reach consensus, or make a plan together; when a second-model planning review is wanted before implementation; or when a plan must be handed directly to the codex-orchestration workflow without rerunning specification phases. |
| [`codex-orchestration`](skills/codex-orchestration/README.md) | Delegate implementation from Claude Code to OpenAI Codex while Claude remains the requirements owner and acceptance reviewer. Use in Claude Code when the user asks to let Codex implement a sizeable change, have Claude direct and verify Codex, or continue a Codex run with targeted guidance after a blocker. In Codex, use only to inspect or maintain this orchestration workflow; do not recursively delegate to another Codex session unless the user explicitly requests it. |
| [`complexity-aware-execution`](skills/complexity-aware-execution/README.md) | Use for code edits, bug fixes, tests, repository exploration, and local configuration or build changes when the agent should right-size its effort. Apply Estimate / Execute / Expand: estimate task complexity and the minimum evidence needed, take the smallest reliable path, verify early, and expand investigation only when verification fails or evidence contradicts the hypothesis. Do not minimize exploration for security, authentication, permissions, secrets, destructive operations, production changes, broad refactors, or explicitly exhaustive audits. |
| [`create-project-map`](skills/create-project-map/README.md) | Create or update a living interactive project architecture map as architecture-map.html plus machine-readable architecture-map.json. Use after a plan or specification is approved, or when the user asks for a project map, architecture map, dependency map, implementation map, module map, system flow visualization, or reusable visual context for later agents. |
| [`handoff`](skills/handoff/README.md) | Create a safe, conversation-centered handoff to a fresh task, thread, session, or chat while preserving the original purpose, changes of direction, decisions, constraints, failed approaches, artifacts, unresolved work, and next action. Use when the user explicitly asks to hand off, transfer, continue in a new task, start fresh without losing context, or says phrases such as "引き継いで", "別セッションに移して", "新しいタスクにして", or "move this to a fresh chat"; if the user only remarks that the conversation is long or slow without asking to move it, recommend a handoff but do not create one. |
| [`open-pull-request`](skills/open-pull-request/README.md) | Use when a completed and verified local branch should be published as a pull request. Triggers on requests such as "PRを作って", "プルリクを出して", "open a pull request", "push this and open a PR", or when finished work must be shared for review. Does not apply when the implementation is unfinished, when tracked files have uncommitted changes, or when the current branch is the repository default branch. |
| [`review-implementation-html`](skills/review-implementation-html/README.md) | Review a completed implementation in separate plan-blind and plan-aware passes, group the diff by intent and risk, and generate a local interactive HTML report with persistent reviewer comments, JSON export, and a copyable correction prompt. Use after implementation when a user asks for an explained diff, visual code review, review screen, or HTML review artifact. |
| [`writing-style`](skills/writing-style/README.md) | Use when drafting or revising Japanese explanatory prose, technical articles, essays, or chapters; when accurate, information-dense writing feels flat, monotonous, mechanical, or difficult to keep reading; or when openings, paragraph rhythm, section transitions, lists, and conclusions need stylistic diagnosis. |
<!-- END SKILL CATALOG -->

## 使い方

このリポジトリでは `skills/<name>/SKILL.md` がAgent向けの実行仕様、同じディレクトリの `README.md` が人間向けの説明です。Skillを明示して使う場合は、Claude CodeまたはCodexで名前を指定します。

```text
$co-create-plan で、この実装の計画をClaude CodeとCodexに共同作成させて
$review-implementation-html で実装差分をレビューして
```

ホストごとの引数や実行方法には差があります。対応範囲は [ホスト互換性](docs/host-compatibility.md) を参照してください。

## インストール

| ホスト | プロジェクト用 | ユーザー用 |
|---|---|---|
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Codex | `.agents/skills/` | `~/.agents/skills/` |

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-skills.ps1 `
  -Agent both -Scope user
```

macOS / Linux:

```bash
./scripts/install-skills.sh --agent both --scope user
```

特定projectへ入れる場合は `-Scope project -ProjectRoot <path>` または `--scope project --project-root <path>` を使います。既存の管理対象Skillを置換する場合だけ `-Force` / `--force` を追加してください。インストール先は配布物であり、編集元ではありません。

## 新しいSkillを追加する

1. `skills/<skill-name>/SKILL.md` を作り、`name` と `description` をfrontmatterに置く。
2. 人間向けの目的、利用場面、入出力、制約を `skills/<skill-name>/README.md` に書く。
3. 必要な場合だけ `scripts/`、`references/`、`assets/`、`agents/openai.yaml`、`evals/<skill-name>/` を追加する。
4. `python scripts/generate-skill-catalog.py` でこの一覧を更新する。
5. validator、focused test、全testを実行する。

Skillは原則として1件1PRに分けます。

## 品質管理

```bash
python -m pip install -r requirements-validation.txt
python scripts/generate-skill-catalog.py --check
python scripts/validate-skills.py
python -m unittest discover -s tests -v
```

`SKILL.md` はAgentの正本、各 `README.md` とこのcatalogは利用者向けの入口です。実行仕様を変えた場合は、該当Skillの評価またはfocused testも更新します。

## SkillOpt

SkillOptはSkillそのものではなく、既存Skillの改善候補を作る品質管理ツールです。このリポジトリへ本体をvendorせず、`requirements.txt` でversionを固定します。

採用は自動化しません。機械判定できる評価を持つSkillだけを候補にし、複数回の検証で既存版を上回った変更を人間が確認して採用します。仕組み、適用条件、運用ルールは [SkillOptによる品質管理](docs/skillopt/README.md)、設定手順は [SKILLOPT-SLEEP.md](SKILLOPT-SLEEP.md) を参照してください。

## ディレクトリ

```text
skills/                 # 独自Skillの正本
evals/                  # Skillごとの行動評価
scripts/                # install、catalog生成、検証
docs/                   # 運用・互換性・設計資料
third_party/            # 実際に収録する第三者由来資産のライセンス
```

## 外部Skillとライセンス

68件の [`phuryn/pm-skills`](https://github.com/phuryn/pm-skills) はこの正本から外しました。必要になったSkillだけを、その都度、元の配布プラグインからインストールしてください。

`handoff` は [`tegnike` のCodex Session Handoff Skill](https://gist.github.com/tegnike/09dbb98711d8b91e66de21611f5b88ff) を基にしています。MIT license、出典、固定hashは `third_party/handoff-gist/` に保持しています。
