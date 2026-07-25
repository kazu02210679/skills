#!/usr/bin/env python3
"""Validate the repository's portable SKILL.md catalog."""

from __future__ import annotations

import re
import sys
from pathlib import Path


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD_PATTERN = re.compile(r"^(name|description):\s*(.+?)\s*$")


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not lines or lines[0] != "---":
        raise ValueError("missing opening YAML delimiter")

    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing YAML delimiter") from exc

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        match = FIELD_PATTERN.match(line)
        if match:
            fields[match.group(1)] = match.group(2).strip("\"'")

    body = "\n".join(lines[end + 1 :]).strip()
    return fields, body


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent
    skills_root = repository_root / "skills"
    errors: list[str] = []
    seen_names: dict[str, Path] = {}

    if not skills_root.is_dir():
        print(f"ERROR: skills directory not found: {skills_root}", file=sys.stderr)
        return 1

    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())

    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{skill_dir.name}: missing SKILL.md")
            continue

        try:
            fields, body = parse_frontmatter(skill_file)
        except (UnicodeDecodeError, ValueError) as exc:
            errors.append(f"{skill_dir.name}: {exc}")
            continue

        name = fields.get("name", "")
        description = fields.get("description", "")

        if not name:
            errors.append(f"{skill_dir.name}: missing name")
        elif not NAME_PATTERN.fullmatch(name):
            errors.append(f"{skill_dir.name}: invalid name {name!r}")
        elif name != skill_dir.name:
            errors.append(f"{skill_dir.name}: frontmatter name is {name!r}")

        if name in seen_names:
            errors.append(
                f"{skill_dir.name}: duplicate name also used by {seen_names[name]}"
            )
        elif name:
            seen_names[name] = skill_file

        if not description:
            errors.append(f"{skill_dir.name}: missing description")
        if not body:
            errors.append(f"{skill_dir.name}: empty body")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Validation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    print(f"Validated {len(skill_dirs)} skills.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
