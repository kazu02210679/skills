# Company Research Skill 設計・計画レビュー

## 判定

**現状の方向性は妥当だが、そのまま実装開始することは推奨しない。**

Evidence-first、Company Understanding と Investment の分離、初回フル調査と差分更新、Coverage Matrix、Watchpoints、External Drivers、固定階層 Dashboard は正しい。一方、正本データの境界、永続化の整合性、業種適用単位、Watchpoint の状態遷移、出力の安全性、v1 の完成条件に未定義部分があり、実装者ごとに異なる設計へ分岐する危険がある。

このレビューに基づく拘束仕様は `2026-08-16-company-research-skill-design-v2.md`、実装順は `2026-08-16-company-research-v1.md` を正本とする。2026-08-14 付の設計書・追補・4本のPhase計画は履歴資料とし、単独では実行しない。

## Critical Findings

### C1. Source・Claim・Observation が一つの Evidence record に平坦化されている

現設計は一つの record に claim、value、source URL、時点、confidence を集約している。この形では、次が正しく扱えない。

- 一つの claim を複数 source が支持・反証する場合
- 一つの source が複数 claim/metric を支持する場合
- 決算訂正、restatement、source retraction
- 同じ数値でも period、scope、accounting basis、currency が異なる場合
- ユーザー提供情報のように URL を持たない正当な source

**修正:** `SourceRecord`、`ClaimRecord`、`ObservationRecord`、`DerivationRecord` を分離する。Claim/Observation は複数 source reference を持ち、source は content digest と locator を持つ。

### C2. `DERIVED_FACT` の自由文 formula だけでは再現可能性が不足する

formula string は表示には使えるが、実装が任意式評価を始めると危険であり、文字列だけでは同じ計算を保証できない。

**修正:** closed registry の `method_id` と `method_version` を正本にする。`operating_margin.v1`、`yoy_growth.v1`、`fcf_simple.v1`、`market_cap.v1` 等を実装し、input IDs、period、unit、currency、parameters、output を記録する。任意式を評価しない。

### C3. ローカルDBの更新がWindows・並行実行・クラッシュに耐えない

現計画の `<timestamp>-<kind>.json` は ISO timestamp を使う実装になりやすく、`:` は Windows filename に使用できない。また、history、event、latest を個別に書くと途中失敗で不整合になる。ロックと expected base version もないため、二つの更新が相互に上書きしうる。

**修正:** Windows-safe UTC run ID、per-company lock、optimistic concurrency、transaction manifest、temp write + fsync + atomic replace、directory fsync、recovery command、content digest を必須化する。

### C4. Company Identity と会計期間の正規化が不足している

`company_id` の生成規則、ticker変更、複数上場、exchange、fiscal calendar、currency、restatement、annual/quarterly/TTM の区別が未定義である。このままでは、同名企業衝突、年次と四半期の混在、異なる通貨・会計基準の比較が起きる。

**修正:** stable company slug と aliases/identifiers を分離し、Financial Observation に `period_kind`、`period_start/end`、`reported_at`、`scope`、`accounting_standard`、`currency`、`unit_scale`、`restatement_status` を持たせる。

### C5. Research acquisition から canonical state までの契約がない

設計は provider payload を canonical state から分離するとしているが、実装計画に provider/host research output を受け取る ingestion packet がない。結果として Codex が各JSONを直接書く実装になり、validation boundary が曖昧になる。

**修正:** `ResearchPacket` を追加する。host browsing/connector/ユーザー入力は packet を作り、CLIの `prepare` が検証・正規化・diffを行い、`apply` がtransactionとして保存する。

### C6. v1 `FULL` の意味が過大で、能力と証拠充足度が混同されている

現計画では semiconductor、machine tools、forklift、construction machinery、factory automation、mobility をすべて v1 FULL とするが、実装は主に declarative dimension contract である。これだけで「FULL」と表示すると分析品質を過大表示する。

**修正:** `capability_status` と `evidence_completeness` を分離する。v1.0 FULL は実企業 fixture と acceptance matrix を持つ `semiconductor.memory.nand`、`machine-tools`、`logistics-equipment` に限定する。DRAM/foundry/logic/equipment、construction machinery、factory automation、mobility は v1.0 PARTIAL、v1.1 FULL候補とする。Manufacturing Common は FULL。

### C7. 業種モジュールを企業単位で適用すると複合企業を誤る

豊田自動織機のような複合企業では、会社全体に mobility と logistics を一括適用すると segment-specific metric が混ざる。

**修正:** module applicability は segment 単位とし、`segment_id`、revenue/materiality share、applicable modules、evidence completeness を持つ。会社ページは segment outputs を集約する。module merge の優先順位と重複dimensionの解決規則を閉じる。

### C8. Watchpoint 状態遷移が曖昧

`CONFIRMED`、`RESOLVED`、`WEAKENING` の関係、確認後に反証が来た場合、administrative close、LLM proposalとdeterministic transitionの境界が未定義である。

**修正:** lifecycle と assessment を分離する。

