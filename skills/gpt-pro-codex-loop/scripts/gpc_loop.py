"""Command-line adapter for the GPT Pro Codex Loop controller."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Sequence

import gpc_loop_controller as controller


COMMANDS = frozenset(
    {
        "inspect-init",
        "init",
        "prepare-requirements",
        "accept-requirements",
        "approve-requirements",
        "build-report",
        "prepare-review",
        "accept-review",
        "final-verify",
        "export-governance-receipt",
        "status",
        "abandon-attempt",
    }
)


class _ArgumentError(ValueError):
    """A parser failure that can be emitted in the stable JSON envelope."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def _command_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser], name: str
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--debug", action="store_true")
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Build the stable command-line interface without invoking the controller."""
    parser = _Parser(prog="gpc_loop.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = _command_parser(subparsers, "inspect-init")
    inspect.add_argument("--write-approval-manifest", type=Path)

    init = _command_parser(subparsers, "init")
    init.add_argument("--request", required=True, type=Path)
    init.add_argument("--repository-context", required=True, type=Path)
    approval = init.add_mutually_exclusive_group()
    approval.add_argument("--approved-existing-path", action="append", default=[])
    approval.add_argument("--approved-existing-path-manifest", type=Path)
    init.add_argument("--retry-incomplete", action="store_true")
    init.add_argument("--model-policy", required=True, choices=("PRO_CLASS", "EXACT_LABEL"))
    init.add_argument("--requested-model-label")
    init.add_argument("--governance-context", type=Path)

    requirements = _command_parser(subparsers, "prepare-requirements")
    requirements.add_argument("--conflict-evidence", type=Path)

    accept_requirements = _command_parser(subparsers, "accept-requirements")
    accept_requirements.add_argument("--raw-response", required=True, type=Path)
    accept_requirements.add_argument("--observed-conversation-url", required=True)
    accept_requirements.add_argument("--observed-model-label", required=True)
    accept_requirements.add_argument("--observed-reasoning-label")
    accept_requirements.add_argument("--observed-plan-label")

    approval = _command_parser(subparsers, "approve-requirements")
    approval.add_argument("--approval-evidence", required=True, type=Path)

    report = _command_parser(subparsers, "build-report")
    report.add_argument("--local-evidence", required=True, type=Path)

    review = _command_parser(subparsers, "prepare-review")
    review.add_argument("--supplemental-evidence", type=Path)

    accept_review = _command_parser(subparsers, "accept-review")
    accept_review.add_argument("--raw-response", required=True, type=Path)
    accept_review.add_argument("--observed-conversation-url", required=True)
    accept_review.add_argument("--observed-model-label", required=True)
    accept_review.add_argument("--observed-reasoning-label")
    accept_review.add_argument("--observed-plan-label")

    _command_parser(subparsers, "final-verify")
    export_receipt = _command_parser(subparsers, "export-governance-receipt")
    export_receipt.add_argument(
        "--type", required=True, choices=("requirements", "review", "final")
    )
    _command_parser(subparsers, "status")

    abandon = _command_parser(subparsers, "abandon-attempt")
    abandon.add_argument("--send-status", required=True, choices=("NOT_SENT",))
    abandon.add_argument("--not-sent-evidence", required=True, type=Path)
    return parser


def _dispatch(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "inspect-init":
        return controller.inspect_initialization(
            args.repo, args.task, args.write_approval_manifest
        )
    if args.command == "init":
        return controller.initialize_run(
            args.repo,
            args.task,
            args.request,
            args.repository_context,
            args.approved_existing_path,
            args.model_policy,
            args.requested_model_label,
            args.approved_existing_path_manifest,
            args.retry_incomplete,
            args.governance_context,
        )
    if args.command == "prepare-requirements":
        return controller.prepare_requirements(args.repo, args.task, args.conflict_evidence)
    if args.command == "accept-requirements":
        return controller.accept_requirements(
            args.repo,
            args.task,
            args.raw_response,
            args.observed_conversation_url,
            args.observed_model_label,
            args.observed_reasoning_label,
            args.observed_plan_label,
        )
    if args.command == "approve-requirements":
        return controller.approve_requirements(args.repo, args.task, args.approval_evidence)
    if args.command == "build-report":
        return controller.build_report(args.repo, args.task, args.local_evidence)
    if args.command == "prepare-review":
        return controller.prepare_review(args.repo, args.task, args.supplemental_evidence)
    if args.command == "accept-review":
        return controller.accept_review(
            args.repo,
            args.task,
            args.raw_response,
            args.observed_conversation_url,
            args.observed_model_label,
            args.observed_reasoning_label,
            args.observed_plan_label,
        )
    if args.command == "final-verify":
        return controller.final_verify(args.repo, args.task)
    if args.command == "export-governance-receipt":
        return controller.export_governance_receipt(args.repo, args.task, args.type)
    if args.command == "status":
        return controller.status_run(args.repo, args.task)
    if args.command == "abandon-attempt":
        return controller.abandon_attempt(
            args.repo, args.task, args.send_status, args.not_sent_evidence
        )
    raise AssertionError("parser accepted an unsupported command")


def _write(value: dict[str, object]) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    sys.stdout.buffer.write(payload + b"\n")


def _command_name(argv: Sequence[str]) -> str | None:
    return argv[0] if argv and argv[0] in COMMANDS else None


def _emit_error(
    command: str | None,
    code: str,
    message: str,
    details: Sequence[str],
    exit_code: int,
    debug: bool,
) -> int:
    try:
        _write(
            {
                "ok": False,
                "command": command,
                "error": {"code": code, "message": message, "details": list(details)},
            }
        )
    except Exception:
        if debug:
            traceback.print_exc(file=sys.stderr)
        return 1
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one controller command and emit exactly one JSON result envelope."""
    values = list(sys.argv[1:] if argv is None else argv)
    args: argparse.Namespace | None = None
    debug = "--debug" in values
    try:
        args = build_parser().parse_args(values)
        debug = args.debug
        result = _dispatch(args)
        _write({"ok": True, "command": args.command, "result": result})
        return 0
    except _ArgumentError:
        return _emit_error(
            _command_name(values), "ARGUMENT_ERROR", "Invalid command arguments.", [], 2, debug
        )
    except controller.ControllerError as error:
        return _emit_error(
            args.command if args is not None else _command_name(values),
            error.code,
            error.message,
            error.details,
            2,
            debug,
        )
    except Exception:
        if debug:
            traceback.print_exc(file=sys.stderr)
        return _emit_error(
            args.command if args is not None else _command_name(values),
            "INTERNAL_ERROR",
            "The controller encountered an internal error.",
            [],
            1,
            False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
