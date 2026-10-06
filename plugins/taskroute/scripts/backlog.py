"""Local, capture-only issue occurrences. No model calls, repair or publication."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path

TOKEN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}\Z")
SEVERITIES = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def database():
    return Path(
        os.environ.get(
            "TASKROUTE_BACKLOG_DB", Path.home() / ".local/state/taskroute/backlog.sqlite3"
        )
    )


def opaque(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Create private before SQLite opens it; never change existing parent permissions.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""CREATE TABLE IF NOT EXISTS occurrences (
        event_key TEXT PRIMARY KEY, issue_key TEXT NOT NULL,
        project_id TEXT NOT NULL, task_id TEXT, run_id TEXT NOT NULL,
        event_id TEXT NOT NULL, stage TEXT NOT NULL, severity INTEGER NOT NULL,
        expected TEXT NOT NULL, observed TEXT NOT NULL, evidence TEXT NOT NULL,
        version TEXT NOT NULL, created REAL NOT NULL
    )""")
    return db


def record(path, item):
    required = {
        "issue_key",
        "project_id",
        "task_id",
        "run_id",
        "event_id",
        "stage",
        "severity",
        "expected",
        "observed",
        "evidence",
        "version",
    }
    if set(item) != required or item["severity"] not in SEVERITIES:
        raise ValueError("INVALID_BACKLOG_FIELDS")
    for key, value in item.items():
        if key == "task_id" and value is None:
            continue
        if not isinstance(value, str) or not TOKEN.fullmatch(value):
            raise ValueError("BACKLOG_REQUIRES_OPAQUE_IDS_AND_CODES")
    # Event identity is independent of grouping: filing it under another issue
    # must not silently inflate counts or regroup prior evidence.
    event_key = opaque(json.dumps([item[k] for k in ("project_id", "run_id", "stage", "event_id")]))
    values = (
        event_key,
        item["issue_key"],
        item["project_id"],
        item["task_id"],
        item["run_id"],
        item["event_id"],
        item["stage"],
        SEVERITIES[item["severity"]],
        item["expected"],
        item["observed"],
        item["evidence"],
        item["version"],
    )
    db = connect(path)
    try:
        with db:
            db.execute(
                "INSERT OR IGNORE INTO occurrences VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*values, time.time()),
            )
            row = db.execute("SELECT * FROM occurrences WHERE event_key=?", (event_key,)).fetchone()
            if tuple(row[:-1]) != values:
                raise ValueError("BACKLOG_EVENT_CONFLICT")
        return {"status": "SAVED", "event_key": event_key, "issue_key": item["issue_key"]}
    finally:
        db.close()


def listing(path):
    if not Path(path).exists():
        return []
    db = connect(path)
    try:
        rows = db.execute("""SELECT issue_key, MIN(severity), COUNT(*),
            COUNT(DISTINCT project_id || ':' || task_id), COUNT(DISTINCT project_id),
            MIN(created), MAX(created) FROM occurrences GROUP BY issue_key
            ORDER BY MIN(severity), COUNT(DISTINCT project_id || ':' || task_id) DESC,
            COUNT(DISTINCT project_id) DESC, MAX(created) DESC""").fetchall()
        return [
            dict(
                issue_key=r[0],
                severity=list(SEVERITIES)[r[1]],
                occurrences=r[2],
                independent_tasks=r[3],
                projects=r[4],
                first_seen=r[5],
                last_seen=r[6],
            )
            for r in rows
        ]
    finally:
        db.close()


def show(path, issue_key):
    if not TOKEN.fullmatch(issue_key):
        raise ValueError("INVALID_ISSUE_KEY")
    if not Path(path).exists():
        return []
    db = connect(path)
    try:
        db.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in db.execute(
                "SELECT * FROM occurrences WHERE issue_key=? ORDER BY created", (issue_key,)
            )
        ]
    finally:
        db.close()


def preparation_code(error):
    """Keep exception text and source bytes out of the shared registry."""
    if isinstance(error, UnicodeDecodeError):
        return "NON_UTF8_INPUT"
    if isinstance(error, json.JSONDecodeError):
        return "INVALID_JSON"
    if isinstance(error, FileNotFoundError):
        return "INPUT_NOT_FOUND"
    if isinstance(error, PermissionError):
        return "LOCAL_ACCESS_DENIED"
    if isinstance(error, OSError):
        return "LOCAL_IO_ERROR"
    if isinstance(error, ValueError):
        match = re.match(r"[A-Z][A-Z_]{2,79}(?=:|$)", str(error))
        return match.group() if match else "INVALID_INPUT"
    return "PREPARATION_EXCEPTION"


