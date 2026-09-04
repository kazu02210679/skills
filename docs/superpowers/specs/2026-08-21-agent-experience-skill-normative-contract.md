# Agent Experience Skill — Normative Runtime Contract

- **文書日**: 2026-08-21
- **対象**: `agent-experience` v1
- **状態**: Binding clarification / implementation prerequisite
- **理由**: adversarial amendmentで安全境界は定義したが、checkpoint compatibility、record staleness、promotion、contested projection、Codex Hook adapterに実装時の裁量が残っていたため。

## 0. Authority and reading order

実装者は次の順で読む。

1. 本Normative Runtime Contract
2. `2026-08-21-agent-experience-skill-adversarial-amendment.md`
3. `2026-08-21-agent-experience-skill-design.md`

本書は新機能を追加するものではない。上記2文書の曖昧な箇所をv1について閉じる。矛盾する場合は本書を優先する。

---

## 1. Checkpoint compatibility

### 1.1 Identity contract

checkpointは最低限次へbindする。

```ts
interface CheckpointIdentityV1 {
  repoId: string;
  worktreeId: string;
  branchRef: string;
  head: string;
  indexManifestDigest: string;
  trackedWorktreeManifestDigest: string;
  untrackedManifestDigest: string;
  scopeManifestDigest: string;
}
```

定義:

- `repoId`: tracked `.agent-experience/config.toml` のUUID。clone間で同じrepository lineageを表すために使用する。remote URLだけをidentityにしない。
- `worktreeId`: local-only UUID。Git worktreeごとに一度生成しlocal storeへbindする。別clone、別worktreeでは再利用しない。
- `branchRef`: symbolic refがある場合はcanonical `refs/heads/<name>`。detached HEADは `DETACHED:<head>`。
- `head`: full commit SHA。
- manifest digest群はadversarial amendmentのcanonical repository snapshot v1で計算する。

machine IDはshared checkpointへ保存しない。別machine/cloneは`worktreeId`が異なるためautomatic exact resumeにはならない。

### 1.2 Deterministic classification order

`classify_checkpoint(checkpoint, current)` は次の順序で一度だけ判定する。後のruleで前のresultを上書きしない。

```text
1. current snapshotを安全・安定に取得できない
   -> unavailable

2. repoIdが一致しない
   -> stale(repo_mismatch)

3. repoId / worktreeId / branchRef / HEAD / index / tracked / untracked /
   scope digestがすべて一致
   -> exact(auto_resume=true)

4. scope digestが一致し、checkpoint HEAD == current HEAD
   または checkpoint HEAD が current HEAD のancestorであり、
   変更がscope外だけである。ただしworktreeId、branchRef、HEAD、out-of-scope
   stateのいずれかがexact条件を満たさない
   -> manual_review_compatible(auto_resume=false)

5. 上記以外
   -> stale(auto_resume=false)
```

`manual_review_compatible` は「安全に続行できる」という判定ではない。current diffとcurrent instructionsを人間またはagentが再確認するための候補である。

### 1.3 Required special cases

| Current situation | v1 classification |
|---|---|
| 同じworktree・同じbranch・同じHEAD・全digest一致 | `exact` |
| 同じworktreeでbranch名だけ切替、同じHEAD | `manual_review_compatible` |
| 同じbranchでHEADがdescendant、scope不変 | `manual_review_compatible` |
| rebaseでcheckpoint HEADがcurrent HEADのancestorではない | `stale` |
| 同じrepoの別worktree、HEAD/scope一致 | `manual_review_compatible` |
| 同じrepoを別PCへclone、HEAD/scope一致 | `manual_review_compatible` |
| detached HEADへ切替 | `manual_review_compatible` または lineage不成立なら`stale` |
| staged/index変更 | `stale` |
| scoped file内容・mode・symlink・submodule変更 | `stale` |
| unstable snapshot / unmerged index / unsafe path | `unavailable` |
| repoId不一致 | `stale`。default recallのcheckpoint候補から除外 |

v1ではrebase後にtree内容が偶然一致しても`exact`へ戻さない。history lineageが切れたcheckpointはautomatic current stateとして扱わない。

---

## 2. Staleness semantics

`checkpoint compatibility`の`stale`と、shared record projectionの`effective_status=stale`を混同しない。

### 2.1 Record-kind matrix

| kind | stale condition | age-only stale? |
|---|---|---|
| checkpoint | §1のcompatibility classifierが`stale` | No |
| observation / failure | historical occurrence自体はstaleにしない。scope/platform/version不一致はrecall applicability filterで除外 | No |
| decision | `revalidate_after`超過、または明示的にbindしたpremise/artifact digestがcurrent validationで不一致 | Yes, only when `revalidate_after` exists |
| knowledge candidate / verified | `revalidate_after`超過、またはrequired evidence/artifact validityがcurrent validationで失効 | Yes |
| adopted knowledge | target artifact digestまたはadoption locatorのcurrent validationが一致しない | No fixed days unless `revalidate_after` exists |
| outcome | historical feedback自体はstaleにしない。target ID/digest mismatchならそのoutcomeをprojection inputから除外 | No |
| promotion/deprecation record | immutable transition event自体はstaleにしない。source/target digest mismatchならinvalid/excluded | No |

