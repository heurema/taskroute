"""Offline native stage integration; fixtures are not provider qualification."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import stage
from runtime import TransportError


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        self.run = self.base / "run"
        self.spec = self.base / "spec.json"
        self.authority = self.base / "authority.txt"
        self.authority.write_text("Synthetic fixture only; no external provider.")
        self.contract = dict(
            task="Fix fixture",
            source_ref="existing/spec",
            scope="output.txt",
            acceptance=["Output is correct; author ran check"],
            routing=dict(
                agreed=True,
                checks_available=True,
                handoff_worthwhile=True,
                reason="Bounded agreed stage",
            ),
            model="fixture-model",
            effort="medium",
            timeout_seconds=3,
            allowed_tools=["Read", "Bash(python3 check.py)"],
            instructions="Synthetic fixture. Write output.txt and check it.",
        )
        self.worker = self.base / "fake-worker"
        self.response = dict(
            is_error=False,
            result="Checked output.txt",
            modelUsage={"fixture-model": dict(inputTokens=10, outputTokens=5)},
            total_cost_usd=0.01,
        )

    def prepare(self):
        self.spec.write_text(json.dumps(self.contract))
        return stage.prepare(self.spec, self.project, self.run)

    def fake(self, prefix="", response=None, suffix=""):
        response = self.response if response is None else response
        self.worker.write_text(
            "#!"
            + sys.executable
            + "\nimport json, sys, time\nfrom pathlib import Path\n"
            + "sys.stdin.read()\n"
            + prefix
            + "\nprint("
            + repr(json.dumps(response))
            + ")\n"
            + suffix
        )
        self.worker.chmod(0o700)

    def launch(self):
        return stage.execute(self.run, self.worker, self.authority)

    def test_end_to_end_actual_subprocess_checks_acceptance_and_accounting(self):
        self.assertEqual(self.prepare()["status"], "PREPARED")
        self.fake(
            "Path('output.txt').write_text('correct'); "
            "assert Path('output.txt').read_text() == 'correct'"
        )
        result = self.launch()
        self.assertEqual(result["status"], "READY_FOR_ACCEPTANCE")
        self.assertFalse(result["full_route_usage_complete"])
        for role in stage.ROLES:
            if role == "worker":
                continue
            path = self.base / (role + ".json")
            value = dict(state="not_used", source="synthetic fixture")
            if role in ("preparation", "acceptance"):
                value.update(state="observed", tokens=dict(input=12, output=4))
            path.write_text(json.dumps(value))
            stage.observe(self.run, role, path)
        review = self.base / "review.json"
        review.write_text(
            json.dumps(
                dict(
                    verdict="accepted",
                    reviewer="independent fixture",
                    reason="Read output and ran fixture assertion",
                    criteria_met=self.contract["acceptance"],
                    evidence=[str(self.project / "output.txt")],
                )
            )
        )
        result = stage.accept(self.run, review)
        self.assertEqual(result["status"], "ACCEPTED")
        self.assertTrue(result["full_route_usage_complete"])
        self.assertEqual(result["savings"], "UNPROVEN")
        self.assertEqual(result["subscription_quota_attribution"], "UNKNOWN")
        (self.project / "output.txt").write_text("changed after acceptance")
        self.assertEqual(stage.report(self.run)["status"], "EVIDENCE_CHANGED")

    def test_cli_preparation_and_route_decision(self):
        self.contract["routing"]["handoff_worthwhile"] = False
        self.spec.write_text(json.dumps(self.contract))
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "taskroute.py"),
                "stage",
                "prepare",
                str(self.spec),
                "--project",
                str(self.project),
                "--run",
                str(self.run),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["route"], "direct")
        with self.assertRaisesRegex(ValueError, "NOT_A_DELEGATED_STAGE"):
            self.launch()
        self.assertFalse((self.run / "worker.reserved.json").exists())

    def test_unagreed_and_missing_checks_never_dispatch(self):
        facts = self.contract["routing"]
        facts["agreed"] = False
        self.assertEqual(stage.choose(facts), "clarify")
        facts.update(agreed=True, checks_available=False)
        self.assertEqual(stage.choose(facts), "blocked")
        facts["agreed"] = "true"
        with self.assertRaises(ValueError):
            stage.choose(facts)

    def test_duplicate_attempt_stops_before_new_process(self):
        self.prepare()
        self.fake()
        self.launch()
        with self.assertRaisesRegex(ValueError, "ATTEMPT_ALREADY_CONSUMED"):
            self.launch()

    def test_project_writer_marker_blocks_another_run(self):
        self.prepare()
        self.fake()
        (self.project / ".taskroute-stage.lock").write_text("other or unknown writer")
        with self.assertRaises(FileExistsError):
            self.launch()
        self.assertFalse((self.run / "worker.reserved.json").exists())

    def test_timeout_is_terminal_no_retry_and_no_acceptance(self):
        self.contract["timeout_seconds"] = 1
        self.prepare()
        self.fake("time.sleep(10)")
        result = self.launch()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["terminal"]["stop_reason"], "TIMEOUT")
        self.assertFalse((self.project / ".taskroute-stage.lock").exists())
        self.assertEqual(result["roles"]["worker"]["state"], "unknown")

    def test_failed_worker_cost_is_not_dropped(self):
        self.prepare()
        self.response["is_error"] = True
        self.fake(suffix="sys.exit(1)")
        result = self.launch()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["roles"]["worker"]["api_estimate_usd"], 0.01)
        self.assertIsNone(result["roles"]["worker"]["actual_charge_usd"])

    def test_wrong_model_never_becomes_accepted_identity(self):
        self.prepare()
        self.response["modelUsage"] = {"other-model": dict(inputTokens=10)}
        self.fake()
        result = self.launch()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertNotIn("accepted_model", result["terminal"])
        self.assertEqual(result["terminal"]["observed_models"], ["other-model"])

    def test_missing_permission_blocks(self):
        self.prepare()
        self.response["permission_denials"] = [dict(tool_name="Bash")]
        self.fake()
        self.assertEqual(self.launch()["status"], "BLOCKED")

    def test_frozen_input_tampering_blocks_before_effect(self):
        self.prepare()
        (self.run / "prompt.txt").write_text("mutated")
        with self.assertRaisesRegex(ValueError, "FROZEN_INPUT_CHANGED"):
            self.launch()
        self.assertFalse((self.run / "worker.reserved.json").exists())

    def test_missing_criteria_and_missing_evidence_cannot_accept(self):
        self.prepare()
        self.fake()
        self.launch()
        review = self.base / "review.json"
        value = dict(verdict="accepted", reviewer="fixture", reason="Inspected", criteria_met=[])
        review.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "ALL_CRITERIA_REQUIRED"):
            stage.accept(self.run, review)
        value["criteria_met"] = self.contract["acceptance"]
        review.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "REVIEW_EVIDENCE_REQUIRED"):
            stage.accept(self.run, review)

    def test_unknown_submission_is_not_running_or_retryable_claim(self):
        self.prepare()
        stage.Journal(self.run).reserve("worker")
        self.assertEqual(stage.report(self.run)["status"], "IN_PROGRESS_OR_UNKNOWN")

    def test_invalid_observation_and_duplicate_rejected(self):
        self.prepare()
        observation = self.base / "observation.json"
        observation.write_text(
            json.dumps(dict(state="observed", source="fixture", tokens=dict(input=-1)))
        )
        with self.assertRaises(ValueError):
            stage.observe(self.run, "preparation", observation)
        observation.write_text(json.dumps(dict(state="unknown", source="fixture gap")))
        stage.observe(self.run, "preparation", observation)
        with self.assertRaises(TransportError):
            stage.observe(self.run, "preparation", observation)

    def test_counter_measurement_is_partial_and_does_not_claim_quota_savings(self):
        self.prepare()
        log = self.base / "session.jsonl"
        log.write_text(
            json.dumps(dict(type="session_meta", payload=dict(id="same-session"))) + "\n"
        )

        def add(value):
            with log.open("a") as stream:
                stream.write(
                    json.dumps(
                        dict(
                            type="event_msg",
                            timestamp=str(value),
                            payload=dict(
                                type="token_count",
                                info=dict(total_token_usage=dict(input_tokens=value)),
                                rate_limits=dict(
                                    primary=dict(used_percent=30, resets_at=1000),
                                    credits=dict(balance="sensitive-balance-fixture"),
                                ),
                            ),
                        )
                    )
                    + "\n"
                )

        add(100)
        stage.snapshot(log, self.base / "before")
        add(140)
        stage.snapshot(log, self.base / "after")
        result = stage.measure(
            self.run,
            "preparation",
            self.base / "before.reserved.json",
            self.base / "after.reserved.json",
        )
        self.assertEqual(result["roles"]["preparation"]["tokens"]["input_tokens"], 40)
        self.assertFalse(result["full_route_usage_complete"])
        self.assertNotIn(
            "sensitive-balance-fixture", (self.base / "after.reserved.json").read_text()
        )
        self.assertEqual(result["subscription_quota_attribution"], "UNKNOWN")

    def test_malformed_result_preserves_consumed_attempt_and_terminal_failure(self):
        self.prepare()
        self.fake(suffix="print('truncated')")
        with self.assertRaises(ValueError):
            self.launch()
        self.assertEqual(stage.report(self.run)["status"], "BLOCKED")
        self.assertTrue((self.run / "worker.reserved.json").exists())


if __name__ == "__main__":
    unittest.main()
