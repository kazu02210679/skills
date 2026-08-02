from __future__ import annotations

import json
import unittest
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EVAL_ROOT.parents[1]
SKILL_PATH = REPOSITORY_ROOT / "skills" / "monitoring-subagents" / "SKILL.md"
CASES_PATH = EVAL_ROOT / "cases.json"


class MonitoringSubagentsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def test_skill_defines_evidence_aware_states(self) -> None:
        for state in (
            "queued",
            "running",
            "waiting",
            "blocked",
            "stale",
            "failed",
            "completed",
            "unavailable",
        ):
            with self.subTest(state=state):
                self.assertIn(f"`{state}`", self.skill)

    def test_skill_has_activation_and_shutdown_boundaries(self) -> None:
        self.assertIn("two or more", self.skill.lower())
        self.assertIn("single short", self.skill.lower())
        self.assertIn("Stop monitoring", self.skill)

    def test_skill_guards_status_integrity(self) -> None:
        for phrase in (
            "Silence is not failure",
            "Do not invent progress",
            "bounded",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)
        self.assertRegex(self.skill, r"raw\s+reasoning")

    def test_cases_cover_activation_staleness_and_visibility(self) -> None:
        ids = {case["id"] for case in self.cases}
        self.assertEqual(
            {
                "parallel-blocker-needs-intervention",
                "single-short-worker-no-dashboard",
                "silent-worker-is-not-failed",
                "cross-session-partial-visibility",
            },
            ids,
        )
        self.assertTrue(all(case["expect"] for case in self.cases))


if __name__ == "__main__":
    unittest.main()
