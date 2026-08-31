# Project Map Schema

Use UTF-8 JSON. The v1 contract remains the seven required top-level fields;
v2 adds optional, reference-based metadata and does not require a conversion.
The Python validator is authoritative. It reports all errors before the builder
writes an HTML output, so invalid existing JSON remains untouched.

## v1 contract

The following fields are required and keep their existing meanings:

| Field | Type | Required content |
|---|---|---|
| `project` | object | `id`, `title`, `summary` |
| `sources` | array | `{path, kind}` using repository-relative paths |
| `categories` | array | `{id, label, color}` |
| `nodes` | array | Components and contracts represented as graph nodes |
| `edges` | array | Directed relationships |
| `flows` | array | Selectable end-to-end paths |
| `phases` | array | `{id, label, description}` |

Every collection ID is unique within that collection. References must point to
the collection named by the field. Node `position.x` and `position.y` are finite
numbers. A node or flow must have non-empty `evidence` or an explicit
`coverageGap`; evidence for a planned node may identify the approved plan.

### Node

```json
{
  "id": "api-service",
  "label": "API Service",
  "category": "service",
  "status": "implemented",
  "phase": "phase-1",
  "description": "Accepts and validates requests.",
  "responsibilities": ["Validate input"],
  "inputs": ["HTTP request"],
  "outputs": ["Command"],
  "sourcePaths": ["src/api.py"],
  "evidence": ["src/api.py", "tests/test_api.py"],
  "coverageGap": "",
  "position": {"x": 120, "y": 180}
}
```

`status` is exactly `planned`, `implemented`, or `deprecated`: planned means
specified but unconfirmed, implemented means confirmed by inspected code,
tests, build output, or runtime evidence, and deprecated means retained to show
a migration or removal.

### Edge

```json
{
  "id": "api-to-worker",
  "source": "api-service",
  "target": "worker",
  "label": "dispatches",
  "contract": "Command"
}
```

Edges are directed; `source` and `target` must be node IDs. The renderer never
infers an edge from a stage, endpoint label, or ordering.

### Flow and phase

```json
{
  "id": "request-flow",
  "label": "Request flow",
  "description": "Accept and process a request.",
  "actor": "User",
  "trigger": "A request arrives.",
  "outcome": "A result is returned.",
  "nodeIds": ["api-service", "worker"],
  "edgeIds": ["api-to-worker"],
  "stages": [
    {
      "id": "accept",
      "label": "Accept",
      "description": "Validate the request.",
      "nodeIds": ["api-service"],
      "backstage": "Parse and validate input.",
      "produces": ["Command"]
    }
  ],
  "outputs": ["Result"],
  "safety": ["Reject invalid input"],
  "evidence": ["plans/request-flow.md"],
  "coverageGap": "Runtime traces are not available."
}
```

`nodeIds` and `edgeIds` reference existing nodes and edges. Stage node IDs must
be nodes and should normally occur in the parent flow. A phase has `{id,
label, description}`. Legacy flow edge behavior is preserved: an empty
`edgeIds` list renders no flow edges.

## Additive v2 fields

Set `schemaVersion` to integer `2` when producing v2 data. All other v2 fields
are optional. Absent `schemaVersion` means schema 1; explicit integer `1` is
also accepted. Only `1` and `2` are valid, and a future, boolean, or malformed
value is an error rather than a silent legacy downgrade. Unknown fields remain
ignored for forward compatibility. Recognized v2 fields with malformed values
produce a recovery error and stop rendering.

This is the complete v15 → v15-4 → v16 shape used by the fixture; the chain is
ordinary data, not a hard-coded UI special case:

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

### Snapshot metadata

- `currentSnapshotId` is optional and must reference `snapshots[].id` when
  present.
- `snapshots` is an optional array of unique objects. Each object requires
  non-empty string `id` and `label`, `kind` equal to `version`, `baseline`,
  `release`, or `working`, and `parentId` present as `null` or a known snapshot
  ID. Duplicate IDs, unknown parents, and parent cycles are errors.
- `snapshotIds` on a node, edge, or flow is optional, must be an array of
  unique IDs from `snapshots`, and describes coverage. It never changes the
  stable element ID.

### Comparisons

`comparisons` is an optional array of unique objects. Each comparison requires
non-empty string `id`, `fromSnapshotId`, and `toSnapshotId`; both snapshots
must exist and differ. `summary`, when present, is text. For each collection,
all six arrays are required:

