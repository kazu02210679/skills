# Create Project Map v2 — Design Specification

Date: 2026-08-31
Status: user-approved design for implementation

## Goal and invariants

Extend `create-project-map` with explicit flow/dependency views, snapshot comparisons, and more legible status semantics while preserving the existing JSON contract and Cytoscape renderer. The output remains the two repository-root artifacts `architecture-map.json` and `architecture-map.html`; the skill does not modify product code, commit, publish, or add a runtime service.

The seven existing required top-level fields remain required and unchanged: `project`, `sources`, `categories`, `nodes`, `edges`, `flows`, and `phases`. Existing node IDs, edge IDs, flow IDs, phase IDs, statuses, positions, and directed relationships keep their current meanings. Existing v1 data must continue to validate and render with no conversion step.

Implementation uses Python standard-library code for generation and validation, native browser JavaScript/CSS, and the already pinned Cytoscape.js CDN script. No layout plugin, framework, bundler, or other heavy runtime dependency is introduced.

## Versioning and the additive v2 schema

All v2 fields are optional. Add this top-level field when producing v2 data:

```json
"schemaVersion": 2
```

If `schemaVersion` is absent, the validator and renderer treat the document as schema 1. `schemaVersion: 1` is accepted as an explicit legacy marker. Only integer `1` or `2` is valid; a future or malformed value is an error and must not silently downgrade. Unknown fields remain ignored for forward compatibility, but malformed values in recognized v2 fields fail validation.

The following fields are the complete v2 additions for the first implementation:

```json
{
  "schemaVersion": 2,
  "currentSnapshotId": "v16",
  "snapshots": [
    {"id": "v15", "label": "v15", "kind": "version", "parentId": null},
    {"id": "v15-4", "label": "v15-4", "kind": "version", "parentId": "v15"},
    {"id": "v16", "label": "v16", "kind": "version", "parentId": "v15-4"}
  ],
  "comparisons": [
    {
      "id": "v15-to-v15-4",
      "fromSnapshotId": "v15",
      "toSnapshotId": "v15-4",
      "existingNodeIds": [], "inheritedNodeIds": [], "changedNodeIds": [], "addedNodeIds": [], "replacedNodeIds": [], "removedNodeIds": [],
      "existingEdgeIds": [], "inheritedEdgeIds": [], "changedEdgeIds": [], "addedEdgeIds": [], "replacedEdgeIds": [], "removedEdgeIds": [],
      "existingFlowIds": [], "inheritedFlowIds": [], "changedFlowIds": [], "addedFlowIds": [], "replacedFlowIds": [], "removedFlowIds": [],
      "summary": "Changes from v15 to v15-4."
    },
    {
      "id": "v15-4-to-v16",
      "fromSnapshotId": "v15-4",
      "toSnapshotId": "v16",
      "existingNodeIds": [], "inheritedNodeIds": [], "changedNodeIds": [], "addedNodeIds": [], "replacedNodeIds": [], "removedNodeIds": [],
      "existingEdgeIds": [], "inheritedEdgeIds": [], "changedEdgeIds": [], "addedEdgeIds": [], "replacedEdgeIds": [], "removedEdgeIds": [],
      "existingFlowIds": [], "inheritedFlowIds": [], "changedFlowIds": [], "addedFlowIds": [], "replacedFlowIds": [], "removedFlowIds": [],
      "summary": "Changes from v15-4 to v16."
    }
  ],
  "view": {
    "defaultMode": "flow",
    "defaultFlowId": "request-flow",
    "availableModes": ["flow", "dependency", "combined"],
    "layouts": {
      "flow": {"name": "breadthfirst", "direction": "TB", "fit": "bounded"},
      "dependency": {"name": "preset", "fit": "bounded"},
      "combined": {"name": "preset", "fit": "bounded"}
    }
  }
}
```

### Field rules

