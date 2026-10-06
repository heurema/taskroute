"""Reason metadata checks; inner role transport is a synthetic local fixture."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import native_route as native
import repository_task as repository
import taskroute


class NativeReasonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / "message.txt").write_bytes(b"old\n")
        (self.project / "check.py").write_text("pass\n")
        self.spec = dict(
            mode="repository",
            contract="Write the new line.",
            files=["message.txt", "check.py"],
            writable_paths=["message.txt"],
            model="gpt-6.1-sol",
            permissions=dict(network=False, install=False),
            checks=[
                dict(name="fixture", argv=[sys.executable, "-B", "check.py"], timeout_seconds=5)
            ],
            acceptance=[
                dict(id="AC1", text="New line.", evidence=["file:message.txt", "check:fixture"])
            ],
            non_goals=[dict(id="NG1", text="Preserve check.")],
            check_inputs=["check.py"],
        )
        self.spec_path = self.base / "spec.json"
        self.spec_path.write_text(json.dumps(self.spec))

    def read(self, path):
        return json.loads(path.read_text())

    def accepted(self, reason="unknown", legacy=False, blocked=False):
        root = self.base / "run"
        native.prepare(self.spec_path, self.project, root, selection_reason=reason)
        if legacy:
            manifest = self.read(root / "manifest.json")
            del manifest["selection_reason"]
            (root / "manifest.json").write_text(json.dumps(manifest))
        native.reserve(root, "worker")
        native.dispatch(root, "worker", "/root/synthetic_reason_worker", "gpt-6.1-sol")
        (root / "workspace/message.txt").write_bytes(b"new\n")
        worker = self.base / "worker.txt"
        worker.write_text(
            'TASKROUTE_RESULT: {"status":"READY_FOR_LEAD","reason":"synthetic fixture"}'
        )
        checks = [
            dict(
                name="fixture",
                argv=self.spec["checks"][0]["argv"],
                exit_code=0,
                stop_reason=None,
                summary="Synthetic inner execution; no model transport",
            )
        ]
        with patch.object(native.repository, "execute", return_value=checks):
            native.worker_complete(root, worker)
        native.reserve(root, "reviewer")
        native.dispatch(root, "reviewer", "/root/synthetic_reason_reviewer", "gpt-6-astra")
        review = self.base / "review.txt"
        review.write_text(
            "TASKROUTE_REVIEW: "
            + json.dumps(
                dict(
                    verdict="CHANGES" if blocked else "APPROVE",
                    acceptance=[
                        dict(
                            id="AC1",
                            status="NOT_MET" if blocked else "MET",
                            evidence=["file:message.txt", "check:fixture"],
                            detail="Synthetic byte fixture",
                        )
                    ],
                    non_goals=[dict(id="NG1", status="KEPT", detail="Frozen fixture check")],
                )
            )
        )
        result = native.finish(root, review)
        if legacy:
            del result["selection_reason"]
            (root / "native-receipt.json").write_text(json.dumps(result))
        return root, result

    def test_all_enum_values_and_default(self):
        for i, reason in enumerate(native.SELECTION_REASONS):
            with self.subTest(reason=reason):
                root = self.base / f"enum-{i}"
                native.prepare(self.spec_path, self.project, root, selection_reason=reason)
                self.assertEqual(self.read(root / "manifest.json")["selection_reason"], reason)
        root = self.base / "default"
        native.prepare(self.spec_path, self.project, root)
        self.assertEqual(self.read(root / "manifest.json")["selection_reason"], "unknown")

    def test_invalid_api_values_precede_reads_and_effects(self):
        for i, reason in enumerate([None, True, 1, [], {}, "", "private prompt", "Owner_Request"]):
            with self.subTest(reason=reason):
                root = self.base / f"invalid-{i}"
                with self.assertRaisesRegex(ValueError, "INVALID_NATIVE_SELECTION_REASON"):
                    native.prepare(
                        self.base / "missing.json", self.project, root, selection_reason=reason
                    )
                self.assertFalse(root.exists())

    def test_cli_enum_default_and_invalid_value(self):
        for i, reason in enumerate([*native.SELECTION_REASONS, None, "private prompt"]):
            with self.subTest(reason=reason):
                root = self.base / f"cli-{i}"
                argv = [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "taskroute.py"),
                    "native-prepare",
                    str(self.spec_path),
                    "--project",
                    str(self.project),
                    "--run",
                    str(root),
                ]
                if reason is not None:
                    argv += ["--selection-reason", reason]
                process = subprocess.run(argv, capture_output=True, text=True, timeout=10)
                if reason == "private prompt":
                    self.assertNotEqual(process.returncode, 0)
                    self.assertFalse(root.exists())
                else:
                    self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                    self.assertEqual(
                        self.read(root / "manifest.json")["selection_reason"], reason or "unknown"
                    )
                    self.assertEqual(json.loads(process.stdout)["model_calls"], 0)

    def test_receipt_reason_and_existing_evidence_preserved(self):
        root, result = self.accepted("task_family_evidence")
        self.assertEqual(native.receipt(root), result)
        self.assertEqual(result["selection_reason"], "task_family_evidence")
        self.assertEqual(result["status"], "READY_FOR_LEAD_REVIEW")
        self.assertEqual(result["route"], "codex-native")
        self.assertIn("+new\n", result["diff"])
        self.assertEqual(result["dispatches"]["worker"]["requested_model"], "gpt-6.1-sol")
        self.assertEqual(result["dispatches"]["reviewer"]["requested_model"], "gpt-6-astra")
        for field in ("actual_charge", "subscription_quota", "token_usage", "backend_model"):
            self.assertIsNone(result[field])
        self.assertEqual((self.project / "message.txt").read_bytes(), b"old\n")

    def test_receipt_reason_enum_mismatch_and_removal_rejected(self):
        root, result = self.accepted()
        for reason in ["owner_request", "private prompt", None, True]:
            with self.subTest(reason=reason):
                changed = dict(result, selection_reason=reason)
                (root / "native-receipt.json").write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    native.receipt(root)
        del result["selection_reason"]
        (root / "native-receipt.json").write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, "NATIVE_RECEIPT_EVIDENCE_CHANGED"):
            native.receipt(root)

    def test_legacy_readback_defaults_without_rewriting_artifacts(self):
        root, result = self.accepted(legacy=True)
        before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(native.receipt(root), dict(result, selection_reason="unknown"))
        after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_changed_manifest_reason_rejected_by_bound_hashes(self):
        root, _ = self.accepted("owner_request")
        manifest = self.read(root / "manifest.json")
        manifest["selection_reason"] = "default_policy"
        (root / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            native.receipt(root)

    def test_invalid_manifest_reason_cannot_reserve(self):
        root = self.base / "run"
        native.prepare(self.spec_path, self.project, root)
        manifest = self.read(root / "manifest.json")
        manifest["selection_reason"] = "private prompt"
        (root / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "INVALID_NATIVE_SELECTION_REASON"):
            native.reserve(root, "worker")
        self.assertFalse((root / "native-worker.reserved.json").exists())

    def test_negative_outcome_remains_blocked(self):
        root, result = self.accepted("tool_requirement", blocked=True)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(native.receipt(root), result)

    def test_diff_and_hash_tampering_still_rejected(self):
        root, result = self.accepted()
        for field, value in [("diff", "forged"), ("file_hashes", {})]:
            with self.subTest(field=field):
                changed = dict(result, **{field: value})
                (root / "native-receipt.json").write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, "NATIVE_RECEIPT_EVIDENCE_CHANGED"):
                    native.receipt(root)

    def test_repository_schema_and_claude_default_unchanged(self):
        with self.assertRaisesRegex(ValueError, "INVALID_REPOSITORY_FIELDS"):
            repository.validate(dict(self.spec, selection_reason="owner_request"), self.project)
        self.assertEqual(taskroute.prepare.__kwdefaults__["route"], "claude")
        self.assertNotIn("selection_reason", taskroute.prepare.__kwdefaults__)


if __name__ == "__main__":
    unittest.main()
