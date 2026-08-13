# Skill Portfolio Core and Public Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic Skill Portfolio core, read-only dashboard, and public Cloudflare Workers Static Assets deployment for the `skills` repository.

**Architecture:** Repository, local Git, GitHub, and registered external sources are normalized into observations; closed inference rules derive `Placement`, `Development Stage`, `Readiness`, `Activity`, `Freshness`, attention, and next action. The generated `portfolio.json` and HTML are ephemeral projections, never the source of truth. Public deployment builds only from public sources and fails closed on privacy violations before publishing to a dedicated Cloudflare Worker.

**Tech Stack:** Python 3.12 standard library, PyYAML 6.0.3, vanilla HTML/CSS/JavaScript, GitHub REST API, GitHub Actions, Cloudflare Workers Static Assets, `cloudflare/wrangler-action@v4` / Wrangler v4.

## Global Constraints

- Treat `docs/superpowers/specs/2026-08-14-skill-portfolio-dashboard-design.md` and `docs/superpowers/specs/2026-08-14-skill-portfolio-dashboard-cloudflare-amendment.md` as the approved requirements.
- v1 is read-only. Do not add Skill execution, install/uninstall, PR creation, merge, HOTL transitions, external upgrades, or agent controls.
- `MAIN` means placement only; it never implies completion.
- `hotl-governance` must render as `MAIN / UNDER_DEVELOPMENT / LIMITED` while the accepted core-completion limitation remains active.
- Current work is `Activity`; product maturity is `Development Stage`. Do not collapse them.
- Never derive state from LLM semantic judgment. Inference consumes closed enums, typed observations, explicit configuration, and current Git/GitHub facts.
- Main canonical Skills are discovered from `skills/*/SKILL.md`; do not enumerate them in portfolio configuration.
- Generated output lives under `.skill-portfolio/` or CI temporary directories and is not committed.
- Public mode must not initialize or read private-source collectors.
- A public privacy violation is fatal; do not redact and continue.
- External-source failure degrades observation freshness, not the underlying Skill state.
- Do not add a database, persistent backend, React/Vite, or Graph DB.
- Keep the dashboard dependency-free at runtime. Do not load JavaScript or CSS from a third-party CDN; use vanilla JS/SVG for the relationship view.
- Cloudflare uses Workers Static Assets with a dedicated public Worker. Static asset paths are relative to the Wrangler configuration file. citeturn831396search0turn831396search5
- Pin the GitHub Action major to `cloudflare/wrangler-action@v4`; the action defaults to Wrangler v4. citeturn518153search0turn518153search1
- Preserve existing validation and context-budget behavior.
- Apply TDD. Each task adds only focused witnesses needed for its acceptance surface.

---

## File Structure

### New public repository files

```text
skills/skill-portfolio/
  SKILL.md                         # user-facing trigger and read-only workflow
  README.md                        # concise human-facing usage and data-source contract
  agents/openai.yaml               # Codex UI metadata
  assets/portfolio-template.html   # dependency-free dark dashboard shell

scripts/build-skill-portfolio.py   # thin CLI/orchestration entry point
scripts/skill_portfolio/
  __init__.py
  model.py                         # enums, typed dict helpers, normalization primitives
  config.py                        # YAML loading and closed configuration validation
  collectors/
    __init__.py
    repository.py                  # canonical Skill/design/plan discovery
    local.py                       # bounded current-worktree observations
    github.py                      # GitHub REST observations
    external.py                    # registered public external GitHub sources
  infer.py                         # deterministic state/attention/next-action rules
  privacy.py                       # public projection privacy guard
  validate.py                      # projection/relation/config contract validation
  render.py                        # JSON + HTML rendering

schemas/skill-portfolio.schema.json
portfolio-intents.yaml
portfolio-external.yaml
cloudflare/public/wrangler.jsonc
.github/workflows/deploy-skill-portfolio-public.yml

tests/test_skill_portfolio.py      # table-driven core/discovery/inference/privacy/renderer tests
```

### Modified public repository files

```text
.gitignore
README.md
.github/workflows/validate-skills.yml
requirements-validation.txt        # no new dependency expected; retain PyYAML==6.0.3
```

### Generated files, ignored

```text
.skill-portfolio/public/
  portfolio.json
  index.html
.skill-portfolio/cache/
  public-observations.json
```

---

