import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "weekly", Path(__file__).resolve().parents[1] / "scripts/metrics.py"
)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "session.jsonl"
        self.start = w.timestamp("2026-09-29T00:00:00+03:00")
        self.end = w.timestamp("2026-10-06T00:00:00+03:00")
        self.events = [
            dict(type="session_meta", payload=dict(id="owned", cwd="/project")),
            dict(type="turn_context", payload=dict(turn_id="turn", model="configured")),
        ]

    def request(self, rid="r", thread="owned", value=100, date="2026-09-29T00:00:00Z"):
        usage = dict(
            input_tokens=value,
            cached_input_tokens=50,
            cache_write_input_tokens=0,
            output_tokens=10,
            reasoning_output_tokens=3,
            total_tokens=value + 10,
        )
        return dict(
            timestamp=date,
            type="token_usage_record",
            payload=dict(thread_id=thread, turn_id="turn", response_id=rid, usage=usage),
        )

    def run_events(self, provider="codex", suffix=""):
        self.path.write_text("".join(json.dumps(e) + "\n" for e in self.events) + suffix)
        files = [dict(provider=provider, path=str(self.path), size=self.path.stat().st_size)]
        result = w.collect(files, self.start, self.end)
        self.assertEqual(result, w.collect(files, self.start, self.end))
        return result

    def test_dedup_foreign_history_and_subsets(self):
        self.events += [self.request(), self.request(), self.request("foreign", "other")]
        result = self.run_events()
        self.assertEqual(len(result["response_records"]), 1)
        self.assertEqual(result["daily_usage"][0]["usage"]["input_tokens"], 100)
        self.assertEqual(result["coverage"]["issues"]["foreign_or_missing_thread_records"], 1)

    def test_conflict_excluded_not_arbitrary_choice(self):
        self.events += [self.request(), self.request(value=101)]
        result = self.run_events()
        self.assertEqual(result["response_records"], [])
        self.assertEqual(result["coverage"]["issues"]["conflicting_responses_excluded"], 1)

    def test_moscow_boundaries(self):
        self.events += [
            self.request("before", date="2026-09-28T20:59:59Z"),
            self.request("first", date="2026-09-28T21:00:00Z"),
            self.request("end", date="2026-10-05T21:00:00Z"),
        ]
        result = self.run_events()
        self.assertEqual([r["response_id"] for r in result["response_records"]], ["first"])
        self.assertEqual(result["daily_usage"][0]["day"], "2026-09-29")

    def test_partial_and_invalid_usage(self):
        bad = self.request()
        bad["payload"]["usage"]["input_tokens"] = -1
        self.events.append(bad)
        result = self.run_events(suffix='{"type":"token_usage_record"')
        self.assertEqual(result["response_records"], [])
        self.assertEqual(result["coverage"]["issues"]["partial_final_lines"], 1)
        self.assertEqual(result["coverage"]["issues"]["invalid_codex_usage"], 1)

    def test_quota_is_not_summed_and_no_private_content_saved(self):
        event = dict(
            timestamp="2026-09-29T00:00:00Z",
            type="event_msg",
            payload=dict(
                type="token_count",
                rate_limits=dict(
                    limit_id="codex",
                    primary=dict(used_percent=30, window_minutes=10080, resets_at=1791000000),
                    credits=dict(balance="sensitive-sentinel"),
                ),
            ),
        )
        self.events += [
            event,
            event,
            dict(type="response_item", payload=dict(text="sensitive-sentinel")),
        ]
        result = self.run_events()
        self.assertEqual(len(result["quota_snapshots"]), 1)
        self.assertNotIn("sensitive-sentinel", json.dumps(result))
        self.assertEqual(result["coverage"]["counter_only_sessions"], ["owned"])

    def test_claude_progressive_message_not_double_counted(self):
        def event(output):
            return dict(
                timestamp="2026-09-29T00:00:00Z",
                type="assistant",
                sessionId="c",
                cwd="/p",
                message=dict(
                    id="msg",
                    model="claude",
                    usage=dict(
                        input_tokens=2,
                        cache_read_input_tokens=10,
                        cache_creation_input_tokens=5,
                        output_tokens=output,
                    ),
                ),
            )

        self.events = [event(1), event(20), event(1)]
        result = self.run_events("claude")
        self.assertEqual(len(result["response_records"]), 1)
        self.assertEqual(result["daily_usage"][0]["usage"]["output_tokens"], 20)

    def test_frozen_prefix_ignores_appends(self):
        self.events.append(self.request())
        self.run_events()
        files = [dict(provider="codex", path=str(self.path), size=self.path.stat().st_size)]
        first = w.collect(files, self.start, self.end)
        with self.path.open("a") as f:
            f.write(json.dumps(self.request("later")) + "\n")
        self.assertEqual(first, w.collect(files, self.start, self.end))

    def test_cli_writes_report_and_preserves_existing_output(self):
        self.events.append(self.request())
        self.run_events()
        root = Path(self.temp.name)
        out = root / "result"
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts/taskroute.py"),
            "metrics",
            "--start",
            self.start.isoformat(),
            "--end",
            self.end.isoformat(),
            "--codex-root",
            str(root),
            "--claude-root",
            str(root / "absent"),
            "--output-dir",
            str(out),
        ]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        saved = (out / "report.json").read_bytes()
        self.assertTrue((out / "report.html").is_file())
        sources = json.loads((out / "sources.json").read_text())
        self.assertFalse(sources["roots"][1]["exists"])
        again = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(saved, (out / "report.json").read_bytes())

    def test_cli_rejects_ambiguous_period_before_output(self):
        out = Path(self.temp.name) / "bad"
        with self.assertRaisesRegex(ValueError, "TIMEZONE_AWARE"):
            w.main(["--start", "2026-09-29", "--end", "2026-10-06", "--output-dir", str(out)])
        self.assertFalse(out.exists())

    def test_html_escapes_source_labels_and_does_not_infer_savings(self):
        self.events[1]["payload"]["model"] = "<script>alert(1)</script>"
        self.events.append(self.request())
        page = w.render(self.run_events())
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Causal savings: UNKNOWN", page)

    def test_malformed_relevant_record_does_not_crash_import(self):
        self.events += [["token_usage_record"], dict(type="token_usage_record", payload="broken")]
        result = self.run_events()
        self.assertEqual(result["coverage"]["issues"]["malformed_relevant_records"], 2)


if __name__ == "__main__":
    unittest.main()
