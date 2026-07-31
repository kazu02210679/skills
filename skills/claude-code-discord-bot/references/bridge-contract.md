# Bridge contract

The data contract between Discord, the bridge process, and Claude Code.

Verified against `@anthropic-ai/claude-agent-sdk` 0.3.220 type declarations and Claude Code CLI
2.1.220 `--help`. Re-verify with `scripts/check_sdk_contract.py` before trusting an older copy of
this file; these shapes have changed before.

## Two session origins, two configuration blocks

A bridge-owned session and a terminal-started session need different plumbing, so the config keeps
them apart. Never describe one approval path as if it covered both.

| Flow | `bridge_sessions` | `terminal_sessions` |
|---|---|---|
| Instruct | Agent SDK `query()`, or `claude -p` | not applicable |
| Notify | the SDK message stream | `Stop` and `Notification` hooks, type `http` |
| Approve | the `canUseTool` callback | the `PermissionRequest` hook, type `http` |

`canUseTool` is an Agent SDK callback. It does not exist on the CLI transport, and it never covers a
session the user started in their own terminal.

## Config schema

`discord-bridge.json` at the user's project root. `scripts/validate_bridge_config.py` enforces it.

```json
{
  "version": 2,
  "discord": {
    "guild_id": "123456789012345678",
    "command_channel_ids": ["223456789012345678"],
    "notification_channel_id": "323456789012345678",
    "operator_user_ids": ["423456789012345678"],
    "approver_user_ids": ["423456789012345678"],
    "token_env": "DISCORD_BOT_TOKEN"
  },
  "bridge_sessions": {
    "enabled": true,
    "transport": "agent-sdk",
    "workspace_root": "/home/me/src",
    "projects": { "skills": "/home/me/src/skills" },
    "permission_mode": "default",
    "setting_sources": ["project"],
    "allowed_tools": ["Read", "Grep", "Glob"],
    "disallowed_tools": [],
    "max_concurrent_sessions": 2,
    "sandbox": { "enabled": true, "fail_if_unavailable": true },
    "approval": {
      "enabled": true,
      "transport": "can-use-tool",
      "timeout_seconds": 300,
      "on_timeout": "deny"
    }
  },
  "terminal_sessions": {
    "enabled": true,
    "listen_host": "127.0.0.1",
    "listen_port": 8787,
    "shared_secret_env": "CLAUDE_DISCORD_HOOK_TOKEN",
    "notifications": {
      "on_completion": true,
      "on_idle_prompt": true,
      "on_permission_request": true
    },
    "approval": {
      "enabled": true,
      "transport": "permission-request-hook",
      "hook_timeout_seconds": 600,
      "timeout_seconds": 300,
      "on_timeout": "deny"
    }
  }
}
```

Either block may be `{"enabled": false}`. At least one must be enabled.

### Permission modes

Taken from the shipped declarations, not from prose. The two hosts differ, and the difference is not
the one an older draft of this file claimed.

| Transport | Accepted values |
|---|---|
| Agent SDK (`PermissionMode`) | `default`, `acceptEdits`, `bypassPermissions`, `plan`, `dontAsk`, `auto` |
| CLI (`--permission-mode` choices) | `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan` |

The CLI does not accept `default`; omit the flag to get default behavior. The SDK does not accept
`manual`. Both accept `acceptEdits` and `auto`.

### Setting sources

`setting_sources` maps to the SDK `settingSources` option, whose values are `user`, `project`, and
`local`. **Omitting it loads all three.** For a bridge that executes code on behalf of a chat
message, that silently pulls in whatever hooks and permission rules already live in
`~/.claude/settings.json` and `.claude/settings.local.json`, which can grant a tool before the
approval path ever runs.

Set it explicitly. `["project"]` keeps `CLAUDE.md` and checked-in project settings, which is the
usual choice. `[]` is full isolation; the managed-settings policy tier is still read.

### What `workspace_root` is, and is not

`workspace_root` restricts **which project directories the bridge may open**. That is a useful
input-validation rule and the validator enforces it.

It is not a filesystem sandbox. Claude Code can read outside the working directory, Bash reaches
absolute paths, and a symlink inside the workspace can point anywhere. A config-file validator
cannot resolve symlinks on the machine that will eventually run the bridge, so it checks path shape
only.

Real containment needs `sandbox` settings, a container, or a VM. The SDK exposes `sandbox` with
`enabled`, `failIfUnavailable`, `network.allowedDomains`, `filesystem.allowRead` / `allowWrite` /
`denyRead` / `denyWrite`, and `credentials` deny rules. Use them when the host holds SSH keys,
tokens, or other projects the operator should not reach through Discord.

## Thread to session mapping

One Discord thread is one Claude Code session.

1. First message in a thread starts a session. Do not pass `resume`.
2. Read the session ID from the SDK stream, or from the `system/init` event when
   `--output-format stream-json` is used. With `--output-format json`, read `.session_id`.
3. Persist `thread_id -> {session_id, project, cwd}`.
4. Every later message in that thread passes the stored session ID as `resume`, from the same
   working directory. Session lookup is scoped to the project directory and its git worktrees.

## Instruct flow, CLI transport

```bash
claude -p "<prompt>" \
  --output-format stream-json --verbose \
  --permission-mode acceptEdits \
  --allowedTools "Read,Grep,Glob"
```

Resume a thread:

```bash
claude -p "<prompt>" --output-format stream-json --verbose --resume "<session_id>"
```

The CLI transport has no interactive approval callback. Route approval for CLI-driven sessions
through the `PermissionRequest` hook, the same path terminal sessions use.

## Instruct and approve flow, Agent SDK transport

`npm install @anthropic-ai/claude-agent-sdk`

