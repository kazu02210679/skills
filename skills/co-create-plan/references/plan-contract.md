# Joint Plan Contract

Use this contract for
`.codex-instructions/<task-slug>.md`. Keep the plan useful to a fresh
implementation agent that has not seen the dialogue.

## Required frontmatter

```yaml
---
planning_status: proposed
planning_method: claude-codex-consensus
task_slug: <lower-case-hyphenated-slug>
participants:
  - claude
  - codex
---
```

Allowed `planning_status` values:

- `proposed`: both models have completed the plan, but the user has not
  approved it;
- `approved`: the user explicitly approved this exact plan;
- `stale`: repository evidence or requirements changed after planning.

## Required sections

Use these headings in this order:

1. `# <Plan title>`
2. `## Objective`
3. `## Requirements`
4. `## Constraints`
5. `## In scope`
6. `## Out of scope`
7. `## Repository evidence`
8. `## Decisions and rationale`
9. `## Implementation steps`
10. `## Acceptance checklist`
11. `## Test policy`
12. `## Risks and rollback`
13. `## Open questions`
14. `## Stuck protocol`
15. `## Planning record`

## Content rules

### Scope guard

The packet must tell the implementation agent explicitly:

> Do not add features that are not explicitly included in this packet.

Keep this instruction near the top-level requirement so it applies to every
implementation step.

### Repository evidence

Cite repository-relative file paths, symbols, commands, or observed behavior.
Label an inference as an inference. Do not present a planned path as existing
code.

### Decisions and rationale

For every material decision, record:

- selected option;
- alternatives considered;
- evidence or trade-off that decided it;
- whether Claude, Codex, or both originally challenged it.

Do not copy the full transcript into the plan.

### Implementation steps

Order steps by dependency. Each step must include:

- exact existing file paths, or an explicit discovery target when a path cannot
  yet be known;
- intended behavior or contract change;
- tests or checks to add or update;
- dependencies on earlier steps;
- a completion signal.

Avoid vague steps such as “implement the feature” or “add tests.”

### Acceptance checklist

Write checkboxes whose truth can be observed. Name commands when known. Include
behavioral checks in addition to test-suite commands.

Example:

```text
- [ ] `python -m pytest tests/unit/test_parser.py -q` passes.
- [ ] An invalid empty payload returns the documented error without writing data.
```

### Test policy

Require test-driven development for implementation behavior changes: add or
update a failing test first, observe the expected failure, implement the
smallest change that passes, then run the relevant regression suite. State the
expected test level, boundary and failure cases, lint/type/build checks, and any
checks that cannot run locally. Never claim an unexecuted check passes.

### Open questions

An approved plan must contain either `None` or only non-blocking questions with
an owner and a validation step. A blocking question requires a user decision
before approval.

### Stuck protocol

Include this exact semantic rule:

> If a blocker, repository contradiction, or API/spec conflict appears, do not
> make large unrequested changes. Record the problem, evidence, and smallest
> viable alternatives, then stop for a decision.

### Planning record

Record:

- dialogue artifact directory;
- number of completed exchange rounds;
- final Claude vote;
- final Codex vote;
- user approval state and date;
- any user tie-break decision.

## Compatibility with codex-orchestration

The approved file is a complete task packet. Pass it directly to:

```bash
"<codex-orchestration-skill-dir>/scripts/codex_run.sh" \
  .codex-instructions/<task-slug>.md \
  <repo>
```

The Skill should begin at delegation/implementation. Do not regenerate the
packet.
