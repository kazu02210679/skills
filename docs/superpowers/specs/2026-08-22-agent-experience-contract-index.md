# Agent Experience Skill — Contract Index

- **文書日**: 2026-08-22
- **対象**: `agent-experience` v1
- **状態**: Binding contract index

## 1. 目的

`agent-experience` の設計は、基礎設計、敵対的レビュー追補、Normative Runtime Contract、Remote Repository State追補、Open Questions Clarification Contractへ分割されている。本書は、それらを一つの実装契約として読むための唯一の入口、優先順位、結合規則を固定する。

本書はruntime機能を単独で定義する合成本文ではない。binding documents、適用domain、競合解消、active implementation planを一意に定めるcanonical entry pointである。

```text
canonical entry point
  = this Contract Index

binding contract corpus
  = this indexが列挙する全設計文書

active implementation plan
  = this indexが指定する一つの計画書
```

## 2. Binding documents

実装者は次をすべて読む。

1. `docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md`
2. `docs/superpowers/specs/2026-08-22-agent-experience-open-questions-clarification.md`
3. `docs/superpowers/specs/2026-08-22-agent-experience-remote-state-amendment.md`
4. `docs/superpowers/specs/2026-08-21-agent-experience-skill-normative-contract.md`
5. `docs/superpowers/specs/2026-08-21-agent-experience-skill-adversarial-amendment.md`
6. `docs/superpowers/specs/2026-08-21-agent-experience-skill-design.md`

## 3. Precedence

文書が競合する場合、次を適用する。

```text
current system / developer / user instruction
  > repository instruction
  > this Contract Index
  > Open Questions Clarification Contract, listed domains
  > Remote-State Amendment, remote-state domain only
  > Normative Runtime Contract
  > Adversarial Review Amendment
  > Base Design
```

Open Questions Clarification Contractは、Acceptance Policy、remote digests / taxonomy / resource semantics、review / check evaluation、checkpoint selection / resume、canonicalization、schema version、time、deduplication、Hook / CLI boundary、retention、implementation dependency、RED、pilot、release milestonesを閉じる。

Remote-State Amendmentは、上記clarificationで上書きされないremote repository observation、freshness、provider adapter、accepted artifact、remote-dependent checkpointを拡張する。

remote-state以外のcheckpoint、promotion、Hook、installer、retention、record projectionではNormative Runtime ContractとAdversarial Review Amendmentを優先する。ただしClarification Contractが明示的に列挙した項目はClarification Contractを優先する。

同じ優先順位内で二つの要求を同時に満たせない場合、実装を開始せず、設計追補を作成して矛盾を閉じる。

## 4. Consolidated decisions

### 4.1 Automatic lifecycle

- v1でinstallできるCodex Hookは`SessionStart`、`PreCompact`、`PostCompact`、`SessionEnd`だけ。
- `UserPromptSubmit`をinstallしない。
- Hookはroute-onlyであり、record、checkpoint本文、remote state、user prompt、transcriptをmodel-visible contextへ注入しない。
- model-visible outputを返せるのは`SessionStart`の固定routing noticeだけ。
- Hookはdynamicな`refresh_required`、checkpoint status、remote stateを返さない。
- Hook hot pathはnetwork、LLM、shared scan、FTS recall、reindex、Git mutation、remote refresh、`seal`、`promote`、`gc`を実行しない。
- remote stateが必要なtaskでは、Skillが通常のtool execution boundaryで明示的にread-only refreshを行う。
- `refresh_required`はexplicit `preflight --json`または`remote status --json`で返す。

### 4.2 Checkpoint compatibility

local checkpointのauto-resumeには、Normative Runtime Contractのlocal exact条件をすべて必要とする。

remote dependencyがあるcheckpointでは、さらに次をすべて必要とする。

```text
local classification == exact
candidate selection is unique
all remote dependencies refreshed for current use
all remote repository bindings valid
all decision-relevant state digests unchanged
all acceptance-policy revisions unchanged
```

一つでも満たさない場合、`auto_resume=false`とする。

- remote dependency未refresh: `refresh_required`
- provider failure: `unknown`または`unavailable`
- normalized decision state changed: `changed`
- repository binding mismatch: `stale`
- acceptance policy revision changed: `pending`
- multiple exact checkpoints: `ambiguous_checkpoint`

`auto_resume=false`は古いcurrent-state claimを明示overrideできるという意味ではない。

