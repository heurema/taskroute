"""Offline scope evidence and exact reviewer access; no provider execution."""

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

import test_repository_task as fixtures

repository = fixtures.repository_task


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox required")
class ReviewerScopeTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.RepositoryTests(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.m = self.case.prepare()
        self.case.candidate()
        self.assertEqual(self.case.verify(), 0)
        self.root = self.case.run
        self.work = self.root / "workspace"
        self.checks = json.loads((self.work / "checks.json").read_text())
        self.path = Path(self.checks["review_evidence_path"])

    def validate(self):
        originals = json.loads((self.root / "originals.json").read_text())
        bodies = repository.snapshot(self.m, originals)
        checks = json.loads((self.work / "checks.json").read_text())
        return repository.validate_scope_evidence(self.root, self.m, originals, bodies, checks)

    def gate(self, tool, path=None, child=True):
        args = (
            {"file_path": str(path)}
            if path
            else {"subagent_type": "reviewer", "prompt": "Review the frozen candidate."}
        )
        event = dict(hook_event_name="PreToolUse", tool_name=tool, tool_input=args)
        if child:
            event["agent_id"] = "fixture-reviewer"
        p = subprocess.run(
            [
                sys.executable,
                "-B",
                str(fixtures.SCRIPTS / "guard_structured_flow.py"),
                str(self.root),
                "--check-only",
            ],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if p.returncode:
            self.assertEqual(p.returncode, 2, p.stderr)
            return "deny"
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]

    def test_artifact_contains_original_addition_diff_and_complete_hashes(self):
        data = json.loads(self.path.read_text())
        self.assertEqual(data["writable_originals"], {"message.txt": "old\n", "note.txt": None})
        self.assertEqual(data["baseline_hashes"], self.m["source_hashes"])
        self.assertEqual(data["candidate_hashes"], self.checks["file_hashes"])
        self.assertEqual(data["changed_paths"], ["message.txt", "note.txt"])
        self.assertIn("-old\n+new\n", data["diff"])
        self.assertIn("+ready\n", data["diff"])
        self.assertNotIn("check.sh", data["writable_originals"])
        self.assertEqual(self.validate(), self.path)
        prompt = json.loads((self.root / "agents.json").read_text())["reviewer"]
        self.assertEqual(prompt["tools"], ["Read"])
        self.assertIn("review_evidence_path", prompt["prompt"])

    def test_only_exact_reviewer_read_is_added(self):
        self.assertEqual(self.gate("Agent", child=False), "allow")
        self.assertEqual(self.gate("Read", self.path), "allow")
        self.assertEqual(self.gate("Read", self.path, child=False), "deny")
        for tool in ("Write", "Edit"):
            for child in (False, True):
                self.assertEqual(self.gate(tool, self.path, child=child), "deny")
        for path in (
            self.root / "originals.json",
            self.root / "manifest.json",
            self.root / "review-evidence-other.json",
        ):
            self.assertEqual(self.gate("Read", path), "deny")
        link = self.root / "alias.json"
        link.symlink_to(self.path)
        self.assertEqual(self.gate("Read", link), "deny")
        self.assertEqual(self.gate("Read", self.work / "message.txt"), "allow")

    def test_tampered_diff_denies_read_launch_and_collection_even_if_rehashed(self):
        data = json.loads(self.path.read_text())
        data["diff"] = "forged scope claim"
        self.path.write_text(json.dumps(data))
        self.assertEqual(self.gate("Read", self.path), "deny")
        self.assertEqual(self.gate("Agent", child=False), "deny")
        self.checks["review_evidence_sha256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        for p in (self.work / "checks.json", self.root / "check-receipt-1.json"):
            p.write_text(json.dumps(self.checks))
        with self.assertRaisesRegex(ValueError, "REVIEW_EVIDENCE_CHANGED"):
            self.validate()
        self.case.evidence()
        with self.assertRaisesRegex(ValueError, "REVIEW_EVIDENCE_CHANGED"):
            fixtures.collector.collect(self.root)

    def test_changed_candidate_or_baseline_invalidates_evidence(self):
        (self.work / "message.txt").write_text("changed after checks\n")
        self.assertEqual(self.gate("Read", self.path), "deny")
        self.assertEqual(self.gate("Agent", child=False), "deny")
        (self.work / "message.txt").write_text("new\n")
        p = self.root / "originals.json"
        originals = json.loads(p.read_text())
        originals["message.txt"] = "forged baseline\n"
        p.write_text(json.dumps(originals))
        with self.assertRaisesRegex(ValueError, "REVIEW_BASELINE_CHANGED"):
            self.validate()
        self.assertEqual(self.gate("Read", self.path), "deny")

    def test_new_check_round_preserves_old_artifact_but_only_allows_current(self):
        old = self.path.read_bytes()
        (self.work / "message.txt").write_text("new\n\n")
        self.assertEqual(self.case.verify(), 0)
        checks = json.loads((self.work / "checks.json").read_text())
        new_path = Path(checks["review_evidence_path"])
        self.assertNotEqual(new_path, self.path)
        self.assertEqual(self.path.read_bytes(), old)
        self.assertEqual(self.gate("Read", self.path), "deny")
        self.assertEqual(self.gate("Read", new_path), "allow")
        (self.work / "message.txt").write_text("invalid\n")
        self.assertEqual(self.case.verify(), 1)
        self.assertFalse((self.root / "review-evidence-3.json").exists())
        self.assertEqual(self.gate("Read", new_path), "deny")
        self.assertEqual(self.gate("Agent", child=False), "deny")


if __name__ == "__main__":
    unittest.main()
