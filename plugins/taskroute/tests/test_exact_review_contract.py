"""Saved real failure and task-specific reviewer guidance; no model calls."""

import copy
import hashlib
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from task_contract import assess, review_instruction

FIXTURE = pathlib.Path(__file__).parent / "fixtures/review-extra-id.json"


class ExactReviewContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text())
        self.spec = self.fixture["spec"]
        # Independently authored valid fixture, not a normalization of the failed review.
        self.good = dict(
            verdict="APPROVE",
            acceptance=[
                dict(
                    id=c["id"],
                    status="MET",
                    evidence=c["evidence"],
                    detail="Offline fixture evidence, not model acceptance",
                )
                for c in self.spec["acceptance"]
            ],
            non_goals=[
                dict(id=c["id"], status="KEPT", detail="Frozen fixture scope")
                for c in self.spec["non_goals"]
            ],
        )

    def check(self, review):
        return assess(
            self.spec,
            "TASKROUTE_REVIEW: " + json.dumps(review),
            "TASKROUTE_RESULT: " + json.dumps(self.fixture["coordinator"]),
            self.fixture["bodies"],
        )

    def test_exact_saved_extra_id_remains_rejected_and_unchanged(self):
        original = copy.deepcopy(self.fixture["review"])
        self.assertEqual(
            hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest(),
            self.fixture["saved_review_sha256"],
        )
        out = self.check(original)
        self.assertIn("REVIEW_OUTCOME_INVALID: INCOMPLETE_FINDINGS", out["reasons"])
        self.assertEqual(out["reviewer_outcome"], original)
        self.assertEqual(original["acceptance"][-1]["id"], "AC3_PLACEHOLDER_REMOVED")

    def test_complete_receipt_accepted(self):
        self.assertEqual(self.check(self.good)["reasons"], [])

    def test_unknown_id_never_accepted_even_if_met(self):
        for status in ["MET", "UNKNOWN"]:
            bad = copy.deepcopy(self.good)
            bad["acceptance"].append(
                dict(
                    id="AC3_PLACEHOLDER_REMOVED",
                    status=status,
                    evidence=["review"],
                    detail="Invented criterion",
                )
            )
            self.assertIn(
                "REVIEW_OUTCOME_INVALID: INCOMPLETE_FINDINGS",
                self.check(bad)["reasons"],
            )

    def test_known_id_unknown_remains_semantic_failure(self):
        bad = copy.deepcopy(self.good)
        bad["acceptance"][0]["status"] = "UNKNOWN"
        self.assertTrue(self.check(bad)["reasons"])

    def test_missing_duplicate_and_wrong_array_fail(self):
        for array in ["acceptance", "non_goals"]:
            bad = copy.deepcopy(self.good)
            bad[array].pop()
            self.assertTrue(self.check(bad)["reasons"])
            bad = copy.deepcopy(self.good)
            bad[array].append(copy.deepcopy(bad[array][0]))
            self.assertIn("REVIEW_OUTCOME_INVALID: DUPLICATE_FINDING", self.check(bad)["reasons"])
        bad = copy.deepcopy(self.good)
        bad["non_goals"][0]["id"] = "AC1"
        self.assertTrue(self.check(bad)["reasons"])

    def test_prompt_shape_uses_only_exact_task_ids(self):
        prompt = review_instruction(self.spec)
        shape = json.JSONDecoder().raw_decode(prompt.split("Complete task-specific shape: ", 1)[1])[
            0
        ]
        self.assertEqual([r["id"] for r in shape["acceptance"]], ["AC1", "AC2"])
        self.assertEqual([r["id"] for r in shape["non_goals"]], ["NG1"])
        self.assertNotIn("AC3_PLACEHOLDER_REMOVED", prompt)
        self.assertIn("no other IDs", prompt)
        self.assertTrue(all(r["status"] == "UNKNOWN" for r in shape["acceptance"]))

    def test_guidance_is_generated_from_nonstandard_ids_not_examples(self):
        spec = copy.deepcopy(self.spec)
        for c, new in zip(spec["acceptance"], ["VALID_INPUT", "EXACT_REPORT"], strict=True):
            c["id"] = new
        spec["non_goals"][0]["id"] = "READ_ONLY"
        prompt = review_instruction(spec)
        shape = json.JSONDecoder().raw_decode(prompt.split("Complete task-specific shape: ", 1)[1])[
            0
        ]
        self.assertEqual([r["id"] for r in shape["acceptance"]], ["VALID_INPUT", "EXACT_REPORT"])
        self.assertEqual([r["id"] for r in shape["non_goals"]], ["READ_ONLY"])
        self.assertNotIn('"AC1"', prompt)
        self.assertNotIn('"NG1"', prompt)

    def test_generated_agent_uses_task_specific_instruction(self):
        import test_repository_task as fixtures

        case = fixtures.RepositoryTests(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.prepare()
        agent = json.loads((case.run / "agents.json").read_text())["reviewer"]
        self.assertIn(review_instruction(case.spec), agent["prompt"])
        self.assertEqual(agent["tools"], ["Read"])
        self.assertEqual(agent["maxTurns"], 6)


if __name__ == "__main__":
    unittest.main()
