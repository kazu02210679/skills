# Company Research Skill 設計 v2

## Status

**AUTHORITATIVE**

本書は次を統合し、実装の正本とする。

- `2026-08-14-company-research-skill-design.md`
- `2026-08-14-company-research-skill-design-amendment.md`
- `2026-08-14-company-research-reference-analysis.md`
- `2026-08-16-company-research-design-review.md`

旧文書と矛盾する場合は本書を優先する。

## 目的

`company-research` を、企業を一度だけ要約するSkillではなく、企業・事業・財務・技術・競争・外部環境・投資上の論点をEvidence付きで継続追跡するresearch systemとして実装する。

初回はFull Researchを実行し、その後は前回stateを基準にIncremental Updateを行う。Dashboardは正本ではなく、検証済みcanonical snapshotから生成されるviewである。

分析は次を分離する。

1. **Source / Evidence Plane** — 何を、どのsourceから、いつ確認したか。
2. **Company Understanding Layer** — 企業、segment、事業、財務、製品、技術、競争のcanonical state。
3. **Forward Monitoring Layer** — Events、External Drivers、Watchpoints、Recent Updates。
4. **Investment Layer** — Company Understandingとmarket evidenceから導く派生state。
5. **Presentation Layer** — Dashboard、Markdown、CSV、JSON exports。

下位layerが上位layerの解釈によって書き換えられることを禁止する。

## 成功条件

1. 重要な表示・結論からsource locatorまで辿れる。
2. Missing/Unknownを0へ変換しない。
3. Fact、Derived Fact、Inference、Scenarioを機械的に区別する。
4. Full ResearchとIncremental Updateで同一schemaを使用する。
5. 更新はimmutable snapshotとappend-only eventを残し、同じinputから同じdiffを得る。
6. WindowsとLinuxで同じcompany DBを安全に扱える。
7. 同時更新、途中失敗、stale lock、corrupt snapshotを検出し、silent overwriteしない。
8. Capability coverageとEvidence completenessを別表示する。
9. 複合企業へindustry moduleをsegment単位で適用できる。
10. Watchpoint transitionはEvidenceまたは明示decision receiptなしに進まない。
11. Dashboardは外部文字列を安全に扱い、keyboardとscreen readerでも利用できる。
12. HTML、Markdown、CSV、JSON exportsが同一snapshot digestを参照する。
13. 非上場企業へmarket capや上場企業向けvaluationを捏造しない。
14. trading execution、brokerage mutation、personalized allocation recommendationを行わない。

## 非対象

- 売買注文、広告、billing、subscription、outbound campaign等の外部操作
- 非公開データの無断取得
- commercial providerの必須化
- Web page/PDF全文の再配布
- generic drag-and-drop dashboard builder
- long-running API serverの必須化
- Graph DB
- technical-pattern scanner、options、paper trading
- investor persona roleplayを標準research pathにすること
- arbitrary formula/evalの実行
- 全業種をv1でFULLと主張すること

## Activation

起動対象:

- 企業全体の調査・比較
- 既存企業stateの更新
- 決算、製品、技術、競合、外部環境、Watchpointの更新
- company Dashboard/reportの生成

非起動対象:

- 単一株価の確認
- 単一指標だけの質問
- 一般ニュース要約
- 個別企業を伴わない一般業界解説

非起動対象であってもユーザーが明示的にFull Researchを指定した場合は起動できる。

## Canonical Identity

### CompanyIdentity

```json
{
  "company_id": "cmp_<stable_digest>",
  "slug": "kioxia-holdings",
  "legal_name": "...",
  "jurisdiction": "JP",
  "listed_status": "LISTED",
  "primary_identifier": {
    "kind": "exchange_security_id",
    "value": "..."
  },
  "identifiers": [
    {"kind": "ticker", "value": "...", "exchange": "...", "valid_from": null, "valid_to": null}
  ],
  "aliases": [],
  "fiscal_year_end": "03-31",
  "reporting_currency": "JPY"
}
```

`company_id`は一度作成したら変更しない。ticker、legal name、exchange変更はidentifier/alias履歴として扱う。

primary identifierの優先順位:

1. regulator/company registration identifier
2. LEI等の安定識別子
3. exchange + security identifier
4. 明示的なuser namespace + slug

同名またはticker一致だけで既存companyへ自動mergeしない。

## Evidence Architecture

### Epistemic Status

```text
FACT
DERIVED_FACT
INFERENCE
SCENARIO
UNKNOWN
```

### SourceRecord

