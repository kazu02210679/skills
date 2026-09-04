# Agent Experience v1 — Independent Review Remediation Contract

- **Document date:** 2026-08-22
- **Target:** `agent-experience` v1
- **Status:** Binding remediation; closure review still required
- **Source review:** `docs/superpowers/reviews/2026-08-22-agent-experience-independent-review.md`
- **Reviewed finding set:** `AEX-IR-C01`–`AEX-IR-C03`, `AEX-IR-I01`–`AEX-IR-I07`

## 0. Authority, scope, and disposition

This contract closes the implementation discretion exposed by the independent artifact review. In the domains listed below, this document overrides earlier design, clarification, and plan prose.

The authoring-side disposition for all ten findings is:

```text
fixed
```

This is **not** a closure declaration. Every finding remains `pending_independent_verification` until a fresh artifact-only reviewer verifies the correction and closure tests. Repository-owner acceptance remains a separate final gate.

| Finding | Authoring disposition | Closure state |
|---|---|---|
| `AEX-IR-C01` | fixed | pending independent verification |
| `AEX-IR-C02` | fixed | pending independent verification |
| `AEX-IR-C03` | fixed | pending independent verification |
| `AEX-IR-I01` | fixed | pending independent verification |
| `AEX-IR-I02` | fixed | pending independent verification |
| `AEX-IR-I03` | fixed | pending independent verification |
| `AEX-IR-I04` | fixed | pending independent verification |
| `AEX-IR-I05` | fixed | pending independent verification |
| `AEX-IR-I06` | fixed | pending independent verification |
| `AEX-IR-I07` | fixed | pending independent verification |

No implementation Task may begin solely because this document exists.

---

## 1. `AEX-IR-C01` — Trusted GitHub CLI executable identity

### 1.1 Tracked configuration prohibition

The target repository's tracked configuration must not contain any executable path, executable name, wrapper, command prefix, arbitrary argument list, environment override, extension name, or full endpoint URL.

The following tracked configuration is invalid:

```toml
[remote]
executable = "./tools/gh"
command = ["python", "wrapper.py"]
```

Tracked configuration may contain only provider policy:

```toml
[remote]
provider = "none" # or "github"
authoritative_remote = "origin"
acceptance_policy = ".agent-experience/acceptance-policy.json"
```

### 1.2 Local provider-install record

The GitHub CLI identity is resolved during an explicit local setup operation and stored outside the target working tree:

```text
$(git rev-parse --git-common-dir)/agent-experience/provider-install.json
```

Required fields:

```json
{
  "schema_version": 1,
  "provider": "github",
  "host": "github.com",
  "canonical_executable_path": "<absolute-local-path>",
  "file_sha256": "sha256:...",
  "file_size": 0,
  "file_mtime_ns": 0,
  "device": 0,
  "inode_or_file_index": "...",
  "is_symlink_or_reparse_point": false,
  "tested_gh_version": "...",
  "provider_contract_version": 1,
  "installed_at": "YYYY-MM-DDTHH:MM:SSZ"
}
```

The record is local-only. It is not copied into shared records or the public Skill repository.

### 1.3 Resolution rules

`agent-experience provider setup` may accept either:

1. an explicit absolute `--gh-path`; or
2. the literal program name `gh`, resolved using a sanitized search path that excludes the current directory, worktree, Git common directory, repository-owned tool directories, and temporary extraction directories.

Rules:

- relative paths are rejected;
- arbitrary executable names are rejected;
- wrappers and scripts are rejected;
- POSIX symlinks are rejected;
- Windows reparse points are rejected;
- the final canonical path must not be inside the current worktree, any registered worktree for the repository, the Git common directory, or a configured temporary directory;
- Windows current-directory and `PATHEXT` lookup must not participate after setup;
- the provider invocation always uses the stored absolute path;
- the executable digest and local file identity are rechecked before every provider invocation;
- any drift returns `provider_executable_integrity_failure` and performs no network call;
- provider subprocesses use `shell=False`, fixed argv construction, and a controlled environment allowlist.

The design does not claim race-free executable invocation against a local same-user attacker. It prevents repository-controlled executable selection and detects pre-invocation drift.

### 1.4 Closure tests

```text
tracked config contains executable -> schema reject
tracked config names ./gh -> schema reject
repository root contains gh/gh.exe shadow -> ignored and rejected
python/sh/cmd.exe/powershell.exe as provider -> rejected
trusted gh replaced after setup -> integrity failure
symlink or Windows reparse target -> rejected
canonical gh outside repository with valid capability fixture -> accepted
```

