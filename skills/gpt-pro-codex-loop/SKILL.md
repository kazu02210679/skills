---
name: gpt-pro-codex-loop
description: Use when the user explicitly asks Codex Desktop to use ChatGPT Pro through the Browser to define or freeze requirements and iteratively review a Codex implementation until both semantic and local verification gates pass.
---

# GPT Pro Codex Loop

ChatGPT Pro owns product requirements, acceptance criteria, and semantic review. Codex owns repository investigation, detailed design, implementation, tests, snapshots, and every local verification claim.

**REQUIRED SUB-SKILL:** Use `browser:control-in-app-browser`.

Read [references/packet-contract.md](references/packet-contract.md) before creating artifacts and [references/prompt-contract.md](references/prompt-contract.md) before every Pro turn.

## Workflow

Use `scripts/gpc_loop.py` for the normal loop. Run `status` before each mutation and execute only a command it lists. Use `validate_packet.py` and `capture_snapshot.py` directly only for documented diagnostic or recovery paths.

`init` is the sole exception to the status-first rule because the run does not exist yet. Do the repository investigation and disclosure review outside the controller, then inspect the exact pre-existing product-path set without creating run state. Write the candidate manifest outside the repository so the manifest does not change the set it describes:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py inspect-init --repo REPOSITORY --task TASK --write-approval-manifest ..\REPOSITORY-TASK-approved-existing-paths.json
```

Review the complete manifest and obtain explicit user approval. Manifest generation is inspection, not approval. Then write the bounded request and repository-context inputs and initialize with the exact approved manifest:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py init --repo REPOSITORY --task TASK --request REQUEST.md --repository-context CONTEXT.md --model-policy PRO_CLASS --approved-existing-path-manifest ..\REPOSITORY-TASK-approved-existing-paths.json
```

For a small set, repeat `--approved-existing-path PATH` instead. Never combine per-path approval with `--approved-existing-path-manifest`. Init re-inspects under its lock, so a stale, changed, mismatched, malformed, or non-canonical manifest fails before state publication. `PREFLIGHT_APPROVAL_REQUIRED` and manifest errors return at most 20 preview paths plus total/omitted counts, the set digest, and JSON argv for generating a fresh manifest and retrying.

After `init`, before every state-changing command, run:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py status --repo REPOSITORY --task TASK
```

The `next_commands` result is authoritative. Do not hand-author state, expected headers, envelopes, prompt digests, consumed history, snapshots, reports, final gates, or approval receipts. If the controller returns an error, stop: do not retry a different transition or alter controller artifacts by hand.

1. When status permits `prepare-requirements`, run it (with `--conflict-evidence FILE` only for a requirements revision). It returns the prompt and expected-header paths. Browser work remains outside the controller: create or reacquire the appropriate conversation, visibly verify the required model and conversation identity, send the prepared prompt once, and save the complete raw response.
2. Run status again. When it permits `accept-requirements`, pass `--raw-response FILE --observed-conversation-url URL --observed-model-label LABEL`. The observed URL and model are required on every accepted response; do not infer either from prior state.
3. When status permits `approve-requirements`, obtain the user's authorization outside the controller, record bounded local evidence, then use `--approval-evidence FILE`. When it permits `build-report`, complete product work and local commands outside the controller, create the closed local-evidence input, then use `--local-evidence FILE`. The controller records evidence and captures the snapshot; it never runs project commands.
4. When status permits `prepare-review`, run it (with `--supplemental-evidence FILE` only for a `PROVIDE_EVIDENCE` route). Use Browser only after that prepared prompt exists. Save the raw response, run status, then use `accept-review --raw-response FILE --observed-conversation-url URL --observed-model-label LABEL` when listed.
5. When status permits `final-verify`, run it. Only its successful result completes the controller run. `abandon-attempt` is allowed only when status lists it and a prompt is proven unsent; it requires exactly `--send-status NOT_SENT --not-sent-evidence FILE`. Ambiguous Browser send status is a hard stop governed by the recovery contract.

## Context budget

The controller enforces UTF-8 byte limits before publishing a prepared prompt:
at most 64 dynamic evidence items, 8,192 bytes per item, 65,536 bytes per
dynamic section, and 131,072 bytes for the complete prepared prompt. Frozen
requirements remain complete and unabridged. Oversized supplemental artifacts
remain unchanged on disk and are represented to the model only by bounded
identity, digest, byte-size, and status metadata. Stable error codes identify
the exact exceeded boundary; never silently truncate a local artifact.

All Browser interaction, project-command execution, detailed design, implementation, tests, and user escalation remain outside the controller. The controller never drives the Browser or runs project commands.

## Recovery

`status` is read-only. A genuinely absent task returns `RUN_NOT_FOUND`. If it reports `phase: INIT_INCOMPLETE` and lists `init --retry-incomplete`, the controller has recognized only allowlisted, controller-owned pre-state scaffolding. Re-run init with `--retry-incomplete` and all original request, context, model, and approval arguments. Retry refuses a live lock, an established or malformed state, links/reparse points, unexpected files, or any ambiguous ownership; it never repairs those cases automatically.

For every other `recovery_required: true`, `INIT_RECOVERY_REQUIRED`, or `RECOVERY_REQUIRED` result, stop the normal loop. Preserve `state.json`, every transaction directory, and all referenced artifacts byte-for-byte; do not delete, rename, repair, or consume them. Escalate to the user with the reported paths and run only the read-only status command:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py status --repo REPOSITORY --task TASK
```

Manual inspection may use the exact low-level validator commands documented in `references/packet-contract.md`, including `validate_packet.py transition` with independently preserved previous/current states and the matching closed context. Those diagnostics do not authorize cleanup or state repair. No normal mutation may resume until the transaction is resolved outside the controller path with explicit user direction.

## Hard Stops

Use at most three valid review packets and one format-only correction per failed turn. Reconnects and format corrections do not consume a review round. Stop on ambiguous send status, authentication or Browser failure, silent model downgrade, conversation/turn/nonce mismatch, replay, repeated malformed output, the same unresolved finding or derived root cause across two consecutive reviews, sensitive disclosure, new scope or user authority, or any destructive/external action.

This Skill does not trigger for requirements-only consultation, standalone review, or ordinary implementation. It never authorizes commit, push, pull request, deployment, permission changes, purchases, messages, or destructive commands.
