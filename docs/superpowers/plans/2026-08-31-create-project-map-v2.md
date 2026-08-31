# Create Project Map v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `create-project-map` with additive schema-v2 flow, dependency, combined-view, snapshot-comparison, status, and accessibility behavior while preserving the existing v1 JSON contract and Cytoscape renderer.

**Architecture:** Keep `validate_document(document)` and `render_html(document, template, data_filename)` as the Python interfaces. The validator accepts v1 unchanged and validates optional v2 metadata; the builder validates before writing and only interpolates escaped title, summary, and relative JSON path. The native template normalizes the fetched document in memory, rebuilds the graph for the selected mode, and keeps all presentation state in browser memory.

**Tech Stack:** Python 3 standard library (`json`, `argparse`, `pathlib`, `html`, `unittest`), UTF-8 JSON/Markdown, native HTML/CSS/JavaScript, pinned Cytoscape.js `3.34.0` CDN, local HTTP server, and the existing browser skill for manual real-browser smoke verification.

**Spec:** `docs/superpowers/specs/2026-08-31-create-project-map-v2-design.md`

## Global Constraints

- The seven existing required top-level fields remain required and unchanged: `project`, `sources`, `categories`, `nodes`, `edges`, `flows`, and `phases`.
- Existing node IDs, edge IDs, flow IDs, phase IDs, statuses, positions, and directed relationships keep their current meanings.
- If `schemaVersion` is absent, the validator and renderer treat the document as schema 1; `schemaVersion: 1` is accepted as an explicit legacy marker; only integer `1` or `2` is valid.
- All v2 fields are optional, and unknown fields remain ignored for forward compatibility.
- Use Python standard-library code for generation and validation, native browser JavaScript/CSS, and the already pinned Cytoscape.js CDN script.
- Do not introduce a layout plugin, framework, bundler, backend, database, runtime service, or other heavy runtime dependency.
- Keep output as the two repository-root artifacts `architecture-map.json` and `architecture-map.html`; the runtime Skill never modifies product code, commits, publishes, or deploys.
- Validate the complete JSON before overwriting an existing map; malformed existing JSON remains untouched.
- Merge by stable ID and preserve a valid stored `position` for every retained node ID.
- A plan-only element remains `planned`; promote to `implemented` only with inspected code, test, build, or runtime evidence; retain removals as `deprecated` before deletion.
- In v2, `flow.edgeIds` is authoritative and every referenced edge must have both endpoints in that flow's `nodeIds`; v1 keeps current `edgeIds` behavior.
- Flow layout uses built-in breadth-first with `directed: true`, `circle: false`, `spacingFactor: 1.2`, `avoidOverlap: true`, and `nodeDimensionsIncludeLabels: true`; do not pass `direction` to Cytoscape.
- The v2 flow direction contract is exactly `direction: "TB"`; reverse the returned y-axis deterministically when the host lays roots below downstream layers.
- Do not reduce spacing or layout dimensions to force a large flow into the viewport; flows over 40 nodes show `Large flow — pan or zoom to explore` and start at zoom `0.35` or higher.
- The Fit control is an explicit opt-in; ordinary mode changes and large-flow selection do not silently call a shrinking fit.
- Encode lifecycle and change meaning with text, glyph/pattern, and accessible labels; color is only an additional cue and deprecated content remains readable.
- At `≤900px`, keep the map at least `450px` tall and move the inspector below it; at `≤560px`, wrap or horizontally scroll controls without hiding an essential control.
- Honor `prefers-reduced-motion` by disabling smooth scrolling and animated layout transitions.
- Treat plans, source paths, labels, descriptions, IDs, evidence, and comparison summaries as untrusted input; use `textContent` or `escapeHtml`, validate IDs before Cytoscape use, and never use `eval` or inline JSON execution.
- For v2 category colors allow only `#RRGGBB` or `#RRGGBBAA`; for legacy unsafe colors use border `#626878` and fill `#171922` without interpolating the unsafe value.
- Keep the existing recovery message and local-server instructions for fetch errors, invalid JSON, missing Cytoscape, and validator failures.
- Do not persist filters, coordinates, comments, or browser state back to the JSON artifact.
- Keep `skills/create-project-map/SKILL.md` concise and move schema detail to `references/project-map-schema.md`; keep production Python standard-library-only.

---

## File Responsibility Map

- `skills/create-project-map/scripts/validate_project_map.py`: preserve v1 validation and add isolated v2 version, enum, reference, cycle, comparison, replacement, color, and flow-endpoint checks; keep the CLI read-only.
- `skills/create-project-map/scripts/build_project_map.py`: preserve `render_html`, escape project metadata and the relative JSON filename, validate before writing, and never embed fetched JSON or v2 text in a script.
- `skills/create-project-map/assets/project-map-template.html`: own in-memory normalization, mode graph selection, layouts, status/change styling, snapshots/comparisons, filters, inventory, inspector, keyboard behavior, responsive CSS, and browser recovery.
- `skills/create-project-map/references/project-map-schema.md`: document the complete v1 contract, additive v2 fields, exact enums/layouts, replacement reciprocity, normalization defaults, and security rules with complete payload examples.
- `skills/create-project-map/SKILL.md`: give the operator the evidence-first merge workflow, v1/v2 behavior, build/validate commands, browser smoke checklist, and stop conditions.
- `skills/create-project-map/README.md`: provide a concise human-facing description of v2 outputs, modes, compatibility, and implementation assets.
- `evals/create-project-map/fixtures/valid-map.json`: retain the existing v1 regression fixture unchanged.
- `evals/create-project-map/fixtures/invalid-edge-map.json`: retain the existing broken-reference fixture unchanged.
- `evals/create-project-map/fixtures/v2-map.json`: add the approved `v15 → v15-4 → v16` chain, all node/edge kinds, replacement pairs, all six comparison states, and complete view metadata.
- `evals/create-project-map/fixtures/legacy-unsafe-color-map.json`: add a v1 document with a previously accepted non-hex category color for validator and neutral-render fallback checks.
- `evals/create-project-map/test_validate_project_map.py`: retain existing function names and add focused v2 validator cases using the v2 fixture and deep-copy mutations.
- `evals/create-project-map/test_build_project_map.py`: retain escaping/control tests and add relative-path, no-inline-data, pre-write rejection, and v2 template-hook checks.
- `evals/create-project-map/cases.json`: retain current regression cases and add explicit v2 mode/comparison/legacy/large-flow evaluation cases.
- `.github/workflows/validate-skills.yml`: add the standard-library create-project-map focused suite to CI; leave real-browser smoke as a browser-skill gate because CI has no pinned browser test dependency.
- `scripts/validate-skills.py`, `scripts/generate-skill-catalog.py`, and `scripts/context_budget_report.py`: run as repository gates; do not modify them for this feature.

## Interfaces Shared Across Tasks

Python interfaces remain:

```python
def validate_document(document: dict[str, Any]) -> list[str]: ...

def render_html(
    document: dict[str, Any],
    template: str,
    data_filename: str,
) -> str: ...

def relative_data_filename(data_path: pathlib.Path, output_path: pathlib.Path) -> str: ...
```

The browser template uses these exact internal interfaces and state shapes:

```javascript
function normalizeModel(data) { /* returns Model */ }
function graphElementsForState(model, state) { /* {nodes, edges} */ }
function layoutForMode(model, state, elementCount) { /* Cytoscape layout options */ }
function orientFlowLayers(flowNodeIds, flowEdgeIds) { /* y-axis correction */ }
function comparisonState(model, collection, id) { /* ChangeType */ }
function applyFilters(model, state, elements) { /* visible node/edge IDs */ }
function chooseMode(mode) { /* flow | dependency | combined */ }
function chooseFlow(flowId, scroll) { /* all | stable flow ID */ }
function chooseSnapshot(snapshotId) { /* current | snapshot ID */ }
function chooseComparison(comparisonId) { /* current | comparison ID */ }
```

`Model` keeps `isV2`, `schemaVersion`, the seven v1 collections, normalized `view`, `snapshots`, and `comparisons`. `UIState` keeps `mode`, `flowId`, `snapshotId`, `comparisonId`, `statusFilter`, `categoryFilter`, `changeFilter`, `showLabels`, `showDeprecated`, and `showChangesOnly`; it is never written to JSON.

### Task 1: Add additive v2 schema validation and fixtures

**Files:**
- Modify: `skills/create-project-map/scripts/validate_project_map.py`
- Modify: `evals/create-project-map/test_validate_project_map.py`
- Create: `evals/create-project-map/fixtures/v2-map.json`
- Create: `evals/create-project-map/fixtures/legacy-unsafe-color-map.json`

