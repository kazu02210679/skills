# Review Implementation HTML Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable `review-implementation-html` skill that performs plan-blind and plan-aware review passes and renders a local, commentable static review report.

**Architecture:** A standard-library collector captures bounded Git evidence and redacts likely secrets. The agent performs two isolated review passes and writes normalized `review-data.json`; a validator enforces review integrity and a renderer produces a self-contained HTML report with local comments, export, and correction-prompt copy.

**Tech Stack:** Markdown Agent Skill format, Python 3 standard library, Git CLI, vanilla HTML/CSS/JavaScript, `localStorage`, `unittest`.

## Global Constraints

- Create the skill under `skills/review-implementation-html/`.
- Use only Python's standard library in bundled scripts and tests.
- Write reports only to `docs/reviews/<plan-slug>/`.
- Keep product code read-only and never stage, commit, push, publish, deploy, or automatically fix findings.
- Keep plan content hidden from the first review pass.
- Group diffs by intent and sort groups by highest risk, not file order.
- Escape all diff, plan, test, and finding text.
- Keep review reports local by default and warn before publication.
- Keep `SKILL.md` under 500 lines and move the full schema to `references/review-model.md`.

---

### Task 1: Initialize the skill and collect bounded Git context

**Files:**
- Create: `skills/review-implementation-html/SKILL.md`
- Create: `skills/review-implementation-html/agents/openai.yaml`
- Create: `skills/review-implementation-html/scripts/collect_review_context.py`
- Create: `evals/review-implementation-html/fixtures/sample.diff`
- Create: `evals/review-implementation-html/test_collect_review_context.py`

**Interfaces:**
- Produces: `redact_text(text: str) -> tuple[str, list[str]]`
- Produces: `collect_context(repo: pathlib.Path, base: str, head: str, max_bytes: int) -> dict`
- Produces CLI: `python collect_review_context.py --repo <path> --base <ref> --head <ref-or-WORKTREE> --output <json> [--max-bytes 500000]`
- Context keys: `repository`, `base`, `head`, `changed_files`, `diff`, `truncated`, `redactions`, and `generated_at`.

- [ ] **Step 1: Initialize the skill scaffold**

Run:

```powershell
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\init_skill.py review-implementation-html `
  --path skills `
  --resources scripts,references,assets `
  --interface display_name="Review Implementation HTML" `
  --interface short_description="Create an explained interactive implementation review" `
  --interface default_prompt="Use $review-implementation-html to review this implementation in two passes and create a local commentable HTML report."
```

- [ ] **Step 2: Write failing collector tests**

```python
class ReviewContextTests(unittest.TestCase):
    def test_redacts_common_secret_assignments(self):
        redacted, labels = MODULE.redact_text("API_KEY=sk-secretvalue123456")
        self.assertNotIn("secretvalue", redacted)
        self.assertIn("[REDACTED]", redacted)
        self.assertIn("API_KEY", labels)

    def test_rejects_non_git_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Git repository"):
                MODULE.collect_context(pathlib.Path(directory), "HEAD~1", "WORKTREE", 1000)
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
python -m unittest evals.review-implementation-html.test_collect_review_context -v
```

Expected: FAIL because collector functions do not exist.

- [ ] **Step 4: Implement collector and redaction**

Use `subprocess.run` with argument arrays and `shell=False`. Resolve repository root with `git rev-parse --show-toplevel`. Collect `git diff --name-status`, `git diff --unified=40`, and revision metadata. Support `WORKTREE` as the unstaged/staged worktree against `base`; otherwise compare `base...head`. Enforce `max_bytes`, preserve whole lines, set `truncated`, and redact common token/password/private-key assignment patterns.

- [ ] **Step 5: Run collector tests**

Run:

```powershell
python -m unittest evals.review-implementation-html.test_collect_review_context -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit context collection**

```powershell
git add skills/review-implementation-html evals/review-implementation-html
git commit -m "feat: collect review context"
```

### Task 2: Implement the review-data validator

**Files:**
- Create: `skills/review-implementation-html/scripts/validate_review_report.py`
- Create: `evals/review-implementation-html/fixtures/valid-review.json`
- Create: `evals/review-implementation-html/fixtures/invalid-review.json`
- Create: `evals/review-implementation-html/test_validate_review_report.py`

