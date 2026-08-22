# Agent Experience Skill — Contract Index

- **Document date:** 2026-08-23
- **Target:** `agent-experience` v1
- **Status:** Binding contract index
- **Task 1 readiness:** blocked pending formal design closure and repository-owner acceptance

## 1. Canonical entry point

This file is the only normative entry point for the `agent-experience` v1 design contract.

```text
canonical entry point
  = this Contract Index

binding contract corpus
  = every document listed by this index

active implementation plan
  = the single plan named by this index
```

This file does not duplicate every lower-level specification paragraph. It fixes document order, precedence, consolidated hard boundaries, the sole active plan, release ranges, and implementation gates.

## 2. Binding documents

Executors and reviewers read every document in this order.

1. `docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md`
2. `docs/superpowers/specs/2026-08-23-agent-experience-closure-reconciliation.md`
3. `docs/superpowers/specs/2026-08-22-agent-experience-independent-review-remediation.md`
4. `docs/superpowers/specs/2026-08-22-agent-experience-trust-roots-runtime-clarification.md`
5. `docs/superpowers/specs/2026-08-22-agent-experience-open-questions-clarification.md`
6. `docs/superpowers/specs/2026-08-22-agent-experience-remote-state-amendment.md`
7. `docs/superpowers/specs/2026-08-21-agent-experience-skill-normative-contract.md`
8. `docs/superpowers/specs/2026-08-21-agent-experience-skill-adversarial-amendment.md`
9. `docs/superpowers/specs/2026-08-21-agent-experience-skill-design.md`

Review provenance:

- `docs/superpowers/reviews/2026-08-22-agent-experience-independent-review.md`
- `docs/superpowers/reviews/2026-08-22-agent-experience-independent-review-remediation.json`
- `docs/superpowers/reviews/2026-08-23-agent-experience-design-closure-preflight.md`

Formal design closure path:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-closure.md
```

Post-implementation closure path:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-implementation-closure.md
```

## 3. Precedence

When documents conflict, apply:

```text
system / developer / user instruction under the host hierarchy
  > active repository instruction
  > this Contract Index
  > Closure Review Reconciliation, listed domains
  > Independent Review Remediation Contract, listed domains
  > Trust Roots and Runtime Semantics Clarification, listed domains
  > Open Questions Clarification Contract, listed domains
  > Remote-State Amendment, remote-state domain only
  > Normative Runtime Contract
  > Adversarial Review Amendment
  > Base Design
```

### 3.1 Reconciliation domain

The Closure Review Reconciliation overrides or closes:

- design-closure versus implementation-closure artifact separation;
- release-range and Task-number alignment;
- predecessor-governed Policy-change evaluation;
- repository-owner design-acceptance evidence.

### 3.2 Independent-review remediation domain

The Independent Review Remediation Contract overrides or closes:

- GitHub CLI executable selection and integrity;
- bootstrap approval provider;
- Policy lineage and rollback prevention;
- active implementation-plan synchronization;
- `authoritative_ref_current` restrictions;
- pagination completeness;
- preflight receipt schema and invalidation;
- check-run-only v1 semantics;
- unsupported last-push approval;
- typed GitHub request construction and encoding.

### 3.3 Conflict rule

If two requirements at the same precedence cannot both be satisfied, do not implement. Add a reviewed clarification, update this index, and reconcile the active plan before proceeding.

---

## 4. Consolidated hard contracts

### 4.1 Review disposition and independence

The authoring-side disposition for original findings `AEX-IR-C01`–`AEX-IR-C03` and `AEX-IR-I01`–`AEX-IR-I07` is `fixed`.

The fresh artifact-only pre-closure pass also found and remediated:

```text
AEX-CR-I01 design/implementation closure conflation
AEX-CR-I02 release-range mismatch
AEX-CR-I03 predecessor Policy-change gate omitted
AEX-CR-I04 owner-acceptance evidence undefined
```

Authoring-side remediation does not close any Critical or Important finding. Formal design closure requires a reviewer that did not author the remediation.

### 4.2 Automatic lifecycle and triggering

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
- No Hook emits record text, checkpoint text, remote state, prompt text, transcript data, path, branch, or HEAD.
- Hook hot paths do not call network, LLM, provider, recall, shared scan, reindex, Git mutation, `seal`, `promote`, or `gc`.
- Dynamic `refresh_required` and checkpoint state are returned only by explicit CLI commands.

Supported setup combines:

