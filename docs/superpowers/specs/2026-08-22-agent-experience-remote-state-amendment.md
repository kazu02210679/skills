# Agent Experience Skill — Remote Repository State 追補設計

## 0. 文書の位置付け

本書は、次の設計書に対する**規範的な追補**である。

- `docs/superpowers/specs/2026-08-21-agent-experience-skill-design.md`

実装計画、実装、review、acceptance では、基礎設計書と本書を一つの設計契約として扱う。

競合する記述がある場合、本書は remote repository state に関して次の節を拡張または上書きする。

- 成功条件
- 設計原則
- アーキテクチャ
- Record kinds
- Codex lifecycle
- Checkpoint compatibility
- CLI contract
- Recall algorithm
- Failure and recovery
- Eval / Test 方針
- 実装段階
- 受け入れ条件

本書は `agent-experience` に remote repository の操作権限を与えない。対象は current state の**read-only observation、revalidation、差分判定**に限定する。

## 1. 追加する問題定義

local checkout だけでは、後続 agent が次を current fact として確定できない場合がある。

- Pull Request が open、closed、merged のどれか
- Issue が open、closed のどれか
- remote branch の current head SHA
- `main` または accepted branch に対象文書が存在するか
- review、check、approval、merge 条件が満たされたか
- accepted artifact として指定された SHA が current authoritative branch に存在するか
- 前回観測後に文書、branch、PR、Issue、check が変化したか

例えば、前回 session が次を確認していても、後続 session で同じ状態とは限らない。

```text
previous observation
  main に accepted design document は存在しない
  PR #12 は open
  PR #14 相当の改訂は未反映

later remote state
  PR #12 は merged
  main に対象文書が存在する
  accepted SHA が更新された
```

古い状態を正確に保存するだけでは不十分である。mutable remote state は、利用前に再検証しなければならない。

## 2. 状態と方針を分離する

次を異なる record として扱う。

```text
Policy / Decision
  「accepted 状態で authoritative branch に存在する文書だけを正式仕様とする」

Remote Observation
  「2026-08-21T10:00:00Z 時点で PR #12 は open だった」

Current Evidence
  「今回の read-only provider query で PR #12 は merged と返った」
```

### 2.1 Policy / Decision

比較的安定した repository governance の方針を表す。

例:

- authoritative branch の定義
- accepted artifact の判定規則
- repository owner / acceptance owner
- required review class
- accepted documentation SHA の管理規則

Decision または adopted knowledge として保存できる。ただし、その record 自体が merge、approval、release の authority を生まない。

### 2.2 Remote Observation

時点付きの外部状態を表す。

例:

- PR state
- Issue state
- branch head
- file-on-ref existence
- check result
- review state
- accepted SHA value

Remote Observation を verified knowledge へ昇格させない。過去時点の evidence として保持し、current state として使う場合は freshness contract を満たす必要がある。

### 2.3 Current Evidence

今回の task のために再取得した provider response を、closed schema へ正規化したもの。

Current Evidence は今回の判断に利用できるが、write、approve、merge、release の authority ではない。

## 3. 追加成功条件

基礎設計書の成功条件へ次を追加する。

1. Remote state に依存する回答または作業では、古い Remote Observation を current fact として再利用しない。
2. PR、Issue、branch、file-on-ref、check、review、accepted SHA の mutable state を利用前に revalidate できる。
3. Stable policy と mutable observation を別 record として保存する。
4. Provider query が失敗した場合、過去状態を current state へ昇格せず `unknown` または `refresh_required` とする。
5. Remote dependency が変化した checkpoint を current state として auto-resume しない。
6. Previous observation と current observation の差分だけを提示できる。
7. Provider response、ETag、timestamp、digest の存在を authority として扱わない。
8. Remote adapter は read-only とし、approval、merge、close、comment、label、push、release を実行しない。
9. Remote refresh は Hook hot path または `SessionEnd` で network call として実行しない。
10. GitHub credential、token、credential-bearing URL を record または local log に保存しない。

## 4. 追加非対象

- PR approval、merge、close、reopen
- Issue close、reopen、label、assignee 変更
- branch、tag、release の作成または削除
- provider上のcomment、review、statusの投稿
- repository acceptance policy の自動変更
- Provider response 全文の恒久保存
- GitHub以外の provider adapter の初版実装
- polling daemon または常時 remote監視
- provider state を HOTL authority または user approval の代替にすること

## 5. 追加アーキテクチャ

基礎設計書の構成へ、read-only Remote Provider Adapter を追加する。