**Interfaces:**
- Produces: `validate_document(document: dict) -> list[str]`
- Produces CLI: `python validate_review_report.py <review-data.json> [--html <index.html>]`
- Valid pass values: `plan-blind`, `plan-aware`
- Valid severities: `blocking`, `high`, `medium`, `low`, `note`

- [ ] **Step 1: Add valid and invalid review fixtures**

The valid fixture contains one intent group, one diff hunk, one plan-blind finding, one plan-aware finding, verification evidence, coverage summary, and result. The invalid fixture assigns the same hunk to two groups and omits recommended action from a high finding.

- [ ] **Step 2: Write failing validation tests**

```python
class ReviewValidationTests(unittest.TestCase):
    def test_valid_review_has_no_errors(self):
        self.assertEqual(MODULE.validate_document(self.load("valid-review.json")), [])

    def test_high_finding_requires_action(self):
        errors = MODULE.validate_document(self.load("invalid-review.json"))
        self.assertTrue(any("recommended_action" in error for error in errors))

    def test_each_hunk_has_exactly_one_group(self):
        errors = MODULE.validate_document(self.load("invalid-review.json"))
        self.assertTrue(any("exactly one intent group" in error for error in errors))
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```powershell
python -m unittest evals.review-implementation-html.test_validate_review_report -v
```

Expected: FAIL because validation is not implemented.

- [ ] **Step 4: Implement validation**

Validate required metadata, unique IDs, group risk ordering, hunk ownership, changed-file references, finding pass/severity/status, evidence/impact/action for blocking and high findings, verification result values, coverage fields, and overall result. Add optional HTML markers for comments, export, correction prompt, clipboard fallback, and embedded review data.

- [ ] **Step 5: Run validator tests**

Run:

```powershell
python -m unittest evals.review-implementation-html.test_validate_review_report -v
python skills/review-implementation-html/scripts/validate_review_report.py evals/review-implementation-html/fixtures/valid-review.json
```

Expected: tests PASS and CLI reports a valid review.

- [ ] **Step 6: Commit review validation**

```powershell
git add skills/review-implementation-html evals/review-implementation-html
git commit -m "feat: validate implementation reviews"
```

### Task 3: Build the interactive static review report

**Files:**
- Create: `skills/review-implementation-html/scripts/build_review_html.py`
- Create: `skills/review-implementation-html/assets/review-template.html`
- Create: `evals/review-implementation-html/test_build_review_html.py`

**Interfaces:**
- Produces: `safe_json_for_script(document: dict) -> str`
- Produces: `render_html(document: dict, template: str) -> str`
- Produces CLI: `python build_review_html.py --data <json> --template <html> --output <index.html>`
- Template token: `{{REVIEW_DATA_JSON}}`.

- [ ] **Step 1: Write failing renderer tests**

```python
class ReviewHtmlBuildTests(unittest.TestCase):
    def test_script_json_escapes_html_terminators(self):
        payload = MODULE.safe_json_for_script({"text": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script>", payload.lower())
        self.assertIn("\\u003c", payload)

    def test_render_contains_comment_and_export_controls(self):
        rendered = MODULE.render_html(self.valid_review(), TEMPLATE.read_text(encoding="utf-8"))
        for marker in ('id="reviewNav"', 'data-comment-id', 'id="exportComments"', 'id="copyCorrectionPrompt"'):
            self.assertIn(marker, rendered)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m unittest evals.review-implementation-html.test_build_review_html -v
```

Expected: FAIL because the renderer and template do not exist.

- [ ] **Step 3: Implement safe JSON embedding and CLI**

Serialize with `ensure_ascii=False`, compact separators, and replacements for `<`, `>`, `&`, U+2028, and U+2029. Validate before rendering. Create parent directories, write UTF-8 output, and refuse invalid input.

- [ ] **Step 4: Implement the review template**

Create a responsive dark UI with:

- summary/result header;
- sticky risk-ordered intent navigation on desktop and normal-flow navigation on mobile;
- expandable explained diff hunks;
- badges for severity and review pass;
- verification and coverage sections;
- textareas keyed by stable group/finding IDs;
- `localStorage` key derived from repository and plan slug;
- JSON comment export;
- correction-prompt generation from open findings and non-empty comments;
- Clipboard API plus visible manual-copy fallback;
- no network calls.

- [ ] **Step 5: Run build and validation tests**

Run:

```powershell
python -m unittest evals.review-implementation-html.test_build_review_html -v
python skills/review-implementation-html/scripts/build_review_html.py `
  --data evals/review-implementation-html/fixtures/valid-review.json `
  --template skills/review-implementation-html/assets/review-template.html `
  --output evals/review-implementation-html/generated-review/index.html
python skills/review-implementation-html/scripts/validate_review_report.py `
  evals/review-implementation-html/fixtures/valid-review.json `
  --html evals/review-implementation-html/generated-review/index.html
```

Expected: tests PASS and HTML validates.

- [ ] **Step 6: Commit the review UI**

```powershell
git add skills/review-implementation-html evals/review-implementation-html
git commit -m "feat: render interactive review reports"
```

### Task 4: Write the review workflow and regression cases

**Files:**
- Modify: `skills/review-implementation-html/SKILL.md`
- Modify: `skills/review-implementation-html/agents/openai.yaml`
- Create: `skills/review-implementation-html/references/review-model.md`
- Create: `evals/review-implementation-html/cases.json`

**Interfaces:**
- `SKILL.md` defines collection, isolated review passes, intent grouping, risk ordering, output generation, browser verification, and privacy constraints.
- `cases.json` defines prompts and machine-checkable expected behaviors.

- [ ] **Step 1: Write `review-model.md`**

Document exact context and review-data schemas, severity definitions, result rules, intent-group ordering, hunk ownership, redaction behavior, and a compact complete JSON example.

- [ ] **Step 2: Replace scaffold instructions in `SKILL.md`**

Use imperative steps:

1. locate the approved plan and determine base/head;
2. collect bounded Git evidence;
3. stop on empty diff;
4. run a plan-blind read-only review;
5. run a plan-aware review;
6. retain unresolved first-pass findings;
7. group by intent and risk;
8. write `review-data.json`;
9. validate and render `docs/reviews/<plan-slug>/index.html`;
10. browser-test comments, persistence, export, copy fallback, desktop/mobile layout, and console state;
11. report the local artifact without publishing it.

Explicitly require confirmation for plan-blind-only output when no plan exists.

- [ ] **Step 3: Regenerate UI metadata**

Run:

```powershell
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\generate_openai_yaml.py `
  skills/review-implementation-html `
  --interface display_name="Review Implementation HTML" `
  --interface short_description="Create an explained interactive implementation review" `
  --interface default_prompt="Use $review-implementation-html to review this implementation in two passes and create a local commentable HTML report."
```

- [ ] **Step 4: Add regression cases**

Add cases for grouping a cross-file rename, ranking a security change first, retaining a plan-blind bug, finding a missing plan requirement, recording missing tests as `not run`, and rejecting an empty diff.

- [ ] **Step 5: Run final skill and unit validation**

Run:

```powershell
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/review-implementation-html
python -m unittest discover -s evals/review-implementation-html -p "test_*.py" -v
```

Expected: skill validation and all tests PASS.

- [ ] **Step 6: Browser smoke-test the report**

Open `generated-review/index.html`, enter comments, reload and confirm persistence, export comment JSON, invoke correction-prompt copy, test the manual fallback, check desktop/mobile layout, and confirm no console errors or network requests.

- [ ] **Step 7: Commit the completed skill**

```powershell
git add skills/review-implementation-html evals/review-implementation-html
git commit -m "feat: add implementation review html skill"
```

### Task 5: Integrate repository-level validation and push

**Files:**
- Modify only if needed: `README.md`
- Validate: all files under `skills/` and `evals/`

**Interfaces:**
- Repository contains two independently installable skill folders and their regression suites.

- [ ] **Step 1: Run both skill validators and all tests**

```powershell
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/create-project-map
python C:\Users\楫屋寿弥\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/review-implementation-html
python -m unittest discover -s evals/create-project-map -p "test_*.py" -v
python -m unittest discover -s evals/review-implementation-html -p "test_*.py" -v
git diff --check
```

Expected: all validations and tests PASS with no whitespace errors.

- [ ] **Step 2: Confirm clean, scoped diff**

Run:

```powershell
git status -sb
git diff --stat HEAD~4..HEAD
```

Expected: only the two skill folders, their evals, and the approved design/plan documents are present.

- [ ] **Step 3: Push the feature branch**

Run:

```powershell
git push -u origin feat-project-map-review-skills
```

Expected: remote branch tracks `origin/feat-project-map-review-skills`.

