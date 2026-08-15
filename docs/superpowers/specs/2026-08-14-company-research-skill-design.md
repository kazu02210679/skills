# Company Research Skill 設計

## 目的

`company-research` を、企業を一度だけ要約するためのレポート生成 Skill ではなく、企業・技術・財務・競争・外部環境・投資判断を継続的に理解するための research system として追加する。

初回は対象企業をフル調査し、その後は前回の調査状態を正本として差分更新する。企業ごとの Evidence、Watchpoints、財務、技術ロードマップ、外部ドライバー、更新履歴をローカル共通 DB に保持し、必要なときに現在の workspace へ Dashboard、Markdown、CSV 等を出力する。

分析は次の二層を明示的に分離する。

1. **Company Understanding Layer** — 企業・事業・製品・技術・財務・競争環境を理解する正本。
2. **Investment Layer** — Company Understanding Layer の Evidence を参照して Catalyst、Risk、Valuation、株価・業績ドライバーを分析する派生層。

技術的に重要な事実と、株価に重要な材料を同一視しない。

## 成功条件

1. 上場企業について、企業理解から投資判断まで一貫した調査ができる。
2. 非上場企業について、公開情報で裏付けられる企業・技術理解まで実行し、欠落財務や推定 valuation を捏造しない。
3. 初回フル調査後は、既存 DB を読み、前回以降に変化した Evidence と Watchpoint 状態を差分更新できる。
4. 重要な主張・数値・将来仮説に Evidence provenance を持たせ、Fact / Inference / Scenario を区別する。
5. 企業固有の「今後見るべきポイント」を Watchpoint として保存し、confirmation / invalidation signal を追跡できる。
6. 為替、金利、産業需給、地政学、原材料等を External Drivers として企業固有の感応度付きで追跡できる。
7. Dashboard を入口とし、会社を開いて数秒で「現在地」「業績変化」「重要論点」「外部環境」「最近の変化」が把握できる。
8. 対応業種の範囲を Coverage Matrix で機械可読かつ人間可読に表示し、未対応業種へ不適切な分析テンプレートを強制しない。
9. Skill 本体と企業調査データを分離し、企業データを `skills` repository に保存しない。
10. focused eval/test により evidence labeling、差分更新、coverage fallback、Watchpoint 遷移、Dashboard data contract を検証する。

## 非対象

初版では次を行わない。

- 売買注文の自動実行
- 投資助言や投資成果の保証
- 非公開情報の推測または取得
- 有料データの無断保存・再配布
- PDF や Web ページの大量コピーを Git repository に保存
- 全業種に同じ KPI を強制
- 企業価値、需要、技術ロードマップを根拠なく補完
- リアルタイム市場データを必須要件とすること
- Graph DB の導入
- Web サーバ常駐を前提とする企業 DB

## Activation Policy

`company-research` は、ユーザーが企業調査、企業比較、企業の継続調査、決算・技術・競争・Watchpoint 更新、または company dashboard の作成・更新を明示的に求めた場合に起動する。

単純な株価確認、一般ニュース検索、単一財務指標の質問では自動的にフル調査を開始しない。

## 対象企業

### 上場企業

Company Understanding Layer と Investment Layer の両方を使用できる。

### 非上場企業

Company Understanding Layer を使用する。公開された財務数値がある場合のみ使用し、欠落した revenue、profit、valuation、market cap 等を埋めない。

Investment Layer は `LIMITED` とし、株価・時価総額・上場企業向け valuation を要求しない。

## アーキテクチャ

```text
User / Codex
    |
    v
company-research Skill
    |
    +-- Source Research
    +-- Evidence Normalization
    +-- Company Understanding
    +-- Industry Module
    +-- External Drivers
    +-- Watchpoints
    +-- Investment Layer
    +-- Incremental Update
    +-- Visualization / Export
    |
    v
Local Company Research DB  <-- canonical operational state
    |
    +-- optional private Git mirror
    +-- workspace exports
```

### Skill 本体

正本は `skills/company-research/` に置く。

想定構成:

