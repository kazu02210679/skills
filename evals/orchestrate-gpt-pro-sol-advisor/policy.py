"""Deterministic behavioral harness delegated to the production policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path


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
SETUP_FAILURES = RECEIPT_ISSUER.SETUP_FAILURES
CODEX_ADVISOR_ROLE = RECEIPT_ISSUER.CODEX_ADVISOR_ROLE
RUNTIME_FIELDS = RECEIPT_ISSUER.RUNTIME_FIELDS
PROFILE_SCOPES = RECEIPT_ISSUER.PROFILE_SCOPES
canonical_workspace = RECEIPT_ISSUER.canonical_workspace
route = RECEIPT_ISSUER.route
bounded_packet = RECEIPT_ISSUER.bounded_packet
evaluate_advice = RECEIPT_ISSUER.evaluate_advice
scenario_digest = RECEIPT_ISSUER.scenario_digest
governance_receipt = RECEIPT_ISSUER.governance_receipt
