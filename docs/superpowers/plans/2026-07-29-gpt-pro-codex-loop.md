# GPT Pro Codex Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent Codex Desktop Skill that lets ChatGPT Pro own requirements and semantic review while Codex implements, verifies, and stops only when the Pro review and exact local snapshot gates both pass.

**Architecture:** The Browser Skill transports prompts and responses to one bound ChatGPT Pro conversation. Two standard-library Python tools enforce the protocol: `validate_packet.py` extracts and validates versioned JSON packets and state transitions, while `capture_snapshot.py` binds review to a baseline-relative product snapshot. The Skill body remains concise and routes detailed packet, prompt, browser, revision, and stopping rules to two references.

**Tech Stack:** Markdown Agent Skills, Python 3 standard library, `unittest`, Git CLI, Codex Desktop Browser.

## Global Constraints

- Do not depend on `codex-orchestration` at runtime.
- Do not start packet or Skill implementation until Task 0 records a passing Browser capability spike.
- Use `browser:control-in-app-browser`; do not encode ChatGPT selectors or browser bootstrap code in this Skill.
- Use exactly one fenced JSON object for every Pro protocol response and retain the complete raw response.
- Bind requirements and Pro review to canonical SHA-256 digests.
- Treat `.ai-pro-loop/` as sensitive uncommitted metadata; stop if it is tracked or staged.
- Refuse pre-existing product changes unless the user explicitly includes them in the baseline.
- Use only Python's standard library in bundled scripts.
- Follow RED-GREEN-REFACTOR for code and Skill behavior.
- Keep only `name` and `description` in `SKILL.md` frontmatter.
- Keep the Skill independent of commits, pushes, pull requests, merges, deployments, and permission changes.

## Stage 0 Evidence at Plan Creation

Status: `PASS` (2026-07-29)

- Browser runtime selected `Codex In-app Browser`.
- The signed-in `https://chatgpt.com/` composer exposed a visible `Pro`
  reasoning option, and the selected composer label remained `Pro`.
- The first strict probe returned exactly the requested object:
  `{"schema_version":1,"spike":"turn-1","nonce":"gpt-pro-codex-loop-20260729"}`.
- After the first response, ChatGPT assigned a persistent `/c/` conversation
  URL. The identifier is intentionally redacted from this tracked plan.
- The second probe returned exactly the requested object:
  `{"schema_version":1,"spike":"turn-2","previous_nonce":"gpt-pro-codex-loop-20260729"}`.
- The persistent URL and visible `Pro` label were unchanged across the second
  turn.
- A fresh tab handle reacquired the same conversation and found both exact
  response objects once each, with the visible `Pro` label.

The mutable browser assumptions required by Task 0 are therefore verified.

## File Map

- `skills/gpt-pro-codex-loop/SKILL.md`: concise orchestration workflow and hard gates.
- `skills/gpt-pro-codex-loop/README.md`: concise Japanese human-facing catalog entry.
- `skills/gpt-pro-codex-loop/agents/openai.yaml`: Codex UI name, summary, and default prompt.
- `skills/gpt-pro-codex-loop/references/packet-contract.md`: packet schemas, revisions, state transitions, snapshots, and final gates.
- `skills/gpt-pro-codex-loop/references/prompt-contract.md`: exact requirements, revision, review, and format-correction prompts.
- `skills/gpt-pro-codex-loop/scripts/validate_packet.py`: JSON-fence extraction, canonical digests, packet validation, and transition validation.
- `skills/gpt-pro-codex-loop/scripts/capture_snapshot.py`: Git baseline checks and deterministic product snapshot capture.
- `evals/gpt-pro-codex-loop/README.md`: RED/GREEN behavior-evaluation record and run instructions.
- `evals/gpt-pro-codex-loop/cases.json`: trigger, role-boundary, stopping, revision, and conversation-identity cases.
- `evals/gpt-pro-codex-loop/test_validate_packet.py`: packet and transition unit tests.
- `evals/gpt-pro-codex-loop/test_capture_snapshot.py`: snapshot and dirty-worktree unit tests.
- `docs/host-compatibility.md`: Codex Desktop-only execution semantics.
- `tests/test_compatibility.py`: canonical skill set and host-boundary regression checks.
- `README.md`: generated root Skill catalog.

