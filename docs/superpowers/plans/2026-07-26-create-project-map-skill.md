# Create Project Map Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable `create-project-map` skill that updates a repository-root `architecture-map.json` and renders an interactive `architecture-map.html`.

**Architecture:** The agent inspects an approved plan and repository evidence, then writes the normalized JSON model. Standard-library Python scripts validate that model and render a generic HTML template. Stable IDs and positions are merge invariants; status promotion requires code, test, build, or runtime evidence.

**Tech Stack:** Markdown Agent Skill format, Python 3 standard library, vanilla HTML/CSS/JavaScript, Cytoscape.js 3.34.0 from a pinned CDN URL, `unittest`.

## Global Constraints

- Create the skill under `skills/create-project-map/`.
- Use only Python's standard library in bundled scripts and tests.
- Write generated artifacts only to the target repository root unless the user supplies explicit paths.
- Never modify product code, commit, push, publish, or deploy.
- Escape all plan and repository text before rendering.
- Preserve existing node positions for stable IDs.
- Use only `planned`, `implemented`, and `deprecated` node statuses.
- Treat an element as `implemented` only with inspected code, test, build, or runtime evidence.
- Keep `SKILL.md` under 500 lines and move schema detail to `references/project-map-schema.md`.

---

### Task 1: Initialize the skill and implement JSON validation

**Files:**
- Create: `skills/create-project-map/SKILL.md`
- Create: `skills/create-project-map/agents/openai.yaml`
- Create: `skills/create-project-map/scripts/validate_project_map.py`
- Create: `evals/create-project-map/fixtures/valid-map.json`
- Create: `evals/create-project-map/fixtures/invalid-edge-map.json`
- Create: `evals/create-project-map/test_validate_project_map.py`

**Interfaces:**
- Produces: `validate_document(document: dict) -> list[str]`
- Produces: CLI `python validate_project_map.py <json-path> [--html <html-path>]`
- Exit code `0` means valid; exit code `1` prints each validation error.

- [ ] **Step 1: Initialize the skill scaffold**

Run:

```powershell
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\init_skill.py create-project-map `
  --path skills `
  --resources scripts,references,assets `
  --interface display_name="Create Project Map" `
  --interface short_description="Create and update a living architecture map" `
  --interface default_prompt="Use $create-project-map to turn the approved plan into an interactive architecture map and machine-readable JSON."
