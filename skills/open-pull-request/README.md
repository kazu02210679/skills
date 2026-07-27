# Open Pull Request

完成・検証済みのローカルブランチを、根拠付きのPull Requestとして公開するSkillです。実装、修正、commitは行わず、検証済みの状態を変えずに公開します。

## 使う場面

- 「PRを作って」「pushしてPull Requestを出して」
- 完成したブランチをレビューへ渡したい
- planやHTML reviewの証跡をPR本文へ反映したい

## 入力と出力

- 入力: cleanな作業ツリー、default branch以外の完成ブランチ、検証結果
- 出力: pushされたbranchとPull Request

## 停止条件

未commitのtracked変更、失敗した検証、未解決review、base不明、default branch上の作業は既定で停止します。未完成状態を公開する場合は、その事実に対するユーザー承認が必要です。

## 実装資材

- `scripts/inspect_pr_context.py`: publish前のGit状態をJSONで収集
- `evals/open-pull-request/`: 行動評価ハーネス
