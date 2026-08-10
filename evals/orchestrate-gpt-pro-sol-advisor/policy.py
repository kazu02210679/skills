"""Deterministic behavioral harness for the composition policy."""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path
from typing import Any


SETUP_FAILURES = {"missing", "schema-old", "corrupt"}
CODEX_ADVISOR_ROLE = "sol_advisor_advisor"
TERRA_IMPLEMENTER_ROLE = "sol_advisor_terra_implementer"
LUNA_MODEL = "gpt-5.6-luna"
TERRA_MODEL = "gpt-5.6-terra"
LUNA_REQUIRED_CAPABILITIES = frozenset(
    {
        "list_projects",
        "create_thread",
        "list_threads",
        "wait_threads",
        "read_thread",
        "send_message_to_thread",
    }
)
RUNTIME_FIELDS = {
    "role": "observed_advisor_role",
    "model": "observed_advisor_model",
    "effort": "observed_advisor_effort",
    "sandbox": "observed_advisor_sandbox",
    "permission_profile": "observed_permission_profile",
}
PROFILE_SCOPES = {"project", "user"}
PUBLIC_RUNTIME_SOURCE = "public-native-details"
INSPECTOR_RUNTIME_SOURCE = "local-runtime-inspector"
HOST_COMPLETION_SOURCES = {"native-result", "native-wait", "native-details"}
INSPECTOR_OUTPUT_FIELDS = {
    "thread_id",
    "parent_thread_id",
    "agent_role",
    "agent_path",
    "model_provider",
    "model",
    "effort",
    "sandbox_policy_type",
    "permission_profile_type",
    "cwd",
}
THREAD_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def canonical_workspace(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return ""
    try:
        if os.name == "nt" and value.startswith("/") and not value.startswith("//"):
            return posixpath.normpath(value)
        return os.path.normcase(
            os.path.realpath(os.path.abspath(os.path.normpath(value)))
        )
    except (OSError, ValueError):
        return ""


def canonical_file(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return ""
    try:
        if os.name == "nt" and value.startswith("/") and not value.startswith("//"):
            return posixpath.normpath(value)
        if not os.path.isabs(value):
            return ""
        return os.path.normcase(os.path.realpath(value))
    except (OSError, ValueError):
        return ""


def _is_within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((path, root)) == root
    except (OSError, ValueError):
        return False


def _official_inspector_path(
    scenario: dict[str, Any], trusted_catalog: dict[str, Any] | None
) -> str:
    selected_skill_path = canonical_file(
        (trusted_catalog or {}).get("selected_sol_advisor_orchestration_skill_path")
    )
    origin_skill_path = canonical_file(
        scenario.get("runtime_inspector_origin_skill_path")
    )
    script_path = canonical_file(scenario.get("runtime_inspector_script_path"))
    if (
        not selected_skill_path
        or not origin_skill_path
        or selected_skill_path != origin_skill_path
        or not script_path
        or not Path(selected_skill_path).is_file()
    ):
        return ""
    skill = Path(selected_skill_path)
    if (
        skill.name.casefold() != "skill.md"
        or skill.parent.name.casefold() != "orchestration"
        or skill.parent.parent.name.casefold() != "skills"
    ):
        return ""
    version_root = os.path.dirname(
        os.path.dirname(os.path.dirname(selected_skill_path))
    )
    if selected_skill_path.startswith("/"):
        expected = posixpath.normpath(
            posixpath.join(
                posixpath.dirname(selected_skill_path),
                "..",
                "..",
                "scripts",
                "inspect-agent-runtime.sh",
            )
        )
    else:
        expected = os.path.normcase(
            os.path.realpath(
                os.path.join(
                    os.path.dirname(selected_skill_path),
                    "..",
                    "..",
                    "scripts",
                    "inspect-agent-runtime.sh",
                )
            )
        )
    return (
        script_path
        if script_path == expected
        and _is_within(script_path, version_root)
        and Path(script_path).is_file()
        else ""
    )


def _failure(terminal: str, dependency: str) -> dict[str, Any]:
    return {
        "selected_mode": "combined-unavailable",
        "dependency": dependency,
        "gpc_started": False,
        "sol_calls": 0,
        "fabricated_consultation": False,
        "silent_downgrade": False,
        "compatibility_fallback": False,
        "advice_admitted": 0,
        "advice_accepted": False,
        "advice_discarded": True,
        "downstream_advice_propagations": 0,
        "fallback_calls": 0,
        "terminal": terminal,
    }


def _advisor_invocation_failure(scenario: dict[str, Any]) -> dict[str, Any] | None:
    if scenario.get("advisor_invocation_succeeded") is True:
        return None
    return {
        "selected_mode": "combined-unavailable",
        "dependency": "advisor-invocation",
        "gpc_started": True,
        "sol_calls": scenario.get("prior_sol_calls", 1),
        "advice_accepted": False,
        "advice_admitted": 0,
        "advice_discarded": True,
        "downstream_advice_propagations": 0,
        "fallback_calls": 0,
        "compatibility_fallback": False,
        "silent_downgrade": False,
        "terminal": "advisor-invocation-failed",
    }


def _runtime_failure(
    scenario: dict[str, Any],
    terminal: str,
    *,
    observations: dict[str, str] | None = None,
    sources: dict[str, str] | None = None,
    attestation_failure: str | None = None,
) -> dict[str, Any]:
    result = {
        "selected_mode": "combined-unavailable",
        "dependency": "advisor-runtime-attestation",
        "gpc_started": True,
        "sol_calls": scenario.get("prior_sol_calls", 1),
        "advice_accepted": False,
        "advice_admitted": 0,
        "advice_discarded": True,
        "downstream_advice_propagations": 0,
        "fallback_calls": 0,
        "compatibility_fallback": False,
        "silent_downgrade": False,
        "runtime_observations": observations or {},
        "runtime_observation_sources": sources or {},
        "runtime_observation_trusted": bool(sources),
        "terminal": terminal,
    }
    if attestation_failure is not None:
        result["attestation_failure"] = attestation_failure
    return result


def _observation_map(value: Any, *, allow_partial: bool) -> dict[str, str] | None:
    if not isinstance(value, dict) or any(key not in RUNTIME_FIELDS for key in value):
        return None
    if not allow_partial and set(value) != set(RUNTIME_FIELDS):
        return None
    observed: dict[str, str] = {}
    for field, raw in value.items():
        if not isinstance(raw, str) or not raw.strip():
            return None
        observed[field] = raw
    return observed


def _inspector_output(value: Any) -> tuple[str, dict[str, str]] | None:
    if not isinstance(value, dict) or set(value) != INSPECTOR_OUTPUT_FIELDS:
        return None
    thread_id = value["thread_id"]
    if not isinstance(thread_id, str) or THREAD_ID_PATTERN.fullmatch(thread_id) is None:
        return None
    for field in ("parent_thread_id", "agent_path", "model_provider", "cwd"):
        if value[field] is not None and not isinstance(value[field], str):
            return None
    observed = _observation_map(
        {
            "role": value["agent_role"],
            "model": value["model"],
            "effort": value["effort"],
            "sandbox": value["sandbox_policy_type"],
            "permission_profile": value["permission_profile_type"],
        },
        allow_partial=False,
    )
    return None if observed is None else (thread_id, observed)


def _runtime_attestation(
    scenario: dict[str, Any],
    advisor_role: str,
    trusted_catalog: dict[str, Any] | None,
    trusted_host: dict[str, Any] | None,
) -> dict[str, Any]:
    public = _observation_map(
        scenario.get("public_runtime_observations"), allow_partial=True
    )
    if public is None or "role" not in public:
        return _runtime_failure(scenario, "advisor-attestation-provenance-invalid")
    if public["role"] != advisor_role:
        return _runtime_failure(
            scenario,
            "advisor-attestation-mismatch",
            observations=public,
            sources={field: PUBLIC_RUNTIME_SOURCE for field in public},
            attestation_failure="role",
        )

    advisor_thread_id = scenario.get("advisor_thread_id")
    public_thread_id = scenario.get("public_runtime_thread_id")
    if (
        not isinstance(advisor_thread_id, str)
        or THREAD_ID_PATTERN.fullmatch(advisor_thread_id) is None
        or public_thread_id != advisor_thread_id
    ):
        return _runtime_failure(scenario, "advisor-attestation-thread-mismatch")

    completion = trusted_host if isinstance(trusted_host, dict) else {}
    if (
        completion.get("advisor_thread_id") != advisor_thread_id
        or completion.get("terminal_state") != "completed"
        or completion.get("source") not in HOST_COMPLETION_SOURCES
    ):
        return _runtime_failure(scenario, "advisor-completion-unavailable")

    missing = set(RUNTIME_FIELDS) - set(public)
    observed = dict(public)
    sources = {field: PUBLIC_RUNTIME_SOURCE for field in public}
    inspector_requested = (
        scenario.get("runtime_inspector_exit_code") is not None
        or scenario.get("runtime_inspector_origin_skill_path") is not None
        or scenario.get("runtime_inspector_script_path") is not None
        or scenario.get("runtime_inspector_output") is not None
    )

    if not missing and inspector_requested:
        return _runtime_failure(
            scenario,
            "advisor-attestation-provenance-invalid",
            observations=observed,
            sources=sources,
        )

    if missing:
        if (
            type(scenario.get("runtime_inspector_exit_code")) is not int
            or scenario.get("runtime_inspector_exit_code") != 0
            or not _official_inspector_path(scenario, trusted_catalog)
        ):
            return _runtime_failure(
                scenario,
                "advisor-attestation-inspector-unavailable",
                observations=observed,
                sources=sources,
            )
        inspected = _inspector_output(scenario.get("runtime_inspector_output"))
        if (
            inspected is None
            or inspected[0] != advisor_thread_id
        ):
            return _runtime_failure(
                scenario,
                "advisor-attestation-inspector-unavailable",
                observations=observed,
                sources=sources,
            )
        inspector_thread_id, inspector = inspected
        for field in set(public) & set(inspector):
            if public[field] != inspector[field]:
                return _runtime_failure(
                    scenario,
                    "advisor-attestation-mismatch",
                    observations=observed,
                    sources=sources,
                    attestation_failure=field,
                )
        for field in missing:
            observed[field] = inspector[field]
            sources[field] = INSPECTOR_RUNTIME_SOURCE

    expected = {
        "role": advisor_role,
        "model": str(scenario["expected_advisor_model"]),
        "effort": str(scenario["expected_advisor_effort"]),
        "sandbox": "read-only",
    }
    for field, expected_value in expected.items():
        if observed[field] != expected_value:
            return _runtime_failure(
                scenario,
                "advisor-attestation-mismatch",
                observations=observed,
                sources=sources,
                attestation_failure=field,
            )
    return {
        "runtime_observations": observed,
        "runtime_observation_sources": sources,
        "runtime_observation_trusted": True,
        "advisor_thread_id": advisor_thread_id,
        "public_runtime_thread_id": public_thread_id,
        "advisor_completion": {
            "thread_id": advisor_thread_id,
            "terminal_state": "completed",
            "source": completion["source"],
        },
        "runtime_inspector": (
            None
            if not missing
            else {
                "script": _official_inspector_path(scenario, trusted_catalog),
                "thread_id": inspector_thread_id,
                "rollout_count": 1,
                "inspection_status": "success",
                "exit_code": 0,
            }
        ),
        "runtime_attestation_source": (
            PUBLIC_RUNTIME_SOURCE
            if not missing
            else f"{PUBLIC_RUNTIME_SOURCE}+{INSPECTOR_RUNTIME_SOURCE}"
        ),
    }


def _worker_preflight(
    scenario: dict[str, Any], worker: str
) -> tuple[dict[str, Any], list[str]]:
    """Require observed runtime capability before claiming an implementation route."""

    field = f"{worker}_runtime_preflight"
    value = scenario.get(field)
    if not isinstance(value, dict):
        return {}, [f"{field}: missing native runtime observation"]

    if worker == "luna":
        expected_keys = {
            "source",
            "capabilities",
            "project_type",
            "workspace_mode",
            "model",
            "thinking",
            "task_status",
        }
        required_capabilities = LUNA_REQUIRED_CAPABILITIES
        expected_values = {
            "source": "native-capability-preflight",
            "project_type": "git",
            "workspace_mode": "worktree",
            "model": LUNA_MODEL,
            "thinking": "max",
            "task_status": "ready",
        }
    elif worker == "terra":
        expected_keys = {
            "source",
            "available_roles",
            "role",
            "model",
            "effort",
            "task_status",
        }
        expected_values = {
            "source": "native-role-preflight",
            "role": TERRA_IMPLEMENTER_ROLE,
            "model": TERRA_MODEL,
            "effort": "high",
            "task_status": "ready",
        }
    else:
        return {}, [f"{field}: unsupported worker"]

    errors: list[str] = []
    missing = sorted(expected_keys - set(value))
    unknown = sorted(set(value) - expected_keys)
    errors.extend(f"{field}: missing {item}" for item in missing)
    errors.extend(f"{field}: unknown {item}" for item in unknown)
    for key, expected in expected_values.items():
        if value.get(key) != expected:
            errors.append(f"{field}.{key}: expected {expected}")

    if worker == "luna":
        capabilities = value.get("capabilities")
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) or not item.strip() for item in capabilities
        ):
            errors.append(f"{field}.capabilities: must be a list of names")
        else:
            errors.extend(
                f"{field}.capabilities: missing {item}"
                for item in sorted(required_capabilities - set(capabilities))
            )
    else:
        roles = value.get("available_roles")
        if not isinstance(roles, list) or any(
            not isinstance(item, str) or not item.strip() for item in roles
        ):
            errors.append(f"{field}.available_roles: must be a list of roles")
        elif TERRA_IMPLEMENTER_ROLE not in roles:
            errors.append(
                f"{field}.available_roles: missing {TERRA_IMPLEMENTER_ROLE}"
            )

    if errors:
        return {}, sorted(set(errors))
    return {
        "worker": worker,
        "source": str(value["source"]),
        "status": "ready",
    }, []


