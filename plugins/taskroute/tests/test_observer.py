"""Offline observation stop/correction/clearance tests; no live model calls."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import observer
import repository_task
import taskroute
import verify_structured_flow


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.m = dict(
            model="fixture-model",
            claude_binary=str(self.root / "fake"),
            max_observer_calls=2,
            observer_seconds=5,
            observer_enabled=True,
            contract="Return correct content.",
            acceptance=[dict(id="AC1", text="Correct", evidence=["review"])],
            non_goals=[],
            check_inputs=[],
            checks=[],
        )
        self.fake = Path(self.m["claude_binary"])
        self.fake.write_text(
            "#!"
            + sys.executable
            + """
import json,sys
payload=json.loads(sys.stdin.read().split("CANDIDATE DATA:\\n",1)[1])
stop="bad" in payload["candidate_files"].values()
out={"verdict":"STOP" if stop else "CONTINUE","summary":"Synthetic fixture verdict.","findings":[{"criterion_id":"AC1","evidence":"Content is bad.","correction":"Use correct content."}] if stop else []}
print(json.dumps({"is_error":False,"modelUsage":{"fixture-model":{}},"result":"TASKROUTE_OBSERVER: "+json.dumps(out)}))
"""
        )
        self.fake.chmod(0o700)

    def test_stop_correct_continue_and_cache(self):
        bad, good = {"content.txt": "bad"}, {"content.txt": "good"}
        first = observer.observe(self.root, self.m, bad)
        self.assertEqual(first["outcome"]["verdict"], "STOP")
        self.assertEqual(observer.observe(self.root, self.m, bad), first)
        self.assertEqual(len(list(self.root.glob("observer-*.reserved.json"))), 1)
        with self.assertRaisesRegex(ValueError, "CLEARANCE"):
            observer.require_clearance(self.root, self.m, bad)
        second = observer.observe(self.root, self.m, good)
        self.assertEqual(second["outcome"]["verdict"], "CONTINUE")
        observer.require_clearance(self.root, self.m, good)
        with self.assertRaisesRegex(ValueError, "CLEARANCE"):
            observer.require_clearance(self.root, self.m, {"content.txt": "changed"})
        with self.assertRaisesRegex(ValueError, "CEILING"):
            observer.observe(self.root, self.m, {"content.txt": "third"})

    def test_unknown_submission_is_not_resent(self):
        (self.root / "observer-1.reserved.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "UNKNOWN_SUBMISSION"):
            observer.observe(self.root, self.m, {})
        self.assertFalse((self.root / "observer-2.reserved.json").exists())

    def test_identity_or_format_error_latches(self):
        self.fake.write_text(
            "#!"
            + sys.executable
            + '\nprint(\'{"is_error": false, "modelUsage": {"wrong": {}}, "result":"CONTINUE"}\')\n'
        )
        with self.assertRaisesRegex(ValueError, "IDENTITY"):
            observer.observe(self.root, self.m, {})
        with self.assertRaisesRegex(ValueError, "PREVIOUS_ERROR"):
            observer.observe(self.root, self.m, {"new": "candidate"})
        self.assertEqual(len(list(self.root.glob("observer-*.reserved.json"))), 1)

    def test_invalid_verdict_cannot_grant_clearance(self):
        for value in [
            dict(verdict="CONTINUE", summary="ok", findings=[{}]),
            dict(verdict="STOP", summary="bad", findings=[]),
            dict(verdict="CONTINUE", summary="", findings=[]),
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                observer.verdict("TASKROUTE_OBSERVER: " + json.dumps(value), self.m)

    @unittest.skipUnless(sys.platform == "darwin", "macOS verifier")
    def test_verifier_does_not_execute_checks_before_clearance(self):
        project = self.root / "project"
        project.mkdir()
        (project / "content.txt").write_text("bad")
        spec = dict(
            mode="repository",
            contract="The content must be good.",
            files=["content.txt"],
            writable_paths=["content.txt"],
            checks=[
                dict(
                    name="content",
                    argv=["/bin/sh", "-c", 'test "$(cat content.txt)" = good'],
                    timeout_seconds=5,
                )
            ],
            acceptance=[dict(id="AC1", text="Good content", evidence=["check:content"])],
            non_goals=[],
            check_inputs=[],
            permissions=dict(network=False, install=False),
            model="fixture-model",
        )
        path = self.root / "spec.json"
        path.write_text(json.dumps(spec))
        run = self.root / "run"
        actual = taskroute.shutil.which
        with patch.object(
            taskroute.shutil,
            "which",
            side_effect=lambda n: str(self.fake) if n == "claude" else actual(n),
        ):
            taskroute.prepare(path, project, run, observe=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify_structured_flow.verify(run), 1)
        self.assertEqual(list(run.glob("check-receipt-*.json")), [])
        (run / "workspace/content.txt").write_text("good")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify_structured_flow.verify(run), 0)
        self.assertEqual(len(list(run.glob("check-receipt-*.json"))), 1)
        receipt = json.loads((run / "check-receipt-1.json").read_text())
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["observer"]["outcome"]["verdict"], "CONTINUE")
        self.assertEqual(receipt["observer"]["number"], 2)
        self.assertEqual(json.loads((run / "workspace/checks.json").read_text()), receipt)
        m = json.loads((run / "manifest.json").read_text())
        bodies = repository_task.snapshot(m, {"content.txt": "bad"})
        observer.require_clearance(run, m, bodies)
        event = dict(
            hook_event_name="PreToolUse",
            tool_name="Agent",
            tool_input=dict(subagent_type="reviewer", prompt="Review."),
        )
        check = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS / "guard_structured_flow.py"),
                str(run),
                "--check-only",
            ],
            input=json.dumps(event),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            json.loads(check.stdout)["hookSpecificOutput"]["permissionDecision"], "allow"
        )


if __name__ == "__main__":
    unittest.main()