- `currentSnapshotId` is optional and references one `snapshots[].id`.
- `snapshots` is an optional array of unique objects. `id` and `label` are non-empty strings; `kind` is `version`, `baseline`, `release`, or `working`; `parentId` is either null or another snapshot ID. The intended comparison chain is ordered `v15` → `v15-4` → `v16`; it is data, not a hard-coded UI special case.
- `comparisons` is an optional array of unique objects. `id`, `fromSnapshotId`, and `toSnapshotId` are non-empty strings; the two snapshot IDs must exist and differ. Every comparison has six state arrays for each collection: `existingNodeIds`, `inheritedNodeIds`, `changedNodeIds`, `addedNodeIds`, `replacedNodeIds`, `removedNodeIds`, and the corresponding `*EdgeIds` and `*FlowIds` arrays; each is an array of IDs present in the current map. An ID may occur in at most one state array per collection. For a replacement, `replacedNodeIds`/`replacedEdgeIds`/`replacedFlowIds` contains the new ID and the matching `removed*Ids` array contains its `replacesId`. `summary` is optional text. A removed item remains in the map as `status: "deprecated"`, so its ID remains addressable and inspectable.
- In schema v2, every ID in a flow's `edgeIds` must reference an edge whose `source` and `target` both occur in that flow's `nodeIds`; this prevents a selected flow from having hidden or ambiguous endpoints. Schema 1 retains the current validator and renderer behavior for legacy `edgeIds`.
- `view.defaultMode` is `flow`, `dependency`, or `combined`. `view.defaultFlowId` references a flow when present. `view.availableModes` is a non-empty subset of `flow`, `dependency`, and `combined`; `combined` is optional and is shown only when listed. `view.layouts.flow` has exactly `name: "breadthfirst"`, `direction: "TB"`, and `fit: "bounded"`; `view.layouts.dependency` and `view.layouts.combined` have `name: "preset"` and `fit: "bounded"`. v2 defaults the flow layout to breadth-first top-to-bottom. Any flow direction other than `TB` or any unsupported flow layout is a validation error rather than an implicit alternative.
- Nodes may add optional `kind`, whose allowed values are `service`, `ui`, `worker`, `data`, `external`, `contract`, `decision`, and `actor`; the renderer maps them respectively to `roundrectangle`, `rectangle`, `hexagon`, `diamond`, `ellipse`, `tag`, `octagon`, and `star` shapes. Nodes, edges, and flows may each add `changeType`, whose exact allowed values are `existing`, `inherited`, `changed`, `added`, `replaced`, and `removed`, plus optional `snapshotIds` (an array of existing snapshot IDs) and `replacesId` (one ID in the same collection). `replacesId` is required for `replaced`, forbidden for other values, and points from the new element to the old element. The old element remains with `changeType: "removed"` and node `status: "deprecated"` where status exists. `status` remains the independent canonical lifecycle field and keeps exactly `planned`, `implemented`, and `deprecated`.
- Edges may add optional `kind`, whose allowed values are `calls`, `data`, `event`, `contains`, `inherits`, `depends-on`, `replaces`, and `unknown`. The renderer maps them to `solid/vee`, `solid/triangle`, `dashed/triangle`, `solid/diamond`, `dotted/tee`, `dashed/vee`, `solid/diamond with 3px width`, and `dotted/circle` line/arrow pairs. An edge without `kind` normalizes to `unknown` for v2 semantics but keeps the v1 neutral line style when rendered as legacy data.
- `categories[].color` remains the category token. For schema v2, validation restricts it to `#RRGGBB` or `#RRGGBBAA`; arbitrary CSS, `url()`, and style fragments are rejected. Schema 1 keeps accepting all previously valid color strings. If a legacy color is unsafe for a CSS token, the renderer uses the neutral border `#626878` and fill `#171922`, retains the category text, and never interpolates the unsafe value. This is a security boundary for v2 style input, not a substitute for escaping.

The validator checks all new references, enum values, duplicate IDs, snapshot parent cycles, finite positions, replacement reciprocity, mutually exclusive comparison state arrays across nodes/edges/flows, and comparison array types in addition to current v1 checks. It reports errors before any existing JSON is overwritten.

## Legacy normalization and migration

The builder and browser normalize into an in-memory model; they do not rewrite legacy input merely because it was opened.

