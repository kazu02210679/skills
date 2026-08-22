# Agent Experience v1 — Independent Artifact Review

- **Review date:** 2026-08-22
- **Reviewed branch:** `docs/agent-experience-design`
- **Reviewed head:** `90f86beb754989435b4719a6b3c692561b008f04`
- **Review mode:** fresh artifact-only review. The review used the branch documents as the source of truth and did not use the authoring conversation as evidence.
- **Scope:** Critical / Important findings only
- **Decision:** **NO-GO for Task 1**

## Review contract

A finding is reported only when it has all of the following.

- stable finding ID
- Critical or Important severity under the Contract Index taxonomy
- exact affected contract or plan section
- concrete exploit, counterexample, or deterministic failure mode
- required correction
- closure test

Minor wording, naming preference, future extension, and optional product enhancement are excluded.

## Summary

| Severity | Count | IDs |
|---|---:|---|
| Critical | 3 | `AEX-IR-C01`–`AEX-IR-C03` |
| Important | 7 | `AEX-IR-I01`–`AEX-IR-I07` |

The design is not ready to enter Task 1 because the Contract Index requires every Critical / Important finding to be independently verified closed or reasoned rejected before implementation begins.

---

## AEX-IR-C01 — Repository-controlled provider executable permits arbitrary code execution

- **Severity:** Critical
- **Contract sections:** Consolidated Plan, Task 4 and Task 19; Contract Index §4.11
- **Owner:** Remote provider / configuration contract
- **Disposition:** Open

### Evidence

The active plan places `executable: str` inside tracked repository configuration and later constructs provider subprocesses from the configured executable. The contract requires `shell=False` and GET-only GitHub endpoints, but it does not remove repository control over the executable being launched.

### Exploit / counterexample

A repository contains:

```toml
[remote]
provider = "github"
executable = "./tools/gh"
```

and commits an executable `tools/gh` or `gh.exe`. When `remote refresh` runs, the process executes repository-supplied code with the user's local filesystem and GitHub credential environment. `shell=False` and `--method GET` do not constrain what the selected executable does.

The same class of attack is possible through current-directory or PATH shadowing, symlink/reparse-point replacement, and Windows executable resolution.

### Required correction

- Remove the provider executable path from Git-tracked repository configuration.
- The v1 provider command must use a local-only, setup-time resolved executable identity.
- Permit only the literal GitHub CLI capability; reject arbitrary executable names, arguments, wrappers, extensions, or repository-relative paths.
- Resolve and store the canonical executable path in local state, outside the target repository.
- Reject executables located inside the worktree, Git common directory, temporary extraction directory, or another writable project path.
- Detect symlink/reparse-point replacement or executable preimage drift before invocation.
- Use a controlled environment and fixed argv allowlist.

### Closure tests

```text
tracked config names ./gh -> rejected
repo-root gh / gh.exe shadows PATH -> rejected
configured python, sh, cmd.exe, powershell.exe -> rejected
setup records trusted gh then file is replaced -> integrity failure
symlink/reparse target changes -> integrity failure
Windows PATHEXT/current-directory lookup cannot select repository binary
normal trusted gh capability fixture -> accepted
```

---

## AEX-IR-C02 — Bootstrap approval is forgeable by the worker and is not a durable trust root

- **Severity:** Critical
- **Contract sections:** Trust Roots Clarification §1.3–§1.7; Contract Index §4.5
- **Owner:** Policy bootstrap contract
- **Disposition:** Open

### Evidence

Bootstrap apply accepts either an interactive TTY re-entry or a trusted outer-controller receipt. The resulting Git-tracked bootstrap audit record is explicitly not cryptographically signed. A later verifier activates the Policy from the Policy file, audit record, matching digests, and current owner metadata.

### Exploit / counterexample

1. The agent already runs under the repository owner's authenticated `gh` account.
2. It starts the bootstrap command under a pseudo-terminal and programmatically supplies the repository name and Policy digest.
3. It creates the Policy and unsigned audit record, then later commits or causes them to reach the authoritative branch.
4. A verifier sees matching repository/owner metadata and activates the Policy.

