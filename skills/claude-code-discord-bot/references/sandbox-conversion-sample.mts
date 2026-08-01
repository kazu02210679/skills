// Compile-checked conversion from the bridge config's `sandbox` block to the
// Agent SDK `Options.sandbox`.
//
// This file exists because a previous review round argued that
// `failIfUnavailable` lives only in the Claude Code settings layer and is not
// part of the public `SandboxSettings` that `Options.sandbox` accepts. The
// shipped declarations disagree, and compiling settles it: if a future SDK
// moves the field, this file stops compiling and CI says so, instead of the
// question being re-argued from prose.
//
// Type-checked in CI under `strict` against a pinned @anthropic-ai/claude-agent-sdk.

import type { Options } from "@anthropic-ai/claude-agent-sdk";

/** The `sandbox` block as it appears in discord-bridge.json. */
export interface BridgeSandboxConfig {
  enabled: boolean;
  /**
   * Defaults to false in Claude Code, which downgrades a missing sandbox to a
   * warning and runs unsandboxed. The validator requires true when enabled.
   */
  fail_if_unavailable?: boolean;
  /**
   * Defaults to true in Claude Code, which lets a command opt out of the
   * sandbox. The validator requires false when enabled.
   */
  allow_unsandboxed_commands?: boolean;
  auto_allow_bash_if_sandboxed?: boolean;
}

/**
 * Every key maps onto `Options.sandbox`. Assigning the result to
 * `Options["sandbox"]` is the assertion: it fails to compile if any of these
 * fields is not part of the public type.
 */
export function toSdkSandbox(config: BridgeSandboxConfig): Options["sandbox"] {
  return {
    enabled: config.enabled,
    failIfUnavailable: config.fail_if_unavailable,
    allowUnsandboxedCommands: config.allow_unsandboxed_commands,
    autoAllowBashIfSandboxed: config.auto_allow_bash_if_sandboxed,
  };
}

/** The containment posture the validator enforces, expressed as a value. */
export const CONTAINED: BridgeSandboxConfig = {
  enabled: true,
  fail_if_unavailable: true,
  allow_unsandboxed_commands: false,
};

export const CONTAINED_SDK_OPTIONS: Options["sandbox"] = toSdkSandbox(CONTAINED);