```text
skills/company-research/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── config/
│   └── coverage.yaml
├── references/
│   ├── research-playbook.md
│   ├── evidence-model.md
│   ├── company-schema.md
│   ├── watchpoints.md
│   ├── external-drivers.md
│   ├── investment-layer.md
│   ├── dashboard-contract.md
│   ├── coverage-matrix.md
│   └── industries/
│       ├── manufacturing-common.md
│       ├── semiconductor.md
│       ├── industrial-machinery.md
│       └── mobility.md
├── scripts/
│   ├── validate_company_data.py
│   ├── diff_company_state.py
│   ├── update_watchpoints.py
│   ├── generate_report.py
│   └── generate_dashboard.py
└── tests/
```

Skill 内には特定企業の永続データを入れない。

## データ保存

### 正本

企業調査データの operational source of truth はローカル共通 DB とする。

既定値:

```text
~/.company-research/
```

Windows では通常:

```text
C:\Users\<user>\.company-research\
```

環境変数 `COMPANY_RESEARCH_HOME` が設定されている場合はそちらを優先する。

### ディレクトリ例

```text
~/.company-research/
├── index.json
├── companies/
│   ├── kioxia/
│   │   ├── profile.json
│   │   ├── evidence.json
│   │   ├── financials.json
│   │   ├── technology.json
│   │   ├── competitors.json
│   │   ├── external-drivers.json
│   │   ├── watchpoints.json
│   │   ├── investment.json
│   │   └── history/
│   │       ├── 2026-08-14-full.json
│   │       └── 2026-09-01-update.json
│   └── toyota-industries/
└── archive/
```

### GitHub 同期

GitHub 同期は任意とする。必要な場合は `skills` repository ではなく、別の **private repository** を mirror として使う。

ローカル DB を operational source とし、GitHub は backup / history mirror とする。

Git mirror に含めてよい例:

- profile
- Watchpoints
- 構造化財務データ
- 自作の要約
- Evidence の URL、title、checked_at、digest
- 差分履歴

原則として含めない:

- ダウンロード済み有報・決算 PDF 本体
- Web ページ全文コピー
- API cache
- 有料ライセンスデータ
- token / credential

archive されたソースには path、URL、取得日、hash 等の参照情報だけを正本に残せる。

## Evidence Model

すべての重要な claim は epistemic status を持つ。

```text
FACT       公開一次情報またはユーザー提供情報で直接確認できる
INFERENCE  複数の事実から導いた解釈・推論
SCENARIO   将来の条件付きシナリオ
UNKNOWN    裏付けられず、安全に推測しない
```

各 Evidence は最低限次を持つ。

```json
{
  "claim_id": "claim-tech-001",
  "claim": "...",
  "epistemic_status": "FACT",
  "confidence": "high",
  "source_url": "https://...",
  "source_title": "...",
  "source_kind": "official_ir",
  "checked_at": "2026-08-14",
  "effective_at": "2026-08-01",
  "notes": "..."
}
```

### Source Priority

原則として次の順に優先する。

1. 有価証券報告書 / Annual Report / 10-K 等
2. 決算短信・決算説明資料・公式 IR
3. 統合報告書・中期経営計画
4. 公式技術資料・製品資料・ニュースリリース
5. 官公庁・規制当局・業界団体
6. 競合企業の一次情報
7. 信頼できる二次情報

検索結果 snippet だけを重要 claim の証拠にしない。

## Watchpoints / Forward View

Watchpoint は「ニュース一覧」ではない。今後確認すべき仮説または重要論点を永続的に追跡する。

例:

```json
{
  "watchpoint_id": "wp-tech-001",
  "title": "次世代製品・技術の投入時期",
  "category": "technology_roadmap",
  "importance": "high",
  "horizon": "2027-2030",
  "status": "open",
  "epistemic_status": "INFERENCE",
  "confidence": "medium",
  "current_view": "...",
  "why_it_matters": "...",
  "evidence_ids": ["claim-tech-001"],
  "confirmation_signals": ["量産開始", "顧客採用", "正式製品発表"],
  "invalidation_signals": ["開発延期", "中止", "競合技術への切替"],
  "investment_relevance": "high",
  "last_checked": "2026-08-14"
}
```

