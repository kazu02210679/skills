"""Deterministic behavioral harness for the composition policy."""

from __future__ import annotations

import os
import posixpath
import re
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any


_FINGERPRINT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verification_fingerprint.py"
_FINGERPRINT_SPEC = spec_from_file_location("composition_verification_fingerprint", _FINGERPRINT_PATH)
if _FINGERPRINT_SPEC is None or _FINGERPRINT_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {_FINGERPRINT_PATH}")
_FINGERPRINT_MODULE = module_from_spec(_FINGERPRINT_SPEC)
_FINGERPRINT_SPEC.loader.exec_module(_FINGERPRINT_MODULE)
FingerprintError = _FINGERPRINT_MODULE.FingerprintError
compute_fingerprint = _FINGERPRINT_MODULE.compute_fingerprint


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
WORKER_IDENTITY_SOURCES = {
    "luna": frozenset({"native-create-thread", "native-thread-discovery"}),
    "terra": frozenset({"native-role-spawn", "native-role-discovery"}),
}
WORKER_TASK_STATES = frozenset({"created", "ready"})
EXECUTION_SOURCES = frozenset({"native-task-result", "native-wait", "native-details"})
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
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
    trusted_runtime: Any, worker: str
) -> tuple[dict[str, Any], list[str]]:
    """Validate native worker routing evidence supplied outside the scenario."""

    field = f"{worker}_runtime_preflight"
    if not isinstance(trusted_runtime, dict):
        return {}, [f"{field}: missing trusted native runtime observation"]

    identity_keys = {
        "project_id",
        "thread_id",
        "host_id",
        "identity_source",
        "task_state",
    }
    if worker == "luna":
        required_keys = {
            "source",
            "capabilities",
            "project_type",
            "workspace_mode",
            "requested_model",
            "requested_thinking",
            *identity_keys,
        }
        allowed_keys = required_keys | {
            "client_thread_id",
            "observed_model",
            "observed_thinking",
        }
        expected_values = {
            "source": "native-capability-preflight",
            "project_type": "git",
            "workspace_mode": "worktree",
            "requested_model": LUNA_MODEL,
            "requested_thinking": "max",
        }
    elif worker == "terra":
        required_keys = {
            "source",
            "available_roles",
            "requested_role",
            "role",
            "model",
            "effort",
            "role_template_path",
            "role_template_status",
            "role_template_digest",
            "shipped_role_template_digest",
            *identity_keys,
        }
        allowed_keys = required_keys
        expected_values = {
            "source": "native-role-preflight",
            "requested_role": TERRA_IMPLEMENTER_ROLE,
            "role": TERRA_IMPLEMENTER_ROLE,
            "model": TERRA_MODEL,
            "effort": "high",
            "role_template_status": "exact",
        }
    else:
        return {}, [f"{field}: unsupported worker"]

    errors: list[str] = []
    missing = sorted(required_keys - set(trusted_runtime))
    unknown = sorted(set(trusted_runtime) - allowed_keys)
    errors.extend(f"{field}: missing {item}" for item in missing)
    errors.extend(f"{field}: unknown {item}" for item in unknown)
    for key, expected in expected_values.items():
        if trusted_runtime.get(key) != expected:
            errors.append(f"{field}.{key}: expected {expected}")

    capabilities = trusted_runtime.get("capabilities")
    if worker == "luna":
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) or not item.strip() for item in capabilities
        ) or len(capabilities) != len(set(capabilities)):
            errors.append(f"{field}.capabilities: must be a unique list of names")
        elif not LUNA_REQUIRED_CAPABILITIES.issubset(set(capabilities)):
            errors.extend(
                f"{field}.capabilities: missing {item}"
                for item in sorted(LUNA_REQUIRED_CAPABILITIES - set(capabilities))
            )
        for optional, expected in (
            ("observed_model", LUNA_MODEL),
            ("observed_thinking", "max"),
        ):
            observed = trusted_runtime.get(optional)
            if observed is not None and observed != expected:
                errors.append(f"{field}.{optional}: expected {expected}")
    else:
        roles = trusted_runtime.get("available_roles")
        if not isinstance(roles, list) or any(
            not isinstance(item, str) or not item.strip() for item in roles
        ):
            errors.append(f"{field}.available_roles: must be a list of roles")
        elif TERRA_IMPLEMENTER_ROLE not in roles:
            errors.append(
                f"{field}.available_roles: missing {TERRA_IMPLEMENTER_ROLE}"
            )
        if trusted_runtime.get("role_template_digest") != trusted_runtime.get(
            "shipped_role_template_digest"
        ):
            errors.append(f"{field}: role template digest mismatch")
        for key in ("role_template_path", "role_template_digest", "shipped_role_template_digest"):
            if not isinstance(trusted_runtime.get(key), str) or not trusted_runtime[key].strip():
                errors.append(f"{field}.{key}: must be non-empty")
        for key in ("role_template_digest", "shipped_role_template_digest"):
            value = trusted_runtime.get(key)
            if isinstance(value, str) and DIGEST_PATTERN.fullmatch(value) is None:
                errors.append(f"{field}.{key}: must be a sha256 digest")

    for key in ("project_id", "host_id", "identity_source"):
        value = trusted_runtime.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field}.{key}: must be non-empty")
    thread_id = trusted_runtime.get("thread_id")
    if not isinstance(thread_id, str) or THREAD_ID_PATTERN.fullmatch(thread_id) is None:
        errors.append(f"{field}.thread_id: must be a real thread identity")
    if trusted_runtime.get("identity_source") not in WORKER_IDENTITY_SOURCES[worker]:
        errors.append(f"{field}.identity_source: unsupported native identity source")
    if trusted_runtime.get("task_state") not in WORKER_TASK_STATES:
        errors.append(f"{field}.task_state: must be a routing-ready state")
    client_thread_id = trusted_runtime.get("client_thread_id")
    if client_thread_id is not None and (
        not isinstance(client_thread_id, str)
        or not client_thread_id.strip()
        or client_thread_id == thread_id
    ):
        errors.append(f"{field}.client_thread_id: setup handle cannot be task identity")

    if errors:
        return {}, sorted(set(errors))
    result = {
        "worker": worker,
        "source": str(trusted_runtime["source"]),
        "status": "ready",
        "project_id": str(trusted_runtime["project_id"]),
        "thread_id": str(trusted_runtime["thread_id"]),
        "host_id": str(trusted_runtime["host_id"]),
        "identity_source": str(trusted_runtime["identity_source"]),
        "task_state": str(trusted_runtime["task_state"]),
    }
    if worker == "luna":
        result.update(
            {
                "requested_model": str(trusted_runtime["requested_model"]),
                "requested_thinking": str(trusted_runtime["requested_thinking"]),
            }
        )
        for key in ("observed_model", "observed_thinking"):
            if key in trusted_runtime:
                result[key] = str(trusted_runtime[key])
    else:
        result.update(
            {
                "role": str(trusted_runtime["role"]),
                "model": str(trusted_runtime["model"]),
                "effort": str(trusted_runtime["effort"]),
                "role_template_path": str(trusted_runtime["role_template_path"]),
                "role_template_status": str(trusted_runtime["role_template_status"]),
                "role_template_digest": str(trusted_runtime["role_template_digest"]),
            }
        )
    return result, []


