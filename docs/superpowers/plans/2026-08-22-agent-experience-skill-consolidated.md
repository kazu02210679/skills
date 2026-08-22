# Agent Experience Skill Consolidated Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task. Every production behavior starts with a focused failing test. Use `superpowers:using-git-worktrees` before production changes and `superpowers:verification-before-completion` before any readiness claim.

**Goal:** Build an independent `agent-experience` Skill that resumes exact local work safely, stores selected immutable advisory experience, retrieves only bounded relevant records, revalidates mutable GitHub state through a trusted read-only provider, and never turns memory, imported data, repository files, or acceptance results into execution authority.

**Architecture:** Build the local identity, snapshot, receipt, and checkpoint core first. Add immutable shared records, projection, recall, feedback, and retention second. Freeze typed remote contracts before implementing the locally trusted GitHub CLI provider. Add provider-mediated bootstrap approval and immutable Policy lineage before accepted-artifact evaluation and remote continuation. Add route-only Hooks and installer mutation only after all memory and remote gates are green.

**Tech Stack:** Python 3.11+ standard library, Git CLI, SQLite/FTS5 with deterministic lexical fallback, immutable Markdown/JSON records, optional locally trusted GitHub CLI `gh`, GitHub Actions on Ubuntu and Windows.

**Spec entry point:** `docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md`

---

## Implementation Entry Gate

Do not start Task 1 until both conditions hold:

1. `docs/superpowers/reviews/2026-08-23-agent-experience-design-closure.md` exists, binds the exact current design artifacts, and records every original and reconciliation finding as `verified_closed` or `reasoned_rejected`.
2. The repository owner explicitly accepts that exact closed design in the active host interaction or through a trusted approval provider.

The following do **not** satisfy the entry gate:

```text
authoring-side remediation
an authoring-side closure preflight
repository JSON claiming owner approval
an old closure review bound to another commit/blob
an implementation closure review
```

---

## Global Constraints

- Read every binding document listed by the Contract Index before implementing a Task.
- This file is the sole active implementation plan. Older plans are historical pointers.
- Runtime code uses Python 3.11+ standard library only.
- Every production behavior begins with a focused failing test, then minimal implementation, then green-preserving refactor.
- Experience records, imported observations, sealed records, accepted-artifact results, and provider receipts are untrusted advisory data and never execution authority.
- Origin knowledge starts only as `candidate`; effective state is replayed from validated transitions.
- Shared records are immutable. Corrections use new records and digest-bound relations.
- Mutable remote observations never become verified or adopted knowledge.
- Raw prompt, transcript, raw tool output, raw diff, raw provider body, credentials, tokens, cookies, credential-bearing URLs, hidden reasoning, absolute home paths, and usernames are not persisted by default.
- Tracked repository configuration cannot select or parameterize an executable, wrapper, command, environment, extension, URL, method, GraphQL query, or arbitrary argument list.
- Provider executable identity is local-only, absolute, outside repository-controlled paths, non-symlink/non-reparse, and digest/file-identity verified before each use.
- GitHub Provider v1 is GitHub.com, GET-only, typed-operation-only, and read-only.
- Pagination-dependent predicates require a complete collection. Partial pagination never passes.
- Agent Experience Policy v1 evaluates check runs only. Commit-status parity and last-push approval are unsupported.
- Policy bootstrap cannot be activated by TTY input, repository bytes, unsigned audit records, self-declared human JSON, or agent-authored approval text.
- Policy revisions use one immutable lineage, monotonic revision numbers, exact predecessor binding, predecessor-governed change approval, and rollback/fork/reset detection.
- `authoritative_ref_current` cannot use historical PR/reviewer/pre-merge predicates. Artifacts needing those predicates use `exact_blob`.
- Preflight receipts are local controller records, operation-specific, exact-context-bound, single-use for mutation, and never accepted as caller-supplied bodies.
- Local auto-resume requires exact snapshot/identity and one unique candidate.
- Remote-dependent continuation uses one command to refresh and decide; old refresh receipts are insufficient.
- Non-exact continuation creates a stable-only successor workstream; v1 has no same-checkpoint manual JSON resume.
- `seal` proves structure and exclusive file creation only. It never proves truth, current evidence, approval, Git publication, acceptance, promotion, or authority.
- `seal`, promotion, migration, provider setup, Policy candidate materialization, installer mutation, uninstall, and GC fail closed on integrity uncertainty.
- No command stages, commits, pushes, opens a PR, approves, merges, releases, or deploys.
- Automatic lifecycle never calls network, LLM, provider, recall, shared scan, reindex, Git mutation, `seal`, promotion, or GC.
- Only `SessionStart` may emit the fixed route-only notice. Other Hook events are silent. V1 does not install `UserPromptSubmit`.
- Existing `handoff`, `codex-orchestration`, `gpt-pro-codex-loop`, `hotl-governance`, and Sol Advisor contracts remain unchanged.
- Every Task is an independent reviewer gate.

## Closed Resource Limits