- No `schemaVersion`, `snapshots`, `comparisons`, or `view`: preserve the existing v1 initial “All relationships” view, flow buttons, preset positions, search, fit, and inspector. Do not render v2 mode controls or claim comparison data exists.
- Missing `changeType` or `snapshotIds`: display no change badge and treat the item as `existing` for filtering. Missing `kind` defaults to `service` for v2 shape rendering; missing `kind` in legacy data preserves the existing round-rectangle appearance. Missing edge `kind` defaults to `unknown` only in normalized v2 state and never removes the edge. Missing `status` is invalid because status is already required for nodes.
- Missing `view.defaultMode`: use `dependency` for v2 documents and the v1 “All relationships” behavior for legacy documents. Missing `defaultFlowId` selects the first flow only when flow mode is selected; an empty flow list falls back to dependency mode.
- Missing layout entries: dependency and combined use stable `preset` positions; flow uses the v2 default `breadthfirst`/`TB`/`bounded` only for a v2 document with flow mode available. A valid `position` is never replaced during merge for an existing stable ID.
- If `schemaVersion: 2` is present but a recognized optional object is malformed, show the visible recovery error and stop rendering; do not hide the error by treating the document as v1.

Migration is additive: a later writer may emit the v2 fields alongside all v1 fields, while an older renderer safely ignores the additions and continues to show the core map.

For a replacement, the new element and the old element coexist during merge. The new element carries `changeType: "replaced"` and `replacesId: "old-id"`; the old element is retained with `changeType: "removed"` and, for nodes, `status: "deprecated"`. Neither is physically deleted until a later approved map update removes the deprecated record. A validator rejects a dangling `replacesId`, a cross-collection target, a target not marked removed, or a replacement ID listed in the wrong comparison state.

## Modes and data flow

Mode is presentation state, not a second graph contract:

- Flow mode selects one named flow, renders exactly its `nodeIds` and `edgeIds`, and presents its stages, actor, trigger, outcome, outputs, safety, evidence, and coverage gap. `flow.edgeIds` is authoritative even when an edge has no `kind`; the renderer never infers an edge from stage order, endpoints, label, or kind. The “All flows” choice is a flow union and remains available when there are multiple flows. A legacy flow with no `edgeIds` renders no flow edges, matching the current empty-list behavior.
- Dependency mode renders every node and every directed edge, preserving edge labels/contracts, `kind` line/arrow semantics, and stable positions. It has no implied user journey and must not invent edges from stage order.
- Combined mode renders every node and edge from dependency mode, then applies flow emphasis only to the selected flow's exact `nodeIds` and `edgeIds`; non-flow edges retain their dependency line/arrow semantics. Combined mode is absent unless explicitly listed in `availableModes`.

The end-to-end pipeline is: read approved plan and repository evidence → merge by stable ID while preserving positions → attach evidence/status/change annotations → validate the complete JSON → render escaped metadata and the relative JSON path → browser fetches JSON and normalizes legacy defaults → select mode/snapshot/comparison → apply filters and layout → update graph and text inspector. Any failure before rendering leaves the old map untouched; a browser load failure keeps the recovery message and explains that a local HTTP server and reachable JSON/CDN are required.

## Layout and large-flow behavior

Cytoscape remains the renderer. Dependency mode uses `preset` with stored coordinates. Flow mode uses the built-in `breadthfirst` layout with only its supported options `directed: true`, `circle: false`, `spacingFactor: 1.2`, `avoidOverlap: true`, and `nodeDimensionsIncludeLabels: true`; the implementation does not pass a non-native `direction` option through to Cytoscape. `direction: "TB"` is the v2 contract and default: after breadth-first layout, the renderer verifies that root layers are above downstream layers and applies a deterministic y-axis inversion/position transform when the host returns the opposite orientation. Any explicit flow direction other than `TB` is rejected.

“Bounded” means the implementation does not reduce node spacing or layout dimensions to force a large flow into the viewport. It lays out at the fixed spacing, initializes large flows at the configured zoom floor (never below `0.35`), and shows a concise “Large flow — pan or zoom to explore” hint when the flow exceeds 40 nodes. The user-facing Fit control is an explicit opt-in and may zoom out to show the complete selection, but normal mode changes and flow selection never silently shrink a large flow. Pan, wheel/touch zoom, and reset-fit remain available. Reduced-motion users receive immediate rather than animated viewport changes.

