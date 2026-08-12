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
7. controller は LLM を呼ばず、自由文を意味解釈せず、同じ event log から常に同じ state、projection、transition 判定を得る。

## 非対象

- commit、push、pull request、deploy の自動実行
- 破壊操作や外部操作の自動承認
- Graph DB、Web UI、汎用 agent runtime
- SkillOpt による Skill の自動更新
- 既存 Skill の全面的な書き換え
- repository への write 権限を持つ悪意ある主体に対する暗号学的な改ざん防止

## Activation Policy

`hotl-governance` は、次のいずれかを満たす場合だけ起動する。

1. ユーザーが HOTL または governed execution を明示的に要求する。
2. outer controller が schema と binding を検証可能な governance context を渡す。

通常の `gpt-pro-codex-loop`、Sol Advisor、その他の standalone Skill を暗黙に wrap しない。無効または不完全な governance context は、暗黙起動の根拠にせず拒否する。

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
- LLM を呼ばず、自由文の同義性、finding の類似性、root cause の意味を推測しない。
- closed enum、stable ID、digest、sequence、明示された policy だけを判定に使う。

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

### State

正式な state set は次のとおりとする。

```text
INIT
  -> REQUIREMENTS
  -> IMPLEMENT
  -> LOCAL_VERIFY
  -> SEMANTIC_REVIEW
  -> COMPLETE

from INIT, REQUIREMENTS, IMPLEMENT, LOCAL_VERIFY, SEMANTIC_REVIEW:
  -> ESCALATED
  -> RECOVERY_REQUIRED
  -> STOPPED

SEMANTIC_REVIEW
  -> IMPLEMENT
```

`COMPLETE`、`ESCALATED`、`RECOVERY_REQUIRED`、`STOPPED` は同一 execution では terminal state とする。`SEMANTIC_REVIEW -> IMPLEMENT` だけが corrective edge である。

### Immutable execution boundary

scope、policy、authority snapshot、frozen requirements のいずれかを変更する場合、同一 execution の artifact を書き換えて再開してはならない。

```text
EXEC-001 -> ESCALATED
human approves a material change
EXEC-001 remains terminal
EXEC-002 starts with revised artifacts
REQ-v2 --supersedes--> REQ-v1
```

人間の承認は frozen artifact の上書き権ではない。変更を承認した場合は successor execution を作り、前 execution、承認 receipt、supersedes relation を参照する。

successor `init` は `predecessor_execution_id` と `lineage_receipt_digest` を必須とし、旧 execution が terminal state であることを検証する。

### Escalation

review failure は、G2 を再評価する `IMPLEMENT` への corrective edge を開ける。次の条件では corrective edge を開かず `ESCALATED` に移る。

- scope、authority、または frozen requirements の変更が必要
- 外部操作、破壊操作、機密情報、または新しいユーザー権限が必要
- 証拠または identity が矛盾
- receipt が同じ `finding_id` または `root_cause_id` を unresolved として二回連続で示す
- 三回の valid review round を消費

controller は finding の自由文を比較しない。`finding_id` と `root_cause_id` は semantic review receipt の必須 stable ID とする。

### Transition table

| From | Condition | To |
|---|---|---|
| none | `init` input、policy snapshot、execution identity が有効 | `INIT` |
| `INIT` | 初期 artifact publication が成功 | `REQUIREMENTS` |
| `REQUIREMENTS` | G1 `requirements_frozen` | `IMPLEMENT` |
| `IMPLEMENT` | G2 `implementation_recorded` | `LOCAL_VERIFY` |
| `LOCAL_VERIFY` | G3 `local_verified` | `SEMANTIC_REVIEW` |
| `SEMANTIC_REVIEW` | correctable findings、retry budget内 | `IMPLEMENT` |
| `SEMANTIC_REVIEW` | G4 `semantically_accepted` | `COMPLETE` |
| mutable state | escalation condition | `ESCALATED` |
| mutable state | transactionまたはintegrity ambiguity | `RECOVERY_REQUIRED` |
| mutable state | trusted operatorの明示停止 | `STOPPED` |

表にない transition はすべて拒否する。

### Gate

#### G1: requirements_frozen

必要証拠:

- requirement IDs
- acceptance criteria
- scope digest
- user approval receipt
- GPT Pro packet identity と model attestation
- authority snapshot digest

#### G2: implementation_recorded

必要証拠:

- change manifest
- requirement-to-code links
- worker report
- base state または snapshot identity
- implementation receipt の `execution_id`、`input_digest`、`output_digest`

#### G3: local_verified

必要証拠:

- exact verification commands
- exit status
- artifact path と SHA-256
- requirement-to-test links
- repository diff または snapshot digest
- evidence が current active snapshot に bind されていること

#### G4: semantically_accepted

必要証拠:

- GPT Pro semantic review receipt
- combined mode で bounded consultation を実施した場合の Sol advice receipt と Codex disposition。相談しなかった場合は、その事実と理由を示す no-consultation event
- 全 active requirement が typed completion predicate を満たすこと
- 未解決 finding がないこと
- accepted review の `input_digest` が current evidence set digest と一致すること

`COMPLETE` は G4 通過後だけ許可する。`gpt-pro-codex-loop` を outer protocol にした run は、同 controller の `final-verify` 成功も必要とする。

## Determinism

controller は外部 Skill が発行した構造化 receipt を検証するだけであり、review 本文の意味を解釈しない。transition 判定へ使える入力は、closed schema の値、stable ID、canonical digest、sequence、active status、policy snapshot に限定する。

```text
same policy snapshot + same ordered event log
  -> same execution state
  -> same provenance projection
  -> same allowed next commands
```

timestamp、表示順、自然言語の表現差は replay と transition 判定に使わない。

## Event Log

### 正本

JSONL event を append-only の正本とする。projection や status file を手編集可能な正本にしない。event は次の最小 envelope を持つ。

```json
{
  "schema_version": 1,
  "event_id": "EVT-...",
  "execution_id": "EXEC-...",
  "sequence": 17,
  "type": "test_verified",
  "payload": {"closed_fields_depend_on_type": true},
  "issuer": {"kind": "tool", "id": "pytest", "version": "..."},
  "subject_ids": ["REQ-017", "TEST-042"],
  "artifact_refs": [{"path": "relative/path", "sha256": "..."}],
  "result": "pass",
  "input_digest": "...",
  "output_digest": "...",
  "previous_event_hash": "...",
  "timestamp": "..."
}
```

順序は `execution_id + sequence + previous_event_hash` で決める。timestamp は監査情報であり、ordering や transition に使用しない。

### Receipt binding

privileged event は generic `record` から作成できない。human approval、GPT Pro packet、Sol advice、completion、stop には専用 import command を使い、少なくとも次を検証する。

- `receipt_schema_version`
- `receipt_id`
- `issuer_skill` と `issuer_version`
- `execution_id`
- `transaction_id` または `invocation_id`
- `input_digest` と `output_digest`
- nonce
- authority snapshot digest
- `issued_at_unix`（整数。authoritative mutation 時に一度だけ確定し、再 export で現在時刻を読まない）

既存 `gpt-pro-codex-loop` の Browser identity、conversation identity、nonce、model attestation、snapshot、transaction を信頼の根として保持する。`hotl-governance` が独自認証へ置き換えない。

agentic mode では、worker が書き込めるローカル CLI operator assertion を human approval として扱わない。G1 の privileged approval は、既存 GPT Pro protocol が発行する bound user-approval receipt、または worker が書き込めない host/tool approval provenance のどちらかに限る。`trusted_local_operator` は明示的な offline/manual mode だけで許可し、その mode 自体を policy snapshot に bind する。`record --actor human` のような自己申告は全 mode で拒否する。

### 整合性

- ID は execution 内で一意とする。
- unknown node への edge、重複 ID、循環する `supersedes` を拒否する。
- artifact path は repository-relative canonical path とする。
- artifact は digest で参照し、大きな証拠本体を event に埋め込まない。
- event hash は canonical JSON bytes から計算する。
- `previous_event_hash` で chain を形成し、編集、削除、並べ替えを検出する。
- replay は同じ入力から同じ state と projection を生成する。

canonical JSON は UTF-8、object key の辞書順、余分な空白なし、LF、整数だけを許可する。float、NaN、Infinity、重複 key、BOM を拒否する。

path は `/` 区切りの POSIX 表記へ正規化する。absolute path、空 segment、`.`、`..`、NUL、repository 外へ解決される symlink または reparse point を拒否する。Windows では比較用 canonical identity と保存用 POSIX path を分離する。

### Threat model

hash chain が検出するのは accidental corruption、partial modification、truncation、並べ替え、naive tampering である。repository 全体へ write できる悪意ある主体が event を再生成・再hash する攻撃は防がない。external signed checkpoint、repository 外 secret、remote transparency log は初版の非対象とする。

## Provenance Graph

### Node

- requirement
- code
- test
- evidence
- review
- change
- command
- failure
- policy

### Edge

- implements
- verifies
- produces
- supports
- executes
- proves
- reviews
- included_in
- violates
- fixes
- derived_from
- supersedes

### Typed edge schema

初版で completion predicate に使用できる triple を次に限定する。