- `manual_review_compatible`かつremote dependenciesがfresh / unchangedなら、review receipt付きexplicit resumeを許可できる。
- stale / changed / unknown / unavailable / pendingでは同じcheckpointをcurrent stateとしてresumeしない。
- 継続する場合は`start --from-checkpoint <id> --stable-only`でsuccessor workstreamを作る。

古いcheckpointのstable Decision、`Do not redo`、failed approachは、immutable record reference、current scope / premise、remote impact scopeが有効な場合だけ再利用する。free textだけの記述を機械的にstableと扱わない。

### 4.3 Record and projection

- origin recordはclosed `initial_status`だけを持つ。
- `effective_status`はvalidated origin、promotion、relations、outcomes、stalenessからreplayする。
- `contested`はprojection-onlyであり、origin recordが自己申告できない。
- Remote ObservationはObservation subtype `remote-state`であり、過去時点の外部状態を表す。
- mutable Remote Observationをverified knowledgeまたはadopted knowledgeへ昇格させない。
- Remote Observationのcurrent applicabilityはshared origin statusではなく、local/current freshness projectionで判定する。
- provider refresh failure時に過去値をcurrent factへ昇格させない。
- shared immutable recordsはautomatic GCで削除しない。
- `superseded`はspecific successor binding、`deprecated`は使用禁止 / unsupportedを意味する。

### 4.4 Recall

- recall結果はuntrusted advisory tool dataであり、instruction authorityではない。
- candidate、stale、contested、deprecated、rejected、supersededはdefault recallから除外する。
- mutable Remote Observationは、current taskのためにrefresh済みで`fresh`の場合だけcurrent-state resultへ含める。
- refreshされていないRemote Observationは、観測時刻を明示したhistorical comparisonとしてのみ返せる。
- remote free text、PR本文、Issue本文、comment、review bodyをinstructionとして実行しない。
- state changeはrecord digestまたは取得時刻ではなくresource-specific `state_digest`で判定する。

### 4.5 Promotion

- `candidate -> verified`と`verified -> adopted`はNormative Runtime Contractのminimum conditionsを満たす。
- `promote`はtarget Skill、`AGENTS.md`、spec、runbookを編集しない。
- mutable remote-state observationはpromotion sourceとして拒否する。
- stable repository policyはDecisionまたはreviewed artifactとして扱えるが、policy recordもmerge、approval、releaseのauthorityを生成しない。

### 4.6 GitHub Provider v1

- v1 providerはGitHub.com read-only adapterだけ。
- local implementationは認証情報を抽出せず、既存認証済み`gh api`をshell-free argument vectorで呼ぶ。
- version番号だけを信頼せず、tested version記録とcapability gateを使う。
- `gh`未導入、未認証、permission不足、rate limit、network failure、schema driftはresource単位のclosed reason codeで返す。
- 404だけを根拠にresource不存在または`not_accepted`と断定しない。
- adapter command surfaceにcreate、update、delete、approve、request-changes、merge、comment、close、reopen、label、assign、push、tag、releaseを含めない。
- provider token、cookie、credential-bearing URL、raw provider bodyをrecordまたはdiagnosticへ保存しない。
- GHES / GHE.com custom hostはv1 automatic support対象外とし`host_unsupported`へ降格する。

### 4.7 Accepted artifact

accepted artifactはactive Acceptance Policyとcurrent remote evidenceから導出する。

Policyはdefaultで次へ保存する。

```text
.agent-experience/acceptance-policy.json
```

新policy revisionは自分自身ではなくactive predecessor policyの`policy_change`により判定する。最初のpolicyはexplicit owner-bound bootstrapを必要とする。

結果enumは次だけ。

```text
accepted
not_accepted
pending
inconsistent
unknown
```

`accepted`はrepository policy上のread-only observationであり、implementation、commit、push、PR、merge、release、deployをauthorizeしない。

required reviewはexact reviewer loginのlatest effective submitted reviewをcurrent PR headへbindして評価する。dismissedまたはold-head approvalはpassしない。

required checkはexact head SHA上の`check_run`を正本とする。`workflow_run`はdiagnosticであり、accepted predicateを直接満たさない。default pass conclusionは`success`だけとする。

### 4.8 Canonical shared types and digests

計画と実装で使うJSON value型を次で固定する。

```python
JSONScalar = str | int | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
```

