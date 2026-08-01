# Session lifecycle

How a bridge behaves once a task is running: what states a thread can be in, when the bridge is
busy, how a run is cancelled, and what may be posted to Discord.

The shape here follows a working owner-only Discord bot that drives a coding agent on a Windows
host, adapted to Claude Code. Its lesson is that the hard part is not the first turn — it is the
states around it.

## Thread states

One Discord thread holds one session record, persisted to disk:

```
thread_id -> { session_id, project, cwd, state, run_id, updated_at }
```

| State | Meaning | What the operator can do |
|---|---|---|
| `running` | a turn is executing | wait, or cancel |
| `waiting_for_owner` | the agent asked a question and stopped | reply in the thread, or cancel |
| `completed` | a turn ended normally | reply to continue, or start a new task |
| `failed` | a turn ended unsuccessfully | reply to retry or clarify |
| `cancelled` | the operator stopped the turn | reply to start a new turn |

Write the record with a temporary file and an atomic rename. A record half-written during a crash
loses the session ID, and a session ID that cannot be read is a conversation the operator cannot
resume.

## Busy rule

`running` and `waiting_for_owner` both count as **active**. The bridge is idle only when no thread
is in either state.

Refuse to start a new task while any thread is active, and say which thread is holding it. Treating
`waiting_for_owner` as idle is the subtle mistake: the operator walks away from an unanswered
question, starts something else, and now two sessions compete for the same working tree.

`max_concurrent_sessions` above 1 only makes sense when each concurrent session has its own project
directory. Two sessions in one working tree corrupt each other's edits regardless of what the
config says.

## Crash recovery

The bridge process can die mid-run: a host reboot, a crash, an update. On startup, before accepting
any Discord message, scan the persisted records and move every `running` record to `failed`.

Without that sweep a stale `running` record makes the bridge permanently busy, and the only cure the
operator can find is deleting files by hand.

## Cancellation

Every active thread needs a cancel affordance, and only an operator may use it. A long agent run
that cannot be stopped from the phone is the failure mode the bridge exists to prevent.

- Hold an `AbortController` per active run and abort it on the button.
- Killing the direct child is not enough. The agent spawns its own processes; terminate the whole
  process tree. On Windows that means `taskkill /PID <pid> /T /F`, with a fallback if it fails or
  hangs. On POSIX, signal the process group.
- Cancelling a `waiting_for_owner` thread needs no signal — no process is running. Move the record
  to `cancelled` so the bridge becomes idle.
- Report cancellation as `cancelled`, never as `completed`.

## Run timeout

Separate from the approval timeout. A turn that never ends holds the single active slot forever, so
give the run its own deadline, terminate the process tree when it expires, and record the outcome as
a timeout rather than a failure. Make it configurable: a ten-minute default is short for a real
refactor and long for a question.

## What may be posted to Discord

Discord history is durable, searchable, and synced to every client the operator is signed in to.
Post milestones, not a transcript:

- `received`, `running`, `waiting for owner`, `completed`, `failed`, `cancelled`.

Edit one milestone message per turn rather than posting a new message per event, so a long run does
not bury the thread.

Do not post the agent's reasoning, raw tool output, command logs, or diagnostics. Write those to a
local run directory (`runs/<run_id>/`) and tell the operator where to look. The operator can read a
file on the host; a leaked secret in a Discord message is there for good.

The final assistant message is the exception: that is the answer the operator asked for.

## Attachments

Anything the agent produces for the operator goes in one declared output directory, and only files
under it are attached.

- Resolve each candidate path and confirm it is inside the output directory after resolution.
- Skip symlinks rather than following them; a symlink in the output directory is a way out of it.
- Enforce a size cap and report skipped files instead of silently dropping them.

Without this, "attach the file you just made" becomes an arbitrary file-read primitive driven by
whatever the agent decided to name.

## Model and effort belong to the bridge

Pass the model and effort level explicitly on every turn rather than inheriting whatever the host's
Claude Code configuration happens to be. The bridge's behavior should not change because the
operator adjusted a local setting for unrelated work, and the operator should be able to read the
config and know what a Discord request will cost.

This is the same rule as `setting_sources`: state it, do not inherit it.
