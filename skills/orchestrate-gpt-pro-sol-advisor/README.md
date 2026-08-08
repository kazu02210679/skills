# GPT Pro + Sol Advisor composition

`gpt-pro-codex-loop` と Sol Advisor を、互いの単独利用を壊さずに併用するための薄いルーティングSkillです。

## 3つのモード

- GPT Pro単独: `gpt-pro-codex-loop`だけを使い、Solを起動しません。
- Sol単独: `sol-advisor:orchestration`だけを使い、GPT Proループを起動しません。
- 併用: ユーザーが明示的に `$orchestrate-gpt-pro-sol-advisor` または両者の併用を指定した場合だけ有効です。

併用時も、GPT Proループが凍結要件・承認・ChatGPT Proのsemantic reviewを担当し、Codexがリポジトリ調査・実装・テスト・local verificationを担当します。SolはCodex担当フェーズ内の任意の助言者であり、要件変更・承認・検証・最終判断を代替しません。

## Solを呼ぶ条件

具体的な技術質問があり、判断に影響する不確実性またはリスクがあり、同等の助言が未取得のときだけ、適切なレーンを1つ選びます。

- 実装・調査: `sol_advisor_terra_implementer`
- 技術・リスクレビュー: `sol_advisor_sol_reviewer`

渡す情報は、関連する凍結制約、確認済みのローカル証拠、選択肢、リスク、質問だけに限定します。Codexは助言を `accept`、`reject`、`partially accept` のいずれかで判断し、実装へ影響する場合は理由を残します。

## ループと失敗の扱い

Solを毎フェーズやPro review前の必須ゲートにはしません。両レーンの自動併用、再帰、SolからSolへの委任、同じ質問の繰り返しは禁止です。再相談は、重要な新証拠または質問の実質的変更と明示的な停止条件がある場合だけです。

Pluginまたは必要レーンが見つからない場合は依存関係エラーとして報告します。相談結果を捏造せず、ユーザーがモード変更を了承しない限り単独処理を併用処理と呼び替えません。

正しい例: 高リスクな移行方式についてTerraへ1回だけ相談し、Codexが助言を判断した後、通常のlocal verificationとGPT Pro semantic reviewへ戻る。

誤った例: 両方がインストール済みという理由だけで併用モードに入り、全変更後にSolレビューを繰り返す。