def _execution_evidence(
    trusted_execution: Any,
    worker: str,
    route_evidence: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Validate native task outcome separately from routing attestation."""

    field = f"{worker}_execution_evidence"
    if not isinstance(trusted_execution, dict):
        return {}, [f"{field}: missing trusted native task result"]
    if worker == "luna":
        required_keys = {
            "source",
            "project_id",
            "thread_id",
            "host_id",
            "outcome",
            "root_cause_key",
            "attempt_count",
            "correction_count",
            "same_root_cause",
        }
        expected_outcomes = {"failed", "partial", "blocked"}
    elif worker == "terra":
        required_keys = {
            "source",
            "project_id",
            "thread_id",
            "host_id",
            "outcome",
            "high_impact_decision_pending",
            "decision_key",
        }
        expected_outcomes = {"blocked"}
    else:
        return {}, [f"{field}: unsupported worker"]

    errors: list[str] = []
    missing = sorted(required_keys - set(trusted_execution))
    unknown = sorted(set(trusted_execution) - required_keys)
    errors.extend(f"{field}: missing {item}" for item in missing)
    errors.extend(f"{field}: unknown {item}" for item in unknown)
    if trusted_execution.get("source") not in EXECUTION_SOURCES:
        errors.append(f"{field}.source: unsupported native task result")
    if trusted_execution.get("outcome") not in expected_outcomes:
        errors.append(f"{field}.outcome: unsupported execution outcome")
    for key in ("project_id", "thread_id", "host_id"):
        if trusted_execution.get(key) != route_evidence.get(key):
            errors.append(f"{field}.{key}: does not bind to routed task")
    if worker == "luna":
        if type(trusted_execution.get("attempt_count")) is not int or trusted_execution["attempt_count"] != 2:
            errors.append(f"{field}.attempt_count: must prove one initial attempt plus one correction")
        if type(trusted_execution.get("correction_count")) is not int or trusted_execution["correction_count"] != 1:
            errors.append(f"{field}.correction_count: must prove exactly one correction")
        if (
            type(trusted_execution.get("attempt_count")) is int
            and type(trusted_execution.get("correction_count")) is int
            and trusted_execution["attempt_count"] != trusted_execution["correction_count"] + 1
        ):
            errors.append(f"{field}: attempt/correction counts are inconsistent")
        if trusted_execution.get("same_root_cause") is not True:
            errors.append(f"{field}.same_root_cause: must be true")
        if not isinstance(trusted_execution.get("root_cause_key"), str) or not trusted_execution["root_cause_key"].strip():
            errors.append(f"{field}.root_cause_key: must be non-empty")
    else:
        if trusted_execution.get("high_impact_decision_pending") is not True:
            errors.append(f"{field}.high_impact_decision_pending: must be true")
        if not isinstance(trusted_execution.get("decision_key"), str) or not trusted_execution["decision_key"].strip():
            errors.append(f"{field}.decision_key: must be non-empty")
    if errors:
        return {}, sorted(set(errors))
    return {
        "source": str(trusted_execution["source"]),
        "outcome": str(trusted_execution["outcome"]),
        "thread_id": str(trusted_execution["thread_id"]),
        **(
            {
                "root_cause_key": str(trusted_execution["root_cause_key"]),
                "attempt_count": int(trusted_execution["attempt_count"]),
                "correction_count": int(trusted_execution["correction_count"]),
            }
            if worker == "luna"
            else {"decision_key": str(trusted_execution["decision_key"])}
        ),
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


def _execution_failure(
    scenario: dict[str, Any],
    preserved: dict[str, Any],
    worker: str,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "selected_mode": "combined",
        "implementation_request": True,
        **preserved,
        "sol_calls": 0,
        "implementation_available": False,
        "dependency": f"{worker}-execution-runtime",
        "execution_errors": errors,
        "advice_admitted": 0,
        "advice_discarded": True,
        "fallback_calls": 0,
        "compatibility_fallback": False,
        "silent_downgrade": False,
        "terra_escalated": worker == "terra",
        "luna_attempts": scenario.get("luna_attempts", 0),
        "terminal": f"{worker}-execution-evidence-failed",
    }


def _implementation_route(
    scenario: dict[str, Any],
    preserved: dict[str, Any],
    *,
    trusted_luna_runtime: dict[str, Any] | None,
    trusted_terra_runtime: dict[str, Any] | None,
    trusted_luna_execution: dict[str, Any] | None,
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
    luna_preflight: dict[str, Any] | None = None
    luna_execution: dict[str, Any] | None = None
    if same_root_cause_failed:
        luna_preflight, luna_errors = _worker_preflight(trusted_luna_runtime, "luna")
        if luna_errors:
            return _implementation_failure(scenario, preserved, "luna", luna_errors)
        luna_execution, execution_errors = _execution_evidence(
            trusted_luna_execution, "luna", luna_preflight
        )
        if execution_errors:
            return _execution_failure(
                scenario, preserved, "luna", execution_errors
            )

    if terra_required:
        preflight, errors = _worker_preflight(trusted_terra_runtime, "terra")
        if errors:
            return _implementation_failure(scenario, preserved, "terra", errors)
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
            **({"luna_execution": luna_execution} if luna_execution else {}),
            "terminal": "terra-implementation",
        }
    preflight, errors = _worker_preflight(trusted_luna_runtime, "luna")
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
    trusted_luna_runtime: dict[str, Any] | None = None,
    trusted_terra_runtime: dict[str, Any] | None = None,
    trusted_luna_execution: dict[str, Any] | None = None,
    trusted_terra_execution: dict[str, Any] | None = None,
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
            "primary_anchor_required": True,
            "also_proves_allowed": True,
            "anchor_catalog_required": [
                "acceptance_criteria",
                "material_risks",
                "root_cause_keys",
            ],
            "max_unjustified_cases_per_anchor": 5,
            "materially_distinct_justification_required": True,
            "test_delta_anchors_required": True,
            "verification_input_fingerprint_required": True,
            "fingerprint_computed_internally": True,
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
    terra_blocked_execution: dict[str, Any] | None = None
    if scenario.get("implementation_request") and not scenario.get("terra_blocked"):
        return _implementation_route(
            scenario,
            preserved,
            trusted_luna_runtime=trusted_luna_runtime,
            trusted_terra_runtime=trusted_terra_runtime,
            trusted_luna_execution=trusted_luna_execution,
        )
    if scenario.get("implementation_request") and scenario.get("terra_blocked"):
        preflight, errors = _worker_preflight(trusted_terra_runtime, "terra")
        if errors:
            return _implementation_failure(scenario, preserved, "terra", errors)
        terra_blocked_execution, execution_errors = _execution_evidence(
            trusted_terra_execution, "terra", preflight
        )
        if execution_errors:
            return _execution_failure(
                scenario, preserved, "terra", execution_errors
            )
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
                "implementation_preflight": {"terra": preflight},
                "terra_execution": terra_blocked_execution,
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
    repo: Any,
    command: Any,
    previous: Any,
) -> dict[str, str]:
    """Compute the current fingerprint internally before deciding to skip."""

    try:
        current_fingerprint = compute_fingerprint(Path(repo), command=command)
    except (FingerprintError, TypeError, ValueError):
        return {"action": "run", "reason": "fingerprint-unavailable"}
    if (
        isinstance(previous, dict)
        and previous.get("outcome") == "PASS"
        and previous.get("command") == command
        and previous.get("verification_input_fingerprint") == current_fingerprint
    ):
        return {"action": "skip", "reason": "unchanged-successful-input"}
    return {"action": "run", "reason": "verification-input-changed"}


def _anchor_catalog(value: Any) -> set[str] | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set, frozenset)):
        return None
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return set(value)


def test_witness_decision(
    witnesses: Any,
    valid_acceptance_ids: Any,
    valid_risk_ids: Any,
    valid_root_cause_keys: Any,
) -> dict[str, str]:
    """Require real acceptance/risk/root-cause anchors and bounded growth."""

    if not isinstance(witnesses, list) or not witnesses:
        return {"action": "reject-test-addition", "reason": "missing-test-anchor"}
    acceptance_ids = _anchor_catalog(valid_acceptance_ids)
    risk_ids = _anchor_catalog(valid_risk_ids)
    root_cause_keys = _anchor_catalog(valid_root_cause_keys)
    if acceptance_ids is None or risk_ids is None or root_cause_keys is None:
        return {"action": "reject-test-addition", "reason": "anchor-catalog-invalid"}
    valid_anchors = acceptance_ids | risk_ids | root_cause_keys
    seen: set[str] = set()
    for witness in witnesses:
        if not isinstance(witness, dict):
            return {"action": "reject-test-addition", "reason": "malformed-test-witness"}
        primary = witness.get("primary_anchor")
        if not isinstance(primary, str) or not primary.strip():
            return {"action": "reject-test-addition", "reason": "missing-primary-anchor"}
        if primary not in valid_anchors:
            return {"action": "reject-test-addition", "reason": "unknown-primary-anchor"}
        if primary in seen:
            if witness.get("materially_distinct") is not True or not isinstance(
                witness.get("justification"), str
            ) or not witness["justification"].strip():
                return {"action": "reject-test-addition", "reason": "duplicate-primary-anchor"}
        seen.add(primary)
        also_proves = witness.get("also_proves", [])
        if not isinstance(also_proves, list) or any(
            not isinstance(anchor, str) or not anchor.strip() for anchor in also_proves
        ):
            return {"action": "reject-test-addition", "reason": "malformed-secondary-anchor"}
        if any(anchor not in valid_anchors for anchor in also_proves):
            return {"action": "reject-test-addition", "reason": "unknown-secondary-anchor"}
        case_count = witness.get("case_count", 1)
        if type(case_count) is not int or case_count < 1:
            return {"action": "reject-test-addition", "reason": "invalid-case-count"}
        if case_count > 5 and (
            witness.get("materially_distinct") is not True
            or not isinstance(witness.get("justification"), str)
            or not witness["justification"].strip()
        ):
            return {"action": "reject-test-addition", "reason": "unbounded-anchor-growth"}
    return {"action": "allow-minimal-witness", "reason": "anchored-witness"}
