# Co-create Plan

Claude CodeとCodexを対等な計画担当として対話させ、証拠付きの実装計画へ合意させるSkillです。片方を単なるreviewerにせず、技術的な結論へ同じ権限で参加させます。

## 使う場面

- Claude CodeとCodexで設計案を議論したい
- 実装前に別モデルから反証や代替案を得たい
- 合意済み計画を `codex-orchestration` へ直接渡したい

## 入力と出力

- 入力: ユーザー要求、対象リポジトリ、適用ルール、必要なコード証拠
- 出力: `.ai-planning/<task>/` の対話証跡と、必要に応じた `.codex-instructions/<task>.md`

## 制約

計画中にproduction codeは変更しません。最終計画は `references/plan-contract.md` の契約に従い、未解決の意見差も隠しません。

## 実装資材

- `scripts/planning_peer.py`: peer dialogueの実行と証跡管理
- `evals/co-create-plan/`: 境界と合意形成の評価
