# Verification economy

The goal is the smallest verification set that proves the frozen acceptance
criteria and the changed behavior. Maximize evidence, not test-file count or
coverage by itself.

## Test additions

- Every new test maps to an acceptance criterion, a material risk, or a bug
  root cause. Record the anchor in the task packet or local evidence.
- `new_test_files = 0` is the default. Add a new test file only when an
  existing file cannot express the contract; record that reason.
- A bug fix gets one regression test per root cause by default. Use a
  table-driven case when several inputs prove the same behavior.
- Test observable behavior and public contracts, not private call counts,
  helper names, or other implementation details.
- Do not add speculative edge, snapshot, integration, or full-suite tests
  unless they prove a material criterion or risk that focused tests cannot.

## Verification ladder

Use the lowest level that can falsify the implementation:

```text
L0  diff and static inspection
L1  affected focused test                 (default)
L2  affected package/module tests         (shared module/API/dependency change)
L3  full repository suite                 (dependency/build/schema/shared-core/release-critical change)
```

Run the worker's focused command once in the primary task when relevant code,
test, or configuration changed. Do not rerun an unchanged successful command.
Worker output is not proof by itself, so the primary must independently inspect
the diff and capture the appropriate local evidence once.

## Compact output

On success, return only:

```text
command, exit code, test count, duration, one-line summary
```

On failure, return:

```text
command, exit code, failed test names, relevant error excerpt,
full log path and digest
```

Do not copy a successful full test log into the next model context. Preserve
the full log on disk when needed for audit or debugging.
