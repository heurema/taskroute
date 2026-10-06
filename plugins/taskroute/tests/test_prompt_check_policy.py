"""Real offline preparation and check-budget compatibility; no provider calls."""

import contextlib
import io
import json
import re
import sys
import unittest
from unittest.mock import patch

import test_repository_task as fixtures


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox required")
class PromptPolicyTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.RepositoryTests(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def prepare_cli(self, *options):
        c = self.case
        spec = c.base / "task.json"
        spec.write_text(json.dumps(c.spec))
        argv = [
            "taskroute",
            "prepare",
            str(spec),
            "--project",
            str(c.project),
            "--run",
            str(c.run),
            *options,
        ]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(fixtures.taskroute.main(), 0)
        self.assertEqual(json.loads(out.getvalue())["model_calls"], 0)
        m = json.loads((c.run / "manifest.json").read_text())
        prompt = (c.run / "prompt.txt").read_text()
        self.assertEqual(
            int(re.search(r"At most (\d+) verifier check batch", prompt).group(1)), m["max_checks"]
        )
        initial = prompt.split("Initially read TASK.md and existing declared source inputs: ", 1)[1]
        inputs, _ = json.JSONDecoder().raw_decode(initial)
        self.assertEqual(inputs, sorted(c.spec["files"]))
        self.assertNotIn("note.txt", inputs)
        self.assertNotIn("checks.json", inputs)
        self.assertNotIn("At most three checks", prompt)
        self.assertNotIn("After correcting a defect, rerun all frozen checks", prompt)
        self.assertEqual(m["permissions"], {"network": False, "install": False})
        self.assertFalse((c.run / "live-launch.reserved.json").exists())
        return m, prompt

    def test_single_check_cli_reaches_render_and_actual_ceiling(self):
        m, prompt = self.prepare_cli("--max-checks", "1")
        self.assertEqual(m["max_checks"], 1)
        self.assertEqual(m["max_child_launches"], 1)
        self.assertIn("Single-check budget", prompt)
        self.assertLess(prompt.index("Initially read"), prompt.index("implement the changes"))
        self.assertLess(
            prompt.index("implement the changes"), prompt.index("After a PASS verifier batch")
        )
        self.case.candidate()
        self.assertEqual(self.case.verify(), 0)
        with self.assertRaisesRegex(ValueError, "CHECK_CEILING"):
            self.case.verify()
        self.assertEqual(len(list(self.case.run.glob("check-receipt-*.json"))), 1)
        agent = json.loads((self.case.run / "agents.json").read_text())["reviewer"]
        self.assertEqual(agent["tools"], ["Read"])
        self.assertEqual(agent["maxTurns"], 6)
        self.assertIn("After a PASS verifier batch", agent["prompt"])

    def test_default_and_multi_check_preserve_runtime_and_repair_limits(self):
        c = self.case
        for budget, options, children in [
            (3, [], 1),
            (2, ["--max-checks", "2", "--review-repair"], 2),
        ]:
            with self.subTest(budget=budget):
                c.run = c.base / f"run-{budget}"
                m, prompt = self.prepare_cli(*options)
                self.assertEqual(m["max_checks"], budget)
                self.assertEqual(m["max_child_launches"], children)
                if children == 2:
                    self.assertIn("2 acceptance check batches total", prompt)
                c.candidate()
                for _ in range(budget):
                    self.assertEqual(c.verify(), 0)
                with self.assertRaisesRegex(ValueError, "CHECK_CEILING"):
                    c.verify()
                self.assertEqual(len(list(c.run.glob("check-receipt-*.json"))), budget)

    def test_invalid_budget_or_incompatible_repair_creates_no_run(self):
        c = self.case
        spec = c.base / "task.json"
        spec.write_text(json.dumps(c.spec))
        for budget in [0, 4, True, "1"]:
            with (
                self.subTest(budget=budget),
                self.assertRaisesRegex(ValueError, "INVALID_CHECK_BUDGET"),
            ):
                fixtures.taskroute.prepare(spec, c.project, c.run, max_checks=budget)
            self.assertFalse(c.run.exists())
        with self.assertRaisesRegex(ValueError, "REVIEW_REPAIR_REQUIRES_TWO_CHECK_BATCHES"):
            fixtures.taskroute.prepare(spec, c.project, c.run, max_checks=1, review_repair=True)
        self.assertFalse(c.run.exists())

    def test_no_change_task_can_check_without_fictitious_edits(self):
        c = self.case
        c.spec["contract"] = "Read-only assessment: verify current message, make no changes."
        c.spec["checks"] = [
            dict(
                name="acceptance",
                argv=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; assert Path('message.txt').read_text() == 'old\\n'",
                ],
                timeout_seconds=10,
            )
        ]
        _, prompt = self.prepare_cli("--max-checks", "1")
        self.assertIn("without manufacturing edits", prompt)
        self.assertEqual(c.verify(), 0)
        self.assertEqual((c.run / "workspace/message.txt").read_bytes(), b"old\n")
        self.assertFalse((c.run / "workspace/note.txt").exists())

    def test_observer_stop_does_not_spend_single_acceptance_batch(self):
        c = self.case
        m, prompt = self.prepare_cli("--max-checks", "1", "--observe")
        self.assertEqual(m["max_checks"], 1)
        self.assertEqual(m["max_observer_calls"], 2)
        self.assertIn("Observer-only outcomes do not consume", prompt)
        observation = {"outcome": {"verdict": "STOP"}, "number": 1}
        with patch("observer.observe", return_value=observation):
            self.assertEqual(c.verify(), 1)
        self.assertFalse(list(c.run.glob("check-receipt-*.json")))
        self.assertFalse((c.run / "workspace/checks.json").exists())
        c.candidate()
        observation = {"outcome": {"verdict": "CONTINUE"}, "number": 2, "fingerprint": "fixture"}
        with patch("observer.observe", return_value=observation):
            self.assertEqual(c.verify(), 0)
        self.assertEqual(len(list(c.run.glob("check-receipt-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
