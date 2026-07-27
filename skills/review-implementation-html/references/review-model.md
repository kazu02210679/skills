# Review data model

Use this schema for `docs/reviews/<plan-slug>/review-data.json`. The validator
is authoritative:

```text
scripts/validate_review_report.py
```

## Top-level fields

| Field | Type | Meaning |
| --- | --- | --- |
| `meta` | object | Repository, revision, plan, slug, and generation metadata. |
| `summary` | object | `headline` and `overview` shown at the top of the report. |
| `verification` | array | Commands or checks and their observed outcomes. |
| `intentGroups` | array | Risk-ordered behavioral groups that own hunks and findings. |
| `files` | array | Changed files referenced by hunks and findings. |
| `hunks` | array | Explained diff fragments. |
| `findings` | array | Evidence-backed review findings from either pass. |
| `coverage` | object | Reviewed files/groups and explicit gaps. |
| `result` | string | Overall review result. |

## Metadata

`meta` requires string fields:

- `repository`: a repository name or non-sensitive path;
- `base`: reviewed base revision;
- `head`: reviewed head revision or `WORKTREE`;
- `plan`: approved plan path, or an empty string for a confirmed incomplete
  plan-blind-only review;
- `planSlug`: non-empty path-safe output slug;
- `generatedAt`: ISO-8601 timestamp.

## Files, hunks, and ownership

Each file is `{ "path": string, "status": string }`.

Each hunk requires:

- `id`: unique stable ID;
- `file`: path present in `files`;
- `oldStart` and `newStart`: non-negative integers;
- `diff`: bounded unified-diff text;
- `explanation`: behavioral explanation of the change.

Each hunk ID must occur in exactly one intent group's `hunkIds`. Group by
behavior across files. Do not duplicate a hunk to make navigation convenient.

## Intent groups

Each intent group requires:

```json
{
  "id": "request-validation",
  "title": "Request validation",
  "summary": "Validate input before dispatch.",
  "risk": "high",
  "hunkIds": ["hunk-api", "hunk-tests"],
  "findingIds": ["finding-bypass"]
}
```

Allowed risk values, in required descending order:

1. `blocking`
2. `high`
3. `medium`
4. `low`
5. `note`

The group's risk is the highest active risk in that intent. Groups with equal
risk may use a logical reading order.

## Findings

Each finding requires:

```json
{
  "id": "finding-bypass",
  "severity": "high",
  "pass": "plan-blind",
  "intentGroupId": "request-validation",
  "file": "src/api.py",
  "line": 11,
  "title": "Validation can be bypassed",
  "evidence": "Direct callers can invoke dispatch without validation.",
  "impact": "Malformed input can reach the worker.",
  "recommendedAction": "Move validation into the shared dispatch boundary.",
  "status": "open"
}
```

Allowed values:

- `severity`: `blocking`, `high`, `medium`, `low`, `note`;
- `pass`: `plan-blind`, `plan-aware`;
- `status`: `open`, `resolved`, `accepted`.

Severity guidance:

- `blocking`: unsafe to merge or evaluate further; data loss, critical security,
  or unusable build/runtime path;
- `high`: likely user-facing failure, serious regression, security weakness, or
  central plan requirement missing;
- `medium`: concrete defect with bounded impact or meaningful missing coverage;
- `low`: localized maintainability or diagnostics risk with clear evidence;
- `note`: non-blocking observation worth preserving.

Blocking and high findings require non-empty evidence, impact, and recommended
action. Findings of every severity should be actionable and tied to a changed
file line.

## Verification and coverage

Each verification item is:

```json
{
  "name": "Unit tests",
  "status": "passed",
  "details": "12 tests passed."
}
```

Allowed statuses are `passed`, `failed`, `not-run`, and `blocked`. Use
`not-run` when a relevant check was not executed; explain why in `details`.

Coverage requires:

```json
{
  "changedFilesReviewed": ["src/api.py"],
  "intentGroupsReviewed": ["request-validation"],
  "gaps": ["Runtime integration was not available."]
}
```

Use explicit gaps for truncated context, unavailable environments, missing
plans, unexecuted checks, or intentionally excluded changed files.

## Result rules

- `passed`: no unresolved blocking/high/medium findings and required
  verification passed;
- `changes-requested`: one or more actionable findings remain open;
- `blocked`: review could not proceed because essential evidence or execution
  was unavailable;
- `incomplete`: the user confirmed a limited review, such as plan-blind only.

Do not infer `passed` from an empty findings array when coverage is incomplete.

## Compact complete example

```json
{
  "meta": {
    "repository": "sample/repository",
    "base": "main",
    "head": "WORKTREE",
    "plan": "docs/plans/sample.md",
    "planSlug": "sample-change",
    "generatedAt": "2026-07-26T00:00:00Z"
  },
  "summary": {
    "headline": "One issue needs correction",
    "overview": "The implementation is close, but validation is bypassable."
  },
  "verification": [
    {"name": "Unit tests", "status": "passed", "details": "12 passed."}
  ],
  "intentGroups": [
    {
      "id": "validation",
      "title": "Validation",
      "summary": "Validate before dispatch.",
      "risk": "high",
      "hunkIds": ["h1"],
      "findingIds": ["f1"]
    }
  ],
  "files": [{"path": "src/api.py", "status": "M"}],
  "hunks": [
    {
      "id": "h1",
      "file": "src/api.py",
      "oldStart": 10,
      "newStart": 10,
      "diff": "@@ -10 +10 @@\n-dispatch(data)\n+validate(data)",
      "explanation": "Adds request validation."
    }
  ],
  "findings": [
    {
      "id": "f1",
      "severity": "high",
      "pass": "plan-blind",
      "intentGroupId": "validation",
      "file": "src/api.py",
      "line": 10,
      "title": "Validation remains bypassable",
      "evidence": "Direct callers still invoke dispatch.",
      "impact": "Malformed input reaches the worker.",
      "recommendedAction": "Validate at the dispatch boundary.",
      "status": "open"
    }
  ],
  "coverage": {
    "changedFilesReviewed": ["src/api.py"],
    "intentGroupsReviewed": ["validation"],
    "gaps": []
  },
  "result": "changes-requested"
}
```

## Redaction and size limits

The collector redacts likely password, token, API-key, client-secret, and
private-key assignments and reports matched labels. It bounds the diff by UTF-8
bytes while retaining whole lines. Redaction is a safety net, not a guarantee:
inspect the normalized report for secrets and personal data before rendering or
sharing it.