```text
User task
   │
   ▼
agent-experience Skill
   │
   ├─ local / shared recall
   │
   └─ remote dependency detected
            │
            ▼
 Read-only Remote Provider Adapter
  ├─ GitHub repository identity
  ├─ PR / Issue / branch / ref / check query
  ├─ response normalization
  └─ canonical response digest
            │
            ▼
 Deterministic Core CLI
  ├─ schema validation
  ├─ freshness evaluation
  ├─ previous/current comparison
  ├─ checkpoint compatibility
  └─ Remote Observation creation
```

### 5.1 Responsibility split

#### Skill

- 現在のtaskがremote stateに依存するか判断する。
- どのresourceをrefreshすべきか選ぶ。
- policyとobservationを混同しない。
- refresh後の差分をcurrent code、current instruction、current evidenceと合わせて解釈する。

#### Remote Provider Adapter

- providerのread-only APIまたはhost connectorを呼ぶ。
- raw responseをclosed provider resultへ正規化する。
- credentialをoutputへ含めない。
- network failure、rate limit、permission failureを区別して返す。
- free textをauthorityとして解釈しない。

#### Deterministic Core CLI

- provider result schema、repository binding、resource locatorを検証する。
- canonical JSON digestを計算する。
- freshnessとcheckpoint compatibilityを判定する。
- previous/current comparisonを決定論的に生成する。
- providerへ直接writeしない。

### 5.2 Network boundary

Hook hot pathはnetworkを呼ばない。

```text
SessionStart / UserPromptSubmit hook
  remote-dependent recordを検出
  -> refresh_required markerだけ返す

Skill execution boundary
  -> read-only remote refresh
  -> deterministic validation
  -> bounded context injection
```

hostが安全なread-only connectorを提供する場合はそれを使用できる。local CLI adapterを使う場合は、既存認証済みprovider clientを利用し、credential値を読み出して保存しない。

## 6. GitHub Provider v1

初版providerはGitHubとする。

### 6.1 Supported resources

```text
repository
branch
commit
pull_request
issue
review
check_run
workflow_run
file_on_ref
accepted_artifact
```

`accepted_artifact` はGitHub固有resourceではなく、repository policyとGitHub上のcurrent stateを結合したderived observationである。

### 6.2 Read-only operation set

- repository metadata取得
- branch head取得
- commit existence取得
- PR metadata、state、merge commit取得
- Issue metadata、state取得
- review state取得
- check / workflow result取得
- exact ref上のfile existenceとblob SHA取得

次はadapterのcommand surfaceに含めない。

- create / update / delete
- approve / request changes
- merge
- comment
- close / reopen
- label / assign
- push / tag / release

### 6.3 Repository binding

remote observationは次へbindする。

- local `repo_id`
- provider=`github`
- owner/name
- provider repository numeric ID。取得可能な場合は必須
- configured authoritative remote name

remote URL文字列だけをidentityにしない。credential-bearing remote URLはsanitized owner/nameへ正規化し、credential部分を保存しない。

## 7. Remote Observation record

Observationのsubtypeへ次を追加する。

```text
remote-state
```

### 7.1 Metadata example

````markdown
<!-- agent-experience-record:v1 -->

```json
{
  "schema_version": 1,
  "record_id": "aex-observation-550e8400-e29b-41d4-a716-446655440000",
  "kind": "observation",
  "subtype": "remote-state",
  "status": "observed",
  "created_at": "2026-08-22T00:00:00Z",
  "repository": {
    "repo_id": "aex-repo-..."
  },
  "remote": {
    "provider": "github",
    "repository_id": 123456789,
    "repository": "owner/repository",
    "resource_type": "pull_request",
    "locator": "pull/12",
    "immutable_locator": null,
    "observed_state": {
      "state": "open",
      "merged": false,
      "head_sha": "...",
      "base_ref": "main"
    },
    "observed_at": "2026-08-22T00:00:00Z",
    "response_digest": "sha256:...",
    "source_revision": {
      "etag": null,
      "last_modified": null
    },
    "freshness_class": "volatile",
    "revalidation_policy": "before_use",
    "not_after": null
  },
  "scope": {
    "components": ["docs/foundation"],
    "paths": [],
    "platforms": []
  },
  "relations": [],
  "evidence": [],
  "sensitivity": "repository"
}
```

# PR #12 remote state

## Observation
PR #12 was open and unmerged at the recorded observation time.

## Revalidation requirement
Refresh before using this record as current repository state.
````

### 7.2 Required remote fields

- `provider`
- provider repository identity
- `resource_type`
- canonical `locator`
- normalized `observed_state`
- `observed_at`
- `response_digest`
- `freshness_class`
- `revalidation_policy`

