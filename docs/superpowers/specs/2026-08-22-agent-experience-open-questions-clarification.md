# Agent Experience Skill — Open Questions Clarification Contract

- **文書日**: 2026-08-22
- **対象**: `agent-experience` v1
- **状態**: Binding clarification
- **入力**: Lunaによる設計理解レビューで挙げられた35項目

## 0. Authority and scope

本書は、次の文書を読んだ後に残った実装上の裁量を閉じる。

- `2026-08-21-agent-experience-skill-design.md`
- `2026-08-21-agent-experience-skill-adversarial-amendment.md`
- `2026-08-21-agent-experience-skill-normative-contract.md`
- `2026-08-22-agent-experience-remote-state-amendment.md`
- `2026-08-22-agent-experience-contract-index.md`

本書は、次の領域では既存文書を拡張または上書きする。

- Acceptance Policy
- remote observation、freshness、change detection
- review / check evaluation
- checkpoint selection、manual resume、stable-only reuse
- canonical JSON、schema version、time、deduplication
- Hook / CLI boundary
- retention / history
- implementation dependency、RED scope、pilot、release milestones

本書は新しいwrite authorityを追加しない。GitHub Providerは引き続きremote read-onlyであり、Experienceはcurrent evidenceまたはexecution authorityではない。

## 1. Canonical contract entry point

### 1.1 唯一の入口

実装者が最初に読む規範的入口は次の一ファイルに固定する。

```text
docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md
```

Contract Index自体が全仕様本文を複製した合成ファイルという意味ではない。Contract Indexが、binding documents、読み順、domain、優先順位、active implementation planを一意に決める。

したがって、次を区別する。

```text
canonical entry point
  = Contract Index

binding contract corpus
  = Contract Indexが列挙する全設計文書

active implementation plan
  = Contract Indexが指定する一つの計画書
```

実装者は「どれか一つの本文だけを読む」のではなく、Contract Indexから解決された順序でbinding corpusを読む。文書の合成結果を別ファイルへ手作業でコピーしない。

### 1.2 実装計画の正本

実装手順の正本は引き続き次の一ファイルだけとする。

```text
docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md
```

本書のTask amendmentsは仕様上のacceptance criteriaであり、第二の実装計画ではない。Consolidated PlanはContract Indexを`Spec`として参照するため、本書の要求を各Taskで満たさなければならない。

## 2. Acceptance Policy lifecycle

### 2.1 保存場所

RepositoryごとのAcceptance Policyは、tracked fileとして次へ保存する。

```text
.agent-experience/acceptance-policy.json
```

`config.toml`はpolicy pathを上記defaultから変更できるが、pathはrepository-relativeでなければならない。absolute path、`..`、symlink escape、Git common directory配下を拒否する。

PolicyはGit-tracked shared artifactである。local SQLite、Hook config、user home、public `skills` repositoryへ保存しない。

### 2.2 Active policy

ある時点のactive policyは、configured authoritative ref上のpolicy fileで、次をすべて満たすものとする。

- strict schema valid
- `policy_revision_digest` valid
- repository binding valid
- predecessor policyのchange gateを通過済み
- bootstrap policyの場合は§2.4のbootstrap receiptが存在

working treeまたはDraft branchにあるpolicyはcandidateであり、active policyではない。

### 2.3 Policy change rule

Policy revision `P(n+1)`の採用条件は、`P(n+1)`自身ではなく現在activeな`P(n)`の`policy_change`で決める。

```text
P(n) --governs acceptance of--> P(n+1)
```

新policyが自分自身の承認条件を緩和して、そのrevisionを自己承認することを禁止する。

`policy_change`は次を持つ。

```json
{
  "required_approvers": ["exact-login"],
  "minimum_approvals": 1,
  "require_distinct_author_and_approver": true,
  "required_checks": [
    {
      "name": "validate-agent-experience-policy",
      "app_id": null,
      "allowed_conclusions": ["success"]
    }
  ]
}
```

Rules:

- reviewerはexact loginで指定する。
- wildcard、organization role、曖昧な`maintainer`等をv1で解釈しない。
- `require_distinct_author_and_approver=true`の場合、policy変更PRのauthorはapproval数へ含めない。
- 個人repositoryで自己承認を許す場合、active policyに明示的に`false`を設定する。暗黙には許可しない。
- policy changeのaccepted判定もread-only observationであり、mergeを実行しない。

### 2.4 Bootstrap

最初のpolicyにはpredecessorがないため、通常のpolicy change gateを適用できない。

Bootstrapは明示commandだけで行う。

