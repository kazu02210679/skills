from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPORARY_ROOT = REPOSITORY_ROOT / ".test-tmp"


def git_bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    drive, tail = os.path.splitdrive(str(resolved))
    normalized_tail = tail.lstrip("/\\").replace(os.sep, "/")
    return f"/{drive[0].lower()}/{normalized_tail}"


def find_bash() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    candidates = (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Git"
        / "usr"
        / "bin"
        / "bash.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Git"
        / "bin"
        / "bash.exe",
    )
    return next((str(path) for path in candidates if path.is_file()), None)


def find_powershell() -> str | None:
    names = ("powershell.exe", "pwsh") if os.name == "nt" else ("pwsh",)
    return next((path for name in names if (path := shutil.which(name))), None)


@dataclass(frozen=True)
class Installer:
    name: str
    executable: str

    def command(
        self,
        repository: Path,
        project: Path,
        *,
        force: bool = False,
        extra: tuple[str, ...] = (),
    ) -> list[str]:
        if self.name == "bash":
            command = [self.executable]
            if os.name == "nt":
                command.append("--login")
            command.extend(
                [
                    "scripts/install-skills.sh",
                    "--agent",
                    "codex",
                    "--scope",
                    "project",
                    "--project-root",
                    os.path.relpath(project, repository).replace("\\", "/"),
                ]
            )
            if force:
                command.append("--force")
            command.extend(extra)
            return command

        command = [
            self.executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repository / "scripts" / "install-skills.ps1"),
            "-Agent",
            "codex",
            "-Scope",
            "project",
            "-ProjectRoot",
            str(project),
        ]
        if force:
            command.append("-Force")
        command.extend(extra)
        return command


_bash = find_bash()
_powershell = find_powershell()
INSTALLERS = tuple(
    installer
    for installer in (
        Installer("bash", _bash) if _bash else None,
        Installer("powershell", _powershell) if _powershell else None,
    )
    if installer is not None
)


def write_fixture_repository(root: Path, *, invalid: bool = False) -> None:
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(
        REPOSITORY_ROOT / "scripts" / "install-skills.sh",
        root / "scripts" / "install-skills.sh",
    )
    shutil.copy2(
        REPOSITORY_ROOT / "scripts" / "install-skills.ps1",
        root / "scripts" / "install-skills.ps1",
    )

    for name in ("alpha-skill", "beta-skill"):
        skill = root / "skills" / name
        skill.mkdir(parents=True)
        if not (invalid and name == "beta-skill"):
            (skill / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Fixture.\n---\n\n# {name}\n",
                encoding="utf-8",
            )
        (skill / ".hidden-fixture").write_text(
            f"hidden:{name}\n",
            encoding="utf-8",
        )

    for source_name, copyright_line in (
        ("handoff-gist", "Copyright (c) 2026 Handoff Fixture"),
    ):
        source = root / "third_party" / source_name
        source.mkdir(parents=True)
        (source / "LICENSE").write_text(
            f"MIT License\n\n{copyright_line}\n\nPermission is hereby granted.\n",
            encoding="utf-8",
        )
        (source / "source.json").write_text(
            '{"license":"MIT","source":"https://example.invalid/source"}\n',
            encoding="utf-8",
        )
        (source / "SHA256SUMS").write_text(
            "0" * 64 + "  alpha-skill/SKILL.md\n",
            encoding="utf-8",
        )

    (root / "docs").mkdir()
    (root / "docs" / "host-compatibility.md").write_text(
        "# Host compatibility\n",
        encoding="utf-8",
    )