### Task 1: Define the closed data and configuration contracts

**Files:**
- Create: `scripts/skill_portfolio/__init__.py`
- Create: `scripts/skill_portfolio/model.py`
- Create: `scripts/skill_portfolio/config.py`
- Create: `schemas/skill-portfolio.schema.json`
- Create: `portfolio-intents.yaml`
- Create: `portfolio-external.yaml`
- Create: `tests/test_skill_portfolio.py`

**Interfaces:**
- Produces: `Placement`, `DevelopmentStage`, `Readiness`, `Activity`, `Freshness`, `AttentionLevel`, `RelationshipType` string enums.
- Produces: `load_public_config(repo: pathlib.Path) -> dict[str, Any]`.
- Produces: `validate_public_config(config: dict[str, Any], repo: pathlib.Path) -> list[str]`.
- Later tasks consume these exact enum values and config shape.

- [ ] **Step 1: Write the failing contract tests**

Add `SkillPortfolioContractTests` to `tests/test_skill_portfolio.py` with exact enum assertions and a HOTL limitation fixture:

```python
from pathlib import Path
import tempfile
import unittest

from scripts.skill_portfolio.model import (
    Activity,
    DevelopmentStage,
    Placement,
    Readiness,
)
from scripts.skill_portfolio.config import load_public_config, validate_public_config


class SkillPortfolioContractTests(unittest.TestCase):
    def test_state_enums_are_closed(self):
        self.assertEqual({item.value for item in Placement}, {
            "MAIN", "PRIVATE", "EXTERNAL", "LOCAL_ONLY", "NONE", "LEGACY"
        })
        self.assertIn("UNDER_DEVELOPMENT", {item.value for item in DevelopmentStage})
        self.assertEqual({item.value for item in Readiness}, {
            "READY", "LIMITED", "DEGRADED", "UNKNOWN"
        })
        self.assertEqual({item.value for item in Activity}, {
            "IDLE", "ACTIVE_LOCAL", "PR_OPEN", "REVIEW_OPEN", "MERGE_READY", "BLOCKED"
        })

    def test_hotl_limitation_requires_machine_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "portfolio-intents.yaml").write_text(
                """version: 1\naccepted_limitations:\n  hotl-governance:\n"
                "    - id: authority-provider-unavailable\n"
                "      scope: core_completion\n"
                "      effect: production_completion_unavailable\n"
                "      evidence:\n"
                "        path: skills/hotl-governance/README.md\n"
                "        contains: caller-independent host/CI provenance provider\n""",
                encoding="utf-8",
            )
            (repo / "portfolio-external.yaml").write_text("version: 1\nexternal: {}\n", encoding="utf-8")
            config = load_public_config(repo)
            self.assertTrue(validate_public_config(config, repo))
```

Change the second assertion after implementation so the missing evidence is reported exactly as `STALE_EXCEPTION: hotl-governance/authority-provider-unavailable`.

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioContractTests -v
```

Expected: import failure because `scripts.skill_portfolio.model` and `config` do not exist.

- [ ] **Step 3: Implement the enum and config primitives**

Create `model.py` with `str, Enum` classes:

```python
from enum import Enum


class Placement(str, Enum):
    MAIN = "MAIN"
    PRIVATE = "PRIVATE"
    EXTERNAL = "EXTERNAL"
    LOCAL_ONLY = "LOCAL_ONLY"
    NONE = "NONE"
    LEGACY = "LEGACY"


class DevelopmentStage(str, Enum):
    DISCOVERED = "DISCOVERED"
    DESIGNING = "DESIGNING"
    PLANNED = "PLANNED"
    IMPLEMENTING = "IMPLEMENTING"
    UNDER_DEVELOPMENT = "UNDER_DEVELOPMENT"
    STABLE = "STABLE"
    DEFERRED = "DEFERRED"
    RETIRED = "RETIRED"


class Readiness(str, Enum):
    READY = "READY"
    LIMITED = "LIMITED"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class Activity(str, Enum):
    IDLE = "IDLE"
    ACTIVE_LOCAL = "ACTIVE_LOCAL"
    PR_OPEN = "PR_OPEN"
    REVIEW_OPEN = "REVIEW_OPEN"
    MERGE_READY = "MERGE_READY"
    BLOCKED = "BLOCKED"


class Freshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class AttentionLevel(str, Enum):
    NONE = "NONE"
    OPPORTUNITY = "OPPORTUNITY"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    CRITICAL = "CRITICAL"


class RelationshipType(str, Enum):
    REQUIRES = "requires"
    USES = "uses"
    FEEDS_INTO = "feeds_into"
    GOVERNS = "governs"
    OBSERVES = "observes"
    REVIEWS = "reviews"
    REPLACES = "replaces"
    MIGRATED_TO = "migrated_to"
    CONFLICTS_WITH = "conflicts_with"
    ROUTES_TO = "routes_to"
```

Implement `config.py` using `yaml.safe_load`. Reject unknown top-level keys; validate evidence paths relative to the repository; for `accepted_limitations[*].evidence.contains`, require the exact substring to be present. Return `STALE_EXCEPTION: <item>/<id>` when it is not.

- [ ] **Step 4: Add initial configuration**

`portfolio-intents.yaml` must contain only intent/exception data, not canonical Skill listings:

```yaml
version: 1
tracking:
  candidates:
    - obsidian-secretary-opt
intent:
  obsidian-secretary-opt:
    priority: P1
accepted_limitations:
  hotl-governance:
    - id: authority-provider-unavailable
      scope: core_completion
      effect: production_completion_unavailable
      evidence:
        path: skills/hotl-governance/README.md
        contains: caller-independent host/CI provenance provider
```

`portfolio-external.yaml` starts with public external items that have a stable public source:

```yaml
version: 1
external:
  ponytail:
    kind: external_skill
    source_type: github
    source: DietrichGebert/ponytail
  caveman:
    kind: external_skill
    source_type: github
    source: juliusbrussee/caveman
  find-skills:
    kind: external_skill
    source_type: github_path
    source: vercel-labs/skills
    path: skills/find-skills/SKILL.md
  sol-advisor:
    kind: runtime
    source_type: registered_identity
    source: sol-advisor
```

`registered_identity` is displayable but has no remote freshness/version claim; it resolves to `EXTERNAL / UNKNOWN / UNAVAILABLE` until a trusted observer is available.

- [ ] **Step 5: Write `schemas/skill-portfolio.schema.json` and cross-check constants**

Use JSON Schema draft 2020-12 as a machine-readable contract. Include closed enums matching `model.py`, require `items`, `observations`, `rule_results`, `relationships`, and forbid unknown top-level fields with `additionalProperties: false`.

Add a test that loads the schema JSON and compares each enum array with the Python enum set. Do not add the `jsonschema` package; runtime validation remains in `validate.py` in Task 4.

- [ ] **Step 6: Run tests and repository validation**

Run:

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioContractTests -v
python scripts/validate-skills.py
```

Expected: PASS; canonical Skill count remains unchanged because `skill-portfolio` Skill is not added until Task 5.

- [ ] **Step 7: Commit**

```bash
git add scripts/skill_portfolio schemas/skill-portfolio.schema.json portfolio-intents.yaml portfolio-external.yaml tests/test_skill_portfolio.py
git commit -m "feat: define skill portfolio contracts"
```

---

### Task 2: Discover repository and local portfolio evidence

**Files:**
- Create: `scripts/skill_portfolio/collectors/__init__.py`
- Create: `scripts/skill_portfolio/collectors/repository.py`
- Create: `scripts/skill_portfolio/collectors/local.py`
- Modify: `tests/test_skill_portfolio.py`

**Interfaces:**
- Produces: `collect_repository(repo: Path, config: dict[str, Any]) -> list[dict[str, Any]]`.
- Produces: `collect_local(repo: Path, known_ids: set[str]) -> list[dict[str, Any]]`.
- Each observation has exactly: `item_id`, `kind`, `source`, `status`, `ref`, `observed_at`, `details`.
- Later inference consumes only normalized observations, never raw subprocess output.

- [ ] **Step 1: Add RED discovery fixtures**

Use temporary repositories with representative files. Tests must cover:

```python
class RepositoryCollectorTests(unittest.TestCase):
    def test_discovers_canonical_skill_without_manual_registration(self): ...
    def test_discovers_design_and_plan_candidate(self): ...
    def test_local_skill_artifact_becomes_local_observation(self): ...
    def test_branch_name_alone_is_not_active_local_evidence(self): ...
```

