"""Command-line adapter for the GPT Pro Codex Loop controller."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Sequence

import gpc_loop_controller as controller


class _ArgumentError(ValueError):
    """A parser failure that can be emitted in the stable JSON envelope."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def _command_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], name: str) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--debug", action="store_true")
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Build the stable command-line interface without invoking the controller."""
    parser = _Parser(prog="gpc_loop.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = _command_parser(subparsers, "init")
    init.add_argument("--request", required=True, type=Path)
    init.add_argument("--repository-context", required=True, type=Path)
    init.add_argument("--approved-existing-path", action="append", default=[])
    init.add_argument("--model-policy", required=True, choices=("PRO_CLASS", "EXACT_LABEL"))
    init.add_argument("--requested-model-label")

    requirements = _command_parser(subparsers, "prepare-requirements")
    requirements.add_argument("--conflict-evidence", type=Path)

    accept_requirements = _command_parser(subparsers, "accept-requirements")
    accept_requirements.add_argument("--raw-response", required=True, type=Path)
    accept_requirements.add_argument("--observed-conversation-url", required=True)
    accept_requirements.add_argument("--observed-model-label", required=True)

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

    _command_parser(subparsers, "final-verify")
    _command_parser(subparsers, "status")

    abandon = _command_parser(subparsers, "abandon-attempt")
    abandon.add_argument("--send-status", required=True, choices=("NOT_SENT",))
    abandon.add_argument("--not-sent-evidence", required=True, type=Path)
    return parser


def _dispatch(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "init":
        return controller.initialize_run(
            args.repo,
            args.task,
            args.request,
            args.repository_context,
            args.approved_existing_path,
            args.model_policy,
            args.requested_model_label,
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
        )
    if args.command == "final-verify":
        return controller.final_verify(args.repo, args.task)
    if args.command == "status":
        return controller.status_run(args.repo, args.task)
    if args.command == "abandon-attempt":
        return controller.abandon_attempt(
            args.repo, args.task, args.send_status, args.not_sent_evidence
        )
    raise AssertionError("parser accepted an unsupported command")


def _write(value: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def _command_name(argv: Sequence[str]) -> str | None:
    return next((value for value in argv if not value.startswith("-")), None)


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one controller command and emit exactly one JSON result envelope."""
    values = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(values)
        result = _dispatch(args)
    except _ArgumentError:
        _write(
            {
                "ok": False,
                "command": _command_name(values),
                "error": {
                    "code": "ARGUMENT_ERROR",
                    "message": "Invalid command arguments.",
                    "details": [],
                },
            }
        )
        return 2
    except controller.ControllerError as error:
        _write(
            {
                "ok": False,
                "command": getattr(locals().get("args", None), "command", _command_name(values)),
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": list(error.details),
                },
            }
        )
        return 2
    except Exception:
        if "args" in locals() and args.debug:
            traceback.print_exc(file=sys.stderr)
        _write(
            {
                "ok": False,
                "command": getattr(locals().get("args", None), "command", _command_name(values)),
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "The controller encountered an internal error.",
                    "details": [],
                },
            }
        )
        return 1
    _write({"ok": True, "command": args.command, "result": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
