# Agent Experience Skill — Trust Roots and Runtime Semantics Clarification

- **文書日**: 2026-08-22
- **対象**: `agent-experience` v1
- **状態**: Binding clarification
- **入力**: Lunaによる第二回設計理解レビューで挙げられた17項目

## 0. Authority and scope

本書は、既存のbinding contract corpusを読んだ後にも残っていた次の領域の裁量を閉じる。

- Acceptance Policy bootstrapの信頼根
- Policyとtarget repositoryのbinding
- content binding modeの選択
- accepted artifactのcommit / blob / review / check関係
- `remote observe` input provenance
- `seal`の意味と権限
- GitHub reviewのeffective-state評価
- required checkのtarget SHA
- remote freshnessのTOCTOU
- manual review receiptの扱い
- stable-only reuseのdependency closure
- local / sealed / shared / indexed dataの境界
- SQLite concurrency
- instruction precedenceとhard safety invariants
- automatic triggerの実際の保証範囲
- Critical / Importantの定義とclosure authority
- implementation開始とPolicy bootstrapの順序

本書は新しいremote write権限、merge権限、approval権限、release権限を追加しない。

本書が既存文書と競合する場合、上記領域では本書を優先する。

---

## 1. Policy bootstrap trust root

### 1.1 v1 support boundary

v1の自動bootstrapをサポートするのは、次をすべて満たすrepositoryだけとする。

```text
provider == github
host == github.com
repository owner type == User
repository is owned by a personal account
```

organization-owned repository、GHES、GHE.com、owner identityを一意に解決できないrepositoryでは、自動bootstrapを行わない。

返却状態:

```text
bootstrap_manual_governance_required
```

### 1.2 Owner definition

bootstrapの`owner`は、local Git configの名前、commit author、environment variable、CLI引数だけでは決めない。

read-only GitHub repository metadataから次を取得してbindする。

```json
{
  "repository_id": 123456789,
  "repository_full_name": "owner/repository",
  "owner_login": "owner",
  "owner_id": 12345,
  "owner_type": "User"
}
```

current authenticated actorはread-only `GET /user`相当から取得し、次をすべて満たす必要がある。

```text
authenticated_login == owner_login
authenticated_user_id == owner_id
repository permissions.admin == true
```

login文字列だけの一致では足りない。

### 1.3 Human-presence requirement

bootstrapは通常のagent taskから暗黙実行しない。

`--apply`には次のいずれかを必要とする。

1. interactive TTYで、人間がexact repository full nameとpolicy digestを再入力する。
2. trusted outer controllerが、repository ID、owner ID、policy digest、plan digestへbindされたverifiable user-approval receiptを渡す。

非対話環境で自己申告の`--actor human`、自由形式JSON、agent生成のapproval textだけを受け付けない。

### 1.4 Plan digest meaning

bootstrapの`plan_digest`が保証するのは、dry-runでreviewしたexact mutation planとapply時のmutation planが同一であることだけである。

planは最低限次へbindする。

```text
repository ID
base authoritative-ref head SHA
candidate policy bytes digest
candidate policy path
bootstrap audit record bytes digest
all planned file preimage digests
all planned file postimage digests
CLI contract version
```

`plan_digest`は次を保証しない。

- owner identityそのもの
- Policyの内容が妥当であること
- GitHubへのcommit / push / merge
- Policyのactive化
- execution authority

### 1.5 Bootstrap audit record

bootstrap applyは、candidate Policyと同時に次のGit-tracked audit recordを作る。

```text
.agent-experience/policy-receipts/bootstrap/<policy-revision-digest>.json
```

recordには次を保存する。

```json
{
  "schema_version": 1,
  "kind": "policy_bootstrap_request",
  "repository_id": 123456789,
  "repository_full_name": "owner/repository",
  "owner_login": "owner",
  "owner_id": 12345,
  "authenticated_login": "owner",
  "authenticated_user_id": 12345,
  "policy_id": "...",
  "policy_revision_digest": "sha256:...",
  "base_authoritative_head": "...",
  "plan_digest": "sha256:...",
  "provider_result_digests": ["sha256:..."],
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "cli_contract_version": 1
}
```

