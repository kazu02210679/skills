from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOCUSED_TEST = ROOT / "evals" / "orchestrate-gpt-pro-sol-advisor" / "test_contract.py"

SPEC = importlib.util.spec_from_file_location("composition_contract", FOCUSED_TEST)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {FOCUSED_TEST}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def load_tests(loader: unittest.TestLoader, _: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    return loader.loadTestsFromTestCase(MODULE.CompositionContractTests)