### Watchpoint 状態

```text
OPEN
CONFIRMING
CONFIRMED
WEAKENING
INVALIDATED
RESOLVED
```

更新時に新 Evidence を既存 Watchpoint へ binding し、confidence と状態を変更する。過去状態は history に保持する。

## Recent Updates

Recent Updates と Watchpoints は分離するが、同格の大規模領域にはしない。

- **Watchpoints**: これから何を見るべきか。
- **Recent Updates**: 前回以降に何が変わったか。

Recent Updates は最新数件の差分フィードとして表示し、可能な限り Watchpoint / Financial / Technology / Competitor 等のどの正本データを更新したかを示す。

```text
new source / event
    -> normalized evidence
    -> affected Watchpoint or company field
    -> state/confidence change
    -> dashboard update
    -> investment impact, if any
```

## External Drivers

企業外部の重要因子を Company Understanding Layer に持つ。

カテゴリ:

- FX
- Interest rates / macro
- Industry demand and price indices
- Commodity / energy
- Regulation
- Geopolitics / trade policy

全企業へ同じ項目を表示しない。企業ごとに relevance / sensitivity を持たせる。

```json
{
  "driver_id": "fx-usdjpy",
  "name": "USD/JPY",
  "category": "fx",
  "relevance": "high",
  "sensitivity": "high",
  "direction": "weaker_jpy_positive",
  "mechanism": "海外売上・輸出採算への影響",
  "evidence_ids": [],
  "linked_watchpoints": []
}
```

トップ Dashboard には relevance の高い 2-4 件だけ表示する。

## Company Understanding Layer

共通コアでは最低限次を扱う。

### Company Profile

- 正式名称
- ticker / exchange
- 上場・非上場
- headquarters
- established
- employees
- fiscal year end
- major segments
- major products / services

### Business

- segment structure
- revenue / profit mix
- geography
- customer / end-market exposure
- business model
- important subsidiaries / alliances

### Financial

- Revenue
- Operating profit
- Operating margin
- Net income
- EPS
- ROE / ROIC where meaningful
- Operating CF
- FCF
- CAPEX
- cash / debt
- working capital where meaningful

### Strategy

- capital allocation
- R&D
- capacity expansion
- M&A
- portfolio changes
- medium-term targets

### Competition

- major competitors
- market positioning
- product / technology comparison
- financial comparison
- cost / capacity / geographic advantage

### Risks

- demand cycle
- execution
- technology
- customer concentration
- regulation
- FX / macro
- geopolitical

## Industry Architecture

`manufacturing` を上位カテゴリとして置くが、メーカー全体を一つの分析テンプレートで扱わない。

```text
common
└── manufacturing-common
    ├── semiconductor
    ├── industrial-machinery
    │   ├── machine-tools
    │   ├── logistics-equipment
    │   ├── construction-machinery
    │   └── factory-automation
    └── mobility
```

### Manufacturing Common

- segment mix
- revenue / margin
- CAPEX
- R&D
- production footprint
- capacity
- supply chain
- product portfolio
- product lifecycle
- service / aftermarket where relevant

### Semiconductor — v1 FULL

例となる企業タイプ: NAND / DRAM / Foundry / logic / semiconductor manufacturing ecosystem。

固有観点:

- process / cell generation roadmap
- layer / node / architecture transitions
- bit growth
- wafer capacity
- yield / cost roadmap when public
- ASP / supply-demand cycle
- CAPEX
- utilization
- SSD / memory productization
- AI / data center exposure
- customer qualification / product ramp

### Industrial Machinery — v1 FULL

#### Machine Tools

- order cycle
- domestic / overseas orders
- end-market exposure
- backlog
- equipment investment cycle
- product generation
- CNC / control
- 5-axis / multi-tasking
- automation / robot integration
- software / digital twin
- services
- capacity expansion

#### Logistics Equipment / Forklift

