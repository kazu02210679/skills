from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "context_budget_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("context_budget_report", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load context budget reporter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContextBudgetReportTests(unittest.TestCase):
    def test_report_is_deterministic_normalizes_lf_and_uses_explicit_assets(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_bytes(
                b"---\r\nname: sample\r\ndescription: Demo.\r\n---\r\n\r\n# Body\r\n"
            )
            (skill / "included.md").write_bytes(b"included\r\nasset\r\n")
            (skill / "ignored.md").write_text("ignore me\n", encoding="utf-8")
            manifest = root / "context-budget-manifest.json"
            manifest.write_text(
                json.dumps({"skills": {"sample": ["included.md"]}}),
                encoding="utf-8",
            )

            first = module.build_report(root, manifest)
            second = module.build_report(root, manifest)

            self.assertEqual(first, second)
            sample = first["skills"][0]
            expected_skill = b"---\nname: sample\ndescription: Demo.\n---\n\n# Body\n"
            expected_asset = b"included\nasset\n"
            self.assertEqual(len(expected_skill), sample["skill_md_utf8_bytes"])
            self.assertEqual(
                sample["skill_md_utf8_bytes"],
                sample["metadata_utf8_bytes"] + sample["body_utf8_bytes"],
            )
            self.assertEqual(len(expected_asset), sample["auxiliary_utf8_bytes"])
            self.assertEqual(
                (len(expected_skill) + len(expected_asset) + 3) // 4,
                sample["approx_tokens"],
            )
            self.assertEqual(["included.md"], [item["path"] for item in sample["auxiliary_assets"]])

    def test_regression_check_uses_explicit_tracked_baseline(self) -> None:
        module = load_module()
        current = {
            "skills": [{"name": "hot", "metadata_utf8_bytes": 10, "skill_md_utf8_bytes": 81, "auxiliary_utf8_bytes": 10}],
            "repository_totals": {"metadata_utf8_bytes": 10, "utf8_bytes": 101, "approx_tokens": 26},
        }
        baseline = {
            "skills": [{"name": "hot", "metadata_utf8_bytes": 10, "skill_md_utf8_bytes": 80, "auxiliary_utf8_bytes": 10}],
            "repository_totals": {"metadata_utf8_bytes": 10, "utf8_bytes": 100, "approx_tokens": 25},
        }
        self.assertEqual([], module.check_regression(current, baseline, max_growth_bytes=1))
        self.assertTrue(module.check_regression(current, baseline, max_growth_bytes=0))

    def test_regression_check_catches_per_skill_growth_hidden_by_repository_total(self) -> None:
        module = load_module()
        current = {
            "skills": [
                {"name": "hot", "metadata_utf8_bytes": 10, "skill_md_utf8_bytes": 110, "auxiliary_utf8_bytes": 0},
                {"name": "cold", "metadata_utf8_bytes": 10, "skill_md_utf8_bytes": 70, "auxiliary_utf8_bytes": 0},
            ],
            "repository_totals": {"metadata_utf8_bytes": 20, "utf8_bytes": 180},
        }
        baseline = {
            "skills": [
                {"name": "hot", "metadata_utf8_bytes": 10, "skill_md_utf8_bytes": 100, "auxiliary_utf8_bytes": 0},
                {"name": "cold", "metadata_utf8_bytes": 10, "skill_md_utf8_bytes": 80, "auxiliary_utf8_bytes": 0},
            ],
            "repository_totals": {"metadata_utf8_bytes": 20, "utf8_bytes": 180},
        }
        failures = module.check_regression(current, baseline, max_growth_bytes=0)
        self.assertTrue(any("hot skill_md_utf8_bytes grew by 10" in item for item in failures))


if __name__ == "__main__":
    unittest.main()
