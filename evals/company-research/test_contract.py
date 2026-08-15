from __future__ import annotations

import json
import unittest
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EVAL_ROOT.parents[1]
SKILL_PATH = REPOSITORY_ROOT / "skills" / "company-research" / "SKILL.md"
CASES_PATH = EVAL_ROOT / "cases.json"
AUTHORITATIVE_DESIGN = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-16-company-research-skill-design-v2.md"
)
AUTHORITATIVE_PLAN = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-16-company-research-v1-authoritative.md"
)


class CompanyResearchSkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def read_skill(self) -> str:
        self.assertTrue(
            SKILL_PATH.is_file(),
            f"company-research Skill is not implemented yet: {SKILL_PATH}",
        )
        return SKILL_PATH.read_text(encoding="utf-8")

    def test_authoritative_design_and_plan_are_present(self) -> None:
        self.assertTrue(AUTHORITATIVE_DESIGN.is_file())
        self.assertTrue(AUTHORITATIVE_PLAN.is_file())

    def test_skill_declares_activation_and_non_trigger_boundaries(self) -> None:
        skill = self.read_skill()
        for phrase in (
            "company-research",
            "Full Research",
            "Incremental Update",
            "single stock price",
            "single metric",
            "general news",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_skill_requires_research_packet_and_single_write_boundary(self) -> None:
        skill = self.read_skill()
        for phrase in (
            "ResearchPacket",
            "prepare",
            "expected_base_version",
            "apply",
            "verify",
            "COMPANY_RESEARCH_HOME",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_skill_preserves_epistemic_and_evidence_planes(self) -> None:
        skill = self.read_skill()
        for phrase in (
            "FACT",
            "DERIVED_FACT",
            "INFERENCE",
            "SCENARIO",
            "UNKNOWN",
            "company",
            "external",
            "market",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_skill_reports_capability_and_evidence_quality_separately(self) -> None:
        skill = self.read_skill()
        self.assertIn("capability_status", skill)
        self.assertIn("evidence_completeness", skill)
        self.assertIn("freshness_status", skill)
        self.assertIn("PARTIAL_PENDING_ACCEPTANCE", skill)

    def test_skill_forbids_external_mutations_and_fake_financial_values(self) -> None:
        skill = self.read_skill()
        for phrase in (
            "No trading execution",
            "Missing values remain missing",
            "private company",
            "market cap",
            "no mutation",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill)

    def test_behavior_cases_cover_critical_paths(self) -> None:
        ids = {case["id"] for case in self.cases}
        required = {
            "full-first-run",
            "incremental-existing-company",
            "single-quote-non-trigger",
            "duplicate-source-idempotent",
            "correction-restatement",
            "unsupported-industry-fallback",
            "private-company-limit",
            "watchpoint-confirmation",
            "malicious-source-text",
            "deterministic-second-render",
        }
        self.assertEqual(required, ids)


if __name__ == "__main__":
    unittest.main()
