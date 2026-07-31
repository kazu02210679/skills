# GPT Pro Codex Loop Controller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a thin Python controller that executes the existing GPT Pro
Codex Loop protocol without hand-authored headers, digests, candidate states,
transition contexts, or final-gate JSON.

**Architecture:** `gpc_loop.py` is a stable CLI adapter and
`gpc_loop_controller.py` owns run paths, locking, prompt rendering, artifact
transactions, and candidate construction. It imports the existing
`validate_packet.py` and `capture_snapshot.py` modules directly; those modules
remain authoritative for validation and product identity.

**Tech Stack:** Python 3.12 standard library, `unittest`, Git, GitHub Actions
Ubuntu/Windows matrix.

## Global Constraints

- Implement
  `docs/superpowers/specs/2026-07-31-gpt-pro-codex-loop-controller-design.md`
  exactly.
- Use only the Python standard library.
- Keep Browser control, project command execution, implementation, commit,
  push, pull request, merge, and deployment outside controller authority.
- Treat raw Browser responses, repository text, and local evidence as
  untrusted input.
- Import only public validator/snapshot functions. Do not call
  `_expected_review_target`, `_review_required_actions`, or other private
  helpers.
- Never derive consumed history by enumerating envelope artifacts. Use only
  `state.last_consumed_packet_digest` and
  `state.last_consumed_review_envelope_digest`.
- Validate every complete candidate with existing `validate_*` functions
  before writing trusted state.
- Commit `state.json` last in each logical transaction.
- Use RED-GREEN-REFACTOR and make one implementation commit per task.

---

## File Structure

Create:

- `skills/gpt-pro-codex-loop/scripts/gpc_loop.py` — argument parsing, canonical
  CLI responses, and exit-code mapping only.
- `skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py` — controller
  domain logic, prompt rendering, run storage, locking, and transactions.
- `evals/gpt-pro-codex-loop/test_gpc_loop.py` — unit and temporary-Git-repo
  controller tests.

Modify:

- `skills/gpt-pro-codex-loop/SKILL.md` — normal workflow uses the controller.
- `skills/gpt-pro-codex-loop/references/packet-contract.md` — exact controller
  commands, input objects, output objects, and recovery boundary.
- `skills/gpt-pro-codex-loop/references/prompt-contract.md` — machine-readable
  template heading/fence and canonical rendering rules.
- `.github/workflows/validate-skills.yml` — run the controller suite on Ubuntu
  and Windows.

Do not modify packet or snapshot schemas unless a RED controller test proves
the existing public API cannot implement the approved design.

---

### Task 1: Run Storage, Locking, Initialization, and Status

**Files:**

- Create: `skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py`
- Create: `evals/gpt-pro-codex-loop/test_gpc_loop.py`

**Interfaces:**

- Consumes:
  - `capture_snapshot.inspect_preflight(repository: Path, baseline_head: str)`
  - `capture_snapshot.validate_preflight(preflight, approved_paths, repository)`
  - `validate_packet.canonical_digest(value)`
  - `validate_packet.strict_json_loads(raw)`
  - `validate_packet.validate_transition(previous, current)`
- Produces:

```python
class ControllerError(RuntimeError):
    code: str
    message: str
    details: tuple[str, ...]

@dataclass(frozen=True)
class RunPaths:
    repository: Path
    task_slug: str
    run: Path
    state: Path
    preflight: Path
    events: Path
    transactions: Path
    lock: Path

def resolve_run(repository: Path, task_slug: str) -> RunPaths
def load_json(path: Path) -> dict[str, object]
def write_json_atomic(path: Path, value: object) -> None
def write_text_atomic(path: Path, value: str) -> None
def initialize_run(
    repository: Path,
    task_slug: str,
    request_path: Path,
    repository_context_path: Path,
    approved_existing_paths: Sequence[str],
    model_policy: str,
    requested_model_label: str | None,
) -> dict[str, object]
def status_run(repository: Path, task_slug: str) -> dict[str, object]
```

- [ ] **Step 1: Write the storage and initialization RED tests**

Add imports and a temporary Git repository fixture:

```python
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "gpt-pro-codex-loop"
    / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

import gpc_loop_controller as controller


class ControllerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name) / "repo"
        self.repository.mkdir()
        subprocess.run(["git", "init"], cwd=self.repository, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "controller@example.invalid"],
            cwd=self.repository,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Controller Test"],
            cwd=self.repository,
            check=True,
        )
        (self.repository / "README.md").write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.repository, check=True)
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=self.repository,
            check=True,
            capture_output=True,
        )
        self.request = self.repository / "request.txt"
        self.context = self.repository / "context.txt"
        self.request.write_text("Add deterministic behavior.\n", encoding="utf-8")
        self.context.write_text("The repository uses Python.\n", encoding="utf-8")

    def _init_run(self) -> dict[str, object]:
        return controller.initialize_run(
            self.repository,
            "controller-test",
            self.request,
            self.context,
            [],
            "PRO_CLASS",
            None,
        )

    def _run_dir(self) -> Path:
        return self.repository / ".ai-pro-loop" / "controller-test"

    def _state(self) -> dict[str, object]:
        return controller.load_json(self._run_dir() / "state.json")

    def _state_bytes(self) -> bytes:
        return (self._run_dir() / "state.json").read_bytes()
```

Add exact tests:

```python
def test_resolve_run_rejects_traversal_and_separator_slugs(self) -> None:
    for slug in ("../escape", r"a\b", "a/b", ".", "..", "a\nb"):
        with self.subTest(slug=slug):
            with self.assertRaisesRegex(controller.ControllerError, "task slug"):
                controller.resolve_run(self.repository, slug)

def test_init_creates_valid_unbound_requirements_pending_state(self) -> None:
    result = controller.initialize_run(
        self.repository,
        "controller-test",
        self.request,
        self.context,
        [],
        "PRO_CLASS",
        None,
    )
    run = self.repository / ".ai-pro-loop" / "controller-test"
    state = controller.load_json(run / "state.json")
    self.assertEqual(result["phase"], "REQUIREMENTS_PENDING")
    self.assertEqual(state["phase"], "REQUIREMENTS_PENDING")
    self.assertEqual(state["conversation_binding_state"], "CONVERSATION_UNBOUND")
    self.assertIsNone(state["bound_conversation_url"])
    self.assertIsNone(state["visible_model_label"])
    self.assertEqual(state["approved_existing_paths"], [])

def test_init_refuses_existing_run_and_unapproved_dirty_baseline(self) -> None:
    controller.initialize_run(
        self.repository, "controller-test", self.request, self.context, [], "PRO_CLASS", None
    )
    with self.assertRaisesRegex(controller.ControllerError, "already exists"):
        controller.initialize_run(
            self.repository, "controller-test", self.request, self.context, [], "PRO_CLASS", None
        )

    (self.repository / "new-product.py").write_text("value = 1\n", encoding="utf-8")
    with self.assertRaisesRegex(controller.ControllerError, "unapproved pre-existing"):
        controller.initialize_run(
            self.repository, "dirty-test", self.request, self.context, [], "PRO_CLASS", None
        )

def test_status_is_read_only_and_reports_lock_and_orphan_transaction(self) -> None:
    controller.initialize_run(
        self.repository, "controller-test", self.request, self.context, [], "PRO_CLASS", None
    )
    paths = controller.resolve_run(self.repository, "controller-test")
    original = paths.state.read_bytes()
    paths.lock.write_text('{"pid":999999}\n', encoding="utf-8")
    (paths.transactions / "orphan").mkdir(parents=True)
    status = controller.status_run(self.repository, "controller-test")
    self.assertTrue(status["lock_present"])
    self.assertEqual(status["orphan_transactions"], ["orphan"])
    self.assertEqual(status["next_commands"], ["prepare-requirements"])
    self.assertEqual(paths.state.read_bytes(), original)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_gpc_loop.py" -v
```

