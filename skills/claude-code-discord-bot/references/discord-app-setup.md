# Discord app setup

Manual steps the user performs, plus the platform limits the bridge designs around. Walk the user
through these; the agent cannot click the portal for them. Collect every value in
[Values the bridge needs](#values-the-bridge-needs) before writing config, so setup is not
interrupted halfway to go hunting for an ID.

## Create the application

1. Open the Discord Developer Portal, choose **New Application**, and name it.
2. Under **Bot**, choose **Reset Token** and copy the token once. It is shown only at that moment;
   losing it means resetting again, which invalidates the old one.
3. Export it under the name recorded in `discord.token_env`.

The bot token is a credential equivalent to a password for the bot account. It goes in the
environment or a secret manager, never in the repository, never in a Discord message, and never in
a screenshot shared for debugging.

## Values the bridge needs

Five values, and only the first is a secret.

| Value | Where it comes from | Used for |
|---|---|---|
| Bot token | **Bot → Reset Token** | authenticating the gateway connection |
| Application ID | **General Information → Application ID** | registering slash commands |
| Guild ID | right-click the server | scoping commands, rejecting other guilds |
| Channel IDs | right-click each channel | `command_channel_ids`, `notification_channel_id` |
| Your user ID | right-click your name | `operator_user_ids`, `approver_user_ids` |

The Application ID is not the bot token. It is a public identifier, safe to commit.

### Turn on Developer Mode to copy IDs

IDs are invisible until Developer Mode is on.

- Desktop and web: **User Settings → Advanced → Developer Mode**.
- Mobile: **Settings → Advanced → Developer Mode**.

Then right-click, or long-press on mobile:

- the server icon or name → **Copy Server ID**;
- a channel → **Copy Channel ID**;
- your own name in the member list → **Copy User ID**.

Every one is a numeric snowflake of 17 to 20 digits. The validator rejects anything else, which
catches the common mistake of pasting a channel *name* instead of its ID.

### Record them

Secrets in the environment, identifiers in `discord-bridge.json`:

```bash
# .env, gitignored, never committed
DISCORD_BOT_TOKEN=...
CLAUDE_DISCORD_HOOK_TOKEN=...   # only when terminal_sessions is enabled
```

Add `.env` to `.gitignore` before writing the token into it, not after. A token committed once is
compromised even if the next commit removes it; reset it in the portal rather than editing history.

The non-secret IDs go in `discord-bridge.json` under `discord`. Generate the hook shared secret
rather than inventing one:

```bash
openssl rand -hex 32
```

## Privileged intents

Under **Bot → Privileged Gateway Intents**:

- **Message Content** is required only to read the text of ordinary messages. Slash commands and
  interaction payloads carry their arguments without it.
- **Server Members** and **Presence** are not needed. Leave them off.

Prefer slash commands. They avoid the privileged intent, they scope cleanly to a guild, and they
give the operator allowlist a natural place to run before any work starts.

With discord.js, the non-privileged setup is `GatewayIntentBits.Guilds` alone. Reading message text
adds `GuildMessages` and `MessageContent`.

## Invite the bot

Under **OAuth2 → URL Generator**:

- Scopes: `bot`, `applications.commands`.
- Bot permissions: View Channels, Send Messages, Send Messages in Threads, Create Public Threads,
  Read Message History, Embed Links, Attach Files.

Grant nothing further. The bridge does not need Manage Messages, Mention Everyone, or any moderation
permission. Open the generated URL and invite the bot to the one guild in `discord.guild_id`.

Restrict the bot's channel access in the guild's own channel permissions as well, so a
misconfigured bridge still cannot read channels the user did not intend.

## Register slash commands

Slash commands are registered through the API, not the portal. Register them **per guild**: guild
commands appear immediately, while global commands can take up to an hour to propagate, which reads
as "the bot is broken" during setup.

This needs the Application ID and the Guild ID together, which is why both are collected above.
With discord.js the call is `REST().setToken(token).put(Routes.applicationGuildCommands(applicationId, guildId), { body: commands })`.

Re-register after changing a command's name, description, or options. Adding a handler alone does
not update what Discord shows.

## Run it

The bridge is a long-lived process. Whatever the project's start script is, the first run is a
verification run, not a deployment.

1. Validate the config first. A bridge that starts with a bad trust boundary is worse than one that
   does not start:

   ```bash
   python <skill-dir>/scripts/validate_bridge_config.py discord-bridge.json
   ```

2. Load the environment and start the process, for example `npm start`. On Windows from PowerShell
   or cmd this is `npm.cmd start`; paths with non-ASCII characters work but must be quoted.
3. Confirm the bot shows as online in the guild member list. Offline means the token is wrong or the
   gateway connection failed; read the process output rather than guessing.
4. Walk the verification list below.

For an always-on bridge, use whatever supervises long-running processes on that host: a systemd
user unit on Linux, `launchd` on macOS, Task Scheduler or a service wrapper on Windows. Say plainly
that a bridge running under a terminal dies with the terminal, and that a sleeping host stops
answering Discord.

## Platform limits the bridge must respect

| Limit | Value | Consequence |
|---|---|---|
| Message content | 2000 characters | Chunk long replies, or attach the remainder as a file |
| Embed description | 4096 characters | Long tool output does not fit one embed |
| Total embed payload | 6000 characters, 10 embeds per message | Budget before serializing |
| Buttons | 5 per action row, 5 action rows | Allow, Deny, and Always allow fit one row |
| Interaction acknowledgement | 3 seconds | Defer the reply, then resolve it when the human answers |
| Deferred interaction follow-up | 15 minutes | Approval timeouts must stay well inside this |

The 3 second and 15 minute rules decide the approval design: acknowledge the button immediately,
hold the approval in the bridge's own state, and keep `approval.timeout_seconds` below both the
follow-up window and the hook timeout.

## Verification

Confirm in a live guild before handing over:

- the bot appears online and responds in an allowed channel;
- slash commands appear in the command picker;
- a non-operator user is ignored;
- an allowed channel creates a thread, and a second message in that thread keeps context;
- an approval prompt renders the tool name and input, and both buttons resolve;
- a reply longer than 2000 characters arrives complete, chunked or attached.

## When it does not work

| Symptom | Cause |
|---|---|
| Bot offline | wrong or reset token; the process is not running |
| Slash commands missing | registered globally instead of per guild, or never registered |
| Bot online but silent on plain messages | Message Content intent is off; use slash commands |
| Bot ignores you | your user ID is not in `operator_user_ids`, or the channel is not allowlisted |
| Validator rejects an ID | a channel or server *name* was pasted instead of its numeric ID |
| Approval never appears | see the failure list in `SKILL.md`: transport, then permission mode, then `setting_sources` |
