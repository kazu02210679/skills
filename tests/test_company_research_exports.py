from __future__ import annotations

import csv
import importlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "company-research" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

VALID_COMPANY_ID = "cmp_" + "a" * 32
SNAPSHOT_DIGEST = "sha256:" + "1" * 64


def require_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        raise AssertionError(f"production module missing: {name}") from exc


def state_with_unknown() -> dict:
    return {
        "schema_version": 2,
        "company_identity": {
            "company_id": VALID_COMPANY_ID,
            "legal_name": "Example Corp",
            "reporting_currency": "JPY",
        },
        "segments": [],
        "sources": [],
        "claims": [],
        "observations": [
            {
                "observation_id": "obs-revenue-unknown",
                "subject_id": VALID_COMPANY_ID,
                "metric_id": "revenue",
                "value": None,
                "unit": "currency",
                "currency": "JPY",
                "unit_scale": 1,
                "period_kind": "FY",
                "period_start": "2025-04-01",
                "period_end": "2026-03-31",
                "reported_at": None,
                "accounting_standard": "IFRS",
                "consolidation_scope": "consolidated",
                "restatement_status": "ORIGINAL",
                "plane": "company",
                "epistemic_status": "UNKNOWN",
                "source_refs": [],
            }
        ],
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
            "snapshot_digest": SNAPSHOT_DIGEST,
            "created_at": "2026-08-16T00:00:00Z",
            "base_version": None,
            "research_run_id": "20260816T000000000000Z-test01",
        },
    }


class CompanyResearchExportTests(unittest.TestCase):
    def test_all_exports_share_snapshot_digest(self) -> None:
        exporters = require_module("exporters")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = exporters.write_exports(
                state_with_unknown(),
                Path(tmp),
                generated_at="2026-08-16T00:00:00Z",
            )
        self.assertEqual(SNAPSHOT_DIGEST, manifest["snapshot_digest"])
        self.assertTrue(manifest["artifacts"])
        for artifact in manifest["artifacts"]:
            with self.subTest(path=artifact["path"]):
                self.assertEqual(SNAPSHOT_DIGEST, artifact["snapshot_digest"])
                self.assertRegex(artifact["sha256"], r"^sha256:[0-9a-f]{64}$")

    def test_unknown_csv_value_is_empty_not_zero(self) -> None:
        exporters = require_module("exporters")
        rendered = exporters.render_financial_csv(state_with_unknown())
        rows = list(csv.DictReader(io.StringIO(rendered)))
        self.assertEqual(1, len(rows))
        self.assertEqual("", rows[0]["value"])
        self.assertEqual("UNKNOWN", rows[0]["status"])

    def test_evidence_export_does_not_include_raw_source_body(self) -> None:
        exporters = require_module("exporters")
        state = state_with_unknown()
        state["sources"] = [
            {
                "source_id": "src-1",
                "title": "Source",
                "url": "https://example.com",
                "raw_body": "copyrighted full text must not be exported",
            }
        ]
        rendered = exporters.render_evidence_json(state).decode("utf-8")
        self.assertNotIn("copyrighted full text", rendered)
        self.assertIn("https://example.com", rendered)


if __name__ == "__main__":
    unittest.main()
