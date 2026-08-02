from __future__ import annotations

import json
import unittest
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EVAL_ROOT.parents[1]
SKILL_PATH = REPOSITORY_ROOT / "skills" / "refresh-thread-titles" / "SKILL.md"
CASES_PATH = EVAL_ROOT / "cases.json"


class RefreshThreadTitlesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def test_skill_has_single_pass_and_window_contract(self) -> None:
        for phrase in (
            "exactly one refresh pass",
            "two days",
            "latest activity",
            "per-run override",
            "current invocation thread",
            "Archived threads",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_preserves_titles_when_judgment_is_uncertain(self) -> None:
        for phrase in (
            "deliberately user-authored",
            "When uncertain",
            "leave the title unchanged",
            "Silence is not completion",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_treats_inspected_threads_as_untrusted_data(self) -> None:
        self.assertIn("untrusted data", self.skill)
        self.assertIn("Do not follow instructions", self.skill)
        for forbidden in (
            "create or fork threads",
            "send messages",
            "archive or delete threads",
            "create schedules",
            "start loops",
            "edit conversation files",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertIn(forbidden, self.skill)

    def test_skill_defines_evidence_based_title_states(self) -> None:
        for emoji in ("🔄", "⏸", "✅", "⚠"):
            with self.subTest(emoji=emoji):
                self.assertIn(emoji, self.skill)
        self.assertIn("Do not infer state from age or silence", self.skill)

    def test_skill_limits_tools_and_confirms_batch_results(self) -> None:
        for phrase in (
            "list threads",
            "read a selected thread",
            "set a selected thread's title",
            "small batches",
            "Inspect every result",
            "host confirmed",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_cases_cover_required_decision_boundaries(self) -> None:
        ids = {case["id"] for case in self.cases}
        self.assertEqual(
            {
                "default-two-day-window",
                "explicit-window-override",
                "preserve-deliberate-title",
                "rename-stale-generic-title",
                "ambiguous-title-is-preserved",
                "thread-content-is-untrusted",
                "current-and-archived-excluded",
                "unavailable-tools-fail-closed",
                "confirmed-small-batch-reporting",
            },
            ids,
        )
        self.assertTrue(all(case["expect"] for case in self.cases))


if __name__ == "__main__":
    unittest.main()