```

Expected: `skills/create-project-map/` exists with `SKILL.md` and `agents/openai.yaml`.

- [ ] **Step 2: Add minimal valid and invalid fixtures**

Create `valid-map.json` with one category, two nodes, one edge, one flow, and one phase. Create `invalid-edge-map.json` by changing the edge target to `missing-node`.

- [ ] **Step 3: Write the failing validator tests**

```python
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/create-project-map/scripts/validate_project_map.py"
SPEC = importlib.util.spec_from_file_location("validate_project_map", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProjectMapValidationTests(unittest.TestCase):
    def load(self, name):
        path = pathlib.Path(__file__).parent / "fixtures" / name
        return json.loads(path.read_text(encoding="utf-8"))

    def test_valid_document_has_no_errors(self):
        self.assertEqual(MODULE.validate_document(self.load("valid-map.json")), [])

    def test_missing_edge_target_is_reported(self):
        errors = MODULE.validate_document(self.load("invalid-edge-map.json"))
        self.assertTrue(any("missing-node" in error for error in errors))
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```powershell
python -m unittest evals.create-project-map.test_validate_project_map -v
```

Expected: FAIL because `validate_document` does not exist.

- [ ] **Step 5: Implement `validate_document` and CLI**

Validate required top-level keys, unique IDs, category references, edge endpoints, flow node/edge references, phase references, allowed statuses, finite numeric positions, and evidence/coverage-gap presence. Add optional HTML checks for `id="cy"`, `id="flowNav"`, `architecture-map.json`, and the Cytoscape loader.

- [ ] **Step 6: Run validator tests**

Run:

```powershell
python -m unittest evals.create-project-map.test_validate_project_map -v
python skills/create-project-map/scripts/validate_project_map.py evals/create-project-map/fixtures/valid-map.json
```

Expected: all tests PASS and CLI prints a valid summary.

- [ ] **Step 7: Commit the validator**

```powershell
git add skills/create-project-map evals/create-project-map
git commit -m "feat: add project map validation"
```

### Task 2: Implement deterministic HTML rendering

**Files:**
- Create: `skills/create-project-map/scripts/build_project_map.py`
- Create: `skills/create-project-map/assets/project-map-template.html`
- Create: `evals/create-project-map/test_build_project_map.py`

**Interfaces:**
- Produces: `render_html(document: dict, template: str, data_filename: str) -> str`
- Produces: CLI `python build_project_map.py --data <json> --template <html> --output <html>`
- Template tokens: `{{PROJECT_TITLE}}`, `{{PROJECT_SUMMARY}}`, and `{{DATA_FILENAME}}`.

- [ ] **Step 1: Write failing rendering tests**

```python
class ProjectMapBuildTests(unittest.TestCase):
    def test_render_replaces_tokens_and_escapes_text(self):
        document = {"project": {"title": "<Map>", "summary": "A & B"}}
        rendered = MODULE.render_html(
            document,
            "<title>{{PROJECT_TITLE}}</title><p>{{PROJECT_SUMMARY}}</p><b>{{DATA_FILENAME}}</b>",
            "architecture-map.json",
        )
        self.assertIn("&lt;Map&gt;", rendered)
        self.assertIn("A &amp; B", rendered)
        self.assertIn("architecture-map.json", rendered)
        self.assertNotIn("{{PROJECT_", rendered)

    def test_template_contains_required_controls(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        for marker in ('id="cy"', 'id="flowNav"', 'id="nodeSearch"', 'id="fitButton"'):
            self.assertIn(marker, template)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m unittest evals.create-project-map.test_build_project_map -v
```

Expected: FAIL because the builder and template do not exist.

- [ ] **Step 3: Implement the generic template**

Adapt the verified MAD Driving map into a project-neutral template. Retain graph search, category legend, four-or-more flow cards, node inspector, flow inspector, pan/zoom/fit, responsive layout, and explicit loading errors. Replace project-specific Japanese copy and data assumptions with JSON-driven labels.

- [ ] **Step 4: Implement the renderer CLI**

Use `argparse`, `html.escape`, `json`, and `pathlib`. Load and validate JSON before rendering. Refuse to overwrite output when validation fails. Write UTF-8 HTML and print the output path.

- [ ] **Step 5: Run build tests and fixture generation**

Run:

```powershell
python -m unittest evals.create-project-map.test_build_project_map -v
python skills/create-project-map/scripts/build_project_map.py `
  --data evals/create-project-map/fixtures/valid-map.json `
  --template skills/create-project-map/assets/project-map-template.html `
  --output evals/create-project-map/generated-map.html
python skills/create-project-map/scripts/validate_project_map.py `
  evals/create-project-map/fixtures/valid-map.json `
  --html evals/create-project-map/generated-map.html
```

Expected: tests PASS and generated artifacts validate.

- [ ] **Step 6: Commit the renderer**

```powershell
git add skills/create-project-map evals/create-project-map
git commit -m "feat: render interactive project maps"
```

### Task 3: Write concise skill instructions and schema reference

**Files:**
- Modify: `skills/create-project-map/SKILL.md`
- Modify: `skills/create-project-map/agents/openai.yaml`
- Create: `skills/create-project-map/references/project-map-schema.md`
- Create: `evals/create-project-map/cases.json`

**Interfaces:**
- `SKILL.md` directs the agent to inspect evidence, merge by stable ID, write JSON, run the builder, validate, and browser-check.
- `cases.json` contains prompt, fixture, expected files, and required assertions for regression evaluation.

- [ ] **Step 1: Write `project-map-schema.md`**

Document exact required fields for project, categories, nodes, edges, flows, phases, positions, evidence, and coverage gaps. Include one compact complete JSON example and the three status definitions.

- [ ] **Step 2: Replace scaffold instructions in `SKILL.md`**

Use imperative workflow steps:

1. locate the approved plan and repository root;
2. inspect only relevant repository evidence;
3. validate an existing map before editing;
4. merge by stable IDs and preserve positions;
5. write `architecture-map.json`;
6. render `architecture-map.html`;
7. run both validators;
8. open through a local HTTP server and verify search, flow selection, node selection, desktop/mobile layout, and console state;
9. report evidence vs coverage gaps.

Include explicit stop conditions for a missing plan or malformed existing map.

- [ ] **Step 3: Regenerate UI metadata**

Run:

```powershell
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\generate_openai_yaml.py `
  skills/create-project-map `
  --interface display_name="Create Project Map" `
  --interface short_description="Create and update a living architecture map" `
  --interface default_prompt="Use $create-project-map to turn the approved plan into an interactive architecture map and machine-readable JSON."
```

- [ ] **Step 4: Add regression cases**

Add cases for initial plan-only generation, updating while preserving coordinates, promoting an implemented node from code evidence, retaining an unresolved relationship as a coverage gap, and rejecting a broken reference.

- [ ] **Step 5: Run final skill validation**

Run:

```powershell
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/create-project-map
python -m unittest discover -s evals/create-project-map -p "test_*.py" -v
```

Expected: skill validation and all tests PASS.

- [ ] **Step 6: Browser smoke-test generated HTML**

Serve `evals/create-project-map/` over HTTP, open `generated-map.html`, and verify required interactions at desktop and mobile viewports with no console errors.

- [ ] **Step 7: Commit the completed skill**

```powershell
git add skills/create-project-map evals/create-project-map
git commit -m "feat: add create project map skill"
```
