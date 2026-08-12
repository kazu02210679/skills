from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "hotl-governance"
SKILL = SKILL_DIR / "SKILL.md"
README = SKILL_DIR / "README.md"
OPENAI_YAML = SKILL_DIR / "agents" / "openai.yaml"
REFERENCE = SKILL_DIR / "references" / "controller-contract.md"
CASES = Path(__file__).with_name("cases.json")

EXPECTED_CASES = {
    "explicit-hotl": {"invoke_hotl": True},
    "valid-context": {"invoke_hotl": True},
    "ordinary-fix": {"invoke_hotl": False},
    "standalone-pro": {"invoke_hotl": False},
    "invalid-context": {"invoke_hotl": False, "fail_closed": True},
}


class HotlSkillContractTests(unittest.TestCase):
    def test_skill_package_has_stable_activation_metadata(self) -> None:
        """A missing or renamed package can no longer advertise the HOTL trigger."""
        text = SKILL.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---\n", 2)[1]
        self.assertIn("name: hotl-governance", frontmatter)
        self.assertIn("description: Use when", frontmatter)
        self.assertTrue(OPENAI_YAML.is_file())

    def test_activation_cases_are_complete_and_machine_readable(self) -> None:
        """A missing positive, negative, or fail-closed case weakens activation coverage."""
        cases = json.loads(CASES.read_text(encoding="utf-8"))
        self.assertIsInstance(cases, list)
        by_id = {case["id"]: case for case in cases}
        self.assertEqual(set(EXPECTED_CASES), set(by_id))
        for case_id, expected in EXPECTED_CASES.items():
            case = by_id[case_id]
            self.assertIsInstance(case["prompt"], str)
            self.assertTrue(case["prompt"])
            self.assertEqual(expected, case["expect"])

    def test_human_and_controller_contract_artifacts_are_reachable(self) -> None:
        """Readers need the human boundary and the detailed controller contract."""
        text = SKILL.read_text(encoding="utf-8")
        self.assertTrue(README.is_file())
        self.assertTrue(REFERENCE.is_file())
        self.assertIn("references/controller-contract.md", text)

    def test_controller_reference_has_required_sections_and_gate_table(self) -> None:
        """The reference must retain the controller's executable-model structure."""
        text = REFERENCE.read_text(encoding="utf-8")
        for heading in (
            "# Controller Contract",
            "## State machine",
            "## Gate table",
            "## Receipt contract",
            "## Typed provenance triples",
            "## Completion predicate",
            "## Evidence lifecycle",
            "## Path rules",
            "## Threat model",
            "## Recovery",
        ):
            self.assertIn(heading, text)
        for gate in ("G1", "G2", "G3", "G4"):
            self.assertIn(f"| {gate} |", text)


if __name__ == "__main__":
    unittest.main()
