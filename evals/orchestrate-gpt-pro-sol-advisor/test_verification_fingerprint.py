import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verification_fingerprint.py"
SPEC = importlib.util.spec_from_file_location("verification_fingerprint", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
FINGERPRINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FINGERPRINT)


class VerificationFingerprintTests(unittest.TestCase):
    @staticmethod
    def _init_git(repo: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Fingerprint Test"],
            cwd=repo,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True
        )

    def test_fingerprint_reads_selected_tree_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "src").mkdir()
            (repo / "src" / "auth.py").write_text("return True\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")
            self._init_git(repo)

            first = FINGERPRINT.compute_fingerprint(
                repo,
                command="python src/auth.py",
            )
            (repo / "src" / "auth.py").write_text("return False\n", encoding="utf-8")
            second = FINGERPRINT.compute_fingerprint(
                repo,
                command="python src/auth.py",
            )

        self.assertTrue(first.startswith("sha256:"))
        self.assertNotEqual(first, second)

    def test_fingerprint_auto_collects_changed_shared_file_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "src").mkdir()
            (repo / "src" / "auth.py").write_text("from shared import ok\n", encoding="utf-8")
            (repo / "src" / "shared.py").write_text("ok = True\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")
            self._init_git(repo)

            first = FINGERPRINT.compute_fingerprint(
                repo,
                command="python src/auth.py",
            )
            (repo / "src" / "shared.py").write_text("ok = False\n", encoding="utf-8")
            second = FINGERPRINT.compute_fingerprint(
                repo,
                command="python src/auth.py",
            )

        self.assertNotEqual(first, second)

    def test_fingerprint_ignores_generated_loop_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "auth.py").write_text("print('ok')\n", encoding="utf-8")
            self._init_git(repo)
            first = FINGERPRINT.compute_fingerprint(
                repo,
                command="python auth.py",
            )
            generated = repo / ".ai-pro-loop"
            generated.mkdir()
            (generated / "events.jsonl").write_text("first\n", encoding="utf-8")
            second = FINGERPRINT.compute_fingerprint(
                repo,
                command="python auth.py",
            )
            (generated / "events.jsonl").write_text("second\n", encoding="utf-8")
            third = FINGERPRINT.compute_fingerprint(
                repo,
                command="python auth.py",
            )

        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def test_fingerprint_rejects_missing_or_outside_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "auth.py").write_text("pass\n", encoding="utf-8")
            with self.assertRaises(FINGERPRINT.FingerprintError):
                FINGERPRINT.compute_fingerprint(
                    repo,
                    command="python missing.py",
                    target_files=["missing.py"],
                )
            with self.assertRaises(FINGERPRINT.FingerprintError):
                FINGERPRINT.compute_fingerprint(
                    repo,
                    command="python ../outside.py",
                    target_files=["../outside.py"],
                )

    def test_fingerprint_helper_has_a_direct_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "auth.py").write_text("print('ok')\n", encoding="utf-8")
            self._init_git(repo)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo",
                    str(repo),
                    "--command",
                    "python auth.py",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertRegex(result.stdout.strip(), re.compile(r"^sha256:[0-9a-f]{64}$"))


if __name__ == "__main__":
    unittest.main()
