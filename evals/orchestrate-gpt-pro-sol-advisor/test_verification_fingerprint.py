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

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True)

    @classmethod
    def _make_submodule_fixture(cls, root: Path) -> tuple[Path, Path]:
        source = root / "submodule-source"
        source.mkdir()
        (source / "module.py").write_text("value = 1\n", encoding="utf-8")
        cls._init_git(source)

        repository = root / "superproject"
        repository.mkdir()
        (repository / "app.py").write_text("print('ok')\n", encoding="utf-8")
        cls._init_git(repository)
        (repository / "deps").mkdir()
        submodule = repository / "deps" / "sub"
        subprocess.run(
            ["git", "clone", "-q", str(source), str(submodule)],
            cwd=repository,
            check=True,
        )
        source_head = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=source,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        cls._git(
            repository,
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{source_head},deps/sub",
        )
        cls._git(repository, "commit", "-qm", "add submodule")
        cls._git(submodule, "config", "user.email", "test@example.invalid")
        cls._git(submodule, "config", "user.name", "Fingerprint Test")
        return repository, submodule

    @classmethod
    def _advance_submodule(cls, submodule: Path, value: int, message: str) -> None:
        (submodule / "module.py").write_text(
            f"value = {value}\n", encoding="utf-8"
        )
        cls._git(submodule, "add", "module.py")
        cls._git(submodule, "commit", "-qm", message)

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

    def test_git_changed_paths_preserves_quoted_unicode_and_rename_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            spaced = repo / "file with space.py"
            unicode_path = repo / "日本語.py"
            old_path = repo / "old name.py"
            new_path = repo / "new name.py"
            spaced.write_text("value = 1\n", encoding="utf-8")
            unicode_path.write_text("value = 1\n", encoding="utf-8")
            old_path.write_text("value = 1\n", encoding="utf-8")
            self._init_git(repo)
            subprocess.run(
                ["git", "config", "core.quotePath", "true"],
                cwd=repo,
                check=True,
            )
            spaced.write_text("value = 2\n", encoding="utf-8")
            unicode_path.write_text("value = 2\n", encoding="utf-8")
            subprocess.run(
                ["git", "mv", str(old_path), str(new_path)],
                cwd=repo,
                check=True,
            )

            changed = FINGERPRINT._git_changed_paths(repo)

        self.assertIn("file with space.py", changed)
        self.assertIn("日本語.py", changed)
        self.assertIn("old name.py", changed)
        self.assertIn("new name.py", changed)
        self.assertNotIn('"日本語.py"', changed)

    def test_environment_identity_binds_the_command_toolchain(self) -> None:
        identity = FINGERPRINT._environment_identity("npm test")

        self.assertEqual("npm", identity["command_executable"])
        self.assertIn("command_toolchain", identity)
        self.assertTrue(identity["command_toolchain"])

    def test_fingerprint_binds_each_changed_submodule_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, submodule = self._make_submodule_fixture(Path(directory))
            self._advance_submodule(submodule, 2, "advance to B")
            second = FINGERPRINT.compute_fingerprint(
                repository,
                command="python app.py",
            )
            record = FINGERPRINT._input_record(
                repository,
                "deps/sub",
                {"changed"},
            )
            self.assertNotIn("deleted", record)
            self.assertEqual(
                FINGERPRINT._git_output(submodule, "rev-parse", "--verify", "HEAD"),
                record["submodule_head"],
            )
            self._advance_submodule(submodule, 3, "advance to C")
            third = FINGERPRINT.compute_fingerprint(
                repository,
                command="python app.py",
            )

        self.assertNotEqual(second, third)

    def test_dirty_submodule_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, submodule = self._make_submodule_fixture(Path(directory))
            (submodule / "module.py").write_text("value = dirty\n", encoding="utf-8")

            with self.assertRaisesRegex(
                FINGERPRINT.FingerprintError,
                "dirty submodule",
            ):
                FINGERPRINT.compute_fingerprint(
                    repository,
                    command="python app.py",
                )

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
