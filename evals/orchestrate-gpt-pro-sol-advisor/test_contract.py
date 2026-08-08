from __future__ import annotations

import json
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "orchestrate-gpt-pro-sol-advisor"
CASES = Path(__file__).with_name("cases.json")
PRESSURE_RESULTS = Path(__file__).with_name("pressure-results.json")
POLICY_PATH = Path(__file__).with_name("policy.py")

SPEC = importlib.util.spec_from_file_location("composition_policy", POLICY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {POLICY_PATH}")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class CompositionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.readme = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
        cls.cases = json.loads(CASES.read_text(encoding="utf-8"))

    def test_routes_only_explicit_combined_mode(self) -> None:
        for phrase in (
            "combined mode",
            "standalone",
            "gpt-pro-codex-loop",
            "sol-advisor:orchestration",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

    def test_preserves_authority_and_bounded_advice(self) -> None:
        for phrase in (
            "requirements and semantic review",
            "advisory only",
            "materially new evidence",
            "sol_advisor_terra_implementer",
            "sol_advisor_sol_reviewer",
            "accept, reject, or partially accept",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

    def test_forbids_duplicate_review_recursion_and_silent_downgrade(self) -> None:
        for phrase in (
            "do not make sol a mandatory pre-pro gate",
            "do not invoke both lanes by default",
            "do not recurse",
            "no fabricated consultation",
            "no silent downgrade",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

    def test_cases_cover_routing_and_failure_boundaries(self) -> None:
        cases = {case["id"]: case for case in self.cases}
        self.assertEqual(
            {
                "standalone-gpt-pro-remains-standalone",
                "standalone-sol-remains-standalone",
                "ambiguous-installation-does-not-compose",
                "explicit-combined-low-risk-skips-sol",
                "implementation-question-selects-terra",
                "risk-review-selects-sol-reviewer",
                "authority-escalation-is-rejected",
                "conflicting-advice-is-rejected",
                "advisor-requested-reentry-is-suppressed",
                "unchanged-follow-up-is-suppressed",
                "material-follow-up-is-bounded",
                "pro-correction-does-not-force-sol-loop",
                "missing-sol-plugin-is-explicit",
                "missing-sol-lane-is-explicit",
            },
            set(cases),
        )

        for case_id, case in cases.items():
            with self.subTest(case_id=case_id):
                self.assertEqual(case["expect"], POLICY.route(case["scenario"]))

    def test_consultation_packet_is_bounded_and_dispositioned(self) -> None:
        source = {
            "frozen_constraints": ["REQ-009"],
            "verified_local_evidence": ["focused tests pass"],
            "alternatives": ["skip consultation"],
            "risks": ["authority drift"],
            "precise_question": "Does this boundary justify one lane?",
            "complete_conversation_history": "excluded",
            "unrelated_repository_content": "excluded",
            "secrets": "excluded",
            "credentials": "excluded",
        }
        packet = POLICY.bounded_packet(source)
        disposition = POLICY.evaluate_advice(
            {"text": "Use the safe subset only", "useful_subset": True}
        )
        self.assertEqual(
            {
                "frozen_constraints",
                "verified_local_evidence",
                "alternatives",
                "risks",
                "precise_question",
            },
            set(packet),
        )
        self.assertTrue(set(source) - set(packet))
        self.assertEqual(
            {
                "disposition": "partially accept",
                "rationale": "Use only the compatible, evidence-supported subset.",
            },
            disposition,
        )

    def test_pressure_results_retain_five_red_and_five_green_traces(self) -> None:
        results = json.loads(PRESSURE_RESULTS.read_text(encoding="utf-8"))
        self.assertEqual(5, len(results["baseline"]))
        self.assertEqual(5, len(results["with_skill"]))
        self.assertEqual(
            4,
            sum(item["automatic_sol_recurrence"] for item in results["baseline"]),
        )
        self.assertTrue(
            all(not item["automatic_sol_recurrence"] for item in results["with_skill"])
        )
        for trace in results["with_skill"]:
            with self.subTest(sample=trace["sample"]):
                self.assertEqual("combined", trace["selected_mode"])
                self.assertEqual("sol_advisor_sol_reviewer", trace["selected_lane"])
                self.assertEqual(1, trace["initial_sol_calls"])
                self.assertEqual("codex", trace["disposition_owner"])
                self.assertEqual("not-applicable", trace["disposition"])
                self.assertTrue(trace["rationale"])
                self.assertEqual("gpt-pro-codex-loop", trace["requirements_owner"])
                self.assertEqual("controller-final-verify", trace["terminal"])
                self.assertTrue(trace["response_excerpt"])

    def test_has_human_and_codex_metadata(self) -> None:
        self.assertTrue((SKILL_ROOT / "README.md").is_file())
        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("$orchestrate-gpt-pro-sol-advisor", metadata)
        self.assertIn("単独", self.readme)
        self.assertIn("併用", self.readme)


if __name__ == "__main__":
    unittest.main()
