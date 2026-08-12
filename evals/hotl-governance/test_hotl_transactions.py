from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "hotl-governance" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hotl_store as store


EXECUTION_ID = "EXEC-123456789ABC"
DIGEST_ONE = "sha256:" + "1" * 64
DIGEST_TWO = "sha256:" + "2" * 64


def event_hash(event: dict[str, object]) -> str:
    encoded = (
        json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def fixture_event(
    sequence: int = 1,
    previous_hash: str | None = None,
    event_id: str = "EVT-000000000001",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "execution_id": EXECUTION_ID,
        "sequence": sequence,
        "type": "node_declared",
        "payload": {"node_id": f"REQ-{sequence}", "node_type": "requirement"},
        "issuer": {"kind": "controller", "id": "hotl-governance", "version": "1"},
        "subject_ids": [f"REQ-{sequence}"],
        "artifact_refs": [],
        "result": "pass",
        "input_digest": DIGEST_ONE,
        "output_digest": DIGEST_TWO,
        "previous_event_hash": previous_hash,
        "timestamp": f"2026-08-09T00:00:0{sequence}Z",
    }


def fixture_state(count: int, head: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "execution_id": EXECUTION_ID,
        "state": "INIT",
        "event_count": count,
        "head_event_hash": head,
    }


class TransactionStorageTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows handle semantics")
    def test_safe_artifact_read_rejects_final_component_swap_to_in_repo_alias(
        self,
    ) -> None:
        candidate = self.repository / "artifact.txt"
        candidate.write_bytes(b"original\n")
        alias_target = self.repository / "alias-target.txt"
        alias_target.write_bytes(b"alias\n")
        probe = self.repository / "probe-link"
        try:
            probe.symlink_to(alias_target)
            probe.unlink()
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        kernel32 = ctypes.windll.kernel32
        real_create_file = kernel32.CreateFileW
        real_os_open = os.open
        swapped = False

        def swap() -> None:
            nonlocal swapped
            if not swapped:
                candidate.unlink()
                candidate.symlink_to(alias_target)
                swapped = True

        def swap_before_create(*args: object) -> object:
            if Path(str(args[0])) == candidate:
                swap()
            return real_create_file(*args)

        def swap_before_os_open(path: object, flags: int, mode: int = 0o777) -> int:
            if Path(path) == candidate:
                swap()
            return real_os_open(path, flags, mode)

        with (
            patch.object(kernel32, "CreateFileW", side_effect=swap_before_create),
            patch.object(store.os, "open", side_effect=swap_before_os_open),
        ):
            content: bytes | None = None
            try:
                content = store.read_repository_artifact(self.repository, "artifact.txt")
            except store.StoreError as error:
                raised = error
            else:
                raised = None

        self.assertTrue(swapped)
        self.assertIsNotNone(raised, f"unsafe alias bytes were accepted: {content!r}")
        assert raised is not None
        self.assertEqual("UNSAFE_ARTIFACT", raised.code)

    @unittest.skipUnless(os.name == "nt", "Windows handle semantics")
    def test_safe_artifact_read_rejects_intermediate_swap_to_in_repo_alias(
        self,
    ) -> None:
        source = self.repository / "source"
        source.mkdir()
        candidate = source / "artifact.txt"
        candidate.write_bytes(b"original\n")
        alias_directory = self.repository / "alias-directory"
        alias_directory.mkdir()
        (alias_directory / "artifact.txt").write_bytes(b"alias\n")
        probe = self.repository / "probe-directory-link"
        try:
            probe.symlink_to(alias_directory, target_is_directory=True)
            probe.unlink()
        except OSError as error:
            self.skipTest(f"directory symlink creation unavailable: {error}")
        kernel32 = ctypes.windll.kernel32
        real_create_file = kernel32.CreateFileW
        swapped = False

        def swap_before_create(*args: object) -> object:
            nonlocal swapped
            if not swapped and Path(str(args[0])) == candidate:
                candidate.unlink()
                source.rmdir()
                source.symlink_to(alias_directory, target_is_directory=True)
                swapped = True
            return real_create_file(*args)

        with patch.object(kernel32, "CreateFileW", side_effect=swap_before_create):
            content: bytes | None = None
            try:
                content = store.read_repository_artifact(
                    self.repository, "source/artifact.txt"
                )
            except store.StoreError as error:
                raised = error
            else:
                raised = None

        self.assertTrue(swapped)
        self.assertIsNotNone(raised, f"unsafe alias bytes were accepted: {content!r}")
        assert raised is not None
        self.assertEqual("UNSAFE_ARTIFACT", raised.code)

    def test_safe_artifact_read_rejects_static_symlink_or_reparse(self) -> None:
        target = self.repository / "target.txt"
        target.write_bytes(b"inside\n")
        link = self.repository / "artifact.txt"
        try:
            link.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")

        with self.assertRaises(store.StoreError) as raised:
            store.read_repository_artifact(self.repository, "artifact.txt")

        self.assertEqual("UNSAFE_ARTIFACT", raised.exception.code)

    def test_safe_artifact_read_fails_closed_on_swap_to_outside_link(self) -> None:
        candidate = self.repository / "artifact.txt"
        candidate.write_bytes(b"inside\n")
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_bytes(b"outside\n")
        probe = self.repository / "probe-link"
        try:
            probe.symlink_to(outside)
            probe.unlink()
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        real_open = os.open
        swapped = False

        def swap() -> None:
            nonlocal swapped
            if not swapped:
                candidate.unlink()
                candidate.symlink_to(outside)
                swapped = True

        def swap_before_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            if not swapped and (str(path) == "artifact.txt" or Path(path) == candidate):
                swap()
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with ExitStack() as patches:
            patches.enter_context(
                patch.object(store.os, "open", side_effect=swap_before_open)
            )
            if os.name == "nt":
                kernel32 = ctypes.windll.kernel32
                real_create_file = kernel32.CreateFileW

                def swap_before_create(*args: object) -> object:
                    if Path(str(args[0])) == candidate:
                        swap()
                    return real_create_file(*args)

                patches.enter_context(
                    patch.object(kernel32, "CreateFileW", side_effect=swap_before_create)
                )
            with self.assertRaises(store.StoreError) as raised:
                store.read_repository_artifact(self.repository, "artifact.txt")

        self.assertTrue(swapped)
        self.assertEqual("UNSAFE_ARTIFACT", raised.exception.code)
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir()
        self.paths = store.resolve_run(self.repository, EXECUTION_ID)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _publish_first(self) -> dict[str, object]:
        first = fixture_event()
        store.publish_initial_run(self.paths, fixture_state(1, event_hash(first)), first)
        return first

    def test_resolve_run_uses_execution_scoped_run_and_shared_evidence(self) -> None:
        self.assertEqual(
            self.repository / ".hotl" / "runs" / EXECUTION_ID,
            self.paths.root,
        )
        self.assertEqual(self.paths.root / "state.json", self.paths.state)
        self.assertEqual(self.paths.root / "events.jsonl", self.paths.events)
        self.assertEqual(self.repository / ".hotl" / "evidence", self.paths.evidence)
        self.assertEqual(self.paths.root / "transactions", self.paths.transactions)
        self.assertEqual(self.paths.root / ".lock", self.paths.lock)

    def test_resolve_run_rejects_invalid_execution_identity(self) -> None:
        with self.assertRaisesRegex(store.StoreError, "execution") as raised:
            store.resolve_run(self.repository, "../escape")
        self.assertEqual("INVALID_EXECUTION_ID", raised.exception.code)

    def test_content_addressed_evidence_is_idempotent(self) -> None:
        digest1 = store.store_evidence(self.paths, b"proof\n")
        digest2 = store.store_evidence(self.paths, b"proof\n")
        self.assertEqual(digest1, digest2)
        self.assertEqual(
            b"proof\n",
            (self.paths.evidence / digest1.removeprefix("sha256:")).read_bytes(),
        )

    def test_concurrent_lock_excludes_second_owner(self) -> None:
        self.paths.root.mkdir(parents=True)
        entered = threading.Event()
        release = threading.Event()

        def owner() -> None:
            with store.run_lock(self.paths.lock):
                entered.set()
                release.wait(timeout=5)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(owner)
            self.assertTrue(entered.wait(timeout=5))
            with self.assertRaises(store.StoreError) as raised:
                with store.run_lock(self.paths.lock):
                    self.fail("contending owner entered the critical section")
            self.assertEqual("RUN_LOCKED", raised.exception.code)
            self.assertTrue(self.paths.lock.is_file())
            release.set()
            future.result(timeout=5)
        self.assertFalse(self.paths.lock.exists())

    def test_batch_append_preserves_exact_prefix_count_and_witnesses(self) -> None:
        first = self._publish_first()
        before = self.paths.events.read_bytes()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")
        third = fixture_event(3, event_hash(second), "EVT-000000000003")
        state = fixture_state(3, event_hash(third))

        store.append_events(self.paths, [second, third], state, {})

        after = self.paths.events.read_bytes()
        self.assertEqual(before, after[: len(before)])
        self.assertEqual(2, after[len(before) :].count(b"\n"))
        self.assertEqual(3, len(store.load_events(self.paths)))
        persisted = json.loads(self.paths.state.read_text(encoding="utf-8"))
        self.assertEqual(3, persisted["event_count"])
        self.assertEqual(event_hash(third), persisted["head_event_hash"])

    def test_initial_batch_publishes_complete_chain_and_state_atomically(self) -> None:
        first = fixture_event()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")

        store.publish_initial_events(
            self.paths,
            fixture_state(2, event_hash(second)),
            [first, second],
            {},
        )

        self.assertEqual([first, second], store.load_events(self.paths))
        persisted = json.loads(self.paths.state.read_text(encoding="utf-8"))
        self.assertEqual(2, persisted["event_count"])
        self.assertEqual(event_hash(second), persisted["head_event_hash"])

    def test_invalid_initial_batch_leaves_no_run(self) -> None:
        first = fixture_event()
        broken = fixture_event(2, DIGEST_ONE, "EVT-000000000002")

        with self.assertRaises(store.StoreError):
            store.publish_initial_events(
                self.paths,
                fixture_state(2, event_hash(broken)),
                [first, broken],
                {},
            )

        self.assertFalse(self.paths.root.exists())

    def test_append_wrapper_publishes_one_event(self) -> None:
        first = self._publish_first()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")
        store.append_event(
            self.paths,
            second,
            fixture_state(2, event_hash(second)),
            {},
        )
        self.assertEqual([first, second], store.load_events(self.paths))

    def test_witness_mismatch_rejects_append_before_publication(self) -> None:
        first = self._publish_first()
        old_events = self.paths.events.read_bytes()
        old_state = self.paths.state.read_bytes()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")

        with self.assertRaises(store.StoreError) as raised:
            store.append_events(
                self.paths,
                [second],
                fixture_state(1, event_hash(first)),
                {},
            )

        self.assertEqual("INVALID_STATE_WITNESS", raised.exception.code)
        self.assertEqual(old_events, self.paths.events.read_bytes())
        self.assertEqual(old_state, self.paths.state.read_bytes())

    def test_interrupted_state_publication_preserves_prior_state(self) -> None:
        first = self._publish_first()
        prior_state = self.paths.state.read_bytes()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")
        replace = os.replace

        def interrupt_state(source: object, destination: object) -> None:
            if Path(destination) == self.paths.state:
                raise KeyboardInterrupt("simulated interruption")
            replace(source, destination)

        with patch.object(store.os, "replace", side_effect=interrupt_state):
            with self.assertRaises(KeyboardInterrupt):
                store.append_events(
                    self.paths,
                    [second],
                    fixture_state(2, event_hash(second)),
                    {},
                )

        self.assertEqual(prior_state, self.paths.state.read_bytes())
        self.assertNotEqual([], list(self.paths.transactions.iterdir()))
        status = store.recovery_status(self.paths)
        self.assertTrue(status["recovery_required"])
        self.assertIn("ORPHAN_TRANSACTION", status["reasons"])

    def test_append_publishes_verified_content_addressed_artifacts(self) -> None:
        first = self._publish_first()
        content = b"command output\n"
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")

        store.append_events(
            self.paths,
            [second],
            fixture_state(2, event_hash(second)),
            {digest: content},
        )

        self.assertEqual(content, (self.paths.evidence / digest[7:]).read_bytes())

    def test_directory_open_failure_aborts_append_as_write_failed(self) -> None:
        first = self._publish_first()
        prior_state = self.paths.state.read_bytes()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")
        open_file = os.open

        def fail_directory_open(
            path: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
        ) -> int:
            if Path(path).is_dir():
                raise OSError(errno.EIO, "injected directory open failure")
            if dir_fd is None:
                return open_file(path, flags, mode)
            return open_file(path, flags, mode, dir_fd=dir_fd)

        with patch.object(store.os, "open", side_effect=fail_directory_open):
            with self.assertRaises(store.StoreError) as raised:
                store.append_event(
                    self.paths,
                    second,
                    fixture_state(2, event_hash(second)),
                    {},
                )

        self.assertEqual("WRITE_FAILED", raised.exception.code)
        self.assertEqual(prior_state, self.paths.state.read_bytes())
        self.assertNotEqual([], list(self.paths.transactions.iterdir()))

    def test_directory_fsync_failure_aborts_append_as_write_failed(self) -> None:
        first = self._publish_first()
        prior_state = self.paths.state.read_bytes()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")
        surrogate = self.repository / "directory-sync-handle"
        surrogate.write_bytes(b"")
        open_file = os.open
        sync_file = os.fsync
        directory_descriptors: set[int] = set()

        def open_directory_as_file(
            path: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
        ) -> int:
            if Path(path).is_dir():
                descriptor = open_file(surrogate, os.O_RDONLY)
                directory_descriptors.add(descriptor)
                return descriptor
            if dir_fd is None:
                return open_file(path, flags, mode)
            return open_file(path, flags, mode, dir_fd=dir_fd)

        def fail_directory_fsync(descriptor: int) -> None:
            if descriptor in directory_descriptors:
                raise OSError(errno.EIO, "injected directory fsync failure")
            sync_file(descriptor)

        with (
            patch.object(store.os, "open", side_effect=open_directory_as_file),
            patch.object(store.os, "fsync", side_effect=fail_directory_fsync),
        ):
            with self.assertRaises(store.StoreError) as raised:
                store.append_event(
                    self.paths,
                    second,
                    fixture_state(2, event_hash(second)),
                    {},
                )

        self.assertEqual("WRITE_FAILED", raised.exception.code)
        self.assertEqual(prior_state, self.paths.state.read_bytes())
        self.assertNotEqual([], list(self.paths.transactions.iterdir()))

    def test_staged_evidence_directory_is_synced_before_publication(self) -> None:
        first = self._publish_first()
        prior_state = self.paths.state.read_bytes()
        content = b"nested evidence\n"
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")
        open_file = os.open

        def fail_nested_evidence_directory_open(
            path: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
        ) -> int:
            candidate = Path(path)
            if (
                candidate.is_dir()
                and candidate.name == "evidence"
                and candidate.parent.parent == self.paths.transactions
            ):
                raise OSError(errno.EIO, "injected staged evidence directory failure")
            if dir_fd is None:
                return open_file(path, flags, mode)
            return open_file(path, flags, mode, dir_fd=dir_fd)

        with patch.object(
            store.os, "open", side_effect=fail_nested_evidence_directory_open
        ):
            with self.assertRaises(store.StoreError) as raised:
                store.append_event(
                    self.paths,
                    second,
                    fixture_state(2, event_hash(second)),
                    {digest: content},
                )

        self.assertEqual("WRITE_FAILED", raised.exception.code)
        self.assertEqual(prior_state, self.paths.state.read_bytes())
        self.assertFalse((self.paths.evidence / digest[7:]).exists())
        self.assertNotEqual([], list(self.paths.transactions.iterdir()))

    def test_hash_chain_truncation_is_recovery_required(self) -> None:
        first = self._publish_first()
        second = fixture_event(2, event_hash(first), "EVT-000000000002")
        store.append_event(
            self.paths,
            second,
            fixture_state(2, event_hash(second)),
            {},
        )
        self.paths.events.write_bytes(self.paths.events.read_bytes().splitlines(keepends=True)[0])

        with self.assertRaises(store.StoreError) as raised:
            store.load_events(self.paths)

        self.assertEqual("RECOVERY_REQUIRED", raised.exception.code)
        status = store.recovery_status(self.paths)
        self.assertTrue(status["recovery_required"])
        self.assertIn("LOG_WITNESS_MISMATCH", status["reasons"])

    def test_orphan_transaction_forces_recovery_without_cleanup(self) -> None:
        orphan = self.paths.transactions / "append-orphan"
        orphan.mkdir(parents=True)

        first = store.recovery_status(self.paths)
        second = store.recovery_status(self.paths)

        self.assertTrue(first["recovery_required"])
        self.assertEqual([], first["next_commands"])
        self.assertEqual(["append-orphan"], first["orphan_transactions"])
        self.assertIn("ORPHAN_TRANSACTION", first["reasons"])
        self.assertEqual(first, second)
        self.assertTrue(orphan.is_dir())

    def test_missing_state_and_non_directory_evidence_are_classified(self) -> None:
        self.paths.root.mkdir(parents=True)
        self.paths.events.write_bytes(b"{}\n")
        self.paths.evidence.parent.mkdir(parents=True, exist_ok=True)
        self.paths.evidence.write_bytes(b"not a directory")

        status = store.recovery_status(self.paths)

        self.assertTrue(status["recovery_required"])
        self.assertIn("MISSING_STATE", status["reasons"])
        self.assertIn("INVALID_EVIDENCE_ROOT", status["reasons"])
        self.assertEqual([], status["next_commands"])

    def test_initial_publication_rejects_non_directory_evidence_as_recovery(self) -> None:
        self.paths.evidence.parent.mkdir(parents=True)
        self.paths.evidence.write_bytes(b"not a directory")
        first = fixture_event()

        with self.assertRaises(store.StoreError) as raised:
            store.publish_initial_run(
                self.paths,
                fixture_state(1, event_hash(first)),
                first,
            )

        self.assertEqual("RECOVERY_REQUIRED", raised.exception.code)
        self.assertEqual(b"not a directory", self.paths.evidence.read_bytes())

    def test_evidence_object_link_is_recovery_required(self) -> None:
        self._publish_first()
        outside = Path(self.temporary.name) / "outside-object"
        outside.write_bytes(b"outside")
        linked_object = self.paths.evidence / ("0" * 64)
        try:
            linked_object.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")

        status = store.recovery_status(self.paths)

        self.assertTrue(status["recovery_required"])
        self.assertIn("LINK_OR_REPARSE_POINT", status["reasons"])
        self.assertTrue(linked_object.is_symlink())

    def test_state_link_is_classified_without_following_or_cleanup(self) -> None:
        self._publish_first()
        outside = Path(self.temporary.name) / "outside-state"
        outside.write_bytes(self.paths.state.read_bytes())
        self.paths.state.unlink()
        try:
            self.paths.state.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")

        status = store.recovery_status(self.paths)

        self.assertTrue(status["recovery_required"])
        self.assertIn("LINK_OR_REPARSE_POINT", status["reasons"])
        self.assertTrue(self.paths.state.is_symlink())

    def test_symlink_or_reparse_evidence_root_is_rejected_and_preserved(self) -> None:
        target = Path(self.temporary.name) / "outside-evidence"
        target.mkdir()
        self.paths.evidence.parent.mkdir(parents=True)
        try:
            self.paths.evidence.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")

        status = store.recovery_status(self.paths)

        self.assertTrue(status["recovery_required"])
        self.assertIn("LINK_OR_REPARSE_POINT", status["reasons"])
        with self.assertRaises(store.StoreError) as raised:
            store.store_evidence(self.paths, b"must not traverse\n")
        self.assertEqual("RECOVERY_REQUIRED", raised.exception.code)
        self.assertTrue(self.paths.evidence.is_symlink())
        self.assertEqual([], list(target.iterdir()))


if __name__ == "__main__":
    unittest.main()