credential、token、cookie、raw GitHub responseは保存しない。

このaudit recordは暗号署名ではない。同一OS userまたは同じGitHub credentialを奪取した攻撃者に対する真正性は主張しない。

### 1.6 When the bootstrap Policy becomes active

bootstrap apply直後のPolicyはcandidateであり、activeではない。

active Policyとして使用できるのは、次をすべてcurrent read-only evidenceで確認した後だけとする。

```text
Policy file exists on configured authoritative ref
bootstrap audit record exists on the same authoritative ref
Policy digest matches the audit record
repository binding matches
current authenticated repository metadata still identifies the same personal owner
Policy schema and digest are valid
```

bootstrap audit record単独、working tree上のPolicy、Draft branch上のPolicy、local SQLite receiptだけではactiveにしない。

### 1.7 Later verification

後続agentはactive Policyを使う前に、Policyとbootstrap audit recordをauthoritative refから再取得またはcurrent blob SHAへbindして検証する。

verification result:

```text
active
candidate
invalid
bootstrap_unverified
unavailable
```

### 1.8 Bootstrap Policy as an accepted artifact

bootstrap Policyは、自分自身をaccepted artifactとして自己承認しない。

bootstrap Policyのactive化は§1.6のbootstrap ruleで行う。active化後のPolicy revisionから、通常のpredecessor-governed change ruleを使う。

Policy自体を一般artifact一覧へ含める場合でも、そのaccepted statusはbootstrap trust rootの代替にならない。

---

## 2. Policy location and repository binding

### 2.1 Per-target-repository Policy

Acceptance PolicyはSkill配布repositoryではなく、**Policyを適用するtarget repository自身**に置く。

```text
<target-repository>/.agent-experience/acceptance-policy.json
```

`agent-experience` Skillのinstalled copyは、current Git rootからtarget repositoryを解決し、そのrepositoryのtracked Policyだけを読む。

### 2.2 Skills repository

`kazu02210679/skills` repository自身にAcceptance Policyが必要なのは、同repositoryを`agent-experience`で初期化し、そのrepository内のartifact acceptanceを評価する場合だけである。

Skillを配布するrepositoryであること自体は、全target repositoryへ適用されるglobal Policyを意味しない。

### 2.3 Cross-repository Policy references

v1ではcross-repository Policy referenceを禁止する。

```text
Policy repository ID == current target repository ID
```

を必須とする。

別repositoryのPolicyをinclude、extend、inherit、URL参照する機能は非対象とする。

共通Policy templateを使う場合は、各target repositoryへ明示的にmaterializeし、個別repository IDとdigestを持たせる。

---

## 3. Content binding mode selection

### 3.1 `exact_blob`

次のartifactで使用する。

- security policy
- governance contract
- authority boundary
- release / deployment contract
- frozen requirements
- exact accepted specificationとして固定する必要がある文書

Policyに`expected_blob_sha`を保持する。

artifact内容が変わる場合、Policy revisionまたは同等のpredecessor-governed artifact-binding updateが必要である。

利点:

- accepted contentを一意に固定できる。

欠点:

- artifact更新ごとにbinding updateが必要になる。

### 3.2 `authoritative_ref_current`

継続更新される次のartifactで使用できる。

- living documentation
- operational notes
- generated catalog
- current provider matrix
- content自体をSHA固定せず、current authoritative stateを毎回評価したい文書

Policy revisionなしでartifact内容を更新できるが、accepted resultは毎回次へbindし直す。

```text
authoritative head SHA
current target blob SHA
provenance PR / commit
required review state
required check state
```

accepted resultはcurrent headが動いた時点で再評価対象になる。

### 3.3 Closed selection rule

Policy authorはartifactごとにmodeを明示し、省略を許可しない。

```text
security / governance / authority affecting
  -> exact_blob required

otherwise
  -> exact_blob or authoritative_ref_current
```

`authoritative_ref_current`を使ってsecurity / governance artifactのbinding updateを回避することを禁止する。

---

