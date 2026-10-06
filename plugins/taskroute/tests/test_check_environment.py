"""Binary dependency integrity, scoped runtime tools and actual local network policy."""

import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_environment as environment
import native_route
import runtime
import test_repository_task as fixtures
import verify_structured_flow


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.deps = self.project / "web/node_modules"
        self.deps.mkdir(parents=True)
        (self.deps / "binding.node").write_bytes(b"\xcf\xfa\xed\xfe")
        (self.deps / "entry.js").write_text("export default 1;\n")
        (self.deps / "binding-link.node").symlink_to("binding.node")
        self.root = self.base / "run"
        self.root.mkdir()
        self.spec = {"dependency_roots": ["web/node_modules"]}

    def manifest(self, value=None):
        config = environment.validate(value or self.spec, self.project, ["web/source.js"])
        manifest = dict(
            project_root=str(self.project),
            workspace=str(self.root / "workspace"),
            check_environment=config,
        )
        environment.prepare(self.root, manifest)
        return manifest

    def test_binary_bytes_and_relative_symlinks_survive_sealed_disposable_copy(self):
        manifest = self.manifest()
        copy = self.root / "scratch/check"
        copy.mkdir(parents=True)
        environment.install_copy(self.root, manifest, copy)
        self.assertEqual((copy / "web/node_modules/binding.node").read_bytes(), b"\xcf\xfa\xed\xfe")
        self.assertEqual(os.readlink(copy / "web/node_modules/binding-link.node"), "binding.node")
        environment.verify(manifest)
        environment.verify_copy(manifest, copy)

    def test_dependency_or_snapshot_byte_and_mode_changes_are_rejected(self):
        manifest = self.manifest()
        original = self.deps / "binding.node"
        original.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "FROZEN_DEPENDENCY_CHANGED"):
            environment.verify(manifest)
        original.write_bytes(b"\xcf\xfa\xed\xfe")
        (self.root / "dependencies/web/node_modules/entry.js").chmod(0o700)
        with self.assertRaisesRegex(ValueError, "FROZEN_DEPENDENCY_CHANGED"):
            environment.verify(manifest)

    def test_dependency_escape_and_source_overlap_are_rejected(self):
        outside = self.base / "private"
        outside.write_bytes(b"private")
        (self.deps / "escape").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "DEPENDENCY_SYMLINK_ESCAPE"):
            environment.validate(self.spec, self.project, ["web/source.js"])
        (self.deps / "escape").unlink()
        with self.assertRaisesRegex(ValueError, "DEPENDENCY_SOURCE_OVERLAP"):
            environment.validate(self.spec, self.project, ["web/node_modules/entry.js"])

    def test_declared_cache_writes_are_allowed_but_package_mutations_are_rejected(self):
        manifest = self.manifest(dict(self.spec, cache_paths=["web/node_modules/.vite"]))
        copy = self.root / "scratch/check"
        copy.mkdir(parents=True)
        environment.install_copy(self.root, manifest, copy)
        cache = copy / "web/node_modules/.vite"
        cache.mkdir()
        (cache / "temporary.js").write_text("generated")
        environment.verify_copy(manifest, copy)
        (copy / "web/node_modules/entry.js").write_text("changed")
        with self.assertRaisesRegex(ValueError, "CHECK_DEPENDENCY_MUTATED"):
            environment.verify_copy(manifest, copy)

    def test_runtime_executable_is_pinned_and_changes_are_rejected(self):
        tool = self.base / "node"
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o700)
        manifest = self.manifest(dict(self.spec, executables=[str(tool)]))
        self.assertEqual(environment.executable_paths(manifest), [str(self.base)])
        tool.write_text("#!/bin/sh\nexit 1\n")
        with self.assertRaisesRegex(ValueError, "RUNTIME_EXECUTABLE_CHANGED"):
            environment.verify(manifest)

    def test_unsafe_capabilities_and_cache_environment_are_rejected(self):
        for value in [
            {"dependency_roots": ["../private"]},
            {"dependency_roots": ["web/node_modules", "web/node_modules/nested"]},
            {"loopback_ports": [True]},
            {"loopback_ports": [80]},
            {"network": True},
            {"read_roots": [str(self.base)]},
            {"cache_environment": {"NODE_OPTIONS": "cache"}},
            {"cache_environment": {"APP_CACHE": "../private"}},
            {"cache_environment": {"APP_CACHE": "web/source.js"}},
            dict(self.spec, cache_paths=["web/other"]),
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                environment.validate(value, self.project, ["web/source.js"])

    def test_cache_environment_stays_inside_each_check_copy(self):
        manifest = self.manifest(dict(self.spec, cache_environment={"APP_CACHE": "web/cache"}))
        copy = self.root / "scratch/check"
        self.assertEqual(
            environment.environment_values(manifest, copy), {"APP_CACHE": str(copy / "web/cache")}
        )

    def test_empty_environment_preserves_legacy_policy(self):
        self.assertEqual(environment.validate({}, self.project, []), {})
        environment.verify({})
        environment.verify({"check_environment": {}})
        policy = runtime.check_policy(self.root / "workspace", self.root / "scratch")
        self.assertIn("(deny network*)", policy)
        self.assertNotIn("network-outbound", policy)


@unittest.skipUnless(sys.platform == "darwin", "macOS policy required")
class EnvironmentExecutionTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.RepositoryTests(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_actual_check_reads_binary_dependencies_and_isolates_cache_writes(self):
        c = self.case
        deps = c.project / "deps"
        deps.mkdir()
        (deps / "binary.node").write_bytes(b"\xcf\xfa\xed\xfe")
        c.spec["check_environment"] = {"dependency_roots": ["deps"], "cache_paths": ["deps/cache"]}
        c.spec["checks"] = [
            dict(
                name="acceptance",
                argv=[
                    sys.executable,
                    "-B",
                    "-c",
                    "from pathlib import Path; assert Path('deps/binary.node').read_bytes()==b'\\xcf\\xfa\\xed\\xfe'; "
                    "Path('deps/cache').mkdir(); Path('deps/cache/output').write_text('cached'); "
                    "assert Path('message.txt').read_text()=='new\\n'",
                ],
                timeout_seconds=10,
            )
        ]
        c.prepare()
        c.candidate()
        self.assertEqual(c.verify(), 0)
        self.assertFalse((deps / "cache").exists())
        self.assertEqual((deps / "binary.node").read_bytes(), b"\xcf\xfa\xed\xfe")

    def test_actual_loopback_policy_permits_declared_port_and_denies_another(self):
        c = self.case
        with socket.socket() as allowed, socket.socket() as denied:
            allowed.bind(("127.0.0.1", 0))
            allowed.listen()
            denied.bind(("127.0.0.1", 0))
            denied.listen()
            good, bad = allowed.getsockname()[1], denied.getsockname()[1]
            c.spec["check_environment"] = {"loopback_ports": [good]}
            c.spec["checks"] = [
                dict(
                    name="acceptance",
                    argv=[
                        sys.executable,
                        "-B",
                        "-c",
                        "import socket; s=socket.socket(); s.settimeout(2); "
                        f"s.connect(('127.0.0.1',{good})); s.close(); "
                        "s=socket.socket(); s.settimeout(2); "
                        f"assert s.connect_ex(('127.0.0.1',{bad})) != 0",
                    ],
                    timeout_seconds=10,
                )
            ]
            c.prepare()
            c.candidate()
            self.assertEqual(c.verify(), 0)

    def test_modified_loopback_policy_is_rejected_before_launch(self):
        c = self.case
        c.spec["check_environment"] = {"loopback_ports": [5198]}
        c.prepare()
        policy = c.run / "test.sb"
        policy.write_text(policy.read_text() + "\n(allow network*)\n")
        with self.assertRaisesRegex(ValueError, "CHECK_POLICY_CHANGED"):
            fixtures.collector.launch_environment(
                c.run, json.loads((c.run / "manifest.json").read_text())
            )
        self.assertFalse((c.run / "live-launch.reserved.json").exists())

    def test_clean_runtime_environment_keeps_secrets_out(self):
        c = self.case
        script = "import os; assert 'PROVIDER_SECRET' not in os.environ; assert os.environ['APP_CACHE'].endswith('cache')"
        with patch.dict(os.environ, PROVIDER_SECRET="private"):
            result = runtime.bounded_check(
                [sys.executable, "-B", "-c", script],
                c.base,
                10,
                extra_paths=[str(Path(sys.executable).parent)],
                cache_environment={"APP_CACHE": str(c.base / "cache")},
            )
        self.assertEqual(result["returncode"], 0)

    def test_unix_socket_directory_is_owned_and_other_temporary_writes_are_denied(self):
        c = self.case
        with (
            tempfile.TemporaryDirectory(prefix="tr-", dir="/private/tmp") as allowed,
            tempfile.TemporaryDirectory(prefix="tr-", dir="/private/tmp") as denied,
        ):
            policy = c.base / "socket.sb"
            policy.write_text(runtime.check_policy(c.project, c.base, temporary_paths=[allowed]))
            script = (
                "import os, socket; from pathlib import Path; "
                "assert os.environ['MAC_CHROMIUM_TMPDIR']==os.environ['TMPDIR']; "
                "s=socket.socket(socket.AF_UNIX); "
                "s.bind(os.environ['TMPDIR']+'/socket'); s.listen(); "
                "t=socket.socket(socket.AF_UNIX); "
                "t.connect(os.environ['TMPDIR']+'/socket'); t.close(); s.close(); "
                f"p=Path({denied!r})/'escape'; "
                "\ntry: p.write_text('forbidden')\n"
                "except PermissionError: pass\nelse: raise AssertionError('outside write allowed')"
            )
            result = runtime.bounded_check(
                ["/usr/bin/sandbox-exec", "-f", str(policy), sys.executable, "-B", "-c", script],
                c.base,
                10,
                temporary_directory=allowed,
            )
            self.assertEqual(result["returncode"], 0, result["feedback"])
            self.assertFalse((Path(denied) / "escape").exists())

    def test_native_route_uses_frozen_verifier_and_host_rechecks_dependency_candidate(self):
        c = self.case
        deps = c.project / "deps"
        deps.mkdir()
        (deps / "binary.node").write_bytes(b"\xcf\xfa\xed\xfe")
        c.spec["model"] = "gpt-6.1-sol"
        c.spec["check_environment"] = {"dependency_roots": ["deps"]}
        spec = c.base / "task.json"
        spec.write_text(json.dumps(c.spec))
        native_route.prepare(spec, c.project, c.run, selection_reason="tool_requirement")
        manifest = json.loads((c.run / "manifest.json").read_text())
        self.assertIn(manifest["verify_command"], (c.run / "worker-prompt.txt").read_text())
        native_route.reserve(c.run, "worker")
        native_route.dispatch(c.run, "worker", "/root/fixture_worker", "gpt-6.1-sol")
        (c.run / "workspace/message.txt").write_text("new\n")
        (c.run / "workspace/note.txt").write_text("ready\n")
        self.assertEqual(verify_structured_flow.verify(c.run), 0)
        result = c.base / "worker.txt"
        result.write_text('TASKROUTE_RESULT: {"status":"READY_FOR_LEAD","reason":"Checks passed"}')
        receipt = native_route.worker_complete(c.run, result)
        self.assertEqual(receipt["status"], "CANDIDATE_FROZEN")
        self.assertEqual(receipt["checks"][0]["exit_code"], 0)
        self.assertEqual((deps / "binary.node").read_bytes(), b"\xcf\xfa\xed\xfe")


if __name__ == "__main__":
    unittest.main()
