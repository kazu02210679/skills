---
name: codex-orchestration
description: Delegate implementation from Claude Code to OpenAI Codex while Claude remains the requirements owner and acceptance reviewer. Use in Claude Code when the user asks to let Codex implement a sizeable change, have Claude direct and verify Codex, or continue a Codex run with targeted guidance after a blocker. In Codex, use only to inspect or maintain this orchestration workflow; do not recursively delegate to another Codex session unless the user explicitly requests it.
---

# Claude ⇄ Codex orchestration

Keep Claude Code as the orchestrator and reviewer. Let Codex investigate,
design, implement, test, and report. Do not let either model's report substitute
for verification.

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`. The wrappers
are `SKILL_DIR/scripts/codex_run.sh` and
`SKILL_DIR/scripts/codex_resume.sh`; do not assume a Claude plugin root.

## 1. Define the boundary

Turn the request into:

- requirements with genuine ambiguities resolved;
- explicit in-scope and out-of-scope items;
- a verifiable acceptance checklist;
- the target repository's build, test, lint, type-check, and dependency rules.

Each acceptance item must name an observable check. Do not add features outside
the agreed boundary.

## 2. Write the task packet

Create `.codex-instructions/<task>.md` in the target repository. Include:

1. the top-level requirement and a prohibition on unrequested features;
2. in-scope and out-of-scope work;
3. the acceptance checklist;
4. a test policy covering relevant boundaries, timeouts, invalid states, and
   reproducibility;
5. this stuck protocol:

   > If you hit a blocker or a spec/API conflict, do not make large
   > unrequested changes. Document the problem, cause, and minimal alternative
   > in the report, then stop.

Keep task packets and later hint files auditable. Commit them only when the
repository's policy allows generated coordination artifacts.

## 3. Delegate

Run:

```bash
"SKILL_DIR/scripts/codex_run.sh" \
  .codex-instructions/<task>.md \
  <workdir>
```

The wrapper prints paths for `report.md`, `events.jsonl`, and `meta.json`.
`CODEX_SANDBOX` defaults to `workspace-write`; use `read-only` for a trial.
Use `danger-full-access` only in an isolated environment after the user has
authorized that risk.

## 4. Verify independently

Read [acceptance-review.md](references/acceptance-review.md), then:

1. read the task packet and derive the acceptance checklist;
2. read `report.md` as a claim, not evidence;
3. run every applicable check yourself;
4. inspect the diff for scope creep, weakened tests, and bypassed guardrails;
5. return `DELIVER` only when every required item passes.

If verification cannot run, mark the affected item unresolved. Do not turn a
missing check into a pass.

## 5. Unblock with a bounded loop

When Codex is blocked or verification fails:

1. diagnose the root cause from `events.jsonl`, `stderr.log`, the diff, and
   failing output;
2. write `.codex-instructions/<task>.hint-N.md` with the root cause, concrete
   guidance, and the minimal path forward;
3. resume:

   ```bash
   "SKILL_DIR/scripts/codex_resume.sh" \
     .codex-instructions/<task>.hint-N.md \
     <workdir> \
     <outdir>
   ```

4. return to independent verification.

Cap the loop at three attempts by default. Stop earlier when the same blocker
repeats without new evidence. Tell the user what failed, what was tried, and
the smallest recommended decision.

## Guardrails

- Do not use this workflow for a trivial change unless the user explicitly
  wants delegation.
- Never trust generated reports without rerunning the acceptance checks.
- Keep the sandbox no broader than the task requires.
- Do not publish, merge, deploy, or change repository permissions unless the
  user separately asks for that action.
- Do not invoke this workflow recursively from Codex by default.
