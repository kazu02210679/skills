#!/usr/bin/env python3
"""Validate a Claude Code Discord bridge configuration."""

from __future__ import annotations

import argparse
import json
import pathlib
import posixpath
import re
import sys
from typing import Any


REQUIRED_TOP_LEVEL = ("version", "discord")
SESSION_BLOCKS = ("bridge_sessions", "terminal_sessions")
SUPPORTED_VERSIONS = {4}
SNOWFLAKE = re.compile(r"^[0-9]{17,20}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
RUNTIME_TRANSPORTS = {"agent-sdk", "cli"}

# From @anthropic-ai/claude-agent-sdk: PermissionMode.
SDK_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "bypassPermissions",
    "plan",
    "dontAsk",
    "auto",
}
# `claude --help` lists a subset of what the CLI accepts: "default" is absent
# from the choices but runs fine. Verified by invoking the CLI, not by parsing
# help text.
CLI_PERMISSION_MODES = SDK_PERMISSION_MODES | {"manual"}

# From @anthropic-ai/claude-agent-sdk: SettingSource.
SETTING_SOURCES = {"user", "project", "local"}

# From @anthropic-ai/claude-agent-sdk: EffortLevel.
EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max"}

# A consultation marker is matched against a whole line of the final message.
MARKER = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")

# Only the Agent SDK has an interactive approval callback. `claude -p` does not
# fire the PermissionRequest hook; PreToolUse is the only hook that runs.
BRIDGE_APPROVAL_TRANSPORTS = {"can-use-tool"}
TERMINAL_APPROVAL_TRANSPORTS = {"permission-request-hook"}

# Modes that never reach the approval callback for a non-preapproved tool.
APPROVAL_INCOMPATIBLE_MODES = {"bypassPermissions", "dontAsk"}
# Modes that reach it for some tools only.
APPROVAL_PARTIAL_MODES = {"acceptEdits", "auto", "plan"}
APPROVAL_COVERAGE = {"all-prompts", "partial"}

MAX_HOOK_TIMEOUT_SECONDS = 600
NOTIFICATION_FLAGS = ("on_completion", "on_idle_prompt", "on_permission_request")
SECRET_BEARING_KEYS = ("token", "secret", "password", "api_key", "apikey")

DISCORD_KEYS = {
    "guild_id",
    "command_channel_ids",
    "notification_channel_id",
    "operator_user_ids",
    "approver_user_ids",
    "token_env",
}
BRIDGE_KEYS = {
    "enabled",
    "transport",
    "workspace_root",
    "projects",
    "permission_mode",
    "setting_sources",
    "allowed_tools",
    "disallowed_tools",
    "max_concurrent_sessions",
    "model",
    "effort",
    "run_timeout_seconds",
    "consult",
    "outputs",
    "sandbox",
    "approval",
}
CONSULT_KEYS = {"enabled", "marker"}
OUTPUTS_KEYS = {"dir", "max_attachment_bytes"}
TERMINAL_KEYS = {
    "enabled",
    "listen_host",
    "listen_port",
    "shared_secret_env",
    "notifications",
    "approval",
}
SANDBOX_KEYS = {
    "enabled",
    "fail_if_unavailable",
    "allow_unsandboxed_commands",
    "auto_allow_bash_if_sandboxed",
}
APPROVAL_KEYS = {
    "enabled",
    "transport",
    "coverage",
    "timeout_seconds",
    "on_timeout",
    "hook_timeout_seconds",
}


def _unknown_keys(
    document: dict[str, Any], allowed: set[str], location: str, errors: list[str]
) -> None:
    for key in document:
        if key not in allowed:
            errors.append(f"{location} has unknown key '{key}'")