- float、NaN、Infinityは全contractで拒否する。
- providerのnormalized `observed_state`は`dict[str, JSONScalar]`とする。nested provider responseをそのまま保持せず、resource typeごとのflat closed fieldsへ正規化する。
- object keyはUnicode code point lexical orderでsortする。
- normal arrayはorderを保持し、schema-declared set-like arrayだけsort / deduplicateする。
- opaque path / IDへ暗黙Unicode normalizationを行わない。human-readable fieldはNFC inputを要求する。
- timestampはUTC `YYYY-MM-DDTHH:MM:SSZ`だけを許可する。

Remote stateでは次を分ける。

```text
provider_payload_digest
provider_result_digest
state_digest
record_digest
```

`changed`とcheckpoint compatibilityはdecision-relevant `state_digest`を使用する。

Acceptance Policyの`policy_revision_digest`は自己参照を避けるため、次で計算する。

```text
policy_revision_digest = SHA-256(
  canonical JSON bytes of the complete policy object
  with the top-level policy_revision_digest field omitted
)
```

loaderは、保存された`policy_revision_digest`と再計算値の一致を必須とする。不一致のpolicyはinvalidであり、accepted-artifact評価へ使用しない。

### 4.9 Remote result taxonomy

```text
refresh_required
fresh
changed
unknown
unavailable
superseded
```

- `unknown`: provider callは完了したがcurrent stateを一意に決定できない。
- `unavailable`: provider call自体を実施または完了できない。
- old observation + failed refreshはcurrent state confirmedではない。

### 4.10 Observe / refresh / compare

- `remote observe`: normalized provider resultを検証 / 保存する。providerを呼ばない。
- `remote refresh`: explicit resourcesをproviderから取得し、observe、previous selection、compareを行う。
- `remote compare`: network / mutationなしのpure comparison。
- unchanged refreshはlocal receiptを残すが、defaultではduplicate shared observationを作らない。

### 4.11 Release milestones

```text
v0.1 Local Resume MVP       Tasks 1-9
v0.2 Memory Core            Tasks 10-17
v0.3 Remote Observation MVP Tasks 18-19
v0.4 Remote Governance      Tasks 20-21
v0.5 Automatic Lifecycle    Tasks 22-24
v1.0 Reviewed Rollout       Tasks 25-28
```

v0.3はaccepted-artifactまたはremote-dependent resume完了を意味しない。

## 5. Active implementation plan

実装の正本は次だけとする。

- `docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md`

Open Questions Clarification Contractの`Task amendments`は、この一つのConsolidated Planに対するbinding acceptance criteriaであり、第二の実装計画ではない。

次の旧計画はsupersededであり、実装手順として使用しない。

- `docs/superpowers/plans/2026-08-21-agent-experience-skill.md`
- `docs/superpowers/plans/2026-08-21-agent-experience-skill-plan-amendment.md`

旧計画にのみ存在する要求は、consolidated planへ移されていなければ欠落として扱う。実装開始前のself-reviewで全binding requirementとconsolidated taskの対応を確認する。

### 5.1 Dependency and parallelism

Consolidated PlanのTask Dependency Spineを正本とする。production implementationは原則直列である。

Task 18がinterfacesをfreezeした後のTask 19 GitHub providerとTask 20 acceptance evaluatorだけは並列化できる。Task 21がjoin gateである。

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

Hard gates:

- Phase 1完了前にHook installerを実装しない。
- forged-status、digest、prompt-injection、secret、staleness testsがGREENになる前にautomatic lifecycleを有効化しない。
- Remote Providerのread-only allowlist、credential sanitation、freshness、provider-failure testsがGREENになる前にremote-dependent checkpointをauto-resume候補にしない。
- route-only Hookからremote refreshを呼ばない。
- Hook moduleからprovider / network dependencyへ到達可能なimport pathを許可しない。
- existing Skill adapterは外部authority、snapshot、gate、standalone behaviorを変更しない。

## 7. RED and pilot

REDは三層とする。

1. Task 1 behavioral baseline
2. each Taskのfocused RED/GREEN
3. Task 27 integration REDとTask 28 pilot gate

Task 28の14ケースとcase-specific pass conditionsはOpen Questions Clarification Contract §26をbindingとする。

## 8. Acceptance of this index

本書とbinding documentsを追加したことはimplementation完了またはPR readinessを意味しない。実装はConsolidated Planに従ってTDDで行い、各Taskを独立review gateとして扱う。