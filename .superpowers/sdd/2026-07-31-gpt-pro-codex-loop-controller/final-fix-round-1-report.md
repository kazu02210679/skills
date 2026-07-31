# Final fix round 1

## Scope delivered

- Bound requirements expected-header digests in trusted state and rejected coordinated valid-shaped header/response tampering.
- Rejected normal mutations with `RECOVERY_REQUIRED` when an interrupted transaction exists.
- Rechecked trusted state before publication and before replacement; races preserve the external state and roll back this command's artifacts.
- Published diagnostic events only after state commit. Added requirements acceptance, material approval, report phase-edge, review, final, and initialization events.

## RED evidence

`test_requirements_expected_header_is_bound_in_trusted_state` initially failed with `KeyError: 'pending_requirements_expected_header_digest'`.

## Verification

- Controller: 66 tests passed in 99.343s.
- Packet validator: 93 tests passed.
- Snapshot: 34 tests passed (2 skipped).
- `py_compile` and `git diff --check` passed.

## Assumptions and unresolved concerns

- The state anchor is optional in the standalone packet validator solely to retain its independent legacy-fixture contract; controller-created state always includes and enforces it.
- The known broad Windows suite was not rerun indefinitely.
