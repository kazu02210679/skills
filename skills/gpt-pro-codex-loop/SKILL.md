---
name: gpt-pro-codex-loop
description: Use when the user explicitly asks Codex Desktop to use ChatGPT Pro through the Browser to define or freeze requirements and iteratively review a Codex implementation until both semantic and local verification gates pass.
---

# GPT Pro Codex Loop

ChatGPT Pro owns product requirements, acceptance criteria, and semantic review. Codex owns repository investigation, detailed design, implementation, tests, snapshots, and every local verification claim.

**REQUIRED SUB-SKILL:** Use `browser:control-in-app-browser`.

Read [references/packet-contract.md](references/packet-contract.md) before creating artifacts and [references/prompt-contract.md](references/prompt-contract.md) before every Pro turn.

## Workflow

1. Preflight the repository and disclosure boundary. Capture and validate the immutable baseline; require explicit inclusion of pre-existing product paths. Refuse tracked or staged `.ai-pro-loop/` metadata.
2. Open a new ChatGPT conversation, visibly verify the requested Pro model policy, and send one correlated requirements-envelope prompt. Bind the persistent conversation URL only after the first valid response. A response from any other conversation is a hard stop recorded as `conversation_identity_mismatch`.
3. Save the raw response, strictly decode exactly one fenced JSON object, and validate its envelope against trusted attempt data. Freeze a valid `PLAN_READY` payload, or preserve an unapproved material proposal unchanged in `USER_DECISION_REQUIRED`. If the user approves, bind the receipt to that stop sequence and exact proposal digest and promote it directly; never ask Pro to rewrite an approved proposal.
4. Implement and verify locally. Capture a stable product snapshot and validate the report against active requirements, trusted state, and that snapshot.
5. In the same bound conversation and model, send a fresh correlated review turn. Validate the envelope and review context before routing `CODE_CHANGE`, `TEST_CHANGE`, `PROVIDE_EVIDENCE`, `REQUIREMENTS_REVISION`, or `USER_DECISION`.
6. Derive every root-cause fingerprint locally from the finding's acceptance ID, category, required action, and stable root-cause key. Never trust a model-selected digest.
7. Complete only after a validated Pro `PASS` and a final gate that revalidates the active requirements and implementation report proves that every recorded local check passed, omissions and unresolved blockers are empty, scope and artifact hygiene passed, and the reviewed snapshot is unchanged. A final-verification stop must preserve these bindings until direct resume.

## Hard Stops

Use at most three valid review packets and one format-only correction per failed turn. Reconnects and format corrections do not consume a review round. Stop on ambiguous send status, authentication or Browser failure, silent model downgrade, conversation/turn/nonce mismatch, replay, repeated malformed output, the same unresolved finding or derived root cause across two consecutive reviews, sensitive disclosure, new scope or user authority, or any destructive/external action.

This Skill does not trigger for requirements-only consultation, standalone review, or ordinary implementation. It never authorizes commit, push, pull request, deployment, permission changes, purchases, messages, or destructive commands.
