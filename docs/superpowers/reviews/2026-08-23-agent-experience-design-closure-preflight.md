# Agent Experience v1 — Design Closure Preflight Review

- **Review date:** 2026-08-23
- **Branch:** `docs/agent-experience-design`
- **Initial reviewed remediation head:** `c3ac1c0435e04ffb6e42d664be4243341c0ab2e0`
- **Reconciled head:** `9c51fe8d814ad5c97632e9d846c70da23ed0ef25`
- **Mode:** fresh artifact-only authoring-side preflight
- **Formal reviewer independence:** **not satisfied**
- **Formal design closure:** **not claimed**
- **Task 1 decision:** **NO-GO pending independent design closure and owner acceptance**

## 1. Review scope

The pass read only repository artifacts required by the Contract Index:

- original independent review;
- independent-review remediation contract;
- Trust Roots and Open Questions clarifications;
- Remote-State amendment;
- Contract Index;
- active consolidated implementation plan;
- machine-readable remediation matrix.

The pass did not use the authoring conversation as evidence for the correctness of a contract.

The same assistant participated in previous remediation. Therefore this review can detect and repair defects, but under the repository's own closure rule it cannot label its own findings `verified_closed`.

## 2. Original independent-review findings

The artifact pass found a concrete remediation and direct active-plan coverage for each original finding.

| Finding | Artifact preflight result | Key corrected boundary |
|---|---|---|
| `AEX-IR-C01` | correction present | tracked config cannot select executable; local canonical `gh` identity and drift checks |
| `AEX-IR-C02` | correction present | TTY/repository bytes cannot activate bootstrap; trusted outer approval provider required |
| `AEX-IR-C03` | correction present | immutable Policy lineage, exact predecessor, rollback/fork/reset detection |
| `AEX-IR-I01` | correction present | one rewritten active plan plus machine-readable requirement coverage |
| `AEX-IR-I02` | correction present | `authoritative_ref_current` cannot reuse historical PR/reviewer predicates |
| `AEX-IR-I03` | correction present | complete pagination mandatory; partial collection is `unknown` |
| `AEX-IR-I04` | correction present | local-only, exact-context, operation-specific, single-use preflight receipt |
| `AEX-IR-I05` | correction present | v1 is explicitly check-run-only and claims no branch-protection parity |
| `AEX-IR-I06` | correction present | last-push approval unsupported; no author/committer approximation |
| `AEX-IR-I07` | correction present | typed GitHub operations, segment/query encoding, request/response rebinding |

This table is not formal closure. Each row remains `pending_independent_verification` in the remediation matrix.

## 3. Additional findings discovered by this pass

### `AEX-CR-I01` — Closure-stage artifact conflation

- **Severity:** Important
- **Observed at:** active plan Task 28 / Contract Index closure gate at initial head
- **Counterexample:** one generic closure file could be used both before Task 1 and after implementation.
- **Correction:** separate design closure, authoring preflight, and implementation closure paths.
- **Status:** authoring-fixed; pending independent verification.

### `AEX-CR-I02` — Release ranges did not match Task meaning

- **Severity:** Important
- **Observed at:** initial Contract Index phase table
- **Counterexample:** remote continuation could be labelled Automatic Lifecycle before Remote Governance completed.
- **Correction:** reconcile to 30 Tasks with Remote Governance 20-23 and Automatic Lifecycle 24-26.
- **Status:** authoring-fixed; pending independent verification.

### `AEX-CR-I03` — Predecessor Policy-change gate omitted from active plan

- **Severity:** Important
- **Observed at:** initial active plan Policy Task versus binding Open Questions contract
- **Counterexample:** exact lineage could pass while successor omitted predecessor-required approvals/check runs.
- **Correction:** Task 21 now owns deterministic predecessor-governed Policy-change evaluation with complete review/check evidence and current-SHA binding.
- **Status:** authoring-fixed; pending independent verification.

### `AEX-CR-I04` — Repository-owner design acceptance was not closed

- **Severity:** Important
- **Observed at:** entry gate
- **Counterexample:** an agent could write an audit JSON claiming owner acceptance without an explicit owner instruction.
- **Correction:** owner acceptance is a human process gate bound to the exact closed design; repository JSON alone is not proof.
- **Status:** authoring-fixed; pending independent verification.

## 4. Reconciliation changes inspected

The pass re-read the following corrections after they were written:

```text
docs/superpowers/specs/2026-08-23-agent-experience-closure-reconciliation.md
docs/superpowers/specs/2026-08-22-agent-experience-contract-index.md
docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md
docs/superpowers/reviews/2026-08-22-agent-experience-independent-review-remediation.json
```

The active plan now has 30 Tasks and directly includes:

- original ten finding pressure cases;
- the four reconciliation finding pressure cases;
- trusted provider executable tests;
- external bootstrap approval-provider tests;
- immutable Policy lineage tests;
- predecessor `policy_change` approval/check tests;
- complete pagination tests;
- preflight receipt tests;
- check-run-only and last-push unsupported tests;
- typed encoding tests;
- design/implementation closure separation;
- owner-acceptance process-gate tests.

## 5. Authoring-side recheck result

After the reconciliation edits, this artifact-only pass did not identify another concrete Critical or Important failure mode within the reviewed document scope.

That statement means only:

```text
no additional Critical/Important issue found by this authoring-side pass
```

It does **not** mean:

```text
formal independent closure complete
Task 1 authorized
PR ready
merge ready
```

## 6. Formal closure instructions

A reviewer who did not author the remediation must create:

```text
docs/superpowers/reviews/2026-08-23-agent-experience-design-closure.md
```

The review must bind the exact current commit and blob SHAs for:

- Contract Index;
- Closure Reconciliation;
- Independent Review Remediation;
- active consolidated plan;
- remediation matrix;
- original independent review.

For every finding below, record one closed value:

```text
verified_closed
reasoned_rejected
disputed
```

Finding set:

```text
AEX-IR-C01
AEX-IR-C02
AEX-IR-C03
AEX-IR-I01
AEX-IR-I02
AEX-IR-I03
AEX-IR-I04
AEX-IR-I05
AEX-IR-I06
AEX-IR-I07
AEX-CR-I01
AEX-CR-I02
AEX-CR-I03
AEX-CR-I04
```

Any `disputed`, open, or unreviewed Critical/Important finding keeps Task 1 at `NO-GO`.

## 7. Repository-owner gate

After valid formal design closure, the repository owner must explicitly accept the exact reviewed design. The authoring agent must not infer acceptance from silence, repository ownership, prior approval of another revision, or an agent-authored JSON file.

## 8. Current decision

```text
Original findings: authoring-fixed, formal verification pending
Reconciliation findings: authoring-fixed, formal verification pending
Formal reviewer independence: not satisfied in this pass
Formal design closure: absent
Repository-owner acceptance: absent
Task 1 readiness: NO-GO
PR readiness: NO-GO
Merge readiness: NO-GO
```