```text
agent-experience policy bootstrap --input <policy.json> --dry-run --json
agent-experience policy bootstrap --input <policy.json> --apply --plan-digest <digest> --json
```

Bootstrap requirements:

- repository owner loginとcurrent authenticated GitHub loginの一致
- authoritative refとrepository IDのcurrent read-only確認
- userの明示`--apply`
- canonical plan digest
- local bootstrap receipt
- policy fileの通常Git review / commit / pushは別操作

Bootstrap commandはpolicyをGitHubへpush、PR作成、mergeしない。bootstrap receiptは「初期policy候補を明示生成した」ことだけを示す。

### 2.5 Policy revision digest

`policy_revision_digest`はContract Indexのcanonical JSON規則に従い、top-levelの同fieldを除外して計算する。

candidate policyが保存値と再計算値で一致しない場合、active policyにもaccepted-artifact評価にも使用しない。

## 3. Acceptance Policy v1 schema

### 3.1 Concrete shape

v1のpolicy objectは次を基準とする。

```json
{
  "schema_version": 1,
  "policy_id": "aex-policy-foundation",
  "policy_revision_digest": "sha256:...",
  "repository": {
    "provider": "github",
    "repository_id": 123456789,
    "full_name": "owner/repository",
    "authoritative_ref": "refs/heads/main",
    "repository_owner_login": "owner"
  },
  "policy_change": {
    "required_approvers": ["owner"],
    "minimum_approvals": 1,
    "require_distinct_author_and_approver": false,
    "required_checks": [
      {
        "name": "validate-policy",
        "app_id": null,
        "allowed_conclusions": ["success"]
      }
    ]
  },
  "artifacts": [
    {
      "artifact_id": "foundation-design",
      "path": "docs/foundation/specs/foundation-design.md",
      "content_binding": {
        "mode": "exact_blob",
        "expected_blob_sha": "0123456789abcdef..."
      },
      "required_pull_requests": [
        {
          "number": 12,
          "must_be_merged": true,
          "merge_commit_must_reach_authoritative_ref": true
        }
      ],
      "review_policy": {
        "required_reviewers": ["owner"],
        "minimum_approvals": 1,
        "require_distinct_author_and_reviewer": false,
        "bind_to_current_head": true
      },
      "required_checks": [
        {
          "name": "validate-foundation",
          "app_id": null,
          "allowed_conclusions": ["success"]
        }
      ]
    }
  ]
}
```

### 3.2 Field mapping

Lunaが挙げた用語は次へ対応する。

| Concept | Policy field |
|---|---|
| authoritative branch | `repository.authoritative_ref` |
| target path | `artifacts[].path` |
| accepted SHA | `artifacts[].content_binding.expected_blob_sha` |
| required PR | `artifacts[].required_pull_requests[]` |
| required reviewer | `artifacts[].review_policy.required_reviewers[]` |
| required check | `artifacts[].required_checks[]` |
| repository owner | `repository.repository_owner_login` |

### 3.3 Content binding modes

v1で許可するmodeは次だけ。

```text
exact_blob
authoritative_ref_current
```

- `exact_blob`: `expected_blob_sha`必須。authoritative ref上のblob SHAと一致しなければ`inconsistent`。
- `authoritative_ref_current`: expected SHAを固定せず、current authoritative ref上のblobを対象にreview / PR / check predicatesを評価する。

security、governance、authorityに関わるartifactでは`exact_blob`を推奨する。

### 3.4 Policy result is not authority

`accepted`はpolicy predicatesがcurrent remote evidence上でpassしたという観測である。implementation、commit、push、PR、merge、release、deployのauthorizationではない。

## 4. Remote digests and change semantics

### 4.1 Three distinct digests

`response_digest`という一語を廃止し、次を区別する。

```text
provider_payload_digest
provider_result_digest
state_digest
```

#### `provider_payload_digest`

providerから受け取ったraw response bytesのSHA-256。取得できる場合だけmemory上で計算し、digestのみ保存できる。raw bodyは保存しない。

#### `provider_result_digest`

resource key、normalized closed fields、provider metadata、adapter contract versionを含むnormalized provider resultのcanonical digest。

`observed_at`は含めない。同じprovider resultを別時刻に取得しても同じdigestになる。

#### `state_digest`

resource typeごとに定義されたdecision-relevant stateだけのcanonical digest。

`changed`判定、remote dependency compatibility、accepted-artifact predicateは`state_digest`または個別predicate resultを使う。URL、取得時刻、API request ID、pagination order、title/body等のnon-decision fieldで`changed`にしない。

### 4.2 Observation digest

Remote Observation record全体のimmutable record digestは、通常record contractに従い`observed_at`を含む。したがって同じstateを再観測したrecordは異なるrecord digestを持ち得る。

