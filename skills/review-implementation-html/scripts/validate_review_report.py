"""Validate normalized implementation-review data and rendered HTML markers."""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter


TOP_LEVEL_KEYS = {
    "meta",
    "summary",
    "verification",
    "intentGroups",
    "files",
    "hunks",
    "findings",
    "coverage",
    "result",
}
META_KEYS = {"repository", "base", "head", "plan", "planSlug", "generatedAt"}
SEVERITIES = {"blocking", "high", "medium", "low", "note"}
PASSES = {"plan-blind", "plan-aware"}
FINDING_STATUSES = {"open", "resolved", "accepted"}
VERIFICATION_STATUSES = {"passed", "failed", "not-run", "blocked"}
RESULTS = {"passed", "changes-requested", "blocked", "incomplete"}
RISK_ORDER = {"blocking": 0, "high": 1, "medium": 2, "low": 3, "note": 4}
HTML_MARKERS = (
    'id="reviewData"',
    'id="reviewNav"',
    "data-comment-id",
    'id="exportComments"',
    'id="copyCorrectionPrompt"',
    'id="manualCopyFallback"',
)


def _require_keys(value: dict, keys: set[str], prefix: str, errors: list[str]) -> None:
    for key in sorted(keys):
        if key not in value:
            errors.append(f"{prefix}.{key} is required")


def _unique_ids(items: list, label: str, errors: list[str]) -> set[str]:
    ids: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"{label}[{index}].id is required")
        else:
            ids.append(identifier)
    duplicates = sorted(identifier for identifier, count in Counter(ids).items() if count > 1)
    for identifier in duplicates:
        errors.append(f"{label} id {identifier!r} must be unique")
    return set(ids)


