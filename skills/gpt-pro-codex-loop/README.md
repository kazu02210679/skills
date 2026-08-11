# GPT Pro Codex Loop

このSkillは、Codex DesktopのBrowser経由でChatGPT Proに要件・Acceptance
Criteria・semantic reviewを担当させ、Codexが実装とlocal verificationを担当する
外側のプロトコルです。

## standaloneの責務

GPT Pro単独で使う場合、このSkillはLuna・Terra・Solやnative worker roleを
起動・選択しません。GPT ProとSol Advisorを明示的に組み合わせる場合だけ、
`orchestrate-gpt-pro-sol-advisor`を追加で使います。単独Skillが別モデルの
導入・実装・レビューまで引き受けることはありません。

## Test Economy

テストはcoverage最大化ではなく、Acceptance Criteriaを証明する最小のverification
witnessを目標にします。

- 新しいテストはAcceptance Criterion、material risk、bug root causeのいずれかに紐付ける。
- `new_test_files = 0`をデフォルトにし、既存ファイルで表現できない理由がある場合だけ追加する。
- bug fixはroot causeごとに原則1 regression witnessとし、同じ契約の入力はtable-drivenにまとめる。
- privateな実装詳細ではなく、observable behaviorやpublic contractをテストする。
- 検証はL0（diff/static）→L1（affected focused test）を基本とし、共有API・依存・schema等だけL2/L3へ上げる。
- 成功済みのverificationは、commandだけでなくbase/tree・関連file・lock/config・必要な環境を含むfingerprintが同じ場合にだけ再実行を省略する。

`--local-evidence`はclosed schemaです。`test_commands`の各要素は
`command`・`outcome`・`output_summary`だけを持ちます。exit code、test count、
duration、test delta、verification fingerprintはunknown fieldとして追加せず、
boundedな`output_summary`へcompact encodingします。

## Quality-first Browser

Browser上でProがreasoning中なら品質優先で同じturnを待ちます。`今すぐ回答`は
現ユーザーがそのturnで速度を優先すると明示した場合だけ許可し、経過時間だけでは
中断理由にしません。

通常のcontroller手順とBrowser上のPro attestationは、[SKILL.md](SKILL.md)と
`references/packet-contract.md`を参照してください。
