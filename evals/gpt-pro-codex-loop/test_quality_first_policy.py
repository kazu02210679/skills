from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "gpt-pro-codex-loop" / "SKILL.md"
README = ROOT / "skills" / "gpt-pro-codex-loop" / "README.md"
PACKET_CONTRACT = (
    ROOT / "skills" / "gpt-pro-codex-loop" / "references" / "packet-contract.md"
)


class QualityFirstBrowserPolicyTests(unittest.TestCase):
    def test_skill_forbids_time_based_answer_now(self) -> None:
        text = SKILL.read_text(encoding="utf-8")

        self.assertIn("Answer now", text)
        self.assertIn("elapsed time alone is not failure evidence", text)
        self.assertIn("explicitly prioritizes speed", text)

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


if __name__ == "__main__":
    unittest.main()