---

## 2. `AEX-IR-C02` — Bootstrap approval provider

### 2.1 TTY is not authority

Interactive TTY re-entry is a user-interface confirmation only. It is never an authorization factor and cannot activate a Policy.

A worker-driven pseudo-terminal, self-declared `human` field, free-form JSON, repository file, Git commit, or matching unsigned audit record cannot establish bootstrap approval.

### 2.2 Candidate generation versus activation

The built-in v1 command may generate a candidate Policy and deterministic mutation plan:

```text
agent-experience policy bootstrap-candidate --input <policy.json> --dry-run --json
agent-experience policy bootstrap-candidate --input <policy.json> --apply --plan-digest <digest> --json
```

This command:

- creates candidate local or working-tree artifacts only;
- does not activate the Policy;
- does not commit, push, open a PR, approve, or merge;
- returns `bootstrap_manual_governance_required` unless a trusted approval provider is available.

### 2.3 Trusted approval provider contract

Policy activation requires a provider-mediated approval that the worker cannot mint or validate from repository bytes alone.

```python
@dataclass(frozen=True)
class VerifiedBootstrapApproval:
    issuer_id: str
    receipt_id: str
    repository_id: int
    owner_id: int
    policy_lineage_id: str
    policy_revision_digest: str
    plan_digest: str
    nonce: str
    issued_at: datetime
    expires_at: datetime
    subject_id: str
```

A trusted approval provider must expose verification through a host/controller boundary. The verifier receives an opaque receipt locator, queries the configured provider, and returns a closed `VerifiedBootstrapApproval`. It must not accept a caller-supplied receipt body as verified evidence.

The local trusted-issuer registry is host-managed and outside the target repository. Repository configuration cannot add or replace issuers.

Required receipt properties:

- schema and issuer contract version;
- issuer ID from the trusted local registry;
- repository numeric ID;
- owner numeric ID;
- Policy lineage ID;
- Policy revision digest;
- exact plan digest;
- nonce;
- issued-at and expiry;
- replay protection;
- exact-byte or provider-native verification.

### 2.4 v1 built-in support boundary

`agent-experience` v1 does not ship a standalone receipt issuer. Without a configured trusted outer-controller adapter, bootstrap stops at candidate generation and returns:

```text
bootstrap_manual_governance_required
```

A future HOTL or host-user-approval adapter may implement the provider interface, but it must be reviewed independently and cannot be inferred from arbitrary repository JSON.

### 2.5 Durable activation

An active bootstrap root requires all of the following:

```text
trusted provider verifies the approval receipt
receipt binding matches repository / owner / lineage / Policy / plan
nonce is unused
receipt is unexpired
candidate Policy revision and root metadata exist on authoritative ref
Policy digest and repository binding are valid
```

Repository files alone never establish approval.

### 2.6 Closure tests

```text
worker drives pseudo-TTY -> activation rejected
self-declared human JSON -> rejected
unsigned audit on authoritative ref -> not active
receipt copied across repository -> rejected
receipt copied across Policy digest or plan -> rejected
nonce replay -> rejected
expired receipt -> rejected
unknown issuer -> rejected
no trusted provider -> bootstrap_manual_governance_required
valid provider verification -> activation predicates may continue
```

---

## 3. `AEX-IR-C03` — Policy lineage

### 3.1 Storage model

Policy revisions are immutable tracked files:

```text
.agent-experience/policies/<policy-lineage-id>/<revision-number>-<policy-digest>.json
```

The configured pointer is:

```text
.agent-experience/acceptance-policy.json
```

The pointer contains only the claimed active revision binding:

```json
{
  "schema_version": 1,
  "policy_lineage_id": "aex-lineage-...",
  "active_revision_number": 3,
  "active_policy_digest": "sha256:...",
  "active_policy_path": ".agent-experience/policies/aex-lineage-.../3-<digest>.json",
  "pointer_base_authoritative_head_sha": "..."
}
```

### 3.2 Revision schema

Every Policy revision contains:

```json
{
  "schema_version": 1,
  "policy_id": "...",
  "policy_lineage_id": "aex-lineage-...",
  "revision_number": 3,
  "policy_revision_digest": "sha256:...",
  "bootstrap_root_receipt_id": "receipt-...",
  "bootstrap_root_receipt_digest": "sha256:...",
  "predecessor": {
    "revision_number": 2,
    "policy_digest": "sha256:...",
    "policy_blob_sha": "...",
    "policy_path": "...",
    "authoritative_head_sha": "..."
  },
  "change_evidence_digest": "sha256:...",
  "repository": {},
  "policy_change": {},
  "artifacts": []
}
```

