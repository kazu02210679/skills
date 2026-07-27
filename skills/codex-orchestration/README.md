# Codex Orchestration

Claude Codeが要件と合格条件を決め、Codexへ実装を委譲し、最後にClaude Code自身が検証するためのSkillです。旧 `kazu02210679/Codex-plugin-Claude-Code` の中核を、共通Skillカタログへ移しました。

## 使う場面

- 「Codexに実装させて、Claudeで確認してほしい」
- 大きめの実装をタスクパケットで明確に委譲したい
- Codexが詰まった原因をClaudeが診断し、最小限のヒントで再開したい

## 入力と出力

- 入力: ユーザー要求、対象リポジトリ、検証可能な合格条件
- 出力: `.codex-instructions/` のタスクパケット、`.codex-runs/` の実行証跡、独立した合否判定

## 実行例

```bash
skills/codex-orchestration/scripts/codex_run.sh \
  .codex-instructions/add-export.md \
  /path/to/repository
```

## ホストと制約

主用途はClaude CodeからCodex CLIを呼ぶ運用です。Codex上では、再帰的なCodex委譲を避けるため暗黙起動を無効にしています。`danger-full-access` は隔離環境以外で使いません。

## 関連Skill

- `co-create-plan`: Claude CodeとCodexが対等に計画を作る
- `review-implementation-html`: 実装差分をHTMLでレビューする
- `open-pull-request`: 検証済みブランチをPRとして公開する

## 旧pluginからの移行

| 旧interface | このSkillでの置き換え |
|---|---|
| `/codex-spec` | `codex-orchestration` の境界定義とtask packet作成 |
| `/codex-run` | `scripts/codex_run.sh` |
| `/codex-accept` | `references/acceptance-review.md` による独立検証 |

Claude Code固有のmarketplace manifestとslash commandは正本にせず、portableな `SKILL.md` と同梱resourceをinterfaceにします。
