# GPT Pro + Sol Advisor composition

`gpt-pro-codex-loop` と Sol Advisor を、権限を混ぜずに併用するための
ルーティングSkillです。ユーザーが `$orchestrate-gpt-pro-sol-advisor` または
両者の併用を明示した場合だけ起動します。

## 役割

- GPT Pro: 要件、Acceptance Criteria、material-change approval、semantic review、最終ゲート。
- Codex Primary: repo調査、設計、タスク分解、worker選択、diff確認、テスト、local verification、最終判断。
- Luna / Max: デフォルト実装worker（`gpt-5.6-luna` / `max`）。
- Terra / High: Lunaで詰まった場合、または難しい実装の救援（`sol_advisor_terra_implementer`）。
- Sol Advisor: Terraでも解けない高影響の設計・安全性・リスク質問へのread-only助言。

Solは実装workerではありません。Solの助言はCodexが `accept`、`reject`、
`partially accept` のいずれかで判断し、完了判定や要件変更をSolに委譲しません。

## 実装ルーティング

併用時の標準経路は次のとおりです。

```text
GPT Pro / Sol Pro
  ↓ 要件・AC
Codex Primary
  ├─ Luna / Max: bounded implementation（標準）
  │    └─ focused verification
  ├─ Terra / High: difficult / stuck implementation
  └─ Sol Advisor: Terra後の高影響な設計判断だけ
       ↓
Codex Primary: 実diff・scope・verificationを再確認
       ↓
GPT Pro: semantic review → final-verify
```

Lunaはfeature、UI、CRUD、API wiring、boilerplate、既存patternに沿うrefactor、
test修正、仕様の固まったアルゴリズムなどを担当します。Lunaの結果が不十分な
場合は、同じtaskへ修正指示を1回だけ送り、同じroot causeで再度失敗したら
Terraへ昇格します。concurrency、security-sensitive code、migration、shared
state、難しいperformance bug、複数workstreamの統合、広い波及範囲もTerraです。

Luna taskは粗いまとまりで作り、原則2件まで並列にします。ファイル単位・テスト
単位の大量spawnや、Luna→Lunaの無限修正ループは禁止です。詳細な作成・監視・
昇格契約は [luna-implementation-lane.md](references/luna-implementation-lane.md) を参照してください。

## Test Economy

テストはcoverage最大化ではなく、Acceptance Criteriaを証明する最小verification
を目標にします。

- 新しいtestはAcceptance Criterion、material risk、bug root causeのいずれかに紐付ける。
- `new_test_files = 0` がデフォルト。既存fileで表現できない理由があるときだけ追加する。
- bug fixはroot causeごとに原則1 regression test。複数入力はtable-drivenにまとめる。
- private methodやcall countではなくobservable behavior/public contractをテストする。
- 検証はL0（diff/static）→L1（affected focused test、デフォルト）→L2（module）→L3（full suite）の段階制。
- 関連code/test/configが変わっていない、成功済みcommandは再実行しない。
- 成功時はcommand、exit code、test count、duration、1行要約だけを次のcontextへ渡す。失敗時だけ失敗名・関連excerpt・full log path/digestを残す。

## 単独利用

- GPT Pro単独: `gpt-pro-codex-loop`だけを使い、Solは起動しません。
- Sol単独: `sol-advisor:orchestration`だけを使い、GPT Pro loopやこのcompositionは起動しません。
- 曖昧な言及やインストール済みという事実だけでは併用にしません。

併用モードでも、`sol-advisor:orchestration`をnested invocationしません。設定済み
advisorのattestationに失敗した場合は相談結果を捨て、モデルやroleを黙って代替せず、
依存関係エラーとして停止します。