Expected: import failure for `gpc_loop_controller`.

- [ ] **Step 3: Implement controller errors, safe paths, strict I/O, and lock**

Start `gpc_loop_controller.py` with:

```python
#!/usr/bin/env python3
"""Deterministic controller for the GPT Pro Codex Loop Skill."""

from __future__ import annotations

import json
import os
import re
import socket
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

import capture_snapshot
import validate_packet

SCHEMA_VERSION = 1
TASK_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z")


class ControllerError(RuntimeError):
    def __init__(
        self, code: str, message: str, details: Sequence[str] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = tuple(details)


@dataclass(frozen=True)
class RunPaths:
    repository: Path
    task_slug: str
    run: Path
    state: Path
    preflight: Path
    events: Path
    transactions: Path
    lock: Path
```

Implement:

- repository root verification with `git rev-parse --show-toplevel`;
- slug validation with `TASK_SLUG.fullmatch`;
- resolved `.ai-pro-loop/<slug>` containment;
- strict JSON loading through `validate_packet.strict_json_loads`;
- canonical JSON bytes through
  `json.dumps(..., ensure_ascii=False, sort_keys=True,
  separators=(",", ":"), allow_nan=False) + "\n"`;
- atomic file replacement using a sibling `NamedTemporaryFile(delete=False)`
  followed by `os.replace`;
- `run_lock()` using `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`;
- lock content with schema version, PID, hostname, and Unix timestamp;
- lock deletion only in the owning context manager's `finally`.

Do not auto-delete an existing lock.

- [ ] **Step 4: Implement the complete initial states and initialization**

Add `initial_state(preflight, approved_paths, model_policy,
requested_label)`. Return every key in
`validate_packet.REQUIRED_STATE_FIELDS`. The `PREFLIGHT` version has:

```python
{
    "schema_version": 1,
    "phase": "PREFLIGHT",
    "review_round": 0,
    "latest_decision": None,
    "latest_requirements_decision": None,
    "required_actions": [],
    "unresolved_finding_ids": [],
    "blocker_fingerprints": [],
    "format_error_count": 0,
    "browser_reconnect_count": 0,
    "conversation_binding_state": "CONVERSATION_UNBOUND",
    "bound_conversation_url": None,
    "model_policy": model_policy,
    "requested_model_label": requested_label,
    "visible_model_label": None,
    "active_requirements_revision": None,
    "active_requirements_digest": None,
    "approval_sequence": 0,
    "pending_requirements_revision": None,
    "pending_requirements_digest": None,
    "pending_supersedes_digest": None,
    "pending_approval_sequence": None,
    "pending_approved_requirements_digest": None,
    "pending_user_approval_evidence": None,
    "behavior_changed": False,
    "user_approval_required": False,
    "scope_changed": False,
    "public_contract_changed": False,
    "prior_evidence_invalidated": False,
    "review_round_reset": False,
    "user_approval_received": False,
    "stop_origin_phase": None,
    "stop_origin_category": None,
    "stop_reason": None,
    "stop_sequence": 0,
    "resolution_evidence": None,
    "resolution_stop_sequence": None,
    "pending_requirements_envelope_digest": None,
    "pending_review_envelope_digest": None,
    "last_consumed_packet_digest": None,
    "last_consumed_review_envelope_digest": None,
    "active_report_digest": None,
    "current_snapshot_digest": None,
    "active_review_packet_digest": None,
    "reviewed_snapshot_digest": None,
    "baseline_head": preflight["baseline_head"],
    "preflight_digest": validate_packet.canonical_digest(preflight),
    "approved_existing_paths": sorted(approved_paths),
}
```

Clone it for the candidate and change only `phase` to
`REQUIREMENTS_PENDING`. Require
`validate_packet.validate_transition(previous, candidate) == []`.

`initialize_run` must validate `PRO_CLASS`/`EXACT_LABEL`, inspect and validate
preflight, stage all files, commit `state.json` last, and return
`status_run(...)`.

- [ ] **Step 5: Implement read-only status**

Use a phase-to-command function so a review-origin user stop cannot be mistaken
for a requirements approval:

```python
def next_commands(
    state: Mapping[str, object],
    outstanding_attempt: Mapping[str, object] | None,
) -> list[str]:
    if outstanding_attempt is not None:
        packet_type = outstanding_attempt["expected_header"]["packet_type"]
        if packet_type == "requirements" and state["phase"] == "REQUIREMENTS_PENDING":
            return ["accept-requirements", "abandon-attempt"]
        if packet_type == "review" and state["phase"] == "REVIEW_PENDING":
            return ["accept-review", "abandon-attempt"]
        return []
    if state["phase"] == "USER_DECISION_REQUIRED":
        return (
            ["approve-requirements"]
            if state["stop_origin_category"] == "REQUIREMENTS_NEED_USER_INPUT"
            else []
        )
    return {
        "REQUIREMENTS_PENDING": ["prepare-requirements"],
        "REQUIREMENTS_FROZEN": ["build-report"],
        "IMPLEMENTING": ["build-report"],
        "LOCAL_VERIFICATION": ["build-report", "prepare-review"],
        "REVIEW_PENDING": ["prepare-review"],
        "FINAL_VERIFICATION": ["final-verify"],
        "COMPLETE": [],
        "BLOCKED": [],
        "PREFLIGHT": [],
    }[str(state["phase"])]
```

Return only phase, revision, review round, safe conversation/model summary,
actions, stop category, outstanding attempt names, lock presence, orphan
transaction names, unreachable artifact names, and permitted commands.
`status_run` passes the single discovered outstanding attempt, or `None`, to
`next_commands`; it never returns both `prepare-*` and `accept-*` for one
semantic turn.

- [ ] **Step 6: Run Task 1 tests and existing suites**

Run:

```powershell
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_gpc_loop.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_capture_snapshot.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_validate_packet.py" -v
```

Expected: all pass.

- [ ] **Step 7: Commit Task 1**

```powershell
git add skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py evals/gpt-pro-codex-loop/test_gpc_loop.py
git commit -m "feat: initialize GPT Pro loop controller runs"
```

---

### Task 2: Canonical Prompt Rendering and Attempt Lifecycle

**Files:**