## 4. Accepted artifact commit graph

### 4.1 Canonical SHA roles

次を別fieldとして保持し、`commit_sha`という一語へまとめない。

```text
pr_head_sha
pr_test_merge_sha
pr_merge_result_sha
authoritative_head_sha
artifact_blob_sha
artifact_introducing_commit_sha
validation_sha
```

定義:

- `pr_head_sha`: current PR source branch head。
- `pr_test_merge_sha`: merge前にGitHubが計算するtest merge commit SHA。
- `pr_merge_result_sha`: merge後のGitHub `merge_commit_sha`。merge / squash / rebase methodにより意味は異なるが、base branchへ反映されたresult commitを表す。
- `authoritative_head_sha`: current authoritative ref head。
- `artifact_blob_sha`: authoritative ref上のtarget file blob SHA。
- `artifact_introducing_commit_sha`: authoritative historyでcurrent target blobを導入したcommit。決定できない場合は`unknown`。
- `validation_sha`: required pre-merge checkを評価するSHA。

### 4.2 Proposal-stage predicates

required PR reviewはcurrent `pr_head_sha`へbindする。

required pre-merge checkの`validation_sha`は次で決める。

```text
if GitHub reports applicable check/status results on pr_test_merge_sha:
    validation_sha = pr_test_merge_sha
else:
    validation_sha = pr_head_sha
```

古いPR headのreviewまたはcheckはcurrent proposal predicateを満たさない。

### 4.3 Integration-stage predicates

PR merge後は次をすべて確認する。

```text
PR merged == true
pr_merge_result_sha is known
pr_merge_result_sha is equal to or an ancestor of authoritative_head_sha
artifact exists on authoritative ref
artifact_blob_sha satisfies the configured content binding
```

merge methodがmerge / squash / rebaseのどれであっても、GitHubがmerge後に返す`pr_merge_result_sha`をresult commitとして扱い、単純にPR head SHAとの同一性を要求しない。

### 4.4 Check phases

required check entryはphaseを必須とする。

```json
{
  "name": "validate-foundation",
  "app_id": null,
  "phase": "pre_merge",
  "allowed_conclusions": ["success"]
}
```

allowed phase:

```text
pre_merge
post_merge_authoritative_head
post_merge_result
```

- `pre_merge`: §4.2の`validation_sha`。
- `post_merge_authoritative_head`: current `authoritative_head_sha`。
- `post_merge_result`: `pr_merge_result_sha`。

phase省略、複数候補からの暗黙選択を禁止する。

### 4.5 Accepted result evidence

accepted-artifact resultは各predicateについて、使用したSHA、observation ID、observation digestを列挙する。

```json
{
  "predicate": "required_check:validate-foundation",
  "phase": "pre_merge",
  "target_sha": "...",
  "observation_id": "...",
  "observation_digest": "sha256:...",
  "result": "pass"
}
```

---

## 5. Remote evidence provenance and `remote observe`

### 5.1 Provenance classes

Remote Observationは次のprovenance classを必須とする。

```text
builtin_refresh
untrusted_import
test_fixture
```

### 5.2 `builtin_refresh`

built-in GitHub Providerが、同一CLI process内でread-only fetch、normalization、digest計算を行い、直接storeへ渡したresult。

current-use evidence、accepted-artifact predicate、remote-dependent checkpoint判定に使用できるのは、このclassだけである。

さらに次へbindする。

```text
provider adapter contract version
refresh_run_id
use_context_id
repository binding
resource key
provider_result_digest
state_digest
```

### 5.3 `untrusted_import`

`remote observe`が外部fileまたはstdinから受け取るnormalized result。

用途:

- historical note
- migration input
- manual comparison
- external adapter evaluation

禁止用途:

- current remote stateの確定
- accepted-artifact predicate
- auto-resume
- Policy bootstrap identity
- promotion evidenceのcurrent validation

schemaとdigestが正しくても、source authenticityを証明しない。

### 5.4 `test_fixture`

focused testsとevalだけで利用する。

production runtimeで`test_fixture`を作成するflag、environment switch、config keyを提供しない。

