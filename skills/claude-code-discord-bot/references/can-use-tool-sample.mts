// Compile-checked source for the canUseTool example in bridge-contract.md.
//
// This file is type-checked in CI against a pinned @anthropic-ai/claude-agent-sdk
// with `tsc --noEmit`. Keep the reference snippet and this file identical: a
// prose example nobody compiles is how the callback signature and the approval
// answer type both went wrong.

import { query } from "@anthropic-ai/claude-agent-sdk";

/**
 * What a Discord approver came back with. Explicit and discriminated so the
 * deny branch cannot accidentally read fields that only exist on allow.
 */
type ApprovalAnswer =
  | { decision: "deny" }
  | {
      decision: "allow";
      /** Set only when the approver edited the arguments before allowing. */
      editedInput?: Record<string, unknown>;
      /** True only when the approver chose "always allow". */
      persistPermission?: boolean;
    };

interface ApprovalRequest {
  /** Correlates the pending approval with the tool call inside the bridge. */
  toolUseID: string;
  /** Prompt sentence Claude Code already rendered, when it supplied one. */
  prompt: string;
  /** Short noun phrase suitable for a button label. */
  label: string;
  toolName: string;
  input: Record<string, unknown>;
  signal: AbortSignal;
}

declare function askDiscord(request: ApprovalRequest): Promise<ApprovalAnswer>;

export function runTurn(
  userMessage: string,
  projectPath: string,
  storedSessionId: string | undefined,
) {
  return query({
    prompt: userMessage,
    options: {
      cwd: projectPath,
      resume: storedSessionId, // omit on the first turn
      permissionMode: "default",
      settingSources: ["project"], // omitting this loads user + project + local
      allowedTools: ["Read", "Grep", "Glob"],

      canUseTool: async (toolName, input, options) => {
        const answer = await askDiscord({
          toolUseID: options.toolUseID,
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
          updatedPermissions: answer.persistPermission
            ? options.suggestions
            : undefined,
        };
      },
    },
  });
}
