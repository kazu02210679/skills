# Final fix round 2

## Scope delivered

- Made `pending_requirements_expected_header_digest` a required standalone-validator state field and limited same-phase preparation to changing only that anchor.
- Captured the canonical state-file digest immediately after every mutator state load and made it a required commit-helper argument.
- Kept foreign-modified destinations and interrupted transactions visible instead of overwriting them during rollback.
- Made orphan-transaction status recovery-only with exact paths, bounded guidance, and no advertised normal mutation.
- Documented the manual recovery boundary in the Skill and packet contract.
- Emitted only report phase edges actually traversed and made post-state diagnostic events best-effort.

## RED evidence

- Missing requirements anchor was accepted by the standalone validator.
- A same-phase anchor update could mutate `active_report_digest` without error.
- A state mutation immediately before commit-helper entry was accepted.
- Recovery status advertised `prepare-requirements` despite an orphan transaction.
- Rollback overwrote a foreign-modified artifact.
- Event persistence failure escaped after a successful state commit.
- `IMPLEMENTING` and `LOCAL_VERIFICATION` report starts emitted false phase edges.

## Verification

- Controller: 69 tests passed in 109.395s.
- Packet validator: 96 tests passed.
- Snapshot: 34 tests passed in 44.150s (2 skipped).
- `py_compile` and `git diff --check` passed.

## Assumptions and unresolved concerns

- State digest checks cover mutations observable immediately after load, before artifact publication, and immediately before state replacement. They do not claim impossible protection against an arbitrary non-cooperating write within the final `os.replace` instruction window. All controller mutations use the run lock, and manual artifact editing is forbidden.
- Transaction resolution remains manual and outside normal controller commands; no destructive cleanup or silent repair was added.