For the canonical fixture create `skills/sample/SKILL.md` and `README.md`; for plan/design create files under `docs/superpowers/specs/` and `docs/superpowers/plans/` containing the explicit token `` `sample-next` `` and phrase `Skill`.

- [ ] **Step 2: Confirm RED**

Run:

```bash
python -m unittest tests.test_skill_portfolio.RepositoryCollectorTests -v
```

Expected: import failure for collectors.

- [ ] **Step 3: Implement canonical/discovery collection**

`repository.py` must:

1. scan only direct `skills/*/SKILL.md` canonical directories;
2. parse frontmatter with the same `name` / `description` constraints as the catalog;
3. emit presence observations for README, agents metadata, scripts, references, and `evals/<id>/`;
4. scan `docs/superpowers/specs/*design.md` and `docs/superpowers/plans/*.md` for explicit tracked candidate IDs;
5. keep ambiguous non-tracked documents as `candidate_discovered`, never as an official item.

Do not infer architecture from filenames alone.

- [ ] **Step 4: Implement bounded local Git collection**

`local.py` uses:

```bash
git status --porcelain=v1 -z --untracked-files=all
```

Parse NUL-delimited records. Emit `local_changed_path` only for paths under:

```text
skills/<id>/
evals/<id>/
docs/superpowers/specs/
docs/superpowers/plans/
portfolio-*.yaml
```

A remote/local branch name without a changed relevant artifact does not emit `active_local`.

- [ ] **Step 5: Run discovery tests**

```bash
python -m unittest tests.test_skill_portfolio.RepositoryCollectorTests -v
```

Expected: PASS.

- [ ] **Step 6: Run a real-repository smoke**

Add a test using the checked-out repository root asserting that every current direct `skills/*/SKILL.md` directory appears once. Derive the expected set from the filesystem in the test; do not hard-code `13`.

Run:

```bash
python -m unittest tests.test_skill_portfolio.RepositoryCollectorTests.test_real_repo_discovers_every_canonical_skill -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/skill_portfolio/collectors tests/test_skill_portfolio.py
git commit -m "feat: discover portfolio repository evidence"
```

---

### Task 3: Collect GitHub and public external observations

**Files:**
- Create: `scripts/skill_portfolio/collectors/github.py`
- Create: `scripts/skill_portfolio/collectors/external.py`
- Modify: `tests/test_skill_portfolio.py`

**Interfaces:**
- Produces: `GitHubClient(api_base: str, token: str | None, opener: Callable)`.
- Produces: `collect_github(repo_slug: str, item_ids: set[str], client: GitHubClient) -> list[dict[str, Any]]`.
- Produces: `collect_external(config: dict[str, Any], client: GitHubClient) -> list[dict[str, Any]]`.
- GitHub observation binding uses PR head SHA / main SHA; a PASS on a different SHA is never current evidence.

- [ ] **Step 1: Write fake-transport GitHub tests**

Create an in-memory `FakeOpener` that maps URLs to JSON + headers. Cover:

```python
class GitHubCollectorTests(unittest.TestCase):
    def test_pr_maps_by_changed_path_before_title(self): ...
    def test_ci_pass_on_old_sha_is_stale_not_current(self): ...
    def test_external_failure_returns_unavailable_freshness(self): ...
    def test_registered_identity_never_claims_remote_version(self): ...
```

The PR mapping fixture must include `skills/hotl-governance/SKILL.md` in changed files and a misleading title referring to another Skill; expected item is still `hotl-governance`.

- [ ] **Step 2: Confirm RED**

```bash
python -m unittest tests.test_skill_portfolio.GitHubCollectorTests -v
```

Expected: import failure.

- [ ] **Step 3: Implement the stdlib GitHub REST client**

Use `urllib.request.Request` and `json.loads`; token header is optional:

```python
headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "skill-portfolio/1",
}
if token:
    headers["Authorization"] = f"Bearer {token}"
```

Support pagination from the HTTP `Link` header. Never print token-bearing headers.

- [ ] **Step 4: Implement PR/check observations**

For each open PR, fetch changed file names. Associate by this precedence:

1. `skills/<id>/` or `evals/<id>/` changed path;
2. explicit item metadata if later introduced;
3. branch-name token;
4. title/body token.

Emit `pr_open`, `review_state`, `check_state`, `head_sha`, `base_sha`. Keep the raw GitHub payload out of `portfolio.json`.

