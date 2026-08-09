#!/usr/bin/env python3
"""Issue deterministic receipts for already-routed bounded Sol consultation."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
from typing import Any, Mapping


RECEIPT_SCHEMA_VERSION = 1
ISSUER_SKILL = "orchestrate-gpt-pro-sol-advisor"
ISSUER_VERSION = "1"
ADVISOR_ROLE = "sol_advisor_advisor"
CODEX_ADVISOR_ROLE = ADVISOR_ROLE
SCENARIO_DIGEST_DOMAIN = "orchestrate-gpt-pro-sol-advisor/scenario/v1"
SETUP_FAILURES = {"missing", "schema-old", "corrupt"}
PROFILE_SCOPES = {"project", "user"}
DISPOSITIONS = frozenset({"accept", "reject", "partially accept"})
NO_CONSULTATION_REASONS = frozenset(
    {
        "NOT_APPLICABLE",
        "NO_MATERIAL_UNCERTAINTY",
        "POLICY_NOT_REQUIRED",
        "ADVISOR_UNAVAILABLE",
    }
)

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_EXECUTION_ID = re.compile(r"EXEC-[A-Z0-9][A-Z0-9-]{0,63}\Z")
_INVOCATION_ID = re.compile(r"INV-[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
RUNTIME_FIELDS = {
    "role": "observed_advisor_role",
    "model": "observed_advisor_model",
    "effort": "observed_advisor_effort",
    "sandbox": "observed_advisor_sandbox",
    "permission_profile": "observed_permission_profile",
}
_RUNTIME_SCENARIO_FIELDS = RUNTIME_FIELDS


class ReceiptError(ValueError):
    """The routed outcome cannot safely produce a governance receipt."""


def _fail(message: str) -> None:
    raise ReceiptError(message)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ReceiptError("Receipt data is not canonical JSON.") from error


def scenario_digest(scenario: Mapping[str, Any]) -> str:
    """Bind a route result to exact canonical scenario input in the v1 domain."""
    if not isinstance(scenario, dict):
        _fail("Scenario must be an object.")
    value = {
        "domain": SCENARIO_DIGEST_DOMAIN,
        "scenario": scenario,
    }
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


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


def _runtime_attestation(
    scenario: dict[str, Any], advisor_role: str
) -> dict[str, Any] | None:
    observed = _runtime_observations(scenario)
    audit = {
        "runtime_observations": observed,
        "runtime_observation_trusted": scenario.get("runtime_observation_trusted")
        is True,
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


def route(scenario: dict[str, Any]) -> dict[str, Any]:
    """Return the authoritative pre-Task7 composition route result."""
    intent = scenario["intent"]
    if intent == "gpt-pro-only":
        return {
            "selected_mode": intent,
            "gpt_pro_calls": 1,
            "sol_calls": 0,
            "terminal": "continue-outer-loop",
        }
    if intent == "sol-only":
        return {
            "selected_mode": intent,
            "gpt_pro_calls": 0,
            "sol_calls": 1,
            "terminal": "continue-sol-standalone",
        }
    if intent != "combined":
        return {
            "selected_mode": "unselected",
            "composition_active": False,
            "sol_calls": 0,
            "terminal": "clarify",
        }

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
        or any(
            not isinstance(role, str) or not role.strip()
            for role in available_roles
        )
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
        return {
            "selected_mode": "combined",
            "sol_calls": 0,
            **preserved,
            "terminal": "local-verify-then-pro",
        }
    if scenario.get("authority_escalation") or scenario.get(
        "conflicts_with_frozen_evidence"
    ):
        if failure := _advisor_invocation_failure(scenario):
            return failure
        if failure := _runtime_attestation(scenario, advisor_role):
            return failure
        disposition = evaluate_advice(scenario["sol_response"])
        return {
            "selected_mode": "combined",
            "sol_calls": scenario.get("prior_sol_calls", 1),
            "advice_admitted": 1,
            "advice_discarded": False,
            "downstream_advice_propagations": 0,
            "fallback_calls": 0,
            "runtime_observations": _runtime_observations(scenario),
            "runtime_observation_trusted": True,
            **disposition,
            **preserved,
            "terminal": "outer-protocol",
        }
    if (
        scenario.get("recursive")
        or scenario.get("duplicate")
        or scenario.get("advisor_reentry")
    ):
        if failure := _advisor_invocation_failure(scenario):
            return failure
        if failure := _runtime_attestation(scenario, advisor_role):
            return failure
        disposition = evaluate_advice(
            scenario.get("sol_response", {"requests_outer_restart": True})
        )
        return {
            "selected_mode": "combined",
            "sol_calls": scenario.get("prior_sol_calls", 0),
            "advice_admitted": 1,
            "advice_discarded": False,
            "downstream_advice_propagations": 0,
            "fallback_calls": 0,
            "runtime_observations": _runtime_observations(scenario),
            "runtime_observation_trusted": True,
            **disposition,
            **preserved,
            "recursion": False,
            "sol_to_sol": False,
            "terminal": "outer-protocol",
        }
    if scenario.get("follow_up") and not scenario.get("materially_new"):
        terminal = (
            "fix-verify-return-to-pro"
            if scenario.get("pro_correction")
            else "use-existing-disposition"
        )
        return {
            "selected_mode": "combined",
            "sol_calls": 0,
            **preserved,
            "terminal": terminal,
        }

    gate = all(
        scenario.get(key, False)
        for key in (
            "codex_commitment_boundary",
            "concrete_question",
            "material_risk",
            "decision_value",
        )
    ) and not scenario.get("equivalent_prior_advice", False)
    gate = gate and bool(scenario.get("precise_question", "").strip())
    if scenario.get("follow_up"):
        gate = gate and bool(scenario.get("stop_condition", "").strip())
    if not gate:
        return {
            "selected_mode": "combined",
            "sol_calls": 0,
            **preserved,
            "terminal": "local-verify-then-pro",
        }
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


def bounded_packet(context: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "frozen_constraints",
        "verified_local_evidence",
        "alternatives",
        "risks",
        "precise_question",
    )
    return {key: context[key] for key in allowed if key in context}


def evaluate_advice(advice: dict[str, Any]) -> dict[str, str]:
    if advice.get("requests_outer_restart"):
        return {
            "disposition": "reject",
            "rationale": "Sol cannot restart or control the outer loop.",
        }
    if advice.get("claims_approval"):
        return {
            "disposition": "reject",
            "rationale": "Sol cannot approve or alter frozen authority.",
        }
    if advice.get("conflicts_with_frozen_requirements") or advice.get(
        "conflicts_with_local_evidence"
    ):
        return {
            "disposition": "reject",
            "rationale": "Advice conflicts with frozen requirements or verified evidence.",
        }
    if advice.get("useful_subset"):
        return {
            "disposition": "partially accept",
            "rationale": "Use only the compatible, evidence-supported subset.",
        }
    return {
        "disposition": "accept",
        "rationale": "Advice is compatible with frozen requirements and verified evidence.",
    }


def _require_string(
    source: Mapping[str, Any], field: str, pattern: re.Pattern[str] | None = None
) -> str:
    value = source.get(field)
    if not isinstance(value, str) or not value or (
        pattern is not None and pattern.fullmatch(value) is None
    ):
        _fail(f"Invalid {field}.")
    return value


def _identity(scenario: Mapping[str, Any]) -> dict[str, Any]:
    execution_id = _require_string(scenario, "execution_id", _EXECUTION_ID)
    invocation_id = _require_string(scenario, "invocation_id", _INVOCATION_ID)
    input_digest = _require_string(scenario, "input_digest", _DIGEST)
    output_digest = _require_string(scenario, "output_digest", _DIGEST)
    authority_digest = _require_string(
        scenario, "authority_snapshot_digest", _DIGEST
    )
    nonce = _require_string(scenario, "nonce", _NONCE)
    expected_scenario_digest = scenario_digest(scenario)
    issued_at = scenario.get("issued_at_unix", 0)
    if not isinstance(issued_at, int) or isinstance(issued_at, bool) or issued_at < 0:
        _fail("issued_at_unix must be a non-negative integer.")
    return {
        "authority_snapshot_digest": authority_digest,
        "execution_id": execution_id,
        "input_digest": input_digest,
        "invocation_id": invocation_id,
        "issued_at_unix": issued_at,
        "issuer_skill": ISSUER_SKILL,
        "issuer_version": ISSUER_VERSION,
        "nonce": nonce,
        "output_digest": output_digest,
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "scenario_digest": expected_scenario_digest,
    }


def _runtime_binding(
    scenario: Mapping[str, Any], route_result: Mapping[str, Any]
) -> dict[str, Any]:
    if scenario.get("advisor_invocation_succeeded") is not True:
        _fail("Consultation requires explicit advisor invocation success.")
    if scenario.get("runtime_observation_trusted") is not True:
        _fail("Consultation requires trusted runtime observations.")
    expected = {
        "role": ADVISOR_ROLE,
        "model": scenario.get("expected_advisor_model"),
        "effort": scenario.get("expected_advisor_effort"),
        "sandbox": "read-only",
        "permission_profile": scenario.get("observed_permission_profile"),
    }
    if scenario.get("configured_advisor_role") != ADVISOR_ROLE:
        _fail("Consultation is not bound to the configured advisor role.")
    for name, scenario_field in _RUNTIME_SCENARIO_FIELDS.items():
        observed = scenario.get(scenario_field)
        if not isinstance(observed, str) or not observed.strip():
            _fail(f"Runtime {name} observation is missing.")
        if observed != expected[name]:
            _fail(f"Runtime {name} observation does not match the binding.")
    routed_observations = route_result.get("runtime_observations")
    if not isinstance(routed_observations, dict) or routed_observations != {
        name: scenario[field] for name, field in _RUNTIME_SCENARIO_FIELDS.items()
    }:
        _fail("Route result runtime observations do not match the scenario.")
    if route_result.get("runtime_observation_trusted") is not True:
        _fail("Route result does not preserve trusted runtime provenance.")
    return {
        "advice_admitted": 1,
        "advisor_invocation_succeeded": True,
        **expected,
        "runtime_attested": True,
        "runtime_observation_trusted": True,
    }


def _closed_disposition(value: Any, label: str) -> str:
    if not isinstance(value, str) or value not in DISPOSITIONS:
        _fail(f"{label} is not in the closed disposition set.")
    return value


def _disposition_value(
    route_result: Mapping[str, Any], disposition: Mapping[str, str] | None
) -> str:
    if not isinstance(disposition, dict) or set(disposition) not in (
        {"disposition"},
        {"disposition", "rationale"},
    ):
        _fail("Disposition must use the closed disposition schema.")
    value = _closed_disposition(disposition.get("disposition"), "Disposition")
    if "rationale" in disposition and not isinstance(disposition["rationale"], str):
        _fail("Disposition rationale must be a string when supplied.")
    if "disposition" in route_result:
        routed_value = _closed_disposition(
            route_result["disposition"], "Routed disposition"
        )
        if routed_value != value:
            _fail("Supplied disposition contradicts the routed disposition.")
    return value


def _consultation_receipt(
    scenario: Mapping[str, Any],
    route_result: Mapping[str, Any],
    disposition: Mapping[str, str] | None,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    selected_mode = _require_string(route_result, "selected_mode")
    if selected_mode != "combined":
        _fail("Consultation route is not active combined mode.")
    admitted = route_result.get("advice_admitted")
    if not isinstance(admitted, int) or isinstance(admitted, bool) or admitted != 1:
        _fail("Consultation requires exactly one admitted advice outcome.")
    if route_result.get("advice_discarded") is not False:
        _fail("Discarded advice cannot produce a consultation receipt.")
    sol_calls = route_result.get("sol_calls")
    if not isinstance(sol_calls, int) or isinstance(sol_calls, bool) or sol_calls < 1:
        _fail("Consultation requires a successful Sol invocation.")
    terminal = _require_string(route_result, "terminal")
    if terminal not in {"primary-disposition", "outer-protocol"}:
        _fail("Route result is not an admitted consultation outcome.")
    value = _disposition_value(route_result, disposition)
    receipt = {
        **identity,
        "binding": _runtime_binding(scenario, route_result),
        "disposition": value,
        "receipt_type": "consultation",
    }
    return _with_receipt_id(receipt)


def _no_consultation_reason(
    scenario: Mapping[str, Any], selected_mode: str, terminal: str
) -> str:
    explicit = scenario.get("no_consultation_reason")
    if explicit is not None:
        if not isinstance(explicit, str) or explicit not in NO_CONSULTATION_REASONS:
            _fail("Unknown no-consultation reason.")
        reason = explicit
    elif selected_mode == "gpt-pro-only" and terminal == "continue-outer-loop":
        reason = "NOT_APPLICABLE"
    elif (
        selected_mode == "combined"
        and terminal == "local-verify-then-pro"
        and scenario.get("material_risk") is False
    ):
        reason = "NO_MATERIAL_UNCERTAINTY"
    elif (
        selected_mode == "gpt-pro-only"
        and terminal == "continue-outer-loop"
        and scenario.get("consultation_policy_required") is False
    ):
        reason = "POLICY_NOT_REQUIRED"
    else:
        _fail("Route has no closed no-consultation reason.")

    if reason == "NOT_APPLICABLE" and not (
        scenario.get("intent") == "gpt-pro-only"
        and selected_mode == "gpt-pro-only"
        and terminal == "continue-outer-loop"
    ):
        _fail("NOT_APPLICABLE requires the exact GPT Pro standalone route.")
    if reason == "NO_MATERIAL_UNCERTAINTY" and not (
        scenario.get("intent") == "combined"
        and selected_mode == "combined"
        and terminal == "local-verify-then-pro"
        and scenario.get("material_risk") is False
    ):
        _fail("NO_MATERIAL_UNCERTAINTY requires an explicit low-risk observation.")
    if reason == "POLICY_NOT_REQUIRED" and not (
        selected_mode == "gpt-pro-only"
        and terminal == "continue-outer-loop"
        and scenario.get("consultation_policy_required") is False
    ):
        _fail("POLICY_NOT_REQUIRED requires explicit policy evidence.")
    if reason == "ADVISOR_UNAVAILABLE" and not (
        scenario.get("intent") == "standalone"
        and selected_mode == "unselected"
        and terminal == "clarify"
        and scenario.get("standalone_policy_allows_advisor_unavailable") is True
        and scenario.get("advisor_availability_is_runtime_dependency") is False
    ):
        _fail("ADVISOR_UNAVAILABLE is allowed only by explicit standalone policy.")
    return reason


def _no_consultation_receipt(
    scenario: Mapping[str, Any],
    route_result: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    selected_mode = _require_string(route_result, "selected_mode")
    terminal = _require_string(route_result, "terminal")
    if selected_mode == "combined-unavailable":
        _fail("Combined-mode failures are hard stops and emit no receipt.")
    if "advice_admitted" in route_result:
        admitted = route_result["advice_admitted"]
        if (
            not isinstance(admitted, int)
            or isinstance(admitted, bool)
            or admitted != 0
        ):
            _fail("No-consultation requires zero admitted advice outcomes.")
    if "disposition" in route_result:
        _closed_disposition(route_result["disposition"], "Routed disposition")
        _fail("No-consultation route cannot carry a disposition.")
    sol_calls = route_result.get("sol_calls")
    if not isinstance(sol_calls, int) or isinstance(sol_calls, bool) or sol_calls != 0:
        _fail("No-consultation requires zero Sol calls.")
    if terminal.startswith("advisor-") or terminal in {
        "setup-required-before-gpc",
        "setup-status-unavailable",
        "fresh-task-required",
        "preferences-unavailable",
    }:
        _fail("Dependency failure cannot be normalized as no consultation.")
    receipt = {
        **identity,
        "reason_code": _no_consultation_reason(
            scenario, selected_mode, terminal
        ),
        "receipt_type": "no-consultation",
    }
    return _with_receipt_id(receipt)


def _with_receipt_id(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt_id = "RCP-SOL-" + hashlib.sha256(_canonical_bytes(receipt)).hexdigest()[
        :20
    ].upper()
    return {**receipt, "receipt_id": receipt_id}


def governance_receipt(
    scenario: dict[str, Any],
    route_result: dict[str, Any],
    disposition: dict[str, str] | None,
) -> dict[str, Any]:
    """Normalize an admitted route outcome into a closed, immutable audit receipt."""
    if not isinstance(scenario, dict) or not isinstance(route_result, dict):
        _fail("Scenario and route_result must be objects.")
    authoritative_route = route(scenario)
    if _canonical_bytes(route_result) != _canonical_bytes(authoritative_route):
        _fail("Supplied route_result does not match authoritative routing.")
    identity = _identity(scenario)
    if authoritative_route.get("advice_admitted") == 1:
        return _consultation_receipt(
            scenario, authoritative_route, disposition, identity
        )
    if disposition is not None:
        _fail("No-consultation cannot carry a disposition.")
    return _no_consultation_receipt(scenario, authoritative_route, identity)
