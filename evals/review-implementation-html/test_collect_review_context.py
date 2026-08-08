from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "review-implementation-html" / "scripts" / "collect_review_context.py"
SPEC = importlib.util.spec_from_file_location("collect_review_context", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ReviewContextTests(unittest.TestCase):
    def test_redacts_common_secret_assignments(self):
        redacted, labels = MODULE.redact_text("API_KEY=sk-secretvalue123456")
        self.assertNotIn("secretvalue", redacted)
        self.assertIn("[REDACTED]", redacted)
        self.assertIn("API_KEY", labels)

    def test_rejects_non_git_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Git repository"):
                MODULE.collect_context(pathlib.Path(directory), "HEAD~1", "WORKTREE", 1000)

    def test_detects_high_risk_changed_lines_without_exposing_content(self):
        diff = """diff --git a/src/server.py b/src/server.py
--- a/src/server.py
+++ b/src/server.py
@@ -1 +1,2 @@
-check_permission(user)
+subprocess.run(command)
+value = safe_parse(data)
"""
        self.assertEqual(
            ["auth_or_authorization", "command_or_rce"],
            MODULE.detect_diff_risk_signals(diff),
        )
        self.assertEqual(
            {"added_lines": 2, "deleted_lines": 1},
            MODULE.diff_stats(diff),
        )

    def test_ignores_diff_headers_and_context_lines_for_risk_detection(self):
        diff = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1 +1 @@
 subprocess.run(existing_command)
-old_value = 1
+new_value = 2
"""
        self.assertEqual([], MODULE.detect_diff_risk_signals(diff))

    def test_collects_worktree_diff_from_real_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = pathlib.Path(directory)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
            target = repo / "sample.txt"
            target.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "sample.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
            target.write_text("after\n", encoding="utf-8")

            context = MODULE.collect_context(repo, "HEAD", "WORKTREE", 100_000)

            self.assertEqual(context["head"], "WORKTREE")
            self.assertIn("sample.txt", context["changed_files"][0]["path"])
            self.assertIn("+after", context["diff"])
            self.assertFalse(context["truncated"])
            self.assertEqual([], context["risk_signals"])

    def test_untracked_content_fails_closed_for_review_topology(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = pathlib.Path(directory)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
            (repo / "README.md").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
            (repo / "server.py").write_text("subprocess.run(command)\n", encoding="utf-8")

            context = MODULE.collect_context(repo, "HEAD", "WORKTREE", 100_000)

            self.assertIn("untracked_content_uninspected", context["risk_signals"])


if __name__ == "__main__":
    unittest.main()
