# Composition skill behavioral evaluation

The second RED baseline used five fresh-context samples against the previous
composition skill. Four safely rejected wrong profiles, contrary runtime
metadata, or retained roles. One accepted useful advice when runtime role,
model, effort, sandbox, and permission-profile evidence was unobservable. The
normalized observations are retained in `pressure-results.json`.

The final five fresh-context samples exercised a valid control, an arbitrary
opaque permission-profile observation, advisor invocation failure, advice-body
attestation claims with no runtime evidence, and equivalent canonical workspace
spellings. All five routed correctly. Invalid advice was discarded before
downstream use; valid low-risk work skipped Sol without making it a gate.

A provenance-hardening RED/GREEN set then exposed the remaining Boolean-trust
gap. The repaired harness requires public native details to identify the role,
binds every public-details result to the spawned thread, and uses the
canonically skill-relative installed inspector only to fill omitted fields for
that thread. Inspector success is derived from exit zero plus exact 10-field
JSON rather than caller status/count. The inspector origin must equal the one
orchestration Skill selected by the trusted catalog; stale cached versions,
caller-supplied roots, and symlink escapes cannot substitute for it. That
selection enters through a separate trusted host input, never scenario data.
It rejects conflicting overlap and records per-field
`public-native-details` or `local-runtime-inspector` provenance. Matching
self-claims cannot be promoted by a caller-supplied trust flag.

`policy.py` is a deterministic evaluation harness, not a runtime dependency.
Its cases verify pre-GPC setup ordering, the single active preferences object,
canonical workspace identity plus exact upstream raw-workspace `profileKey`
serialization, the exact Codex advisor, trusted runtime identity/isolation
attestation provenance, exact-thread host completion, inspector success, opaque permission
audit evidence, authority, bounded recurrence, and fail-closed dependency
handling.

The routing cases also verify Luna / Max as the default implementation worker,
one same-task correction (two total attempts) before Terra / High escalation for difficult or stuck work, fail-closed
Luna/Terra capability preflight, Sol read-only escalation only after trusted
Terra execution evidence reports one blocked high-impact decision, and the
explicit Test Economy defaults. Worker routing evidence is supplied through
separate trusted inputs, so scenario self-claims cannot establish availability.
Cases bind real project/thread/host identities, allow absent Luna post-creation
model metadata, reject mismatches when it is returned, and require exact
shipped Terra role-template digests. Deterministic adversarial replays cover
missing roles, wrong models, setup-only `clientThreadId`, route/outcome mixing,
command-text-only verification skips, unbounded test growth, and invented test
anchors. The `scripts/verification_fingerprint.py` helper automatically reads
Git identity, changed files, command targets, lock/config inputs, and host
identity; the policy computes it internally before a skip decision. The helper
also has a direct CLI for recording evidence. The implementation references keep app-task identity,
execution outcome, and compact verification rules separate from the main router.

The repository records pressure prompts for a future fresh-context model run;
this local suite labels its executable checks honestly as deterministic policy
replays and does not claim that a fresh model pressure run occurred here.

Run:

```powershell
python -m unittest discover -s evals/orchestrate-gpt-pro-sol-advisor -p "test_*.py"
```
