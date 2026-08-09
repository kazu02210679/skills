# HOTL Governance Skill 設計

## 目的

`hotl-governance` を、既存 Skill の間にある未接続の遷移を閉じる governance layer として追加する。人間は目標、policy、risk、例外承認、停止権限を保持する。controller は証拠が揃った遷移だけを許可し、通常処理から人間を外しても統治可能な Human on the Loop（HOTL）運用を実現する。

初版では、次の二つを明示的に分離する。

- Execution Graph: 次に何を実行できるかを表す状態遷移。
- Specification Provenance Graph: 何を根拠に要求が成立しているかを表す証拠関係。

追記専用 event log を両 graph の共通正本にする。Graph DB や Web UI は導入しない。

## 成功条件

1. `hotl-governance` が決定論的な CLI controller を持つ。
2. 証拠不足、矛盾、改ざん、未承認の権限変更を fail closed で拒否する。
3. requirement から code、test、evidence、review、change までの provenance path を検証できる。
4. event replay から同じ execution state と provenance projection を再生成できる。
5. `gpt-pro-codex-loop` と Sol Advisor の既存安全契約および standalone 利用を壊さない。
6. trigger、non-trigger、controller、adapter、回帰の focused eval/test を持つ。

## 非対象

- commit、push、pull request、deploy の自動実行
- 破壊操作や外部操作の自動承認
- Graph DB、Web UI、汎用 agent runtime
- SkillOpt による Skill の自動更新
- 既存 Skill の全面的な書き換え

## アーキテクチャ

### 責務

#### Human on the Loop

- goal、policy、scope、risk budget を定義する。
- frozen requirements を承認する。
- scope または権限の変更、高リスク操作、回復不能な矛盾を判断する。
- controller を停止し、例外を承認または拒否する。

#### hotl-governance

- execution state machine を管理する。
- gate の必要証拠を closed schema で検証する。
- append-only event を lock と atomic replace で記録する。
- event replay から execution state と provenance graph を生成する。
- retry budget と escalation 条件を強制する。
- 外部 Skill の receipt を検証して正規化する。

#### GPT Pro Codex Loop

- frozen requirements、acceptance criteria、semantic review を所有する。
- Browser identity、model attestation、nonce、replay、recovery の既存契約を維持する。
- governance context を受け取り、accepted packet receipt を出力する。

#### Codex / Sol Advisor

- Codex は調査、設計、実装、テスト、ローカル evidence を所有する。
- combined mode の Sol は bounded read-only advice だけを提供する。
- Sol は要求、承認、completion、verification を代行しない。
- `orchestrate-gpt-pro-sol-advisor` を使う場合、GPT Pro controller を outer protocol とし、その preflight と role attestation を変更しない。

## Execution Graph

通常経路を次の状態で表す。

```text
INIT
  -> REQUIREMENTS
  -> IMPLEMENT
  -> LOCAL_VERIFY
  -> SEMANTIC_REVIEW
  -> COMPLETE
```

review failure は `IMPLEMENT` への corrective edge を開く。次の条件では corrective edge を開かず `ESCALATED` に移る。

- scope、authority、または frozen requirements の変更が必要
- 外部操作、破壊操作、機密情報、または新しいユーザー権限が必要
- 証拠または identity が矛盾
- 同じ unresolved finding または derived root cause が二回連続
- 三回の valid review round を消費
- controller が recovery-required 状態

### Gate

#### G1: requirements_frozen

必要証拠:

- requirement IDs
- acceptance criteria
- scope digest
- user approval receipt
- GPT Pro packet identity と model attestation

#### G2: implementation_recorded

必要証拠:

- change manifest
- requirement-to-code links
- worker report
- base state または snapshot identity

#### G3: local_verified

必要証拠:

- exact verification commands
- exit status
- artifact path と SHA-256
- requirement-to-test links
- repository diff または snapshot digest

#### G4: semantically_accepted

必要証拠:

- GPT Pro semantic review receipt
- combined mode で bounded consultation を実施した場合の Sol advice receipt と Codex disposition。相談しなかった場合は、その事実と理由を示す no-consultation event
- 全 requirement の有効な implements、verified_by、reviewed_by path
- 未解決 finding がないこと

`COMPLETE` は G4 通過後だけ許可する。`gpt-pro-codex-loop` を outer protocol にした run は、同 controller の `final-verify` 成功も必要とする。

## Event Log

### 正本

JSONL event を append-only の正本とする。projection や status file を手編集可能な正本にしない。event は次の最小 envelope を持つ。

```json
{
  "schema_version": 1,
  "event_id": "EVT-...",
  "execution_id": "EXEC-...",
  "type": "test_verified",
  "actor": {"kind": "tool", "id": "pytest"},
  "subject_ids": ["REQ-017", "TEST-042"],
  "artifact_refs": [{"path": "relative/path", "sha256": "..."}],
  "result": "pass",
  "previous_event_hash": "...",
  "timestamp": "..."
}
```

### 整合性

