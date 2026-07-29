# Task 2 Report: GPT Pro Loop Packet Validation

## Files changed

- `skills/gpt-pro-codex-loop/SKILL.md`
- `skills/gpt-pro-codex-loop/agents/openai.yaml`
- `skills/gpt-pro-codex-loop/scripts/validate_packet.py`
- `evals/gpt-pro-codex-loop/test_validate_packet.py`
- `docs/superpowers/plans/2026-07-29-gpt-pro-codex-loop.md` (Task 2 checkboxes only)

The required `scripts/` and `references/` directories were created by the prescribed initializer. `references/` is empty, so Git does not record it until a later task adds its contract files.

## RED evidence

After initializing the Skill and adding the tests, before implementing `validate_packet.py`, this command exited 1:

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
```

Expected failure observed:

```text
ModuleNotFoundError: No module named 'validate_packet'
```

This established that the test suite failed because the requested validator implementation did not exist.

## GREEN command/output summary

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/validate_packet.py
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py' skills/gpt-pro-codex-loop
```

All commands exited 0. The focused suite reported `Ran 13 tests` followed by `OK`; compilation succeeded; and Skill validation reported `Skill is valid!`.

## Self-review

- Implemented the exact public extraction/digest interfaces and all four required validator signatures.
- Kept validation fail-closed, standard-library-only, and independent of `codex-orchestration`.
- Encoded schema fields, decisions, actions, digest checks, acceptance coverage, and state transitions as constants.
- Added deterministic, stable-path error ordering and a nonzero CLI result for invalid packets/transitions.
- Confirmed `git diff --check` before committing.
- Updated only the six Task 2 checkboxes in the implementation plan; no Task 3+ deliverable was changed.

## Commit

`712b27a Add GPT Pro loop packet validation`

## Concerns

`python scripts/validate-skills.py` still exits nonzero because it requires the human-facing `skills/gpt-pro-codex-loop/README.md` and a regenerated root Skill catalog. Both are explicitly assigned to later tasks, so they were intentionally left untouched. The focused Task 2 tests and direct Skill frontmatter validation pass.

## Fix Round 1

### Changed files

- `skills/gpt-pro-codex-loop/scripts/validate_packet.py`
- `evals/gpt-pro-codex-loop/test_validate_packet.py`

### Covering tests

- malformed requirements dependencies are rejected by `validate_report` and its CLI subcommand;
- malformed requirements and report dependencies are rejected by `validate_review`;
- material scope changes require `behavior_changed`, explicit user approval, evidence invalidation, and a review-round reset;
- material public-contract changes require the next implementation report to use review round zero.

### Commands and results

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/validate_packet.py
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py' skills/gpt-pro-codex-loop
```

All commands exited 0. The focused validator suite reported `Ran 18 tests` followed by `OK`; bytecode compilation succeeded; and direct Skill validation reported `Skill is valid!`.

### Self-review

- Removed the unused `req_errors` path and propagated dependency validation errors with stable `requirements.` and `report.` field prefixes.
- Ensured CLI validation becomes nonzero when a supplied requirements dependency is malformed.
- Added explicit material-revision fields and enforced approval, superseding-digest validation (when the prior packet is supplied), prior-evidence invalidation, and zero review round for the next report.
- Confirmed `git diff --check` before committing and changed no Task 3+ deliverables.

### Commit

`5d2a122 Harden GPT Pro packet dependencies`

## Fix Round 2

### Changed files

- `skills/gpt-pro-codex-loop/scripts/validate_packet.py`
- `evals/gpt-pro-codex-loop/test_validate_packet.py`

The paused Task 4 Skill, UI metadata, README, evaluation README, and reference changes were not edited or staged.

### RED evidence

After adding the routing, round-accounting, blocker-continuity, initial-revision, and PASS-gate tests, the focused command exited 1 with nine failures:

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
```

Failures covered missing initial-revision enforcement, PASS accepting findings/scope violations, `decision`/`latest_decision` routing mismatch, missing exact round increments, and incorrect blocker continuity. A subsequent round-zero boundary test also failed before the continuity condition was tightened.

