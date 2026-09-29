"""Frozen probe execution and failure gates; no live provider calls."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import observer
import observer_probes


@unittest.skipUnless(sys.platform == "darwin", "macOS probe sandbox")
class ProbeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "scratch").mkdir()
        (self.root / "test.sb").write_text(
            "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n"
            "(allow file-write* (subpath " + json.dumps(str(self.root / "scratch")) + "))\n"
        )
        self.m = dict(
            model="fixture-model",
            python=sys.executable,
            observer_enabled=True,
            observer_strategy="probes",
            max_observer_calls=2,
            observer_seconds=5,
            contract="content.txt must contain good.",
            checks=[],
            check_inputs=[],
            acceptance=[dict(id="AC1", text="Good content", evidence=["review"])],
            non_goals=[],
        )
        self.source = """import json
from pathlib import Path
actual = Path("content.txt").read_text()
print("TASKROUTE_PROBE_RESULTS: " + json.dumps({"results": [{"criterion_id": "AC1", "status": "PASS" if actual == "good" else "FAIL", "evidence": "expected good, actual " + actual}]}))
"""

    def provider(self, source=None):
        return patch.object(
            observer,
            "call_provider",
            return_value=dict(
                result="TASKROUTE_PROBES: "
                + json.dumps(
                    dict(
                        rationale="Execute the actual content check.", source=source or self.source
                    )
                ),
                modelUsage={"fixture-model": {"inputTokens": 1}},
            ),
        )

    def test_real_stop_correction_same_frozen_probe_one_generation(self):
        with self.provider() as provider:
            first = observer.observe(self.root, self.m, {"content.txt": "bad"})
            self.assertEqual(first["outcome"]["verdict"], "STOP")
            self.assertIn("actual bad", first["outcome"]["findings"][0]["evidence"])
            self.assertEqual(observer.observe(self.root, self.m, {"content.txt": "bad"}), first)
            second = observer.observe(self.root, self.m, {"content.txt": "good"})
            self.assertEqual(second["outcome"]["verdict"], "CONTINUE")
            self.assertEqual(first["probe_hash"], second["probe_hash"])
            self.assertEqual(second["model_usage"], {})
            self.assertEqual(provider.call_count, 1)
            observer.require_clearance(self.root, self.m, {"content.txt": "good"})
            with self.assertRaisesRegex(ValueError, "CEILING"):
                observer.observe(self.root, self.m, {"content.txt": "third"})
            (self.root / "observer-probes.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "PROBES_CHANGED"):
                observer.require_clearance(self.root, self.m, {"content.txt": "good"})

    def test_harness_crash_latches_without_regeneration(self):
        with self.provider("raise RuntimeError('broken harness')") as provider:
            with self.assertRaisesRegex(ValueError, "EXECUTION_ERROR"):
                observer.observe(self.root, self.m, {"content.txt": "bad"})
            with self.assertRaisesRegex(ValueError, "PREVIOUS_ERROR"):
                observer.observe(self.root, self.m, {"content.txt": "good"})
            self.assertEqual(provider.call_count, 1)

    def test_candidate_mutation_is_not_a_pass(self):
        with self.provider(
            'from pathlib import Path\nPath("content.txt").write_text("good")\n' + self.source
        ):
            with self.assertRaisesRegex(ValueError, "MUTATED_CANDIDATE"):
                observer.observe(self.root, self.m, {"content.txt": "bad"})

    def test_unprobed_criteria_are_unknown_not_passed(self):
        self.m["acceptance"].append(dict(id="AC2", text="Other", evidence=["review"]))
        row = dict(criterion_id="AC1", status="PASS", evidence="Actual case passed")
        result = observer_probes.result_outcome(
            "TASKROUTE_PROBE_RESULTS: " + json.dumps(dict(results=[row])), self.m
        )
        self.assertEqual(result["probe_results"][1]["status"], "UNKNOWN")
        with self.assertRaises(ValueError):
            observer_probes.result_outcome(
                "TASKROUTE_PROBE_RESULTS: "
                + json.dumps(dict(results=[row, dict(row, criterion_id="AC2")])),
                self.m,
            )

    def test_oversized_generation_stops_before_execution(self):
        with self.provider("#" + "x" * 4000) as provider:
            with self.assertRaisesRegex(ValueError, "INVALID_PROBE_PLAN"):
                observer.observe(self.root, self.m, {"content.txt": "bad"})
            self.assertEqual(provider.call_count, 1)
            self.assertFalse((self.root / "observer-probes-1-execution.json").exists())

    def test_incomplete_duplicate_and_unknown_only_cannot_clear(self):
        row = dict(criterion_id="AC1", status="PASS", evidence="Observed good")
        for rows in [[], [row, row], [dict(row, status="UNKNOWN")], [dict(row, criterion_id="X")]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                observer_probes.result_outcome(
                    "TASKROUTE_PROBE_RESULTS: " + json.dumps(dict(results=rows)), self.m
                )


if __name__ == "__main__":
    unittest.main()