**Interfaces:**
- Consumes: existing v1 document shape and the seven required top-level keys.
- Produces: unchanged `validate_document(document: dict[str, Any]) -> list[str]` and CLI `python skills/create-project-map/scripts/validate_project_map.py <json-path> [--html <html-path>]`.
- Error strings must include the field path and a stable term used by tests, such as `schemaVersion`, `defaultMode`, `kind`, `changeType`, `snapshot`, `comparison`, `replacesId`, `deprecated`, or `flow.edgeIds`.

- [ ] **Step 1: Add the v2 and legacy fixtures before changing validator behavior.**

Keep `valid-map.json` and `invalid-edge-map.json` byte-for-byte unchanged. Add `v2-map.json` with this concrete metadata and corresponding v1 collections:

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
      "existingNodeIds": ["api"],
      "inheritedNodeIds": ["ui"],
      "changedNodeIds": ["decision"],
      "addedNodeIds": ["store"],
      "replacedNodeIds": ["worker-v2"],
      "removedNodeIds": ["worker-v1"],
      "existingEdgeIds": ["api-calls-ui"],
      "inheritedEdgeIds": ["api-data-store"],
      "changedEdgeIds": ["worker-v2-data-store"],
      "addedEdgeIds": ["api-event-worker"],
      "replacedEdgeIds": ["edge-replaces"],
      "removedEdgeIds": ["worker-v1-data-store"],
      "existingFlowIds": ["request-flow"],
      "inheritedFlowIds": ["dependency-flow"],
      "changedFlowIds": ["decision-flow"],
      "addedFlowIds": ["request-flow-v2"],
      "replacedFlowIds": ["replacement-flow-v2"],
      "removedFlowIds": ["request-flow-v1"],
      "summary": "Changes from v15 to v15-4."
    },
    {
      "id": "v15-4-to-v16",
      "fromSnapshotId": "v15-4",
      "toSnapshotId": "v16",
      "existingNodeIds": ["api"],
      "inheritedNodeIds": ["store"],
      "changedNodeIds": ["decision"],
      "addedNodeIds": ["external"],
      "replacedNodeIds": ["worker-v2"],
      "removedNodeIds": ["worker-v1"],
      "existingEdgeIds": ["api-calls-ui"],
      "inheritedEdgeIds": ["api-data-store"],
      "changedEdgeIds": ["worker-v2-data-store"],
      "addedEdgeIds": ["api-event-worker"],
      "replacedEdgeIds": ["edge-replaces"],
      "removedEdgeIds": ["worker-v1-data-store"],
      "existingFlowIds": ["request-flow"],
      "inheritedFlowIds": ["dependency-flow"],
      "changedFlowIds": ["decision-flow"],
      "addedFlowIds": ["request-flow-v2"],
      "replacedFlowIds": ["replacement-flow-v2"],
      "removedFlowIds": ["request-flow-v1"],
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

The fixture must include nodes named `api`, `ui`, `worker-v2`, `store`, `external`, `contract`, `decision`, and `actor` for every allowed node `kind`; edges named `api-calls-ui`, `api-data-store`, `api-event-worker`, `edge-contains`, `edge-inherits`, `edge-depends-on`, `edge-replaces`, and `edge-to-external` for every allowed edge `kind` (one edge intentionally omits `kind`); and replacement pairs such as:

Set the `api` node itself to include the element-level default `changeType: "changed"`, for example `{"id":"api","kind":"service","changeType":"changed","snapshotIds":["v15","v15-4","v16"],"position":{"x":100,"y":100}}` plus its required descriptive/evidence fields. Keep `api` in `existingNodeIds` for the active `v15-4-to-v16` comparison. The browser assertion for that comparison must expect `data-change-type="existing"`; this is the regression guard that active comparison arrays override an element-level `changeType`.

```json
{
  "id": "worker-v2",
  "kind": "worker",
  "changeType": "replaced",
  "replacesId": "worker-v1",
  "snapshotIds": ["v15-4", "v16"]
}
```

```json
{
  "id": "worker-v1",
  "kind": "worker",
  "status": "deprecated",
  "changeType": "removed",
  "snapshotIds": ["v15"]
}
```

Use the same reciprocity for `edge-replaces` (`replacesId: "worker-v1-data-store"`) and `replacement-flow-v2` (`replacesId: "request-flow-v1"`); keep each old record in the map with `changeType: "removed"` and keep the old node's status `deprecated`. Leave `snapshotIds` absent on the `actor` node so snapshot selection exercises the visible `snapshot coverage unknown` state.

Use `request-flow-v2` only in `addedFlowIds` and a distinct `replacement-flow-v2` in `replacedFlowIds`, with `request-flow-v1` in `removedFlowIds`; include all six flow records named in the comparison arrays and mark the old/new pair with `changeType: "removed"`/`"replaced"` and reciprocal `replacesId` semantics. Include an edge named `edge-to-external` whose target is the `external` node and leave it out of `request-flow`, so the hidden-endpoint test has a concrete edge to append. Give every fixture node finite `position.x`/`position.y`, evidence or a coverage gap, and make every v2 flow edge endpoint occur in that flow's `nodeIds`. Add `legacy-unsafe-color-map.json` by copying the valid v1 shape and setting its category color to `linear-gradient(red,blue)`; it must remain v1-valid.

- [ ] **Step 2: Write focused failing validator tests.**

Extend `ProjectMapValidationTests` without deleting `test_valid_document_has_no_errors` or `test_missing_edge_target_is_reported`:

```python
import copy

    def load(self, name):
        path = pathlib.Path(__file__).parent / "fixtures" / name
        return json.loads(path.read_text(encoding="utf-8"))

    def v2(self):
        return copy.deepcopy(self.load("v2-map.json"))

    def assert_error(self, document, fragment):
        errors = MODULE.validate_document(document)
        self.assertTrue(
            any(fragment in error for error in errors),
            f"Expected {fragment!r} in {errors!r}",
        )

    def test_v1_fixture_with_legacy_color_remains_valid(self):
        self.assertEqual(
            MODULE.validate_document(self.load("legacy-unsafe-color-map.json")),
            [],
        )

    def test_valid_v2_chain_contains_all_change_states(self):
        document = self.v2()
        self.assertEqual(MODULE.validate_document(document), [])
        comparison = document["comparisons"][0]
        for collection in ("Node", "Edge", "Flow"):
            keys = [
                f"{state}{collection}Ids"
                for state in ("existing", "inherited", "changed", "added", "replaced", "removed")
            ]
            self.assertEqual(6, len(keys))
            self.assertTrue(all(isinstance(comparison[key], list) for key in keys))

    def test_rejects_future_schema_without_legacy_downgrade(self):
        document = self.v2()
        document["schemaVersion"] = 3
        self.assert_error(document, "schemaVersion")

    def test_explicit_schema_one_and_unknown_fields_preserve_legacy_rules(self):
        document = self.load("legacy-unsafe-color-map.json")
        document["schemaVersion"] = 1
        document["futureField"] = {"html": "<script>ignored</script>"}
        self.assertEqual(MODULE.validate_document(document), [])

    def test_rejects_invalid_v2_enums_and_color(self):
        cases = (
            ("view", lambda d: d["view"].update(defaultMode="journey"), "defaultMode"),
            ("node kind", lambda d: next(node for node in d["nodes"] if node["id"] == "api").update(kind="invalid"), "kind"),
            ("edge kind", lambda d: next(edge for edge in d["edges"] if edge["id"] == "api-calls-ui").update(kind="invalid"), "kind"),
            ("change type", lambda d: next(node for node in d["nodes"] if node["id"] == "api").update(changeType="moved"), "changeType"),
            ("color", lambda d: d["categories"][0].update(color="url(javascript:bad)"), "color"),
        )
        for _, mutate, fragment in cases:
            with self.subTest(fragment=fragment):
                document = self.v2()
                mutate(document)
                self.assert_error(document, fragment)

    def test_rejects_snapshot_cycles_duplicates_and_unknown_parents(self):
        document = self.v2()
        document["snapshots"][0]["parentId"] = "v16"
        self.assert_error(document, "cycle")

        document = self.v2()
        document["snapshots"].append(copy.deepcopy(document["snapshots"][0]))
        self.assert_error(document, "duplicate")

        document = self.v2()
        document["snapshots"][1]["parentId"] = "missing-snapshot"
        self.assert_error(document, "parentId")

    def test_rejects_bad_comparison_arrays_and_references(self):
        document = self.v2()
        document["comparisons"][0]["existingNodeIds"] = "api"
        self.assert_error(document, "existingNodeIds")

        document = self.v2()
        document["comparisons"][0]["addedNodeIds"] = ["missing-node"]
        self.assert_error(document, "comparison")

        document = self.v2()
        document["comparisons"][0]["existingNodeIds"].append("api")
        self.assert_error(document, "at most one")

        document = self.v2()
        document["currentSnapshotId"] = "missing-snapshot"
        self.assert_error(document, "currentSnapshotId")

        document = self.v2()
        document["view"]["defaultFlowId"] = "missing-flow"
        self.assert_error(document, "defaultFlowId")

        document = self.v2()
        document["view"]["availableModes"] = []
        self.assert_error(document, "availableModes")

    def test_rejects_v2_flow_edge_with_hidden_endpoint(self):
        document = self.v2()
        document["flows"][0]["edgeIds"].append("edge-to-external")
        self.assert_error(document, "flow.edgeIds")

    def test_rejects_invalid_replacement_reciprocity_and_removed_status(self):
        document = self.v2()
        document["nodes"][0].update(changeType="replaced", replacesId="missing-node")
        self.assert_error(document, "replacesId")

        document = self.v2()
        next(edge for edge in document["edges"] if edge["id"] == "api-calls-ui"]).update(
            changeType="replaced", replacesId="api"
        )
        self.assert_error(document, "same collection")

        document = self.v2()
        old = next(node for node in document["nodes"] if node["id"] == "worker-v1")
        old["status"] = "planned"
        self.assert_error(document, "deprecated")

        document = self.v2()
        document["comparisons"][0]["removedNodeIds"] = ["api"]
        self.assert_error(document, "replacement")

    def test_rejects_non_tb_flow_layout(self):
        document = self.v2()
        document["view"]["layouts"]["flow"]["direction"] = "LR"
        self.assert_error(document, "direction")

        document = self.v2()
        document["view"]["layouts"]["flow"]["name"] = "grid"
        self.assert_error(document, "layout")

    def test_existing_finite_position_and_broken_edge_checks_remain(self):
        document = self.v2()
        document["nodes"][0]["position"]["x"] = float("nan")
        self.assert_error(document, "finite")
        self.assertTrue(
            any("missing-node" in error for error in MODULE.validate_document(
                self.load("invalid-edge-map.json")
            ))
        )
```

Keep the fixture's collection-state keys exactly as `existingNodeIds`, `existingEdgeIds`, and `existingFlowIds` (and the five corresponding state names); the loop above is intentionally explicit about those suffixes rather than relying on inferred names.

- [ ] **Step 3: Run the focused validator tests and record the expected failure.**

Run:

```powershell
python -m unittest evals/create-project-map/test_validate_project_map.py -v
```

Expected: the two original tests pass, and the new v2 tests fail because the current validator has no schema-version, snapshot, comparison, enum, replacement, or v2 color checks.

- [ ] **Step 4: Implement the smallest additive validator.**

Add constants and helpers beside the existing v1 constants, retaining `_list`, `_ids`, `_require_reference`, `_has_evidence`, `validate_document`, `validate_html`, and `main`:

```python
SCHEMA_VERSIONS = {1, 2}
NODE_KINDS = {"service", "ui", "worker", "data", "external", "contract", "decision", "actor"}
EDGE_KINDS = {"calls", "data", "event", "contains", "inherits", "depends-on", "replaces", "unknown"}
CHANGE_TYPES = {"existing", "inherited", "changed", "added", "replaced", "removed"}
SNAPSHOT_KINDS = {"version", "baseline", "release", "working"}
MODES = {"flow", "dependency", "combined"}
V2_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")

def document_schema_version(document: dict[str, Any], errors: list[str]) -> int:
    value = document.get("schemaVersion", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value not in SCHEMA_VERSIONS:
        errors.append("schemaVersion must be integer 1 or 2")
        return 1
    return value
```

For `schemaVersion == 2`, validate optional recognized objects as follows: `currentSnapshotId` references a snapshot; `snapshots` is an array of unique objects with non-empty `id`/`label`, allowed `kind`, null-or-known `parentId`, and no parent cycle; `comparisons` is an array of unique objects with distinct known `fromSnapshotId`/`toSnapshotId`, all eighteen state arrays present and typed as arrays, known IDs only, and no ID repeated across the six states within a collection; and `view` is an object whose present `defaultMode`, `defaultFlowId`, `availableModes`, and layout values satisfy the exact enum/reference rules. Allow omitted optional members so browser normalization can apply the documented defaults, but reject every malformed member that is present.

Validate v2 node, edge, and flow annotations with collection-local IDs: `kind` and `changeType` use the exact sets above, `snapshotIds` is a unique array of existing snapshot IDs, `replacesId` is forbidden unless `changeType == "replaced"`, and `replaced` requires a same-collection target. Require the old target to have `changeType == "removed"`; require a removed node to have `status == "deprecated"`; require comparison `replaced*Ids` and `removed*Ids` to contain the new and old IDs respectively; and reject cross-collection, dangling, target-not-removed, and wrong-state replacements. Enforce the v2 flow endpoint rule after collecting edge endpoints. Restrict v2 category colors with `V2_COLOR` while leaving the legacy branch's arbitrary color acceptance intact.

Keep finite position checks, evidence/coverage-gap checks, all current references, duplicate IDs, required top-level fields, and invalid-edge rejection unchanged. Do not mutate the document. Run the v2 branch only after the v1 base checks so old inputs still validate exactly as before.

- [ ] **Step 5: Run the validator tests and direct CLI checks.**

Run:

```powershell
python -m unittest evals/create-project-map/test_validate_project_map.py -v
python skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/fixtures/valid-map.json
python skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/fixtures/v2-map.json
python skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/fixtures/legacy-unsafe-color-map.json
```

Expected: all validator tests pass; each valid CLI invocation exits `0` and prints `Project map is valid`; the invalid fixture test still reports `missing-node` and exits `1`.

- [ ] **Step 6: Commit the validator and fixtures.**

```powershell
git add skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/test_validate_project_map.py evals/create-project-map/fixtures/v2-map.json evals/create-project-map/fixtures/legacy-unsafe-color-map.json
git commit -m "feat: validate project map schema v2"
```

### Task 2: Preserve builder escaping and validate before rendering

**Files:**
- Modify: `skills/create-project-map/scripts/build_project_map.py`
- Modify: `evals/create-project-map/test_build_project_map.py`

**Interfaces:**
- Consumes: `validate_document` from `validate_project_map.py` and template tokens `{{PROJECT_TITLE}}`, `{{PROJECT_SUMMARY}}`, `{{DATA_FILENAME}}`.
- Produces: existing `render_html(document, template, data_filename) -> str`, new `relative_data_filename(data_path: pathlib.Path, output_path: pathlib.Path) -> str`, and the existing `main(argv) -> int` CLI.
- The output path is written only after JSON parsing, template loading, validator success, relative-path computation, and rendering success.

- [ ] **Step 1: Write failing builder/security tests.**

Add these methods to `ProjectMapBuildTests` while keeping `test_render_replaces_tokens_and_escapes_text` and `test_template_exposes_interactive_map_controls`:

```python
import copy
import json
import tempfile

    def test_v2_metadata_is_not_embedded_as_html_or_javascript(self):
        document = {
            "schemaVersion": 2,
            "project": {
                "title": "</title><script>alert(1)</script>",
                "summary": "</script><script>owned()</script>",
            },
            "comparisons": [{"summary": "<img src=x onerror=owned()>"}],
        }
        before = copy.deepcopy(document)
        rendered = MODULE.render_html(
            document,
            "<title>{{PROJECT_TITLE}}</title><p>{{PROJECT_SUMMARY}}</p>",
            "../data/architecture-map.json",
        )
        self.assertEqual(before, document)
        self.assertNotIn("</script>", rendered.lower())
        self.assertNotIn("<script>", rendered.lower())
        self.assertNotIn("<img", rendered.lower())
        self.assertIn("../data/architecture-map.json", rendered)

    def test_relative_data_filename_uses_posix_relative_path(self):
        data = pathlib.Path("C:/repo/maps/architecture-map.json")
        output = pathlib.Path("C:/repo/maps/html/architecture-map.html")
        self.assertEqual(
            "../architecture-map.json",
            MODULE.relative_data_filename(data, output),
        )

    def test_invalid_document_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            data = root / "invalid.json"
            template = root / "template.html"
            output = root / "architecture-map.html"
            data.write_text(json.dumps({"schemaVersion": 2}), encoding="utf-8")
            template.write_text("<html>{{PROJECT_TITLE}}</html>", encoding="utf-8")
            output.write_text("old rendered map", encoding="utf-8")
            result = MODULE.main([
                "--data", str(data),
                "--template", str(template),
                "--output", str(output),
            ])
            self.assertEqual(1, result)
            self.assertEqual("old rendered map", output.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run builder tests and verify the new failure.**

```powershell
python -m unittest evals/create-project-map/test_build_project_map.py -v
```

Expected: the two current tests pass; the new relative-path test fails because `relative_data_filename` is not defined, and the invalid-output/security tests expose the missing explicit contract.

- [ ] **Step 3: Implement the relative-path helper and preserve escaped token rendering.**

Refactor the current inline path calculation into this exact helper and keep it based on resolved filesystem paths:

```python
def relative_data_filename(data_path: pathlib.Path, output_path: pathlib.Path) -> str:
    relative = pathlib.Path(os.path.relpath(data_path.resolve(), output_path.parent.resolve()))
    return relative.as_posix()
```

Keep `render_html` limited to `html.escape(str(project.get("title", "Project Map")))`, `html.escape(str(project.get("summary", "")))`, and `html.escape(data_filename, quote=True)`. It must not serialize `document`, `snapshots`, `comparisons`, or summaries into the HTML. In `main`, call `validator.validate_document(document)` before `args.output.parent.mkdir` or `write_text`; use `relative_data_filename(args.data, args.output)` and retain the current CLI error/exit behavior. Do not add a dependency or mutate the input mapping.

- [ ] **Step 4: Run builder, validator, and generated-artifact checks.**

```powershell
python -m unittest evals/create-project-map/test_build_project_map.py -v
python skills/create-project-map/scripts/build_project_map.py --data evals/create-project-map/fixtures/valid-map.json --template skills/create-project-map/assets/project-map-template.html --output evals/create-project-map/generated-v1.html
python skills/create-project-map/scripts/build_project_map.py --data evals/create-project-map/fixtures/v2-map.json --template skills/create-project-map/assets/project-map-template.html --output evals/create-project-map/generated-v2.html
python skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/fixtures/valid-map.json --html evals/create-project-map/generated-v1.html
python skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/fixtures/v2-map.json --html evals/create-project-map/generated-v2.html
```

Expected: builder tests pass; both CLIs print `Project map HTML written to ...`; both validator commands exit `0`. Treat `generated-v1.html` and `generated-v2.html` as temporary smoke artifacts and remove them from the working tree after browser verification rather than adding them to the Skill.

- [ ] **Step 5: Commit the builder contract.**

```powershell
git add skills/create-project-map/scripts/build_project_map.py evals/create-project-map/test_build_project_map.py
git commit -m "test: preserve project map rendering safety"
```

### Task 3: Implement normalized graph modes and bounded layouts

**Files:**
- Modify: `skills/create-project-map/assets/project-map-template.html`
- Preserve unchanged: the existing marker tests in `evals/create-project-map/test_build_project_map.py`, including `test_render_replaces_tokens_and_escapes_text` and `test_template_exposes_interactive_map_controls`

**Interfaces:**
- Consumes: valid v1/v2 JSON fetched from the relative `DATA_URL`, normalized `Model`, and `UIState`.
- Produces: `normalizeModel`, `graphElementsForState`, `layoutForMode`, `orientFlowLayers`, `chooseMode`, `chooseFlow`, and `focusCurrent` in the template; `#cy` data attributes `data-visible-node-ids`, `data-visible-edge-ids`, `data-layout-mode`, and `data-large-flow` are read-only smoke-test telemetry.
- Dependency mode always uses all directed nodes/edges and stored positions; flow mode uses exactly the selected flow's node/edge IDs; combined mode uses all dependency elements and marks only the selected flow's exact nodes/edges.

- [ ] **Step 1: Run the mode/layout browser RED gate against generated v2 and large-flow artifacts.**

Before editing the template, use the generated `v2.html` and deterministic `large.html` from Task 5's temporary server setup with the existing browser skill; do not add a browser dependency. At a desktop viewport, run these exact assertions (the single executable definitions are the named checks in Task 5 and must be reused there):

- `await expect(page.locator("#modeControls")).toBeVisible()` and `await expect(page.locator("#modeControls [data-mode='flow']")).toHaveAttribute("aria-pressed", "true")`.
- `await expect(page.locator("#flowNav [data-flow-id='request-flow']")).toHaveAttribute("aria-pressed", "true")`; then `const initial = await page.evaluate(() => window.__projectMapTestHooks.getState())`, `expect(initial.mode).toBe("flow")`, `expect(initial.flowId).toBe("request-flow")`, `expect(initial.layoutOptions.name).toBe("breadthfirst")`, and `expect(initial.layoutOptions.direction).toBeUndefined()`.
- Assert `initial.visibleEdgeIds` equals `initial.selectedFlow.edgeIds` after sorting, click `#modeControls [data-mode='dependency']`, assert the hook reports all node and edge IDs, click `#modeControls [data-mode='combined']`, and assert the hook reports all edges while only selected-flow edges are emphasized.
- On `large.html?test=1`, read `window.__projectMapTestHooks.getState()` and assert `large.layoutOptions.direction` is `undefined`; this is the unsupported-Cytoscape-direction guard through returned runtime telemetry, not a source search.

Record the first failing assertion, console messages, and page errors. Expected RED result before this task's implementation: the current template has no `#modeControls`, v2 flow/default state, or `__projectMapTestHooks`, so the browser gate fails before the mode/layout behavior exists.

- [ ] **Step 2: Add `normalizeModel` with explicit v1/v2 defaults.**

Use an in-memory normalized copy and never write it back to the fetched object:

```javascript
function normalizeModel(data) {
  const isV2 = data.schemaVersion === 2;
  const view = isV2 ? (data.view || {}) : {};
  const availableModes = isV2
    ? (view.availableModes || ["flow", "dependency"])
    : ["dependency"];
  return {
    ...data,
    isV2,
    schemaVersion: isV2 ? 2 : 1,
    view: {
      defaultMode: isV2 ? (view.defaultMode || "dependency") : "dependency",
      defaultFlowId: view.defaultFlowId || "",
      availableModes,
      layouts: {
        flow: {name: "breadthfirst", direction: "TB", fit: "bounded", ...(view.layouts?.flow || {})},
        dependency: {name: "preset", fit: "bounded", ...(view.layouts?.dependency || {})},
        combined: {name: "preset", fit: "bounded", ...(view.layouts?.combined || {})},
      },
    },
    snapshots: isV2 ? (data.snapshots || []) : [],
    comparisons: isV2 ? (data.comparisons || []) : [],
  };
}
```

After normalization, coerce a v2 default mode that is absent from `availableModes` to the first available mode, select `defaultFlowId` only when it exists and flow mode has at least one flow, and fall back to dependency mode for an empty flow list. If a v2 recognized object fails the client-side shape check, throw a field-specific error and route it to the visible escaped recovery message; never downgrade malformed v2 to v1. For legacy data, hide `#modeControls`, snapshot/comparison controls, change filters, and change legend entries; retain the existing “All relationships” initial detail, flow buttons, preset positions, search, fit, and inspector.

- [ ] **Step 3: Rebuild graph elements for each mode without inventing edges.**

Implement exact set construction:

```javascript
function idsForFlow(model, flowId) {
  if (flowId === "all") {
    return {
      nodeIds: [...new Set(model.flows.flatMap((flow) => flow.nodeIds || []))],
      edgeIds: [...new Set(model.flows.flatMap((flow) => flow.edgeIds || []))],
    };
  }
  const flow = byId(model.flows, flowId);
  return {nodeIds: [...(flow?.nodeIds || [])], edgeIds: [...(flow?.edgeIds || [])]};
}

function graphElementsForState(model, state) {
  const all = {nodeIds: model.nodes.map((node) => node.id), edgeIds: model.edges.map((edge) => edge.id)};
  const selected = state.mode === "flow" ? idsForFlow(model, state.flowId) : all;
  const nodes = model.nodes.filter((node) => selected.nodeIds.includes(node.id));
  const nodeSet = new Set(nodes.map((node) => node.id));
  const edges = model.edges.filter((edge) => selected.edgeIds.includes(edge.id)
    && nodeSet.has(edge.source) && nodeSet.has(edge.target));
  return {nodes, edges};
}
```

Replace the current dimming-only flow update with a graph rebuild that removes old elements, adds only the returned elements, and stores the exact ID sets on `#cy.dataset`. Flow mode must use `flow.edgeIds` even when an edge has no `kind`; it must not derive edges from stage order, endpoints, labels, or edge kind. The v1 `selectedFlow === "all"` experience remains the all-relationships view; for a selected legacy flow, retain the current all-elements graph and `.dimmed`/`.flow` emphasis behavior. The v2 “All flows” option is the union of flow IDs, not an invented dependency graph.

- [ ] **Step 4: Implement layout options, orientation correction, and large-flow behavior.**

Use these layout options and no unsupported `direction` property in the Cytoscape call:

```javascript
function layoutForMode(model, state, elementCount) {
  if (state.mode === "flow" && model.isV2) {
    return {
      name: "breadthfirst",
      fit: false,
      directed: true,
      circle: false,
      spacingFactor: 1.2,
      avoidOverlap: true,
      nodeDimensionsIncludeLabels: true,
      animate: !reducedMotion,
    };
  }
  return {name: "preset", fit: false, animate: false};
}
```

Run `orientFlowLayers(flowNodeIds, flowEdgeIds)` after breadth-first stops. Compute roots from directed in-degree within the selected flow; if the mean root y is below the mean downstream y, replace each selected node's y with `maxY - y` while preserving x. Do not replace valid stored positions for dependency/combined mode. For a selected flow over 40 nodes, set `#largeFlowHint` text to `Large flow — pan or zoom to explore`, set the `#cy` telemetry flag, and raise the current zoom to `Math.max(cy.zoom(), 0.35)` without calling `cy.fit`. For a v2 flow of 40 or fewer nodes, one fit after layout is allowed; v2 large-flow mode changes and flow selections must not call it. Legacy flow selection retains the current focus behavior. Set `cy.minZoom(.12)` globally so the explicit Fit control remains available; enforce the `0.35` floor only during large-flow initialization. Keep pan, wheel/touch zoom, and reset-fit behavior.

- [ ] **Step 5: Run the unchanged marker tests and focused suite.**

```powershell
python -m unittest evals/create-project-map/test_build_project_map.py -v
python -m unittest discover -s evals/create-project-map -p "test_*.py" -v
```

Expected: the existing marker tests and focused Python tests pass unchanged; interactive mode, set-membership, layout, and hook assertions are the browser checks defined in Task 5.

- [ ] **Step 6: Commit graph mode/layout behavior.**

```powershell
git add skills/create-project-map/assets/project-map-template.html evals/create-project-map/test_build_project_map.py
git commit -m "feat: add project map graph modes"
```

### Task 4: Add status/change styling, comparisons, filters, and accessible controls

**Files:**
- Modify: `skills/create-project-map/assets/project-map-template.html`
- Preserve unchanged: the existing marker tests in `evals/create-project-map/test_build_project_map.py`, including `test_render_replaces_tokens_and_escapes_text` and `test_template_exposes_interactive_map_controls`

**Interfaces:**
- Consumes: normalized `Model`, `UIState`, `graphElementsForState`, and `layoutForMode` from Task 3.
- Produces: `comparisonState`, `applyFilters`, `renderNodeInventory`, `chooseSnapshot`, `chooseComparison`, `renderLegend`, `renderOverview`, `renderFlow`, and `renderNode`; DOM controls with the exact IDs `statusFilter`, `categoryFilter`, `changeFilter`, `showLabelsToggle`, `showDeprecatedToggle`, `showChangesOnlyToggle`, `snapshotSelect`, and `comparisonSelect`.
- Active comparison arrays override an element's `changeType`; without an active comparison, explicit element `changeType` is the default annotation and missing annotations remain unbadged in legacy mode.

- [ ] **Step 1: Run the accessibility/comparison browser RED gate against the generated v2 artifact.**

Before editing the template, use Task 5's generated `v2.html` and browser setup; keep the existing browser skill as the only interactive dependency. Run these exact assertions at desktop and then at `390×844` (the single executable definitions are the named checks in Task 5 and must be reused there):

- Assert `#statusFilter`, `#categoryFilter`, `#changeFilter`, `#showLabelsToggle`, `#showDeprecatedToggle`, `#showChangesOnlyToggle`, `#snapshotSelect`, and `#comparisonSelect` are visible. Select `v15-4-to-v16`, assert `#detailBody` contains `From v15-4 → v16`, and assert `#nodeInventory [data-node-id='api']` has `data-change-type` equal to `existing`.
- Fill `#nodeSearch` with `worker`, focus `#nodeInventory [data-node-id='worker-v2']`, press Enter, and assert `#detailKicker` contains `Node inspector` and `#inspector` has `aria-live="polite"`.
- Read `window.__projectMapTestHooks.getState().styles` and assert the exact node shapes and edge line/arrow/width mappings from `NODE_KIND_SHAPES` and `EDGE_KIND_STYLES`, including `api` roundrectangle, `worker-v2` hexagon, `edge-replaces` solid diamond width 3, and `edge-to-external` dotted circle.
- At `390×844`, assert `.map-panel` has CSS `min-height` `450px` and `#modeControls`, `#statusFilter`, `#fitButton`, and `#inspector` remain visible. The same run must capture an empty console/page-error result.

Record the first failing assertion, console messages, and page errors. Expected RED result before this task's implementation: the current template has no v2 filter/comparison controls, inventory hook, kind/change style state, live inspector region, or responsive controls, so these browser assertions fail.

- [ ] **Step 2: Add exact node/edge kind and change maps.**

Define immutable maps in the template:

```javascript
const NODE_KIND_SHAPES = Object.freeze({
  service: "roundrectangle", ui: "rectangle", worker: "hexagon", data: "diamond",
  external: "ellipse", contract: "tag", decision: "octagon", actor: "star",
});
const EDGE_KIND_STYLES = Object.freeze({
  calls: {lineStyle: "solid", arrow: "vee", width: 1},
  data: {lineStyle: "solid", arrow: "triangle", width: 1},
  event: {lineStyle: "dashed", arrow: "triangle", width: 1},
  contains: {lineStyle: "solid", arrow: "diamond", width: 1},
  inherits: {lineStyle: "dotted", arrow: "tee", width: 1},
  "depends-on": {lineStyle: "dashed", arrow: "vee", width: 1},
  replaces: {lineStyle: "solid", arrow: "diamond", width: 3},
  unknown: {lineStyle: "dotted", arrow: "circle", width: 1},
});
const CHANGE_STYLES = Object.freeze({
  existing: {glyph: "=", borderStyle: "solid", borderWidth: 1},
  inherited: {glyph: "↥", borderStyle: "dashed", borderWidth: 1},
  changed: {glyph: "~", borderStyle: "solid", borderWidth: 3},
  added: {glyph: "+", borderStyle: "solid", borderWidth: 2},
  replaced: {glyph: "⇄", borderStyle: "solid", borderWidth: 3},
  removed: {glyph: "−", borderStyle: "dotted", borderWidth: 1},
});
const CHANGE_EDGE_STYLES = Object.freeze({
  existing: {lineStyle: "solid", width: 1},
  inherited: {lineStyle: "dashed", width: 1},
  changed: {lineStyle: "solid", width: 2},
  added: {lineStyle: "solid", width: 1},
  replaced: {lineStyle: "solid", width: 3},
  removed: {lineStyle: "dotted", width: 1},
});
```

Apply the node base shape from `NODE_KIND_SHAPES`, the edge line/arrow pair from `EDGE_KIND_STYLES`, the node change border/label from `CHANGE_STYLES`, and the edge change line width from `CHANGE_EDGE_STYLES` while retaining each edge-kind arrowhead. An omitted v2 edge kind normalizes to `unknown`; an omitted legacy edge kind retains the existing neutral solid line/triangle appearance. Use `displayLabel` values such as `⇄ Worker [replaced]` and `− Old worker [removed]`; the accessible label and inspector spell out the same state. Keep lifecycle `status` independent of `changeType`: use planned = dashed 2px border, implemented = solid 1px border, and deprecated = dotted 2px border plus readable dimming, alongside status text/chips and an `aria-label`; color is only supplementary.

- [ ] **Step 3: Implement comparison precedence and snapshot filtering.**

Use an explicit collection suffix map and active-array lookup:

```javascript
const COMPARISON_SUFFIX = {nodes: "Node", edges: "Edge", flows: "Flow"};

function comparisonState(model, collection, id) {
  const active = model.comparisons.find((item) => item.id === state.comparisonId);
  if (active) {
    for (const change of ["existing", "inherited", "changed", "added", "replaced", "removed"]) {
      if ((active[`${change}${COMPARISON_SUFFIX[collection]}Ids`] || []).includes(id)) return change;
    }
  }
  const item = byId(model[collection], id);
  return item?.changeType || "existing";
}
```

`chooseComparison` accepts only a known comparison ID, sets `state.comparisonId`, reapplies classes/inventory, and renders `From <from.label> → <to.label>`, counts for all six states across nodes, edges, and flows, replacement links (`new-id replaces old-id`), and the optional summary. An invalid or missing selection resets to `Current`, updates the select, and announces the fallback in the `aria-live` inspector. `chooseSnapshot` filters only elements whose `snapshotIds` include the selected ID; elements without that field stay visible and get the text `snapshot coverage unknown`. Selecting a snapshot never invents a diff. A `Current` option uses `currentSnapshotId` as its value/label when present.

- [ ] **Step 4: Implement filters, labels, inventory, keyboard selection, and inspector safety.**

Implement `applyFilters` with these exact predicates: status equality unless `statusFilter == "all"`; category equality unless `categoryFilter == "all"`; `comparisonState(...)` equality unless `changeFilter == "all"`; hide deprecated only when `showDeprecated == false`; show only explicit element `changeType` or active-comparison membership when `showChangesOnly == true`; and case-insensitive JSON search over the node's label, description, responsibilities, inputs, outputs, source paths, evidence, and coverage gap. `comparisonState` may return `existing` for a missing annotation to make filtering deterministic, but `displayLabel`, legend, and inventory must omit a change badge for missing legacy annotations. Remove an edge from the visible set when either endpoint is hidden. Preserve selected node if it remains visible, otherwise clear it.

Render `#nodeInventory` as a list of `<button type="button" data-node-id="..." data-change-type="...">` entries with text for label, status, kind, and change value. Click and Enter/Space call `chooseNode(id)` and synchronize Cytoscape selection; focus outlines remain visible. Keep relationship buttons keyboard-navigable. Put `aria-live="polite"` on the inspector detail status region, use `textContent` for plain fields, and use `escapeHtml` only for generated list fragments. Add legend entries for category, all three lifecycle states, and all six change values; each entry includes readable text plus its glyph/pattern explanation.

- [ ] **Step 5: Implement responsive and reduced-motion behavior.**

Retain the top bar, graph, inspector, flow navigation, search, Fit, and JSON link. Add CSS that keeps `.map-panel { min-height: 450px; }` at `max-width: 900px`, changes `.workspace` to block and places `.inspector` below the map, and at `max-width: 560px` wraps the toolbar while making mode/filter groups horizontally scrollable or stacked. Do not hide legend or essential controls with positional selectors. Keep `#contentAnchor` scroll-margin and call `scrollIntoView({behavior: reducedMotion ? "auto" : "smooth"})`; pass `animate: !reducedMotion` to layout options. Use `safeCategoryColor` that returns a validated hex token for v2, and `#626878`/`#171922` for unsafe legacy input without interpolating raw CSS.

- [ ] **Step 6: Run the unchanged marker tests and focused suite, then commit UI semantics.**

```powershell
python -m unittest evals/create-project-map/test_build_project_map.py -v
python -m unittest discover -s evals/create-project-map -p "test_*.py" -v
```

Expected: the existing marker tests and focused Python tests pass unchanged; filter, comparison, inventory, style, accessibility, and responsive behavior are verified by the browser checks defined in Task 5.

```powershell
git add skills/create-project-map/assets/project-map-template.html evals/create-project-map/test_build_project_map.py
git commit -m "feat: add project map status and comparison UI"
```

### Task 5: Add evaluation cases and perform real-browser smoke verification

**Files:**
- Modify: `evals/create-project-map/cases.json`
- Modify: `evals/create-project-map/test_build_project_map.py`
- Validate: generated v1/v2 HTML and an in-memory 100-node large-flow fixture

**Interfaces:**
- Consumes: `generated-v1.html`, `generated-v2.html`, the local HTTP server, and the template's `?test=1` read-only telemetry hook.
- Produces: durable evaluation cases and browser evidence; no production dependency or browser state is committed.
- Browser checks use the existing `playwright` skill or an equivalent real browser. Do not add Playwright to `requirements.txt` or `requirements-validation.txt`.

- [ ] **Step 1: Add a failing case-index test before adding the evaluation cases.**

Add this standard-library test to `ProjectMapBuildTests`:

```python
    def test_cases_include_v2_browser_and_large_flow_cases(self):
        cases = json.loads(
            (ROOT / "evals" / "create-project-map" / "cases.json").read_text(encoding="utf-8")
        )
        by_id = {case["id"]: case for case in cases}
        expected = {
            "v2-snapshot-comparison",
            "v2-mode-and-edge-authority",
            "legacy-v1-compatibility",
            "large-flow-bounded-layout",
        }
        self.assertTrue(expected <= set(by_id))
        self.assertEqual(100, by_id["large-flow-bounded-layout"]["expect"]["node_count"])
```

Run:

```powershell
python -m unittest evals/create-project-map/test_build_project_map.py -v
```

Expected: the new test fails because the four v2 case IDs are not yet present.

- [ ] **Step 2: Add concrete evaluation cases.**

Retain all five existing cases and append these records to `evals/create-project-map/cases.json`:

```json
{
  "id": "v2-snapshot-comparison",
  "prompt": "Render the v15 to v15-4 to v16 project map and inspect its comparison states.",
  "fixture": "fixtures/v2-map.json",
  "expect": {
    "schema_version": 2,
    "current_snapshot": "v16",
    "comparison_ids": ["v15-to-v15-4", "v15-4-to-v16"],
    "change_states": ["existing", "inherited", "changed", "added", "replaced", "removed"]
  }
}
```

```json
{
  "id": "v2-mode-and-edge-authority",
  "prompt": "Verify flow, dependency, and combined views without inferring relationships.",
  "fixture": "fixtures/v2-map.json",
  "expect": {
    "default_mode": "flow",
    "default_flow": "request-flow",
    "flow_edge_ids_are_authoritative": true,
    "dependency_contains_all_edges": true,
    "combined_is_explicit": true
  }
}
```

```json
{
  "id": "legacy-v1-compatibility",
  "prompt": "Open a v1 map with a legacy unsafe category color and preserve its initial experience.",
  "fixture": "fixtures/legacy-unsafe-color-map.json",
  "expect": {
    "mode_controls_hidden": true,
    "initial_detail": "All relationships",
    "unsafe_color_fallback": "#626878/#171922",
    "input_not_rewritten": true
  }
}
```

```json
{
  "id": "large-flow-bounded-layout",
  "prompt": "Open a 100-node flow and inspect its top-to-bottom layers without automatic shrinking.",
  "fixture": "in-memory large_flow_document()",
  "expect": {
    "node_count": 100,
    "large_flow_hint": "Large flow — pan or zoom to explore",
    "minimum_initial_zoom": 0.35,
    "breadthfirst_direction_option": "absent",
    "implicit_fit_on_flow_selection": false
  }
}
```

- [ ] **Step 3: Prepare the local smoke artifacts and server.**

Use the already pinned template and build both fixtures into a temporary directory so the relative JSON links are exercised:

```powershell
$SMOKE_ROOT = Join-Path ([System.IO.Path]::GetTempPath()) "create-project-map-v2-smoke"
New-Item -ItemType Directory -Force $SMOKE_ROOT
Copy-Item evals/create-project-map/fixtures/valid-map.json (Join-Path $SMOKE_ROOT "v1.json")
Copy-Item evals/create-project-map/fixtures/v2-map.json (Join-Path $SMOKE_ROOT "v2.json")
python skills/create-project-map/scripts/build_project_map.py --data (Join-Path $SMOKE_ROOT "v1.json") --template skills/create-project-map/assets/project-map-template.html --output (Join-Path $SMOKE_ROOT "v1.html")
python skills/create-project-map/scripts/build_project_map.py --data (Join-Path $SMOKE_ROOT "v2.json") --template skills/create-project-map/assets/project-map-template.html --output (Join-Path $SMOKE_ROOT "v2.html")
python -m http.server 8765 --directory $SMOKE_ROOT
```

The large-flow browser payload must be deterministic: 100 nodes named `large-node-000` through `large-node-099`, 99 directed edges named `large-edge-000` through `large-edge-098`, one flow containing every node and edge ID, positions `x=(index % 10) * 180`, `y=(index // 10) * 100`, category `service`, phase `phase-1`, and `evidence: ["fixtures/large-flow-map.json"]`. Serve it as a temporary `large.json` beside `large.html`, and validate it with `validate_project_map.py` before opening it.

- [ ] **Step 4: Run desktop and mobile browser assertions with named checks.**

Use the browser skill against `http://127.0.0.1:8765/v2.html?test=1` at a desktop viewport (1440×900) and a mobile viewport (390×844). The implementation may expose the read-only hook only when `location.search` contains `test=1`; it must return IDs, mode, layout, zoom, fit-call count, style data, and selected state without mutation. Capture console messages and page errors, and run these concrete checks:

The functions below are the single executable definitions for the Task 3 and Task 4 RED gates as well as this final smoke run. Reuse or refactor them in place; do not add source-marker tests or duplicate their assertions in Python.

```javascript
async function test_initial_v2_mode_and_default_flow(page) {
  await page.goto("http://127.0.0.1:8765/v2.html?test=1");
  await expect(page.locator("#modeControls [data-mode='flow']")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#flowNav [data-flow-id='request-flow']")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#detailTitle")).toContainText("Request flow");
  await expect(page.locator("#cy")).toHaveAttribute("data-layout-mode", "flow");
}

async function test_dependency_and_combined_use_exact_edge_sets(page) {
  await page.locator("#modeControls [data-mode='dependency']").click();
  const dependency = await page.evaluate(() => window.__projectMapTestHooks.getState());
  expect(dependency.visibleNodeIds).toHaveLength(dependency.allNodeIds.length);
  expect(dependency.visibleEdgeIds).toHaveLength(dependency.allEdgeIds.length);
  await page.locator("#modeControls [data-mode='combined']").click();
  const combined = await page.evaluate(() => window.__projectMapTestHooks.getState());
  expect(combined.visibleEdgeIds).toEqual(combined.allEdgeIds);
  expect(combined.flowEdgeIds.every((id) => combined.emphasizedEdgeIds.includes(id))).toBeTruthy();
  expect(combined.nonFlowEdgeIds.every((id) => !combined.emphasizedEdgeIds.includes(id))).toBeTruthy();
}

async function test_flow_edge_ids_and_comparison_precedence(page) {
  await page.locator("#modeControls [data-mode='flow']").click();
  const flow = await page.evaluate(() => window.__projectMapTestHooks.getState());
  expect([...flow.visibleEdgeIds].sort()).toEqual([...flow.selectedFlow.edgeIds].sort());
  expect(flow.visibleEdgeIds).not.toContain("edge-to-external");
  await page.locator("#comparisonSelect").selectOption("v15-4-to-v16");
  await expect(page.locator("#detailBody")).toContainText("From v15-4 → v16");
  await expect(page.locator("#nodeInventory [data-node-id='api']")).toHaveAttribute("data-change-type", "existing");
  await expect(page.locator("#detailBody")).toContainText("replaces");
}

async function test_search_filters_labels_and_inventory_keyboard(page) {
  await page.locator("#nodeSearch").fill("worker");
  await expect(page.locator("#nodeInventory [data-node-id='worker-v2']")).toBeVisible();
  await page.locator("#showLabelsToggle").uncheck();
  await expect(page.locator("#cy")).toHaveAttribute("data-labels", "hidden");
  await page.locator("#nodeInventory [data-node-id='worker-v2']").focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#detailKicker")).toContainText("Node inspector");
  await expect(page.locator("#inspector")).toHaveAttribute("aria-live", "polite");
}

async function test_legacy_v1_initial_view_and_unsafe_color(page) {
  await page.goto("http://127.0.0.1:8765/v1.html?test=1");
  await expect(page.locator("#modeControls")).toBeHidden();
  await expect(page.locator("#detailTitle")).toHaveText("All relationships");
  const state = await page.evaluate(() => window.__projectMapTestHooks.getState());
  expect(state.categoryColors.service).toBe("#626878");
  expect(state.fillColor).toBe("#171922");
}

async function test_filters_kind_mappings_and_snapshot_coverage(page) {
  await page.goto("http://127.0.0.1:8765/v2.html?test=1");
  await page.locator("#categoryFilter").selectOption("external");
  await expect(page.locator("#nodeInventory [data-node-id='external']")).toBeVisible();
  await page.locator("#categoryFilter").selectOption("all");
  await page.locator("#changeFilter").selectOption("replaced");
  await expect(page.locator("#nodeInventory [data-node-id='worker-v2']")).toBeVisible();
  await page.locator("#changeFilter").selectOption("all");
  await page.locator("#statusFilter").selectOption("deprecated");
  await expect(page.locator("#nodeInventory [data-node-id='worker-v1']")).toBeVisible();
  await page.locator("#showDeprecatedToggle").uncheck();
  await page.locator("#showChangesOnlyToggle").check();
  const styles = await page.evaluate(() => window.__projectMapTestHooks.getState().styles);
  expect(styles.nodes["api"].shape).toBe("roundrectangle");
  expect(styles.nodes["ui"].shape).toBe("rectangle");
  expect(styles.nodes["worker-v2"].shape).toBe("hexagon");
  expect(styles.nodes["store"].shape).toBe("diamond");
  expect(styles.nodes["external"].shape).toBe("ellipse");
  expect(styles.nodes["contract"].shape).toBe("tag");
  expect(styles.nodes["decision"].shape).toBe("octagon");
  expect(styles.nodes["actor"].shape).toBe("star");
  expect(styles.edges["api-calls-ui"]).toMatchObject({lineStyle: "solid", arrow: "vee"});
  expect(styles.edges["api-data-store"]).toMatchObject({lineStyle: "solid", arrow: "triangle"});
  expect(styles.edges["api-event-worker"]).toMatchObject({lineStyle: "dashed", arrow: "triangle"});
  expect(styles.edges["edge-contains"]).toMatchObject({lineStyle: "solid", arrow: "diamond"});
  expect(styles.edges["edge-inherits"]).toMatchObject({lineStyle: "dotted", arrow: "tee"});
  expect(styles.edges["edge-depends-on"]).toMatchObject({lineStyle: "dashed", arrow: "vee"});
  expect(styles.edges["edge-replaces"]).toMatchObject({lineStyle: "solid", arrow: "diamond", width: 3});
  expect(styles.edges["edge-to-external"]).toMatchObject({lineStyle: "dotted", arrow: "circle"});
  await page.locator("#statusFilter").selectOption("all");
  await page.locator("#showDeprecatedToggle").check();
  await page.locator("#showChangesOnlyToggle").uncheck();
  await page.locator("#snapshotSelect").selectOption("v15");
  await expect(page.locator("#nodeInventory")).toContainText("snapshot coverage unknown");
  await page.evaluate(() => window.__projectMapTestHooks.chooseComparison("missing-comparison"));
  await expect(page.locator("#detailBody")).toContainText("Current");
}

async function test_pointer_zoom_focus_and_mobile_layout(page) {
  await page.goto("http://127.0.0.1:8765/v2.html?test=1");
  const before = await page.evaluate(() => window.__projectMapTestHooks.getState().zoom);
  await page.mouse.wheel(0, -300);
  const after = await page.evaluate(() => window.__projectMapTestHooks.getState().zoom);
  expect(after).toBeGreaterThan(before);
  await page.locator("#fitButton").click();
  await page.setViewportSize({width: 390, height: 844});
  await expect(page.locator(".map-panel")).toHaveCSS("min-height", "450px");
  await expect(page.locator("#modeControls")).toBeVisible();
  await expect(page.locator("#statusFilter")).toBeVisible();
  await expect(page.locator("#fitButton")).toBeVisible();
  await expect(page.locator("#inspector")).toBeVisible();
}
```

Also verify every `NODE_KIND_SHAPES` entry, every `EDGE_KIND_STYLES` line/arrow pair, all status/change text and glyphs, flow stage/actor/trigger/outcome/output/safety/evidence/coverage content, relation buttons, Fit, pan, wheel/touch zoom, reset-fit, focus outlines, and no essential controls hidden at 390px. The browser console and `pageerror` collection must be empty on both viewports.

- [ ] **Step 5: Run the large-flow, reduced-motion, and recovery checks.**

Use the same browser session with the deterministic 100-node payload:

```javascript
async function test_large_flow_keeps_zoom_floor_and_tb_layers(page) {
  await page.goto("http://127.0.0.1:8765/large.html?test=1");
  const state = await page.evaluate(() => window.__projectMapTestHooks.getState());
  expect(state.largeFlow).toBe(true);
  expect(state.zoom).toBeGreaterThanOrEqual(0.35);
  expect(state.fitCallsAfterSelection).toBe(0);
  expect(state.rootMeanY).toBeLessThan(state.downstreamMeanY);
  expect(state.layoutOptions.direction).toBeUndefined();
  await page.locator("#fitButton").click();
  expect((await page.evaluate(() => window.__projectMapTestHooks.getState())).fitCallsAfterSelection).toBe(1);
}

async function test_reduced_motion_and_recovery_messages(page) {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("http://127.0.0.1:8765/v2.html?test=1");
  await page.locator("#flowNav [data-flow-id='request-flow']").click();
  expect(await page.evaluate(() => window.__projectMapTestHooks.lastScrollBehavior)).toBe("auto");
  await page.goto("http://127.0.0.1:8765/missing.html?test=1");
  await expect(page.locator("#loading")).toContainText("local HTTP server");
  await expect(page.locator("#loading")).toContainText("JSON");
}
```

Route the Cytoscape CDN to fail once and verify the same visible escaped recovery message. Feed a malformed v2 JSON with a bad `view` object and verify it does not render a graph or downgrade to v1. Confirm no `eval`, inline JSON blob, external navigation from `sourcePaths`, or raw unsafe legacy color appears in the generated HTML.

- [ ] **Step 6: Finish the focused evaluation run and commit cases.**

```powershell
python -m unittest discover -s evals/create-project-map -p "test_*.py" -v
```

Expected: all standard-library tests pass. Record the browser viewport, URL, fixture, console/page-error result, and each named check in the implementation handoff; do not claim interactive verification if a browser is unavailable.

```powershell
git add evals/create-project-map/cases.json evals/create-project-map/test_build_project_map.py
git commit -m "test: cover project map v2 evaluations"
```

### Task 6: Document v2 behavior, integrate CI, and run repository gates

**Files:**
- Modify: `skills/create-project-map/references/project-map-schema.md`
- Modify: `skills/create-project-map/SKILL.md`
- Modify: `skills/create-project-map/README.md`
- Modify: `.github/workflows/validate-skills.yml`
- Do not modify: root `README.md`, `context-budget-baseline.json`, or `context-budget-manifest.json` unless an explicitly reviewed baseline change is required.

**Interfaces:**
- Consumes: completed validator, builder, template, fixtures, evaluation cases, and browser evidence.
- Produces: concise operator instructions, complete schema reference, CI execution of the focused suite, and repository validation evidence.

- [ ] **Step 1: Review the documentation contract before editing docs.**

Use this checklist during implementation; do not add a source-text test that greps human prose. Confirm the schema reference documents the unchanged seven v1 fields, every recognized v2 field and exact enum/reference rule, replacement reciprocity, comparison-state precedence, legacy normalization, unsafe-color fallback, and no-inline-data/security behavior. Confirm `SKILL.md` keeps its frontmatter and exact build/validate commands, describes stable-ID merging and invalid-existing-JSON recovery, names the browser checks and local HTTP-server requirement, and states the runtime/output boundary. Confirm the README remains concise, Japanese-facing, names the v2 modes/snapshots/comparisons/filters/accessibility additions and the three implementation assets, and states v2 is additive with invalid existing JSON preserved. Reconcile each statement with the validator, builder, template, fixture, and browser-test interfaces before moving on.

- [ ] **Step 2: Expand the schema reference with exact v1/v2 rules and examples.**

Keep the seven v1 required fields and current node/edge/flow examples. Add the exact v2 top-level payload, field rules for `schemaVersion`, `currentSnapshotId`, `snapshots`, `comparisons`, and `view`, all allowed kind/change/status values, color regex semantics, flow endpoint rule, replacement reciprocity, finite positions, comparison mutual exclusion, and legacy normalization. Include this compact complete replacement example:

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

State that absent v2 fields do not cause a legacy rewrite, missing v2 annotations do not show badges, missing v2 `view.defaultMode` normalizes to dependency, empty flow lists fall back to dependency, and malformed recognized v2 objects show recovery errors rather than v1 fallback. Document exact node shapes, edge line/arrow pairs, change glyphs/borders, active comparison precedence, snapshot coverage unknown, HTML escaping, neutral legacy color fallback, and the no-inline-JSON rule.

- [ ] **Step 3: Update `SKILL.md` without changing its frontmatter.**

Keep the existing `name`, `description`, and `agents/openai.yaml` interface unchanged. Replace the workflow body with concise imperative steps that:

1. locate the approved plan and repository root;
2. inspect only relevant README, AGENTS, plan, source, test, build, and runtime evidence;
3. validate any existing `architecture-map.json` before editing and stop without overwriting invalid data;
4. merge by stable IDs, preserve positions, retain replacements/deprecations, and distinguish planned from implemented evidence;
5. write the seven v1 fields plus optional v2 fields;
6. render with the existing `build_project_map.py` command;
7. validate JSON and HTML;
8. browser-check legacy, flow, dependency, combined, snapshots/comparisons, filters, inventory, keyboard navigation, responsive layout, reduced motion, large-flow behavior, and console recovery;
9. report artifact paths, evidence-backed statuses, coverage gaps, and any browser block.

Keep the exact commands:

```bash
python <skill-dir>/scripts/build_project_map.py \
  --data <repo>/architecture-map.json \
  --template <skill-dir>/assets/project-map-template.html \
  --output <repo>/architecture-map.html

python <skill-dir>/scripts/validate_project_map.py \
  <repo>/architecture-map.json \
  --html <repo>/architecture-map.html
```

State that the Skill runtime writes only repository-root `architecture-map.json` and `architecture-map.html`, never commits/pushes/publishes/deploys, never persists browser state, and requires a local HTTP server with reachable same-origin JSON and pinned CDN for interactive verification.

- [ ] **Step 4: Update the concise human-facing README.**

Retain the H1 and Japanese audience. Add a short “v2 additions” section naming flow/dependency/combined modes, snapshots/comparisons, lifecycle/change filters, accessible inventory, v1 compatibility, the three implementation assets, and the two build/validate output files. State that v2 fields are additive and that malformed existing JSON is preserved.

- [ ] **Step 5: Add the focused suite to CI without adding a browser dependency.**

In `.github/workflows/validate-skills.yml`, after the existing root unit-test step and before the review eval step, add:

```yaml
      - run: python -m unittest discover -s evals/create-project-map -p "test_*.py" -v
```

Do not add Node, Playwright, a layout plugin, or a browser download to the workflow. The repository's standard-library tests run in CI; the real-browser gate remains the documented `playwright` skill/manual check from Task 5.

- [ ] **Step 6: Run focused tests and the required repository validation commands.**

Install the pinned validation dependency and run the focused suite:

```powershell
python -m pip install -r requirements-validation.txt
python -m unittest discover -s evals/create-project-map -p "test_*.py" -v
```

Expected: dependency installation succeeds; all current and v2 evals pass.

Validate generated artifacts again:

```powershell
python skills/create-project-map/scripts/build_project_map.py --data evals/create-project-map/fixtures/valid-map.json --template skills/create-project-map/assets/project-map-template.html --output evals/create-project-map/generated-v1.html
python skills/create-project-map/scripts/build_project_map.py --data evals/create-project-map/fixtures/v2-map.json --template skills/create-project-map/assets/project-map-template.html --output evals/create-project-map/generated-v2.html
python skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/fixtures/valid-map.json --html evals/create-project-map/generated-v1.html
python skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/fixtures/v2-map.json --html evals/create-project-map/generated-v2.html
```

Expected: four commands exit `0`; both generated HTML files contain the required HTML markers and relative JSON links.

Run repository gates required by `AGENTS.md` and the current workflow:

```powershell
python scripts/validate-skills.py
python scripts/generate-skill-catalog.py --check
python scripts/context_budget_report.py --repo . --manifest context-budget-manifest.json --baseline context-budget-baseline.json --max-growth-bytes 0
python -m unittest discover -s tests -v
python -m unittest discover -s evals/review-implementation-html -p "test_*.py" -v
git diff --check
```

Expected: all validation/tests pass and `git diff --check` prints nothing. If the context-budget command reports growth from the edited Skill, shorten only redundant model-visible prose and move detail to the schema reference, then rerun until the zero-growth command passes; do not update the tracked baseline without explicit review. The root catalog should remain current because frontmatter is unchanged; never hand-edit its generated section.

- [ ] **Step 7: Inspect scope, remove temporary smoke files, and commit documentation/CI.**

```powershell
Remove-Item -LiteralPath 'evals/create-project-map/generated-v1.html' -ErrorAction SilentlyContinue
Remove-Item -LiteralPath 'evals/create-project-map/generated-v2.html' -ErrorAction SilentlyContinue
git status --short
git diff --stat
git diff --check
```

Expected: only the files listed in this plan are changed, no generated HTML is staged, no unrelated concurrent edit is reverted, and the diff is whitespace-clean.

```powershell
git add skills/create-project-map/references/project-map-schema.md skills/create-project-map/SKILL.md skills/create-project-map/README.md .github/workflows/validate-skills.yml
git commit -m "docs: document project map schema v2"
```

## Final Acceptance Checklist

- [ ] `valid-map.json`, `invalid-edge-map.json`, `v2-map.json`, and `legacy-unsafe-color-map.json` produce the expected validator results.
- [ ] All v2 recognized fields validate references, enums, duplicate IDs, parent cycles, finite positions, replacement reciprocity, comparison-state exclusivity, and malformed array types before any output write.
- [ ] Builder escaping, relative JSON paths, no-inline-v2-data, legacy unsafe-color fallback, and invalid-output preservation are covered by named tests.
- [ ] Flow mode uses exact `nodeIds`/`edgeIds`; dependency mode uses all directed edges; combined mode emphasizes only the selected flow; no edge is inferred.
- [ ] Breadth-first flow layout uses only supported Cytoscape options, applies deterministic TB correction, preserves preset coordinates, uses the large-flow zoom floor/hint, and reserves Fit for explicit user action.
- [ ] All node/edge kinds, lifecycle statuses, change glyphs/patterns, active comparison precedence, snapshot coverage, filters, labels, deprecated toggles, inventory selection, inspector relationships, keyboard/focus, responsive breakpoints, and reduced motion are verified.
- [ ] Desktop/mobile browser checks report no console/page errors; fetch, invalid JSON, and missing CDN recovery messages remain visible and escaped.
- [ ] Focused evals are CI-enforced; `validate-skills.py`, catalog check, zero-growth context report, root tests, review evals, generated-artifact validation, and `git diff --check` pass.
- [ ] No runtime dependency, product-code change, map publication, automatic migration, or persisted browser state was added.

Plan complete and saved to `docs/superpowers/plans/2026-08-31-create-project-map-v2.md`. Two execution options:

1. Subagent-Driven (recommended) — dispatch a fresh subagent per task and review between tasks.
2. Inline Execution — execute tasks in this session using executing-plans with checkpoints.

Choose one approach before implementation.