- [ ] **Step 5: Implement external GitHub source observation**

For `source_type: github`, fetch repository default branch and current commit SHA. For `github_path`, also fetch the configured path at that ref and record its blob SHA. On HTTP/network/rate-limit failure, emit `Freshness: UNAVAILABLE` observation and retain the item.

- [ ] **Step 6: Run focused tests**

```bash
python -m unittest tests.test_skill_portfolio.GitHubCollectorTests -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/skill_portfolio/collectors/github.py scripts/skill_portfolio/collectors/external.py tests/test_skill_portfolio.py
git commit -m "feat: collect GitHub portfolio evidence"
```

---

### Task 4: Implement deterministic inference, privacy, and projection validation

**Files:**
- Create: `scripts/skill_portfolio/infer.py`
- Create: `scripts/skill_portfolio/privacy.py`
- Create: `scripts/skill_portfolio/validate.py`
- Modify: `tests/test_skill_portfolio.py`

**Interfaces:**
- Produces: `infer_item(item_id: str, observations: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]`.
- Produces: `build_projection(observations: list[dict[str, Any]], config: dict[str, Any], mode: str, generated_at: str) -> dict[str, Any]`.
- Produces: `validate_projection(document: dict[str, Any]) -> list[str]`.
- Produces: `find_public_privacy_violations(document: dict[str, Any]) -> list[str]`.

- [ ] **Step 1: Add table-driven inference RED tests**

Use one table in `SkillPortfolioInferenceTests`:

```python
cases = [
    ("main-ready", obs_main_ready(), ("MAIN", "STABLE", "READY", "IDLE")),
    ("hotl-limited", obs_hotl_ready(), ("MAIN", "UNDER_DEVELOPMENT", "LIMITED", "IDLE")),
    ("main-failing-pr", obs_main_failing_pr(), ("MAIN", "STABLE", "READY", "BLOCKED")),
    ("plan-only", obs_plan_only(), ("NONE", "PLANNED", "UNKNOWN", "IDLE")),
    ("local-impl", obs_local_impl(), ("LOCAL_ONLY", "IMPLEMENTING", "UNKNOWN", "ACTIVE_LOCAL")),
]
```

Also add privacy cases for:

- `C:\Users\Name\secret`
- `/home/name/private`
- a configured private repository identifier
- a token-like string `ghp_` + 36 characters
- a 17+ digit Discord-like numeric ID
- `api.github.com/repos/<private-owner>/<private-repo>`

- [ ] **Step 2: Confirm RED**

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioInferenceTests -v
```

Expected: import failure.

- [ ] **Step 3: Implement precedence rules exactly**

In `infer.py`, keep each axis in a separate pure function:

```python
def infer_placement(observations, config): ...
def infer_development_stage(observations, config, placement): ...
def infer_readiness(observations, config, placement, stage): ...
def infer_activity(observations): ...
def infer_freshness(observations): ...
def infer_attention(stage, readiness, activity, rule_results): ...
def infer_next_action(stage, readiness, activity, config): ...
```

No function may inspect README prose directly; collectors/config validation convert prose-bound accepted limitations into typed observations before inference.

HOTL rule: an active `accepted_limitation` with `scope == "core_completion"` and official placement yields `UNDER_DEVELOPMENT`; the same limitation yields `LIMITED` readiness, not `DEGRADED`.

- [ ] **Step 4: Implement privacy fail-closed checks**

`privacy.py` recursively visits all string values and refs in the public projection. Return stable codes such as:

```text
ABSOLUTE_WINDOWS_PATH
ABSOLUTE_POSIX_PATH
PRIVATE_REPOSITORY_IDENTIFIER
TOKEN_LIKE_VALUE
DISCORD_ID_LIKE_VALUE
PRIVATE_GITHUB_API_REF
```

Do not mutate/redact the document.

- [ ] **Step 5: Implement closed projection validation**

`validate.py` verifies:

- required top-level keys;
- enum membership;
- unique item IDs;
- every relationship source/target exists, except an explicit unavailable external stub;
- observations reference known item IDs;
- rule results reference known item IDs;
- Public projection contains no `PRIVATE` source details;
- schema enum arrays and Python enum values remain identical.

- [ ] **Step 6: Run inference/privacy tests**

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioInferenceTests -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/skill_portfolio/infer.py scripts/skill_portfolio/privacy.py scripts/skill_portfolio/validate.py tests/test_skill_portfolio.py
git commit -m "feat: infer skill portfolio state"
```

