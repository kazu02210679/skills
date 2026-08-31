#!/usr/bin/env python3
"""Render project-map JSON into an interactive HTML file."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import pathlib
import sys
from typing import Any
from urllib.parse import quote


TOKENS = {
    "title": "{{PROJECT_TITLE}}",
    "summary": "{{PROJECT_SUMMARY}}",
    "data": "{{DATA_FILENAME}}",
    "data_text": "{{DATA_FILENAME_TEXT}}",
    "data_url": "{{DATA_FILENAME_URL}}",
    "data_js": "{{DATA_FILENAME_JS}}",
}


def render_html(
    document: dict[str, Any],
    template: str,
    data_filename: str,
) -> str:
    """Render escaped project metadata and a relative JSON path into the template."""
    project = document.get("project", {})
    data_text = html.escape(data_filename)
    data_url = html.escape(quote(data_filename, safe="/"), quote=True)
    data_js = _javascript_string_literal(quote(data_filename, safe="/"))
    replacements = {
        TOKENS["title"]: html.escape(str(project.get("title", "Project Map"))),
        TOKENS["summary"]: html.escape(str(project.get("summary", ""))),
        TOKENS["data"]: data_text,
        TOKENS["data_text"]: data_text,
        TOKENS["data_url"]: data_url,
        TOKENS["data_js"]: data_js,
    }
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    return rendered


def _javascript_string_literal(value: str) -> str:
    literal = json.dumps(value, ensure_ascii=False)
    for character, replacement in (
        ("<", r"\u003C"),
        (">", r"\u003E"),
        ("&", r"\u0026"),
        ("\u2028", r"\u2028"),
        ("\u2029", r"\u2029"),
    ):
        literal = literal.replace(character, replacement)
    return literal


def relative_data_filename(data_path: pathlib.Path, output_path: pathlib.Path) -> str:
    relative = pathlib.Path(
        os.path.relpath(data_path.resolve(), output_path.parent.resolve())
    )
    return relative.as_posix()


def _load_validator(script_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("project_map_validator", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load validator: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=pathlib.Path)
    parser.add_argument("--template", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)

    try:
        document = json.loads(args.data.read_text(encoding="utf-8"))
        template = args.template.read_text(encoding="utf-8")
        validator = _load_validator(
            pathlib.Path(__file__).with_name("validate_project_map.py")
        )
        errors = validator.validate_document(document)
        if errors:
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        data_filename = relative_data_filename(args.data, args.output)
        rendered = render_html(document, template, data_filename)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Unable to build project map: {exc}", file=sys.stderr)
        return 1

    print(f"Project map HTML written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
