# Company Research Skill — Reference Analysis

## Benchmarks reviewed

- Koyfin: financial-analysis templates, historical graphs, linked/custom dashboards.
- TIKR: detailed financials, estimates, transcripts, event/watchlist feeds, valuation workflows.
- OpenBB: provider/data separation, source-aware widget metadata, linked parameters.
- AdvancingTitans/stock-analysis: evidence-first company research, explicit time/source boundaries, immutable thesis history.
- Alpha Terminal: three-pane research UI, catalyst calendar, macro context, thesis-impact news triage.

## Patterns to adopt

### Evidence before presentation

Use three planes:

```text
Source / Evidence Plane
        ↓
Canonical Company State
        ↓
Analysis + Presentation
```

Provider payloads must not be read directly by Dashboard code.

### Add DERIVED_FACT

Use machine-distinct epistemic classes:

```text
FACT          directly supported value/statement
DERIVED_FACT  deterministic calculation from supported inputs
INFERENCE     interpretation not mechanically entailed by inputs
SCENARIO      conditional future state
UNKNOWN       not safely determined
```

`DERIVED_FACT` must record formula/method, input evidence IDs, aligned effective periods, units/currency, and a reproducible output.

### Keep company evidence separate from market evidence

FX, rates, NAND pricing, PMIs, geopolitics, commodities, and other External Drivers are contextual evidence. They can bind to sensitivities and Watchpoints but cannot silently become company facts.

### Version Watchpoints instead of overwriting them

Persist a latest materialized view plus immutable versions and audit events:

```text
companies/<company>/
├── watchpoints.json
└── watchpoints/<id>/
    ├── versions/v0001.json
    ├── versions/v0002.json
    └── events/0001-create.json
```

Recent Updates should be generated from normalized change/audit events, not maintained as a second narrative source of truth.

### Keep v1 Dashboard opinionated

Borrow Koyfin/TIKR's separation of detailed financial views, but not their full customization surface. v1 retains the approved fixed hierarchy:

1. company header / coverage;
2. about four headline KPIs;
3. one large Revenue-bar + Operating-Profit-line chart;
4. Key Watchpoints;
5. compact Recent Updates;
6. right-side company info / next earnings / top External Drivers;
7. separate Financial / Technology / Competitors / Market / Investment pages.

### Add explicit event objects

Upcoming earnings, investor days, product launches, regulatory deadlines, and material macro/policy dates should be structured events. Events can bind to Watchpoints and affected company fields.

## Patterns not to adopt in v1

- generic drag-and-drop dashboard builder;
- technical-pattern scanners, options, paper trading, brokerage sync;
- investor-persona roleplay as a core research path;
- mandatory commercial-data providers;
- long-running API server as a requirement;
- copying OpenBB implementation code (architecture inspiration only; its repository is AGPLv3).

## Implementation consequences

1. Add `DERIVED_FACT` before financial computation work.
2. Build provider adapters behind normalized source outcomes.
3. Add immutable Watchpoint/investment-state versions and audit events.
4. Generate Recent Updates from change events.
5. Dashboard consumes validated normalized view models only.
6. Add event/calendar contracts and evidence-to-Watchpoint impact bindings.
7. Add tests for missing-not-zero, time-bound derivations, provider degradation, immutable history, and Recent Update de-duplication.

## Code-reuse policy

Use the reviewed projects as reference implementations, not as codebases to vendor. `AdvancingTitans/stock-analysis` and Alpha Terminal are MIT-licensed, but independent implementation is preferred for v1; any later copied code requires explicit attribution/license handling. OpenBB code is not copied into this repository without a separate licensing decision.
