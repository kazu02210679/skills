from __future__ import annotations

from copy import deepcopy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals" / "hotl-governance"
WORKFLOW = ROOT / ".github" / "workflows" / "validate-skills.yml"
FOCUSED_COMMAND = 'python -m unittest discover -s evals/hotl-governance -p "test_*.py" -v'
INSTALL_COMMAND = "python -m pip install -r requirements-validation.txt"


class HotlWorkflowTests(unittest.TestCase):
    def _assert_hotl_job(self, job: dict[str, object], runner: str) -> None:
        self.assertEqual(runner, job["runs-on"])
        steps = job["steps"]
        self.assertIsInstance(steps, list)
        checkout = [
            index
            for index, step in enumerate(steps)
            if step.get("uses") == "actions/checkout@v4"
        ]
        setup = [
            index
            for index, step in enumerate(steps)
            if step.get("uses") == "actions/setup-python@v5"
        ]
        install = [
            index
            for index, step in enumerate(steps)
            if step.get("run") == INSTALL_COMMAND
        ]
        focused = [
            index
            for index, step in enumerate(steps)
            if step.get("run") == FOCUSED_COMMAND
        ]
        self.assertEqual(1, len(checkout))
        self.assertEqual(1, len(setup))
        self.assertEqual("3.12", steps[setup[0]].get("with", {}).get("python-version"))
        self.assertEqual(1, len(install))
        self.assertEqual(1, len(focused))
        self.assertLess(checkout[0], setup[0])
        self.assertLess(setup[0], install[0])
        self.assertLess(install[0], focused[0])

    def test_linux_and_windows_jobs_run_hotl_suite(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        for name, runner in (
            ("hotl-governance-ubuntu", "ubuntu-latest"),
            ("hotl-governance-windows", "windows-latest"),
        ):
            with self.subTest(name=name):
                self._assert_hotl_job(workflow["jobs"][name], runner)

    def test_job_contract_rejects_runtime_dependency_and_order_mutations(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        original = workflow["jobs"]["hotl-governance-ubuntu"]

        wrong_python = deepcopy(original)
        wrong_python["steps"][1]["with"]["python-version"] = "3.11"

        missing_install = deepcopy(original)
        missing_install["steps"] = [
            step
            for step in missing_install["steps"]
            if step.get("run") != INSTALL_COMMAND
        ]

        duplicate_focused = deepcopy(original)
        duplicate_focused["steps"].append({"run": FOCUSED_COMMAND})

        out_of_order = deepcopy(original)
        out_of_order["steps"][1], out_of_order["steps"][3] = (
            out_of_order["steps"][3],
            out_of_order["steps"][1],
        )

        for name, mutated in (
            ("python-3.11", wrong_python),
            ("missing-install", missing_install),
            ("duplicate-focused", duplicate_focused),
            ("out-of-order", out_of_order),
        ):
            with self.subTest(name=name):
                with self.assertRaises(AssertionError):
                    self._assert_hotl_job(mutated, "ubuntu-latest")


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
