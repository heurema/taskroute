"""One-shot local evidence collection; no LLM polling or automatic retries."""

import ast
import difflib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from runtime import Journal, bounded_check, unittest_script
from verify_structured_flow import outside, read_stats


def preflight(run):
    """Check local launch inputs without model calls or attempt reservations."""
    run = Path(run).resolve()
    for name in (
        "manifest.json",
        "originals.json",
        "launch.py",
        "settings.json",
        "agents.json",
        "prompt.txt",
        "test.sb",
        "preflight.json",
    ):
        if not (run / name).is_file():
            raise ValueError("MISSING_LAUNCH_FILE: " + name)
    m = json.loads((run / "manifest.json").read_text())
    originals = json.loads((run / "originals.json").read_text())
    for name in ("settings.json", "agents.json", "preflight.json"):
        json.loads((run / name).read_text())
    if json.loads((run / "preflight.json").read_text()).get("status") != "PASS":
        raise ValueError("PREPARATION_NOT_APPROVED")
    if (run / "live-launch.reserved.json").exists():
        raise ValueError("LIVE_ATTEMPT_ALREADY_RESERVED")
    workspace = run / "workspace"
    if workspace.is_symlink() or Path(m["workspace"]) != workspace:
        raise ValueError("WORKSPACE_PATH_MISMATCH")
    if set(originals) != set(m["source_hashes"]):
        raise ValueError("INPUT_MANIFEST_MISMATCH")
    for name, expected in m["source_hashes"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("INVALID_INPUT_PATH")
        p = workspace / relative
        if not p.resolve().is_relative_to(workspace) or not p.is_file():
            raise ValueError("MISSING_OR_ESCAPING_INPUT: " + name)
        if (
            hashlib.sha256(p.read_bytes()).hexdigest() != expected
            or p.read_text() != originals[name]
        ):
            raise ValueError("INITIAL_INPUT_CHANGED: " + name)
    for name, expected in m["canonical_source_hashes"].items():
        if hashlib.sha256((Path(m["project_root"]) / name).read_bytes()).hexdigest() != expected:
            raise ValueError("CANONICAL_SOURCE_CHANGED")
    if not os.access(m["python"], os.X_OK):
        raise ValueError("PYTHON_NOT_EXECUTABLE")
    scratch = run / "scratch"
    if scratch.is_symlink():
        raise ValueError("SCRATCH_SYMLINK")
    scratch.mkdir(exist_ok=True)
    if any(scratch.iterdir()):
        raise ValueError("SCRATCH_NOT_EMPTY")
    with tempfile.TemporaryFile(dir=scratch) as probe:
        probe.write(b"local-preflight")
        probe.flush()
    return {
        "status": "PASS",
        "model_calls": 0,
        "checks": [
            "launch_files",
            "json",
            "fresh_attempt",
            "input_hashes",
            "canonical_hashes",
            "python",
            "scratch_writable",
        ],
        "limitations": ["Does not verify provider availability or future model behavior"],
    }


def inspect(run):
    run = Path(run).resolve()
    m = json.loads((run / "manifest.json").read_text())
    w = Path(m["workspace"])
    originals = json.loads((run / "originals.json").read_text())
    source = (w / m["target"]).read_text()
    tests = (w / m["test_target"]).read_text()
    checks = json.loads((w / "checks.json").read_text())
    function = m.get("target_function", "normalize_session")
    if outside(source, function) != outside(originals[m["target"]], function):
        raise ValueError("OUTSIDE_FUNCTION_CHANGE")
    allowed = {*originals, m["test_target"], "TASK.md", "checks.json"}
    for p in w.rglob("*"):
        if p.is_symlink() or (p.is_file() and str(p.relative_to(w)) not in allowed):
            raise ValueError("UNDECLARED_WORKSPACE_FILE")
    for n, body in originals.items():
        if n != m["target"] and (w / n).read_text() != body:
            raise ValueError("FROZEN_INPUT_CHANGED")
    for n, expected in m["canonical_source_hashes"].items():
        if hashlib.sha256((Path(m["project_root"]) / n).read_bytes()).hexdigest() != expected:
            raise ValueError("CANONICAL_SOURCE_CHANGED")
    for key, body in [("source_sha256", source), ("test_sha256", tests)]:
        if hashlib.sha256(body.encode()).hexdigest() != checks[key]:
            raise ValueError("CHECK_HASH_MISMATCH")
    methods = sum(
        isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        for n in ast.walk(ast.parse(tests))
    )
    if methods != m.get("worker_test_methods", 8) or checks["status"] != "PASS":
        raise ValueError("WORKER_CHECKS_NOT_ACCEPTABLE")
    rows = [json.loads(line) for line in (run / "stdout.jsonl").read_text().splitlines()]
    results = [x for x in rows if x.get("type") == "result"]
    terminal = json.loads((run / "terminal.json").read_text())
    if (
        len(results) != 1
        or results[0].get("is_error")
        or terminal["exit_code"] != 0
        or terminal.get("status", "ENDED") != "ENDED"
    ):
        raise ValueError("NONTERMINAL_WORKER")
    result = results[0]
    if m["model"] not in result.get("modelUsage", {}):
        raise ValueError("MODEL_IDENTITY_UNVERIFIED")
    children = result.get("subagent_stats", {})
    if children.get("spawned") != 1 or children.get("completed") != 1:
        raise ValueError("REVIEWER_NOT_COMPLETED")
    review = "\n\n".join(
        b["text"]
        for x in rows
        if x.get("type") == "assistant" and x.get("parent_tool_use_id")
        for b in x.get("message", {}).get("content", [])
        if b.get("type") == "text"
    )
    if not review.strip():
        raise ValueError("MISSING_REVIEW_TEXT")
    gates = [json.loads(line) for line in (run / "gate-events.jsonl").read_text().splitlines()]
    index = next(i for i, e in enumerate(gates) if e["tool"] in ("Task", "Agent") and e["allowed"])
    if any(e["allowed"] and e["tool"] in ("Edit", "Write") for e in gates[index + 1 :]):
        raise ValueError("EDIT_AFTER_REVIEW_START")
    return m, originals, source, tests, checks, review, result


def collect(run):
    run = Path(run).resolve()
    m, originals, source, tests, checks, review, result = inspect(run)
    expected_tests = m.get("independent_test_count", 45)
    Journal(run).reserve(
        "packet-acceptance", scope=f"fixed {expected_tests} tests, no worker tests"
    )
    scratch = run / "scratch/packet-acceptance"
    scratch.mkdir()
    for n, body in {**originals, m["target"]: source}.items():
        p = scratch / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    script = unittest_script(m.get("test_pattern", "test_claude_accounting*.py"), "stats.json")
    process = bounded_check(
        ["/usr/bin/sandbox-exec", "-f", str(run / "test.sb"), m["python"], "-B", "-c", script],
        scratch,
        30,
    )
    (run / "packet-check.log").write_text(process["feedback"])
    stats = read_stats(scratch / "stats.json", process)
    if process["returncode"] != 0 or stats["tests"] != expected_tests or stats["skips"] != 0:
        raise ValueError("INDEPENDENT_ACCEPTANCE_FAILED")
    # Bind the packet to the same files checked before and after execution.
    after = inspect(run)
    if after[2:4] != (source, tests):
        raise ValueError("CANDIDATE_CHANGED_DURING_CHECKS")
    packet = dict(
        status="READY_FOR_LEAD_REVIEW",
        independent_tests=stats,
        worker_tests={k: v["stats"] for k, v in checks["checks"].items()},
        source_sha256=checks["source_sha256"],
        test_sha256=checks["test_sha256"],
        scope=f"Only {m.get('target_function', 'normalize_session')} and {m.get('worker_test_methods', 8)} new worker test methods; canonical unchanged",
        diff="".join(
            difflib.unified_diff(
                originals[m["target"]].splitlines(True),
                source.splitlines(True),
                fromfile=m["target"] + " (stub)",
                tofile=m["target"],
            )
        ),
        worker_test_source=tests,
        reviewer_text=review,
        model_usage=result["modelUsage"],
        limitations=[
            "Exposed tests, not an unseen holdout; no quota weights",
            "Review verdict/findings need semantic lead acceptance; READY is not acceptance",
        ],
        evidence_root=str(run),
    )
    raw = json.dumps(packet, ensure_ascii=False, indent=2)
    if len(raw.encode()) > 48000:
        raise ValueError("PACKET_SIZE_CAP")
    (run / "acceptance-packet.json").write_text(raw)
    return packet


def main():
    run = Path(sys.argv[1]).resolve()
    try:
        if "--preflight" in sys.argv:
            print(json.dumps(preflight(run)))
            return 0
        if "--launch" in sys.argv:
            preflight(run)
            # launch.py owns the one-shot reservation and process timeout.
            done = subprocess.run(
                [sys.executable, "-B", str(run / "launch.py")], capture_output=True, text=True
            )
            if done.returncode:
                raise ValueError("LAUNCH_FAILED_NO_RETRY")
        print(json.dumps(collect(run), ensure_ascii=False))
    except Exception as exc:
        error = dict(status="BLOCKED", reason=str(exc), error_type=type(exc).__name__)
        (run / "packet-error.json").write_text(json.dumps(error, indent=2))
        print(json.dumps(error))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
