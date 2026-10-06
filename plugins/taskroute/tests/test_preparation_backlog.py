"""Offline preparation blockers, immutable capture and visible persistence failures."""

import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import backlog
import test_repository_task as fixtures


class PreparationCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.run = self.root / "requested-run"
        self.db = self.root / "backlog.sqlite3"

    def capture(self, error=None, **options):
        return backlog.capture_preparation(
            self.project,
            self.run,
            error or UnicodeDecodeError("utf-8", b"\xcfprivate-source", 0, 1, "private-detail"),
            project_id="project-a",
            task_id="task-a",
            path=self.db,
            **options,
        )

    def test_binary_failure_has_private_evidence_and_no_run_or_manifest(self):
        result = self.capture()
        self.assertEqual(result["status"], "SAVED")
        self.assertFalse(self.run.exists())
        evidence = Path(result["evidence"])
        self.assertEqual(evidence.stat().st_mode & 0o777, 0o600)
        payload = json.loads(evidence.read_text())
        self.assertEqual(payload["model_calls"], 0)
        self.assertFalse(payload["automatic_retry"])
        row = backlog.show(self.db, "preparation.non_utf8_input")[0]
        self.assertEqual(row["observed"], "NON_UTF8_INPUT")
        self.assertEqual(row["run_id"], backlog.opaque(self.run))
        for raw in [b"private-source", b"private-detail", str(self.project).encode()]:
            self.assertNotIn(raw, self.db.read_bytes())
            self.assertNotIn(raw, evidence.read_bytes())

    def test_replay_and_concurrent_capture_save_one_occurrence(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.capture(), range(8)))
        self.assertTrue(all(r["status"] == "SAVED" for r in results))
        row = backlog.listing(self.db)[0]
        self.assertEqual((row["occurrences"], row["independent_tasks"]), (1, 1))
        self.assertEqual(len({r["evidence_sha256"] for r in results}), 1)

    def test_changed_failure_cannot_overwrite_same_event_evidence(self):
        saved = self.capture()
        target = Path(saved["evidence"])
        original = target.read_bytes()
        conflict = self.capture(ValueError("INVALID_CONTRACT"))
        self.assertEqual(conflict["status"], "NOT_SAVED")
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(len(backlog.listing(self.db)), 1)

    def test_database_failure_keeps_evidence_for_exact_explicit_replay(self):
        with patch.object(
            backlog, "record", side_effect=sqlite3.OperationalError("private-detail")
        ):
            result = self.capture()
        self.assertEqual(result["status"], "NOT_SAVED")
        self.assertEqual(result["error_type"], "OperationalError")
        target = Path(result["evidence"])
        original = target.read_bytes()
        self.assertFalse(self.db.exists())
        self.assertEqual(self.capture()["status"], "SAVED")
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(backlog.listing(self.db)[0]["occurrences"], 1)

    def test_evidence_failure_is_visible_and_does_not_create_database(self):
        with patch.object(
            backlog.tempfile, "mkstemp", side_effect=PermissionError("private-detail")
        ):
            result = self.capture()
        self.assertEqual(result["status"], "NOT_SAVED")
        self.assertEqual(result["error_type"], "PermissionError")
        self.assertNotIn("private-detail", json.dumps(result))
        self.assertFalse(self.db.exists())
        self.assertFalse(self.run.exists())

    def test_existing_run_and_invalid_identifiers_are_not_modified_or_copied(self):
        self.run.mkdir()
        sentinel = self.run / "manifest.json"
        sentinel.write_bytes(b"private-existing-run")
        result = backlog.capture_preparation(
            self.project,
            self.run,
            ValueError("RUN_DIRECTORY_ALREADY_EXISTS"),
            project_id="../private-project",
            task_id="private/task",
            path=self.db,
        )
        self.assertEqual(result["status"], "SAVED")
        self.assertEqual(sentinel.read_bytes(), b"private-existing-run")
        self.assertEqual(list(self.run.iterdir()), [sentinel])
        row = backlog.listing(self.db)[0]
        self.assertEqual(row["independent_tasks"], 0)
        payload = Path(result["evidence"]).read_text()
        self.assertNotIn("private-project", payload)
        self.assertNotIn("private/task", payload)


