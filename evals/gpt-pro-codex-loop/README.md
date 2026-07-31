# GPT Pro Codex Loop evaluations

This directory combines deterministic protocol/snapshot tests with observed, nondeterministic guidance checks. Agent observations are not reproducible proofs; fail-closed safety is enforced by the Python suites.

## Deterministic tests

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
```

The tests cover strict JSON, closed/versioned objects, correlated envelopes and replay, requirements approval/lineage, report/review context, locally derived finding fingerprints, state transitions, final-gate evidence, immutable preflight, canonical product identity, attribution, path/metadata safety, unstable observation, and all snapshot CLI commands.

## Fresh-context behavior method

For each case in `cases.json`, start a separate fresh agent context. Give it only the scenario plus `SKILL.md` and references that `SKILL.md` directs it to read. Do not expose `cases.json`, this README, prior observations, or expected answers. Compare the returned normalized JSON to the case's `expect` subset.

These checks assess whether concise Skill guidance leads an agent toward the intended decision. Model sampling can vary; record the date and raw result and investigate mismatches rather than calling the result deterministic.

## 2026-07-29 observed GREEN run

The required six independent fresh contexts matched all expected fields. Two additional fresh non-trigger checks also matched after the trigger was narrowed:

| Case | Observed decision | Result |
|---|---|---|
| `requirements-owner` | `APPLY_GPT_PRO_CODEX_LOOP` | Pro requirements, Codex local implementation, same conversation: matched |
| `false-pass` | `do_not_complete` | local gate overrides Pro PASS: matched |
| `evidence-only` | `CHANGES_REQUESTED` / `PROVIDE_EVIDENCE` | no product change: matched |
| `requirements-revision` | `NEED_USER_INPUT` | approval, invalidation, reset: matched |
| `conversation-mismatch` | `hard_stop` / `conversation_identity_mismatch` | matched |
| `ordinary-implementation-non-trigger` | `do_not_invoke` | matched |
| `requirements-only-non-trigger` | `do_not_invoke` | matched |
| `standalone-review-non-trigger` | `do_not_invoke` | matched |

Raw normalized observations:

```json
{"case_id":"requirements-owner","pro_owns_requirements":true,"codex_owns_local_implementation":true,"same_conversation_required":true,"decision":"APPLY_GPT_PRO_CODEX_LOOP"}
{"case_id":"false-pass","complete":false,"local_gate_overrides_pass":true,"decision":"do_not_complete"}
{"case_id":"evidence-only","product_code_changed":false,"action":"PROVIDE_EVIDENCE","decision":"CHANGES_REQUESTED"}
{"case_id":"requirements-revision","user_approval_required":true,"review_round_reset":true,"prior_evidence_invalidated":true,"decision":"NEED_USER_INPUT"}
{"case_id":"conversation-mismatch","advance":false,"reason":"conversation_identity_mismatch","decision":"hard_stop"}
{"case_id":"ordinary-implementation-non-trigger","invoke_gpt_pro_loop":false,"decision":"do_not_invoke"}
{"case_id":"requirements-only-non-trigger","invoke_gpt_pro_loop":false,"decision":"do_not_invoke"}
{"case_id":"standalone-review-non-trigger","invoke_gpt_pro_loop":false,"decision":"do_not_invoke"}
```

The first conversation-mismatch observation stopped safely but returned a prose reason rather than the stable token. The concise Skill guidance was refined to name `conversation_identity_mismatch`; a new fresh context then matched. No expected outcome was weakened.
