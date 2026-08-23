# Agent Experience Skill — Contract Index

- **Document date:** 2026-08-23
- **Target:** `agent-experience` v1
- **Status:** Binding contract index / formal design closure pending
- **Current implementation state:** `DESIGN_REVIEW_PENDING`
- **Task 1 readiness:** `BLOCKED`

## 1. Canonical entry point

This file is the only normative entry point for the `agent-experience` v1 design contract.

```text
canonical entry point
  = this Contract Index

binding contract corpus
  = every specification listed by this index

active implementation plan
  = the single plan named by this index

operational implementation status
  = the status ledger named by this index
```

The status ledger is not design authority. It records execution evidence only.

## 2. Binding documents

Executors and reviewers read every specification in this order.

1. `docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md`
2. `docs/superpowers/specs/2026-08-23-agent-experience-execution-readiness-clarification.md`
3. `docs/superpowers/specs/2026-08-23-agent-experience-closure-reconciliation.md`
4. `docs/superpowers/specs/2026-08-22-agent-experience-independent-review-remediation.md`
5. `docs/superpowers/specs/2026-08-22-agent-experience-trust-roots-runtime-clarification.md`
6. `docs/superpowers/specs/2026-08-22-agent-experience-open-questions-clarification.md`
7. `docs/superpowers/specs/2026-08-22-agent-experience-remote-state-amendment.md`
8. `docs/superpowers/specs/2026-08-21-agent-experience-skill-normative-contract.md`
9. `docs/superpowers/specs/2026-08-21-agent-experience-skill-adversarial-amendment.md`
10. `docs/superpowers/specs/2026-08-21-agent-experience-skill-design.md`

Review provenance:

- `docs/superpowers/reviews/2026-08-22-agent-experience-independent-review.md`
- `docs/superpowers/reviews/2026-08-22-agent-experience-independent-review-remediation.json`
- `docs/superpowers/reviews/2026-08-23-agent-experience-design-closure-preflight.md`
- `docs/superpowers/reviews/2026-08-23-agent-experience-execution-readiness-review.md`

Formal design closure path:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-closure.md
```

Post-implementation closure path:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-implementation-closure.md
```

Operational progress ledger:

```text
docs/superpowers/status/agent-experience-implementation.json
```

## 3. Precedence

When documents conflict, apply:

```text
system / developer / user instruction under the host hierarchy
  > active repository instruction
  > this Contract Index
  > Execution Readiness Clarification, listed domains
  > Closure Review Reconciliation, listed domains
  > Independent Review Remediation Contract, listed domains
  > Trust Roots and Runtime Semantics Clarification, listed domains
  > Open Questions Clarification Contract, listed domains
  > Remote-State Amendment, remote-state domain only
  > Normative Runtime Contract
  > Adversarial Review Amendment
  > Base Design
```

### 3.1 Execution-readiness domain

The Execution Readiness Clarification closes:

- Task-1 GO/NO-GO computation;
- implementation-progress and Task-completion evidence;
- treatment of staged/unstaged or unpushed prototype code;
- v1 no-built-in-bootstrap-issuer boundary;
- Policy-change command flow and candidate resubmission;
- operation-scoped `use_context_id` and refresh-run lifetime;
- Hook/installer start conditions and host-contract probe;
- design/implementation closure targets and invalidation;
- machine/human error envelopes and fail-open/fail-closed presentation.

### 3.2 Reconciliation domain

The Closure Review Reconciliation closes:

- design-closure versus implementation-closure artifact separation;
- release-range and Task-number alignment;
- predecessor-governed Policy-change evaluation;
- repository-owner design-acceptance evidence.

### 3.3 Independent-review remediation domain

The Independent Review Remediation Contract closes implementation discretion around:

- GitHub CLI executable selection and integrity;
- bootstrap approval-provider trust boundary;
- Policy lineage and rollback prevention;
- active implementation-plan synchronization;
- `authoritative_ref_current` restrictions;
- pagination completeness;
- preflight receipt schema and invalidation;
- check-run-only v1 semantics;
- unsupported last-push approval;
- typed GitHub request construction and encoding.

