# Host compatibility

This catalog shares portable Skill content across Claude Code and Codex. It
does not claim that the hosts have identical runtime behavior.

## Shared conventions

- Discover a Skill from the `name` and `description` in `skills/<name>/SKILL.md`.
- Resolve bundled `scripts/`, `references/`, and `assets/` relative to the
  Skill directory.
- Read repository instructions before editing: `AGENTS.md` for Codex and
  `CLAUDE.md` for Claude Code.
- Install only the Skills needed for the current host and scope.

## Invocation differences

Claude Code can invoke a named Skill directly. In Codex, follow the workflow
when the request matches the Skill description or the user names the Skill.
Do not treat one host's tool syntax as an automatic substitute for the other's.

## `codex-orchestration`

Use `codex-orchestration` in Claude Code to delegate a guarded task to the
Codex CLI while Claude owns requirements and independent acceptance review. In
Codex, use it to inspect or maintain the workflow; do not recursively delegate
to another Codex session unless the user explicitly asks.

The portable interface is `SKILL.md`, its references, and its six bundled
scripts. The former plugin-only manifest, slash commands, and dedicated
reviewer agent are intentionally retired. They are not alternate interfaces.
Run scripts relative to the installed Skill directory rather than a plugin
root. The task-plan contract defines the portable run, resume, scope, commit,
and status behavior.

## Host-specific metadata

`agents/openai.yaml` provides Codex UI metadata. Claude Code does not consume
that file. Do not recreate host-specific packages merely to make the two hosts
look symmetrical; keep shared instructions and resources canonical under
`skills/`.
