"""Stable JSON command boundary for HOTL governance."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

import hotl_contract as contract
import hotl_controller as controller
import hotl_store as store


COMMANDS = (
    "init",
    "status",
    "record",
    "approve",
    "import-receipt",
    "record-implementation",
    "run-verification",
    "import-sol-receipt",
    "export-governance-context",
    "evaluate",
    "project",
    "verify-log",
    "start-successor",
)


class _ArgumentError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise _ArgumentError(message or "argument parsing stopped")


def _run_arguments(parser: argparse.ArgumentParser, *, execution: bool = True) -> None:
    parser.add_argument("--repo", required=True)
    if execution:
        parser.add_argument("--execution", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="hotl-governance", add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", add_help=False)
    _run_arguments(init)
    init.add_argument("--policy", required=True)
    init.add_argument("--requirements", required=True)

    status = subparsers.add_parser("status", add_help=False)
    _run_arguments(status)

    record = subparsers.add_parser("record", add_help=False)
    _run_arguments(record)
    record.add_argument("--event", required=True)

    approve = subparsers.add_parser("approve", add_help=False)
    _run_arguments(approve)
    approve.add_argument("--evidence", required=True)

    receipt = subparsers.add_parser("import-receipt", add_help=False)
    _run_arguments(receipt)
    receipt.add_argument("--receipt", required=True)
    receipt.add_argument("--gpt-repo")

    implementation = subparsers.add_parser("record-implementation", add_help=False)
    _run_arguments(implementation)
    implementation.add_argument("--manifest", required=True)
    implementation.add_argument("--report", required=True)

    verification = subparsers.add_parser("run-verification", add_help=False)
    _run_arguments(verification)
    verification.add_argument("--argv", required=True)

    sol = subparsers.add_parser("import-sol-receipt", add_help=False)
    _run_arguments(sol)
    sol.add_argument("--receipt", required=True)

    context = subparsers.add_parser("export-governance-context", add_help=False)
    _run_arguments(context)
    context.add_argument("--output", required=True)

    evaluate = subparsers.add_parser("evaluate", add_help=False)
    _run_arguments(evaluate)
    evaluate.add_argument(
        "--gate",
        required=True,
        choices=(
            "INIT",
            "G1",
            "G2",
            "G3",
            "G4",
            "CORRECTIVE",
            "ESCALATION",
            "MATERIAL_CHANGE",
            "STOP",
        ),
    )

    project = subparsers.add_parser("project", add_help=False)
    _run_arguments(project)
    project.add_argument("--stdout", action="store_true")

    verify = subparsers.add_parser("verify-log", add_help=False)
    _run_arguments(verify)

    successor = subparsers.add_parser("start-successor", add_help=False)
    _run_arguments(successor, execution=False)
    successor.add_argument("--predecessor", required=True)
    successor.add_argument("--lineage", required=True)
    successor.add_argument("--policy", required=True)
    successor.add_argument("--requirements", required=True)
    return parser


def _read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def _read_object(path: str, label: str) -> dict[str, object]:
    raw = _read_bytes(path)
    try:
        value = contract.strict_json_loads(raw.decode("utf-8", errors="strict"))
    except UnicodeError as error:
        raise controller.ControllerError(
            "INVALID_JSON", f"{label} must be UTF-8 JSON."
        ) from error
    if not isinstance(value, dict):
        raise controller.ControllerError("INVALID_SCHEMA", f"{label} must be an object.")
    if contract.canonical_json_bytes(value) != raw:
        raise controller.ControllerError(
            "NONCANONICAL_JSON", f"{label} must use canonical JSON."
        )
    return value


def _record_artifacts(repository: Path, event: dict[str, object]) -> dict[str, bytes]:
    refs = event.get("artifact_refs")
    if not isinstance(refs, list):
        raise controller.ControllerError(
            "INVALID_SCHEMA", "Event artifact_refs must be a list."
        )
    artifacts: dict[str, bytes] = {}
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise controller.ControllerError(
                "INVALID_SCHEMA", "Artifact reference fields are invalid."
            )
        if not isinstance(ref["path"], str):
            raise controller.ControllerError(
                "INVALID_SCHEMA", "Artifact reference path must be a string."
            )
        content = store.read_repository_artifact(repository, ref["path"])
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if digest != ref["sha256"]:
            raise controller.ControllerError(
                "DIGEST_MISMATCH", "Artifact bytes do not match the event digest."
            )
        artifacts[digest] = content
    return artifacts


def _next_commands(
    status: dict[str, object], *, repository: Path | None = None, execution_id: str | None = None
) -> list[str]:
    state = status["state"]
    if state == "UNINITIALIZED":
        return ["init"]
    if state == controller.State.RECOVERY_REQUIRED.value or state in {
        member.value for member in controller.TERMINAL_STATES
    }:
        if repository is not None and isinstance(execution_id, str) and controller.has_material_predecessor(
            repository, execution_id
        ):
            return ["start-successor"]
        return []
    if status.get("allowed_transitions"):
        return ["evaluate"]
    if state == controller.State.REQUIREMENTS.value:
        return ["export-governance-context", "import-receipt"]
    if state == controller.State.IMPLEMENT.value:
        return ["record-implementation"]
    if state == controller.State.LOCAL_VERIFY.value:
        return ["run-verification"]
    if state == controller.State.SEMANTIC_REVIEW.value:
        return ["import-receipt", "import-sol-receipt"]
    return []


def _dispatch(arguments: argparse.Namespace) -> dict[str, object]:
    command = arguments.command
    repository = Path(arguments.repo)
    if command == "init":
        return controller.initialize_execution(
            repository,
            arguments.execution,
            _read_object(arguments.policy, "policy"),
            _read_object(arguments.requirements, "requirements"),
        )
    if command == "status":
        status = controller.status_execution(repository, arguments.execution)
        return status | {"next_commands": _next_commands(status, repository=repository, execution_id=arguments.execution)}
    if command == "record":
        event = _read_object(arguments.event, "event")
        artifacts = _record_artifacts(repository, event)
        try:
            return controller.record_event(
                repository, arguments.execution, event, artifacts
            )
        except controller.ControllerError as error:
            if error.code == "PRIVILEGED_EVENT":
                raise controller.ControllerError(
                    "PRIVILEGED_EVENT_REQUIRES_RECEIPT",
                    "Privileged events require an issuer-validated receipt command.",
                ) from error
            raise
    if command == "approve":
        return controller.approve_execution(
            repository,
            arguments.execution,
            _read_bytes(arguments.evidence),
        )
    if command == "import-receipt":
        return controller.import_receipt(
            repository, arguments.execution, _read_bytes(arguments.receipt),
            gpt_repository=Path(arguments.gpt_repo) if arguments.gpt_repo else None,
        )
    if command == "record-implementation":
        return controller.record_implementation(
            repository,
            arguments.execution,
            _read_bytes(arguments.manifest),
            _read_bytes(arguments.report),
        )
    if command == "run-verification":
        return controller.run_verification(
            repository, arguments.execution, _read_bytes(arguments.argv)
        )
    if command == "import-sol-receipt":
        return controller.import_sol_receipt(repository, arguments.execution, _read_bytes(arguments.receipt))
    if command == "export-governance-context":
        context = controller.export_governance_context(repository, arguments.execution)
        payload = contract.canonical_json_bytes(context)
        try:
            Path(arguments.output).write_bytes(payload)
        except OSError as error:
            raise controller.ControllerError("OUTPUT_WRITE_ERROR", "Could not write governance context artifact.") from error
        return {"context_file_digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
    if command == "evaluate":
        return controller.commit_transition(
            repository, arguments.execution, arguments.gate
        )
    if command == "project":
        if not arguments.stdout:
            raise controller.ControllerError(
                "STDOUT_REQUIRED", "v1 project requires --stdout."
            )
        return controller.project_execution(repository, arguments.execution)
    if command == "verify-log":
        return controller.verify_execution(repository, arguments.execution)
    if command == "start-successor":
        return controller.start_successor(
            repository,
            arguments.predecessor,
            _read_object(arguments.lineage, "lineage"),
            _read_object(arguments.policy, "policy"),
            _read_object(arguments.requirements, "requirements"),
        )
    raise controller.ControllerError("UNKNOWN_COMMAND", "Command is not supported.")


def _failure(command: str | None, code: str, message: str) -> dict[str, object]:
    return {
        "command": command,
        "error": {"code": code, "message": message},
        "ok": False,
    }


def main_json(argv: Sequence[str]) -> dict[str, object]:
    command = argv[0] if argv else None
    try:
        arguments = _parser().parse_args(list(argv))
        result = _dispatch(arguments)
    except _ArgumentError as error:
        return _failure(command, "ARGUMENT_ERROR", str(error))
    except (controller.ControllerError, store.StoreError, contract.ContractError) as error:
        return _failure(command, error.code, error.message)
    except (OSError, UnicodeError) as error:
        return _failure(command, "INPUT_READ_ERROR", str(error))
    except TypeError:
        return _failure(command, "INVALID_SCHEMA", "Input values have invalid types.")
    return {"command": command, "ok": True, "result": result}


def main(argv: Sequence[str] | None = None) -> int:
    result = main_json(sys.argv[1:] if argv is None else argv)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
