# Project Map Schema

Use UTF-8 JSON. All referenced IDs must exist and be unique within their collection.

## Top-level fields

| Field | Type | Required content |
|---|---|---|
| `project` | object | `id`, `title`, `summary` |
| `sources` | array | `{path, kind}` using repository-relative paths |
| `categories` | array | `{id, label, color}` |
| `nodes` | array | Components and contracts represented as graph nodes |
| `edges` | array | Directed relationships |
| `flows` | array | Selectable end-to-end paths |
| `phases` | array | `{id, label, description}` |

## Node

Required fields:

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

Statuses:

- `planned`: specified but not confirmed in implementation.
- `implemented`: confirmed by inspected code, tests, build output, or runtime evidence.
- `deprecated`: retained temporarily to show a migration or removal.

`evidence` or `coverageGap` must be non-empty. Evidence paths do not need to exist for `planned` nodes when they identify the source plan.

## Edge

```json
{
  "id": "api-to-worker",
  "source": "api-service",
  "target": "worker",
  "label": "dispatches",
  "contract": "Command"
}
```

Edges are directed. `source` and `target` must reference node IDs.

## Flow

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

Each `nodeIds` and `edgeIds` entry must reference an existing element. Stage node IDs must be part of the project map; they should normally also appear in the Flow's `nodeIds`.

## Layout

- Preserve existing finite `position.x` and `position.y` values by stable node ID.
- Place new nodes in the nearest relevant category/Flow region.
- Avoid identical coordinates.
- Keep the primary direction left-to-right when the plan does not define another direction.