```json
{
  "source_id": "src_<digest>",
  "source_kind": "issuer_filing",
  "title": "...",
  "publisher": "...",
  "url": "https://...",
  "published_at": "2026-08-01T00:00:00Z",
  "retrieved_at": "2026-08-16T00:00:00Z",
  "content_digest": "sha256:...",
  "locator": {"page": 12, "section": "..."},
  "rights": "public_reference_only",
  "local_archive_ref": null
}
```

`url`は`user_supplied` sourceの場合のみ空を許可する。その場合はuser-provided receiptまたはworkspace file digestを持つ。

Source kind:

```text
issuer_filing
issuer_ir
issuer_product
regulator
industry_body
competitor_primary
market_data
secondary
user_supplied
```

### ClaimRecord

非数値の主張を保持する。

```json
{
  "claim_id": "clm_<digest>",
  "subject_id": "cmp_...",
  "predicate": "technology_generation_status",
  "object": "sample shipment started",
  "plane": "company",
  "epistemic_status": "FACT",
  "confidence": "high",
  "source_refs": [{"source_id": "src_...", "locator": {"page": 3}}],
  "effective_from": "2026-08-01",
  "effective_to": null,
  "status": "ACTIVE",
  "supersedes": []
}
```

一つのclaimは複数sourceを参照できる。矛盾するclaimを単一値へ潰さず、`DISPUTED`またはsupersession relationを保持する。

### ObservationRecord

数値を保持する。JSON valueはdecimal stringとし、binary floatの丸め差を正本にしない。

```json
{
  "observation_id": "obs_<digest>",
  "subject_id": "cmp_...",
  "metric_id": "revenue",
  "value": "1234560000000",
  "unit": "currency",
  "currency": "JPY",
  "unit_scale": 1,
  "period_kind": "FY",
  "period_start": "2025-04-01",
  "period_end": "2026-03-31",
  "reported_at": "2026-05-10",
  "accounting_standard": "IFRS",
  "consolidation_scope": "consolidated",
  "restatement_status": "ORIGINAL",
  "plane": "company",
  "epistemic_status": "FACT",
  "source_refs": []
}
```

Annual、Quarterly、Half-year、TTM、instant balanceを混同しない。restatementは旧Observationを削除せずsupersedeする。

### DerivationRecord

任意式を評価しない。closed method registryだけを使用する。

```json
{
  "derivation_id": "drv_<digest>",
  "method_id": "operating_margin",
  "method_version": 1,
  "input_ids": ["obs_revenue", "obs_operating_profit"],
  "parameters": {},
  "effective_period": {"start": "...", "end": "..."},
  "output_observation_id": "obs_margin",
  "calculated_at": "2026-08-16T00:00:00Z"
}
```

v1 method registry:

- `operating_margin.v1`
- `yoy_growth.v1`
- `fcf_simple.v1`
- `market_cap.v1`
- `pe.v1`
- `pb.v1`

計算前にperiod、scope、currency、unitを検証する。FX換算を伴う場合はFX Observationをinputに含める。

### Evidence Plane

```text
company
external
market
```

External/market observationはCompany Factの代用品にならない。company sensitivityまたはInvestment derivationを通じて参照する。

## ResearchPacket

agent/browser/connector/user inputからcanonical stateへ入る唯一の入口とする。

```json
{
  "schema_version": 1,
  "run_id": "20260816T000000000000Z-ab12cd",
  "mode": "FULL",
  "company_identity": {},
  "sources": [],
  "claims": [],
  "observations": [],
  "proposed_derivations": [],
  "events": [],
  "industry_hints": [],
  "meta": {
    "created_at": "...",
    "actor_kind": "agent",
    "source_boundaries": []
  }
}
```

`prepare`はpacketを検証し、source/claim/observation IDをcanonicalizeし、derivationを再計算し、candidate stateとdiffを作る。agentが直接canonical snapshotを書かない。

## Canonical Company State

```json
{
  "schema_version": 2,
  "company_identity": {},
  "segments": [],
  "sources": [],
  "claims": [],
  "observations": [],
  "derivations": [],
  "business": {},
  "technology": {},
  "competitors": {},
  "coverage": {},
  "evidence_quality": {},
  "external_drivers": [],
  "events": [],
  "watchpoint_index": [],
  "investment_ref": null,
  "meta": {
    "snapshot_version": 1,
    "snapshot_digest": "sha256:...",
    "created_at": "...",
    "base_version": null,
    "research_run_id": "..."
  }
}
```

Snapshot serializationはkey order、UTF-8、number representationをcanonical化し、digestを再現できるようにする。

## Persistence

### Root