@unittest.skipUnless(sys.platform == "darwin", "macOS preparation required")
class PreparationEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.RepositoryTests(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        c = self.case
        self.spec = c.base / "task.json"
        self.bin = c.base / "bin"
        self.bin.mkdir()
        self.invoked = c.base / "provider-invoked"
        binary = self.bin / "claude"
        binary.write_text("#!/bin/sh\ntouch " + shlex.quote(str(self.invoked)) + "\nexit 97\n")
        binary.chmod(0o700)
        self.env = dict(
            os.environ,
            PATH=str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            TASKROUTE_BACKLOG_DB=str(c.backlog_db),
        )

    def binary_input(self):
        c = self.case
        (c.project / "native.node").write_bytes(b"\xcfprivate-source")
        c.spec["files"].append("native.node")
        c.spec["check_inputs"].append("native.node")
        self.spec.write_text(json.dumps(c.spec))

    def cli(self, action="prepare", *, db=None):
        c = self.case
        command = [sys.executable, "-B", str(fixtures.SCRIPTS / "taskroute.py"), action]
        if action == "preflight":
            command.append(str(c.run))
        else:
            command.extend(
                [
                    str(self.spec),
                    "--project",
                    str(c.project),
                    "--run",
                    str(c.run),
                    "--project-id",
                    "project-a",
                    "--task-id",
                    "task-a",
                ]
            )
        env = dict(self.env)
        if db is not None:
            env["TASKROUTE_BACKLOG_DB"] = str(db)
        proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        packet = json.loads(proc.stdout)
        self.assertEqual(packet["status"], "BLOCKED")
        self.assertEqual(packet["model_calls"], 0)
        self.assertIsNone(packet["accepted_model"])
        self.assertFalse(packet["automatic_retry"])
        self.assertFalse(self.invoked.exists())
        return packet

    def test_real_prepare_and_deliver_binary_blockers_are_captured_once(self):
        self.binary_input()
        for action in ["prepare", "prepare", "deliver"]:
            packet = self.cli(action)
            self.assertEqual(packet["error_type"], "UnicodeDecodeError")
            self.assertEqual(packet["backlog"]["status"], "SAVED")
            self.assertFalse(self.case.run.exists())
        row = backlog.listing(self.case.backlog_db)[0]
        self.assertEqual(row["issue_key"], "preparation.non_utf8_input")
        self.assertEqual(row["occurrences"], 1)
        self.assertEqual((self.case.project / "native.node").read_bytes(), b"\xcfprivate-source")

    def test_cli_database_failure_preserves_the_primary_binary_blocker(self):
        self.binary_input()
        invalid_db = self.case.base / "database-directory"
        invalid_db.mkdir()
        packet = self.cli(db=invalid_db)
        self.assertEqual(packet["error_type"], "UnicodeDecodeError")
        self.assertIn("utf-8", packet["reason"])
        self.assertEqual(packet["backlog"]["status"], "NOT_SAVED")
        self.assertTrue(Path(packet["backlog"]["evidence"]).is_file())
        self.assertFalse(self.case.run.exists())

    def test_manifest_free_preflight_is_captured_without_inventing_project(self):
        packet = self.cli("preflight")
        self.assertEqual(packet["stage"], "preflight")
        self.assertEqual(packet["backlog"]["status"], "SAVED")
        self.assertFalse(self.case.run.exists())
        row = backlog.show(self.case.backlog_db, "preflight.input_not_found")[0]
        self.assertEqual(row["project_id"], "unknown")
        self.assertIsNone(row["task_id"])

    def test_late_preflight_failure_saves_run_receipt_and_registry_observation(self):
        with (
            patch.object(
                fixtures.collector, "preflight", side_effect=ValueError("EXECUTOR_NOT_READY")
            ),
            patch.object(fixtures.taskroute.subprocess, "run") as launch,
        ):
            with self.assertRaisesRegex(ValueError, "EXECUTOR_NOT_READY") as caught:
                self.case.prepare()
        launch.assert_not_called()
        packet = caught.exception.taskroute_failure
        self.assertEqual(packet["stage"], "preflight")
        self.assertEqual(packet["backlog"]["status"], "SAVED")
        for name in ["preflight.json", "packet-error.json"]:
            self.assertEqual(json.loads((self.case.run / name).read_text()), packet)
        self.assertEqual(backlog.listing(self.case.backlog_db)[0]["occurrences"], 1)

    def test_run_receipt_write_failure_does_not_replace_primary_preflight_error(self):
        original = Path.write_text

        def write(path, text, *args, **kwargs):
            if path.name == "packet-error.json":
                raise PermissionError("private-detail")
            return original(path, text, *args, **kwargs)

        with (
            patch.object(
                fixtures.collector, "preflight", side_effect=ValueError("EXECUTOR_NOT_READY")
            ),
            patch.object(Path, "write_text", write),
        ):
            with self.assertRaisesRegex(ValueError, "EXECUTOR_NOT_READY") as caught:
                self.case.prepare()
        packet = caught.exception.taskroute_failure
        self.assertEqual(packet["backlog"]["status"], "SAVED")
        self.assertEqual(packet["run_receipt"]["status"], "NOT_SAVED")

    def test_successful_preparation_creates_no_failure_database(self):
        self.case.prepare()
        self.assertFalse(self.case.backlog_db.exists())
        self.assertFalse(Path(str(self.case.backlog_db) + ".evidence").exists())


if __name__ == "__main__":
    unittest.main()