| Source node | Edge | Target node |
|---|---|---|
| code | `implements` | requirement |
| test | `verifies` | requirement |
| command | `executes` | test |
| command | `produces` | evidence |
| evidence | `proves` | test |
| evidence | `supports` | review |
| review | `reviews` | requirement |
| code | `included_in` | change |
| test | `included_in` | change |
| failure | `violates` | requirement |
| change | `fixes` | failure |
| evidence | `derived_from` | evidence |
| review | `derived_from` | review |
| change | `derived_from` | change |
| requirement | `supersedes` | requirement |
| policy | `supersedes` | policy |

表にない triple は拒否する。`derived_from` は監査用であり、completion coverage を単独では満たさない。

### Completion predicate

各 active requirement R について、次をすべて満たす場合だけ coverage を認める。

1. active code C が存在し、`C implements R` である。
2. active test T が存在し、`T verifies R` である。
3. command K が T を成功実行し、K が valid evidence E を生成し、`E proves T` であり、E が current active snapshot に bind されている。
4. accepted review V が存在し、`V reviews R` であり、V の `input_digest` が current evidence set digest と一致する。
5. active change M が存在し、C と T が M に `included_in` されている。

単なる reachability では completion を認めない。superseded node、invalidated evidence、過去 snapshot の evidence は current coverage に数えない。

## Evidence Lifecycle

event と receipt、command output などの immutable evidence artifact は `.hotl/evidence/<sha256>` に content-addressed で保存する。mutable repository file の過去 digest は historical observation であり、現在の file digest と一致し続ける必要はない。

`.hotl/` は予約済み controller metadata root とする。tracked または staged されている場合は hygiene gate を失敗させる。GPT Pro snapshot adapter は、予約状態と hygiene を検証した後だけ `.hotl/` を product snapshot から除外し、governance metadata による snapshot の自己汚染を防ぐ。

code、test、または active snapshot が変わった場合、`evidence_invalidated` event により関連 evidence の projection status を `historically_valid` へ移す。削除せず監査履歴に残すが、G3/G4 の current coverage には数えない。再検証で新しい `valid_current` evidence を生成する。

`verify-log` は次を別々に報告する。

- log integrity
- projection determinism
- immutable evidence artifact integrity
- current active snapshot integrity
- historical mutable path observation

## CLI

初版は次の command を提供する。

- `init`: execution と policy snapshot を初期化する。
- `status`: 現在 state、満たされた gate、missing evidence、許可された次 command を表示する。
- `record`: closed event type と検証済み subject/artifact を追記する。
- `approve`: offline/manual policy mode でだけ trusted local operator に承認対象 digest を提示し、専用 approval receipt を生成する。agentic mode では bound GPT Pro または host/tool approval の import だけを許可する。
- `import-receipt`: GPT Pro、Sol Advisor、または検証 tool の receipt を issuer ごとの closed schema で検証して event に変換する。
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

`no-consultation` は closed `reason_code` を必須とする。

- `NOT_APPLICABLE`
- `NO_MATERIAL_UNCERTAINTY`
- `POLICY_NOT_REQUIRED`
- `ADVISOR_UNAVAILABLE`

`ADVISOR_UNAVAILABLE` を許容できるのは、Sol consultation を runtime dependency にしない standalone HOTL policy だけである。`orchestrate-gpt-pro-sol-advisor` combined mode では既存 contract を優先し、advisor preflight、invocation、attestation の失敗は hard stop とする。runtime で暗黙に緩和しない。

## Error Handling

- schema error、identity mismatch、digest mismatch、unknown transition は安定した error code を返す。
- partial transaction、lock ambiguity、hash-chain corruption は recovery-required とし、通常 mutation を停止する。
- recovery 状態では read-only status と検証だけを許可する。
- 既存 artifact を自動削除、修復、改名しない。
- adapter receipt が不正な場合、その本文を判断材料にせず停止する。

v1 は repair command を実装しない。`RECOVERY_REQUIRED` に入った execution は再開できない。operator が controller 外で artifact を保全・調査し、必要なら known-good source から復元した後、旧 execution を参照する successor execution を新規作成する。

## Testing

### Unit

- schema、ID、node、edge validation
- gate table と state transition
- retry と escalation
- canonical JSON と hash chain
- path canonicalization と artifact digest
- replay determinism
- privileged receipt spoof の拒否
- immutable execution boundary

### Transaction

- concurrent lock
- interrupted write
- atomic publication
- stale receipt と replay
- tamper detection
- recovery-required hard stop
- successor execution の lineage

### Adapter

- GPT Pro requirements/review/final receipt fixture
- Sol advice/attestation/disposition fixture
- malformed、mismatched、replayed receipt
- consultationなしの正常経路
- no-consultation reason policy
- stale snapshot evidence の invalidation

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
- `python scripts/context_budget_report.py --repo . --manifest context-budget-manifest.json --baseline context-budget-baseline.json --max-growth-bytes 0` を baseline 変更前に実行する。
- growth がある場合は file/byte 単位で内容を確認し、HOTL に必要な増加だけを明示承認して baseline を更新する。その後、同じ `--max-growth-bytes 0` command を再実行する。失敗だけを理由に baseline を更新しない。
- GPT Pro controller の `final-verify` が成功する。
- fresh repository diff inspection で対象外変更がない。

