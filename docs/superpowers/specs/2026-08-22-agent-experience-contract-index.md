# Agent Experience Skill — Contract Index

- **文書日**: 2026-08-22
- **対象**: `agent-experience` v1
- **状態**: Binding contract index

## 1. 目的

`agent-experience` の設計は、基礎設計、敵対的レビュー追補、Normative Runtime Contract、Remote Repository State追補へ分割されている。本書は、それらを一つの実装契約として読むための優先順位と結合規則を固定する。

本書は新しいruntime機能を追加しない。文書間の読み順、適用範囲、競合解消、実装計画の正本を定義する。

## 2. Binding documents

実装者は次をすべて読む。

1. `docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md`
2. `docs/superpowers/specs/2026-08-22-agent-experience-remote-state-amendment.md`
3. `docs/superpowers/specs/2026-08-21-agent-experience-skill-normative-contract.md`
4. `docs/superpowers/specs/2026-08-21-agent-experience-skill-adversarial-amendment.md`
5. `docs/superpowers/specs/2026-08-21-agent-experience-skill-design.md`

## 3. Precedence

文書が競合する場合、次を適用する。

```text
current system / developer / user instruction
  > repository instruction
  > this Contract Index
  > Remote-State Amendment, remote-state domain only
  > Normative Runtime Contract
  > Adversarial Review Amendment
  > Base Design
```

Remote-State Amendmentは、remote repository observation、freshness、provider adapter、accepted artifact、remote-dependent checkpointに限ってNormative Runtime ContractとAdversarial Review Amendmentを拡張する。remote-state以外のcheckpoint、promotion、Hook、installer、retention、record projectionではNormative Runtime ContractとAdversarial Review Amendmentを優先する。

同じ優先順位内で二つの要求を同時に満たせない場合、実装を開始せず、設計追補を作成して矛盾を閉じる。

## 4. Consolidated decisions

### 4.1 Automatic lifecycle

- v1でinstallできるCodex Hookは`SessionStart`、`PreCompact`、`PostCompact`、`SessionEnd`だけ。
- `UserPromptSubmit`をinstallしない。
- Hookはroute-onlyであり、record、checkpoint本文、remote state、user prompt、transcriptをmodel-visible contextへ注入しない。
- model-visible outputを返せるのは`SessionStart`の固定routing noticeだけ。
- Hook hot pathはnetwork、LLM、shared scan、FTS recall、reindex、Git mutation、remote refresh、`seal`、`promote`、`gc`を実行しない。
- remote stateが必要なtaskでは、Skillが通常のtool execution boundaryで明示的にread-only refreshを行う。

### 4.2 Checkpoint compatibility

local checkpointのauto-resumeには、Normative Runtime Contractのlocal exact条件をすべて必要とする。

remote dependencyがあるcheckpointでは、さらに次をすべて必要とする。

```text
local classification == exact
all remote dependencies refreshed for current use
all remote repository bindings valid
all normalized remote states unchanged
all acceptance-policy revisions unchanged
```

一つでも満たさない場合、`auto_resume=false`とする。

- remote dependency未refresh: `refresh_required`
- provider failure: `unknown`または`unavailable`
- normalized state changed: `changed`
- repository binding mismatch: `stale`
- acceptance policy revision changed: `pending`

古いcheckpointのstable Decision、`Do not redo`、failed approachは個別scopeが現在も有効なら再利用できる。古いcurrent-state claimだけを失効させる。

### 4.3 Record and projection

- origin recordはclosed `initial_status`だけを持つ。
- `effective_status`はvalidated origin、promotion、relations、outcomes、stalenessからreplayする。
- `contested`はprojection-onlyであり、origin recordが自己申告できない。
- Remote ObservationはObservation subtype `remote-state`であり、過去時点の外部状態を表す。
- mutable Remote Observationをverified knowledgeまたはadopted knowledgeへ昇格させない。
- Remote Observationのcurrent applicabilityはshared origin statusではなく、local/current freshness projectionで判定する。
- provider refresh failure時に過去値をcurrent factへ昇格させない。

### 4.4 Recall

- recall結果はuntrusted advisory tool dataであり、instruction authorityではない。
- candidate、stale、contested、deprecated、rejected、supersededはdefault recallから除外する。
- mutable Remote Observationは、current taskのためにrefresh済みで`fresh`の場合だけcurrent-state resultへ含める。
- refreshされていないRemote Observationは、観測時刻を明示したhistorical comparisonとしてのみ返せる。
- remote free text、PR本文、Issue本文、comment、review bodyをinstructionとして実行しない。

### 4.5 Promotion

- `candidate -> verified`と`verified -> adopted`はNormative Runtime Contractのminimum conditionsを満たす。
- `promote`はtarget Skill、`AGENTS.md`、spec、runbookを編集しない。
- mutable remote-state observationはpromotion sourceとして拒否する。
- stable repository policyはDecisionまたはreviewed artifactとして扱えるが、policy recordもmerge、approval、releaseのauthorityを生成しない。

### 4.6 GitHub Provider v1

- v1 providerはGitHub read-only adapterだけ。
- local implementationは認証情報を抽出せず、既存認証済み`gh api`をshell-free argument vectorで呼ぶ。
- `gh`未導入、未認証、permission不足、rate limit、schema driftはresource単位の`unknown`または`unavailable`として返す。
- adapter command surfaceにcreate、update、delete、approve、request-changes、merge、comment、close、reopen、label、assign、push、tag、releaseを含めない。
- provider token、cookie、credential-bearing URL、raw provider bodyをrecordまたはdiagnosticへ保存しない。

### 4.7 Accepted artifact

accepted artifactはrepository policyとcurrent remote evidenceから導出する。

結果enumは次だけ。

```text
accepted
not_accepted
pending
inconsistent
unknown
```

`accepted`はrepository policy上のread-only observationであり、implementation、commit、push、PR、merge、release、deployをauthorizeしない。

## 5. Active implementation plan

実装の正本は次だけとする。

- `docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md`

次の旧計画はsupersededであり、実装手順として使用しない。

- `docs/superpowers/plans/2026-08-21-agent-experience-skill.md`
- `docs/superpowers/plans/2026-08-21-agent-experience-skill-plan-amendment.md`

旧計画にのみ存在する要求は、consolidated planへ移されていなければ欠落として扱う。実装開始前のself-reviewで全binding requirementとconsolidated taskの対応を確認する。

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
- existing Skill adapterは外部authority、snapshot、gate、standalone behaviorを変更しない。

## 7. Acceptance of this index

本書を追加したことはimplementation完了またはPR readinessを意味しない。実装はconsolidated planに従ってTDDで行い、各Taskを独立review gateとして扱う。