## UI behavior and accessibility

The existing top bar, graph, inspector, flow navigation, search, fit control, and JSON link remain. v2 adds:

- a mode button group with `aria-pressed` for `flow`, `dependency`, and optional `combined`;
- snapshot and comparison selects when valid `snapshots`/`comparisons` exist, with a “Current” option tied to `currentSnapshotId`;
- filters for lifecycle status (`statusFilter`), category (`categoryFilter`), and change type (`changeFilter`), plus toggles `showLabelsToggle`, `showDeprecatedToggle`, and `showChangesOnlyToggle`;
- a legend containing category, lifecycle, and change-type entries; every entry includes text and a glyph/pattern explanation;
- a keyboard-navigable node inventory/list synchronized with the graph selection, because a canvas graph alone is not an accessible substitute for relationships and details;
- an inspector `aria-live="polite"` region, visible focus outlines, descriptive labels, and relationship buttons that preserve keyboard navigation.

Lifecycle is encoded redundantly: status text/chip, a distinct node shape or border pattern, and an accessible label; color is only an additional cue. The node's `kind` selects its base Cytoscape shape, while each change value adds a shape marker, text label, and native border/line treatment: `existing` gets a circle “=” marker, `[existing]` label, and neutral solid 1px border; `inherited` gets a chevron “↥” marker, `[inherited]` label, and dashed border; `changed` gets a square “~” marker, `[changed]` label, and solid 3px border; `added` gets an octagon “+” marker, `[added]` label, and solid 2px border; `replaced` gets a diamond “⇄” marker, `[replaced]` label, and solid 3px border; `removed` gets a triangle “−” marker, `[removed]` label, and dotted border. The corresponding edge change treatment uses solid, dashed, solid 2px, solid, solid 3px, and dotted lines respectively, while retaining the edge-kind arrowhead; the graph label and inspector spell out the value. The legend and accessible labels spell out every value, so glyphs are supplemental rather than required. Deprecated items are dimmed only after their status and text remain readable, and may be shown/hidden with the explicit toggle.

