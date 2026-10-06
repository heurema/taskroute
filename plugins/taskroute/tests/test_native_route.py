"""Offline native-helper acceptance. Synthetic dispatch is not platform evidence."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import native_route as native
from runtime import TransportError


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / "message.txt").write_bytes(b"old\n")
        (self.project / "check.py").write_text(
            "from pathlib import Path\nassert Path('message.txt').read_bytes() == b'new\\n'\nassert Path('note.txt').read_bytes() == b'ready\\n'\n"
        )
        self.spec = dict(
            mode="repository",
            contract="Write exact new/ready lines, preserving the check.",
            files=["message.txt", "check.py"],
            writable_paths=["message.txt", "note.txt"],
            model="gpt-6.1-sol",
            permissions=dict(network=False, install=False),
            checks=[dict(name="bytes", argv=[sys.executable, "-B", "check.py"], timeout_seconds=5)],
            acceptance=[
                dict(
                    id="AC1",
                    text="Exact newline semantics.",
                    evidence=["check:bytes", "file:note.txt"],
                )
            ],
            non_goals=[dict(id="NG1", text="Preserve the check.")],
            check_inputs=["check.py"],
        )
        self.spec_path = self.base / "task.json"
        self.spec_path.write_text(json.dumps(self.spec))
        self.root = self.base / "run"
        native.prepare(self.spec_path, self.project, self.root)
        self.worker = self.base / "worker.txt"
        self.worker.write_text(
            'TASKROUTE_RESULT: {"status":"READY_FOR_LEAD","reason":"Declared checks passed"}'
        )
        self.report = dict(
            verdict="APPROVE",
            acceptance=[
                dict(
                    id="AC1",
                    status="MET",
                    evidence=["check:bytes", "file:note.txt"],
                    detail="Full bytes and host check agree",
                )
            ],
            non_goals=[dict(id="NG1", status="KEPT", detail="Frozen check hashes match")],
        )
        self.review = self.base / "review.txt"

    def candidate(self):
        native.reserve(self.root, "worker")
        native.dispatch(self.root, "worker", "/root/fixture_worker", "gpt-6.1-sol")
        (self.root / "workspace/message.txt").write_bytes(b"new\n")
        (self.root / "workspace/note.txt").write_bytes(b"ready\n")
        return native.worker_complete(self.root, self.worker)

    def reviewer(self):
        native.reserve(self.root, "reviewer")
        native.dispatch(self.root, "reviewer", "/root/fixture_reviewer", "gpt-6-astra")
        self.review.write_text("TASKROUTE_REVIEW: " + json.dumps(self.report))

    def test_full_flow_real_frozen_checks_and_distinct_profiles(self):
        checked = self.candidate()
        self.assertEqual(checked["status"], "CANDIDATE_FROZEN")
        self.assertEqual(checked["checks"][0]["exit_code"], 0)
        self.reviewer()
        result = native.finish(self.root, self.review)
        self.assertEqual(result["status"], "READY_FOR_LEAD_REVIEW")
        self.assertEqual(native.receipt(self.root), result)
        self.assertIsNone(result["backend_model"])
        self.assertIn("+ready\n", result["diff"])
        self.assertNotIn("worker-result", (self.root / "reviewer-prompt.txt").read_text())
        self.assertEqual((self.project / "message.txt").read_bytes(), b"old\n")
        with self.assertRaises(TransportError):
            native.finish(self.root, self.review)

    def test_uncertain_dispatch_and_replay_consume_once(self):
        native.reserve(self.root, "worker")
        with self.assertRaises(TransportError):
            native.reserve(self.root, "worker")
        with self.assertRaisesRegex(ValueError, "MISSING_NATIVE_WORKER_DISPATCH"):
            native.worker_complete(self.root, self.worker)

    def test_wrong_profile_or_reused_agent_rejected(self):
        native.reserve(self.root, "worker")
        with self.assertRaisesRegex(ValueError, "PROFILE_MISMATCH"):
            native.dispatch(self.root, "worker", "/root/w", "wrong")
        native.dispatch(self.root, "worker", "/root/same", "gpt-6.1-sol")
        (self.root / "workspace/message.txt").write_bytes(b"new\n")
        (self.root / "workspace/note.txt").write_bytes(b"ready\n")
        native.worker_complete(self.root, self.worker)
        native.reserve(self.root, "reviewer")
        with self.assertRaisesRegex(ValueError, "AGENT_REUSED"):
            native.dispatch(self.root, "reviewer", "/root/same", "gpt-6-astra")

    def test_reviewer_requires_checked_candidate(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            native.reserve(self.root, "reviewer")
        self.assertFalse((self.root / "native-reviewer.reserved.json").exists())

    def test_failed_real_check_stops_review_and_no_repair(self):
        native.reserve(self.root, "worker")
        native.dispatch(self.root, "worker", "/root/w", "gpt-6.1-sol")
        (self.root / "workspace/note.txt").write_bytes(b"ready\n")
        with self.assertRaisesRegex(ValueError, "NATIVE_CHECKS_FAILED"):
            native.worker_complete(self.root, self.worker)
        with self.assertRaises(TransportError):
            native.worker_complete(self.root, self.worker)
        self.assertFalse((self.root / "reviewer-prompt.txt").exists())

    def test_negative_and_incomplete_findings_fail_closed(self):
        self.candidate()
        self.reviewer()
        self.report["acceptance"] = []
        self.review.write_text("TASKROUTE_REVIEW: " + json.dumps(self.report))
        result = native.finish(self.root, self.review)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("INCOMPLETE_FINDINGS", " ".join(result["assessment"]["reasons"]))
        with self.assertRaisesRegex(ValueError, "NATIVE_RUN_TERMINAL"):
            native.reserve(self.root, "reviewer")

    def test_negative_review_never_ready(self):
        self.candidate()
        self.report["verdict"] = "CHANGES"
        self.report["acceptance"][0]["status"] = "NOT_MET"
        self.reviewer()
        self.assertEqual(native.finish(self.root, self.review)["status"], "BLOCKED")

    def test_worker_and_review_copy_mutation_rejected(self):
        self.candidate()
        self.reviewer()
        (self.root / "review-workspace/note.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "NATIVE_REVIEW_COPY_CHANGED"):
            native.finish(self.root, self.review)

    def test_candidate_mutation_after_approval_invalidates_receipt(self):
        self.candidate()
        self.reviewer()
        native.finish(self.root, self.review)
        (self.root / "workspace/note.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "NATIVE_CANDIDATE_CHANGED"):
            native.receipt(self.root)

    def test_fresh_worker_recovers_and_executes_exact_declared_commands(self):
        prompt = (self.root / "worker-prompt.txt").read_text()
        line = next(
            line
            for line in prompt.splitlines()
            if line.startswith("Declared checks (cwd is this workspace): ")
        )
        commands = json.loads(line.split(": ", 1)[1])
        expected = dict(self.spec["checks"][0])
        expected["argv"] = [str(Path(expected["argv"][0]).resolve()), *expected["argv"][1:]]
        self.assertEqual(commands[0], expected)
        workspace = self.root / "workspace"
        (workspace / "message.txt").write_bytes(b"new\n")
        (workspace / "note.txt").write_bytes(b"ready\n")
        check = commands[0]
        process = subprocess.run(
            check["argv"], cwd=workspace, timeout=check["timeout_seconds"], capture_output=True
        )
        self.assertEqual(process.returncode, 0)

    def accepted(self):
        self.candidate()
        self.reviewer()
        native.finish(self.root, self.review)

    def test_receipt_reread_rejects_changed_review_copy(self):
        self.accepted()
        (self.root / "review-workspace/note.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "NATIVE_REVIEW_COPY_CHANGED"):
            native.receipt(self.root)

    def test_receipt_reread_rejects_changed_review_result(self):
        self.accepted()
        (self.root / "reviewer-result.txt").write_text('TASKROUTE_REVIEW: {"verdict":"CHANGES"}')
        with self.assertRaisesRegex(ValueError, "NATIVE_RECEIPT_EVIDENCE_CHANGED"):
            native.receipt(self.root)

    def test_receipt_reread_rejects_changed_check_exit_code(self):
        self.accepted()
        path = self.root / "native-checks.json"
        checks = json.loads(path.read_text())
        checks["checks"][0]["exit_code"] = 99
        path.write_text(json.dumps(checks))
        with self.assertRaisesRegex(ValueError, "NATIVE_RECEIPT_EVIDENCE_CHANGED"):
            native.receipt(self.root)

    def test_receipt_reread_rejects_changed_dispatch(self):
        self.accepted()
        path = self.root / "reviewer-dispatch.json"
        dispatch = json.loads(path.read_text())
        dispatch["agent"] = "/root/fixture_worker"
        path.write_text(json.dumps(dispatch))
        with self.assertRaisesRegex(ValueError, "NATIVE_RECEIPT_EVIDENCE_CHANGED"):
            native.receipt(self.root)

    def test_receipt_reread_rejects_changed_diff(self):
        self.accepted()
        path = self.root / "native-receipt.json"
        receipt = json.loads(path.read_text())
        receipt["diff"] = "incorrect inspection diff"
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "NATIVE_RECEIPT_EVIDENCE_CHANGED"):
            native.receipt(self.root)

    def test_receipt_reread_rejects_changed_candidate_hashes(self):
        self.accepted()
        path = self.root / "native-receipt.json"
        receipt = json.loads(path.read_text())
        receipt["file_hashes"] = {"message.txt": "0" * 64}
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "NATIVE_RECEIPT_EVIDENCE_CHANGED"):
            native.receipt(self.root)

    def test_cli_prepares_without_codex_dependency_or_inference(self):
        p = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS / "taskroute.py"),
                "native-prepare",
                str(self.spec_path),
                "--project",
                str(self.project),
                "--run",
                str(self.base / "cli-run"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
