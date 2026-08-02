---
name: monitoring-subagents
description: Use when coordinating two or more concurrent subagents, when a user asks who is doing what, when parallel work may be blocked, stale, or failed, or when long-running or cross-session agent work needs a concise intervention view.
---

# Monitoring Subagents

## Overview

Maintain an evidence-backed roster of workers, changes, and intervention
needs. Prefer action-relevant state over a live transcript; never expose raw
reasoning or hidden chain-of-thought.

## Activate proportionately

- Show a full roster when two or more workers are concurrent, the run is long,
  or the user explicitly asks for status.
- For a single short worker, skip the dashboard unless it needs attention.
- Include cross-session workers only when the host can inspect them. Mark the
  rest `unavailable`; do not claim runtime parity the host does not provide.

## Build the roster

Record each worker's stable ID or label, parent session, assigned outcome,
state, latest evidence and timestamp, output location, and required action.
Derive state only from host status tools, explicit agent messages, terminal
results, or observed artifacts.

| State | Use when |
|---|---|
| `queued` | Dispatched but not confirmed running |
| `running` | Recent evidence shows active work |
| `waiting` | Paused for an expected dependency or approval |
| `blocked` | Explicitly cannot continue without intervention |
| `stale` | No recent evidence, but no terminal or blocked signal |
| `failed` | The host or worker reports terminal failure |
| `completed` | A terminal result or verified output exists |
| `unavailable` | The host cannot inspect the worker |

Silence is not failure. Do not invent progress, percentages, blockers, or
completion from elapsed time alone.

## Refresh and report

Refresh after dispatch, on completion or attention events, on request, and
before final synthesis. Use host-native status or wait tools. Prefer one
bounded snapshot that covers all workers; do not busy-poll or repeatedly read
unchanged threads.

Present the first view as a compact table:

| Agent | Session | State | Current task | Last evidence | Action/output |
|---|---|---|---|---|---|

Afterward, report only material changes unless the user requests the full
roster. Keep updates in normal progress commentary so they remain visible
without interrupting the work.

## Prioritize intervention

Handle explicit user-input requests, `blocked`, and `failed` first. Inspect a
`stale` worker once before deciding whether to redirect it. Collect
`completed` outputs and release finished workers when the host supports it.
Leave healthy `running` workers alone.

## Stop

Stop monitoring when every worker is terminal, unavailable, or handed off.
Publish one final roster, collect outputs, identify unresolved items, and close
or release workers that no longer need to remain active.

## Common mistakes

- Creating permanent status artifacts for one quick worker.
- Treating silence as `blocked` or `failed`.
- Streaming full logs instead of state changes and intervention needs.
- Replacing real work with polling or status narration.
- Claiming cross-session visibility that the host cannot verify.