A pseudo-terminal proves only that input came through a TTY. It does not prove that a human supplied the input. The unsigned audit record also cannot prove that the owner, rather than the worker with repository write access, approved the bootstrap.

### Required correction

- Do not treat TTY re-entry as an authorization factor. It may remain a UX confirmation only.
- Bootstrap apply must require a host- or controller-mediated approval receipt that the worker cannot mint or edit.
- Define a closed approval-receipt contract: trusted issuer registry, receipt schema version, repository ID, owner ID, Policy digest, plan digest, nonce, issued-at, expiry, replay protection, and exact-byte validation.
- The durable active-Policy decision must verify that receipt through the trusted provider; repository files alone cannot establish bootstrap approval.
- If no trusted approval provider is available, v1 must stop at candidate generation and return `bootstrap_manual_governance_required`.

### Closure tests

```text
worker drives a pseudo-TTY and retypes challenge -> apply rejected
self-declared human JSON -> rejected
unsigned matching bootstrap audit on main -> not active
receipt copied to another repository -> rejected
receipt copied to another Policy digest -> rejected
receipt replay / nonce reuse -> rejected
expired or unknown issuer receipt -> rejected
valid trusted-provider receipt -> candidate can enter the defined activation flow
```

---

## AEX-IR-C03 — Policy lineage can be reset, rolled back, or forked through an undefined predecessor chain

- **Severity:** Critical
- **Contract sections:** Open Questions Clarification §2.2–§3.1; Trust Roots Clarification §1.6–§1.8; Contract Index §4.5
- **Owner:** Acceptance Policy lifecycle
- **Disposition:** Open

### Evidence

The contract states that `P(n)` governs `P(n+1)`, but the concrete Policy schema does not bind a candidate to an exact predecessor digest, predecessor blob, sequence, or base authoritative head. It also does not define a persistent bootstrap lineage anchor or a deterministic rule for detecting a second bootstrap after a Policy has already existed.

### Exploit / counterexample

- `P2` is active and requires two approvals.
- A new file `P0-prime` with weaker rules is placed on the authoritative branch together with a new matching bootstrap audit record.
- The active-Policy verifier has no closed lineage field proving that bootstrap was already consumed or that `P0-prime` must be governed by `P2`.

A related rollback uses an old permissive `P1` as the claimed predecessor for a new revision after stricter `P2` became active. A fork can produce two candidate successors from the same predecessor without a deterministic conflict state.

### Required correction

Add a closed Policy lineage contract containing at least:

```text
policy_lineage_id
revision_number
predecessor_policy_digest
predecessor_blob_sha
base_authoritative_head_sha
change_evidence_digest
bootstrap_root_receipt_id
```

Rules:

- Bootstrap is valid only when no trusted bootstrap root exists for the lineage.
- Every later Policy must reference the exact currently active predecessor and base authoritative head.
- Revision numbers are monotonic and cannot be reused.
- Multiple valid successors, rollback to an older digest, missing history, force-pushed lineage breaks, and second-bootstrap attempts produce `policy_lineage_inconsistent`.
- Rebootstrap or lineage recovery is a separate owner-governed recovery protocol, not the normal bootstrap path.

### Closure tests

```text
second bootstrap after P1 -> rejected
P3 references old P1 while P2 is active -> rejected
candidate base head is stale -> rejected
revision number repeats or decreases -> rejected
two successors from one predecessor -> inconsistent
force-push removes predecessor -> inconsistent
valid P1 -> P2 exact chain -> accepted for evaluation
```

---

## AEX-IR-I01 — The active implementation plan still contradicts the binding contract corpus

- **Severity:** Important
- **Contract sections:** Consolidated Plan Tasks 1, 4, 7, 18–21; Contract Index §5–§7; Trust Roots Clarification §18
- **Owner:** Implementation plan
- **Disposition:** Open

### Evidence

The Contract Index names one consolidated plan as the implementation source of truth, but the plan predates the Trust Roots clarification and still contains obsolete interfaces and test matrices. Examples include:

- Task 18 still defines one `response_digest` instead of payload/result/state/record digests and omits provenance class and `use_context_id`.
- Task 20 omits bootstrap trust-root implementation, Policy lineage, content-binding selection gate, full SHA graph, check phase, and effective-review corrections.
- Task 21 treats a separately refreshed `fresh` state as sufficient for auto-resume instead of same-command refresh-and-decide.
- Task 7 omits the binding requirements for checkpoint optimistic revision and active index-generation pinning.
- Task 1 omits the newer bootstrap, imported-observation, and seal-as-authority pressure cases.

### Counterexample

An implementer follows Task 18–21 literally and passes every test written in those Tasks. The resulting system can still reuse a previous remote refresh, lacks provenance classes, and has no bootstrap trust root, despite satisfying the active plan as written.

### Required correction

Rewrite the consolidated plan at its existing canonical path so that every current binding requirement appears directly in the applicable Task, interface, RED test, GREEN condition, and commit boundary. Do not rely on prose saying that external amendments also apply.

### Closure tests

- Add a machine-readable requirement-to-task matrix with stable requirement IDs.
- Fail plan validation when a binding requirement has no Task and focused test.
- Remove obsolete terms and interfaces such as the singular remote `response_digest` and separately reusable fresh receipt.
- Assert the plan contains the bootstrap trust root, Policy lineage, provenance classes, same-command refresh-and-decide, optimistic checkpoint revision, and index-generation pinning.
- Re-run a fresh implementation-plan review against only the rewritten plan plus Contract Index.

---

## AEX-IR-I02 — `authoritative_ref_current` can accept content that bypassed the required review and checks

- **Severity:** Important
- **Contract sections:** Trust Roots Clarification §3.2 and §4.3–§4.5; Contract Index §4.6 and §4.12
- **Owner:** Accepted-artifact evaluator
- **Disposition:** Open

### Evidence

For `authoritative_ref_current`, the current blob is accepted without an expected blob SHA. Integration predicates require a configured PR result to be an ancestor of the current authoritative head, but do not require the current blob to be the blob introduced by that reviewed and checked PR. `artifact_introducing_commit_sha` is named but no mandatory predicate binds it to current review/check evidence.

### Counterexample

1. PR #12 introduces blob `A`, receives required approval/checks, and merges.
2. A later direct push or unrelated PR changes the same path to blob `B` without the required review/checks.
3. PR #12's merge result remains an ancestor of the authoritative head.
4. `authoritative_ref_current` accepts current blob `B`, while the historical PR #12 review/check predicates remain green.

The evaluator can therefore report `accepted` for content that never passed the configured acceptance process.

### Required correction

Choose one closed v1 rule:

1. **Recommended:** if an artifact has required PR/reviewer predicates, require the current `artifact_blob_sha` to equal the blob at the accepted provenance commit / PR merge result; otherwise return `pending` or `inconsistent`.
2. Alternatively, restrict `authoritative_ref_current` to current-authoritative-head checks only and prohibit historical PR/reviewer predicates for that mode.

If the latest path-changing provenance cannot be determined unambiguously across merge, squash, rebase, rename, revert, or direct push, the result must be `unknown`, not `accepted`.

### Closure tests

```text
reviewed blob A then unreviewed direct-push blob B -> not accepted
reviewed blob A then unrelated PR changes path -> not accepted
reviewed change later reverted -> not accepted as original content
rename / cherry-pick / squash provenance ambiguous -> unknown
current blob exactly bound to accepted provenance -> accepted
```

---

## AEX-IR-I03 — Provider pagination completeness is undefined and can reverse review/check decisions

- **Severity:** Important
- **Contract sections:** Consolidated Plan Task 19; Trust Roots Clarification §7–§8
- **Owner:** GitHub read-only provider
- **Disposition:** Open

### Evidence

The provider plan lists review and check-run endpoints but defines no pagination-completeness contract. The evaluator selects the effective latest decision review and latest check run, which is only sound when the complete relevant result set has been retrieved.

GitHub's review and check-run list endpoints are paginated; the normal page size is bounded. A partial page cannot be treated as a complete chronology.

