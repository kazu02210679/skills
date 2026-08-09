# GPT Pro Codex Loop

## Governance receipt export

Authoritative requirements-freeze, accepted-review, and successful
`final-verify` transactions publish canonical immutable receipt artifacts.
Use the read-only `export-governance-receipt --type requirements|review|final`
command to export and revalidate the persisted bytes. Repeated export is
byte-stable and does not read the clock or modify the run.

Requirements receipt history is append-only under
`governance-receipt-history/`; the fixed receipt filename is the current export
copy. Export rejects noncanonical requirements bytes, missing or altered
history, orphan transactions, and artifacts that change between stability
reads. Complete nonempty conversation/model/reasoning/plan provenance is
required to issue a receipt; standalone transitions without it remain valid
but have nothing to export.

The requirements receipt's `output_digest` is the semantic GPT Pro transition
output (`active_requirements_digest`). Its `requirements_digest` is instead the
SHA-256 digest of the exact canonical persisted `requirements.json` bytes,
including the terminal LF. HOTL can initialize from that exact artifact while
retaining its closed list of typed requirement IDs.

For an explicit HOTL-bound run, initialize GPT with the exact deterministic HOTL governance-context artifact; it binds execution, policy, authority, snapshot, nonce, and digest but grants no authority. The accepted requirements receipt is the GPT-bound G1 approval boundary. Preserve this completion ordering:
`final-verify` -> export the final receipt -> import the receipt into HOTL ->
evaluate G4. Receipt export does not authorize commits, pushes, pull requests,
deployments, requirements changes, or other external actions. Standalone use
of the GPT Pro controller remains unchanged.

## GPT-5.6 Sol Pro の確認

`PRO_CLASS` は単一のモデル名 `Pro` を探しません。ChatGPT画面で、契約プランが `Pro`・`Business`・`Enterprise` のいずれか、モデル系統が `GPT-5.6 Sol`、推論レベルが `Pro` であることを別々に確認します。`非常に高い`（`Extra High` / `Very High`）はPro推論ではないため拒否します。

旧controllerのrunは、会話未固定なら次の通常遷移で新しいモデル証明stateへ更新されます。すでに会話固定済み、またはモデル証明が部分的な旧stateは推測移行せず、`LEGACY_STATE_RESTART_REQUIRED` で停止します。旧runを保持したまま、新しいtask slugで再開始してください。

Codex Desktop から、ChatGPT Pro に要件定義と反復的な意味レビューを担当させ、Codex がリポジトリ調査・詳細設計・実装・テスト・ローカル検証を担当する独立 Skill です。`codex-orchestration` には依存しません。

ユーザーが「ChatGPT Pro で要件を定義または固定し、Codex の実装を合格まで反復レビューする」組み合わせを明示的に依頼した場合だけ使います。要件相談だけ、単発レビュー、通常の実装では起動しません。

Codex Desktop の Browser、サインイン済みの ChatGPT Pro、同一会話の固定、厳格な JSON envelope、正規化 snapshot、ローカル検証が必要です。Pro の `PASS` だけでは完了しません。

## Pro応答の待機方針

このSkillは品質優先です。Proが同じターンで正常に推論・生成中なら、経過時間だけを理由に `今すぐ回答`（`Answer now`）を押したり、生成停止・再生成・再送信・モデル切替を行ったりしません。Browser操作のタイムアウト時は同じ会話とターンを再確認し、完了または明示的な生成エラーまで待機します。

`今すぐ回答` を使えるのは、現在のユーザーがそのターンについて推論の深さより速度を優先すると直接明示した場合だけです。許可は使用可能という意味であり、使用必須ではありません。締切、経過時間、関係者からの要望、Codex自身の判断をユーザー許可として推測しません。送信状態が曖昧、会話を再取得できない、または明示的な生成エラーがある場合は、推測で介入せず復旧・停止ルールに従います。

## 初期化

既存ファイルがある通常のリポジトリでは、まず run state を作らずに対象パスを manifest へ出力します。manifest は対象リポジトリの外に置いてください。

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py inspect-init --repo REPOSITORY --task TASK --write-approval-manifest ..\REPOSITORY-TASK-approved-existing-paths.json
```

manifest の全パスを確認して明示的な承認を得た後、その同じ manifest を `init` に渡します。生成しただけでは承認になりません。

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py init --repo REPOSITORY --task TASK --request REQUEST.md --repository-context CONTEXT.md --model-policy PRO_CLASS --approved-existing-path-manifest ..\REPOSITORY-TASK-approved-existing-paths.json
```

少数なら従来どおり `--approved-existing-path PATH` を繰り返せます。両方式の併用はエラーです。`init` はロック下で再検査するため、生成後にパス集合が変わった manifest、別リポジトリ・別タスク用、重複・絶対・親参照などを含む manifest は state 公開前に拒否されます。

未承認パスのエラーは最大20件の preview、総数、省略数、集合 digest、manifest 生成と再実行に使える JSON argv を返します。数百件をエラー本文へ列挙しません。

## 中断からの復旧

`status` が `INIT_INCOMPLETE` と `init --retry-incomplete` を返した場合だけ、元の入力と承認をすべて付けて明示的に再実行できます。

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py init --repo REPOSITORY --task TASK --retry-incomplete --request REQUEST.md --repository-context CONTEXT.md --model-policy PRO_CLASS --approved-existing-path-manifest ..\REPOSITORY-TASK-approved-existing-paths.json
```

生きたロック、`state.json` がある run、壊れた state、想定外ファイル、リンク／reparse point、所有権が曖昧な状態は変更せず拒否します。確立済み run や orphan transaction の自動修復は行いません。真に存在しないタスクの `status` は従来どおり `RUN_NOT_FOUND` です。
