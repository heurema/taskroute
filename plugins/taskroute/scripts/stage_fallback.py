"""One native Sol fallback after lead-confirmed Claude unavailability."""

import fcntl
import os
from pathlib import Path

from runtime import Journal
from stage import digest, load, read, required_text

MODEL = "gpt-6.1-sol"
REASONS = ("quota_exhausted", "balance_exhausted", "service_unavailable", "cli_unavailable")


def reserve(directory, evidence_path):
    root, manifest, contract = load(directory)
    if manifest["route"] != "delegate" or (root / "acceptance.reserved.json").exists():
        raise ValueError("FALLBACK_ROUTE_NOT_ELIGIBLE")
    proof = read(evidence_path)
    if proof.get("reason") not in REASONS or proof.get("confirmed") is not True:
        raise ValueError("CONFIRMED_AVAILABILITY_FAILURE_REQUIRED")
    if proof.get("prior_effects") not in ("none", "inspected_partial_work"):
        raise ValueError("PRIOR_EFFECTS_UNRESOLVED")
    required_text(proof.get("lead"))
    required_text(proof.get("assessment"))
    if not proof.get("evidence"):
        raise ValueError("AVAILABILITY_EVIDENCE_REQUIRED")
    hashes = {str(Path(p).resolve(strict=True)): digest(p) for p in proof["evidence"]}
    terminal_path = root / "terminal.json"
    if (root / "worker.reserved.json").exists():
        if not terminal_path.exists():
            raise ValueError("CLAUDE_SUBMISSION_UNKNOWN")
        terminal = read(terminal_path)
        if terminal.get("status") != "BLOCKED" or terminal.get("stop_reason") in (
            "TIMEOUT",
            "INTERRUPTED",
            "OUTPUT_LIMIT",
        ):
            raise ValueError("CLAUDE_OUTCOME_NOT_RESOLVED")
        if not (root / "worker.json").exists() or terminal.get("worker_sha256") != digest(
            root / "worker.json"
        ):
            raise ValueError("CLAUDE_TERMINAL_EVIDENCE_REQUIRED")
        hashes[str(terminal_path)] = digest(terminal_path)
        hashes[str(root / "worker.json")] = digest(root / "worker.json")
    else:
        # Only positively proven missing CLI can bypass an unsubmitted primary attempt.
        if proof["reason"] != "cli_unavailable" or proof["prior_effects"] != "none":
            raise ValueError("PRIMARY_NOT_ATTEMPTED")
        binary = Path(required_text(proof.get("binary")))
        if not binary.is_absolute() or binary.exists():
            raise ValueError("CLI_NOT_CONFIRMED_MISSING")
    marker = Path(manifest["project"]) / ".taskroute-stage.lock"
    with (root / "mutation.lock").open("a") as mutex:
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / "fallback.reserved.json").exists():
            raise ValueError("FALLBACK_ALREADY_CONSUMED")
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(str(root))
            stream.flush()
            os.fsync(stream.fileno())
        Journal(root).reserve(
            "fallback",
            model=MODEL,
            effort="medium",
            evidence=proof,
            evidence_hashes=hashes,
            requested_by="coordinator",
        )
        prompt = (
            (root / "prompt.txt").read_text()
            + "\nPrimary Claude is unavailable. You are the sole fresh native Codex worker. "
            + "The selected worker model is gpt-6.1-sol; Claude model/tool settings in the "
            + "original contract are historical and do not override native controls. "
            + "No child agents or provider calls. Inspect preserved partial work before "
            + "editing; do not replay uncertain effects. Keep the same scope and acceptance. "
            + "Return changed files, check outputs and blockers. Project: "
            + manifest["project"]
            + "\nLead handoff assessment:\n"
            + proof["assessment"]
        )
        (root / "fallback-prompt.txt").write_text(prompt)
    return dict(
        status="FALLBACK_RESERVED_SUBMISSION_UNCERTAIN",
        model=MODEL,
        effort="medium",
        fork_turns="none",
        prompt=str(root / "fallback-prompt.txt"),
        project=manifest["project"],
        attempt_ceiling=1,
        automatic_retry=False,
    )


def dispatched(directory, agent, model):
    root, _, _ = load(directory)
    if not (root / "fallback.reserved.json").exists():
        raise ValueError("FALLBACK_NOT_RESERVED")
    if model != MODEL or not isinstance(agent, str) or not agent.startswith("/root/"):
        raise ValueError("FALLBACK_NATIVE_SELECTION_MISMATCH")
    Journal(root).reserve(
        "fallback-dispatch",
        agent=agent,
        requested_model=MODEL,
        recorded_tool_selection=model,
        observed_backend_model=None,
    )
    return dict(status="FALLBACK_DISPATCH_RECORDED", agent=agent)


def complete(directory, result_path):
    root, manifest, _ = load(directory)
    dispatch = read(root / "fallback-dispatch.reserved.json")
    result = read(result_path)
    if result.get("agent") != dispatch["agent"] or result.get("ended") is not True:
        raise ValueError("FALLBACK_END_NOT_CONFIRMED")
    if result.get("status") not in ("ready", "blocked"):
        raise ValueError("INVALID_FALLBACK_RESULT")
    required_text(result.get("summary"))
    if not result.get("evidence"):
        raise ValueError("FALLBACK_RESULT_EVIDENCE_REQUIRED")
    hashes = {str(Path(p).resolve(strict=True)): digest(p) for p in result["evidence"]}
    marker = Path(manifest["project"]) / ".taskroute-stage.lock"
    if marker.read_text() != str(root):
        raise ValueError("FALLBACK_WRITER_MARKER_CHANGED")
    Journal(root).reserve(
        "fallback-complete",
        result=result,
        evidence_hashes=hashes,
        result_sha256=digest(result_path),
    )
    marker.unlink()
    return view(root)


def view(root):
    root = Path(root)
    reserved = root / "fallback.reserved.json"
    if not reserved.exists():
        return None
    saved = read(reserved)
    result = dict(
        status="FALLBACK_IN_PROGRESS_OR_UNKNOWN",
        requested_model=MODEL,
        recorded_tool_selection=None,
        observed_backend_model=None,
        reason=saved["evidence"]["reason"],
        usage={"state": "unknown"},
    )
    if (root / "fallback-dispatch.reserved.json").exists():
        result["recorded_tool_selection"] = MODEL
    end = root / "fallback-complete.reserved.json"
    if end.exists():
        terminal = read(end)
        changed = any(
            not Path(p).is_file() or digest(p) != sha
            for p, sha in terminal["evidence_hashes"].items()
        )
        result["status"] = (
            "EVIDENCE_CHANGED"
            if changed
            else "READY_FOR_ACCEPTANCE"
            if terminal["result"]["status"] == "ready"
            else "BLOCKED"
        )
    return result