## Normative controller semantics

この節は event、projection、gate、adapter の実装契約を固定する。本文中の例と衝突する場合はこの節を優先する。

### Evidence plane と transition plane

`record` と `import-receipt` は検証済み evidence event を追記するだけで、execution state を変更しない。状態を進められるのは明示的な `evaluate` だけである。

```text
record / import-receipt
  -> evidence event append
  -> replay (state unchanged)
  -> evaluate Gx
  -> predicate PASS
  -> transition_committed append
  -> replay (state advanced)
```

FAIL は missing/invalid evidence を返し、`transition_committed` を作らない。Replay が状態を変更するのは schema-valid な `transition_committed` event を読む時だけであり、evidence event は直接遷移を起こさない。

### Closed payload と node identity

event envelope は必須の `payload` object を持ち、`type` ごとに必須 field、許可 field、型を closed schema で固定する。未知 field は拒否する。v1 の production event type は少なくとも `node_declared`、`edge_declared`、`snapshot_activated`、`evidence_recorded`、`evidence_invalidated`、`review_recorded`、`finding_recorded`、`receipt_imported`、`transition_committed` を含む。

| Prefix | Node type |
|---|---|
| `REQ-` | requirement |
| `CODE-` | code |
| `TEST-` | test |
| `CMD-` | command |
| `EVID-` | evidence |
| `REV-` | review |
| `CHG-` | change |
| `FAIL-` | failure |
| `POL-` | policy |

`transition_committed.payload` は `gate`、`from_state`、`to_state`、`evidence_set_digest`、`cycle_id` を必須とする。Projection は最低限、typed `nodes`、typed `edges`、`evidence_records`、`review_records`、`active_snapshot_digest`、`gate_evidence`、`finding_state`、`valid_review_rounds`、`cycle_id`、execution state を保持する。

### Canonical evidence set と review cycle

public contract function `evidence_set_digest(requirements_digest, snapshot_digest, evidence_records)` を定義する。canonical input は requirements digest、snapshot digest、そして `(evidence_id, artifact_digest, test_id)` で整列した current-cycle の valid evidence records である。自由文、timestamp、配列入力順は digest に含めない。

corrective edge または新 snapshot の activation は `cycle_id` を増やす。G2/G3/G4 の receipt と evidence は current cycle に bind し、旧 cycle の証拠を再利用しない。valid review round は schema、execution、current snapshot、current evidence-set binding が有効で semantic review が commit された review だけである。malformed/stale receipt は round を消費しない。同じ stable `root_cause_id` が連続する二つの valid failed review に現れるか、三回目の valid failed review に達した時点で `ESCALATED` へ遷移する。

### Atomic append と truncation witness

storage mutation primitive は `append_events(...)` とし、`append_event(...)` は一件用 wrapper とする。candidate log が旧 `events.jsonl` bytes を完全な prefix として保持し、event count が batch 件数だけ増えたことを publication 前に検証する。state witness に `event_count` と `head_event_hash` を永続化し、全 write 前と `verify-log` で照合する。snapshot activation と関連する全 `evidence_invalidated` は一つの atomic batch で追記する。

同じ terminal predecessor から複数 successor が分岐してよい。v1 は repository-global lineage registry を持たないため、predecessor の一回限り利用を要求しない。

### Adapter issuer と最終順序

Sol receipt の実 issuer は `skills/orchestrate-gpt-pro-sol-advisor/scripts/governance_receipt.py` とする。eval policy は production exporter を検証する側であり、eval-only 実装を正本にしない。`ADVISOR_UNAVAILABLE` は standalone policy では明示的に許容できるが、combined mode では receipt に downgrade せず hard stop とする。

combined outer protocol の G4 は次の順序を固定する。

1. requirements、review、必要な Sol receipt を import する。
2. GPT Pro controller の `final-verify` を実行する。
3. GPT Pro final governance receipt を export する。
4. final receipt を HOTL に import する。
5. G4 を `evaluate` し、`transition_committed` により `COMPLETE` へ進める。
6. `verify-log` で event chain、witness、projection、artifact integrity を再検証する。

## Current implementation-session prerequisite

これは今回の実装セッションにだけ適用する前提であり、`hotl-governance` の runtime dependency ではない。

`orchestrate-gpt-pro-sol-advisor` combined mode の preflight が成功しなければ、GPT Pro controller を初期化しない。現在の Codex task で `get_setup_status`、`get_preferences`、`sol_advisor_advisor` が観測できない場合は、Sol Advisor setup と adapter installation を完了し、新しい Codex task を開始してから実装へ進む。