```text
active AGENTS managed routing block
+ fixed SessionStart notice
+ Skill description matching
+ explicit invocation
```

This makes preflight the default instructed workflow. V1 does not claim that arbitrary repository edits are mechanically intercepted.

### 4.3 Preflight receipt

`start`, `checkpoint`, `capture`, `seal`, provider setup apply, Policy candidate materialization, installer mutation, uninstall, migration, and guarded GC use a valid local operation-specific receipt where the applicable Task defines one.

`PreflightReceiptV1` is controller-created and local-only.

- The CLI returns only its receipt ID.
- Caller-supplied receipt JSON, stdin body, shared record, or repository file is never accepted.
- It binds repository, worktree, branch, HEAD, canonical snapshot digests, config digest, active Policy binding, workstream, operation, scope, use context, CLI version, nonce, issue time, and expiry.
- Mutation receipts are single-use and valid for at most five minutes.
- Every gated command recomputes current bindings before atomic consumption.

Missing or invalid receipt:

```text
preflight_required
```

### 4.4 Local checkpoint and continuation

Automatic resume requires:

```text
local identity and snapshot classification == exact
candidate checkpoint is unique
```

Multiple exact candidates produce:

```text
ambiguous_checkpoint
```

For remote-dependent continuation, one explicit command performs current refresh and decision. It additionally requires:

```text
all dependencies observed in the current use-context
all repository bindings valid
all decision state digests unchanged
all active Policy revisions unchanged
```

No separately stored old refresh receipt is sufficient.

V1 has no same-checkpoint manual JSON review receipt. Any non-exact or remote-changed continuation uses only:

```text
agent-experience start --from-checkpoint <id> --stable-only --json
```

This creates a successor workstream and transfers only records whose recursive dependency closure proves `immutable_stable` or currently `scope_revalidated`.

### 4.5 Policy repository boundary

Policy belongs to the target repository:

```text
<target-repository>/.agent-experience/acceptance-policy.json
```

Immutable Policy revisions live at:

```text
.agent-experience/policies/<lineage-id>/<revision>-<digest>.json
```

V1 rejects cross-repository include, inheritance, extension, and URL reference. Policy repository numeric ID must equal the current target repository numeric ID.

### 4.6 Bootstrap approval trust root

Built-in v1 can generate a candidate bootstrap Policy and deterministic mutation plan. It cannot activate the Policy from:

```text
TTY input
repository bytes
unsigned audit records
self-declared human JSON
agent-authored approval text
```

Activation requires a trusted outer approval provider that the worker cannot mint or configure from target-repository data. The verified receipt binds:

```text
trusted issuer
repository numeric ID
owner numeric ID
Policy lineage ID
Policy revision digest
plan digest
nonce
issued-at / expiry
subject
```

No trusted provider:

```text
bootstrap_manual_governance_required
```

TTY re-entry is UX confirmation only.

### 4.7 Policy lineage and successor changes

Every Policy revision binds:

```text
policy_lineage_id
revision_number
bootstrap root receipt ID / digest
exact predecessor revision / digest / blob / path / authoritative head
change_evidence_digest
repository binding
```

Rules:

- root revision requires verified trusted bootstrap approval;
- later revisions reference the exact current active predecessor;
- revision is predecessor plus one;
- rollback, second bootstrap, old-predecessor fork, stale base head, repeated revision, missing predecessor, and force-pushed lineage break are rejected or `policy_lineage_inconsistent`;
- lineage recovery and rebootstrap are future separate governance protocols.

A successor cannot approve itself. Current Policy `P(n)` governs `P(n+1)` through its own `policy_change` block.

A successor is eligible only when:

```text
exact predecessor and base-head binding pass
predecessor policy_change schema is valid
required exact-login approvals pass
required check-run predicates pass
review/check collections are complete
approvals/checks bind to the current candidate validation SHA
no rollback/fork/reset/lineage break exists
candidate revision and pointer reach the authoritative ref
```

Missing, partial, stale, old-head, ambiguous, wrong-App, wrong-SHA, or wrong-phase evidence never passes.

### 4.8 Content-binding modes

Allowed:

```text
exact_blob
authoritative_ref_current
```

`exact_blob` is mandatory for security, governance, authority, release, deployment, frozen requirements, and exact accepted specifications.

`authoritative_ref_current` is restricted to living artifacts evaluated from the current authoritative head. It must not contain:

```text
required_pull_requests
review_policy
pre_merge checks
post_merge_result checks
historical PR/reviewer predicates
```