`COMPANY_RESEARCH_HOME`、未設定時は`~/.company-research`。

### Layout

```text
<home>/
├── index.json
└── companies/<company_id>/
    ├── identity.json
    ├── latest.json
    ├── snapshots/
    │   └── v000001/
    │       ├── state.json
    │       └── manifest.json
    ├── events/
    │   └── 000001-<event-id>.json
    ├── watchpoints/
    ├── investment/
    ├── staging/<run_id>/
    └── locks/update.lock
```

`latest.json`はstate本体ではなく、version、snapshot digest、manifest digestへのpointerとする。

### Transaction

1. exclusive per-company lockを取得する。
2. `expected_base_version`とlatestを比較する。
3. stagingへsnapshot/event/manifestを書く。
4. file fsyncと可能な範囲のdirectory fsyncを行う。
5. immutable snapshot directoryへrenameする。
6. eventをpublishする。
7. `latest.json`をatomic replaceする。
8. lockを解放する。

latest更新前の失敗は未commitとしてrecoveryで破棄可能。latest更新後はmanifestから完全stateを検証できる。

### Portable IDs

filenameへISO `:`を使用しない。

```text
run_id: 20260816T123456123456Z-a1b2c3
version: v000001
sequence: 000001
```

### Concurrency

applyは`expected_base_version`を必須とし、mismatch時は`CONFLICT`でfailする。silent last-write-winsを禁止する。

### Recovery and Integrity

`verify`はsnapshot/event/manifest digest、version sequence、latest pointerを検証する。`recover`はstagingとstale lockを診断し、automatic destructive repairをしない。schema migrationはversioned migration functionを通し、旧snapshotを変更しない。

## Coverage and Industry Modules

### Separate Dimensions

```text
capability_status: FULL | PARTIAL | COMMON_ONLY | OUT_OF_SCOPE
evidence_completeness: 0-100 | UNKNOWN
freshness_status: CURRENT | MIXED | STALE | UNKNOWN
```

Capabilityと今回のEvidence量を混同しない。

### Segment Applicability

```json
{
  "segment_id": "seg-logistics",
  "name": "Logistics Equipment",
  "materiality": {
    "basis": "revenue_share",
    "value": "0.62",
    "confidence": "high"
  },
  "modules": ["manufacturing-common", "logistics-equipment"]
}
```

moduleはsegment単位で適用し、company viewは集約する。同一dimensionが複数moduleに存在する場合はsubtype moduleを優先し、source dataは重複コピーせずreferenceする。

### v1.0 Coverage

FULL:

- common
- manufacturing-common
- semiconductor.memory.nand
- industrial-machinery.machine-tools
- industrial-machinery.logistics-equipment

PARTIAL:

- semiconductor.memory.dram
- semiconductor.foundry
- semiconductor.logic
- semiconductor.equipment
- industrial-machinery.construction-machinery
- industrial-machinery.factory-automation
- mobility

COMMON_ONLY:

- electronic-components
- materials-chemicals
- project-heavy-industry
- software-saas
- healthcare
- financials
- その他未実装業種

v1.1でPARTIAL moduleのFULL化を検討する。Coverage表にはtarget versionを表示する。

### FULL Promotion Gate

FULLへ昇格するには次を満たす。

1. required/optional/not-applicable dimension contract
2. synthetic edge fixtures
3. representative real-company manual acceptance
4. missing-data behavior
5. cross-period/source validation
6. Dashboard rendering
7. adversarial review

## Events

```json
{
  "event_id": "evt_<digest>",
  "event_fingerprint": "sha256:...",
  "scope": {"company_id": "cmp_...", "segment_id": null},
  "event_type": "EARNINGS",
  "title": "...",
  "status": "SCHEDULED",
  "scheduled_at": "2026-11-01T06:00:00Z",
  "effective_at": null,
  "timezone": "Asia/Tokyo",
  "source_refs": [],
  "linked_watchpoint_ids": [],
  "materiality": "high"
}
```

Event status:

```text
SCHEDULED | OCCURRED | DELAYED | CANCELLED | SUPERSEDED
```

Deduplicationはevent IDだけでなくfingerprintとaliasesを用いる。

## External Drivers

Driverはexternal planeのObservation/Claimを参照する。

```json
{
  "driver_id": "drv-usdjpy",
  "category": "FX",
  "name": "USD/JPY",
  "relevance": "high",
  "sensitivity": "unknown",
  "direction": "POSITIVE|NEGATIVE|MIXED|NONLINEAR|UNKNOWN",
  "mechanism_claim_ids": [],
  "observation_ids": [],
  "linked_watchpoint_ids": [],
  "as_of": "..."
}
```

