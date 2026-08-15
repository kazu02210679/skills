from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "company-research" / "scripts" / "company_research.py"


class CompanyResearchCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

    def test_cli_help_is_available(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("company research", result.stdout.lower())

    def test_missing_packet_returns_contract_error_exit_code(self) -> None:
        result = self.run_cli("prepare", "--packet", "does-not-exist.json")
        self.assertEqual(2, result.returncode)
        self.assertIn("does-not-exist.json", result.stderr)

    def test_recover_help_labels_command_diagnostic_only(self) -> None:
        result = self.run_cli("recover", "--help")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("diagnostic only", result.stdout.lower())
        self.assertIn("no mutation", result.stdout.lower())

    def test_render_writes_only_requested_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "rendered"
            result = self.run_cli(
                "render",
                "--company-id",
                "cmp_" + "a" * 32,
                "--output-dir",
                str(output),
            )
            self.assertIn(result.returncode, {0, 4, 5})
            self.assertFalse((ROOT / "company-dashboard.html").exists())


if __name__ == "__main__":
    unittest.main()