---

### Task 5: Render the dashboard and expose the `skill-portfolio` Skill

**Files:**
- Create: `skills/skill-portfolio/SKILL.md`
- Create: `skills/skill-portfolio/README.md`
- Create: `skills/skill-portfolio/agents/openai.yaml`
- Create: `skills/skill-portfolio/assets/portfolio-template.html`
- Create: `scripts/skill_portfolio/render.py`
- Create: `scripts/build-skill-portfolio.py`
- Modify: `tests/test_skill_portfolio.py`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- CLI:

```text
python scripts/build-skill-portfolio.py \
  --repo <repo> \
  --mode public|private \
  --output <directory> \
  [--private-config <path>] \
  [--github-token-env GITHUB_TOKEN]
```

- Public mode never imports/calls a private collector.
- `render_dashboard(document: dict[str, Any], template: str, data_filename: str) -> str`.

- [ ] **Step 1: Add renderer/CLI RED tests**

Tests must assert:

```python
class SkillPortfolioRendererTests(unittest.TestCase):
    def test_hotl_badges_render_under_development_and_limited(self): ...
    def test_attention_queue_and_inventory_are_present(self): ...
    def test_relationship_targets_are_clickable_in_detail_panel(self): ...
    def test_public_mode_never_initializes_private_collector(self): ...
    def test_public_privacy_violation_exits_nonzero_without_html(self): ...
```

Use a fixture projection; do not snapshot the whole HTML.

- [ ] **Step 2: Confirm RED**

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioRendererTests -v
```

Expected: import/CLI failure.

- [ ] **Step 3: Implement `render.py` and the dependency-free template**

Follow the existing project-map pattern: escaped template replacements, relative `portfolio.json`, validator before write. Do not reuse the project-map schema.

Required DOM markers:

```text
id="portfolioSearch"
id="attentionQueue"
id="inventoryTable"
id="relationshipGraph"
id="recentChanges"
id="detailPanel"
data-view="public|private"
```

The relationship graph uses inline SVG generated by vanilla JavaScript. No CDN script.

Responsive behavior:

- desktop: summary/attention + inventory + side panels;
- <= 900px: cards stack, detail panel becomes full-width;
- <= 560px: inventory hides secondary columns and moves them to Detail Panel.

- [ ] **Step 4: Implement the CLI**

`build-skill-portfolio.py` imports the core modules, loads public config, collects repository/local/GitHub/external observations, builds and validates the projection, runs public privacy checks, writes `portfolio.json`, then renders `index.html` atomically via temporary files + `os.replace`.

If GitHub/external collection fails and a cache exists, load only the matching source cache and mark it `STALE`. Never treat cached data as fresh.

- [ ] **Step 5: Add the Skill instructions**

`SKILL.md` description:

```yaml
---
name: skill-portfolio
description: Use when the user asks to inspect, refresh, open, summarize, or explain the Skill portfolio, including canonical, under-development, external, private, or migrated Skills and their relationships, readiness, attention items, and evidence.
---
```

Workflow must explicitly say:

- dashboard is read-only;
- `open` uses an existing healthy deployed/private view when available;
- `refresh` rebuilds observations only when requested;
- public/private source boundaries are not interchangeable;
- state-changing actions route to the appropriate separate workflow instead of being performed by this Skill.

`agents/openai.yaml`:

```yaml
interface:
  display_name: "Skill Portfolio"
  short_description: "Inspect Skill lifecycle, readiness, and dependencies"
  default_prompt: "Use $skill-portfolio to refresh and open the read-only Skill Portfolio dashboard."
```

- [ ] **Step 6: Update README and ignore rules**

Add `.skill-portfolio/` to `.gitignore`.

Add a short root README `Skill Portfolio` section after the generated catalog explaining that state is generated, not hand-maintained, and that the deployed public URL will be linked once configured. Do not duplicate a status table in README.

Regenerate catalog after adding the Skill:

```bash
python scripts/generate-skill-catalog.py
```

- [ ] **Step 7: Run focused and integration tests**

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioRendererTests -v
python scripts/validate-skills.py
python scripts/generate-skill-catalog.py --check
python scripts/build-skill-portfolio.py --repo . --mode public --output .skill-portfolio/public
```

