from __future__ import annotations

import json
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "orchestrate-gpt-pro-sol-advisor"
CASES = Path(__file__).with_name("cases.json")
PRESSURE_RESULTS = Path(__file__).with_name("pressure-results.json")
POLICY_PATH = Path(__file__).with_name("policy.py")

SPEC = importlib.util.spec_from_file_location("composition_policy", POLICY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {POLICY_PATH}")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def valid_combined(**overrides: object) -> dict[str, object]:
    scenario: dict[str, object] = {
        "intent": "combined",
        "setup_status": "ready",
        "preferences_loaded": True,
        "preferences_client": "codex",
        "preferences_scope": "project",
        "preferences_workspace": "/repo/current",
        "trusted_current_workspace": "/repo/current",
        "current_workspace": "/repo/current",
        "preferences_profile_key": "codex:project:/repo/current",
        "configured_advisor_role": "sol_advisor_advisor",
        "configured_combined_roles": ["sol_advisor_advisor"],
        "available_roles": ["sol_advisor_advisor"],
        "expected_advisor_model": "gpt-5.6-sol",
        "expected_advisor_effort": "high",
    }
    scenario.update(overrides)
    return scenario


def public_observations(**overrides: object) -> dict[str, object]:
    observed: dict[str, object] = {
        "role": "sol_advisor_advisor",
        "model": "gpt-5.6-sol",
        "effort": "high",
        "sandbox": "read-only",
        "permission_profile": "managed",
    }
    observed.update(overrides)
    return observed


def inspector_output(
    thread_id: str = "11111111-1111-7111-8111-111111111111",
    **overrides: object,
) -> dict[str, object]:
    output: dict[str, object] = {
        "thread_id": thread_id,
        "parent_thread_id": "00000000-0000-7000-8000-000000000000",
        "agent_role": "sol_advisor_advisor",
        "agent_path": "agents/sol_advisor_advisor.toml",
        "model_provider": "openai",
        "model": "gpt-5.6-sol",
        "effort": "high",
        "sandbox_policy_type": "read-only",
        "permission_profile_type": "managed",
        "cwd": "/repo/current",
    }
    output.update(overrides)
    return output


def installed_plugin_root(codex_home: str | None = None) -> Path:
    return (
        Path(codex_home or os.environ["CODEX_HOME"])
        / "plugins"
        / "cache"
        / "sol-advisor"
        / "sol-advisor"
        / "0.5.0"
    )


def inspector_evidence(
    thread_id: str = "11111111-1111-7111-8111-111111111111",
    **overrides: object,
) -> dict[str, object]:
    plugin_root = installed_plugin_root()
    evidence: dict[str, object] = {
        "runtime_inspector_exit_code": 0,
        "runtime_inspector_origin_skill_path": str(
            plugin_root / "skills" / "orchestration" / "SKILL.md"
        ),
        "runtime_inspector_script_path": str(
            plugin_root / "scripts" / "inspect-agent-runtime.sh"
        ),
        "runtime_inspector_output": inspector_output(thread_id),
    }
    evidence.update(overrides)
    return evidence


def trusted_catalog_context(**overrides: object) -> dict[str, object]:
    context: dict[str, object] = {
        "selected_sol_advisor_orchestration_skill_path": str(
            installed_plugin_root() / "skills" / "orchestration" / "SKILL.md"
        )
    }
    context.update(overrides)
    return context


def trusted_host_context(
    thread_id: str = "11111111-1111-7111-8111-111111111111",
    **overrides: object,
) -> dict[str, object]:
    context: dict[str, object] = {
        "advisor_thread_id": thread_id,
        "terminal_state": "completed",
        "source": "native-result",
    }
    context.update(overrides)
    return context


_RAW_ROUTE = POLICY.route
_DEFAULT_TRUSTED_HOST = object()


def _route_with_trusted_host(
    scenario: dict[str, object],
    *,
    trusted_catalog: dict[str, object] | None = None,
    trusted_host: dict[str, object] | None | object = _DEFAULT_TRUSTED_HOST,
) -> dict[str, object]:
    if trusted_host is _DEFAULT_TRUSTED_HOST:
        thread_id = scenario.get(
            "advisor_thread_id", "11111111-1111-7111-8111-111111111111"
        )
        trusted_host = trusted_host_context(str(thread_id))
    return _RAW_ROUTE(
        scenario,
        trusted_catalog=trusted_catalog,
        trusted_host=trusted_host if isinstance(trusted_host, dict) else None,
    )


POLICY.route = _route_with_trusted_host


def attested_combined(**overrides: object) -> dict[str, object]:
    public = public_observations()
    for field, legacy_key in POLICY.RUNTIME_FIELDS.items():
        if legacy_key in overrides:
            public[field] = overrides.pop(legacy_key)
    evidence: dict[str, object] = {
        "advisor_invocation_succeeded": True,
        "advisor_thread_id": "11111111-1111-7111-8111-111111111111",
        "public_runtime_thread_id": "11111111-1111-7111-8111-111111111111",
        "public_runtime_observations": public,
    }
    evidence.update(overrides)
    return valid_combined(**evidence)


class CompositionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.codex_home = tempfile.TemporaryDirectory()
        plugin_root = installed_plugin_root(cls.codex_home.name)
        skill = plugin_root / "skills" / "orchestration" / "SKILL.md"
        script = plugin_root / "scripts" / "inspect-agent-runtime.sh"
        skill.parent.mkdir(parents=True)
        script.parent.mkdir(parents=True)
        skill.write_text("# installed orchestration\n", encoding="utf-8")
        script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        stale_root = plugin_root.parent / "0.4.0"
        stale_skill = stale_root / "skills" / "orchestration" / "SKILL.md"
        stale_script = stale_root / "scripts" / "inspect-agent-runtime.sh"
        stale_skill.parent.mkdir(parents=True)
        stale_script.parent.mkdir(parents=True)
        stale_skill.write_text("# stale orchestration\n", encoding="utf-8")
        stale_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        cls.stale_paths = (str(stale_skill), str(stale_script))
        cls.lookalike_root = tempfile.TemporaryDirectory()
        lookalike = Path(cls.lookalike_root.name)
        fake_skill = lookalike / "skills" / "orchestration" / "SKILL.md"
        fake_script = lookalike / "scripts" / "inspect-agent-runtime.sh"
        fake_skill.parent.mkdir(parents=True)
        fake_script.parent.mkdir(parents=True)
        fake_skill.write_text("# repo lookalike\n", encoding="utf-8")
        fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        escaped_version = (
            Path(cls.codex_home.name)
            / "plugins"
            / "cache"
            / "sol-advisor"
            / "sol-advisor"
            / "0.6.0"
        )
        escaped_version.parent.mkdir(parents=True, exist_ok=True)
        try:
            escaped_version.symlink_to(lookalike, target_is_directory=True)
            cls.symlink_escape_paths = (
                str(escaped_version / "skills" / "orchestration" / "SKILL.md"),
                str(escaped_version / "scripts" / "inspect-agent-runtime.sh"),
            )
        except OSError:
            cls.symlink_escape_paths = None
        cls.env_patch = patch.dict(os.environ, {"CODEX_HOME": cls.codex_home.name})
        cls.env_patch.start()
        cls.skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.readme = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
        cls.cases = json.loads(CASES.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.env_patch.stop()
        cls.codex_home.cleanup()
        cls.lookalike_root.cleanup()

    def test_routes_only_explicit_combined_mode(self) -> None:
        for phrase in (
            "combined mode",
            "standalone",
            "gpt-pro-codex-loop",
            "sol-advisor:orchestration",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

    def test_preserves_authority_and_bounded_advice(self) -> None:
        for phrase in (
            "frozen requirements, acceptance criteria, semantic review",
            "sol supplies bounded advice only",
            "materially new evidence",
            "sol_advisor_advisor",
            "sol_advisor_terra_implementer",
            "`partially accept`",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

    def test_forbids_duplicate_review_recursion_and_silent_downgrade(self) -> None:
        for phrase in (
            "do not make sol a mandatory pre-pro or final gate",
            "reject nested",
            "sol-to-sol review",
            "fabricate a",
            "do not silently downgrade",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

    def test_luna_first_routing_has_bounded_terra_and_sol_escalation(self) -> None:
        for phrase in (
            "implementation_policy: luna_first",
            "gpt-5.6-luna",
            "thinking: max",
            "gpt-5.6-terra",
            "difficult or stuck implementation",
            "max_parallel_tasks: 2",
            "sol is not the default implementation worker",
            "sol must remain read-only",
            "one precise, bounded packet",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

        lane = SKILL_ROOT / "references" / "luna-implementation-lane.md"
        self.assertTrue(lane.is_file())
        lane_text = lane.read_text(encoding="utf-8").lower()
        for phrase in (
            "clientthreadid",
            "one precise correction to the same task",
            "sol_advisor_terra_implementer",
            "do not create a replacement task",
        ):
            with self.subTest(reference_phrase=phrase):
                self.assertIn(phrase, lane_text)

    def test_verification_economy_is_explicit(self) -> None:
        economy = (
            SKILL_ROOT / "references" / "verification-economy.md"
        ).read_text(encoding="utf-8").lower()
        for phrase in (
            "new_test_files = 0",
            "one regression test per root cause",
            "observable behavior",
            "l1  affected focused test",
            "do not rerun an unchanged successful command",
            "full log path and digest",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, economy)

    def test_combined_mode_does_not_invoke_sol_orchestration(self) -> None:
        lower = self.skill.lower()
        self.assertNotIn(
            "required sub-skill (conditional advisory dependency)", lower
        )
        self.assertIn("do not invoke", lower)
        self.assertIn("`sol-advisor:orchestration` in combined mode", lower)
        self.assertIn("configured advisor", lower)

    def test_skill_requires_codex_workspace_profile_binding(self) -> None:
        lower = self.skill.lower()
        for phrase in (
            "`preferences.client` must equal `codex`",
            "canonicalizing `preferences.workspace`",
            "`codex:<scope>:<raw preferences.workspace>`",
            "never rebuild it from another runtime's canonical path",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, lower)

    def test_wrong_client_and_workspace_profiles_stop_before_gpc(self) -> None:
        wrong_client = POLICY.route(valid_combined(preferences_client="cursor"))
        self.assertEqual("profile-client-mismatch", wrong_client["terminal"])
        self.assertFalse(wrong_client["gpc_started"])

        wrong_workspace = POLICY.route(
            valid_combined(preferences_workspace="/repo/other")
        )
        self.assertEqual("profile-workspace-mismatch", wrong_workspace["terminal"])
        self.assertFalse(wrong_workspace["gpc_started"])

        wrong_profile = POLICY.route(
            valid_combined(preferences_profile_key="codex:project:/repo/other")
        )
        self.assertEqual("profile-key-mismatch", wrong_profile["terminal"])
        self.assertFalse(wrong_profile["gpc_started"])

    def test_profile_binding_is_canonical_and_uses_trusted_workspace(self) -> None:
        equivalent = POLICY.route(
            valid_combined(
                preferences_workspace="/repo/current/.",
                trusted_current_workspace="/repo/current",
                preferences_profile_key="codex:project:/repo/current/.",
            )
        )
        self.assertTrue(equivalent["gpc_started"])

        transformed_posix_key = POLICY.route(
            valid_combined(
                preferences_workspace="/repo/current/.",
                trusted_current_workspace="/repo/current",
                preferences_profile_key="codex:project:/repo/current",
            )
        )
        self.assertEqual("profile-key-mismatch", transformed_posix_key["terminal"])
        self.assertFalse(transformed_posix_key["gpc_started"])

        attacker_supplied = POLICY.route(
            valid_combined(
                current_workspace="/repo/other",
                trusted_current_workspace="/repo/current",
            )
        )
        self.assertTrue(attacker_supplied["gpc_started"])

    def test_profile_key_preserves_upstream_raw_workspace_serialization(self) -> None:
        raw_workspace = r"C:\Users\Foo\repo"
        runtime_workspace = "c:/users/foo/repo"
        canonical_identity = r"c:\users\foo\repo"
        with patch.object(
            POLICY,
            "canonical_workspace",
            side_effect=lambda value: str(value).replace("/", "\\").lower(),
        ):
            matching_upstream_key = POLICY.route(
                attested_combined(
                    preferences_workspace=raw_workspace,
                    trusted_current_workspace=runtime_workspace,
                    preferences_profile_key=f"codex:project:{raw_workspace}",
                    codex_commitment_boundary=True,
                    concrete_question=True,
                    material_risk=True,
                    decision_value=True,
                    precise_question="Is the raw-bound profileKey valid?",
                    sol_response={"recommendation": "keep the raw-bound key"},
                )
            )
            recomputed_canonical_key = POLICY.route(
                valid_combined(
                    preferences_workspace=raw_workspace,
                    trusted_current_workspace=runtime_workspace,
                    preferences_profile_key=f"codex:project:{canonical_identity}",
                )
            )

        self.assertTrue(matching_upstream_key["gpc_started"])
        self.assertEqual(1, matching_upstream_key["advice_admitted"])
        self.assertFalse(matching_upstream_key["advice_discarded"])
        self.assertEqual("profile-key-mismatch", recomputed_canonical_key["terminal"])
        self.assertTrue(recomputed_canonical_key["advice_discarded"])

    def test_workspace_identity_preserves_significant_edge_whitespace(self) -> None:
        trailing_space_workspace = "/repo/current "
        matching = POLICY.route(
            valid_combined(
                preferences_workspace=trailing_space_workspace,
                trusted_current_workspace=trailing_space_workspace,
                preferences_profile_key=f"codex:project:{trailing_space_workspace}",
            )
        )
        mismatching = POLICY.route(
            valid_combined(
                preferences_workspace=trailing_space_workspace,
                trusted_current_workspace="/repo/current",
                preferences_profile_key=f"codex:project:{trailing_space_workspace}",
            )
        )

        self.assertTrue(matching["gpc_started"])
        self.assertEqual("profile-workspace-mismatch", mismatching["terminal"])
        self.assertFalse(mismatching["gpc_started"])

    def test_malformed_workspace_values_fail_closed_without_coercion(self) -> None:
        missing = valid_combined()
        missing.pop("preferences_workspace")
        nul_workspace = "bad" + chr(0) + "workspace"
        scenarios = {
            "missing": missing,
            "null": valid_combined(preferences_workspace=None),
            "non-string": valid_combined(preferences_workspace=7),
            "empty": valid_combined(preferences_workspace=""),
            "whitespace-only": valid_combined(preferences_workspace="   "),
            "nul": valid_combined(
                preferences_workspace=nul_workspace,
                trusted_current_workspace=nul_workspace,
                preferences_profile_key=f"codex:project:{nul_workspace}",
            ),
        }
        for name, scenario in scenarios.items():
            with self.subTest(name=name):
                result = POLICY.route(scenario)
                self.assertEqual("profile-workspace-mismatch", result["terminal"])
                self.assertFalse(result["gpc_started"])
                self.assertTrue(result["advice_discarded"])
                self.assertEqual(0, result["fallback_calls"])

    def test_canonicalization_exception_fails_closed(self) -> None:
        workspace = r"C:\repo\current"
        with patch.object(
            POLICY.os.path, "normpath", side_effect=ValueError("invalid path")
        ):
            result = POLICY.route(
                valid_combined(
                    preferences_workspace=workspace,
                    trusted_current_workspace=workspace,
                    preferences_profile_key=f"codex:project:{workspace}",
                )
            )

        self.assertEqual("profile-workspace-mismatch", result["terminal"])
        self.assertTrue(result["advice_discarded"])

    def test_profile_key_rejects_altered_complete_strings(self) -> None:
        workspace = r"C:\Users\Foo\repo"
        for profile_key in (
            f"prefix:codex:project:{workspace}",
            f"cursor:project:{workspace}",
            f"codex:user:{workspace}",
            f"codex:project:{workspace}\\extra",
            r"codex:project:c:\users\foo\repo",
        ):
            with self.subTest(profile_key=profile_key):
                result = POLICY.route(
                    valid_combined(
                        preferences_workspace=workspace,
                        trusted_current_workspace=workspace,
                        preferences_profile_key=profile_key,
                    )
                )
                self.assertEqual("profile-key-mismatch", result["terminal"])
                self.assertTrue(result["advice_discarded"])

    def test_exact_raw_key_does_not_override_workspace_identity_mismatch(self) -> None:
        result = POLICY.route(
            valid_combined(
                preferences_workspace="/repo/other",
                trusted_current_workspace="/repo/current",
                preferences_profile_key="codex:project:/repo/other",
            )
        )

        self.assertEqual("profile-workspace-mismatch", result["terminal"])
        self.assertTrue(result["advice_discarded"])

    def test_missing_profile_fields_fail_closed(self) -> None:
        cases = {
            "client": {"preferences_client": None},
            "scope": {"preferences_scope": None},
            "workspace": {"preferences_workspace": None},
            "profile-key": {"preferences_profile_key": None},
            "model": {"expected_advisor_model": None},
            "effort": {"expected_advisor_effort": None},
        }
        for field, override in cases.items():
            with self.subTest(field=field):
                result = POLICY.route(valid_combined(**override))
                self.assertFalse(result["gpc_started"])
                self.assertEqual(0, result["advice_admitted"])
                self.assertEqual(0, result["fallback_calls"])

    def test_profile_scope_must_use_the_plugin_schema(self) -> None:
        for scope in (None, "", "workspace", ["project"]):
            with self.subTest(scope=scope):
                result = POLICY.route(valid_combined(preferences_scope=scope))
                self.assertEqual("profile-scope-invalid", result["terminal"])
                self.assertFalse(result["gpc_started"])

    def test_available_roles_must_be_a_well_formed_collection(self) -> None:
        for roles in (
            "sol_advisor_advisor",
            None,
            ["sol_advisor_advisor", ""],
            ["sol_advisor_advisor", 7],
        ):
            with self.subTest(roles=roles):
                result = POLICY.route(valid_combined(available_roles=roles))
                self.assertEqual("available-roles-invalid", result["terminal"])
                self.assertFalse(result["gpc_started"])

    def test_combined_role_configuration_is_exactly_one_advisor(self) -> None:
        for roles in (
            [],
            ["sol_advisor_advisor", "sol_advisor_sol_reviewer"],
            ["sol_advisor_advisor", "sol_advisor_high"],
        ):
            with self.subTest(roles=roles):
                result = POLICY.route(valid_combined(configured_combined_roles=roles))
                self.assertEqual("configured-role-set-invalid", result["terminal"])
                self.assertFalse(result["gpc_started"])

    def test_legacy_reviewer_cannot_be_the_configured_advisor(self) -> None:
        result = POLICY.route(
            valid_combined(
                configured_advisor_role="sol_advisor_sol_reviewer",
                available_roles=["sol_advisor_sol_reviewer"],
            )
        )
        self.assertEqual("configured-advisor-invalid", result["terminal"])
        self.assertFalse(result["gpc_started"])
        self.assertEqual(0, result["sol_calls"])

    def test_runtime_attestation_is_required_before_advice_disposition(self) -> None:
        base = valid_combined(
            advisor_invocation_succeeded=True,
            advisor_thread_id="11111111-1111-7111-8111-111111111111",
            public_runtime_thread_id="11111111-1111-7111-8111-111111111111",
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Does this auth boundary preserve tenant isolation?",
            material_risk=True,
            decision_value=True,
        )
        unavailable = POLICY.route(base)
        self.assertEqual(
            "advisor-attestation-provenance-invalid", unavailable["terminal"]
        )
        self.assertEqual(1, unavailable["sol_calls"])
        self.assertFalse(unavailable["advice_accepted"])

        mismatches = {
            "role": {
                "observed_advisor_role": "sol_advisor_high",
                "observed_advisor_model": "gpt-5.6-sol",
                "observed_advisor_effort": "high",
                "observed_advisor_sandbox": "read-only",
                "observed_permission_profile": "restricted",
            },
            "model": {
                "observed_advisor_role": "sol_advisor_advisor",
                "observed_advisor_model": "gpt-5.6-terra",
                "observed_advisor_effort": "high",
                "observed_advisor_sandbox": "read-only",
                "observed_permission_profile": "restricted",
            },
            "effort": {
                "observed_advisor_role": "sol_advisor_advisor",
                "observed_advisor_model": "gpt-5.6-sol",
                "observed_advisor_effort": "low",
                "observed_advisor_sandbox": "read-only",
                "observed_permission_profile": "restricted",
            },
            "sandbox": {
                "observed_advisor_role": "sol_advisor_advisor",
                "observed_advisor_model": "gpt-5.6-sol",
                "observed_advisor_effort": "high",
                "observed_advisor_sandbox": "workspace-write",
                "observed_permission_profile": "managed",
            },
        }
        for field, evidence in mismatches.items():
            with self.subTest(field=field):
                public = {
                    name: evidence[key]
                    for name, key in POLICY.RUNTIME_FIELDS.items()
                }
                result = POLICY.route(
                    {**base, "public_runtime_observations": public}
                )
                self.assertEqual("advisor-attestation-mismatch", result["terminal"])
                self.assertEqual(field, result["attestation_failure"])
                self.assertFalse(result["advice_accepted"])

    def test_each_runtime_field_must_be_trusted_and_observable(self) -> None:
        base = attested_combined(
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Does this boundary hold?",
            material_risk=True,
            decision_value=True,
        )
        for field in POLICY.RUNTIME_FIELDS:
            with self.subTest(missing=field):
                public = dict(base["public_runtime_observations"])
                public.pop(field)
                result = POLICY.route(
                    {**base, "public_runtime_observations": public}
                )
                expected = (
                    "advisor-attestation-provenance-invalid"
                    if field == "role"
                    else "advisor-attestation-inspector-unavailable"
                )
                self.assertEqual(expected, result["terminal"])
                self.assertTrue(result["advice_discarded"])
                self.assertEqual(0, result["downstream_advice_propagations"])
                self.assertEqual(0, result["fallback_calls"])

        malformed_public = dict(base["public_runtime_observations"])
        malformed_public["model"] = ["gpt-5.6-sol"]
        malformed = POLICY.route(
            {**base, "public_runtime_observations": malformed_public}
        )
        self.assertEqual(
            "advisor-attestation-provenance-invalid", malformed["terminal"]
        )

    def test_advisor_invocation_failure_discards_advice_without_fallback(self) -> None:
        base = attested_combined(
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Did the bounded advisor invocation complete?",
            material_risk=True,
            decision_value=True,
            advice_body="must never propagate",
        )
        for succeeded in (None, False, "true"):
            with self.subTest(succeeded=succeeded):
                result = POLICY.route(
                    {**base, "advisor_invocation_succeeded": succeeded}
                )
                self.assertEqual("advisor-invocation-failed", result["terminal"])
                self.assertEqual(1, result["sol_calls"])
                self.assertEqual(0, result["advice_admitted"])
                self.assertTrue(result["advice_discarded"])
                self.assertEqual(0, result["downstream_advice_propagations"])
                self.assertEqual(0, result["fallback_calls"])

    def test_caller_boolean_cannot_promote_or_veto_runtime_provenance(self) -> None:
        public = attested_combined(
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Can a caller Boolean decide provenance?",
            material_risk=True,
            decision_value=True,
        )
        for claimed in (None, False, True, "true"):
            with self.subTest(claimed=claimed):
                result = POLICY.route({**public, "runtime_observation_trusted": claimed})
                self.assertEqual("primary-disposition", result["terminal"])
                self.assertEqual(1, result["advice_admitted"])

    def test_runtime_attestation_prefers_public_native_details(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        public = {
            "role": "sol_advisor_advisor",
            "model": "gpt-5.6-sol",
            "effort": "high",
            "sandbox": "read-only",
            "permission_profile": "managed",
        }
        result = POLICY.route(
            valid_combined(
                advisor_invocation_succeeded=True,
                advisor_thread_id=thread_id,
                public_runtime_thread_id=thread_id,
                public_runtime_observations=public,
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Do public native details prove the runtime route?",
                material_risk=True,
                decision_value=True,
            )
        )
        self.assertEqual("primary-disposition", result["terminal"])
        self.assertEqual(thread_id, result["advisor_thread_id"])
        self.assertEqual(thread_id, result.get("public_runtime_thread_id"))
        self.assertEqual(public, result["runtime_observations"])
        self.assertEqual(
            {field: "public-native-details" for field in POLICY.RUNTIME_FIELDS},
            result["runtime_observation_sources"],
        )

    def test_public_details_are_bound_to_the_spawned_advisor_thread(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        base = attested_combined(
            advisor_thread_id=thread_id,
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Are these public details from the spawned advisor?",
            material_risk=True,
            decision_value=True,
        )
        for public_thread_id in (
            None,
            "22222222-2222-7222-8222-222222222222",
            "not-a-thread-id",
        ):
            with self.subTest(public_thread_id=public_thread_id):
                result = POLICY.route(
                    {**base, "public_runtime_thread_id": public_thread_id}
                )
                self.assertEqual(
                    "advisor-attestation-thread-mismatch", result["terminal"]
                )
                self.assertEqual(0, result["advice_admitted"])
                self.assertTrue(result["advice_discarded"])

    def test_inspector_path_is_derived_from_the_installed_orchestration_skill(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        lookalike = Path(self.lookalike_root.name)
        paths = (
            (
                "/plugins/sol-advisor/0.5.0/skills/orchestration/SKILL.md",
                "/repo/scripts/inspect-agent-runtime.sh",
            ),
            (
                str(lookalike / "skills" / "orchestration" / "SKILL.md"),
                str(lookalike / "scripts" / "inspect-agent-runtime.sh"),
            ),
            (
                "/plugins/ghost/9.9.9/skills/orchestration/SKILL.md",
                "/plugins/ghost/9.9.9/scripts/inspect-agent-runtime.sh",
            ),
        )
        for skill_path, script_path in paths:
            with self.subTest(skill_path=skill_path, script_path=script_path):
                result = POLICY.route(
                    attested_combined(
                        public_runtime_observations={"role": "sol_advisor_advisor"},
                        advisor_thread_id=thread_id,
                        public_runtime_thread_id=thread_id,
                        runtime_inspector_exit_code=0,
                        runtime_inspector_origin_skill_path=skill_path,
                        runtime_inspector_script_path=script_path,
                        runtime_inspector_output=inspector_output(thread_id),
                        codex_commitment_boundary=True,
                        concrete_question=True,
                        precise_question="Is this the installed package inspector?",
                        material_risk=True,
                        decision_value=True,
                    ),
                    trusted_catalog=trusted_catalog_context(),
                )
                self.assertEqual(
                    "advisor-attestation-inspector-unavailable", result["terminal"]
                )
                self.assertEqual(0, result["advice_admitted"])

    def test_catalog_symlink_cannot_escape_to_a_repo_lookalike(self) -> None:
        if self.symlink_escape_paths is None:
            self.skipTest("file symlinks are unavailable on this Windows host")
        skill_path, script_path = self.symlink_escape_paths
        thread_id = "11111111-1111-7111-8111-111111111111"
        result = POLICY.route(
            attested_combined(
                public_runtime_observations={"role": "sol_advisor_advisor"},
                advisor_thread_id=thread_id,
                public_runtime_thread_id=thread_id,
                runtime_inspector_exit_code=0,
                runtime_inspector_origin_skill_path=skill_path,
                runtime_inspector_script_path=script_path,
                runtime_inspector_output=inspector_output(thread_id),
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Can a catalog symlink escape its plugin root?",
                material_risk=True,
                decision_value=True,
            ),
            trusted_catalog=trusted_catalog_context(),
        )
        self.assertEqual("advisor-attestation-inspector-unavailable", result["terminal"])
        self.assertEqual(0, result["advice_admitted"])

    def test_stale_cached_version_cannot_replace_catalog_selected_skill(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        stale_skill, stale_script = self.stale_paths
        result = POLICY.route(
            attested_combined(
                public_runtime_observations={"role": "sol_advisor_advisor"},
                advisor_thread_id=thread_id,
                public_runtime_thread_id=thread_id,
                **inspector_evidence(
                    thread_id,
                    runtime_inspector_origin_skill_path=stale_skill,
                    runtime_inspector_script_path=stale_script,
                ),
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Can a stale cached version replace the selected Skill?",
                material_risk=True,
                decision_value=True,
            ),
            trusted_catalog=trusted_catalog_context(),
        )
        self.assertEqual("advisor-attestation-inspector-unavailable", result["terminal"])
        self.assertEqual(0, result["advice_admitted"])

    def test_paired_scenario_override_cannot_replace_trusted_catalog_identity(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        lookalike = Path(self.lookalike_root.name)
        fake_skill = str(lookalike / "skills" / "orchestration" / "SKILL.md")
        fake_script = str(lookalike / "scripts" / "inspect-agent-runtime.sh")
        result = POLICY.route(
            attested_combined(
                public_runtime_observations={"role": "sol_advisor_advisor"},
                advisor_thread_id=thread_id,
                public_runtime_thread_id=thread_id,
                catalog_selected_sol_advisor_orchestration_skill_path=fake_skill,
                runtime_inspector_exit_code=0,
                runtime_inspector_origin_skill_path=fake_skill,
                runtime_inspector_script_path=fake_script,
                runtime_inspector_output=inspector_output(thread_id),
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Can paired scenario values override the catalog?",
                material_risk=True,
                decision_value=True,
            ),
            trusted_catalog=trusted_catalog_context(),
        )
        self.assertEqual("advisor-attestation-inspector-unavailable", result["terminal"])
        self.assertEqual(0, result["advice_admitted"])

    def test_inspector_success_is_derived_from_exit_zero_and_exact_json(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        result = POLICY.route(
            attested_combined(
                public_runtime_observations={"role": "sol_advisor_advisor"},
                advisor_thread_id=thread_id,
                public_runtime_thread_id=thread_id,
                **inspector_evidence(thread_id),
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Did the official inspector complete?",
                material_risk=True,
                decision_value=True,
            ),
            trusted_catalog=trusted_catalog_context(),
        )
        self.assertEqual("primary-disposition", result["terminal"])
        self.assertEqual(1, result["advice_admitted"])
        self.assertEqual(1, result["runtime_inspector"]["rollout_count"])
        self.assertEqual(
            "success", result["runtime_inspector"]["inspection_status"]
        )
        self.assertNotIn("status", result["runtime_inspector"])
        self.assertEqual(
            {
                "thread_id": thread_id,
                "terminal_state": "completed",
                "source": "native-result",
            },
            result["advisor_completion"],
        )

    def test_inspector_exit_zero_does_not_prove_advisor_completion(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        result = _RAW_ROUTE(
            attested_combined(
                public_runtime_observations={"role": "sol_advisor_advisor"},
                advisor_thread_id=thread_id,
                public_runtime_thread_id=thread_id,
                **inspector_evidence(thread_id),
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Did the advisor itself reach a terminal state?",
                material_risk=True,
                decision_value=True,
            ),
            trusted_catalog=trusted_catalog_context(),
        )
        self.assertEqual("advisor-completion-unavailable", result["terminal"])
        self.assertEqual(0, result["advice_admitted"])
        self.assertTrue(result["advice_discarded"])

    def test_completion_must_be_host_confirmed_for_the_same_thread(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        scenario = attested_combined(
            advisor_thread_id=thread_id,
            public_runtime_thread_id=thread_id,
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Is completion proven by the host for this thread?",
            material_risk=True,
            decision_value=True,
        )
        invalid = (
            None,
            True,
            trusted_host_context(
                "22222222-2222-7222-8222-222222222222"
            ),
            trusted_host_context(thread_id, terminal_state="running"),
            trusted_host_context(thread_id, source="local-runtime-inspector"),
        )
        for trusted_host in invalid:
            with self.subTest(trusted_host=trusted_host):
                result = _RAW_ROUTE(scenario, trusted_host=trusted_host)
                self.assertEqual("advisor-completion-unavailable", result["terminal"])
                self.assertEqual(0, result["advice_admitted"])
                self.assertTrue(result["advice_discarded"])

    def test_runtime_attestation_uses_same_thread_inspector_only_for_omissions(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        inspector = {
            "role": "sol_advisor_advisor",
            "model": "gpt-5.6-sol",
            "effort": "high",
            "sandbox": "read-only",
            "permission_profile": "managed",
        }
        result = POLICY.route(
            valid_combined(
                advisor_invocation_succeeded=True,
                public_runtime_observations={"role": "sol_advisor_advisor"},
                advisor_thread_id=thread_id,
                public_runtime_thread_id=thread_id,
                **inspector_evidence(thread_id),
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Can omitted native details be filled safely?",
                material_risk=True,
                decision_value=True,
            ),
            trusted_catalog=trusted_catalog_context(),
        )
        self.assertEqual("primary-disposition", result["terminal"])
        self.assertEqual(inspector, result["runtime_observations"])
        self.assertEqual("public-native-details", result["runtime_observation_sources"]["role"])
        for field in ("model", "effort", "sandbox", "permission_profile"):
            with self.subTest(field=field):
                self.assertEqual(
                    "local-runtime-inspector",
                    result["runtime_observation_sources"][field],
                )

    def test_inspector_requires_official_path_exit_zero_and_exact_result(self) -> None:
        thread_id = "11111111-1111-7111-8111-111111111111"
        complete = {
            "advisor_thread_id": thread_id,
            "public_runtime_thread_id": thread_id,
            **inspector_evidence(thread_id),
        }
        base = attested_combined(
            public_runtime_observations={"role": "sol_advisor_advisor"},
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Is the local inspector result admissible?",
            material_risk=True,
            decision_value=True,
        )
        invalid = (
            ("runtime_inspector_exit_code", None),
            ("runtime_inspector_exit_code", 1),
            ("runtime_inspector_exit_code", True),
            ("runtime_inspector_origin_skill_path", None),
            ("runtime_inspector_script_path", None),
            ("runtime_inspector_script_path", "/repo/scripts/inspect-agent-runtime.sh"),
            (
                "runtime_inspector_output",
                {key: value for key, value in inspector_output().items() if key != "cwd"},
            ),
            (
                "runtime_inspector_output",
                {**inspector_output(), "advice_body": "not allowlisted"},
            ),
        )
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                evidence = {**complete, field: value}
                result = POLICY.route(
                    {**base, **evidence},
                    trusted_catalog=trusted_catalog_context(),
                )
                self.assertEqual(
                    "advisor-attestation-inspector-unavailable", result["terminal"]
                )
                self.assertEqual(0, result["advice_admitted"])
                self.assertTrue(result["advice_discarded"])

    def test_self_claims_and_failed_inspector_cannot_satisfy_provenance(self) -> None:
        gate = {
            "codex_commitment_boundary": True,
            "concrete_question": True,
            "precise_question": "Can useful advice bypass runtime provenance?",
            "material_risk": True,
            "decision_value": True,
        }
        self_claim = POLICY.route(
            valid_combined(
                **gate,
                advisor_invocation_succeeded=True,
                observed_advisor_role="sol_advisor_advisor",
                observed_advisor_model="gpt-5.6-sol",
                observed_advisor_effort="high",
                observed_advisor_sandbox="read-only",
                observed_permission_profile="managed",
            )
        )
        self.assertEqual("advisor-attestation-provenance-invalid", self_claim["terminal"])
        self.assertEqual(0, self_claim["advice_admitted"])
        self.assertTrue(self_claim["advice_discarded"])

        failed_inspector = POLICY.route(
            attested_combined(
                **gate,
                public_runtime_observations={"role": "sol_advisor_advisor"},
                runtime_inspector_exit_code=1,
                advisor_thread_id="11111111-1111-7111-8111-111111111111",
            )
        )
        self.assertEqual(
            "advisor-attestation-inspector-unavailable",
            failed_inspector["terminal"],
        )
        self.assertEqual(0, failed_inspector["advice_admitted"])
        self.assertTrue(failed_inspector["advice_discarded"])

    def test_permission_profile_is_observed_but_not_a_saved_preference(self) -> None:
        for permission in (
            "managed",
            "custom-host-policy-v7",
            "  custom-host-policy-v7  ",
        ):
            with self.subTest(permission=permission):
                result = POLICY.route(
                    attested_combined(
                        codex_commitment_boundary=True,
                        concrete_question=True,
                        precise_question="Is runtime permission observable?",
                        material_risk=True,
                        decision_value=True,
                        observed_permission_profile=permission,
                    )
                )
                self.assertEqual("primary-disposition", result["terminal"])
                self.assertTrue(result["runtime_attested"])
                self.assertEqual(1, result["advice_admitted"])
                self.assertEqual(
                    permission,
                    result["runtime_observations"]["permission_profile"],
                )

    def test_permission_profile_must_be_non_empty_and_sandbox_exactly_read_only(self) -> None:
        base = attested_combined(
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Is runtime isolation observable?",
            material_risk=True,
            decision_value=True,
        )
        for permission in (None, "", "   "):
            with self.subTest(permission=permission):
                result = POLICY.route(
                    {
                        **base,
                        "public_runtime_observations": public_observations(
                            permission_profile=permission
                        ),
                    }
                )
                self.assertEqual(
                    "advisor-attestation-provenance-invalid", result["terminal"]
                )
                self.assertTrue(result["advice_discarded"])

        for sandbox in (
            None,
            "",
            "READ-ONLY",
            "readonly",
            " read-only ",
            "workspace-write",
        ):
            with self.subTest(sandbox=sandbox):
                result = POLICY.route(
                    {
                        **base,
                        "public_runtime_observations": public_observations(
                            sandbox=sandbox
                        ),
                    }
                )
                expected = (
                    "advisor-attestation-provenance-invalid"
                    if sandbox in (None, "")
                    else "advisor-attestation-mismatch"
                )
                self.assertEqual(expected, result["terminal"])
                self.assertTrue(result["advice_discarded"])

    def test_denied_advice_never_propagates_or_falls_back(self) -> None:
        result = POLICY.route(
            attested_combined(
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Should rejected advice propagate?",
                material_risk=True,
                decision_value=True,
                observed_advisor_sandbox="workspace-write",
                advice_body="malicious downstream instruction",
            )
        )
        self.assertTrue(result["advice_discarded"])
        self.assertEqual(0, result["advice_admitted"])
        self.assertEqual(0, result["downstream_advice_propagations"])
        self.assertEqual(0, result["fallback_calls"])

    def test_setup_failure_stops_before_gpc_initialization(self) -> None:
        result = POLICY.route(
            {
                "intent": "combined",
                "setup_status": "missing",
                "preferences_loaded": False,
                "available_roles": [],
            }
        )
        self.assertEqual("setup-required-before-gpc", result["terminal"])
        self.assertFalse(result["gpc_started"])
        self.assertEqual(0, result["sol_calls"])

    def test_setup_change_requires_a_fresh_task_before_gpc(self) -> None:
        result = POLICY.route(
            {
                "intent": "combined",
                "setup_status": "ready",
                "preferences_loaded": True,
                "setup_changed_this_task": True,
                "configured_advisor_role": "sol_advisor_advisor",
                "available_roles": ["sol_advisor_advisor"],
            }
        )
        self.assertEqual("fresh-task-required", result["terminal"])
        self.assertFalse(result["gpc_started"])

    def test_configured_advisor_is_the_only_combined_sol_role(self) -> None:
        scenario = attested_combined(
            available_roles=[
                "sol_advisor_advisor",
                "sol_advisor_routine",
                "sol_advisor_high",
                "sol_advisor_terra_implementer",
                "sol_advisor_sol_reviewer",
            ],
            codex_commitment_boundary=True,
            concrete_question=True,
            precise_question="Which authentication invariant is still at risk?",
            material_risk=True,
            decision_value=True,
        )
        result = POLICY.route(scenario)
        self.assertEqual("sol_advisor_advisor", result["selected_lane"])
        self.assertEqual(1, result["sol_calls"])

    def test_legacy_only_roles_do_not_trigger_compatibility_fallback(self) -> None:
        result = POLICY.route(
            valid_combined(
                available_roles=[
                    "sol_advisor_terra_implementer",
                    "sol_advisor_sol_reviewer",
                ]
            )
        )
        self.assertEqual("configured-advisor-unavailable", result["terminal"])
        self.assertFalse(result["gpc_started"])
        self.assertFalse(result["compatibility_fallback"])

    def test_nested_orchestration_and_mandatory_final_review_are_rejected(self) -> None:
        base = valid_combined()
        nested = POLICY.route(
            {**base, "requested_dependency": "sol-advisor:orchestration"}
        )
        self.assertEqual("forbidden-nested-orchestration", nested["terminal"])
        self.assertEqual(0, nested["sol_calls"])

        final_gate = POLICY.route({**base, "mandatory_final_sol_review": True})
        self.assertEqual("local-verify-then-pro", final_gate["terminal"])
        self.assertEqual(0, final_gate["sol_calls"])

        implementer = POLICY.route(
            {**base, "requested_role": "sol_advisor_terra_implementer"}
        )
        self.assertEqual("non-advisor-role-rejected", implementer["terminal"])
        self.assertEqual(0, implementer["sol_calls"])

    def test_cases_cover_routing_and_failure_boundaries(self) -> None:
        cases = {case["id"]: case for case in self.cases}
        self.assertEqual(
            {
                "standalone-gpt-pro-remains-standalone",
                "standalone-sol-remains-standalone",
                "ambiguous-installation-does-not-compose",
                "missing-setup-stops-before-gpc",
                "setup-change-requires-fresh-task",
                "legacy-only-does-not-fallback",
                "nested-orchestration-is-rejected",
                "explicit-combined-low-risk-skips-sol",
                "technical-question-selects-configured-advisor",
                "authority-escalation-is-rejected",
                "conflicting-advice-is-rejected",
                "advisor-requested-reentry-is-suppressed",
                "unchanged-follow-up-is-suppressed",
                "material-follow-up-is-bounded",
                "pro-correction-does-not-force-sol-loop",
                "mandatory-final-sol-review-is-suppressed",
                "implementer-role-is-rejected",
                "wrong-client-profile-is-rejected",
                "wrong-workspace-profile-is-rejected",
                "wrong-profile-key-is-rejected",
                "legacy-reviewer-config-is-rejected",
                "advisor-invocation-failure-stops",
                "runtime-attestation-unavailable",
                "runtime-role-mismatch-is-rejected",
                "runtime-model-mismatch-is-rejected",
                "runtime-effort-mismatch-is-rejected",
                "runtime-writable-sandbox-is-rejected",
                "missing-client-profile-is-rejected",
                "missing-profile-key-is-rejected",
                "retained-implementer-config-is-rejected",
                "runtime-permission-missing-is-rejected",
                "runtime-permission-blank-is-rejected",
                "public-native-attestation-is-preferred",
                "inspector-fills-public-omissions",
                "inspector-thread-mismatch-stops",
                "self-claims-do-not-establish-provenance",
                "luna-is-default-implementation-worker",
                "luna-same-root-cause-escalates-terra",
                "difficult-scope-starts-at-terra",
                "terra-blocker-uses-sol-read-only-advice",
                "test-economy-policy-is-explicit",
            },
            set(cases),
        )

        for case_id, case in cases.items():
            with self.subTest(case_id=case_id):
                scenario = case["scenario"]
                if scenario.get("intent") == "combined":
                    if scenario.get("runtime_inspector_output") is not None:
                        output = scenario["runtime_inspector_output"]
                        scenario = {
                            **scenario,
                            **inspector_evidence(
                                str(scenario.get("advisor_thread_id"))
                            ),
                            "runtime_inspector_output": output,
                        }
                    scenario = attested_combined(**scenario)
                actual = POLICY.route(
                    scenario,
                    trusted_catalog=trusted_catalog_context(),
                )
                for key, value in case["expect"].items():
                    self.assertEqual(value, actual.get(key), key)

    def test_consultation_packet_is_bounded_and_dispositioned(self) -> None:
        source = {
            "frozen_constraints": ["REQ-009"],
            "verified_local_evidence": ["focused tests pass"],
            "alternatives": ["skip consultation"],
            "risks": ["authority drift"],
            "precise_question": "Does this boundary justify one lane?",
            "complete_conversation_history": "excluded",
            "unrelated_repository_content": "excluded",
            "secrets": "excluded",
            "credentials": "excluded",
        }
        packet = POLICY.bounded_packet(source)
        disposition = POLICY.evaluate_advice(
            {"text": "Use the safe subset only", "useful_subset": True}
        )
        self.assertEqual(
            {
                "frozen_constraints",
                "verified_local_evidence",
                "alternatives",
                "risks",
                "precise_question",
            },
            set(packet),
        )
        self.assertTrue(set(source) - set(packet))
        self.assertEqual(
            {
                "disposition": "partially accept",
                "rationale": "Use only the compatible, evidence-supported subset.",
            },
            disposition,
        )

    def test_pressure_results_retain_five_red_and_five_green_traces(self) -> None:
        results = json.loads(PRESSURE_RESULTS.read_text(encoding="utf-8"))
        self.assertEqual(5, len(results["baseline"]))
        self.assertEqual(5, len(results["with_skill"]))
        self.assertEqual(
            1,
            sum(item["contract_violation"] for item in results["baseline"]),
        )
        self.assertTrue(
            all(not item["contract_violation"] for item in results["with_skill"])
        )
        replay_scenarios = {
            "pro-green-valid": attested_combined(
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Does the bounded decision preserve the contract?",
                material_risk=True,
                decision_value=True,
            ),
            "pro-green-opaque-permission": attested_combined(
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Is the permission profile auditable?",
                material_risk=True,
                decision_value=True,
                observed_permission_profile="custom-host-policy-v7",
            ),
            "pro-green-invocation-failure": attested_combined(
                advisor_invocation_succeeded=False,
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Did the bounded advisor invocation complete?",
                material_risk=True,
                decision_value=True,
            ),
            "pro-green-selfclaim": valid_combined(
                advisor_invocation_succeeded=True,
                observed_advisor_role="sol_advisor_advisor",
                observed_advisor_model="gpt-5.6-sol",
                observed_advisor_effort="high",
                observed_advisor_sandbox="read-only",
                observed_permission_profile="managed",
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Can advice-body self-claims replace attestation?",
                material_risk=True,
                decision_value=True,
            ),
            "pro-green-canonical": valid_combined(
                preferences_workspace="/repo/current/.",
                trusted_current_workspace="/repo/current",
                preferences_profile_key="codex:project:/repo/current/.",
                material_risk=False,
            ),
        }
        for trace in results["with_skill"]:
            with self.subTest(sample=trace["sample"]):
                self.assertFalse(trace["nested_orchestration"])
                self.assertFalse(trace["legacy_fallback"])
                self.assertTrue(trace["rationale"])
                self.assertTrue(trace["response_excerpt"])
                actual = POLICY.route(replay_scenarios[trace["sample"]])
                for key in (
                    "selected_mode",
                    "gpc_started",
                    "sol_calls",
                    "terminal",
                    "advice_admitted",
                    "advice_discarded",
                    "fallback_calls",
                ):
                    if key in trace:
                        self.assertEqual(trace[key], actual.get(key), key)

        provenance = results["provenance_hardening"]
        self.assertEqual(3, len(provenance["baseline"]))
        self.assertEqual(3, len(provenance["with_skill"]))
        self.assertTrue(
            all(item["contract_violation"] for item in provenance["baseline"])
        )
        provenance_replays = {
            "provenance-green-public": attested_combined(
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Does public metadata prove the route?",
                material_risk=True,
                decision_value=True,
            ),
            "provenance-green-inspector": attested_combined(
                public_runtime_observations={"role": "sol_advisor_advisor"},
                advisor_thread_id="11111111-1111-7111-8111-111111111111",
                **inspector_evidence(),
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Can the inspector fill omitted fields?",
                material_risk=True,
                decision_value=True,
            ),
            "provenance-green-selfclaim": valid_combined(
                advisor_invocation_succeeded=True,
                observed_advisor_role="sol_advisor_advisor",
                observed_advisor_model="gpt-5.6-sol",
                observed_advisor_effort="high",
                observed_advisor_sandbox="read-only",
                observed_permission_profile="managed",
                codex_commitment_boundary=True,
                concrete_question=True,
                precise_question="Can self-claims establish provenance?",
                material_risk=True,
                decision_value=True,
            ),
        }
        for trace in provenance["with_skill"]:
            with self.subTest(sample=trace["sample"]):
                actual = POLICY.route(
                    provenance_replays[trace["sample"]],
                    trusted_catalog=trusted_catalog_context(),
                )
                for key in (
                    "advice_admitted",
                    "advice_discarded",
                    "terminal",
                    "runtime_attestation_source",
                ):
                    if key in trace:
                        self.assertEqual(trace[key], actual.get(key), key)

    def test_has_human_and_codex_metadata(self) -> None:
        self.assertTrue((SKILL_ROOT / "README.md").is_file())
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("$orchestrate-gpt-pro-sol-advisor", metadata)
        self.assertIn("単独", self.readme)
        self.assertIn("併用", self.readme)
        self.assertIn("Luna", self.readme)
        self.assertIn("Test Economy", self.readme)


if __name__ == "__main__":
    unittest.main()
