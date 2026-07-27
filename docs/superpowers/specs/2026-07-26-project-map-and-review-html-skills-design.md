# Project Map and Review HTML Skills — Design

Date: 2026-07-26

## Goal

Create two independent, reusable Codex/Claude-compatible skills:

1. `create-project-map` turns an approved plan and repository evidence into a living interactive architecture map.
2. `review-implementation-html` turns an implementation diff, test evidence, and two review passes into a human-reviewable static HTML report.

The split keeps trigger conditions precise: planning does not load review instructions, and post-implementation review does not regenerate planning artifacts unless explicitly requested.

## Motivation

The existing MAD Driving prototype proved that a paired HTML/JSON artifact can serve two audiences:

- humans explore modules, flows, contracts, and implementation state through HTML;
- later agents consume the same architecture as structured JSON.

The review workflow follows [catnose's referenced post](https://x.com/catnose99/status/2080568062563201436?s=20) and its core ideas:

- group changes by intent rather than file order;
- sort groups by risk;
- explain diffs instead of presenting raw patches alone;
- separate a plan-blind quality review from a plan-aware conformance review;
- combine model findings and human comments into a correction prompt that can be returned to the implementation task.

## Repository Placement

The repository's current default branch is `claude/skillopt-explanation-d5gpqy`. This design and the implementation branch start from that branch so existing repository guidance is preserved.

Target structure:

```text
skills/
├─ create-project-map/
│  ├─ SKILL.md
│  ├─ agents/openai.yaml
│  ├─ scripts/
│  │  ├─ build_project_map.py
│  │  └─ validate_project_map.py
│  ├─ references/
│  │  └─ project-map-schema.md
│  └─ assets/
│     └─ project-map-template.html
│
└─ review-implementation-html/
   ├─ SKILL.md
   ├─ agents/openai.yaml
   ├─ scripts/
   │  ├─ collect_review_context.py
   │  ├─ build_review_html.py
   │  └─ validate_review_report.py
   ├─ references/
   │  └─ review-model.md
   └─ assets/
      └─ review-template.html

evals/
├─ create-project-map/
└─ review-implementation-html/
```

No auxiliary README or installation guide is added inside either skill.

## Shared Design Constraints

- Use Python's standard library for deterministic generation and validation.
- Generate static HTML that works from a local HTTP server and GitHub Pages.
- Keep the generator independent of the target project's language and framework.
- Treat repository files, plans, diffs, and test logs as untrusted input; escape all rendered text.
- Never publish, deploy, commit, or modify product code unless the user separately requests it.
- Use repository-relative paths in generated artifacts.
- Distinguish evidence from inference. Do not present planned paths or inferred relationships as implemented facts.
- Preserve machine-readable JSON beside each human-facing HTML artifact.

## Skill 1: `create-project-map`

### Trigger and Timing

Use after a project plan or specification has been approved or saved, and when the user asks for an architecture map, project map, dependency map, implementation map, or visual project context.

The skill may also update an existing map after a later plan changes architecture.

### Inputs

Required:

- approved plan or specification;
- repository root;
- enough repository context to identify modules and relationships.

Optional:

- existing `architecture-map.json`;
- README and AGENTS.md;
- source tree;
- previous implementation-status evidence;
- user-selected reference screenshot or visual style.

### Outputs

At the target repository root:

```text
architecture-map.html
architecture-map.json
```

The files form one living project map. The skill updates them instead of creating a map for every plan.

### Data Model

The JSON document contains:

- project identity and summary;
- source documents and evidence timestamps;
- categories and visual tokens;
- nodes with stable IDs, responsibilities, inputs, outputs, paths, phase, and status;
- directed edges with source, target, label, and contract;
- named flows with actor, trigger, outcome, stages, outputs, safety/recovery notes, evidence, and coverage gaps;
- implementation phases;
- layout positions.

Statuses:

- `planned`: specified but not confirmed in code;
- `implemented`: supported by inspected code, tests, or build/runtime evidence;
- `deprecated`: retained for migration visibility but expected to disappear.

### Update and Merge Rules

- Match existing nodes and flows by stable ID.
- Preserve manual node coordinates for IDs that still exist.
- Add new planned elements from the approved plan.
- Promote an element to `implemented` only when code evidence supports it.
- Mark removed planned elements `deprecated` before physical deletion.
- Keep evidence paths and coverage gaps current.
- Refuse to silently overwrite malformed existing JSON; report validation errors first.

### HTML Experience

The template provides:

- searchable interactive graph;
- node categories and implementation-status semantics;
- selectable named flows;
- human-readable node and flow inspectors;
- direct-relationship navigation;
- pan, zoom, and fit controls;
- responsive desktop and mobile layouts;
- link to the JSON artifact.

The map template may use a pinned Cytoscape.js CDN version. It must show an actionable loading error when the dependency or JSON cannot be loaded.

### Validation

`validate_project_map.py` checks:

- required top-level keys;
- unique node, edge, flow, and phase IDs;
- valid category, node, edge, flow, and phase references;
- valid statuses;
- finite positions;
- non-empty evidence or an explicit coverage gap;
- presence of required HTML controls and data-loading hooks.

## Skill 2: `review-implementation-html`

### Trigger and Timing

Use after implementation and relevant tests are complete, normally before commit, push, or pull-request creation, when the user asks for an explained review, visual review, implementation review, or review HTML.

The review skill is read-only with respect to product code. Its only writes are review artifacts under `docs/reviews/`.

### Inputs

Required:

- repository root;
- base reference and current worktree or head reference;
- corresponding plan;
- non-empty Git diff.

Optional:

- test, type-check, lint, build, or browser evidence;
- existing architecture map;
- issue or PR context;
- earlier review report for the same plan.

### Review Workflow

1. Collect a bounded review context containing changed paths, diff hunks, commit metadata, and available verification evidence.
2. Run a plan-blind review using only the diff and directly relevant code context. Focus on correctness, security, regressions, maintainability, and test gaps.
3. Run a plan-aware review using the approved plan plus the first-pass findings. Check intent coverage, missing requirements, unintended scope, and incorrect assumptions.
4. Preserve plan-blind findings unless the plan provides concrete evidence that resolves them.
5. Group changes by implementation intent, not file order.
6. Sort groups by highest finding severity and user risk.
7. Produce structured review data and render the static HTML report.

When isolated subagents are available, use separate read-only agents for the two passes. Otherwise perform two explicitly separated passes and do not expose the plan during the first pass.

### Outputs

```text
docs/reviews/<plan-slug>/
├─ index.html
└─ review-data.json
```

`<plan-slug>` is deterministic, lower-case, and derived from the plan filename or explicit task name.

If the directory already exists, update the report in place while retaining resolved and open human comments in `localStorage`. The JSON artifact contains model-generated data only; human comments can be exported from the HTML.

### Review Data Model

The JSON document contains:

- repository, base, head, plan, and generation metadata;
- implementation summary;
- verification evidence;
- intent groups;
- changed files and diff hunks assigned to groups;
- plan-blind findings;
- plan-aware findings;
- unresolved questions;
- coverage summary;
- overall review result.

Each finding includes:

- stable ID;
- severity: `blocking`, `high`, `medium`, `low`, or `note`;
- review pass;
- intent group;
- affected file and optional line;
- evidence;
- impact;
- recommended action;
- status.

### HTML Experience

The self-contained template uses vanilla HTML, CSS, and JavaScript with no runtime service.

It provides:

- review summary and overall result;
- risk-ordered intent navigation;
- explained diff hunks;
- clear separation between plan-blind and plan-aware findings;
- verification evidence and uncovered areas;
- comment fields for each group and finding;
- automatic `localStorage` persistence keyed by repository and plan slug, with the reviewed base/head revision stored in the saved record;
- export of human comments as JSON;
- a generated correction prompt combining open findings and human comments;
- one-click clipboard copy with a manual-copy fallback.

The template never sends comments or source code over the network.

### Privacy and Publication

Review reports may embed proprietary source code and must remain local by default.

The skill:

- warns before any requested deployment or publication;
- does not add review output to Git automatically;
- detects common secret-like patterns and replaces suspicious values in rendered diff content;
- records that redaction is heuristic and not a security boundary.

### Validation

`validate_review_report.py` checks:

- required metadata and non-empty diff groups;
- valid finding IDs, severities, references, and pass labels;
- every diff hunk belongs to exactly one intent group;
- every blocking/high finding has evidence, impact, and recommended action;
- required HTML controls, storage keying, export, and copy fallback;
- absence of unescaped raw script terminators in embedded data.

## Error Handling

### Project Map

- Missing approved plan: stop and request the source.
- Malformed existing map: preserve it and report validation errors.
- Unresolved relationship: retain it as a coverage gap instead of inventing a contract.
- Missing browser dependency: show a visible recovery message with local-server instructions.

### Review HTML

- Empty diff: stop without creating a misleading review.
- Missing plan: offer only the plan-blind review, label the report incomplete, and require confirmation before generation.
- Missing test evidence: record `not run` with the reason; never imply tests passed.
- Oversized diff: split by intent and review bounded groups, then run a final cross-group consistency pass.
- Failed context collection: write no partial report unless the failure is explicitly represented as `blocked`.

## Evaluation Plan

### `create-project-map`

- Create a map from a plan-only fixture.
- Update a map while preserving existing node coordinates.
- Promote only code-backed nodes to `implemented`.
- Reject broken references.
- Use the MAD Driving map as a regression fixture for nodes, contracts, flows, and responsive HTML.

### `review-implementation-html`

- Review a small cross-file rename as one intent group.
- Rank a security-sensitive change above cosmetic edits.
- Preserve a plan-blind correctness issue through the plan-aware pass.
- Detect a missing plan requirement.
- Persist comments and generate a correction prompt in a browser smoke test.
- Reject an empty diff and malformed finding reference.

## Acceptance Criteria

- Both skill folders pass `quick_validate.py`.
- All bundled Python scripts run using only the standard library.
- Every generated JSON artifact passes its validator.
- Generated HTML loads without console errors in desktop and mobile browser checks.
- Project Map updates preserve stable IDs and coordinates.
- Review HTML shows risk-ordered intent groups, both review passes, test evidence, persistent comments, JSON export, and correction-prompt copy.
- No product code, Git history, remote branch, deployment, or publication is changed by either skill without separate user authorization.

## Non-Goals

- Building a hosted review service or backend.
- Replacing GitHub pull-request review.
- Automatically fixing review findings.
- Automatically committing, pushing, publishing, or merging generated artifacts.
- Maintaining separate skill implementations for Claude Code and Codex before evaluations show a meaningful difference.