- Modify: `skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py`
- Modify: `evals/gpt-pro-codex-loop/test_gpc_loop.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class Template:
    parts: tuple[str | Token, ...]

@dataclass(frozen=True)
class Token:
    name: str

def load_template(contract: Path, heading: str) -> Template
def parse_template(raw: str, required_tokens: set[str]) -> Template
def render_prompt(
    template: Template, values: Mapping[str, str | Template]
) -> dict[str, str]
def prepare_requirements(
    repository: Path,
    task_slug: str,
    conflict_evidence_path: Path | None = None,
) -> dict[str, object]
def abandon_attempt(
    repository: Path,
    task_slug: str,
    send_status: str,
    evidence_path: Path,
) -> dict[str, object]
```

- [ ] **Step 1: Write prompt and attempt RED tests**

Add tests:

```python
def test_template_rendering_is_platform_stable_and_does_not_reparse_values(self) -> None:
    template = controller.Template(
        (
            "Request:\n",
            controller.Token("USER_REQUEST"),
            "\nDigest:",
            controller.Token("PROMPT_DIGEST"),
            "\n",
        )
    )
    value = "literal {{PROMPT_DIGEST}}\r\nline"
    first = controller.render_prompt(template, {"USER_REQUEST": value})
    second = controller.render_prompt(template, {"USER_REQUEST": value.replace("\r\n", "\n")})
    self.assertEqual(first, second)
    self.assertIn("literal {{PROMPT_DIGEST}}", first["prompt"])
    self.assertRegex(first["prompt_digest"], r"sha256:[0-9a-f]{64}")

def test_template_rejects_missing_duplicate_and_unknown_tokens(self) -> None:
    with self.assertRaisesRegex(controller.ControllerError, "duplicate"):
        controller.parse_template("{{USER_REQUEST}}{{USER_REQUEST}}\n", {"USER_REQUEST"})
    with self.assertRaisesRegex(controller.ControllerError, "unknown"):
        controller.parse_template("{{UNSUPPORTED}}\n", {"USER_REQUEST"})
    with self.assertRaisesRegex(controller.ControllerError, "missing"):
        controller.parse_template("plain\n", {"USER_REQUEST"})

def test_prepare_requirements_persists_expected_header_before_return(self) -> None:
    self._init_run()
    result = controller.prepare_requirements(self.repository, "controller-test")
    expected = controller.load_json(Path(result["expected_header_path"]))
    self.assertEqual(expected["packet_type"], "requirements")
    self.assertEqual(expected["previous_packet_digest"], None)
    self.assertTrue(Path(result["prompt_path"]).is_file())
    self.assertEqual(
        expected["prompt_digest"],
        result["prompt_digest"],
    )
    self.assertEqual(
        controller.status_run(self.repository, "controller-test")["next_commands"],
        ["accept-requirements", "abandon-attempt"],
    )

def test_second_outstanding_attempt_is_refused(self) -> None:
    self._init_run()
    controller.prepare_requirements(self.repository, "controller-test")
    with self.assertRaisesRegex(controller.ControllerError, "outstanding"):
        controller.prepare_requirements(self.repository, "controller-test")

def test_abandon_requires_proven_not_sent_and_preserves_state(self) -> None:
    self._init_run()
    controller.prepare_requirements(self.repository, "controller-test")
    paths = controller.resolve_run(self.repository, "controller-test")
    original = paths.state.read_bytes()
    evidence = self.repository / "not-sent.txt"
    evidence.write_text("The composer remained empty; no send action occurred.\n", encoding="utf-8")
    with self.assertRaisesRegex(controller.ControllerError, "NOT_SENT"):
        controller.abandon_attempt(
            self.repository, "controller-test", "AMBIGUOUS", evidence
        )
    result = controller.abandon_attempt(
        self.repository, "controller-test", "NOT_SENT", evidence
    )
    self.assertEqual(paths.state.read_bytes(), original)
    self.assertTrue(Path(result["abandoned_attempt_path"]).is_file())
    replacement = controller.prepare_requirements(self.repository, "controller-test")
    self.assertNotEqual(result["nonce"], replacement["nonce"])
```

- [ ] **Step 2: Run prompt tests and verify RED**

Run:

```powershell
python -m unittest evals.gpt-pro-codex-loop.test_gpc_loop -v
```

If module-name discovery rejects the hyphenated directory, use:

```powershell
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_gpc_loop.py" -v
```

Expected: missing template and attempt interfaces.

- [ ] **Step 3: Implement structural templates and canonical prompt digest**

Extend the controller imports with:

```python
import hashlib
import secrets
from typing import Mapping
```

Parse only the first text fence immediately following an exact Markdown
heading. Normalize source and inserted text to LF and one trailing LF. Build
token nodes from the source template before inserting values. Render twice and
hash the exact first rendering bytes:

```python
def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()

digest_source = render_nodes(
    template.parts,
    values,
    prompt_digest="{{PROMPT_DIGEST}}",
)
prompt_digest = sha256_bytes(digest_source.encode("utf-8"))
prompt = render_nodes(template.parts, values, prompt_digest=prompt_digest)
```

Do not hash a JSON wrapper around the prompt.

Required token sets:

```python
TEMPLATE_TOKENS = {
    "Shared envelope instruction": {
        "PACKET_TYPE",
        "RUN_ID",
        "TURN_ID",
        "NONCE",
        "IN_REPLY_TO_DIGEST",
        "PROMPT_DIGEST",
        "PREVIOUS_PACKET_DIGEST_OR_NULL",
    },
    "Initial requirements": {
        "USER_REQUEST",
        "REPOSITORY_EVIDENCE",
        "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REQUIREMENTS",
    },
    "Requirements revision": {
        "PREVIOUS_REQUIREMENTS_JSON",
        "PREVIOUS_REQUIREMENTS_DIGEST",
        "CONFLICT_EVIDENCE",
        "APPROVAL_RECEIPT_OR_NULL",
        "NEXT_REVISION",
        "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REQUIREMENTS",
    },
    "Implementation review": {
        "REQUIREMENTS_JSON",
        "REQUIREMENTS_DIGEST",
        "IMPLEMENTATION_REPORT_JSON",
        "SNAPSHOT_DIGEST",
        "SHARED_ENVELOPE_INSTRUCTION_WITH_PACKET_TYPE_REVIEW",
    },
    "Evidence-only supplementation": {
        "SNAPSHOT_DIGEST",
        "REQUIREMENTS_JSON",
        "PRIOR_REVIEW_JSON",
        "SUPPLEMENTAL_EVIDENCE",
    },
}
```

Nested template values are rendered node sequences, not reparsed strings.

- [ ] **Step 4: Implement correlated attempt creation**

Use:

```python
run_id = f"gpc-loop-{task_slug}"
turn_id = f"{packet_type}-{semantic_sequence:02d}"
nonce = secrets.token_hex(16)
in_reply_to = validate_packet.canonical_digest(
    {"run_id": run_id, "turn_id": turn_id, "source_digest": source_digest}
)
previous_packet_digest = state["last_consumed_packet_digest"]
```

Persist:

```text
prompts/<turn-id>-attempt-NN.md
expected-attempt-NN.json
```

The expected file is the exact eight-field header. Sequence selection scans
all expected and abandoned attempt names, but consumed-envelope history still
comes only from state.

- [ ] **Step 5: Implement atomic attempt abandonment**

