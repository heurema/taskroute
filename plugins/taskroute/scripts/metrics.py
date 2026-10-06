"""Collect local historical counters. Metadata only, no model calls or message copies."""

import argparse
import csv
import hashlib
import html
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FIELDS = {
    "codex": (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ),
    "claude": (
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "output_tokens",
    ),
}


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def counters(provider, value):
    if not isinstance(value, dict) or any(k not in value for k in FIELDS[provider]):
        raise ValueError("missing counters")
    out = {k: value[k] for k in FIELDS[provider]}
    if any(type(v) is not int or v < 0 for v in out.values()):
        raise ValueError("invalid counters")
    if provider == "codex" and out["cached_input_tokens"] > out["input_tokens"]:
        raise ValueError("invalid cached subset")
    return out


def inventory(roots, start):
    result = []
    for provider, root in roots:
        for path in sorted(Path(root).rglob("*.jsonl")):
            stat = path.stat()
            if stat.st_mtime >= start.timestamp():
                result.append(dict(provider=provider, path=str(path), size=stat.st_size))
    return result


def collect(files, start, end, zone="Europe/Moscow"):
    tz = ZoneInfo(zone)
    records, conflicts, snapshots, issues = {}, set(), {}, Counter()
    observed_sessions, covered_sessions, sources = set(), set(), []
    owned_counters = Counter()
    for source in files:
        provider, path, size = source["provider"], Path(source["path"]), source["size"]
        sid, cwd, model = None, "UNKNOWN", "UNKNOWN"
        turns = {}
        line_no, consumed = 0, 0
        sha = hashlib.sha256()
        try:
            stream = path.open("rb")
        except OSError:
            issues["unreadable_files"] += 1
            continue
        with stream:
            while consumed < size:
                line = stream.readline(size - consumed)
                if not line:
                    issues["shortened_files"] += 1
                    break
                consumed += len(line)
                sha.update(line)
                line_no += 1
                if not line.endswith(b"\n"):
                    issues["partial_final_lines"] += 1
                    continue
                needles = (
                    (b"session_meta", b"turn_context", b"token_usage_record", b"token_count")
                    if provider == "codex"
                    else (b'"usage"',)
                )
                if not any(word in line for word in needles):
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    issues["malformed_relevant_lines"] += 1
                    continue
                if not isinstance(event, dict):
                    issues["malformed_relevant_records"] += 1
                    continue
                payload = event.get("payload") or {}
                if not isinstance(payload, dict):
                    issues["malformed_relevant_records"] += 1
                    continue
                typ = event.get("type")
                if provider == "codex" and typ == "session_meta":
                    sid = payload.get("id")
                    cwd = payload.get("cwd") or "UNKNOWN"
                    continue
                if provider == "codex" and typ == "turn_context":
                    model = payload.get("model") or "UNKNOWN"
                    turns[payload.get("turn_id")] = model
                    continue
                try:
                    when = timestamp(event["timestamp"])
                    if not start <= when < end:
                        continue
                except (KeyError, ValueError, TypeError):
                    issues["missing_or_invalid_timestamp"] += 1
                    continue
                day = when.astimezone(tz).date().isoformat()
                if (
                    provider == "codex"
                    and typ == "event_msg"
                    and payload.get("type") == "token_count"
                ):
                    if sid:
                        observed_sessions.add(sid)
                        owned_counters[sid] += 1
                    limits = payload.get("rate_limits") or {}
                    for slot in ("primary", "secondary"):
                        window = limits.get(slot)
                        if not isinstance(window, dict):
                            continue
                        used = window.get("used_percent")
                        if type(used) not in (int, float) or not 0 <= used <= 100:
                            issues["invalid_quota_snapshots"] += 1
                            continue
                        snap = dict(
                            timestamp=event["timestamp"],
                            day=day,
                            limit_id=limits.get("limit_id"),
                            slot=slot,
                            used_percent=used,
                            window_minutes=window.get("window_minutes"),
                            resets_at=window.get("resets_at"),
                        )
                        key = json.dumps(snap, sort_keys=True)
                        snapshots[key] = snap
                    continue
                if provider == "codex":
                    if typ != "token_usage_record":
                        continue
                    if not sid or payload.get("thread_id") != sid:
                        issues["foreign_or_missing_thread_records"] += 1
                        continue
                    observed_sessions.add(sid)
                    rid = payload.get("response_id")
                    record_model = turns.get(payload.get("turn_id"), "UNKNOWN")
                    usage = payload.get("usage")
                    record_sid = sid
                else:
                    message = event.get("message")
                    if typ != "assistant" or not isinstance(message, dict):
                        continue
                    rid = message.get("id")
                    record_model = message.get("model") or "UNKNOWN"
                    record_sid = event.get("sessionId")
                    cwd = event.get("cwd") or "UNKNOWN"
                    usage = message.get("usage")
                if not rid or not record_sid:
                    issues["missing_response_or_session_id"] += 1
                    continue
                try:
                    usage = counters(provider, usage)
                except ValueError:
                    issues["invalid_" + provider + "_usage"] += 1
                    continue
                key = (provider, rid)
                record = dict(
                    provider=provider,
                    response_id=rid,
                    session_id=record_sid,
                    project=cwd,
                    model=record_model,
                    day=day,
                    usage=usage,
                    model_basis="configured_turn" if provider == "codex" else "logged_message",
                    timestamp=event["timestamp"],
                )
                if key in records:
                    previous = records[key]
                    # Claude can emit progressively completed copies of one message.
                    same_identity = all(
                        record[k] == previous[k] for k in ("session_id", "model", "project")
                    )
                    old, new = previous["usage"], record["usage"]
                    if same_identity and old == new:
                        issues["duplicate_response_records"] += 1
                    elif (
                        provider == "claude"
                        and same_identity
                        and all(new[k] >= old[k] for k in old)
                    ):
                        records[key] = record
                        issues["claude_progress_updates"] += 1
                    elif (
                        provider == "claude"
                        and same_identity
                        and all(new[k] <= old[k] for k in old)
                    ):
                        issues["claude_older_updates"] += 1
                    else:
                        conflicts.add(key)
                else:
                    records[key] = record
        sources.append(dict(**source, read_bytes=consumed, prefix_sha256=sha.hexdigest()))
    for key in conflicts:
        del records[key]
    issues["conflicting_responses_excluded"] = len(conflicts)
    totals = {}
    for record in records.values():
        if record["provider"] == "codex":
            covered_sessions.add(record["session_id"])
        key = (record["provider"], record["day"], record["project"], record["model"])
        row = totals.setdefault(
            key,
            dict(
                provider=key[0],
                day=key[1],
                project=key[2],
                model=key[3],
                requests=0,
                usage={k: 0 for k in FIELDS[key[0]]},
            ),
        )
        row["requests"] += 1
        for field, value in record["usage"].items():
            row["usage"][field] += value
    return dict(
        period=dict(start=start.isoformat(), end_exclusive=end.isoformat(), timezone=zone),
        sources=sources,
        daily_usage=[totals[k] for k in sorted(totals)],
        response_records=sorted(records.values(), key=lambda r: (r["provider"], r["response_id"])),
        quota_snapshots=sorted(snapshots.values(), key=lambda r: r["timestamp"]),
        coverage=dict(
            files=len(sources),
            codex_sessions_with_counters=len(observed_sessions),
            codex_sessions_with_request_usage=len(covered_sessions),
            counter_only_sessions=sorted(observed_sessions - covered_sessions),
            issues=dict(issues),
        ),
        accepted_task_count=None,
        causal_savings=None,
        subscription_attributed_cost=None,
        limitations=[
            "mtime-filtered available local JSONL files, frozen byte prefixes",
            "No cloud/deleted/unpersisted sessions or guaranteed complete coverage",
            "No task linking or semantic acceptance inferred from session metadata",
            "Quota snapshots are shared-account observations, not task charges",
            "Codex model is configured, not backend attestation",
            "Claude message usage is not added to terminal aggregates",
            "Daily assignment is record timestamp, not billing timestamp",
        ],
    )


