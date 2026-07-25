---
name: create-project-map
description: Create or update a living interactive project architecture map as architecture-map.html plus machine-readable architecture-map.json. Use after a plan or specification is approved, or when the user asks for a project map, architecture map, dependency map, implementation map, module map, system flow visualization, or reusable visual context for later agents.
---

# Create Project Map

Build one living map for the repository. Update existing artifacts instead of creating a map per plan.

## Required Inputs

- An approved plan or specification.
- The target repository root.
- Repository evidence sufficient to distinguish planned and implemented components.

Stop and request the plan when it cannot be found or identified. Do not infer an architecture from filenames alone.

## Workflow

1. Resolve the repository root and approved plan.
2. Read relevant README, AGENTS.md, plan sections, source paths, tests, and build/runtime evidence. Do not inventory unrelated files.
3. If `architecture-map.json` exists, run `scripts/validate_project_map.py` before editing it. Stop on invalid data and preserve the original file.
4. Read [project-map-schema.md](references/project-map-schema.md).
5. Merge the project model:
   - match nodes and flows by stable ID;
   - preserve positions for retained node IDs;
   - add plan-only elements as `planned`;
   - promote to `implemented` only with inspected code, test, build, or runtime evidence;
   - mark removed plan elements `deprecated` before deleting them;
   - record repository-relative evidence and explicit coverage gaps.
6. Write `architecture-map.json` at the repository root.
7. Copy `assets/project-map-template.html` only through the renderer:

   ```bash
   python <skill-dir>/scripts/build_project_map.py \
     --data <repo>/architecture-map.json \
     --template <skill-dir>/assets/project-map-template.html \
     --output <repo>/architecture-map.html
   ```

8. Validate both artifacts:

   ```bash
   python <skill-dir>/scripts/validate_project_map.py \
     <repo>/architecture-map.json \
     --html <repo>/architecture-map.html
   ```

9. Serve the repository over HTTP. Browser-check:
   - initial all-relationships view;
   - search;
   - each Flow selection and automatic detail scroll;
   - node selection and relationship navigation;
   - fit, pan, and zoom;
   - desktop and mobile layout;
   - browser console errors.
10. Report the artifact paths, validation result, evidence-backed status changes, and remaining coverage gaps.

## Merge Rules

- Use lower-case hyphenated stable IDs.
- Keep manually adjusted coordinates unless the node is new.
- Keep directed relationships explicit; do not invent an edge when the contract is unknown.
- Prefer one Flow per meaningful user, system, training, evaluation, or delivery path.
- Keep Flow descriptions short enough for navigation cards.
- Treat generated file paths from a plan as planned evidence, not implementation evidence.
- Never remove malformed existing JSON, product code, or unrelated user changes.

## Output Boundary

The skill may write only:

- `<repo>/architecture-map.json`
- `<repo>/architecture-map.html`

Do not commit, push, deploy, or publish unless the user separately requests it. Warn that GitHub Pages publication makes the map publicly reachable.

## Failure Handling

- Missing plan: stop and request it.
- Invalid existing JSON: report validator errors and do not overwrite.
- Unresolved relationship: retain a coverage gap.
- Missing Cytoscape.js or JSON at runtime: preserve the template's visible recovery message and provide local-server instructions.
- Browser unavailable: report browser verification as blocked; do not claim the HTML was interactively verified.