def _mapping(document: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


def _snowflake(value: Any, location: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not SNOWFLAKE.fullmatch(value):
        errors.append(f"{location} must be a Discord ID string of 17 to 20 digits")


def _snowflake_list(
    value: Any, location: str, errors: list[str], *, require_nonempty: bool
) -> None:
    if not isinstance(value, list):
        errors.append(f"{location} must be an array")
        return
    if require_nonempty and not value:
        errors.append(
            f"{location} must not be empty; an empty allowlist exposes the host "
            "to every member of the guild"
        )
    seen: set[str] = set()
    for index, item in enumerate(value):
        _snowflake(item, f"{location}[{index}]", errors)
        if isinstance(item, str):
            if item in seen:
                errors.append(f"{location} contains duplicate id '{item}'")
            seen.add(item)


def _env_name(value: Any, location: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not ENV_NAME.fullmatch(value):
        errors.append(
            f"{location} must be an UPPER_SNAKE_CASE environment variable name, "
            "not the secret itself"
        )


def _bool(value: Any, location: str, errors: list[str]) -> bool | None:
    if not isinstance(value, bool):
        errors.append(f"{location} must be a boolean")
        return None
    return value


def _positive_int(value: Any, location: str, errors: list[str]) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        errors.append(f"{location} must be a positive integer")
        return None
    return value


def _string_list(value: Any, location: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        errors.append(f"{location} must be an array of non-empty strings")


def _normalize(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/")).rstrip("/") or "/"


def _is_absolute(path: str) -> bool:
    return path.startswith("/") or re.fullmatch(r"[A-Za-z]:[\\/].*", path) is not None


def _is_within(child: str, parent: str) -> bool:
    normalized_child = _normalize(child)
    normalized_parent = _normalize(parent)
    if normalized_child == normalized_parent:
        return True
    return normalized_child.startswith(f"{normalized_parent}/")


def _reject_inline_secrets(document: Any, errors: list[str], path: str = "") -> None:
    if isinstance(document, dict):
        for key, value in document.items():
            location = f"{path}.{key}" if path else str(key)
            lowered = str(key).lower()
            if lowered.endswith("_env"):
                continue
            if any(marker in lowered for marker in SECRET_BEARING_KEYS) and isinstance(
                value, str
            ):
                errors.append(
                    f"{location} holds an inline secret; use a '{key}_env' "
                    "environment variable name instead"
                )
                continue
            _reject_inline_secrets(value, errors, location)
    elif isinstance(document, list):
        for index, item in enumerate(document):
            _reject_inline_secrets(item, errors, f"{path}[{index}]")


def _validate_discord(discord: dict[str, Any], errors: list[str]) -> None:
    _unknown_keys(discord, DISCORD_KEYS, "discord", errors)
    _snowflake(discord.get("guild_id"), "discord.guild_id", errors)
    _snowflake_list(
        discord.get("command_channel_ids"),
        "discord.command_channel_ids",
        errors,
        require_nonempty=True,
    )
    _snowflake_list(
        discord.get("operator_user_ids"),
        "discord.operator_user_ids",
        errors,
        require_nonempty=True,
    )
    _env_name(discord.get("token_env"), "discord.token_env", errors)
    if "notification_channel_id" in discord:
        _snowflake(
            discord.get("notification_channel_id"),
            "discord.notification_channel_id",
            errors,
        )


def _validate_sandbox(sandbox: Any, errors: list[str]) -> None:
    location = "bridge_sessions.sandbox"
    if not isinstance(sandbox, dict):
        errors.append(f"{location} must be an object")
        return
    _unknown_keys(sandbox, SANDBOX_KEYS, location, errors)
    for key in SANDBOX_KEYS:
        if key in sandbox:
            _bool(sandbox[key], f"{location}.{key}", errors)

    if sandbox.get("enabled") is not True:
        return
    if sandbox.get("allow_unsandboxed_commands") is not False:
        errors.append(
            f"{location}.allow_unsandboxed_commands must be false when the "
            "sandbox is enabled; the documented default is true, which lets a "
            "command opt out of the sandbox and sends the decision back to the "
            "permission system"
        )
    if sandbox.get("fail_if_unavailable") is not True:
        errors.append(
            f"{location}.fail_if_unavailable must be true when the sandbox is "
            "enabled; the default differs by layer (true on the SDK "
            "Options.sandbox path, false in Claude Code settings), so state the "
            "containment posture here instead of inheriting it"
        )


def _validate_consult(consult: Any, errors: list[str]) -> None:
    location = "bridge_sessions.consult"
    if not isinstance(consult, dict):
        errors.append(f"{location} must be an object")
        return
    _unknown_keys(consult, CONSULT_KEYS, location, errors)
    if _bool(consult.get("enabled"), f"{location}.enabled", errors) is not True:
        return
    marker = consult.get("marker")
    if not isinstance(marker, str) or not MARKER.fullmatch(marker):
        errors.append(
            f"{location}.marker must be an UPPER_SNAKE_CASE token of at least 4 "
            "characters and no whitespace; it is matched against a whole line of "
            "the final assistant message"
        )


def _validate_outputs(outputs: Any, errors: list[str]) -> None:
    location = "bridge_sessions.outputs"
    if not isinstance(outputs, dict):
        errors.append(f"{location} must be an object")
        return
    _unknown_keys(outputs, OUTPUTS_KEYS, location, errors)
    directory = outputs.get("dir")
    if not isinstance(directory, str) or not directory.strip():
        errors.append(f"{location}.dir must be a non-empty string")
    elif _is_absolute(directory) or _normalize(directory).startswith(".."):
        errors.append(
            f"{location}.dir must be a relative path inside the project; only "
            "files under it are attached to Discord"
        )
    _positive_int(
        outputs.get("max_attachment_bytes"), f"{location}.max_attachment_bytes", errors
    )


def _validate_approval(
    approval: dict[str, Any],
    origin: str,
    permission_mode: Any,
    discord: dict[str, Any],
    errors: list[str],
) -> bool:
    location = f"{origin}.approval"
    _unknown_keys(approval, APPROVAL_KEYS, location, errors)
    if _bool(approval.get("enabled"), f"{location}.enabled", errors) is not True:
        return False

    allowed = (
        BRIDGE_APPROVAL_TRANSPORTS
        if origin == "bridge_sessions"
        else TERMINAL_APPROVAL_TRANSPORTS
    )
    transport = approval.get("transport")
    if transport not in allowed:
        detail = ""
        if origin == "bridge_sessions" and transport == "permission-request-hook":
            detail = (
                "; `claude -p` does not fire the PermissionRequest hook, so a "
                "CLI-driven bridge session has no approval path"
            )
        errors.append(f"{location}.transport must be one of {sorted(allowed)}{detail}")
        transport = None

    _snowflake_list(
        discord.get("approver_user_ids"),
        "discord.approver_user_ids",
        errors,
        require_nonempty=True,
    )

    if approval.get("on_timeout") != "deny":
        errors.append(
            f"{location}.on_timeout must be 'deny'; a missing, late, or failed "
            "answer is not treated as a denial by Claude Code, so the bridge "
            "has to send one"
        )

    timeout = _positive_int(
        approval.get("timeout_seconds"), f"{location}.timeout_seconds", errors
    )

    if transport == "permission-request-hook":
        hook_timeout = _positive_int(
            approval.get("hook_timeout_seconds"),
            f"{location}.hook_timeout_seconds",
            errors,
        )
        if hook_timeout is not None:
            if hook_timeout > MAX_HOOK_TIMEOUT_SECONDS:
                errors.append(
                    f"{location}.hook_timeout_seconds must not exceed "
                    f"{MAX_HOOK_TIMEOUT_SECONDS}"
                )
            if timeout is not None and timeout >= hook_timeout:
                errors.append(
                    f"{location}.timeout_seconds must be below "
                    f"{location}.hook_timeout_seconds so the bridge can answer "
                    "with an explicit deny before Claude Code abandons the hook"
                )
    elif "hook_timeout_seconds" in approval:
        errors.append(
            f"{location}.hook_timeout_seconds applies only to the "
            "'permission-request-hook' transport"
        )

    coverage = approval.get("coverage")
    if coverage is not None and coverage not in APPROVAL_COVERAGE:
        errors.append(f"{location}.coverage must be one of {sorted(APPROVAL_COVERAGE)}")
        coverage = None

    if origin == "bridge_sessions":
        if permission_mode in APPROVAL_INCOMPATIBLE_MODES:
            errors.append(
                f"bridge_sessions.permission_mode '{permission_mode}' never "
                f"reaches the approval callback: a tool that is not already "
                "allowed is decided without a prompt. Choose 'default' or "
                f"disable {location}"
            )
        elif permission_mode in APPROVAL_PARTIAL_MODES and coverage != "partial":
            errors.append(
                f"bridge_sessions.permission_mode '{permission_mode}' approves "
                "some tools without prompting, so Discord does not see every "
                f"tool call. Set {location}.coverage to 'partial' to accept "
                "that, or use 'default'"
            )
        elif permission_mode == "default" and coverage == "partial":
            errors.append(
                f"{location}.coverage 'partial' contradicts permission_mode "
                "'default', which prompts for everything not pre-approved"
            )

    return True


def _validate_bridge_sessions(
    block: dict[str, Any], discord: dict[str, Any], errors: list[str]
) -> None:
    _unknown_keys(block, BRIDGE_KEYS, "bridge_sessions", errors)

    transport = block.get("transport")
    if transport not in RUNTIME_TRANSPORTS:
        errors.append(
            f"bridge_sessions.transport must be one of {sorted(RUNTIME_TRANSPORTS)}"
        )
        transport = None

    workspace_root = block.get("workspace_root")
    if not isinstance(workspace_root, str) or not workspace_root.strip():
        errors.append("bridge_sessions.workspace_root must be a non-empty string")
        workspace_root = None
    elif not _is_absolute(workspace_root):
        errors.append("bridge_sessions.workspace_root must be an absolute path")
        workspace_root = None

    projects = block.get("projects")
    if not isinstance(projects, dict) or not projects:
        errors.append(
            "bridge_sessions.projects must be a non-empty object of name to path"
        )
    else:
        for name, path in projects.items():
            location = f"bridge_sessions.projects['{name}']"
            if not isinstance(path, str) or not path.strip():
                errors.append(f"{location} must be a non-empty string")
                continue
            if not _is_absolute(path):
                errors.append(f"{location} must be an absolute path")
                continue
            if workspace_root and not _is_within(path, workspace_root):
                errors.append(
                    f"{location} escapes bridge_sessions.workspace_root "
                    f"('{workspace_root}')"
                )

    permission_mode = block.get("permission_mode")
    allowed_modes = (
        SDK_PERMISSION_MODES if transport == "agent-sdk" else CLI_PERMISSION_MODES
    )
    if permission_mode not in allowed_modes:
        errors.append(
            f"bridge_sessions.permission_mode '{permission_mode}' is not "
            f"accepted by the {transport or 'selected'} transport; use one of "
            f"{sorted(allowed_modes)}"
        )
        permission_mode = None

    setting_sources = block.get("setting_sources")
    if setting_sources is None:
        errors.append(
            "bridge_sessions.setting_sources must be set explicitly; omitting it "
            "loads user, project, and local settings, which can grant a tool "
            "through an existing rule or hook before the approval path runs"
        )
    elif not isinstance(setting_sources, list):
        errors.append("bridge_sessions.setting_sources must be an array")
    else:
        for index, source in enumerate(setting_sources):
            if source not in SETTING_SOURCES:
                errors.append(
                    f"bridge_sessions.setting_sources[{index}] must be one of "
                    f"{sorted(SETTING_SOURCES)}"
                )

    for key in ("allowed_tools", "disallowed_tools"):
        if key in block:
            _string_list(block[key], f"bridge_sessions.{key}", errors)

    if "max_concurrent_sessions" in block:
        _positive_int(
            block.get("max_concurrent_sessions"),
            "bridge_sessions.max_concurrent_sessions",
            errors,
        )

    model = block.get("model")
    if not isinstance(model, str) or not model.strip():
        errors.append(
            "bridge_sessions.model must be a non-empty string; pass it on every "
            "turn instead of inheriting whatever the host's Claude Code is set to"
        )

    effort = block.get("effort")
    if effort is not None and effort not in EFFORT_LEVELS:
        errors.append(
            f"bridge_sessions.effort must be one of {sorted(EFFORT_LEVELS)}"
        )

    if "run_timeout_seconds" in block:
        _positive_int(
            block.get("run_timeout_seconds"),
            "bridge_sessions.run_timeout_seconds",
            errors,
        )

    if "consult" in block:
        _validate_consult(block["consult"], errors)

    if "outputs" in block:
        _validate_outputs(block["outputs"], errors)

    if "sandbox" in block:
        _validate_sandbox(block["sandbox"], errors)

    if "approval" in block:
        approval = _mapping(block, "approval", errors)
        approval_enabled = (
            _validate_approval(
                approval, "bridge_sessions", permission_mode, discord, errors
            )
            if approval
            else False
        )
        if approval_enabled and transport != "agent-sdk":
            errors.append(
                "bridge_sessions.approval requires transport 'agent-sdk'. The "
                "CLI transport has no approval path: `claude -p` does not fire "
                "the PermissionRequest hook"
            )


def _validate_terminal_sessions(
    block: dict[str, Any], discord: dict[str, Any], errors: list[str]
) -> None:
    _unknown_keys(block, TERMINAL_KEYS, "terminal_sessions", errors)

    if block.get("listen_host") not in LOOPBACK_HOSTS:
        errors.append(
            "terminal_sessions.listen_host must be loopback "
            f"({sorted(LOOPBACK_HOSTS)}); binding elsewhere exposes the hook "
            "endpoint beyond this host"
        )
    port = _positive_int(
        block.get("listen_port"), "terminal_sessions.listen_port", errors
    )
    if port is not None and port > 65535:
        errors.append("terminal_sessions.listen_port must be a valid TCP port")
    _env_name(
        block.get("shared_secret_env"), "terminal_sessions.shared_secret_env", errors
    )

    notifications = block.get("notifications")
    if notifications is None:
        notifications = {}
    elif not isinstance(notifications, dict):
        errors.append("terminal_sessions.notifications must be an object")
        notifications = {}
    else:
        _unknown_keys(
            notifications, set(NOTIFICATION_FLAGS), "terminal_sessions.notifications", errors
        )
    for flag in NOTIFICATION_FLAGS:
        if flag in notifications:
            _bool(notifications[flag], f"terminal_sessions.notifications.{flag}", errors)
    if any(
        notifications.get(flag) is True for flag in NOTIFICATION_FLAGS
    ) and "notification_channel_id" not in discord:
        errors.append(
            "discord.notification_channel_id is required when any "
            "terminal_sessions.notifications flag is enabled"
        )

    if "approval" in block:
        _validate_approval(
            _mapping(block, "approval", errors),
            "terminal_sessions",
            None,
            discord,
            errors,
        )


def validate_document(document: Any) -> list[str]:
    """Return every trust-boundary and contract error in a bridge config."""

    errors: list[str] = []
    if not isinstance(document, dict):
        return ["configuration must be a JSON object"]

    _unknown_keys(
        document, set(REQUIRED_TOP_LEVEL) | set(SESSION_BLOCKS), "configuration", errors
    )
    for key in REQUIRED_TOP_LEVEL:
        if key not in document:
            errors.append(f"missing required key '{key}'")

    if document.get("version") not in SUPPORTED_VERSIONS:
        errors.append(f"version must be one of {sorted(SUPPORTED_VERSIONS)}")

    _reject_inline_secrets(document, errors)

    discord = _mapping(document, "discord", errors)
    _validate_discord(discord, errors)

    enabled_blocks: list[str] = []
    for name in SESSION_BLOCKS:
        if name not in document:
            continue
        block = _mapping(document, name, errors)
        if not block:
            continue
        if _bool(block.get("enabled"), f"{name}.enabled", errors) is not True:
            continue
        enabled_blocks.append(name)
        if name == "bridge_sessions":
            _validate_bridge_sessions(block, discord, errors)
        else:
            _validate_terminal_sessions(block, discord, errors)

    if not enabled_blocks:
        errors.append(
            "at least one of bridge_sessions or terminal_sessions must be enabled"
        )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config_path", type=pathlib.Path)
    args = parser.parse_args(argv)

    try:
        document = json.loads(args.config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"Unable to read bridge config: {exc}", file=sys.stderr)
        return 1

    errors = validate_document(document)
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print(f"Bridge config is invalid: {len(errors)} error(s).", file=sys.stderr)
        return 1

    enabled = [
        name
        for name in SESSION_BLOCKS
        if isinstance(document.get(name), dict)
        and document[name].get("enabled") is True
    ]
    print(
        "Bridge config is valid: "
        f"{len(document['discord']['operator_user_ids'])} operator(s), "
        f"enabled: {', '.join(enabled)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
