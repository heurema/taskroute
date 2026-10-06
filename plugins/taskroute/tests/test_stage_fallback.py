"""Synthetic unavailable-primary handoff; no live child or provider invocation."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stage
import stage_fallback as fallback
import test_stage


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_stage.StageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare()
        self.root = self.fixture.run
        self.proof = self.fixture.base / "availability.json"
        self.value = dict(
            reason="cli_unavailable",
            confirmed=True,
            prior_effects="none",
            binary=str(self.fixture.base / "missing-cli"),
            lead="fixture",
            assessment="Confirmed missing executable before submission",
            evidence=[str(self.fixture.authority)],
        )

    def reserve(self):
        self.proof.write_text(json.dumps(self.value))
        return fallback.reserve(self.root, self.proof)

    def test_missing_cli_native_handoff_and_independent_acceptance(self):
        reserved = self.reserve()
        self.assertEqual(reserved["model"], "gpt-6.1-sol")
        self.assertEqual(reserved["fork_turns"], "none")
        agent = "/root/synthetic_fallback"
        fallback.dispatched(self.root, agent, fallback.MODEL)
        output = self.fixture.project / "output.txt"
        output.write_text("synthetic checked result")
        result = self.fixture.base / "result.json"
        result.write_text(
            json.dumps(
                dict(
                    agent=agent,
                    ended=True,
                    status="ready",
                    summary="Synthetic completed work",
                    evidence=[str(output)],
                )
            )
        )
        fallback.complete(self.root, result)
        report = stage.report(self.root)
        self.assertEqual(report["status"], "READY_FOR_ACCEPTANCE")
        self.assertIsNone(report["fallback"]["observed_backend_model"])
        review = self.fixture.base / "review.json"
        review.write_text(
            json.dumps(
                dict(
                    verdict="accepted",
                    reviewer="lead",
                    reason="Inspected",
                    criteria_met=self.fixture.contract["acceptance"],
                    evidence=[str(output)],
                )
            )
        )
        self.assertEqual(stage.accept(self.root, review)["status"], "ACCEPTED")
        output.write_text("changed")
        self.assertEqual(stage.report(self.root)["status"], "EVIDENCE_CHANGED")

    def test_unknown_primary_never_switches(self):
        stage.Journal(self.root).reserve("worker")
        self.value["reason"] = "quota_exhausted"
        with self.assertRaisesRegex(ValueError, "CLAUDE_SUBMISSION_UNKNOWN"):
            self.reserve()

    def test_generic_error_or_unresolved_effects_never_switch(self):
        self.value["reason"] = "network_error"
        with self.assertRaisesRegex(ValueError, "CONFIRMED_AVAILABILITY"):
            self.reserve()
        self.value.update(reason="quota_exhausted", prior_effects="unknown")
        with self.assertRaisesRegex(ValueError, "PRIOR_EFFECTS_UNRESOLVED"):
            self.reserve()

    def test_existing_primary_executable_cannot_be_claimed_missing(self):
        self.value["binary"] = sys.executable
        with self.assertRaisesRegex(ValueError, "CLI_NOT_CONFIRMED_MISSING"):
            self.reserve()

    def test_one_attempt_and_correct_native_selection(self):
        self.reserve()
        with self.assertRaisesRegex(ValueError, "FALLBACK_ALREADY_CONSUMED"):
            self.reserve()
        with self.assertRaisesRegex(ValueError, "SELECTION_MISMATCH"):
            fallback.dispatched(self.root, "/root/worker", "wrong-model")
        self.fixture.fake()
        with self.assertRaisesRegex(ValueError, "ATTEMPT_ALREADY_CONSUMED"):
            self.fixture.launch()

    def test_quota_after_resolved_primary_keeps_failed_usage(self):
        self.fixture.response.update(is_error=True, result="Usage limit reached")
        self.fixture.fake(suffix="sys.exit(1)")
        self.fixture.launch()
        self.value.update(reason="quota_exhausted", assessment="Terminal quota denial inspected")
        self.reserve()
        report = stage.report(self.root)
        self.assertEqual(report["roles"]["worker"]["api_estimate_usd"], 0.01)
        self.assertEqual(report["roles"]["fallback_worker"]["state"], "unknown")
        self.assertEqual(report["status"], "FALLBACK_IN_PROGRESS_OR_UNKNOWN")

    def test_timeout_cannot_be_reclassified_as_quota(self):
        stage.Journal(self.root).reserve("worker")
        stage.save(self.root, "terminal.json", dict(status="BLOCKED", stop_reason="TIMEOUT"))
        self.value["reason"] = "quota_exhausted"
        with self.assertRaisesRegex(ValueError, "CLAUDE_OUTCOME_NOT_RESOLVED"):
            self.reserve()


if __name__ == "__main__":
    unittest.main()