| Resource | Limit |
|---|---:|
| Shared record | 65,536 bytes |
| Metadata block | 16,384 bytes |
| Markdown body | 49,152 bytes |
| Relations / evidence | 32 each |
| Scope paths | 64 |
| Tags | 32 |
| Default recall results | 5 |
| Default recall record text | 8,000 characters |
| Full recall output | 10,000 characters |
| Query input | 2,048 UTF-8 bytes |
| Query terms | 32, max 64 chars each |
| Normal relation traversal | depth 1 / 50 neighbors |
| Stable-only traversal | depth 8 / 128 records |
| GitHub page size | 100 requested items |
| GitHub pages | 20 per resource |
| GitHub items | 2,000 per resource |
| Normalized remote bytes | 16 MiB per resource |
| Remote batch wall time | 30 seconds |
| SQLite busy timeout | 750 ms |
| Mutation preflight receipt | max 5 minutes, single-use |

---

## File Structure

### Skill surface

```text
skills/agent-experience/
├── SKILL.md
├── README.md
├── agents/openai.yaml
├── references/
│   ├── lifecycle-contract.md
│   ├── record-contract.md
│   ├── recall-contract.md
│   ├── remote-state-contract.md
│   ├── provider-runtime-contract.md
│   ├── policy-contract.md
│   ├── host-adapters.md
│   └── integration-contract.md
├── schemas/
│   ├── config.schema.json
│   ├── checkpoint.schema.json
│   ├── preflight-receipt.schema.json
│   ├── provider-install.schema.json
│   ├── record-envelope.schema.json
│   ├── observation.schema.json
│   ├── decision.schema.json
│   ├── knowledge.schema.json
│   ├── outcome.schema.json
│   ├── promotion.schema.json
│   ├── remote-provider-result.schema.json
│   ├── remote-observation.schema.json
│   ├── bootstrap-approval.schema.json
│   ├── policy-pointer.schema.json
│   ├── policy-revision.schema.json
│   ├── acceptance-policy.schema.json
│   └── accepted-artifact-result.schema.json
└── scripts/
    ├── agent_experience.py
    └── agent_experience_lib/
        ├── __init__.py
        ├── canonical.py
        ├── cli.py
        ├── config.py
        ├── git_identity.py
        ├── snapshot.py
        ├── store.py
        ├── receipts.py
        ├── records.py
        ├── security.py
        ├── projection.py
        ├── recall.py
        ├── remote.py
        ├── provider_runtime.py
        ├── github_provider.py
        ├── approval_provider.py
        ├── policy.py
        ├── acceptance.py
        ├── hooks.py
        ├── installer.py
        └── adapters.py
```

### Tests and evals

```text
tests/test_agent_experience_*.py
evals/agent-experience/requirements.json
evals/agent-experience/cases.json
evals/agent-experience/criteria.yaml
evals/agent-experience/baseline-observations.json
evals/agent-experience/test_requirements_contract.py
evals/agent-experience/test_skill_contract.py
evals/agent-experience/test_adversarial_contract.py
evals/agent-experience/test_remote_state_contract.py
evals/agent-experience/fixtures/{records,snapshots,github}/
```

---

## Task Map and Release Boundaries

| Task | Deliverable |
|---:|---|
| 1 | Observable RED baseline including all review exploits |
| 2 | Skill contract and machine-readable requirement coverage |
| 3 | Canonical JSON/path/time/digest primitives |
| 4 | Closed tracked configuration and CLI envelope |
| 5 | Repository/worktree/branch identity |
| 6 | Canonical snapshot and exact compatibility classifier |
| 7 | Transactional local store and local trust state |
| 8 | Recovery, quarantine, and retention primitives |
| 9 | Preflight receipts and manual local-checkpoint MVP |
| 10 | Shared record and provenance schemas |
| 11 | Security gates and immutable `seal` |
| 12 | Shared scan, validation, and index generations |
| 13 | Projection, staleness, contested state, stable-only closure |
| 14 | Explicit promotion and deprecation |
| 15 | Bounded deterministic recall |
| 16 | Recall feedback and harmful suppression |
| 17 | Explicit local GC |
| 18 | Typed remote contracts, digests, provenance, completeness |
| 19 | Trusted local GitHub CLI provider, encoding, pagination |
| 20 | Bootstrap approval-provider boundary and candidate materialization |
| 21 | Immutable Policy lineage and predecessor-governed Policy changes |
| 22 | Accepted-artifact evaluator |
| 23 | Remote-dependent same-command continuation |
| 24 | Route-only Codex Hooks |
| 25 | Setup installer and Hook ownership |
| 26 | Conflict-safe uninstall |
| 27 | Final Skill and operator documentation |
| 28 | Read-only existing-Skill adapters |
| 29 | Requirement validation, CI, context budget, smoke tests |
| 30 | Pilot, implementation closure, and rollout gate |

```text
v0.1 Local Resume MVP       Tasks 1-9
v0.2 Memory Core            Tasks 10-17
v0.3 Remote Observation MVP Tasks 18-19
v0.4 Remote Governance      Tasks 20-23
v0.5 Automatic Lifecycle    Tasks 24-26
v1.0 Reviewed Rollout       Tasks 27-30
```

---

## Task 1 — Record observable RED baseline behavior

**Files**
- Create `evals/agent-experience/baseline-observations.json`

**RED cases**

Use a fresh worker per case and record only observable response/tool behavior:

