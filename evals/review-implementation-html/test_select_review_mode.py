from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPOSITORY_ROOT
    / "skills"
    / "review-implementation-html"
    / "scripts"
    / "select_review_mode.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("select_review_mode", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load review selector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SelectReviewModeTests(unittest.TestCase):
    class SpyReviewer:
        def __init__(self, session_id: str, trace: list[tuple[str, str, str | None]]) -> None:
            self.session_id = session_id
            self.trace = trace

        def review(self, pass_name: str, plan: str | None) -> str:
            self.trace.append((self.session_id, pass_name, plan))
            return pass_name

    @staticmethod
    def factory(trace: list[tuple[str, str, str | None]], creations: list[str]):
        def create(mode: str):
            session_id = f"session-{len(creations) + 1}"
            creations.append(mode)
            return SelectReviewModeTests.SpyReviewer(session_id, trace)
        return create

    def test_normal_changes_use_serial_same_session_review(self) -> None:
        decision = load_module().select_review_mode(
            changed_files=19, added_lines=500, deleted_lines=499, paths=["src/view.py"]
        )
        self.assertEqual("serial_same_session", decision["mode"])
        self.assertEqual([], decision["reasons"])

    def test_file_and_line_thresholds_are_inclusive(self) -> None:
        module = load_module()
        self.assertEqual(
            "isolated",
            module.select_review_mode(20, 0, 0, ["src/view.py"])["mode"],
        )
        self.assertEqual(
            "isolated",
            module.select_review_mode(1, 600, 400, ["src/view.py"])["mode"],
        )

    def test_high_risk_paths_force_isolation(self) -> None:
        decision = load_module().select_review_mode(
            1, 1, 1, ["src/auth/permissions.py"]
        )
        self.assertEqual("isolated", decision["mode"])
        self.assertIn("auth_or_authorization", decision["risk_categories"])

    def test_diff_risk_signals_force_isolation_for_ordinary_paths(self) -> None:
        decision = load_module().select_review_mode(
            1,
            1,
            0,
            ["src/server.py"],
            risk_signals=["command_or_rce"],
        )
        self.assertEqual("isolated", decision["mode"])
        self.assertIn("high_risk:command_or_rce", decision["reasons"])

    def test_force_isolated_is_fail_closed(self) -> None:
        decision = load_module().select_review_mode(
            1, 1, 0, ["README.md"], force_isolated=True
        )
        self.assertEqual("isolated", decision["mode"])
        self.assertIn("force_isolated", decision["reasons"])

    def test_plan_blind_always_precedes_plan_aware(self) -> None:
        decision = load_module().select_review_mode(1, 1, 1, ["README.md"])
        self.assertEqual(["plan_blind", "plan_aware"], decision["review_order"])

    def test_serial_orchestration_reuses_one_session_and_injects_plan_after_blind(self) -> None:
        module = load_module()
        trace: list[tuple[str, str, str | None]] = []
        creations: list[str] = []
        result = module.orchestrate_review(
            {"mode": "serial_same_session"},
            "approved plan",
            self.factory(trace, creations),
        )
        self.assertEqual(["serial_same_session"], creations)
        self.assertEqual(
            [
                ("session-1", "plan_blind", None),
                ("session-1", "plan_aware", "approved plan"),
            ],
            trace,
        )
        self.assertEqual(0, result["isolated_session_creations"])
        events = [event["event"] for event in result["events"]]
        self.assertLess(events.index("pass_completed"), events.index("plan_injected"))

    def test_isolated_orchestration_still_hides_plan_until_blind_completes(self) -> None:
        module = load_module()
        trace: list[tuple[str, str, str | None]] = []
        creations: list[str] = []
        result = module.orchestrate_review(
            {"mode": "isolated"},
            "approved plan",
            self.factory(trace, creations),
        )
        self.assertEqual(["isolated", "isolated"], creations)
        self.assertEqual(None, trace[0][2])
        self.assertEqual("approved plan", trace[1][2])
        self.assertNotEqual(trace[0][0], trace[1][0])
        self.assertEqual(2, result["isolated_session_creations"])
        events = [event["event"] for event in result["events"]]
        self.assertLess(events.index("pass_completed"), events.index("plan_injected"))


if __name__ == "__main__":
    unittest.main()
