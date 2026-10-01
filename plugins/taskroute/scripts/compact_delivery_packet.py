"""One-shot local evidence collection; no LLM polling or automatic retries."""

import ast
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from runtime import Journal, bounded_check, unittest_script
from verify_structured_flow import outside, read_stats

TOKEN = re.compile(r"[a-z0-9_]{1,64}")


class DeliveryFailure(ValueError):
    """Primary native failure; secondary lists success-only artifacts left unread."""

    def __init__(self, primary, stage, evidence, secondary):
        super().__init__("NONTERMINAL_WORKER: " + primary)
        self.primary, self.stage, self.evidence, self.secondary = (
            primary,
            stage,
            evidence,
            secondary,
        )


def _token(value, fallback):
    value = str(value).lower() if isinstance(value, str) else ""
    return value if TOKEN.fullmatch(value) else fallback


def native_outcome(run, m):
    """Inspect terminal and native result before any success-only artifact.

    Evidence holds only sanitized scalar fields, never raw model or error text.
    """
    terminal_path, stream = run / "terminal.json", run / "stdout.jsonl"
    invalid_terminal = False
    try:
        terminal = json.loads(terminal_path.read_text()) if terminal_path.is_file() else None
        invalid_terminal = terminal_path.is_file() and not isinstance(terminal, dict)
    except (OSError, ValueError):
        terminal, invalid_terminal = None, True
    missing_terminal = not isinstance(terminal, dict)
    terminal = {} if missing_terminal else terminal
    rows, invalid = [], False
    if stream.is_file():
        try:
            lines = stream.read_text().splitlines()
        except (OSError, UnicodeError):
            lines, invalid = [], True
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                row = None
            if isinstance(row, dict):
                rows.append(row)
            else:
                invalid = True
    results = [x for x in rows if x.get("type") == "result"]
    result = results[0] if len(results) == 1 else {}
    subtype = result.get("subtype", "success") if len(results) == 1 else None
    status = terminal.get("status", "MISSING" if missing_terminal else "ENDED")
    if invalid_terminal:
        primary = "invalid_terminal"
    elif missing_terminal:
        primary = "missing_terminal"
    elif invalid:
        primary = "invalid_stream"
    elif len(results) > 1:
        primary = "duplicate_result"
    elif results and (result.get("is_error") or subtype != "success"):
        primary = _token(subtype, "result_error")
        primary = "result_error" if primary == "success" else primary
    elif status != "ENDED":
        primary = _token(status, "abnormal_terminal")
    elif not results:
        primary = "missing_result"
    elif terminal.get("exit_code") != 0:
        primary = "nonzero_exit"
    else:
        return rows, result
    exit_code, turns = terminal.get("exit_code"), result.get("num_turns")
    evidence = dict(
        terminal_status=_token(status, "unrecognized"),
        exit_code=exit_code if type(exit_code) is int else None,
        result_count=len(results),
        subtype=_token(subtype, "unrecognized") if subtype is not None else None,
        is_error=bool(result.get("is_error")) if results else None,
        requested_model=m.get("model"),
        observed_model=None,
        accepted_model=None,
        usage=None,
        num_turns=turns if type(turns) is int else None,
        max_parent_turns=m.get("max_parent_turns"),
        check_receipts=len(list(run.glob("check-receipt-*.json"))),
    )
    expected = [Path(m["workspace"]) / "checks.json", run / "gate-events.jsonl"]
    if m.get("review_gate_enabled"):
        expected.append(run / "review-gate.json")
    secondary = ["MISSING_SUCCESS_ARTIFACT: " + p.name for p in expected if not p.exists()]
    if not evidence["check_receipts"]:
        secondary.append("CHECKS_NOT_RUN")
    raise DeliveryFailure(primary, "native_result", evidence, secondary)