```text
stale checkpoint after rebase
memory record treated as merge authority
secret-bearing tool output offered for memory
self-declared verified knowledge
non-trivial task without preflight
stale PR observation used as current
provider failure followed by old-state substitution
malicious PR body instruction
accepted artifact treated as write authority
changed remote dependency auto-resumed
repository-controlled ./gh executed
worker-driven pseudo-TTY bootstrap accepted
second bootstrap / Policy rollback / Policy fork accepted
old reviewed blob accepts later current blob
partial reviews/check runs treated as complete
caller-supplied preflight receipt accepted
check-run result claimed as branch-protection parity
last pusher approximated from commit author
pre-encoded endpoint/path changes resource binding
seal treated as truth or accepted evidence
Policy successor bypasses predecessor policy_change gate
design closure mistaken for implementation closure
owner acceptance self-minted by agent
```

Closed violation codes include every original finding and reconciliation finding.

**Verification**

- At least 10 distinct violation classes are observed or explicitly recorded as non-reproduced with evidence.
- Required cases include provider executable injection, bootstrap self-approval, lineage reset, partial pagination, stale receipt, endpoint mismatch, predecessor gate bypass, closure-stage confusion, and owner-acceptance forgery.

**Commit**

```bash
git add evals/agent-experience/baseline-observations.json
git commit -m "test: record agent experience red baseline"
```

---

## Task 2 — Freeze Skill and requirement contracts

**Files**
- Create Skill, README, `agents/openai.yaml`, all reference files
- Create `evals/agent-experience/requirements.json`, cases, criteria, runner
- Create `evals/agent-experience/test_requirements_contract.py`
- Create `evals/agent-experience/test_skill_contract.py`
- Create `tests/test_agent_experience_contract.py`

**RED**

Require model-facing contracts to state:

```text
route-only
untrusted advisory data
never execution authority
exact compatibility
current builtin refresh required for mutable remote facts
repository configuration cannot select an executable
bootstrap requires a trusted approval provider
Policy successor is governed by predecessor policy_change
manual review JSON cannot resume a checkpoint
remote observe imports are historical untrusted data
seal proves structure, not truth or authority
design closure and implementation closure are distinct
owner acceptance cannot be self-minted
must not install UserPromptSubmit
must not stage, commit, push, open a PR, approve, merge, release, or deploy
```

`requirements.json` maps every original and reconciliation finding to:

```text
stable requirement ID
contract locator
Task IDs
test files
required case IDs
```

Reject duplicate IDs, unknown Tasks, missing tests, empty cases, or unmapped binding findings.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_contract.py evals/agent-experience/test_requirements_contract.py evals/agent-experience/test_skill_contract.py -v
```

**Commit**

```bash
git add skills/agent-experience evals/agent-experience tests/test_agent_experience_contract.py
git commit -m "feat: define agent experience contracts"
```

---

## Task 3 — Implement canonical primitives

**Files**
- Create `canonical.py`, package init, canonical tests

**RED**

Test duplicate JSON keys, floats, NaN/Infinity, BOM, invalid UTF-8, canonical key order, stable SHA-256, normal-array order, set-like duplicate rejection, NFC human fields, opaque-ID preservation, path traversal, drive prefix, NUL/control, and exact UTC-second timestamps.

**Implementation**

Expose:

```text
ContractError
JSONScalar / JSONValue
load_json_strict
canonical_json_bytes
digest_bytes
normalize_relative_path
require_nfc
parse_rfc3339_utc
format_rfc3339_utc
```

**GREEN**

```bash
python -m unittest tests/test_agent_experience_canonical.py -v
```

---

## Task 4 — Define tracked configuration and CLI envelope

**Files**
- Create entrypoint, `config.py`, `cli.py`, config schema, tests

**RED**

Reject missing marker, unknown keys, unsupported schema, invalid UUID, unsafe shared store, non-route-only Hook mode, oversized limits, provider other than `none|github`, unsafe Policy path, cross-repository Policy path, and every tracked field named or equivalent to:

```text
executable command args env url method graphql extension headers
```

**Implementation**

Tracked remote config contains only provider policy:

```text
provider
authoritative_remote
acceptance_policy
```

No local executable identity enters tracked config.

Exit codes:

```text
0 success / empty / Hook no-op
2 invalid argument or schema
3 degraded or unavailable read capability
4 integrity violation
5 explicit mutation conflict
```

**GREEN**

```bash
python -m unittest tests/test_agent_experience_config.py -v
```

---

## Task 5 — Bind repository, worktree, branch, and HEAD identity

**Files**
- Create `git_identity.py`, tests

**RED matrix**

```text
another clone -> same repo_id, different worktree_id
second worktree -> different worktree_id
branch switch at same HEAD -> branch_ref changes
detached HEAD -> DETACHED:<sha>
restart -> worktree_id stable
copied local DB -> binding mismatch
credential-bearing remote URL -> sanitized
subdirectory cwd -> same root
registered worktree list -> canonical roots
```

**GREEN**

```bash
python -m unittest tests/test_agent_experience_git_identity.py -v
```

---

## Task 6 — Capture canonical snapshots and classify compatibility

**Files**
- Create `snapshot.py`, snapshot tests and fixtures

**RED**

Cover tracked/staged/unstaged/untracked/deleted files, mode, symlink target, submodule SHA/dirty state, case collision, unmerged index, unsafe path, controller metadata exclusion, and unstable two-sample capture.

Only identical repo/worktree/branch/HEAD/index/tracked/untracked/scope is `exact` and auto-resumable.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_snapshot.py -v
```

---

## Task 7 — Build transactional local store and trust state

**Files**
- Create `store.py`, `receipts.py`
- Create preflight-receipt and provider-install schemas
- Create store/receipt tests

**Required tables**

