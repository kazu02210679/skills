# GPT Pro + Sol Advisor composition

`gpt-pro-codex-loop` と Sol Advisor を、それぞれ単独利用できる状態を保ちながら明示的に併用するためのルーティング Skill です。

## 3つのモード

- GPT Pro 単独: `gpt-pro-codex-loop` だけを使い、Sol を起動しません。
- Sol 単独: Sol Advisor の通常フローだけを使い、GPT Pro ループを起動しません。
- 併用: ユーザーが `$orchestrate-gpt-pro-sol-advisor` または両者の併用を明示した場合だけ有効です。

## 併用前の必須確認

GPT Pro の初期化より先に Sol Advisor の setup status と preferences を確認します。setup が未完了・旧形式・破損なら Sol の setup だけを行い、そのタスクを終了します。adapter を導入または更新した後は、新しい Codex タスクで再開します。

新しいタスクではCodex runtimeから現在のworkspaceをcanonical pathに解決し、`get_preferences` が返す上流で検証済みのactive preferences objectについて、`client=codex` とworkspace identityの一致を要求します。workspace identityは双方をcanonicalizeして比較しますが、`profileKey` は別runtimeのcanonical pathから再生成せず、上流が保存したraw `preferences.workspace` を使った `codex:<scope>:<raw preferences.workspace>` と厳密比較します。別client・別workspace・不一致のprofileは使用しません。併用設定の助言ロールは `sol_advisor_advisor` だけです。旧互換のTerra / Sol reviewerへ自動フォールバックしません。

Solを起動した後、助言を読む・採否判断する前に、まずpublic native spawn/details metadataを確認し、そこに実際の `sol_advisor_advisor` roleが含まれることを必須とします。public detailsがrole以外のmodel、reasoning effort、sandbox mode、permission profileを省略した場合だけ、インストール済みSol Advisor packageの `scripts/inspect-agent-runtime.sh` をskill-relative pathから解決し、同じnative advisor thread IDに対して1回実行します。inspectorは一意のrolloutを読み、同じthreadを識別し、必要項目をすべて返し、public detailsと重複する値が一致しなければなりません。

各項目の出所を `public-native-details` または `local-runtime-inspector` として記録します。role/model/effortはbound profileと一致し、sandboxは厳密に `read-only` でなければなりません。permission profileはpreferencesに保存されないため一致比較やallowlist判定をせず、空でない観測値をそのまま監査記録へ残します。public role欠落、inspector失敗・曖昧・別thread・不正形式・競合、呼び出し失敗なら助言本文を下流へ渡さず破棄し、advisor再試行・role fallback・GPT Pro続行をせず併用モードを停止します。自己申告、caller-supplied Boolean、role manifest、要求設定は実行時attestationの代用になりません。

## 権限境界

- ChatGPT Pro: 凍結要件、受入基準、semantic review、外側のレビュー状態
- Codex: 調査、設計、実装、テスト、local verification、Sol 助言の採否
- Sol: Codex フェーズ内の限定された read-only 助言

併用モードから `sol-advisor:orchestration` は起動しません。これは単独利用時の architect・実装委譲・final Sol review を含むため、併用モードの権限モデルと競合するからです。`sol_advisor_routine`、`sol_advisor_high`、`sol_advisor_terra_implementer` などの実装ロールも助言用途には使いません。

Sol を呼ぶのは、具体的な技術質問、重大な不確実性またはリスク、判断価値が揃う commitment boundary だけです。Codex が助言を `accept` / `reject` / `partially accept` と理由付きで処理し、local verification 後に GPT Pro の semantic review へ戻します。

Pro の修正要求や実装変更のたびに Sol を繰り返しません。新しい証拠または技術的リスク質問が実質的に変わった場合だけ、停止条件付きで再相談します。完了を決めるのは Sol verdict ではなく、外側の controller の `final-verify` です。