### 5.5 `remote observe` command

productionの`remote observe`はproviderを呼ばず、全入力を`untrusted_import`として保存する。

`remote refresh`は`remote observe` commandをsubprocess経由で呼ばず、built-in provider resultを内部APIで直接`builtin_refresh`としてstoreする。

### 5.6 Sealing does not upgrade provenance

`untrusted_import`を`seal`しても`builtin_refresh`にはならない。

provenance classはimmutableであり、seal、commit、authoritative-ref到達、record rankingによって昇格しない。

---

## 6. `seal` semantics

### 6.1 Meaning

`seal`は次だけを保証する。

- closed schema valid
- path valid
- resource limits valid
- secret / local-path gate pass
- canonical record digest valid
- immutable shared-record fileがworking treeへexclusive createされた

`seal`は次を保証しない。

- content truth
- current evidence
- human approval
- accepted artifact status
- repository authority
- Git commit inclusion
- authoritative ref inclusion
- promotion / adoption

### 6.2 Who may seal

local repository write accessを持ち、explicit commandを実行できるactorはsealを要求できる。

actor categoryはaudit fieldとして記録できるが、自己申告された`human`をauthorityとして扱わない。

### 6.3 Trust tiers

| Tier | Location | Meaning | Current evidence / acceptance use |
|---|---|---|---|
| pending local | SQLite | unsealed candidate | No |
| local normalized observation | SQLite | local provider/import result | `builtin_refresh` + current use-context only |
| sealed working-tree record | `.agent-experience/records/` | structurally immutable local artifact | No |
| committed branch record | Git commit on any branch | shared historical advisory record | No current-state authority |
| authoritative-ref record | authoritative ref | canonical shared historical record | No current-state authority by itself |
| adopted knowledge | valid promotion projection | reviewed instruction candidate reflected elsewhere | Still not execution authority |

### 6.4 Remote evidence

accepted-artifact evaluationはsealed recordの存在ではなく、current `builtin_refresh` observationとactive Policyを使用する。

---

## 7. Effective review semantics

### 7.1 COMMENTED does not revoke approval

同じreviewerが`APPROVED`後に`COMMENTED` reviewを投稿しても、COMMENTEDだけでは既存approvalを無効化しない。

以前の「latest submitted reviewを無条件に採用する」ruleを廃止する。

### 7.2 Decision-review sequence

reviewerごとに次を行う。

1. malformed / pending reviewを除外する。
2. dismissed reviewをreview IDで無効化する。
3. `APPROVED`と`CHANGES_REQUESTED`だけをdecision reviewとして抽出する。
4. `submitted_at`、次にreview IDで最後のdecision reviewを選ぶ。
5. COMMENTEDはaudit / discussionとして保持するがdecision stateを変更しない。

### 7.3 Predicate result

| Effective decision | Predicate |
|---|---|
| current-head `APPROVED` | pass |
| `CHANGES_REQUESTED` | fail |
| approval on old head when head binding required | pending |
| decision reviewなし | pending |
| dismissal / malformed relation ambiguity | unknown |

後のAPPROVEDは以前のCHANGES_REQUESTEDをsupersedeできる。

### 7.4 Repository-rule scope

v1はGitHub branch protection / ruleset全体を複製しない。

Acceptance Policyが次を明示する。

```text
bind_to_current_head
require_distinct_author_and_reviewer
require_last_push_approval
```

GitHub上のmerge readinessそのものを完全再現したと主張しない。

---

## 8. Required check target semantics

### 8.1 Check run key

required checkは次へbindする。

```text
check name
GitHub App ID or explicit null policy
target SHA
phase
```

### 8.2 Latest run selection

同じkeyとtarget SHAに複数check runがある場合、`started_at`、次にcheck run IDで最新を選ぶ。

### 8.3 No cross-SHA reuse

次を禁止する。

- old PR headのsuccessをcurrent PR headへ使用
- pre-merge successをpost-merge authoritative-head checkへ使用
- merge-result successを別のauthoritative headへ使用
- same check nameだけで異なるAppのresultを混同