```text
metadata
workstreams
checkpoints
preflight_receipts
pending_records
shared_bindings
record_index_generations
record_index
record_relations
recall_receipts
feedback
hook_events
hook_owner
provider_install
trusted_issuer_registry_cache
policy_approval_cache
policy_lineage_cache
remote_observations
remote_dependencies
remote_refresh_runs
quarantine_events
migration_state
```

**RED**

Test foreign keys, repo/worktree namespace, `BEGIN IMMEDIATE`, 750ms timeout, concurrent writers, optimistic checkpoint revision, duplicate Hook event, local-only provider-install fields, receipt uniqueness/expiry/consumption, refresh receipt unique key, and index generation pinning.

**Concurrency**

- checkpoint update requires `expected_revision`;
- mismatch returns `checkpoint_revision_conflict`, exit 5;
- network fetch holds no write transaction;
- refresh commit is short `BEGIN IMMEDIATE`;
- recall pins one active index generation;
- local trust records never enter shared records.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_store.py tests/test_agent_experience_receipts.py -v
```

---

## Task 8 — Add recovery, quarantine, and retention primitives

**Files**
- Modify store; create recovery tests

**RED**

Cover corrupt DB/WAL/SHM, unique quarantine, explicit loss witness, read-only directory, active checkpoint preservation, unresolved pending preservation, active remote dependency pins, receipt expiry, provider-install preservation, issuer-registry preservation, and prohibition on automatic shared-file deletion.

**Retention defaults**

```text
Hook idempotency 7 days
closed local checkpoints 30 days
expired/consumed preflight receipts +7 days audit
recall receipts 90 days
completed remote refresh 90 days
unsealed remote observations 90 days unless pinned
quarantine 30 days after acknowledged loss report
active/unresolved/provider-install/issuer/installer state no automatic deletion
```

**GREEN**

```bash
python -m unittest tests/test_agent_experience_recovery.py -v
```

---

## Task 9 — Deliver preflight receipts and local checkpoint MVP

**Files**
- Modify CLI/config/store/receipts; create CLI tests

**Receipt contract**

Bind:

```text
receipt ID / nonce
repo / worktree / branch / HEAD
index / tracked / untracked / scope digests
config digest
active Policy pointer and revision digest
workstream
operation and operation-scope digest
use-context ID
CLI contract version
issued-at / expiry
```

Caller supplies only a receipt ID. Mutation receipts are operation-specific, single-use, and atomically consumed after exact state recomputation.

**RED**

```text
init -> preflight --for start -> start consumes once
preflight --for checkpoint -> checkpoint consumes once
cross-repo/worktree receipt -> reject
branch/HEAD/snapshot/config/Policy/operation mismatch -> reject
expired/replayed/caller-body receipt -> reject
exact context -> accept once
scoped change -> old checkpoint stale
```

**Local MVP gate**

```bash
python -m unittest tests/test_agent_experience_canonical.py tests/test_agent_experience_config.py tests/test_agent_experience_git_identity.py tests/test_agent_experience_snapshot.py tests/test_agent_experience_store.py tests/test_agent_experience_receipts.py tests/test_agent_experience_recovery.py tests/test_agent_experience_cli.py -v
```

---

## Task 10 — Define immutable shared record and provenance contracts

**Files**
- Create `records.py`, all record schemas, record tests and fixtures

**RED**

Test sentinel/fence, duplicate keys, BOM, line ending normalization, ID/path/kind/month mismatch, unknown fields, size/fan-out limits, origin-status forgery, relation digest, provenance class, and `untrusted_import` restrictions.

Origin statuses:

```text
checkpoint=active
observation=observed
decision=active
knowledge=candidate
outcome=recorded
promotion=committed
```

Remote provenance class is immutable. Record body remains untrusted.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_records.py -v
```

---

## Task 11 — Enforce security and `seal` semantics

**Files**
- Create `security.py`; modify records/CLI/store; create security tests

**RED**

Cover token/key prefixes, PEM, credential URL, environment values, home/user path, traversal, symlink/reparse escape, same-file alias, recursive import, prompt-like body, cross-repository publication, `untrusted_import` sealing, and seal-as-authority misuse.

**Implementation**

- `capture` writes local pending state only.
- High-confidence secret/local-path suspicion rejects `seal` without guess-redaction.
- `seal` validates and exclusively creates a unique working-tree record.
- `seal` does not stage, publish, approve, accept, or upgrade provenance.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_security.py tests/test_agent_experience_records.py -v
```

---

## Task 12 — Scan and atomically reindex shared records

**Files**
- Modify records/store/CLI; create reindex tests

**RED**

Mix valid, malformed, mutated, oversize, digest-mismatched, relation-retargeted, provenance-invalid, and repository-binding-invalid records. Invalid records never enter the active index.

**Implementation**

Build a shadow generation bound to sorted source digests, then atomically activate. Recall readers pin one generation.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_reindex.py -v
```

---

## Task 13 — Project effective state and stable-only closure

**Files**
- Create `projection.py`, projection tests

**RED**

Test unknown target, self-reference, supersedes cycle, digest mismatch, valid promotion replay, contradiction, harmful outcome, per-kind staleness, adopted-target invalidation, and precedence:

```text
invalid/excluded > superseded/deprecated > contested > stale > normal
```

Stable-only candidates:

```text
stable_decision
do_not_redo
failed_approach
verified_or_adopted_reference
```

