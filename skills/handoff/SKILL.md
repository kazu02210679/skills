---
name: handoff
description: Create a safe, conversation-centered handoff to a fresh task, thread, session, or chat while preserving the original purpose, changes of direction, decisions, constraints, failed approaches, artifacts, unresolved work, and next action. Use when the user explicitly asks to hand off, transfer, continue in a new task, start fresh without losing context, or says phrases such as "引き継いで", "別セッションに移して", "新しいタスクにして", or "move this to a fresh chat"; if the user only remarks that the conversation is long or slow without asking to move it, recommend a handoff but do not create one.
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
- For every known material implementation, test, deployment, failed operation, and result, check for a supporting durable artifact and locator. If either the locator or the supporting artifact's existence is not recoverable, list it in `Relevant artifacts` as unknown; never invent an identifier, silently omit it, or present a speculative artifact as fact. Add resolving every material unknown artifact or locator explicitly to `Open questions and next actions`.
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

In `First response contract`, require the destination's first response to restate the actual material information in the handoff: why the task exists, the current objective and state, every material decision, correction, prohibition, completed or pending test status, unknown, and the proposed next action. Name those items concretely rather than repeating category labels. Require it to wait for confirmation before calling tools or continuing work.

## 4. Run the safety pass

- Remove secrets, credentials, tokens, private keys, cookies, passwords, unnecessary personal data, and any sensitive values that are not needed to continue. If secret involvement matters operationally, state that a redacted secret was involved without exposing it.
- Retain actionable safety constraints, such as a failed approach that must not be repeated, corrected targets, approvals, and explicit prohibitions.
- Verify that facts, inferences, and unknowns remain distinct; references are durable; and the handoff contains no hidden reasoning.

## 5. Save a temporary backup when possible

- When file creation is available, create a uniquely named `.md` file in the operating system's temporary directory, never inside the repository, and write the complete redacted handoff there.
- Re-read the backup after writing it. Verify that the file exists and that its contents exactly match the complete redacted handoff. Report the verified backup path only after both checks pass.
- Treat the file as backup only. Keep the complete handoff inline in every destination prompt; never make continuation depend on the file.
- Retain the backup until the destination has received and acknowledged the handoff; after acknowledgment, delete it when cleanup is available. Delete it earlier only on explicit user request. Never make continuation or recovery depend on retaining the backup.
- Whenever a backup is created, include in the source-task result its verified path, that it is retained pending destination receipt and acknowledgment, and that cleanup occurs only after acknowledgment (or earlier only on explicit user request).
- If backup creation, verification, or cleanup is unavailable or fails, say so honestly and continue with the complete copyable handoff.

## 6. Create a fresh task when possible

- When a suitable task-management capability is available, create a genuinely new task in the same project or local environment. Use section 7 only if that capability is unavailable or the creation attempt fails.
- Construct the complete destination prompt, including the complete inline handoff, destination instruction, and first-response contract, before invoking the capability. Pass that exact full text literally in the capability's prompt or input argument; never use a placeholder, file-only reference, or adjacent block in place of the actual argument.
- Verify that direct task creation succeeded and identifies a genuinely new non-fork task before claiming success. Do not substitute a transcript-preserving fork.

## 7. Fall back honestly

- If task creation is unavailable or fails, do not claim that a task or chat was created.
- Return the complete, copyable handoff inline, plus the concise destination instruction. State whether backup creation was unavailable or failed when applicable.
- Preserve the same first-response contract so the user can paste the handoff into a new conversation without loss.

## 8. Close out the source task

- Report the verified result: the new task reference when creation succeeded, or the copyable handoff and reason for fallback when it did not.
- Keep the source task intact. Do not perform lifecycle actions beyond the requested transfer.
