# Agent Experience v1 — Closure Review Reconciliation

- **Document date:** 2026-08-23
- **Target:** `agent-experience` v1
- **Status:** Binding reconciliation
- **Reviewed input:** corrected artifact set at commit `c3ac1c0435e04ffb6e42d664be4243341c0ab2e0`
- **Review mode:** fresh artifact-only pre-closure review

## 0. Scope and reviewer independence

This document records defects found while re-reading only the corrected repository artifacts:

- the original independent review;
- the independent-review remediation contract;
- the Contract Index;
- the active consolidated implementation plan;
- the machine-readable remediation matrix.

The reviewing assistant also authored earlier remediation changes. Therefore this pass is technically fresh and artifact-only, but it does **not** satisfy the contract's organizational independence rule. It may find and repair defects, but it does not self-close Critical or Important findings.

Formal closure still requires a reviewer that did not author the remediation. That reviewer records `verified_closed`, `reasoned_rejected`, or `disputed` in the design-closure artifact.

This reconciliation has higher precedence than earlier documents in the domains listed below.

---

## 1. `AEX-CR-I01` — Design closure and implementation closure were conflated

- **Severity:** Important
- **Affected artifacts:** active plan Task 28; Contract Index independent closure gate
- **Disposition:** fixed, pending independent verification

### Failure mode

The pre-Task-1 design closure and the post-implementation closure were both directed toward a generic file named:

```text
docs/superpowers/reviews/2026-08-22-agent-experience-independent-review-closure.md
```

These are different review objects:

1. **Design closure** decides whether Task 1 may begin.
2. **Implementation closure** decides whether the completed Skill may roll out.

Using one path permits a pre-implementation review to be mistaken for implementation evidence, or a later implementation review to overwrite design provenance.

### Closed rule

Use separate immutable review stages:

```text
Design closure:
docs/superpowers/reviews/2026-08-23-agent-experience-design-closure.md

Implementation closure:
docs/superpowers/reviews/2026-08-23-agent-experience-implementation-closure.md
```