Sensitivityとdirectionはcompany disclosureまたは明示Inferenceを必要とする。単なる為替変動から利益影響をFactとして断定しない。

## Watchpoints

### State

```text
lifecycle: ACTIVE | CLOSED
assessment: UNRESOLVED | CONFIRMING | CONFIRMED | WEAKENING | INVALIDATED
closure_reason: CONFIRMED | INVALIDATED | NO_LONGER_RELEVANT | SUPERSEDED | null
```

### Signal

```json
{
  "signal_id": "sig-001",
  "signal_type": "CONFIRMATION",
  "match_mode": "STRUCTURED_EVENT",
  "description": "Mass production announcement",
  "predicate": {"event_type": "TECH_MILESTONE", "status": "OCCURRED"}
}
```

Match mode:

```text
STRUCTURED_EVENT | METRIC_THRESHOLD | SOURCE_CLAIM | MANUAL_DECISION
```

LLMはtransition proposalを作れるが、closed predicate matchまたはhuman decision receiptなしにpersisted assessmentを変更しない。

### TransitionReceipt

```json
{
  "transition_id": "wpt_<digest>",
  "watchpoint_id": "wp-001",
  "previous_version": 2,
  "previous_digest": "sha256:...",
  "rule_id": "confirm-tech-milestone-v1",
  "matched_signal_ids": ["sig-001"],
  "new_evidence_ids": ["clm-..."],
  "actor_kind": "deterministic_rule",
  "rationale": "...",
  "recorded_at": "..."
}
```

Confidence上昇には新Evidenceが必要。Closed Watchpointは同一IDでreopenせずsuccessorを作る。source retraction/supersession時のみCONFIRMEDからWEAKENING/INVALIDATEDへの再評価を許可する。

Watchpointはimmutable versions/eventsを持ち、latest indexは再生成可能なprojectionとする。

## Recent Updates

独立truth sourceではなくaudit/change projectionとする。

Grouping key:

```text
research_run_id + event_fingerprint + change_group
```

一つのsourceが財務・capacity・guidanceを別々に重大変更する場合は複数groupを許す。同一change groupの再取得は重複させない。

## Investment Layer

Company stateを変更しないversioned derived documentとする。

```json
{
  "schema_version": 2,
  "status": "FULL|LIMITED|INSUFFICIENT_DATA",
  "as_of": "...",
  "earnings_drivers": [],
  "catalysts": [],
  "risks": [],
  "scenarios": {},
  "valuation": [],
  "expectation_gaps": [],
  "watchpoint_links": [],
  "source_snapshot_digest": "sha256:..."
}
```

- Catalyst/RiskはClaim/Watchpoint referenceを必須とする。
- Bull/Base/BearはSCENARIO。
- valuationはclosed derivation methodを使う。
- price、shares、earnings、FX、currency、corporate-action adjustmentのas-ofを揃える。
- probability、price target、recommendationを根拠なく生成しない。
- 非上場企業はLIMITEDとし、公開Evidenceがある企業理解・scenarioだけを扱う。
- individualized portfolio weightやbuy/sell命令を出さない。

## CLI

Skillはad-hoc importではなく次のCLIを使用する。

```text
python company_research.py coverage ...
python company_research.py prepare <packet.json> --output <prepared.json>
python company_research.py diff <prepared.json> --company-id <id> --output <diff.json>
python company_research.py apply <prepared.json> --expected-base-version <n> --update-kind <kind>
python company_research.py verify --company-id <id>
python company_research.py recover --company-id <id>
python company_research.py watchpoint-update <receipt.json>
python company_research.py render --company-id <id> --output-dir <path>
```

`prepare`、`diff`、`verify`はread-only。`apply`と`watchpoint-update`だけがlocal DBを変更する。外部serviceへwriteしない。

## Dashboard and Exports

### Routes

```text
top
business
financial
technology
competitors
external-drivers
watchpoints
market
investment
reports
sources
update-history
```

interactive settingsはv1対象外。

### Top

- company header、capability、evidence completeness、freshness、last update
- 最大4 KPI。存在しないKPIを別metricで穴埋めしない
- 一枚のRevenue bar + Operating Profit line
- Key Watchpoints
- compact Recent Updates
- 右context: company info、next event、top External Drivers、latest material update

### Chart Contract

- AnnualとQuarterlyは別series/toggleで混ぜない
- Revenue barはzero baseline
- Operating Profitは負値対応
- missing pointを0または補間にしない
- axisにcurrency/unit/scaleを表示
- dual axisを明示し、tooltip/tableでexact valuesを提供
- actual/guidance/consensusを色だけで区別しない
- period/source statusを表示