Revision `0` has `predecessor = null` and requires a verified trusted bootstrap receipt. Every later revision requires an exact predecessor.

### 3.3 Activation rules

- bootstrap is valid only when no trusted root exists for the lineage;
- the candidate predecessor must equal the current active revision and digest;
- the candidate base authoritative head must match the head used by the change evaluation;
- revision number must be previous revision plus one;
- revision number and Policy digest cannot be reused;
- predecessor file and blob must remain reachable and valid;
- a candidate fork from an old predecessor is rejected;
- multiple competing successors from the same predecessor produce `policy_lineage_inconsistent` until one is authoritatively selected and the others are invalidated by current evidence;
- rollback to an older active pointer is rejected;
- force-pushed history that removes required lineage evidence produces `policy_lineage_inconsistent`;
- rebootstrap and lineage recovery are separate future governance protocols.

### 3.4 Closure tests

```text
second bootstrap after root exists -> rejected
P3 references P1 while P2 active -> rejected
stale base authoritative head -> rejected
revision number repeat/decrease -> rejected
two successors from same predecessor -> inconsistent
predecessor removed by force push -> inconsistent
pointer rollback -> rejected
valid root -> P1 -> P2 exact chain -> valid
```

---

## 4. `AEX-IR-I01` — Active plan synchronization

The active implementation plan at

```text
docs/superpowers/plans/2026-08-22-agent-experience-skill-consolidated.md
```

is replaced in place. It directly includes every current binding requirement in the relevant Task, interface, failing test, implementation step, green gate, and commit boundary.

No executor may rely on a sentence saying that an external amendment also applies while the active Task retains an obsolete interface.

### 4.1 Machine-readable requirement map

The implementation creates and validates:

```text
evals/agent-experience/requirements.json
```

Each entry contains:

```json
{
  "requirement_id": "AEX-IR-C01",
  "contract_locator": "...",
  "task_ids": [4, 19],
  "test_files": ["tests/test_agent_experience_provider_runtime.py"],
  "required_case_ids": ["repo_controlled_executable_rejected"]
}
```

Plan validation fails when a binding requirement lacks a Task, a focused test file, or a required case ID.

### 4.2 Obsolete interfaces removed

The active plan must not contain these obsolete contracts:

```text
tracked remote executable path
single response_digest for remote state
caller-supplied manual review receipt
separately reusable fresh receipt for remote resume
unqualified required check source
require_last_push_approval=true support
```

---

## 5. `AEX-IR-I02` — `authoritative_ref_current`

### 5.1 Closed v1 restriction

`authoritative_ref_current` is intentionally restricted to living artifacts evaluated from the current authoritative head.

For this mode, the Policy must not declare:

- `required_pull_requests`;
- `review_policy`;
- `pre_merge` checks;
- `post_merge_result` checks;
- historical PR/reviewer provenance predicates.

It may declare only:

- current path and file type;
- optional content-class constraints;
- `post_merge_authoritative_head` check runs bound to the current authoritative head;
- repository and authoritative-ref binding.

Artifacts requiring PR/reviewer provenance must use `exact_blob`.

### 5.2 Result behavior

If a Policy combines `authoritative_ref_current` with prohibited historical predicates, schema validation fails with:

```text
authoritative_current_historical_predicate_forbidden
```

The evaluator never reuses an older reviewed PR to accept a later unreviewed blob.

### 5.3 Closure tests

```text
authoritative_ref_current + required PR -> schema reject
authoritative_ref_current + reviewer policy -> schema reject
authoritative_ref_current + pre_merge check -> schema reject
current-head check success on current SHA -> eligible
reviewed blob A then direct-push blob B -> old PR cannot accept B
exact_blob with matching reviewed provenance -> eligible
```

---

## 6. `AEX-IR-I03` — Pagination completeness

### 6.1 Complete-set requirement

Any predicate that selects a latest or effective item from a GitHub collection requires a complete normalized collection.

Affected resources include:

- pull-request reviews;
- check runs;
- workflow runs used diagnostically;
- future paginated collection resources.

### 6.2 Pagination contract

The provider:

