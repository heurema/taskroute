"""Language-neutral delivery tests. Fake provider is explicitly not live evidence."""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))
import compact_delivery_packet as collector
import repository_task
import taskroute
import verify_structured_flow as verifier


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox required")
class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.originals = {
            "message.txt": "old\n",
            "check.sh": 'test "$(cat message.txt)" = new && test "$(cat note.txt)" = ready\n',
        }
        for name, body in self.originals.items():
            (self.project / name).write_text(body)
        self.spec = dict(
            mode="repository",
            contract="Update the message and add a ready note.",
            files=list(self.originals),
            writable_paths=["message.txt", "note.txt"],
            checks=[dict(name="acceptance", argv=["/bin/sh", "check.sh"], timeout_seconds=10)],
            model="fixture-only",
            permissions=dict(network=False, install=False),
            acceptance=[
                dict(
                    id="AC1",
                    text="Message and note have required contents.",
                    evidence=["check:acceptance"],
                )
            ],
            non_goals=[dict(id="NG1", text="Preserve the check.")],
            check_inputs=["check.sh"],
        )
        self.run = self.base / "run"

    def prepare(self, review_repair=False):
        path = self.base / "task.json"
        path.write_text(json.dumps(self.spec))
        actual = shutil.which
        with patch.object(taskroute.shutil, "which", wraps=actual) as which:
            which.side_effect = lambda name: sys.executable if name == "claude" else actual(name)
            taskroute.prepare(path, self.project, self.run, review_repair=review_repair)
        return json.loads((self.run / "manifest.json").read_text())

    def candidate(self):
        (self.run / "workspace/message.txt").write_text("new\n")
        (self.run / "workspace/note.txt").write_text("ready\n")

    def verify(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return verifier.verify(self.run)

    def review_record(self):
        return dict(
            verdict="APPROVE",
            acceptance=[
                dict(
                    id=c["id"],
                    status="MET",
                    evidence=c["evidence"],
                    detail="Synthetic fixture evidence.",
                )
                for c in self.spec["acceptance"]
            ],
            non_goals=[
                dict(id=c["id"], status="KEPT", detail="Frozen input unchanged.")
                for c in self.spec["non_goals"]
            ],
        )

    def review_text(self):
        return "TASKROUTE_REVIEW: " + json.dumps(self.review_record())

    def coordinator_text(self):
        return (
            'TASKROUTE_RESULT: {"status":"READY_FOR_LEAD","reason":"Synthetic offline evidence."}'
        )

    def evidence(self):
        rows = [
            dict(
                type="assistant",
                parent_tool_use_id="fixture-review",
                message=dict(content=[dict(type="text", text=self.review_text())]),
            ),
            dict(
                type="result",
                is_error=False,
                result=self.coordinator_text(),
                modelUsage={"fixture-only": {}},
                subagent_stats=dict(spawned=1, completed=1),
            ),
        ]
        (self.run / "stdout.jsonl").write_text("\n".join(map(json.dumps, rows)))
        (self.run / "terminal.json").write_text(json.dumps(dict(exit_code=0)))
        (self.run / "gate-events.jsonl").write_text(
            json.dumps(dict(tool="Agent", allowed=True)) + "\n"
        )

    def test_guarded_author_repair_and_collector(self):
        import review_gate

        m = self.prepare(review_repair=True)
        self.candidate()
        self.assertEqual(self.verify(), 0)

        def gate(tool, args, child=None):
            event = dict(hook_event_name="PreToolUse", tool_name=tool, tool_input=args)
            if child:
                event["agent_id"] = child
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "guard_structured_flow.py"), str(self.run)],
                input=json.dumps(event),
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

        launch = dict(subagent_type="reviewer", prompt="Review current candidate")
        edit = dict(file_path=str(self.run / "workspace/message.txt"), content="new\n\n")
        self.assertEqual(gate("Agent", launch), "allow")
        self.assertEqual(gate("Write", edit), "deny")
        negative = self.review_record()
        negative["verdict"] = "CHANGES"
        bad_text = "TASKROUTE_REVIEW: " + json.dumps(negative)
        review_gate.handle(
            self.run,
            dict(
                hook_event_name="SubagentStop",
                agent_type="reviewer",
                agent_id="first",
                last_assistant_message=bad_text,
            ),
        )
        self.assertEqual(gate("Write", edit, child="first"), "deny")
        self.assertEqual(gate("Agent", launch), "deny")
        self.assertEqual(gate("Write", edit), "allow")
        (self.run / "workspace/message.txt").write_text("new\n\n")
        self.assertEqual(gate("Agent", launch), "deny")
        self.assertEqual(self.verify(), 0)
        self.assertEqual(gate("Agent", launch), "allow")
        self.assertEqual(gate("Write", edit), "deny")
        review_gate.handle(
            self.run,
            dict(
                hook_event_name="SubagentStop",
                agent_type="reviewer",
                agent_id="second",
                last_assistant_message=self.review_text(),
            ),
        )
        self.assertEqual(gate("Agent", launch), "deny")
        rows = [
            dict(
                type="assistant",
                parent_tool_use_id="first",
                message=dict(content=[dict(type="text", text=bad_text)]),
            ),
            dict(
                type="assistant",
                parent_tool_use_id="second",
                message=dict(content=[dict(type="text", text=self.review_text())]),
            ),
            dict(
                type="result",
                is_error=False,
                result=self.coordinator_text(),
                modelUsage={"fixture-only": {}},
                subagent_stats=dict(spawned=2, completed=2),
            ),
        ]
        (self.run / "stdout.jsonl").write_text("\n".join(map(json.dumps, rows)))
        (self.run / "terminal.json").write_text(json.dumps(dict(exit_code=0)))
        review, _ = collector.review_evidence(self.run, m)
        self.assertEqual(review, self.review_text())
        with (self.run / "gate-events.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(tool="Write", allowed=True, time=1e20)) + "\n")
        with self.assertRaisesRegex(ValueError, "OUTSIDE_REPAIR"):
            collector.review_evidence(self.run, m)

    def test_complete_fake_provider_flow(self):
        m = self.prepare()
        fake = self.base / "fake-claude"
        fake.write_text(
            "#!" + sys.executable + "\nimport json,sys,subprocess\nfrom pathlib import Path\n"
            'r=Path(sys.argv[sys.argv.index("--settings")+1]).parent\n'
            '(r/"workspace/message.txt").write_text("new\\n")\n'
            '(r/"workspace/note.txt").write_text("ready\\n")\n'
            'p=subprocess.run([sys.executable,"-B",'
            + repr(str(SCRIPTS / "verify_structured_flow.py"))
            + ",str(r)],capture_output=True,text=True)\n"
            "if p.returncode: raise RuntimeError(p.stdout)\n"
            '(r/"gate-events.jsonl").write_text(json.dumps({"tool":"Agent","allowed":True})+"\\n")\n'
            + "print(json.dumps("
            + repr(
                dict(
                    type="assistant",
                    parent_tool_use_id="fixture",
                    message=dict(content=[dict(type="text", text=self.review_text())]),
                )
            )
            + "))\n"
            + "print(json.dumps("
            + repr(
                dict(
                    type="result",
                    is_error=False,
                    result=self.coordinator_text(),
                    modelUsage={"fixture-only": {}},
                    subagent_stats=dict(spawned=1, completed=1),
                )
            )
            + "))\n"
        )
        fake.chmod(0o700)
        m["claude_binary"] = str(fake)
        (self.run / "manifest.json").write_text(json.dumps(m))
        args = [sys.executable, "-B", str(SCRIPTS / "taskroute.py"), "run", str(self.run)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        packet = json.loads(result.stdout)
        self.assertEqual(packet["status"], "READY_FOR_LEAD_REVIEW")
        self.assertIn("note.txt", packet["diff"])
        self.assertEqual(packet["independent_checks"][0]["exit_code"], 0)
        self.assertEqual((self.project / "message.txt").read_text(), "old\n")
        self.assertFalse((self.project / "note.txt").exists())
        replay = subprocess.run(args, capture_output=True, text=True, timeout=10)
        self.assertIn("LIVE_ATTEMPT_ALREADY_RESERVED", replay.stdout)

    def test_blocked_and_changes_return_decision_packet(self):
        self.prepare()
        self.candidate()
        self.assertEqual(self.verify(), 0)
        self.evidence()
        rows = [json.loads(line) for line in (self.run / "stdout.jsonl").read_text().splitlines()]
        review = self.review_record()
        review["verdict"] = "CHANGES"
        review["acceptance"][0]["status"] = "NOT_MET"
        rows[0]["message"]["content"][0]["text"] = "TASKROUTE_REVIEW: " + json.dumps(review)
        rows[1]["result"] = (
            'TASKROUTE_RESULT: {"status":"BLOCKED","reason":"Reviewer found missing behavior."}'
        )
        (self.run / "stdout.jsonl").write_text("\n".join(map(json.dumps, rows)))
        packet = collector.collect(self.run)
        self.assertEqual(packet["status"], "NEEDS_LEAD_DECISION")
        self.assertIn("COORDINATOR_BLOCKED", packet["reasons"])
        self.assertIn("REVIEW_REQUESTS_CHANGES", packet["reasons"])
        self.assertEqual(packet["independent_checks"], [])
        self.assertIn("missing behavior", packet["coordinator_text"])
        self.assertIn("note.txt", packet["diff"])

    def test_review_gate_requires_current_passing_checks(self):
        self.prepare()
        event = dict(
            hook_event_name="PreToolUse",
            tool_name="Agent",
            tool_input=dict(subagent_type="reviewer", prompt="Review TASK.md."),
        )

        def gate():
            process = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "guard_structured_flow.py"),
                    str(self.run),
                    "--check-only",
                ],
                input=json.dumps(event),
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(process.stdout)["hookSpecificOutput"]["permissionDecision"]

        self.assertEqual(gate(), "deny")
        self.candidate()
        self.assertEqual(self.verify(), 0)
        self.assertEqual(gate(), "allow")
        (self.run / "workspace/message.txt").write_text("changed after tests\n")
        self.assertEqual(gate(), "deny")

    def test_failed_checks_never_make_ready_packet(self):
        self.prepare()
        self.assertEqual(self.verify(), 1)
        self.evidence()
        with self.assertRaisesRegex(ValueError, "CHECK_HASH_MISMATCH"):
            collector.collect(self.run)

    def test_frozen_and_undeclared_files_block(self):
        m = self.prepare()
        w = self.run / "workspace"
        (w / "check.sh").write_text("exit 0\n")
        with self.assertRaisesRegex(ValueError, "FROZEN_INPUT_CHANGED"):
            repository_task.snapshot(m, self.originals)
        (w / "check.sh").write_text(self.originals["check.sh"])
        (w / "extra").write_text("bad")
        with self.assertRaisesRegex(ValueError, "UNDECLARED"):
            repository_task.snapshot(m, self.originals)

    def test_symlink_and_escaping_paths_rejected(self):
        for name in ["../escape", "/tmp/escape", "./message.txt", ".git/config", "TASK.md"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                repository_task.paths([name])
        (self.project / "link.txt").symlink_to(self.project / "message.txt")
        self.spec["files"].append("link.txt")
        with self.assertRaisesRegex(ValueError, "SOURCE_SYMLINK"):
            self.prepare()
        self.assertFalse(self.run.exists())

    def test_unknown_permissions_and_shell_string_rejected(self):
        self.spec["permissions"]["network"] = True
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_PERMISSIONS"):
            self.prepare()
        self.spec["permissions"]["network"] = False
        self.spec["checks"][0]["argv"] = "sh check.sh"
        with self.assertRaisesRegex(ValueError, "INVALID_CHECK_ARGV"):
            self.prepare()

    def test_changed_candidate_and_check_tool_block(self):
        m = self.prepare()
        self.candidate()
        self.assertEqual(self.verify(), 0)
        self.evidence()
        (self.run / "workspace/message.txt").write_text("later\n")
        with self.assertRaisesRegex(ValueError, "CHECK_HASH_MISMATCH"):
            collector.collect(self.run)
        m["checks"][0]["executable_sha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "CHECK_TOOL_CHANGED"):
            repository_task.check_tools(m)

    def test_gate_enforces_scope_and_reviewer_readonly(self):
        self.prepare()

        def gate(tool, name, **extra):
            event = dict(
                hook_event_name="PreToolUse",
                tool_name=tool,
                tool_input=dict(file_path=name),
                **extra,
            )
            p = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "guard_structured_flow.py"),
                    str(self.run),
                    "--check-only",
                ],
                input=json.dumps(event),
                text=True,
                capture_output=True,
                check=True,
            )
            return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]

        self.assertEqual(gate("Write", "note.txt"), "allow")
        self.assertEqual(gate("Write", "check.sh"), "deny")
        self.assertEqual(gate("Write", "note.txt", agent_id="reviewer"), "deny")
        self.assertEqual(gate("Read", "../manifest.json"), "deny")

    def test_check_input_mutation_and_timeout_block(self):
        self.spec["checks"][0]["argv"] = ["/bin/sh", "-c", "echo mutated > message.txt"]
        self.prepare()
        with self.assertRaisesRegex(ValueError, "CHECK_INPUT_MUTATED"):
            self.verify()
        m = json.loads((self.run / "manifest.json").read_text())
        m["checks"][0]["argv"] = ["/bin/sh", "-c", "sleep 5"]
        m["checks"][0]["timeout_seconds"] = 1
        (self.run / "manifest.json").write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, "CHECK_TIMEOUT"):
            self.verify()

    @unittest.skipUnless(shutil.which("go"), "Go unavailable; no installation")
    def test_real_go_checks_without_language_adapter(self):
        originals = {
            "main.go": 'package main\nfunc main() { if label() != "ready" { panic("bad label") } }\n',
            "label.go": 'package main\nfunc label() string { return "old" }\n',
        }
        for name, body in originals.items():
            (self.project / name).write_text(body)
        self.spec.update(
            files=list(originals),
            writable_paths=["label.go"],
            checks=[
                dict(
                    name="go acceptance",
                    argv=[shutil.which("go"), "run", "main.go", "label.go"],
                    timeout_seconds=60,
                )
            ],
        )
        self.spec.update(
            check_inputs=["main.go"],
            acceptance=[
                dict(id="AC1", text="Go label returns ready.", evidence=["check:go acceptance"])
            ],
        )
        self.prepare()
        (self.run / "workspace/label.go").write_text(
            'package main\nfunc label() string { return "ready" }\n'
        )
        code = self.verify()
        self.assertEqual(code, 0, (self.run / "workspace/checks.json").read_text())
        self.evidence()
        self.assertEqual(collector.collect(self.run)["independent_checks"][0]["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
