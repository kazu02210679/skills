from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPOSITORY_ROOT
    / "skills"
    / "claude-code-discord-bot"
    / "scripts"
    / "validate_bridge_config.py"
)
FIXTURE_ROOT = REPOSITORY_ROOT / "evals" / "claude-code-discord-bot" / "fixtures"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_bridge_config", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


def fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


class BridgeConfigValidationTests(unittest.TestCase):
    def assertErrorMentions(self, errors: list[str], fragment: str) -> None:
        self.assertTrue(
            any(fragment in error for error in errors),
            f"expected an error containing {fragment!r}, got {errors}",
        )

    def test_agent_sdk_fixture_is_valid(self):
        self.assertEqual(MODULE.validate_document(fixture("valid-bridge.json")), [])

    def test_http_hook_fixture_is_valid(self):
        self.assertEqual(
            MODULE.validate_document(fixture("valid-http-hook-bridge.json")), []
        )

    def test_empty_operator_allowlist_is_rejected(self):
        document = fixture("valid-bridge.json")
        document["discord"]["operator_user_ids"] = []
        self.assertErrorMentions(
            MODULE.validate_document(document), "discord.operator_user_ids"
        )

    def test_empty_command_channels_are_rejected(self):
        document = fixture("valid-bridge.json")
        document["discord"]["command_channel_ids"] = []
        self.assertErrorMentions(
            MODULE.validate_document(document), "discord.command_channel_ids"
        )

    def test_project_outside_workspace_root_is_rejected(self):
        document = fixture("valid-bridge.json")
        document["runtime"]["projects"]["etc"] = "/etc"
        self.assertErrorMentions(
            MODULE.validate_document(document), "escapes runtime.workspace_root"
        )

    def test_parent_traversal_out_of_workspace_root_is_rejected(self):
        document = fixture("valid-bridge.json")
        document["runtime"]["projects"]["escape"] = "/home/me/src/../../etc"
        self.assertErrorMentions(
            MODULE.validate_document(document), "escapes runtime.workspace_root"
        )

    def test_workspace_root_prefix_collision_is_rejected(self):
        document = fixture("valid-bridge.json")
        document["runtime"]["projects"]["sibling"] = "/home/me/srcother"
        self.assertErrorMentions(
            MODULE.validate_document(document), "escapes runtime.workspace_root"
        )

    def test_relative_project_path_is_rejected(self):
        document = fixture("valid-bridge.json")
        document["runtime"]["projects"]["skills"] = "src/skills"
        self.assertErrorMentions(
            MODULE.validate_document(document), "must be an absolute path"
        )

    def test_bypass_permissions_with_approval_is_rejected(self):
        document = fixture("valid-bridge.json")
        document["runtime"]["permission_mode"] = "bypassPermissions"
        self.assertErrorMentions(
            MODULE.validate_document(document), "suppresses the permission event"
        )

    def test_bypass_permissions_without_permission_flows_is_accepted(self):
        document = fixture("valid-bridge.json")
        document["runtime"]["permission_mode"] = "bypassPermissions"
        document["approval"]["enabled"] = False
        document["notifications"]["on_permission_request"] = False
        self.assertEqual(MODULE.validate_document(document), [])

    def test_cli_only_permission_mode_is_rejected_for_agent_sdk(self):
        document = fixture("valid-bridge.json")
        document["runtime"]["permission_mode"] = "acceptEdits"
        self.assertErrorMentions(
            MODULE.validate_document(document), "is not accepted by the agent-sdk"
        )

    def test_unknown_permission_mode_is_rejected_for_cli(self):
        document = fixture("valid-http-hook-bridge.json")
        document["runtime"]["permission_mode"] = "yolo"
        self.assertErrorMentions(
            MODULE.validate_document(document), "is not accepted by the cli"
        )

    def test_allow_on_timeout_is_rejected(self):
        document = fixture("valid-http-hook-bridge.json")
        document["approval"]["on_timeout"] = "allow"
        self.assertErrorMentions(
            MODULE.validate_document(document), "must be 'deny'"
        )

    def test_approval_timeout_must_stay_below_hook_timeout(self):
        document = fixture("valid-http-hook-bridge.json")
        document["approval"]["timeout_seconds"] = 600
        self.assertErrorMentions(MODULE.validate_document(document), "must be below")

    def test_hook_timeout_above_platform_maximum_is_rejected(self):
        document = fixture("valid-http-hook-bridge.json")
        document["approval"]["hook_timeout_seconds"] = 900
        self.assertErrorMentions(MODULE.validate_document(document), "must not exceed 600")

    def test_non_loopback_listen_host_is_rejected(self):
        document = fixture("valid-http-hook-bridge.json")
        document["approval"]["listen_host"] = "0.0.0.0"
        self.assertErrorMentions(MODULE.validate_document(document), "must be loopback")

    def test_inline_token_is_rejected(self):
        document = fixture("valid-bridge.json")
        document["discord"]["token"] = "MTIzNDU2Nzg5.Gabcde.fghijklmnop"
        self.assertErrorMentions(MODULE.validate_document(document), "inline secret")

    def test_inline_shared_secret_is_rejected(self):
        document = fixture("valid-http-hook-bridge.json")
        document["approval"]["shared_secret"] = "hunter2"
        self.assertErrorMentions(MODULE.validate_document(document), "inline secret")

    def test_env_names_are_not_treated_as_inline_secrets(self):
        document = fixture("valid-http-hook-bridge.json")
        self.assertEqual(MODULE.validate_document(document), [])

    def test_secret_env_must_name_a_variable(self):
        document = fixture("valid-http-hook-bridge.json")
        document["approval"]["shared_secret_env"] = "not a var name"
        self.assertErrorMentions(
            MODULE.validate_document(document), "environment variable name"
        )

    def test_approver_allowlist_is_required_when_approval_is_enabled(self):
        document = fixture("valid-bridge.json")
        document["discord"]["approver_user_ids"] = []
        self.assertErrorMentions(
            MODULE.validate_document(document), "discord.approver_user_ids"
        )

    def test_notification_channel_is_required_when_notifications_are_on(self):
        document = fixture("valid-bridge.json")
        del document["discord"]["notification_channel_id"]
        self.assertErrorMentions(
            MODULE.validate_document(document), "discord.notification_channel_id"
        )

    def test_malformed_discord_ids_are_rejected(self):
        document = fixture("valid-bridge.json")
        document["discord"]["guild_id"] = "my-server"
        self.assertErrorMentions(MODULE.validate_document(document), "discord.guild_id")

    def test_duplicate_operator_ids_are_reported(self):
        document = fixture("valid-bridge.json")
        operator = document["discord"]["operator_user_ids"][0]
        document["discord"]["operator_user_ids"].append(operator)
        self.assertErrorMentions(MODULE.validate_document(document), "duplicate id")

    def test_missing_top_level_keys_are_reported(self):
        errors = MODULE.validate_document({"version": 1})
        for key in ("discord", "runtime", "approval", "notifications"):
            self.assertErrorMentions(errors, f"missing required key '{key}'")

    def test_unsupported_version_is_rejected(self):
        document = fixture("valid-bridge.json")
        document["version"] = 2
        self.assertErrorMentions(MODULE.validate_document(document), "version must be")

    def test_non_object_document_is_rejected(self):
        self.assertEqual(
            MODULE.validate_document([]), ["configuration must be a JSON object"]
        )

    def test_fixture_is_not_mutated_between_cases(self):
        document = fixture("valid-bridge.json")
        snapshot = copy.deepcopy(document)
        MODULE.validate_document(document)
        self.assertEqual(document, snapshot)


class BridgeConfigCliTests(unittest.TestCase):
    def test_valid_config_exits_zero(self):
        self.assertEqual(
            MODULE.main([str(FIXTURE_ROOT / "valid-bridge.json")]),
            0,
        )

    def test_missing_file_exits_one(self):
        self.assertEqual(
            MODULE.main([str(FIXTURE_ROOT / "does-not-exist.json")]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
