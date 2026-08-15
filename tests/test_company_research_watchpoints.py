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


class CompanyResearchWatchpointTests(unittest.TestCase):
    def test_watchpoint_transition_requires_receipt(self) -> None:
        watchpoints = require_module("watchpoints")
        incomplete = {
            "watchpoint_id": "wp-tech-001",
            "previous_version": 1,
            "proposed_assessment": "CONFIRMING",
            "new_evidence_ids": ["clm-tech-002"],
            "rationale": "A new source supports the milestone.",
        }
        with self.assertRaisesRegex(ValueError, "receipt|previous_digest|rule_id"):
            watchpoints.apply_transition(VALID_COMPANY_ID, incomplete)

    def test_confidence_cannot_increase_without_new_evidence(self) -> None:
        watchpoints = require_module("watchpoints")
        current = {
            "watchpoint_id": "wp-tech-001",
            "version": 1,
            "digest": "sha256:" + "1" * 64,
            "lifecycle": "ACTIVE",
            "assessment": "UNRESOLVED",
            "confidence": "medium",
            "evidence_ids": ["clm-tech-001"],
        }
        with self.assertRaisesRegex(ValueError, "new evidence|confidence"):
            watchpoints.propose_transition(
                current,
                evidence_delta=[],
                proposed_assessment="CONFIRMING",
                rationale="No new evidence was supplied.",
            )

    def test_external_observation_cannot_be_company_fact(self) -> None:
        external_drivers = require_module("external_drivers")
        state = {
            "observations": [
                {
                    "observation_id": "obs-usdjpy",
                    "subject_id": "market-usdjpy",
                    "metric_id": "usd_jpy",
                    "value": "150.00",
                    "unit": "ratio",
                    "currency": None,
                    "unit_scale": 1,
                    "period_kind": "INSTANT",
                    "period_start": "2026-08-16",
                    "period_end": "2026-08-16",
                    "reported_at": "2026-08-16T00:00:00Z",
                    "accounting_standard": None,
                    "consolidation_scope": None,
                    "restatement_status": "ORIGINAL",
                    "plane": "company",
                    "epistemic_status": "FACT",
                    "source_refs": [{"source_id": "src-market", "locator": {}}],
                }
            ]
        }
        driver = {
            "driver_id": "fx-usdjpy",
            "name": "USD/JPY",
            "category": "FX",
            "relevance": "high",
            "sensitivity": "high",
            "direction": "POSITIVE_WHEN_RISING",
            "mechanism": "Export translation exposure",
            "evidence_ids": ["obs-usdjpy"],
            "linked_watchpoints": [],
            "last_checked": "2026-08-16",
        }
        with self.assertRaisesRegex(ValueError, "external|plane"):
            external_drivers.validate_external_driver(driver, state)


if __name__ == "__main__":
    unittest.main()