An authoring-side diagnostic pass uses a third path and is never formal closure:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-closure-preflight.md
```

The design-closure artifact binds the exact reviewed Contract Index blob, active-plan blob, remediation-contract blob, remediation-matrix blob, branch, and reviewed commit.

The implementation-closure artifact additionally binds implementation HEAD, full verification output locators, pilot evidence, CI runs, and code/test digests.

### Closure tests

```text
design closure path != implementation closure path
Task 1 gate reads design closure only
rollout gate reads implementation closure only
preflight review cannot satisfy either gate
review artifact reviewed-head/blob mismatch -> invalid
```

---

## 2. `AEX-CR-I02` — Release boundaries no longer matched the active Task graph

- **Severity:** Important
- **Affected artifacts:** Contract Index phase/release order; active plan Task map
- **Disposition:** fixed, pending independent verification

### Failure mode

The corrected plan moved remote continuation after accepted-artifact evaluation, but the Contract Index still described:

```text
v0.4 Remote Governance   Tasks 20-21
v0.5 Automatic Lifecycle Tasks 22-24
```

In the then-current plan, Task 22 was still remote continuation rather than a Hook task. A release could therefore be labelled automatic lifecycle before remote governance was complete.

### Closed release boundaries

The reconciled active plan uses 30 Tasks and the following boundaries:

```text
v0.1 Local Resume MVP       Tasks 1-9
v0.2 Memory Core            Tasks 10-17
v0.3 Remote Observation MVP Tasks 18-19
v0.4 Remote Governance      Tasks 20-23
v0.5 Automatic Lifecycle    Tasks 24-26
v1.0 Reviewed Rollout       Tasks 27-30
```

Task meaning is fixed as:

```text
20 bootstrap approval-provider boundary
21 immutable Policy lineage and predecessor-governed Policy changes
22 accepted-artifact evaluator
23 same-command remote continuation
24 route-only Hooks
25 setup installer / Hook ownership
26 conflict-safe uninstall
27 final Skill and operator documentation
28 read-only existing-Skill adapters
29 CI / requirement validation / disposable integration
30 pilot / implementation closure / rollout gate
```

### Closure tests

```text
each release range maps to contiguous declared Tasks
remote continuation is inside Remote Governance
Hook/setup/uninstall only are inside Automatic Lifecycle
implementation closure occurs only in Reviewed Rollout
Contract Index and active plan ranges are byte-for-byte equivalent
```

---

## 3. `AEX-CR-I03` — The active plan omitted predecessor-governed Policy-change evaluation

- **Severity:** Important
- **Affected artifacts:** Open Questions Clarification §2.3; active plan Policy Task
- **Disposition:** fixed, pending independent verification

### Failure mode

The binding corpus says current Policy `P(n)` governs acceptance of `P(n+1)`. The rewritten active plan included bootstrap approval and exact predecessor lineage, but did not directly require evaluation of the predecessor Policy's `policy_change` approval/check predicates.

An implementation could validate an exact predecessor chain while activating a successor that never satisfied the predecessor's required approvers or required check runs.

### Closed Policy-change contract

Task 21 owns a pure, deterministic successor-Policy evaluator. It consumes normalized complete evidence types frozen by Task 18 and provider results produced by Task 19.

A non-root Policy revision activates only when all of the following hold:

```text
candidate predecessor == current active Policy revision/digest/blob/path
candidate revision_number == predecessor + 1
candidate base_authoritative_head == evaluated base head
candidate cannot use its own policy_change block to approve itself
predecessor policy_change schema is valid
all predecessor required approver predicates pass
all predecessor required check-run predicates pass
change evidence is complete and bound to candidate head/base
no competing successor, rollback, reset, or lineage break exists
candidate revision and pointer are present on authoritative ref
```

`policy_change` v1 fields are closed:

```json
{
  "required_approvers": ["exact-login"],
  "minimum_approvals": 1,
  "require_distinct_author_and_approver": true,
  "required_checks": [
    {
      "source": "check_run",
      "name": "validate-policy",
      "app_id": null,
      "phase": "pre_merge",
      "allowed_conclusions": ["success"]
    }
  ]
}
```

Rules:

- reviewer identities are exact GitHub logins;
- wildcards, team names, permission roles, and inferred maintainers are unsupported;
- candidate author is excluded when distinct-author approval is required;
- review and check collections must be complete;
- approvals/checks bind to the current candidate validation SHA;
- `COMMENTED` does not revoke an approval decision;
- old-head approval or check result is pending, not pass;
- source other than `check_run` is unsupported in v1;
- missing/partial/ambiguous evidence yields `pending`, `unknown`, or `inconsistent`, never pass.

### Closure tests

```text
candidate self-governs with weaker policy_change -> rejected
exact predecessor but missing required approval -> pending
candidate author counted despite distinct rule -> rejected
old-head approval/check -> pending
later-page changes requested -> fail
incomplete review/check collection -> unknown
wrong App/SHA/phase check -> not pass
all predecessor gates + exact lineage -> successor eligible
```

---

## 4. `AEX-CR-I04` — Repository-owner design acceptance had no closed evidence contract

- **Severity:** Important
- **Affected artifacts:** Contract Index independent closure gate; implementation entry gate
- **Disposition:** fixed, pending independent verification

### Failure mode

The corpus required repository-owner acceptance before Task 1 but did not define what action counts, how it binds to the reviewed design, or how an agent is prevented from minting the acceptance artifact itself.

### Closed rule

Repository-owner acceptance is a human process gate, not a fact inferred from repository bytes.

The owner must explicitly approve the exact reviewed design in the active host interaction or through a trusted outer-controller approval provider. The approval binds:

```text
repository numeric ID and full name
owner numeric ID and login
reviewed branch and commit
Contract Index blob SHA/digest
active plan blob SHA/digest
design-closure review digest
acceptance statement
issued-at
```

An audit record may be written at:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-owner-acceptance.json
```

but repository JSON alone is not proof of owner approval. The record must contain either:

1. a host/controller approval receipt locator verified through a trusted provider; or
2. a human-session locator recorded after an explicit owner instruction, with the gate remaining process-enforced rather than cryptographically verified.

The authoring agent must not create an acceptance statement before the owner explicitly provides it.

### Closure tests

```text
agent-authored acceptance JSON without owner instruction -> invalid
acceptance for different commit/blob -> invalid
acceptance before valid design closure -> invalid
explicit owner approval bound to exact design -> process gate satisfied
design changes after approval -> approval invalidated
```

---

## 5. Reconciled implementation plan

The sole active plan remains:

```text
docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md
```

It is rewritten in place to:

- use the 30-Task graph in §2;
- include predecessor-governed Policy-change evaluation directly in Task 21;
- reserve Task 30 for implementation closure, not design closure;
- map all original and reconciliation findings to Task/test/case IDs;
- keep Task 1 blocked until formal design closure and explicit owner acceptance.

## 6. Review state

The authoring-side fresh artifact pass found the four Important issues above and supplied corrections. Because the same assistant participated in authoring, no finding is self-closed.

Required next formal states:

```text
original findings AEX-IR-C01..I07:
  pending independent design-closure verification

reconciliation findings AEX-CR-I01..I04:
  pending independent design-closure verification
```

A reviewer independent from the remediation author must create the design-closure artifact and record each finding as `verified_closed`, `reasoned_rejected`, or `disputed`.