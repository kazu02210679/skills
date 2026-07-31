# Discord app setup

Manual steps the user performs in the Discord Developer Portal, plus the platform limits the bridge
has to design around. Walk the user through these; the agent cannot click the portal for them.

## Create the application

1. Open the Developer Portal, choose **New Application**, and name it.
2. Under **Bot**, choose **Reset Token** and copy the token once. It is shown only at that moment.
3. Export it under the name recorded in `discord.token_env`, for example:

   ```bash
   export DISCORD_BOT_TOKEN='...'
   ```

   Put it in the shell profile or a secret manager, not in the repository.

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
hold the approval on the deferred reply, and keep `approval.timeout_seconds` below both the
follow-up window and the hook timeout.

## Verification

Confirm in a live guild before handing over:

- the bot appears online and responds in an allowed channel;
- a non-operator user is ignored;
- an allowed channel creates a thread and a second message in that thread keeps context;
- an approval prompt renders the tool name and input, and both buttons resolve;
- a reply longer than 2000 characters arrives complete, chunked or attached.