Expected:

- validation PASS;
- new canonical Skill is included automatically;
- `.skill-portfolio/public/portfolio.json` and `index.html` exist;
- HOTL row includes `MAIN`, `UNDER_DEVELOPMENT`, `LIMITED`.

- [ ] **Step 8: Commit**

```bash
git add skills/skill-portfolio scripts/build-skill-portfolio.py scripts/skill_portfolio/render.py tests/test_skill_portfolio.py .gitignore README.md
git commit -m "feat: render skill portfolio dashboard"
```

---

### Task 6: Add deterministic CI validation

**Files:**
- Modify: `.github/workflows/validate-skills.yml`
- Modify: `tests/test_skill_portfolio.py`

**Interfaces:**
- Repository validation remains network-independent for portfolio contract tests.
- Live GitHub/external refresh is tested only with fake transport in `tests/test_skill_portfolio.py`.

- [ ] **Step 1: Add a workflow-contract RED test**

Add `SkillPortfolioWorkflowTests` that parses `.github/workflows/validate-skills.yml` as text and requires these commands:

```text
python -m unittest tests.test_skill_portfolio -v
python scripts/build-skill-portfolio.py --repo . --mode public --output .skill-portfolio/ci-public --offline
```

`--offline` must skip live GitHub/external HTTP and still validate canonical discovery/inference/privacy/rendering using repository facts + configuration stubs.

- [ ] **Step 2: Confirm RED**

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioWorkflowTests -v
```

Expected: FAIL because workflow and `--offline` do not exist.

- [ ] **Step 3: Add `--offline` and CI commands**

`--offline` must:

- collect repository facts;
- collect local Git facts available in checkout;
- convert external items to `Freshness: UNAVAILABLE` without network;
- never read stale local cache;
- still run projection and privacy validation.

Add the focused portfolio test and offline build to the existing `validate` job.

- [ ] **Step 4: Run validation suite**

```bash
python -m unittest tests.test_skill_portfolio -v
python scripts/build-skill-portfolio.py --repo . --mode public --output .skill-portfolio/ci-public --offline
python scripts/validate-skills.py
python scripts/generate-skill-catalog.py --check
python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/validate-skills.yml scripts/build-skill-portfolio.py tests/test_skill_portfolio.py
git commit -m "test: validate skill portfolio contracts"
```

---

### Task 7: Add the public Cloudflare Workers Static Assets deployment

**Files:**
- Create: `cloudflare/public/wrangler.jsonc`
- Create: `.github/workflows/deploy-skill-portfolio-public.yml`
- Modify: `tests/test_skill_portfolio.py`
- Modify: `skills/skill-portfolio/README.md`

**Interfaces:**
- Worker name: `skill-portfolio-public`.
- Build output: `.skill-portfolio/public-dist`.
- Required repository secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
- Public workflow triggers: `push` to `main`, `schedule`, `workflow_dispatch`.
- Schedule: `17 */6 * * *` UTC to avoid the top-of-hour herd.

- [ ] **Step 1: Add RED deployment-contract tests**

Add assertions that:

```python
class SkillPortfolioPublicDeployTests(unittest.TestCase):
    def test_public_worker_identity_and_assets_directory_are_fixed(self): ...
    def test_public_workflow_has_push_schedule_and_dispatch(self): ...
    def test_public_workflow_does_not_reference_private_secrets(self): ...
```

Require exact worker name `skill-portfolio-public` and forbid strings `PRIVATE_REPO`, `PRIVATE_CLOUDFLARE`, `private-codex-toolkit`, `private-claude-toolkit` in the public workflow.

- [ ] **Step 2: Confirm RED**

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioPublicDeployTests -v
```

Expected: FAIL because files are absent.

- [ ] **Step 3: Create Wrangler configuration**

`cloudflare/public/wrangler.jsonc`:

```jsonc
{
  "$schema": "../../node_modules/wrangler/config-schema.json",
  "name": "skill-portfolio-public",
  "compatibility_date": "2026-08-14",
  "assets": {
    "directory": "../../.skill-portfolio/public-dist",
    "not_found_handling": "single-page-application"
  }
}
```

Cloudflare documents `assets.directory` relative to the Wrangler configuration and `single-page-application` fallback for SPAs. citeturn831396search0turn565241search0

