"""Synthetic human/recorded intake tests in disposable databases, with no inference."""

import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import backlog
import feedback


def example():
    # User provenance and recorded basis are simulated classification inputs.
    fixture = Path(__file__).resolve().parent / "fixtures" / "feedback-example.txt"
    raw = fixture.read_bytes()
    return dict(
        project_id="synthetic-taskroute",
        task_id="synthetic-delivery-flow",
        run_id="synthetic-feedback-run",
        event_id="synthetic-goal-correction",
        completed=True,
        provenance="user",
        source=dict(
            reference="tests/fixtures/feedback-example.txt",
            sha256=hashlib.sha256(raw).hexdigest(),
        ),
        message=raw.decode("utf-8"),
        result="Synthetic scenario: prerequisite work continued without proving the parent delivery capability.",
        classification=dict(
            kind="correction",
            basis="recorded",
            evidence="Synthetic fixture; provenance=user and basis=recorded are simulated classification inputs, not historical owner evidence.",
        ),
        proposal=dict(
            problem="Prerequisite drift from delivery goal",
            expected="Compare actual artifacts with parent acceptance before adding prerequisites",
            target="unknown; inspect current PLAN and task artifacts",
            repair="Propose an explicit parent-gap check before the next prerequisite",
            check="Demonstrate that a proposed prerequisite unlocks a missing parent capability; reject an unrelated prerequisite",
            rollback="Discard proposal; no automatic instruction or memory edits",
        ),
    )


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "backlog.sqlite3"
        self.item = example()

    def test_synthetic_correction_proposal_and_idempotent_replay(self):
        first = feedback.ingest(self.path, self.item)
        second = feedback.ingest(self.path, copy.deepcopy(self.item))
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "SAVED")
        self.assertEqual(backlog.listing(self.path)[0]["occurrences"], 1)
        self.assertEqual(backlog.listing(self.path)[0]["independent_tasks"], 1)
        shown = feedback.inspect(self.path)[0]
        self.assertEqual(shown["details"]["input"]["source"], self.item["source"])
        self.assertIn("no change authorized", shown["details"]["proposal"]["authority"])
        self.assertEqual(shown["status"], "AVAILABLE")

    def test_conflicting_replay_preserves_original(self):
        feedback.ingest(self.path, self.item)
        self.item["message"] = "changed interpretation"
        with self.assertRaisesRegex(ValueError, "FEEDBACK_EVENT_CONFLICT"):
            feedback.ingest(self.path, self.item)
        self.assertEqual(backlog.listing(self.path)[0]["occurrences"], 1)
        self.assertNotEqual(
            feedback.inspect(self.path)[0]["details"]["input"]["message"], self.item["message"]
        )

    def test_question_new_request_quote_and_unknown_are_not_corrections(self):
        for kind in ("question", "new_request", "quoted_report", "unknown"):
            with self.subTest(kind=kind):
                self.item["event_id"] = "boundary-" + kind
                self.item["classification"]["kind"] = kind
                result = feedback.ingest(self.path, self.item)
                self.assertEqual(result["status"], "NOT_ACTIONABLE")
                self.assertEqual(result["kind"], kind)
        self.assertFalse(self.path.exists())
        self.assertEqual(len(list(Path(str(self.path) + ".evidence").glob("*.json"))), 4)

    def test_quote_and_unknown_provenance_override_claimed_correction(self):
        for provenance, kind in (("quote", "quoted_report"), ("unknown", "unknown")):
            self.item["event_id"] = "provenance-" + provenance
            self.item["provenance"] = provenance
            self.assertEqual(feedback.ingest(self.path, self.item)["kind"], kind)
        self.assertFalse(self.path.exists())

    def test_missing_context_or_classification_fails_closed(self):
        for field, value in (
            ("completed", False),
            ("source", {}),
            ("result", ""),
            ("classification", {}),
        ):
            item = copy.deepcopy(self.item)
            item[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                feedback.ingest(self.path, item)
        self.assertFalse(self.path.exists())

    def test_no_proposal_remains_unknown(self):
        self.item["proposal"] = None
        self.assertEqual(feedback.ingest(self.path, self.item)["status"], "UNKNOWN")
        self.assertFalse(self.path.exists())

    def test_second_event_same_task_counts_once_as_independent(self):
        feedback.ingest(self.path, self.item)
        self.item["event_id"] = "another-correction"
        feedback.ingest(self.path, self.item)
        listing = backlog.listing(self.path)[0]
        self.assertEqual(listing["occurrences"], 2)
        self.assertEqual(listing["independent_tasks"], 1)

    def test_failed_database_save_visible_then_exact_replay_recovers(self):
        with patch.object(
            backlog, "record", side_effect=sqlite3.OperationalError("fixture unavailable")
        ):
            self.assertEqual(feedback.ingest(self.path, self.item)["status"], "NOT_SAVED")
        self.assertEqual(feedback.ingest(self.path, self.item)["status"], "SAVED")

    def test_missing_sidecar_visible(self):
        saved = feedback.ingest(self.path, self.item)
        Path(saved["evidence"]).unlink()
        self.assertEqual(feedback.inspect(self.path)[0]["status"], "EVIDENCE_UNAVAILABLE")

    def test_conflict_cannot_be_hidden_by_reclassification(self):
        feedback.ingest(self.path, self.item)
        self.item["classification"]["kind"] = "question"
        with self.assertRaisesRegex(ValueError, "FEEDBACK_EVENT_CONFLICT"):
            feedback.ingest(self.path, self.item)

    def test_changed_sidecar_is_unavailable(self):
        saved = feedback.ingest(self.path, self.item)
        target = Path(saved["evidence"])
        value = json.loads(target.read_text())
        value["input"]["message"] = "tampered"
        target.write_text(json.dumps(value))
        self.assertEqual(feedback.inspect(self.path)[0]["status"], "EVIDENCE_UNAVAILABLE")

    def test_non_actionable_event_identity_cannot_be_reclassified(self):
        for kind in ("question", "new_request", "quoted_report", "unknown"):
            with self.subTest(kind=kind):
                item = copy.deepcopy(self.item)
                item["event_id"] = "first-" + kind
                item["classification"]["kind"] = kind
                first = feedback.ingest(self.path, item)
                self.assertEqual(first, feedback.ingest(self.path, item))
                self.assertTrue(Path(first["evidence"]).is_file())
                item["classification"]["kind"] = "correction"
                with self.assertRaisesRegex(ValueError, "FEEDBACK_EVENT_CONFLICT"):
                    feedback.ingest(self.path, item)
        self.assertFalse(self.path.exists())

    def test_missing_proposal_identity_cannot_be_reinterpreted(self):
        item = copy.deepcopy(self.item)
        item["proposal"] = None
        first = feedback.ingest(self.path, item)
        self.assertEqual(first["status"], "UNKNOWN")
        self.assertEqual(first, feedback.ingest(self.path, item))
        with self.assertRaisesRegex(ValueError, "FEEDBACK_EVENT_CONFLICT"):
            feedback.ingest(self.path, self.item)
        self.assertFalse(self.path.exists())

    def test_cli_end_to_end(self):
        source = self.path.parent / "input.json"
        source.write_text(json.dumps(self.item))
        for _ in range(2):
            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "taskroute.py"),
                    "feedback-ingest",
                    str(source),
                    "--db",
                    str(self.path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        shown = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS / "taskroute.py"),
                "feedback-show",
                "--db",
                str(self.path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(len(json.loads(shown.stdout)), 1)


if __name__ == "__main__":
    unittest.main()
