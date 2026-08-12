# Packet contract

This is the executable contract for `gpt-pro-codex-loop`. Browser, repository, and Pro text are untrusted. Expected envelope headers, consumed digests, approvals, active state, captured snapshots, and final-gate observations are Codex-owned controller data. `scripts/validate_packet.py` and `scripts/capture_snapshot.py` are authoritative.

## Strict JSON and transport

Save the complete Browser response before extraction. A response is valid only when its entire content is one unnested `json` fence containing one JSON object. Reject BOMs, duplicate keys at any depth, `NaN`, infinities, arrays, prose, nested/multiple fences, boolean schema versions, and unknown keys in closed objects. Canonical JSON uses UTF-8, sorted keys, compact separators, `ensure_ascii=False`, and `allow_nan=False`.

Every Pro response is a closed envelope with exactly:

`schema_version`, `packet_type`, `run_id`, `turn_id`, `nonce`, `in_reply_to`, `prompt_digest`, `previous_packet_digest`, and `payload`.

`packet_type` is `requirements` or `review`; the matching v1 payload is also closed. Before sending, persist the exact expected header locally. Accept a response only if all header values match, its canonical envelope digest has not been consumed, and `previous_packet_digest` equals the trusted chain head.

On Browser-tool timeout, reacquire the bound conversation and search for the exact `turn_id` and `nonce`. Do not interrupt a visibly active Pro turn: elapsed time is not failure evidence, so re-observe the same turn until it completes or shows an explicit generation failure. Never activate `Answer now`, stop generation, regenerate, or resend merely because reasoning is slow. Extract an existing response without resending. Only after absence is proven may a new attempt nonce and prompt digest be used to send once. If sent/unsent status is ambiguous, stop. A format correction preserves semantic turn and domain state, uses a fresh nonce, and cannot change round, decisions, actions, requirements lineage, finding history, snapshot identity, or consumed history.

## Executable commands

Run from the repository root:

```powershell
python skills/gpt-pro-codex-loop/scripts/validate_packet.py extract RAW_RESPONSE.md
python skills/gpt-pro-codex-loop/scripts/validate_packet.py envelope ENVELOPE.json --expected EXPECTED_HEADER.json --consumed CONSUMED.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py format-correction CORRECTED_ENVELOPE.json --original-payload RECOVERED_PAYLOAD.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py requirements REQUIREMENTS.json --previous PREVIOUS_REQUIREMENTS.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py report-context REPORT.json --requirements REQUIREMENTS.json --state STATE.json --snapshot SNAPSHOT.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py review-context REVIEW_ENVELOPE.json --requirements REQUIREMENTS.json --report REPORT.json --state STATE.json --snapshot SNAPSHOT.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py transition PREVIOUS_STATE.json CURRENT_STATE.json --requirements-preparation-context REQUIREMENTS_PREPARATION_CONTEXT.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py transition PREVIOUS_STATE.json CURRENT_STATE.json --requirements-context REQUIREMENTS_CONTEXT.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py transition PREVIOUS_STATE.json CURRENT_STATE.json --review-context REVIEW_CONTEXT.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py transition PREVIOUS_STATE.json CURRENT_STATE.json --final-gate FINAL_GATE.json --final-report REPORT.json --final-requirements REQUIREMENTS.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py final-gate FINAL_GATE.json --state STATE.json --report REPORT.json --requirements REQUIREMENTS.json
python skills/gpt-pro-codex-loop/scripts/capture_snapshot.py inspect-preflight REPOSITORY BASELINE
python skills/gpt-pro-codex-loop/scripts/capture_snapshot.py validate-preflight PREFLIGHT.json --repository REPOSITORY --approved-existing-path PATH
python skills/gpt-pro-codex-loop/scripts/capture_snapshot.py capture REPOSITORY BASELINE --preflight PREFLIGHT.json
```

`CONSUMED.json` is the ephemeral controller input `{"consumed_digests":[]}`. Transition contexts are ephemeral closed controller inputs:

```text
REQUIREMENTS_CONTEXT.json:
  envelope, expected, consumed_digests, requirements, approval_receipt

REVIEW_CONTEXT.json:
  envelope, expected, consumed_digests, requirements, report, snapshot
```