### 3.4 Conflict rule

If two requirements at the same precedence cannot both be satisfied, do not implement. Add a reviewed clarification, update this index, and reconcile the active plan before proceeding.

---

## 4. Consolidated hard contracts

### 4.1 Experience is advisory, never authority

Historical records, remote observations, acceptance results, sealed records, checkpoints, Policy evaluation, and provider receipts never by themselves authorize commit, push, PR creation, approval, merge, release, deploy, or other external mutation.

Current instruction and current code/test/runtime evidence outrank recalled experience.

### 4.2 Design entry and Task 1

Task 1 is `READY` only when both predicates hold for the exact current binding-design digest set:

```text
ValidDesignClosure(current_design_digest_set)
AND
ValidOwnerAcceptance(current_design_digest_set, design_closure_digest)
```

Formal closure must come from a reviewer satisfying the independence contract. Repository JSON claiming approval is not self-proving. Owner acceptance occurs after formal design closure and binds the same exact reviewed design.

Any binding-design byte change invalidates the prior closure, owner acceptance, and Task-1 readiness.

Until the gate passes:

```text
state = DESIGN_REVIEW_PENDING
Task 1 = BLOCKED
```

### 4.3 Implementation progress and prototype code

Task progress is recorded in the operational ledger, not inferred from file names.

A Task becomes `DONE` only from committed implementation-branch changes plus the RED/GREEN/exit/review evidence required by the active plan. Required behavior that exists only in a dirty working tree cannot satisfy a Task.

Staged, unstaged, untracked, or local-only pre-acceptance implementation is:

```text
prototype_unverified
```

After the entry gate, prototype changes may be adopted only by mapping hunks to active Tasks, recreating planned RED evidence, transplanting minimal implementation, running GREEN/regressions, and committing Task-scoped changes on the official implementation branch.

### 4.4 Local checkpoint and continuation

Automatic local resume requires exact compatible state and one unique checkpoint candidate. Non-exact continuation creates a stable-only successor workstream.

Remote-dependent continuation uses one explicit current operation to refresh and decide; an old separately stored refresh cannot become current evidence.

### 4.5 `use_context_id` and refresh runs

`use_context_id` is controller-created for one top-level current remote-decision command. Caller-supplied or previously stored IDs never confer current-evidence status.

```text
new CLI invocation -> new use_context_id
new Codex task -> new use_context_id
post-compaction new command -> new use_context_id
process restart/resume -> new use_context_id
```

One top-level command may perform multiple bounded provider batches. Each receives a distinct `refresh_run_id` under the same use context. The context ends when the command returns, aborts, or reaches its deadline.

### 4.6 Automatic lifecycle and Hooks

V1 may install only:

```text
SessionStart
PreCompact
PostCompact
SessionEnd
```

`UserPromptSubmit` is not installed.

- Hooks are route-only.
- Only `SessionStart` may emit the fixed routing notice.
- Other successful Hook handlers are silent.
- Hook hot paths do not call network, LLM, provider, recall, shared scan, reindex, Git mutation, `seal`, promotion, or GC.
- Hook/local-store degradation fails open for ordinary work.
- Explicit shared/configuration mutation fails closed on integrity uncertainty.

Hooks are Task 24, setup/ownership is Task 25, and uninstall is Task 26. Their absence before those gates is expected.

Task 24 starts with a reviewed host-contract probe. Unsupported or ambiguous installed Codex Hook semantics return:

```text
hook_contract_unsupported
```

and leave manual mode available; installer mutation does not proceed.

### 4.7 Preflight receipt

Operation-specific mutation receipts are controller-created, local-only, exact-context-bound, single-use where required, and valid for at most five minutes. Caller-supplied receipt bodies are rejected. Every gated command recomputes current bindings before consumption.

### 4.8 Policy repository boundary