### 8.4 GitHub-required status compatibility

`pre_merge` phaseでは§4.2のtest-merge/head resolutionを使用する。

`neutral`と`skipped`はGitHub上でmergeを妨げない場合があるが、Agent Experience Policyのdefault allowed conclusionは`success`だけとする。Policyが明示した場合だけ`neutral`または`skipped`を許可する。

---

## 9. Remote freshness and TOCTOU

### 9.1 No remote lock claim

GitHub remote stateをlockできないため、race-freeなfreshnessを主張しない。

`fresh`の意味は次だけである。

```text
state was observed successfully for this use-context at observed_at
```

### 9.2 Separate refresh is insufficient for resume

過去に実行した`remote refresh` receiptだけではauto-resumeしない。

remote-dependent resume判定は、単一のexplicit CLI command内で次を行う。

```text
fetch current remote dependencies
-> normalize and validate
-> compare with checkpoint dependencies
-> create use_context_id
-> decide resume eligibility
-> commit local resume/start decision
```

network fetch中はSQLite write transactionを保持しない。fetch完了後、short `BEGIN IMMEDIATE` transactionでobservationとdecisionを一緒にcommitする。

### 9.3 Residual race

GitHub stateはprovider response後に変わり得る。このresidual raceを消したとは主張しない。

次のboundaryで再検証する。

- remote current-state claimを再表示するとき
- accepted-artifactを再評価するとき
- checkpointを再度close / publishするとき
- 外部write workflowへ引き渡す直前。外部workflow側の責務

### 9.4 `use_context_id`

resume decision、remote observations、refresh runを同じ`use_context_id`へbindする。

別use-contextのfresh observationを暗黙再利用しない。

---

## 10. Manual review receipt

### 10.1 v1 removal

自由形式またはlocal JSONのmanual review receiptで`manual_review_compatible` checkpointを同一workstreamとしてresumeする機能を、v1から削除する。

理由:

- actor authenticityを決定論的に検証できない。
- arbitrary JSONでauto-resume gateを迂回できる。
- same-checkpoint current-state claimを復活させる必要性が低い。

### 10.2 Allowed continuation

`manual_review_compatible`、`stale`、`changed`、`unknown`、`unavailable`、`pending`の場合、継続は次だけとする。

```text
agent-experience start --from-checkpoint <id> --stable-only --json
```

新しいsuccessor workstreamを作り、current-state claimは引き継がない。

### 10.3 Future extension

trusted outer controllerがverifiable approval receiptを提供する場合のsame-checkpoint explicit resumeはv1非対象とし、別設計とする。

---

## 11. Stable-only dependency closure

### 11.1 Empty dependency list is not proof

`remote_dependency_ids=[]`だけでstableと判定しない。

### 11.2 Eligible categories

stable-only移行候補:

```text
stable_decision
do_not_redo
failed_approach
verified_or_adopted_knowledge_reference
```

次は移行しない。

```text
current_state
open_work
next_action
unverified observation
free-text-only assertion
```

### 11.3 Recursive closure

候補itemについて、参照recordと次のrelationをrecursiveに検証する。

```text
depends-on
premise
supports
applies-to
resolved-by
```

closed traversal limit:

```text
max depth = 8
max visited records = 128
```

次のいずれかがあれば除外する。

- mutable remote dependency
- stale / contested / superseded / deprecated / invalid record
- current artifact digest mismatch
- unresolved premise
- unknown relation target
- traversal limit超過

### 11.4 Stability classes

projectionは次を算出する。

```text
immutable_stable
scope_revalidated
remote_bound
unknown_stability
ineligible
```

stable-onlyへ移せるのは`immutable_stable`またはcurrent scope validationを通った`scope_revalidated`だけである。

---

## 12. Storage and evidence boundary

