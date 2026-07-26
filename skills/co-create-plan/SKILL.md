---
name: co-create-plan
description: Have Claude Code and OpenAI Codex jointly create an evidence-backed implementation plan as equal planning peers. Use when the user asks Claude and Codex to discuss, debate, challenge assumptions, reach consensus, or make a plan together; when a second-model planning review is wanted before implementation; or when a plan must be handed directly to the Codex-plugin-Claude-Code workflow without rerunning specification phases.
---

# Co-create Plan

Create the plan through an auditable Claude Code–Codex dialogue. Treat the two
models as peers with equal authority over technical conclusions. Do not let the
host model silently overrule the peer, and do not implement production code
during this workflow.

Read [plan-contract.md](references/plan-contract.md) before drafting the final
plan.

## 1. Establish the planning boundary

Resolve the repository root, task slug, user request, and applicable repository
instructions. Inspect only the code and documentation needed to plan the work.
Put applicable `AGENTS.md`, `CLAUDE.md`, and repository constraints into the
brief because the peer process disables custom instructions, hooks, and MCP
servers.

Write dialogue artifacts under:

```text
<repo>/.ai-planning/<task-slug>/
```

The planning workflow may additionally write the final packet to:

```text
<repo>/.codex-instructions/<task-slug>.md
```

Do not edit product code, dependency files, tests, or configuration while
planning. Use a separate implementation workflow after approval.

Treat `.ai-planning/` as sensitive working data. Prompts, transcripts, stderr,
and absolute local paths can contain repository information. Check whether it
is ignored before starting; if it is not, warn the user and recommend adding it
to `.gitignore` outside this planning-only workflow. Never stage, commit, or
publish `.ai-planning/` automatically.

## 2. Have Claude organize the brief first

Claude Code owns the first brief, but not the final technical decision. The
brief must separate:

- objective and user-visible outcome;
- requirements;
- constraints and repository rules;
- in scope and out of scope;
- known evidence and assumptions;
- unresolved questions and decision points;
- initial acceptance signals.

Save it as `.ai-planning/<task-slug>/requirements.md`.

If the current host is Claude Code, write the brief directly. If the current
host is Codex:

1. Save the raw user request and known context to
   `.ai-planning/<task-slug>/request.md`.
2. Invoke Claude with all required paths:

   ```text
   python <skill-dir>/scripts/planning_peer.py start \
     --peer claude \
     --repo <repo> \
     --brief <repo>/.ai-planning/<task-slug>/request.md \
     --outdir <repo>/.ai-planning/<task-slug>
   ```

3. Normalize Claude's first response into `requirements.md` without erasing its
   uncertainties or dissent.
4. Write Codex's response as `round-01-host.md` and continue the recorded Claude
   session with `planning_peer.py reply`.

Ask the user only when missing information would materially change the product
behavior, safety boundary, public contract, data migration, or cost. Otherwise
record a reversible assumption and continue.

## 3. Start the peer dialogue

Run the peer in a planning-only permission mode:

```text
python <skill-dir>/scripts/planning_peer.py start \
  --peer <codex-or-claude> \
  --repo <repo> \
  --brief <repo>/.ai-planning/<task-slug>/requirements.md \
  --outdir <repo>/.ai-planning/<task-slug> \
  --max-rounds 3
```

Choose the other model as `--peer`: use `codex` when hosted by Claude Code and
`claude` when hosted by Codex. The script records the exact peer session ID in
`state.json`; never use a global “resume last session” operation.

Claude runs with safe mode, an empty strict MCP configuration, planning
permissions, and only read/search tools. Codex runs with a read-only sandbox.
Do not weaken either boundary for ordinary planning.

Read the peer response and verify cited repository facts yourself. A model
claim is a proposal, not evidence.

## 4. Debate instead of serially reviewing

For each round:

1. Write the host's response to
   `.ai-planning/<task-slug>/round-NN-host.md`, using the same sections and vote
   vocabulary required from the peer.
2. Address every blocking challenge from the peer.
3. Distinguish agreement, disagreement, new evidence, and proposed plan edits.
4. Send that response into the same peer session:

   ```text
   python <skill-dir>/scripts/planning_peer.py reply \
     --state <repo>/.ai-planning/<task-slug>/state.json \
     --message <repo>/.ai-planning/<task-slug>/round-NN-host.md
   ```

5. Update a provisional plan after the exchange, not before reading it.

If a peer command fails, inspect the retained events and stderr first. Retry
only when duplicate delivery will not make the transcript ambiguous:

```text
python <skill-dir>/scripts/planning_peer.py reply \
  --state <repo>/.ai-planning/<task-slug>/state.json \
  --message <repo>/.ai-planning/<task-slug>/round-NN-host.md \
  --retry
```

The script moves the failed attempt into
`failed-attempts/round-NN-attempt-MM/` before retrying the exact recorded
session. For a failed initial `start`, use `start --retry`; it archives the
failed artifacts and creates a new peer session because no trusted state was
completed.

Require both sides to end each turn with one vote:

- `AGREE` — no material objection remains;
- `AGREE_WITH_CHANGES` — listed edits are required but no user decision is
  needed;
- `BLOCK` — a material conflict or missing decision prevents a responsible
  plan.

Do not manufacture consensus. The script enforces at most three substantive
exchange rounds by default. If a high-impact `BLOCK` remains, present the
competing options and evidence to the user for a decision. The user is the
tie-breaker, not either model.

## 5. Produce one joint plan

Create `.codex-instructions/<task-slug>.md` using the required structure in
[plan-contract.md](references/plan-contract.md). Incorporate accepted changes
from both participants. Preserve resolved disagreements in the decision log so
later implementation agents can see why an approach was chosen.

Set `planning_status: proposed` until the user approves the plan. After explicit
approval, change it to `planning_status: approved` and record the approval in
the decision log. Do not call a plan approved merely because both models agree.

Before presenting it, check:

- every implementation step names concrete files or discovery targets;
- every acceptance item is verifiable;
- constraints and non-goals are retained;
- risky assumptions have evidence, validation steps, or rollback paths;
- no unresolved `BLOCK` is hidden;
- the plan contains no production-code changes made during planning.

## 6. Hand off without replanning

For `kazu02210679/Codex-plugin-Claude-Code`, an approved packet is already the
input expected by `/codex-run`. Hand it off directly:

```text
/codex-run .codex-instructions/<task-slug>.md <repo>
```

Start that plugin at its implementation/delegation phase. Do not run
`/codex-spec` and do not repeat its requirements, design-direction, or task
packet phases unless the approved plan is stale or the user explicitly asks to
replan.

## Failure handling

- Missing peer CLI or authentication: preserve the brief, report the exact
  prerequisite, and do not imitate the unavailable model.
- Peer timeout or malformed output: retain logs in the planning directory and
  report the failed turn. Use `--retry` only after checking whether duplicate
  delivery could create an ambiguous transcript.
- Session ID missing: stop before replying; never resume an unrelated session.
- Repository changed materially during discussion: mark the plan stale and
  re-check affected evidence.
- Peer proposes implementation edits: reject the edits and keep the peer in
  planning-only mode.
