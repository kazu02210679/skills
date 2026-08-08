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

`policy.py` is a deterministic evaluation harness, not a runtime dependency.
Its cases verify pre-GPC setup ordering, the single active preferences object,
canonical workspace/profile binding, the exact Codex advisor, trusted runtime
identity/isolation attestation, opaque permission audit evidence, authority,
bounded recurrence, and fail-closed dependency handling.

Run:

```powershell
python -m unittest evals/orchestrate-gpt-pro-sol-advisor/test_contract.py
```