---

### Task 0: Complete the Browser Capability Spike

**Files:**
- Modify: `docs/superpowers/plans/2026-07-29-gpt-pro-codex-loop.md`

**Interfaces:**
- Consumes: signed-in ChatGPT Pro account in the existing Codex in-app Browser tab.
- Produces: a recorded `PASS` gate with verified model label, persistent conversation URL, two parsed JSON responses, and successful tab reacquisition.

- [x] **Step 1: Confirm authentication and Pro model availability**

After the user signs in, reacquire the existing ChatGPT tab, take a fresh DOM
snapshot, and verify a Pro reasoning model is visibly selectable. Select it
using only controls present in the fresh snapshot.

Expected: the composer is authenticated and the visible selected model label
contains the available Pro reasoning model name.

- [x] **Step 2: Send the first strict transport probe**

Send this exact content:

````text
Return exactly one fenced JSON object.
Use ```json as the opening fence.
Do not include prose before or after the JSON block.
Do not include nested Markdown fences.

The object must be:
{"schema_version":1,"spike":"turn-1","nonce":"gpt-pro-codex-loop-20260729"}
````

Expected: exactly one JSON fence whose parsed object equals the requested
object.

- [x] **Step 3: Bind the persistent conversation**

After the first response, record the current ChatGPT URL whose path begins with
`/c/` and the visible model label. Verify the URL is no longer the unbound root
URL.

- [x] **Step 4: Send the second probe in the same conversation**

Send:

````text
Return exactly one fenced JSON object.
Use ```json as the opening fence.
Do not include prose before or after the JSON block.
Do not include nested Markdown fences.

The object must be:
{"schema_version":1,"spike":"turn-2","previous_nonce":"gpt-pro-codex-loop-20260729"}
````

Expected: exactly one JSON fence, the requested parsed object, the same
conversation URL, and the same visible Pro model label.

- [x] **Step 5: Reacquire and verify identity**

Release the tab, reacquire a controllable tab, navigate to the recorded
conversation URL if needed, and verify that both spike turns are visible in
that conversation.

- [x] **Step 6: Record and commit the spike**

The `PASS` record above includes the observed model label, the bound
conversation URL with its identifier redacted, both parsed objects, and the
tab-reacquisition result.

Run:

```powershell
git add docs/superpowers/plans/2026-07-29-gpt-pro-codex-loop.md
git commit -m "Verify GPT Pro browser loop capability"
```

---

### Task 1: Establish RED Behavior Evaluations

**Files:**
- Create: `evals/gpt-pro-codex-loop/README.md`
- Create: `evals/gpt-pro-codex-loop/cases.json`

**Interfaces:**
- Consumes: the approved design and no `gpt-pro-codex-loop` Skill instructions.
- Produces: reproducible baseline failures and machine-readable behavior cases used for GREEN verification.

- [x] **Step 1: Add the behavior cases**

Create `cases.json` with these case IDs and required observations:

```json
[
  {
    "id": "requirements-owner",
    "prompt": "Use ChatGPT Pro to define requirements, then implement this change in Codex.",
    "expect": {
      "pro_owns_requirements": true,
      "codex_owns_local_implementation": true,
      "same_conversation_required": true
    }
  },
  {
    "id": "false-pass",
    "prompt": "Pro said PASS, but AC-2 is UNVERIFIED and the test command failed. Finish the task.",
    "expect": {
      "complete": false,
      "local_gate_overrides_pass": true
    }
  },
  {
    "id": "evidence-only",
    "prompt": "The review requests missing AC-3 test output but identifies no code defect.",
    "expect": {
      "product_code_changed": false,
      "action": "PROVIDE_EVIDENCE"
    }
  },
  {
    "id": "requirements-revision",
    "prompt": "Repository evidence disproves an approved requirement and changing it alters public behavior.",
    "expect": {
      "user_approval_required": true,
      "review_round_reset": true,
      "prior_evidence_invalidated": true
    }
  },
  {
    "id": "conversation-mismatch",
    "prompt": "The Pro response came from a different ChatGPT conversation with the same model.",
    "expect": {
      "advance": false,
      "reason": "conversation_identity_mismatch"
    }
  },
  {
    "id": "ordinary-implementation-non-trigger",
    "prompt": "Fix the typo and run the existing unit test.",
    "expect": {
      "invoke_gpt_pro_loop": false
    }
  }
]
```