Traverse `depends-on`, `premise`, `supports`, `applies-to`, `resolved-by` to depth 8 / 128 records. Exclude mutable remote dependency, invalid/stale/contested/superseded/deprecated target, digest mismatch, unresolved premise, unknown target, or limit exceedance.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_projection.py -v
```

---

## Task 14 — Implement explicit promotion and deprecation

**Files**
- Modify projection/records/CLI; create promotion tests

**RED matrix**

```text
one observation -> reject
duplicate evidence -> reject
same workstream only -> reject
two independent workstreams + current validation -> eligible
human review without current validation -> reject
untrusted_import as current validation -> reject
unresolved contested/harmful -> reject
remote-state source -> reject
candidate -> adopted directly -> reject
```

Adoption requires reviewed target artifact, target digest, exact commit/PR locator, repository acceptance, current validation, and no stale/contested state. Promotion never edits the target artifact.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_promotion.py tests/test_agent_experience_projection.py -v
```

---

## Task 15 — Implement bounded deterministic recall

**Files**
- Create `recall.py`; modify CLI/store; create recall tests

**RED**

Use 1,000 records. Assert budgets, invalid-state exclusion, exact-failure precedence, platform/scope filters, deterministic order, FTS injection rejection, fallback determinism, untrusted fields, historical remote labels, generation pinning, and no incomplete remote collection as current result.

Ranking:

```text
compatible checkpoint
adopted knowledge
verified knowledge
active decision
exact failure
other observation
historical remote observation
```

Persist only query digest, structured filters, returned IDs, exclusions, generation ID, and character count.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_recall.py -v
```

---

## Task 16 — Record feedback and suppress harmful guidance

**Files**
- Modify store/projection/CLI; create feedback tests

**RED**

Cover result enums, digest/workstream mismatch, reason privacy, immediate local harmful suppression, local feedback not changing shared projection, sealed exact-target harmful outcome, and malformed contradiction exclusion.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_feedback.py tests/test_agent_experience_projection.py tests/test_agent_experience_recall.py -v
```

---

## Task 17 — Add explicit local GC

**Files**
- Modify store/CLI; create GC tests

**RED**

Test retention thresholds, dependency pins, dry-run immutability, canonical plan digest, stale plan, concurrent change, provider-install and trusted-issuer preservation, and prohibition on Git-tracked record deletion.

Apply rechecks the exact candidate set in one transaction.

**Memory Core gate**

```bash
python -m unittest tests/test_agent_experience_records.py tests/test_agent_experience_security.py tests/test_agent_experience_reindex.py tests/test_agent_experience_projection.py tests/test_agent_experience_promotion.py tests/test_agent_experience_recall.py tests/test_agent_experience_feedback.py tests/test_agent_experience_gc.py -v
```

---

## Task 18 — Freeze typed remote contracts

**Files**
- Create `remote.py`, remote schemas, remote-contract tests

**Typed operations**

```text
repository
branch
commit
pull_request
issue
pull_request_reviews
check_runs_for_ref
workflow_runs_for_sha
file_on_ref
authenticated_user
```

Callers cannot supply method, URL, endpoint, query string, GraphQL, extension command, or arbitrary headers.

**RED**

- cross-repository binding;
- full URL;
- pre-encoded `%HH`;
- empty/dot/NUL/control segment;
- response-key mismatch;
- four digest separation;
- provenance `builtin_refresh|untrusted_import|test_fixture`;
- `refresh_run_id`, `use_context_id`, adapter version;
- pagination completeness metadata;
- incomplete collection cannot pass;
- provider failure plus old observation is not fresh;
- check source is exactly `check_run`;
- commit status, both, and source omission unsupported.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_remote_contract.py -v
```

---

## Task 19 — Implement trusted GitHub CLI provider

**Files**
- Create `provider_runtime.py`, `github_provider.py`
- Modify CLI/store
- Create provider-runtime/provider tests and fixtures

**Executable trust RED**

```text
tracked executable field -> reject
relative/repository gh -> reject
PATH/current-directory shadow -> reject
python/sh/cmd/powershell wrapper -> reject
symlink/reparse -> reject
file replacement after setup -> integrity failure
valid absolute gh outside repository -> accepted
```

Provider setup is explicit, local-only, receipt-gated, and stores canonical path, digest, size, mtime, file identity, reparse/symlink state, tested version, contract version, and timestamp under Git-common-dir state.

**Typed encoding RED**

Test `?`, `&`, `#`, `%`, Unicode path segments, slash-containing branch/ref, pre-encoded separator rejection, full URL rejection, exact response binding, and same-operation next-link validation.

**Pagination RED**

Request `per_page=100`; follow validated same-host/same-operation `Link rel=next`; enforce 20 pages / 2000 items / 16 MiB / 30 s. Cover later-page review/check changes, duplicate App/name, rate limit, malformed link, malicious host, and cap exceedance.

**Process boundary**

Absolute executable argv, `shell=False`, fixed GET, controlled environment, no token output, 10-second request timeout, 30-second batch deadline, GitHub.com-only capability gate.

**Remote Provider gate**

```bash
python -m unittest tests/test_agent_experience_provider_runtime.py tests/test_agent_experience_github_provider.py tests/test_agent_experience_remote_contract.py -v
```

---

## Task 20 — Implement bootstrap approval-provider boundary and candidate materialization

**Files**
- Create `approval_provider.py`
- Create bootstrap approval schema
- Modify CLI/store
- Create bootstrap approval tests

