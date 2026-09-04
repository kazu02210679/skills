# Agent Experience v1 — Execution Readiness Clarification

- **Document date:** 2026-08-23
- **Target:** `agent-experience` v1
- **Status:** Binding clarification; formal design closure still required
- **Source review:** `docs/superpowers/reviews/2026-08-23-agent-experience-execution-readiness-review.md`

## 0. Authority and scope

This document closes implementation-readiness ambiguity without widening runtime authority. In the following domains it overrides less specific earlier prose:

- design-entry and Task-1 readiness;
- implementation-progress accounting;
- trusted bootstrap-approval support boundary;
- Policy candidate/change/evaluation command flow;
- remote `use_context_id` lifetime;
- Hook/installer start conditions and host-contract discovery;
- design-closure and implementation-closure invalidation;
- CLI failure envelope and human-facing recovery guidance;
- treatment of pre-acceptance staged/unstaged implementation work.

It does not make Task 1 ready by its own existence.

---

## 1. One canonical implementation-entry state

### 1.1 State model

```text
DESIGN_REVIEW_PENDING
DESIGN_CLOSED
OWNER_ACCEPTANCE_PENDING
IMPLEMENTATION_READY
IMPLEMENTATION_IN_PROGRESS
IMPLEMENTATION_PAUSED
IMPLEMENTATION_REVIEW
IMPLEMENTATION_CLOSED
```

These are process states. Repository prose, an audit JSON, a local variable, or an old review cannot self-select a later state.

### 1.2 Task-1 readiness formula

Task 1 is `READY` if and only if all of the following are true at the same time:

```text
formal design-closure artifact exists
closure reviewer satisfies the independence contract
closure binds the exact current Contract Index blob
closure binds the exact current active-plan blob
closure binds every other binding design blob required by the Index
closure records every required Critical/Important finding as verified_closed or reasoned_rejected
repository owner explicitly accepts that exact closed design after closure
owner acceptance binds the same reviewed branch/commit and design blob set
no binding design file changed after closure/acceptance
```

Otherwise Task 1 is `BLOCKED`.

Equivalent predicate:

```text
Task1Ready = ValidDesignClosure(current_design_digest_set)
             AND ValidOwnerAcceptance(current_design_digest_set,
                                     design_closure_digest)
```

There is no third state in which a repository audit file that says `approved` makes Task 1 ready by itself.

### 1.3 Current PR #35 interpretation

Until a valid formal design-closure artifact and matching explicit owner acceptance exist for the final PR head, the official state is:

```text
DESIGN_REVIEW_PENDING
Task 1 = BLOCKED
```

The old plan sentence `Task 1 remains NO-GO` is therefore not a stale historical note; it is the correct computed state until the gate changes.

### 1.4 Invalidation

Any byte change to a binding design artifact listed by the Contract Index after design closure invalidates:

```text
design closure
owner acceptance bound to that closure
Task1Ready
```

Non-binding operational status updates do not invalidate design closure unless they change a binding contract.

---

## 2. Implementation-progress ledger

### 2.1 Required path

The implementation branch maintains:

```text
docs/superpowers/status/agent-experience-implementation.json
```

This is operational state, not a design authority document.

### 2.2 Task status enum

```text
BLOCKED
READY
IN_PROGRESS
VERIFYING
DONE
PAUSED
SUPERSEDED
```

### 2.3 Minimum task entry

```json
{
  "task_id": 1,
  "title": "Observable RED baseline including all review exploits",
  "status": "BLOCKED",
  "implementation_commit_sha": null,
  "red_evidence": [],
  "green_evidence": [],
  "review_locators": [],
  "changed_paths": [],
  "blockers": ["design_entry_gate"],
  "updated_at": "YYYY-MM-DDTHH:MM:SSZ"
}
```

### 2.4 Completion rule

A Task becomes `DONE` only when all applicable evidence exists:

```text
production/test changes are committed on the accepted implementation branch
commit is descendant of the implementation baseline
changed paths are mapped to that Task
required focused RED was observed for the intended reason, or the Task is explicitly a baseline-only Task
required GREEN command passed at the committed implementation state
Task exit gate in the active plan is satisfied
no staged/unstaged change is required for the claimed behavior
review evidence required by that Task is present
```

A file existing in a working tree is not Task completion evidence.

### 2.5 Dirty and local-only work

```text
staged or unstaged implementation code
untracked implementation files
local commits not pushed to the tracked implementation branch
```

may be recorded as:

```text
prototype_unverified
```

but never as `DONE`.