状態変化判定にはrecord digestを使わない。

## 5. Remote result taxonomy

### 5.1 `unknown`

provider callは完了したが、current stateを安全に一意決定できない場合。

```text
not_found_or_access_denied
ambiguous_404
partial_response
missing_required_field
ambiguous_duplicate_check_name
ambiguous_review_state
unsupported_resource_semantics
```

過去値をcurrent factとして代入しない。

### 5.2 `unavailable`

current observation自体を実施・完了できない場合。

```text
provider_not_configured
gh_missing
auth_unavailable
rate_limited
network_error
provider_timeout
provider_unavailable
provider_schema_unsupported
host_unsupported
```

### 5.3 `refresh_required`

まだcurrent-use refreshを実行していない状態。failureではない。

### 5.4 `not_accepted`

positive current evidenceにより、acceptance predicateが明確にfailした場合だけ使用する。

404だけを根拠に`not_accepted`へ落とさない。GitHubの404はresource不存在とaccess denialを区別できない場合があるため、v1では`unknown/not_found_or_access_denied`とする。

### 5.5 Error envelope

remote commandのmachine outputは最低限次を持つ。

```json
{
  "schema_version": 1,
  "status": "unknown",
  "code": "not_found_or_access_denied",
  "retryable": false,
  "resource_key": {},
  "previous_observation_id": null
}
```

## 6. Resource-specific normalized state

### 6.1 Pull Request profile

PRの`state_digest`へ含めるfieldを次に固定する。

```text
number
state
draft
merged
merge_commit_sha
head_sha
base_ref
base_sha
```

次は保存またはhistorical displayには使えても、PR state digestへ含めない。

```text
title
body
description
html_url
updated_at
API order
user profile fields
```

force-pushは`head_sha`変化として`changed`になる。

review追加・取消、check再実行はPR resource自体のstate changeではない。CheckpointまたはAcceptance Policyがreview/checkを必要とする場合、review/checkを独立remote dependencyとして宣言する。

### 6.2 Branch profile

branch resourceのdecision-relevant fields:

```text
branch_ref
head_sha
protected
```

branch headが変化しても、当該branch resourceをdependencyとして持つcheckpoint itemだけをinvalidateする。同じrepositoryの全checkpointを一括invalidateしない。

### 6.3 File-on-ref profile

```text
ref
path
blob_sha
file_type
```

raw contentをRemote Observationへ保存しない。

### 6.4 Dependency impact scope

Checkpoint remote dependencyは次を持つ。

```json
{
  "resource_key": {},
  "state_digest": "sha256:...",
  "freshness_policy": "before_resume",
  "affects_item_ids": ["current-state-1"],
  "required_fields": ["head_sha"]
}
```

remote state変化時は`affects_item_ids`のcurrent-state claimsだけを失効させる。emptyまたはunknown impact scopeは安全側に倒し、checkpoint全体をmanual reviewへ落とす。

## 7. Review evaluation contract

### 7.1 Identity

required reviewerはexact GitHub loginで指定する。v1ではorganization role、team membership、repository permissionを動的にrequired reviewerへ変換しない。

### 7.2 Effective review per reviewer

レビュー一覧はchronological inputとして受け、reviewerごとに`submitted_at`、次にreview IDで最後のsubmitted reviewを選ぶ。

`PENDING` reviewはsubmitted reviewとして数えない。

### 7.3 Approval pass

required reviewerがpassする条件:

- latest effective review stateが`APPROVED`
- reviewがdismissされていない
- `bind_to_current_head=true`の場合、review `commit_id == current PR head_sha`
- `require_distinct_author_and_reviewer=true`の場合、reviewer != PR author

### 7.4 Other states

| Latest state | Predicate result |
|---|---|
| `APPROVED` and current | pass |
| `CHANGES_REQUESTED` | fail |
| `COMMENTED` | pending |
| `DISMISSED` | pending |
| no submitted review | pending |
| approval on old head | pending |
| ambiguous/malformed | unknown |

一度approveされた履歴があっても、後のeffective reviewまたはhead変更でpredicateは再評価される。

## 8. Check and workflow evaluation

### 8.1 Canonical acceptance source

accepted-artifactのrequired check判定では`check_run`を正本とする。

`workflow_run`はdiagnostic / navigation用であり、accepted predicateへ直接使用しない。これにより同じGitHub Actions実行をcheckとworkflowで二重評価しない。

### 8.2 Exact head binding

required checkはPRまたはauthoritative refのexact current head SHAへbindする。

### 8.3 Check selection

required check keyは次とする。

```text
(name, app_id-or-null)
```

同じnameが複数appに存在し、policyが`app_id`を指定していない場合は`inconsistent`とする。

同じkeyに複数runがある場合、`started_at`、次にcheck run IDで最新を選ぶ。

### 8.4 Status and conclusion

| State | Default predicate |
|---|---|
| missing, queued, requested, waiting, pending, in_progress | pending |
| completed + success | pass |
| completed + neutral | fail unless explicitly allowed |
| completed + skipped | fail unless explicitly allowed |
| completed + failure | fail |
| completed + cancelled | fail |
| completed + timed_out | fail |
| completed + action_required | fail |
| completed + stale | fail |
| malformed / permission ambiguity | unknown |

Policyの`allowed_conclusions`で`neutral`または`skipped`を明示許可できる。defaultは`success`のみ。

## 9. `remote observe`, `refresh`, `compare`

### 9.1 `remote observe`

provider fetchを実行しない。host connector、fixture、または別のread-only adapterが生成したnormalized provider resultを受け取り、schema / binding / digestを検証してlocal observationへ保存する。

```text
input normalized result
  -> validate
  -> store observation
```

### 9.2 `remote refresh`

explicit resource listをread-only providerへ問い合わせる。

```text
fetch current
  -> normalize
  -> observe
  -> select previous observation
  -> compare state_digest
  -> return delta
```

partial successをresource単位で返す。

### 9.3 `remote compare`

networkとstorage mutationを行わないpure operationとする。同一resource keyの二つのvalidated observationを比較し、decision-relevant field deltaだけを返す。

### 9.4 Unchanged refresh

同じresource keyで`state_digest`が同じ場合:

- local refresh receiptは毎回保存できる。
- shared Remote Observation recordはdefaultでは新規作成しない。
- previous observation ID、new observed_at、provider result digestをlocal receiptへ記録する。
- policyが明示的な監査revalidationを要求する場合だけ、`--seal-revalidation`で新しいshared outcomeを作成できる。

## 10. Meaning of read-only

`GitHub Provider read-only`は、GitHub remoteへwriteしないことを意味する。

次のlocal mutationは許可される。

- normalized observationのlocal SQLite保存
- refresh receipt
- derived local index / cache
- explicit `capture` / `seal`によるrepository内shared record作成

ただし`seal`はGit stage、commit、push、PR作成を行わない。

## 11. Checkpoint structure and selection

### 11.1 Structured items

Checkpoint本文の重要事項をfree textだけで保存しない。

```json
{
  "items": [
    {
      "item_id": "decision-1",
      "category": "stable_decision",
      "record_id": "aex-decision-...",
      "record_digest": "sha256:...",
      "remote_dependency_ids": []
    },
    {
      "item_id": "current-state-1",
      "category": "current_state",
      "record_id": null,
      "record_digest": null,
      "remote_dependency_ids": ["dep-pr-12"]
    }
  ]
}
```

Allowed categories:

```text
current_state
stable_decision
do_not_redo
failed_approach
open_work
next_action
```

### 11.2 Remote-dependency-free item

itemの`remote_dependency_ids`が空で、参照recordのpremise / scopeにもremote dependencyがない場合だけremote-independentとする。

後からremote dependencyが判明した場合、次checkpointから明示する。過去checkpointを黙って書き換えない。

### 11.3 Multiple active checkpoints

Checkpointはworkstreamごとにactiveになり得る。repository全体で一つのmutable `current` pointerを持たない。

selection order:

```text
1. explicit --checkpoint or --workstream
2. local session-to-workstream binding
3. exactly one exact active checkpoint
4. otherwise ambiguous
```

exact candidateが複数ある場合も自動選択しない。`ambiguous_checkpoint`を返し、candidate IDだけを提示する。

`handoff` artifactをautomatic checkpoint candidateとして使用しない。

## 12. `auto_resume`, explicit resume, successor workstream

### 12.1 Auto resume

`auto_resume=true`は次をすべて満たす場合だけ。

- local compatibility = `exact`
- candidate selectionが一意
- all remote dependencies = `fresh` and unchanged
- policy revisions unchanged
- no integrity / schema ambiguity

### 12.2 Explicit resume

`auto_resume=false`でも、次の条件なら明示resumeを許可できる。

- local compatibility = `manual_review_compatible`
- current diff / branch / HEADを明示review済み
- all mutable remote dependenciesをrefresh済み
- normalized remote state unchanged
- review receiptをlocal storeへ記録

```text
agent-experience resume --checkpoint <id> --review <review.json> --json
```

### 12.3 Resume prohibited

次では同じcheckpointをcurrent stateとしてresumeしない。

```text
local stale
local unavailable
remote refresh_required
remote changed
remote unknown
remote unavailable
policy pending / inconsistent
```

明示overrideで古いcurrent-state claimをcurrentへ昇格させない。

### 12.4 Stable-only successor

上記状態から継続したい場合、新しいworkstreamを作る。

```text
agent-experience start --from-checkpoint <id> --stable-only --json
```

`stable-only`がimportできるのは次だけ。

- valid immutable Decision reference
- valid `Do not redo` / failed approach record
- remote dependencyの影響scope外であることが機械判定可能なitem
- superseded / deprecated / contested / staleでないrecord

current-state claim、old next action、unverified blocker stateをimportしない。

## 13. Local checkpoint compatibility clarifications

Remote stateが一致していても、local classifierが優先する。

| Local state | Result |
|---|---|
| exact same branch / HEAD / manifests | exact candidate |
| dirty treeがcheckpoint時とbyte-for-byte同一 | exact candidateになり得る |
| dirty treeがcheckpoint後に変化 | stale |
| same branch, HEAD descendant, scope unchanged | manual review compatible |
| branch same, unrelated HEAD | stale |
| branch switched at same HEAD | manual review compatible |
| detached HEAD switch | manual review compatible or stale by lineage |
| untracked set changed | stale |
| worktree deleted / missing | unavailable |
| unmerged index / unstable snapshot | unavailable |

remote exactはlocal staleを上書きしない。

## 14. Reusing old checkpoint material

free-text sectionを機械的に「stable」と判断しない。

再利用可能なのは、Checkpoint itemがimmutable record ID/digestを参照し、次を満たす場合だけ。

- record valid
- effective state valid
- scope/premise digest current
- affected remote dependencyなし、またはdependency unchanged
- categoryが`stable_decision`、`do_not_redo`、`failed_approach`

`Do not redo`が単なる文章でrecord referenceを持たない場合、historical displayはできるがstable-only importしない。

## 15. Canonical JSON v1

### 15.1 Object and key order

- duplicate keyをparse時に拒否する。
- object keyはUnicode code point lexical orderでsortする。
- compact separatorsを使う。
- canonical JSON bytesにBOM、indent、trailing whitespace、final newlineを含めない。

### 15.2 Arrays

- 通常arrayはinput orderを保持する。
- schemaがset-likeと宣言するarrayだけ、element canonical bytesでsortしduplicateを拒否する。
- Policyの`required_approvers`、`required_reviewers`、`required_pull_requests`、`required_checks`はset-likeとする。

### 15.3 Unicode

全stringへ暗黙のUnicode normalizationを適用しない。path、ID、SHA等のopaque fieldを変形しないためである。

schemaがhuman-readable textと定義するfieldはNFCを必須とし、non-NFC inputをrejectする。query tokenizerはNFCへnormalizeしてよい。

### 15.4 Numbers

許可:

```text
integer
boolean
null
```

拒否:

```text
float
NaN
Infinity
-0.0
scientific notation
```

### 15.5 Time

contract timestampは次だけを許可する。

```text
YYYY-MM-DDTHH:MM:SSZ
```

- UTCのみ
- offset表記なし
- fractional secondsなし
- leap second拒否

### 15.6 Markdown

record bodyはCRLF/CRをLFへnormalizeし、file末尾を一つのLFにする。record digestのbody部分はこのnormalized bytesを使用する。

## 16. Schema version policy

v1 runtimeは`schema_version == 1`だけをread/writeする。

| Input | Behavior |
|---|---|
| version 1 | normal validation |
| missing / 0 / negative | invalid |
| newer version | `unsupported_schema`, exclude / manual mode |
| older future-supported version | version-specific readerが実装されるまでexclude |

automatic in-place migrationを行わない。

```text
agent-experience migrate --dry-run --json
agent-experience migrate --apply --plan-digest <digest> --json
```

migrationはnew file / new DBへ変換し、validation後にatomic switchする。元artifactをbackupまたはGit historyで保持する。

## 17. Time and freshness

### 17.1 `observed_at`

`observed_at`はprovider event時刻ではなく、adapterがnormalized resultを受理したclient UTC時刻である。

providerが返す`updated_at`、`submitted_at`、`completed_at`等は別fieldとして保存する。

### 17.2 Clock skew

- persisted freshnessをwall-clockだけで証明しない。
- `volatile / before_use` resourceはcurrent refresh runへのbindingを要求する。
- `session` resourceはcurrent sessionまたはcurrent preflight runへのbindingを要求する。
- observed_atがlocal current timeより300秒超未来ならinvalid。
- process内timeoutにはmonotonic clockを使い、persistしない。

