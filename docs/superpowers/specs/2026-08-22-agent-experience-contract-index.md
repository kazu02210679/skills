# Agent Experience Skill — Contract Index

- **文書日**: 2026-08-22
- **対象**: `agent-experience` v1
- **状態**: Binding contract index

## 1. 目的

本書は、`agent-experience` v1の設計契約を読むための**唯一の規範的入口**である。

```text
canonical entry point
  = this Contract Index

binding contract corpus
  = this indexが列挙する全設計文書

active implementation plan
  = this indexが指定する一つの計画書
```

本書は全仕様本文を複製した合成文書ではない。文書の読み順、適用domain、競合解消、実装計画、hard gateを一意に固定する。

## 2. Binding documents

実装者は次をすべて読む。

1. `docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md`
2. `docs/superpowers/specs/2026-08-22-agent-experience-trust-roots-runtime-clarification.md`
3. `docs/superpowers/specs/2026-08-22-agent-experience-open-questions-clarification.md`
4. `docs/superpowers/specs/2026-08-22-agent-experience-remote-state-amendment.md`
5. `docs/superpowers/specs/2026-08-21-agent-experience-skill-normative-contract.md`
6. `docs/superpowers/specs/2026-08-21-agent-experience-skill-adversarial-amendment.md`
7. `docs/superpowers/specs/2026-08-21-agent-experience-skill-design.md`

## 3. Precedence

文書が競合する場合、次を適用する。

```text
system / developer / user instruction under the host hierarchy
  > active repository instruction
  > this Contract Index
  > Trust Roots and Runtime Semantics Clarification, listed domains
  > Open Questions Clarification Contract, listed domains
  > Remote-State Amendment, remote-state domain only
  > Normative Runtime Contract
  > Adversarial Review Amendment
  > Base Design
```

### 3.1 Domain of the Trust Roots clarification

次を上書きまたは拡張する。

- Policy bootstrap trust root
- Policy repository binding
- content-binding selection
- accepted-artifact SHA graph
- remote observation provenance
- `seal` semantics
- effective review state
- required-check target SHA
- remote freshness TOCTOU
- same-checkpoint manual resume
- stable-only dependency closure
- storage tier
- SQLite concurrency
- instruction / hard safety boundary
- automatic trigger guarantee
- severity / review closure
- Task 1とPolicy bootstrapの順序

### 3.2 Conflict rule

同じ優先順位内で二つの要求を同時に満たせない場合、実装を開始しない。追加clarificationを作成して矛盾を閉じる。

---

## 4. Consolidated decisions

### 4.1 Automatic lifecycle and triggering

- v1でinstallできるCodex Hookは`SessionStart`、`PreCompact`、`PostCompact`、`SessionEnd`だけ。
- `UserPromptSubmit`をinstallしない。
- Hookはroute-onlyであり、record、checkpoint本文、remote state、user prompt、transcriptをmodel-visible contextへ注入しない。
- model-visible outputを返せるのは`SessionStart`の固定routing noticeだけ。
- Hookはdynamicな`refresh_required`、checkpoint status、remote stateを返さない。
- Hook hot pathはnetwork、LLM、shared scan、FTS recall、reindex、Git mutation、remote refresh、`seal`、`promote`、`gc`を実行しない。
- `refresh_required`はexplicit `preflight --json`または`remote status --json`で返す。

supported setupは次を組み合わせる。

```text
active AGENTS managed routing block
+ fixed SessionStart routing notice
+ Skill description matching
+ explicit invocation
```

これによりpreflightをdefault instructed workflowにするが、v1は任意のtool useをOS-levelでinterceptしない。100%のmechanical invocationを主張しない。

`start`、`checkpoint`、`capture`、`seal`はvalid preflight receiptを要求し、欠落時は`preflight_required`を返す。

### 4.2 Local checkpoint and continuation

local auto-resumeにはNormative Runtime Contractのexact identity / snapshot条件をすべて必要とする。

さらに候補checkpointが一意でなければならない。

```text
multiple exact candidates
  -> ambiguous_checkpoint
  -> auto_resume=false
```

remote dependencyがある場合、同一explicit resume/start command内でcurrent refreshとdecisionを行い、次をすべて必要とする。