```text
lifecycle: ACTIVE | CLOSED
assessment: UNRESOLVED | CONFIRMING | CONFIRMED | WEAKENING | INVALIDATED
```

transition receipt に previous digest、rule ID、matched signal IDs、new evidence IDs、actor kind、rationale を必須とする。LLMはproposalだけを出し、closed ruleまたは明示的human decisionが無ければ自動遷移しない。

### C9. DashboardにXSS・アクセシビリティ・chart semanticsの要件がない

source title、company description、Watchpoint rationale 等は外部由来文字列である。HTML generatorが `innerHTML` や未escapeのscript JSONを使うとローカルHTMLでもコード実行が起こる。また視覚デザインだけで、keyboard、screen reader、table fallback、negative operating profit、dual-axis labeling が未定義である。

**修正:** textContent/escaping、安全なJSON埋め込み、no remote script、CSP、malicious fixture tests、semantic landmarks、keyboard navigation、SVG title/desc、accessible table fallback、contrast/reduced-motionを必須化する。Revenue barは0 baseline、Operating Profitは負値対応、missing pointを補間しない。

### C10. Markdown/CSV/Evidence/Update exporter が計画から落ちている

設計上の成果物には `company-report.md`、`company-evidence.json`、`company-financials.csv`、`company-watchpoints.json`、`update-summary.md` があるが、Dashboard計画は「存在すればlink」とするだけで生成Taskがない。

**修正:** exporter task と deterministic output manifest を追加する。HTML、Markdown、CSV、JSON の全成果物は同一 canonical snapshot digest を参照する。

### C11. 決定論的CLIがない

各Python moduleの関数は定義されているが、Skillがどのcommandを呼ぶかが未定義である。Codexがad-hoc Pythonを実行する形では再現性とテスト性が落ちる。

**修正:** `company_research.py` CLIを追加し、`coverage`、`prepare`、`diff`、`apply`、`verify`、`watchpoint`、`render`、`recover` を閉じたsubcommandとして持たせる。defaultは外部writeをせず、local DB applyは明示commandにする。

### C12. 既存の4本の実装計画が実装者に十分な粒度ではない

特にIndustry/Dashboard計画は、「追加する」「可視化する」という作業記述が中心で、error contract、input/output schema、failing test、minimal implementationが不足している。`writing-plans` の要件である、各Taskを独立して実装・レビューできる粒度に達していない。

**修正:** 4本を履歴扱いとし、一つの改訂実装計画へ統合する。各Taskに exact file、interface、test code、command、expected failure/pass、commit boundary を定義する。

## Important Findings

### I1. Coverage と Data Quality を別表示にする

`FULL` は「Skillがそのmoduleを実装済み」であり、「今回の会社に十分なEvidenceがある」という意味ではない。Dashboardには次を別に出す。

```text
Capability: FULL
Evidence completeness: 62%
Freshness: MIXED
Critical gaps: yield, customer qualification
```

### I2. Event dedupe は event_id だけでは不足する

異なるsourceが同一eventへ別IDを付ける。canonical fingerprint、aliases、source references、scheduled/actual/cancelled status、timezoneを持たせる。

### I3. Recent Updates の1 source = 1 item規則は粗い

一つの決算資料が財務・capacity・guidanceを同時に大きく変更する場合は、materiality/category別に複数itemが必要になりうる。`run_id + event_fingerprint + change_group` をgroup keyとする。

### I4. Investment valuationにはas-of alignmentが必要

price、shares、earnings、FX、currency、corporate actionの時点を揃えないvaluationを禁止する。arbitrary price targetは作らず、method、assumptions、sensitivityを表示する。

### I5. Export routeとSidebarが不一致

元設計のSidebarにはReports、Update History、Settingsがあるが、Dashboard計画のroute testには含まれない。v1では `reports`、`sources`、`update-history` を実装し、interactive settingsは対象外とする。

### I6. Visual QAが不足している

synthetic fixtureのbyte-identical testだけではレイアウト崩れを検出できない。desktop/mobile screenshot review、approved hierarchy checklist、long Japanese/English text、negative values、missing valuesのvisual casesを追加する。

## Retained Decisions

以下は変更しない。

- 初回Full + 以降Incremental
- local common DBをoperational source of truthにする
- private Git mirrorはoptional
- Company UnderstandingとInvestmentを分離
- External Driversをcompany factsから分離
- WatchpointsとRecent Updatesを分離
- TopはRevenue bar + Operating Profit lineの一枚を主表示
- 左Sidebarを唯一のformal navigationにする
- PL/BS/CF、Competitors、Marketを別viewにする
- drag-and-drop widget builder、trading execution、mandatory commercial providerはv1対象外

## Review Outcome

**BLOCKED before hardening; APPROVABLE after v2 design and revised plan are adopted.**

実装着手条件は次のとおり。

1. v2設計を正本として明示する。
2. 旧Phase計画をsuperseded扱いにする。
3. revised planのFoundation gateを最初に通す。
4. pilot vertical acceptanceを通さずにCoverageをFULLと表示しない。
5. Dashboard前にend-to-end canonical snapshotを固定する。
