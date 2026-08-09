from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals" / "hotl-governance"
WORKFLOW = ROOT / ".github" / "workflows" / "validate-skills.yml"
FOCUSED_COMMAND = 'python -m unittest discover -s evals/hotl-governance -p "test_*.py" -v'


class HotlWorkflowTests(unittest.TestCase):
    def test_linux_and_windows_jobs_run_hotl_suite(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        for name, runner in (
            ("hotl-governance-ubuntu", "ubuntu-latest"),
            ("hotl-governance-windows", "windows-latest"),
        ):
            with self.subTest(name=name):
                job = workflow["jobs"][name]
                self.assertEqual(runner, job["runs-on"])
                self.assertTrue(
                    any(step.get("run") == FOCUSED_COMMAND for step in job["steps"])
                )


def load_tests(
    loader: unittest.TestLoader,
    _: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for path in sorted(EVAL_ROOT.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(f"hotl_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    suite.addTests(loader.loadTestsFromTestCase(HotlWorkflowTests))
    return suite