### 17.3 Refresh run binding

current-use freshness overlayは次を持つ。

```text
refresh_run_id
resource_key
observation_id
state_digest
started_at
completed_at
use_context_id
```

過去sessionのvolatile observationを時刻だけでfreshとみなさない。

## 18. Auditability without raw provider body

Remote Observationまたはlocal refresh receiptへ次を保存する。

```text
provider
adapter_contract_version
resource key
endpoint profile ID
normalized closed state
state_digest
provider_result_digest
optional provider_payload_digest
source revision: ETag / Last-Modified / request ID when available
observed_at
provider_updated_at when available
error code / partial status
```

Accepted-artifact resultは各predicateについてevidence observation IDとdigestを列挙する。

raw bodyを保存しないため、将来adapter normalization codeが変わった後にraw responseから完全再演算することはできない。この制約を明示し、adapter contract versionとnormalized evidenceを監査正本とする。

## 19. Hook contract clarifications

### 19.1 Hookは`refresh_required`を返さない

v1 Hookはroute-onlyである。dynamic checkpoint status、remote state、`refresh_required`をmodel-visible output、stderr、exit codeで返さない。

`SessionStart`は固定routing noticeだけを返す。他のHookはsilentである。

`refresh_required`はexplicit CLIのmachine-readable resultで返す。

```text
agent-experience preflight --json
agent-experience remote status --json
```

### 19.2 No-network enforcement

方針だけでなく三層で強制する。

1. **Dependency boundary**: `hooks.py`は`github_provider`、`remote`、`urllib`、`socket`をimportしない。
2. **Runtime boundary**: Hook runtime interfaceはlocal marker / SQLite / snapshot fingerprintだけをexposeする。
3. **Tests**: socket、subprocess、provider entrypointを呼ぶとfailするtestとAST import allowlist testを持つ。

Hook hot pathからremote providerへ到達可能なdependency pathが存在すればTask 22はfailとする。

## 20. CLI authority and output

### 20.1 Provider read-only vs local mutation

`remote` command groupはGitHub read-onlyであるが、local observation保存は行える。

CLI全体にはlocal mutation commandが存在するため、「CLI全体がread-only」とは表現しない。

### 20.2 Command-tree allowlist

GitHub providerを呼べるcommandは次だけ。

```text
remote status
remote refresh
remote accepted-artifact
```

`remote observe`と`remote compare`はproviderを呼ばない。

provider invocationはfixed GET endpoint profileからのみ生成する。arbitrary method、URL、GraphQL、extension commandを受け付けない。

### 20.3 Forbidden remote verbs

CLI help treeとparser testで次が存在しないことを検証する。

```text
create
update
delete
approve
request-changes
merge
comment
close
reopen
label
assign
push
tag
release
deploy
```

### 20.4 Machine-readable output

全commandは`--json`を持ち、top-levelに次を持つ。

```json
{
  "schema_version": 1,
  "command": "remote compare",
  "ok": true,
  "status": "changed",
  "data": {},
  "errors": []
}
```

human outputは`--format human`の明示時だけ。Hookやagent間連携はJSONを使用する。

## 21. GitHub CLI capability contract

### 21.1 Version number aloneを信頼しない

固定minimum versionだけではなくcapability gateを使う。

Task 19開始時にtested `gh version`を`host-adapters.md`へ記録するが、runtimeは次を確認する。

- executable available
- configured host is `github.com`
- `gh auth status --active --hostname github.com --json hosts`をtoken表示なしでparse可能
- `gh api --method GET`をshell-free argvで実行可能
- configured REST endpoint profileとAPI version headerを使用可能

`gh auth status --show-token`を呼ばない。

### 21.2 GitHub Enterprise

v1は`github.com`だけをautomatic provider support対象とする。

GHES / GHE.com custom hostnameは`host_unsupported`としてmanual/custom adapterへ降格する。GitHub CLI自体がEnterpriseを支援していても、本Skill v1のnormalization / API compatibilityを未検証のまま主張しない。

### 21.3 API version

Task 19でthen-current official GitHub REST versionをfixtureへ固定し、request headerとして明示する。unknown newer response schemaを推測で受け入れない。

## 22. GC and history

### 22.1 Shared records

Git-tracked immutable shared recordsはautomatic GCで削除しない。

- Observation
- Decision
- Knowledge
- Outcome
- Promotion
- sealed Remote Observation
- sealed Checkpoint

はGit historyと監査用途のため保持する。削除は別の明示purge設計がない限り非対象。

### 22.2 Local ephemeral retention

