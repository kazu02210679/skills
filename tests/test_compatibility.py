from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_SKILLS = {
    "complexity-aware-execution",
    "handoff",
    "open-pull-request",
    "writing-style",
}


def parse_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, relative_path = line.split("  ", 1)
        entries[relative_path] = digest
    return entries


class HostCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        contract_path = (
            REPOSITORY_ROOT / "compatibility" / "host-contract.json"
        )
        cls.contract = json.loads(contract_path.read_text(encoding="utf-8"))

    def test_argument_placeholder_has_native_and_adapter_semantics(self) -> None:
        argument_contract = self.contract["argument_placeholder"]
        self.assertEqual("$ARGUMENTS", argument_contract["token"])
        self.assertEqual(
            "native_substitution",
            argument_contract["hosts"]["claude_code"]["mode"],
        )
        self.assertEqual(
            "semantic_adapter",
            argument_contract["hosts"]["codex"]["mode"],
        )
        self.assertFalse(self.contract["claims"]["full_runtime_parity"])

        pm_skill_files = [
            path
            for path in (REPOSITORY_ROOT / "skills").glob("*/SKILL.md")
            if path.parent.name not in CUSTOM_SKILLS
        ]
        self.assertTrue(
            any("$ARGUMENTS" in path.read_text(encoding="utf-8") for path in pm_skill_files)
        )

    def test_every_upstream_slash_reference_maps_to_present_skills(self) -> None:
        shipping_text = (
            REPOSITORY_ROOT / "skills" / "shipping-artifacts" / "SKILL.md"
        ).read_text(encoding="utf-8")
        slash_references = set(re.findall(r"`(/[-a-z]+)`", shipping_text))
        mappings = self.contract["slash_command_mappings"]
        self.assertEqual(slash_references, set(mappings))

        for command, mapping in mappings.items():
            with self.subTest(command=command):
                self.assertTrue(mapping["procedure"].strip())
                for skill_name in mapping["skills"]:
                    self.assertTrue(
                        (
                            REPOSITORY_ROOT
                            / "skills"
                            / skill_name
                            / "SKILL.md"
                        ).is_file(),
                        f"{command} maps to missing Skill {skill_name}",
                    )

    def test_pm_skill_bodies_match_the_pinned_sha256_manifest(self) -> None:
        manifest_path = (
            REPOSITORY_ROOT / "third_party" / "pm-skills" / "SHA256SUMS"
        )
        entries = parse_manifest(manifest_path)
        pm_skill_names = {
            path.name
            for path in (REPOSITORY_ROOT / "skills").iterdir()
            if path.is_dir() and path.name not in CUSTOM_SKILLS
        }
        self.assertEqual(
            {f"{name}/SKILL.md" for name in pm_skill_names},
            set(entries),
        )
        self.assertEqual(68, len(entries))

        for relative_path, expected_digest in entries.items():
            with self.subTest(relative_path=relative_path):
                actual_digest = hashlib.sha256(
                    (REPOSITORY_ROOT / "skills" / relative_path).read_bytes()
                ).hexdigest()
                self.assertEqual(expected_digest, actual_digest)

    def test_provenance_records_name_their_manifests(self) -> None:
        for source_name in ("pm-skills", "handoff-gist"):
            with self.subTest(source_name=source_name):
                source = json.loads(
                    (
                        REPOSITORY_ROOT
                        / "third_party"
                        / source_name
                        / "source.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual("SHA256SUMS", source["sha256_manifest"])


if __name__ == "__main__":
    unittest.main()
