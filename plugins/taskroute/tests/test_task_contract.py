"""Adversarial evidence/status checks independent of a live model."""

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from task_contract import assess, validate_contract


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.spec = dict(
            acceptance=[
                dict(
                    id="AC1", text="Required behavior.", evidence=["check:tests", "file:output.txt"]
                )
            ],
            non_goals=[dict(id="NG1", text="Preserve compatibility.")],
            check_inputs=["tests.sh"],
            files=["tests.sh", "output.txt"],
            writable_paths=["output.txt"],
            checks=[dict(name="tests")],
        )
        self.review = dict(
            verdict="APPROVE",
            acceptance=[
                dict(
                    id="AC1",
                    status="MET",
                    evidence=["check:tests", "file:output.txt"],
                    detail="Observed fixture output.",
                )
            ],
            non_goals=[dict(id="NG1", status="KEPT", detail="Regression evidence.")],
        )
        self.coordinator = 'TASKROUTE_RESULT: {"status":"READY_FOR_LEAD","reason":"Complete."}'

    def assessment(self, review=None, coordinator=None, bodies=None):
        return assess(
            self.spec,
            "TASKROUTE_REVIEW: " + json.dumps(self.review if review is None else review),
            self.coordinator if coordinator is None else coordinator,
            {"output.txt": "ready"} if bodies is None else bodies,
        )

    def test_complete_findings_allow_readiness(self):
        validate_contract(self.spec)
        self.assertEqual(self.assessment()["reasons"], [])

    def test_each_negative_signal_prevents_readiness(self):
        variants = []
        for field, value in [
            ("status", "UNKNOWN"),
            ("status", "NOT_MET"),
            ("evidence", []),
            ("detail", ""),
        ]:
            row = copy.deepcopy(self.review)
            row["acceptance"][0][field] = value
            variants.append(row)
        for state in ["UNKNOWN", "BROKEN"]:
            row = copy.deepcopy(self.review)
            row["non_goals"][0]["status"] = state
            variants.append(row)
        for field, value in [("verdict", "CHANGES"), ("acceptance", []), ("non_goals", [])]:
            row = copy.deepcopy(self.review)
            row[field] = value
            variants.append(row)
        for row in variants:
            with self.subTest(review=row):
                self.assertTrue(self.assessment(review=row)["reasons"])
        blocked = 'TASKROUTE_RESULT: {"status":"BLOCKED","reason":"Missing requirement."}'
        self.assertIn("COORDINATOR_BLOCKED", self.assessment(coordinator=blocked)["reasons"])

    def test_malformed_missing_and_duplicate_records_fail_closed(self):
        for text in [
            "Ready!",
            "TASKROUTE_RESULT: {}",
            self.coordinator + "\n" + self.coordinator,
            'TASKROUTE_RESULT: {"status":"BLOCKED","status":"READY_FOR_LEAD","reason":"Conflicting statuses."}',
        ]:
            with self.subTest(text=text):
                self.assertTrue(self.assessment(coordinator=text)["reasons"])
        for review in [
            None,
            [],
            {},
            "APPROVE",
            dict(self.review, acceptance=[*self.review["acceptance"], *self.review["acceptance"]]),
        ]:
            result = assess(
                self.spec, "TASKROUTE_REVIEW: " + json.dumps(review), self.coordinator, {}
            )
            self.assertTrue(result["reasons"])

    def test_missing_artifact_and_invented_reference_fail(self):
        self.assertIn("EVIDENCE_FILE_MISSING: AC1", self.assessment(bodies={})["reasons"])
        self.review["acceptance"][0]["evidence"] = ["check:invented", "file:output.txt"]
        self.assertTrue(self.assessment()["reasons"])
        self.spec["acceptance"][0]["evidence"] = ["check:invented"]
        with self.assertRaisesRegex(ValueError, "INVALID_EVIDENCE_REFERENCE"):
            validate_contract(self.spec)

    def test_frozen_checks_cannot_be_writable_or_unlisted(self):
        for paths in [["output.txt"], ["unlisted.sh"], ["tests.sh", "tests.sh"]]:
            self.spec["check_inputs"] = paths
            with (
                self.subTest(paths=paths),
                self.assertRaisesRegex(ValueError, "INVALID_FROZEN_CHECK_INPUTS"),
            ):
                validate_contract(self.spec)

    def test_empty_or_ambiguous_criteria_rejected(self):
        for field, value in [
            ("acceptance", []),
            ("acceptance", self.spec["acceptance"] * 2),
            ("non_goals", [dict(id="AC1", text="Conflicting ID.")]),
        ]:
            spec = dict(self.spec, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_contract(spec)


if __name__ == "__main__":
    unittest.main()
