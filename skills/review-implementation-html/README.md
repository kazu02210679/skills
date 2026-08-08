# Review Implementation HTML

通常の変更は同一セッション内で plan-blind → plan-aware の順に直列レビューします。
20ファイル以上、変更行合計1,000以上、または認証・権限・秘密情報・コマンド実行・
破壊的変更・署名/リリース・安全ポリシーに触れる変更だけを分離レビューへ切り替えます。

完成した実装をplan-blindとplan-awareの2段階でreviewし、コメント可能なローカルHTML reportへまとめるSkillです。差分を意図とriskで整理し、修正promptも生成します。

## 使う場面

- 実装差分を視覚的に説明・reviewしたい
- planから見た不足と、planに引きずられない不具合を分けたい
- review結果を後続のPR作成へ渡したい

## 入力と出力

- 入力: 承認済みplan、明示したbase/head、repository evidence
- 出力: `docs/reviews/<plan-slug>/` のHTML、review data JSON、修正prompt

## 制約

product codeは変更せず、review artifactだけを書きます。planがない場合は確認を取り、plan-blindのみの不完全reportとして明示します。

## 実装資材

- `references/review-model.md`: findingとreportの契約
- `scripts/collect_review_context.py`: bounded evidence収集
- `scripts/validate_review_report.py`: JSON検証
- `scripts/build_review_html.py`: HTML生成
