from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals" / "company-research"


def load_tests(
    loader: unittest.TestLoader,
    _: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for path in sorted(EVAL_ROOT.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(
            f"company_research_{path.stem}",
            path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite
