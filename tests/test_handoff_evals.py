from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = REPOSITORY_ROOT / "evals" / "handoff"
RUNNER_PATH = EVAL_ROOT / "run.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("handoff_eval_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HandoffEvaluationIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()
        cls.criteria = yaml.safe_load(
            (EVAL_ROOT / "criteria.yaml").read_text(encoding="utf-8")
        )

    def test_raw_inputs_are_separate_from_evaluator_criteria(self) -> None:
        case_ids = set(self.criteria["cases"])
        input_ids = {
            path.stem
            for path in (EVAL_ROOT / "inputs").glob("*.md")
        }
        self.assertEqual(case_ids, input_ids)

        criteria_only_markers = (
            "pass_conditions",
            "universal_pass_conditions",
            "genuinely new non-fork task",
        )
        for input_path in (EVAL_ROOT / "inputs").glob("*.md"):
            text = input_path.read_text(encoding="utf-8")
            with self.subTest(input=input_path.name):
                for marker in criteria_only_markers:
                    self.assertNotIn(marker, text)

    def test_execution_prompts_do_not_include_evaluator_criteria(self) -> None:
        criteria_text = (EVAL_ROOT / "criteria.yaml").read_text(encoding="utf-8")
        for case_id in self.criteria["cases"]:
            prompt = self.runner.build_execution_prompt(
                Path("candidate/SKILL.md"),
                Path(f"inputs/{case_id}.md"),
            )
            with self.subTest(case_id=case_id):
                self.assertNotIn("criteria.yaml", prompt)
                self.assertNotIn(criteria_text, prompt)
                self.assertNotIn("pass_conditions", prompt)
                self.assertNotRegex(prompt, r"[A-Za-z]:\\Users\\")
                self.assertFalse(prompt.startswith("/"))

    def test_evidence_manifest_records_candidate_and_exact_prompts(self) -> None:
        prompts = {
            case_id: self.runner.build_execution_prompt(
                Path("candidate/SKILL.md"),
                Path(f"inputs/{case_id}.md"),
            )
            for case_id in self.criteria["cases"]
        }
        manifest = self.runner.build_evidence_manifest(
            candidate_commit="a" * 40,
            skill_sha256="b" * 64,
            codex_version="codex-cli test",
            model="test-model",
            execution_prompts=prompts,
        )
        self.assertEqual("a" * 40, manifest["candidate"]["commit"])
        self.assertEqual("b" * 64, manifest["candidate"]["skill_sha256"])
        self.assertEqual(prompts, manifest["execution_prompts"])
        json.dumps(manifest)

    def test_candidate_binding_rejects_content_not_in_recorded_commit(self) -> None:
        digest = self.runner.assert_candidate_content(
            b"same candidate\n",
            b"same candidate\n",
        )
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.runner.assert_candidate_content(
                b"recorded candidate\n",
                b"dirty candidate\n",
            )

    def test_dry_run_binds_linked_worktree_commit_and_writes_evidence(self) -> None:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            text=True,
        ).strip()
        resolved_commit, committed_skill = self.runner._read_committed_candidate(
            head
        )

        def fake_run(command: list[str], *, cwd: Path):
            del cwd
            if command[-1] == "--version":
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="codex-cli dry-run\n",
                    stderr="",
                )

            output_path = Path(command[command.index("-o") + 1])
            prompt = command[-1]
            if prompt.startswith("Act as a strict behavioral evaluator."):
                payload = json.loads(prompt.split("\n\n", 1)[1])
                output_path.write_text(
                    json.dumps(
                        {
                            "case_id": payload["case_id"],
                            "pass": True,
                            "findings": [],
                        }
                    ),
                    encoding="utf-8",
                )
            else:
                output_path.write_text(
                    "Simulated candidate response.\n",
                    encoding="utf-8",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"type":"dry-run"}\n',
                stderr="",
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            candidate_path = temporary_root / "SKILL.md"
            candidate_path.write_bytes(committed_skill)
            output_directory = temporary_root / "evidence"
            arguments = argparse.Namespace(
                output_dir=str(output_directory),
                candidate_commit=head,
                model="dry-run-model",
                codex="codex-dry-run",
            )

            with (
                mock.patch.object(
                    self.runner,
                    "CANDIDATE_PATH",
                    candidate_path,
                ),
                mock.patch.object(
                    self.runner,
                    "_run",
                    side_effect=fake_run,
                ),
            ):
                result = self.runner.run_evaluation(arguments)

            self.assertEqual(0, result)
            evidence = json.loads(
                (output_directory / "evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(resolved_commit, evidence["candidate"]["commit"])
            self.assertEqual(
                hashlib.sha256(committed_skill).hexdigest(),
                evidence["candidate"]["skill_sha256"],
            )
            self.assertEqual(
                {"passed": 3, "total": 3},
                evidence["summary"],
            )
            self.assertEqual(
                set(self.criteria["cases"]),
                set(evidence["execution_prompts"]),
            )
            for case_id in self.criteria["cases"]:
                with self.subTest(case_id=case_id):
                    self.assertTrue(
                        (
                            output_directory
                            / evidence["cases"][case_id]["artifacts"]["response"]
                        ).is_file()
                    )

    def test_tracked_eval_files_have_no_machine_specific_paths(self) -> None:
        for path in EVAL_ROOT.rglob("*"):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or path.suffix == ".pyc"
            ):
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT)):
                self.assertIsNone(re.search(r"[A-Za-z]:\\Users\\", text))
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/home/", text)


if __name__ == "__main__":
    unittest.main()