def capture_preparation(
    project, destination, error, *, stage="preparation", project_id=None, task_id=None, path=None
):
    """Capture a local blocker without a manifest or writes to the requested run."""
    receipt = {"status": "NOT_SAVED"}
    try:
        if stage not in {"preparation", "preflight"}:
            raise ValueError("INVALID_PREPARATION_STAGE")
        db_path = Path(path) if path is not None else database()
        code = preparation_code(error)
        valid_project = isinstance(project_id, str) and TOKEN.fullmatch(project_id)
        valid_task = isinstance(task_id, str) and TOKEN.fullmatch(task_id)
        item = dict(
            issue_key=stage + "." + code.lower(),
            project_id=project_id
            if valid_project
            else (opaque(Path(project).resolve()) if project is not None else "unknown"),
            task_id=task_id if valid_task else None,
            run_id=opaque(Path(destination).resolve()),
            event_id="blocked",
            stage=stage,
            severity="medium",
            expected="prepared-delivery" if stage == "preparation" else "executor-ready",
            observed=code,
            version="0.2.2",
        )
        event_key = opaque(
            json.dumps([item[k] for k in ("project_id", "run_id", "stage", "event_id")])
        )
        item["evidence"] = f"preparation-{event_key}.json"
        folder = Path(str(db_path) + ".evidence")
        if folder.is_symlink():
            raise ValueError("PREPARATION_EVIDENCE_UNSAFE")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = folder / item["evidence"]
        payload = dict(
            occurrence=item,
            error_type=type(error).__name__,
            model_calls=0,
            automatic_retry=False,
            meaning="Local preparation observation; not a model run or repair authority",
        )
        body = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
        # Publish complete, private evidence once; conflicting replays cannot overwrite it.
        fd, temporary = tempfile.mkstemp(prefix=".preparation-", dir=folder)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                if target.is_symlink() or target.read_bytes() != body:
                    raise ValueError("PREPARATION_EVENT_CONFLICT") from exc
        finally:
            Path(temporary).unlink()
        receipt["evidence"] = str(target)
        receipt["evidence_sha256"] = hashlib.sha256(body).hexdigest()
        saved = record(db_path, item)
        receipt.update(status="SAVED", events=[saved])
    except Exception as exc:
        receipt.update(status="NOT_SAVED", error_type=type(exc).__name__)
    return receipt


def capture(run, packet, path=None):
    """Capture terminal blockers and recovered protocol failures, never raw logs."""
    run = Path(run)
    try:
        m = json.loads((run / "manifest.json").read_text())
        context = m.get("backlog_context", {})
        base = dict(
            project_id=context.get("project_id", opaque(m["project_root"])),
            task_id=context.get("task_id"),
            run_id=opaque(run),
            version="0.2.2",
        )
        pending = []
        if packet.get("status") not in ("PASS", "PREPARED", "READY_FOR_LEAD_REVIEW"):
            reason = packet.get("reason") or next(
                iter(packet.get("reasons") or []), "UNKNOWN_FAILURE"
            )
            match = re.match(r"[A-Z][A-Z_]{2,79}(?=:|$)", str(reason))
            code = match.group() if match else "UNKNOWN_FAILURE"
            pending.append(
                dict(
                    issue_key="runner." + code.lower(),
                    event_id="terminal",
                    stage="delivery",
                    severity="medium",
                    expected="accepted-delivery",
                    observed=code,
                    evidence="packet-error.json",
                )
            )
        gate = run / "review-gate.json"
        if gate.exists():
            for index, row in enumerate(json.loads(gate.read_text())):
                if row.get("status") == "FORMAT_CORRECTION":
                    pending.append(
                        dict(
                            issue_key="review.incomplete-report",
                            event_id=f"format-{index}",
                            stage="review",
                            severity="low",
                            expected="complete-report",
                            observed="FORMAT_CORRECTION",
                            evidence="review-gate.json",
                        )
                    )
        saved = [record(path or database(), {**base, **item}) for item in pending]
        receipt = dict(
            status="SAVED" if saved else "NO_FINDINGS",
            events=saved,
            meaning="Observations for triage; not confirmed tool defects or repair authority",
        )
    except Exception as exc:
        receipt = dict(status="NOT_SAVED", error_type=type(exc).__name__)
    try:
        (run / "backlog-capture.json").write_text(json.dumps(receipt, indent=2))
    except OSError:
        receipt = dict(status="NOT_SAVED", error_type="ReceiptWriteError")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=database())
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("record")
    p.add_argument("item", type=Path, help="Sanitized JSON codes and opaque identifiers only")
    sub.add_parser("list")
    p = sub.add_parser("show")
    p.add_argument("issue_key")
    p = sub.add_parser("capture")
    p.add_argument("run", type=Path)
    p.add_argument("packet", type=Path)
    args = parser.parse_args()
    if args.action == "record":
        result = record(args.db, json.loads(args.item.read_text()))
    elif args.action == "show":
        result = show(args.db, args.issue_key)
    elif args.action == "capture":
        result = capture(args.run, json.loads(args.packet.read_text()), args.db)
    else:
        result = listing(args.db)
    print(json.dumps(result, indent=2))
    return 2 if isinstance(result, dict) and result.get("status") == "NOT_SAVED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
