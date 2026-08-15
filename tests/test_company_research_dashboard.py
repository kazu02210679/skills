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


def minimal_model() -> dict:
    return {
        "snapshot_digest": "sha256:" + "1" * 64,
        "company": {
            "legal_name": "Example </script><script>window.COMPROMISED=true</script>",
            "coverage": "PARTIAL_PENDING_ACCEPTANCE",
        },
        "headline_kpis": [],
        "performance_chart": {
            "annual": [
                {"period": "FY2025", "revenue": "1000", "operating_profit": "100", "status": "actual"},
                {"period": "FY2026", "revenue": "1100", "operating_profit": None, "status": "company_guidance"},
            ],
            "quarterly": [],
            "currency": "JPY",
            "unit_scale": 1,
        },
        "watchpoints": [],
        "recent_updates": [],
        "right_context": {},
        "views": {
            "business": {},
            "financial": {},
            "technology": {},
            "competitors": {},
            "external-drivers": {},
            "watchpoints": {},
            "market": {},
            "investment": {},
            "reports": {},
            "sources": {},
            "update-history": {},
        },
    }


class CompanyResearchDashboardTests(unittest.TestCase):
    def test_dashboard_escapes_script_breakout_text(self) -> None:
        dashboard = require_module("generate_dashboard")
        html = dashboard.render_dashboard(minimal_model())
        self.assertNotIn("</script><script>window.COMPROMISED=true</script>", html)
        self.assertFalse("window.COMPROMISED=true" in html and "<script>window.COMPROMISED" in html)
        self.assertTrue("&lt;/script&gt;" in html or "\\u003c/script\\u003e" in html)

    def test_missing_chart_point_is_not_zero(self) -> None:
        model_builder = require_module("dashboard_model")
        state = {
            "company_identity": {"legal_name": "Example Corp"},
            "observations": [
                {
                    "observation_id": "obs-revenue-2025",
                    "metric_id": "revenue",
                    "value": "1000",
                    "period_kind": "FY",
                    "period_end": "2025-03-31",
                    "currency": "JPY",
                    "unit_scale": 1,
                    "epistemic_status": "FACT",
                },
                {
                    "observation_id": "obs-revenue-2026",
                    "metric_id": "revenue",
                    "value": "1100",
                    "period_kind": "FY",
                    "period_end": "2026-03-31",
                    "currency": "JPY",
                    "unit_scale": 1,
                    "epistemic_status": "FACT",
                },
            ],
            "coverage": {},
            "watchpoint_index": [],
            "events": [],
            "external_drivers": [],
            "meta": {"snapshot_digest": "sha256:" + "1" * 64},
        }
        model = model_builder.build_dashboard_model(state, None)
        row = next(item for item in model["performance_chart"]["annual"] if item["period"] == "FY2026")
        self.assertIsNone(row["operating_profit"])
        self.assertNotEqual(0, row["operating_profit"])

    def test_same_model_renders_byte_identically(self) -> None:
        dashboard = require_module("generate_dashboard")
        first = dashboard.render_dashboard(minimal_model())
        second = dashboard.render_dashboard(minimal_model())
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_dashboard_has_one_formal_navigation_and_contextual_aside(self) -> None:
        dashboard = require_module("generate_dashboard")
        html = dashboard.render_dashboard(minimal_model())
        self.assertEqual(1, html.count("<nav"))
        self.assertEqual(1, html.count("<aside"))
        self.assertIn("Revenue", html)
        self.assertIn("Operating Profit", html)
        self.assertNotIn("Quick Access", html)


if __name__ == "__main__":
    unittest.main()