It may use current-path predicates and `post_merge_authoritative_head` check runs only. Artifacts requiring PR/reviewer provenance use `exact_blob`.

### 4.9 Record provenance and `seal`

Remote provenance classes:

```text
builtin_refresh
untrusted_import
test_fixture
```

Only a current-use-context `builtin_refresh` may serve current remote evidence, accepted-artifact predicates, or remote-dependent resume.

Production `remote observe` imports are `untrusted_import` and historical only.

`seal` proves only:

```text
closed schema
safe path
resource limits
secret/local-path gate
canonical digest
exclusive working-tree file creation
```

It does not prove truth, current evidence, approval, accepted status, Git inclusion, publication, promotion, or authority. Seal, commit, and authoritative-ref reachability never upgrade provenance class.

### 4.10 Trusted GitHub CLI identity

Tracked configuration cannot specify an executable, wrapper, command, extension, environment override, arbitrary arguments, or full endpoint URL.

Provider setup resolves the literal GitHub CLI locally and stores a canonical absolute executable identity in Git-common-dir local state.

- relative or arbitrary executable paths are rejected;
- worktree, Git-common-dir, temporary, symlink, and Windows reparse-point executables are rejected;
- invocation uses stored absolute path, `shell=False`, fixed argv, and controlled environment;
- file digest and local file identity are revalidated before each invocation;
- drift returns `provider_executable_integrity_failure` before network access.

### 4.11 Typed GitHub Provider v1

V1 supports a GitHub.com read-only adapter only.

The provider accepts typed operations, not caller-supplied URLs or methods.

- every request is GET-only;
- branch/ref is encoded from a decoded typed value;
- file path is normalized, split, and encoded segment-by-segment;
- query keys and values are encoded separately;
- pre-encoded `%HH` input is rejected;
- full URL, endpoint text, GraphQL, extension command, and arbitrary header input are rejected;
- normalized response is rebound to repository numeric ID and exact typed request key.

GHES and GHE.com custom hosts return `host_unsupported` in v1.

### 4.12 Pagination completeness

Latest/effective review and check-run decisions require a complete collection.

Closed limits:

```text
100 requested items per page
20 pages per resource
2000 items per resource
16 MiB normalized bytes per resource
30 seconds remote batch wall time
```

Only validated GitHub `Link rel="next"` relations for the same host, typed operation, repository, API version, and resource are followed.

Any incomplete pagination, rate limit, timeout, malformed link, cap exceedance, or partial response yields:

```text
unknown / partial_response
```

A partial collection never produces a pass predicate.

### 4.13 Remote digests and freshness

Keep distinct:

```text
provider_payload_digest
provider_result_digest
state_digest
record_digest
```

`changed` and checkpoint compatibility use resource-specific decision-state `state_digest`.

`fresh` means observed successfully for this use-context at `observed_at`; it does not mean remote state is locked.

Remote-dependent continuation performs same-command refresh-and-decide. Residual TOCTOU is documented, and state is revalidated before current-state display, accepted-artifact evaluation, checkpoint publication, and handoff to an external write workflow.

### 4.14 Remote result taxonomy

```text
refresh_required
fresh
changed
unknown
unavailable
superseded
```

- `unknown`: call completed but current meaning is ambiguous.
- `unavailable`: call could not be performed or completed.
- 404 alone does not prove absence or `not_accepted`.
- an old observation plus failed refresh is never current fact.

### 4.15 Accepted-artifact SHA graph

Keep separate:

```text
pr_head_sha
pr_test_merge_sha
pr_merge_result_sha
authoritative_head_sha
artifact_blob_sha
artifact_introducing_commit_sha
validation_sha
```

Proposal review binds to current PR head.

Required check-run entries state an explicit phase:

```text
pre_merge
post_merge_authoritative_head
post_merge_result
```

Cross-SHA, cross-App, cross-phase, incomplete, or stale result reuse is prohibited.

### 4.16 Check-run-only scope

Agent Experience v1 evaluates GitHub check runs only. Policy check entries require:

```text
source = "check_run"
```

`commit_status`, `both`, source omission, and branch-protection parity requests are unsupported. Accepted-artifact results explicitly report that branch-protection parity was not evaluated.

`require_last_push_approval=true` is unsupported. The implementation does not approximate a last-push actor from author or committer fields.

### 4.17 Effective review semantics

COMMENTED does not revoke APPROVED or CHANGES_REQUESTED.

For each reviewer:

1. remove malformed/pending entries;
2. apply dismissals by exact review identity;
3. select the final decision review from APPROVED and CHANGES_REQUESTED only;
4. bind required approval to current candidate/PR head when Policy requires it.

Result:

```text
current-head APPROVED -> pass
CHANGES_REQUESTED -> fail
old-head approval -> pending
no decision review -> pending
dismissal ambiguity -> unknown
```

V1 does not claim complete GitHub ruleset or merge-readiness parity.

### 4.18 Canonical JSON, storage, and concurrency

Canonical JSON rejects floats, NaN, Infinity, duplicate keys, unsafe paths, invalid UTF-8, and non-canonical timestamps. Timestamps are UTC `YYYY-MM-DDTHH:MM:SSZ`.

One SQLite database exists per Git common directory and is namespaced by repository and worktree.

- `foreign_keys=ON`;
- WAL where supported;
- `busy_timeout=750ms`;
- checkpoint updates use optimistic revision comparison;
- network fetch holds no write transaction;
- refresh results commit in a short `BEGIN IMMEDIATE` transaction;
- reindex uses shadow generation plus atomic activation;
- recall pins one active index generation;
- Hook lock timeout is silent exit 0;
- explicit mutation lock timeout is exit 5 with no partial write.

### 4.19 Safety invariants

Ordinary prose instructions cannot disable:

- Experience is not authority;
- Remote Provider is read-only;
- secret/credential persistence is prohibited;
- stale, forged, partial, or unknown remote state is not current fact;
- self-declared promotion is invalid;
- non-exact checkpoint does not auto-resume;
- Hook network access is prohibited;
- `seal` does not publish to Git;
- repository configuration cannot select provider executable;
- repository bytes cannot establish bootstrap approval;
- shared/config mutation fails closed on integrity uncertainty.

Changing these invariants requires the designated specification/governance workflow.

---

## 5. Sole active implementation plan

```text
docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md
```

The plan is rewritten in place and contains 30 Tasks. Superseded plans remain historical pointers only.

## 6. Release order

```text
v0.1 Local Resume MVP       Tasks 1-9
v0.2 Memory Core            Tasks 10-17
v0.3 Remote Observation MVP Tasks 18-19
v0.4 Remote Governance      Tasks 20-23
v0.5 Automatic Lifecycle    Tasks 24-26
v1.0 Reviewed Rollout       Tasks 27-30
```

Task 19 GitHub Provider and Task 20 bootstrap approval boundary may be implemented in parallel only after Task 18 freezes shared interfaces. Task 21 Policy lineage joins both. Tasks 22 and 23 complete Remote Governance.

## 7. Hard gates

- Task 1 baseline precedes any real Policy bootstrap.
- No real Policy activation occurs without a trusted approval provider.
- Formal design closure must be valid before Task 1.
- Repository-owner acceptance of the exact closed design is required before Task 1.
- Memory, provider, Policy, receipt, pagination, encoding, and remote-continuation tests are green before automatic lifecycle work.
- Phase 1 completes before Hook installer implementation.
- Hook module has no provider/network dependency path.
- Existing-Skill adapters do not change external authority, snapshot, gate, or standalone behavior.

## 8. Review artifacts and owner acceptance

### 8.1 Authoring-side preflight

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-closure-preflight.md
```

This file may identify and repair defects but cannot close findings.

### 8.2 Formal design closure

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-closure.md
```

It binds the exact reviewed commit and blobs. Every original and reconciliation finding must be `verified_closed` or `reasoned_rejected`. Any `disputed` or open Critical/Important finding keeps Task 1 at `NO-GO`.

### 8.3 Repository-owner acceptance

The repository owner explicitly accepts the exact closed design in the active host interaction or through a trusted approval provider.

An audit file may be recorded at:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-owner-acceptance.json
```

Repository JSON alone is not proof of approval. Design changes invalidate prior acceptance.

### 8.4 Implementation closure

```text
docs/superpowers/reviews/2026-08-23-agent-experience-implementation-closure.md
```

This is created only after implementation, tests, CI, and pilot evidence exist. It cannot substitute for the pre-Task-1 design closure.

## 9. Current gate state

```text
Original ten findings: authoring-fixed, pending formal independent verification
Reconciliation findings AEX-CR-I01..I04: authoring-fixed, pending formal independent verification
Formal design closure: absent
Repository-owner acceptance: absent
Task 1 readiness: NO-GO
PR readiness: NO-GO
Merge readiness: NO-GO
```