Policy belongs to the target repository. Immutable revisions and the active pointer use the paths defined by the binding Policy contracts. Cross-repository Policy inheritance/reference is unsupported in v1.

### 4.9 Bootstrap approval trust root

V1 ships no standalone trusted approval issuer.

Built-in v1 may generate a bootstrap Policy candidate and deterministic mutation plan. It cannot activate from TTY text, repository bytes, unsigned audit records, self-declared human JSON, agent-authored approval text, GitHub CLI identity, or GitHub repository objects by themselves.

Task 20 implements the verifier SPI and candidate/plan lifecycle, not a receipt issuer. Activation requires a separately trusted outer-controller adapter whose issuer cannot be minted/configured by target-repository bytes.

Without such an adapter:

```text
bootstrap_manual_governance_required
```

is a supported completed v1 outcome for bootstrap activation. This runtime Policy bootstrap boundary is distinct from the pre-Task-1 human design-acceptance process gate.

### 4.10 Policy lineage and successor execution

Current active `P(n)` governs `P(n+1)`. A successor cannot self-govern.

V1 exposes the closed candidate/evaluation/materialization commands defined by the Execution Readiness Clarification. Predecessor identity is resolved from current authoritative remote state and Policy lineage, not caller prose/JSON.

Evaluation results are limited to:

```text
eligible
pending
not_eligible
unknown
unavailable
inconsistent
```

A rejected/unaccepted candidate does not change the active predecessor. A corrected candidate uses the same next revision number with new bytes/digest/validation SHA. Competing authoritative successors produce `policy_lineage_inconsistent` until current evidence resolves the lineage under the closed rule.

No Policy command commits, pushes, opens a PR, approves, or merges.

### 4.11 Trusted GitHub CLI and read-only Provider v1

Tracked repository configuration cannot select/parameterize executable identity. Provider setup stores a canonical local executable identity outside the working tree and revalidates file identity/digest before use.

GitHub Provider v1 is GitHub.com, typed-operation-only, GET-only, with segment/query encoding, complete pagination requirements, bounded resource limits, response rebinding, and no write operation surface. GHES/GHE.com are unsupported in v1.

### 4.12 Remote provenance and freshness

Keep distinct:

```text
provider_payload_digest
provider_result_digest
state_digest
record_digest
```

Only current-use-context `builtin_refresh` may serve as current remote evidence. Imports are historical/untrusted. Old observations plus refresh failure never become current fact.

Result taxonomy includes `refresh_required`, `fresh`, `changed`, `unknown`, `unavailable`, and `superseded`; accepted-artifact evaluation separately uses its closed predicate/result states.

### 4.13 Accepted-artifact SHA and review/check graph

PR head, test-merge, merge-result, authoritative head, blob, introducing commit, and validation SHA remain distinct. Review/check evidence is bound to the correct SHA/App/phase and requires complete collections.

V1 evaluates GitHub check runs only. Commit-status parity, branch-protection parity, and last-push approval are not approximated.

### 4.14 `seal`

`seal` proves only closed schema, safe path, resource limits, secret/local-path gate, canonical digest, and exclusive working-tree file creation. It does not prove truth, current evidence, approval, accepted status, Git inclusion/publication, promotion, or authority.

### 4.15 Storage, concurrency, recovery

One SQLite store per Git common directory, namespaced by repository/worktree. Use foreign keys, WAL where supported, `busy_timeout=750ms`, optimistic checkpoint revision checks, no network fetch under a write transaction, short commit transactions, atomic index activation, and pinned index generation for recall.

Hook lock timeout is silent exit 0. Explicit mutation lock timeout is fail-closed exit 5. Corruption/recovery-required mutation remains blocked until the recovery workflow completes.

### 4.16 Standard failure contract

Explicit CLI non-success uses the closed JSON envelope:

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

Exit classes:

```text
0 success / empty / automatic Hook no-op
2 invalid argument / closed-schema violation
3 degraded / unavailable / partial / unsupported capability
4 integrity / identity / unsafe path / digest failure
5 stale receipt / transaction conflict / explicit lock timeout / recovery-required mutation
```