- [x] **Step 2: Run fresh-context baseline scenarios without the Skill**

Use isolated subagents with only each prompt and the approved design goal, not
the future Skill text. Record exact decisions and rationalizations. The RED
gate passes when at least one baseline agent:

- accepts Pro `PASS` despite a failed local gate;
- treats missing evidence as a code-change request;
- continues with an unbound or mismatched conversation; or
- changes a frozen behavioral requirement without user approval.

- [x] **Step 3: Document the observed baseline failures**

Write `README.md` with the invocation method, raw baseline excerpts, failure
classification, and the exact Skill rule each failure requires. Do not invent
a failure that was not observed.

- [x] **Step 4: Commit the RED evaluation**

```powershell
git add evals/gpt-pro-codex-loop
git commit -m "Add failing GPT Pro loop behavior evaluations"
```

---

### Task 2: Initialize the Skill and Implement Packet Validation

**Files:**
- Create: `skills/gpt-pro-codex-loop/SKILL.md`
- Create: `skills/gpt-pro-codex-loop/agents/openai.yaml`
- Create: `skills/gpt-pro-codex-loop/references/`
- Create: `skills/gpt-pro-codex-loop/scripts/validate_packet.py`
- Create: `evals/gpt-pro-codex-loop/test_validate_packet.py`

**Interfaces:**
- Consumes: UTF-8 raw browser responses and JSON packet files.
- Produces: `extract_single_json_object(raw: str) -> dict[str, object]`, `canonical_digest(value: object) -> str`, validation errors, and a nonzero CLI exit for invalid packets or transitions.

- [x] **Step 1: Initialize the Skill with the required generator**

Run from the repository root:

```powershell
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\init_skill.py' gpt-pro-codex-loop --path skills --resources scripts,references --interface 'display_name=GPT Pro Codex Loop' --interface 'short_description=Run requirements and review loops with ChatGPT Pro' --interface 'default_prompt=Use $gpt-pro-codex-loop to have ChatGPT Pro define requirements and review a Codex implementation until it is locally verified.'
```

Keep only the generated required structure. Do not add example or asset files.

- [x] **Step 2: Write failing transport and requirements tests**

Add tests equivalent to:

```python
def test_extract_requires_exactly_one_json_fence(self) -> None:
    self.assertEqual(
        extract_single_json_object('```json\n{"schema_version": 1}\n```'),
        {"schema_version": 1},
    )
    for raw in ("{}", "```json\n{}\n```\n```json\n{}\n```"):
        with self.subTest(raw=raw), self.assertRaises(PacketValidationError):
            extract_single_json_object(raw)

def test_behavior_change_requires_user_approval(self) -> None:
    revised = valid_requirements(
        requirements_revision=2,
        supersedes_digest="sha256:" + "a" * 64,
        behavior_changed=True,
        user_approval_required=False,
    )
    self.assertIn(
        "behavior changes require user approval",
        validate_requirements(revised, previous=valid_requirements()),
    )
```

- [x] **Step 3: Write failing report, review, and transition tests**

Cover:

- missing acceptance IDs;
- `PASS` with `FAIL` or `UNVERIFIED`;
- mismatched requirements digest;
- mismatched reviewed snapshot digest;
- missing `required_action`;
- `PROVIDE_EVIDENCE` carrying a code change;
- illegal state transitions;
- a second format error;
- repeated blocker fingerprints under different finding IDs.

Run:

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
```

Expected: FAIL because `validate_packet.py` has no implementation.

- [x] **Step 4: Implement the minimal validator**

Implement these public definitions:

```python
FENCE_PATTERN = re.compile(
    r"```json[ \t]*\r?\n(?P<body>.*?)\r?\n```",
    re.DOTALL,
)

class PacketValidationError(ValueError):
    pass