`existingNodeIds`, `inheritedNodeIds`, `changedNodeIds`, `addedNodeIds`,
`replacedNodeIds`, `removedNodeIds`, with the corresponding `EdgeIds` and
`FlowIds` suffixes. Every value must be an ID in its own collection, and an ID
may occur in at most one state array for that collection. The six exact states
are `existing`, `inherited`, `changed`, `added`, `replaced`, and `removed`.

For a replacement, the new ID is in `replaced*Ids`, its `replacesId` points to
an element in the same collection, and that old ID is in `removed*Ids`. The
new element has `changeType: "replaced"`; the old element has
`changeType: "removed"`, and a removed node also has `status: "deprecated"`.
The validator rejects dangling or cross-collection targets, a target that is
not removed, a node target that is not deprecated, or a replacement listed in
the wrong comparison state. The two records coexist until a later approved
map update removes the deprecated record.

These compact records show the required reciprocity:

```json
{
  "id": "worker-v2",
  "status": "implemented",
  "kind": "worker",
  "changeType": "replaced",
  "replacesId": "worker-v1",
  "snapshotIds": ["v15-4", "v16"]
}
```

```json
{
  "id": "worker-v1",
  "status": "deprecated",
  "kind": "worker",
  "changeType": "removed",
  "snapshotIds": ["v15"]
}
```

### Element annotations and colors

The optional `kind` on a node is one of `service`, `ui`, `worker`, `data`,
`external`, `contract`, `decision`, or `actor`, mapped respectively to
Cytoscape shapes `roundrectangle`, `rectangle`, `hexagon`, `diamond`,
`ellipse`, `tag`, `octagon`, and `star`.

The optional edge `kind` is one of `calls`, `data`, `event`, `contains`,
`inherits`, `depends-on`, `replaces`, or `unknown`. The line/arrow mapping is:

| Edge kind | Line / arrow |
|---|---|
| `calls` | `solid/vee` |
| `data` | `solid/triangle` |
| `event` | `dashed/triangle` |
| `contains` | `solid/diamond` |
| `inherits` | `dotted/tee` |
| `depends-on` | `dashed/vee` |
| `replaces` | `solid/diamond`, 3px |
| `unknown` | `dotted/circle` |

Nodes, edges, and flows may each add `changeType` with one of the six states,
`snapshotIds`, and `replacesId`. `replacesId` is required only for
`changeType: "replaced"` and forbidden otherwise; it must be a non-empty ID in
the same collection. A missing edge `kind` normalizes to `unknown` in v2, but
does not remove the edge and preserves the neutral v1 style for legacy data.

In v2, `categories[].color` must match `^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$`:
exactly `#RRGGBB` or `#RRGGBBAA`. CSS functions, `url()`, and style fragments
are rejected. Schema 1 retains previously accepted color strings. When a v1
color is unsafe as a CSS token, the renderer uses neutral border `#626878` and
fill `#171922`, retains the category text, and never interpolates the unsafe
value.

## v2 flow and view rules

In v2, every `flow.edgeIds` entry must reference an edge whose `source` and
`target` both occur in that flow's `nodeIds`; schema 1 keeps the legacy
validator behavior. This is an endpoint check, not an inferred relationship.

`view` is optional. When present, its recognized fields are:

- `defaultMode`: `flow`, `dependency`, or `combined`.
- `defaultFlowId`: an existing flow ID when present.
- `availableModes`: a non-empty, duplicate-free array containing only those
  three modes. `combined` is shown only when listed.
- `layouts`: an object whose supplied `flow` entry uses `name: "breadthfirst"`,
  `direction: "TB"`, and `fit: "bounded"`; supplied `dependency` and
  `combined` entries use `name: "preset"` and `fit: "bounded"`. Missing entries
  normalize to those defaults, and any supplied unsupported value is an error.

Flow mode renders exactly the selected flow's `nodeIds` and `edgeIds`; “All
flows” is their union. Dependency mode renders every node and every directed
edge with its stored position. Combined mode renders the dependency graph and
emphasizes only the selected flow's exact IDs; non-flow edges retain their
dependency styling. No edge is inferred in any mode.

Flow layout uses Cytoscape's built-in `breadthfirst` with `directed: true`,
`circle: false`, `spacingFactor: 1.2`, `avoidOverlap: true`, and
`nodeDimensionsIncludeLabels: true`. The renderer does not pass an unsupported
`direction` option to Cytoscape. `direction: "TB"` is enforced by a
deterministic y-axis correction after layout. `preset` preserves valid stable
positions. “Bounded” means normal selection does not silently call a shrinking
fit; the explicit Fit button remains available. A flow with more than 40
visible nodes shows `Large flow — pan or zoom to explore` and initializes at a
zoom floor of at least `0.35`.

