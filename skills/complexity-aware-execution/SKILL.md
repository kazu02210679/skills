---
name: complexity-aware-execution
description: 'Use for code edits, bug fixes, tests, repository exploration, and local configuration or build changes when the agent should right-size its effort. Apply Estimate / Execute / Expand: estimate task complexity and the minimum evidence needed, take the smallest reliable path, verify early, and expand investigation only when verification fails or evidence contradicts the hypothesis. Do not minimize exploration for security, authentication, permissions, secrets, destructive operations, production changes, broad refactors, or explicitly exhaustive audits.'
---

# Complexity-Aware Execution

Use the E3 loop to match investigation and tool usage to the task's actual difficulty.

## Estimate

Before acting, identify the likely change surface, minimum files and dependencies to inspect, cheapest meaningful verification, next expansion layer, and safety or external-impact risks. Treat an obviously local task as local; do not begin with repository-wide reading unless the task or uncertainty justifies it.

## Execute

Read the user's target, the reported error, and directly related tests first. Read one layer of callers, callees, types, or configuration only when needed. Make the smallest coherent change and run the cheapest verification that can falsify the current hypothesis immediately.

Track which files were read, which checks ran, and which assumptions remain unverified.

## Expand

Expand only after a check fails or observed behavior contradicts the hypothesis. Use this order: nearby files; direct callers/callees, types, and configuration; related tests/build/dependencies; the subsystem; repository-wide search. At each layer, stop if the new evidence does not change the decision.

## Verification and stopping

Scale checks to risk: targeted tests/type checks/lint/diff review for local changes; related tests and build for multi-file changes; focused security, permission, data-integrity, and regression checks for high-risk changes. Stop when the request is satisfied and appropriate checks pass, or when further investigation produces no decision-changing evidence. Report skipped checks and residual risk.

## Exceptions

Do not force minimal exploration for security, authentication, permissions, secrets, destructive operations, production changes, broad refactors, or an explicitly exhaustive review. Confirm scope and impact before destructive actions. Correctness, safety, and the user's request outrank token or file-count reduction.