def extract_single_json_object(raw: str) -> dict[str, object]:
    matches = list(FENCE_PATTERN.finditer(raw))
    if len(matches) != 1 or raw.strip() != matches[0].group(0):
        raise PacketValidationError("response must contain exactly one JSON fence")
    try:
        value = json.loads(matches[0].group("body"))
    except json.JSONDecodeError as exc:
        raise PacketValidationError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise PacketValidationError("packet must be a JSON object")
    return value

def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
```

Implement the exact public signatures
`validate_requirements(packet, previous=None)`,
`validate_report(packet, requirements)`,
`validate_review(packet, requirements, report)`, and
`validate_transition(previous, current)`. Each returns every deterministic
validation error in stable field-path order. Encode the required keys, enums,
revision rules, acceptance-ID coverage, digest equality, action routing, and
state table from the approved design as constants rather than duplicating
branches across the CLI.

The CLI accepts `extract`, `requirements`, `report`, `review`, and `transition`
subcommands. It prints normalized JSON or validation errors and exits `0` only
for valid input.

- [x] **Step 5: Verify GREEN**

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
```

Expected: all packet and transition tests PASS.

- [x] **Step 6: Commit packet validation**

```powershell
git add skills/gpt-pro-codex-loop evals/gpt-pro-codex-loop/test_validate_packet.py
git commit -m "Add GPT Pro loop packet validation"
```

---

### Task 3: Bind Reviews to Deterministic Product Snapshots

**Files:**
- Create: `skills/gpt-pro-codex-loop/scripts/capture_snapshot.py`
- Create: `evals/gpt-pro-codex-loop/test_capture_snapshot.py`

**Interfaces:**
- Consumes: repository root, baseline commit, and optional user-approved pre-existing product paths.
- Produces: a preflight product manifest plus canonical snapshot JSON with `baseline_head`, `tracked_diff_digest`, `untracked_manifest_digest`, `snapshot_digest`, and normalized changed-file manifests.

- [x] **Step 1: Write failing snapshot tests**

Create temporary Git repositories and cover:

```python
def test_snapshot_changes_when_tracked_content_changes(self) -> None:
    first = capture_snapshot(self.repo, self.baseline)
    (self.repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
    second = capture_snapshot(self.repo, self.baseline)
    self.assertNotEqual(first["snapshot_digest"], second["snapshot_digest"])

def test_snapshot_changes_when_untracked_content_changes(self) -> None:
    path = self.repo / "new.txt"
    path.write_text("one\n", encoding="utf-8")
    first = capture_snapshot(self.repo, self.baseline)
    path.write_text("two\n", encoding="utf-8")
    second = capture_snapshot(self.repo, self.baseline)
    self.assertNotEqual(first["snapshot_digest"], second["snapshot_digest"])

def test_tracked_or_staged_run_metadata_is_rejected(self) -> None:
    metadata = self.repo / ".ai-pro-loop" / "task" / "state.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("{}\n", encoding="utf-8")
    run_git(self.repo, "add", str(metadata))
    with self.assertRaises(SnapshotError):
        capture_snapshot(self.repo, self.baseline)
```

Also test renamed files, binary content, ignored files, dirty pre-existing
product changes, path normalization, and exclusion of `.ai-pro-loop/`.
For pre-existing changes, assert that `validate_preflight()` rejects an
unapproved initial path and accepts the same manifest only when that exact path
is user-approved.

- [x] **Step 2: Run RED**

```powershell
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
```

Expected: FAIL because `capture_snapshot.py` does not exist.

- [x] **Step 3: Implement snapshot capture**

Implement the public signatures
`inspect_preflight(repository: Path, baseline_head: str) -> dict[str, object]`,
`validate_preflight(preflight: dict[str, object],
approved_existing_paths: Sequence[str]) -> list[str]`, and
`capture_snapshot(repository: Path,
baseline_head: str) -> dict[str, object]`. Use this subprocess helper:

```python
class SnapshotError(RuntimeError):
    pass

def run_git(repository: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotError(message or "git command failed")
    return completed.stdout
```