## Normalization, merge, and comparison display

Normalization is in memory only; opening a map never rewrites its JSON.

- A legacy document with no `schemaVersion`, v2 metadata, or `view` keeps the
  v1 initial `All relationships` view, flow buttons, preset positions, search,
  fit, and inspector. It has no v2 mode controls or comparison claim.
- In v2, missing `view.defaultMode` means `dependency`; missing
  `defaultFlowId` selects the first flow only when flow mode is selected. An
  empty flow list falls back to dependency. Missing layout entries receive the
  defaults above.
- Missing `changeType` or `snapshotIds` shows no change badge and treats an
  item as `existing` for filters. Missing node `kind` uses `service` in v2;
  missing legacy `kind` keeps the round-rectangle appearance. Node `status`
  remains required.
- Selecting a snapshot filters elements whose `snapshotIds` include it.
  Elements without `snapshotIds` remain visible and are labeled `snapshot
  coverage unknown`; no diff is invented. An unavailable snapshot or
  comparison falls back to Current and announces the fallback.
- With an active comparison, its state arrays take precedence over the
  element's own `changeType`. Without one, the element annotation is the
  current/default state. The inspector reports the selected pair, counts,
  replacement links, and summary.

Merge by stable IDs. Preserve valid positions for retained IDs, retain
replacement/deprecated records, add plan-only records as `planned`, and use
inspected code, tests, build output, or runtime evidence before marking a
record `implemented`. Keep repository-relative evidence and explicit coverage
gaps; do not infer architecture from filenames.

## Status, change, accessibility, and layout semantics

Lifecycle meaning is redundant: status text/chip, a shape or border pattern,
and an accessible label. Color is only an additional cue. Change markers are:

| Change | Node marker / label / border | Edge line |
|---|---|---|
| `existing` | `=` / `[existing]` / solid 1px | solid |
| `inherited` | `↥` / `[inherited]` / dashed 1px | dashed |
| `changed` | `~` / `[changed]` / solid 3px | solid 2px |
| `added` | `+` / `[added]` / solid 2px | solid |
| `replaced` | `⇄` / `[replaced]` / solid 3px | solid 3px |
| `removed` | `−` / `[removed]` / dotted 1px | dotted |

The UI exposes `aria-pressed` mode buttons, snapshot/comparison selects,
`statusFilter`, `categoryFilter`, and `changeFilter`, plus
`showLabelsToggle`, `showDeprecatedToggle`, and `showChangesOnlyToggle`.
The legend spells out category, lifecycle, and change meanings. The keyboard-
navigable node inventory is synchronized with graph selection; the inspector
uses an `aria-live="polite"` region, visible focus outlines, descriptive
labels, and relationship buttons. Deprecated items are dimmed only after text
remains readable. At widths ≤900px the inspector moves below a map at least
450px tall; at ≤560px controls wrap or scroll horizontally. Reduced-motion
users receive immediate scrolling and layout changes.

## Security and runtime boundary

Project title, summary, data filename, labels, IDs, descriptions, evidence,
paths, and comparison summaries are untrusted. The builder HTML-escapes title,
summary, and the relative data filename. The browser uses `textContent` where
possible and `escapeHtml` for generated fragments and attributes; IDs are
validated before Cytoscape selectors or `data-*` attributes. There is no
`eval`, inline JSON, inline-data execution, or user-controlled HTML. The JSON
link is a relative path computed from output to data; source paths do not
become external navigation. The pinned Cytoscape.js CDN and same-origin JSON
are the only runtime fetches.

Serve the repository over a local HTTP server for interactive verification;
opening the file directly cannot satisfy same-origin fetch. Confirm the pinned
CDN and JSON are reachable, then check legacy, flow/dependency/combined modes,
snapshots/comparisons, search and filters, inventory and relationship
navigation, keyboard/focus, desktop/mobile breakpoints, reduced motion,
large-flow behavior, pan/zoom/explicit Fit, and console recovery for missing
JSON, invalid JSON, or missing Cytoscape. Errors remain visible and escaped,
with local-server recovery instructions.

The Skill writes only repository-root `architecture-map.json` and
`architecture-map.html`. It does not add a runtime service, dependencies,
layout plugins, or browser state; it never commits, pushes, publishes,
deploys, migrates, or deletes an existing map.