At narrow widths (≤900px), the map remains at least 450px tall and the inspector moves below it; at ≤560px, toolbar controls wrap, mode/filter controls become horizontally scrollable or stacked, and no essential control is hidden. Flow navigation and detail scrolling preserve the current anchor behavior. `prefers-reduced-motion` disables smooth scrolling and animated layout transitions. Keyboard operation, focus visibility, non-color semantics, and contrast target [WCAG 2.2](https://www.w3.org/TR/WCAG22/), especially [Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html), [Keyboard](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html), and [Focus Visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible).

## Snapshot comparison behavior

Selecting a comparison sets `activeComparisonId` and applies its six state arrays (`existing`, `inherited`, `changed`, `added`, `replaced`, `removed`) for nodes, edges, and flows to graph classes and the node inventory. The active comparison arrays take precedence over an element's single `changeType`, because one element can be existing in v15 → v15-4 but changed in v15-4 → v16. Element-level `changeType` is only the current/default annotation used when no comparison is active. The inspector shows “From v15 → v15-4” (or the selected pair), counts by change type, replacement links, and the comparison summary. Selecting a snapshot without a comparison changes the current snapshot label and filters elements whose `snapshotIds` include it; elements without `snapshotIds` remain visible and are marked “snapshot coverage unknown” rather than being falsely attributed or hidden. It does not invent a diff. A missing or invalid comparison selection falls back to Current and announces the fallback in the inspector. The v15 → v15-4 → v16 example is therefore rendered as ordinary data and remains extensible to later versions.

## Security and sanitization

Plans, source paths, labels, descriptions, IDs, evidence, and comparison summaries are untrusted input. Python escapes project title, summary, and data filename; browser rendering uses `textContent` wherever possible and `escapeHtml` for the remaining generated fragments. IDs are validated before being used in Cytoscape selectors or `data-*` attributes. No `eval`, inline JSON execution, or user-controlled HTML is allowed. Relative JSON paths are generated by the builder; external navigation is not created from source paths. Fetch errors, invalid JSON, missing Cytoscape, and validator failures result in a visible, escaped error message with local-server recovery instructions. Category colors are allowlisted as described above. v2 does not require a new CSP; when a host supplies one, it must allow the pinned Cytoscape CDN and same-origin JSON fetch without adding inline data execution.

## Implementation and testing plan (TDD)

Write focused tests before changing behavior, then implement the smallest matching changes in `validate_project_map.py`, `build_project_map.py`, and `project-map-template.html`:

1. Validator tests prove v1 fixtures remain valid, including previously accepted non-hex category colors; v2 accepts the exact v15 → v15-4 → v16 chain and all six comparison states (`existing`, `inherited`, `changed`, `added`, `replaced`, `removed`); invalid mode, `kind`, edge kind, change type, v2 color, parent, comparison reference, duplicate snapshot, malformed optional field, unsupported flow direction, dangling/cross-collection `replacesId`, and inconsistent replacement state fail; deprecated/removed consistency is enforced; finite positions and existing broken-edge rejection remain. A legacy unsafe color remains validator-compatible and renders with the neutral fallback.
2. Builder tests prove all existing escaping and relative filename behavior, v2 metadata does not execute as HTML/JavaScript, and legacy normalization does not mutate input.
3. Renderer/browser tests use a real browser against a local HTTP server. On desktop and narrow mobile widths, verify no console errors; initial mode/default flow; dependency and combined toggles; exact flow `edgeIds` inclusion (including edges without `kind`), all-edge dependency inclusion, combined flow emphasis versus dependency styling; snapshot/comparison selection and active-array precedence; search; lifecycle/category/change filters; labels/deprecated toggles; every node-kind shape and edge-kind line/arrow mapping; node selection and relationship navigation; fit, pan, zoom; keyboard focus and visible status text; reduced-motion behavior; missing JSON/CDN recovery.
4. A fixture with at least 100 nodes in one flow verifies TB layering produced by breadth-first plus the explicit orientation transform, fixed spacing, the large-flow hint, zoom floor ≥0.35, absence of an unsupported `direction` option in the Cytoscape invocation, and that ordinary flow selection does not call an implicit shrinking fit. A fixture with legacy JSON verifies the exact v1 initial experience and neutral rendering fallback for an unsafe legacy color.
5. Run the existing focused suite (`python -m unittest discover -s evals/create-project-map -p "test_*.py" -v`) and the repository validation suite required by `AGENTS.md` after implementation. The implementation must continue to use only the standard library for Python scripts.

Acceptance requires the current validator/evals to pass, all new v2 tests to pass, generated v1 and v2 JSON to validate, and real-browser desktop/mobile checks to show no console errors and the interactions above. The old required JSON contract, stable IDs, positions, directed edges, Cytoscape renderer, and recovery message remain intact.

## Research rationale and sources

- The existing schema and validator are intentionally additive and reference-based; [JSON Schema’s official specification](https://json-schema.org/specification) supports explicit version signaling and validation of structured JSON without requiring a runtime schema package.
- [Cytoscape.js official documentation](https://js.cytoscape.org/) documents serializable graph data, `preset` positions, and built-in layouts, supporting continued use of the pinned renderer and built-in breadth-first flow layout.
- The non-color status/change encodings follow [WCAG 2.2 Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) and keyboard/focus criteria linked above; patterns, text, and inventory controls ensure meaning survives grayscale, color-vision differences, and assistive technology.
- [MDN’s `prefers-reduced-motion` reference](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion) supports the existing native media-query approach for avoiding unnecessary animation without a new library.

## Non-goals

- Replacing the seven-field v1 contract, stable IDs, directed edges, or Cytoscape with a new graph engine.
- Reconstructing architecture from filenames, inventing relationships, or promoting plan-only evidence to implemented status.
- Persisting user filters, coordinates, comments, or browser state back into the JSON artifact.
- Supporting arbitrary user-authored CSS/HTML, remote data services, or a hosted map.
- Adding a dependency/layout plugin, framework, backend, database, or build pipeline.
- Automatically committing, publishing, deploying, migrating, or deleting an existing map; malformed existing JSON remains untouched.