`canUseTool` takes the tool name and input as **separate positional arguments**, and returns a
`PermissionResult` discriminated on `behavior`. It is not a request object, and it does not return
`approved`.

```ts
import { query } from "@anthropic-ai/claude-agent-sdk";

const q = query({
  prompt: userMessage,
  options: {
    cwd: projectPath,
    resume: storedSessionId,          // omit on the first turn
    permissionMode: "default",
    settingSources: ["project"],      // omitting this loads user + project + local
    allowedTools: ["Read", "Grep", "Glob"],

    canUseTool: async (toolName, input, { signal, suggestions, title, displayName }) => {
      const answer = await askDiscord({
        // `title` is the prompt sentence Claude Code already rendered, for example
        // "Claude wants to read foo.txt". Prefer it over rebuilding text from toolName.
        prompt: title ?? `${toolName}`,
        label: displayName ?? toolName,
        toolName,
        input,
        signal,
      });

      if (answer === "deny") {
        return { behavior: "deny", message: "Denied in Discord" };
      }
      return {
        behavior: "allow",
        // Optional. Send it only when the approver edited the arguments.
        updatedInput: answer.editedInput,
        // Only when the approver chose "always allow": pass the suggestions through
        // so the same call is not asked again this session.
        updatedPermissions: answer === "always" ? suggestions : undefined,
      };
    },
  },
});

for await (const message of q) {
  // stream tool activity and assistant text to the thread
}
```

`canUseTool` runs only when the permission flow falls through to a prompt. A tool listed in
`allowedTools`, or granted by a loaded settings source, is auto-approved and never reaches Discord.

The callback has no deadline: an unanswered permission prompt blocks that session indefinitely. The
bridge owns the timeout. Resolve with `{ behavior: "deny", message: "Approval timed out" }` when the
window expires, and honor `signal` so an aborted session does not leak a pending approval.

## Notify flow, hook transport

`Stop` fires after Claude finishes a turn. `Notification` fires for permission prompts, idle
prompts, and agent lifecycle events; matcher values include `permission_prompt`, `idle_prompt`,
`auth_success`, `agent_needs_input`, and `agent_completed`. Neither event can block.

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "http",
            "url": "http://127.0.0.1:8787/hooks/stop",
            "headers": { "Authorization": "Bearer $CLAUDE_DISCORD_HOOK_TOKEN" },
            "allowedEnvVars": ["CLAUDE_DISCORD_HOOK_TOKEN"],
            "timeout": 15
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "idle_prompt|agent_needs_input",
        "hooks": [
          {
            "type": "http",
            "url": "http://127.0.0.1:8787/hooks/notification",
            "headers": { "Authorization": "Bearer $CLAUDE_DISCORD_HOOK_TOKEN" },
            "allowedEnvVars": ["CLAUDE_DISCORD_HOOK_TOKEN"],
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Every hook body carries `session_id`, `transcript_path`, `cwd`, and optional `prompt_id`,
`permission_mode`, `agent_id`, and `agent_type`.

`Stop` adds `stop_hook_active`, an **optional** `last_assistant_message`, and `background_tasks`.
Treat `last_assistant_message` as possibly absent and fall back to a generic completion line rather
than posting `undefined`. A non-empty `background_tasks` means the session is waiting on background
work, not finished; say so instead of announcing completion.

`Notification` adds `message`, optional `title`, and `notification_type`.

Newer matcher values do not exist on older Claude Code builds. Degrade rather than lose the
notification: `Stop` for turn completion, `StopFailure` for failure, `idle_prompt` for waiting, and
`agent_completed` only where it is supported.

Return `204` with an empty body. These hooks need no decision.

## Approve flow, hook transport

`PermissionRequest` fires only when a tool call needs a decision, which is what a human-in-the-loop
channel wants. `PreToolUse` fires on every tool call and would flood Discord.

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "Bash|Write|Edit|WebFetch",
        "hooks": [
          {
            "type": "http",
            "url": "http://127.0.0.1:8787/hooks/permission",
            "headers": { "Authorization": "Bearer $CLAUDE_DISCORD_HOOK_TOKEN" },
            "allowedEnvVars": ["CLAUDE_DISCORD_HOOK_TOKEN"],
            "timeout": 600
          }
        ]
      }
    ]
  }
}
```

`PermissionRequestHookInput` is the common hook fields plus `tool_name`, `tool_input`, and an
optional `permission_suggestions` array.

**There is no `tool_use_id`, `permission_rule_match`, or `permission_rule` on this event.** Do not
key Discord buttons on a field the payload does not carry. Mint an approval ID in the bridge and
keep the correlation server side:

```
approval_id
  -> session_id
  -> cwd
  -> tool_name
  -> canonicalized tool_input digest
  -> permission_suggestions
  -> expires_at
```

Accept only the first valid answer for an approval ID, disable the buttons once answered, and reject
replays, double clicks, and stale buttons left over from a bridge restart.

Answer `200` with:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": { "behavior": "allow" }
  }
}
```

`decision` is `{"behavior": "allow", "updatedInput"?, "updatedPermissions"?}` or
`{"behavior": "deny", "message"?, "interrupt"?}`.

**Persisting an "always allow" choice uses `updatedPermissions`, not `applyRule`.** Echo back the
`permission_suggestions` the event supplied, and only when the approver explicitly chose to stop
being asked.

A non-2xx response, a connection failure, or a timeout is a non-blocking error: Claude Code
continues without a decision and falls back to the normal permission flow. Silence is therefore not
a denial. Always answer 200 with an explicit `deny` before the hook timeout expires, which is why
`timeout_seconds` must stay below `hook_timeout_seconds`.
