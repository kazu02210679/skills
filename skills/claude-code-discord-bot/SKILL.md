---
name: claude-code-discord-bot
description: Set up a Discord bridge in front of Claude Code so the user can send instructions from Discord, receive progress and completion notifications, and approve or deny tool use from a phone. Use when the user asks to turn Claude Code into a Discord bot, drive Claude Code from Discord or a phone, get a Discord ping when Claude Code finishes or needs input, or add a human-in-the-loop approval channel for an agent running on their own machine. Does not apply to Slack or other chat platforms, to chat bots unrelated to Claude Code, or to hosting one bot for other people to share.
---

# Claude Code Discord Bot

Build one bridge process that owns the Discord connection and brokers three flows against Claude Code
on the user's own host: instruct, notify, approve. The bridge is remote code execution with a chat
front end. Fix its trust boundary before writing any feature code.

## Required Inputs

- Which of the three flows the user wants. Do not build an unrequested flow.
- The host that runs Claude Code, and whether it stays awake.
- The Discord guild ID, the channel IDs the bridge may listen to, and the user IDs allowed to
  operate and to approve.
- The workspace root and the project directories the bridge may open.
- Whether the user needs real containment. Ask what else lives on the host: SSH keys, cloud
  credentials, other people's repositories.

Stop and ask when the operator user IDs or the workspace root are unknown. Do not default to "any
member of the guild" or to the process working directory.

## Trust Boundary

Establish these before the bridge runs, and never relax one to make a demo work:

- The bridge accepts work only from the configured guild, the configured channels, and the
  configured operator user IDs. Reject direct messages and every other guild.
- Secrets live in the environment, never in the config file or the repository. Store the bot token
  under a `*_env` name and read it at startup.
- Declare `setting_sources` explicitly. Omitting it loads user, project, and local settings, so an
  existing permission rule or hook can grant a tool before the approval path ever runs.
- The hook endpoint binds loopback only, and requires a shared secret.
- Approval fails closed. Claude Code does not treat a missing, late, or failed answer as a denial,
  so the bridge must send one.
- This is a personal bridge to one user's own Claude Code. Do not turn it into a shared service:
  the Agent SDK terms do not permit offering claude.ai login or its rate limits to third parties.

### What the workspace root does and does not do

`workspace_root` restricts which project directories the bridge may open. It is input validation on
a chat message, and the validator enforces it.

It is not a filesystem sandbox. Claude Code reads outside the working directory, Bash reaches
absolute paths, and a symlink inside the workspace can point anywhere. Do not tell the user their
host is contained because a workspace root is set.

When the host holds anything the operator should not reach through Discord, say so plainly and
configure real containment: the SDK `sandbox` settings, a container, or a VM. Otherwise state the
limitation and let the user decide.

## Transport Matrix

Two session origins need different plumbing, and the config keeps them in separate blocks. Read
[bridge-contract.md](references/bridge-contract.md) for the exact payload shapes.

| Flow | `bridge_sessions` | `terminal_sessions` |
|---|---|---|
| Instruct | Agent SDK `query()`, or `claude -p --output-format stream-json` | not applicable |
| Notify | the SDK message stream | `Stop` and `Notification` hooks, type `http` |
| Approve | the `canUseTool` callback | the `PermissionRequest` hook, type `http` |

`canUseTool` is an Agent SDK callback. It does not exist on the CLI transport, and it never covers a
session the user started in their own terminal. A CLI-driven bridge session routes approval through
the same `PermissionRequest` hook that terminal sessions use.

Prefer the Agent SDK (`@anthropic-ai/claude-agent-sdk`) for bridge-owned sessions. It delivers
streaming, session resumption, and approval through one in-process API.

## Workflow

1. Confirm the requested flows, the host, and the trust boundary inputs. Record what the user
   declined so later steps do not smuggle it back in.
2. Verify the contract against what is actually installed before writing anything that depends on
   it. These shapes have changed between releases:

   ```bash
   python <skill-dir>/scripts/check_sdk_contract.py \
     --sdk-types <project>/node_modules/@anthropic-ai/claude-agent-sdk/sdk.d.ts \
     --cli claude
   ```

   On drift, read the shipped declarations and update
   [bridge-contract.md](references/bridge-contract.md) and the validator together. Do not code
   against the reference file when the checker disagrees with it.