| Local data | Default retention |
|---|---:|
| completed Hook idempotency rows | 7 days |
| closed local checkpoints | 30 days |
| recall receipts | 90 days |
| completed remote refresh runs | 90 days |
| unsealed normalized remote observations | 90 days |
| quarantined DB files | 30 days after explicit loss report acknowledgement |
| active checkpoint / unresolved pending | no automatic deletion |
| remote observation referenced by active dependency | pinned |
| installer manifest | until successful uninstall |

GC dry-run must show dependency pins and exclusion reasons。

### 22.3 Superseded vs deprecated

```text
superseded
  = specific successor record replaces this record
  = requires successor ID + digest

deprecated
  = use is prohibited or unsupported, with or without replacement
  = requires reason and approval locator
```

両方ともdefault recallから除外する。explicit history queryでは取得できる。

`superseded` relationがあるのにsuccessorがinvalidな場合、old recordを自動削除せずprojectionを`invalid/excluded`としてreviewへ回す。

## 23. Implementation dependency and parallelism

Consolidated PlanのTask Dependency Spineが正本である。

v1 production implementationは原則直列とする。例外は次だけ。

```text
Task 18 remote contract
  ├─ Task 19 GitHub provider
  └─ Task 20 acceptance evaluator
Task 19 + Task 20
  -> Task 21 remote checkpoint integration
```

Task 19と20はTask 18のinterfacesをfreezeした後、異なるworkerで並列実装できる。Task 21がjoin gateである。

その他のTaskを並列化する場合は、shared file、public interface、schema、test fixtureの競合がないことをplan amendmentで明示しなければならない。

## 24. RED strategy

REDは一度に全systemをfailさせる一枚のtestではない。

### Layer A: Task 1 behavioral baseline

Skillなしのagentが次を誤ることをobservableに記録する。

- stale resume
- memory as authority
- secret capture
- forged verified
- preflight omission
- stale remote fact
- provider failure false confirmation
- remote prompt injection

### Layer B: Task-specific RED

各Taskはproduction behaviorを書く前にfocused failing testを持つ。

- schema / canonicalization
- CLI
- snapshot
- store
- record / projection
- recall
- remote provider
- acceptance
- checkpoint
- Hook
- installer
- end-to-end

### Layer C: Integration RED

Task 27でlocal / fake-GitHub disposable end-to-endをREDにし、Task 28でpilot hard-stopを評価する。

## 25. Failure behavior matrix

| Failure | Ordinary local work | Current remote claim | Auto resume | Shared/config mutation |
|---|---|---|---|---|
| `gh` missing / auth unavailable | continue degraded | unavailable | false if dependency exists | remote publication reject |
| rate limit / timeout / network | continue degraded | unavailable | false | reject affected mutation |
| 404 ambiguity | continue degraded | unknown | false | accepted result unknown |
| schema drift | local core continues | unavailable | false | fail closed |
| remote state changed | continue after replan | changed | false | old current-state claim reject |
| local snapshot stale | no implicit resume | historical only | false | new workstream required |
| Hook DB lock / local read failure | continue | unchanged claim prohibited | no Hook auto action | explicit mutation fail closed |
| secret suspicion | work may continue without seal | n/a | n/a | seal reject |

### 25.1 No current-state override

ユーザーまたはagentが古いremote stateをcurrent factへ強制昇格するoverrideはv1に設けない。

必要なら`start --from-checkpoint --stable-only`でsuccessor workstreamを作る。

## 26. Fourteen-case pilot contract

Task 28の14ケースは既に列挙済みである。本書で各pass conditionを固定する。

| Case | Pass condition |
|---:|---|
| 1 exact-session resume | unique exact checkpoint only; `auto_resume=true` |
| 2 Windows known failure | relevant failure recalled; repeated failure avoided |
| 3 scoped local change | old checkpoint not auto-resumed |
| 4 prior decision | valid decision shown as advisory; current premise checked |
| 5 harmful guidance | harmful record excluded by default |
| 6 large unrelated corpus | default 5 records / 8,000 chars; Hook latency independent |
| 7 explicit handoff | routes to `handoff`; no automatic transfer |
| 8 no Skill name | routing causes preflight before non-trivial work |
| 9 compaction/re-entry | last committed local checkpoint survives; no lossless claim |
| 10 setup/uninstall | idempotent setup; drift-safe uninstall |
| 11 PR open -> merged | current refresh reports exact field delta; old state not current |
| 12 file absent -> present | accepted predicate reevaluated from current evidence |
| 13 provider failure | returns unknown/unavailable; old value not substituted |
| 14 blob/review/check mismatch | predicate-level pending/inconsistent/not_accepted; no authority |