- requests the endpoint's documented maximum page size, capped at `100` in v1;
- follows only validated GitHub `Link` relations with `rel="next"`;
- validates that the next URL remains on `https://api.github.com`, uses the same typed operation, repository, resource, and API version;
- does not accept a caller-supplied next URL;
- stops only when no validated next relation exists;
- uses closed limits:

```text
max_pages_per_resource = 20
max_items_per_resource = 2000
max_normalized_bytes_per_resource = 16 MiB
max_remote_batch_wall_time = 30 seconds
```

Normalized collection metadata contains:

```json
{
  "complete": true,
  "page_count": 2,
  "item_count": 130,
  "normalized_items_digest": "sha256:..."
}
```

Any timeout, rate limit, page or item cap, malformed Link header, host/path drift, schema failure, or partial provider failure before completion returns:

```text
unknown / partial_response
```

A partial collection never produces a pass predicate.

### 6.3 Closure tests

```text
later-page CHANGES_REQUESTED -> fail
later-page failing/latest check -> selected correctly
later-page duplicate app/name -> inconsistent
rate limit after page one -> unknown
page/item/byte cap exceeded -> unknown
pagination order changes but normalized complete set same -> same digest/result
malicious next URL host or operation drift -> integrity failure
```

---

## 7. `AEX-IR-I04` — Preflight receipt

### 7.1 Local-only controller record

`PreflightReceiptV1` is created and stored by the deterministic local controller. The CLI returns only a receipt ID. It never accepts a caller-supplied receipt body, stdin JSON, shared record, or repository file as a valid receipt.

```python
@dataclass(frozen=True)
class PreflightReceiptV1:
    receipt_id: str
    nonce: str
    repo_id: str
    worktree_id: str
    branch_ref: str
    head_sha: str
    index_manifest_digest: str
    tracked_worktree_manifest_digest: str
    untracked_manifest_digest: str
    scope_manifest_digest: str
    config_digest: str
    active_policy_pointer_digest: str | None
    active_policy_revision_digest: str | None
    workstream_id: str | None
    operation: str
    operation_scope_digest: str
    use_context_id: str | None
    cli_contract_version: int
    issued_at: datetime
    expires_at: datetime
```

### 7.2 Issue and consumption

A receipt is:

- local-only;
- operation-specific;
- single-use for mutation commands;
- valid for at most five minutes;
- consumed atomically with the gated command;
- namespaced by repository and worktree;
- invalid after any bound identity, snapshot, configuration, Policy, workstream, operation, or scope change.

The gated commands are:

```text
start
checkpoint
capture
seal
policy bootstrap-candidate --apply
provider setup --apply
```

Before consuming the receipt, the command recomputes current identity, snapshot, configuration, and active Policy binding and compares every field exactly. Remote-dependent operations additionally require the same `use_context_id`.

### 7.3 Closure tests

```text
receipt body supplied by caller -> rejected
receipt ID copied across repo/worktree -> rejected
branch or HEAD changes -> rejected
tracked/untracked/scope digest changes -> rejected
config or active Policy changes -> rejected
operation mismatch -> rejected
expired or replayed receipt -> rejected
exact current context and matching operation -> accepted once
```

---

## 8. `AEX-IR-I05` — Check-run-only v1 policy

### 8.1 Explicit scope

Agent Experience v1 intentionally evaluates GitHub **check runs only**. It does not reproduce GitHub branch-protection or ruleset required-status behavior and does not evaluate commit statuses.

Policy entries use:

```json
{
  "source": "check_run",
  "name": "validate-foundation",
  "app_id": 12345,
  "phase": "pre_merge",
  "allowed_conclusions": ["success"]
}
```

Rules:

- `source` is required and the only v1 value is `check_run`;
- source omission is invalid;
- `commit_status` and `both` are unsupported in v1 and return `unsupported_resource_semantics`;
- all wording in the active plan and contract says `check run`, not ambiguous `checks/statuses`;
- an accepted-artifact result includes `branch_protection_parity_evaluated = false`;
- accepted status never means GitHub merge readiness.

### 8.2 Closure tests

```text
source omitted -> schema reject
source=commit_status -> unsupported
source=both -> unsupported
check run selected only by exact source/name/app/SHA/phase
same-name commit status does not silently alter Policy result
result explicitly reports no branch-protection parity claim
```

---

## 9. `AEX-IR-I06` — Last-push approval

`require_last_push_approval` is not supported in v1.

The Policy schema rejects the field when `true`, and rejects any equivalent alias or approximation request with:

```text
unsupported_resource_semantics
```

