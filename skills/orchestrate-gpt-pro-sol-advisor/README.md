# GPT Pro + Sol Advisor composition

`gpt-pro-codex-loop` と Sol Advisor を、それぞれ単独利用できる状態を保ちながら明示的に併用するためのルーティング Skill です。

## 3つのモード

- GPT Pro 単独: `gpt-pro-codex-loop` だけを使い、Sol を起動しません。
- Sol 単独: Sol Advisor の通常フローだけを使い、GPT Pro ループを起動しません。
- 併用: ユーザーが `$orchestrate-gpt-pro-sol-advisor` または両者の併用を明示した場合だけ有効です。

## 併用前の必須確認

GPT Pro の初期化より先に Sol Advisor の setup status と preferences を確認します。setup が未完了・旧形式・破損なら Sol の setup だけを行い、そのタスクを終了します。adapter を導入または更新した後は、新しい Codex タスクで再開します。

新しいタスクでは、preferences が示す現在の client 用 advisor role が実際に見えることを確認します。Codex では通常 `sol_advisor_advisor` ですが、保存済み設定と観測結果を正とします。旧互換の Terra / Sol reviewer へ自動フォールバックしません。

## 権限境界

- ChatGPT Pro: 凍結要件、受入基準、semantic review、外側のレビュー状態
- Codex: 調査、設計、実装、テスト、local verification、Sol 助言の採否
- Sol: Codex フェーズ内の限定された read-only 助言

併用モードから `sol-advisor:orchestration` は起動しません。これは単独利用時の architect・実装委譲・final Sol review を含むため、併用モードの権限モデルと競合するからです。`sol_advisor_routine`、`sol_advisor_high`、`sol_advisor_terra_implementer` などの実装ロールも助言用途には使いません。

Sol を呼ぶのは、具体的な技術質問、重大な不確実性またはリスク、判断価値が揃う commitment boundary だけです。Codex が助言を `accept` / `reject` / `partially accept` と理由付きで処理し、local verification 後に GPT Pro の semantic review へ戻します。

Pro の修正要求や実装変更のたびに Sol を繰り返しません。新しい証拠または技術的リスク質問が実質的に変わった場合だけ、停止条件付きで再相談します。完了を決めるのは Sol verdict ではなく、外側の controller の `final-verify` です。
