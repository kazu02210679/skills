# Bridge contract

The data contract between Discord, the bridge process, and Claude Code.

Verified against `@anthropic-ai/claude-agent-sdk` 0.3.220 type declarations and Claude Code CLI
2.1.220, by reading the shipped declarations and by running the CLI, not by reading prose. Re-verify
with `scripts/check_sdk_contract.py` before trusting an older copy of this file; these shapes have
changed before.

## Two session origins, and only one approval path

A bridge-owned session and a terminal-started session need different plumbing, so the config keeps
them apart.

| Flow | `bridge_sessions`, `agent-sdk` | `bridge_sessions`, `cli` | `terminal_sessions` |
|---|---|---|---|
| Instruct | `query()` | `claude -p` | not applicable |
| Notify | the SDK message stream | stream-json events | `Stop` and `Notification` hooks |
| Approve | the `canUseTool` callback | **none** | the `PermissionRequest` hook |

**The `PermissionRequest` hook does not fire under `claude -p`.** Measured, not inferred: with a
`PermissionRequest` and a `PreToolUse` hook both registered through `--settings`, a `Bash` call under
`permission_mode` `default` and again under `manual`, with a clean `HOME`, fired `PreToolUse` every
time and `PermissionRequest` never.

**This Skill's CLI transport therefore implements no approval path**, and the validator rejects
approval on it rather than letting a bridge report a human-in-the-loop channel that silently never
prompts. That is a scope decision, not a claim that Claude Code offers no route at all. Two other designs
exist and are simply out of scope here:

- a `PreToolUse` hook returning `permissionDecision: "defer"` (`HookPermissionDecision` is
  `allow | deny | ask | defer`), with an external UI collecting the answer and resuming. This fires
  on every tool call rather than only on ones needing a decision, so Discord would see the full
  volume;
- a permission-prompt transport, where the prompt is routed to a tool the bridge exposes. This is
  not exotic: `canUseTool` is itself implemented this way. The SDK passes
  `--permission-prompt-tool stdio` to the CLI when the callback is set, and rejects the combination
  of `canUseTool` and `permissionPromptToolName` because they are the same channel.

Either would be a separate transport with its own contract. Build one deliberately if the user
wants CLI approval; do not imply the current CLI transport already gates anything. Do not conclude
a CLI flag is absent because `claude --help` omits it — the help output is not the complete flag
list, as `--permission-mode default` already showed.

## Config schema

`discord-bridge.json` at the user's project root. `scripts/validate_bridge_config.py` enforces it,
and rejects unknown keys so a typo such as `fail_if_unavailble` cannot pass silently.

