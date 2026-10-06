"""Real macOS SQLite readiness and bounded denial checks; no providers."""

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import compact_delivery_packet as packet
import native_route as native
import taskroute


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox required")
class SQLiteBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Default /private/var temp paths miss the denied /Users ancestor bug.
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / "input.txt").write_text("synthetic\n")
        self.spec = dict(
            mode="repository",
            contract="Keep synthetic input.",
            files=["input.txt"],
            writable_paths=["input.txt"],
            checks=[
                dict(name="synthetic", argv=[sys.executable, "-B", "-c", "pass"], timeout_seconds=5)
            ],
            model="gpt-6.1-sol",
            permissions=dict(network=False, install=False),
            acceptance=[dict(id="AC1", text="Keep input", evidence=["file:input.txt"])],
            non_goals=[],
            check_inputs=[],
        )
        self.spec_path = self.base / "task.json"
        self.spec_path.write_text(json.dumps(self.spec))

    def prepare(self, route):
        root = self.base / route
        if route == "native":
            native.prepare(self.spec_path, self.project, root)
        else:
            actual = shutil.which
            with patch.object(
                taskroute.shutil,
                "which",
                side_effect=lambda name: sys.executable if name == "claude" else actual(name),
            ):
                taskroute.prepare(self.spec_path, self.project, root)
        return root

    def test_both_generated_policies_sqlite_and_negative_boundaries(self):
        sentinel = self.base / "outside.txt"
        sentinel.write_text("synthetic outside\n")
        for route in ("native", "claude"):
            with self.subTest(route=route):
                root = self.prepare(route)
                with (
                    tempfile.TemporaryDirectory(dir=root / "scratch") as directory,
                    socket.socket() as listener,
                ):
                    listener.bind(("127.0.0.1", 0))
                    listener.listen(1)
                    script = """import errno,os,socket,sqlite3,sys
from pathlib import Path
root=Path.cwd()
for name in ('absolute','relative','uri'):
    p=root/(name+'.sqlite3')
    location=p.as_uri()+'?mode=rwc' if name=='uri' else str(p) if name=='absolute' else p.name
    with sqlite3.connect(location,uri=name=='uri') as db:
        db.execute('create table evidence(value text)');db.execute('insert into evidence values (?)',('synthetic',));db.commit()
        assert db.execute('select value from evidence').fetchone()==('synthetic',)
outside=Path(sys.argv[1]);parent=Path(sys.argv[2]);port=int(sys.argv[3])
def denied(fn):
    try:fn()
    except PermissionError as e:assert e.errno==errno.EPERM
    else:raise AssertionError('Forbidden operation succeeded')
denied(lambda:outside.read_text())
denied(lambda:outside.write_text('unexpected'))
denied(lambda:os.listdir(parent))
def network():
    with socket.create_connection(('127.0.0.1',port),timeout=1):pass
denied(network)
assert os.lstat(parent).st_mode
print('SQLite3 modes and four negative boundaries PASS')
"""
                    proc = subprocess.run(
                        [
                            "/usr/bin/sandbox-exec",
                            "-f",
                            str(root / "test.sb"),
                            sys.executable,
                            "-B",
                            "-c",
                            script,
                            str(sentinel),
                            str(root),
                            str(listener.getsockname()[1]),
                        ],
                        cwd=directory,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(sentinel.read_text(), "synthetic outside\n")

    def strip_metadata(self, root):
        policy = root / "test.sb"
        policy.write_text(
            "".join(
                line + "\n"
                for line in policy.read_text().splitlines()
                if not line.startswith("(allow file-read-metadata ")
            )
        )

    def test_native_db_denial_prevents_role_reservation(self):
        root = self.prepare("native")
        self.strip_metadata(root)
        with self.assertRaisesRegex(ValueError, "TEST_ENVIRONMENT_UNAVAILABLE"):
            native.reserve(root, "worker")
        self.assertFalse((root / "native-worker.reserved.json").exists())
        self.assertEqual(list((root / "scratch").iterdir()), [])

    def test_claude_db_denial_prevents_launch_preflight(self):
        root = self.prepare("claude")
        self.strip_metadata(root)
        with self.assertRaisesRegex(ValueError, "TEST_ENVIRONMENT_UNAVAILABLE"):
            packet.preflight(root)
        self.assertFalse((root / "live-launch.reserved.json").exists())
        self.assertEqual(list((root / "scratch").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
