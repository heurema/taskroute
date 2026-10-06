"""Deterministic route fixtures; never launch a real model."""

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import codex_route as route
import taskroute
from runtime import TransportError


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / "message.txt").write_text("old\n")
        (self.project / "check.sh").write_text('test "$(cat message.txt)" = new\n')
        self.spec = dict(
            mode="repository",
            contract="Update message to new.",
            files=["message.txt", "check.sh"],
            writable_paths=["message.txt"],
            checks=[dict(name="check", argv=["/bin/sh", "check.sh"], timeout_seconds=5)],
            model="gpt-6.1-sol",
            permissions=dict(network=False, install=False),
            acceptance=[dict(id="AC1", text="Message is new.", evidence=["check:check"])],
            non_goals=[dict(id="NG1", text="Preserve frozen check.")],
            check_inputs=["check.sh"],
        )
        self.spec_path = self.base / "task.json"
        self.spec_path.write_text(json.dumps(self.spec))
        self.root = self.base / "run"
        actual = shutil.which
        with patch.object(
            route.shutil,
            "which",
            side_effect=lambda n: sys.executable if n == "codex" else actual(n),
        ):
            taskroute.prepare(self.spec_path, self.project, self.root, route="sol-astra")
        self.calls = []
        self.review = dict(
            verdict="APPROVE",
            acceptance=[
                dict(
                    id="AC1",
                    status="MET",
                    evidence=["check:check"],
                    detail="Frozen check exercises new message",
                )
            ],
            non_goals=[dict(id="NG1", status="KEPT", detail="Frozen source preserved")],
        )

    def transport(self, command, prompt, workspace, timeout):
        role = "worker" if not self.calls else "reviewer"
        self.calls.append(dict(role=role, command=command, prompt=prompt, workspace=workspace))
        if role == "worker":
            (workspace / "message.txt").write_text("new\n")
        text = (
            'TASKROUTE_RESULT: {"status":"READY_FOR_LEAD","reason":"Implemented."}'
            if role == "worker"
            else "TASKROUTE_REVIEW: " + json.dumps(self.review)
        )
        events = [
            dict(type="thread.started", thread_id=role + "-session", model=route.PROFILES[role]),
            dict(type="item.completed", item=dict(type="agent_message", text=text)),
            dict(type="turn.completed", usage=dict(input_tokens=10, output_tokens=5)),
        ]
        return 0, "\n".join(json.dumps(e) for e in events)

    def offline_checks(self, root, manifest, bodies, label):
        # Execute the real frozen check with stdlib on disposable inputs. The
        # production sandbox policy is separately exercised by existing tests.
        from runtime import bounded_check

        copy = root / "scratch" / label
        copy.mkdir()
        for name, body in bodies.items():
            (copy / name).write_text(body)
        proc = bounded_check(manifest["checks"][0]["argv"], copy, 5)
        return [dict(name="check", exit_code=proc["returncode"], stop_reason=proc["stop_reason"])]

    def run_route(self, transport=None):
        with patch.object(route.repository, "execute", side_effect=self.offline_checks):
            return route.run(self.root, transport or self.transport)

    def test_full_route_profiles_fresh_review_and_frozen_checks(self):
        result = self.run_route()
        self.assertEqual(result["status"], "READY_FOR_LEAD_REVIEW", result)
        self.assertEqual(
            [c["command"][c["command"].index("-m") + 1] for c in self.calls],
            list(route.PROFILES.values()),
        )
        self.assertIn("read-only", self.calls[1]["command"])
        self.assertNotEqual(self.calls[0]["workspace"], self.calls[1]["workspace"])
        self.assertNotIn("Implemented.", self.calls[1]["prompt"])
        self.assertIn("AC1", self.calls[1]["prompt"])
        self.assertIn(result["candidate"]["message.txt"], self.calls[1]["prompt"])
        self.assertEqual((self.project / "message.txt").read_text(), "old\n")
        self.assertIsNone(result["actual_charge"])
        self.assertEqual(result["live_qualification"], "UNVERIFIED")
        with self.assertRaises(TransportError):
            self.run_route()
        self.assertEqual(len(self.calls), 2)

    def test_uncertain_startup_consumes_before_effect_and_never_retries(self):
        def broken(*args):
            self.assertTrue((self.root / "codex-worker.reserved.json").exists())
            raise OSError("startup ambiguous")

        result = self.run_route(broken)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            json.loads((self.root / "worker-launch.json").read_text())["state"],
            "SUBMISSION_UNCERTAIN",
        )
        with self.assertRaises(TransportError):
            self.run_route()

    def test_unknown_identity_stops_before_checks_and_review(self):
        def unknown(*args):
            code, output = self.transport(*args)
            rows = [json.loads(s) for s in output.splitlines()]
            del rows[0]["model"]
            return code, "\n".join(json.dumps(r) for r in rows)

        result = self.run_route(unknown)
        self.assertEqual(result["reason"], "CODEX_IDENTITY_UNKNOWN")
        receipt = json.loads((self.root / "worker-receipt.json").read_text())
        self.assertIsNone(receipt["accepted_model"])
        self.assertEqual(len(self.calls), 1)
        self.assertFalse((self.root / "codex-checks.reserved.json").exists())

    def test_mismatch_keeps_requested_and_observed_separate(self):
        output = "\n".join(
            json.dumps(e)
            for e in [
                dict(type="thread.started", thread_id="s", model="wrong"),
                dict(type="item.completed", item=dict(type="agent_message", text="ok")),
                dict(type="turn.completed"),
            ]
        )
        result = route.parse(0, output, "gpt-6.1-sol")
        self.assertEqual(result["identity"], "MISMATCH")
        self.assertIsNone(result["accepted_model"])

    def test_malformed_or_failed_events_rejected(self):
        for output in [
            "not-json",
            "{}",
            '{"type":"turn.failed"}',
            '{"type":"thread.started","thread_id":"s"}',
        ]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                route.parse(0, output, "gpt-6.1-sol")

    def test_incomplete_negative_and_unknown_review_block(self):
        self.review["acceptance"] = []
        self.assertIn("INCOMPLETE_FINDINGS", self.run_route()["reason"])

    def test_negative_review_blocks(self):
        self.review["verdict"] = "CHANGES"
        self.review["acceptance"][0]["status"] = "NOT_MET"
        self.assertIn("REVIEW_REQUESTS_CHANGES", self.run_route()["reason"])

    def test_unknown_review_blocks(self):
        self.review["acceptance"][0]["status"] = "UNKNOWN"
        self.assertIn("CRITERION_NOT_MET", self.run_route()["reason"])

    def test_candidate_mutated_during_review_blocks(self):
        def mutate(*args):
            response = self.transport(*args)
            if len(self.calls) == 2:
                (self.root / "workspace/message.txt").write_text("later\n")
            return response

        self.assertEqual(self.run_route(mutate)["reason"], "CANDIDATE_CHANGED_DURING_REVIEW")

    def test_review_copy_mutation_blocks(self):
        def mutate(*args):
            response = self.transport(*args)
            if len(self.calls) == 2:
                (args[2] / "message.txt").write_text("later\n")
            return response

        self.assertEqual(self.run_route(mutate)["reason"], "REVIEW_COPY_CHANGED")

    def test_session_alias_reuse_blocks(self):
        def alias(*args):
            code, text = self.transport(*args)
            return code, text.replace("reviewer-session", "worker-session")

        self.assertEqual(self.run_route(alias)["reason"], "REVIEW_SESSION_REUSED")

    def test_frozen_input_change_blocks_before_review(self):
        def mutate(*args):
            response = self.transport(*args)
            (args[2] / "check.sh").write_text("exit 0\n")
            return response

        self.assertEqual(self.run_route(mutate)["reason"], "FROZEN_INPUT_CHANGED")
        self.assertEqual(len(self.calls), 1)

    def test_worker_blocked_outcome_stops_before_review(self):
        def blocked(*args):
            code, text = self.transport(*args)
            return code, text.replace("READY_FOR_LEAD", "BLOCKED")

        self.assertEqual(self.run_route(blocked)["reason"], "WORKER_OUTCOME_BLOCKED_OR_INVALID")
        self.assertEqual(len(self.calls), 1)

    def test_deadline_covers_prompt_pipe_backpressure(self):
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "CODEX_TIMEOUT"):
            route.invoke(
                [sys.executable, "-c", "import time; time.sleep(0.6)"],
                "x" * 1048576,
                self.base,
                0.05,
            )
        self.assertLess(time.monotonic() - started, 0.5)

    def test_submission_timeout_retains_consumed_route_reservation(self):
        def stalled(command, prompt, workspace, timeout):
            return route.invoke(
                [sys.executable, "-c", "import time; time.sleep(0.6)"],
                "x" * 1048576,
                workspace,
                0.05,
            )

        result = self.run_route(stalled)
        self.assertEqual(result["reason"], "CODEX_TIMEOUT")
        self.assertTrue((self.root / "codex-worker.reserved.json").is_file())
        with self.assertRaises(TransportError):
            self.run_route()

    def test_stdout_drained_while_submitting_large_prompt(self):
        code, output = route.invoke(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('y'*200000); sys.stdout.flush(); value=sys.stdin.read(); print(len(value))",
            ],
            "x" * 200000,
            self.base,
            3,
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, "y" * 200000 + "200000\n")

    def test_explicit_profile_required(self):
        self.spec["model"] = "claude-fixture"
        self.spec_path.write_text(json.dumps(self.spec))
        with self.assertRaisesRegex(ValueError, "WORKER_PROFILE_MISMATCH"):
            route.prepare(self.spec_path, self.project, self.base / "other")


if __name__ == "__main__":
    unittest.main()
