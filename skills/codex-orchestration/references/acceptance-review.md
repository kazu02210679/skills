# Acceptance review

Review the finished task independently. Do not repair production code during
this review; return a focused correction or ask the user for a decision.

1. Read `packet.md`, the task packet, and its acceptance criteria before any
   Codex report. Map each criterion to a command, inspection, or observable
   result.
2. Run every mapped check and record its command, exit status, and concise
   result. Mark a check `UNRESOLVED` when it cannot run; never convert missing
   evidence into a pass.
3. Read the latest run evidence as claims: `report.md`, `events.jsonl`,
   `stderr.log`, `meta.json`, and `scope.txt`.
4. Re-run the scope check with the **frozen** allowlist and base commit from
   `RUNDIR`, not the mutable plan file:

   ```bash
   "<skill-dir>/scripts/codex_scope_check.sh" \
     <rundir>/allowlist <workdir> "$(cat <rundir>/base_commit)"
   ```

   Treat a scope violation as `FAIL`. Treat an unavailable or indeterminate
   result as `UNRESOLVED`.
5. Inspect the diff for work outside the packet, weakened tests, disabled
   checks, broad permission changes, and generated artifacts that bypass the
   guardrails.
6. Inspect task history. Verify that each completed task has exactly one commit
   carrying one matching `Codex-Plan:` trailer and one matching `Codex-Task:`
   trailer. A commit spanning tasks, multiple commits for one task, missing
   trailers, or a trailer for another plan is a `FAIL`.
7. Run `codex_status.sh <plan-dir> <workdir>`. A plan with pending tasks is not
   ready for plan-level delivery.

Return a compact table with the acceptance item, command or evidence, status
(`PASS`, `FAIL`, or `UNRESOLVED`), and the shortest useful explanation. Finish
with `DELIVER` only when every required item passes; otherwise return `SEND
BACK` for an implementation fix or `ASK USER` for a decision requiring new
authority.
