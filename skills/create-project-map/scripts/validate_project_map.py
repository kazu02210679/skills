#!/usr/bin/env python3
"""Validate project-map JSON and rendered HTML."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
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
SCHEMA_VERSIONS = {1, 2}
NODE_KINDS = {
    "service",
    "ui",
    "worker",
    "data",
    "external",
    "contract",
    "decision",
    "actor",
}
EDGE_KINDS = {
    "calls",
    "data",
    "event",
    "contains",
    "inherits",
    "depends-on",
    "replaces",
    "unknown",
}
CHANGE_TYPES = {"existing", "inherited", "changed", "added", "replaced", "removed"}
SNAPSHOT_KINDS = {"version", "baseline", "release", "working"}
MODES = {"flow", "dependency", "combined"}
V2_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
CHANGE_STATES = ("existing", "inherited", "changed", "added", "replaced", "removed")
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


def document_schema_version(document: dict[str, Any], errors: list[str]) -> int:
    value = document.get("schemaVersion", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value not in SCHEMA_VERSIONS:
        errors.append("schemaVersion must be integer 1 or 2")
        return 1
    return value


def _record_map(items: Any) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        return records
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            records.setdefault(item["id"], item)
    return records


def _validate_v2_snapshots(
    document: dict[str, Any], errors: list[str]
) -> set[str]:
    if "snapshots" not in document:
        return set()
    raw_snapshots = document["snapshots"]
    if not isinstance(raw_snapshots, list):
        errors.append("snapshots must be an array")
        return set()

    snapshot_ids: set[str] = set()
    parents: dict[str, Any] = {}
    for index, snapshot in enumerate(raw_snapshots):
        location = f"snapshots[{index}]"
        if not isinstance(snapshot, dict):
            errors.append(f"{location} must be an object")
            continue

        snapshot_id = snapshot.get("id")
        valid_id = isinstance(snapshot_id, str) and bool(snapshot_id.strip())
        if not valid_id:
            errors.append(f"{location}.id must be a non-empty string")
        elif snapshot_id in snapshot_ids:
            errors.append(f"snapshots contains duplicate id '{snapshot_id}'")
        else:
            snapshot_ids.add(snapshot_id)

        label = snapshot.get("label")
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{location}.label must be a non-empty string")

        kind = snapshot.get("kind")
        if not isinstance(kind, str) or kind not in SNAPSHOT_KINDS:
            errors.append(
                f"{location}.kind must be one of {sorted(SNAPSHOT_KINDS)}"
            )

        if "parentId" not in snapshot:
            errors.append(f"{location}.parentId must be null or a known snapshot id")
            parent = None
        else:
            parent = snapshot["parentId"]
            if parent is not None and (
                not isinstance(parent, str) or not parent.strip()
            ):
                errors.append(
                    f"{location}.parentId must be null or a known snapshot id"
                )
        if valid_id:
            parents[snapshot_id] = parent

    for snapshot_id, parent in parents.items():
        if isinstance(parent, str) and parent not in snapshot_ids:
            errors.append(
                f"snapshots[{snapshot_id}].parentId references unknown snapshot '{parent}'"
            )

    visit_state: dict[str, int] = {}

    def visit(snapshot_id: str) -> None:
        state = visit_state.get(snapshot_id, 0)
        if state == 1:
            errors.append(f"snapshots parent cycle detected at '{snapshot_id}'")
            return
        if state == 2:
            return
        visit_state[snapshot_id] = 1
        parent = parents.get(snapshot_id)
        if isinstance(parent, str) and parent in snapshot_ids:
            visit(parent)
        visit_state[snapshot_id] = 2

    for snapshot_id in snapshot_ids:
        visit(snapshot_id)

    return snapshot_ids


def _validate_v2_annotations(
    items: Any,
    label: str,
    allowed_ids: set[str],
    all_ids: set[str],
    snapshot_ids: set[str],
    errors: list[str],
    kind_values: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    records = _record_map(items)
    if not isinstance(items, list):
        return records

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        location = f"{label}[{index}]"
        item_id = item.get("id")

        if kind_values is not None and "kind" in item:
            kind = item["kind"]
            if not isinstance(kind, str) or kind not in kind_values:
                errors.append(
                    f"{location}.kind must be one of {sorted(kind_values)}"
                )

        if "changeType" in item:
            change_type = item["changeType"]
            if not isinstance(change_type, str) or change_type not in CHANGE_TYPES:
                errors.append(
                    f"{location}.changeType must be one of {sorted(CHANGE_TYPES)}"
                )
        else:
            change_type = None

        if "snapshotIds" in item:
            item_snapshots = item["snapshotIds"]
            if not isinstance(item_snapshots, list):
                errors.append(f"{location}.snapshotIds must be an array")
            else:
                seen_snapshots: set[str] = set()
                for snapshot_index, snapshot_id in enumerate(item_snapshots):
                    if not isinstance(snapshot_id, str) or snapshot_id not in snapshot_ids:
                        errors.append(
                            f"{location}.snapshotIds[{snapshot_index}] references unknown snapshot '{snapshot_id}'"
                        )
                    elif snapshot_id in seen_snapshots:
                        errors.append(
                            f"{location}.snapshotIds contains duplicate snapshot '{snapshot_id}'"
                        )
                    else:
                        seen_snapshots.add(snapshot_id)

        if "replacesId" in item:
            replacement_id = item["replacesId"]
            if change_type != "replaced":
                errors.append(
                    f"{location}.replacesId is forbidden unless changeType is 'replaced'"
                )
            elif not isinstance(replacement_id, str) or not replacement_id.strip():
                errors.append(f"{location}.replacesId must be a non-empty string")
            elif replacement_id not in allowed_ids:
                if replacement_id in all_ids:
                    errors.append(
                        f"{location}.replacesId must reference the same collection"
                    )
                else:
                    errors.append(
                        f"{location}.replacesId references unknown id '{replacement_id}'"
                    )
        elif change_type == "replaced":
            errors.append(
                f"{location}.replacesId is required when changeType is 'replaced'"
            )

        if label == "nodes" and item.get("changeType") == "removed":
            if item.get("status") != "deprecated":
                errors.append(
                    f"{location}.status must be 'deprecated' for a removed node"
                )

    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("changeType") != "replaced":
            continue
        replacement_id = item.get("replacesId")
        if not isinstance(replacement_id, str) or replacement_id not in records:
            continue
        target = records[replacement_id]
        if target.get("changeType") != "removed":
            errors.append(
                f"{label}[{index}].replacesId target '{replacement_id}' must have changeType 'removed'"
            )
        if label == "nodes" and target.get("status") != "deprecated":
            errors.append(
                f"{label}[{index}].replacesId target '{replacement_id}' must be deprecated"
            )
    return records


def _validate_v2_comparisons(
    document: dict[str, Any],
    snapshot_ids: set[str],
    collection_records: dict[str, dict[str, dict[str, Any]]],
    collection_ids: dict[str, set[str]],
    errors: list[str],
) -> None:
    if "comparisons" not in document:
        return
    raw_comparisons = document["comparisons"]
    if not isinstance(raw_comparisons, list):
        errors.append("comparisons must be an array")
        return

    comparison_ids: set[str] = set()
    collection_suffixes = {
        "Node": "nodes",
        "Edge": "edges",
        "Flow": "flows",
    }

    for index, comparison in enumerate(raw_comparisons):
        location = f"comparisons[{index}]"
        if not isinstance(comparison, dict):
            errors.append(f"{location} must be an object")
            continue

        comparison_id = comparison.get("id")
        if not isinstance(comparison_id, str) or not comparison_id.strip():
            errors.append(f"{location}.id must be a non-empty string")
        elif comparison_id in comparison_ids:
            errors.append(f"comparisons contains duplicate id '{comparison_id}'")
        else:
            comparison_ids.add(comparison_id)

        from_id = comparison.get("fromSnapshotId")
        to_id = comparison.get("toSnapshotId")
        if not isinstance(from_id, str) or from_id not in snapshot_ids:
            errors.append(
                f"{location}.fromSnapshotId references unknown snapshot '{from_id}'"
            )
        if not isinstance(to_id, str) or to_id not in snapshot_ids:
            errors.append(
                f"{location}.toSnapshotId references unknown snapshot '{to_id}'"
            )
        if isinstance(from_id, str) and isinstance(to_id, str) and from_id == to_id:
            errors.append(f"{location} fromSnapshotId and toSnapshotId must differ")

        if "summary" in comparison and not isinstance(comparison["summary"], str):
            errors.append(f"{location}.summary must be text")

        for collection, suffix in collection_suffixes.items():
            fields = {
                state: f"{state}{collection}Ids" for state in CHANGE_STATES
            }
            seen_ids: dict[str, str] = {}
            values: dict[str, list[Any]] = {}
            for state, field in fields.items():
                if field not in comparison:
                    errors.append(f"{location}.{field} must be an array")
                    values[state] = []
                    continue
                raw_ids = comparison[field]
                if not isinstance(raw_ids, list):
                    errors.append(f"{location}.{field} must be an array")
                    values[state] = []
                    continue
                values[state] = raw_ids
                for item_index, item_id in enumerate(raw_ids):
                    if not isinstance(item_id, str) or item_id not in collection_ids[suffix]:
                        errors.append(
                            f"{location}.{field}[{item_index}] comparison references unknown {suffix[:-1]} id '{item_id}'"
                        )
                        continue
                    prior_state = seen_ids.get(item_id)
                    if prior_state is not None:
                        errors.append(
                            f"{location}.{field} id '{item_id}' appears in at most one comparison state for {suffix} (already {prior_state})"
                        )
                    else:
                        seen_ids[item_id] = state
            replaced_ids = values["replaced"]
            removed_ids = values["removed"]
            removed_set = {
                item_id for item_id in removed_ids if isinstance(item_id, str)
            }
            records = collection_records[suffix]
            for item_id in replaced_ids:
                if not isinstance(item_id, str) or item_id not in records:
                    continue
                replacement = records[item_id]
                if replacement.get("changeType") != "replaced":
                    errors.append(
                        f"{location}.replaced{collection}Ids id '{item_id}' is in the wrong replacement state"
                    )
                    continue
                old_id = replacement.get("replacesId")
                if not isinstance(old_id, str) or old_id not in records:
                    continue
                if old_id not in removed_set:
                    errors.append(
                        f"{location} replacement '{item_id}' requires '{old_id}' in removed{collection}Ids"
                    )
            for item_id in removed_ids:
                if not isinstance(item_id, str) or item_id not in records:
                    continue
                removed = records[item_id]
                if removed.get("changeType") != "removed":
                    errors.append(
                        f"{location}.removed{collection}Ids id '{item_id}' is in the wrong replacement state"
                    )


def _validate_v2_view(
    document: dict[str, Any], flow_ids: set[str], errors: list[str]
) -> None:
    if "view" not in document:
        return
    view = document["view"]
    if not isinstance(view, dict):
        errors.append("view must be an object")
        return

    default_mode = view.get("defaultMode")
    if "defaultMode" in view and (
        not isinstance(default_mode, str) or default_mode not in MODES
    ):
        errors.append(f"view.defaultMode must be one of {sorted(MODES)}")

    if "defaultFlowId" in view:
        default_flow_id = view["defaultFlowId"]
        if not isinstance(default_flow_id, str) or default_flow_id not in flow_ids:
            errors.append(
                f"view.defaultFlowId references unknown flow '{default_flow_id}'"
            )

    if "availableModes" in view:
        raw_modes = view["availableModes"]
        if not isinstance(raw_modes, list) or not raw_modes:
            errors.append("view.availableModes must be a non-empty array")
        else:
            seen_modes: set[str] = set()
            for mode_index, mode in enumerate(raw_modes):
                if not isinstance(mode, str) or mode not in MODES:
                    errors.append(
                        f"view.availableModes[{mode_index}] must be one of {sorted(MODES)}"
                    )
                elif mode in seen_modes:
                    errors.append(
                        f"view.availableModes contains duplicate mode '{mode}'"
                    )
                else:
                    seen_modes.add(mode)
    if "layouts" not in view:
        return
    layouts = view["layouts"]
    if not isinstance(layouts, dict):
        errors.append("view.layouts must be an object")
        return

    expected_layouts = {
        "flow": {"name": "breadthfirst", "direction": "TB", "fit": "bounded"},
        "dependency": {"name": "preset", "fit": "bounded"},
        "combined": {"name": "preset", "fit": "bounded"},
    }
    for layout_name, expected in expected_layouts.items():
        if layout_name not in layouts:
            continue
        layout = layouts[layout_name]
        location = f"view.layouts.{layout_name}"
        if not isinstance(layout, dict):
            errors.append(f"{location} must be an object")
            continue
        for key, expected_value in expected.items():
            if key not in layout:
                continue
            if layout[key] != expected_value:
                term = "direction" if key == "direction" else "layout"
                errors.append(
                    f"{location}.{key} {term} must be '{expected_value}'"
                )


def _validate_v2_flow_edges(
    flows: Any,
    edge_records: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    if not isinstance(flows, list):
        return
    for index, flow in enumerate(flows):
        if not isinstance(flow, dict) or "edgeIds" not in flow:
            continue
        edge_ids = flow["edgeIds"]
        location = f"flows[{index}]"
        if not isinstance(edge_ids, list):
            errors.append(f"{location}.edgeIds must be an array")
            continue
        raw_node_ids = flow.get("nodeIds")
        node_ids = {
            node_id for node_id in _list(raw_node_ids) if isinstance(node_id, str)
        }
        for edge_id in edge_ids:
            if not isinstance(edge_id, str):
                continue
            edge = edge_records.get(edge_id)
            if edge is None:
                continue
            source = edge.get("source")
            target = edge.get("target")
            if (
                not isinstance(source, str)
                or not isinstance(target, str)
                or source not in node_ids
                or target not in node_ids
            ):
                errors.append(
                    f"{location}.edgeIds (flow.edgeIds) edge '{edge_id}' source and target must both occur in flow.nodeIds"
                )


def _validate_v2_colors(document: dict[str, Any], errors: list[str]) -> None:
    categories = document.get("categories")
    if not isinstance(categories, list):
        return
    for index, category in enumerate(categories):
        if not isinstance(category, dict) or "color" not in category:
            continue
        color = category["color"]
        if not isinstance(color, str) or V2_COLOR.fullmatch(color) is None:
            errors.append(
                f"categories[{index}].color must be a #RRGGBB or #RRGGBBAA value"
            )


def _require_v2_string(
    value: Any, location: str, errors: list[str], non_empty: bool = False
) -> bool:
    if not isinstance(value, str) or (non_empty and not value.strip()):
        requirement = "a non-empty string" if non_empty else "a string"
        errors.append(f"{location} must be {requirement}")
        return False
    return True


def _require_v2_string_array(
    value: Any, location: str, errors: list[str]
) -> bool:
    if not isinstance(value, list):
        errors.append(f"{location} must be an array")
        return False
    for index, entry in enumerate(value):
        _require_v2_string(entry, f"{location}[{index}]", errors, non_empty=True)
    return True


def _require_v2_object_array(
    value: Any, location: str, errors: list[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{location} must be an array")
        return []
    objects: list[dict[str, Any]] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            errors.append(f"{location}[{index}] must be an object")
        else:
            objects.append(entry)
    return objects


def _require_v2_references(
    value: Any, location: str, allowed: set[str], errors: list[str]
) -> bool:
    if not _require_v2_string_array(value, location, errors):
        return False
    for index, entry in enumerate(value):
        if isinstance(entry, str) and entry.strip() and entry not in allowed:
            errors.append(
                f"{location}[{index}] references unknown id '{entry}'"
            )
    return True


def _validate_v2_base_fields(
    document: dict[str, Any],
    category_ids: set[str],
    phase_ids: set[str],
    node_ids: set[str],
    edge_ids: set[str],
    errors: list[str],
) -> None:
    sources = _require_v2_object_array(document.get("sources"), "sources", errors)
    for index, source in enumerate(sources):
        location = f"sources[{index}]"
        _require_v2_string(source.get("path"), f"{location}.path", errors, True)
        _require_v2_string(source.get("kind"), f"{location}.kind", errors, True)

    categories = document.get("categories")
    if isinstance(categories, list):
        for index, category in enumerate(categories):
            if not isinstance(category, dict):
                continue
            location = f"categories[{index}]"
            _require_v2_string(category.get("label"), f"{location}.label", errors, True)
            _require_v2_string(category.get("color"), f"{location}.color", errors, True)

    phases = document.get("phases")
    if isinstance(phases, list):
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                continue
            location = f"phases[{index}]"
            _require_v2_string(phase.get("label"), f"{location}.label", errors, True)
            _require_v2_string(phase.get("description"), f"{location}.description", errors)

    nodes = document.get("nodes")
    if isinstance(nodes, list):
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            location = f"nodes[{index}]"
            _require_v2_string(node.get("label"), f"{location}.label", errors, True)
            category_valid = _require_v2_string(
                node.get("category"), f"{location}.category", errors, True
            )
            phase_valid = _require_v2_string(
                node.get("phase"), f"{location}.phase", errors, True
            )
            if category_valid and node.get("category") not in category_ids:
                errors.append(
                    f"{location}.category references unknown id '{node.get('category')}'"
                )
            if phase_valid and node.get("phase") not in phase_ids:
                errors.append(
                    f"{location}.phase references unknown id '{node.get('phase')}'"
                )
            _require_v2_string(node.get("status"), f"{location}.status", errors, True)
            _require_v2_string(node.get("description"), f"{location}.description", errors)
            for key in ("responsibilities", "inputs", "outputs", "sourcePaths"):
                _require_v2_string_array(node.get(key), f"{location}.{key}", errors)
            if "evidence" in node:
                _require_v2_string_array(node["evidence"], f"{location}.evidence", errors)
            if "coverageGap" in node:
                _require_v2_string(node["coverageGap"], f"{location}.coverageGap", errors)

    edges = document.get("edges")
    if isinstance(edges, list):
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            location = f"edges[{index}]"
            source_valid = _require_v2_string(
                edge.get("source"), f"{location}.source", errors, True
            )
            target_valid = _require_v2_string(
                edge.get("target"), f"{location}.target", errors, True
            )
            if source_valid and edge.get("source") not in node_ids:
                errors.append(
                    f"{location}.source references unknown node '{edge.get('source')}'"
                )
            if target_valid and edge.get("target") not in node_ids:
                errors.append(
                    f"{location}.target references unknown node '{edge.get('target')}'"
                )
            _require_v2_string(edge.get("label"), f"{location}.label", errors, True)
            _require_v2_string(edge.get("contract"), f"{location}.contract", errors, True)

    flows = document.get("flows")
    if isinstance(flows, list):
        for index, flow in enumerate(flows):
            if not isinstance(flow, dict):
                continue
            location = f"flows[{index}]"
            _require_v2_string(flow.get("label"), f"{location}.label", errors, True)
            _require_v2_string(flow.get("description"), f"{location}.description", errors)
            _require_v2_string(flow.get("actor"), f"{location}.actor", errors, True)
            _require_v2_string(flow.get("trigger"), f"{location}.trigger", errors, True)
            _require_v2_string(flow.get("outcome"), f"{location}.outcome", errors, True)
            node_refs_valid = _require_v2_references(
                flow.get("nodeIds"), f"{location}.nodeIds", node_ids, errors
            )
            _require_v2_references(
                flow.get("edgeIds"), f"{location}.edgeIds", edge_ids, errors
            )
            stages = _require_v2_object_array(flow.get("stages"), f"{location}.stages", errors)
            for key in ("outputs", "safety"):
                _require_v2_string_array(flow.get(key), f"{location}.{key}", errors)
            if "evidence" in flow:
                _require_v2_string_array(flow["evidence"], f"{location}.evidence", errors)
            if "coverageGap" in flow:
                _require_v2_string(flow["coverageGap"], f"{location}.coverageGap", errors)

            parent_node_ids = set(
                node_id for node_id in _list(flow.get("nodeIds")) if isinstance(node_id, str)
            )
            for stage_index, stage in enumerate(stages):
                stage_location = f"{location}.stages[{stage_index}]"
                _require_v2_string(stage.get("id"), f"{stage_location}.id", errors, True)
                _require_v2_string(
                    stage.get("label"), f"{stage_location}.label", errors, True
                )
                _require_v2_string(
                    stage.get("description"), f"{stage_location}.description", errors
                )
                stage_nodes_valid = _require_v2_references(
                    stage.get("nodeIds"), f"{stage_location}.nodeIds", node_ids, errors
                )
                if node_refs_valid and stage_nodes_valid:
                    for node_index, node_id in enumerate(stage["nodeIds"]):
                        if isinstance(node_id, str) and node_id not in parent_node_ids:
                            errors.append(
                                f"{stage_location}.nodeIds[{node_index}] must occur in the parent flow.nodeIds"
                            )
                _require_v2_string(
                    stage.get("backstage"), f"{stage_location}.backstage", errors
                )
                _require_v2_string_array(
                    stage.get("produces"), f"{stage_location}.produces", errors
                )


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
    flow_ids = _ids(document.get("flows"), "flows", errors)

    for index, node in enumerate(_list(document.get("nodes"))):
        if not isinstance(node, dict):
            continue
        location = f"nodes[{index}]"
        _require_reference(node.get("category"), category_ids, f"{location}.category", errors)
        _require_reference(node.get("phase"), phase_ids, f"{location}.phase", errors)
        status = node.get("status")
        if not isinstance(status, str) or status not in ALLOWED_STATUSES:
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

    schema_version = document_schema_version(document, errors)
    if schema_version == 2:
        _validate_v2_base_fields(
            document,
            category_ids,
            phase_ids,
            node_ids,
            edge_ids,
            errors,
        )
        snapshot_ids = _validate_v2_snapshots(document, errors)
        if "currentSnapshotId" in document:
            current_snapshot_id = document["currentSnapshotId"]
            if (
                not isinstance(current_snapshot_id, str)
                or current_snapshot_id not in snapshot_ids
            ):
                errors.append(
                    f"currentSnapshotId references unknown snapshot '{current_snapshot_id}'"
                )
        all_ids = node_ids | edge_ids | flow_ids
        collection_records = {
            "nodes": _validate_v2_annotations(
                document.get("nodes"),
                "nodes",
                node_ids,
                all_ids,
                snapshot_ids,
                errors,
                NODE_KINDS,
            ),
            "edges": _validate_v2_annotations(
                document.get("edges"),
                "edges",
                edge_ids,
                all_ids,
                snapshot_ids,
                errors,
                EDGE_KINDS,
            ),
            "flows": _validate_v2_annotations(
                document.get("flows"),
                "flows",
                flow_ids,
                all_ids,
                snapshot_ids,
                errors,
            ),
        }
        _validate_v2_comparisons(
            document,
            snapshot_ids,
            collection_records,
            {"nodes": node_ids, "edges": edge_ids, "flows": flow_ids},
            errors,
        )
        _validate_v2_view(document, flow_ids, errors)
        _validate_v2_flow_edges(
            document.get("flows"), collection_records["edges"], errors
        )
        _validate_v2_colors(document, errors)

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
