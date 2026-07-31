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


REQUIRED_TOP_LEVEL = ("version", "discord", "runtime", "approval", "notifications")
SUPPORTED_VERSIONS = {1}
SNOWFLAKE = re.compile(r"^[0-9]{17,20}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
RUNTIME_TRANSPORTS = {"agent-sdk", "cli"}
APPROVAL_TRANSPORTS = {"canusetool", "http-hook"}
CLI_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "plan",
    "auto",
    "dontAsk",
    "bypassPermissions",
    "manual",
}
SDK_PERMISSION_MODES = {"default", "plan", "dontAsk", "bypassPermissions"}
MAX_HOOK_TIMEOUT_SECONDS = 600
SECRET_BEARING_KEYS = ("token", "secret", "password", "api_key", "apikey")


def _mapping(document: Any, key: str, errors: list[str]) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


def _snowflake(value: Any, location: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not SNOWFLAKE.fullmatch(value):
        errors.append(f"{location} must be a Discord ID string of 17 to 20 digits")


def _snowflake_list(
    value: Any,
    location: str,
    errors: list[str],
    *,
    require_nonempty: bool,
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


def _positive_int(value: Any, location: str, errors: list[str]) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        errors.append(f"{location} must be a positive integer")
        return None
    return value


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


def _validate_runtime(runtime: dict[str, Any], errors: list[str]) -> str | None:
    transport = runtime.get("transport")
    if transport not in RUNTIME_TRANSPORTS:
        errors.append(
            "runtime.transport must be one of "
            f"{sorted(RUNTIME_TRANSPORTS)}"
        )
        transport = None

    workspace_root = runtime.get("workspace_root")
    if not isinstance(workspace_root, str) or not workspace_root.strip():
        errors.append("runtime.workspace_root must be a non-empty string")
        workspace_root = None
    elif not _is_absolute(workspace_root):
        errors.append("runtime.workspace_root must be an absolute path")
        workspace_root = None

    projects = runtime.get("projects")
    if not isinstance(projects, dict) or not projects:
        errors.append("runtime.projects must be a non-empty object of name to path")
    else:
        for name, path in projects.items():
            location = f"runtime.projects['{name}']"
            if not isinstance(path, str) or not path.strip():
                errors.append(f"{location} must be a non-empty string")
                continue
            if not _is_absolute(path):
                errors.append(f"{location} must be an absolute path")
                continue
            if workspace_root and not _is_within(path, workspace_root):
                errors.append(
                    f"{location} escapes runtime.workspace_root "
                    f"('{workspace_root}')"
                )

    permission_mode = runtime.get("permission_mode")
    allowed_modes = (
        SDK_PERMISSION_MODES if transport == "agent-sdk" else CLI_PERMISSION_MODES
    )
    if permission_mode not in allowed_modes:
        errors.append(
            f"runtime.permission_mode '{permission_mode}' is not accepted by the "
            f"{transport or 'selected'} transport; use one of {sorted(allowed_modes)}"
        )

    for key in ("allowed_tools", "disallowed_tools"):
        value = runtime.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            errors.append(f"runtime.{key} must be an array of non-empty strings")

    if "max_concurrent_sessions" in runtime:
        _positive_int(
            runtime.get("max_concurrent_sessions"),
            "runtime.max_concurrent_sessions",
            errors,
        )

    return permission_mode if isinstance(permission_mode, str) else None


def _validate_approval(
    approval: dict[str, Any],
    discord: dict[str, Any],
    errors: list[str],
) -> bool:
    enabled = approval.get("enabled")
    if not isinstance(enabled, bool):
        errors.append("approval.enabled must be a boolean")
        return False
    if not enabled:
        return False

    transport = approval.get("transport")
    if transport not in APPROVAL_TRANSPORTS:
        errors.append(
            f"approval.transport must be one of {sorted(APPROVAL_TRANSPORTS)}"
        )
        transport = None

    _snowflake_list(
        discord.get("approver_user_ids"),
        "discord.approver_user_ids",
        errors,
        require_nonempty=True,
    )

    if approval.get("on_timeout") != "deny":
        errors.append(
            "approval.on_timeout must be 'deny'; approval has to fail closed"
        )

    timeout = _positive_int(
        approval.get("timeout_seconds"), "approval.timeout_seconds", errors
    )

    if transport == "http-hook":
        host = approval.get("listen_host")
        if host not in LOOPBACK_HOSTS:
            errors.append(
                "approval.listen_host must be loopback "
                f"({sorted(LOOPBACK_HOSTS)}); binding elsewhere exposes the "
                "approval endpoint beyond this host"
            )
        port = _positive_int(approval.get("listen_port"), "approval.listen_port", errors)
        if port is not None and port > 65535:
            errors.append("approval.listen_port must be a valid TCP port")
        _env_name(
            approval.get("shared_secret_env"), "approval.shared_secret_env", errors
        )
        hook_timeout = _positive_int(
            approval.get("hook_timeout_seconds"),
            "approval.hook_timeout_seconds",
            errors,
        )
        if hook_timeout is not None:
            if hook_timeout > MAX_HOOK_TIMEOUT_SECONDS:
                errors.append(
                    "approval.hook_timeout_seconds must not exceed "
                    f"{MAX_HOOK_TIMEOUT_SECONDS}"
                )
            if timeout is not None and timeout >= hook_timeout:
                errors.append(
                    "approval.timeout_seconds must be below "
                    "approval.hook_timeout_seconds so the bridge can answer with an "
                    "explicit deny before Claude Code abandons the hook"
                )

    return True


def _validate_notifications(
    notifications: dict[str, Any],
    discord: dict[str, Any],
    errors: list[str],
) -> bool:
    flags = ("on_completion", "on_idle_prompt", "on_permission_request")
    for flag in flags:
        if flag in notifications and not isinstance(notifications[flag], bool):
            errors.append(f"notifications.{flag} must be a boolean")
    enabled = any(notifications.get(flag) is True for flag in flags)
    if enabled and "notification_channel_id" not in discord:
        errors.append(
            "discord.notification_channel_id is required when any notification "
            "flag is enabled"
        )
    return notifications.get("on_permission_request") is True


def validate_document(document: Any) -> list[str]:
    """Return every trust-boundary and contract error in a bridge config."""

    errors: list[str] = []
    if not isinstance(document, dict):
        return ["configuration must be a JSON object"]

    for key in REQUIRED_TOP_LEVEL:
        if key not in document:
            errors.append(f"missing required key '{key}'")

    if document.get("version") not in SUPPORTED_VERSIONS:
        errors.append(f"version must be one of {sorted(SUPPORTED_VERSIONS)}")

    _reject_inline_secrets(document, errors)

    discord = _mapping(document, "discord", errors)
    runtime = _mapping(document, "runtime", errors)
    approval = _mapping(document, "approval", errors)
    notifications = _mapping(document, "notifications", errors)

    _validate_discord(discord, errors)
    permission_mode = _validate_runtime(runtime, errors)
    approval_enabled = _validate_approval(approval, discord, errors)
    permission_notice = _validate_notifications(notifications, discord, errors)

    if permission_mode == "bypassPermissions" and (
        approval_enabled or permission_notice
    ):
        errors.append(
            "runtime.permission_mode 'bypassPermissions' suppresses the permission "
            "event that approval and permission notifications depend on; choose "
            "another mode or disable those flows"
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

    runtime = document["runtime"]
    approval = document["approval"]
    print(
        "Bridge config is valid: "
        f"{len(document['discord']['operator_user_ids'])} operator(s), "
        f"{len(runtime['projects'])} project(s), "
        f"transport {runtime['transport']}, "
        f"approval {'on' if approval.get('enabled') else 'off'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