- ID は execution 内で一意とする。
- unknown node への edge、重複 ID、循環する `supersedes` を拒否する。
- artifact path は repository-relative canonical path とする。
- artifact は digest で参照し、大きな証拠本体を event に埋め込まない。
- event hash は canonical JSON bytes から計算する。
- `previous_event_hash` で chain を形成し、編集、削除、並べ替えを検出する。
- replay は同じ入力から同じ state と projection を生成する。

## Provenance Graph

### Node

- requirement
- decision
- code
- test
- evidence
- review
- change
- failure
- policy
- skill-version

### Edge

- implements
- verifies
- produces
- supports
- reviews
- included_in
- violates
- fixes
- derived_from
- supersedes

各 requirement は completion 時点で、現在有効な code、test、evidence、review、change へ到達できなければならない。superseded node または invalidated evidence を coverage に数えない。

## CLI

初版は次の command を提供する。

- `init`: execution と policy snapshot を初期化する。
- `status`: 現在 state、満たされた gate、missing evidence、許可された次 command を表示する。
- `record`: closed event type と検証済み subject/artifact を追記する。
- `import-receipt`: GPT Pro または Sol Advisor receipt を検証して event に変換する。
- `evaluate`: gate を評価し、許可された state transition だけを実行する。
- `project`: execution/provenance projection を再生成する。
- `verify-log`: schema、hash chain、artifact digest、replay determinism を検証する。

すべての mutation は lock を取得し、一時ファイルへの完全書き込み、fsync、atomic replace の順で公開する。`status`、`verify-log`、`project --stdout` は read-only とする。

## Adapter

### gpt-pro-codex-loop

既存 controller state を維持し、次の additive contract だけを加える。

- governance context input
- requirement、review、execution ID
- accepted requirements/review packet の digest 付き receipt
- completion receipt に `final-verify` identity を含める

Browser 制御、model attestation、conversation identity、nonce、snapshot、transaction、recovery contract は変更しない。

### orchestrate-gpt-pro-sol-advisor

既存 composition contract を維持する。

- outer protocol は `gpt-pro-codex-loop`
- observable role は configured `sol_advisor_advisor`
- advice は read-only、bounded、one-question
- trusted role/model/effort/sandbox/permission observations を receipt に含める
- Codex disposition は `accept`、`reject`、`partially accept`

Sol を mandatory final gate にしない。未実施の相談を捏造せず、相談が不要だった事実を明示的 event として記録できるようにする。

## Error Handling

- schema error、identity mismatch、digest mismatch、unknown transition は安定した error code を返す。
- partial transaction、lock ambiguity、hash-chain corruption は recovery-required とし、通常 mutation を停止する。
- recovery 状態では read-only status と検証だけを許可する。
- 既存 artifact を自動削除、修復、改名しない。
- adapter receipt が不正な場合、その本文を判断材料にせず停止する。

## Testing

### Unit

- schema、ID、node、edge validation
- gate table と state transition
- retry と escalation
- canonical JSON と hash chain
- path canonicalization と artifact digest
- replay determinism

### Transaction

- concurrent lock
- interrupted write
- atomic publication
- stale receipt と replay
- tamper detection
- recovery-required hard stop

### Adapter

- GPT Pro requirements/review/final receipt fixture
- Sol advice/attestation/disposition fixture
- malformed、mismatched、replayed receipt
- consultationなしの正常経路

### Regression と Eval

- `gpt-pro-codex-loop` standalone workflow の既存テスト
- `orchestrate-gpt-pro-sol-advisor` composition eval
- `hotl-governance` trigger と non-trigger eval
- incomplete provenance が completion を開かない end-to-end fixture
- full evidence chain が replay 後も completion を開く end-to-end fixture

## リポジトリ変更範囲

新規:

- `skills/hotl-governance/`
- `evals/hotl-governance/`
- focused tests

更新:

- `skills/gpt-pro-codex-loop/` の additive receipt 出力
- `skills/orchestrate-gpt-pro-sol-advisor/` の additive advice receipt
- 対応する eval、test、catalog

既存 controller の状態 schema を直接共有しない。adapter は versioned receipt を介し、各 Skill の transaction boundary を保つ。

## 受け入れ検証

- focused unit、transaction、adapter、eval が通る。
- `python scripts/validate-skills.py` が通る。
- `python scripts/generate-skill-catalog.py` 後に意図した catalog 差分だけが残る。
- `python scripts/context_budget_report.py --repo . --manifest context-budget-manifest.json --baseline context-budget-baseline.json --max-growth-bytes 0` が通る。意図的な model-visible 増加は別途レビューして baseline を更新する。
- GPT Pro controller の `final-verify` が成功する。
- fresh repository diff inspection で対象外変更がない。

## 実装開始前の前提

`orchestrate-gpt-pro-sol-advisor` combined mode の preflight が成功しなければ、GPT Pro controller を初期化しない。現在の Codex task で `get_setup_status`、`get_preferences`、`sol_advisor_advisor` が観測できない場合は、Sol Advisor setup と adapter installation を完了し、新しい Codex task を開始してから実装へ進む。
