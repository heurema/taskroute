"""Frozen stdlib execution primitives; no project runtime dependencies."""

import json
import os
import selectors
import signal
import subprocess
import tempfile
import time
from pathlib import Path


class TransportError(RuntimeError):
    pass


def clean_environment() -> dict[str, str]:
    # Subscription/keychain only. Do not inherit provider keys, endpoint overrides,
    # model overrides, nested sessions, or arbitrary project environment variables.
    names = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "USER", "LOGNAME", "SHELL")
    return {name: os.environ[name] for name in names if name in os.environ}


def check_policy(workspace, scratch, *, loopback_ports=(), read_files=(), temporary_paths=()):
    """Content stays scoped; SQLite can resolve exact owned ancestor metadata."""
    workspace, scratch = Path(workspace).resolve(), Path(scratch).resolve()
    policy = '(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(deny file-read* (subpath "/Users"))\n'
    policy += (
        "(allow file-read* (subpath "
        + json.dumps(str(workspace))
        + ") (subpath "
        + json.dumps(str(scratch))
        + "))\n"
    )
    policy += (
        "(allow file-write* (subpath " + json.dumps(str(scratch)) + ') (literal "/dev/null"))\n'
    )
    for port in loopback_ports:
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("INVALID_LOOPBACK_PORT")
        endpoint = json.dumps(f"localhost:{port}")
        policy += f"(allow network-bind (local ip {endpoint}))\n"
        policy += f"(allow network-inbound (local ip {endpoint}))\n"
        policy += f"(allow network-outbound (remote ip {endpoint}))\n"
    if read_files:
        policy += (
            "(allow file-read* "
            + " ".join("(literal " + json.dumps(str(Path(p).resolve())) + ")" for p in read_files)
            + ")\n"
        )
    for temporary in temporary_paths:
        scoped = json.dumps(str(Path(temporary).resolve()))
        policy += f"(allow file-read* file-write* (subpath {scoped}))\n"
        policy += f"(allow network-bind network-inbound network-outbound (subpath {scoped}))\n"
    ancestors = sorted(
        {
            str(parent)
            for root in (workspace, scratch, *(Path(p).resolve() for p in read_files))
            for parent in root.parents
            if parent.is_relative_to(Path("/Users"))
        }
    )
    if ancestors:
        policy += (
            "(allow file-read-metadata "
            + " ".join("(literal " + json.dumps(parent) + ")" for parent in ancestors)
            + ")\n"
        )
    return policy


def readiness_script(inputs=()):
    """Probe actual DB create/commit/read, not just SQLite import."""
    return (
        "import pathlib, sqlite3, unittest; "
        + "[pathlib.Path(p).open('rb').close() for p in "
        + repr(list(inputs))
        + "]; "
        + "pathlib.Path('probe').write_bytes(b'preflight'); "
        + "db=sqlite3.connect(str(pathlib.Path('probe.sqlite3').resolve())); "
        + "db.execute('create table evidence(value text)'); "
        + "db.execute('insert into evidence values (?)', ('synthetic',)); db.commit(); "
        + "assert db.execute('select value from evidence').fetchone()==('synthetic',); db.close()"
    )


def sqlite_readiness(root, python, inputs=()):
    """Local preparation only; errors precede native submission reservation."""
    with tempfile.TemporaryDirectory(dir=Path(root) / "scratch") as directory:
        result = bounded_check(
            [
                "/usr/bin/sandbox-exec",
                "-f",
                str(Path(root) / "test.sb"),
                python,
                "-B",
                "-c",
                readiness_script(inputs),
            ],
            Path(directory),
            10,
        )
    if result["returncode"] != 0 or result["stop_reason"]:
        raise ValueError("TEST_ENVIRONMENT_UNAVAILABLE")


class Journal:
    """Durable effect reservations owned by one frozen local run directory."""

    def __init__(self, root: Path):
        self.root = root

    def reserve(self, name: str, **metadata) -> None:
        if not name or not all(c.isalnum() or c in "-_" for c in name):
            raise ValueError("INVALID_RESERVATION_NAME")
        path = self.root / (name + ".reserved.json")
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise TransportError("ALREADY_CONSUMED") from exc
        with os.fdopen(fd, "w") as stream:
            json.dump({"state": "consumed_before_effect", **metadata}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def event(self, kind: str, **metadata) -> None:
        with (self.root / "events.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {"schema_version": 1, "time": time.time(), "kind": kind, **metadata},
                    sort_keys=True,
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())


def bounded_check(
    argv, workspace, timeout, *, extra_paths=(), cache_environment=None, temporary_directory=None
):
    """Reviewed command/code only. Empty credential environment; no sandbox claim."""
    temporary = (
        str(temporary_directory)
        if temporary_directory
        else tempfile.mkdtemp(prefix=".taskroute-tmp-", dir=workspace)
    )
    env = {
        "PATH": ":".join([*extra_paths, "/usr/bin", "/bin"]),
        "HOME": str(workspace),
        "TMPDIR": temporary,
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(workspace / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if temporary_directory:
        # Chromium's macOS temp lookup deliberately ignores TMPDIR.
        env["MAC_CHROMIUM_TMPDIR"] = temporary
    env.update(cache_environment or {})
    proc = subprocess.Popen(
        argv,
        cwd=workspace,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    data = bytearray()
    deadline = time.monotonic() + timeout
    reason = None
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            while sel.get_map():
                if time.monotonic() >= deadline:
                    reason = "CHECK_TIMEOUT"
                    break
                for key, _ in sel.select(min(0.1, max(0, deadline - time.monotonic()))):
                    block = os.read(key.fd, 8192)
                    if not block:
                        sel.unregister(key.fileobj)
                    else:
                        data.extend(block)
                        if len(data) > 65536:
                            reason = "CHECK_OUTPUT_CAP"
                            break
                if reason:
                    break
        if reason is None:
            try:
                proc.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                reason = "CHECK_TIMEOUT"
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        proc.stdout.close()
    return {
        "returncode": proc.returncode,
        "stop_reason": reason,
        "feedback": bytes(data[:65536]).decode("utf-8", errors="replace")[:12000],
    }


def unittest_script(pattern: str, result_name: str) -> str:
    """Build the same isolated unittest entrypoint for worker and frozen checks."""
    return f"""import json
import sys
import unittest
from pathlib import Path

sys.path[:0] = ["src", "tests"]
suite = unittest.defaultTestLoader.discover("tests", pattern={pattern!r})
result = unittest.TextTestRunner().run(suite)
Path({result_name!r}).write_text(json.dumps({{
    "tests": result.testsRun,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "skips": len(result.skipped),
}}))
sys.exit(not result.wasSuccessful())
"""
