"""Offline checks for one-shot entrypoint and evidence-preserving lead output."""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compact_delivery_packet as collector
import taskroute


class DeliveryTests(unittest.TestCase):
    def test_deliver_prepares_once_and_launches_once_without_intermediate_output(self):
        argv = [
            "taskroute",
            "deliver",
            "task.json",
            "--project",
            "project",
            "--run",
            "fresh-run",
            "--review-repair",
            "--project-id",
            "project-id",
            "--task-id",
            "task-id",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(
                taskroute, "prepare", return_value={"status": "PREPARED", "run": "fresh-run"}
            ) as prepare,
            patch.object(
                taskroute.subprocess, "run", return_value=SimpleNamespace(returncode=2)
            ) as launch,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(taskroute.main(), 2)
        prepare.assert_called_once_with(
            "task.json",
            "project",
            "fresh-run",
            observe=False,
            probes=False,
            review_repair=True,
            project_id="project-id",
            task_id="task-id",
        )
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[0][-2:], ["--launch", "--lead-view"])
        self.assertEqual(output.getvalue(), "")

    def test_invalid_preparation_never_launches(self):
        with (
            patch.object(
                sys, "argv", ["taskroute", "deliver", "spec", "--project", "p", "--run", "r"]
            ),
            patch.object(taskroute, "prepare", side_effect=ValueError("INVALID")),
            patch.object(taskroute.subprocess, "run") as launch,
        ):
            with self.assertRaisesRegex(ValueError, "INVALID"):
                taskroute.main()
        launch.assert_not_called()

    def test_lead_view_preserves_all_non_task_evidence_and_unknown_fields(self):
        packet = dict(
            status="BLOCKED",
            contract="original",
            acceptance=[{"id": "AC1"}],
            non_goals=["NG1"],
            check_inputs=["tests"],
            reviewer_text="APPROVE but a known bug",
            reviewer_outcome={"findings": ["known bug"]},
            coordinator_text="limitation",
            reasons=["violation"],
            diff="actual diff",
            independent_checks=[{"exit_code": 0}],
            worker_checks=[{"exit_code": 0}],
            future_evidence={"uncertain": True},
            backlog={"status": "NOT_SAVED"},
        )
        view = collector.lead_view(packet, Path("run"))
        for key, value in packet.items():
            if key not in {"contract", "acceptance", "non_goals", "check_inputs"}:
                self.assertEqual(view[key], value)
        self.assertEqual(
            view["omitted_task_fields"], ["acceptance", "check_inputs", "contract", "non_goals"]
        )
        self.assertEqual(packet["contract"], "original")


if __name__ == "__main__":
    unittest.main()