`expected` contains the eight envelope header fields without `payload`; `consumed_digests` is an array of lowercase SHA-256 strings; `approval_receipt` is the trusted digest-bound receipt or `null`. A successful command exits `0` and prints canonical JSON plus one newline.

`review-context` validates and prints the envelope; that output is **not** a `REVIEW_CONTEXT.json` transition input. The controller constructs the composed context from the same validated envelope, trusted expected header and consumed set, active requirements/report, and captured snapshot, then passes that closed object to `transition`.

`requirements-preparation-context` is a closed, controller-built local authorization for changing the pending requirements expected-header anchor. It contains exactly the new expected header and either `null` for the first attempt or the complete matching `ABANDONED_NOT_SENT` receipt for the previous anchor. A same-phase anchor replacement or clear without that proof fails closed.

## Controller CLI

The normal-loop entry point is `python skills/gpt-pro-codex-loop/scripts/gpc_loop.py COMMAND`. Every command accepts `--repo REPOSITORY --task TASK`. Initialization has two commands:

```text
inspect-init  [--write-approval-manifest FILE]
init          --request FILE --repository-context FILE --model-policy PRO_CLASS|EXACT_LABEL
              [--requested-model-label LABEL] [--retry-incomplete]
              [--approved-existing-path PATH ... | --approved-existing-path-manifest FILE]
```

`inspect-init` is read-only with respect to run-owned state. It returns a path count, canonical set digest, at most 20 preview paths, omitted count, and the resolved output path or `null`. Only an explicit `--write-approval-manifest` atomically writes a candidate manifest; its parent must already exist. Keep that file outside the inspected repository so it does not change the product-path set. Generation does not constitute approval.

The closed manifest schema is:

```json
{
  "schema_version": 1,
  "repository": "CANONICAL-ABSOLUTE-REPOSITORY",
  "task": "TASK-SLUG",
  "baseline_head": "40-HEX-GIT-OID",
  "initial_product_paths": ["canonical/repository-relative/path"],
  "path_count": 1,
  "path_set_digest": "sha256:..."
}
```

Passing the manifest to `init` explicitly approves exactly its complete sorted unique path list. Init re-inspects under the initialization lock and rejects missing, extra, stale, malformed, non-canonical, absolute, traversal, duplicate, repository-mismatched, or task-mismatched entries before publishing `state.json`. The manifest option and repeated `--approved-existing-path` are mutually exclusive; repeated per-path approval remains supported unchanged. `--retry-incomplete` does not weaken any approval or preflight check.

The remaining command-specific inputs are:

```text
prepare-requirements  [--conflict-evidence FILE]
accept-requirements   --raw-response FILE --observed-conversation-url URL --observed-model-label LABEL
                      [--observed-reasoning-label LABEL] [--observed-plan-label LABEL]
approve-requirements  --approval-evidence FILE
build-report          --local-evidence FILE
prepare-review        [--supplemental-evidence FILE]
accept-review         --raw-response FILE --observed-conversation-url URL --observed-model-label LABEL
                      [--observed-reasoning-label LABEL] [--observed-plan-label LABEL]
final-verify
status
abandon-attempt       --send-status NOT_SENT --not-sent-evidence FILE
```

`--local-evidence` is one strict UTF-8 JSON object with exactly this shape (no unknown fields):

```json
{
  "schema_version": 1,
  "changed_file_intents": {"example.py": "Implement AC-1."},
  "intent_summary": "Implement and verify AC-1.",
  "acceptance_evidence": {"AC-1": ["Focused test passed."]},
  "test_commands": [{"command": "python -m unittest test_example.py -v", "outcome": "PASS", "output_summary": "1 test passed."}],
  "diff_evidence": ["example.py implements AC-1."],
  "omissions": [],
  "unresolved_risks_or_blockers": []
}
```

