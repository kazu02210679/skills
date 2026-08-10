# Verification economy

Choose the smallest evidence set that can falsify the frozen acceptance
criteria and changed behavior. Token cost is part of the verification design.

## Test additions

- Default to `new_test_files = 0`.
- Each witness has exactly one `primary_anchor` naming an Acceptance Criterion,
  material risk, or bug root cause. Optional `also_proves` anchors may record
  other behavior covered by that same observable witness.
- A bug fix gets one regression witness per root cause by default. Use a
  table-driven witness set for equivalent inputs; do not add speculative edge,
  snapshot, integration, or full-suite tests without a material anchor.
- Record `case_count` per primary anchor. More than five cases on one anchor
  requires `materially_distinct: true` plus a non-empty justification. A repeated
  primary anchor without that justification is rejected.
- Test observable behavior/public contracts, not private call counts or helper
  names.

Example bounded delta:

```text
test_delta=files:0,cases:2,primary_anchors:AC-3,also_proves:BUG-auth-expiry
```

## Verification ladder and trusted fingerprint

Use the lowest level that can falsify the change:

```text
L0  diff and static inspection
L1  affected focused test                 (default)
L2  affected package/module tests         (shared/API/dependency change)
L3  full repository suite                 (schema/shared-core/release-critical)
```

Generate the verification-input fingerprint with
`scripts/verification_fingerprint.py`. The helper reads selected files and
lock/config files from the current repository; the adapter supplies the trusted
VCS tree identity and material environment identity. The input is:

```text
verification_input = command
  + base/tree commit
  + relevant-file digest
  + lock/config digest
  + material environment identity
```

The same command with a new tree, dependency, generated artifact, config,
environment, or merged worktree is a new verification. The skip policy accepts
only the helper's trusted fingerprint, never a caller-typed `current_fingerprint`
or a copied previous value.

## Closed local evidence

`--local-evidence` is a closed schema. Each `test_commands` item has exactly
`command`, `outcome`, and `output_summary`; unknown siblings are rejected.
Encode bounded metrics, `test_delta`, and the fingerprint inside
`output_summary`:

```text
exit=0; tests=12; duration=2.4s; summary=focused auth tests passed;
verify_input=sha256:...; test_delta=files:0,cases:2,primary_anchors:AC-3
```

On failure, retain only the command, exit code, failed names, relevant error
excerpt, and full log path plus digest. Never return a successful full log to
the next model context.
