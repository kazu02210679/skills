#!/usr/bin/env python3
"""Issue deterministic receipts for already-routed bounded Sol consultation."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


RECEIPT_SCHEMA_VERSION = 1
ISSUER_SKILL = "orchestrate-gpt-pro-sol-advisor"
ISSUER_VERSION = "1"
ADVISOR_ROLE = "sol_advisor_advisor"
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
_IDENTITY_FIELDS = (
    "execution_id",
    "invocation_id",
    "input_digest",
    "output_digest",
    "authority_snapshot_digest",
    "nonce",
)
_RUNTIME_SCENARIO_FIELDS = {
    "role": "observed_advisor_role",
    "model": "observed_advisor_model",
    "effort": "observed_advisor_effort",
    "sandbox": "observed_advisor_sandbox",
    "permission_profile": "observed_permission_profile",
}


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


def _require_string(
    source: Mapping[str, Any], field: str, pattern: re.Pattern[str] | None = None
) -> str:
    value = source.get(field)
    if not isinstance(value, str) or not value or (
        pattern is not None and pattern.fullmatch(value) is None
    ):
        _fail(f"Invalid {field}.")
    return value


def _identity(scenario: Mapping[str, Any], route_result: Mapping[str, Any]) -> dict[str, Any]:
    execution_id = _require_string(scenario, "execution_id", _EXECUTION_ID)
    invocation_id = _require_string(scenario, "invocation_id", _INVOCATION_ID)
    input_digest = _require_string(scenario, "input_digest", _DIGEST)
    output_digest = _require_string(scenario, "output_digest", _DIGEST)
    authority_digest = _require_string(
        scenario, "authority_snapshot_digest", _DIGEST
    )
    nonce = _require_string(scenario, "nonce", _NONCE)
    for field in _IDENTITY_FIELDS:
        if field in route_result and route_result[field] != scenario[field]:
            _fail(f"Route result {field} does not match the scenario binding.")
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


def _scenario_can_consult(scenario: Mapping[str, Any]) -> bool:
    special_path = any(
        scenario.get(field) is True
        for field in (
            "authority_escalation",
            "conflicts_with_frozen_evidence",
            "recursive",
            "duplicate",
            "advisor_reentry",
        )
    )
    gate = all(
        scenario.get(field) is True
        for field in (
            "codex_commitment_boundary",
            "concrete_question",
            "material_risk",
            "decision_value",
        )
    )
    precise_question = scenario.get("precise_question")
    gate = gate and isinstance(precise_question, str) and bool(precise_question.strip())
    gate = gate and scenario.get("equivalent_prior_advice") is not True
    if scenario.get("follow_up") is True:
        stop_condition = scenario.get("stop_condition")
        gate = gate and scenario.get("materially_new") is True
        gate = gate and isinstance(stop_condition, str) and bool(stop_condition.strip())
    return special_path or gate


def _consultation_receipt(
    scenario: Mapping[str, Any],
    route_result: Mapping[str, Any],
    disposition: Mapping[str, str] | None,
) -> dict[str, Any]:
    if scenario.get("intent") != "combined" or not _scenario_can_consult(scenario):
        _fail("Scenario is not eligible for bounded consultation.")
    if route_result.get("selected_mode") != "combined":
        _fail("Consultation route is not active combined mode.")
    admitted = route_result.get("advice_admitted")
    if not isinstance(admitted, int) or isinstance(admitted, bool) or admitted != 1:
        _fail("Consultation requires exactly one admitted advice outcome.")
    if route_result.get("advice_discarded") is not False:
        _fail("Discarded advice cannot produce a consultation receipt.")
    sol_calls = route_result.get("sol_calls")
    if not isinstance(sol_calls, int) or isinstance(sol_calls, bool) or sol_calls < 1:
        _fail("Consultation requires a successful Sol invocation.")
    if route_result.get("terminal") not in {"primary-disposition", "outer-protocol"}:
        _fail("Route result is not an admitted consultation outcome.")
    if not isinstance(disposition, dict) or set(disposition) not in (
        {"disposition"},
        {"disposition", "rationale"},
    ):
        _fail("Disposition must use the closed disposition schema.")
    value = disposition.get("disposition")
    if value not in DISPOSITIONS:
        _fail("Disposition is not in the closed disposition set.")
    if "rationale" in disposition and not isinstance(disposition["rationale"], str):
        _fail("Disposition rationale must be a string when supplied.")
    receipt = {
        **_identity(scenario, route_result),
        "binding": _runtime_binding(scenario, route_result),
        "disposition": value,
        "receipt_type": "consultation",
    }
    return _with_receipt_id(receipt)


def _no_consultation_reason(
    scenario: Mapping[str, Any], route_result: Mapping[str, Any]
) -> str:
    explicit = scenario.get("no_consultation_reason")
    if explicit is not None:
        if not isinstance(explicit, str) or explicit not in NO_CONSULTATION_REASONS:
            _fail("Unknown no-consultation reason.")
        reason = explicit
    elif route_result.get("selected_mode") == "gpt-pro-only":
        reason = "NOT_APPLICABLE"
    elif scenario.get("material_risk") is False:
        reason = "NO_MATERIAL_UNCERTAINTY"
    elif scenario.get("consultation_policy_required") is False:
        reason = "POLICY_NOT_REQUIRED"
    else:
        _fail("Route has no closed no-consultation reason.")

    if reason == "NOT_APPLICABLE" and scenario.get("intent") == "combined":
        _fail("Combined mode is not a NOT_APPLICABLE consultation policy.")
    if reason == "NO_MATERIAL_UNCERTAINTY" and scenario.get("material_risk") is not False:
        _fail("NO_MATERIAL_UNCERTAINTY requires an explicit low-risk observation.")
    if reason == "POLICY_NOT_REQUIRED" and scenario.get("consultation_policy_required") is not False:
        _fail("POLICY_NOT_REQUIRED requires explicit policy evidence.")
    if reason == "ADVISOR_UNAVAILABLE" and not (
        scenario.get("intent") != "combined"
        and scenario.get("standalone_policy") is True
        and scenario.get("advisor_availability_runtime_dependency") is False
    ):
        _fail("ADVISOR_UNAVAILABLE is allowed only by explicit standalone policy.")
    return reason


def _no_consultation_receipt(
    scenario: Mapping[str, Any], route_result: Mapping[str, Any]
) -> dict[str, Any]:
    if route_result.get("selected_mode") == "combined-unavailable":
        _fail("Combined-mode failures are hard stops and emit no receipt.")
    if route_result.get("advice_admitted") == 1:
        _fail("Admitted advice requires a dispositioned consultation receipt.")
    sol_calls = route_result.get("sol_calls")
    if not isinstance(sol_calls, int) or isinstance(sol_calls, bool) or sol_calls != 0:
        _fail("No-consultation requires zero Sol calls.")
    terminal = route_result.get("terminal")
    if isinstance(terminal, str) and (
        terminal.startswith("advisor-")
        or terminal in {
            "setup-required-before-gpc",
            "setup-status-unavailable",
            "fresh-task-required",
            "preferences-unavailable",
        }
    ):
        _fail("Dependency failure cannot be normalized as no consultation.")
    receipt = {
        **_identity(scenario, route_result),
        "reason_code": _no_consultation_reason(scenario, route_result),
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
    if route_result.get("advice_admitted") == 1:
        return _consultation_receipt(scenario, route_result, disposition)
    if disposition is not None:
        _fail("No-consultation cannot carry a disposition.")
    return _no_consultation_receipt(scenario, route_result)
