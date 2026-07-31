from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPOSITORY_ROOT / "skills" / "claude-code-discord-bot" / "scripts"
FIXTURE_ROOT = REPOSITORY_ROOT / "evals" / "claude-code-discord-bot" / "fixtures"


def load_module(name: str):
    path = SCRIPT_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module("validate_bridge_config")
CONTRACT = load_module("check_sdk_contract")


def fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


class BridgeConfigTestCase(unittest.TestCase):
    def assertErrorMentions(self, errors: list[str], fragment: str) -> None:
        self.assertTrue(
            any(fragment in error for error in errors),
            f"expected an error containing {fragment!r}, got {errors}",
        )

    def assertNoErrorMentions(self, errors: list[str], fragment: str) -> None:
        self.assertFalse(
            any(fragment in error for error in errors),
            f"unexpected error containing {fragment!r} in {errors}",
        )


class FixtureTests(BridgeConfigTestCase):
    def test_bridge_sessions_fixture_is_valid(self):
        self.assertEqual(MODULE.validate_document(fixture("bridge-sessions.json")), [])

    def test_terminal_sessions_fixture_is_valid(self):
        self.assertEqual(MODULE.validate_document(fixture("terminal-sessions.json")), [])

    def test_validation_does_not_mutate_the_document(self):
        document = fixture("bridge-sessions.json")
        snapshot = copy.deepcopy(document)
        MODULE.validate_document(document)
        self.assertEqual(document, snapshot)


class AllowlistTests(BridgeConfigTestCase):
    def test_empty_operator_allowlist_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["discord"]["operator_user_ids"] = []
        self.assertErrorMentions(
            MODULE.validate_document(document), "discord.operator_user_ids"
        )

    def test_empty_command_channels_are_rejected(self):
        document = fixture("bridge-sessions.json")
        document["discord"]["command_channel_ids"] = []
        self.assertErrorMentions(
            MODULE.validate_document(document), "discord.command_channel_ids"
        )

    def test_empty_approver_allowlist_is_rejected_when_approval_is_on(self):
        document = fixture("bridge-sessions.json")
        document["discord"]["approver_user_ids"] = []
        self.assertErrorMentions(
            MODULE.validate_document(document), "discord.approver_user_ids"
        )

    def test_malformed_discord_ids_are_rejected(self):
        document = fixture("bridge-sessions.json")
        document["discord"]["guild_id"] = "my-server"
        self.assertErrorMentions(MODULE.validate_document(document), "discord.guild_id")

    def test_duplicate_operator_ids_are_reported(self):
        document = fixture("bridge-sessions.json")
        document["discord"]["operator_user_ids"].append(
            document["discord"]["operator_user_ids"][0]
        )
        self.assertErrorMentions(MODULE.validate_document(document), "duplicate id")


class WorkspaceTests(BridgeConfigTestCase):
    def test_project_outside_workspace_root_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["projects"]["etc"] = "/etc"
        self.assertErrorMentions(MODULE.validate_document(document), "escapes")

    def test_parent_traversal_out_of_workspace_root_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["projects"]["escape"] = "/home/me/src/../../etc"
        self.assertErrorMentions(MODULE.validate_document(document), "escapes")

    def test_workspace_root_prefix_collision_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["projects"]["sibling"] = "/home/me/srcother"
        self.assertErrorMentions(MODULE.validate_document(document), "escapes")

    def test_relative_project_path_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["projects"]["skills"] = "src/skills"
        self.assertErrorMentions(
            MODULE.validate_document(document), "must be an absolute path"
        )

    def test_empty_projects_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["projects"] = {}
        self.assertErrorMentions(MODULE.validate_document(document), "non-empty object")