| Object | Canonical location | Default lifetime | Rebuildable | Audit use | Current-state / accepted use |
|---|---|---:|---|---|---|
| pending record | local SQLite | unresolvedは自動削除なし | No | local only | No |
| unsealed `builtin_refresh` observation | local SQLite | 90 days、active dependencyはpin | No | Yes | same use-context only |
| untrusted import observation | local SQLite | 90 days | No | historical only | No |
| refresh receipt | local SQLite | 90 days | Partly | Yes | receipt単独ではNo |
| sealed record | target repo working tree | Git管理へ移るまで | No | Yes | No |
| committed shared record | Git object | Git history | Yes from Git | Yes | historical advisory only |
| authoritative shared record | authoritative ref | Git history | Yes | Yes | historical advisory only |
| record index / FTS | local SQLite | rebuildable | Yes | No | candidate retrieval only |
| projection cache | local SQLite | rebuildable | Yes | No | recompute required |
| installer manifest | local Git common dir | uninstall完了まで | No | Yes | No |

shared Git-tracked recordをautomatic GCで削除しない。

---

## 13. SQLite concurrency contract

### 13.1 General

- DBはGit common directoryごとに一つ。
- 全rowを`repo_id`でnamespaceする。
- workstream / checkpointは`worktree_id`へもbindする。
- `foreign_keys=ON`。
- WALを利用可能なplatformではWALを使用し、不可能な場合はdocumented fallbackを使う。
- default `busy_timeout=750ms`。

### 13.2 Transaction boundaries

| Operation | Transaction |
|---|---|
| Hook idempotency claim | single short write transaction |
| checkpoint save/update | `BEGIN IMMEDIATE` + optimistic revision compare |
| refresh network fetch | no DB write transaction held |
| refresh result commit | short `BEGIN IMMEDIATE` transaction |
| index rebuild | shadow generation + atomic active-generation switch |
| recall | read transaction pinned to one active generation |
| GC apply | `BEGIN IMMEDIATE` + plan-digest recheck |

### 13.3 Concurrent checkpoint update

checkpoint rowはmonotonic `revision`を持つ。

updateはexpected revisionを必須とし、不一致は次で拒否する。

```text
checkpoint_revision_conflict
exit 5
```

last-write-winsを使用しない。

### 13.4 Duplicate refresh receipts

次のunique keyで収束させる。

```text
repo_id
resource_key_digest
provider_result_digest
use_context_id
```

### 13.5 Recall during reindex

recallは開始時にactive index generation IDを取得し、transaction終了まで同じgenerationを使用する。

途中で新generationがactivateされても、同一recall内で混在させない。

### 13.6 Lock timeout

- Hook: silent no-op、exit 0、model-visible outputなし。
- explicit read: degraded result、exit 3。
- explicit mutation: conflict、exit 5、no partial write。

raw exception、absolute path、record bodyをstderrへ出さない。

---

## 14. Instruction precedence and hard invariants

### 14.1 Prose instruction precedence

system / developer / user / repository instructionの競合はhostのinstruction hierarchyに従う。

ただし、次のclosed safety invariantは普通の自然言語指示で解除しない。

- Experienceはauthorityではない。
- Remote Providerはread-only。
- credential / secretを保存しない。
- forged / stale / unknown remote stateをcurrent factにしない。
- origin recordのself-declared promotionを拒否する。
- exactでないcheckpointをauto-resumeしない。
- Hook hot pathからnetworkを呼ばない。
- `seal`はGit publicationを行わない。
- integrity uncertainty時のshared/config mutationはfail closed。

### 14.2 Policy changes

Policyまたはsafety boundaryを変更する要求は、自然言語で直接上書きせず、designated Policy / specification change workflowへrouteする。

### 14.3 User authority

ユーザーはtask scopeを変更し、明示操作を承認できる。ただし、system/developer instruction、platform capability、closed integrity contractを越える自己申告authorityを生成できない。

---

## 15. Automatic trigger mechanism and guarantees

### 15.1 Mechanisms

supported setupでは次を組み合わせる。

1. active global / project `AGENTS.md` managed routing block。
2. `SessionStart` fixed route-only notice。
3. Skill `description` matchingによるimplicit discovery。
4. explicit user invocation。

### 15.2 Primary trigger

非自明なrepository workのprimary semantic triggerは、active repository / global instructionから`agent-experience` Skillを読み、explicit `preflight`を実行するagent behaviorである。

