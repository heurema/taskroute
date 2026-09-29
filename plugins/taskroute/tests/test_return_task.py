"""Explicit artifact-bound returns; no live provider calls."""

import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import return_task
import test_repository_task as fixtures


class ReturnTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.RepositoryTests(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.prepare()
        self.case.candidate()
        self.assertEqual(self.case.verify(), 0)
        r = self.case.run
        checks = json.loads((r / "workspace/checks.json").read_text())
        (r / "acceptance-packet.json").write_text(
            json.dumps({"file_hashes": checks["file_hashes"]})
        )
        (r / "terminal.json").write_text(json.dumps({"status": "ENDED", "exit_code": 0}))
        self.finding = self.case.base / "finding.json"
        self.finding.write_text(
            json.dumps(
                dict(
                    criterion="AC1",
                    expected="correct",
                    observed="wrong",
                    reproduction="fixture",
                    regression_files={"return.sh": "test -f message.txt\n"},
                    checks=[
                        dict(
                            name="returned finding",
                            argv=["/bin/sh", "return.sh"],
                            timeout_seconds=10,
                        )
                    ],
                )
            )
        )

    def prepare(self):
        actual = shutil.which
        with patch(
            "taskroute.shutil.which",
            side_effect=lambda n: sys.executable if n == "claude" else actual(n),
        ):
            return return_task.prepare_return(
                self.case.run, self.finding, self.case.base / "repair"
            )

    def test_preserves_contract_checks_and_rejected_candidate_as_delta_baseline(self):
        result = self.prepare()
        run = Path(result["run"])
        m = json.loads((run / "manifest.json").read_text())
        self.assertEqual((run / "workspace/message.txt").read_text(), "new\n")
        self.assertIn("return.sh", m["check_inputs"])
        self.assertEqual(m["writable_paths"], self.case.spec["writable_paths"])
        self.assertEqual(len(m["checks"]), 2)
        self.assertEqual(m["acceptance"][0]["text"], self.case.spec["acceptance"][0]["text"])
        self.assertEqual(m["non_goals"], self.case.spec["non_goals"])
        context = json.loads((run / "return-context.json").read_text())
        self.assertEqual(
            context["baseline_hashes"]["message.txt"], hashlib.sha256(b"new\n").hexdigest()
        )
        self.assertFalse((run / "live-launch.reserved.json").exists())
        with self.assertRaisesRegex(RuntimeError, "ALREADY_CONSUMED"):
            return_task.prepare_return(self.case.run, self.finding, self.case.base / "another")
        with self.assertRaisesRegex(ValueError, "RETURN_CEILING"):
            return_task.prepare_return(run, self.finding, self.case.base / "third")

    def test_return_preserves_crlf_regression_bytes(self):
        finding = json.loads(self.finding.read_text())
        finding["regression_files"]["frozen.eml"] = "header\r\n\r\nbody\r\n"
        self.finding.write_text(json.dumps(finding))
        result = self.prepare()
        run = Path(result["run"])
        self.assertEqual((run / "workspace/frozen.eml").read_bytes(), b"header\r\n\r\nbody\r\n")
        fixtures.collector.preflight(run)

    def test_rejects_changed_candidate(self):
        (self.case.run / "workspace/message.txt").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "PARENT_CANDIDATE_CHANGED"):
            self.prepare()

    def test_rejects_replacing_frozen_checks(self):
        f = json.loads(self.finding.read_text())
        f["regression_files"] = {"check.sh": "true"}
        self.finding.write_text(json.dumps(f))
        with self.assertRaisesRegex(ValueError, "RETURN_CANNOT_REPLACE_INPUTS"):
            self.prepare()
