from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "company-research" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

VALID_COMPANY_ID = "cmp_" + "a" * 32


def require_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        raise AssertionError(f"production module missing: {name}") from exc


def source_record(*, source_id: str = "src_primary", kind: str = "issuer_filing") -> dict:
    return {
        "source_id": source_id,
        "source_kind": kind,
        "title": "Annual report",
        "publisher": "Example Corp",
        "url": "https://example.com/report.pdf" if kind != "user_supplied" else "",
        "published_at": "2026-05-10T00:00:00Z",
        "retrieved_at": "2026-08-16T00:00:00Z",
        "content_digest": "sha256:" + "1" * 64,
        "locator": {"page": 12},
        "rights": "public_reference_only" if kind != "user_supplied" else "private_user_supplied",
        "local_archive_ref": None,
    }


def observation(
    metric_id: str,
    value: str | None,
    *,
    observation_id: str,
    period_start: str = "2025-04-01",
    period_end: str = "2026-03-31",
    epistemic_status: str = "FACT",
    plane: str = "company",
) -> dict:
    return {
        "observation_id": observation_id,
        "subject_id": VALID_COMPANY_ID,
        "metric_id": metric_id,
        "value": value,
        "unit": "currency",
        "currency": "JPY",
        "unit_scale": 1,
        "period_kind": "FY",
        "period_start": period_start,
        "period_end": period_end,
        "reported_at": "2026-05-10",
        "accounting_standard": "IFRS",
        "consolidation_scope": "consolidated",
        "restatement_status": "ORIGINAL",
        "plane": plane,
        "epistemic_status": epistemic_status,
        "source_refs": [{"source_id": "src_primary", "locator": {"page": 12}}],
    }


class EvidenceContractTests(unittest.TestCase):
    def test_user_source_may_omit_url_but_requires_receipt_digest(self) -> None:
        evidence = require_module("evidence")
        result = evidence.validate_source(source_record(source_id="src_user", kind="user_supplied"))
        self.assertEqual("src_user", result["source_id"])

    def test_unknown_numeric_observation_must_not_have_zero_value(self) -> None:
        evidence = require_module("evidence")
        record = observation(
            "revenue",
            "0",
            observation_id="obs_unknown",
            epistemic_status="UNKNOWN",
        )
        with self.assertRaisesRegex(ValueError, "UNKNOWN observation value must be null"):
            evidence.validate_observation(record)

    def test_derived_fact_uses_registered_method_not_arbitrary_formula(self) -> None:
        derivations = require_module("derivations")
        inputs = [
            observation("revenue", "1000", observation_id="obs_revenue"),
            observation("operating_profit", "100", observation_id="obs_op"),
        ]
        with self.assertRaisesRegex(ValueError, "unknown derivation method"):
            derivations.derive(
                "python_eval",
                1,
                inputs,
                output_id="obs_margin",
                parameters={"formula": "__import__('os').system('echo unsafe')"},
                calculated_at="2026-08-16T00:00:00Z",
            )

    def test_period_mismatch_blocks_derivation(self) -> None:
        derivations = require_module("derivations")
        inputs = [
            observation("revenue", "1000", observation_id="obs_revenue"),
            observation(
                "operating_profit",
                "100",
                observation_id="obs_op",
                period_start="2024-04-01",
                period_end="2025-03-31",
            ),
        ]
        with self.assertRaisesRegex(ValueError, "period"):
            derivations.derive(
                "operating_margin",
                1,
                inputs,
                output_id="obs_margin",
                calculated_at="2026-08-16T00:00:00Z",
            )

    def test_company_id_rejects_identity_collision(self) -> None:
        identity = require_module("identity")
        record = {
            "company_id": VALID_COMPANY_ID,
            "slug": "example-corp",
            "legal_name": "Example Corp",
            "jurisdiction": "JP",
            "listed_status": "LISTED",
            "primary_identifier": {
                "kind": "exchange_security_id",
                "value": "TSE-0000",
            },
            "identifiers": [
                {
                    "kind": "ticker",
                    "value": "0000",
                    "exchange": "TSE",
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                },
                {
                    "kind": "ticker",
                    "value": "0000",
                    "exchange": "TSE",
                    "valid_from": "2024-01-01",
                    "valid_to": None,
                },
            ],
            "aliases": [],
            "fiscal_year_end": "03-31",
            "reporting_currency": "JPY",
        }
        with self.assertRaisesRegex(ValueError, "duplicate|overlap"):
            identity.validate_company_identity(record)


if __name__ == "__main__":
    unittest.main()
