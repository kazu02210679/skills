"""Deterministic behavioral harness for the composition policy."""

from __future__ import annotations

import importlib.util
import os
import posixpath
from pathlib import Path
from typing import Any


RECEIPT_ISSUER_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "orchestrate-gpt-pro-sol-advisor"
    / "scripts"
    / "governance_receipt.py"
)
_RECEIPT_SPEC = importlib.util.spec_from_file_location(
    "sol_governance_receipt", RECEIPT_ISSUER_PATH
)
if _RECEIPT_SPEC is None or _RECEIPT_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {RECEIPT_ISSUER_PATH}")
RECEIPT_ISSUER = importlib.util.module_from_spec(_RECEIPT_SPEC)
_RECEIPT_SPEC.loader.exec_module(RECEIPT_ISSUER)
ReceiptError = RECEIPT_ISSUER.ReceiptError
NO_CONSULTATION_REASONS = RECEIPT_ISSUER.NO_CONSULTATION_REASONS
governance_receipt = RECEIPT_ISSUER.governance_receipt


SETUP_FAILURES = {"missing", "schema-old", "corrupt"}
CODEX_ADVISOR_ROLE = "sol_advisor_advisor"
RUNTIME_FIELDS = {
    "role": "observed_advisor_role",
    "model": "observed_advisor_model",
    "effort": "observed_advisor_effort",
    "sandbox": "observed_advisor_sandbox",
    "permission_profile": "observed_permission_profile",
}
PROFILE_SCOPES = {"project", "user"}


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


def _runtime_observations(scenario: dict[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, key in RUNTIME_FIELDS.items():
        value = scenario.get(key)
        observed[name] = value if isinstance(value, str) else ""
    return observed


def _runtime_attestation(scenario: dict[str, Any], advisor_role: str) -> dict[str, Any] | None:
    observed = _runtime_observations(scenario)
    audit = {
        "runtime_observations": observed,
        "runtime_observation_trusted": scenario.get("runtime_observation_trusted") is True,
    }
    if any(not value.strip() for value in observed.values()):
        return {
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
            **audit,
            "terminal": "advisor-attestation-unavailable",
        }
    if scenario.get("runtime_observation_trusted") is not True:
        return {
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
            **audit,
            "terminal": "advisor-attestation-untrusted",
        }
    expected = {
        "role": advisor_role,
        "model": str(scenario["expected_advisor_model"]),
        "effort": str(scenario["expected_advisor_effort"]),
        "sandbox": "read-only",
    }
    for field, expected_value in expected.items():
        if observed[field] != expected_value:
            return {
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
                **audit,
                "attestation_failure": field,
                "terminal": "advisor-attestation-mismatch",
            }
    return None


def _route_unbound(scenario: dict[str, Any]) -> dict[str, Any]:
    intent = scenario["intent"]
    if intent == "gpt-pro-only":
        return {"selected_mode": intent, "gpt_pro_calls": 1, "sol_calls": 0, "terminal": "continue-outer-loop"}
    if intent == "sol-only":
        return {"selected_mode": intent, "gpt_pro_calls": 0, "sol_calls": 1, "terminal": "continue-sol-standalone"}
    if intent == "standalone":
        return {"selected_mode": intent, "gpt_pro_calls": 0, "sol_calls": 0, "terminal": "continue-codex-standalone"}
    if intent != "combined":
        return {"selected_mode": "unselected", "composition_active": False, "sol_calls": 0, "terminal": "clarify"}

    if scenario.get("requested_dependency") == "sol-advisor:orchestration":
        return _failure("forbidden-nested-orchestration", "nested-orchestration")

    setup_status = scenario.get("setup_status", "unavailable")
    if isinstance(setup_status, str) and setup_status in SETUP_FAILURES:
        return _failure("setup-required-before-gpc", "sol-setup")
    if not isinstance(setup_status, str) or setup_status != "ready":
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
    if scenario.get("mandatory_final_sol_review"):
        return {"selected_mode": "combined", "sol_calls": 0, **preserved, "terminal": "local-verify-then-pro"}
    if scenario.get("authority_escalation") or scenario.get("conflicts_with_frozen_evidence"):
        if failure := _advisor_invocation_failure(scenario):
            return failure
        if failure := _runtime_attestation(scenario, advisor_role):
            return failure
        disposition = evaluate_advice(scenario["sol_response"])
        return {"selected_mode": "combined", "sol_calls": scenario.get("prior_sol_calls", 1), "advice_admitted": 1, "advice_discarded": False, "downstream_advice_propagations": 0, "fallback_calls": 0, "runtime_observations": _runtime_observations(scenario), "runtime_observation_trusted": True, **disposition, **preserved, "terminal": "outer-protocol"}
    if scenario.get("recursive") or scenario.get("duplicate") or scenario.get("advisor_reentry"):
        if failure := _advisor_invocation_failure(scenario):
            return failure
        if failure := _runtime_attestation(scenario, advisor_role):
            return failure
        disposition = evaluate_advice(scenario.get("sol_response", {"requests_outer_restart": True}))
        return {"selected_mode": "combined", "sol_calls": scenario.get("prior_sol_calls", 0), "advice_admitted": 1, "advice_discarded": False, "downstream_advice_propagations": 0, "fallback_calls": 0, "runtime_observations": _runtime_observations(scenario), "runtime_observation_trusted": True, **disposition, **preserved, "recursion": False, "sol_to_sol": False, "terminal": "outer-protocol"}
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
    if failure := _runtime_attestation(scenario, advisor_role):
        return failure
    return {
        "selected_mode": "combined",
        "selected_lane": advisor_role,
        "sol_calls": 1,
        "maximum_lanes": 1,
        "requires_stop_condition": bool(scenario.get("follow_up")),
        "runtime_attested": True,
        "runtime_observations": _runtime_observations(scenario),
        "runtime_observation_trusted": True,
        "advice_admitted": 1,
        "advice_discarded": False,
        "downstream_advice_propagations": 0,
        "fallback_calls": 0,
        "advice_eligible_for_disposition": True,
        **preserved,
        "terminal": "primary-disposition",
    }


def route(scenario: dict[str, Any]) -> dict[str, Any]:
    """Route once, then bind the closed result to the exact canonical scenario."""
    if not isinstance(scenario, dict):
        raise ReceiptError("Scenario must be an object.")
    routed = _route_unbound(scenario)
    routed["scenario_digest"] = RECEIPT_ISSUER.scenario_digest(scenario)
    routed.setdefault("advice_admitted", 0)
    for field in RECEIPT_ISSUER.ROUTE_IDENTITY_FIELDS:
        if field in scenario:
            routed[field] = scenario[field]
    return routed


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
