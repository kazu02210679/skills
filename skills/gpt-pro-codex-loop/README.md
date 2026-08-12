# GPT Pro Codex Loop

## Governance receipt export

Authoritative requirements-freeze, accepted-review, and successful
`final-verify` transactions publish canonical immutable receipt artifacts.
Use the read-only `export-governance-receipt --type requirements|review|final`
command to export and revalidate the persisted bytes. Repeated export is
byte-stable and does not read the clock or modify the run.

Requirements receipt history is append-only under
`governance-receipt-history/`; the fixed receipt filename is the current export
copy. Export rejects noncanonical requirements bytes, missing or altered
history, orphan transactions, and artifacts that change between stability
reads. Complete nonempty conversation/model/reasoning/plan provenance is
required to issue a receipt; standalone transitions without it remain valid
but have nothing to export.

The requirements receipt's `output_digest` is the semantic GPT Pro transition
output (`active_requirements_digest`). Its `requirements_digest` is instead the
SHA-256 digest of the exact canonical persisted `requirements.json` bytes,
including the terminal LF. HOTL can initialize from that exact artifact while
retaining its closed list of typed requirement IDs.

For an explicit HOTL-bound run, initialize GPT with the exact deterministic HOTL governance-context artifact; it binds execution, policy, authority, snapshot, nonce, and digest but grants no authority. Exported receipts are audit evidence only until a caller-independent provider admits them; without one, HOTL G1/G4 remain closed. Receipt export does not authorize commits, pushes, pull requests,
deployments, requirements changes, or other external actions. Standalone use
of the GPT Pro controller remains unchanged.

## GPT-5.6 Sol / Pro attestation

`PRO_CLASS` は、Codex内ブラウザのChatGPT画面で独立したUIフィールドを確認します。モデル欄は正確に `GPT-5.6 Sol`、推論の強さ欄は正確に `Pro`、プラン欄は `Pro`・`Business`・`Enterprise` のいずれかでなければなりません。モデルの identity と reasoning strength は別の次元です。旧契約の `GPT-5.6 Pro`、`Sol` + `High`、`Extra High`、`Very High`、`非常に高い`、空白・大文字小文字違い・ローカライズ表記・許可外プランは拒否します。

旧controllerのrunは、会話未固定でURL・モデル・推論・プランがすべてnullなら、coherentなv3またはv2（または旧形式の未束縛state）を次の通常遷移でv4/nullへ更新します。すでに会話固定済み、v3/v2の一部だけが残るstate、またはモデル証明が部分的・不正な旧stateは推測移行せず、`LEGACY_STATE_RESTART_REQUIRED` で停止します。requirements/review/finalのreceipt exportも同じ読み取り専用分類を適用します。旧runを保持したまま、新しいtask slugで再開始してください。
In explicit composition mode, a Luna-Max sub-agent handles one bounded
read-only routine review before the final Pro review. Sol is reserved for one
bounded read-only high-impact consultation when escalation evidence warrants
it; it never replaces the final Pro gate.

このSkillは、Codex DesktopのBrowser経由でChatGPT Proに要件・Acceptance
Criteria・semantic reviewを担当させ、Codexが実装とlocal verificationを担当する
外側のプロトコルです。

## Proの使用量を抑える既定

新規runは `FINAL_ONLY` が既定です。通常の1 runでProを使うのは、要件・計画の
固定時と、Codexが実装・local verificationを終えた後の最終semantic reviewの
2回だけです。最終reviewが `CHANGES_REQUESTED` または `BLOCK` になった場合は
controllerが停止し、Proへの自動再レビューは行いません。

反復レビューが本当に必要で、Proの使用量を受け入れる場合だけ
`--review-policy ITERATIVE` を明示します。通常のdiff review・テスト結果の確認・
local verificationはCodexが担当し、明示的なcomposition modeではLuna-Max sub-agentを
最終Pro review前のbounded read-only routine reviewに使います。Solは高影響な
read-only consultationに限定し、完了判定
やProの最終gateを代替しません。

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
