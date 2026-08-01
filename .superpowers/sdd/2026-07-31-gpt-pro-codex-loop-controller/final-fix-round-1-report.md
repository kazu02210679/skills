# Final fix round 1

## Scope delivered

- Bound requirements expected-header digests in trusted state and rejected coordinated valid-shaped header/response tampering.
- Rejected normal mutations with `RECOVERY_REQUIRED` when an interrupted transaction exists.
- Rechecked trusted state before publication and before replacement; mutations observed at those checks preserve external state and roll back only transaction-owned artifacts.
- Published diagnostic events only after state commit. Added requirements acceptance, material approval, report phase-edge, review, final, and initialization events.

## RED evidence

`test_requirements_expected_header_is_bound_in_trusted_state` initially failed with `KeyError: 'pending_requirements_expected_header_digest'`.

## Verification

- Controller: 66 tests passed in 99.343s.
- Packet validator: 93 tests passed.
- Snapshot: 34 tests passed (2 skipped).
- `py_compile` and `git diff --check` passed.

## Assumptions and unresolved concerns

- Round 2 made the requirements expected-header anchor required in the standalone validator and updated its fixtures.
- These checks do not claim protection from an arbitrary non-cooperating write inside the final atomic-replace instruction window. Controller mutations share the run lock, and manual artifact editing is forbidden.
- The known broad Windows suite was not rerun indefinitely.
