# GPT Pro Codex Loop Hardening Implementation Plan

> This plan implements
> `docs/superpowers/specs/2026-07-29-gpt-pro-codex-loop-hardening.md`.
> It supersedes incomplete Task 2, Task 3, Task 4, and Task 6 details in the
> original plan.

**Goal:** Close reproduced transport, validation, baseline attribution, product
identity, and completion gaps before publishing the independent Codex Desktop
Skill.

**Global constraints**

- Preserve uncommitted Task 4 files while Tasks H1 and H2 change interfaces.
- Use RED-GREEN-REFACTOR and standard-library Python.
- Keep `codex-orchestration`, API calls, commits/pushes/PRs/deployments, and
  Browser selectors out of the runtime Skill.
- Preserve raw prompts/responses and bound conversation/model identity.
- Do not mark Task 4 complete until every reference example validates against
  the final interfaces.

## Task H1: Strict JSON, Correlated Transport, and Context Gates

**Files**

- Modify `skills/gpt-pro-codex-loop/scripts/validate_packet.py`
- Modify `evals/gpt-pro-codex-loop/test_validate_packet.py`

**Required interfaces**

```python
strict_json_loads(raw: str) -> object
validate_transport_envelope(envelope, expected, consumed_digests) -> list[str]
validate_report_context(report, requirements, state, snapshot) -> list[str]
validate_review_context(envelope, requirements, report, state, snapshot) -> list[str]
validate_final_gate(evidence, state) -> list[str]
```

`expected` carries the exact envelope header values. All protocol artifacts
carry `schema_version: 1`.

**RED tests**

- duplicate keys at any nesting level;
- NaN, Infinity, and `-Infinity`;
- BOM and nested/multiple fences;
- `schema_version: true`;
- unknown keys in closed objects;
- stale/mismatched run, turn, nonce, reply, prompt, or previous-packet fields;
- consumed response digest reuse;
- format correction mutating domain state;
- unapproved or inactive requirements revision used by a report;
- report round/state mismatch;
- report snapshot/component mismatch;
- review without fresh validated envelope;
- review-stop resume retaining decision/actions;
- lowercase canonical fingerprint enforcement;
- completion without explicit bound final-gate evidence.

Run the tests and record the expected failures before implementation.

**GREEN requirements**

- Both Browser extraction and file loading use the strict decoder.
- Canonical digest sets `allow_nan=False`.
- Envelope fields and packet types are exact and closed.
- Context validators bind requirements, approval, report, review, state, and
  snapshot rather than trusting caller-selected compatible objects.
- Review-stop resume clears consumed routing data.
- `COMPLETE` is impossible without validated final-gate evidence.

Run:

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/validate_packet.py
```

Commit only after an independent task review is clean.

## Task H2: Canonical Preflight and Snapshot CLI

**Files**

- Modify `skills/gpt-pro-codex-loop/scripts/capture_snapshot.py`
- Modify `evals/gpt-pro-codex-loop/test_capture_snapshot.py`
- Update Task H1 report fixtures only when required by the new snapshot schema

**Required interfaces**

```python
inspect_preflight(repository, baseline_head) -> dict[str, object]
validate_preflight(preflight, approved_existing_paths) -> list[str]
capture_snapshot(repository, baseline_head, preflight) -> dict[str, object]
```

Implement the exact preflight, snapshot, tracked state, attribution, digest,
and CLI contracts from the hardening spec.

**RED tests**

- schema and digest formula;
- dirty tracked/untracked baseline preservation;
- untouched pre-existing, modified pre-existing, and new change attribution;
- tampered/wrong-baseline/path-only preflight;
- mode-only, symlink, submodule, delete, rename, and type changes;
- staged, unstaged, and staged-plus-unstaged distinctions;
- unmerged index and dirty submodule rejection;
- host diff/config independence of manifest identity;
- all three CLI commands, stdout, stderr, and exit codes;
- continued report-validator compatibility.

Retain every existing stable-observation, metadata, unsafe-path, ignored-file,
binary, case-alias, and integration test.

Run:

```powershell
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/capture_snapshot.py
```

Commit only after an independent task review is clean.

## Task H3: Align the Skill, References, Trigger, and Behavior Evaluation

**Files**

- Modify `skills/gpt-pro-codex-loop/SKILL.md`
- Modify `skills/gpt-pro-codex-loop/README.md`
- Modify `skills/gpt-pro-codex-loop/agents/openai.yaml`
- Modify `skills/gpt-pro-codex-loop/references/packet-contract.md`
- Modify `skills/gpt-pro-codex-loop/references/prompt-contract.md`
- Modify `evals/gpt-pro-codex-loop/README.md`
- Modify `evals/gpt-pro-codex-loop/cases.json`

Requirements:

- keep `SKILL.md` concise and link to the two references;
- narrow the trigger to an explicit combined requirements-and-review loop;
- document the envelope, timeout/reconnect decision, strict JSON, model policy,
  versioned artifacts, context gates, canonical snapshot CLI, and trust boundary;
- include complete validated requirements and review envelope examples;
- include executable preflight/capture/validation commands;
- replace `exactly these required fields` with exact closed-envelope wording and
  accurate payload extensibility wording;
- include preflight and snapshot JSON in the artifact tree;
- record behavior evaluations as observed, nondeterministic guidance checks.

Run every documented JSON example through the final validators. Repeat the six
fresh-context behavior cases with the final Skill. Require 6/6 expected
decisions, without claiming deterministic model reproduction.

Run:

```powershell
python scripts/validate-skills.py
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
```

Commit only after spec and standards reviews are clean.

## Task H4: Catalog and Host Integration

- Add the canonical Skill name to `tests/test_compatibility.py`.
- State in `docs/host-compatibility.md` that Codex Desktop executes the Browser
  loop; Claude Code may inspect or maintain it only.
- Generate the root catalog rather than editing it manually.
- Remove user-specific absolute paths from plan commands by using
  `$env:USERPROFILE` or repository-relative commands.

Run:

```powershell
python scripts/generate-skill-catalog.py
python scripts/generate-skill-catalog.py --check
python scripts/validate-skills.py
python -m unittest discover -s tests -v
```

## Task H5: Full and Live Correction-Loop Verification

1. Run both focused suites, catalog check, Skill validation, and the full unit
   suite.
2. Use a safe temporary repository with no secrets.
3. In one verified Pro conversation, execute the correction-loop smoke from the
   hardening spec: requirements, insufficient evidence or bounded omission,
   `CHANGES_REQUESTED`, routed correction/supplement, fresh report/snapshot,
   second review, `PASS`, and explicit final gate.
4. Verify turn/nonces, envelope chaining, round accounting, same conversation
   and model, stale artifact rejection, and unchanged final snapshot.
5. Preserve only redacted smoke evidence; do not commit `.ai-pro-loop/`.

After H1-H5, run a broad whole-branch review. Address one final fix wave, rerun
the relevant focused tests, and then use the branch-finishing workflow.
