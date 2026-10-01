"""Reject preparation failures before any provider process is started."""

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compact_delivery_packet as packet


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name).resolve()
        self.probe = self.enterContext(
            patch.object(
                packet,
                "bounded_check",
                return_value={"returncode": 0, "stop_reason": None, "feedback": ""},
            )
        )
        work = self.run / "workspace"
        work.mkdir()
        body = "def example():\n    pass\n"
        (work / "example.py").write_text(body)
        manifest = dict(
            workspace=str(work),
            python=sys.executable,
            claude_binary=sys.executable,
            source_hashes={"example.py": hashlib.sha256(body.encode()).hexdigest()},
            canonical_source_hashes={},
        )
        for name, value in [
            ("manifest.json", manifest),
            ("originals.json", {"example.py": body}),
            ("settings.json", {}),
            ("agents.json", {}),
            ("preflight.json", {"status": "PASS"}),
        ]:
            (self.run / name).write_text(json.dumps(value))
        for name in ["launch.py", "prompt.txt", "test.sb"]:
            (self.run / name).write_text("fixture")

    def test_denied_workspace_never_launches(self):
        original = packet.tempfile.TemporaryFile

        def deny_workspace(*args, **kwargs):
            if Path(kwargs.get("dir", ".")).name == "workspace":
                raise PermissionError("fixture denial")
            return original(*args, **kwargs)

        with (
            patch.object(packet.tempfile, "TemporaryFile", side_effect=deny_workspace),
            patch.object(sys, "argv", ["packet", str(self.run), "--launch"]),
            patch.object(packet.subprocess, "run") as launch,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(packet.main(), 2)
        launch.assert_not_called()
        self.assertIn("WORKSPACE_NOT_WRITABLE", (self.run / "packet-error.json").read_text())

    def test_unavailable_workspace(self):
        work = self.run / "workspace"
        (work / "example.py").unlink()
        work.rmdir()
        with self.assertRaisesRegex(ValueError, "MISSING_OR_ESCAPING_INPUT"):
            packet.preflight(self.run)

    def test_dependency_expansion_rejected_before_probe_or_launch(self):
        for root in ("/fixture/shared", "/fixture/library", "/missing", "/denied"):
            m = json.loads((self.run / "manifest.json").read_text())
            m["check_environment"] = {"read_only_roots": [root]}
            (self.run / "manifest.json").write_text(json.dumps(m))
            with (
                patch.object(sys, "argv", ["packet", str(self.run), "--launch"]),
                patch.object(packet.subprocess, "run") as launch,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(packet.main(), 2)
            launch.assert_not_called()
        self.probe.assert_not_called()

    def test_missing_test_executable_blocks(self):
        m = json.loads((self.run / "manifest.json").read_text())
        m["python"] = str(self.run / "missing-python")
        (self.run / "manifest.json").write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, "PYTHON_NOT_EXECUTABLE"):
            packet.preflight(self.run)

    def test_missing_repository_check_tool_before_process(self):
        m = json.loads((self.run / "manifest.json").read_text())
        m.update(
            mode="repository",
            checks=[{"argv": [str(self.run / "missing-tool")], "executable_sha256": "unknown"}],
        )
        (self.run / "manifest.json").write_text(json.dumps(m))
        with (
            patch.object(sys, "argv", ["packet", str(self.run), "--launch"]),
            patch.object(packet.subprocess, "run") as launch,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(packet.main(), 2)
        launch.assert_not_called()
        self.assertIn("CHECK_TOOL_CHANGED", (self.run / "packet-error.json").read_text())

    def test_unavailable_sandbox_before_probe(self):
        access = packet.os.access
        with patch.object(
            packet.os,
            "access",
            side_effect=lambda p, mode: (
                False if str(p) == "/usr/bin/sandbox-exec" else access(p, mode)
            ),
        ):
            with self.assertRaisesRegex(ValueError, "TEST_SANDBOX_UNAVAILABLE"):
                packet.preflight(self.run)
        self.probe.assert_not_called()

    def test_denied_check_environment_no_provider(self):
        self.probe.return_value = {"returncode": 1, "stop_reason": None, "feedback": "private"}
        with (
            patch.object(sys, "argv", ["packet", str(self.run), "--launch"]),
            patch.object(packet.subprocess, "run") as launch,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(packet.main(), 2)
        launch.assert_not_called()
        error = json.loads((self.run / "packet-error.json").read_text())
        self.assertEqual(error["stage"], "preflight")
        self.assertFalse(error["automatic_retry"])
        self.assertIsNone(error["observed_model"])
        self.assertIsNone(error["usage"])
        self.assertNotIn("private", json.dumps(error))

    def test_missing_scratch_is_created_without_reserving_launch(self):
        self.assertEqual(packet.preflight(self.run)["status"], "PASS")
        self.assertTrue((self.run / "scratch").is_dir())
        self.assertEqual(list((self.run / "scratch").iterdir()), [])
        self.assertFalse((self.run / "live-launch.reserved.json").exists())
        self.assertEqual(packet.preflight(self.run)["status"], "PASS")

    def test_changed_input_blocks_before_process(self):
        (self.run / "workspace/example.py").write_text("changed")
        with (
            patch.object(sys, "argv", ["packet", str(self.run), "--launch"]),
            patch.object(packet.subprocess, "run") as launch,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(packet.main(), 2)
        launch.assert_not_called()
        self.assertIn("INITIAL_INPUT_CHANGED", (self.run / "packet-error.json").read_text())

    def test_missing_file_blocks(self):
        (self.run / "settings.json").unlink()
        with self.assertRaisesRegex(ValueError, "MISSING_LAUNCH_FILE"):
            packet.preflight(self.run)

    def test_prior_terminal_is_preserved(self):
        terminal = self.run / "terminal.json"
        terminal.write_text('{"status":"ENDED"}')
        with self.assertRaisesRegex(ValueError, "PRIOR_LAUNCH_RECEIPT"):
            packet.preflight(self.run)
        self.assertEqual(terminal.read_text(), '{"status":"ENDED"}')

    def test_existing_attempt_cannot_be_replayed(self):
        (self.run / "live-launch.reserved.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "ALREADY_RESERVED"):
            packet.preflight(self.run)

    def test_scratch_file_and_used_directory_block(self):
        scratch = self.run / "scratch"
        scratch.write_text("not a directory")
        with self.assertRaises(FileExistsError):
            packet.preflight(self.run)
        scratch.unlink()
        scratch.mkdir()
        (scratch / "old-check").write_text("preserve")
        with self.assertRaisesRegex(ValueError, "SCRATCH_NOT_EMPTY"):
            packet.preflight(self.run)
        self.assertEqual((scratch / "old-check").read_text(), "preserve")

    def test_preflight_only_never_launches(self):
        with (
            patch.object(sys, "argv", ["packet", str(self.run), "--preflight"]),
            patch.object(packet.subprocess, "run") as launch,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(packet.main(), 0)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
