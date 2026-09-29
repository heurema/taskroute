"""Capture-only backlog behavior; no model calls or user state in tests."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import backlog


class BacklogTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "backlog.sqlite3"
        self.item = dict(
            issue_key="review.false-approval",
            project_id="project-a",
            task_id="task-1",
            run_id="run-1",
            event_id="acceptance",
            stage="lead",
            severity="high",
            expected="preserve-valid-inputs",
            observed="over-rejection",
            evidence="lead-acceptance.json",
            version="v-test",
        )

    def test_duplicate_and_retry_do_not_inflate_independent_tasks(self):
        backlog.record(self.db, self.item)
        backlog.record(self.db, self.item)
        backlog.record(self.db, dict(self.item, run_id="retry-2"))
        row = backlog.listing(self.db)[0]
        self.assertEqual((row["occurrences"], row["independent_tasks"], row["projects"]), (2, 1, 1))
        backlog.record(self.db, dict(self.item, project_id="project-b", task_id="task-2"))
        row = backlog.listing(self.db)[0]
        self.assertEqual((row["occurrences"], row["independent_tasks"], row["projects"]), (3, 2, 2))

    def test_show_retains_codes_and_version(self):
        backlog.record(self.db, self.item)
        row = backlog.show(self.db, self.item["issue_key"])[0]
        self.assertEqual(row["observed"], "over-rejection")
        self.assertEqual(row["version"], "v-test")
        self.assertEqual(backlog.show(self.db, "missing.issue"), [])

    def test_unknown_task_not_counted_as_independent(self):
        backlog.record(self.db, dict(self.item, task_id=None))
        self.assertEqual(backlog.listing(self.db)[0]["independent_tasks"], 0)

    def test_conflicting_event_is_not_regrouped(self):
        backlog.record(self.db, self.item)
        with self.assertRaisesRegex(ValueError, "CONFLICT"):
            backlog.record(self.db, dict(self.item, issue_key="other.issue"))
        self.assertEqual(len(backlog.listing(self.db)), 1)

    def test_severity_precedes_frequency(self):
        for i in range(4):
            backlog.record(
                self.db, dict(self.item, task_id=f"task-{i}", run_id=f"run-{i}", severity="low")
            )
        backlog.record(
            self.db,
            dict(self.item, issue_key="scope.escape", run_id="critical", severity="critical"),
        )
        self.assertEqual(backlog.listing(self.db)[0]["issue_key"], "scope.escape")

    def test_concurrent_duplicate_writers(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: backlog.record(self.db, self.item), range(12)))
        self.assertEqual(backlog.listing(self.db)[0]["occurrences"], 1)

    def test_raw_paths_and_extra_content_rejected(self):
        with self.assertRaisesRegex(ValueError, "OPAQUE"):
            backlog.record(self.db, dict(self.item, evidence="/outside/private.txt"))
        with self.assertRaisesRegex(ValueError, "FIELDS"):
            backlog.record(self.db, dict(self.item, prompt="private source"))

    def manifest(self):
        (self.root / "manifest.json").write_text(
            json.dumps(
                dict(
                    project_root=str(self.root),
                    backlog_context=dict(project_id="project-a", task_id="task-1"),
                )
            )
        )

    def test_recovered_format_failure_captured_after_success(self):
        self.manifest()
        (self.root / "review-gate.json").write_text(
            json.dumps(
                [dict(status="FORMAT_CORRECTION", text="sensitive raw text"), dict(status="PASS")]
            )
        )
        result = backlog.capture(self.root, dict(status="READY_FOR_LEAD_REVIEW"), self.db)
        self.assertEqual(result["status"], "SAVED")
        self.assertEqual(backlog.listing(self.db)[0]["issue_key"], "review.incomplete-report")
        self.assertNotIn(b"sensitive raw text", self.db.read_bytes())

    def test_write_failure_visible(self):
        self.manifest()
        result = backlog.capture(
            self.root, dict(status="BLOCKED", reason="TEST_FAILURE"), self.root
        )
        self.assertEqual(result["status"], "NOT_SAVED")

    def test_runner_error_is_automatically_captured(self):
        self.manifest()
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        proc = subprocess.run(
            [
                sys.executable,
                "-B",
                str(scripts / "compact_delivery_packet.py"),
                str(self.root),
                "--preflight",
            ],
            env=dict(os.environ, TASKROUTE_BACKLOG_DB=str(self.db)),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        packet = json.loads(proc.stdout)
        self.assertEqual(packet["backlog"]["status"], "SAVED")
        self.assertEqual(backlog.listing(self.db)[0]["occurrences"], 1)


if __name__ == "__main__":
    unittest.main()