def _implementation_failure(
    scenario: dict[str, Any], preserved: dict[str, Any], worker: str, errors: list[str]
) -> dict[str, Any]:
    return {
        "selected_mode": "combined",
        "implementation_request": True,
        **preserved,
        "sol_calls": 0,
        "implementation_available": False,
        "dependency": f"{worker}-implementation-runtime",
        "preflight_errors": errors,
        "advice_admitted": 0,
        "advice_discarded": True,
        "fallback_calls": 0,
        "compatibility_fallback": False,
        "silent_downgrade": False,
        "terra_escalated": worker == "terra",
        "luna_attempts": scenario.get("luna_attempts", 0),
        "terminal": f"{worker}-capability-preflight-failed",
    }


def _implementation_route(
    scenario: dict[str, Any], preserved: dict[str, Any]
) -> dict[str, Any]:
    """Route a Codex-owned implementation without invoking Sol advisory logic."""

    common = {
        "selected_mode": "combined",
        "implementation_request": True,
        "sol_calls": 0,
        "max_parallel_luna_tasks": 2,
        **preserved,
    }
    same_root_cause_failed = bool(scenario.get("luna_same_root_cause_failed"))
    terra_required = bool(
        scenario.get("force_terra")
        or scenario.get("difficult_scope")
        or same_root_cause_failed
    )
    if terra_required:
        preflight, errors = _worker_preflight(scenario, "terra")
        if errors:
            return _implementation_failure(scenario, preserved, "terra", errors)
        if same_root_cause_failed:
            luna_preflight, luna_errors = _worker_preflight(scenario, "luna")
            if luna_errors:
                return _implementation_failure(
                    scenario, preserved, "luna", luna_errors
                )
        else:
            luna_preflight = None
        return {
            **common,
            "implementation_lane": TERRA_IMPLEMENTER_ROLE,
            "implementation_model": TERRA_MODEL,
            "implementation_effort": "high",
            "luna_attempts": 2 if same_root_cause_failed else 0,
            "terra_escalated": True,
            "implementation_available": True,
            "implementation_preflight": {
                "terra": preflight,
                **({"luna": luna_preflight} if luna_preflight else {}),
            },
            "terminal": "terra-implementation",
        }
    preflight, errors = _worker_preflight(scenario, "luna")
    if errors:
        return _implementation_failure(scenario, preserved, "luna", errors)
    return {
        **common,
        "implementation_lane": "luna",
        "implementation_model": LUNA_MODEL,
        "implementation_thinking": "max",
        "luna_attempts": 1,
        "terra_escalated": False,
        "implementation_available": True,
        "implementation_preflight": {"luna": preflight},
        "terminal": "luna-implementation",
    }


