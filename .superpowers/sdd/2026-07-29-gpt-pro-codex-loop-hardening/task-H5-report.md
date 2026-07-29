# Task H5 Report: Live Pro Correction Loop

## Outcome

Completed the signed-in Codex Desktop Browser smoke test in one persistent
ChatGPT Pro conversation:

`https://chatgpt.com/c/6a69c31c-4460-83ee-92dc-915865d1645b`

The smoke repository contained `normalize_name(value: str)`, initially
implemented as only `value.strip()`, plus one trimming test. The frozen
requirements added an observable second criterion: whitespace-only input must
raise `ValueError`.

## Prompt-contract defect found and fixed

The first live conversation before this successful run demonstrated that the
transport validator failed closed, but also exposed underspecified nested
prompt shapes: Pro returned arrays where scalar evidence was required and used
an unsupported severity label. The Skill now states the exact closed nested
shapes for requirements, acceptance criteria, risk items, acceptance results,
and the exact finding severity enum.

The regression test
`test_prompt_contract_spells_out_closed_nested_shapes_and_enums` prevents those
constraints from disappearing.

## Successful loop evidence

1. A fresh Pro conversation returned a requirements envelope with the expected
   header, exact closed payload, stable acceptance IDs, and `PLAN_READY`.
2. The real transport and requirements validators accepted it.
3. Codex deliberately submitted AC-2 as unverified with one passing AC-1 test.
4. Pro returned a valid `CHANGES_REQUESTED` review:
   - `F-1`: `CODE_CHANGE` for the missing empty-trimmed-value check.
   - `F-2`: `TEST_CHANGE` for missing whitespace-only regression coverage.
5. Codex implemented only those bounded changes and ran the local suite:
   2/2 tests passed.
6. A canonical snapshot captured only `normalizer.py` and
   `test_normalizer.py`, with snapshot digest
   `sha256:814ae378d32ef79d4382d2ddd89d40f8e18f7f5d7e900d83493aee5970871b56`.
7. The second valid review in the same conversation returned `PASS` for AC-1
   and AC-2 with no findings or scope violations.
8. Final tests passed again, recapture produced the exact reviewed snapshot,
   `.ai-pro-loop/` was neither tracked nor staged, and the explicit
   `final-gate` validator accepted all bound evidence.

## Validator evidence

- Requirements transport envelope: PASS.
- Requirements payload: PASS.
- Initial implementation report: PASS.
- `CHANGES_REQUESTED` transport envelope and payload: PASS.
- Corrected implementation report: PASS.
- `PASS` transport envelope and payload: PASS.
- Final gate bound to requirements, review packet, and unchanged snapshot:
  PASS.

Sensitive run artifacts remain untracked under the temporary smoke repository's
`.ai-pro-loop/` directory and are not part of the Skill commit.
