# GPT Pro Codex Loop Controller Design

Date: 2026-07-31

## Goal

Add a thin, standard-library Python controller to `gpt-pro-codex-loop` so
Codex no longer hand-builds protocol headers, digests, candidate states, or
final-gate evidence during the normal requirements, implementation, review,
and correction loop.

The controller is invoked without installation:

```powershell
python skills/gpt-pro-codex-loop/scripts/gpc_loop.py <command> ...
```

It remains part of the existing Skill and does not create a separate package
or runtime dependency.

## Responsibility Boundary

The controller owns deterministic protocol mechanics:

- initialize one run from a validated repository preflight;
- render correlated requirements and review prompts;
- validate and consume Pro response envelopes;
- assemble implementation reports from Codex-owned evidence;
- capture and bind product snapshots;
- derive candidate workflow states and root-cause fingerprints;
- validate every transition before replacing trusted state;
- derive final-gate evidence from validated artifacts;
- report the current phase and permitted next operations.

Codex and the Browser continue to own:

- repository investigation and bounded evidence selection;
- ChatGPT authentication, model selection, conversation verification, and
  message transport;
- detailed design, product changes, and test execution;
- semantic content in local evidence;
- user escalation and sensitive-data decisions.

The controller never executes project commands, drives the Browser, edits
product files, or performs commits, pushes, pull requests, merges,
deployments, messages, purchases, permission changes, or destructive
operations.

## Selected Architecture

Use a Python entry point that imports the existing `validate_packet.py` and
`capture_snapshot.py` modules directly:

```text
Codex / Browser
  | raw response and local evidence
  v
gpc_loop.py
  | command parsing and stable JSON output
  v
gpc_loop_controller.py
  | run loading, prompt rendering, candidate construction,
  | locking, staging, and trusted-state commit
  +--> validate_packet.py
  +--> capture_snapshot.py
```

Direct imports keep one authoritative implementation of packet, transition,
digest, and snapshot rules. The controller must not duplicate the validators
or parse their CLI output.

Alternatives rejected:

- A subprocess wrapper would require more temporary JSON hand-offs and make
  failures harder to classify across Windows and Linux.
- An installable package and global `gpc-loop` command would add packaging and
  versioning work before the workflow has demonstrated a need for independent
  distribution.
- A full Browser or workflow automation engine would cross the existing
  authority boundary and reproduce mutable UI behavior.

## Files

Create:

```text
skills/gpt-pro-codex-loop/scripts/gpc_loop.py
skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py
evals/gpt-pro-codex-loop/test_gpc_loop.py
```

Modify:

```text
skills/gpt-pro-codex-loop/SKILL.md
skills/gpt-pro-codex-loop/references/packet-contract.md
skills/gpt-pro-codex-loop/references/prompt-contract.md
.github/workflows/validate-skills.yml
```

`gpc_loop.py` is only the command-line adapter. All filesystem and protocol
logic lives in `gpc_loop_controller.py`, which can be tested without launching
a subprocess.

The controller reads the prompt bodies from stable, named fenced sections in
`prompt-contract.md`; it does not keep a second copy of prompt wording in
Python. Tests fail if a required heading or exactly one following text fence
cannot be found.

Prompt templates are UTF-8 without BOM. After fence extraction, normalize
`CRLF` and bare `CR` to `LF` and retain exactly one trailing `LF`. Parse
template placeholders into text and token nodes before inserting any bounded
user content. Each required token must occur exactly once in its source
template; unknown or missing template tokens fail closed. Inserted values are
leaf nodes and are never reparsed as template syntax, so a user request that
contains text such as `{{PROMPT_DIGEST}}` cannot alter replacement or digest
behavior. Render the one prompt-digest node as the literal
`{{PROMPT_DIGEST}}` for hashing and as the resulting lowercase SHA-256 value
for the final prompt.

## Run Selection

Every command except `init` accepts:

```text
--repo <repository-root>
--task <task-slug>
```

The run directory is always:

```text
<repository-root>/.ai-pro-loop/<task-slug>/
```

The controller resolves the repository root and run directory before reading
or writing. It rejects task slugs containing separators, traversal, control
characters, or names outside the existing slug policy. It rejects symlink or
junction traversal that escapes the resolved `.ai-pro-loop` directory.

No command searches globally for a run or silently selects the most recent
run.

Consumed-envelope and domain-workflow authority comes only from `state.json`
and the exact artifacts whose digests or identities are reachable from that
state. An artifact placed before a failed state commit is an orphan and has no
consumed-envelope or workflow authority. A persisted expected-attempt artifact
is separate pre-send intent: it can block duplicate preparation but cannot
mark an envelope consumed or advance the domain workflow.

## Commands and Data Flow

### `init`

Inputs:

- repository root and task slug;
- user request file;
- bounded repository-context file;
- optional approved pre-existing product paths;
- model policy and optional exact requested label.

Behavior:

1. Refuse an existing run directory.
2. Run the existing preflight inspection and validation.
3. Build the complete initial trusted state.
4. Validate the `PREFLIGHT -> REQUIREMENTS_PENDING` transition.
5. Persist `request.md`, `repository-context.md`, `preflight.json`,
   `state.json`, and the initial event.

The initial state remains conversation-unbound. `init` does not generate or
send a prompt.

### `prepare-requirements`

Inputs:

- run identity;
- optional conflict-evidence file when the active phase represents a
  requirements revision.

Behavior:

1. Require `REQUIREMENTS_PENDING`.
2. Select the initial or revision template from `prompt-contract.md`.
3. Generate `run_id`, semantic `turn_id`, fresh nonce, `in_reply_to`, and
   previous packet digest from trusted artifacts.
4. Render every placeholder except `PROMPT_DIGEST`, hash the exact UTF-8
   bytes, then insert that digest.
5. Persist the prompt and closed expected header before returning.

The command prints canonical JSON containing the prompt path, expected-header
path, turn ID, nonce, and the required Browser checks. It never sends the
prompt.

Only one outstanding expected attempt is allowed for a semantic turn.
Reconnect, retry, and format-correction workflows remain explicit recovery
operations governed by the existing prompt contract.

### `accept-requirements`

Inputs:

- run identity;
- complete raw Browser response;
- currently observed persistent conversation URL;
- currently observed model label.

Behavior:

1. Load the outstanding expected header and derive the consumed-envelope set
   only from trusted `state.last_consumed_packet_digest` and
   `state.last_consumed_review_envelope_digest`.
2. Strictly extract one JSON fence and validate the envelope.
3. Require the currently observed conversation URL and model label to satisfy
   the unbound/bound conversation and model policy before accepting the
   response.
4. Validate the requirements payload against the active prior revision.
5. Construct a complete candidate state and requirements transition context.
6. Validate the transition.
7. Stage the raw response, envelope, immutable requirements revision,
   `requirements.json`, event, and candidate state.
8. Commit the candidate state last.

`PLAN_READY` advances to `REQUIREMENTS_FROZEN`. A material
`NEED_USER_INPUT` proposal is preserved unchanged in
`USER_DECISION_REQUIRED`. `BLOCK` remains a hard stop.

Material approval uses a separate `approve-requirements` command. That command
accepts one local user-approval evidence file, derives the exact receipt from
trusted stop state, validates direct promotion of the stored proposal, and
never asks Pro to rewrite it. The evidence file records the authorization but
does not choose or modify the requirements digest.

### `build-report`

Inputs:

- run identity;
- one strict local-evidence JSON object containing:
  - an intent for every changed product path;
  - intent summary;
  - evidence for every acceptance ID;
  - commands already executed by Codex, with `PASS` or `FAIL` outcomes and
    bounded output summaries;
  - diff evidence, omissions, and unresolved risks or blockers.

Behavior:

1. Require `REQUIREMENTS_FROZEN`, `IMPLEMENTING`, or
   `LOCAL_VERIFICATION` as allowed by the validated transition contract.
2. Capture a stable product snapshot using the immutable preflight.
3. Require the evidence path set to match the captured changed-product path
   set exactly.
4. Fill controller-owned report fields from active state, requirements, and
   snapshot.
5. Validate the report context.
6. Validate the candidate transition to `REVIEW_PENDING`.
7. Persist the snapshot, report, event, and state, with state committed last.

For an initial implementation, the command validates the in-memory sequence
`REQUIREMENTS_FROZEN -> IMPLEMENTING -> LOCAL_VERIFICATION ->
REVIEW_PENDING`. After a code/test correction, it validates
`IMPLEMENTING -> LOCAL_VERIFICATION -> REVIEW_PENDING`. Only the final
candidate state is authoritative; the event log records every validated
intermediate edge. This allows Codex to perform implementation outside the
controller without hand-authoring phase-only states.

The controller records supplied test evidence but does not execute its
commands. `FAIL`, omissions, and unresolved blockers may be recorded for Pro
review, but they cannot pass `final-verify`.

### `prepare-review`

Inputs:

- run identity;
- optional supplemental-evidence file when the active route is
  `PROVIDE_EVIDENCE`.

Behavior:

1. Require `REVIEW_PENDING`, or `LOCAL_VERIFICATION` with only a validated
   `PROVIDE_EVIDENCE` route and an unchanged snapshot.
2. Select the normal review or evidence-supplementation prompt.
3. Bind the complete active requirements, requirements digest, report, and
   snapshot.
4. Create and persist a fresh correlated expected header and prompt before
   returning their paths.

The command never sends the prompt.

