"""Bounded same-reviewer protocol correction, without model calls."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import review_gate


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.m = dict(
            acceptance=[dict(id=i, text=i, evidence=["review"]) for i in ["AC1", "AC2"]],
            non_goals=[dict(id="NG1", text="Keep scope")],
        )
        (self.root / "manifest.json").write_text(json.dumps(self.m))
        (self.root / "originals.json").write_text("{}")
        mock = patch("repository_task.snapshot", return_value={"file.txt": "candidate"})
        self.snapshot = mock.start()
        self.addCleanup(mock.stop)
        self.good = dict(
            verdict="APPROVE",
            acceptance=[
                dict(id=i, status="MET", evidence=["review"], detail="Inspected actual behavior")
                for i in ["AC1", "AC2"]
            ],
            non_goals=[dict(id="NG1", status="KEPT", detail="Scope preserved")],
        )

    def text(self, value):
        return "TASKROUTE_REVIEW: " + json.dumps(value)

    def event(self, value, agent="reviewer-id"):
        return dict(
            hook_event_name="SubagentStop",
            agent_type="reviewer",
            agent_id=agent,
            last_assistant_message=self.text(value),
        )

    def test_incomplete_then_complete_same_reviewer(self):
        bad = dict(self.good, acceptance=self.good["acceptance"][:1])
        first = review_gate.handle(self.root, self.event(bad))
        self.assertEqual(first["decision"], "block")
        self.assertIn("AC2", first["reason"])
        self.assertEqual(review_gate.handle(self.root, self.event(self.good)), {})
        text = self.text(bad) + "\n" + self.text(self.good)
        self.assertEqual(review_gate.accepted_review(self.root, self.m, text), self.text(self.good))

    def test_second_malformed_stops_and_cannot_be_accepted(self):
        bad = dict(self.good, acceptance=[])
        review_gate.handle(self.root, self.event(bad))
        self.assertEqual(review_gate.handle(self.root, self.event(bad)), {})
        with self.assertRaisesRegex(ValueError, "REJECTED"):
            review_gate.accepted_review(self.root, self.m, self.text(bad))
        with self.assertRaisesRegex(ValueError, "CEILING"):
            review_gate.handle(self.root, self.event(self.good))

    def test_mixed_arrays_feedback_identifies_exact_schema(self):
        bad = dict(verdict="APPROVE", acceptance=self.good["acceptance"] + self.good["non_goals"])
        result = review_gate.handle(self.root, self.event(bad))
        self.assertEqual(result["decision"], "block")
        self.assertIn("SEPARATE required array", result["reason"])
        self.assertIn('"non_goals": [', result["reason"])
        self.assertIn("Do not put NG records in acceptance", result["reason"])

    def test_malformed_negative_report_is_not_format_retried(self):
        bad = dict(verdict="CHANGES", acceptance=[])
        self.assertEqual(review_gate.handle(self.root, self.event(bad)), {})

    def test_negative_semantic_review_is_not_retried(self):
        bad = dict(self.good, verdict="CHANGES")
        self.assertEqual(review_gate.handle(self.root, self.event(bad)), {})
        with self.assertRaisesRegex(ValueError, "REJECTED"):
            review_gate.accepted_review(self.root, self.m, self.text(bad))

    def test_identity_change_and_missing_evidence_fail(self):
        review_gate.handle(self.root, self.event(dict(self.good, acceptance=[])))
        with self.assertRaisesRegex(ValueError, "IDENTITY"):
            review_gate.handle(self.root, self.event(self.good, agent="other"))
        with self.assertRaisesRegex(ValueError, "MISSING"):
            review_gate.handle(
                self.root, dict(hook_event_name="SubagentStop", agent_type="reviewer")
            )

    def test_stale_or_unobserved_review_cannot_be_accepted(self):
        review_gate.handle(self.root, self.event(self.good))
        with self.assertRaisesRegex(ValueError, "STREAM_MISMATCH"):
            review_gate.accepted_review(self.root, self.m, "unrelated")
        self.snapshot.return_value = {"file.txt": "changed"}
        with self.assertRaisesRegex(ValueError, "STALE"):
            review_gate.accepted_review(self.root, self.m, self.text(self.good))

    def enable_repair(self):
        self.m.update(review_repair_enabled=True, workspace=str(self.root))
        (self.root / "manifest.json").write_text(json.dumps(self.m))

    def changed_check(self):
        from repository_task import digest

        self.snapshot.return_value = {"file.txt": "repaired"}
        (self.root / "checks.json").write_text(
            json.dumps(dict(status="PASS", file_hashes={"file.txt": digest("repaired")}))
        )

    def test_one_author_repair_then_fresh_review(self):
        self.enable_repair()
        bad = dict(self.good, verdict="CHANGES")
        review_gate.handle(self.root, self.event(bad))
        self.assertTrue(review_gate.repair_window(self.root, self.m, 1))
        self.assertFalse(review_gate.repair_window(self.root, self.m, 2))
        with self.assertRaisesRegex(ValueError, "REJECTED"):
            review_gate.accepted_review(self.root, self.m, self.text(bad))
        self.changed_check()
        review_gate.handle(self.root, self.event(self.good, agent="fresh-reviewer"))
        self.assertFalse(review_gate.repair_window(self.root, self.m, 1))
        self.assertEqual(
            review_gate.accepted_review(self.root, self.m, self.text(self.good)),
            self.text(self.good),
        )

    def test_negative_rereview_and_third_reviewer_stop(self):
        self.enable_repair()
        bad = dict(self.good, verdict="CHANGES")
        review_gate.handle(self.root, self.event(bad))
        self.changed_check()
        review_gate.handle(self.root, self.event(bad, agent="fresh-reviewer"))
        with self.assertRaisesRegex(ValueError, "REJECTED"):
            review_gate.accepted_review(self.root, self.m, self.text(bad))
        with self.assertRaisesRegex(ValueError, "CEILING"):
            review_gate.handle(self.root, self.event(self.good, agent="third"))

    def test_approval_or_malformed_negative_never_unlocks_writes(self):
        self.enable_repair()
        review_gate.handle(self.root, self.event(self.good))
        self.assertFalse(review_gate.repair_window(self.root, self.m, 1))
        (self.root / "review-gate.json").unlink()
        review_gate.handle(self.root, self.event(dict(verdict="CHANGES", acceptance=[])))
        self.assertFalse(review_gate.repair_window(self.root, self.m, 1))

    def test_changed_but_unchecked_rereview_rejected(self):
        self.enable_repair()
        review_gate.handle(self.root, self.event(dict(self.good, verdict="CHANGES")))
        self.changed_check()
        (self.root / "checks.json").write_text(json.dumps(dict(status="PASS", file_hashes={})))
        with self.assertRaisesRegex(ValueError, "CHECKED"):
            review_gate.handle(self.root, self.event(self.good, agent="fresh-reviewer"))


if __name__ == "__main__":
    unittest.main()