```text
local classification == exact
candidate selection is unique
all remote dependencies refreshed in the current use-context
all remote repository bindings valid
all decision-relevant state digests unchanged
all acceptance-policy revisions unchanged
```

result:

- dependency未refresh: `refresh_required`
- provider failure: `unknown`または`unavailable`
- state changed: `changed`
- repository binding mismatch: `stale`
- Policy revision changed: `pending`

### 4.3 No same-checkpoint manual resume in v1

自由形式またはlocal JSONのmanual review receiptで`manual_review_compatible` checkpointをresumeする機能をv1に含めない。

non-exact continuationは次だけとする。

```text
agent-experience start --from-checkpoint <id> --stable-only --json
```

新しいsuccessor workstreamを作り、current-state claimを引き継がない。

stable-only reuseは参照recordのrecursive dependency closureを検証する。free textまたはempty dependency listだけをstableの証拠にしない。

### 4.4 Acceptance Policy repository boundary

Policyはtarget repository自身のtracked fileとして保存する。

```text
<target-repository>/.agent-experience/acceptance-policy.json
```

- Policy repository IDはcurrent target repository IDと一致しなければならない。
- Skill配布repositoryのPolicyをglobal Policyとして使わない。
- cross-repository include / inherit / URL referenceをv1で許可しない。
- `skills` repository自身のPolicyは、同repositoryを個別targetとして初期化する場合だけ必要である。

### 4.5 Policy bootstrap trust root

v1 automatic bootstrapはGitHub.comのpersonal-account-owned repositoryだけを対象とする。

owner identityはread-only GitHub repository metadataのnumeric repository ID、owner login、owner numeric ID、owner typeへbindする。

current authenticated actorはGitHub user numeric IDとloginの両方がownerと一致し、repository admin permissionを持つ必要がある。

bootstrap applyには次のいずれかを必要とする。

- interactive human confirmation of exact repository full name and Policy digest
- trusted outer-controller user-approval receipt bound to repository ID、owner ID、Policy digest、plan digest

自己申告の`human` fieldまたは自由形式JSONだけでは実行しない。

`plan_digest`はreview済みmutation planとapply時のmutation planが同一であることだけを保証し、identity、approval、Policy validity、Git publicationを保証しない。

bootstrap applyはcandidate PolicyとGit-tracked audit recordを作るが、直後にactiveとはしない。

active化には、Policyとaudit recordがauthoritative ref上に存在し、digest / repository / owner bindingがcurrent read-only evidenceで有効であることを必要とする。

organization-owned repository等は`bootstrap_manual_governance_required`へ降格する。

### 4.6 Content binding modes

allowed mode:

```text
exact_blob
authoritative_ref_current
```

- security、governance、authority、release、frozen requirement artifactは`exact_blob`必須。
- living documentation等は`authoritative_ref_current`を選択できる。
- mode省略を許可しない。
- `authoritative_ref_current`はPolicy revisionなしでcontent更新できるが、accepted resultをcurrent head / blob / provenance / review / checksへ毎回bindし直す。

### 4.7 Record, provenance, and `seal`

origin recordはclosed `initial_status`だけを持つ。`effective_status`はvalidated transitionとprojectionから導出する。

Remote Observation provenance class:

```text
builtin_refresh
untrusted_import
test_fixture
```

- current-use evidence、accepted-artifact predicate、remote-dependent resumeに使えるのはcurrent use-contextの`builtin_refresh`だけ。
- production `remote observe`の外部inputは`untrusted_import`であり、historical useだけ。
- `test_fixture`はtest runtimeだけ。
- `seal`、commit、authoritative-ref到達によってprovenance classは昇格しない。

`seal`が保証するのはschema、path、resource、secret gate、canonical digest、exclusive file creationだけである。

`seal`はtruth、current evidence、human approval、accepted status、Git commit inclusion、authorityを保証しない。

### 4.8 Storage tiers

| Tier | Canonical location | Meaning |
|---|---|---|
| pending local | SQLite | unsealed candidate |
| normalized remote observation | SQLite | provenance-bound local evidence/import |
| refresh receipt | SQLite | fetch audit, not evidence by itself |
| sealed record | target working tree | structurally immutable local artifact |
| committed shared record | Git object | historical advisory record |
| authoritative shared record | authoritative ref | canonical historical advisory record |
| derived index / projection cache | SQLite | rebuildable, not source of truth |

