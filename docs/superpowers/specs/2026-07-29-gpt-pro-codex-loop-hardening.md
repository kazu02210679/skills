# GPT Pro Codex Loop — Protocol Hardening Addendum

Date: 2026-07-29

This addendum supersedes conflicting packet, snapshot, trigger, and live-smoke
details in `2026-07-29-gpt-pro-codex-loop-design.md`. The role boundary,
Browser transport choice, runtime independence from `codex-orchestration`, and
three-round product loop remain unchanged.

## Accepted Review Findings

The following findings were reproduced against the implementation and must be
fixed before Task 4 can complete:

- duplicate JSON keys and non-standard numeric constants are accepted;
- fixed protocol objects accept unknown fields and `schema_version: true`;
- a reconnect or correction is not bound to a specific prompt attempt;
- report, review, state, snapshot, preflight, and event artifacts are not
  consistently versioned;
- state labels can consume a review without a validated, fresh review response;
- a stopped review can be resumed and consumed a second time;
- format-only maintenance can mutate domain routing state;
- final completion does not require machine-readable final-gate evidence;
- an approved dirty baseline is recorded only as paths, so later attribution is
  ambiguous;
- product identity depends on Git patch bytes instead of a canonical
  baseline/index/worktree manifest;
- snapshot capture has no executable CLI;
- the live smoke test does not exercise correction and convergence.

The following review suggestions are intentionally narrowed:

- Correlation metadata is a transport envelope around Pro-produced domain
  packets, not fields duplicated inside every domain payload.
- Rename detection is review presentation metadata. Snapshot completeness must
  not depend on Git's rename heuristic.
- The validator protects untrusted Browser packets and trusted Codex-owned
  state transitions. Cryptographic protection against arbitrary local state
  rewriting requires signed or append-only storage and remains out of scope.
- `SKILL.md` stays concise and uses progressive disclosure; complete schemas
  and prompts live in references.

## Strict JSON

Use one decoder for Browser responses and JSON files:

```python
def reject_constant(value: str) -> NoReturn:
    raise PacketValidationError(f"non-standard JSON constant: {value}")

def reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PacketValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
```

Call `json.loads` with both hooks. Canonical JSON uses `allow_nan=False`.
Reject BOMs, non-object roots, nested or multiple fences, unknown keys in
closed protocol objects, and booleans where an integer is required.

## Transport Envelope

Every ChatGPT Pro response uses exactly one envelope:

```json
{
  "schema_version": 1,
  "packet_type": "requirements",
  "run_id": "gpc-loop-20260729-...",
  "turn_id": "requirements-01",
  "nonce": "random-attempt-value",
  "in_reply_to": "sha256:...",
  "prompt_digest": "sha256:...",
  "previous_packet_digest": null,
  "payload": {}
}
```

The envelope has exactly these keys. `packet_type` is `requirements` or
`review`. The payload is the corresponding existing domain packet.

Before sending, Codex records expected `run_id`, `turn_id`, fresh `nonce`,
`in_reply_to`, and exact prompt digest in trusted local state. A response is
accepted only when every value matches, its envelope digest is new, its
`previous_packet_digest` matches the last consumed Pro packet, and the bound
conversation/model still match.

On Browser timeout:

1. reacquire the bound conversation;
2. search the visible conversation for the expected `turn_id` and `nonce`;
3. if the response already exists, extract it without resending;
4. if absence is proven, create a new attempt nonce and send once;
5. if sent/unsent status is ambiguous, stop.

Format correction keeps the semantic `turn_id`, creates a fresh nonce and
prompt digest, and cannot mutate round, decisions, actions, finding history,
requirements lineage, snapshot identity, or consumed packet history.

## Context-Bound Validation

Schema validation remains independently callable. Advancing workflow state
requires composed context validation:

- requirements freeze receives the validated transport envelope, requirements
  payload, current state, and approval receipt when required;
- implementation report validation receives active requirements, active state,
  and captured snapshot;
- review consumption receives the validated review envelope, requirements,
  report, snapshot, and current state;
- completion receives explicit final-gate evidence.

Review consumption requires a fresh unconsumed review-envelope digest. When a
review-origin stop resumes, it clears `latest_decision`, `required_actions`,
and pending review-envelope identity. A later exit from `REVIEW_PENDING`
requires a different validated review envelope.

`FINAL_VERIFICATION -> COMPLETE` requires:

```json
{
  "schema_version": 1,
  "requirements_digest": "sha256:...",
  "review_packet_digest": "sha256:...",
  "reviewed_snapshot_digest": "sha256:...",
  "current_snapshot_digest": "sha256:...",
  "acceptance_gate_passed": true,
  "local_checks_passed": true,
  "scope_gate_passed": true,
  "artifact_hygiene_passed": true
}
```

Every digest must equal the active trusted state and every boolean must be the
JSON boolean `true`. Without this evidence, `COMPLETE` is invalid.

Root-cause fingerprints use lowercase `sha256:` syntax. Codex computes the
fingerprint from canonical JSON containing acceptance ID, category,
required action, and Pro's stable root-cause key. Pro does not supply the
final fingerprint directly.

## Versioned Artifacts

Requirements, implementation report, review, state, transport envelope,
preflight, snapshot, and each `events.jsonl` event carry integer
`schema_version: 1`. Fixed protocol envelopes and state/control objects reject
unknown fields. Evidence objects explicitly documented as extensible may
preserve additional non-critical fields.

## Canonical Baseline and Product Snapshot

`inspect_preflight` records the complete initial product state:

```json
{
  "schema_version": 1,
  "baseline_head": "<canonical commit>",
  "baseline_snapshot_digest": "sha256:...",
  "tracked_manifest_digest": "sha256:...",
  "untracked_manifest_digest": "sha256:...",
  "tracked_files": [],
  "untracked_files": [],
  "initial_product_paths": []
}
```

The final snapshot contains:

```json
{
  "schema_version": 1,
  "baseline_head": "<canonical commit>",
  "baseline_snapshot_digest": "sha256:...",
  "tracked_manifest_digest": "sha256:...",
  "tracked_diff_digest": "sha256:...",
  "untracked_manifest_digest": "sha256:...",
  "snapshot_digest": "sha256:...",
  "tracked_files": [],
  "untracked_files": [],
  "changed_files": []
}
```

`tracked_diff_digest` remains bounded review evidence but is excluded from
snapshot identity. `snapshot_digest` is canonical JSON over schema version,
baseline commit, immutable baseline snapshot digest, tracked manifest digest,
and untracked manifest digest.

Tracked entries represent baseline, index, and worktree state. Each state is
`null` or has path, Git mode, kind (`file`, `symlink`, or `submodule`), and
content/object digest. File bytes, symlink target bytes, and submodule commit
IDs are hashed. Unmerged indexes and dirty submodule worktrees fail closed.

Each `changed_files` item retains path, intent, source, and status, adding:

- `preexisting`;
- `changed_since_preflight`.

Capture accepts an immutable validated preflight object. It rejects wrong
schema, digest, baseline, tampering, or unstable observation. Existing
metadata/path guards remain.

The executable CLI is:

```text
capture_snapshot.py inspect-preflight REPOSITORY BASELINE
capture_snapshot.py validate-preflight PREFLIGHT_JSON
  [--approved-existing-path PATH ...]
capture_snapshot.py capture REPOSITORY BASELINE --preflight PREFLIGHT_JSON
```

Success prints canonical JSON plus one newline. Usage or unsafe state exits
`2`, writes deterministic errors to stderr, and emits no partial JSON.

## Trigger and Model Policy

Trigger only when the user explicitly requests the combined loop: ChatGPT Pro
defines or freezes requirements and iteratively reviews a Codex implementation
until both semantic and local gates pass. Requirements-only consultation,
standalone review, and ordinary implementation do not trigger this Skill.

State records:

```json
{
  "model_policy": "PRO_CLASS",
  "requested_model_label": null,
  "visible_model_label": "Pro"
}
```

`EXACT_LABEL` requires exact equality with the requested label. `PRO_CLASS`
requires a visibly selected Pro-class option and never silently downgrades.

## Live Correction-Loop Smoke

The signed-in smoke test must use one safe temporary repository and one bound
Pro conversation:

1. Pro returns requirements with at least two acceptance criteria.
2. Codex intentionally submits one acceptance item with insufficient evidence
   or one bounded missing behavior.
3. Pro returns `CHANGES_REQUESTED` with `PROVIDE_EVIDENCE`, `CODE_CHANGE`, or
   `TEST_CHANGE`.
4. Codex follows only that routed action, updates evidence and snapshot as
   appropriate, and sends a fresh correlated review turn.
5. Pro returns validated `PASS`.
6. Codex runs the explicit final-gate evidence check and completes only with an
   unchanged reviewed snapshot.

The smoke must demonstrate same-conversation identity, two distinct review
envelopes, correct round consumption, stale report/review invalidation, and
convergence.