- model generation / model change cycle
- unit sales
- electrification
- battery / FC transition
- autonomous operation
- warehouse automation
- installed base
- service / aftermarket
- logistics-system integration

#### Construction Machinery

- demand by geography
- fleet cycle
- mining / infrastructure exposure
- electrification / autonomy
- utilization / aftermarket
- dealer network

#### Factory Automation

- orders
- book-to-bill / backlog where available
- robot / CNC / servo demand
- semiconductor / auto / electronics capex exposure
- automation penetration

### Mobility — v1 FULL

- model / platform cycle
- xEV mix
- product content per vehicle
- OEM exposure
- powertrain transition
- electronics / ADAS exposure
- regional vehicle production
- customer concentration

## Coverage Matrix

Coverage は Skill の正式仕様であり、README の手書き表だけにしない。

機械可読の正本を `config/coverage.yaml` に置き、README / `references/coverage-matrix.md` の表はそこから生成できる設計にする。

### Status

```text
FULL         業種固有分析まで対応
PARTIAL      一部の固有分析のみ対応
COMMON_ONLY  共通企業分析のみ対応
OUT_OF_SCOPE 現在の対象外
```

### Roadmap

| Version | Coverage | 主な追加分析 |
|---|---|---|
| v1 | Common, Manufacturing Common, Semiconductor, Industrial Machinery, Machine Tools, Logistics/Forklift, Construction Machinery, Factory Automation, Mobility | Evidence, Watchpoints, External Drivers, Investment Layer, Dashboard, incremental update |
| v2 | Electronic Components, Materials & Chemicals, Project-based Heavy Industry | component content, utilization, materials pricing, capacity expansion, backlog/project economics |
| v3 | Software / SaaS, IT Services | ARR, NRR, ARPU, CAC, churn, pricing, inference cost |
| v4 | Healthcare / Pharma / Medical Devices | pipeline, trials, approval, patent lifecycle, regulatory events |
| v5 | Bank / Insurance / Securities | NIM, credit cost, CET1, AUM, underwriting / investment sensitivity |
| Later | Energy, Utilities, Retail, Telecom, Real Estate etc. | industry-specific modules |

未対応企業でも `COMMON_ONLY` で調査を継続できる。未対応業種に別業種の固有 KPI を強制しない。

## Investment Layer

Company Understanding Layer の Evidence を参照する派生層とする。

含むもの:

- earnings drivers
- catalysts
- downside risks
- bull / base / bear scenarios
- earnings revisions
- valuation metrics appropriate to sector
- consensus where legally and technically available
- market expectations versus company guidance
- Watchpoint investment relevance

Investment Layer は事実、推論、シナリオを混ぜない。

## Market / Stock View

株価情報は Top Dashboard に詰め込まず専用 view を持つ。

表示候補:

- stock price history
- 1Y / 3Y / 5Y
- relative performance versus benchmark
- relative performance versus competitors
- valuation history
- earnings revisions
- consensus
- event overlay

Event Overlay では決算、製品発表、M&A、大型受注、規制イベント、主要 Watchpoint update を株価 timeline 上へ重ねられるようにする。

Market View と Investment View は別物とする。Market View は市場で何が起きたか、Investment View は Evidence をどう解釈するかを扱う。

## Competitor View

競合情報は専用 view とする。

- revenue / growth / margins
- market share where reliable
- CAPEX
- product / technology generation
- capacity
- geography
- customer / end-market exposure
- valuation for listed peers

単一の総合点やレーダーチャートを主表示にせず、比較対象に意味のある指標を選ぶ。

## Financial Views

Top には財務情報を詰め込まない。

### Top Dashboard

主要スナップショットは 4 項目前後に制限する。

例:

- Revenue
- Operating profit
- Operating margin
- Market cap（上場企業）

### 業績トレンド

トップの最大グラフは一枚に統合する。

- Revenue: bar
- Operating profit: line
- annual / quarterly toggle
- actual / company guidance / consensus を区別できる data contract
- 必要なら左右 axis を使用

