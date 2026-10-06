"""Explicit human/recorded feedback intake; proposals never execute changes."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import backlog

KINDS = {"correction", "new_request", "question", "quoted_report", "unknown"}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def validate(item):
    required = {
        "project_id",
        "task_id",
        "run_id",
        "event_id",
        "completed",
        "provenance",
        "source",
        "message",
        "result",
        "classification",
        "proposal",
    }
    if not isinstance(item, dict) or set(item) != required:
        raise ValueError("INVALID_FEEDBACK_FIELDS")
    for key in ("project_id", "task_id", "run_id", "event_id"):
        if not isinstance(item[key], str) or not backlog.TOKEN.fullmatch(item[key]):
            raise ValueError("INVALID_FEEDBACK_ID")
    if item["completed"] is not True or item["provenance"] not in {"user", "quote", "unknown"}:
        raise ValueError("INCOMPLETE_OR_INVALID_PROVENANCE")
    for key in ("message", "result"):
        if not isinstance(item[key], str) or not 1 <= len(item[key]) <= 4000:
            raise ValueError("INVALID_FEEDBACK_TEXT")
    source = item["source"]
    if not isinstance(source, dict) or set(source) != {"reference", "sha256"}:
        raise ValueError("INVALID_SOURCE")
    if not isinstance(source["reference"], str) or not 1 <= len(source["reference"]) <= 500:
        raise ValueError("INVALID_SOURCE_REFERENCE")
    if (
        not isinstance(source["sha256"], str)
        or len(source["sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in source["sha256"])
    ):
        raise ValueError("INVALID_SOURCE_HASH")
    c = item["classification"]
    if not isinstance(c, dict) or set(c) != {"kind", "basis", "evidence"}:
        raise ValueError("INVALID_CLASSIFICATION")
    if c["kind"] not in KINDS or c["basis"] not in {"human", "recorded"}:
        raise ValueError("INVALID_CLASSIFICATION_BASIS")
    if not isinstance(c["evidence"], str) or not 1 <= len(c["evidence"]) <= 2000:
        raise ValueError("MISSING_CLASSIFICATION_EVIDENCE")
    proposal = item["proposal"]
    if proposal is not None:
        if (
            not isinstance(proposal, dict)
            or set(proposal) != {"problem", "expected", "target", "repair", "check", "rollback"}
            or any(not isinstance(v, str) or not 1 <= len(v) <= 2000 for v in proposal.values())
        ):
            raise ValueError("INVALID_PROPOSAL")
    if len(canonical(item).encode()) > 16000:
        raise ValueError("FEEDBACK_SIZE_CAP")


def ingest(path, item):
    validate(item)
    kind = item["classification"]["kind"]
    if item["provenance"] == "quote":
        kind = "quoted_report"
    elif item["provenance"] == "unknown":
        kind = "unknown"
    identity = [item[k] for k in ("project_id", "run_id")] + ["feedback", item["event_id"]]
    event = backlog.opaque(json.dumps(identity))
    evidence = "feedback-" + event + ".json"
    folder = Path(str(path) + ".evidence")
    payload = dict(
        input=item,
        effective_kind=kind,
        proposal=None
        if item["proposal"] is None
        else {
            **item["proposal"],
            "source": item["source"],
            "authority": "proposal-only; no change authorized",
        },
    )
    target = folder / evidence
    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.read_bytes() != canonical(payload).encode():
            raise ValueError("FEEDBACK_EVENT_CONFLICT")
    body = canonical(payload).encode()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive publication: concurrent and conflicting replays never overwrite evidence.
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        if target.is_symlink() or target.read_bytes() != body:
            raise ValueError("FEEDBACK_EVENT_CONFLICT") from exc
    if kind != "correction":
        return dict(
            status="NOT_ACTIONABLE",
            kind=kind,
            classification_basis=item["classification"]["basis"],
            proposal=None,
            evidence=str(target),
            model_calls=0,
        )
    if item["proposal"] is None:
        return dict(
            status="UNKNOWN",
            kind=kind,
            reason="MISSING_REPAIR_EVIDENCE",
            evidence=str(target),
            model_calls=0,
        )
    occurrence = dict(
        issue_key="feedback.correction",
        project_id=item["project_id"],
        task_id=item["task_id"],
        run_id=item["run_id"],
        event_id=item["event_id"],
        stage="feedback",
        severity="medium",
        expected="review-proposal",
        observed=hashlib.sha256(body).hexdigest(),
        evidence=evidence,
        version="0.2.2",
    )
    try:
        saved = backlog.record(path, occurrence)
    except (OSError, ValueError, sqlite3.Error) as exc:
        return dict(status="NOT_SAVED", reason=str(exc), evidence=str(target), model_calls=0)
    return dict(
        **saved, kind=kind, evidence=str(target), proposal=payload["proposal"], model_calls=0
    )


def inspect(path, issue_key="feedback.correction"):
    result = []
    for row in backlog.show(path, issue_key):
        if row["stage"] != "feedback":
            continue
        target = Path(str(path) + ".evidence") / row["evidence"]
        try:
            body = target.read_bytes()
            if target.is_symlink() or hashlib.sha256(body).hexdigest() != row["observed"]:
                raise ValueError("FEEDBACK_EVIDENCE_CHANGED")
            value = json.loads(body)
            validate(value["input"])
            result.append(dict(occurrence=row, details=value, status="AVAILABLE"))
        except (OSError, ValueError, KeyError, TypeError):
            result.append(dict(occurrence=row, status="EVIDENCE_UNAVAILABLE"))
    return result
