from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPOSITORY_ROOT / "scripts" / "validate-skills.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_skills", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


class SkillValidationTests(unittest.TestCase):
    def validate_skill(
        self,
        frontmatter: str,
        *,
        directory_name: str = "valid-skill",
        body: str = "# Valid skill\n\nDo the work.\n",
        openai_yaml: str | None = None,
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            skill_directory = Path(temporary_directory) / directory_name
            skill_directory.mkdir()
            (skill_directory / "SKILL.md").write_text(
                f"---\n{frontmatter}\n---\n\n{body}",
                encoding="utf-8",
            )
            if openai_yaml is not None:
                agents_directory = skill_directory / "agents"
                agents_directory.mkdir()
                (agents_directory / "openai.yaml").write_text(
                    openai_yaml,
                    encoding="utf-8",
                )
            return VALIDATOR.validate_skill_directory(skill_directory)

    def assert_rejected(self, frontmatter: str, expected: str, **kwargs) -> None:
        errors = self.validate_skill(frontmatter, **kwargs)
        self.assertTrue(
            any(expected in error for error in errors),
            f"Expected {expected!r} in {errors!r}",
        )

    def test_rejects_malformed_yaml(self) -> None:
        self.assert_rejected(
            "name: valid-skill\ndescription: [unterminated",
            "invalid YAML",
        )

    def test_rejects_duplicate_frontmatter_keys(self) -> None:
        self.assert_rejected(
            "name: valid-skill\nname: shadowed\ndescription: Useful.",
            "duplicate YAML key 'name'",
        )

    def test_rejects_unknown_frontmatter_keys(self) -> None:
        self.assert_rejected(
            "name: valid-skill\ndescription: Useful.\nlicense: MIT",
            "unknown frontmatter key 'license'",
        )

    def test_rejects_empty_and_overlength_metadata(self) -> None:
        self.assert_rejected(
            "name: ''\ndescription: Useful.",
            "name must not be empty",
        )
        self.assert_rejected(
            "name: valid-skill\ndescription: ''",
            "description must not be empty",
        )
        self.assert_rejected(
            f"name: {'a' * 65}\ndescription: Useful.",
            "name exceeds 64 characters",
            directory_name="a" * 65,
        )
        self.assert_rejected(
            f"name: valid-skill\ndescription: {'x' * 1025}",
            "description exceeds 1024 characters",
        )

    def test_rejects_invalid_skill_names(self) -> None:
        for invalid_name in ("Bad_Name", "-leading", "trailing-", "two--hyphens"):
            with self.subTest(invalid_name=invalid_name):
                self.assert_rejected(
                    f"name: {invalid_name}\ndescription: Useful.",
                    "invalid name",
                    directory_name=invalid_name,
                )

    def test_accepts_strict_multiline_yaml(self) -> None:
        errors = self.validate_skill(
            "name: valid-skill\n"
            "description: >-\n"
            "  A valid folded description for a portable Skill.",
        )
        self.assertEqual([], errors)

    def test_rejects_invalid_openai_interface_structure(self) -> None:
        valid_frontmatter = "name: valid-skill\ndescription: Useful."
        self.assert_rejected(
            valid_frontmatter,
            "interface must be a mapping",
            openai_yaml="interface: invalid\n",
        )
        self.assert_rejected(
            valid_frontmatter,
            "unknown interface key 'surprise'",
            openai_yaml=(
                "interface:\n"
                '  display_name: "Valid Skill"\n'
                '  short_description: "A useful short description"\n'
                '  default_prompt: "Use $valid-skill to do the work."\n'
                '  surprise: "not allowed"\n'
            ),
        )
        self.assert_rejected(
            valid_frontmatter,
            "duplicate YAML key 'display_name'",
            openai_yaml=(
                "interface:\n"
                '  display_name: "Valid Skill"\n'
                '  display_name: "Shadowed"\n'
                '  short_description: "A useful short description"\n'
                '  default_prompt: "Use $valid-skill to do the work."\n'
            ),
        )

    def test_rejects_openai_prompt_that_does_not_name_the_skill(self) -> None:
        self.assert_rejected(
            "name: valid-skill\ndescription: Useful.",
            "default_prompt must mention '$valid-skill'",
            openai_yaml=(
                "interface:\n"
                '  display_name: "Valid Skill"\n'
                '  short_description: "A useful short description"\n'
                '  default_prompt: "Do the work."\n'
            ),
        )

    def test_rejects_unknown_or_malformed_openai_dependencies(self) -> None:
        frontmatter = "name: valid-skill\ndescription: Useful."
        interface = (
            "interface:\n"
            '  display_name: "Valid Skill"\n'
            '  short_description: "A useful portable Skill description"\n'
            '  default_prompt: "Use $valid-skill to do the work."\n'
        )
        self.assert_rejected(
            frontmatter,
            "dependencies.tools[0].type must be 'mcp'",
            openai_yaml=(
                interface
                + "dependencies:\n"
                + "  tools:\n"
                + '    - type: "shell"\n'
                + '      value: "arbitrary"\n'
            ),
        )
        self.assert_rejected(
            frontmatter,
            "unknown top-level key 'surprise'",
            openai_yaml=interface + "surprise: true\n",
        )


class CatalogInvariantTests(unittest.TestCase):
    def copy_catalog(self, target: Path) -> None:
        shutil.copytree(REPOSITORY_ROOT / "skills", target / "skills")
        shutil.copytree(REPOSITORY_ROOT / "third_party", target / "third_party")
        shutil.copy2(REPOSITORY_ROOT / "README.md", target / "README.md")

    def test_current_catalog_satisfies_all_invariants(self) -> None:
        self.assertEqual([], VALIDATOR.validate_repository(REPOSITORY_ROOT))

    def test_rejects_catalog_count_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            self.copy_catalog(repository)
            shutil.rmtree(repository / "skills" / "ab-test-analysis")
            errors = VALIDATOR.validate_repository(repository)
            self.assertTrue(any("expected 71 skills" in error for error in errors))
            self.assertTrue(any("expected 68 PM Skills" in error for error in errors))

    def test_rejects_readme_count_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            self.copy_catalog(repository)
            readme = repository / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "次の71個",
                    "次の70個",
                ),
                encoding="utf-8",
            )
            errors = VALIDATOR.validate_repository(repository)
            self.assertTrue(any("README catalog count" in error for error in errors))

    def test_rejects_provenance_count_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            self.copy_catalog(repository)
            source_path = repository / "third_party" / "pm-skills" / "source.json"
            source_path.write_text(
                source_path.read_text(encoding="utf-8").replace(
                    '"imported_skill_count": 68',
                    '"imported_skill_count": 67',
                ),
                encoding="utf-8",
            )
            errors = VALIDATOR.validate_repository(repository)
            self.assertTrue(
                any("imported_skill_count must be 68" in error for error in errors)
            )

    def test_rejects_manifest_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            self.copy_catalog(repository)
            skill_path = repository / "skills" / "ab-test-analysis" / "SKILL.md"
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8") + "\nchanged\n",
                encoding="utf-8",
            )
            errors = VALIDATOR.validate_repository(repository)
            self.assertTrue(any("SHA-256 mismatch" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