The authoritative GitHub progress ledger records only evidence observable from the designated implementation branch. A local progress inspector may additionally show `prototype_unverified` items, but must label their provenance as local-only.

### 2.6 Next Task selection

The controller selects the lowest Task whose predecessors are `DONE` and whose explicit blockers are cleared. Parallel Tasks require an explicit plan dependency allowing concurrency; Task number alone does not create a parallel lane.

The controller never infers Task completion from file names such as `store.py` or `controller.py`.

---

## 3. Trusted bootstrap approval provider: v1 support boundary

### 3.1 Closed decision

V1 ships **no built-in trusted approval issuer**.

The following are not trusted bootstrap issuers merely because they exist:

```text
Codex itself
GitHub CLI
GitHub repository files
GitHub comments or reviews by themselves
owner-acceptance JSON stored in the repository
interactive or pseudo-TTY text
```

### 3.2 What Task 20 implements

Task 20 implements:

```text
approval-provider verifier SPI
closed VerifiedBootstrapApproval type
trusted local issuer registry boundary
opaque receipt-locator verification flow
candidate Policy generation
bootstrap mutation-plan generation
replay/expiry/binding checks
no-provider fallback
```

Task 20 does not implement a receipt issuer.

### 3.3 Production behavior without an outer adapter

When no independently reviewed outer-controller adapter is configured:

```text
policy bootstrap-candidate -> supported
policy bootstrap activation -> bootstrap_manual_governance_required
```

This is a supported v1 outcome, not an incomplete Task-20 implementation.

### 3.4 Future adapters

A future adapter may use a HOTL/controller or host-native user-approval mechanism only if it can verify an opaque receipt through a boundary that target-repository bytes cannot configure or mint. That adapter is separately reviewed.

### 3.5 Design owner acceptance is different

The pre-Task-1 repository-owner acceptance gate is a human process gate tied to formal design closure. It is not the runtime Acceptance Policy bootstrap provider and must not be conflated with Task 20.

---

## 4. Policy-change execution path

### 4.1 V1 CLI surface

```text
agent-experience policy status --json
agent-experience policy bootstrap-candidate --input <policy.json> --dry-run --json
agent-experience policy bootstrap-candidate --input <policy.json> --apply --plan-digest <digest> --json
agent-experience policy change-candidate --input <policy.json> --dry-run --json
agent-experience policy change-candidate --input <policy.json> --apply --plan-digest <digest> --json
agent-experience policy evaluate-change --candidate <path> --refresh --json
agent-experience policy materialize-successor --candidate <path> --apply --plan-digest <digest> --json
agent-experience policy verify-lineage --refresh --json
```

No command commits, pushes, opens a PR, approves, or merges.

### 4.2 Predecessor resolution

`change-candidate` and `evaluate-change` do not accept a caller-supplied predecessor as authority.

They resolve the current active predecessor from:

```text
current target repository
configured authoritative ref
current Policy pointer
immutable Policy revision path/blob
validated repository binding
current read-only GitHub provider evidence
```

If the authoritative predecessor cannot be resolved completely:

```text
status = unknown | unavailable | inconsistent
eligible = false
```

### 4.3 Change-evaluation flow

```text
current active P(n)
   -> create candidate P(n+1)
   -> current GitHub refresh for candidate PR/reviews/check-runs
   -> evaluate P(n).policy_change against complete current evidence
   -> verify lineage/base-head/candidate digest
   -> result
```

Allowed evaluation result states:

```text
eligible
pending
not_eligible
unknown
unavailable
inconsistent
```

`eligible` still does not perform Git writes outside candidate materialization.

### 4.4 Provider ownership

Task 19's trusted local GitHub CLI provider supplies read-only repository, PR, review, check-run, ref, and file observations. Task 21 consumes only normalized complete provider results. `policy.py` does not issue arbitrary GitHub requests itself.

### 4.5 Candidate resubmission

If a candidate fails or is rejected before it becomes the authoritative active successor:

- the active predecessor remains unchanged;
- a corrected candidate uses the same required successor revision number `P(n)+1` but a new candidate digest and validation SHA;
- the old candidate is historical evidence only;
- it must not remain selected by the active pointer;
- if multiple competing successors are simultaneously reachable as authoritative successor candidates, result is `policy_lineage_inconsistent` until current evidence identifies one valid authoritative successor under the closed lineage rule.

The tool never silently edits an immutable published Policy revision.

---

## 5. Remote refresh and `use_context_id`

### 5.1 Ownership

`use_context_id` is created by the deterministic controller for one top-level decision operation. Callers cannot supply or reuse an arbitrary `use_context_id` as current-evidence authority.

