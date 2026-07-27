#!/usr/bin/env python3
"""Validate project-map JSON and rendered HTML."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from typing import Any


REQUIRED_TOP_LEVEL = (
    "project",
    "sources",
    "categories",
    "nodes",
    "edges",
    "flows",
    "phases",
)
ALLOWED_STATUSES = {"planned", "implemented", "deprecated"}
HTML_MARKERS = (
    'id="cy"',
    'id="flowNav"',
    'id="nodeSearch"',
    'id="fitButton"',
    "cytoscape",
)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _ids(items: Any, label: str, errors: list[str]) -> set[str]:
    values: set[str] = set()
    if not isinstance(items, list):
        errors.append(f"{label} must be an array")
        return values
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            errors.append(f"{label}[{index}].id must be a non-empty string")
        elif item_id in values:
            errors.append(f"{label} contains duplicate id '{item_id}'")
        else:
            values.add(item_id)
    return values


def _require_reference(
    value: Any,
    allowed: set[str],
    location: str,
    errors: list[str],
) -> None:
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"{location} references unknown id '{value}'")


def _has_evidence(item: dict[str, Any]) -> bool:
    evidence = item.get("evidence")
    gap = item.get("coverageGap")
    return bool(_list(evidence)) or (isinstance(gap, str) and bool(gap.strip()))


def validate_document(document: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors for a project-map document."""
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["document must be an object"]

    for key in REQUIRED_TOP_LEVEL:
        if key not in document:
            errors.append(f"missing top-level key '{key}'")

    project = document.get("project")
    if not isinstance(project, dict):
        errors.append("project must be an object")
    else:
        for key in ("id", "title", "summary"):
            if not isinstance(project.get(key), str) or not project[key].strip():
                errors.append(f"project.{key} must be a non-empty string")

    category_ids = _ids(document.get("categories"), "categories", errors)
    phase_ids = _ids(document.get("phases"), "phases", errors)
    node_ids = _ids(document.get("nodes"), "nodes", errors)
    edge_ids = _ids(document.get("edges"), "edges", errors)
    _ids(document.get("flows"), "flows", errors)

    for index, node in enumerate(_list(document.get("nodes"))):
        if not isinstance(node, dict):
            continue
        location = f"nodes[{index}]"
        _require_reference(node.get("category"), category_ids, f"{location}.category", errors)
        _require_reference(node.get("phase"), phase_ids, f"{location}.phase", errors)
        if node.get("status") not in ALLOWED_STATUSES:
            errors.append(
                f"{location}.status must be one of {sorted(ALLOWED_STATUSES)}"
            )
        position = node.get("position")
        if not isinstance(position, dict):
            errors.append(f"{location}.position must be an object")
        else:
            for axis in ("x", "y"):
                value = position.get(axis)
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                ):
                    errors.append(f"{location}.position.{axis} must be finite")
        if not _has_evidence(node):
            errors.append(f"{location} needs evidence or an explicit coverageGap")

    for index, edge in enumerate(_list(document.get("edges"))):
        if not isinstance(edge, dict):
            continue
        location = f"edges[{index}]"
        _require_reference(edge.get("source"), node_ids, f"{location}.source", errors)
        _require_reference(edge.get("target"), node_ids, f"{location}.target", errors)

    for index, flow in enumerate(_list(document.get("flows"))):
        if not isinstance(flow, dict):
            continue
        location = f"flows[{index}]"
        for node_id in _list(flow.get("nodeIds")):
            _require_reference(node_id, node_ids, f"{location}.nodeIds", errors)
        for edge_id in _list(flow.get("edgeIds")):
            _require_reference(edge_id, edge_ids, f"{location}.edgeIds", errors)
        for stage_index, stage in enumerate(_list(flow.get("stages"))):
            if not isinstance(stage, dict):
                errors.append(f"{location}.stages[{stage_index}] must be an object")
                continue
            for node_id in _list(stage.get("nodeIds")):
                _require_reference(
                    node_id,
                    node_ids,
                    f"{location}.stages[{stage_index}].nodeIds",
                    errors,
                )
        if not _has_evidence(flow):
            errors.append(f"{location} needs evidence or an explicit coverageGap")

    return errors


def validate_html(text: str) -> list[str]:
    """Return errors for missing runtime hooks in rendered HTML."""
    return [f"HTML is missing required marker: {marker}" for marker in HTML_MARKERS if marker not in text]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=pathlib.Path)
    parser.add_argument("--html", dest="html_path", type=pathlib.Path)
    args = parser.parse_args(argv)

    try:
        document = json.loads(args.json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Unable to read project map: {exc}", file=sys.stderr)
        return 1

    errors = validate_document(document)
    if args.html_path:
        try:
            errors.extend(validate_html(args.html_path.read_text(encoding="utf-8")))
        except OSError as exc:
            errors.append(f"Unable to read HTML: {exc}")

    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Project map is valid: "
        f"{len(document['nodes'])} nodes, "
        f"{len(document['edges'])} edges, "
        f"{len(document['flows'])} flows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
