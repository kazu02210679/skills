from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "review-implementation-html" / "scripts" / "validate_review_report.py"
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SPEC = importlib.util.spec_from_file_location("validate_review_report", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ReviewValidationTests(unittest.TestCase):
    @staticmethod
    def load(name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_valid_review_has_no_errors(self):
        self.assertEqual(MODULE.validate_document(self.load("valid-review.json")), [])

    def test_high_finding_requires_action(self):
        errors = MODULE.validate_document(self.load("invalid-review.json"))
        self.assertTrue(any("recommended_action" in error for error in errors))

    def test_each_hunk_has_exactly_one_group(self):
        errors = MODULE.validate_document(self.load("invalid-review.json"))
        self.assertTrue(any("exactly one intent group" in error for error in errors))

    def test_finding_group_reference_matches_group_ownership(self):
        document = self.load("valid-review.json")
        document["intentGroups"].append(
            {
                "id": "other",
                "title": "Other",
                "summary": "Another intent.",
                "risk": "low",
                "hunkIds": [],
                "findingIds": [],
            }
        )
        document["findings"][0]["intentGroupId"] = "other"

        errors = MODULE.validate_document(document)

        self.assertTrue(any("does not match intent group ownership" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