3. Create the Discord application and invite the bot. Follow
   [discord-app-setup.md](references/discord-app-setup.md). Prefer slash commands, which need no
   privileged intent, over reading raw message content.
4. Write `discord-bridge.json` in the user's project from the schema in
   [bridge-contract.md](references/bridge-contract.md).
5. Validate it before writing feature code, and again after every edit:

   ```bash
   python <skill-dir>/scripts/validate_bridge_config.py <project>/discord-bridge.json
   ```

   Fix reported errors in the config. Do not weaken the validator.
6. Implement only the confirmed flows in the user's project:
   - Instruct: one Discord thread is one Claude Code session. Store the `session_id` from the
     `system/init` event or the SDK stream, and pass it as `resume` on every later turn in that
     thread. Post tool activity as it streams so a long run is visible.
   - Notify: post turn completion and idle or input-needed events to the configured channel. Treat
     `last_assistant_message` as optional, and report a session with in-flight `background_tasks`
     as still working rather than finished.
   - Approve: mint an approval ID in the bridge, because the permission event carries no tool use
     ID. Render the prompt, ask for a decision with buttons, return the decision to the waiting
     session, and deny on timeout.
7. Wire hooks only when the user wants terminal sessions covered. Add the `http` hook entries from
   the reference to the project's `.claude/settings.json`, or to `~/.claude/settings.json` for
   every project. Keep the shared secret in `allowedEnvVars`, not inline.
8. Verify against a live guild, in this order:
   - an unauthorized user ID is ignored in an allowed channel;
   - a message in a non-allowed channel is ignored;
   - a two-turn thread keeps context, proving session resumption;
   - a completion notification arrives;
   - an approval prompt appears, allow runs the tool, deny blocks it;
   - an unanswered approval denies within the configured timeout;
   - a second click on an answered approval changes nothing;
   - a reply longer than 2000 characters is chunked, not truncated or dropped.
9. Report the config path, the contract check result, the validator result, which flows are live,
   which verification steps passed, and the exact secrets the user must set in the environment.
   State plainly whether the host is sandboxed.

## Constraints

- Never commit the bot token, the shared secret, or `discord-bridge.json` when it holds an inline
  secret. Add the config to `.gitignore` when it carries any host-specific ID the user wants private.
- Never enable `bypassPermissions` to make approval prompts stop appearing. That mode removes the
  event the approval flow depends on; the validator rejects the combination.
- Persist an "always allow" choice by echoing the permission suggestions the event supplied, and
  only when the approver explicitly asked not to be asked again.
- Do not echo file contents, diffs, or environment values into a channel the user did not designate.
  Discord history is durable and searchable.
- Truncate at a boundary you choose and attach the remainder as a file. Never let the Discord 2000
  character limit silently drop the tail of an answer.
- Hold a pending approval in the bridge's own state, not in a Discord interaction. Post the prompt,
  wait, and when a button is finally pressed acknowledge that interaction within three seconds,
  resolve the pending approval, and disable the buttons.
- Accept only the first valid answer per approval ID. Reject replays, double clicks, and stale
  buttons left over from a bridge restart.
- Run one bridge per host. Two bridges resuming the same session ID corrupt the transcript.

## Failure Handling

- Bot cannot read messages: the Message Content intent is off, or the flow needs slash commands.
- Session resume fails: the recorded `session_id` was written from the wrong stream event, or the
  session was started from a different directory. Session lookup is scoped to the project directory.
- Approval never fires: a loaded settings source or an `allowedTools` rule already granted the tool,
  or the permission mode grants it outright. Check `setting_sources` first.
- Approval times out: deny, post that it was denied on timeout, and keep the thread usable. A failed
  or timed-out HTTP hook is a non-blocking error in Claude Code, so the bridge must send an explicit
  deny before the hook timeout rather than rely on silence.
- A `canUseTool` prompt has no deadline of its own; an unanswered one blocks that session forever.
  The bridge owns that timeout, and must honor the abort signal.
- Host sleeps mid-run: report the run as interrupted. Do not present a partial transcript as complete.