Hookはmemoryを実行するcontrollerではなく、固定routing reminderである。

### 15.3 CLI limitation

CLIはagentが呼ぶまで自律起動しない。v1はOS-level wrapperまたはmandatory controllerとして全編集をinterceptしない。

したがって次を主張しない。

```text
100% of non-trivial tasks mechanically run preflight
```

正確なclaim:

```text
supported host setup makes preflight the default instructed workflow;
compliance is measured and enforced at subsequent agent-experience commands,
but arbitrary tool use outside the workflow cannot be prevented by v1.
```

### 15.4 Omission detection

`start`、`checkpoint`、`capture`、`seal`はcurrent workstreamのvalid preflight receiptを要求する。

receiptなしの場合:

```text
preflight_required
```

を返す。

ただしagentがAgent Experience CLIを一切使わずにrepositoryを編集した事実を、v1は完全には検出できない。

Task 1 / Task 28でimplicit trigger success rateとpreflight omissionを測定する。

より強いmechanical enforcementは別controller / wrapper設計とする。

---

## 16. Review severity and closure authority

### 16.1 Severity

#### Critical

次のいずれか。

- authority / permission bypass
- secret / credential exposure
- forged or stale stateをcurrent evidenceとして使用
- non-exact checkpoint auto-resumeによるstate corruption
- remote write capabilityの混入
- Hook context privilege escalation
- installer / uninstallによるoperator file clobber
- Policy self-approval / bootstrap trust-root bypass

#### Important

次のいずれか。

- deterministic state / schema ambiguity
- accepted-artifactの誤分類
- recovery / concurrency defectでmaterial stateを誤る
- Windows / Linuxのsupported behavior不一致
- unbounded resource consumption
- audit provenance欠落により誤判断を誘発
- trigger / lifecycleが設計上の主目的を安定して満たさない

#### Minor

- user-facing clarity
- non-material documentation issue
- cosmetic / naming inconsistency
- safe workaroundが明確な低影響問題

### 16.2 Finding record

各findingは次を持つ。

```text
finding_id
severity
contract section
evidence locator
reproduction or counterexample
required correction
owner
disposition
verification evidence
independent reviewer
repository owner acceptance
```

### 16.3 Closure

- authoring agentはCritical / Importantを単独でcloseしない。
- fresh independent reviewerがcorrectionとtestsを確認する。
- repository ownerがfinal design acceptanceを行う。
- unresolved / disputed findingはclosedとして数えない。

「Critical / Importantなし」は、全finding IDがverified closedまたはreasoned rejectedになった後だけ宣言する。

---

## 17. Implementation and Policy bootstrap order

### 17.1 Task 1 first

Task 1 RED behavioral baselineをPolicy bootstrapより先に実行する。

理由:

- Task 1はSkill / Policyがないbaseline behaviorを測る。
- bootstrap implementationはまだ存在しない。
- initial Policyを先に置くとbaselineを汚染する。

### 17.2 Bootstrap implementation

Policy schema、digest、provider identity、bootstrap command、accepted-artifact evaluatorはTask 20で実装する。

Task 20がGREENになる前にreal target repositoryをbootstrapしない。

### 17.3 Actual bootstrap

実repositoryのbootstrapは次の後に行う。

```text
Task 20 focused tests GREEN
Remote Core gate GREEN
independent review of bootstrap contract complete
explicit repository-owner action
```

pilot fixture repositoryのbootstrapはTask 28準備として行える。

`skills` repository自身は、Skill実装のためだけにはPolicy bootstrapを必要としない。

---

## 18. Binding Task amendments

本節は第二の実装計画ではない。Contract Indexが指すConsolidated Planのacceptance criteriaを追加する。

### Task 1

- bootstrapなしでRED baselineを実行する。
- preflight omission、forged bootstrap、manual receipt bypass、untrusted observe、seal-as-authorityのpressure caseを追加する。

### Task 2

Skill contractへ次を追加する。

```text
manual review receipt cannot resume a checkpoint in v1
remote observe imports are historical untrusted data
seal proves structure, not truth or authority
Policy is per target repository
hard safety invariants are not overridden by ordinary prose
```