ROE、Operating CF、FCF、CAPEX 等の小型チャートをトップへ大量に置かない。

### Financial Detail

```text
Financial
├── Overview
├── PL
├── BS
├── CF
├── Profitability
├── Capital Allocation
└── Segment Financials
```

#### PL

Revenue、gross profit、operating profit、net income、margin の構造と推移を表示する。

#### BS

cash、inventory、fixed assets、interest-bearing debt、equity 等の構成と推移を表示する。

#### CF

Operating CF -> CAPEX -> FCF -> dividends / buyback / M&A / debt reduction の cash allocation を可視化する。

## Dashboard UX

Dashboard は会社を開いた最初の画面とする。

### 表示原則

1. **Snapshot は最小限、Trend を優先する。**
2. 数字の羅列より変化を図示する。
3. Top は「何が重要か」を 5 秒程度で把握できる密度にする。
4. 詳細な財務表、BS / PL / CF、競合、株価は別 view へ送る。
5. 左 sidebar を唯一の正式ナビゲーションとする。
6. 右 panel は navigation の複製ではなく、会社情報、次回決算、External Drivers、重要な最新差分などの contextual summary に使う。
7. 同じカテゴリの Quick Access を上下左右へ重複配置しない。

### 左 Sidebar

```text
Top
Business
Financial
Technology / Products
Competitors
External Drivers
Watchpoints
Market / Stock
Investment
----------------
Reports
Update History
Settings
```

### Top Main Area

```text
Company header + coverage + last updated
KPI snapshot (about four)
Large Revenue-bar + Operating-profit-line chart
Key Watchpoints
Recent Updates (small feed)
```

### Right Context Panel

- company information
- next earnings date
- top External Drivers
- latest material update summary

右 panel に full navigation menu を複製しない。

## Full Research Workflow

```text
1. Resolve company identity
2. Resolve listed/private status, ticker, exchange, fiscal calendar
3. Detect coverage and industry module
4. Read existing local state if present
5. Gather primary sources
6. Normalize facts and financials
7. Build company/segment/product/technology understanding
8. Run industry-specific analysis
9. Build competitor set
10. Build External Drivers
11. Generate Watchpoints
12. Build Investment Layer where eligible
13. Validate provenance and unknowns
14. Persist canonical local state
15. Generate Dashboard / report exports
```

初回調査では既存 state が無いことを明示し、full snapshot を history に保存する。

## Incremental Update Workflow

```text
1. Load last canonical company state
2. Determine last checked boundary by source/category
3. Search only for material changes since boundary
4. Normalize new Evidence
5. Diff against previous state
6. Update affected financial / business / technology / competitor fields
7. Bind new Evidence to Watchpoints
8. Recompute Watchpoint state/confidence
9. Re-evaluate affected External Drivers / Investment View
10. Write update history
11. Regenerate Dashboard
```

既存情報を毎回ゼロから上書きしない。削除・矛盾・訂正は history へ残す。

## Change Classification

差分は最低限次に分類する。

```text
FINANCIAL
BUSINESS
PRODUCT
TECHNOLOGY
CAPACITY
COMPETITOR
EXTERNAL_DRIVER
REGULATORY
GEOPOLITICAL
MARKET
WATCHPOINT
OTHER
```

Materiality を `low / medium / high / critical` で持てるようにする。

## Export

企業 DB の正本とは別に、workspace へ必要時に出力する。

```text
outputs/<company>/
├── company-dashboard.html
├── company-report.md
├── company-evidence.json
├── company-watchpoints.json
├── company-financials.csv
└── update-summary.md
```

Dashboard は export artifact であり、DB の正本ではない。

## Source Freshness

各データ種別で `checked_at` と `effective_at` を分離する。

例:

- FY2025 revenue の effective_at は決算期末または対象会計年度。
- source の checked_at は調査実行日。
- stock price の effective_at は価格日時。

古い facts が新しい upload timestamp によって新情報と誤認されないよう、document content の period を優先する。

## Failure / Uncertainty Behavior

