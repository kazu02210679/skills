from __future__ import annotations

import copy
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


def private_company_state() -> dict:
    return {
        "schema_version": 2,
        "company_identity": {
            "company_id": VALID_COMPANY_ID,
            "slug": "private-example",
            "legal_name": "Private Example Co.",
            "jurisdiction": "JP",
            "listed_status": "PRIVATE",
            "primary_identifier": {"kind": "user_namespace", "value": "private-example"},
            "identifiers": [],
            "aliases": [],
            "fiscal_year_end": "03-31",
            "reporting_currency": "JPY",
        },
        "segments": [],
        "sources": [],
        "claims": [],
        "observations": [],
        "derivations": [],
        "business": {},
        "technology": {},
        "competitors": {},
        "coverage": {},
        "evidence_quality": {},
        "external_drivers": [],
        "events": [],
        "watchpoint_index": [],
        "investment_ref": None,
        "meta": {
            "snapshot_version": 1,
            "snapshot_digest": "sha256:" + "1" * 64,
            "created_at": "2026-08-16T00:00:00Z",
            "base_version": None,
            "research_run_id": "20260816T000000000000Z-test01",
        },
    }


class CompanyResearchInvestmentTests(unittest.TestCase):
    def test_private_company_has_no_market_cap_placeholder(self) -> None:
        investment = require_module("investment")
        result = investment.build_investment_candidate(
            private_company_state(),
            market_records=[],
            as_of="2026-08-16T00:00:00Z",
        )
        self.assertEqual("LIMITED", result["status"])
        self.assertNotIn("market_cap", result.get("valuation", {}))
        self.assertNotIn("stock_price", result.get("valuation", {}))

    def test_building_investment_state_does_not_mutate_company_understanding(self) -> None:
        investment = require_module("investment")
        state = private_company_state()
        before = copy.deepcopy(state)
        investment.build_investment_candidate(
            state,
            market_records=[],
            as_of="2026-08-16T00:00:00Z",
        )
        self.assertEqual(before, state)

    def test_bull_base_bear_entries_are_scenarios_not_facts(self) -> None:
        investment = require_module("investment")
        state = private_company_state()
        candidate = {
            "schema_version": 1,
            "status": "LIMITED",
            "source_snapshot_digest": state["meta"]["snapshot_digest"],
            "earnings_drivers": [],
            "catalysts": [],
            "risks": [],
            "scenarios": {
                "bull": {"epistemic_status": "FACT"},
                "base": {"epistemic_status": "SCENARIO"},
                "bear": {"epistemic_status": "SCENARIO"},
            },
            "valuation": {},
            "expectation_gaps": [],
            "watchpoint_links": [],
            "updated_at": "2026-08-16T00:00:00Z",
        }
        with self.assertRaisesRegex(ValueError, "SCENARIO"):
            investment.validate_investment_state(candidate, state)


if __name__ == "__main__":
    unittest.main()