def route(
    scenario: dict[str, Any],
    *,
    trusted_catalog: dict[str, Any] | None = None,
    trusted_host: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intent = scenario["intent"]
    if intent == "gpt-pro-only":
        return {"selected_mode": intent, "gpt_pro_calls": 1, "sol_calls": 0, "terminal": "continue-outer-loop"}
    if intent == "sol-only":
        return {"selected_mode": intent, "gpt_pro_calls": 0, "sol_calls": 1, "terminal": "continue-sol-standalone"}
    if intent == "test-economy":
        return {
            "selected_mode": intent,
            "test_anchor_required": True,
            "test_delta_anchors_required": True,
            "verification_input_fingerprint_required": True,
            "skip_requires_same_fingerprint": True,
            "new_test_files_default": 0,
            "regression_tests_per_root_cause": 1,
            "default_verification_level": "L1",
            "full_suite_default": False,
            "rerun_unchanged_success": False,
            "compact_success_output": [
                "command",
                "exit code",
                "test count",
                "duration",
                "one-line summary",
            ],
            "compact_failure_output": [
                "command",
                "exit code",
                "failed test names",
                "relevant error excerpt",
                "full log path + digest",
            ],
            "terminal": "test-policy",
        }
    if intent != "combined":
        return {"selected_mode": "unselected", "composition_active": False, "sol_calls": 0, "terminal": "clarify"}

    if scenario.get("requested_dependency") == "sol-advisor:orchestration":
        return _failure("forbidden-nested-orchestration", "nested-orchestration")

    setup_status = scenario.get("setup_status", "unavailable")
    if setup_status in SETUP_FAILURES:
        return _failure("setup-required-before-gpc", "sol-setup")
    if setup_status != "ready":
        return _failure("setup-status-unavailable", "sol-setup-status")
    if scenario.get("setup_changed_this_task"):
        return _failure("fresh-task-required", "native-role-discovery")
    if not scenario.get("preferences_loaded"):
        return _failure("preferences-unavailable", "sol-preferences")

    client_value = scenario.get("preferences_client")
    client = client_value.strip() if isinstance(client_value, str) else ""
    if client != "codex":
        return _failure("profile-client-mismatch", "sol-profile")
    preferences_workspace = scenario.get("preferences_workspace")
    workspace = canonical_workspace(preferences_workspace)
    current_workspace = canonical_workspace(scenario.get("trusted_current_workspace"))
    if not workspace or not current_workspace or workspace != current_workspace:
        return _failure("profile-workspace-mismatch", "sol-profile")
    scope_value = scenario.get("preferences_scope")
    scope = scope_value.strip() if isinstance(scope_value, str) else ""
    if scope not in PROFILE_SCOPES:
        return _failure("profile-scope-invalid", "sol-profile")
    expected_profile_key = f"codex:{scope}:{preferences_workspace}"
    profile_key = scenario.get("preferences_profile_key")
    if not isinstance(profile_key, str) or profile_key != expected_profile_key:
        return _failure("profile-key-mismatch", "sol-profile")
    expected_model = scenario.get("expected_advisor_model")
    expected_effort = scenario.get("expected_advisor_effort")
    if (
        not isinstance(expected_model, str)
        or not expected_model.strip()
        or not isinstance(expected_effort, str)
        or not expected_effort.strip()
    ):
        return _failure("advisor-preference-invalid", "sol-preferences")

    advisor_role = str(scenario.get("configured_advisor_role", "")).strip()
    if advisor_role != CODEX_ADVISOR_ROLE:
        return _failure("configured-advisor-invalid", "configured-advisor")
    if scenario.get("configured_combined_roles") != [CODEX_ADVISOR_ROLE]:
        return _failure("configured-role-set-invalid", "configured-advisor")
    available_roles = scenario.get("available_roles")
    if (
        not isinstance(available_roles, list)
        or any(not isinstance(role, str) or not role.strip() for role in available_roles)
    ):
        return _failure("available-roles-invalid", "configured-advisor")
    if advisor_role not in available_roles:
        return _failure("configured-advisor-unavailable", "configured-advisor")

    requested_role = scenario.get("requested_role")
    if requested_role and requested_role != advisor_role:
        return _failure("non-advisor-role-rejected", "advisory-role")

    preserved = {
        "gpc_started": True,
        "frozen_requirements": True,
        "user_approval_authority": "user-and-outer-protocol",
        "repository_owner": "codex",
        "local_verification_retained": True,
        "pro_review_retained": True,
    }
    if scenario.get("implementation_request") and not scenario.get("terra_blocked"):
        return _implementation_route(scenario, preserved)
    if scenario.get("implementation_request") and scenario.get("terra_blocked"):
        preflight, errors = _worker_preflight(scenario, "terra")
        if errors:
            return _implementation_failure(scenario, preserved, "terra", errors)
    if scenario.get("mandatory_final_sol_review"):
        return {"selected_mode": "combined", "sol_calls": 0, **preserved, "terminal": "local-verify-then-pro"}
    if scenario.get("authority_escalation") or scenario.get("conflicts_with_frozen_evidence"):
        if failure := _advisor_invocation_failure(scenario):
            return failure
        attestation = _runtime_attestation(
            scenario, advisor_role, trusted_catalog, trusted_host
        )
        if "terminal" in attestation:
            return attestation
        disposition = evaluate_advice(scenario["sol_response"])
        return {"selected_mode": "combined", "sol_calls": scenario.get("prior_sol_calls", 1), "advice_admitted": 1, "advice_discarded": False, "downstream_advice_propagations": 0, "fallback_calls": 0, **attestation, **disposition, **preserved, "terminal": "outer-protocol"}
    if scenario.get("recursive") or scenario.get("duplicate") or scenario.get("advisor_reentry"):
        if failure := _advisor_invocation_failure(scenario):
            return failure
        attestation = _runtime_attestation(
            scenario, advisor_role, trusted_catalog, trusted_host
        )
        if "terminal" in attestation:
            return attestation
        disposition = evaluate_advice(scenario.get("sol_response", {"requests_outer_restart": True}))
        return {"selected_mode": "combined", "sol_calls": scenario.get("prior_sol_calls", 0), "advice_admitted": 1, "advice_discarded": False, "downstream_advice_propagations": 0, "fallback_calls": 0, **attestation, **disposition, **preserved, "recursion": False, "sol_to_sol": False, "terminal": "outer-protocol"}
    if scenario.get("follow_up") and not scenario.get("materially_new"):
        terminal = "fix-verify-return-to-pro" if scenario.get("pro_correction") else "use-existing-disposition"
        return {"selected_mode": "combined", "sol_calls": 0, **preserved, "terminal": terminal}

    gate = all(
        scenario.get(key, False)
        for key in ("codex_commitment_boundary", "concrete_question", "material_risk", "decision_value")
    ) and not scenario.get("equivalent_prior_advice", False)
    gate = gate and bool(scenario.get("precise_question", "").strip())
    if scenario.get("follow_up"):
        gate = gate and bool(scenario.get("stop_condition", "").strip())
    if not gate:
        return {"selected_mode": "combined", "sol_calls": 0, **preserved, "terminal": "local-verify-then-pro"}
    if failure := _advisor_invocation_failure(scenario):
        return failure
    attestation = _runtime_attestation(
        scenario, advisor_role, trusted_catalog, trusted_host
    )
    if "terminal" in attestation:
        return attestation
    result = {
        "selected_mode": "combined",
        "selected_lane": advisor_role,
        "sol_calls": 1,
        "maximum_lanes": 1,
        "requires_stop_condition": bool(scenario.get("follow_up")),
        "runtime_attested": True,
        **attestation,
        "advice_admitted": 1,
        "advice_discarded": False,
        "downstream_advice_propagations": 0,
        "fallback_calls": 0,
        "advice_eligible_for_disposition": True,
        **preserved,
        "terminal": "primary-disposition",
    }
    if scenario.get("implementation_request") and scenario.get("terra_blocked"):
        result.update(
            {
                "implementation_escalation": "terra-blocked",
                "implementation_lane": "sol-advisor-read-only",
                "sol_is_implementation": False,
                "terra_escalated": True,
                "luna_attempts": scenario.get("luna_attempts", 2),
            }
        )
    return result


def bounded_packet(context: dict[str, Any]) -> dict[str, Any]:
    allowed = ("frozen_constraints", "verified_local_evidence", "alternatives", "risks", "precise_question")
    return {key: context[key] for key in allowed if key in context}


def evaluate_advice(advice: dict[str, Any]) -> dict[str, str]:
    if advice.get("requests_outer_restart"):
        return {"disposition": "reject", "rationale": "Sol cannot restart or control the outer loop."}
    if advice.get("claims_approval"):
        return {"disposition": "reject", "rationale": "Sol cannot approve or alter frozen authority."}
    if advice.get("conflicts_with_frozen_requirements") or advice.get("conflicts_with_local_evidence"):
        return {"disposition": "reject", "rationale": "Advice conflicts with frozen requirements or verified evidence."}
    if advice.get("useful_subset"):
        return {"disposition": "partially accept", "rationale": "Use only the compatible, evidence-supported subset."}
    return {"disposition": "accept", "rationale": "Advice is compatible with frozen requirements and verified evidence."}


def verification_reuse_decision(
    command: Any, current_fingerprint: Any, previous: Any
) -> dict[str, str]:
    """Skip only an unchanged successful verification, never by command text alone."""

    if not isinstance(command, str) or not command.strip():
        return {"action": "run", "reason": "invalid-command"}
    if not isinstance(current_fingerprint, str) or not current_fingerprint.strip():
        return {"action": "run", "reason": "missing-current-fingerprint"}
    if (
        isinstance(previous, dict)
        and previous.get("outcome") == "PASS"
        and previous.get("command") == command
        and previous.get("verification_input_fingerprint") == current_fingerprint
    ):
        return {"action": "skip", "reason": "unchanged-successful-input"}
    return {"action": "run", "reason": "verification-input-changed"}


def test_witness_decision(anchors: Any) -> dict[str, str]:
    """Require a bounded acceptance/risk/root-cause anchor for each new witness."""

    if not isinstance(anchors, list) or not anchors or any(
        not isinstance(anchor, str) or not anchor.strip() for anchor in anchors
    ):
        return {"action": "reject-test-addition", "reason": "missing-test-anchor"}
    return {"action": "allow-minimal-witness", "reason": "anchored-witness"}
