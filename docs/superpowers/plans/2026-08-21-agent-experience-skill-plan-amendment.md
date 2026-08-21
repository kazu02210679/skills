# Agent Experience Skill — Implementation Plan Amendment

> **For agentic workers:** This document is binding on the existing `2026-08-21-agent-experience-skill.md` plan. Apply these changes before writing production code.

**Normative contract:** `docs/superpowers/specs/2026-08-21-agent-experience-skill-normative-contract.md`

**Purpose:** Remove remaining implementation discretion identified by the post-amendment Codex review: checkpoint compatibility, record staleness, promotion evidence, contested projection, and Hook behavior.

---

## 1. Global plan amendments

Add these constraints to the existing plan:

- `branchRef` participates in exact checkpoint identity. Same HEAD on a different branch is never `exact`.
- rebase that breaks checkpoint-HEAD ancestry is `stale` in v1 even when scoped file bytes happen to match.
- another clone or another worktree can never be `exact`; at best it is `manual_review_compatible`.
- checkpoint age does not by itself make a checkpoint stale; compatibility does.
- historical observation/outcome age does not by itself make those records stale.
- adopted knowledge loses adopted applicability when its target artifact digest no longer validates.
- `contested` is projection-only; no origin record may self-declare it.
- `candidate -> verified` requires the exact verification basis in the Normative Contract.
- `verified -> adopted` records an already-reviewed target change; `promote` never edits the target artifact.
- automatic Hook setup is allowed only for a tested Codex host contract. Unknown host schemas fall back to manual mode.
- Hook crash handling guarantees only transaction-committed local state; no claim of lossless current-turn capture.

---

## 2. Task 5 amendment — Repository/worktree identity

Extend `RepositoryIdentity` with a canonical branch identity and worktree-local UUID.

Required interface:

```python
@dataclass(frozen=True)
class RepositoryIdentity:
    repo_id: str
    worktree_id: str
    branch_ref: str
    head: str
```

Required RED cases:

```text
same repo config in another clone -> same repo_id, different worktree_id
second git worktree -> different worktree_id
branch switch at same HEAD -> branch_ref changes
Detached HEAD -> DETACHED:<sha>
restart same worktree -> worktree_id stable
copied local DB into another worktree -> binding mismatch, reject
```

`worktree_id` is local-only and must never be inferred from branch name, absolute path string alone, or remote URL.

---

## 3. Task 6 amendment — Compatibility predicate

Replace prose-only classification with table-driven tests for the Normative Contract decision order.

Required helper:

```python
def classify_checkpoint(
    checkpoint: CheckpointFingerprint,
    current: RepositorySnapshot,
) -> Compatibility:
    ...
```

Required reason codes:

```text
snapshot_unavailable
repo_mismatch
worktree_changed
branch_changed
head_advanced
head_lineage_broken
index_changed
tracked_worktree_changed
untracked_changed
scope_changed
mode_changed
symlink_changed
submodule_changed
unsafe_git_state
out_of_scope_only_changed
```

Required RED/GREEN matrix:

```text
same everything -> exact / auto_resume true
branch renamed/switched, same HEAD/scope -> manual_review_compatible
HEAD descendant, scope same -> manual_review_compatible
rebase, no ancestry -> stale
new clone, same HEAD/scope -> manual_review_compatible
second worktree, same HEAD/scope -> manual_review_compatible
staged/index delta -> stale
scope content/mode/symlink/submodule delta -> stale
unstable/unmerged capture -> unavailable
repo ID mismatch -> stale and excluded from default checkpoint recall
```

Assert classification is deterministic and first-match ordered.

---

## 4. Task 13 amendment — Per-kind staleness and precedence

Do not implement one generic `revalidate_after => stale` rule for every record kind.

Add tests for the Normative Contract record-kind matrix.

Required projection precedence:

```text
invalid/excluded
> superseded/deprecated
> contested
> stale
> normal effective state
```

Required cases:

```text
checkpoint 180 days old but exact snapshot -> checkpoint compatibility remains exact
observation 180 days old -> still observed; applicability may filter it
knowledge past revalidate_after -> stale
verified knowledge with invalid required evidence -> stale
adopted knowledge target digest changed -> stale
active decision premise digest changed -> stale
outcome age alone -> still recorded
promotion record age alone -> still committed event
invalid outcome target digest -> outcome excluded, not target contested
```

Add explicit fields/relations for decision premise digest binding where the decision depends on mutable artifacts.

---

## 5. Task 14 amendment — Promotion minimum conditions

Extend promotion schema/input with:

```text
verification_basis:
  two_independent_evidence | human_review

workstream_id on evidence provenance
current_validation_locator
counterconditions
failure_conditions
```

Required tests for `candidate -> verified`:

```text
one agent observation only -> reject
same evidence duplicated -> reject
two records from same workstream only -> reject
two independent workstreams + current validation -> accept
human review + no current validation evidence -> reject
human review + current validation -> accept
unresolved contested/harmful -> reject
missing counterconditions/failure conditions -> reject
```

Required tests for `verified -> adopted`:

```text
no target artifact -> reject
target artifact digest missing -> reject
no exact commit/PR locator -> reject
repository review/acceptance missing -> reject
current target digest mismatch -> reject
valid reviewed Skill/AGENTS/spec/runbook change -> accept
```

`promote` never writes target Skill/AGENTS/spec/runbook files.

---

## 6. Task 16 amendment — Contested generation

Clarify that local `harmful` feedback and shared contested state are separate.

Required tests:

```text
local harmful feedback -> immediate local suppression only
local harmful feedback without seal -> shared projection unchanged
sealed harmful outcome with exact target digest/current evidence -> target contested
sealed contradicts relation with exact target digest -> target contested
CLI cannot create contested by passing status='contested'
malformed/digest-mismatched contradiction -> excluded
contested record stays excluded from default recall
corrected replacement superseding old contested record -> replacement follows normal candidate lifecycle
```

CLI responsibilities are structural only. Semantic contradiction must originate from structured Skill/user/agent input and pass normal seal validation.

---

## 7. Task 18 amendment — Hook normative contract

Before coding Hook handlers, freeze a test fixture representing the then-current official Codex Hook contract and record the tested Codex version/contract version in `skills/agent-experience/references/host-adapters.md`.

Required normalized adapter contract:

```text
SessionStart: session_id, source=startup|resume|clear|compact
PreCompact: session_id, trigger=manual|auto
PostCompact: session_id, trigger=manual|auto
SessionEnd: session_id, reason
```

Required tests:

```text
unknown newer host contract -> automatic hooks disabled/manual mode available
missing required event/source semantics -> installer refuses automatic lifecycle
extra future host fields -> ignored and not persisted
transcript_path supplied -> never read/persisted
SessionStart -> fixed routing notice only
PreCompact/PostCompact/SessionEnd -> empty stdout/stderr
DB lock/read failure -> exit 0/no model-visible output/stable local code only
process crash after prior committed checkpoint -> prior checkpoint survives
in-flight semantic state at crash -> no lossless-capture claim
SessionEnd failure -> ordinary work not blocked
```

No Hook handler may invoke network, LLM, recall, shared scan, reindex, Git mutation, `seal`, `promote`, or `gc`.

---

## 8. Task 19 amendment — Installer host-contract gate

Installer plan must distinguish three outcomes:

```text
hooks_ready
manual_mode_only
installation_conflict
```

Rules:

- `hooks_ready`: tested host contract matches and representation/preimage checks pass.
- `manual_mode_only`: host Hook contract unavailable/unsupported; no guessed Hook entry is installed.
- `installation_conflict`: mixed representation, drift, ambiguous owner, unsafe path; mutation fails closed.

`manual_mode_only` is not repository task failure. `agent-experience preflight/checkpoint/recall` remain available.

---

## 9. Task 24 amendment — Pilot acceptance

Add five mandatory decision-contract gates to the final pilot:

```text
checkpoint compatibility matrix: all cases green
record-kind staleness matrix: all cases green
promotion evidence matrix: all cases green
contested generation/resolution matrix: all cases green
Hook host/failure/crash matrix: all cases green on supported host
```

Pilot report must include exact tested Codex host version and whether automatic hooks were `hooks_ready` or `manual_mode_only`.

A `manual_mode_only` host may pass the Memory Core/Skill pilot, but may not be reported as automatic lifecycle support.

---

## 10. Implementation readiness

With the Normative Runtime Contract and this plan amendment accepted, the conceptual design has no known unresolved blocker for **Phase 1 Manual Local Checkpoint MVP**.

This does not authorize skipping TDD or jumping to Hooks. Execution remains:

```text
Phase 0 RED contracts
  -> Phase 1 manual checkpoint MVP
  -> Phase 2 shared records/projection/recall
  -> Phase 3 route-only Hooks/installer
  -> Phase 4 promotion/adapters
  -> Phase 5 pilot
```

If official Codex Hook behavior differs when Task 18 begins, amend only the host adapter contract; do not weaken memory authority, privacy, or fail-open/fail-closed boundaries to force compatibility.