### Counterexample

- Page 1 contains an older `APPROVED` review.
- Page 2 contains a later `CHANGES_REQUESTED` review.
- The provider reads only page 1 and reports the reviewer predicate as pass.

The same defect can omit a later failing check run, a duplicate check name from another App, or a dismissal record.

### Required correction

- Define pagination per supported endpoint.
- Request the maximum supported page size and follow provider pagination until complete.
- Set closed maximum pages/items/bytes and a batch deadline.
- Record a `complete` flag and page/item counts in the normalized provider result.
- Any rate limit, timeout, page cap, malformed Link relation, or partial response before completion yields `unknown/partial_response`.
- For check-run limits that cannot guarantee complete history, return `unknown` rather than selecting from a truncated set.

### Closure tests

```text
latest CHANGES_REQUESTED occurs on page 2 -> fail
latest successful/failing check occurs on later page -> correct latest result
duplicate app/name appears on later page -> inconsistent
rate limit after first page -> unknown
configured maximum exceeded -> unknown, never pass
pagination order changes but normalized set is same -> same result
```

References:

- GitHub REST pagination documentation
- GitHub pull-request review list endpoint
- GitHub check-run list endpoint

---

## AEX-IR-I04 — `valid preflight receipt` has no closed schema or invalidation rule

- **Severity:** Important
- **Contract sections:** Contract Index §4.1; Consolidated Plan Task 7 and Task 9
- **Owner:** Local lifecycle / CLI contract
- **Disposition:** Open

### Evidence

The Contract Index requires `start`, `checkpoint`, `capture`, and `seal` to present a valid preflight receipt, but the binding corpus does not define the receipt fields, issuer, storage location, snapshot binding, validity interval, replay behavior, or invalidation conditions. The plan does not create a preflight-receipt interface or table.

### Counterexample

1. Run preflight on branch `A`, HEAD `H1`, clean snapshot `S1`.
2. Switch branch, change HEAD, modify config/Policy, or alter scoped files.
3. Reuse the old receipt to call `checkpoint`, `capture`, or `seal`.

Without a closed binding, both the stale and current receipts are equally "valid" to an implementation.

### Required correction

Define `PreflightReceiptV1` as local-only, controller-created state. At minimum bind it to:

```text
repo_id
worktree_id
branch_ref
head_sha
canonical snapshot digest set
config digest
active Policy digest or explicit none
workstream_id / operation scope
CLI contract version
use_context_id
issued_at
nonce / receipt ID
```

- Do not accept a receipt from arbitrary JSON, stdin, or a shared record.
- Recompute current identity/snapshot/config before every gated command.
- Any mismatch invalidates the receipt.
- Define whether a receipt is single-use or reusable only while every bound value remains exact.

### Closure tests

```text
receipt copied to another repo/worktree -> rejected
branch or HEAD changes -> rejected
tracked/untracked/scope digest changes -> rejected
config or active Policy changes -> rejected
receipt JSON supplied by caller -> rejected
exact unchanged context -> accepted
```

---

## AEX-IR-I05 — Check-run-only evaluation is inconsistent with the contract's checks/statuses language

- **Severity:** Important
- **Contract sections:** Contract Index §4.12 and §4.14; Trust Roots Clarification §8.4; Consolidated Plan Task 19–20
- **Owner:** Accepted-artifact check semantics
- **Disposition:** Open

### Evidence

The SHA-selection rule refers to applicable checks/statuses, while the provider and evaluator designate only `check_run` as the accepted source. GitHub required status checks may be either Checks API runs or commit statuses. If a check and a status share the same required context name, GitHub can require both.

### Counterexample

On the validation SHA:

```text
check_run "ci/build" -> success
commit status "ci/build" -> failure
```

The proposed evaluator sees only the check run and reports pass, while the repository's actual required status context remains failing.

### Required correction

Make one explicit v1 choice:

- Add a `commit_status` resource and require each Policy check to state `source = check_run | commit_status | both`; or
- State that Agent Experience Policy is intentionally check-run-only, prohibit branch-protection parity claims, remove checks/statuses wording, and reject any Policy that asks for commit-status semantics.

