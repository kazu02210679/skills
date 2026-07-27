#!/usr/bin/env python3
"""Strictly validate the portable Skill catalog and vendored snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MANIFEST_PATTERN = re.compile(
    r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._/-]*)$"
)
CUSTOM_SKILLS = {
    "complexity-aware-execution",
    "handoff",
    "open-pull-request",
    "writing-style",
}
FRONTMATTER_KEYS = {"name", "description"}
OPENAI_TOP_LEVEL_KEYS = {"interface", "dependencies", "policy"}
OPENAI_INTERFACE_KEYS = {
    "display_name",
    "short_description",
    "icon_small",
    "icon_large",
    "brand_color",
    "default_prompt",
}
OPENAI_REQUIRED_INTERFACE_KEYS = {
    "display_name",
    "short_description",
    "default_prompt",
}
OPENAI_DEPENDENCY_KEYS = {"tools"}
OPENAI_TOOL_KEYS = {
    "type",
    "value",
    "description",
    "transport",
    "url",
}
OPENAI_POLICY_KEYS = {"allow_implicit_invocation"}


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    if not isinstance(node, MappingNode):
        raise ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node.id}",
            node.start_mark,
        )
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate YAML key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_unique_yaml(text: str) -> Any:
    return yaml.load(text, Loader=UniqueKeyLoader)


def _yaml_error_message(error: yaml.YAMLError) -> str:
    for line in str(error).splitlines():
        if "duplicate YAML key" in line:
            return line.strip()
    return str(error).splitlines()[0]


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """Parse strict YAML frontmatter and return it with the Markdown body."""

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening YAML delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing YAML delimiter") from exc

    frontmatter_text = "\n".join(lines[1:end])
    try:
        fields = _load_unique_yaml(frontmatter_text)
    except yaml.YAMLError as exc:
        message = _yaml_error_message(exc)
        raise ValueError(f"invalid YAML: {message}") from exc
    if not isinstance(fields, dict):
        raise ValueError("frontmatter must be a mapping")

    body = "\n".join(lines[end + 1 :]).strip()
    return fields, body


def _validate_nonempty_string(
    value: Any,
    field: str,
    errors: list[str],
    *,
    maximum: int | None = None,
) -> str | None:
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")
        return None
    if not value.strip():
        errors.append(f"{field} must not be empty")
        return None
    if maximum is not None and len(value) > maximum:
        errors.append(f"{field} exceeds {maximum} characters")
    return value


def _validate_openai_yaml(path: Path, skill_name: str) -> list[str]:
    errors: list[str] = []
    try:
        document = _load_unique_yaml(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        message = (
            _yaml_error_message(exc)
            if isinstance(exc, yaml.YAMLError)
            else str(exc)
        )
        return [f"agents/openai.yaml invalid YAML: {message}"]

    if not isinstance(document, dict):
        return ["agents/openai.yaml must be a mapping"]
    for key in document:
        if key not in OPENAI_TOP_LEVEL_KEYS:
            errors.append(f"agents/openai.yaml unknown top-level key {key!r}")

    interface = document.get("interface")
    if not isinstance(interface, dict):
        errors.append("interface must be a mapping")
    else:
        for key in interface:
            if key not in OPENAI_INTERFACE_KEYS:
                errors.append(f"unknown interface key {key!r}")
        for key in sorted(OPENAI_REQUIRED_INTERFACE_KEYS):
            if key not in interface:
                errors.append(f"interface is missing required key {key!r}")
            else:
                _validate_nonempty_string(
                    interface[key],
                    f"interface.{key}",
                    errors,
                )
        for key in ("icon_small", "icon_large", "brand_color"):
            if key in interface:
                _validate_nonempty_string(
                    interface[key],
                    f"interface.{key}",
                    errors,
                )
        default_prompt = interface.get("default_prompt")
        if isinstance(default_prompt, str) and f"${skill_name}" not in default_prompt:
            errors.append(
                f"default_prompt must mention '${skill_name}'"
            )
        short_description = interface.get("short_description")
        if isinstance(short_description, str) and not (
            25 <= len(short_description) <= 64
        ):
            errors.append(
                "interface.short_description must be 25 to 64 characters"
            )
        brand_color = interface.get("brand_color")
        if isinstance(brand_color, str) and not re.fullmatch(
            r"#[0-9A-Fa-f]{6}",
            brand_color,
        ):
            errors.append("interface.brand_color must be a six-digit hex color")

    dependencies = document.get("dependencies")
    if dependencies is not None:
        if not isinstance(dependencies, dict):
            errors.append("dependencies must be a mapping")
        else:
            for key in dependencies:
                if key not in OPENAI_DEPENDENCY_KEYS:
                    errors.append(f"unknown dependencies key {key!r}")
            tools = dependencies.get("tools")
            if tools is not None:
                if not isinstance(tools, list):
                    errors.append("dependencies.tools must be a list")
                else:
                    for index, tool in enumerate(tools):
                        prefix = f"dependencies.tools[{index}]"
                        if not isinstance(tool, dict):
                            errors.append(f"{prefix} must be a mapping")
                            continue
                        for key in tool:
                            if key not in OPENAI_TOOL_KEYS:
                                errors.append(
                                    f"{prefix} unknown key {key!r}"
                                )
                        for key in ("type", "value"):
                            if key not in tool:
                                errors.append(
                                    f"{prefix} is missing required key {key!r}"
                                )
                            else:
                                _validate_nonempty_string(
                                    tool[key],
                                    f"{prefix}.{key}",
                                    errors,
                                )
                        if tool.get("type") != "mcp":
                            errors.append(f"{prefix}.type must be 'mcp'")
                        for key in ("description", "transport", "url"):
                            if key in tool:
                                _validate_nonempty_string(
                                    tool[key],
                                    f"{prefix}.{key}",
                                    errors,
                                )

    policy = document.get("policy")
    if policy is not None:
        if not isinstance(policy, dict):
            errors.append("policy must be a mapping")
        else:
            for key in policy:
                if key not in OPENAI_POLICY_KEYS:
                    errors.append(f"unknown policy key {key!r}")
            implicit = policy.get("allow_implicit_invocation")
            if implicit is not None and not isinstance(implicit, bool):
                errors.append(
                    "policy.allow_implicit_invocation must be a boolean"
                )

    return errors


def validate_skill_directory(skill_directory: Path) -> list[str]:
    """Validate one Skill directory and return unprefixed errors."""

    errors: list[str] = []
    skill_file = skill_directory / "SKILL.md"
    if not skill_file.is_file():
        return ["missing SKILL.md"]

    try:
        fields, body = parse_frontmatter(skill_file)
    except (UnicodeDecodeError, ValueError) as exc:
        return [str(exc)]

    for key in fields:
        if key not in FRONTMATTER_KEYS:
            errors.append(f"unknown frontmatter key {key!r}")
    for required in sorted(FRONTMATTER_KEYS):
        if required not in fields:
            errors.append(f"missing {required}")

    name = fields.get("name")
    parsed_name = _validate_nonempty_string(
        name,
        "name",
        errors,
        maximum=64,
    )
    if parsed_name:
        if not NAME_PATTERN.fullmatch(parsed_name):
            errors.append(f"invalid name {parsed_name!r}")
        if parsed_name != skill_directory.name:
            errors.append(
                f"frontmatter name is {parsed_name!r}, "
                f"directory is {skill_directory.name!r}"
            )

    description = fields.get("description")
    parsed_description = _validate_nonempty_string(
        description,
        "description",
        errors,
        maximum=1024,
    )
    if parsed_description and (
        "<" in parsed_description or ">" in parsed_description
    ):
        errors.append("description must not contain angle brackets")

    if not body:
        errors.append("empty body")

    openai_yaml = skill_directory / "agents" / "openai.yaml"
    if openai_yaml.exists():
        if not openai_yaml.is_file():
            errors.append("agents/openai.yaml is not a file")
        elif parsed_name:
            errors.extend(_validate_openai_yaml(openai_yaml, parsed_name))

    return errors


def _read_source_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path.as_posix()}: invalid JSON: {exc}")
        return {}
    if not isinstance(document, dict):
        errors.append(f"{path.as_posix()}: source record must be an object")
        return {}
    return document


def _validate_manifest(
    repository_root: Path,
    source_name: str,
    expected_paths: set[str],
    errors: list[str],
) -> None:
    manifest_path = (
        repository_root / "third_party" / source_name / "SHA256SUMS"
    )
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"missing or unreadable {manifest_path.as_posix()}: {exc}")
        return

    entries: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        match = MANIFEST_PATTERN.fullmatch(line)
        if not match:
            errors.append(
                f"{manifest_path.as_posix()}:{line_number}: "
                "invalid SHA256SUMS entry"
            )
            continue
        digest, relative_path = match.groups()
        path_parts = Path(relative_path).parts
        if ".." in path_parts or Path(relative_path).is_absolute():
            errors.append(
                f"{manifest_path.as_posix()}:{line_number}: unsafe path"
            )
            continue
        if relative_path in entries:
            errors.append(
                f"{manifest_path.as_posix()}:{line_number}: duplicate path "
                f"{relative_path!r}"
            )
            continue
        entries[relative_path] = digest

    if set(entries) != expected_paths:
        missing = sorted(expected_paths - set(entries))
        extra = sorted(set(entries) - expected_paths)
        errors.append(
            f"{source_name} SHA256SUMS paths do not match the vendored set "
            f"(missing={missing}, extra={extra})"
        )

    for relative_path, expected_digest in entries.items():
        file_path = repository_root / "skills" / relative_path
        if not file_path.is_file():
            continue
        actual_digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            errors.append(
                f"{relative_path}: SHA-256 mismatch "
                f"(expected {expected_digest}, got {actual_digest})"
            )


def validate_repository(repository_root: Path) -> list[str]:
    """Validate all Skill files, catalog counts, and provenance snapshots."""

    errors: list[str] = []
    skills_root = repository_root / "skills"
    if not skills_root.is_dir():
        return [f"skills directory not found: {skills_root}"]

    skill_directories = sorted(
        path for path in skills_root.iterdir() if path.is_dir()
    )
    seen_names: dict[str, Path] = {}
    for skill_directory in skill_directories:
        for error in validate_skill_directory(skill_directory):
            errors.append(f"{skill_directory.name}: {error}")
        try:
            fields, _ = parse_frontmatter(skill_directory / "SKILL.md")
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        name = fields.get("name")
        if isinstance(name, str) and name:
            if name in seen_names:
                errors.append(
                    f"{skill_directory.name}: duplicate name also used by "
                    f"{seen_names[name]}"
                )
            else:
                seen_names[name] = skill_directory / "SKILL.md"

    skill_names = {path.name for path in skill_directories}
    pm_skill_names = skill_names - CUSTOM_SKILLS
    if len(skill_names) != 72:
        errors.append(f"expected 72 skills, found {len(skill_names)}")
    if not CUSTOM_SKILLS <= skill_names:
        errors.append(
            f"missing custom Skills: {sorted(CUSTOM_SKILLS - skill_names)}"
        )
    if len(pm_skill_names) != 68:
        errors.append(f"expected 68 PM Skills, found {len(pm_skill_names)}")

    readme_path = repository_root / "README.md"
    try:
        readme = readme_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"README catalog count cannot be verified: {exc}")
    else:
        if "次の72個" not in readme or "68 Skill" not in readme:
            errors.append(
                "README catalog count must state 72 total and 68 PM Skills"
            )

    for source_name in ("pm-skills", "handoff-gist"):
        source_path = (
            repository_root / "third_party" / source_name / "source.json"
        )
        source = _read_source_json(source_path, errors)
        if source.get("license") != "MIT":
            errors.append(f"{source_name} source record license must be MIT")
        if source.get("sha256_manifest") != "SHA256SUMS":
            errors.append(
                f"{source_name} source record must name SHA256SUMS"
            )
        license_path = repository_root / "third_party" / source_name / "LICENSE"
        if not license_path.is_file():
            errors.append(f"{source_name}: missing LICENSE")

    pm_source = _read_source_json(
        repository_root / "third_party" / "pm-skills" / "source.json",
        [],
    )
    if pm_source.get("imported_skill_count") != 68:
        errors.append("pm-skills imported_skill_count must be 68")

    _validate_manifest(
        repository_root,
        "pm-skills",
        {f"{name}/SKILL.md" for name in pm_skill_names},
        errors,
    )
    _validate_manifest(
        repository_root,
        "handoff-gist",
        {"handoff/SKILL.md"},
        errors,
    )
    return errors


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent
    errors = validate_repository(repository_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"Validation failed with {len(errors)} error(s).",
            file=sys.stderr,
        )
        return 1
    skill_count = len(
        [path for path in (repository_root / "skills").iterdir() if path.is_dir()]
    )
    print(f"Validated {skill_count} skills.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
