import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "gpt-pro-codex-loop" / "SKILL.md"
README = ROOT / "skills" / "gpt-pro-codex-loop" / "README.md"
PACKET_CONTRACT = (
    ROOT / "skills" / "gpt-pro-codex-loop" / "references" / "packet-contract.md"
)
CASES = ROOT / "evals" / "gpt-pro-codex-loop" / "cases.json"


class QualityFirstBrowserPolicyTests(unittest.TestCase):
    def test_behavior_cases_cover_quality_first_decision_boundaries(self) -> None:
        cases = {
            case["id"]: case
            for case in json.loads(CASES.read_text(encoding="utf-8"))
        }

        expected = {
            "quality-first-active-turn": {
                "action": "WAIT",
                "answer_now": False,
            },
            "quality-first-browser-timeout": {
                "action": "REACQUIRE_AND_REOBSERVE",
                "resend": False,
            },
            "quality-first-explicit-error": {
                "action": "BOUNDED_RECOVERY",
                "guessed_resend": False,
            },
            "quality-first-user-speed-priority": {
                "action": "ANSWER_NOW_PERMITTED",
                "answer_now_required": False,
            },
        }

        for case_id, expected_subset in expected.items():
            with self.subTest(case_id=case_id):
                self.assertIn(case_id, cases)
                self.assertEqual(expected_subset, cases[case_id]["expect"])

    def test_skill_forbids_time_based_answer_now(self) -> None:
        text = SKILL.read_text(encoding="utf-8")

        self.assertIn("Answer now", text)
        self.assertIn("elapsed time alone is not failure evidence", text)
        self.assertIn("explicitly prioritizes speed", text)
        self.assertIn(
            "Deadlines, elapsed time, stakeholder requests, and agent judgment are not permission",
            text,
        )

    def test_skill_defaults_to_two_pro_turns_and_routes_routine_review_to_luna(self) -> None:
        text = " ".join(SKILL.read_text(encoding="utf-8").lower().split())
        self.assertIn("--review-policy final_only", text)
        self.assertIn("does not automatically send another pro review", text)
        self.assertIn("luna-max sub-agent may provide one bounded read-only routine review", text)
        self.assertIn("sol may provide one bounded read-only high-impact consultation", text)
        self.assertIn("sol cannot replace the final pro gate", text)

    def test_timeout_contract_reobserves_active_turn_without_interrupting_it(self) -> None:
        text = PACKET_CONTRACT.read_text(encoding="utf-8")

        self.assertIn("Do not interrupt a visibly active Pro turn", text)
        self.assertIn("re-observe the same turn", text)
        self.assertIn("explicit generation failure", text)

    def test_readme_documents_quality_first_default(self) -> None:
        text = README.read_text(encoding="utf-8")

        self.assertIn("品質優先", text)
        self.assertIn("今すぐ回答", text)
        self.assertIn("経過時間だけ", text)

    def test_standalone_skill_keeps_routing_in_composition_and_documents_test_economy(self) -> None:
        skill = " ".join(SKILL.read_text(encoding="utf-8").lower().split())
        readme = README.read_text(encoding="utf-8")

        for phrase in (
            "standalone use owns only the outer gpt pro protocol",
            "does not select or invoke luna, terra, sol",
            "orchestrate-gpt-pro-sol-advisor",
            "one regression witness per root cause",
            "new_test_files = 0",
            "l1 affected focused tests",
            "closed schema",
            "verification-input",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

        for phrase in ("standalone", "Test Economy", "closed schema"):
            with self.subTest(readme_phrase=phrase):
                self.assertIn(phrase, readme)


if __name__ == "__main__":
    unittest.main()
