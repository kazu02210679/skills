from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def parse_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, relative_path = line.split("  ", 1)
        entries[relative_path] = digest
    return entries


class HostCompatibilityTests(unittest.TestCase):
    def test_repository_does_not_claim_full_runtime_parity(self) -> None:
        compatibility = (
            REPOSITORY_ROOT / "docs" / "host-compatibility.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "does not claim that the hosts have identical runtime behavior",
            compatibility,
        )
        self.assertIn("intentionally retired", compatibility)

    def test_codex_orchestration_uses_skill_relative_wrappers(self) -> None:
        skill_root = REPOSITORY_ROOT / "skills" / "codex-orchestration"
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("SKILL_DIR/scripts/codex_run.sh", skill_text)
        self.assertIn("SKILL_DIR/scripts/codex_resume.sh", skill_text)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", skill_text)
        for filename in ("codex_run.sh", "codex_resume.sh"):
            with self.subTest(filename=filename):
                script = skill_root / "scripts" / filename
                self.assertTrue(script.is_file())
                self.assertIn("codex exec", script.read_text(encoding="utf-8"))

    def test_handoff_body_matches_the_pinned_manifest(self) -> None:
        manifest_path = (
            REPOSITORY_ROOT / "third_party" / "handoff-gist" / "SHA256SUMS"
        )
        entries = parse_manifest(manifest_path)
        self.assertEqual({"handoff/SKILL.md"}, set(entries))
        for relative_path, expected_digest in entries.items():
            actual_digest = hashlib.sha256(
                (REPOSITORY_ROOT / "skills" / relative_path).read_bytes()
            ).hexdigest()
            self.assertEqual(expected_digest, actual_digest)

    def test_pm_skills_are_not_vendored(self) -> None:
        self.assertFalse(
            (REPOSITORY_ROOT / "third_party" / "pm-skills").exists()
        )
        skill_names = {
            path.name
            for path in (REPOSITORY_ROOT / "skills").iterdir()
            if path.is_dir()
        }
        self.assertEqual(
            {
                "co-create-plan",
                "codex-orchestration",
                "complexity-aware-execution",
                "create-project-map",
                "handoff",
                "open-pull-request",
                "review-implementation-html",
                "writing-style",
            },
            skill_names,
        )
        root_readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("PM Skills are not vendored here.", root_readme)
        self.assertIn("its source plugin", root_readme)

    def test_codex_orchestration_documents_retired_plugin_interfaces(self) -> None:
        readme = (
            REPOSITORY_ROOT / "skills" / "codex-orchestration" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("intentionally retired", readme)
        self.assertIn("legacy plugin repository is retired or deleted", readme)


if __name__ == "__main__":
    unittest.main()