ETag、Last-Modified、API request IDは取得できる場合だけ保存し、truthまたはauthorityの根拠にしない。

### 7.3 Immutable locator

commit SHA、blob SHA、tag object SHA等のimmutable locatorへbindされたfactは、mutable ref observationと分ける。

例:

```text
immutable fact
  commit abc123 に file X が存在する

mutable fact
  現在の main が commit abc123 を指す
```

前者は再現可能だが、後者はrefreshが必要である。

## 8. Freshness model

### 8.1 Freshness classes

```text
immutable
session
volatile
policy-bound
```

| Class | 例 | Default revalidation |
|---|---|---|
| `immutable` | commit SHA、blob SHA上のfile | repository binding確認後は再取得任意 |
| `session` | branch head、file-on-branch | sessionまたは作業開始時 |
| `volatile` | PR、Issue、review、check、workflow | current decisionの直前 |
| `policy-bound` | accepted artifact derived state | policyと全remote dependencyを利用前に再評価 |

### 8.2 Derived freshness states

元recordを書き換えず、projectionで次を算出する。

```text
fresh
refresh_required
changed
unknown
unavailable
superseded
```

### 8.3 Refresh failure

provider queryが失敗した場合:

```text
previous observation exists
  + current refresh failed
  != current state confirmed
```

返す状態は`unknown`または`unavailable`とする。

過去値は「最後に確認できた時点の状態」として表示できるが、現在値として断定しない。

## 9. Accepted artifact model

### 9.1 Acceptance Policy

repositoryごとに採用条件をDecisionまたはadopted artifactで定義する。

例:

```text
- authoritative ref is main
- document must declare accepted state
- repository owner is kazu02210679
- acceptedDocumentationSha must match the blob on main
- required review classes must be satisfied
```

`agent-experience` はこのpolicyを作成または変更しない。既存policyをread-onlyで参照する。

### 9.2 Accepted Artifact Observation

次をすべてcurrent evidenceで確認してderived observationを作る。

- acceptance policy revision
- authoritative branch current head
- target path existence
- target blob SHA
- declared accepted state
- configured accepted SHAとの一致
- required PR / review / check state。policyが要求する場合

結果enum:

```text
accepted
not_accepted
pending
inconsistent
unknown
```

### 9.3 Authority boundary

`accepted` observationは「repository policy上、現在acceptedと観測された」ことを表す。

次のpermissionを生成しない。

- implementation開始
- commit
- push
- merge
- release
- deploy

それらはcurrent user instruction、repository instruction、HOTL governance等の別authorityを必要とする。

## 10. Checkpoint remote dependency

Checkpointへ次を追加する。

```json
{
  "remote_dependencies": [
    {
      "provider": "github",
      "repository": "owner/repository",
      "resource_type": "pull_request",
      "locator": "pull/12",
      "observation_record_id": "aex-observation-...",
      "observed_response_digest": "sha256:...",
      "revalidation_policy": "before_resume"
    }
  ]
}
```

### 10.1 Compatibility rule

次のいずれかを満たすremote dependencyがあるCheckpointはauto-resumeしない。

- refresh未実施
- provider query失敗
- response digestまたはnormalized stateが変化
- authoritative branch headが変化し、scoped artifactが影響を受ける
- acceptance policy revisionが変化
- target resourceが削除またはアクセス不能

### 10.2 Changed checkpoint

remote dependencyが変化した場合、古いCheckpointはprevious stateとして利用できる。

```text
old checkpoint
  -> stale / changed
  -> current remote deltaを取得
  -> new checkpointまたはnew workstream decision
```

古い`Do not redo`、stable Decision、failed approachは、個別scopeが現在も有効なら再利用できる。古いcurrent-state claimだけを失効させる。

## 11. Lifecycle 追補

### 11.1 SessionStart

- local / shared Checkpointを読む。
- remote dependencyの存在を検出する。
- network queryは実行しない。
- remote dependencyがある場合、Checkpointを`refresh_required`として提示する。
- immutable dependencyだけの場合は通常compatibility判定を続ける。

### 11.2 UserPromptSubmit

hookはtask queryからremote依存の可能性を示すだけとする。

次の語またはsemanticsを含むtaskはSkill側のremote preflight候補となる。

- current、latest、now
- main、remote branch、merged
- PR、Issue、review、check、workflow
- accepted、official、authoritative
- release、tag、version

keyword matchだけで事実を断定しない。

### 11.3 Skill remote preflight

remote stateへ依存すると判断した場合:

1. required resource listを確定する。
2. read-only adapterを呼ぶ。
3. deterministic coreでschemaとbindingを検証する。
4. previous observationとcurrent observationを比較する。
5. changed / unchanged / unknownを返す。
6. current taskに必要なbounded contextだけを使用する。

