# Company Research v1 Authoritative Execution Entry

## Status

**AUTHORITATIVE EXECUTION ENTRYPOINT**

実装者は次を順に読む。

1. `docs/superpowers/specs/2026-08-16-company-research-skill-design-v2.md`
2. `docs/superpowers/plans/2026-08-16-company-research-v1.md`
3. 本書の補正事項

本書は敵対的レビュー後の最終実行補正であり、詳細計画と矛盾する場合は本書を優先する。

## Preflight Gate

実装開始前に、`design/company-research-skill` を最新 `main` にrebaseまたはmergeし、設計外の既存変更との衝突を解消する。

現在のreview時点ではbranchはmerge base `1b1bdb44cbce907a181a26349b541a75d4a88afb` から分岐し、`main` 側にSkill Portfolio Dashboard関連の4 commitが追加されている。実装worktreeは古いbranch headから作らない。

Preflightで確認する。

```bash
git fetch origin
git switch design/company-research-skill
git rebase origin/main
python scripts/validate-skills.py
python -m unittest tests.test_skill_catalog -v
```

rebase conflictや既存test failureがある場合はTask 1へ進まない。

## Corrections to the Detailed Plan

### 1. Test fixtureのcompany ID

Task 1の例にある `"subject_id": "cmp_x"` はinvalid fixtureであり、ObservationのUNKNOWN検証より先にID validationで失敗しうる。

次を使用する。

```python
VALID_COMPANY_ID = "cmp_" + "a" * 32
```

Observation、Claim、Segment、Event等のunit testは、対象以外のfieldをすべてvalidにして一つのfailure reasonだけを検証する。

### 2. Interface blockの`...`はstub実装ではない

詳細計画のInterfacesにある次の表記はsignature declarationである。

```python
def validate_source(value: dict) -> dict: ...
```

実装fileへellipsis bodyをcommitしてはならない。各Taskのgreen commitでは、公開interfaceの全functionにcomplete implementation、docstring、type annotation、focused testを持たせる。

### 3. CLI subcommandの導入順

Task 6では、依存実装済みの次だけをproduction commandとして有効化する。

```text
coverage
prepare
diff
apply
verify
recover
```

ただし`coverage`はTask 7完了前には非公開のdependency injection版または明示的`NOT_IMPLEMENTED`であり、成功を返してはならない。

`watchpoint-update`はTask 10で追加し、`render`はTask 13で追加する。未実装commandをplaceholder successとして登録しない。

### 4. `recover`の意味

v1の`recover`は**診断専用**である。staging、orphaned snapshot/event、stale lock、latest pointerの状態を報告するが、自動削除、自動lock steal、latest書換えを行わない。

CLI helpと出力では`diagnostic only; no mutation`を明示する。将来repair commandを追加する場合は別設計・別承認とする。

### 5. Transaction commit marker

`latest.json`のatomic replaceをlogical commit markerとする。

- latest更新前にpublishされたsnapshot/eventはorphaned candidateであり、committed historyとして列挙しない。
- `verify`はlatestから到達可能なmanifest/event sequenceだけをcommittedとみなす。
- `recover`はorphanを診断するが削除しない。
- event filename sequenceだけでcommit済みと判定しない。

Crash injection testは少なくとも次の三地点で行う。

```text
after staging fsync

after immutable snapshot publish

after event publish but before latest replace
```

いずれも旧latestが有効であることを確認する。

### 6. WatchpointとInvestmentのwrite coordination

Company snapshot、Watchpoint、Investmentは別versionを持つが、一つのresearch runの出力関係を`research_run_id`と`source_snapshot_digest`で結ぶ。

- Watchpoint transitionは存在するcommitted company snapshotを参照する。
- Investment stateは存在するcommitted company snapshot digestを参照する。
- company apply失敗時にWatchpoint/Investmentを先行commitしない。
- Dashboardは互いに整合するversionだけを組み合わせる。不一致は`STALE_DERIVED_STATE`として表示する。

### 7. Manual acceptanceとFULL表示

coverage.yamlへFULLを記述するだけではFULLにならない。公開表示では、module promotion receiptが存在する場合だけFULLを返す。

Promotion receiptは最低限次を持つ。

```json
{
  "module_id": "semiconductor.memory.nand",
  "target_version": "v1.0",
  "synthetic_tests": "PASS",
  "real_company_manual_audit": "PASS",
  "dashboard_render": "PASS",
  "adversarial_review": "PASS",
  "approved_at": "...",
  "approval_evidence": "docs/company-research-v1-manual-audit.json"
}
```

receiptがない間は、configured targetがFULLでもruntime statusは`PARTIAL_PENDING_ACCEPTANCE`とする。Release acceptance後にFULLへ昇格する。

### 8. Visual verification

Task 15のvisual reviewは目視宣言だけで終えない。各fixtureについてdesktop/narrowのrendered screenshotまたは構造化visual-audit recordを残し、少なくとも次を確認する。

- Revenue bar / Operating Profit lineのscaleとnegative value
- missing pointが0に見えない
- long Japanese/English text overflow
- sidebar/contextの重複なし
- keyboard focus order
- malicious textが表示されても実行されない
- PL/BS/CF table fallback

binary screenshotをrepositoryへ入れない場合も、viewport、snapshot digest、checked routes、findings、decisionをmanual audit JSONへ記録する。

## Execution Order

```text
Preflight/rebase
  -> Task 1-6 Foundation
  -> Foundation Review Gate
  -> Task 7-8 Industry Pilot
  -> Pilot Promotion Review
  -> Task 9-11 Monitoring/Investment
  -> Task 12-13 Export/Dashboard
  -> Task 14 Integration/CI
  -> Task 15 Release Acceptance
```

Foundation Review Gateでは、transactional store、ResearchPacket boundary、registered derivation、CLI exit codes、Windows path testsがPASSするまでindustry workへ進まない。

Pilot Promotion Reviewでは、NAND、Machine Tools、Logistics/Forkliftのsynthetic testsがPASSしても、real-company manual audit前はFULL表示しない。

## Final Review Decision

このentrypoint、v2設計、詳細計画の三点を一組として使用する場合、設計・計画は実装着手可能である。

旧2026-08-14計画、旧design amendment、承認前のv1 scope表を実装根拠に使用しない。