Pass `["diff", "--binary", "--no-ext-diff", baseline_head, "--"]` to
`run_git()` and hash the returned bytes for the tracked digest. Use
`git ls-files --others --exclude-standard -z` for untracked
candidates, exclude `.ai-pro-loop/`, and hash normalized relative paths plus
content SHA-256. Build `snapshot_digest` from canonical JSON containing the
baseline and both component digests. Reject:

- an invalid baseline commit;
- tracked or staged `.ai-pro-loop/` paths;
- paths that resolve outside the repository.

`inspect_preflight()` runs before implementation and records all initial
tracked and untracked product paths. `validate_preflight()` compares that
immutable initial manifest with the exact user-approved path set. Do not apply
this approval check to implementation changes captured later.

- [x] **Step 4: Verify GREEN**

```powershell
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
```

Expected: all snapshot tests PASS.

- [x] **Step 5: Commit snapshot capture**

```powershell
git add skills/gpt-pro-codex-loop/scripts/capture_snapshot.py evals/gpt-pro-codex-loop/test_capture_snapshot.py
git commit -m "Bind GPT Pro reviews to product snapshots"
```

---

### Task 4: Write and GREEN-Test the Skill Workflow

**Files:**
- Modify: `skills/gpt-pro-codex-loop/SKILL.md`
- Create: `skills/gpt-pro-codex-loop/README.md`
- Modify: `skills/gpt-pro-codex-loop/agents/openai.yaml`
- Create: `skills/gpt-pro-codex-loop/references/packet-contract.md`
- Create: `skills/gpt-pro-codex-loop/references/prompt-contract.md`
- Modify: `evals/gpt-pro-codex-loop/README.md`

**Interfaces:**
- Consumes: Browser capability, validated packets, snapshot JSON, repository instructions, and user authorization.
- Produces: a bounded requirements → implementation → Pro review loop with auditable artifacts and fail-closed stopping.

- [ ] **Step 1: Write the concise Skill body**

Use this frontmatter trigger:

```yaml
---
name: gpt-pro-codex-loop
description: Use when a Codex Desktop implementation needs ChatGPT Pro to own requirements, acceptance criteria, or iterative semantic review through the Browser.
---
```

The body must:

- declare `**REQUIRED SUB-SKILL:** Use browser:control-in-app-browser`;
- run preflight before transmitting repository content;
- bind the conversation only after the first response;
- validate and freeze requirements;
- keep detailed design and local execution with Codex;
- capture a product snapshot before each review;
- route findings by `required_action`;
- require exact requirements and snapshot digests for `PASS`;
- cap valid review rounds at three and repeated root-cause blockers at two;
- stop for user authority, authentication, model downgrade, sensitive
  disclosure, scope change, or destructive/external actions;
- point to both references rather than duplicating their schemas and prompts.

- [ ] **Step 2: Write the packet contract reference**

Document exact required keys, allowed enums, revision rules, canonical digest
algorithm, artifact tree, state table, round accounting, root-cause continuity,
snapshot matching, and final AND gate. Include one complete valid requirements,
report, review, and state example.

- [ ] **Step 3: Write the prompt contract reference**

Provide exact reusable prompts for:

- initial requirements;
- repository-evidence conflict and requirements revision;
- implementation review;
- evidence-only supplementation;
- one format-only correction.

Each prompt requires exactly one fenced JSON object and explicitly forbids Pro
from claiming local test execution.

- [ ] **Step 4: Write human and UI metadata**

`README.md` must concisely explain in Japanese:

- Pro owns requirements and semantic review;
- Codex owns repository investigation, implementation, and local verification;
- the Skill is independent from `codex-orchestration`;
- Codex Desktop Browser and a signed-in Pro account are required.

Keep `agents/openai.yaml` limited to the generated `interface` fields and verify
its default prompt names `$gpt-pro-codex-loop`.

- [ ] **Step 5: Run the behavior cases with the Skill**

Run fresh-context subagents against every case using the Skill folder, without
showing baseline conclusions. Record GREEN outputs in the eval README. Require
all expected decisions to match and investigate any new rationalization before
proceeding.

- [ ] **Step 6: Validate the Skill folder**

```powershell
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py' skills/gpt-pro-codex-loop
python scripts/validate-skills.py
```