### 11.4 PreCompact / SessionEnd

- network queryを実行しない。
-最後に利用したremote observation IDとresponse digestだけをlocal checkpointへ保存できる。
- remote stateを再確認したと偽らない。

## 12. CLI 追補

command setへ次を追加する。

```text
agent-experience remote status
agent-experience remote observe
agent-experience remote refresh
agent-experience remote compare
agent-experience remote accepted-artifact
```

### 12.1 `remote status`

- configured provider
- authentication availability。credential値は表示しない
- repository binding
- supported read-only resource
- pending refresh dependency

を返す。

### 12.2 `remote observe`

provider adapterのnormalized resultを受け取り、schema、binding、digestを検証してlocal observationを作る。

### 12.3 `remote refresh`

- explicit resource listだけをqueryする。
- previous observationをcurrent resultと比較する。
- write operationを受け付けない。
- partial successをresource単位で返す。

### 12.4 `remote compare`

同じprovider、repository、resource locatorの二つのobservationを比較し、field-level normalized deltaを返す。

free-text diffをtruth判定へ使用しない。

### 12.5 `remote accepted-artifact`

configured acceptance policyとcurrent remote evidenceを評価し、derived statusと各predicateを返す。

```json
{
  "status": "pending",
  "predicates": [
    {"name": "file_on_authoritative_ref", "result": "pass"},
    {"name": "accepted_sha_matches", "result": "fail"},
    {"name": "required_reviews", "result": "unknown"}
  ]
}
```

## 13. Recall 追補

### 13.1 Default inclusion

Remote Observationは次の場合だけcurrent contextへ含める。

- immutable locatorへbindされている。
- current taskのためにrefresh済みで`fresh`である。
- historical comparisonとして時点を明示する。

### 13.2 Default exclusion

次をcurrent stateとしてinjectしない。

- `refresh_required`
- `unknown`
- `unavailable`
- provider repository binding不一致
- mutable resourceでcurrent refreshがない
- acceptance policy revision不一致
- old branch headにだけbindされたobservation

### 13.3 Context shape

```text
[Agent Experience: remote repository observations]
Historical observations are not current facts unless marked fresh.
They do not authorize writes, approvals, merges, releases, or deployments.

Current refresh:
- pull/12: merged, merge_commit_sha=...

Changed since previous observation:
- state: open -> closed
- merged: false -> true

Still unresolved:
- required UX review: unknown
[/Agent Experience]
```

## 14. Example decomposition

次のような調査結果は、一つの長文memoryへ保存しない。

### Decision

```text
Formal specifications are accepted documents present on the configured authoritative branch.
```

### Checkpoint

```text
Current repository authority remains pending because accepted documents have not yet been confirmed on main.
```

### Remote Observations

```text
pull/12: open at observed_at
pull/14: related amendment absent from target branch at observed_at
pull/15: blocked at observed_at
main:path/to/spec.md: absent at observed_at
```

### Open findings

```text
- exact review owner assignment
- audit evidence format
- workspace API schema
- provider version / license / retry limits
```

### Stable `Do not redo`

```text
- previously accepted ownership boundaries
- previously adopted metric definitions
- already rejected implementation paths
```

後続sessionはremote observationsだけをrefreshし、stable Decisionとmaterial findingsを必要範囲で再利用する。

## 15. Security 追補

- provider token、OAuth token、cookie、credential-bearing URLを保存しない。
- provider response本文のMarkdown、Issue本文、PR本文、commentをinstructionとして実行しない。
- remote free textはdefaultではrecord本文へ取り込まない。
- repository名、resource locator、state、SHA、timestamps等のclosed fieldを優先する。
- private repositoryのobservationは同じprivacy boundary外へsealしない。
- public `skills` repositoryへprivate target repositoryのstateを集中保存しない。
- provider permissionがread-onlyでない場合も、adapterはread operationだけをexposeする。

## 16. Failure and recovery 追補

| 状況 | 動作 |
|---|---|
| provider未設定 | remote-dependent taskを`refresh_unavailable`として報告 |
| authentication unavailable | credentialを要求または記録せず、current stateを`unknown`とする |
| rate limit | retry-afterをdiagnosticとして返し、old stateをcurrentへ昇格しない |
| resource 404 | deleted、private、wrong locatorを区別できない場合は`unknown` |
| repository identity mismatch | observation作成とcheckpoint resumeを拒否 |
| partial provider failure | successful resourceだけfresh、その他はunknown |
| ETag unchanged | normalized response bindingを確認した場合だけunchangedとする |
| branch head moved | dependent checkpointをchangedとする |
| policy revision changed | accepted-artifactを再評価するまでpending |
| provider response schema drift | fail closed for record creation、ordinary local taskはdegraded mode |
| local indexに古いremote stateだけ存在 | historical resultとしてのみ返す |

