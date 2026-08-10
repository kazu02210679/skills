# GPT Pro + Sol Advisor composition

`gpt-pro-codex-loop`とSol Advisorを、権限を混ぜずに同じCodex taskで使うための
composition Skillです。`$orchestrate-gpt-pro-sol-advisor`または両者の併用を
明示的に求めた場合だけ有効になります。

## 責務

- GPT Pro: 要件、Acceptance Criteria、material-change approval、semantic review、外側のgate
- Codex Primary: repo調査、設計、task packet、worker routing、diff、tests、local verification、最終判断
- Luna / Max: bounded implementationのデフォルト（`gpt-5.6-luna` / `max`）
- Terra / High: 難しい・詰まった実装の救援（`sol_advisor_terra_implementer`）
- Sol Advisor: Terraでも解けない高影響な設計・安全性・リスク判断へのread-only助言

Solは実装workerでも完了判定者でもありません。助言はCodex Primaryが
`accept`、`reject`、`partially accept`のいずれかに処理します。

## 実装ルート

```text
GPT Pro → Codex Primary → Luna / Max
                         ↓ focused verification + diff inspection
               difficult/stuck? → Terra / High
                         ↓ still blocked on high-impact decision?
                       Sol read-only advice
                         ↓ primary verification → Pro → final-verify
```

Lunaは1 taskを粗くboundedにし、並列は原則2件までです。Lunaが同じroot causeで
もう一度失敗した場合、またはconcurrency、security、migration、shared state、
統合、性能、広い波及範囲がある場合だけTerraへ昇格します。Solへの自動昇格や
Solによる実装は行いません。

詳細なtask identity・runtime capability preflight・Terra attestationは
[references/luna-implementation-lane.md](references/luna-implementation-lane.md)、
テスト増殖抑制・verification fingerprint・local evidenceのcompact契約は
[references/verification-economy.md](references/verification-economy.md)を参照してください。

## Test Economy

- 新規testはAcceptance Criterion、material risk、bug root causeのいずれかに紐付ける
- `new_test_files = 0`をデフォルトにする
- bug fixはroot causeごとに原則1 regression witness、同等入力はtable-drivenにまとめる
- privateな実装詳細ではなくobservable behavior/public contractを検証する
- L0 → L1を基本にし、共有API・依存・schema・shared coreだけL2/L3へ上げる
- 成功済みcommandの再実行は、commandと検証入力fingerprintが変わった場合だけ行う
- `--local-evidence`のclosed schemaを守り、metrics・test delta・fingerprintは`output_summary`にcompact化する

## モード境界

- GPT Pro単独: `gpt-pro-codex-loop`だけを使い、Solやworker routingは起動しない
- Sol Advisor単独: `sol-advisor:orchestration`だけを使い、このcompositionを起動しない
- combined: このSkillを明示的に選び、`sol-advisor:orchestration`をnested invocationしない

workerの結果は主タスクがdiff・scope・local evidenceを確認するまで受入れません。
commit、push、PR、deployment、権限変更、破壊的操作はworkerに委譲しません。