`schema_version` is integer `1`. `changed_file_intents` is an object of non-empty changed-path keys and non-empty intent strings; its keys must equal the captured product snapshot's changed-path set exactly. `intent_summary` is a non-empty string. `acceptance_evidence` must have exactly every active acceptance ID as keys and each value is a non-empty list of non-empty strings. `diff_evidence`, `omissions`, and `unresolved_risks_or_blockers` are lists of non-empty strings. Every `test_commands` item has exactly non-empty string `command`, `outcome`, and `output_summary` fields; the controller records commands without executing them. A report may record a non-`PASS` outcome, but final verification requires at least one command and every outcome to be `PASS`, with empty omissions and unresolved blockers.

`--request` and `--repository-context` are UTF-8 text inputs read with universal-newline handling: CRLF and bare CR become LF before persistence. No trailing newline is added or removed; any trailing newline sequence is preserved after that line-ending normalization. `--conflict-evidence`, `--supplemental-evidence`, and `--approval-evidence` are readable, non-empty UTF-8 text files. `--not-sent-evidence` is readable, non-empty UTF-8 text normalized to LF and stored up to 8192 UTF-8 bytes; it is valid only with literal `--send-status NOT_SENT`. `accept-*` always receives the complete raw response plus the URL and model label observed in the Browser at acceptance time.

Each non-help invocation prints exactly one canonical UTF-8 JSON object and one LF: success is `{"ok":true,"command":"COMMAND","result":RESULT}`; a stable controller failure is `{"ok":false,"command":"COMMAND","error":{"code":"CODE","message":"MESSAGE","details":[]}}`. Success exits `0`, an expected controller failure exits `2`, and an unexpected failure returns `INTERNAL_ERROR` with exit `1`; `--debug` sends its traceback only to stderr. New expected failures use `PREFLIGHT_APPROVAL_REQUIRED`, `APPROVAL_MANIFEST_INVALID`, `APPROVAL_SOURCE_CONFLICT`, `INIT_INCOMPLETE`, `INIT_RECOVERY_REQUIRED`, or `INIT_RECOVERY_REFUSED`; lock contention remains `RUN_LOCKED`. CLI mutual-exclusion errors remain `ARGUMENT_ERROR`. These all use exit `2` and preserve the envelope shape.

Large approval failures are bounded independently of repository size. `details` contains `initial_product_path_count`, `path_set_digest`, no more than 20 `path_preview` entries, `omitted_path_count`, and `generate_manifest_argv` / `retry_init_argv` JSON arrays. The suggested manifest path is outside the repository, and the argv records the actual request, context, model, repository, and task values so executing the generation argv and then the retry argv is sufficient when the inspected set remains unchanged.

Use `status` before every controller mutation after `init` and follow only its `next_commands`. The controller writes artifacts and validates candidates before replacing `state.json` last. Its consumed-envelope set comes only from trusted chain-head fields in `state.json`, never from scanning artifact history. It derives and validates every prompt/header digest, state transition, snapshot/report binding, and final gate; never hand-author those artifacts. `abandon-attempt` atomically replaces only the outstanding expected attempt with a `NOT_SENT` receipt and preserves `state.json` and all domain artifacts unchanged.

## Recovery

`status` never repairs or removes files. True absence returns `RUN_NOT_FOUND`. A no-state run that matches the versioned controller marker or the documented legacy-minimal allowlist, contains only allowed pre-state files, has no link/reparse-point escape, and has no live lock is reported as `phase: INIT_INCOMPLETE` with `next_commands: ["init --retry-incomplete"]`. Retry must repeat all normal input, model, and approval arguments. It acquires the initialization lock, removes only the reclassified allowlisted scaffolding, and runs a fresh normal initialization. A live lock returns `RUN_LOCKED` without mutation.

Any `state.json` (including malformed state), unexpected or foreign artifact, ambiguous ownership, malformed lock, link/reparse point, or established-run evidence makes retry return `INIT_RECOVERY_REFUSED` without mutation. A no-state ambiguous run is `INIT_RECOVERY_REQUIRED`. An existing transaction on an established run remains a manual recovery boundary: `status` returns `recovery_required: true`, reports exact transaction paths and unreachable artifacts, and returns an empty `next_commands`; normal mutations return `RECOVERY_REQUIRED`. Preserve `state.json`, the complete transaction directory, its manifest/staged files/backups, and all run artifacts byte-for-byte. Do not delete, rename, restore, publish, or otherwise repair them through the normal controller. Escalate to the user before any resolution.

