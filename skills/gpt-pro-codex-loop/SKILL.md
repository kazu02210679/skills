---
name: gpt-pro-codex-loop
description: Use when the user explicitly asks Codex Desktop to use ChatGPT Pro through the Browser to define or freeze requirements and perform one final semantic review of a Codex implementation until both semantic and local verification gates pass.
---

# GPT Pro Codex Loop

ChatGPT Pro owns product requirements, acceptance criteria, and semantic review. Codex owns repository investigation, detailed design, implementation, tests, snapshots, and every local verification claim.

**REQUIRED SUB-SKILL:** Use `browser:control-in-app-browser`.

## Pro usage policy

New runs default to `--review-policy FINAL_ONLY`: use Pro once to define and
freeze requirements, then once for the final semantic review after Codex has
implemented and locally verified the change. A non-passing final review is a
bounded stop; the controller does not automatically send another Pro review.

Use `--review-policy ITERATIVE` only when the user explicitly accepts repeated
Pro review usage. Routine diff review and local verification remain Codex-owned
in standalone mode. In the explicit composition mode, Sol may provide one
bounded read-only routine review before the final Pro review; Sol cannot replace
the final Pro gate or decide completion.

## Standalone scope and local-evidence economy

Standalone use owns only the outer GPT Pro protocol. It does not select or
invoke Luna, Terra, Sol, or a native worker role. Combined routing belongs to
`orchestrate-gpt-pro-sol-advisor`; do not infer combined mode from an
installation or a casual mention of another model.

Codex still owns repository work, tests, snapshots, and every local
verification claim. Keep verification economical: every added test maps to an
acceptance criterion, material risk, or bug root cause; `new_test_files = 0`
is the default; one regression witness per root cause is the default; and
prefer observable contracts and table-driven witnesses over implementation
details or speculative coverage. Use L0 diff/static inspection, L1 affected
focused tests by default, L2 for shared/API/dependency changes, and L3 only
for dependency, build-system, schema, shared-core, or release-critical work.

The controller's `--local-evidence` input is a closed schema. Keep exactly
these top-level fields and do not add metrics as sibling fields:

```json
{
  "schema_version": 1,
  "changed_file_intents": {"example.py": "Implement AC-1."},
  "intent_summary": "Implement and verify AC-1.",
  "acceptance_evidence": {"AC-1": ["Focused test passed."]},
  "test_commands": [{
    "command": "python -m unittest test_example.py -v",
    "outcome": "PASS",
    "output_summary": "exit=0; tests=1; duration=0.2s; summary=focused test passed; verify_input=sha256:...; test_delta=files:0,cases:1,anchors:AC-1"
  }],
  "diff_evidence": ["example.py implements AC-1."],
  "omissions": [],
  "unresolved_risks_or_blockers": []
}
```

Encode bounded success metrics, test-delta anchors, and the verification-input
fingerprint inside `output_summary`; never add `exit_code`, `test_count`,
`duration`, `summary`, `test_delta`, or `fingerprint` fields to the object.
On failure, keep only the command, exit code, failed names, relevant excerpt,
and full-log path plus digest. Do not rerun an unchanged successful command:
the skip key is the command plus the base/tree, relevant-file, lock/config,
and material environment fingerprint—not the command string alone.

For the normal controller loop, do not load
[references/prompt-contract.md](references/prompt-contract.md) or
[references/packet-contract.md](references/packet-contract.md) into model
context. Use only prompts, expected headers, status, and commands emitted by the
controller. Read `prompt-contract.md` only when modifying or diagnosing prompt
generation. Read `packet-contract.md` only for controller maintenance,
validation diagnostics, or the documented recovery path below.

## Workflow

Use `scripts/gpc_loop.py` for the normal loop. Run `status` before each mutation and execute only a command it lists. Use `validate_packet.py` and `capture_snapshot.py` directly only for documented diagnostic or recovery paths.

`init` is the sole exception to the status-first rule because the run does not exist yet. Do the repository investigation and disclosure review outside the controller, then inspect the exact pre-existing product-path set without creating run state. Write the candidate manifest outside the repository so the manifest does not change the set it describes:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py inspect-init --repo REPOSITORY --task TASK --write-approval-manifest ..\REPOSITORY-TASK-approved-existing-paths.json
```

Review the complete manifest and obtain explicit user approval. Manifest generation is inspection, not approval. Then write the bounded request and repository-context inputs and initialize with the exact approved manifest:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py init --repo REPOSITORY --task TASK --request REQUEST.md --repository-context CONTEXT.md --model-policy PRO_CLASS --review-policy FINAL_ONLY --approved-existing-path-manifest ..\REPOSITORY-TASK-approved-existing-paths.json
```

For a small set, repeat `--approved-existing-path PATH` instead. Never combine per-path approval with `--approved-existing-path-manifest`. Init re-inspects under its lock, so a stale, changed, mismatched, malformed, or non-canonical manifest fails before state publication. `PREFLIGHT_APPROVAL_REQUIRED` and manifest errors return at most 20 preview paths plus total/omitted counts, the set digest, and JSON argv for generating a fresh manifest and retrying.