```json
{
  "version": 3,
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
    "sandbox": {
      "enabled": true,
      "fail_if_unavailable": true,
      "allow_unsandboxed_commands": false
    },
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

| Transport | Accepted values |
|---|---|
| Agent SDK (`PermissionMode`) | `default`, `acceptEdits`, `bypassPermissions`, `plan`, `dontAsk`, `auto` |
| CLI (`--permission-mode`) | the same six, plus `manual` |

`claude --help` lists its choices without `default`, but the CLI accepts `--permission-mode default`
and runs normally. Do not treat the help enumeration as the accepted set; the validator does not.

### Which modes actually reach Discord

The approval callback only sees a tool call that reaches a prompt. The mode decides how many do.

| Mode | Reaches `canUseTool` | Config rule |
|---|---|---|
| `default` | everything not pre-approved | the canonical choice |
| `acceptEdits` | not edits or common filesystem commands | requires `coverage: "partial"` |
| `auto` | classifier decides most calls first | requires `coverage: "partial"` |
| `plan` | no execution happens | requires `coverage: "partial"` |
| `dontAsk` | nothing; unlisted tools are denied outright | rejected with approval enabled |
| `bypassPermissions` | nothing; no prompts at all | rejected with approval enabled |

`allowed_tools` narrows this further: a tool listed there, or granted by a loaded settings source, is
auto-approved and never reaches Discord. Say which tools the operator will actually be asked about,
rather than implying every tool call is gated.

### Setting sources

`setting_sources` maps to the SDK `settingSources` option, whose values are `user`, `project`, and
`local`. **Omitting it loads all three.** For a bridge that executes code on behalf of a chat
message, that silently pulls in whatever hooks and permission rules already live in
`~/.claude/settings.json` and `.claude/settings.local.json`, which can grant a tool before the
approval path ever runs.

Set it explicitly. `["project"]` keeps `CLAUDE.md` and checked-in project settings, which is the
usual choice. `[]` is full isolation; the managed-settings policy tier is still read.

### Sandbox

`SandboxSettings` is what `Options.sandbox` takes, and it carries `enabled`, `failIfUnavailable`,
`autoAllowBashIfSandboxed`, `allowUnsandboxedCommands`, `network`, `filesystem`, and `credentials`.
The config uses snake_case names and the bridge converts them.

The published SDK reference omits `failIfUnavailable` from `SandboxSettings`, which has led a review
to conclude it is settings-only. The shipped declarations accept it on `Options.sandbox`, and
[sandbox-conversion-sample.mts](sandbox-conversion-sample.mts) compiles the whole conversion in CI
so the question is settled by the type checker rather than re-argued from prose.

#### `failIfUnavailable` defaults differ by layer

The two layers do not agree, which is why the config pins it rather than inheriting anything:

| Layer | Default when `enabled: true` | Behavior when the sandbox cannot start |
|---|---|---|
| SDK `Options.sandbox` | **`true`** | `query()` emits an error result and exits |
| Claude Code settings | **`false`** | a warning is shown and commands run unsandboxed |

The SDK injects the default rather than leaving it to the CLI: when `enabled` is `true` and
`failIfUnavailable` is undefined, it substitutes `failIfUnavailable: true` before spawning.

The validator requires `fail_if_unavailable: true` whenever the sandbox is enabled. Not because the
default is unsafe — on the SDK path it already is `true` — but because the bridge's containment
posture should be stated in its own config instead of depending on which layer happens to apply. A
config that survives a move between the SDK and the settings layer, or an upstream default change,
is worth more than one that is merely correct today.

`allowUnsandboxedCommands` is pinned for the same reason, and there the documented default is `true`:
a command can opt out of the sandbox through `dangerouslyDisableSandbox`, and the decision returns to
the permission system. Set it `false` for containment that does not depend on the model's restraint.

`network.strictAllowlist` is honored only from user, managed, or `--settings` sources; project
settings are ignored for it. Do not put it in `.claude/settings.json` and expect enforcement.

### What `workspace_root` is, and is not

`workspace_root` restricts **which project directories the bridge may open**. That is useful input
validation and the validator enforces it.

It is not a filesystem sandbox. Claude Code reads outside the working directory, Bash reaches
absolute paths, and a symlink inside the workspace can point anywhere. A config-file validator
cannot resolve symlinks on the machine that will eventually run the bridge, so it checks path shape
only. Real containment is the `sandbox` block above, a container, or a VM.

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

Anything not covered by `--allowedTools` is decided without a prompt. Use this transport only when
the user accepted that there is no approval step.

## Instruct and approve flow, Agent SDK transport

`npm install @anthropic-ai/claude-agent-sdk`

The code below is the whole of [can-use-tool-sample.mts](can-use-tool-sample.mts), which CI
type-checks under `strict` against a pinned SDK. Edit that file and copy it here, never the reverse.

`canUseTool` takes the tool name and input as **separate positional arguments** and returns a
`PermissionResult` discriminated on `behavior`. It is not a request object, and it does not return
`approved`.

```ts
import { query } from "@anthropic-ai/claude-agent-sdk";

type ApprovalAnswer =
  | { decision: "deny" }
  | {
      decision: "allow";
      editedInput?: Record<string, unknown>;
      persistPermission?: boolean;
    };

declare function askDiscord(request: {
  toolUseID: string;
  prompt: string;
  label: string;
  toolName: string;
  input: Record<string, unknown>;
  signal: AbortSignal;
}): Promise<ApprovalAnswer>;

const q = query({
  prompt: userMessage,
  options: {
    cwd: projectPath,
    resume: storedSessionId,          // omit on the first turn
    permissionMode: "default",
    settingSources: ["project"],      // omitting this loads user + project + local
    allowedTools: ["Read", "Grep", "Glob"],

    canUseTool: async (toolName, input, options) => {
      const answer = await askDiscord({
        toolUseID: options.toolUseID,
        // `title` is the prompt sentence Claude Code already rendered, for example
        // "Claude wants to read foo.txt". Prefer it over rebuilding text yourself.
        prompt: options.title ?? toolName,
        label: options.displayName ?? toolName,
        toolName,
        input,
        signal: options.signal,
      });

      if (answer.decision === "deny") {
        return { behavior: "deny", message: "Denied in Discord" };
      }

      return {
        behavior: "allow",
        updatedInput: answer.editedInput,
        updatedPermissions: answer.persistPermission ? options.suggestions : undefined,
      };
    },
  },
});
```

The callback options also carry `toolUseID`, `requestId`, `agentID`, `blockedPath`,
`decisionReason`, and `matchedAskRule`. **Correlate with `toolUseID`**, which the SDK path does
supply; the hook path is the one with no tool use ID. Never put either value in a Discord button ID
where a guild member can read or forge it: mint an unguessable nonce for the button and keep the
mapping in the bridge.

`canUseTool` runs only when the permission flow falls through to a prompt, and it has no deadline of
its own: an unanswered prompt blocks that session indefinitely. The bridge owns the timeout. Resolve
with `{ behavior: "deny", message: "Approval timed out" }` when the window expires, and honor
`signal` so an aborted session does not leak a pending approval.

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

For sessions the user starts in their own terminal. `PermissionRequest` fires only when a tool call
needs a decision, which is what a human-in-the-loop channel wants. `PreToolUse` fires on every tool
call and would flood Discord.

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
