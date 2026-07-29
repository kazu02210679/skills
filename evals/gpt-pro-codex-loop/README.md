# GPT Pro Codex Loop evaluations

This directory records the behavior contract for `gpt-pro-codex-loop`.
Run behavior prompts in a fresh agent context without the Skill for RED, then
repeat with the Skill loaded for GREEN. Machine-checkable validator and
snapshot tests live beside this file.

## RED method

On 2026-07-29, six fresh-context agents received no Skill text and no
repository access. Three pressure scenarios tested runtime judgment and three
prompts asked for a minimal production protocol. The pressure scenarios
correctly stopped on failed local verification, material requirement changes,
and a replacement conversation. The design prompts exposed the protocol gaps
the Skill must close.

## Observed baseline failures

### Conversation continuity was not preserved

The minimal evidence design instructed automation to:

> open a fresh browser conversation

for review. That loses the requirements conversation identity and permits a
review response from an unrelated thread. The Skill must bind one persistent
conversation after the first requirements response and reject every later
response whose conversation identity or visible Pro model does not match.

### Material revisions could advance without user approval

The baseline state machine routed:

> newer revision detected → restart this state

and:

> Revision → `SYNC_REQUIREMENTS`

without distinguishing clarification from a behavioral or public-contract
change. The Skill must require explicit user approval for material behavior,
scope, or public-contract changes, create a superseding requirements digest,
invalidate prior implementation evidence, and reset review rounds.

### Local failures could be waived too loosely

The baseline completion protocol allowed:

> required automated checks pass, or an explicitly accepted exception is
> recorded

without defining who may accept the exception or how that affects the final
gate. The Skill must fail closed: Pro `PASS` cannot override a failed required
local check or an unverified acceptance criterion.

### Review identity was not bound to the complete worktree

The baseline evidence format recorded a commit/base SHA and changed files but
did not hash untracked product files or bind the reviewer verdict to a combined
product snapshot. The Skill must compute a deterministic snapshot digest from
the baseline-relative tracked diff and bounded untracked product manifest, and
require `reviewed_snapshot_digest` to equal the final local snapshot.

## GREEN expectations

The cases in `cases.json` pass only when the Skill:

- gives requirements and semantic review to ChatGPT Pro while Codex retains
  repository inspection, implementation, and local verification;
- keeps one bound Pro conversation for requirements, revisions, and reviews;
- treats local tests, acceptance evidence, scope, and snapshot identity as an
  AND gate with Pro `PASS`;
- distinguishes evidence requests from code changes;
- requires user approval and fresh review for material requirement revisions;
- does not trigger for ordinary implementation work that did not request the
  Pro loop.

## Automated tests

Run:

```powershell
python evals/gpt-pro-codex-loop/test_validate_packet.py -v
python evals/gpt-pro-codex-loop/test_capture_snapshot.py -v
```

Run repository-wide validation after the Skill and tests are complete.