Git-tracked shared recordsはautomatic GCで削除しない。

### 4.9 Remote digests and freshness

次を分ける。

```text
provider_payload_digest
provider_result_digest
state_digest
record_digest
```

`changed`とcheckpoint compatibilityにはresource-specific decision stateの`state_digest`を使用する。

`fresh`は、そのuse-contextにおいて`observed_at`時点で成功裏に観測されたことだけを意味する。remote stateをlockしたことを意味しない。

remote-dependent continuationではseparate old refresh receiptを再利用せず、same-command refresh-and-decideを行う。

residual TOCTOUは残るため、current-state再表示、accepted-artifact再評価、checkpoint close / publication、外部write workflowへの引渡し前に再検証する。

### 4.10 Remote result taxonomy

```text
refresh_required
fresh
changed
unknown
unavailable
superseded
```

- `unknown`: provider callは完了したがcurrent stateを安全に一意決定できない。
- `unavailable`: provider call自体を実行または完了できない。
- 404だけを根拠にresource不存在または`not_accepted`と断定しない。
- old observation + failed refreshをcurrent factへ昇格させない。

### 4.11 GitHub Provider v1

- GitHub.com read-only adapterだけ。
- built-in implementationはexisting authenticated `gh api`をshell-free GET-only argvで呼ぶ。
- version番号だけでなくcapability gateを使う。
- GHES / GHE.com custom hostは`host_unsupported`。
- raw provider body、credential、token、cookie、credential-bearing URLを保存しない。
- provider command surfaceにwrite verbを含めない。

### 4.12 Accepted artifact SHA graph

次を別fieldとして保持する。

```text
pr_head_sha
pr_test_merge_sha
pr_merge_result_sha
authoritative_head_sha
artifact_blob_sha
artifact_introducing_commit_sha
validation_sha
```

proposal-stage reviewはcurrent PR headへbindする。

pre-merge required-check targetは次で解決する。

```text
if applicable checks/statuses exist on pr_test_merge_sha:
    validation_sha = pr_test_merge_sha
else:
    validation_sha = pr_head_sha
```

merge後は、`pr_merge_result_sha`がauthoritative headと同一またはancestorであり、authoritative ref上のartifact blobがcontent bindingを満たすことを検証する。

required check entryはphaseを必須とする。

```text
pre_merge
post_merge_authoritative_head
post_merge_result
```

### 4.13 Effective review semantics

COMMENTED reviewは既存APPROVEDまたはCHANGES_REQUESTED decisionを無効化しない。

reviewerごとにdismissed reviewを除外し、`APPROVED` / `CHANGES_REQUESTED`の最後のdecision reviewを選ぶ。

- current-head APPROVED: pass
- CHANGES_REQUESTED: fail
- old-head approval when binding required: pending
- no decision review: pending
- dismissal ambiguity: unknown

GitHub branch protection / ruleset全体を完全再現したとは主張しない。必要なreview semanticsはPolicyへ明示する。

### 4.14 Required checks

required checkはname、App ID policy、target SHA、phaseへbindする。

同じkeyとSHAの最新runを選び、異なるSHAまたはAppのresultを再利用しない。

`workflow_run`はdiagnosticであり、accepted predicateの正本は`check_run`とする。

default allowed conclusionは`success`だけ。`neutral` / `skipped`はPolicyが明示した場合だけ許可する。

### 4.15 SQLite concurrency

- one DB per Git common directory
- namespace by repo ID and worktree ID
- `foreign_keys=ON`
- WAL where supported
- `busy_timeout=750ms`
- checkpoint updateはoptimistic revision compare
- network fetch中にwrite transactionを保持しない
- refresh resultはshort `BEGIN IMMEDIATE` transactionでcommit
- reindexはshadow generation + atomic active-generation switch
- recallは一つのgenerationへpin
- Hook lock timeoutはsilent no-op
- explicit mutation lock timeoutはexit 5、partial writeなし

### 4.16 Instruction and hard safety boundary

host instruction hierarchyはprose conflictを解決する。

ただし普通の自然言語指示で次のclosed invariantを解除しない。

