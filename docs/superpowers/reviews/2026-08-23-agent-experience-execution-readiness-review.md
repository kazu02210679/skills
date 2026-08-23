# Agent Experience v1 — Execution Readiness Review

- **Document date:** 2026-08-23
- **Target repository:** `kazu02210679/skills`
- **Target PR:** #35
- **Reviewed PR head:** `a073d2a001d62316c6de471a1ceef4e79ca55e65`
- **Review input:** user-provided external current-state review plus current GitHub artifacts
- **Result:** `CHANGES_REQUIRED`, with corrections defined by the companion Execution Readiness Clarification
- **Closure authority:** this review is not formal design closure and does not self-close earlier Critical/Important findings

## 1. Scope

This pass does not reopen the already-remediated trust-boundary design. It checks whether an implementer can answer, without guessing:

1. whether Task 1 may start;
2. which of the 30 Tasks are actually implemented;
3. what the trusted approval-provider boundary means in v1;
4. how Policy successor changes are executed;
5. who owns `use_context_id` and when it expires;
6. when Hook/installer implementation is allowed to begin;
7. what invalidates design closure versus implementation closure;
8. what users and automation receive on failure;
9. how pre-acceptance local implementation work is handled.

## 2. Repository evidence

At the reviewed GitHub head:

- PR #35 is a Draft documentation PR.
- The active plan declares 30 Tasks.
- The Contract Index states Task 1 is blocked pending formal design closure and repository-owner acceptance.
- `docs/superpowers/reviews/2026-08-23-agent-experience-design-closure.md` is not present on the PR branch.
- PR #35 does not contain `skills/agent-experience/` runtime implementation files.
- The active plan already places Hooks at Tasks 24-26 and bootstrap approval at Task 20.
- The binding remediation already states that v1 ships no standalone trusted approval issuer.

Therefore, local staged/unstaged code mentioned by the external review cannot be treated as GitHub-verifiable implementation progress.

## 3. Finding disposition

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| `AEX-ER-I01` | Important | Task 1 GO/NO-GO is not presented as one computed state | fix: one entry-gate state machine and explicit current status |
| `AEX-ER-I02` | Important | 30 Tasks have no authoritative progress/evidence ledger | fix: machine-readable task-progress ledger with evidence rules |
| `AEX-ER-I03` | Important | trusted approval provider looks like an unspecified mandatory component | fix: v1 has no built-in issuer; SPI/manual-governance fallback is normative and not a Task-1 blocker |
| `AEX-ER-I04` | Important | Policy successor command/evaluation/resubmission path is under-specified | fix: freeze CLI surface, predecessor resolution, provider usage, result states, and resubmission rules |
| `AEX-ER-I05` | Important | `use_context_id` owner/lifetime/reuse is unclear | fix: controller-created operation-scoped context; caller cannot reuse it across commands/tasks |
| `AEX-ER-I06` | Important | missing Hook/installer files could be mistaken for incomplete earlier Tasks | fix: explicit Task 24/25/26 start gates and host-contract probe |
| `AEX-ER-I07` | Important | design/implementation closure invalidation rules are incomplete | fix: exact clean committed targets; binding-design change forces re-closure |
| `AEX-ER-I08` | Important | fail-open/fail-closed policy lacks one user/machine error contract | fix: stable JSON envelope, exit-code classes, human next-action mapping |
| `AEX-ER-I09` | Important | local staged/unstaged implementation may be mistaken for accepted implementation | fix: classify as `prototype_unverified`; require adoption review into a post-gate implementation branch |

## 4. Deliberate non-change: no built-in approval issuer

The review asks whether the trusted approval provider is Codex, a GitHub App, or another CLI. The safe v1 answer is **none of those by default**.

The existing remediation correctly states:

- the Skill may verify an opaque approval through a trusted outer-controller adapter;
- the target repository cannot configure or mint trusted issuers;
- v1 does not ship a standalone issuer;
- without such an adapter, bootstrap candidate generation still works but activation returns `bootstrap_manual_governance_required`.

Inventing a GitHub review/comment or owner JSON as a built-in human-presence proof would weaken the trust boundary because an agent using the same account credential could potentially mint the same repository object. The Execution Readiness Clarification therefore makes the existing boundary explicit instead of adding a fake trust root.

## 5. Current authoritative status

For the GitHub branch reviewed here:

```text
Design candidate:        REVIEW / not formally closed
Formal design closure:   MISSING on branch
Owner acceptance:        NOT SATISFIED by repository bytes alone
Task 1:                  BLOCKED
Runtime implementation:  NOT PRESENT on GitHub PR #35
Implementation branch:   NOT ESTABLISHED on GitHub
Hooks / installer:       CORRECTLY NOT STARTED on GitHub
```

If a local working copy contains implementation code, it is not discarded automatically. It is classified as `prototype_unverified` until it is mapped to Tasks and replayed through the accepted implementation gate.

## 6. Required correction set

The companion binding clarification must freeze:

- entry-gate computation;
- task status/evidence schema;
- v1 no-built-in-issuer boundary;
- Policy CLI/state machine;
- operation-scoped `use_context_id`;
- Hook host-contract probe and Task gates;
- closure invalidation rules;
- error envelope and exit mapping;
- prototype adoption workflow.

Issue #34 and PR #35 must then reflect those rules. Any previous formal closure or owner acceptance bound to `a073d2a...` would be invalid after these binding documents change and must target the new final design head.

## 7. Closure state

This review records and remediates execution-readiness ambiguity. It does **not** constitute the independent design-closure artifact required by the Contract Index. After the corrections are committed, a formal reviewer that satisfies the independence rule must review the new exact head and create the designated design-closure artifact. Repository-owner acceptance follows that closure and must bind the same design state.