Human output without `--json` is limited to safe code/message and next action. No raw exception, provider body, token, prompt, absolute path, or username appears.

### 4.17 Closure separation and invalidation

Design closure targets one clean committed documentation PR head and exact binding blobs. Implementation starts from a dedicated branch created from accepted `main`, not from a dirty prototype or documentation branch.

Implementation may reuse the accepted design closure only while the binding design corpus is byte-identical. Binding-design changes pause implementation and require new independent design closure plus new owner acceptance.

Implementation closure targets one clean committed implementation HEAD with Task ledger, full verification, pilot evidence, and no required dirty changes. Post-closure runtime changes invalidate rollout closure; binding-design changes additionally invalidate design closure/acceptance.

### 4.18 Hard safety invariants

Ordinary prose cannot disable:

- Experience is not authority.
- Remote Provider is read-only.
- secret/credential persistence is prohibited.
- stale, forged, partial, unknown, or unavailable remote state is not current fact.
- self-declared promotion is invalid.
- non-exact checkpoint does not auto-resume.
- Hook network access is prohibited.
- `seal` does not publish to Git.
- repository configuration cannot select provider executable or trusted approval issuer.
- repository bytes cannot establish bootstrap or owner approval.
- shared/config mutation fails closed on integrity uncertainty.

Changing these invariants requires the designated specification/governance workflow.

---

## 5. Sole active implementation plan

```text
docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md
```

It contains exactly 30 Tasks. Older implementation plans are historical pointers only.

## 6. Release order

```text
v0.1 Local Resume MVP       Tasks 1-9
v0.2 Memory Core            Tasks 10-17
v0.3 Remote Observation MVP Tasks 18-19
v0.4 Remote Governance      Tasks 20-23
v0.5 Automatic Lifecycle    Tasks 24-26
v1.0 Reviewed Rollout       Tasks 27-30
```

Dependency gates:

```text
Task 1 entry gate
-> Tasks 1-17 Memory Core
-> Tasks 18-19 Remote Observation
-> Tasks 20-23 Remote Governance
-> Task 24 Hooks
-> Task 25 setup/ownership
-> Task 26 uninstall
-> Tasks 27-30 rollout/closure
```

Task 20 can be complete without a configured production approval issuer when its verifier SPI, candidate path, binding/replay tests, and `bootstrap_manual_governance_required` fallback satisfy the contract.

## 7. Review, acceptance, and implementation gates

### 7.1 Formal design closure

Required path:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-closure.md
```

It binds the exact current design commit/blob set. Every required Critical/Important finding—including execution-readiness findings after they enter the binding corpus—must be independently verified closed or reasoned rejected. Self-remediation/preflight is insufficient.

### 7.2 Repository-owner acceptance

After valid formal design closure, the repository owner explicitly accepts that exact closed design in the active host interaction or via a separately trusted outer provider. A repository audit JSON may record the event but is not self-proving.

### 7.3 Task progress

Official progress is recorded in:

```text
docs/superpowers/status/agent-experience-implementation.json
```

Only committed accepted-branch evidence can move Tasks to `DONE`. Local prototype status does not.

### 7.4 Implementation closure

Required path:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-implementation-closure.md
```

It is created after implementation, full verification, CI, pilot, and progress-ledger evidence exist. It never substitutes for design closure.

## 8. Current gate state

At the time this index is updated:

```text
Original AEX-IR findings: remediated, formal independent design closure still required
AEX-CR reconciliation findings: remediated, formal independent design closure still required
AEX-ER execution-readiness findings: remediated by binding clarification, formal independent verification required
Formal design closure for current head: absent
Repository-owner acceptance for current closed design: absent
Official implementation branch: not established on GitHub
GitHub-verifiable runtime Tasks DONE: 0
Task 1 readiness: BLOCKED
PR #35: documentation review / not implementation-ready
```

Any local staged/unstaged or unpushed implementation, if present, is `prototype_unverified` until adopted through the post-gate workflow.
