"""Deterministic behavioral harness for the composition policy."""

from __future__ import annotations

from typing import Any


SETUP_FAILURES = {"missing", "schema-old", "corrupt"}
IMPLEMENTER_ROLES = {
    "sol_advisor_routine",
    "sol_advisor_high",
    "sol_advisor_terra_implementer",
}


def _failure(terminal: str, dependency: str) -> dict[str, Any]:
    return {
        "selected_mode": "combined-unavailable",
        "dependency": dependency,
        "gpc_started": False,
        "sol_calls": 0,
        "fabricated_consultation": False,
        "silent_downgrade": False,
        "compatibility_fallback": False,
        "terminal": terminal,
    }


def route(scenario: dict[str, Any]) -> dict[str, Any]:
    intent = scenario["intent"]
    if intent == "gpt-pro-only":
        return {"selected_mode": intent, "gpt_pro_calls": 1, "sol_calls": 0, "terminal": "continue-outer-loop"}
    if intent == "sol-only":
        return {"selected_mode": intent, "gpt_pro_calls": 0, "sol_calls": 1, "terminal": "continue-sol-standalone"}
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

    advisor_role = str(scenario.get("configured_advisor_role", "")).strip()
    if not advisor_role or advisor_role in IMPLEMENTER_ROLES:
        return _failure("configured-advisor-invalid", "configured-advisor")
    if advisor_role not in scenario.get("available_roles", []):
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
        disposition = evaluate_advice(scenario["sol_response"])
        return {"selected_mode": "combined", "sol_calls": scenario.get("prior_sol_calls", 1), **disposition, **preserved, "terminal": "outer-protocol"}
    if scenario.get("recursive") or scenario.get("duplicate") or scenario.get("advisor_reentry"):
        disposition = evaluate_advice(scenario.get("sol_response", {"requests_outer_restart": True}))
        return {"selected_mode": "combined", "sol_calls": scenario.get("prior_sol_calls", 0), **disposition, **preserved, "recursion": False, "sol_to_sol": False, "terminal": "outer-protocol"}
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
    return {
        "selected_mode": "combined",
        "selected_lane": advisor_role,
        "sol_calls": 1,
        "maximum_lanes": 1,
        "requires_stop_condition": bool(scenario.get("follow_up")),
        **preserved,
        "terminal": "primary-disposition",
    }


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