### 5.2 Lifetime

A use context begins when one of these commands starts a current remote decision:

```text
remote refresh
remote accepted-artifact
policy evaluate-change --refresh
policy verify-lineage --refresh
remote-dependent preflight/continuation
```

It ends when that top-level command returns, aborts, or reaches its operation deadline.

Therefore:

```text
new CLI invocation -> new use_context_id
new Codex task -> new use_context_id
post-compaction new command -> new use_context_id
resume after process exit -> new use_context_id
```

Compaction itself does not preserve current remote evidence.

### 5.3 Refresh run

Each provider batch attempt receives a distinct:

```text
refresh_run_id
```

A single top-level command may perform more than one bounded provider batch under the same `use_context_id`; each batch gets a new `refresh_run_id`. Results remain current only for that command's decision.

### 5.4 Same-command rule

`same-command remote continuation` means:

```text
create use_context
-> fetch current dependencies
-> validate completeness/bindings
-> atomically record observations and decision digest
-> decide continuation
-> return
```

A stored result from a prior command cannot be promoted back into current evidence by replaying its `use_context_id`.

### 5.5 Persistence

Historical observations may store `use_context_id` and `refresh_run_id` for correlation, but these identifiers never extend freshness. They are audit/correlation identifiers only.

---

## 6. Hook and installer implementation start conditions

### 6.1 File absence before Tasks 24-26

Before Task 24, absence of:

```text
hooks.py
installer.py
uninstall behavior
active Hook configuration
```

is correct and must not be reported as an earlier-Task implementation defect.

### 6.2 Task gates

```text
Tasks 1-17 DONE -> Memory Core eligible
Tasks 18-19 DONE -> Remote Observation MVP eligible
Tasks 20-23 DONE -> Remote Governance gate green
only then -> Task 24 Hooks may begin
Task 24 DONE -> Task 25 installer may begin
Task 25 DONE -> Task 26 uninstall may begin
```

### 6.3 Host-contract probe

Task 24 begins by freezing the supported installed Codex Hook contract into a local test receipt derived from reviewed authoritative host documentation/runtime capability. The implementation does not guess a schema from old examples.

Minimum receipt fields:

```text
Codex version
Hook contract version
supported events
input fields per event
timeout/config representation
stdout/stderr/additional-context behavior
configuration file representation tested
recorded-at
```

If the installed/authoritative contract is unsupported or ambiguous:

```text
hook_contract_unsupported
manual mode remains available
installer is not applied
```

### 6.4 Ownership

Exactly one local Hook owner is active per repository:

```text
user
project
none
```

Project ownership does not silently replace user ownership. Migration requires the explicit owner-migration flow and conflict-safe install plan.

---

## 7. Design closure and implementation closure

### 7.1 Design closure target

Design closure targets a clean committed documentation PR head and the exact binding blob/digest set from the Contract Index.

It does not target staged/unstaged working-tree bytes.

### 7.2 Reuse of design closure during implementation

An implementation commit may descend from the accepted design baseline without repeating design closure if and only if the binding design corpus is byte-identical to the accepted design set.

If an implementation change modifies any binding design/spec/active-plan artifact:

```text
implementation state -> PAUSED
prior design closure -> invalid for new design
prior owner acceptance -> invalid for new design
new independent design closure required
new owner acceptance required
```

Tests/code may not silently redefine the contract.

### 7.3 Implementation baseline

The official implementation branch is created only after the documentation PR is accepted/merged and Task-1 entry gate is satisfied. The implementation baseline is the clean accepted `main` commit from which that dedicated implementation branch is created.

The documentation branch head itself is not the implementation baseline.

### 7.4 Implementation closure target

Implementation closure targets exactly one clean committed implementation HEAD.

Requirements:

```text
clean index and worktree
HEAD is descendant of accepted implementation baseline
binding design digest set is still accepted
Task ledger has required Tasks DONE
full verification results bind the same HEAD
pilot evidence binds the same HEAD
no required behavior exists only in staged/unstaged files
```

Dirty working trees cannot receive implementation closure.

### 7.5 Closure invalidation

Any post-closure code/test/config change invalidates implementation closure for rollout. Any binding-design change additionally invalidates design closure and owner acceptance.

---

## 8. Standard failure contract

### 8.1 Machine JSON envelope

Every explicit CLI command uses this outer shape for non-success results:

```json
{
  "schema_version": 1,
  "ok": false,
  "status": "blocked",
  "code": "preflight_expired",
  "message": "The operation-specific preflight receipt expired.",
  "retryable": true,
  "next_action": "run_preflight",
  "operation_id": "local-correlation-id",
  "details": {}
}
```