METRICS = ("responses", "uncached_input", "cache_read", "cache_write", "output")


def analytics(records):
    """Describe observed workload; never infer price or accepted task identity."""
    dimensions = {
        "providers": ("provider",),
        "sessions": ("provider", "session_id"),
        "projects": ("provider", "project"),
        "models": ("provider", "model"),
        "days": ("provider", "day"),
    }
    result = {}
    for name, fields in dimensions.items():
        groups = {}
        for record in records:
            key = tuple(record[f] for f in fields)
            row = groups.setdefault(
                key,
                dict(
                    zip(fields, key, strict=True),
                    **{
                        "responses": 0,
                        "uncached_input": 0,
                        "cache_read": 0,
                        "cache_write": 0,
                        "output": 0,
                        "session_ids": set(),
                        "projects": set(),
                        "models": set(),
                    },
                ),
            )
            u = record["usage"]
            codex = record["provider"] == "codex"
            cached = u["cached_input_tokens" if codex else "cache_read_input_tokens"]
            row["responses"] += 1
            row["uncached_input"] += u["input_tokens"] - cached if codex else u["input_tokens"]
            row["cache_read"] += cached
            row["cache_write"] += u[
                "cache_write_input_tokens" if codex else "cache_creation_input_tokens"
            ]
            row["output"] += u["output_tokens"]
            row["session_ids"].add(record["session_id"])
            row["projects"].add(record["project"])
            row["models"].add(record["model"])
        rows = []
        for key in sorted(groups):
            row = groups[key]
            row["sessions"] = len(row.pop("session_ids"))
            row["projects"] = sorted(row["projects"])
            row["models"] = sorted(row["models"])
            row["mean_uncached_input_per_response"] = round(
                row["uncached_input"] / row["responses"], 2
            )
            rows.append(row)
        result[name] = rows
    return result