Any hard-stop in the Consolidated Plan forces`NO-GO`。

## 27. Release milestones

Phase 2.5を一度に「最小MVP」と呼ばない。release boundaryを次に分ける。

```text
v0.1 Local Resume MVP
  Tasks 1-9
  manual local checkpoint only

v0.2 Memory Core
  Tasks 10-17
  shared records / projection / recall / feedback / GC

v0.3 Remote Observation MVP
  Tasks 18-19
  observe / refresh / compare via read-only GitHub provider
  no accepted-artifact authority model, no remote-dependent resume

v0.4 Remote Governance
  Tasks 20-21
  acceptance predicates and remote-dependent checkpoint

v0.5 Automatic Lifecycle
  Tasks 22-24
  route-only Hooks, setup, uninstall

v1.0 Reviewed Rollout
  Tasks 25-28
  final Skill, adapters, CI, pilot GO
```

各milestoneは前段のverification gateを満たす。v0.3を「accepted artifact対応済み」または「remote resume対応済み」と報告しない。

## 28. Task amendments

本書はConsolidated Planの次のTask acceptance criteriaを拡張する。

| Task | Additional binding requirements |
|---:|---|
| 2 | canonical entry point、remote historical wording、handoff separation |
| 3 | §15 canonical JSON / time rules |
| 4 | policy path、remote output envelope、command tree |
| 6 | local matrix、multiple candidate ambiguity |
| 7-8 | refresh receipt、pins、retention |
| 9 | explicit resume / stable-only successor skeleton |
| 10-13 | structured checkpoint items、remote digests、projection semantics |
| 15 | historical/current remote separation |
| 17 | local-only automatic GC |
| 18 | digest split、taxonomy、time、dedup、audit fields |
| 19 | PR/branch/file profiles、404、capability gate、GitHub.com-only |
| 20 | policy lifecycle/schema、review/check evaluation |
| 21 | dependency impact scope、resume rules、selection ambiguity |
| 22 | no dynamic refresh output、AST/dependency no-network tests |
| 23-24 | command boundary、host capability、drift safety |
| 25 | operator docs for every clarification |
| 27 | machine output schemas、fake-gh fixtures、forbidden command test |
| 28 | §26 pass conditions and §27 milestone claims |

## 29. Required additional tests

最低限次を追加する。

```text
policy revision cannot approve itself
bootstrap requires explicit owner-bound plan/apply
provider_result_digest stable across observed_at changes
state_digest ignores title/body but changes on head_sha/merge state
404 -> unknown, never not_accepted by itself
latest effective review per reviewer
approval on old head -> pending
DISMISSED approval -> pending
required check exact head and check key
neutral/skipped require explicit policy allowance
workflow_run never directly satisfies required check
unchanged refresh creates receipt but no duplicate shared observation
multiple exact checkpoints -> ambiguous, no auto selection
manual_review_compatible explicit resume with review receipt
changed/unknown remote -> resume rejected, stable-only successor allowed
non-NFC human text rejected; opaque path not normalized
unknown newer schema excluded
Hook AST/import graph cannot reach provider/network
CLI parser contains no forbidden remote verbs
shared records never appear in automatic GC plan
```

## 30. Acceptance

本clarificationを適用したv1は次を満たす。

- Contract Indexが唯一のcanonical entry pointである。
- Acceptance Policyの保存場所、bootstrap、revision governance、具体schemaが固定される。
- provider result、state、observationのdigestが分離される。
- `unknown`と`unavailable`がclosed reason codeで分離される。
- PR、review、check、branch、fileのdecision-relevant stateが固定される。
- changed remote resourceはdependency impact scopeだけをinvalidateする。
- Hookはdynamic remote statusを返さず、network dependencyを持たない。
- auto resume、explicit resume、stable-only successorが別契約になる。
- multiple checkpoint selectionがdeterministicである。
- canonical JSON、schema version、time、deduplication、audit fieldsが固定される。
- read-only providerとlocal mutationが区別される。
- shared historyをautomatic GCしない。
- Task dependency、RED layers、14 pilot pass criteria、release milestonesが固定される。

## 31. Primary references

- [GitHub REST API: pull request reviews](https://docs.github.com/en/rest/pulls/reviews)
- [GitHub REST API: check runs](https://docs.github.com/en/rest/checks/runs)
- [GitHub CLI: `gh api`](https://cli.github.com/manual/gh_api)
- [GitHub CLI: `gh auth status`](https://cli.github.com/manual/gh_auth_status)
- [OpenAI Codex Hooks](https://developers.openai.com/codex/hooks)
