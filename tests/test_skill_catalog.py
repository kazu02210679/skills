from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPOSITORY_ROOT / "scripts" / "generate-skill-catalog.py"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_skill_catalog",
        GENERATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_generator()


class SkillCatalogTests(unittest.TestCase):
    def test_generated_catalog_is_current(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR_PATH), "--check"],
            cwd=REPOSITORY_ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_catalog_is_sorted_and_links_human_readmes(self) -> None:
        records = GENERATOR.skill_records(REPOSITORY_ROOT)
        names = [name for name, _ in records]
        self.assertEqual(sorted(names), names)

        catalog = GENERATOR.render_catalog(REPOSITORY_ROOT)
        for name in names:
            with self.subTest(name=name):
                self.assertIn(
                    f"[`{name}`](skills/{name}/README.md)",
                    catalog,
                )

    def test_expected_skills_are_in_the_canonical_catalog(self) -> None:
        names = [name for name, _ in GENERATOR.skill_records(REPOSITORY_ROOT)]
        self.assertEqual(
            [
                "co-create-plan",
                "codex-orchestration",
                "complexity-aware-execution",
                "create-project-map",
                "gpt-pro-codex-loop",
                "handoff",
                "open-pull-request",
                "review-implementation-html",
                "writing-style",
            ],
            names,
        )


if __name__ == "__main__":
    unittest.main()
