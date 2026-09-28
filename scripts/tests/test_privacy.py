"""Exercise the Git index boundary without embedding real private values."""

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCANNER = Path(__file__).resolve().parents[1] / "check_privacy.py"
module_spec = importlib.util.spec_from_file_location("privacy", SCANNER)
privacy = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(privacy)


class PatternTests(unittest.TestCase):
    def test_paths_and_email(self):
        samples = [
            b"/Users/" + b"someone/work",
            b"/home/" + b"someone/work",
            b"C:\\Users\\" + b"someone\\work",
            b"person" + b"@" + b"private.test",
        ]
        for sample in samples:
            self.assertTrue(privacy.findings(sample, []))
        self.assertFalse(privacy.findings(b"contributors@example.invalid", []))

    def test_private_terms_and_binary_metadata(self):
        term = b"Example Personal Name"
        self.assertTrue(privacy.findings(b"\x00" + term + b"\xff", [term]))


@unittest.skipUnless(shutil.which("gitleaks"), "Gitleaks required")
class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.command("git", "init", "-q")
        self.command("git", "config", "user.name", "Test contributors")
        self.command("git", "config", "user.email", "contributors@example.invalid")

    def command(self, *args):
        return subprocess.run(args, cwd=self.root, capture_output=True, check=True)

    def scan(self, *args):
        return subprocess.run(
            [sys.executable, str(SCANNER), *args], cwd=self.root, capture_output=True
        )

    def test_staged_bad_worktree_clean_blocks(self):
        path = self.root / "sample.txt"
        value = b"/Users/" + b"someone/private"
        path.write_bytes(value)
        self.command("git", "add", "sample.txt")
        path.write_text("clean working tree")
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_staged_clean_worktree_bad_passes(self):
        path = self.root / "sample.txt"
        path.write_text("public text")
        self.command("git", "add", "sample.txt")
        path.write_bytes(b"/Users/" + b"someone/private")
        self.assertEqual(self.scan().returncode, 0)

    def test_known_token_shape_blocks(self):
        token = b"ghp_" + hashlib.sha256(b"nonsecret fixture").hexdigest()[:36].encode()
        (self.root / "sample.txt").write_bytes(b"credential = " + token)
        self.command("git", "add", "sample.txt")
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(token, result.stdout + result.stderr)

    def test_missing_tool_fails_closed(self):
        result = subprocess.run(
            [sys.executable, str(SCANNER)],
            cwd=self.root,
            env={**os.environ, "PATH": ""},
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)

    def test_author_metadata_is_out_of_scope(self):
        (self.root / "sample.txt").write_text("public text")
        self.command("git", "add", "sample.txt")
        address = "person" + "@" + "private.test"
        self.command("git", "-c", f"user.email={address}", "commit", "-qm", "Fixture")
        result = self.scan("--history")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(address.encode(), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