def account_history(path, start, end):
    """Import an explicit account/usage/read receipt, without network or credentials."""
    raw = path.read_bytes()
    receipt = json.loads(raw)
    if receipt.get("method") != "account/usage/read" or receipt.get("params") != {}:
        raise ValueError("ACCOUNT_LEVEL_USAGE_RECEIPT_REQUIRED")
    observed = timestamp(receipt["observed_at"])
    if observed.tzinfo is None:
        raise ValueError("ACCOUNT_OBSERVATION_OFFSET_REQUIRED")
    body = receipt["response"]["result"]
    buckets = body.get("dailyUsageBuckets")
    if buckets is not None and not isinstance(buckets, list):
        raise ValueError("INVALID_ACCOUNT_BUCKETS")
    days = {}
    for bucket in buckets or []:
        day, tokens = bucket["startDate"], bucket["tokens"]
        if date.fromisoformat(day).isoformat() != day or type(tokens) is not int or tokens < 0:
            raise ValueError("INVALID_ACCOUNT_DAY")
        if day in days:
            raise ValueError("DUPLICATE_ACCOUNT_DAY")
        days[day] = tokens
    # Date labels only: the service does not attest the bucket timezone.
    selected = [
        dict(day=d, tokens=n)
        for d, n in sorted(days.items())
        if start.date().isoformat() <= d < end.date().isoformat()
    ]
    return dict(
        status="AVAILABLE" if buckets is not None else "UNAVAILABLE",
        observed_at=receipt["observed_at"],
        source=str(path),
        sha256=hashlib.sha256(raw).hexdigest(),
        timezone="UNKNOWN",
        selection="Start date inclusive, end date exclusive; date labels only, not timestamp reconciliation",
        daily=selected,
        freshness="UNKNOWN",
        per_thread_cost="UNKNOWN",
    )


def export_analytics(result, directory):
    for name, rows in result["analytics"].items():
        if not rows:
            continue
        with (directory / (name + ".csv")).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                safe = {}
                for key, value in row.items():
                    if isinstance(value, list):
                        value = json.dumps(value, ensure_ascii=False)
                    # Do not let source labels become spreadsheet formulas.
                    if isinstance(value, str) and value.startswith(
                        ("=", "+", "-", "@", "\t", "\r", "\n")
                    ):
                        value = "'" + value
                    safe[key] = value
                writer.writerow(safe)