- 一次情報が見つからない重要 claim は `UNKNOWN` または低 confidence とする。
- competitor price / market share / capacity が矛盾した場合は単一値に潰さず disagreement を保持する。
- industry module 未対応の場合は `COMMON_ONLY` へ fallback する。
- Investment Layer の入力が不足する場合は analysis limitation を表示する。
- forecast や future roadmap は Fact として表示しない。
- Watchpoint の horizon を根拠なく精密化しない。

## Security / Rights

- private analytics、customer data、billing、内部資料はユーザーが明示的に提供・許可した場合だけ扱う。
- credential は DB に保存しない。
- externally licensed data は license terms を尊重し、再配布可能性を推測しない。
- 自動更新が外部 write を要求する場合は別途明示的な許可・governance を必要とする。

## Testing / Evals

### Trigger / Non-trigger

- 企業全体調査要求で起動する。
- 単純な株価照会でフル調査を開始しない。

### Evidence

- Fact に source が無ければ fail / downgrade する。
- Inference を Fact として保存しない。
- Unknown を数値で埋めない。

### Coverage

- semiconductor -> FULL v1
- machine-tools -> FULL v1
- materials-chemicals -> COMMON_ONLY v1 / planned v2
- non-listed company -> Investment LIMITED

### Incremental Update

- 前回 state を維持したまま新 Evidence だけ追加できる。
- correction が来た場合に旧値を history へ保持する。
- 重複 source/event を二重計上しない。

### Watchpoints

- confirmation signal で状態が前進する。
- invalidation signal で WEAKENING / INVALIDATED へ移る。
- evidence 無しに confidence が上がらない。

### Dashboard Contract

- Top の主要業績グラフは Revenue bar + Operating Profit line。
- Top の小型 KPI/chart 数を制限する。
- 左 nav と右 panel が重複した full navigation を持たない。
- unsupported metric は空値または明示的 unavailable とし、0 に変換しない。

## v1 Deliverables

v1 の完成条件は次のとおり。

1. `company-research` canonical Skill を `skills/` に追加。
2. Evidence schema と validator。
3. local DB path resolution (`COMPANY_RESEARCH_HOME` + default)。
4. full research / incremental update data contract。
5. Watchpoint schema / updater。
6. External Driver schema。
7. Coverage Matrix と fallback。
8. Manufacturing Common。
9. Semiconductor module。
10. Industrial Machinery module。
11. Machine Tools / Logistics-Forklift / Construction Machinery / Factory Automation submodules。
12. Mobility module。
13. Company Understanding / Investment separation。
14. Competitor / Market-Stock / Financial detail contracts。
15. Dashboard HTML generator with approved information architecture。
16. focused tests/evals。
17. README / catalog registration。

## 将来拡張

- scheduled update / alert は v1 の core persistence と独立して追加できるようにする。
- private Git mirror sync は optional adapter とし、core workflow の必須依存にしない。
- multiple-company portfolio dashboard は company-level DB が安定した後に別機能として追加する。
- user-defined Watchpoints を標準 Watchpoint と同じ schema で保存できるよう拡張可能にする。
- sector-wide research と peer graph は company research の上位 layer として追加できる。

## 設計上の判断

1. **初回フル調査 + 差分更新**を採用する。毎回ゼロから調べ直さない。
2. **共通コア + 業種別モジュール**を採用する。万能テンプレートにはしない。
3. **Company Understanding + Investment Layer** を分離する。
4. **ローカル共通 DB を正本**にする。GitHub は optional private mirror。
5. **上場企業中心、非上場は可能範囲まで**とする。
6. v1 は **Manufacturing 中心**で、Semiconductor / Industrial Machinery / Mobility を FULL 対応する。
7. Coverage Matrix を正式仕様としてバージョン別に公開する。
8. Dashboard は **B 案のストーリー型レイアウト**を採用し、左 sidebar を正式 nav、右 panel を context summary に限定する。
9. Top の最大グラフは **Revenue bar + Operating Profit line の一枚**とする。
10. Watchpoints、External Drivers、Recent Updates を別責務で保持し、相互に binding する。
