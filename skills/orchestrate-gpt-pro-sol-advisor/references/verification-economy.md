# Verification economy

Choose the smallest evidence set that can falsify the frozen acceptance
criteria and changed behavior. Token cost is part of the verification design.

## Test additions

- Default to `new_test_files = 0`.
- Each witness has exactly one `primary_anchor` naming an existing Acceptance
  Criterion, material-risk ID, or bug-root-cause key. Optional `also_proves`
  anchors must also exist in those trusted catalogs; invented IDs are rejected.
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
`python scripts/verification_fingerprint.py --repo . --command "<command>"`.
The helper reads the current Git tree identity, changed files, command targets,
lock/config files, file contents, and material host identity itself. Optional
`--target-file` values only add hints; they cannot hide changed inputs. The
input is:

```text
verification_input = command
  + base/tree commit
  + relevant-file digest
  + lock/config digest
  + material environment identity
```

Changed-file discovery uses NUL-delimited `git status --porcelain=v1 -z`
records. This preserves spaces, non-ASCII names, and rename pairs without
relying on Git's human-readable quoting. The environment identity also records
the command executable, its resolved path, and an allowlisted toolchain version
for common Python, npm, pnpm, Cargo, Go, and .NET commands.

Gitlink inputs are handled separately from regular files. Every tracked Gitlink
is included even when status is clean; a clean submodule records both the
superproject gitlink object and the submodule `HEAD` after independent-worktree
validation. A missing, deinitialized, uninitialized, or dirty submodule makes
the fingerprint unavailable and forces the verification to run.

The same command with a new tree, dependency, generated artifact, config,
environment, or merged worktree is a new verification. The skip policy invokes
the helper internally for the current repository; it accepts no external
fingerprint argument and never trusts a caller-typed or copied digest.

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
