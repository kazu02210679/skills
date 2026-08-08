# GPT Pro Codex Loop

## GPT-5.6 Sol Pro の確認

`PRO_CLASS` は単一のモデル名 `Pro` を探しません。ChatGPT画面で、契約プランが `Pro`・`Business`・`Enterprise` のいずれか、モデル系統が `GPT-5.6 Sol`、推論レベルが `Pro` であることを別々に確認します。`非常に高い`（`Extra High` / `Very High`）はPro推論ではないため拒否します。

旧controllerのrunは、会話未固定なら次の通常遷移で新しいモデル証明stateへ更新されます。すでに会話固定済み、またはモデル証明が部分的な旧stateは推測移行せず、`LEGACY_STATE_RESTART_REQUIRED` で停止します。旧runを保持したまま、新しいtask slugで再開始してください。

Codex Desktop から、ChatGPT Pro に要件定義と反復的な意味レビューを担当させ、Codex がリポジトリ調査・詳細設計・実装・テスト・ローカル検証を担当する独立 Skill です。`codex-orchestration` には依存しません。

ユーザーが「ChatGPT Pro で要件を定義または固定し、Codex の実装を合格まで反復レビューする」組み合わせを明示的に依頼した場合だけ使います。要件相談だけ、単発レビュー、通常の実装では起動しません。

Codex Desktop の Browser、サインイン済みの ChatGPT Pro、同一会話の固定、厳格な JSON envelope、正規化 snapshot、ローカル検証が必要です。Pro の `PASS` だけでは完了しません。

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