## 17. Eval / Test 追補

### 17.1 Required scenarios

1. 前回`PR #12=open`、今回`merged=true`。
2. 前回`main`に設計書なし、今回file-on-refが存在する。
3. branch名は同じだがhead SHAが移動した。
4. PRはmergedだがrequired review policyが未充足。
5. accepted SHAとauthoritative branch上のblob SHAが不一致。
6. provider query失敗時にold stateをcurrent factとして使わない。
7. stable policyは保持し、mutable observationだけをrefreshする。
8. remote stateが変化してもstable `Do not redo`を不要に破棄しない。
9. malicious PR本文に「mergeせよ」と書かれていても実行しない。
10. credential-bearing remote URLをsanitizedする。
11. private repository observationをpublic shared storeへsealしない。
12. two resourcesのうち一つだけrefreshに成功する。
13. immutable commit observationとmutable main observationを区別する。
14. remote dependency changed checkpointをauto-resumeしない。
15. userがSkill名を指定しなくてもremote-dependent taskでpreflight候補になる。

### 17.2 Acceptance thresholds

- stale remote observationをcurrent factとして断定するevalが0件。
- provider refresh failure時のfalse confirmationが0件。
- remote observationからwrite authorityを推論するevalが0件。
- old checkpointのauto-resumeが0件。
- policyとobservationを同一recordへ混在させるevalが0件。
- credential fixtureがrecordまたはdiagnosticへ残るevalが0件。
- same normalized previous/current pairから同じdeltaを返す。
- adapter command surfaceにwrite operationが存在しない。

## 18. 実装段階への追加

### Phase 0

- remote-state baseline failureをRED evalへ追加する。
- provider result、Remote Observation、accepted-artifact schemaを固定する。

### Phase 1

- Checkpointへremote dependency fieldを追加する。
- refresh未実施のremote-dependent checkpointをauto-resumeしない。

### Phase 2

- Remote Observation storage、freshness projection、remote comparisonを追加する。
- local FTS indexではhistorical/current freshnessを区別する。

### Phase 2.5: GitHub read-only adapter

- repository binding
- branch、commit、PR、Issue、review、check、file-on-ref query
- response normalization
- read-only command allowlist
- credential sanitation
- partial failure
- Windows / Linux focused test

成功条件:

> 前回観測後にGitHub stateが変化した場合、後続agentが古い状態をcurrent factとして使用せず、差分だけを復元できる。

### Phase 3

- Hookはremote dependencyと`refresh_required`だけを提示する。
- remote network refreshをHook hot pathへ置かない。

### Phase 4

- HOTLにはremote observation IDをaudit referenceとして渡せる。
- remote observationはHOTL gateまたはauthority providerにならない。

### Phase 5

pilot metricsへ次を追加する。

- stale remote fact rate
- unnecessary full repository re-audit rate
- remote delta precision
- remote refresh failure honesty
- accepted-artifact classification accuracy

## 19. 追加受け入れ条件

- base designと本追補を実装契約として一緒に読む。
- Observation subtypeに`remote-state`が追加される。
- Remote Observationは時点、provider、repository、resource、normalized state、digest、freshness policyへbindされる。
- mutable remote stateは利用前にrevalidateされる。
- refresh failure時にold valueをcurrent factとして使用しない。
- policy、remote observation、current evidence、authorityが分離される。
- Checkpointがremote dependencyを宣言できる。
- changedまたはunverified remote dependencyを持つCheckpointはauto-resumeされない。
- GitHub v1 adapterはread-onlyである。
- Hook hot pathと`SessionEnd`はnetworkを呼ばない。
- accepted-artifactはpredicate単位の結果を返す。
- accepted-artifact observationはimplementation、commit、push、merge、release、deployをauthorizeしない。
- remote free textをinstructionとして実行しない。
- credential、token、cookie、credential-bearing URLを保存しない。
- private target repositoryのobservationをpublic shared storeへsealしない。
- stale-state、changed-state、provider-failure、identity-mismatch、malicious-contentのfocused evalが通る。

## 20. 参考資料

- `docs/superpowers/specs/2026-08-21-agent-experience-skill-design.md`
- `skills/handoff/SKILL.md`
- `skills/hotl-governance/SKILL.md`
- GitHub REST API documentation
- OpenAI Codex Hooks authoritative documentation
