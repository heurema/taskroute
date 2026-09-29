"""Validate reviewer completion and permit one same-agent format correction."""

import hashlib
import json
import sys
import time
from pathlib import Path

from task_contract import _record, assess


def validate(m, text, bodies):
    result = assess(
        m,
        text,
        'TASKROUTE_RESULT: {"status":"READY_FOR_LEAD","reason":"Review protocol validation only"}',
        bodies,
    )
    reasons = result["reasons"]
    malformed = any(
        x.startswith(("REVIEW_OUTCOME_INVALID:", "EVIDENCE_INCOMPLETE:")) for x in reasons
    )
    review = result.get("reviewer_outcome") or {}
    # Never turn a known negative semantic finding into a formatting retry.
    negative = review.get("verdict") == "CHANGES"
    for key, states in [
        ("acceptance", {"NOT_MET", "UNKNOWN"}),
        ("non_goals", {"BROKEN", "UNKNOWN"}),
    ]:
        values = review.get(key, [])
        if isinstance(values, list):
            negative |= any(isinstance(row, dict) and row.get("status") in states for row in values)
    return reasons, malformed and not negative


def correction_schema(m, text):
    try:
        value = _record(text, "TASKROUTE_REVIEW:")
        observed = sorted(value)
    except (ValueError, TypeError):
        observed = []
    skeleton = dict(
        verdict="CHANGES",
        acceptance=[
            dict(
                id=c["id"],
                status="UNKNOWN",
                evidence=c["evidence"],
                detail="Replace with observed evidence",
            )
            for c in m["acceptance"]
        ],
        non_goals=[
            dict(id=c["id"], status="UNKNOWN", detail="Replace with observed evidence")
            for c in m["non_goals"]
        ],
    )
    return (
        "Required top-level keys are exactly verdict, acceptance, non_goals; observed "
        + json.dumps(observed)
        + ". acceptance contains only acceptance IDs with MET/NOT_MET/UNKNOWN. "
        + "non_goals is a SEPARATE required array containing only non-goal IDs with KEPT/BROKEN/UNKNOWN. "
        + "Do not put NG records in acceptance. Use this complete shape, replacing UNKNOWN and details only from your actual review: "
        + json.dumps(skeleton)
    )


def rounds(rows):
    """Group contiguous native completions; never permit a finished agent to return."""
    groups = []
    for row in rows:
        if not groups or groups[-1][-1]["agent_id"] != row["agent_id"]:
            if any(g[0]["agent_id"] == row["agent_id"] for g in groups):
                raise ValueError("REVIEW_IDENTITY_REUSED")
            groups.append([])
        group = groups[-1]
        if group and (len(group) >= 2 or group[-1]["status"] != "FORMAT_CORRECTION"):
            raise ValueError("REVIEW_CORRECTION_CEILING_OR_IDENTITY")
        group.append(row)
    return groups


def repair_window(root, m, launches):
    """Only one completed, well-formed negative first review unlocks author edits."""
    if not m.get("review_repair_enabled") or launches != 1:
        return False
    if (root / "review-gate-error.json").exists():
        return False
    path = root / "review-gate.json"
    groups = rounds(json.loads(path.read_text())) if path.exists() else []
    return len(groups) == 1 and groups[0][-1]["status"] == "CHANGES"


def handle(root, event):
    m = json.loads((root / "manifest.json").read_text())
    if event.get("hook_event_name") != "SubagentStop" or event.get("agent_type") != "reviewer":
        raise ValueError("UNEXPECTED_REVIEW_STOP")
    agent = event.get("agent_id")
    text = event.get("last_assistant_message")
    if not isinstance(agent, str) or not agent or not isinstance(text, str) or not text.strip():
        raise ValueError("MISSING_REVIEW_STOP_EVIDENCE")
    from repository_task import digest, snapshot

    bodies = snapshot(m, json.loads((root / "originals.json").read_text()))
    reasons, malformed = validate(m, text, bodies)
    path = root / "review-gate.json"
    previous = json.loads(path.read_text()) if path.exists() else []
    groups = rounds(previous)
    new_round = bool(groups and groups[-1][-1]["agent_id"] != agent)
    if new_round:
        if not repair_window(root, m, len(groups)):
            raise ValueError("REVIEW_CORRECTION_CEILING_OR_IDENTITY")
        hashes = {n: digest(b) for n, b in bodies.items()}
        checks = json.loads((Path(m["workspace"]) / "checks.json").read_text())
        if (
            hashes == groups[0][-1]["file_hashes"]
            or checks.get("status") != "PASS"
            or checks.get("file_hashes") != hashes
        ):
            raise ValueError("REPAIR_REQUIRES_CHANGED_CHECKED_CANDIDATE")
    elif groups and (len(groups[-1]) >= 2 or groups[-1][-1]["status"] != "FORMAT_CORRECTION"):
        raise ValueError("REVIEW_CORRECTION_CEILING_OR_IDENTITY")
    block = malformed and (not groups or new_round)
    semantic = bool(reasons) and all(
        x.startswith(("REVIEW_REQUESTS_CHANGES", "CRITERION_NOT_MET:", "NON_GOAL_NOT_KEPT:"))
        for x in reasons
    )
    repairable = m.get("review_repair_enabled") and not new_round and len(groups) <= 1 and semantic
    record = dict(
        agent_id=agent,
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        file_hashes={n: digest(b) for n, b in bodies.items()},
        reasons=reasons,
        status="FORMAT_CORRECTION"
        if block
        else ("PASS" if not reasons else ("CHANGES" if repairable else "REJECTED")),
        completed_at=time.time(),
    )
    path.write_text(json.dumps([*previous, record], indent=2))
    if block:
        return dict(
            decision="block",
            reason="Your review report is incomplete or malformed: "
            + "; ".join(reasons)
            + ". "
            + correction_schema(m, text)
            + " Preserve honest findings; never infer approval. This is your one formatting correction; no tools or code changes. Output only the complete corrected TASKROUTE_REVIEW record.",
        )
    return {}


def accepted_review(root, m, streamed_review):
    from repository_task import digest, snapshot

    rows = json.loads((root / "review-gate.json").read_text())
    groups = rounds(rows)
    maximum = 2 if m.get("review_repair_enabled") else 1
    if not 1 <= len(groups) <= maximum or (
        len(groups) == 2 and groups[0][-1]["status"] != "CHANGES"
    ):
        raise ValueError("INVALID_REVIEW_GATE_HISTORY")
    last = rows[-1]
    bodies = snapshot(m, json.loads((root / "originals.json").read_text()))
    if last["file_hashes"] != {n: digest(b) for n, b in bodies.items()}:
        raise ValueError("STALE_REVIEW_GATE")
    if last["text"] not in streamed_review:
        raise ValueError("REVIEW_GATE_STREAM_MISMATCH")
    reasons, _ = validate(m, last["text"], bodies)
    if last["status"] != "PASS" or reasons:
        raise ValueError("REVIEW_GATE_REJECTED: " + "; ".join(reasons))
    return last["text"]


if __name__ == "__main__":
    try:
        print(json.dumps(handle(Path(sys.argv[1]).resolve(), json.loads(sys.stdin.read(1000000)))))
    except Exception as error:
        # No continuation on unknown evidence. Collector independently requires PASS.
        root = Path(sys.argv[1]).resolve()
        (root / "review-gate-error.json").write_text(
            json.dumps(dict(error_type=type(error).__name__, reason=str(error)))
        )
        print("{}")
