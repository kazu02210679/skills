---
name: handoff
description: Create a safe, conversation-centered handoff to a fresh task, thread, session, or chat while preserving the original purpose, changes of direction, decisions, constraints, failed approaches, artifacts, unresolved work, and next action. Use when the user explicitly asks to hand off, transfer, continue in a new task, start fresh without losing context, or says phrases such as "蠑輔″邯吶＞縺ｧ", "蛻･繧ｻ繝・す繝ｧ繝ｳ縺ｫ遘ｻ縺励※", "譁ｰ縺励＞繧ｿ繧ｹ繧ｯ縺ｫ縺励※", or "move this to a fresh chat"; if the user only remarks that the conversation is long or slow without asking to move it, recommend a handoff but do not create one.
---

# Handoff

Preserve the user's intent and meaningful trajectory, not a message-by-message transcript. Match the source conversation's language. State only observable actions and the user's stated rationale; never reveal hidden reasoning or chain-of-thought.

If the user only says the conversation is long or slow, recommend a handoff and ask whether they want one. Do not create a task, backup, or handoff unless they ask to transfer.

## 1. Confirm transfer scope

- Confirm the continuing objective, intended destination, and what must survive the transfer.
- Identify the source language and use it for the handoff and user-facing messages.
- Search available thread- or task-management capabilities before choosing a fallback.
- Leave the source task unchanged. Do not archive, delete, compact, fork, branch, or create a worktree solely for the handoff. Never use a transcript-preserving fork.

## 2. Recover only necessary history

- Use current context when it is sufficient. Recover history only to resolve material gaps in the objective, decisions, state, constraints, failed approaches, artifacts, or next action.
- Separate facts, inferences, and unknowns. Mark uncertainty rather than filling it with guesses.
- Reference durable files, commits, PRs, issues, plans, URLs, and test identifiers instead of copying diffs, logs, or transcripts.
- Include repository state only when it changes the next action.

## 3. Build the handoff

- Create one self-contained Markdown handoff using the output contract below. Omit a section only when it is genuinely irrelevant.
- Preserve corrections, reversals, decisions, prohibitions, constraints, unresolved work, and the next concrete action.
- Suggest skills only when they are clearly relevant; otherwise omit the suggestion.
- Add one concise instruction for the destination: read the inline handoff, make no assumptions beyond it, and follow the first-response contract.

```markdown
# Handoff: {short continuing objective}

## Why this task exists
## Current objective
## Trajectory and decisions
## Current state
## Friction and failed approaches
## Constraints and preferences
## Open questions and next actions
## Relevant artifacts
## Suggested skills
## First response contract
```

In `First response contract`, require the destination's first response to restate: (1) why the task exists; (2) the current objective and state; (3) unresolved points; and (4) the proposed first action. Require it to wait for confirmation before calling tools or continuing work.

## 4. Run the safety pass

- Remove secrets, credentials, tokens, private keys, cookies, passwords, unnecessary personal data, and any sensitive values that are not needed to continue. If secret involvement matters operationally, state that a redacted secret was involved without exposing it.
- Retain actionable safety constraints, such as a failed approach that must not be repeated, corrected targets, approvals, and explicit prohibitions.
- Verify that facts, inferences, and unknowns remain distinct; references are durable; and the handoff contains no hidden reasoning.

## 5. Save a temporary backup when possible

- When file creation is available, save the complete redacted handoff as a temporary backup outside the repository when possible.
- Treat the file as backup only. Keep the complete handoff inline in every destination prompt; never make continuation depend on the file.
- If backup creation is unavailable or fails, say so honestly and continue with the complete copyable handoff.

## 6. Create a fresh task when possible

- Prefer a genuinely new task in the same project or local environment.
- Put the complete handoff inline in the destination prompt, including the destination instruction and first-response contract.
- Verify that direct task creation succeeded before claiming success. Do not substitute a transcript-preserving fork.

## 7. Fall back honestly

- If task creation is unavailable or fails, do not claim that a task or chat was created.
- Return the complete, copyable handoff inline, plus the concise destination instruction. State whether backup creation was unavailable or failed when applicable.
- Preserve the same first-response contract so the user can paste the handoff into a new conversation without loss.

## 8. Close out the source task

- Report the verified result: the new task reference when creation succeeded, or the copyable handoff and reason for fallback when it did not.
- Keep the source task intact. Do not perform lifecycle actions beyond the requested transfer.