For evidence-only supplementation, it validates the phase-only
`LOCAL_VERIFICATION -> REVIEW_PENDING` candidate before persisting the new
expected attempt. It preserves the active report and snapshot digests and does
not authorize a product change.

### `accept-review`

Inputs:

- run identity;
- complete raw Browser response;
- currently observed persistent conversation URL;
- currently observed model label.

Behavior:

1. Require the currently observed conversation URL and model label to match
   the bound trusted state and model policy.
2. Validate the envelope against the outstanding attempt and the consumed
   chain heads from trusted state.
3. Validate review semantics against the active requirements and report.
4. Derive finding fingerprints locally.
5. Derive the transition target using the existing validator's routing rules.
6. Construct and validate the complete candidate review state and transition
   context.
7. Persist the raw response, envelope, review payload, event, and state, with
   state committed last.

Routes:

```text
PASS                  -> FINAL_VERIFICATION
CODE_CHANGE           -> IMPLEMENTING
TEST_CHANGE           -> IMPLEMENTING
PROVIDE_EVIDENCE      -> LOCAL_VERIFICATION
REQUIREMENTS_REVISION -> REQUIREMENTS_PENDING
USER_DECISION / BLOCK -> USER_DECISION_REQUIRED
```

The validator remains authoritative when multiple findings require a more
restrictive target.

### `final-verify`

Inputs:

- run identity.

Behavior:

1. Require `FINAL_VERIFICATION`.
2. Recapture the product snapshot from the immutable preflight.
3. Derive the closed final-gate object from trusted state, active
   requirements, report, review, and current snapshot.
4. Derive gate booleans rather than accepting them as CLI input:
   - every acceptance result and report test is `PASS`;
   - omissions, blockers, pending actions, and scope violations are empty;
   - run metadata hygiene and current snapshot checks pass.
5. Validate the final gate and `FINAL_VERIFICATION -> COMPLETE` transition.
6. Persist the current snapshot, final-gate evidence, completion event, and
   state, with state committed last.

Any product drift or failed gate leaves the prior trusted state unchanged and
returns a structured error. The controller does not synthesize a `PASS`.

### `status`

Read only. Print canonical JSON containing:

- run identity and current phase;
- active requirements revision and review round;
- conversation/model binding summary without credentials;
- pending actions and stop category;
- outstanding attempt, if any;
- the exact next controller commands permitted by the combination of phase and
  outstanding-attempt state.

When no attempt is outstanding, a pending requirements or review phase offers
only its matching `prepare-*` command. When an attempt is outstanding, `status`
offers only the matching `accept-*` command and `abandon-attempt`; it must not
also offer a `prepare-*` command that is guaranteed to fail.

`status` must work when an orphan transaction or lock exists and report it
without deleting it.

### `abandon-attempt`

Inputs:

- run identity;
- exact send status `NOT_SENT`;
- one local evidence file explaining how the user or Codex verified that the
  outstanding prompt was not submitted to ChatGPT.

Behavior:

1. Require exactly one outstanding expected attempt and no raw response,
   accepted envelope, or consumed state binding for it.
2. Reject any missing, ambiguous, sent, or unknown send status.
3. Atomically replace the expected-attempt artifact with a closed abandoned
   attempt record containing its header digest, nonce, prompt digest, evidence,
   and abandonment time.
4. Preserve `state.json` and every domain artifact unchanged.

All future attempt generation treats nonces and prompt digests in abandoned
records as used. This command is only for a prompt proven not to have been
sent. If send status is ambiguous, use the Browser timeout/reconnect contract
and do not abandon or resend.

## Trusted Writes and Concurrency

Each mutating command takes an exclusive per-run lock using atomic file
creation. An existing lock causes refusal; the controller never guesses that a
lock is stale or removes it automatically.

Multi-file replacement cannot be one filesystem transaction. The controller
therefore uses a logical commit:

1. create a transaction directory inside the run;
2. write complete candidate artifacts with UTF-8 and deterministic canonical
   JSON;
3. run all packet, context, snapshot, and transition validation against the
   staged candidates;
4. atomically replace immutable/non-authoritative artifacts;
5. atomically replace `state.json` last;
6. append the diagnostic event after state commit;
7. remove the transaction directory and lock in `finally`.

`state.json` is the authority for progress. Consumed transport history is
derived only from its two chain-head fields, never by enumerating envelope
files. The expected header and `previous_packet_digest` make any older
envelope invalid for the current turn, while the chain head prevents replay of
the most recently consumed envelope. A crash before state replacement cannot
advance the run; any artifact not reachable from the unchanged state is an
orphan. A crash after state replacement may omit only a diagnostic event.
`status` reports orphan transaction directories and unreachable artifacts for
manual inspection. No command silently repairs or consumes them.

All state-changing commands compare the loaded state digest immediately before
commit with the digest observed at command start. A mismatch rejects the
commit even if the lock was bypassed externally.

