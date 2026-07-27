# Host compatibility

The 68 vendored PM Skill bodies are distributed byte-for-byte as imported. This
repository supplies a host compatibility layer around them instead of silently
rewriting third-party instructions.

## Invocation arguments

- Claude Code natively replaces `$ARGUMENTS` in a Skill with the arguments from
  the invocation.
- Codex documents explicit Skill invocation with `$skill-name`, but does not
  document textual `$ARGUMENTS` substitution. On Codex, interpret a literal
  `$ARGUMENTS` semantically as the current explicit Skill invocation or the
  user's task input. The installer does not preprocess or mutate Skill bodies.

This convention preserves intent, but it is not a claim of full runtime parity.
If an instruction truly depends on host-side textual substitution, the agent
must ask for or infer the invocation input from the current user request rather
than claiming that substitution occurred.

## Referenced upstream slash commands

The vendored `shipping-artifacts` Skill refers to upstream command files that
are not redistributed. Use these repository-present procedures:

| Reference | Portable procedure |
|---|---|
| `/document-app` | Invoke `shipping-artifacts` and follow its documentation workflow. |
| `/derive-tests` | Invoke `shipping-artifacts` to identify shipped behavior, then `test-scenarios` to derive coverage. |
| `/ship-check` | Invoke `intended-vs-implemented`, then `shipping-artifacts` to assemble and verify release evidence. |

The machine-readable contract is
`compatibility/host-contract.json`.

## Documentation basis

- Claude Code Skills documentation:
  <https://code.claude.com/docs/en/skills>
- OpenAI's Codex Skill-building documentation:
  <https://learn.chatgpt.com/docs/build-skills>