def validate_document(document: dict) -> list[str]:
    """Return human-readable schema and integrity errors."""
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["review document must be an object"]
    _require_keys(document, TOP_LEVEL_KEYS, "review", errors)
    if errors:
        return errors

    meta = document["meta"]
    if not isinstance(meta, dict):
        errors.append("review.meta must be an object")
    else:
        _require_keys(meta, META_KEYS, "review.meta", errors)
        for key in META_KEYS:
            if key in meta and not isinstance(meta[key], str):
                errors.append(f"review.meta.{key} must be a string")
        slug = meta.get("planSlug")
        if isinstance(slug, str) and (not slug or "/" in slug or "\\" in slug):
            errors.append("review.meta.planSlug must be a non-empty path-safe slug")

    summary = document["summary"]
    if not isinstance(summary, dict):
        errors.append("review.summary must be an object")
    else:
        _require_keys(summary, {"headline", "overview"}, "review.summary", errors)

    collection_keys = ("verification", "intentGroups", "files", "hunks", "findings")
    for key in collection_keys:
        if not isinstance(document[key], list):
            errors.append(f"review.{key} must be an array")
    if any(not isinstance(document[key], list) for key in collection_keys):
        return errors

    groups = document["intentGroups"]
    files = document["files"]
    hunks = document["hunks"]
    findings = document["findings"]
    group_ids = _unique_ids(groups, "intentGroups", errors)
    hunk_ids = _unique_ids(hunks, "hunks", errors)
    finding_ids = _unique_ids(findings, "findings", errors)

    file_paths: set[str] = set()
    for index, file_item in enumerate(files):
        if not isinstance(file_item, dict):
            errors.append(f"files[{index}] must be an object")
            continue
        path = file_item.get("path")
        if not isinstance(path, str) or not path:
            errors.append(f"files[{index}].path is required")
        elif path in file_paths:
            errors.append(f"file path {path!r} must be unique")
        else:
            file_paths.add(path)
        if not isinstance(file_item.get("status"), str) or not file_item.get("status"):
            errors.append(f"files[{index}].status is required")

    previous_rank = -1
    hunk_owners: Counter[str] = Counter()
    finding_owners: Counter[str] = Counter()
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        _require_keys(
            group,
            {"id", "title", "summary", "risk", "hunkIds", "findingIds"},
            f"intentGroups[{index}]",
            errors,
        )
        risk = group.get("risk")
        if risk not in SEVERITIES:
            errors.append(f"intentGroups[{index}].risk must be a valid severity")
        else:
            rank = RISK_ORDER[risk]
            if rank < previous_rank:
                errors.append("intentGroups must be sorted from highest to lowest risk")
            previous_rank = rank
        for hunk_id in group.get("hunkIds", []) if isinstance(group.get("hunkIds"), list) else []:
            hunk_owners[hunk_id] += 1
            if hunk_id not in hunk_ids:
                errors.append(f"intentGroups[{index}] references unknown hunk {hunk_id!r}")
        for finding_id in (
            group.get("findingIds", []) if isinstance(group.get("findingIds"), list) else []
        ):
            finding_owners[finding_id] += 1
            if finding_id not in finding_ids:
                errors.append(
                    f"intentGroups[{index}] references unknown finding {finding_id!r}"
                )

    for hunk_id in sorted(hunk_ids):
        if hunk_owners[hunk_id] != 1:
            errors.append(
                f"hunk {hunk_id!r} must belong to exactly one intent group "
                f"(found {hunk_owners[hunk_id]})"
            )
    for finding_id in sorted(finding_ids):
        if finding_owners[finding_id] != 1:
            errors.append(
                f"finding {finding_id!r} must belong to exactly one intent group"
            )

    for index, hunk in enumerate(hunks):
        if not isinstance(hunk, dict):
            continue
        _require_keys(
            hunk,
            {"id", "file", "oldStart", "newStart", "diff", "explanation"},
            f"hunks[{index}]",
            errors,
        )
        if hunk.get("file") not in file_paths:
            errors.append(f"hunks[{index}].file must reference a changed file")
        for key in ("oldStart", "newStart"):
            if not isinstance(hunk.get(key), int) or hunk.get(key, 0) < 0:
                errors.append(f"hunks[{index}].{key} must be a non-negative integer")
        if not isinstance(hunk.get("diff"), str) or not hunk.get("diff"):
            errors.append(f"hunks[{index}].diff is required")
        if not isinstance(hunk.get("explanation"), str) or not hunk.get("explanation"):
            errors.append(f"hunks[{index}].explanation is required")

    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        _require_keys(
            finding,
            {
                "id",
                "severity",
                "pass",
                "intentGroupId",
                "file",
                "line",
                "title",
                "evidence",
                "impact",
                "recommendedAction",
                "status",
            },
            f"findings[{index}]",
            errors,
        )
        severity = finding.get("severity")
        if severity not in SEVERITIES:
            errors.append(f"findings[{index}].severity is invalid")
        if finding.get("pass") not in PASSES:
            errors.append(f"findings[{index}].pass is invalid")
        if finding.get("status") not in FINDING_STATUSES:
            errors.append(f"findings[{index}].status is invalid")
        if finding.get("intentGroupId") not in group_ids:
            errors.append(f"findings[{index}].intentGroupId is unknown")
        if finding.get("file") not in file_paths:
            errors.append(f"findings[{index}].file must reference a changed file")
        if not isinstance(finding.get("line"), int) or finding.get("line", 0) < 1:
            errors.append(f"findings[{index}].line must be a positive integer")
        for key in ("title", "evidence", "impact"):
            if not isinstance(finding.get(key), str) or not finding.get(key).strip():
                errors.append(f"findings[{index}].{key} is required")
        if severity in {"blocking", "high"} and (
            not isinstance(finding.get("recommendedAction"), str)
            or not finding.get("recommendedAction", "").strip()
        ):
            errors.append(
                f"findings[{index}].recommended_action is required for {severity} severity"
            )

    for index, check in enumerate(document["verification"]):
        if not isinstance(check, dict):
            errors.append(f"verification[{index}] must be an object")
            continue
        _require_keys(check, {"name", "status", "details"}, f"verification[{index}]", errors)
        if check.get("status") not in VERIFICATION_STATUSES:
            errors.append(f"verification[{index}].status is invalid")

    coverage = document["coverage"]
    if not isinstance(coverage, dict):
        errors.append("review.coverage must be an object")
    else:
        _require_keys(
            coverage,
            {"changedFilesReviewed", "intentGroupsReviewed", "gaps"},
            "review.coverage",
            errors,
        )
        reviewed_files = coverage.get("changedFilesReviewed", [])
        if isinstance(reviewed_files, list):
            unknown = sorted(set(reviewed_files) - file_paths)
            for path in unknown:
                errors.append(f"coverage references unknown file {path!r}")
        else:
            errors.append("review.coverage.changedFilesReviewed must be an array")
        reviewed_groups = coverage.get("intentGroupsReviewed", [])
        if isinstance(reviewed_groups, list):
            unknown = sorted(set(reviewed_groups) - group_ids)
            for identifier in unknown:
                errors.append(f"coverage references unknown intent group {identifier!r}")
        else:
            errors.append("review.coverage.intentGroupsReviewed must be an array")
        if not isinstance(coverage.get("gaps"), list):
            errors.append("review.coverage.gaps must be an array")

    if document["result"] not in RESULTS:
        errors.append("review.result is invalid")
    return errors


def validate_html(html: str) -> list[str]:
    """Check that a rendered report exposes its required interaction contracts."""
    return [f"HTML marker missing: {marker}" for marker in HTML_MARKERS if marker not in html]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_data", type=pathlib.Path)
    parser.add_argument("--html", type=pathlib.Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.review_data.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    errors = validate_document(document)
    if args.html:
        try:
            errors.extend(validate_html(args.html.read_text(encoding="utf-8")))
        except OSError as exc:
            parser.error(str(exc))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Review report is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