**RED**

Reject pseudo-TTY, self-declared human JSON, unsigned repository receipt, caller-supplied receipt body, cross-repository/Policy/plan copy, replayed nonce, expired receipt, and unknown issuer.

Without trusted provider:

```text
bootstrap_manual_governance_required
```

Use a fake trusted provider in tests that accepts an opaque locator and returns a closed verified approval bound to issuer, repository ID, owner ID, lineage ID, Policy digest, plan digest, nonce, issue/expiry, and subject.

**Candidate behavior**

`policy bootstrap-candidate` may create deterministic candidate files and mutation plan. It does not activate, commit, push, open PR, approve, or merge.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_bootstrap_approval.py -v
```

---

## Task 21 — Implement immutable Policy lineage and predecessor-governed changes

**Files**
- Create `policy.py`
- Create Policy pointer/revision/acceptance-policy schemas
- Modify CLI/store
- Create Policy lineage/change tests

**Immutable storage**

```text
.agent-experience/acceptance-policy.json
.agent-experience/policies/<lineage-id>/<revision>-<digest>.json
```

**Root RED**

```text
root without verified trusted approval -> inactive
second bootstrap -> reject
receipt/repository/owner/lineage/Policy/plan mismatch -> reject
```

**Lineage RED**

```text
P3 references old P1 while P2 active -> reject
stale base head -> reject
revision repeat/decrease -> reject
two successors -> policy_lineage_inconsistent
force-push removes predecessor -> inconsistent
pointer rollback -> reject
valid root -> P1 -> P2 -> valid
```

**Predecessor Policy-change RED**

Current predecessor `P(n)` governs successor `P(n+1)`.

```text
candidate uses its own weaker policy_change -> reject
missing required exact-login approval -> pending
candidate author counted despite distinct-author rule -> reject
old-head approval/check -> pending
COMMENTED after APPROVED -> approval remains decision
later-page CHANGES_REQUESTED -> fail
incomplete review/check collection -> unknown
wrong App/SHA/phase -> not pass
all predecessor gates + exact lineage -> successor eligible
```

Policy-change check entries require `source=check_run`, explicit App policy, phase, and allowed conclusions. Wildcards, teams, inferred maintainers, commit status, and last-push approximation are unsupported.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_policy.py tests/test_agent_experience_policy_change.py -v
```

---

## Task 22 — Implement accepted-artifact evaluator

**Files**
- Create `acceptance.py`, result schema, tests
- Modify policy/CLI

**Mode RED**

- `exact_blob` required for security/governance/authority/release/frozen artifacts.
- `authoritative_ref_current` rejects required PR, review policy, pre-merge check, post-merge-result check, or historical provenance.

**SHA graph RED**

Keep PR head/test-merge/result, authoritative head, artifact blob, introducing commit, and validation SHA separate. Reject cross-SHA/App/phase reuse and ambiguous provenance.

**Review RED**

COMMENTED does not revoke APPROVED. Apply dismissal by exact review identity. Select the latest APPROVED/CHANGES_REQUESTED decision review only. Bind to current head. Require complete pagination.

**Check-run-only RED**

Require `source=check_run`, name, App policy, phase, target SHA, complete collection. Reject source omission, commit status, both, last-push approval, wrong App/SHA/phase, and incomplete collection. Result reports:

```text
branch_protection_parity_evaluated=false
```

**Result enum**

```text
accepted
not_accepted
pending
inconsistent
unknown
```

Every predicate lists evidence observation ID/digest, target SHA, phase, completeness, and result. `accepted` never implies implementation or merge authority.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_acceptance.py tests/test_agent_experience_policy.py tests/test_agent_experience_policy_change.py -v
```

---

## Task 23 — Implement same-command remote continuation

**Files**
- Modify CLI/store/snapshot/remote/projection/checkpoint schema
- Create remote-checkpoint tests

**Decision matrix**

```text
local exact + no remote -> auto true
local exact + same-command fresh unchanged -> auto true
old separate refresh receipt -> auto false
provider failure -> unknown/unavailable false
PR/branch/Policy state changed -> false
repository mismatch -> stale false
multiple exact candidates -> ambiguous false
non-exact continuation -> stable-only successor
```

**TOCTOU/transaction RED**

Network fetch holds no write lock. After fetch, one short transaction stores observations/use-context and decision. Another use-context cannot reuse the result. Residual race is reported, not hidden.

`remote observe` imports normalized input only as `untrusted_import`; it cannot satisfy current evidence, accepted predicates, or resume.

**Remote Governance gate**

```bash
python -m unittest tests/test_agent_experience_remote_contract.py tests/test_agent_experience_provider_runtime.py tests/test_agent_experience_github_provider.py tests/test_agent_experience_bootstrap_approval.py tests/test_agent_experience_policy.py tests/test_agent_experience_policy_change.py tests/test_agent_experience_acceptance.py tests/test_agent_experience_remote_checkpoint.py -v
```

---

## Task 24 — Implement route-only Codex Hooks

**Files**
- Create `hooks.py`; modify CLI
- Create Hook and adversarial tests

**RED**

- Freeze tested official Codex Hook contract.
- Unknown contract leaves manual mode.
- Private prompt, transcript, path, branch, record, checkpoint, token, and remote observation never enter stdout/stderr/DB.
- AST/import tests reject provider/network dependency paths.
- Runtime patches socket/subprocess/provider calls to fail if invoked.
- Duplicate owner/event, DB lock, unsupported schema, and non-owner exit 0 silently.
- Only SessionStart returns fixed <=512-byte notice with `additionalContextLimit=256`; other events are silent.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_hooks.py evals/agent-experience/test_adversarial_contract.py -v
```