### Task 4

config schemaへ次を追加する。

- target repository binding
- Policy pathはcurrent repository relative
- cross-repository Policy reference禁止
- personal-owner bootstrap support flagはruntime-derivedでありconfig自己申告不可

### Task 7

store testsへ次を追加する。

- checkpoint optimistic revision
- refresh receipt unique key
- index generation pinning
- network fetch中にwrite lockを保持しない
- lock-timeout exit mapping

### Task 10 / 11

record contractへ次を追加する。

- provenance class
- sealed stateとGit locationを別fieldで表す
- sealでprovenance / trustが昇格しない
- remote-state imported recordはaccepted evidence不可

### Task 13

stable-only recursive dependency closureとstability classを追加する。

### Task 18

remote coreへ次を追加する。

- provider payload / result / state / record digest分離
- provenance class
- `use_context_id`
- state profiles
- untrusted import exclusion

### Task 19

GitHub Providerへ次を追加する。

- personal owner identity fields
- authenticated actor identity fields
- repository admin permission observation
- PR test-merge SHAとpost-merge result SHAのstate profile
- raw payload digestはmemory内計算のみ

### Task 20

Acceptance / Policyへ次を追加する。

- bootstrap trust-root contract
- per-target-repository Policy
- bootstrap audit record
- content binding selection gate
- proposal / integration stage predicates
- check phase and validation SHA
- COMMENTED does not revoke APPROVED
- Policy self-approval prohibition

### Task 21

- same-checkpoint manual resumeとreview JSONを削除する。
- remote-dependent continuationはsame-command refresh-and-decideを使う。
- non-exact continuationはstable-only successorだけ。
- ambiguous checkpointはauto-resumeしない。

### Task 22

- Hook no-network AST/import testsを維持する。
- Hookはpreflight completionを偽らない。

### Task 25

README / referencesへstorage trust-tier table、trigger guarantees、hard invariants、TOCTOU residual raceを明記する。

### Task 27

Linux / WindowsでSQLite concurrency、shadow index switch、parallel Hook、fake provider race fixtureを追加する。

### Task 28

pilot hard-stopへ次を追加する。

- forged bootstrap accepted
- manual receipt same-checkpoint resume
- untrusted observe used as current evidence
- seal treated as truth / authority
- APPROVED followed by COMMENTED becomes pending
- wrong check target SHA accepted
- remote refresh result reused across a different use-context
- concurrent checkpoint lost update
- implicit trigger omission without detection

---

## 19. Additional acceptance conditions

- automatic bootstrap is limited to GitHub.com personal-account repositories.
- bootstrap trust root binds repository numeric ID、owner numeric ID、authenticated actor numeric ID、admin permission。
- `plan_digest` is not described as identity or approval proof.
- Policy is read only from the current target repository; cross-repository inheritance is absent.
- security / governance artifacts require `exact_blob`.
- accepted-artifact evaluation exposes all SHA roles and check phases.
- `remote observe` imported data cannot satisfy current evidence or accepted predicates.
- `seal` never upgrades truth, provenance, acceptance, or authority.
- COMMENTED after APPROVED does not revoke the approval.
- auto-resume uses same-command refresh-and-decide and documents residual TOCTOU.
- manual JSON review receipt cannot resume a checkpoint in v1.
- stable-only reuse validates recursive dependencies.
- storage tiers and lifetime are documented and tested.
- concurrent checkpoint update uses optimistic conflict detection.
- recall pins one index generation.
- natural-language instruction cannot disable closed safety invariants.
- implicit trigger is described as instructed default, not perfect mechanical enforcement.
- Critical / Important closure requires independent verification and repository-owner acceptance.
- Task 1 precedes Policy bootstrap.

## 20. References

- `docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md`
- `docs/superpowers/specs/2026-08-22-agent-experience-open-questions-clarification.md`
- `docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md`
- GitHub REST API endpoints for pull requests
- GitHub documentation: troubleshooting required status checks
- GitHub documentation: protected branch approval behavior
