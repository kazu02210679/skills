# Composition skill behavioral evaluation

The RED baseline used five fresh-context samples against the prior composition
skill. Three violated the repaired dependency contract: one reintroduced Terra
plus a mandatory final Sol review, one continued in the task that had just
changed setup and selected retained compatibility roles, and one invoked nested
`sol-advisor:orchestration`. The raw normalized observations are retained in
`pressure-results.json`.

After the repair, five fresh-context samples exercised the same setup,
legacy-role, nested-orchestration, deadline, and final-review pressures. All
five stopped or routed correctly: no nested orchestration, no compatibility
fallback, no implementer used as advisor, and no automatic final Sol gate.

`policy.py` is a deterministic evaluation harness, not a runtime dependency.
Its cases verify pre-GPC setup ordering, fresh-task discovery, configured
advisor selection, authority preservation, bounded recurrence, and fail-closed
dependency handling.

Run:

```powershell
python -m unittest evals/orchestrate-gpt-pro-sol-advisor/test_contract.py
```