### 2.2 Effective-state precedence

同じshared recordへ複数conditionが成立する場合、projectionは次の順で決める。

```text
invalid / excluded
  > superseded / deprecated
  > contested
  > stale
  > adopted / verified / candidate / active / observed / recorded
```

理由:

- digest/schema不正なrecordをstatus projectionへ参加させない。
- superseded/deprecatedは意図的なlifecycle終端であり、単なるstaleより強い。
- current contradiction/harmful evidenceがあるrecordを「古いだけ」と弱く扱わない。
- stale recordはdefault recallから除外するが、explicit queryではhistorical contextとして取得できる。

### 2.3 Decision premise invalidation

Decisionがartifactまたはevidenceへ依存する場合、relationはIDだけでなくdigestをbindする。

```text
premise_record_id + premise_record_digest
artifact_locator + artifact_digest
```

current validationでdigestが変化した場合、decision origin fileは編集せずprojectionだけを`stale`にする。

---

## 3. Promotion minimum conditions

Promotionはstatus fieldの書換えではなく、validated immutable promotion recordの追加とprojection replayでのみ成立する。

### 3.1 Candidate -> Verified

次をすべて満たす。

1. source recordがvalidで、直前`effective_status == candidate`。
2. source ID/digestが一致。
3. unresolved contradiction、shared harmful outcome、deprecated/superseded relationがない。
4. reuse scope、counterconditions、failure conditionsが空でない。
5. `verification_basis`が次のどちらか。

#### A. `two_independent_evidence`

- sealed evidence recordが2件以上。
- evidence record ID/digestがすべてvalid。
- 少なくとも2件は異なる`workstream_id`から生成される。
- 同一tool outputや同一test resultの複製を独立evidenceとして数えない。
- 少なくとも1件はcurrent validation locatorを持つ。

#### B. `human_review`

- human reviewer locatorが1件。
- current validation evidenceが1件以上。
- reviewer locatorだけで、test/runtime/evidenceなしのverified化はしない。

6. promotion recordにreviewerとapproval locatorを持つ。
7. authoring agent/session自身の自己申告だけをindependent evidenceとして数えない。

### 3.2 Verified -> Adopted

次をすべて満たす。

1. sourceの直前`effective_status == verified`。
2. target artifactが次のreviewed surfaceのいずれか。

```text
Skill
AGENTS.md / equivalent repository instruction
specification / policy
runbook / operator contract
```

3. target artifact path/locatorとexact content digestがある。
4. target changeを含むexact commitまたはPR locatorがある。
5. repositoryの通常review/acceptance gateを通過している。
6. current validation evidenceがtarget artifactの内容と矛盾しない。
7. unresolved contested/stale stateがない。

`agent-experience promote`はtarget Skill、AGENTS、spec、runbookを書き換えない。通常の変更・reviewが先に存在し、その採用事実をpromotion recordで記録するだけである。

### 3.3 Prohibited transitions

```text
candidate -> adopted
observed -> verified
Hook -> verified/adopted
SessionEnd -> verified/adopted
harmful feedback -> deprecated automatically
```

反証は即時削除ではなく§4のcontested projectionまたは明示deprecation/supersessionで扱う。

---

## 4. Contested projection

### 4.1 Contested is derived, not authored

`contested`はorigin record kindでもself-declared statusでもない。

```text
validated origin
  + validated contradiction relation
  + validated shared harmful outcome
  -> projection effective_status=contested
```

CLIは自由文を読んで「矛盾している」と自律判断しない。Skill/user/agentがstructured inputとしてmaterial findingをcaptureし、normal validation/sealを通ったrecordだけがprojection inputになる。

### 4.2 Sources that can contest a record

対象recordを`contested`へできるのは次だけ。

1. exact target ID + target digestへbindされたsealed recordの`contradicts` relation。
2. exact target ID + target digest + current evidence locatorを持つsealed shared `harmful` outcome。

local-only `feedback harmful` は即時local suppressionだけを行う。shared corpus全体を`contested`にするにはnormal capture/sealが必要である。

### 4.3 Agent / CLI / human responsibility

- **Agent/Skill**: current evidenceと既存recordの不一致を発見した場合、pending observation/outcomeをstructured inputとして提案できる。
- **CLI**: schema、digest、relation、path、resource limitだけをdeterministicに検証する。semantic contradictionを発明しない。
- **Human/independent review**: contesting recordをseal/promote/deprecateする通常reviewに参加できる。

### 4.4 Resolution policy

v1では既存contested recordのstatusを直接「uncontest」しない。

解決方法:

