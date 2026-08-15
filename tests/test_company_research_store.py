from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


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


def candidate_state(version: int) -> dict:
    return {
        "schema_version": 2,
        "company_identity": {
            "company_id": VALID_COMPANY_ID,
            "slug": "example-corp",
            "legal_name": "Example Corp",
            "jurisdiction": "JP",
            "listed_status": "LISTED",
            "primary_identifier": {"kind": "exchange_security_id", "value": "TSE-0000"},
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
            "snapshot_version": version,
            "snapshot_digest": "sha256:" + str(version) * 64,
            "created_at": "2026-08-16T00:00:00Z",
            "base_version": version - 1 if version else None,
            "research_run_id": f"20260816T000000000000Z-run{version:02d}",
        },
    }


def prepared(base_version: int, next_version: int) -> dict:
    state = candidate_state(next_version)
    return {
        "schema_version": 1,
        "run_id": state["meta"]["research_run_id"],
        "base_version": base_version,
        "candidate_state": state,
        "changes": [],
        "warnings": [],
        "candidate_digest": "sha256:" + "b" * 64,
    }


class CompanyStoreTests(unittest.TestCase):
    def test_windows_safe_run_id_contains_no_colon(self) -> None:
        store = require_module("company_store")
        run_id = store.make_run_id(
            datetime(2026, 8, 16, 12, 34, 56, 123456, tzinfo=timezone.utc),
            "a1b2c3",
        )
        self.assertNotIn(":", run_id)
        self.assertRegex(run_id, r"^[0-9]{8}T[0-9]{12}Z-[a-z0-9]{6,16}$")

    def test_base_version_conflict_rejects_second_writer(self) -> None:
        store = require_module("company_store")
        errors = require_module("errors")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"COMPANY_RESEARCH_HOME": tmp}, clear=False):
                store.apply_prepared(
                    prepared(0, 1),
                    expected_base_version=0,
                    update_kind="FULL",
                )
                with self.assertRaisesRegex(errors.ConflictError, "expected base version 0, found 1"):
                    store.apply_prepared(
                        prepared(0, 2),
                        expected_base_version=0,
                        update_kind="INCREMENTAL",
                    )

    def test_interrupted_staging_does_not_move_latest(self) -> None:
        store = require_module("company_store")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"COMPANY_RESEARCH_HOME": tmp}, clear=False):
                store.apply_prepared(
                    prepared(0, 1),
                    expected_base_version=0,
                    update_kind="FULL",
                )
                before = store.load_latest(VALID_COMPANY_ID)
                with mock.patch.object(
                    store,
                    "_after_snapshot_publish",
                    side_effect=RuntimeError("injected crash"),
                    create=True,
                ):
                    with self.assertRaisesRegex(RuntimeError, "injected crash"):
                        store.apply_prepared(
                            prepared(1, 2),
                            expected_base_version=1,
                            update_kind="INCREMENTAL",
                        )
                after = store.load_latest(VALID_COMPANY_ID)
                self.assertEqual(before, after)
                self.assertEqual(1, after["version"])

    def test_corrupt_snapshot_requires_recovery(self) -> None:
        store = require_module("company_store")
        errors = require_module("errors")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"COMPANY_RESEARCH_HOME": tmp}, clear=False):
                result = store.apply_prepared(
                    prepared(0, 1),
                    expected_base_version=0,
                    update_kind="FULL",
                )
                state_path = Path(result["snapshot_path"]) / "state.json"
                state_path.write_text(json.dumps({"corrupt": True}), encoding="utf-8")
                with self.assertRaises(errors.IntegrityError):
                    store.verify_company(VALID_COMPANY_ID)
                diagnosis = store.diagnose_recovery(VALID_COMPANY_ID)
                self.assertEqual("RECOVERY_REQUIRED", diagnosis["status"])


if __name__ == "__main__":
    unittest.main()
