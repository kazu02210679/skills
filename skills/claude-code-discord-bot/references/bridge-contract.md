# Bridge contract

The data contract between Discord, the bridge process, and Claude Code. Verified against the
Claude Code CLI, hooks, and Agent SDK references.

## Config schema

`discord-bridge.json` at the user's project root. `scripts/validate_bridge_config.py` enforces it.

```json
{
  "version": 1,
  "discord": {
    "guild_id": "123456789012345678",
    "command_channel_ids": ["123456789012345678"],
    "notification_channel_id": "123456789012345678",
    "operator_user_ids": ["123456789012345678"],
    "approver_user_ids": ["123456789012345678"],
    "token_env": "DISCORD_BOT_TOKEN"
  },
  "runtime": {
    "transport": "agent-sdk",
    "workspace_root": "/home/me/src",
    "projects": {
      "skills": "/home/me/src/skills"
    },
    "permission_mode": "default",
    "allowed_tools": ["Read", "Grep", "Glob"],
    "disallowed_tools": [],
    "max_concurrent_sessions": 2
  },
  "approval": {
    "enabled": true,
    "transport": "canusetool",
    "timeout_seconds": 300,
    "on_timeout": "deny"
  },
  "notifications": {
    "on_completion": true,
    "on_idle_prompt": true,
    "on_permission_request": true
  }
}
```

`runtime.transport` is `agent-sdk` or `cli`. `approval.transport` is `canusetool` for bridge-owned
sessions or `http-hook` for terminal sessions. `http-hook` adds:

```json
{
  "approval": {
    "enabled": true,
    "transport": "http-hook",
    "listen_host": "127.0.0.1",
    "listen_port": 8787,
    "shared_secret_env": "CLAUDE_DISCORD_HOOK_TOKEN",
    "hook_timeout_seconds": 600,
    "timeout_seconds": 300,
    "on_timeout": "deny"
  }
}
```

`timeout_seconds` must stay below `hook_timeout_seconds`. Claude Code treats a hook timeout or a
connection failure as a non-blocking error and continues without a decision, so the bridge has to
answer with an explicit deny while the hook is still listening.

## Rejected configurations

The validator fails, rather than warns, on each of these:

- empty `operator_user_ids`, empty `command_channel_ids`, or missing `guild_id`;
- a project path that is relative, or that escapes `workspace_root`;
- an inline `token` or `shared_secret`; only `token_env` and `shared_secret_env` are accepted;
- `permission_mode: "bypassPermissions"` together with `approval.enabled` or
  `notifications.on_permission_request`, because that mode suppresses the permission event;
- `on_timeout` other than `deny`;
- a non-loopback `listen_host`;
- `timeout_seconds` at or above `hook_timeout_seconds`, or `hook_timeout_seconds` above 600;
- a `permission_mode` the chosen transport does not accept.

`permission_mode` accepts `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`,
and `manual` on the CLI transport. The Agent SDK accepts only `default`, `plan`, `dontAsk`, and
`bypassPermissions`.

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
  --permission-mode default \
  --allowedTools "Read,Grep,Glob"
```

Resume a thread:

```bash
claude -p "<prompt>" --output-format stream-json --verbose --resume "<session_id>"
```

Headless permission prompts route through `--permission-prompt-tool <mcp tool name>` when the
bridge exposes an MCP server instead of hooks.

## Instruct flow, Agent SDK transport

`npm install @anthropic-ai/claude-agent-sdk`

```ts
import { query } from "@anthropic-ai/claude-agent-sdk";

const q = query({
  prompt: userMessage,
  options: {
    cwd: projectPath,
    resume: storedSessionId,          // omit on the first turn
    permissionMode: "default",
    allowedTools: ["Read", "Grep", "Glob"],
    canUseTool: async (request, { signal }) => {
      const approved = await askDiscord(request.tool_name, request.input, signal);
      return approved ? { approved: true } : { approved: false, reason: "Denied in Discord" };
    },
  },
});

for await (const message of q) {
  // stream tool activity and assistant text to the thread
}
```

`canUseTool` runs only when the permission flow falls through to a prompt. A tool listed in
`allowedTools` is auto-approved and never reaches Discord.

## Notify flow, hook transport

`Stop` fires after Claude finishes a turn. `Notification` fires for permission prompts, idle
prompts, and agent completion; its matcher values include `permission_prompt`, `idle_prompt`,
`agent_needs_input`, and `agent_completed`. Neither event can block.

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

`Stop` posts a body carrying `session_id`, `cwd`, `permission_mode`, and `last_assistant_message`.
Use `last_assistant_message` as the notification body. `Notification` posts `session_id`, `cwd`,
`message`, and `notification_type`. Return `204` with an empty body; these hooks need no decision.

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

Request body fields: `session_id`, `cwd`, `permission_mode`, `tool_name`, `tool_input`,
`tool_use_id`, `permission_rule_match`, `permission_rule`.

The bridge posts the decision to Discord, waits for a button press from an approver, and answers
`200` with:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": { "behavior": "allow" }
  }
}
```

`decision.behavior` is `allow` or `deny`. `decision.applyRule` optionally saves a permission rule so
the same call is not asked again; only set it when the approver explicitly chose "always allow".
A non-2xx response, a connection failure, or a timeout leaves the decision to the normal permission
flow, so always answer 200 with an explicit `deny` on timeout.