def launch_environment(run, m):
    """Probe current permissions; never grant access or run project test code."""
    environment = m.get("check_environment", {})
    if environment not in ({}, None):
        raise ValueError("UNSUPPORTED_CHECK_ENVIRONMENT: no additional roots or network")
    workspace = Path(m["workspace"])
    if not workspace.is_dir():
        raise ValueError("WORKSPACE_UNAVAILABLE")
    targets = m.get("writable_paths", [m.get("target"), m.get("test_target")])
    directories = {workspace}
    for name in filter(None, targets):
        target = workspace / name
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("INVALID_WRITE_PATH")
        if not target.resolve().is_relative_to(workspace):
            raise ValueError("WORKSPACE_WRITE_ESCAPE")
        parent = target.parent
        while not parent.exists():
            parent = parent.parent
        directories.add(parent)
        if target.exists():
            try:
                # Opening for write checks access without changing bytes.
                with target.open("r+b"):
                    pass
            except OSError as exc:
                raise ValueError("WORKSPACE_NOT_WRITABLE") from exc
    try:
        for directory in directories:
            with tempfile.TemporaryFile(dir=directory) as probe:
                probe.write(b"workspace-preflight")
                probe.flush()
    except OSError as exc:
        raise ValueError("WORKSPACE_NOT_WRITABLE") from exc
    for key, reason in (
        ("claude_binary", "PROVIDER_NOT_EXECUTABLE"),
        ("python", "PYTHON_NOT_EXECUTABLE"),
    ):
        binary = Path(m.get(key, ""))
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError(reason)
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file() or not os.access(sandbox, os.X_OK):
        raise ValueError("TEST_SANDBOX_UNAVAILABLE")
    scratch = run / "scratch"
    # Actual read/write/import capability in the unchanged check boundary.
    # This probes declared inputs only; arbitrary transitive dependencies are unknown.
    inputs = [str(workspace / name) for name in m["source_hashes"]]
    inputs.extend(check["argv"][0] for check in m.get("checks", []))
    script = (
        "import pathlib, unittest; "
        + "[pathlib.Path(p).open('rb').close() for p in "
        + repr(inputs)
        + "]; "
        + "pathlib.Path('probe').write_bytes(b'preflight')"
    )
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        result = bounded_check(
            [str(sandbox), "-f", str(run / "test.sb"), m["python"], "-B", "-c", script],
            Path(directory),
            10,
        )
    if result["returncode"] != 0 or result["stop_reason"]:
        raise ValueError("TEST_ENVIRONMENT_UNAVAILABLE")


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
    if (run / "terminal.json").exists() or (run / "launch-preflight-error.json").exists():
        raise ValueError("PRIOR_LAUNCH_RECEIPT: use a fresh run")
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
        if hashlib.sha256(p.read_bytes()).hexdigest() != expected or p.read_bytes() != originals[
            name
        ].encode("utf-8"):
            raise ValueError("INITIAL_INPUT_CHANGED: " + name)
    for name, expected in m["canonical_source_hashes"].items():
        if hashlib.sha256((Path(m["project_root"]) / name).read_bytes()).hexdigest() != expected:
            raise ValueError("CANONICAL_SOURCE_CHANGED")
    if not os.access(m["python"], os.X_OK):
        raise ValueError("PYTHON_NOT_EXECUTABLE")
    if m.get("mode") == "repository":
        from repository_task import check_tools, snapshot

        check_tools(m)
        snapshot(m, originals)
    scratch = run / "scratch"
    if scratch.is_symlink():
        raise ValueError("SCRATCH_SYMLINK")
    scratch.mkdir(exist_ok=True)
    if any(scratch.iterdir()):
        raise ValueError("SCRATCH_NOT_EMPTY")
    with tempfile.TemporaryFile(dir=scratch) as probe:
        probe.write(b"local-preflight")
        probe.flush()
    launch_environment(run, m)
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
            "workspace_writable",
            "test_environment",
            "provider_executable",
        ],
        "limitations": [
            "Does not verify provider auth, availability or future model behavior",
            "Transitive test dependencies remain unverified",
            "Provider instructions/hooks are not an OS sandbox or timeout guarantee",
        ],
    }


def inspect(run):
    run = Path(run).resolve()
    m = json.loads((run / "manifest.json").read_text())
    w = Path(m["workspace"])
    originals = json.loads((run / "originals.json").read_text())
    source = (w / m["target"]).read_bytes().decode("utf-8")
    tests = (w / m["test_target"]).read_bytes().decode("utf-8")
    checks = json.loads((w / "checks.json").read_text())
    function = m.get("target_function", "normalize_session")
    if outside(source, function) != outside(originals[m["target"]], function):
        raise ValueError("OUTSIDE_FUNCTION_CHANGE")
    allowed = {*originals, m["test_target"], "TASK.md", "checks.json"}
    for p in w.rglob("*"):
        if p.is_symlink() or (p.is_file() and str(p.relative_to(w)) not in allowed):
            raise ValueError("UNDECLARED_WORKSPACE_FILE")
    for n, body in originals.items():
        if n != m["target"] and (w / n).read_bytes() != body.encode("utf-8"):
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
    review, result = review_evidence(run, m)
    return m, originals, source, tests, checks, review, result


