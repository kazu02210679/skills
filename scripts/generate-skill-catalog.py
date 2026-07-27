#!/usr/bin/env python3
"""Generate the README Skill catalog from skills/*/SKILL.md frontmatter."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


BEGIN_MARKER = "<!-- BEGIN SKILL CATALOG -->"
END_MARKER = "<!-- END SKILL CATALOG -->"


def read_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if match is None:
        raise ValueError(f"{path}: missing YAML frontmatter")
    document = yaml.safe_load(match.group(1))
    if not isinstance(document, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return document


def skill_records(repository_root: Path) -> list[tuple[str, str]]:
    skills_root = repository_root / "skills"
    records: list[tuple[str, str]] = []
    for skill_directory in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_path = skill_directory / "SKILL.md"
        if not skill_path.is_file():
            raise ValueError(f"{skill_directory}: missing SKILL.md")
        frontmatter = read_frontmatter(skill_path)
        name = frontmatter.get("name")
        description = frontmatter.get("description")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{skill_path}: missing non-empty name")
        if name != skill_directory.name:
            raise ValueError(
                f"{skill_path}: name {name!r} does not match directory "
                f"{skill_directory.name!r}"
            )
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{skill_path}: missing non-empty description")
        records.append((name, " ".join(description.split())))
    return records


def render_catalog(repository_root: Path) -> str:
    rows = [
        "| Skill | 説明 |",
        "|---|---|",
    ]
    for name, description in skill_records(repository_root):
        safe_description = description.replace("|", "\\|")
        rows.append(
            f"| [`{name}`](skills/{name}/README.md) | {safe_description} |"
        )
    return "\n".join(rows)


def replace_catalog(readme: str, catalog: str) -> str:
    if readme.count(BEGIN_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError("README must contain exactly one Skill catalog marker pair")
    begin = readme.index(BEGIN_MARKER) + len(BEGIN_MARKER)
    end = readme.index(END_MARKER)
    if begin > end:
        raise ValueError("README Skill catalog markers are reversed")
    return f"{readme[:begin]}\n{catalog}\n{readme[end:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when README.md does not match the generated catalog",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print the generated table without changing README.md",
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parent.parent
    readme_path = repository_root / "README.md"
    try:
        catalog = render_catalog(repository_root)
        if args.stdout:
            print(catalog)
            return 0
        current = readme_path.read_text(encoding="utf-8")
        updated = replace_catalog(current, catalog)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if current != updated:
            print(
                "README Skill catalog is stale. "
                "Run python scripts/generate-skill-catalog.py.",
                file=sys.stderr,
            )
            return 1
        print("README Skill catalog is current.")
        return 0

    if current != updated:
        readme_path.write_text(updated, encoding="utf-8", newline="\n")
        print(f"Updated {readme_path}.")
    else:
        print("README Skill catalog is already current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
