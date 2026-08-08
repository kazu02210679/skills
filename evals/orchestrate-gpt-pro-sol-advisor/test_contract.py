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
            "frozen requirements, acceptance criteria, semantic review",
            "sol supplies bounded advice only",
            "materially new evidence",
            "sol_advisor_advisor",
            "sol_advisor_terra_implementer",
            "`accept`, `reject`, or `partially accept`",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

    def test_forbids_duplicate_review_recursion_and_silent_downgrade(self) -> None:
        for phrase in (
            "do not make sol a mandatory pre-pro or final gate",
            "reject nested",
            "sol-to-sol review",
            "fabricate a",
            "do not silently downgrade",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.skill.lower())

    def test_combined_mode_does_not_invoke_sol_orchestration(self) -> None:
        lower = self.skill.lower()
        self.assertNotIn(
            "required sub-skill (conditional advisory dependency)", lower
        )
        self.assertIn("do not invoke", lower)
        self.assertIn("`sol-advisor:orchestration` in combined mode", lower)
        self.assertIn("configured advisor", lower)

    def test_setup_failure_stops_before_gpc_initialization(self) -> None:
        result = POLICY.route(
            {
                "intent": "combined",
                "setup_status": "missing",
                "preferences_loaded": False,
                "available_roles": [],
            }
        )
        self.assertEqual("setup-required-before-gpc", result["terminal"])
        self.assertFalse(result["gpc_started"])
        self.assertEqual(0, result["sol_calls"])

    def test_setup_change_requires_a_fresh_task_before_gpc(self) -> None:
        result = POLICY.route(
            {
                "intent": "combined",
                "setup_status": "ready",
                "preferences_loaded": True,
                "setup_changed_this_task": True,
                "configured_advisor_role": "sol_advisor_advisor",
                "available_roles": ["sol_advisor_advisor"],
            }
        )
        self.assertEqual("fresh-task-required", result["terminal"])
        self.assertFalse(result["gpc_started"])

    def test_configured_advisor_is_the_only_combined_sol_role(self) -> None:
        scenario = {
            "intent": "combined",
            "setup_status": "ready",
            "preferences_loaded": True,
            "configured_advisor_role": "sol_advisor_advisor",
            "available_roles": [
                "sol_advisor_advisor",
                "sol_advisor_routine",
                "sol_advisor_high",
                "sol_advisor_terra_implementer",
                "sol_advisor_sol_reviewer",
            ],
            "codex_commitment_boundary": True,
            "concrete_question": True,
            "precise_question": "Which authentication invariant is still at risk?",
            "material_risk": True,
            "decision_value": True,
        }
        result = POLICY.route(scenario)
        self.assertEqual("sol_advisor_advisor", result["selected_lane"])
        self.assertEqual(1, result["sol_calls"])

    def test_legacy_only_roles_do_not_trigger_compatibility_fallback(self) -> None:
        result = POLICY.route(
            {
                "intent": "combined",
                "setup_status": "ready",
                "preferences_loaded": True,
                "configured_advisor_role": "sol_advisor_advisor",
                "available_roles": [
                    "sol_advisor_terra_implementer",
                    "sol_advisor_sol_reviewer",
                ],
            }
        )
        self.assertEqual("configured-advisor-unavailable", result["terminal"])
        self.assertFalse(result["gpc_started"])
        self.assertFalse(result["compatibility_fallback"])

    def test_nested_orchestration_and_mandatory_final_review_are_rejected(self) -> None:
        base = {
            "intent": "combined",
            "setup_status": "ready",
            "preferences_loaded": True,
            "configured_advisor_role": "sol_advisor_advisor",
            "available_roles": ["sol_advisor_advisor"],
        }
        nested = POLICY.route(
            {**base, "requested_dependency": "sol-advisor:orchestration"}
        )
        self.assertEqual("forbidden-nested-orchestration", nested["terminal"])
        self.assertEqual(0, nested["sol_calls"])

        final_gate = POLICY.route({**base, "mandatory_final_sol_review": True})
        self.assertEqual("local-verify-then-pro", final_gate["terminal"])
        self.assertEqual(0, final_gate["sol_calls"])

        implementer = POLICY.route(
            {**base, "requested_role": "sol_advisor_terra_implementer"}
        )
        self.assertEqual("non-advisor-role-rejected", implementer["terminal"])
        self.assertEqual(0, implementer["sol_calls"])

    def test_cases_cover_routing_and_failure_boundaries(self) -> None:
        cases = {case["id"]: case for case in self.cases}
        self.assertEqual(
            {
                "standalone-gpt-pro-remains-standalone",
                "standalone-sol-remains-standalone",
                "ambiguous-installation-does-not-compose",
                "missing-setup-stops-before-gpc",
                "setup-change-requires-fresh-task",
                "legacy-only-does-not-fallback",
                "nested-orchestration-is-rejected",
                "explicit-combined-low-risk-skips-sol",
                "technical-question-selects-configured-advisor",
                "authority-escalation-is-rejected",
                "conflicting-advice-is-rejected",
                "advisor-requested-reentry-is-suppressed",
                "unchanged-follow-up-is-suppressed",
                "material-follow-up-is-bounded",
                "pro-correction-does-not-force-sol-loop",
                "mandatory-final-sol-review-is-suppressed",
                "implementer-role-is-rejected",
            },
            set(cases),
        )

        for case_id, case in cases.items():
            with self.subTest(case_id=case_id):
                actual = POLICY.route(case["scenario"])
                for key, value in case["expect"].items():
                    self.assertEqual(value, actual.get(key), key)

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
            3,
            sum(item["contract_violation"] for item in results["baseline"]),
        )
        self.assertTrue(
            all(not item["contract_violation"] for item in results["with_skill"])
        )
        for trace in results["with_skill"]:
            with self.subTest(sample=trace["sample"]):
                self.assertEqual("combined", trace["selected_mode"])
                self.assertFalse(trace["nested_orchestration"])
                self.assertFalse(trace["legacy_fallback"])
                self.assertTrue(trace["rationale"])
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