class PermissionModeTests(BridgeConfigTestCase):
    def test_agent_sdk_accepts_accept_edits(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["permission_mode"] = "acceptEdits"
        self.assertNoErrorMentions(
            MODULE.validate_document(document), "permission_mode"
        )

    def test_agent_sdk_accepts_auto(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["permission_mode"] = "auto"
        self.assertNoErrorMentions(
            MODULE.validate_document(document), "permission_mode"
        )

    def test_agent_sdk_rejects_manual(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["permission_mode"] = "manual"
        self.assertErrorMentions(MODULE.validate_document(document), "permission_mode")

    def test_cli_accepts_manual(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["transport"] = "cli"
        document["bridge_sessions"]["permission_mode"] = "manual"
        document["bridge_sessions"]["approval"] = {"enabled": False}
        self.assertNoErrorMentions(
            MODULE.validate_document(document), "permission_mode"
        )

    def test_cli_rejects_default(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["transport"] = "cli"
        document["bridge_sessions"]["permission_mode"] = "default"
        document["bridge_sessions"]["approval"] = {"enabled": False}
        self.assertErrorMentions(MODULE.validate_document(document), "permission_mode")

    def test_unknown_permission_mode_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["permission_mode"] = "yolo"
        self.assertErrorMentions(MODULE.validate_document(document), "permission_mode")

    def test_bypass_permissions_with_approval_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["permission_mode"] = "bypassPermissions"
        self.assertErrorMentions(
            MODULE.validate_document(document), "suppresses the permission prompt"
        )

    def test_bypass_permissions_without_approval_is_accepted(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["permission_mode"] = "bypassPermissions"
        document["bridge_sessions"]["approval"] = {"enabled": False}
        self.assertEqual(MODULE.validate_document(document), [])


class SettingSourceTests(BridgeConfigTestCase):
    def test_omitted_setting_sources_is_rejected(self):
        document = fixture("bridge-sessions.json")
        del document["bridge_sessions"]["setting_sources"]
        self.assertErrorMentions(
            MODULE.validate_document(document), "setting_sources must be set explicitly"
        )

    def test_empty_setting_sources_is_accepted_as_isolation(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["setting_sources"] = []
        self.assertEqual(MODULE.validate_document(document), [])

    def test_unknown_setting_source_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["setting_sources"] = ["global"]
        self.assertErrorMentions(MODULE.validate_document(document), "setting_sources[0]")


class ApprovalTransportTests(BridgeConfigTestCase):
    def test_can_use_tool_requires_the_agent_sdk_transport(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["transport"] = "cli"
        document["bridge_sessions"]["permission_mode"] = "acceptEdits"
        self.assertErrorMentions(
            MODULE.validate_document(document), "is an Agent SDK callback"
        )

    def test_terminal_sessions_reject_can_use_tool(self):
        document = fixture("terminal-sessions.json")
        document["terminal_sessions"]["approval"]["transport"] = "can-use-tool"
        self.assertErrorMentions(
            MODULE.validate_document(document), "terminal_sessions.approval.transport"
        )

    def test_bridge_sessions_may_use_the_permission_request_hook(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["transport"] = "cli"
        document["bridge_sessions"]["permission_mode"] = "acceptEdits"
        document["bridge_sessions"]["approval"] = {
            "enabled": True,
            "transport": "permission-request-hook",
            "hook_timeout_seconds": 600,
            "timeout_seconds": 300,
            "on_timeout": "deny",
        }
        self.assertEqual(MODULE.validate_document(document), [])

    def test_hook_timeout_on_can_use_tool_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"]["approval"]["hook_timeout_seconds"] = 600
        self.assertErrorMentions(
            MODULE.validate_document(document), "applies only to the"
        )


class ApprovalTimeoutTests(BridgeConfigTestCase):
    def test_allow_on_timeout_is_rejected(self):
        document = fixture("terminal-sessions.json")
        document["terminal_sessions"]["approval"]["on_timeout"] = "allow"
        self.assertErrorMentions(MODULE.validate_document(document), "must be 'deny'")

    def test_approval_timeout_must_stay_below_hook_timeout(self):
        document = fixture("terminal-sessions.json")
        document["terminal_sessions"]["approval"]["timeout_seconds"] = 600
        self.assertErrorMentions(MODULE.validate_document(document), "must be below")

    def test_hook_timeout_above_platform_maximum_is_rejected(self):
        document = fixture("terminal-sessions.json")
        document["terminal_sessions"]["approval"]["hook_timeout_seconds"] = 900
        self.assertErrorMentions(
            MODULE.validate_document(document), "must not exceed 600"
        )


class EndpointTests(BridgeConfigTestCase):
    def test_non_loopback_listen_host_is_rejected(self):
        document = fixture("terminal-sessions.json")
        document["terminal_sessions"]["listen_host"] = "0.0.0.0"
        self.assertErrorMentions(MODULE.validate_document(document), "must be loopback")

    def test_out_of_range_port_is_rejected(self):
        document = fixture("terminal-sessions.json")
        document["terminal_sessions"]["listen_port"] = 70000
        self.assertErrorMentions(MODULE.validate_document(document), "valid TCP port")

    def test_secret_env_must_name_a_variable(self):
        document = fixture("terminal-sessions.json")
        document["terminal_sessions"]["shared_secret_env"] = "not a var name"
        self.assertErrorMentions(
            MODULE.validate_document(document), "environment variable name"
        )


class SecretTests(BridgeConfigTestCase):
    def test_inline_token_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["discord"]["token"] = "MTIzNDU2Nzg5.Gabcde.fghijklmnop"
        self.assertErrorMentions(MODULE.validate_document(document), "inline secret")

    def test_inline_shared_secret_is_rejected(self):
        document = fixture("terminal-sessions.json")
        document["terminal_sessions"]["shared_secret"] = "hunter2"
        self.assertErrorMentions(MODULE.validate_document(document), "inline secret")

    def test_env_suffixed_keys_are_not_inline_secrets(self):
        self.assertNoErrorMentions(
            MODULE.validate_document(fixture("terminal-sessions.json")), "inline secret"
        )


class StructureTests(BridgeConfigTestCase):
    def test_notification_channel_is_required_when_notifications_are_on(self):
        document = fixture("terminal-sessions.json")
        del document["discord"]["notification_channel_id"]
        self.assertErrorMentions(
            MODULE.validate_document(document), "discord.notification_channel_id"
        )

    def test_both_blocks_disabled_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["bridge_sessions"] = {"enabled": False}
        self.assertErrorMentions(
            MODULE.validate_document(document), "at least one of bridge_sessions"
        )

    def test_both_blocks_enabled_is_accepted(self):
        document = fixture("bridge-sessions.json")
        terminal = fixture("terminal-sessions.json")
        document["terminal_sessions"] = terminal["terminal_sessions"]
        self.assertEqual(MODULE.validate_document(document), [])

    def test_version_one_is_rejected(self):
        document = fixture("bridge-sessions.json")
        document["version"] = 1
        self.assertErrorMentions(MODULE.validate_document(document), "version must be")

    def test_missing_top_level_keys_are_reported(self):
        errors = MODULE.validate_document({"version": 2})
        self.assertErrorMentions(errors, "missing required key 'discord'")
        self.assertErrorMentions(errors, "at least one of bridge_sessions")

    def test_non_object_document_is_rejected(self):
        self.assertEqual(
            MODULE.validate_document([]), ["configuration must be a JSON object"]
        )


class ContractDriftTests(BridgeConfigTestCase):
    """The drift checker must actually catch the shapes that were wrong before."""

    CURRENT_TYPES = """
export declare type PermissionMode = 'default' | 'acceptEdits' | 'bypassPermissions' | 'plan' | 'dontAsk' | 'auto';
export declare type SettingSource = 'user' | 'project' | 'local';
export declare type CanUseTool = (toolName: string, input: Record<string, unknown>, options: {
    signal: AbortSignal;
    suggestions?: PermissionUpdate[];
}) => Promise<PermissionResult | null>;
export declare type PermissionResult = {
    behavior: 'allow';
    updatedInput?: Record<string, unknown>;
    updatedPermissions?: PermissionUpdate[];
} | {
    behavior: 'deny';
    message: string;
    interrupt?: boolean;
};
export declare type PermissionRequestHookInput = BaseHookInput & {
    hook_event_name: 'PermissionRequest';
    tool_name: string;
    tool_input: unknown;
    permission_suggestions?: PermissionUpdate[];
};
export declare type PermissionRequestHookSpecificOutput = {
    hookEventName: 'PermissionRequest';
    decision: {
        behavior: 'allow';
        updatedInput?: Record<string, unknown>;
        updatedPermissions?: PermissionUpdate[];
    } | {
        behavior: 'deny';
        message?: string;
    };
};
"""

    def test_current_types_pass(self):
        self.assertEqual(CONTRACT.check_sdk_types(self.CURRENT_TYPES), [])

    def test_request_object_signature_is_flagged(self):
        drifted = self.CURRENT_TYPES.replace(
            "(toolName: string, input: Record<string, unknown>, options: {",
            "(request: ToolUseRequest, options: {",
        )
        self.assertErrorMentions(
            CONTRACT.check_sdk_types(drifted), "toolName as its first positional"
        )

    def test_approved_boolean_result_is_flagged(self):
        drifted = self.CURRENT_TYPES.replace("behavior: 'allow';", "approved: true;")
        self.assertErrorMentions(CONTRACT.check_sdk_types(drifted), "PermissionResult")

    def test_tool_use_id_on_permission_request_is_flagged(self):
        drifted = self.CURRENT_TYPES.replace(
            "    tool_name: string;\n    tool_input: unknown;",
            "    tool_use_id: string;\n    tool_name: string;\n    tool_input: unknown;",
        )
        self.assertErrorMentions(CONTRACT.check_sdk_types(drifted), "tool_use_id")

    def test_apply_rule_output_is_flagged(self):
        drifted = self.CURRENT_TYPES.replace(
            "updatedPermissions?: PermissionUpdate[];\n    } | {",
            "applyRule?: string;\n    } | {",
        )
        self.assertErrorMentions(CONTRACT.check_sdk_types(drifted), "applyRule")

    def test_dropped_permission_mode_is_flagged(self):
        drifted = self.CURRENT_TYPES.replace(" | 'acceptEdits'", "")
        self.assertErrorMentions(
            CONTRACT.check_sdk_types(drifted), "PermissionMode drifted"
        )

    def test_cli_permission_modes_match_documented_set(self):
        help_text = (
            '  --permission-mode <mode>   Permission mode\n'
            '                             (choices: "acceptEdits", "auto",\n'
            '                             "bypassPermissions", "manual",\n'
            '                             "dontAsk", "plan")\n'
            '  --plugin-dir <path>        Load a plugin\n'
        )
        self.assertEqual(CONTRACT.check_cli_permission_modes(help_text), [])

    def test_cli_permission_mode_drift_is_flagged(self):
        help_text = (
            '  --permission-mode <mode>   Permission mode\n'
            '                             (choices: "acceptEdits", "plan")\n'
            '  --plugin-dir <path>        Load a plugin\n'
        )
        self.assertErrorMentions(
            CONTRACT.check_cli_permission_modes(help_text), "drifted"
        )


class CliTests(BridgeConfigTestCase):
    def test_valid_config_exits_zero(self):
        self.assertEqual(MODULE.main([str(FIXTURE_ROOT / "bridge-sessions.json")]), 0)

    def test_missing_file_exits_one(self):
        self.assertEqual(MODULE.main([str(FIXTURE_ROOT / "nope.json")]), 1)


if __name__ == "__main__":
    unittest.main()
