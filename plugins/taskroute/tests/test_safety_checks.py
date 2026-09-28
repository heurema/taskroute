"""Guard behavior remains active under optimization and after review starts."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from verify_structured_flow import outside


class SafetyTests(unittest.TestCase):
    def test_unannotated_function_scope(self):
        self.assertEqual(outside("def work(x):\n    pass\n", "work")[2], None)
        with self.assertRaisesRegex(ValueError, "TARGET_FUNCTION_NOT_UNIQUE"):
            outside("def other():\n    pass\n", "work")

    def test_scope_check_survives_python_optimization(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            work = root / "workspace"
            work.mkdir()
            (work / "candidate.py").write_text("outside = 2\ndef work():\n    return 1\n")
            (root / "originals.json").write_text(
                json.dumps({"candidate.py": "outside = 1\ndef work():\n    pass\n"})
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "workspace": str(work),
                        "target": "candidate.py",
                        "target_function": "work",
                        "max_checks": 1,
                    }
                )
            )
            result = subprocess.run(
                [sys.executable, "-O", "-B", str(SCRIPTS / "verify_structured_flow.py"), str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("OUTSIDE_FUNCTION_CHANGE", result.stdout)
            self.assertFalse((root / "scratch").exists())

    def test_candidate_freezes_when_review_begins(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "workspace": str(root),
                        "target": "candidate.py",
                        "test_target": "test_candidate.py",
                        "model": "fixture",
                    }
                )
            )
            (root / "gate-events.jsonl").write_text(
                json.dumps({"allowed": True, "tool": "Agent"}) + "\n"
            )
            event = {
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(root / "candidate.py"), "content": "changed"},
            }
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "guard_structured_flow.py"), str(root)],
                input=json.dumps(event),
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(
                json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny"
            )


if __name__ == "__main__":
    unittest.main()