```text
old contested record
  -> new corrected knowledge/decision record
  -> new record supersedes old
  -> new recordは通常のcandidate -> verified -> adopted lifecycleを通る
```

または旧recordを明示deprecateする。

これにより、反証履歴を消さずにdefault recallから旧recordを外せる。

---

## 5. Codex Hook v1 normative contract

### 5.1 Supported events

v1 automatic lifecycleが使用を許可するeventは次の4つだけ。

```text
SessionStart
PreCompact
PostCompact
SessionEnd
```

`UserPromptSubmit`はv1でinstallしない。

### 5.2 Normalized input allowlist

host raw payload全体をdomain inputとして扱わない。adapterが使用できるnormalized fieldは次だけ。

| Event | Allowed normalized input |
|---|---|
| SessionStart | `session_id`、`source=startup|resume|clear|compact` |
| PreCompact | `session_id`、`trigger=manual|auto` |
| PostCompact | `session_id`、`trigger=manual|auto` |
| SessionEnd | `session_id`、`reason` |

Rules:

- `session_id`はlocal idempotency/correlationだけに使いshared recordへ保存しない。
- `reason`はauthorityとして解釈しない。
- transcript path、prompt、tool output、cwd/home path、environment value、diffを読み取らない・保存しない。
- future host fieldはdefault ignore。安全上必要なfieldが欠落した場合はそのhandlerをsilent no-opにする。

### 5.3 Output contract

- `SessionStart`: fixed routing noticeだけをmodel-visible outputとして返せる。512 UTF-8 bytes以下。`additionalContextLimit=256`。
- `PreCompact`: success時stdout/stderr空。
- `PostCompact`: success時stdout/stderr空。
- `SessionEnd`: success時stdout/stderr空。
- record body/title/summary/checkpoint objective/current state/path/branch/HEADをHook outputへ含めない。

### 5.4 Timeout contract

| Event | host timeout | internal deadline |
|---|---:|---:|
| SessionStart | 2.0 s | 1.5 s |
| PreCompact | 2.0 s | 1.5 s |
| PostCompact | 2.0 s | 1.5 s |
| SessionEnd | 3.0 s | 2.5 s |

Hook hot pathでnetwork、LLM、shared scan、FTS recall、reindex、Git mutation、seal、promotion、GCを実行しない。

### 5.5 Host compatibility gate

implementation時にthen-current official Codex Hook documentationからv1 fixtureを作成し、tested host contract/versionを`host-adapters.md`へ固定する。

- expected eventまたはrequired source/trigger semanticsが確認できないhost versionではautomatic Hook setupを行わない。
- unknown newer host schemaを「たぶん互換」と推定しない。
- automatic setup不可でもmanual `preflight` / `checkpoint` / `recall` modeは利用可能。
- unsupported hostを理由にordinary repository workを停止しない。

このruleにより「実装時にdocsを見る」はfield名を勝手に決める余地ではなく、host compatibilityを検証するgateになる。

### 5.6 Persistence guarantee

保証するのは**transaction commit済みlocal stateだけ**である。

- PreCompactは既にcommittedなlocal checkpoint fingerprintをtransactionで固定する。
- PostCompactはmarker整合だけを確認する。
- SessionEndはbounded close metadataのbest-effort commitであり、semantic observationのsealを保証しない。
- process crash、OS kill、電源断でin-flight turnや未commit pending stateを必ず保存できるとは主張しない。
- crash recovery後はlast committed checkpointから開始し、loss witnessがある場合はcurrent evidenceを再確認する。

### 5.7 Failure policy

#### Fail open for ordinary agent work

次はHook adapterがexit `0`、model-visible outputなしで終了する。

```text
local DB read failure
lock timeout
unsupported newer local schema
duplicate Hook event
non-owner Hook
missing optional Hook field
Hook contract unavailable at runtime
```

local diagnosticはstable codeだけを保存し、raw exceptionをstdout/stderrへ出さない。

#### Fail closed for explicit mutation/setup

次はexplicit CLI/setup operationを拒否する。

```text
seal/promote/migrate integrity uncertainty
mixed Hook representations
unknown/unsupported host Hook contract
installer preimage drift
unsafe path/digest mismatch
ambiguous active owner migration
```

Hook failureを理由にagentの通常編集・testを強制停止しない。安全なmanual modeへ降格する。

---

## 6. Phase-1 implementation gate

Phase 1 Manual Local Checkpoint MVPへ入る前に、少なくとも設計reviewで次をaccepted contractとする。

1. §1 compatibility classifier
2. §2 record-kind staleness matrix
3. §3 promotion minimum conditions
4. §4 contested derivation
5. §5 Hook normative contract

Hook implementation自体は既存のcorrected implementation orderどおりPhase 3まで開始しない。

本書を追加したことはimplementation完了を意味しない。次はimplementation plan amendmentに従い、これらの判定をRED testsとして固定してからproduction codeを書く。