- Experience is not authority
- Remote Provider is read-only
- secret / credential persistence禁止
- stale / forged / unknown remote stateをcurrent factにしない
- self-declared promotion禁止
- non-exact auto-resume禁止
- Hook network access禁止
- `seal`によるGit publication禁止
- integrity uncertainty時のshared/config mutation fail-closed

Policy / safety boundary変更はdesignated change workflowを必要とする。

### 4.17 Canonical shared types and digests

```python
JSONScalar = str | int | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
```

- float、NaN、Infinity拒否
- object keyはUnicode code point lexical order
- normal arrayはorder保持
- schema-declared set-like arrayだけsort / deduplicate
- opaque path / IDへ暗黙Unicode normalizationをしない
- human-readable fieldはNFC inputを要求
- timestampはUTC `YYYY-MM-DDTHH:MM:SSZ`

Policy revision digestはtop-levelの同fieldを除外したcanonical Policy objectから計算する。

### 4.18 Review severity and closure

Critical:

- authority bypass
- secret exposure
- forged / stale current evidence
- non-exact state corruption
- remote write capability
- Hook privilege escalation
- installer clobber
- Policy self-approval / bootstrap bypass

Important:

- deterministic ambiguity
- accepted-artifact誤分類
- material recovery / concurrency defect
- supported-platform inconsistency
- unbounded resource consumption
- material audit gap
- trigger / lifecycleの主要目的不達

Critical / Importantはauthoring agentだけでcloseしない。fresh independent reviewerのverificationとrepository-owner acceptanceを必要とする。

### 4.19 Release milestones

```text
v0.1 Local Resume MVP       Tasks 1-9
v0.2 Memory Core            Tasks 10-17
v0.3 Remote Observation MVP Tasks 18-19
v0.4 Remote Governance      Tasks 20-21
v0.5 Automatic Lifecycle    Tasks 22-24
v1.0 Reviewed Rollout       Tasks 25-28
```

---

## 5. Active implementation plan

実装の正本は次だけとする。

```text
docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md
```

Trust Roots clarificationとOpen Questions clarificationのTask amendmentsは、この一つのConsolidated Planに対するbinding acceptance criteriaであり、第二の実装計画ではない。

旧計画はsupersededであり実行しない。

## 6. Phase order

```text
Phase 0  RED baseline and closed contracts
Phase 1  Manual local checkpoint MVP
Phase 2  Immutable shared records, projection, recall, feedback, retention
Phase 2.5  Remote-state core and GitHub read-only provider
Phase 3  Route-only Codex Hooks and conflict-safe installer
Phase 4  Final Skill workflow and read-only existing-Skill adapters
Phase 5  Cross-platform verification and pilot rollout gate
```

### 6.1 Hard gates

- Task 1 RED baselineをPolicy bootstrapより先に実行する。
- Task 20がGREENになる前にreal repository Policyをbootstrapしない。
- Phase 1完了前にHook installerを実装しない。
- forged-status、digest、prompt-injection、secret、staleness testsがGREENになる前にautomatic lifecycleを有効化しない。
- read-only allowlist、provenance、credential sanitation、freshness、provider-failure testsがGREENになる前にremote-dependent continuationを有効化しない。
- Hook moduleからprovider / network dependencyへ到達可能なimport pathを許可しない。
- existing-Skill adapterは外部authority、snapshot、gate、standalone behaviorを変更しない。

## 7. RED and pilot

REDは三層とする。

1. Task 1 behavioral baseline
2. each Taskのfocused RED/GREEN
3. Task 27 integration REDとTask 28 pilot gate

Task 28は次をhard-stopに含める。

- forged bootstrap accepted
- manual receipt same-checkpoint resume
- untrusted observe used as current evidence
- seal treated as truth / authority
- COMMENTED incorrectly revokes APPROVED
- wrong check target SHA accepted
- remote observation reused across different use-context
- concurrent checkpoint lost update
- implicit trigger omission without detection

## 8. Acceptance of this index

本書とbinding documentsの追加は、implementation完了、PR readiness、merge readinessを意味しない。

Task 1へ進む前に、全Critical / Important finding IDがfresh independent reviewでverified closedまたはreasoned rejectedとなり、repository ownerが設計契約をacceptする必要がある。