### Security

- external textはHTML escapeまたはDOM `textContent`
- untrusted contentを`innerHTML`へ渡さない
- script JSONは`</script>`等を安全にserialize
- remote script/font/imageを必須にしない
- self-contained artifactに適切なCSPを付与
- raw source全文を埋め込まない
- malicious fixtureでXSS regression testを行う

### Accessibility

- semantic landmarks、heading hierarchy、keyboard route navigation
- visible focus
- chart `title`/`desc`
- accessible data table fallback
- contrastとnon-color encoding
- `prefers-reduced-motion`
- narrow screenでhorizontal body scrollを発生させない

### Exports

```text
outputs/<company-slug>/
├── manifest.json
├── company-dashboard.html
├── company-report.md
├── company-evidence.json
├── company-watchpoints.json
├── company-financials.csv
└── update-summary.md
```

manifestはcompany ID、snapshot version/digest、generated_at、各artifact digestを持つ。全artifactは同一snapshotから生成する。生成時刻をinputとして受け、固定inputではbyte-identical outputを得られる。

## Research Workflows

### Full

1. identity候補を解決し、既存companyとの衝突を確認
2. primary sourcesを優先してResearchPacketを作成
3. `prepare`
4. validation errors、disagreements、unknownsを確認
5. industry applicabilityをsegment単位で解決
6. candidate state、derivations、diffを作成
7. Watchpoint/Event/External Driver proposalを作成
8. `apply --expected-base-version 0`
9. Investment snapshotを作成
10. export/render

### Incremental

1. latest pointer、snapshot、source boundariesをload
2. category/source別のchecked boundaryを決定
3. material changesをResearchPacketへ追加
4. `prepare`と`diff`
5. corrections/retractions/supersessionsを確認
6. Watchpoint transition proposalをrule/decision receiptへ変換
7. `apply --expected-base-version <current>`
8. Recent Updatesをevent projectionから生成
9. Investment impactを再評価
10. export/render

毎回ゼロからstateを書き直さず、candidate snapshotは前snapshotからmaterializeする。

## Failure Behavior

- identity collision: fail closed
- schema unknown: migration required
- base version mismatch: CONFLICT
- corrupt digest: RECOVERY_REQUIRED
- stale lock: report; automatic steal禁止
- source contradiction: preserve disagreement
- derivation input mismatch: no output
- missing market evidence: Market/valuation unavailable
- unsupported module: COMMON_ONLY
- insufficient evidence: evidence completenessを下げ、capabilityは変えない
- unsafe HTML value: escape and retain text, never execute

## Verification

最低限のtest matrix:

- Linux + Windows path/storage
- duplicate/superseded source
- user-supplied source without URL
- decimal/unit/currency/period mismatch
- derivation registry
- concurrent base-version conflict
- interrupted staging recovery
- corrupt snapshot digest
- segment multi-module routing
- capability vs completeness
- Watchpoint transition receipts
- Event fingerprint dedupe
- External-to-company contamination
- private-company Investment limit
- HTML XSS/accessibility structure
- negative/missing financial chart points
- deterministic export manifest
- end-to-end packet -> prepare -> apply -> render

Release acceptanceは、synthetic fixturesに加えて、NAND企業、工作機械企業、物流機器/フォークリフト企業の実調査を手動監査する。実企業の取得データをrepositoryへ恒久保存する必要はないが、source coverage、unknowns、render、Watchpoints、diffをacceptance recordへ残す。

## v1.0 Deliverables

1. canonical Skill/README/agent metadata
2. ResearchPacket、Source/Claim/Observation/Derivation schemas
3. deterministic CLI
4. transactional local DB、verify、recover
5. typed diff/change events
6. coverage/capability/evidence quality
7. Manufacturing Common
8. NAND、Machine Tools、Logistics/Forklift FULL modules
9. remaining approved manufacturing modules PARTIAL contracts
10. structured Events、External Drivers
11. versioned Watchpoints
12. versioned Investment Layer
13. Top/Financial/Business/Technology/Competitors/Market/Investment/Sources/History views
14. deterministic HTML/Markdown/CSV/JSON exporters
15. focused evals、cross-platform tests、manual release acceptance
16. catalog/host compatibility/context budget validation

## Deferred

- PARTIAL modulesのFULL昇格
- scheduled alerts
- private Git mirror adapter
- portfolio-level multi-company dashboard
- live API server
- user-editable visual layout
