---
name: create-project-map
description: Create or update a living interactive project architecture map as architecture-map.html plus machine-readable architecture-map.json. Use after a plan or specification is approved, or when the user asks for a project map, architecture map, dependency map, implementation map, module map, system flow visualization, or reusable visual context for later agents.
---

# Create Project Map

Build one living map for the repository. Update existing artifacts instead of
creating a map per plan.

## Workflow

1. Locate the repository root and an approved plan or specification. Stop and
   request the plan when it cannot be identified; filenames alone are not
   architecture evidence.
2. Read only relevant README, `AGENTS.md`, plan sections, source, tests,
   build output, and runtime evidence. Read [project-map-schema.md](references/project-map-schema.md)
   before writing the model.
3. If `<repo>/architecture-map.json` exists, run the Python validator first.
   It is authoritative for writes: stop on any error and preserve the original;
   never overwrite malformed JSON. Browser v2 checks are defensive recovery,
   not full-invariant parity.
4. Merge by stable IDs. Preserve valid positions, directed relationships, and
   replacement/deprecated records. Add plan-only records as `planned`; mark
   `implemented` only with inspected code, tests, build, or runtime evidence.
   Keep relative evidence paths and explicit coverage gaps.
5. Write the seven v1 fields and optional v2 fields. Active comparison state
   takes precedence over an element annotation; do not infer edges or rewrite
   legacy input.
6. Render and validate with the existing standard-library scripts:

   ```bash
   python <skill-dir>/scripts/build_project_map.py \
     --data <repo>/architecture-map.json \
     --template <skill-dir>/assets/project-map-template.html \
     --output <repo>/architecture-map.html

   python <skill-dir>/scripts/validate_project_map.py \
     <repo>/architecture-map.json \
     --html <repo>/architecture-map.html
   ```

7. Serve the repository over a local HTTP server, then browser-check legacy,
   flow, dependency, combined, snapshots/comparisons, search and lifecycle/
   category/change filters, inventory and relationship navigation, keyboard
   focus, responsive layout, reduced motion, large-flow behavior, pan/zoom,
   explicit Fit, direct malformed-v2 recovery, and missing-JSON/invalid-JSON/
   CDN console recovery.
8. Report both artifact paths, validation, evidence-backed status changes,
   comparison/coverage gaps, and any browser block.

## Runtime boundary

The Skill writes only repository-root `architecture-map.json` and
`architecture-map.html`. It uses the pinned Cytoscape CDN and same-origin JSON
fetch at runtime, requires the local HTTP server for interactive verification,
and never commits, pushes, publishes, deploys, migrates, or deletes. URL
hash/history may reflect the current mode or selection, but browser state is
never persisted into JSON/HTML artifacts or committed.