@unittest.skipUnless(INSTALLERS, "No Bash or PowerShell executable available")
class InstallerSafetyTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        TEMPORARY_ROOT.mkdir(exist_ok=False)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEMPORARY_ROOT, ignore_errors=True)

    def run_installer(
        self,
        installer: Installer,
        repository: Path,
        project: Path,
        *,
        force: bool = False,
        extra: tuple[str, ...] = (),
        fail_after: int | None = None,
        fail_before_backup_after: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        if fail_after is not None:
            environment["SKILLS_INSTALL_TEST_FAIL_AFTER"] = str(fail_after)
        if fail_before_backup_after is not None:
            environment["SKILLS_INSTALL_TEST_FAIL_BEFORE_BACKUP_AFTER"] = str(
                fail_before_backup_after
            )
        return subprocess.run(
            installer.command(
                repository,
                project,
                force=force,
                extra=extra,
            ),
            cwd=repository,
            env=environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_notices_are_preserved_by_both_installers(self) -> None:
        for installer in INSTALLERS:
            with self.subTest(installer=installer.name):
                with tempfile.TemporaryDirectory(
                    dir=TEMPORARY_ROOT
                ) as temporary_directory:
                    project = Path(temporary_directory)
                    result = self.run_installer(
                        installer,
                        REPOSITORY_ROOT,
                        project,
                    )
                    self.assertEqual(
                        0,
                        result.returncode,
                        f"{result.stdout}\n{result.stderr}",
                    )
                    destination = project / ".agents" / "skills"
                    notices = destination / ".third-party-notices"
                    for source_name in ("handoff-gist",):
                        for filename in ("LICENSE", "source.json", "SHA256SUMS"):
                            self.assertEqual(
                                (
                                    REPOSITORY_ROOT
                                    / "third_party"
                                    / source_name
                                    / filename
                                ).read_bytes(),
                                (notices / source_name / filename).read_bytes(),
                            )
                    self.assertEqual(
                        (
                            REPOSITORY_ROOT / "docs" / "host-compatibility.md"
                        ).read_bytes(),
                        (notices / "HOST-COMPATIBILITY.md").read_bytes(),
                    )

    def test_conflict_refusal_and_force_replacement_are_non_merging(self) -> None:
        for installer in INSTALLERS:
            with self.subTest(installer=installer.name):
                with tempfile.TemporaryDirectory(
                    dir=TEMPORARY_ROOT
                ) as temporary_directory:
                    project = Path(temporary_directory)
                    first = self.run_installer(
                        installer,
                        REPOSITORY_ROOT,
                        project,
                    )
                    self.assertEqual(0, first.returncode, first.stderr)

                    destination_skill = (
                        project / ".agents" / "skills" / "handoff"
                    )
                    sentinel = b"user-owned conflicting content\n"
                    (destination_skill / "SKILL.md").write_bytes(sentinel)
                    (destination_skill / "stale-file.txt").write_text(
                        "stale\n",
                        encoding="utf-8",
                    )

                    conflict = self.run_installer(
                        installer,
                        REPOSITORY_ROOT,
                        project,
                    )
                    self.assertNotEqual(0, conflict.returncode)
                    self.assertIn(
                        "conflict",
                        (conflict.stdout + conflict.stderr).lower(),
                    )
                    self.assertEqual(
                        sentinel,
                        (destination_skill / "SKILL.md").read_bytes(),
                    )
                    self.assertTrue((destination_skill / "stale-file.txt").exists())

                    replaced = self.run_installer(
                        installer,
                        REPOSITORY_ROOT,
                        project,
                        force=True,
                    )
                    self.assertEqual(
                        0,
                        replaced.returncode,
                        f"{replaced.stdout}\n{replaced.stderr}",
                    )
                    self.assertEqual(
                        (
                            REPOSITORY_ROOT / "skills" / "handoff" / "SKILL.md"
                        ).read_bytes(),
                        (destination_skill / "SKILL.md").read_bytes(),
                    )
                    self.assertFalse((destination_skill / "stale-file.txt").exists())

    def test_hidden_files_are_copied_and_stale_files_are_removed(self) -> None:
        for installer in INSTALLERS:
            with self.subTest(installer=installer.name):
                with tempfile.TemporaryDirectory(
                    dir=TEMPORARY_ROOT
                ) as temporary_directory:
                    temporary_root = Path(temporary_directory)
                    fixture_repository = temporary_root / "repository"
                    project = temporary_root / "project"
                    fixture_repository.mkdir()
                    project.mkdir()
                    write_fixture_repository(fixture_repository)

                    first = self.run_installer(
                        installer,
                        fixture_repository,
                        project,
                    )
                    self.assertEqual(0, first.returncode, first.stderr)
                    installed = (
                        project / ".agents" / "skills" / "alpha-skill"
                    )
                    self.assertEqual(
                        (
                            fixture_repository
                            / "skills"
                            / "alpha-skill"
                            / ".hidden-fixture"
                        ).read_bytes(),
                        (installed / ".hidden-fixture").read_bytes(),
                    )
                    (installed / "stale").write_text("old\n", encoding="utf-8")

                    replaced = self.run_installer(
                        installer,
                        fixture_repository,
                        project,
                        force=True,
                    )
                    self.assertEqual(0, replaced.returncode, replaced.stderr)
                    self.assertFalse((installed / "stale").exists())
                    self.assertEqual(
                        (
                            fixture_repository
                            / "skills"
                            / "alpha-skill"
                            / ".hidden-fixture"
                        ).read_bytes(),
                        (installed / ".hidden-fixture").read_bytes(),
                    )

    def test_injected_install_error_rolls_back_every_target(self) -> None:
        for installer in INSTALLERS:
            with self.subTest(installer=installer.name):
                with tempfile.TemporaryDirectory(
                    dir=TEMPORARY_ROOT
                ) as temporary_directory:
                    temporary_root = Path(temporary_directory)
                    fixture_repository = temporary_root / "repository"
                    project = temporary_root / "project"
                    fixture_repository.mkdir()
                    project.mkdir()
                    write_fixture_repository(fixture_repository)

                    destination = project / ".agents" / "skills"
                    for name in ("alpha-skill", "beta-skill"):
                        existing = destination / name
                        existing.mkdir(parents=True)
                        (existing / "original.txt").write_text(
                            f"original:{name}\n",
                            encoding="utf-8",
                        )

                    result = self.run_installer(
                        installer,
                        fixture_repository,
                        project,
                        force=True,
                        fail_after=1,
                    )
                    self.assertNotEqual(0, result.returncode)
                    for name in ("alpha-skill", "beta-skill"):
                        existing = destination / name
                        self.assertEqual(
                            f"original:{name}\n",
                            (existing / "original.txt").read_text(encoding="utf-8"),
                        )
                        self.assertFalse((existing / "SKILL.md").exists())

                    parent = destination.parent
                    leftovers = [
                        path.name
                        for path in parent.iterdir()
                        if path.name.startswith(".skills-install-")
                    ]
                    self.assertEqual([], leftovers)

    def test_backup_failure_does_not_delete_original_target(self) -> None:
        for installer in INSTALLERS:
            with self.subTest(installer=installer.name):
                with tempfile.TemporaryDirectory(
                    dir=TEMPORARY_ROOT
                ) as temporary_directory:
                    temporary_root = Path(temporary_directory)
                    fixture_repository = temporary_root / "repository"
                    project = temporary_root / "project"
                    fixture_repository.mkdir()
                    project.mkdir()
                    write_fixture_repository(fixture_repository)

                    existing = (
                        project / ".agents" / "skills" / "alpha-skill"
                    )
                    existing.mkdir(parents=True)
                    (existing / "original.txt").write_text(
                        "original\n",
                        encoding="utf-8",
                    )

                    result = self.run_installer(
                        installer,
                        fixture_repository,
                        project,
                        force=True,
                        fail_before_backup_after=1,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual(
                        "original\n",
                        (existing / "original.txt").read_text(encoding="utf-8"),
                    )
                    self.assertFalse((existing / "SKILL.md").exists())

    def test_invalid_source_fails_before_replacing_existing_skills(self) -> None:
        for installer in INSTALLERS:
            with self.subTest(installer=installer.name):
                with tempfile.TemporaryDirectory(
                    dir=TEMPORARY_ROOT
                ) as temporary_directory:
                    temporary_root = Path(temporary_directory)
                    fixture_repository = temporary_root / "repository"
                    project = temporary_root / "project"
                    fixture_repository.mkdir()
                    project.mkdir()
                    write_fixture_repository(fixture_repository, invalid=True)

                    existing = (
                        project / ".agents" / "skills" / "alpha-skill"
                    )
                    existing.mkdir(parents=True)
                    (existing / "original.txt").write_text(
                        "original\n",
                        encoding="utf-8",
                    )

                    result = self.run_installer(
                        installer,
                        fixture_repository,
                        project,
                        force=True,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual(
                        "original\n",
                        (existing / "original.txt").read_text(encoding="utf-8"),
                    )

    def test_bash_missing_option_values_are_explicit(self) -> None:
        bash_installers = [
            installer for installer in INSTALLERS if installer.name == "bash"
        ]
        if not bash_installers:
            self.skipTest("Bash is unavailable")

        installer = bash_installers[0]
        for option in ("--agent", "--scope", "--project-root"):
            with self.subTest(option=option):
                result = subprocess.run(
                    (
                        [installer.executable, "--login"]
                        if os.name == "nt"
                        else [installer.executable]
                    )
                    + [
                        "scripts/install-skills.sh",
                        option,
                    ],
                    cwd=REPOSITORY_ROOT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(2, result.returncode)
                self.assertIn(
                    f"Missing value for {option}",
                    result.stdout + result.stderr,
                )


if __name__ == "__main__":
    unittest.main()
