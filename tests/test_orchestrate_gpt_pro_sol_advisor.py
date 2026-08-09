from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FOCUSED_TEST = ROOT / "evals" / "orchestrate-gpt-pro-sol-advisor" / "test_contract.py"
WORKFLOW = ROOT / ".github" / "workflows" / "validate-skills.yml"
WINDOWS_JOB = "orchestrate-gpt-pro-sol-advisor-windows"
FOCUSED_COMMAND = "python -m unittest evals/orchestrate-gpt-pro-sol-advisor/test_contract.py -v"

SPEC = importlib.util.spec_from_file_location("composition_contract", FOCUSED_TEST)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {FOCUSED_TEST}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WindowsWorkflowContractTests(unittest.TestCase):
    def test_dedicated_windows_job_runs_focused_contract_evaluation(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertIn(WINDOWS_JOB, workflow["jobs"])
        job = workflow["jobs"][WINDOWS_JOB]

        self.assertEqual(job["runs-on"], "windows-latest")
        self.assertNotIn("continue-on-error", job)
        self.assertTrue(
            any(step.get("run") == FOCUSED_COMMAND for step in job["steps"]),
            f"{WINDOWS_JOB} must run {FOCUSED_COMMAND!r}",
        )


def load_tests(loader: unittest.TestLoader, _: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = loader.loadTestsFromTestCase(MODULE.CompositionContractTests)
    suite.addTests(loader.loadTestsFromTestCase(WindowsWorkflowContractTests))
    return suite
