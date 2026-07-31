#!/usr/bin/env python3
"""Check the documented Claude Code contract against the installed SDK and CLI.

The bridge depends on shapes this repository does not own: the Agent SDK
`canUseTool` callback, `PermissionMode`, `SettingSource`, and the
`PermissionRequest` hook payload and decision. Those have changed before, and a
stale reference file silently produces a bridge whose approval flow never works.

Run this against a real install to detect drift:

    python check_sdk_contract.py \
      --sdk-types node_modules/@anthropic-ai/claude-agent-sdk/sdk.d.ts \
      --cli claude

Either source may be omitted; only what is supplied is checked.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys


# Kept in sync with references/bridge-contract.md.
EXPECTED_SDK_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "bypassPermissions",
    "plan",
    "dontAsk",
    "auto",
}
EXPECTED_CLI_PERMISSION_MODES = {
    "acceptEdits",
    "auto",
    "bypassPermissions",
    "manual",
    "dontAsk",
    "plan",
}
EXPECTED_SETTING_SOURCES = {"user", "project", "local"}
EXPECTED_PERMISSION_REQUEST_FIELDS = {"tool_name", "tool_input", "permission_suggestions"}
FORBIDDEN_PERMISSION_REQUEST_FIELDS = {
    "tool_use_id",
    "permission_rule",
    "permission_rule_match",
}


def _union_members(declaration: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", declaration))


def _find_type(text: str, name: str) -> str | None:
    """Return a type declaration body, honoring braces so unions stay intact."""

    match = re.search(rf"declare type {re.escape(name)}\s*=", text)
    if match is None:
        return None
    depth = 0
    start = match.end()
    for index in range(start, len(text)):
        character = text[index]
        if character in "{([":
            depth += 1
        elif character in "})]":
            depth -= 1
        elif character == ";" and depth == 0:
            return text[start:index]
    return None


def check_sdk_types(text: str) -> list[str]:
    """Return drift between the documented contract and shipped declarations."""

    errors: list[str] = []

    modes = _find_type(text, "PermissionMode")
    if modes is None:
        errors.append("PermissionMode declaration not found")
    else:
        actual = _union_members(modes)
        if actual != EXPECTED_SDK_PERMISSION_MODES:
            errors.append(
                "PermissionMode drifted: documented "
                f"{sorted(EXPECTED_SDK_PERMISSION_MODES)}, shipped {sorted(actual)}"
            )

    sources = _find_type(text, "SettingSource")
    if sources is None:
        errors.append("SettingSource declaration not found")
    else:
        actual = _union_members(sources)
        if actual != EXPECTED_SETTING_SOURCES:
            errors.append(
                "SettingSource drifted: documented "
                f"{sorted(EXPECTED_SETTING_SOURCES)}, shipped {sorted(actual)}"
            )

    can_use_tool = _find_type(text, "CanUseTool")
    if can_use_tool is None:
        errors.append("CanUseTool declaration not found")
    else:
        if not re.match(r"\s*\(\s*toolName:\s*string\s*,", can_use_tool):
            errors.append(
                "CanUseTool no longer takes toolName as its first positional "
                "argument; the documented example is wrong"
            )
        if "input: Record<string, unknown>" not in can_use_tool:
            errors.append(
                "CanUseTool no longer takes input as its second positional argument"
            )

    permission_result = _find_type(text, "PermissionResult")
    if permission_result is None:
        errors.append("PermissionResult declaration not found")
    else:
        for token in ("behavior: 'allow'", "behavior: 'deny'"):
            if token not in permission_result:
                errors.append(f"PermissionResult no longer declares {token}")
        if "approved" in permission_result:
            errors.append(
                "PermissionResult declares 'approved'; the documented "
                "behavior-based result may be stale"
            )
        for token in ("updatedInput", "updatedPermissions", "message"):
            if token not in permission_result:
                errors.append(f"PermissionResult no longer declares '{token}'")

    hook_input = _find_type(text, "PermissionRequestHookInput")
    if hook_input is None:
        errors.append("PermissionRequestHookInput declaration not found")
    else:
        for field in sorted(EXPECTED_PERMISSION_REQUEST_FIELDS):
            if field not in hook_input:
                errors.append(
                    f"PermissionRequestHookInput no longer carries '{field}'"
                )
        for field in sorted(FORBIDDEN_PERMISSION_REQUEST_FIELDS):
            if field in hook_input:
                errors.append(
                    f"PermissionRequestHookInput now carries '{field}'; the "
                    "bridge-minted approval ID guidance may be outdated"
                )

    hook_output = _find_type(text, "PermissionRequestHookSpecificOutput")
    if hook_output is None:
        errors.append("PermissionRequestHookSpecificOutput declaration not found")
    else:
        if "updatedPermissions" not in hook_output:
            errors.append(
                "PermissionRequestHookSpecificOutput no longer declares "
                "'updatedPermissions'"
            )
        if "applyRule" in hook_output:
            errors.append(
                "PermissionRequestHookSpecificOutput declares 'applyRule'; the "
                "documented updatedPermissions guidance may be stale"
            )

    return errors


def check_cli_permission_modes(help_text: str) -> list[str]:
    """Return drift between documented and actual --permission-mode choices."""

    match = re.search(
        r"--permission-mode <mode>(.*?)(?:\n\s*--\w)", help_text, re.DOTALL
    )
    if match is None:
        return ["--permission-mode not found in CLI help output"]
    choices = _union_members(match.group(1).replace('"', "'"))
    if not choices:
        return ["--permission-mode lists no choices in CLI help output"]
    if choices != EXPECTED_CLI_PERMISSION_MODES:
        return [
            "CLI --permission-mode drifted: documented "
            f"{sorted(EXPECTED_CLI_PERMISSION_MODES)}, actual {sorted(choices)}"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk-types",
        type=pathlib.Path,
        help="path to @anthropic-ai/claude-agent-sdk/sdk.d.ts",
    )
    parser.add_argument("--cli", help="claude executable to query for --help")
    args = parser.parse_args(argv)

    if not args.sdk_types and not args.cli:
        parser.error("supply --sdk-types, --cli, or both")

    errors: list[str] = []

    if args.sdk_types:
        try:
            errors.extend(
                check_sdk_types(args.sdk_types.read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"Unable to read SDK types: {exc}")

    if args.cli:
        try:
            result = subprocess.run(
                [args.cli, "--help"],
                text=True,
                capture_output=True,
                encoding="utf-8",
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"Unable to run '{args.cli} --help': {exc}")
        else:
            errors.extend(check_cli_permission_modes(result.stdout + result.stderr))

    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print(
            f"Contract drift detected: {len(errors)} finding(s). "
            "Update references/bridge-contract.md and the validator together.",
            file=sys.stderr,
        )
        return 1

    print("Documented contract matches the installed SDK and CLI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
