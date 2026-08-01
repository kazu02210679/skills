# Final fix round 3

## Scope delivered

- Made same-phase requirements expected-header anchor changes fail closed unless a closed controller-built preparation context authorizes them.
- Bound first preparation to a `null` abandoned receipt and replacement preparation to the complete, validated `ABANDONED_NOT_SENT` receipt whose expected-header digest matches the previous anchor.
- Kept the legitimate prepare, abandon, and fresh-prepare flow working with a new anchor and nonce.
- Made `abandon-attempt` load canonical state through the common mutator helper, verify the outstanding attempt against the trusted phase anchor, and recheck the loaded state digest immediately before replacing the expected-attempt receipt.
- Documented the preparation-context contract and CLI input.

## RED evidence

- Standalone transition validation accepted both a requirements anchor replacement and anchor clearing without explicit authorization.
- Injecting an external state mutation after abandonment staging did not raise and allowed the expected attempt to be replaced.

## Verification

- Focused packet authorization tests: 2 passed.
- Focused controller abandon/reprepare and state-race tests: 2 passed.
- Packet validator: 98 tests passed in 0.047s.
- Controller: 70 tests passed in 112.832s.
- Snapshot: 34 tests passed in 44.486s (2 platform-specific skips).
- `py_compile` and `git diff --check` passed.

## Assumptions and unresolved concerns

- Preparation context is trusted only because the controller constructs it from local expected-header and abandoned-attempt artifacts; it is never Pro output.
- No unresolved concerns remain within this fix-round scope.
