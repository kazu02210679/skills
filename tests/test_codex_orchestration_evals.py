from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals" / "codex-orchestration"


def find_bash() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    candidates = (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Git" / "usr" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Git" / "bin" / "bash.exe",
    )
    return next((str(path) for path in candidates if path.is_file()), None)


BASH = find_bash()


@unittest.skipUnless(BASH, "Bash 4.4+ is required")
class CodexOrchestrationShellEvaluations(unittest.TestCase):
    def run_eval(self, name: str) -> None:
        env = os.environ.copy()
        if os.name == "nt":
            env["PATH"] = os.pathsep.join((str(Path(BASH).parent), env.get("PATH", "")))
        result = subprocess.run(
            [BASH, str(EVAL_DIR / name)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=540,
            check=False,
        )
        self.assertEqual(
            0,
            result.returncode,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_scope_check(self) -> None:
        self.run_eval("test_scope_check.sh")

    def test_run_resume(self) -> None:
        self.run_eval("test_run_resume.sh")

    def test_commit_status(self) -> None:
        self.run_eval("test_commit_status.sh")