Do not add Worker `main` code in v1.

- [ ] **Step 4: Create the public deployment workflow**

Use:

```yaml
name: Deploy Skill Portfolio Public

on:
  push:
    branches: [main]
  schedule:
    - cron: "17 */6 * * *"
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: read
  checks: read
  actions: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install -r requirements-validation.txt
      - name: Build public projection
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: >-
          python scripts/build-skill-portfolio.py
          --repo . --mode public
          --output .skill-portfolio/public-dist
          --github-token-env GITHUB_TOKEN
      - name: Deploy public dashboard
        uses: cloudflare/wrangler-action@v4
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: deploy --config cloudflare/public/wrangler.jsonc
```

Do not upload the generated projection as a GitHub Actions artifact.

- [ ] **Step 5: Add deploy documentation**

In `skills/skill-portfolio/README.md`, document one-time setup only:

- create Cloudflare Worker via first workflow deploy;
- set least-privilege `CLOUDFLARE_API_TOKEN` and account ID as GitHub secrets;
- optionally attach a stable custom domain;
- once stable URL exists, add only the public URL to root README.

- [ ] **Step 6: Run static contract tests**

```bash
python -m unittest tests.test_skill_portfolio.SkillPortfolioPublicDeployTests -v
python -m unittest tests.test_skill_portfolio -v
```

Expected: PASS.

- [ ] **Step 7: Perform a dry local asset build**

```bash
python scripts/build-skill-portfolio.py --repo . --mode public --output .skill-portfolio/public-dist --offline
```

Verify only `index.html` and `portfolio.json` plus intentional local assets exist in the deploy directory; no `.env`, cache, local path manifest, or private config file.

- [ ] **Step 8: Commit**

```bash
git add cloudflare/public/wrangler.jsonc .github/workflows/deploy-skill-portfolio-public.yml tests/test_skill_portfolio.py skills/skill-portfolio/README.md
git commit -m "feat: deploy public skill portfolio"
```

---

### Task 8: Final verification and handoff to the Private deployment plan

**Files:**
- Modify only if verification exposes a defect in files already owned by Tasks 1-7.
- Read: `docs/superpowers/plans/2026-08-14-skill-portfolio-private-cloudflare.md` after it exists in the private build-authority repository or as a copied handoff artifact.

**Interfaces:**
- Public core CLI and data contract are frozen inputs to the Private plan.
- Private plan may consume `--mode private` / `--private-config`, but must not weaken public privacy behavior.

- [ ] **Step 1: Run all focused verification**

```bash
python -m unittest tests.test_skill_portfolio -v
python scripts/build-skill-portfolio.py --repo . --mode public --output .skill-portfolio/final-public --offline
python scripts/validate-skills.py
python scripts/generate-skill-catalog.py --check
python -m unittest discover -s tests -v
```

Expected: all PASS.

- [ ] **Step 2: Inspect the generated HOTL projection**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('.skill-portfolio/final-public/portfolio.json').read_text(encoding='utf-8'))
item = next(i for i in p['items'] if i['id'] == 'hotl-governance')
print(item['state'])
PY
```

Expected exact values:

```text
placement=MAIN
development_stage=UNDER_DEVELOPMENT
readiness=LIMITED
activity=IDLE
```

If a real active PR exists at execution time, only `activity` may differ; the first three values must not be overwritten by PR state.

- [ ] **Step 3: Verify public privacy boundary**

Run the privacy tests plus a recursive grep of generated public assets for local home-path prefixes and known private repository names. This is defense in depth; the Python privacy validator remains authoritative.

- [ ] **Step 4: Verify Cloudflare config against current official docs**

Before first deploy, re-check current Cloudflare Workers Static Assets and Wrangler config documentation because deployment syntax is temporally unstable. Confirm `assets.directory`, `not_found_handling`, and `cloudflare/wrangler-action@v4` remain supported. citeturn565241search1turn831396search0turn518153search0

- [ ] **Step 5: Record one-time operator prerequisites without committing secrets**

Report only the names of required secrets and the Worker identity. Do not print token values. If secrets are absent, report deployment as blocked but keep core implementation complete.

- [ ] **Step 6: Commit any final documentation-only correction**

Only if needed:

```bash
git add README.md skills/skill-portfolio/README.md
git commit -m "docs: finalize skill portfolio deployment"
```

Do not create a no-op commit.
