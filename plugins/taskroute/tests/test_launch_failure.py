"""Fixture-only completion and primary failure regression checks."""

import contextlib
import io
import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compact_delivery_packet as packet
import runtime


class OutcomeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run = Path(temp.name)
        self.m = {"workspace": str(self.run / "workspace"), "model": "requested-only"}
        (self.run / "manifest.json").write_text(json.dumps(self.m))
        (self.run / "terminal.json").write_text(json.dumps({"exit_code": 0, "status": "ENDED"}))
        self.result = {"type": "result", "subtype": "success"}
        self.stream(self.result)

    def stream(self, *rows):
        (self.run / "stdout.jsonl").write_text("\n".join(json.dumps(row) for row in rows))

    def failure(self, reason):
        with self.assertRaises(packet.DeliveryFailure) as caught:
            packet.native_outcome(self.run, self.m)
        self.assertEqual(caught.exception.primary, reason)
        return caught.exception

    def test_duplicate_completion_rejected(self):
        self.stream(self.result, self.result)
        self.failure("duplicate_result")

    def test_single_completion(self):
        rows, result = packet.native_outcome(self.run, self.m)
        self.assertEqual(rows, [self.result])
        self.assertEqual(result, self.result)

    def test_invalid_terminal_and_stream(self):
        for body in (b"{", b"\xff", b"[]"):
            (self.run / "terminal.json").write_bytes(body)
            self.failure("invalid_terminal")
        (self.run / "terminal.json").write_text('{"exit_code": 0}')
        (self.run / "stdout.jsonl").write_bytes(b"\xff")
        self.failure("invalid_stream")

    def test_absent_completion_has_no_success_or_identity(self):
        self.stream()
        evidence = self.failure("missing_result").evidence
        for name in ("subtype", "is_error", "observed_model", "accepted_model", "usage"):
            self.assertIsNone(evidence[name])

    def test_max_turns_precedes_success_artifacts(self):
        self.stream({"type": "result", "subtype": "error_max_turns", "is_error": True})
        with self.assertRaises(packet.DeliveryFailure) as caught:
            packet.collect(self.run)
        self.assertEqual(caught.exception.primary, "error_max_turns")
        self.assertIn("CHECKS_NOT_RUN", caught.exception.secondary)

    def test_wrapper_failure_keeps_native_reason(self):
        # Real subprocess fixture writes only local receipts; no provider invocation.
        (self.run / "launch.py").write_text(
            "import json, pathlib\nr=pathlib.Path(__file__).parent\n"
            "(r/'terminal.json').write_text(json.dumps({'status':'ENDED','exit_code':1}))\n"
            "(r/'stdout.jsonl').write_text(json.dumps({'type':'result','subtype':'error_max_turns','is_error':True}))\n"
            "raise SystemExit(1)\n"
        )
        with (
            patch.object(packet, "preflight", return_value={"status": "PASS"}),
            patch.object(sys, "argv", ["packet", str(self.run), "--launch"]),
            patch("backlog.capture", return_value={"status": "fixture"}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(packet.main(), 2)
        error = json.loads((self.run / "packet-error.json").read_text())
        self.assertEqual(error["primary"], "error_max_turns")
        self.assertFalse(error["automatic_retry"])


class PreparationFailureTests(unittest.TestCase):
    def test_preparation_keeps_failed_readiness_receipt(self):
        import test_repository_task as fixtures

        case = fixtures.RepositoryTests(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        with patch.object(
            packet, "preflight", side_effect=ValueError("TEST_ENVIRONMENT_UNAVAILABLE")
        ):
            with self.assertRaisesRegex(ValueError, "TEST_ENVIRONMENT_UNAVAILABLE"):
                case.prepare()
        failure = json.loads((case.run / "preflight.json").read_text())
        self.assertEqual(failure["status"], "BLOCKED")
        self.assertEqual(failure["model_calls"], 0)
        self.assertEqual(failure, json.loads((case.run / "packet-error.json").read_text()))
        self.assertFalse((case.run / "live-launch.reserved.json").exists())


class LaunchTests(unittest.TestCase):
    def launch(self, preflight_error=None, startup_error=None, prior_terminal=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "claude_binary": "fixture-provider",
                    "model": "fixture-only",
                    "effort": "medium",
                    "max_parent_turns": 1,
                    "wall_seconds": 30,
                    "workspace": str(root),
                }
            )
        )
        if prior_terminal:
            (root / "terminal.json").write_text(prior_terminal)
        (root / "prompt.txt").write_text("fixture only")
        template = Path(packet.__file__).with_name("launch_template.py")
        (root / "launch.py").write_text(template.read_text())
        process = Mock(pid=12345, returncode=0)
        with (
            patch.object(packet, "preflight", side_effect=preflight_error) as preflight,
            patch.object(runtime.Journal, "reserve") as reserve,
            patch("subprocess.Popen", side_effect=startup_error, return_value=process) as popen,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            try:
                runpy.run_path(str(root / "launch.py"))
            except SystemExit as exc:
                self.assertEqual(exc.code, 2)
        return root, process, preflight, reserve, popen

    def test_direct_launch_preflight_blocks_before_reservation(self):
        root, _, preflight, reserve, popen = self.launch(ValueError("WORKSPACE_NOT_WRITABLE"))
        preflight.assert_called_once()
        reserve.assert_not_called()
        popen.assert_not_called()
        result = json.loads((root / "terminal.json").read_text())
        self.assertEqual(result["status"], "PREFLIGHT_FAILED")
        self.assertEqual(result["live_launches"], 0)

    def test_failed_direct_replay_preserves_terminal(self):
        root, _, _, reserve, popen = self.launch(
            ValueError("LIVE_ATTEMPT_ALREADY_RESERVED"), prior_terminal='{"status":"ENDED"}'
        )
        self.assertEqual((root / "terminal.json").read_text(), '{"status":"ENDED"}')
        self.assertTrue((root / "launch-preflight-error.json").is_file())
        reserve.assert_not_called()
        popen.assert_not_called()

    def test_completion_wait_once_no_status_poll(self):
        root, process, preflight, reserve, popen = self.launch()
        preflight.assert_called_once()
        reserve.assert_called_once()
        popen.assert_called_once()
        process.communicate.assert_called_once_with(b"fixture only", timeout=30)
        process.poll.assert_not_called()
        result = json.loads((root / "terminal.json").read_text())
        self.assertEqual(result["wait_mode"], "process_completion")
        self.assertEqual(result["containment"], "instructions_and_hooks_only")

    def test_uncertain_startup_reserved_once_never_resends(self):
        root, _, _, reserve, popen = self.launch(startup_error=PermissionError("denied"))
        reserve.assert_called_once()
        popen.assert_called_once()
        result = json.loads((root / "terminal.json").read_text())
        self.assertEqual(result["status"], "LAUNCH_FAILED_UNKNOWN")
        self.assertFalse(result["automatic_retry"])
        self.assertEqual(result["resends"], 0)
