"""Offline replay of two accepted artifacts; synthetic transport, no model calls."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))
import backlog
import compact_delivery_packet as collector
import taskroute
import verify_structured_flow as verifier


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox required")
class PackagedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.backlog_db = Path(temp.name) / "backlog.sqlite3"
        self.enterContext(patch.dict(os.environ, TASKROUTE_BACKLOG_DB=str(self.backlog_db)))

    def replay(self, name):
        fixture = json.loads((PLUGIN / "tests/fixtures" / f"{name}.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            project = base / "project"
            project.mkdir()
            for n, b in fixture["originals"].items():
                p = project / n
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(b)
            spec = {
                k: fixture[k]
                for k in [
                    "target",
                    "test_target",
                    "target_function",
                    "test_pattern",
                    "independent_test_count",
                    "worker_test_methods",
                ]
            }
            spec.update(
                files=list(fixture["originals"]),
                model="fixture-only",
                contract="Offline artifact replay; no live call.",
            )
            path = base / "task.json"
            path.write_text(json.dumps(spec))
            run = base / "run"
            with patch.object(taskroute.shutil, "which", return_value=sys.executable):
                self.assertEqual(taskroute.prepare(path, project, run)["status"], "PREPARED")
                with self.assertRaisesRegex(ValueError, "ALREADY_EXISTS"):
                    taskroute.prepare(path, project, run)
            m = json.loads((run / "manifest.json").read_text())
            (run / "workspace" / m["target"]).write_text(fixture["candidate"])
            (run / "workspace" / m["test_target"]).write_text(fixture["worker_tests"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verifier.verify(run), 0)
            # Explicit synthetic transport to exercise collector; not live review evidence.
            result = dict(
                type="result",
                is_error=False,
                modelUsage={"fixture-only": {}},
                subagent_stats={"spawned": 1, "completed": 1},
            )
            review = dict(
                type="assistant",
                parent_tool_use_id="fixture",
                message={
                    "content": [
                        {"type": "text", "text": "Synthetic reviewer receipt for offline replay."}
                    ]
                },
            )
            (run / "stdout.jsonl").write_text(json.dumps(review) + "\n" + json.dumps(result) + "\n")
            (run / "terminal.json").write_text(json.dumps({"exit_code": 0}))
            (run / "gate-events.jsonl").write_text(
                json.dumps({"tool": "Agent", "allowed": True}) + "\n"
            )
            packet = collector.collect(run)
            self.assertEqual(
                packet["independent_tests"]["tests"], fixture["independent_test_count"]
            )
            self.assertEqual(packet["status"], "READY_FOR_LEAD_REVIEW")
            for n, b in fixture["originals"].items():
                self.assertEqual((project / n).read_text(), b)
            with self.assertRaisesRegex(RuntimeError, "ALREADY_CONSUMED"):
                collector.collect(run)

    def fake_provider_delivery(self, deliver=False):
        fixture = json.loads((PLUGIN / "tests/fixtures/batches.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            project = base / "project"
            project.mkdir()
            for n, b in fixture["originals"].items():
                p = project / n
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(b)
            data = base / "fixture.json"
            data.write_text(json.dumps(fixture))
            fake = base / "fake-claude"
            fake.write_text(
                "#!"
                + sys.executable
                + "\n"
                + "import json,sys,subprocess\nfrom pathlib import Path\n"
                + 'r=Path(sys.argv[sys.argv.index("--settings")+1]).parent\n'
                + 'm=json.loads((r/"manifest.json").read_text());w=Path(m["workspace"])\n'
                + "f=json.loads(Path("
                + repr(str(data))
                + ").read_text())\n"
                + '(w/m["target"]).write_text(f["candidate"]);(w/m["test_target"]).write_text(f["worker_tests"])\n'
                + 'v=subprocess.run([sys.executable,"-B",'
                + repr(str(PLUGIN / "scripts/verify_structured_flow.py"))
                + ",str(r)],capture_output=True,text=True);assert v.returncode==0,v.stdout\n"
                + '(r/"gate-events.jsonl").write_text(json.dumps({"tool":"Agent","allowed":True})+"\\n")\n'
                + 'print(json.dumps({"type":"assistant","parent_tool_use_id":"fixture","message":{"content":[{"type":"text","text":"Synthetic offline review."}]}}))\n'
                + 'print(json.dumps({"type":"result","is_error":False,"modelUsage":{"fixture-only":{}},"subagent_stats":{"spawned":1,"completed":1}}))\n'
            )
            # Normalize the generated JSONL newline literal.
            fake.write_text(fake.read_text().replace('"\\\\n"', '"\\n"'))
            fake.chmod(0o700)
            spec = {
                k: fixture[k]
                for k in [
                    "target",
                    "test_target",
                    "target_function",
                    "test_pattern",
                    "independent_test_count",
                    "worker_test_methods",
                ]
            }
            spec.update(
                files=list(fixture["originals"]),
                model="fixture-only",
                contract="Offline fake-provider launch.",
            )
            path = base / "task.json"
            path.write_text(json.dumps(spec))
            run = base / "run"
            if deliver:
                real_run = subprocess.run
                captured = []

                def execute(command):
                    result = real_run(command, capture_output=True, text=True, timeout=30)
                    captured.append(result)
                    return result

                argv = [
                    "taskroute",
                    "deliver",
                    str(path),
                    "--project",
                    str(project),
                    "--run",
                    str(run),
                ]
                with (
                    patch.object(taskroute.shutil, "which", return_value=str(fake)),
                    patch.object(sys, "argv", argv),
                    patch.object(taskroute.subprocess, "run", side_effect=execute),
                ):
                    self.assertEqual(taskroute.main(), 0)
                self.assertEqual(len(captured), 1)
                view = json.loads(captured[0].stdout)
                full = json.loads((run / "acceptance-packet.json").read_text())
                self.assertEqual(view["reviewer_text"], full["reviewer_text"])
                self.assertEqual(view["backlog"], full["backlog"])
                self.assertEqual(view["independent_tests"]["tests"], 20)
                self.assertTrue((run / "live-launch.reserved.json").exists())
                return
            with patch.object(taskroute.shutil, "which", return_value=str(fake)):
                taskroute.prepare(path, project, run)
            args = [sys.executable, "-B", str(PLUGIN / "scripts/taskroute.py"), "run", str(run)]
            first = subprocess.run(args, capture_output=True, text=True, timeout=30)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(json.loads(first.stdout)["independent_tests"]["tests"], 20)
            self.assertTrue((run / "live-launch.reserved.json").exists())
            second = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("LIVE_ATTEMPT_ALREADY_RESERVED", second.stdout)
            rows = backlog.show(self.backlog_db, "runner.live_attempt_already_reserved")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["run_id"], backlog.opaque(run))

    def test_complete_launcher_with_fake_provider(self):
        self.fake_provider_delivery()

    def test_deliver_end_to_end_with_fake_provider(self):
        self.fake_provider_delivery(deliver=True)

    def test_receipt_regression(self):
        self.replay("receipts")

    def test_batch_regression(self):
        self.replay("batches")


if __name__ == "__main__":
    unittest.main()