If the Policy does not specify the source and the same context could be supplied by both mechanisms, return `inconsistent`.

### Closure tests

```text
check success + status failure same name -> not pass
status-only required context -> handled according to explicit source
check/status same name with source omitted -> inconsistent
check from wrong App -> not pass
```

References:

- GitHub protected-branch and ruleset documentation for required status checks
- GitHub Checks API documentation
- GitHub commit-status API documentation

---

## AEX-IR-I06 — `require_last_push_approval` is declared but cannot be evaluated from the defined provider data

- **Severity:** Important
- **Contract sections:** Trust Roots Clarification §7.4; Open Questions Clarification review policy; Consolidated Plan Task 19–20
- **Owner:** Review predicate contract
- **Disposition:** Open

### Evidence

The Policy may declare `require_last_push_approval`, but the provider schema and endpoint set do not define a trusted last-pusher identity or an algorithm proving that an approving reviewer is different from the person who made the most recent reviewable push.

### Counterexample

- PR author is user `A`.
- Collaborator `B` makes the most recent push.
- `B` then approves the PR.
- `require_distinct_author_and_reviewer=true` passes because `B != A`.
- GitHub's last-push approval rule should fail because the last pusher and approver are both `B`.

### Required correction

For v1, either:

- add a verified last-reviewable-push actor source and bind the approval predicate to that actor and current head; or
- reject `require_last_push_approval=true` as `unsupported_resource_semantics` until such a source exists.

Do not approximate the last pusher with commit author or committer identity; those are not equivalent to the actor who pushed the reviewable update.

### Closure tests

```text
last pusher approves -> fail/pending
other authorized reviewer approves after last push -> pass
push actor unavailable -> unknown
commit author differs from pusher -> no author-based approximation
```

Reference:

- GitHub protected-branch documentation for approval of the most recent reviewable push

---

## AEX-IR-I07 — Endpoint interpolation and percent-encoding are not closed

- **Severity:** Important
- **Contract sections:** Consolidated Plan Task 19; Remote Provider endpoint allowlist
- **Owner:** GitHub provider request builder
- **Disposition:** Open

### Evidence

The plan defines endpoint string templates such as:

```text
repos/{owner}/{repo}/contents/{path}?ref={ref}
```

but does not define segment-wise encoding, query-value encoding, rejection of double encoding, or canonicalization before allowlist matching.

### Counterexample

A valid Git path may contain characters meaningful to a URL query or fragment. Raw interpolation of a path or ref containing `?`, `&`, `#`, `%2f`, or Unicode variants can change the requested endpoint, query parameters, or binding while still beginning with an allowed template prefix.

The request remains GET-only but may fetch a different object than the `RemoteResourceKey` claims, producing a falsely bound observation.

### Required correction

- Build requests from typed resource fields, never from caller-supplied endpoint text.
- Percent-encode each path segment separately.
- Encode query keys and values separately.
- Define canonical handling for `/`, `%`, Unicode, empty segments, and already-encoded input.
- Perform allowlist validation on the typed operation before URL construction, not on a string prefix after interpolation.
- Bind the normalized response back to the exact typed request key.

### Closure tests

```text
file path contains ?, &, #, %, Unicode -> exact intended file only
branch/ref contains reserved characters allowed by Git -> exact intended ref only
double-encoded slash -> rejected
caller supplies full URL or endpoint string -> rejected
response repository/path/ref differs from request key -> integrity failure
```

---

## Required disposition format

For every finding, the authoring side must record one of:

```text
fixed
reasoned_rejected
disputed
```

A `fixed` finding requires the specified closure tests and fresh independent verification. A `reasoned_rejected` finding requires concrete counter-evidence from the binding contract or executable test. `disputed` remains open.

## Final judgment

```text
Critical open: 3
Important open: 7
Task 1 readiness: NO-GO
PR readiness: NO-GO
Merge readiness: NO-GO
```

No implementation task should begin until all ten findings are independently closed or reasoned rejected and the repository owner accepts the corrected design contract.