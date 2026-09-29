"""A short receipt preserves findings and fails closed on evidence gaps."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from delivery_receipt import receipt


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        (self.run / "workspace").mkdir()
        (self.run / "workspace/a").write_text("new")
        (self.run / "manifest.json").write_text(
            json.dumps(
                dict(
                    mode="repository",
                    files=["a"],
                    writable_paths=["a"],
                    acceptance=[{"id": "AC1"}],
                    non_goals=[],
                    checks=[{"name": "check"}],
                )
            )
        )
        (self.run / "originals.json").write_text(json.dumps({"a": "old"}))
        self.packet = dict(
            status="READY_FOR_LEAD_REVIEW",
            reasons=[],
            file_hashes={"a": hashlib.sha256(b"new").hexdigest()},
            reviewer_outcome=dict(
                verdict="APPROVE",
                acceptance=[
                    dict(
                        id="AC1",
                        status="MET",
                        detail="Limitation and uncertainty must remain visible.",
                    )
                ],
                non_goals=[],
            ),
            coordinator_outcome=dict(status="READY_FOR_LEAD", reason="Done, with limits"),
            worker_checks=[dict(name="check", exit_code=0)],
            independent_checks=[dict(name="check", exit_code=0)],
            diff="long code",
            reviewer_text="full detailed review",
            backlog={"status": "NOT_SAVED"},
        )

    def build(self):
        (self.run / "acceptance-packet.json").write_text(json.dumps(self.packet))
        return receipt(self.packet, self.run)

    def test_small_receipt_keeps_findings_without_claiming_astra_review(self):
        result = self.build()
        self.assertEqual(result["status"], "CLAUDE_VERIFIED")
        self.assertEqual(result["review_findings"], self.packet["reviewer_outcome"])
        self.assertEqual(result["backlog"]["status"], "NOT_SAVED")
        self.assertFalse(result["independent_astra_code_review"])
        self.assertNotIn("diff", result)
        self.assertEqual(result["changed_files"], ["a"])

    def test_unknown_or_missing_criterion_cannot_pass(self):
        for rows in [[], [dict(id="AC1", status="UNKNOWN", detail="unknown")]]:
            self.packet["reviewer_outcome"]["acceptance"] = rows
            self.assertEqual(self.build()["status"], "BLOCKED")

    def test_failed_or_missing_independent_checks_cannot_pass(self):
        for checks in [[], [dict(name="check", exit_code=2)]]:
            self.packet["independent_checks"] = checks
            self.assertEqual(self.build()["status"], "BLOCKED")

    def test_tampered_candidate_is_rejected(self):
        (self.run / "workspace/a").write_text("changed after review")
        with self.assertRaisesRegex(ValueError, "CANDIDATE_CHANGED"):
            self.build()

    def test_packet_identity_must_match_archive(self):
        self.build()
        self.packet["status"] = "BLOCKED"
        with self.assertRaisesRegex(ValueError, "PACKET_MISMATCH"):
            receipt(self.packet, self.run)
