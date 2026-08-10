# Verification economy

The goal is the smallest evidence set that proves the frozen acceptance
criteria and changed behavior. Maximize falsifiability, not test-file count or
coverage by itself.

## Test additions

- Every added witness names exactly one Acceptance Criterion, material risk, or
  bug root cause. Do not add a second independent witness for the same anchor
  unless it proves materially distinct behavior.
- `new_test_files = 0` is the default. Add a file only with a recorded reason
  an existing file cannot express the contract.
- A bug fix gets one regression witness per root cause by default. Use a
  table-driven witness set for equivalent inputs.
- Test observable behavior/public contracts, not private call counts or helper
  names. Do not add speculative edge, snapshot, integration, or full-suite
  tests without a material criterion or risk.

Record the bounded delta as text, for example:

```text
test_delta=files:0,cases:2,anchors:AC-3|BUG-auth-expiry
```

This is evidence, not a new controller field.

## Verification ladder and fingerprint

Use the lowest level that can falsify the change:

```text
L0  diff and static inspection
L1  affected focused test                 (default)
L2  affected package/module tests         (shared/API/dependency change)
L3  full repository suite                 (dependency/build/schema/shared-core/release-critical)
```

The primary runs the worker's focused command once when relevant inputs changed.
Skip a previous successful result only when this complete fingerprint is
unchanged:

```text
verification_input = command
  + base/tree commit
  + relevant-file digest
  + lock/config digest
  + material environment identity
```

The same command with a new base commit, changed dependency/lockfile,
generated artifact, configuration, environment, or merged worktree is a new
verification and must run again.

## Closed local evidence and compact output

The controller's `--local-evidence` object is closed. Each `test_commands` item
has exactly `command`, `outcome`, and `output_summary`; unknown siblings are
rejected. Encode bounded metrics, the `test_delta`, and the fingerprint inside
`output_summary`:

```text
exit=0; tests=12; duration=2.4s; summary=focused auth tests passed;
verify_input=sha256:...; test_delta=files:0,cases:2,anchors:AC-3|BUG-auth-expiry
```

On failure, retain only command, exit code, failed names, a relevant error
excerpt, and the full log path plus digest. Never return a successful full log
to the next model context.