### GREEN commands and results

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/validate_packet.py
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py' skills/gpt-pro-codex-loop
git diff --check
```

All commands exited 0. Packet validation reported `Ran 28 tests` and `OK`. Snapshot validation reported `Ran 16 tests` and `OK (skipped=1)`; the skip is the expected POSIX case-sensitive-path test on Windows. Compilation and direct Skill validation passed, and `git diff --check` was clean.

### Self-review

- Review routing now consumes required `latest_decision` and never reads the obsolete state `decision` field.
- Each routed valid review increments `review_round` exactly once; evidence resubmission, Browser reconnect, and first format correction preserve it.
- Consecutive blocker enforcement compares both stable finding IDs and root-cause fingerprints only between round-coupled valid reviews; round zero and nonconsecutive occurrences do not trigger the stop.
- Valid review consumption requires explicit stable-ID and fingerprint history arrays, preventing omitted history from bypassing continuity checks.
- Initial public requirements validation requires revision 1 and no superseding digest, while report/review dependency validation retains a schema-only path for later revisions.
- `PASS` now requires empty findings and empty scope violations, including non-BLOCKER action findings.
- Only the two Task 2 files were staged and committed.

### Commit

`8dacead Fix GPT Pro review state validation`

### Concerns

None within Task 2. The unrelated paused Task 4 worktree changes remain present and unstaged for their owning task.

## Fix Round 3

### Changed files

- `skills/gpt-pro-codex-loop/scripts/validate_packet.py`
- `evals/gpt-pro-codex-loop/test_validate_packet.py`

### RED evidence

The focused packet command exited 1 with two failures after adding authoritative-history precedence and legacy-compatibility regressions:

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
```

An explicitly present empty authoritative history incorrectly fell back to stale `unresolved_findings`, while truly absent authoritative fields rejected a valid legacy history.

### GREEN commands and results

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/validate_packet.py
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py' skills/gpt-pro-codex-loop
git diff --check
```

All commands exited 0. Packet validation reported `Ran 30 tests` and `OK`. Snapshot validation reported `Ran 16 tests` and `OK (skipped=1)` with the expected Windows POSIX-path skip. Compilation, Skill validation, and diff checks passed.

### Self-review

- Authoritative `unresolved_finding_ids` and `blocker_fingerprints` now win whenever their fields are present, including explicit empty arrays that clear continuity.
- Legacy `unresolved_findings` fallback is used only when the corresponding authoritative field is absent.
- Legacy IDs and fingerprints are shape-validated before they can satisfy valid-review history requirements.
- Only the Task 2 validator and test files were staged; paused Task 4 files were not edited or staged.

### Commit

`3b63f0e Fix blocker history precedence`

### Concerns

None within Task 2. Paused Task 4 changes remain unstaged for their owning task.

## Fix Round 4

### Changed files

- `skills/gpt-pro-codex-loop/scripts/validate_packet.py`
- `evals/gpt-pro-codex-loop/test_validate_packet.py`
- `.superpowers/sdd/2026-07-29-gpt-pro-codex-loop/task-2-report.md`

The paused Task 4 Skill, UI metadata, README, evaluation README, and reference
changes were not edited or staged.

### RED evidence

Each transition behavior was introduced as a focused failing test through the
public `validate_transition(previous, current)` seam:

- the approved material revision test rejected the legal round-two-to-zero
  requirements freeze with
  `review_round: non-review transitions must preserve the review round`;
- requirements `NEED_USER_INPUT` and `BLOCK` routes were illegal, and wrong
  requirements routing was not detected;
- bound conversation URL/model drift and missing identity were accepted;
- phase-string shorthand was accepted and omitted state fields silently
  defaulted;
- self-review added a final RED regression showing that a non-requirements
  `BLOCKED` state could resume as though it were a requirements unblock.

Every focused RED command exited 1 for the intended assertion before its
corresponding validator change.

### GREEN commands and results

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/validate_packet.py
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py' skills/gpt-pro-codex-loop
git diff --check
```

All commands exited 0. Packet validation reported `Ran 34 tests` and `OK`.
Snapshot validation reported `Ran 16 tests` and `OK (skipped=1)` with the
expected Windows POSIX-path skip. Compilation, direct Skill validation, and
diff checks passed.

### Self-review

- A valid review can route to requirements revision and consume exactly one
  round; the subsequent requirements freeze resets to zero only for the
  explicit approved material-revision flags. Unapproved and arbitrary resets
  remain invalid.
