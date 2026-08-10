import importlib.util
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
    def test_fingerprint_reads_selected_tree_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "src").mkdir()
            (repo / "src" / "auth.py").write_text("return True\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")

            first = FINGERPRINT.compute_fingerprint(
                repo,
                command="pytest tests/auth.py",
                base_tree="tree-1",
                relevant_files=["src/auth.py"],
                lock_config_files=["pyproject.toml"],
                environment_identity={"python": "3.12", "platform": "win32"},
            )
            (repo / "src" / "auth.py").write_text("return False\n", encoding="utf-8")
            second = FINGERPRINT.compute_fingerprint(
                repo,
                command="pytest tests/auth.py",
                base_tree="tree-1",
                relevant_files=["src/auth.py"],
                lock_config_files=["pyproject.toml"],
                environment_identity={"python": "3.12", "platform": "win32"},
            )

        self.assertTrue(first.startswith("sha256:"))
        self.assertNotEqual(first, second)

    def test_fingerprint_rejects_missing_or_outside_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "auth.py").write_text("pass\n", encoding="utf-8")
            with self.assertRaises(FINGERPRINT.FingerprintError):
                FINGERPRINT.compute_fingerprint(
                    repo,
                    command="pytest",
                    base_tree="tree-1",
                    relevant_files=["missing.py"],
                    lock_config_files=[],
                    environment_identity={"python": "3.12"},
                )
            with self.assertRaises(FINGERPRINT.FingerprintError):
                FINGERPRINT.compute_fingerprint(
                    repo,
                    command="pytest",
                    base_tree="tree-1",
                    relevant_files=[str(repo.parent / "outside.py")],
                    lock_config_files=[],
                    environment_identity={"python": "3.12"},
                )


if __name__ == "__main__":
    unittest.main()