Require `send_status == "NOT_SENT"`, one outstanding expected file, no matching
raw response or envelope, and non-empty evidence. Atomically replace the
expected file with:

```json
{
  "schema_version": 1,
  "status": "ABANDONED_NOT_SENT",
  "expected_header": {},
  "expected_header_digest": "sha256:...",
  "nonce": "copied from expected_header",
  "prompt_digest": "copied from expected_header",
  "evidence": "bounded local evidence",
  "abandoned_at_unix": 0
}
```

Use the actual Unix integer at runtime. The object is closed in controller
validation and never passed to Pro.

- [ ] **Step 6: Run Task 2 tests and commit**

Run:

```powershell
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_gpc_loop.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_validate_packet.py" -v
```

Commit:

```powershell
git add skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py evals/gpt-pro-codex-loop/test_gpc_loop.py
git commit -m "feat: prepare correlated GPT Pro loop prompts"
```

---

### Task 3: Requirements Acceptance and Material Approval

**Files:**

- Modify: `skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py`
- Modify: `evals/gpt-pro-codex-loop/test_gpc_loop.py`

**Interfaces:**

```python
def observed_browser_errors(
    state: Mapping[str, object],
    observed_url: str,
    observed_model_label: str,
    allow_initial_binding: bool,
) -> list[str]
def consumed_chain_heads(state: Mapping[str, object]) -> set[str]
def accept_requirements(
    repository: Path,
    task_slug: str,
    raw_response_path: Path,
    observed_conversation_url: str,
    observed_model_label: str,
) -> dict[str, object]
def approve_requirements(
    repository: Path,
    task_slug: str,
    approval_evidence_path: Path,
) -> dict[str, object]
```

- [ ] **Step 1: Add end-to-end requirements RED tests**

Create test helpers that read the outstanding expected header and build one
strict fenced envelope:

```python
def write_raw_envelope(
    path: Path,
    expected: dict[str, object],
    payload: dict[str, object],
) -> dict[str, object]:
    envelope = {**expected, "payload": payload}
    path.write_text(
        "```json\n"
        + json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    return envelope


def valid_requirements(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "requirements_revision": 1,
        "supersedes_digest": None,
        "change_reason": "Initial requirements.",
        "behavior_changed": False,
        "user_approval_required": False,
        "user_approval_received": False,
        "scope_changed": False,
        "public_contract_changed": False,
        "prior_evidence_invalidated": False,
        "review_round_reset": False,
        "decision": "PLAN_READY",
        "objective": "Implement deterministic behavior.",
        "requirements": [{"id": "REQ-1", "statement": "Behavior is deterministic."}],
        "in_scope": ["example.py"],
        "out_of_scope": ["deployment"],
        "constraints": ["standard library"],
        "acceptance_criteria": [
            {
                "id": "AC-1",
                "criterion": "The focused test passes.",
                "required_evidence": "Focused unittest output.",
            }
        ],
        "design_direction": ["Keep the implementation small."],
        "risk_items": [
            {
                "id": "RISK-1",
                "risk": "Evidence may be incomplete.",
                "required_mitigation": "Require AC-1 evidence.",
            }
        ],
        "verification_strategy": ["Run the focused unittest."],
        "open_questions": [],
    }
    value.update(overrides)
    return value


def _freeze_initial_requirements(self) -> dict[str, object]:
    self._init_run()
    attempt = controller.prepare_requirements(self.repository, "controller-test")
    expected = controller.load_json(Path(attempt["expected_header_path"]))
    raw = self.repository / "requirements.raw.md"
    write_raw_envelope(raw, expected, valid_requirements())
    return controller.accept_requirements(
        self.repository,
        "controller-test",
        raw,
        "https://chatgpt.com/c/controller-test",
        "Pro",
    )


def _seed_requirements_revision_pending(self) -> None:
    state = self._state()
    state.update(
        phase="REQUIREMENTS_PENDING",
        latest_decision="CHANGES_REQUESTED",
        latest_requirements_decision=None,
        required_actions=["REQUIREMENTS_REVISION"],
        pending_requirements_envelope_digest=None,
        pending_review_envelope_digest=None,
    )
    controller.write_json_atomic(self._run_dir() / "state.json", state)


def _write_conflict(self) -> Path:
    path = self.repository / "conflict.txt"
    path.write_text(
        "Repository evidence requires a material behavior revision.\n",
        encoding="utf-8",
    )
    return path
```

Add tests:

```python
def test_accept_initial_requirements_binds_browser_and_freezes(self) -> None:
    self._init_run()
    attempt = controller.prepare_requirements(self.repository, "controller-test")
    expected = controller.load_json(Path(attempt["expected_header_path"]))
    raw = self.repository / "requirements.raw.md"
    envelope = write_raw_envelope(raw, expected, valid_requirements())
    result = controller.accept_requirements(
        self.repository,
        "controller-test",
        raw,
        "https://chatgpt.com/c/controller-test",
        "Pro",
    )
    self.assertEqual(result["phase"], "REQUIREMENTS_FROZEN")
    state = self._state()
    self.assertEqual(
        state["last_consumed_packet_digest"],
        controller.validate_packet.canonical_digest(envelope),
    )
    self.assertEqual(
        state["bound_conversation_url"],
        "https://chatgpt.com/c/controller-test",
    )

def test_accept_requirements_rejects_wrong_observed_browser_without_state_change(self) -> None:
    self._init_run()
    attempt = controller.prepare_requirements(self.repository, "controller-test")
    expected = controller.load_json(Path(attempt["expected_header_path"]))
    raw = self.repository / "requirements.raw.md"
    write_raw_envelope(raw, expected, valid_requirements())
    before = self._state_bytes()
    with self.assertRaisesRegex(controller.ControllerError, "model"):
        controller.accept_requirements(
            self.repository,
            "controller-test",
            raw,
            "https://chatgpt.com/c/controller-test",
            "Standard",
        )
    self.assertEqual(self._state_bytes(), before)

def test_orphan_envelope_does_not_enter_consumed_history(self) -> None:
    self._init_run()
    paths = controller.resolve_run(self.repository, "controller-test")
    (paths.run / "envelope-99.json").write_text(
        json.dumps({"schema_version": 1}) + "\n",
        encoding="utf-8",
    )
    self.assertEqual(controller.consumed_chain_heads(self._state()), set())

def test_material_proposal_requires_digest_bound_local_approval(self) -> None:
    self._freeze_initial_requirements()
    self._seed_requirements_revision_pending()
    attempt = controller.prepare_requirements(
        self.repository,
        "controller-test",
        conflict_evidence_path=self._write_conflict(),
    )
    expected = controller.load_json(Path(attempt["expected_header_path"]))
    proposal = valid_requirements(
        requirements_revision=2,
        supersedes_digest=self._state()["active_requirements_digest"],
        decision="NEED_USER_INPUT",
        behavior_changed=True,
        user_approval_required=True,
        prior_evidence_invalidated=True,
        review_round_reset=True,
    )
    raw = self.repository / "revision.raw.md"
    write_raw_envelope(raw, expected, proposal)
    stopped = controller.accept_requirements(
        self.repository,
        "controller-test",
        raw,
        self._state()["bound_conversation_url"],
        "Pro",
    )
    self.assertEqual(stopped["phase"], "USER_DECISION_REQUIRED")
    evidence = self.repository / "approval.txt"
    evidence.write_text("The user approved this exact proposal.\n", encoding="utf-8")
    frozen = controller.approve_requirements(
        self.repository, "controller-test", evidence
    )
    self.assertEqual(frozen["phase"], "REQUIREMENTS_FROZEN")
    self.assertEqual(frozen["review_round"], 0)