- Requirements `NEED_USER_INPUT` and `BLOCK` route to
  `USER_DECISION_REQUIRED` and `BLOCKED`; guarded resumes return to
  `REQUIREMENTS_PENDING` without consuming a review round.
- Transition validation now accepts only complete state objects. Review-round
  values, decision fields, action lists, maintenance counters, binding fields,
  and revision-reset approval fields cannot be omitted and silently defaulted.
- The initial unbound-to-bound requirements conversation is explicit. Once
  bound, the conversation URL and visible model label must remain present and
  byte-for-byte unchanged.
- Removed redundant required-field presence checks identified during the
  standards review. Existing latest-review decision routing, PASS gates,
  approved revision validation, and authoritative/legacy blocker continuity
  tests remain green.
- Only the two Task 2 implementation/test files and this report are intended
  for staging.

### Concerns

None within Task 2. Paused Task 4 changes remain present and unstaged for their
owning task.

## Fix Round 5

### Changed files

- `skills/gpt-pro-codex-loop/scripts/validate_packet.py`
- `evals/gpt-pro-codex-loop/test_validate_packet.py`
- `.superpowers/sdd/2026-07-29-gpt-pro-codex-loop/task-2-report.md`

The concurrent Task 4 Skill, UI metadata, README, evaluation README, and
reference changes were not edited or staged by this round.

### RED evidence

The first focused run after adding the reset- and stop-provenance regressions
reported `Ran 42 tests` and failed 29 assertions. The failures were specific to
the old validator accepting self-asserted reset flags, missing or mismatched
revision provenance, stale-label stop resumes, missing resolution evidence,
retained stop provenance, and omitted required state fields.

Subsequent focused RED cycles caught and proved the breaker-round edge cases:

- non-material evidence invalidation was incorrectly treated as a material
  round reset;
- Browser-reconnect maintenance, non-requirements phases, and preflight could
  inject pending material-reset authority;
- active requirements provenance could remain null or be injected late;
- resolution evidence was not bound to a unique stop instance; and
- a prior approval event could be replayed against a later requirements
  digest.

Each targeted command exited 1 for its intended assertion before the matching
validator change. The independent breaker review reproduced the lifecycle,
active-provenance, resolution-replay, and approval-replay holes before their
fixes.

### GREEN commands and results

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/validate_packet.py
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py' skills/gpt-pro-codex-loop
git diff --check
```

All commands exited 0. Packet validation reported `Ran 50 tests` and `OK`.
Snapshot validation reported `Ran 16 tests` and `OK (skipped=1)` with the
expected Windows POSIX-path skip. Compilation, direct Skill validation, and
diff checks passed.

### Self-review and breaker review

- Material reset authority now belongs to a phase-scoped pending revision:
  active revision/digest are immutable after their one allowed initialization;
  pending revision is exactly next, has a new digest, and supersedes the active
  digest.
- Material flags match the requirements validator semantics. Approval is bound
  to the pending digest and a monotonic approval sequence with explicit
  evidence; evidence invalidation and reset are required.
- Freezing promotes active revision/digest and approval sequence, resets the
  review round to zero only for a material revision, and consumes every pending
  provenance and authorization field. Maintenance and unrelated phases cannot
  inject or mutate that authority.
- Stop entry records the actual origin phase, route category, reason, and a
  monotonic stop sequence. Resume targets are category-specific, preserve the
  review round, require evidence bound to that exact stop sequence, and consume
  origin provenance. The next transition must clear the resolution binding.
- Exact revision reset replay, stale approval replay, stale decision-label
  routing, wrong-origin resume, and nonadjacent resolution replay all fail
  closed in a validated state chain.

### Concerns

DONE_WITH_CONCERNS. The final independent breaker pass found that approval or
resolution evidence could be reused if a party able to rewrite Codex-owned
local control artifacts also relabeled it with the expected next
sequence/digest. The controller parked this as a real but out-of-scope
adversarial-local-state concern: untrusted inputs are Pro browser packets,
whereas state and events are trusted Codex-owned control artifacts. This
validator guarantees transition continuity and stale-metadata detection; it
does not provide cryptographic authenticity against arbitrary local-state
rewrites. Literal protection would require signed or append-only trusted
storage outside the approved Skill scope. Task 4 must document this trust
boundary and preserve raw responses/events.
