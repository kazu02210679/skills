# Task H3 Report: Skill, Contract, Trigger, and Evaluation Alignment

Date: 2026-07-29

## Outcome

H3 is implemented. The concise Skill now triggers only for the explicit combined requirements-and-iterative-review loop. Its references match the final H1/H2 transport, context, state, snapshot, and final-gate interfaces.

## RED evidence

The required fingerprint hardening began with:

```text
test_review_derives_root_cause_fingerprint_from_stable_source_fields ... ERROR
AttributeError: module 'validate_packet' has no attribute 'derive_root_cause_fingerprint'
Ran 1 test
FAILED (errors=1)
```

After the first implementation, the complete packet suite ran 72 tests with 11 failures. Those failures identified every old fixture or route that still depended on a Pro-selected fingerprint. No previous H1 test was removed to obtain GREEN.

Independent review then reproduced three further unsafe assumptions:

- a Pro-controlled final fingerprint and an undefined draft protocol;
- substring-based `PRO_CLASS` acceptance;
- ambiguous format correction without a recoverable original payload.

Each received a focused regression test before the final implementation.

## Implemented contract

- Pro review findings contain stable source fields, not a final fingerprint.
- Codex derives the four-field root-cause digest and a conservative three-field route continuity key. Finding-ID/root-key renames cannot evade consecutive blocker detection.
- Legacy `unresolved_findings` is rejected; v1 state requires controller-owned ID and derived fingerprint arrays.
- `PRO_CLASS` accepts only the controlled visible label `Pro`; other exact labels use `EXACT_LABEL`.
- Format correction is non-consuming only when a strictly recovered original payload has the same canonical digest. Ambiguous recovery stops or becomes a new semantic attempt.
- Minimal safe CLI entries cover envelope, format-correction, report context, review context, final gate, and context-bound transitions.
- Complete requirements/review envelopes, report, staged review state, final gate, context construction, canonical preflight/snapshot commands, model policy, timeout/reconnect, trust boundary, and artifact tree are documented.
- All five JSON examples in the packet reference are extracted and run through final validators by a regression test.

## Behavior observations

Each observation ran in a separate fresh context that received the scenario, `SKILL.md`, and only references directed by the Skill. Agents were not shown `cases.json`, the evaluation README, or earlier results. These are nondeterministic guidance observations, not deterministic safety proofs.

The required six cases matched all expected fields:

```text
requirements-owner                    matched
false-pass                            matched
evidence-only                         matched
requirements-revision                 matched
conversation-mismatch                 matched after one guidance refinement and fresh retest
ordinary-implementation-non-trigger   matched
```

Two added trigger guards also matched:

```text
requirements-only-non-trigger         matched
standalone-review-non-trigger         matched
```

The first conversation-mismatch sample stopped safely but returned prose instead of the stable audit token. The concise Skill named `conversation_identity_mismatch`; a new fresh context then matched without weakening the expected outcome.

## Final verification

```text
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
Ran 76 tests
OK

python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
Ran 34 tests
OK (skipped=2)
```

The two skips require POSIX case-sensitive paths or executable-mode behavior and are expected on Windows.

```text
python -m py_compile skills/gpt-pro-codex-loop/scripts/validate_packet.py
PASS

git diff --check
PASS

python scripts/validate-skills.py
ERROR: README Skill catalog is stale
```

The only Skill-validation failure is the root catalog update explicitly assigned to H4. H3 did not edit the catalog or host-compatibility files.

## Independent reviews

Spec review after fixes:

```text
Blocking 0 / High 0 / Medium 1
```

The sole Medium was this required report before it existed. Code and contracts were otherwise clean.

Standards review findings on fingerprint provenance, rename evasion, correction ambiguity, complete state/context guidance, non-trigger coverage, and event-version wording were addressed before commit.

## Scope

H3 changed only the Skill body/metadata/readmes/references, behavior cases, packet validator/tests, and this report. Catalog and host-compatibility integration remain H4.