```

- [ ] **Step 2: Run requirements tests and verify RED**

Run the controller suite. Expected: missing acceptance and approval functions.

- [ ] **Step 3: Implement observed Browser validation and consumed heads**

Rules:

```python
def consumed_chain_heads(state):
    return {
        value
        for value in (
            state["last_consumed_packet_digest"],
            state["last_consumed_review_envelope_digest"],
        )
        if isinstance(value, str)
    }
```

For first binding require an HTTPS `chatgpt.com/c/` URL and policy-compliant
label. For a bound run require exact URL and exact controlled label. `PRO_CLASS`
requires `Pro`; `EXACT_LABEL` requires `requested_model_label`.

- [ ] **Step 4: Implement requirements candidate construction**

Perform these validations before staging:

```python
envelope = validate_packet.extract_single_json_object(raw)
envelope_errors = validate_packet.validate_transport_envelope(
    envelope, expected, consumed_chain_heads(state)
)
requirements = envelope["payload"]
requirements_errors = validate_packet.validate_requirements(
    requirements, previous_requirements
)
```

Build an in-memory pending state with:

- browser binding filled on the first response;
- `pending_requirements_envelope_digest` set to envelope digest;
- `latest_requirements_decision` from the payload;
- active or pending revision provenance matching the validator test helper
  `bind_requirements_transition_context`;
- stop provenance only for `NEED_USER_INPUT` or `BLOCK`.

Build the requirements context with exactly:

```python
{
    "envelope": envelope,
    "expected": expected,
    "consumed_digests": sorted(consumed_chain_heads(state)),
    "requirements": requirements,
    "approval_receipt": None,
}
```

Build the final candidate target from:

```python
REQUIREMENTS_TARGETS = {
    "PLAN_READY": "REQUIREMENTS_FROZEN",
    "NEED_USER_INPUT": "USER_DECISION_REQUIRED",
    "BLOCK": "BLOCKED",
}
```

Consume the envelope digest into `last_consumed_packet_digest`, clear pending
envelope identity, promote active requirements only on `PLAN_READY`, and
validate the pending-to-target transition with the full context. Persist raw,
envelope, immutable revision, active requirements when applicable, and state
last.

- [ ] **Step 5: Implement direct material approval**

Require `REQUIREMENTS_NEED_USER_INPUT`. Derive:

```python
receipt = (
    f"user-approval:stop-{state['stop_sequence']}:"
    f"{state['pending_requirements_digest']}"
)
```

Use the stored immutable proposal, populate resolution evidence and
`resolution_stop_sequence`, promote the pending revision/digest, clear pending
provenance, increment `approval_sequence`, reset review bindings for a material
revision, and validate
`USER_DECISION_REQUIRED -> REQUIREMENTS_FROZEN` with a requirements context
whose `approval_receipt` is the derived receipt.

- [ ] **Step 6: Run requirements, packet, and snapshot suites**

Run all three focused suites. Expected: all pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py evals/gpt-pro-codex-loop/test_gpc_loop.py
git commit -m "feat: accept GPT Pro loop requirements"
```

---

### Task 4: Report Construction and Review Preparation

**Files:**

- Modify: `skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py`
- Modify: `evals/gpt-pro-codex-loop/test_gpc_loop.py`

**Interfaces:**

```python
def build_report(
    repository: Path,
    task_slug: str,
    local_evidence_path: Path,
) -> dict[str, object]
def prepare_review(
    repository: Path,
    task_slug: str,
    supplemental_evidence_path: Path | None = None,
) -> dict[str, object]
```

The local evidence object is closed:

```json
{
  "schema_version": 1,
  "changed_file_intents": {"src/example.py": "Implement AC-1."},
  "intent_summary": "Implement validated behavior.",
  "acceptance_evidence": {"AC-1": ["Focused test passed."]},
  "test_commands": [
    {
      "command": "python -m unittest test_example.py -v",
      "outcome": "PASS",
      "output_summary": "1 test passed."
    }
  ],
  "diff_evidence": ["src/example.py implements the required behavior."],
  "omissions": [],
  "unresolved_risks_or_blockers": []
}
```

- [ ] **Step 1: Write report and review-preparation RED tests**

Add fixture helpers:

```python
def _write_local_evidence(
    self,
    intents: dict[str, str],
    **overrides: object,
) -> Path:
    path = self.repository / "local-evidence.json"
    value = {
        "schema_version": 1,
        "changed_file_intents": intents,
        "intent_summary": "Implement AC-1.",
        "acceptance_evidence": {"AC-1": ["Focused unittest passed."]},
        "test_commands": [
            {
                "command": "python -m unittest test_example.py -v",
                "outcome": "PASS",
                "output_summary": "1 test passed.",
            }
        ],
        "diff_evidence": ["example.py implements AC-1."],
        "omissions": [],
        "unresolved_risks_or_blockers": [],
    }
    value.update(overrides)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _build_valid_report(self, **evidence_overrides: object) -> dict[str, object]:
    self._freeze_initial_requirements()
    (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
    evidence = self._write_local_evidence(
        {"example.py": "Implement AC-1."},
        **evidence_overrides,
    )
    return controller.build_report(
        self.repository, "controller-test", evidence
    )
```

Add tests:

```python
def test_build_report_fills_controller_owned_fields_and_binds_snapshot(self) -> None:
    self._freeze_initial_requirements()
    (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
    evidence = self._write_local_evidence({"example.py": "Implement AC-1."})
    result = controller.build_report(
        self.repository, "controller-test", evidence
    )
    report = controller.load_json(Path(result["report_path"]))
    snapshot = controller.load_json(Path(result["snapshot_path"]))
    self.assertEqual(report["snapshot_digest"], snapshot["snapshot_digest"])
    self.assertEqual(
        report["requirements_digest"],
        self._state()["active_requirements_digest"],
    )
    self.assertEqual(self._state()["phase"], "REVIEW_PENDING")

def test_build_report_rejects_missing_and_extra_changed_path_intents(self) -> None:
    self._freeze_initial_requirements()
    (self.repository / "example.py").write_text("value = 1\n", encoding="utf-8")
    for intents in ({}, {"example.py": "Implement AC-1.", "ghost.py": "extra"}):
        with self.subTest(intents=intents):
            evidence = self._write_local_evidence(intents)
            before = self._state_bytes()
            with self.assertRaisesRegex(controller.ControllerError, "changed_file_intents"):
                controller.build_report(
                    self.repository, "controller-test", evidence
                )
            self.assertEqual(self._state_bytes(), before)

def test_prepare_review_binds_active_requirements_report_and_snapshot(self) -> None:
    self._build_valid_report()
    result = controller.prepare_review(self.repository, "controller-test")
    expected = controller.load_json(Path(result["expected_header_path"]))
    prompt = Path(result["prompt_path"]).read_text(encoding="utf-8")
    self.assertEqual(expected["packet_type"], "review")
    self.assertEqual(
        expected["previous_packet_digest"],
        self._state()["last_consumed_packet_digest"],
    )
    self.assertIn(self._state()["active_requirements_digest"], prompt)
    self.assertEqual(
        controller.status_run(self.repository, "controller-test")["next_commands"],
        ["accept-review", "abandon-attempt"],
    )
```