def render_analytics(result, table):
    data = result.get("analytics") or analytics(result["response_records"])
    out = "<h2>Workload overview</h2><p>Observed token volumes, not monetary cost or subscription debits. Rankings stay within each provider.</p>"
    out += table(
        [
            "Provider",
            "Sessions",
            "Responses",
            "Uncached input",
            "Cache read",
            "Cache write",
            "Output",
        ],
        [
            (r["provider"], r["sessions"], *(format(r[k], ",") for k in METRICS))
            for r in data["providers"]
        ],
    )
    for provider in ("codex", "claude"):
        out += "<h2>" + provider.title() + " workload hotspots</h2>"
        for dimension, label in (
            ("sessions", "session_id"),
            ("projects", "project"),
            ("models", "model"),
        ):
            rows = [r for r in data[dimension] if r["provider"] == provider]
            if not rows:
                out += "<p>No observed " + dimension + ". Coverage unknown.</p>"
                continue
            for metric in ("uncached_input", "output", "responses"):
                ranked = sorted(rows, key=lambda r: (-r[metric], r[label]))[:10]
                total = sum(r[metric] for r in rows)
                out += (
                    "<details"
                    + (" open" if dimension == "projects" and metric == "uncached_input" else "")
                    + "><summary>Top "
                    + dimension
                    + " by "
                    + metric.replace("_", " ")
                    + "</summary>"
                )
                out += (
                    table(
                        [
                            "Name / ID",
                            "Projects",
                            "Models",
                            "Responses",
                            "Uncached input",
                            "Cache read",
                            "Cache write",
                            "Output",
                            "Share of selected metric",
                        ],
                        [
                            (
                                r[label],
                                "; ".join(r["projects"]),
                                "; ".join(r["models"]),
                                *(format(r[k], ",") for k in METRICS),
                                format(100 * r[metric] / total, ".1f") + "%" if total else "N/A",
                            )
                            for r in ranked
                        ],
                    )
                    + "</details>"
                )
    out += "<h2>Daily local activity</h2>" + table(
        [
            "Provider",
            "Day (Moscow)",
            "Responses",
            "Uncached input",
            "Cache read",
            "Cache write",
            "Output",
        ],
        [(r["provider"], r["day"], *(format(r[k], ",") for k in METRICS)) for r in data["days"]],
    )
    account = result.get("account_history")
    out += "<h2>Codex service history</h2>"
    if account is None:
        out += "<p>Not imported. Use --account-usage with an account/usage/read receipt.</p>"
    else:
        out += (
            "<p>Status: "
            + html.escape(account["status"])
            + "; observed: "
            + html.escape(account["observed_at"])
            + ". Bucket timezone and freshness: UNKNOWN. Date-label selection only; never added to local totals or reconciled as billing.</p>"
        )
        out += table(
            ["Service date label", "Account tokens"],
            [(r["day"], format(r["tokens"], ",")) for r in account["daily"]],
        )
    out += (
        "<p>Download complete tables: "
        + " · ".join('<a href="' + n + '.csv">' + n + "</a>" for n, rows in data.items() if rows)
        + "</p>"
    )
    return out


