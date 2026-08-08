#!/usr/bin/env python3
"""Report deterministic, explicitly scoped Skill context budgets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def approximate_tokens(byte_count: int) -> int:
    return (byte_count + 3) // 4


def split_skill_document(value: bytes) -> tuple[bytes, bytes]:
    if not value.startswith(b"---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    boundary = value.find(b"\n---\n", 4)
    if boundary < 0:
        raise ValueError("SKILL.md frontmatter is not closed")
    end = boundary + len(b"\n---\n")
    return value[:end], value[end:]


def build_report(repository: Path, manifest_path: Path) -> dict[str, Any]:
    repository = repository.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    configured = manifest.get("skills", {})
    reports: list[dict[str, Any]] = []
    for skill_dir in sorted((repository / "skills").iterdir(), key=lambda item: item.name):
        skill_file = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_file.is_file():
            continue
        skill_bytes = normalized_bytes(skill_file)
        metadata_bytes, body_bytes = split_skill_document(skill_bytes)
        assets = []
        auxiliary_bytes = 0
        for relative in sorted(configured.get(skill_dir.name, [])):
            asset_path = skill_dir / relative
            if not asset_path.is_file():
                raise ValueError(f"Missing configured context asset: {skill_dir.name}/{relative}")
            size = len(normalized_bytes(asset_path))
            auxiliary_bytes += size
            assets.append({"path": relative, "utf8_bytes": size, "approx_tokens": approximate_tokens(size)})
        total = len(skill_bytes) + auxiliary_bytes
        reports.append(
            {
                "name": skill_dir.name,
                "metadata_utf8_bytes": len(metadata_bytes),
                "body_utf8_bytes": len(body_bytes),
                "skill_md_utf8_bytes": len(skill_bytes),
                "auxiliary_utf8_bytes": auxiliary_bytes,
                "utf8_bytes": total,
                "approx_tokens": approximate_tokens(total),
                "auxiliary_assets": assets,
            }
        )
    total_bytes = sum(item["utf8_bytes"] for item in reports)
    metadata_bytes = sum(item["metadata_utf8_bytes"] for item in reports)
    return {
        "schema_version": 1,
        "approximation": "ceil(normalized_utf8_bytes/4)",
        "skills": reports,
        "repository_totals": {
            "skill_count": len(reports),
            "metadata_utf8_bytes": metadata_bytes,
            "utf8_bytes": total_bytes,
            "approx_tokens": approximate_tokens(total_bytes),
        },
    }


def check_regression(current: dict[str, Any], baseline: dict[str, Any], *, max_growth_bytes: int) -> list[str]:
    failures: list[str] = []
    current_totals = current["repository_totals"]
    baseline_totals = baseline["repository_totals"]
    for field in ("metadata_utf8_bytes", "utf8_bytes"):
        if field not in current_totals or field not in baseline_totals:
            continue
        growth = current_totals[field] - baseline_totals[field]
        if growth > max_growth_bytes:
            failures.append(f"repository {field} grew by {growth}; allowed {max_growth_bytes}")
    current_skills = {item["name"]: item for item in current.get("skills", [])}
    baseline_skills = {item["name"]: item for item in baseline.get("skills", [])}
    for name in sorted(current_skills.keys() & baseline_skills.keys()):
        for field in ("metadata_utf8_bytes", "skill_md_utf8_bytes", "auxiliary_utf8_bytes"):
            growth = current_skills[name][field] - baseline_skills[name][field]
            if growth > max_growth_bytes:
                failures.append(f"{name} {field} grew by {growth}; allowed {max_growth_bytes}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=Path("context-budget-manifest.json"))
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--max-growth-bytes", type=int, default=0)
    args = parser.parse_args()
    manifest = args.manifest if args.manifest.is_absolute() else args.repo / args.manifest
    report = build_report(args.repo, manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.baseline:
        failures = check_regression(report, json.loads(args.baseline.read_text(encoding="utf-8")), max_growth_bytes=args.max_growth_bytes)
        if failures:
            for failure in failures:
                print(failure)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
