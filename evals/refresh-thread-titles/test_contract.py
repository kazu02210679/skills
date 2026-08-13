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

    def test_skill_uses_whole_thread_and_protects_version_suffixes(self) -> None:
        for phrase in (
            "whole available thread",
            "initial request",
            "major pivots",
            "durable objective",
            "_v[0-9０-９]+$",
            "Do not rename it",
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

    def test_skill_requires_state_prefix_for_every_unprotected_title(self) -> None:
        for phrase in (
            "Every non-protected title must begin with an evidence-backed state emoji",
            "Update an existing state emoji when the evidence changes",
            "If the task phrase remains accurate, preserve it and change only the state prefix",
            "Do not treat inactivity as completion",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_bounds_title_length_and_protects_safe_content(self) -> None:
        for phrase in (
            "approximately 15 characters",
            "12-18 characters",
            "counting the state emoji and separating space",
            "Prioritize identifiability, meaning, and protected names",
            "exclude personal names, customer names, secrets, credentials, and full URLs",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_uses_bounded_discovery_retry_and_failure_semantics(self) -> None:
        for phrase in (
            "list_threads({limit})",
            "finite response deadline",
            "at most one retry",
            "same or smaller limit",
            "list_threads does not accept a cursor",
            "discovery failure",
            "must not be reported as zero",
            "Do not update from a partial or stale listing",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_matches_host_schema_without_invented_pagination(self) -> None:
        for phrase in (
            "list_threads({limit})",
            "read_thread(cursor...)",
            "set_thread_title",
            "list_threads itself has no cursor",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_reports_each_item_state_and_failure_categories(self) -> None:
        for phrase in (
            "each eligible item",
            "state and title",
            "changed",
            "unchanged",
            "protected",
            "skipped",
            "failed",
            "unknown",
            "lookback",
            "confirmed changes",
            "discovery failure",
            "Do not expose inspected conversation contents",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_reads_protected_threads_for_state_without_mutating_titles(self) -> None:
        for phrase in (
            "Classify protected titles before reading",
            "Read every eligible thread for state evidence",
            "Protected titles are read for state only",
            "Mutate only non-protected titles",
            "state is unknown when the thread cannot be read",
            "Confirmed unresolved work maps to 🔄",
            "Without complete history or explicit state evidence, report skipped with state unknown",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_expands_short_titles_from_durable_context_without_guessing(self) -> None:
        for phrase in (
            "Aim for 12-18 characters for every non-protected title",
            "When a non-protected title is shorter than that range, expand it from the durable objective",
            "Preserve the task phrase's meaning while adding only context established by the whole thread",
            "Do not pad a title with guessed or generic words",
            "If the objective is ambiguous or evidence is absent, report skipped with state unknown",
            "Protected titles are exempt from the length target",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill)

    def test_skill_keeps_all_discovery_failure_counts_unknown(self) -> None:
        for phrase in (
            "On discovery failure, target, unchanged, protected, skipped, and failed counts are unknown",
            "Only the confirmed-changes count is zero on discovery failure",
            "Do not evaluate items after discovery failure",
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
                "whole-thread-over-latest-subtask",
                "version-suffix-is-protected",
                "state-prefix-required-for-unprotected-titles",
                "title-length-is-bounded",
                "bounded-discovery-retry-and-failure",
                "host-schema-and-no-invented-pagination",
                "per-item-state-reporting",
                "protected-title-state-is-read-only",
                "short-title-expands-from-durable-objective",
                "discovery-failure-counts-are-unknown",
            },
            ids,
        )
        self.assertTrue(all(case["expect"] for case in self.cases))


if __name__ == "__main__":
    unittest.main()