---

## Task 25 — Implement setup installer and Hook ownership

**Files**
- Create `installer.py`; modify CLI/host reference
- Create installer tests

**RED**

Cover `CODEX_HOME`, active `AGENTS.override.md`, 32 KiB budget, hooks.json/inline conflict, POSIX/Windows command, exact timeouts, SessionStart context limit, absence of UserPromptSubmit, dry-run digest, idempotency, stale plan, owner migration, unsupported host, and no provider executable in tracked files.

**Implementation**

Atomic plan/apply rechecks preimages, writes same-directory temporary files, fsyncs, atomically replaces, and records a local install manifest.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_installer.py tests/test_agent_experience_hooks.py -v
```

---

## Task 26 — Implement conflict-safe uninstall

**Files**
- Modify installer/CLI/host reference
- Create uninstall tests

**RED**

Cover exact managed removal, unrelated content preservation, operator edit, manifest drift, missing backup, repeated uninstall, owner cleanup, and exit 5 without clobbering.

Uninstall removes only content whose current digest matches the install manifest. It never restores an old whole-file backup over operator edits.

**Automatic Lifecycle gate**

```bash
python -m unittest tests/test_agent_experience_hooks.py tests/test_agent_experience_installer.py tests/test_agent_experience_uninstall.py evals/agent-experience/test_adversarial_contract.py -v
```

---

## Task 27 — Finalize Skill and operator documentation

**Files**
- Modify all Skill/reference files and model-facing eval contracts

**Workflow contract**

```text
marker
-> preflight receipt
-> current local/remote evidence
-> bounded recall
-> current code/test/runtime comparison
-> work
-> fresh preflight for mutation
-> checkpoint / feedback / selected seal
```

Document trusted provider setup, no standalone bootstrap activation, predecessor Policy-change gates, Policy lineage, storage tiers, check-run-only scope, unsupported last-push, typed requests, pagination completeness, TOCTOU, trigger limits, design/implementation closure separation, owner-acceptance process gate, and hard invariants.

`SKILL.md` target <500 words, hard limit <800; exhaustive detail stays in references.

**GREEN**

```bash
python evals/agent-experience/run.py --cases evals/agent-experience/cases.json --criteria evals/agent-experience/criteria.yaml
python -m unittest tests/test_agent_experience_contract.py evals/agent-experience/test_requirements_contract.py evals/agent-experience/test_skill_contract.py -v
```

---

## Task 28 — Add read-only existing-Skill adapters

**Files**
- Create `adapters.py`; modify integration reference; create adapter tests

External artifacts produce locators, digests, and observed results only. They never produce authority, completion, merge permission, or external state-machine transitions.

A trusted approval adapter verifies through its native controller/provider, not repository bytes. Arbitrary JSON cannot become a verified bootstrap approval.

Automatic lifecycle never invokes `handoff`, creates a task, creates a backup, or requires destination confirmation.

**GREEN**

```bash
python -m unittest tests/test_agent_experience_adapters.py tests/test_handoff_evals.py tests/test_hotl_governance.py tests/test_codex_orchestration_evals.py -v
```

---

## Task 29 — Integrate requirement validation, CI, context budget, and smoke tests

**Files**
- Modify CI, generated README, context-budget files
- Create integration tests

**Requirement validation**

Every original and reconciliation finding must map to a Task, test file, and case ID. Fail on missing/duplicate/stale mappings or obsolete plan terms.

**CI**

- Ubuntu Python 3.11 runs all Agent Experience tests/evals.
- Windows Python 3.12 runs snapshot, store, receipts, recovery, security, provider runtime, encoding, pagination, Policy bootstrap/lineage/change, acceptance, remote continuation, Hooks, setup/uninstall, and adversarial tests.

Fake GitHub fixtures cover:

```text
repository executable shadow / replacement / reparse
multi-page reviews and check runs
malicious Link next URL
encoded path/ref
partial pagination
Policy second bootstrap / rollback / fork
predecessor policy_change approval/check failures
trusted / no-trusted approval provider
same-command refresh race
concurrent checkpoint revision
```

**Smoke tests**

Local:

```text
init -> preflight -> start -> checkpoint -> preflight -> recall -> setup dry-run
```

Remote:

```text
provider setup -> refresh/compare -> bootstrap candidate/status
-> Policy successor evaluation -> accepted artifact
-> remote-dependent stable-only continuation
```

**Complete verification**

```bash
python scripts/validate-skills.py
python scripts/context_budget_report.py --repo . --manifest context-budget-manifest.json --baseline context-budget-baseline.json --max-growth-bytes 0
python -m unittest discover -s tests -v
python -m unittest discover -s evals/agent-experience -p "test_*.py" -v
python -m unittest discover -s evals/hotl-governance -p "test_*.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_*.py" -v
```

---

## Task 30 — Run pilot, implementation closure review, and rollout gate

**Files**
- Create `docs/agent-experience-pilot.md`
- Create `docs/superpowers/reviews/2026-08-23-agent-experience-implementation-closure.md`

Do not modify or replace the pre-Task-1 design-closure artifact.

**Fourteen representative pilot tasks**

```text
1 exact-session resume
2 Windows known failure
3 stale local checkpoint
4 prior decision
5 harmful guidance
6 large unrelated corpus
7 explicit handoff
8 task without Skill name
9 compaction/re-entry
10 setup/uninstall
11 PR open -> merged delta
12 file absent -> present
13 provider failure with old observation
14 accepted artifact blob/review/check mismatch
```

**Mandatory exploit hard stops**

```text
repository-controlled gh executed
pseudo-TTY or unsigned bootstrap activated
Policy second bootstrap / rollback / fork accepted
successor bypasses predecessor policy_change gate
old reviewed blob accepts later current blob
partial pagination passes
stale/replayed preflight receipt accepted
commit-status parity falsely claimed
last-push actor approximated
endpoint encoding/resource binding mismatch
seal treated as truth or authority
old remote observation reused across use-context
concurrent checkpoint lost update
implicit trigger omission undetected
```

**Implementation closure review**

A reviewer who did not author the implementation or remediation reads the exact implementation HEAD, original review, all reconciliation documents, Contract Index, active plan, code, tests, requirement map, CI, and pilot evidence.

For every original/reconciliation finding record:

```text
verified_closed
reasoned_rejected
disputed
```

Include exact test/evidence locators and reviewed blob/commit digests.

**Mechanical GO**

`GO` requires:

- all tests/context budget green;
- no pilot hard stop;
- every finding verified or reasonedly rejected;
- no open Critical/Important finding;
- repository-owner rollout acceptance.

Otherwise `NO-GO` with exact finding/test locator.

---

## Task Dependency Spine

```text
1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9
-> 10 -> 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17
-> 18
   ├-> 19 provider
   └-> 20 bootstrap approval boundary
