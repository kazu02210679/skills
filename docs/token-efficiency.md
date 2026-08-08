# Token efficiency controls

The repository now measures only the Skill material explicitly expected to be
prompt-fed. `context-budget-manifest.json` keeps recovery-only references out of
the default budget and makes auxiliary inclusion reviewable.

Using the same reporter and manifest on baseline revision `48be21a`, the
repository measured 93,335 normalized UTF-8 bytes (about 23,334 tokens). The
reviewed implementation measures 94,790 bytes (about 23,698 tokens), an
increase of 1,455 bytes (about 364 tokens) caused by the new safety controls.
The affected comparisons are recorded in `context-budget-comparison.json`:
`gpt-pro-codex-loop` is 16,961 -> 17,511 bytes and
`review-implementation-html` is 11,746 -> 12,651 bytes.

This change therefore does not claim a reduction in the canonical instruction
files themselves. Savings are structural: selective installation avoids
unrequested Skill copies; ordinary review avoids a second isolated context;
and GPT-loop evidence cannot grow past explicit model-bound limits. Provider
token or credit savings were not directly measured locally.

Run the non-mutating report and tracked regression check with:

```text
python scripts/context_budget_report.py --repo . \
  --manifest context-budget-manifest.json \
  --baseline context-budget-baseline.json \
  --max-growth-bytes 1455
```

This estimate is deterministic `ceil(normalized_utf8_bytes / 4)`, not a model
tokenizer bill. Actual usage still depends on which Skill is triggered and
which references the task requires.

Codex auto review remains enabled. Its cost is reduced indirectly by keeping
writable roots narrow and requesting precise, reusable command approvals. The
repository does not weaken or bypass approval policy.

## Verification summary

- Prepared semantic-review prompt: 48,180 UTF-8 bytes.
- Complete frozen requirements: 35,847 UTF-8 bytes.
- Dynamic implementation summary: 9,521 UTF-8 bytes across 59 bounded items.
- Installer and context tests: 14 passed on the available PowerShell and Bash
  hosts.
- GPT-loop evaluations: 219 passed, with two pre-existing skips.
- Review HTML evaluations: 14 passed before the added lifecycle traces; the
  focused lifecycle suite then passed all six selector/orchestration cases.
- Canonical validation: all 11 Skills passed; the generated catalog was current.
- README adjacency: 11 canonical Skill directories inspected, zero missing
  adjacent README files.

The review lifecycle traces record one session for ordinary review, zero
isolated session creations, a blind pass with no plan, blind completion before
plan injection, and plan-aware reuse of that session. The isolated trace records
two distinct sessions while preserving the same plan-visibility ordering.

## Test-first evidence

Representative tests were added before their implementations and observed red:

- installer list/select cases rejected unknown `--list`, `--skill`, `-List`,
  and `-Skill` arguments;
- the context reporter and review selector tests failed because their scripts
  did not exist;
- GPT boundary tests failed with missing `validate_model_bound_*` functions.

After implementation, those same focused cases passed. The later Pro-requested
review lifecycle tests were also added before the lifecycle function and then
passed against its implementation. These are local red/green observations, not
provider-side execution or billing measurements.
