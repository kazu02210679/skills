#!/usr/bin/env python3
"""Choose the cheapest review topology that preserves review ordering."""

from __future__ import annotations

import json
import re
import sys
from typing import Callable, Iterable, Protocol


RISK_PATTERNS = {
    "auth_or_authorization": re.compile(r"(^|[/\\])(auth|authentication|authorization|permissions?)([/\\.]|$)", re.I),
    "secrets_or_credentials": re.compile(r"secret|credential|token|private[_-]?key", re.I),
    "sandbox_or_permissions": re.compile(r"sandbox|approvals?|permissions?", re.I),
    "command_or_rce": re.compile(r"shell|command|subprocess|exec|rce", re.I),
    "destructive_data_change": re.compile(r"migration|delete|drop|truncate|purge", re.I),
    "release_or_signing_trust": re.compile(r"release|signing|provenance|supply[_-]?chain", re.I),
    "reviewer_or_safety_policy": re.compile(r"reviewer|auto[_-]?review|safety[_-]?policy", re.I),
}


class Reviewer(Protocol):
    session_id: str

    def review(self, pass_name: str, plan: str | None) -> object: ...


def select_review_mode(
    changed_files: int,
    added_lines: int,
    deleted_lines: int,
    paths: Iterable[str],
) -> dict[str, object]:
    risks = sorted(
        category
        for category, pattern in RISK_PATTERNS.items()
        if any(pattern.search(path) for path in paths)
    )
    reasons = []
    if changed_files >= 20:
        reasons.append("changed_files_at_least_20")
    if added_lines + deleted_lines >= 1000:
        reasons.append("changed_lines_at_least_1000")
    reasons.extend(f"high_risk:{risk}" for risk in risks)
    return {
        "mode": "isolated" if reasons else "serial_same_session",
        "reasons": reasons,
        "risk_categories": risks,
        "review_order": ["plan_blind", "plan_aware"],
    }


def orchestrate_review(
    decision: dict[str, object],
    plan: str,
    create_reviewer: Callable[[str], Reviewer],
) -> dict[str, object]:
    """Execute the observable blind-then-aware lifecycle selected above."""
    mode = decision.get("mode")
    if mode not in {"serial_same_session", "isolated"}:
        raise ValueError("Unknown review mode")
    events: list[dict[str, object]] = []
    blind = create_reviewer(str(mode))
    events.append({"event": "session_created", "pass": "plan_blind", "session_id": blind.session_id})
    blind_result = blind.review("plan_blind", None)
    events.append({"event": "pass_completed", "pass": "plan_blind", "session_id": blind.session_id})
    aware = blind if mode == "serial_same_session" else create_reviewer("isolated")
    if aware is not blind:
        events.append({"event": "session_created", "pass": "plan_aware", "session_id": aware.session_id})
    events.append({"event": "plan_injected", "pass": "plan_aware", "session_id": aware.session_id})
    aware_result = aware.review("plan_aware", plan)
    events.append({"event": "pass_completed", "pass": "plan_aware", "session_id": aware.session_id})
    return {
        "mode": mode,
        "events": events,
        "isolated_session_creations": 0 if mode == "serial_same_session" else 2,
        "session_ids": [blind.session_id, aware.session_id],
        "results": [blind_result, aware_result],
    }


def main() -> int:
    payload = json.load(sys.stdin)
    print(json.dumps(select_review_mode(**payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