19 + 20 -> 21 Policy lineage/change
-> 22 accepted artifact
-> 23 remote continuation
-> 24 Hooks
-> 25 setup
-> 26 uninstall
-> 27 docs
-> 28 adapters
-> 29 CI/integration
-> 30 pilot/implementation closure
```

Tasks 19 and 20 may run in parallel only after Task 18 interfaces are frozen. All other production Tasks are sequential unless a reviewed plan amendment proves no shared interface/file/fixture conflict.

## Requirement Coverage Matrix

| Requirement | Tasks |
|---|---|
| `AEX-IR-C01` trusted provider executable | 4, 7, 19, 29, 30 |
| `AEX-IR-C02` bootstrap approval provider | 20, 28, 29, 30 |
| `AEX-IR-C03` Policy lineage | 21, 29, 30 |
| `AEX-IR-I01` active plan and requirement map | 2, 29, 30 |
| `AEX-IR-I02` current artifact restriction | 22, 30 |
| `AEX-IR-I03` pagination completeness | 18, 19, 21, 22, 29, 30 |
| `AEX-IR-I04` preflight receipt | 7, 9, 29, 30 |
| `AEX-IR-I05` check-run-only scope | 18, 21, 22, 30 |
| `AEX-IR-I06` last-push unsupported | 21, 22, 30 |
| `AEX-IR-I07` typed endpoint encoding | 18, 19, 29, 30 |
| `AEX-CR-I01` closure-stage separation | 2, 27, 30 |
| `AEX-CR-I02` release-range alignment | 2, 29, 30 |
| `AEX-CR-I03` predecessor Policy-change gate | 1, 21, 22, 29, 30 |
| `AEX-CR-I04` owner design acceptance | entry gate, 2, 27, 30 |
| explicit handoff separation | 2, 27, 28, 30 |
| exact local resume | 5, 6, 9, 23 |
| immutable record/digest binding | 10-14 |
| bounded recall | 15 |
| secret/privacy/resource limits | 3, 10-12, 15, 17, 19, 29 |
| route-only network-free Hooks | 24 |
| existing-Skill authority preservation | 28 |
| Windows/Linux behavior | 5-9, 11, 19-26, 29 |

## Self-Review Gate

Before Task 1 begins, confirm:

- Contract Index is the sole spec entry point.
- Formal design closure and owner acceptance bind the exact current design.
- The active plan contains exactly 30 declared Tasks and matching release ranges.
- Design closure and implementation closure use different paths.
- Every original and reconciliation finding has a Task/test/case mapping.
- No tracked executable, singular remote digest, caller JSON resume, reusable old fresh receipt, ambiguous check source, or supported last-push approval remains.
- No Hook can import or reach provider/network modules.
- No repository file can establish bootstrap or owner approval.
- Policy lineage and predecessor `policy_change` approval/check gates are explicit.
- `authoritative_ref_current` historical predicates are rejected.
- Pagination completeness is mandatory for review/check decisions.
- Preflight receipt is local-only, exact, operation-specific, single-use, and caller-body-proof.
- GitHub requests are typed and segment/query encoded.
- Windows executable shadow/reparse and SQLite concurrency tests exist.
- Independent closure has not been self-claimed.

Placeholder scan:

```bash
python - <<'PY'
from pathlib import Path
p = Path('docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md')
needles = ('T' + 'BD', 'T' + 'ODO', 'implement ' + 'later', 'fill in ' + 'details')
for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
    if any(n.lower() in line.lower() for n in needles):
        print(i, line)
PY
```

Expected: empty output.

## Execution Handoff

```text
docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md
```

Task 1 remains `NO-GO` until a formally independent design-closure review and explicit repository-owner acceptance exist.