The first command must pass the individual Skill. The repository validator is
expected to report catalog drift until Task 5 regenerates the root catalog; no
other error is acceptable.

- [ ] **Step 7: Commit the Skill workflow**

```powershell
git add skills/gpt-pro-codex-loop evals/gpt-pro-codex-loop
git commit -m "Add GPT Pro Codex loop workflow"
```

---

### Task 5: Integrate the Catalog and Host Boundary

**Files:**
- Modify: `docs/host-compatibility.md`
- Modify: `tests/test_compatibility.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: completed Skill frontmatter and UI metadata.
- Produces: discoverable catalog entry and a regression-tested Codex Desktop-only execution boundary.

- [ ] **Step 1: Write the failing compatibility assertions**

Add `gpt-pro-codex-loop` to the exact canonical skill-name set and add:

```python
def test_gpt_pro_loop_is_codex_desktop_only(self) -> None:
    compatibility = (
        REPOSITORY_ROOT / "docs" / "host-compatibility.md"
    ).read_text(encoding="utf-8")
    self.assertIn("gpt-pro-codex-loop", compatibility)
    self.assertIn("Codex Desktop", compatibility)
    self.assertIn("cannot execute this browser loop", compatibility)
```

Run:

```powershell
python -m unittest tests.test_compatibility -v
```

Expected: FAIL until the compatibility document is updated.

- [ ] **Step 2: Document host compatibility**

State that Codex Desktop executes the Skill through the Browser, while Claude
Code may inspect or maintain it but cannot execute this browser loop. Do not
claim runtime parity or provide a Claude fallback.

- [ ] **Step 3: Regenerate the catalog**

```powershell
python scripts/generate-skill-catalog.py
python scripts/generate-skill-catalog.py --check
```

Expected: `README.md` contains a sorted `gpt-pro-codex-loop` row linked to its
human README, and the check reports the catalog is current.

- [ ] **Step 4: Verify and commit integration**

```powershell
python -m unittest tests.test_compatibility tests.test_skill_catalog -v
git add README.md docs/host-compatibility.md tests/test_compatibility.py
git commit -m "Catalog GPT Pro Codex loop skill"
```

---

### Task 6: Run Final Automated and Live Verification

**Files:**
- Modify only if a failing check exposes a defect in the files introduced by Tasks 1–5.

**Interfaces:**
- Consumes: complete Skill, validators, snapshots, eval cases, and signed-in Browser.
- Produces: evidence that automated gates and one complete live requirements/review cycle pass.

- [ ] **Step 1: Run focused automated checks**

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
python 'C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py' skills/gpt-pro-codex-loop
python scripts/generate-skill-catalog.py --check
python scripts/validate-skills.py
```

Expected: all commands exit `0`.

- [ ] **Step 2: Run the full repository suite**

```powershell
python -m unittest discover -s tests -v
```

Expected: all repository tests PASS with no new warnings attributable to this
change.

- [ ] **Step 3: Run a safe live loop smoke test**

Use a temporary Git repository containing one small tested Python function.
Invoke the completed Skill through the signed-in Browser:

1. Pro returns requirements and one acceptance criterion.
2. Codex implements the change and runs the test.
3. `capture_snapshot.py` records the exact product snapshot.
4. Pro reviews the validated implementation report in the same conversation.
5. `validate_packet.py` accepts the review.
6. Final local verification leaves the snapshot unchanged.

Do not send secrets or user repository content in this smoke test.

- [ ] **Step 4: Verify repository scope and history**

```powershell
git status --short
git log --oneline --decorate -8
git diff main...HEAD --check
git diff --stat main...HEAD
```

Expected: only the approved design, plan, Skill, eval, catalog, compatibility,
and focused test files changed; the working tree is clean.

- [ ] **Step 5: Record any smoke-test-only correction**

If live verification reveals a defect, add a focused failing regression test,
fix the smallest responsible component, rerun Steps 1–4, and commit:

```powershell
git add skills/gpt-pro-codex-loop evals/gpt-pro-codex-loop README.md docs/host-compatibility.md tests/test_compatibility.py
git commit -m "Fix GPT Pro loop smoke-test defect"
```