def render(result):
    """Static local report. All source strings escaped; no scripts or external assets."""

    def table(headers, rows):
        return (
            "<table><tr>"
            + "".join("<th>" + html.escape(str(h)) + "</th>" for h in headers)
            + "</tr>"
            + "".join(
                "<tr>" + "".join("<td>" + html.escape(str(v)) + "</td>" for v in row) + "</tr>"
                for row in rows
            )
            + "</table>"
        )

    quota = defaultdict(list)
    for row in result["quota_snapshots"]:
        # Report each distinct observed reset date separately. No inferred debit.
        reset = row["resets_at"]
        reset_day = (
            datetime.fromtimestamp(reset, ZoneInfo("UTC")).date().isoformat()
            if type(reset) in (int, float)
            else "UNKNOWN"
        )
        quota[
            (row["day"], str(row["limit_id"]), row["slot"], str(row["window_minutes"]), reset_day)
        ].append(row)
    totals = {}
    for row in result["daily_usage"]:
        key = (row["provider"], row["model"])
        total = totals.setdefault(key, Counter())
        total["responses"] += row["requests"]
        total.update(row["usage"])
    usage = []
    for (provider, model), counts in sorted(totals.items()):
        uncached = (
            counts["input_tokens"] - counts["cached_input_tokens"]
            if provider == "codex"
            else counts["input_tokens"]
        )
        cached = (
            counts["cached_input_tokens"]
            if provider == "codex"
            else counts["cache_read_input_tokens"]
        )
        written = (
            counts["cache_write_input_tokens"]
            if provider == "codex"
            else counts["cache_creation_input_tokens"]
        )
        usage.append(
            (
                provider,
                model,
                counts["responses"],
                uncached,
                cached,
                written,
                counts["output_tokens"],
            )
        )
    c = result["coverage"]
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><title>TaskRoute metrics</title>
<style>body{font:16px/1.55 system-ui;max-width:1500px;margin:40px auto;padding:0 20px;color:#20242a}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}td{overflow-wrap:anywhere}details{margin:16px 0;overflow-x:auto}summary{cursor:pointer;font-weight:600}h1{line-height:1.2}.note{background:#fff4db;padding:16px}</style>
<h1>TaskRoute local usage report</h1><p>"""
        + html.escape(result["period"]["start"])
        + " → "
        + html.escape(result["period"]["end_exclusive"])
        + " (end exclusive)</p><p>"
        + str(c["files"])
        + " files; "
        + str(len(result["response_records"]))
        + " recorded responses. No subscription price inferred.</p>"
        + '<p class="note">Accepted task count: UNKNOWN. Causal savings: UNKNOWN. '
        + "Missing sessions and unpersisted calls are not zero. This is an explicit local snapshot, not a background monitor.</p>"
        + render_analytics(result, table)
        + "<h2>Coverage</h2>"
        + table(["Observation", "Count"], sorted(c["issues"].items()))
        + "<p>Codex sessions with counters: "
        + str(c["codex_sessions_with_counters"])
        + "; with per-response usage: "
        + str(c["codex_sessions_with_request_usage"])
        + "; counter-only sessions: "
        + str(len(c["counter_only_sessions"]))
        + "</p>"
        + "<h2>Observed quota snapshots</h2><p>Shared-account observations, not daily consumption. "
        + "Reset dates are labels from source data; different dates must not be subtracted as one continuous window. "
        + "Creator/account identity at the time of each debit is not verified.</p>"
        + table(
            [
                "Day",
                "Limit",
                "Slot",
                "Window minutes",
                "Reset date UTC",
                "First %",
                "Last %",
                "Snapshots",
            ],
            [
                (*key, rows[0]["used_percent"], rows[-1]["used_percent"], len(rows))
                for key, rows in sorted(quota.items())
            ],
        )
        + "<h2>Token volumes by provider and model</h2>"
        + table(
            [
                "Provider",
                "Model/configuration",
                "Responses",
                "Input without cache read",
                "Cache read",
                "Cache write",
                "Output",
            ],
            usage,
        )
        + "<p>Codex model labels describe configuration, not observed backend identity. "
        + "Codex cached input is a subset of input; reasoning is a subset of output. "
        + "Claude cache creation/read are separate input counters. Do not add inclusive totals again.</p>"
        + "<h2>Limitations</h2><ul>"
        + "".join("<li>" + html.escape(x) + "</li>" for x in result["limitations"])
        + '</ul><p><a href="report.json">Structured report</a></p></html>'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory", type=Path, help="Replay a previously saved file-prefix inventory"
    )
    parser.add_argument("--start", required=True, help="Inclusive ISO timestamp with UTC offset")
    parser.add_argument("--end", required=True, help="Exclusive ISO timestamp with UTC offset")
    parser.add_argument(
        "--account-usage", type=Path, help="Import a saved account/usage/read receipt"
    )
    parser.add_argument("--codex-root", type=Path, action="append")
    parser.add_argument("--claude-root", type=Path, action="append")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Fresh local output directory"
    )
    args = parser.parse_args(argv)
    start, end = timestamp(args.start), timestamp(args.end)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("ORDERED_TIMEZONE_AWARE_PERIOD_REQUIRED")
    if args.inventory and (args.codex_root or args.claude_root):
        raise ValueError("REPLAY_OR_SOURCE_ROOTS_NOT_BOTH")
    roots = [
        ("codex", p)
        for p in (
            args.codex_root
            or [Path.home() / ".codex/sessions", Path.home() / ".codex/archived_sessions"]
        )
    ] + [("claude", p) for p in (args.claude_root or [Path.home() / ".claude/projects"])]
    files = json.loads(args.inventory.read_text()) if args.inventory else inventory(roots, start)
    account = account_history(args.account_usage, start, end) if args.account_usage else None
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "inventory.json").write_text(json.dumps(files, indent=2) + "\n")
    sources = (
        dict(mode="replay", source=str(args.inventory))
        if args.inventory
        else dict(
            mode="discovery",
            roots=[dict(provider=k, path=str(p), exists=p.is_dir()) for k, p in roots],
        )
    )
    (args.output_dir / "sources.json").write_text(json.dumps(sources, indent=2) + "\n")
    result = collect(files, start, end)
    result["analytics"] = analytics(result["response_records"])
    result["account_history"] = account
    export_analytics(result, args.output_dir)
    (args.output_dir / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.output_dir / "report.html").write_text(render(result))
    print(
        json.dumps(
            dict(
                status="COLLECTED_PARTIAL_OBSERVATIONS",
                output=str(args.output_dir),
                coverage=result["coverage"],
                responses=len(result["response_records"]),
            )
        )
    )
    return 0


if __name__ == "__main__":
    main()
