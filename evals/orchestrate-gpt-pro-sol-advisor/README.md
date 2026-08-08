# Composition skill behavioral evaluation

The RED baseline used five fresh-context authority-boundary samples before the
composition skill existed. Four of five made Sol review recur after every
correction or Pro-requested change, effectively turning advice into a mandatory
pre-Pro gate. The focused cases and contract test preserve that failure as the
regression target.

After the skill was implemented, five fresh-context samples ran the same
high-risk authority-boundary scenario while reading the new `SKILL.md`. All
five suppressed automatic Sol recurrence and allowed another consultation
only for materially new evidence or a materially changed question. This is a
baseline improvement from 1/5 to 5/5 correct recurrence decisions.
The normalized observations are retained in `pressure-results.json`.

`policy.py` is a deterministic evaluation harness, not a runtime dependency of
the Skill. Each case supplies a scenario to the harness and asserts the
observed mode, lane, call count, preserved authority, and terminal state.

Run:

```powershell
python -m unittest evals.orchestrate-gpt-pro-sol-advisor.test_contract
```
