from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "company-research" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def require_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        raise AssertionError(f"production module missing: {name}") from exc


class CompanyResearchIndustryTests(unittest.TestCase):
    def test_coverage_capability_is_separate_from_completeness(self) -> None:
        coverage = require_module("coverage")
        industry = require_module("industry")
        capability = coverage.resolve_capability("semiconductor.memory.nand")
        contract = industry.load_industry_contract("semiconductor.memory.nand")
        state = {
            "segments": [
                {
                    "segment_id": "seg-nand",
                    "name": "NAND",
                    "materiality": {
                        "basis": "revenue_share",
                        "value": "1.0",
                        "confidence": "high",
                    },
                    "modules": ["manufacturing-common", "semiconductor.memory.nand"],
                }
            ],
            "claims": [],
            "observations": [],
        }
        completeness = industry.calculate_evidence_completeness(
            contract,
            state,
            "seg-nand",
        )
        self.assertIn(
            capability["capability_status"],
            {"FULL", "PARTIAL_PENDING_ACCEPTANCE"},
        )
        self.assertIn("evidence_completeness", completeness)
        self.assertNotEqual(
            capability["capability_status"],
            completeness["evidence_completeness"],
        )
        self.assertIn("missing_required_dimensions", completeness)

    def test_multi_segment_company_routes_modules_per_segment(self) -> None:
        industry = require_module("industry")
        hints = [
            {"segment_id": "seg-logistics", "module_id": "industrial-machinery.logistics-equipment"},
            {"segment_id": "seg-mobility", "module_id": "mobility"},
        ]
        logistics = {
            "segment_id": "seg-logistics",
            "name": "Logistics Equipment",
            "materiality": {"basis": "revenue_share", "value": "0.62", "confidence": "high"},
        }
        mobility = {
            "segment_id": "seg-mobility",
            "name": "Automotive",
            "materiality": {"basis": "revenue_share", "value": "0.28", "confidence": "high"},
        }
        logistics_modules = industry.resolve_segment_modules(logistics, hints)
        mobility_modules = industry.resolve_segment_modules(mobility, hints)
        self.assertIn("industrial-machinery.logistics-equipment", [row["module_id"] for row in logistics_modules])
        self.assertNotIn("mobility", [row["module_id"] for row in logistics_modules])
        self.assertIn("mobility", [row["module_id"] for row in mobility_modules])

    def test_projected_model_change_is_not_recorded_as_launch_date(self) -> None:
        industry = require_module("industry")
        projected = {
            "product_family": "forklift",
            "generation": "next generation",
            "launch_date": "2029-01-01",
            "replacement_of": "current generation",
            "epistemic_status": "INFERENCE",
            "evidence_ids": ["clm-cycle-estimate"],
        }
        with self.assertRaisesRegex(ValueError, "launch_date|INFERENCE"):
            industry.normalize_product_generation(projected)


if __name__ == "__main__":
    unittest.main()