def review_evidence(run, m):
    """Validate transport/review evidence, independent of the project language."""
    rows, result = native_outcome(run, m)
    if m["model"] not in result.get("modelUsage", {}):
        raise ValueError("MODEL_IDENTITY_UNVERIFIED")
    children = result.get("subagent_stats", {})
    expected_children = 1
    if m.get("review_repair_enabled"):
        from review_gate import rounds

        expected_children = len(rounds(json.loads((run / "review-gate.json").read_text())))
        if expected_children not in (1, 2):
            raise ValueError("INVALID_REVIEW_ROUNDS")
    if (
        children.get("spawned") != expected_children
        or children.get("completed") != expected_children
    ):
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
    starts = [i for i, e in enumerate(gates) if e["tool"] in ("Task", "Agent") and e["allowed"]]
    if len(starts) != expected_children:
        raise ValueError("REVIEW_LAUNCH_COUNT_MISMATCH")
    for i, e in enumerate(gates):
        if not (e["allowed"] and e["tool"] in ("Edit", "Write") and i > starts[0]):
            continue
        if not m.get("review_repair_enabled") or expected_children != 2:
            raise ValueError("EDIT_AFTER_REVIEW_START")
        groups = rounds(json.loads((run / "review-gate.json").read_text()))
        if not (
            groups[0][-1]["status"] == "CHANGES"
            and e.get("time", 0) > groups[0][-1]["completed_at"]
            and i < starts[1]
            and not e.get("agent_id")
        ):
            raise ValueError("EDIT_OUTSIDE_REPAIR_WINDOW")
    if m.get("review_gate_enabled"):
        from review_gate import accepted_review

        if (run / "review-gate-error.json").exists():
            raise ValueError("REVIEW_GATE_ERROR")
        review = accepted_review(run, m, review)
    return review, result


def collect(run):
    run = Path(run).resolve()
    manifest = json.loads((run / "manifest.json").read_text())
    native_outcome(run, manifest)
    if manifest.get("mode") == "repository":
        from repository_task import collect as collect_repository

        return collect_repository(run)
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
        p.write_bytes(body.encode("utf-8"))
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


def lead_view(packet, run):
    """Omit echoed task fields only; retain all review text, findings and checks."""
    echoed = {"contract", "acceptance", "non_goals", "check_inputs"}
    view = {key: value for key, value in packet.items() if key not in echoed}
    view["task_source"] = str(Path(run) / "workspace" / "TASK.md")
    view["full_packet"] = str(Path(run) / "acceptance-packet.json")
    view["omitted_task_fields"] = sorted(echoed.intersection(packet))
    return view


def main():
    run = Path(sys.argv[1]).resolve()
    stage = "preflight"
    try:
        if "--preflight" in sys.argv:
            print(json.dumps(preflight(run)))
            return 0
        if "--launch" in sys.argv:
            preflight(run)
            stage = "launch"
            # launch.py owns the one-shot reservation and process timeout.
            done = subprocess.run(
                [sys.executable, "-B", str(run / "launch.py")], capture_output=True, text=True
            )
            if done.returncode:
                # Never discard a primary provider failure because the wrapper failed.
                native_outcome(run, json.loads((run / "manifest.json").read_text()))
                raise ValueError("LAUNCH_FAILED_NO_RETRY")
        stage = "collect"
        packet = collect(run)
        from backlog import capture

        packet["backlog"] = capture(run, packet)
        # Archive the exact complete packet, including backlog capture status.
        (run / "acceptance-packet.json").write_text(
            json.dumps(packet, ensure_ascii=False, indent=2)
        )
        output = lead_view(packet, run) if "--lead-view" in sys.argv else packet
        if "--receipt-only" in sys.argv:
            from delivery_receipt import receipt

            output = receipt(packet, run)
        print(json.dumps(output, ensure_ascii=False))
        if output.get("status") == "BLOCKED":
            return 2
        if packet["status"] != "READY_FOR_LEAD_REVIEW":
            return 2
    except Exception as exc:
        error = dict(
            status="BLOCKED",
            reason=str(exc),
            error_type=type(exc).__name__,
            stage=stage,
            primary="local_failure",
            secondary=[],
            readiness="NOT_READY",
            automatic_retry=False,
            requested_model=None,
            observed_model=None,
            accepted_model=None,
            usage=None,
        )
        if isinstance(exc, DeliveryFailure):
            error.update(
                stage=exc.stage,
                primary=exc.primary,
                secondary=exc.secondary,
                evidence=exc.evidence,
                requested_model=exc.evidence["requested_model"],
            )
        (run / "packet-error.json").write_text(json.dumps(error, indent=2))
        from backlog import capture

        error["backlog"] = capture(run, error)
        print(json.dumps(error))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