The implementation must not approximate the last pusher using commit author, committer, PR author, or current reviewer.

Closure tests:

```text
require_last_push_approval=true -> rejected
commit author used as pusher -> prohibited by contract test
field absent/false -> no last-push parity claim
```

A future version requires an independently reviewed provider for the last reviewable-push actor.

---

## 10. `AEX-IR-I07` — Typed GitHub requests and encoding

### 10.1 Typed request model

The provider accepts typed operations only:

```python
class GitHubOperation(Enum):
    REPOSITORY = "repository"
    BRANCH = "branch"
    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    PULL_REQUEST_REVIEWS = "pull_request_reviews"
    CHECK_RUNS_FOR_REF = "check_runs_for_ref"
    WORKFLOW_RUNS_FOR_SHA = "workflow_runs_for_sha"
    FILE_ON_REF = "file_on_ref"
    AUTHENTICATED_USER = "authenticated_user"
```

Callers cannot supply a method, URL, endpoint string, query string, GraphQL document, extension command, or arbitrary header.

### 10.2 Encoding rules

- owner and repository fields are validated as decoded GitHub identifiers;
- branch/ref fields are decoded values and encoded as one URI path segment when used in a segment position;
- Git file paths are normalized repository-relative POSIX paths, split on `/`, and each decoded segment is encoded separately;
- query keys and decoded values are encoded separately;
- input containing a percent escape sequence `%HH` is rejected as `preencoded_input_rejected`; callers provide decoded values only;
- empty path segments, `.`, `..`, NUL, control characters, and encoded path separators are rejected;
- operation allowlisting happens before URL construction;
- pagination next links are parsed into the same typed operation and validated before use;
- normalized responses are rebound to repository numeric ID and the exact typed request key.

### 10.3 Closure tests

```text
path contains ?, &, #, %, Unicode -> exact intended encoded resource
branch contains slash -> one encoded branch segment
pre-encoded %2F or double-encoded separator -> rejected
full URL or endpoint string input -> rejected
response repository/path/ref mismatch -> integrity failure
pagination next URL changes operation or host -> integrity failure
```

---

## 11. Binding implementation-plan changes

The active consolidated plan is rewritten in place and must include:

- Task 1 pressure cases for all ten independent-review findings;
- Task 2 machine-readable requirement mapping and contract tests;
- Task 4 prohibition of tracked executable configuration;
- Task 7 preflight receipt, optimistic checkpoint revision, provider-install, pagination/refresh storage, and index-generation tables;
- Task 9 operation-specific receipt issue/consume behavior;
- Task 18 typed request, provenance, four digests, completeness metadata, `use_context_id`;
- Task 19 trusted local GitHub CLI setup, executable drift detection, typed encoding, complete pagination;
- Task 20 external bootstrap approval provider, immutable Policy lineage, `authoritative_ref_current` restriction, check-run-only source, last-push rejection, accepted-artifact evaluator;
- Task 21 same-command refresh-and-decide and stable-only successor behavior;
- Task 27 closure tests on Windows and Linux;
- Task 28 all review findings as rollout hard stops.

---

## 12. Closure matrix

| Finding | Primary Tasks | Required verification |
|---|---|---|
| `AEX-IR-C01` | 4, 7, 19, 27 | executable-shadow/drift tests |
| `AEX-IR-C02` | 20, 26, 28 | unforgeable-provider / no-provider tests |
| `AEX-IR-C03` | 20, 27, 28 | lineage reset/rollback/fork tests |
| `AEX-IR-I01` | 2, all | requirement-map and fresh plan review |
| `AEX-IR-I02` | 20, 28 | current-blob provenance restriction tests |
| `AEX-IR-I03` | 18, 19, 27 | multi-page completeness tests |
| `AEX-IR-I04` | 7, 9, 27 | stale/replayed receipt tests |
| `AEX-IR-I05` | 18, 20 | check-run-only schema tests |
| `AEX-IR-I06` | 20 | unsupported last-push tests |
| `AEX-IR-I07` | 18, 19, 27 | typed encoding / response binding tests |

## 13. Review gate

After the documents and plan are updated, a fresh independent artifact-only closure review must inspect:

1. this remediation contract;
2. the rewritten Contract Index;
3. the rewritten active consolidated plan;
4. the original independent review;
5. the machine-readable remediation matrix.

The closure reviewer records each finding as:

```text
verified_closed
reasoned_rejected
disputed
```

Task 1 remains blocked while any Critical or Important finding is `disputed` or otherwise open.