- [ ] **Step 2: Run report tests and verify RED**

Expected: missing `build_report` and `prepare_review`.

- [ ] **Step 3: Validate local evidence and capture the snapshot**

Reject unknown fields, non-string evidence, forbidden credential/session field
names, missing acceptance IDs, unknown acceptance IDs, and changed-file intent
path mismatch.

Capture:

```python
snapshot = capture_snapshot.capture_snapshot(
    paths.repository,
    state["baseline_head"],
    load_json(paths.preflight),
)
```

Use `snapshot["changed_files"]` paths as the exact required intent set. Replace
only each discovered placeholder intent with the supplied bounded intent.

- [ ] **Step 4: Construct and validate the report**

Controller-owned fields:

```python
report = {
    "schema_version": 1,
    "baseline_head": state["baseline_head"],
    "requirements_revision": state["active_requirements_revision"],
    "requirements_digest": state["active_requirements_digest"],
    "review_round": state["review_round"],
    "snapshot_digest": snapshot["snapshot_digest"],
    "tracked_diff_digest": snapshot["tracked_diff_digest"],
    "untracked_manifest_digest": snapshot["untracked_manifest_digest"],
    "changed_files": changed_files,
    "intent_summary": evidence["intent_summary"],
    "acceptance_evidence": evidence["acceptance_evidence"],
    "test_commands": evidence["test_commands"],
    "diff_evidence": evidence["diff_evidence"],
    "omissions": evidence["omissions"],
    "unresolved_risks_or_blockers": evidence["unresolved_risks_or_blockers"],
}
```

Advance in memory through every legal phase-only edge required by the starting
phase, then set `active_report_digest` and `current_snapshot_digest`. Require
`validate_report_context(report, requirements, candidate, snapshot) == []` and
`validate_transition` for every edge. Persist snapshot, report, events, and
state last.

- [ ] **Step 5: Implement review prompt preparation**

Require a validated active report and snapshot. For ordinary review, render
`Implementation review`. For an evidence-only route, require only
`PROVIDE_EVIDENCE`, recapture and prove the same snapshot, validate
`LOCAL_VERIFICATION -> REVIEW_PENDING`, and render
`Evidence-only supplementation`.

Persist a fresh review expected header and prompt. Do not modify report,
requirements, or snapshot identities during evidence-only preparation.

- [ ] **Step 6: Run focused suites and commit Task 4**

Run controller, packet, and snapshot suites.

Commit:

```powershell
git add skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py evals/gpt-pro-codex-loop/test_gpc_loop.py
git commit -m "feat: build GPT Pro loop review reports"
```

---

### Task 5: Review Acceptance and Final Verification

**Files:**

- Modify: `skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py`
- Modify: `evals/gpt-pro-codex-loop/test_gpc_loop.py`

**Interfaces:**

```python
def accept_review(
    repository: Path,
    task_slug: str,
    raw_response_path: Path,
    observed_conversation_url: str,
    observed_model_label: str,
) -> dict[str, object]
def final_verify(repository: Path, task_slug: str) -> dict[str, object]
```

- [ ] **Step 1: Write review routing and final-gate RED tests**

Add fixture helpers:

```python
def _active_report(self) -> dict[str, object]:
    path = sorted(self._run_dir().glob("implementation-report-*.json"))[-1]
    return controller.load_json(path)


def _valid_pass_review(self) -> dict[str, object]:
    report = self._active_report()
    return {
        "schema_version": 1,
        "requirements_digest": self._state()["active_requirements_digest"],
        "reviewed_snapshot_digest": report["snapshot_digest"],
        "decision": "PASS",
        "acceptance_results": {
            "AC-1": {"status": "PASS", "evidence": "Focused unittest passed."}
        },
        "findings": [],
        "scope_violations": [],
        "next_instruction": "Run final verification.",
    }


def _valid_changes_review(
    self, action: str, category: str, root_cause_key: str
) -> dict[str, object]:
    value = self._valid_pass_review()
    finding = {
        "id": "F-1",
        "acceptance_id": "AC-1",
        "root_cause_key": root_cause_key,
        "severity": "HIGH",
        "category": category,
        "required_action": action,
        "evidence": "The behavior is incomplete.",
        "required_change": "Implement the missing AC-1 behavior.",
    }
    value.update(
        decision="CHANGES_REQUESTED",
        acceptance_results={
            "AC-1": {"status": "FAIL", "evidence": "The behavior is incomplete."}
        },
        findings=[finding],
        next_instruction="Apply the routed correction.",
    )
    return value


def _prepare_valid_review(self, **evidence_overrides: object) -> dict[str, object]:
    self._build_valid_report(**evidence_overrides)
    return controller.prepare_review(self.repository, "controller-test")


def _write_review_response(
    self, attempt: dict[str, object], payload: dict[str, object]
) -> Path:
    expected = controller.load_json(Path(attempt["expected_header_path"]))
    raw = self.repository / "review.raw.md"
    write_raw_envelope(raw, expected, payload)
    return raw


def _accept_pass_review(self, **evidence_overrides: object) -> dict[str, object]:
    attempt = self._prepare_valid_review(**evidence_overrides)
    raw = self._write_review_response(attempt, self._valid_pass_review())
    return controller.accept_review(
        self.repository,
        "controller-test",
        raw,
        self._state()["bound_conversation_url"],
        "Pro",
    )
```

Add tests:

```python
def test_accept_pass_review_consumes_round_and_routes_to_final_verification(self) -> None:
    review_attempt = self._prepare_valid_review()
    raw = self._write_review_response(review_attempt, self._valid_pass_review())
    result = controller.accept_review(
        self.repository,
        "controller-test",
        raw,
        self._state()["bound_conversation_url"],
        "Pro",
    )
    self.assertEqual(result["phase"], "FINAL_VERIFICATION")
    self.assertEqual(result["review_round"], 1)
    self.assertEqual(result["required_actions"], [])

def test_accept_changes_requested_routes_and_derives_fingerprints(self) -> None:
    review_attempt = self._prepare_valid_review()
    review = self._valid_changes_review(
        action="CODE_CHANGE",
        category="CORRECTNESS",
        root_cause_key="missing-empty-input-guard",
    )
    raw = self._write_review_response(review_attempt, review)
    result = controller.accept_review(
        self.repository,
        "controller-test",
        raw,
        self._state()["bound_conversation_url"],
        "Pro",
    )
    self.assertEqual(result["phase"], "IMPLEMENTING")
    self.assertEqual(result["required_actions"], ["CODE_CHANGE"])
    self.assertEqual(len(result["blocker_fingerprints"]), 2)

def test_accept_review_rejects_wrong_current_conversation_and_model(self) -> None:
    review_attempt = self._prepare_valid_review()
    raw = self._write_review_response(review_attempt, self._valid_pass_review())
    before = self._state_bytes()
    for url, label in (
        ("https://chatgpt.com/c/other", "Pro"),
        (self._state()["bound_conversation_url"], "Standard"),
    ):
        with self.subTest(url=url, label=label):
            with self.assertRaises(controller.ControllerError):
                controller.accept_review(
                    self.repository, "controller-test", raw, url, label
                )
            self.assertEqual(self._state_bytes(), before)

def test_final_verify_derives_gate_and_completes_unchanged_snapshot(self) -> None:
    self._accept_pass_review()
    result = controller.final_verify(self.repository, "controller-test")
    self.assertEqual(result["phase"], "COMPLETE")
    gate = controller.load_json(
        self.repository / ".ai-pro-loop" / "controller-test" / "final-gate.json"
    )
    self.assertTrue(all(
        gate[field] is True
        for field in (
            "acceptance_gate_passed",
            "local_checks_passed",
            "scope_gate_passed",
            "artifact_hygiene_passed",
        )
    ))

def test_final_verify_rejects_bound_failed_report_without_state_change(self) -> None:
    self._accept_pass_review(
        test_commands=[
            {
                "command": "python -m unittest test_example.py -v",
                "outcome": "FAIL",
                "output_summary": "1 test failed.",
            }
        ]
    )
    before = self._state_bytes()
    with self.assertRaises(controller.ControllerError):
        controller.final_verify(self.repository, "controller-test")
    self.assertEqual(self._state_bytes(), before)

def test_final_verify_rejects_bound_report_with_omission(self) -> None:
    self._accept_pass_review(omissions=["AC-1 edge case was not exercised."])
    before = self._state_bytes()
    with self.assertRaises(controller.ControllerError):
        controller.final_verify(self.repository, "controller-test")
    self.assertEqual(self._state_bytes(), before)

def test_final_verify_rejects_bound_report_with_blocker(self) -> None:
    self._accept_pass_review(
        unresolved_risks_or_blockers=["Required dependency is unavailable."]
    )
    before = self._state_bytes()
    with self.assertRaises(controller.ControllerError):
        controller.final_verify(self.repository, "controller-test")
    self.assertEqual(self._state_bytes(), before)

def test_pass_with_scope_violation_is_rejected_before_final_gate(self) -> None:
    attempt = self._prepare_valid_review()
    review = self._valid_pass_review()
    review["scope_violations"] = ["example.py changed outside the frozen scope."]
    raw = self._write_review_response(attempt, review)
    before = self._state_bytes()
    with self.assertRaises(controller.ControllerError):
        controller.accept_review(
            self.repository,
            "controller-test",
            raw,
            self._state()["bound_conversation_url"],
            "Pro",
        )
    self.assertEqual(self._state_bytes(), before)

def test_final_verify_rejects_tracked_or_staged_run_metadata(self) -> None:
    self._accept_pass_review()
    subprocess.run(
        [
            "git",
            "add",
            "-f",
            ".ai-pro-loop/controller-test/state.json",
        ],
        cwd=self.repository,
        check=True,
        capture_output=True,
        text=True,
    )
    before = self._state_bytes()
    with self.assertRaises(controller.ControllerError):
        controller.final_verify(self.repository, "controller-test")
    self.assertEqual(self._state_bytes(), before)

def test_final_verify_rejects_product_drift_without_state_change(self) -> None:
    self._accept_pass_review()
    (self.repository / "example.py").write_text("value = 2\n", encoding="utf-8")
    before = self._state_bytes()
    with self.assertRaises(controller.ControllerError):
        controller.final_verify(self.repository, "controller-test")
    self.assertEqual(self._state_bytes(), before)
```

- [ ] **Step 2: Run review/final tests and verify RED**

Expected: missing review acceptance and final verification functions.

- [ ] **Step 3: Implement review validation and deterministic routing**

Validate observed Browser identity, extract and validate the envelope, validate
review semantics, and build:

```python
actions = sorted({
    finding["required_action"]
    for finding in review["findings"]
})
finding_ids = sorted({finding["id"] for finding in review["findings"]})
fingerprints = sorted({
    fingerprint
    for finding in review["findings"]
    for fingerprint in (
        validate_packet.derive_root_cause_fingerprint(finding),
        validate_packet.derive_root_cause_route_fingerprint(finding),
    )
})
```

Use this public controller routing table:

```python
def review_target(decision: str, actions: Sequence[str]) -> str:
    action_set = set(actions)
    if decision == "PASS":
        return "FINAL_VERIFICATION"
    if decision == "BLOCK" or "USER_DECISION" in action_set:
        return "USER_DECISION_REQUIRED"
    if "REQUIREMENTS_REVISION" in action_set:
        return "REQUIREMENTS_PENDING"
    if action_set & {"CODE_CHANGE", "TEST_CHANGE"}:
        return "IMPLEMENTING"
    if action_set == {"PROVIDE_EVIDENCE"}:
        return "LOCAL_VERIFICATION"
    raise ControllerError("INVALID_REVIEW_ROUTE", "Review has no valid route.")
```

The existing validator must independently accept the candidate; the table is
not authoritative.

- [ ] **Step 4: Build and validate staged review state and consumption**

Before routing, construct a complete `REVIEW_PENDING` candidate containing:

- pending envelope digest;
- active review payload digest and reviewed snapshot digest;
- latest decision and actions;
- locally derived finding IDs/fingerprints;
- unchanged active requirements/report/snapshot bindings.

Require `validate_review_context(...) == []`. Then construct the target state,
increment review round exactly once, move the envelope digest to both consumed
review fields, clear pending review identity, set stop provenance where
required, and require `validate_transition(..., review_context=context) == []`.

Persist raw response, envelope, review payload, events, and state last.

- [ ] **Step 5: Implement controller-derived final gate**

Recapture the snapshot. Derive:

```python
gate = {
    "schema_version": 1,
    "requirements_digest": state["active_requirements_digest"],
    "review_packet_digest": state["active_review_packet_digest"],
    "reviewed_snapshot_digest": state["reviewed_snapshot_digest"],
    "current_snapshot_digest": current_snapshot["snapshot_digest"],
    "acceptance_gate_passed": (
        review["decision"] == "PASS"
        and all(
            item["status"] == "PASS"
            for item in review["acceptance_results"].values()
        )
    ),
    "local_checks_passed": (
        bool(report["test_commands"])
        and all(item["outcome"] == "PASS" for item in report["test_commands"])
        and report["omissions"] == []
        and report["unresolved_risks_or_blockers"] == []
    ),
    "scope_gate_passed": review["scope_violations"] == [],
    "artifact_hygiene_passed": metadata_hygiene_is_clean(repository),
}
```

`metadata_hygiene_is_clean` runs read-only Git checks for tracked or staged
`.ai-pro-loop/` paths. It does not modify ignore rules.

Require:

```python
validate_packet.validate_final_gate(gate, state, report, requirements) == []
validate_packet.validate_transition(
    state,
    complete_candidate,
    final_gate_evidence=gate,
    final_gate_report=report,
    final_gate_requirements=requirements,
) == []
```

On failure, leave state unchanged and return a stable error. On success,
persist the fresh snapshot, final gate, completion event, and `COMPLETE` state
last.

- [ ] **Step 6: Add correction-loop integration test**

Create one temporary-repository test that performs:

```text
init
-> prepare/accept requirements
-> build report with one missing behavior
-> prepare/accept CHANGES_REQUESTED(CODE_CHANGE)
-> edit product file and build fresh report
-> prepare/accept PASS
-> final-verify COMPLETE
```

Assert the review round is `2`, the second snapshot differs from the first,
the first review cannot be replayed, and the final gate binds the second
snapshot.

- [ ] **Step 7: Run all controller and existing focused suites**

Run:

```powershell
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_gpc_loop.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_validate_packet.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_capture_snapshot.py" -v
```

- [ ] **Step 8: Commit Task 5**

```powershell
git add skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py evals/gpt-pro-codex-loop/test_gpc_loop.py
git commit -m "feat: complete GPT Pro review controller loop"
```

---

### Task 6: CLI Adapter, Skill Documentation, CI, and Full Verification

**Files:**

- Create: `skills/gpt-pro-codex-loop/scripts/gpc_loop.py`
- Modify: `evals/gpt-pro-codex-loop/test_gpc_loop.py`
- Modify: `skills/gpt-pro-codex-loop/SKILL.md`
- Modify: `skills/gpt-pro-codex-loop/references/packet-contract.md`
- Modify: `skills/gpt-pro-codex-loop/references/prompt-contract.md`
- Modify: `.github/workflows/validate-skills.yml`

**Interfaces:**

```python
def build_parser() -> argparse.ArgumentParser
def main(argv: Sequence[str] | None = None) -> int
```

Commands:

```text
init
prepare-requirements
accept-requirements
approve-requirements
build-report
prepare-review
accept-review
final-verify
status
abandon-attempt
```

- [ ] **Step 1: Write CLI RED tests**

Use subprocess tests against `gpc_loop.py`:

```python
def test_cli_status_prints_one_canonical_json_object(self) -> None:
    self._init_run()
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "gpc_loop.py"),
            "status",
            "--repo",
            str(self.repository),
            "--task",
            "controller-test",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    self.assertEqual(completed.returncode, 0)
    value = json.loads(completed.stdout)
    self.assertEqual(value["ok"], True)
    self.assertEqual(value["command"], "status")
    self.assertEqual(completed.stderr, "")

def test_cli_expected_error_is_json_and_exit_two(self) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "gpc_loop.py"),
            "status",
            "--repo",
            str(self.repository),
            "--task",
            "missing",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    self.assertEqual(completed.returncode, 2)
    error = json.loads(completed.stdout)["error"]
    self.assertEqual(error["code"], "RUN_NOT_FOUND")
    self.assertNotIn("Traceback", completed.stdout)
```

Add parser coverage for every command and required argument, including observed
URL/model on both `accept-*` commands and `NOT_SENT` evidence on
`abandon-attempt`.

- [ ] **Step 2: Implement the thin CLI**

`main()` dispatches to controller functions and emits:

```python
{"ok": True, "command": args.command, "result": result}
```

with canonical JSON and one newline. Map:

- success to exit `0`;
- `ControllerError` to exit `2`;
- unexpected exceptions to `INTERNAL_ERROR` and exit `1`;
- `--debug` traceback to stderr only.

Do not perform domain logic in `gpc_loop.py`.

- [ ] **Step 3: Update the Skill and contracts**

In `SKILL.md`, replace hand-authored normal-loop mechanics with:

```text
Use `scripts/gpc_loop.py` for the normal loop. Run `status` before each
mutation and execute only a command it lists. Use `validate_packet.py` and
`capture_snapshot.py` directly only for documented diagnostic or recovery
paths.
```

In `packet-contract.md`, document every controller command, exact evidence
schema, output envelope, state-last transaction, chain-head consumed history,
observed Browser identity, and `abandon-attempt`.

In `prompt-contract.md`, add stable heading/fence extraction, UTF-8/LF, token
cardinality, structural substitution, and prompt-digest byte rules. Preserve
the actual Pro prompt wording.

- [ ] **Step 4: Add the controller suite to the CI matrix**

Add:

```yaml
      - run: python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_gpc_loop.py" -v
```

to `gpt-pro-loop-evals` after the existing snapshot test command.

- [ ] **Step 5: Validate Skill metadata and documentation**

Run:

```powershell
python scripts/validate-skills.py
python -m unittest discover -s tests -v
```

Verify `agents/openai.yaml` still matches the Skill trigger. Regenerate only if
the trigger/default behavior changed; this controller does not change the
trigger.

- [ ] **Step 6: Run the complete focused matrix locally**

Run:

```powershell
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_gpc_loop.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_validate_packet.py" -v
python -m unittest discover -s evals/gpt-pro-codex-loop -p "test_capture_snapshot.py" -v
python -m py_compile skills/gpt-pro-codex-loop/scripts/gpc_loop.py
python -m py_compile skills/gpt-pro-codex-loop/scripts/gpc_loop_controller.py
git diff --check
```

Expected: every command exits `0`.

- [ ] **Step 7: Forward-test the updated Skill**

Use a fresh subagent with only the updated Skill path and this realistic
request:

```text
Use $gpt-pro-codex-loop at skills/gpt-pro-codex-loop to prepare a new run for
a small local Python repository. Stop before Browser interaction and report
the exact next command and artifact paths.
```

Verify it uses `gpc_loop.py`, does not hand-author state, does not invoke
Browser before the prepared prompt exists, and does not perform Git publication
actions.

- [ ] **Step 8: Request independent code review**

Review the complete branch against:

```text
docs/superpowers/specs/2026-07-31-gpt-pro-codex-loop-controller-design.md
```

Require checks for:

- state-last crash safety;
- chain-head-only consumed history;
- observed Browser identity on every response;
- no project command execution;
- report and final-gate evidence integrity;
- Windows/Linux path behavior;
- controller scope and file size.

Address reproduced findings one at a time and rerun the focused suites after
each fix.

- [ ] **Step 9: Commit Task 6**

```powershell
git add skills/gpt-pro-codex-loop/scripts/gpc_loop.py skills/gpt-pro-codex-loop/SKILL.md skills/gpt-pro-codex-loop/references/packet-contract.md skills/gpt-pro-codex-loop/references/prompt-contract.md evals/gpt-pro-codex-loop/test_gpc_loop.py .github/workflows/validate-skills.yml
git commit -m "docs: adopt GPT Pro loop controller workflow"
```

- [ ] **Step 10: Final verification before publication handoff**

Run:

```powershell
git status --short
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

Expected:

- no uncommitted implementation changes;
- the design and plan commits plus six bounded implementation commits;
- no `.ai-pro-loop/` artifact staged or tracked;
- no push, pull request, merge, or deployment performed without separate user
  authorization.