After `init`, before every state-changing command, run:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py status --repo REPOSITORY --task TASK
```

The `next_commands` result is authoritative. Do not hand-author state, expected headers, envelopes, prompt digests, consumed history, snapshots, reports, final gates, or approval receipts. If the controller returns an error, stop: do not retry a different transition or alter controller artifacts by hand.

Browser waiting is quality-first. While the expected Pro turn is visibly reasoning or generating without an explicit error, wait for that same turn to finish; elapsed time alone is not failure evidence. Never activate `Answer now` / `今すぐ回答`, stop generation, regenerate, resend, or switch model merely because the turn is slow. A Browser-tool timeout means re-observe the same conversation and turn, not interrupt it. `Answer now` is allowed only when the current user directly and explicitly prioritizes speed over reasoning depth for that turn; permission makes the action optional, not required. Deadlines, elapsed time, stakeholder requests, and agent judgment are not permission. An explicit generation error, a lost conversation that cannot be reacquired, or an ambiguous send state follows the recovery and hard-stop rules below.

1. When status permits `prepare-requirements`, run it (with `--conflict-evidence FILE` only for a requirements revision). It returns the prompt and expected-header paths. Browser work remains outside the controller: create or reacquire the appropriate conversation, visibly verify the required model state and conversation identity, send the prepared prompt once, and save the complete raw response. For `PRO_CLASS`, verify all three independent UI facts: the plan is Pro-capable (`Pro`, `Business`, or `Enterprise`), the model family is exactly `GPT-5.6 Sol`, and the reasoning level is exactly `Pro`. `Extra High` / `Very High` / `非常に高い` is not Pro reasoning and must fail closed.
2. Run status again. When it permits `accept-requirements`, pass `--raw-response FILE --observed-conversation-url URL --observed-model-label LABEL --observed-reasoning-label LABEL --observed-plan-label LABEL`. Record the three values visibly observed in the Browser on every accepted response; do not infer them from prior state. Under `PRO_CLASS`, the controller requires `GPT-5.6 Sol`, `Pro`, and a Pro-capable plan respectively.
3. When status permits `approve-requirements`, obtain the user's authorization outside the controller, record bounded local evidence, then use `--approval-evidence FILE`. When it permits `build-report`, complete product work and local commands outside the controller, create the closed local-evidence input, then use `--local-evidence FILE`. The controller records evidence and captures the snapshot; it never runs project commands.
4. When status permits `prepare-review`, run it once after the final local
   verification report (with `--supplemental-evidence FILE` only for an
   explicitly iterative run). Use Browser only after that prepared prompt
   exists. Save the raw response, run status, then use `accept-review
   --raw-response FILE --observed-conversation-url URL --observed-model-label
   LABEL --observed-reasoning-label LABEL --observed-plan-label LABEL` when
   listed. Under `FINAL_ONLY`, `CHANGES_REQUESTED` or `BLOCK` stops the run;
   do not prepare another Pro review.
5. When status permits `final-verify`, run it. Only its successful result completes the controller run. `abandon-attempt` is allowed only when status lists it and a prompt is proven unsent; it requires exactly `--send-status NOT_SENT --not-sent-evidence FILE`. Ambiguous Browser send status is a hard stop governed by the recovery contract.

## Context budget

The controller enforces UTF-8 byte limits before publishing a prepared prompt:
field-specific item caps (32 or 64), 8,192 bytes per item, 65,536 bytes per
dynamic section, and 131,072 bytes for the complete prepared prompt. Frozen
requirements remain complete and unabridged. Oversized supplemental artifacts
remain unchanged on disk and are represented to the model only by bounded
identity, digest, byte-size, and status metadata. Stable error codes identify
the exact exceeded boundary; never silently truncate a local artifact.

All Browser interaction, project-command execution, detailed design, implementation, tests, and user escalation remain outside the controller. The controller never drives the Browser or runs project commands.

## Recovery

`status` is read-only. A genuinely absent task returns `RUN_NOT_FOUND`. If it reports `phase: INIT_INCOMPLETE` and lists `init --retry-incomplete`, the controller has recognized only allowlisted, controller-owned pre-state scaffolding. Re-run init with `--retry-incomplete` and all original request, context, model, and approval arguments. Retry refuses a live lock, an established or malformed state, links/reparse points, unexpected files, or any ambiguous ownership; it never repairs those cases automatically.

Model attestation has its own state schema version. A legacy run that is still completely conversation-unbound is upgraded in memory and persists the new null attestation fields on its next normal controller transition. A legacy or partial state that is already bound cannot be re-attested safely: `status` returns `LEGACY_STATE_RESTART_REQUIRED`, lists no next command, and requires preserving the old run while starting again under a new task slug. Never edit legacy state to invent a model family, reasoning level, or plan.

For every other `recovery_required: true`, `INIT_RECOVERY_REQUIRED`, or `RECOVERY_REQUIRED` result, stop the normal loop. Preserve `state.json`, every transaction directory, and all referenced artifacts byte-for-byte; do not delete, rename, repair, or consume them. Escalate to the user with the reported paths and run only the read-only status command:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py status --repo REPOSITORY --task TASK
```

Manual inspection may use the exact low-level validator commands documented in `references/packet-contract.md`, including `validate_packet.py transition` with independently preserved previous/current states and the matching closed context. Those diagnostics do not authorize cleanup or state repair. No normal mutation may resume until the transaction is resolved outside the controller path with explicit user direction.

## Hard Stops

Use at most one accepted review packet for `FINAL_ONLY` and at most three for
explicit `ITERATIVE` runs, plus one format-only correction per failed turn.
Reconnects and format corrections do not consume a review round. A long-running
but visibly active Pro turn is not a timeout failure and must not be accelerated
automatically. Stop on ambiguous send status, authentication or Browser
failure, explicit generation failure, silent model downgrade,
conversation/turn/nonce mismatch, replay, repeated malformed output, the same
unresolved finding or derived root cause across two consecutive reviews,
sensitive disclosure, new scope or user authority, or any destructive/external
action.

This Skill does not trigger for requirements-only consultation, standalone review, or ordinary implementation. It never authorizes commit, push, pull request, deployment, permission changes, purchases, messages, or destructive commands.