The shared transport `schema_version` remains 1. Model attestation is independently versioned by `model_attestation_schema_version=3`; v3 makes `GPT-5.6 Pro` the sole `PRO_CLASS` model. A completely conversation-unbound state with URL, model, reasoning, and plan all null may normalize to version 3 in memory and persist that upgrade during the next ordinary state transition. This includes a coherent v2 (all four identity fields explicitly null) and an older fieldless unbound legacy state. A bound v2, partial v2, bound legacy, or otherwise partial/unsupported attestation returns `LEGACY_STATE_RESTART_REQUIRED`; `status` is read-only, sets `recovery_required: true`, exposes no next command, and directs the user to preserve the run and restart with a new task slug. Receipt export applies the same classification for requirements, review, and final receipts without writing any run bytes. No model, reasoning, or plan value may be inferred from the old `visible_model_label`.

Re-run the exact read-only status command as needed:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py status --repo REPOSITORY --task TASK
```

For manual validation, copy the relevant states and closed context to separately preserved diagnostic inputs, then run the matching command without altering the run:

```powershell
python skills/gpt-pro-codex-loop/scripts/validate_packet.py transition PREVIOUS_STATE.json CURRENT_STATE.json --requirements-context REQUIREMENTS_CONTEXT.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py transition PREVIOUS_STATE.json CURRENT_STATE.json --review-context REVIEW_CONTEXT.json
python skills/gpt-pro-codex-loop/scripts/validate_packet.py envelope ENVELOPE.json --expected EXPECTED_HEADER.json --consumed CONSUMED.json
```

The validator only reports validity; it does not select, publish, clean, or repair a transaction. No mutation may resume until the transaction is resolved outside the normal controller path under explicit user direction. Version 1 intentionally provides no recovery or destructive-cleanup command and never silently repairs an interrupted transaction.

## Complete requirements envelope

```json
{
  "schema_version": 1,
  "packet_type": "requirements",
  "run_id": "gpc-loop-example",
  "turn_id": "requirements-01",
  "nonce": "attempt-01",
  "in_reply_to": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  "prompt_digest": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
  "previous_packet_digest": null,
  "payload": {
    "schema_version": 1,
    "requirements_revision": 1,
    "supersedes_digest": null,
    "change_reason": "Initial requirements from the user request.",
    "behavior_changed": false,
    "user_approval_required": false,
    "user_approval_received": false,
    "scope_changed": false,
    "public_contract_changed": false,
    "prior_evidence_invalidated": false,
    "review_round_reset": false,
    "decision": "PLAN_READY",
    "objective": "Add deterministic validation for one JSON response packet.",
    "requirements": [
      {"id": "REQ-1", "statement": "Reject responses that are not exactly one fenced JSON object."}
    ],
    "in_scope": ["Response extraction", "Packet validation"],
    "out_of_scope": ["Browser selector implementation", "Deployment"],
    "constraints": ["Use the Python standard library"],
    "acceptance_criteria": [
      {"id": "AC-1", "criterion": "Zero or multiple JSON fences are rejected.", "required_evidence": "Focused automated test output"}
    ],
    "design_direction": ["Fail closed on ambiguous transport"],
    "risk_items": [
      {"id": "RISK-1", "risk": "A truncated Browser response could look complete.", "required_mitigation": "Persist the raw response and require complete JSON parsing."}
    ],
    "verification_strategy": ["Run the focused packet-validator tests"],
    "open_questions": []
  }
}
```

Only `PLAN_READY` with no material open question advances automatically. A revision increments by one and supersedes the exact prior payload digest. An unapproved material proposal returns `NEED_USER_INPUT`; the controller preserves its revision, digest, supersedes digest, and material flags in `USER_DECISION_REQUIRED`. Approval uses the exact receipt `user-approval:stop-<stop_sequence>:<pending_requirements_digest>` and promotes that stored proposal directly to `REQUIREMENTS_FROZEN`. It must not request a rewritten packet from Pro after approval. Material behavior, scope, or public-contract changes invalidate prior evidence and reset review accounting.

## Implementation report

The closed report object requires:

- integer `schema_version: 1`;
- `baseline_head`, active requirements revision/digest, and current review round;
- `snapshot_digest`, `tracked_diff_digest`, and `untracked_manifest_digest` from the same capture;
- changed-file manifest and intent summary;
- evidence for every acceptance ID;
- test commands with outcomes and bounded summaries;
- diff evidence, explicit omissions, and unresolved risks/blockers.

Each `acceptance_evidence` value is a non-empty list of non-empty strings.
Nested objects and arbitrary credential/session-shaped evidence are rejected;
perform disclosure review before putting any string into the report.

Report validation must use `report-context`; the context-free `report` command is diagnostic only. Context binds the report to active approved requirements, trusted round/report digest, and exact captured snapshot.

Complete report matching the examples in this reference:

```json
{
  "schema_version": 1,
  "baseline_head": "1111111111111111111111111111111111111111",
  "requirements_revision": 1,
  "requirements_digest": "sha256:93b668942c44346dda2d59fa8b77b83093f035de6f2f0d6dcdff536ec6232944",
  "review_round": 0,
  "snapshot_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "tracked_diff_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "untracked_manifest_digest": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "changed_files": [{"path": "validator.py", "intent": "Validate exactly one fenced JSON object."}],
  "intent_summary": "Implemented fail-closed response extraction and validation.",
  "acceptance_evidence": {"AC-1": ["Focused rejection tests passed."]},
  "test_commands": [{"command": "python test_validator.py -v", "outcome": "PASS", "output_summary": "2 tests passed."}],
  "diff_evidence": ["validator.py rejects ambiguous transport."],
  "omissions": [],
  "unresolved_risks_or_blockers": []
}
```

## Review findings and locally derived fingerprint

A v1 Pro finding is closed and requires `id`, `acceptance_id`, `root_cause_key`, `severity`, `category`, `required_action`, and `evidence`. `category` is exactly one of `CORRECTNESS`, `TEST_COVERAGE`, `INSUFFICIENT_EVIDENCE`, `SCOPE`, `REQUIREMENTS`, `SAFETY`, or `OTHER`. `acceptance_id` must name an active criterion.

Action payloads are structural:

- `CODE_CHANGE` and `TEST_CHANGE` require one non-empty `required_change` string and forbid `required_evidence`.
- `PROVIDE_EVIDENCE` requires one non-empty `required_evidence` string and forbids `required_change`.
- `REQUIREMENTS_REVISION` and `USER_DECISION` forbid both action-detail fields.

Pro supplies only these stable source fields. Codex computes:

```python
canonical_digest({
    "acceptance_id": finding["acceptance_id"],
    "category": finding["category"],
    "required_action": finding["required_action"],
    "root_cause_key": finding["root_cause_key"],
})
```

The Pro payload must not contain `root_cause_fingerprint`. After validation, Codex stores the locally derived lowercase SHA-256 value in trusted finding history. It also derives a conservative continuity key from `acceptance_id`, `category`, and `required_action`; changing only Pro-controlled finding ID or root-cause key cannot evade the two-round stop. A model-selected digest is an unknown field and is rejected.

## Complete review envelope

This PASS example refers to the requirements payload above and a report whose snapshot digest is the shown value.

```json
{
  "schema_version": 1,
  "packet_type": "review",
  "run_id": "gpc-loop-example",
  "turn_id": "review-01",
  "nonce": "attempt-02",
  "in_reply_to": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
  "prompt_digest": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
  "previous_packet_digest": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
  "payload": {
    "schema_version": 1,
    "requirements_digest": "sha256:93b668942c44346dda2d59fa8b77b83093f035de6f2f0d6dcdff536ec6232944",
    "reviewed_snapshot_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "decision": "PASS",
    "acceptance_results": {
      "AC-1": {"status": "PASS", "evidence": "Codex reported both focused rejection tests passing."}
    },
    "findings": [],
    "scope_violations": [],
    "next_instruction": "Run the explicit final local gate against the unchanged snapshot."
  }
}
```

The visible model label is a UI attestation used to detect an obvious silent downgrade. It is not a cryptographic proof of the underlying model identity and may require a contract update when ChatGPT UI labels or localization change.

`PASS` is invalid unless every acceptance item is present and `PASS`, findings and scope violations are empty, evidence is sufficient, and both digests match. `PROVIDE_EVIDENCE` never authorizes product changes.

## Canonical preflight and snapshot

`inspect-preflight` records a versioned immutable baseline with `baseline_head`, `baseline_snapshot_digest`, tracked/untracked manifest digests, complete tracked/untracked entries, and initial product paths. Every captured snapshot also carries the canonical `preflight_digest` and the unchanged `initial_product_paths`; report context binds those values to trusted state and the exact user-approved path set. Capture rejects a tampered or wrong-baseline preflight, unmerged index, dirty submodule, unstable observation, unsafe path, or tracked/staged run metadata.

Tracked entries record baseline, index, and worktree state including Git mode, kind, and content/object digest. Snapshot identity is canonical JSON over:

`schema_version`, `baseline_head`, `baseline_snapshot_digest`, `tracked_manifest_digest`, and `untracked_manifest_digest`.

`tracked_diff_digest` is bounded review evidence only and is excluded from identity. Each changed-file item records `preexisting` and `changed_since_preflight`.

## Artifacts

Persisted requirements, report, review, state, envelope, preflight, snapshot, and final-gate artifacts carry integer `schema_version: 1`. `events.jsonl` is an append-only diagnostic transition log and is not consumed as protocol authority. Ephemeral CLI wrapper inputs such as `CONSUMED.json` and transition contexts are closed controller inputs rather than persisted protocol artifacts.

```text
<repo>/.ai-pro-loop/<task-slug>/
├── initialization.json
├── request.md
├── repository-context.md
├── preflight.json
├── expected-attempt-NN.json
├── envelope-NN.json
├── requirements.json
├── requirements-rev-NN.json
├── implementation-report-NN.json
├── snapshot-NN.json
├── review-NN.json
├── final-gate.json
├── state.json
├── events.jsonl
├── prompts/
└── responses/
```

Never store credentials, tokens, cookies, or Browser session state. Never stage, publish, or include this directory in product evidence.

## State and final gate

Fixed state/control objects are closed. State records phase, round, binding/model policy, immutable baseline HEAD, preflight digest, exact user-approved pre-existing paths, active and pending requirements lineage, approval provenance, envelope receipts/chain head, active report/review/snapshot digests, routed actions, derived finding history, stop provenance, and maintenance counters. A valid review consumes exactly one round. Reconnect, first format correction, and evidence preparation do not; the next Pro decision does.

Complete staged `REVIEW_PENDING` state for the PASS review example:

```json
{
  "schema_version": 1,
  "phase": "REVIEW_PENDING",
  "review_round": 0,
  "latest_decision": "PASS",
  "latest_requirements_decision": null,
  "required_actions": [],
  "unresolved_finding_ids": [],
  "blocker_fingerprints": [],
  "format_error_count": 0,
  "browser_reconnect_count": 0,
  "conversation_binding_state": "CONVERSATION_BOUND",
  "bound_conversation_url": "https://chatgpt.com/c/example-conversation",
  "model_policy": "PRO_CLASS",
  "requested_model_label": null,
  "visible_model_label": "GPT-5.6 Pro",
  "visible_reasoning_label": "Pro",
  "visible_plan_label": "Pro",
  "model_attestation_schema_version": 3,
  "active_requirements_revision": 1,
  "active_requirements_digest": "sha256:93b668942c44346dda2d59fa8b77b83093f035de6f2f0d6dcdff536ec6232944",
  "approval_sequence": 0,
  "pending_requirements_revision": null,
  "pending_requirements_digest": null,
  "pending_supersedes_digest": null,
  "pending_approval_sequence": null,
  "pending_approved_requirements_digest": null,
  "pending_user_approval_evidence": null,
  "behavior_changed": false,
  "user_approval_required": false,
  "scope_changed": false,
  "public_contract_changed": false,
  "prior_evidence_invalidated": false,
  "review_round_reset": false,
  "user_approval_received": false,
  "stop_origin_phase": null,
  "stop_origin_category": null,
  "stop_reason": null,
  "stop_sequence": 0,
  "resolution_evidence": null,
  "resolution_stop_sequence": null,
  "pending_requirements_envelope_digest": null,
  "pending_requirements_expected_header_digest": null,
  "pending_review_envelope_digest": "sha256:3a63ffc1078e3eb2ca79474c0f63a79c203ebf00cef62e6b259e030d3afb5bb2",
  "pending_review_expected_header_digest": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "last_consumed_packet_digest": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
  "last_consumed_review_envelope_digest": null,
  "active_report_digest": "sha256:4198d50d6002e2ac6819ba5f7398d4df12e457a9ee58f0d7d50538cc32a93204",
  "current_snapshot_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "active_review_packet_digest": "sha256:b873cdabd3063d440545ce8ca76a55442f488c1b4c9a692009ba8c99e5582f9a",
  "reviewed_snapshot_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "baseline_head": "1111111111111111111111111111111111111111",
  "preflight_digest": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
  "nonce_derivation_key": "0000000000000000000000000000000000000000000000000000000000000000",
  "approved_existing_paths": []
}
```

`nonce_derivation_key` is immutable, local-only preparation provenance. The controller derives each exact attempt nonce from it and the trusted run, packet, semantic-turn, and attempt identities; acceptance recomputes that nonce instead of trusting the mutable expected-attempt file.

After envelope and report checks pass, the controller constructs this complete state as an ephemeral candidate using the validated review payload, pending envelope digest, routed actions, and locally derived history. Run `review-context` against that candidate. Only after it passes may the controller atomically replace persisted `state.json`; never mutate persisted trusted state before candidate validation. `REVIEW_PENDING -> FINAL_VERIFICATION` then consumes the pending envelope: increment round, move its digest to both consumed fields, clear pending identity, and preserve active report/review/snapshot digests. Other routes populate their candidate actions and derived history before validation and the corresponding edge. Never hand-author or persist a partial state.

Build the composed review context deterministically from already validated artifacts:

```python
review_context = {
    "envelope": load_strict("review-envelope.json"),
    "expected": load_strict("expected-header.json"),
    "consumed_digests": load_strict("consumed.json")["consumed_digests"],
    "requirements": load_strict("requirements.json"),
    "report": load_strict("implementation-report-01.json"),
    "snapshot": load_strict("snapshot-01.json"),
}
```

The requirements context uses the same first three fields plus `requirements` and `approval_receipt`. These are controller-built transition inputs, not Pro output. When a material proposal needs approval, its pending identity and flags survive the requirements stop unchanged. A valid digest-bound receipt resumes directly to `REQUIREMENTS_FROZEN`, promotes exactly the pending revision/digest, consumes pending provenance, increments `approval_sequence`, and resets the review round. The frozen artifact retains its original `NEED_USER_INPUT`/`user_approval_received=false` model fields; report-context recognizes it only when the trusted active digest and consumed controller approval sequence match. Any different digest or free-form receipt fails closed.

Review-origin resume clears decision, actions, and pending review identity. A later review route requires a fresh validated envelope. The same finding ID or derived fingerprint across two consecutive valid review consumptions stops the loop.

Completion requires this closed object:

```json
{
  "schema_version": 1,
  "requirements_digest": "sha256:93b668942c44346dda2d59fa8b77b83093f035de6f2f0d6dcdff536ec6232944",
  "review_packet_digest": "sha256:6666666666666666666666666666666666666666666666666666666666666666",
  "reviewed_snapshot_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "current_snapshot_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "acceptance_gate_passed": true,
  "local_checks_passed": true,
  "scope_gate_passed": true,
  "artifact_hygiene_passed": true
}
```

Every digest must match trusted active state and every boolean must be JSON `true`. The final gate revalidates the exact active requirements packet and the full report schema, then requires the report canonical digest to equal `state.active_report_digest`; every `test_commands[].outcome` must be `PASS`, `omissions` and `unresolved_risks_or_blockers` must be empty, and the report requirements/snapshot digests must match the gate. A `FINAL_VERIFICATION_BLOCK` stop preserves all reviewed report, snapshot, review, and consumption bindings when entering the stop or resuming directly to final verification. Product drift or a changed report invalidates Pro `PASS`, requires a new report/snapshot, and returns to fresh review.