Rules:

- `message` is stable, short, and safe for humans.
- `details` uses a closed schema per error code.
- no raw exception, prompt, token, response body, absolute path, username, or credential appears.
- `operation_id` is local correlation only and is never authority.

### 8.2 Exit-code classes

```text
0 success / empty result / automatic Hook no-op
2 invalid argument or closed-schema violation
3 degraded / unavailable / partial / unsupported capability
4 integrity / unsafe path / digest / identity violation
5 stale receipt / transaction conflict / explicit lock timeout / recovery-required mutation
```

### 8.3 Required mappings

| Situation | Explicit CLI exit | Code | Human next action |
|---|---:|---|---|
| preflight missing | 5 | `preflight_required` | run preflight |
| preflight expired | 5 | `preflight_expired` | run a fresh preflight |
| provider not configured | 3 | `provider_not_configured` | run provider setup or continue local-only |
| remote partial | 3 | `remote_partial` | inspect unknown resources and retry refresh |
| remote unavailable | 3 | provider-specific safe code | retry later / use historical data only |
| unknown Hook contract in explicit doctor/setup | 3 | `hook_contract_unsupported` | stay in manual mode |
| unknown Hook contract during automatic Hook invocation | 0 | no model-visible error | local diagnostic only |
| SQLite lock timeout in explicit mutation | 5 | `local_store_busy` | retry; do not claim mutation |
| SQLite lock timeout in Hook hot path | 0 | no output | local diagnostic only |
| corruption/recovery required for mutation | 5 | `recovery_required` | run doctor/recovery workflow |
| read-only status during recovery-required state | 3 | `recovery_required` | inspect recovery state |
| digest/repository/provider executable mismatch | 4 | stable integrity code | stop and repair trust binding |

### 8.4 Human output

Without `--json`, print only:

```text
<code>: <safe message>
Next: <safe action>
```

Detailed diagnostics remain local, bounded, and secret-safe.

---

## 9. Pre-acceptance prototype adoption

### 9.1 Classification

Implementation code written before the official entry gate or existing only as staged/unstaged local changes is:

```text
prototype_unverified
```

It is neither discarded automatically nor counted as completed implementation.

### 9.2 Adoption workflow

After the implementation gate is satisfied:

1. create a dedicated implementation branch from the accepted implementation baseline;
2. capture the prototype diff without secrets or unrelated local state;
3. map each changed file/hunk to one or more active-plan Tasks;
4. reject changes with no Task/contract mapping;
5. for each Task, establish the planned failing test on the accepted branch;
6. replay or transplant only the minimal implementation needed for that Task;
7. run focused GREEN and regression gates;
8. commit in Task-scoped commits;
9. update the progress ledger with commit/test evidence;
10. leave unmatched prototype changes out of the implementation branch until separately reviewed.

### 9.3 No baseline laundering

Do not set a pre-acceptance dirty working-tree HEAD as the implementation baseline merely because code already exists there. Do not mark Tasks complete retroactively from file presence.

---

## 10. Required new RED/GREEN cases

The implementation plan must cover at least:

```text
task1_gate_false_without_formal_closure
task1_gate_false_without_owner_acceptance
design_change_invalidates_closure_and_acceptance
uncommitted_file_does_not_complete_task
prototype_requires_task_mapping
no_builtin_bootstrap_issuer_is_supported_state
caller_use_context_id_rejected
new_command_gets_new_use_context
same_command_multiple_refresh_runs_share_context
prior_use_context_cannot_make_old_refresh_current
policy_change_reads_authoritative_predecessor
policy_rejected_candidate_resubmission_has_new_digest
policy_competing_successors_inconsistent
hooks_absent_before_task24_is_expected
unsupported_hook_contract_keeps_manual_mode
implementation_closure_rejects_dirty_worktree
binding_design_change_pauses_implementation
error_envelope_contains_no_raw_exception_or_absolute_path
hook_lock_timeout_is_silent_fail_open
explicit_lock_timeout_is_exit5_fail_closed
```

---

## 11. Immediate repository status after this clarification

Because this clarification changes the binding design set, any design-closure or owner-acceptance evidence bound only to the prior head is stale.

Until the new exact PR head receives formal independent design closure and subsequent explicit repository-owner acceptance:

```text
PR #35: documentation review
Task 1: BLOCKED
Implementation branch: not established on GitHub
GitHub-verifiable runtime Tasks DONE: 0
Local unpushed/staged implementation: prototype_unverified if it exists
```

This status may advance only through the evidence rules above.