## Error Model

The CLI emits one canonical JSON object to standard output:

```json
{"ok": true, "command": "status", "result": {}}
```

or:

```json
{
  "ok": false,
  "command": "accept-review",
  "error": {
    "code": "ENVELOPE_MISMATCH",
    "message": "The Pro response does not match the outstanding review attempt.",
    "details": []
  }
}
```

Expected protocol, phase, filesystem, and validation failures use documented
stable error codes and exit `2`. Unexpected internal failures use
`INTERNAL_ERROR` and exit `1` without a traceback on standard output; an
optional `--debug` flag sends the traceback to standard error.

Validation failures must not modify trusted state. The controller rejects
explicitly forbidden credential- and Browser-session-shaped field names and
structures before persistence. It does not detect or redact secrets embedded
in arbitrary strings. Errors do not echo full raw responses or sensitive
evidence.

## Recovery Boundary

Version 1 automates the primary loop and material requirements approval. It
does not automate:

- ambiguous Browser send recovery;
- Browser reacquisition or model selection;
- format-only correction construction;
- arbitrary resolution of `BLOCK` or `USER_DECISION` review stops;
- destructive cleanup of orphan locks or transactions.

For these cases, the controller stops without state mutation and returns the
exact existing packet/prompt-contract section and validator command needed for
manual recovery. This prevents rare recovery paths from turning the thin
controller into a second workflow engine. A later controller version may add
one recovery only after a real run demonstrates repeated, error-prone manual
work.

`abandon-attempt` is intentionally included despite this recovery boundary
because a prompt can be proven unsent before any Browser action. It is not
valid for an ambiguous Browser timeout.

Any manually recovered or format-corrected Browser response remains subject to
the same currently observed conversation URL and model-label checks before a
controller `accept-*` command may consume it.

## Testing

Use `unittest` and temporary Git repositories. No test uses ChatGPT
credentials, network access, or mutable Browser selectors.

Focused controller tests cover:

- initialization and deterministic prompt/header generation;
- the normal requirements, report, review `PASS`, and final-gate path;
- `CHANGES_REQUESTED`, fresh report, fresh review, and convergence;
- evidence-only review without snapshot change;
- material requirements proposal and digest-bound approval;
- malformed JSON, duplicate/replayed envelopes, wrong nonce, stale prompt,
  wrong conversation, and wrong model;
- accepted artifacts orphaned before state commit do not enter consumed
  history;
- every `accept-*` command rechecks the observed conversation URL and model;
- abandoned unsent attempts cannot be consumed or reuse correlation values,
  while ambiguous send status is refused;
- LF/CRLF templates produce identical prompts and digests, template tokens
  have exact cardinality, and token-like user content remains literal;
- illegal command/phase combinations;
- local-evidence path and acceptance-ID mismatches;
- report `FAIL`, omission, blocker, scope violation, and product drift at the
  final gate;
- lock contention, state digest races, orphan transaction reporting, and
  state unchanged after every rejected operation;
- canonical CLI output and stable exit codes.

The existing packet-validator and snapshot suites remain mandatory. Add the
controller suite to the existing Ubuntu and Windows matrix job.

## Skill Documentation

Update `SKILL.md` to use the controller for the normal loop and to state that
the low-level validator and snapshot commands are recovery and diagnostic
interfaces. Keep the Skill body concise; detailed command arguments and
artifact behavior belong in `packet-contract.md`.

Update `prompt-contract.md` only where the controller now renders and persists
prompt correlation data. The Pro prompt wording and Browser authority boundary
remain unchanged.

## Acceptance Criteria

- The controller is executable with Python alone and has no new dependency.
- The normal requirements-to-final-verification loop requires no hand-authored
  expected header, digest, candidate state, transition context, or final-gate
  JSON.
- Every Browser response acceptance verifies the current observed conversation
  URL and model label against trusted run state.
- A proven-unsent prompt can be abandoned without changing domain state or
  reusing its correlation values; an ambiguous send cannot.
- Existing validator and snapshot modules remain authoritative and are not
  duplicated.
- Every trusted state change is validated as a complete candidate and commits
  `state.json` last under an exclusive run lock.
- Browser, implementation, tests, and external Git operations remain outside
  controller authority.
- `status` identifies the current phase and permitted next commands without
  modifying the run.
- Focused controller tests pass on Windows and Ubuntu together with every
  existing Skill test.

## Non-Goals

- OpenAI API use or separate API billing.
- ChatGPT Web selectors or Browser automation.
- Project command execution or local implementation.
- Detection or redaction of secrets embedded in arbitrary user strings.
- A globally installed package or shell-specific launcher.
- Compatibility with `codex-orchestration`.
- Commit, push, pull request, merge, or deployment automation.
- Automatic recovery from every Browser or workflow failure.
