"""One native stage, coordinator decisions and evidence. No daemon or retries."""

import argparse
import fcntl
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from runtime import Journal, clean_environment

ROLES = ("preparation", "direct_work", "worker", "advice", "review", "acceptance", "repair")


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(root, name, value):
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".stage-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, Path(root) / name)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def required_text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("NONEMPTY_TEXT_REQUIRED")
    return value


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("INVALID_NONNEGATIVE_MEASUREMENT")
    return value


def choose(facts):
    """Judgment belongs to the coordinator; this is a frozen transparent policy."""
    for key in ("agreed", "checks_available", "handoff_worthwhile"):
        if type(facts.get(key)) is not bool:
            raise ValueError("ROUTING_FACTS_REQUIRED")
    required_text(facts.get("reason"))
    if not facts["agreed"]:
        return "clarify"
    if not facts["checks_available"]:
        return "blocked"
    return "delegate" if facts["handoff_worthwhile"] else "direct"


def prepare(contract_path, project, root):
    contract = read(contract_path)
    project, root = Path(project).resolve(strict=True), Path(root).resolve()
    if not project.is_dir():
        raise ValueError("PROJECT_DIRECTORY_REQUIRED")
    route = choose(contract["routing"])
    required_text(contract.get("task"))
    required_text(contract.get("source_ref"))
    required_text(contract.get("scope"))
    acceptance = contract.get("acceptance")
    if not isinstance(acceptance, list) or not acceptance:
        raise ValueError("ACCEPTANCE_REQUIRED")
    for item in acceptance:
        required_text(item)
    if len(set(acceptance)) != len(acceptance):
        raise ValueError("DUPLICATE_ACCEPTANCE")
    if route == "delegate":
        required_text(contract.get("model"))
        if contract.get("effort") not in ("low", "medium", "high"):
            raise ValueError("EXPLICIT_EFFORT_REQUIRED")
        seconds = contract.get("timeout_seconds")
        if type(seconds) is not int or not 1 <= seconds <= 3600:
            raise ValueError("TIMEOUT_REQUIRED_1_TO_3600")
        allowed = contract.get("allowed_tools")
        if not isinstance(allowed, list) or not allowed:
            raise ValueError("EXPLICIT_TOOL_PERMISSIONS_REQUIRED")
        for tool in allowed:
            required_text(tool)
            if tool.split("(", 1)[0] not in ("Read", "Glob", "Grep", "Edit", "Write", "Bash"):
                raise ValueError("UNSUPPORTED_TOOL_PERMISSION")
        required_text(contract.get("instructions"))
    root.mkdir(parents=True, exist_ok=False)
    save(root, "contract.json", contract)
    prompt = (
        "Implement one agreed stage. Read applicable project instructions first. "
        "No subagents, provider calls, network commands, installation, credentials, "
        "configuration changes, git mutations or publication. Do not resume other sessions. "
        "Own implementation and executable checks; at most one understood corrective "
        "repair within this same turn. Otherwise report a blocker. Preserve unrelated work. "
        "Never weaken acceptance. Stop on missing permission or capability. "
        "Return changed paths, executed check commands, outcomes, evidence paths and risks. "
        "Do not claim lead acceptance. This instruction is not an OS sandbox.\n\n"
        + json.dumps(contract, indent=2)
    )
    (root / "prompt.txt").write_text(prompt)
    save(
        root,
        "manifest.json",
        dict(
            schema_version=1,
            project=str(project),
            route=route,
            created_at=time.time(),
            contract_sha256=digest(root / "contract.json"),
            prompt_sha256=digest(root / "prompt.txt"),
            attempt_ceiling=1,
            automatic_retry=False,
        ),
    )
    return report(root)


def load(root):
    root = Path(root).resolve(strict=True)
    manifest = read(root / "manifest.json")
    for name in ("contract", "prompt"):
        path = root / (name + (".json" if name == "contract" else ".txt"))
        if digest(path) != manifest[name + "_sha256"]:
            raise ValueError("FROZEN_INPUT_CHANGED")
    return root, manifest, read(root / "contract.json")


def execute(root, binary, authority):
    """An explicit authority receipt is required; it is evidence, not an ACL."""
    root, manifest, contract = load(root)
    if manifest["route"] != "delegate":
        raise ValueError("NOT_A_DELEGATED_STAGE")
    authority = Path(authority).resolve(strict=True)
    required_text(authority.read_text())
    binary = Path(binary).resolve(strict=True)
    # Persistent marker survives a lost parent. All stage runs in this project share it.
    lock = Path(manifest["project"]) / ".taskroute-stage.lock"
    journal = Journal(root)
    with (root / "mutation.lock").open("a") as mutex:
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (root / "worker.reserved.json").exists() or (root / "fallback.reserved.json").exists():
            raise ValueError("ATTEMPT_ALREADY_CONSUMED")
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(str(root))
            stream.flush()
            os.fsync(stream.fileno())
        terminal = None
        try:
            journal.reserve(
                "worker",
                authority_sha256=digest(authority),
                authority_ref=str(authority),
                binary=str(binary),
                binary_sha256=digest(binary),
            )
            started = time.time()
            save(root, "state.json", dict(status="RUNNING", started_at=started))
            argv = [
                str(binary),
                "--print",
                "--safe-mode",
                "--no-session-persistence",
                "--output-format",
                "json",
                "--model",
                contract["model"],
                "--effort",
                contract["effort"],
                "--permission-mode",
                "dontAsk",
                "--tools",
                "Read,Glob,Grep,Edit,Write,Bash",
                "--allowedTools",
                *contract["allowed_tools"],
            ]
            with (
                (root / "prompt.txt").open("rb") as prompt,
                (root / "worker.json").open("wb") as stdout,
                (root / "worker.stderr").open("wb") as stderr,
            ):
                proc = subprocess.Popen(
                    argv,
                    cwd=manifest["project"],
                    stdin=prompt,
                    stdout=stdout,
                    stderr=stderr,
                    env=clean_environment(),
                    start_new_session=True,
                )
                stop = None
                try:
                    deadline = time.monotonic() + contract["timeout_seconds"]
                    while proc.poll() is None:
                        if time.monotonic() >= deadline:
                            stop = "TIMEOUT"
                            break
                        if (
                            sum(
                                (root / name).stat().st_size
                                for name in ("worker.json", "worker.stderr")
                            )
                            > 16 * 1024 * 1024
                        ):
                            stop = "OUTPUT_LIMIT"
                            break
                        time.sleep(0.1)
                except BaseException:
                    stop = "INTERRUPTED"
                    raise
                finally:
                    # Kill our process group, including children after CLI exit.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    terminal = dict(
                        status="BLOCKED",
                        stop_reason=stop,
                        returncode=proc.returncode,
                        elapsed_seconds=time.time() - started,
                    )
                    save(root, "terminal.json", terminal)
            if (
                sum((root / name).stat().st_size for name in ("worker.json", "worker.stderr"))
                > 16 * 1024 * 1024
            ):
                stop = "OUTPUT_LIMIT"
                terminal["stop_reason"] = stop
            if stop is None:
                result = read(root / "worker.json")
                models = list(result.get("modelUsage", {}))
                observed_usage = result.get("modelUsage", {})
                for counts in observed_usage.values():
                    for key in (
                        "inputTokens",
                        "outputTokens",
                        "cacheReadInputTokens",
                        "cacheCreationInputTokens",
                        "costUSD",
                    ):
                        if key in counts:
                            number(counts[key])
                if result.get("total_cost_usd") is not None:
                    number(result["total_cost_usd"])
                denied = result.get("permission_denials", [])
                terminal.update(observed_models=models, requested_model=contract["model"])
                if (
                    proc.returncode == 0
                    and result.get("is_error") is False
                    and models == [contract["model"]]
                    and not denied
                ):
                    terminal["status"] = "READY_FOR_ACCEPTANCE"
                    terminal["accepted_model"] = contract["model"]
                else:
                    terminal["stop_reason"] = "MODEL_ERROR_IDENTITY_OR_PERMISSION"
                terminal["worker_sha256"] = digest(root / "worker.json")
            save(root, "terminal.json", terminal)
        except Exception as error:
            if terminal is None:
                terminal = dict(status="UNKNOWN", reason=type(error).__name__)
            else:
                terminal.update(status="BLOCKED", reason=type(error).__name__)
            save(root, "terminal.json", terminal)
            raise
        finally:
            # UNKNOWN retains its marker: process completion has not been established.
            if terminal and terminal["status"] != "UNKNOWN":
                lock.unlink()
    return report(root)


def observe(root, role, path):
    root, _, _ = load(root)
    if role not in ROLES or role == "worker":
        raise ValueError("INVALID_OBSERVATION_ROLE")
    value = read(path)
    if value.get("state") not in ("observed", "not_used", "unknown"):
        raise ValueError("OBSERVATION_STATE_REQUIRED")
    required_text(value.get("source"))
    if value["state"] == "observed":
        if not isinstance(value.get("tokens"), dict) or not value["tokens"]:
            raise ValueError("TOKEN_OBSERVATION_REQUIRED")
        for measurement in value["tokens"].values():
            number(measurement)
    for key in ("elapsed_seconds", "owner_minutes", "actual_charge_usd", "api_estimate_usd"):
        if value.get(key) is not None:
            number(value[key])
    # One summary per role prevents accidental re-import/double counting.
    Journal(root).reserve("observation-" + role, observation=value, source_sha256=digest(path))
    return report(root)


def accept(root, review_path):
    root, manifest, contract = load(root)
    if manifest["route"] not in ("direct", "delegate"):
        raise ValueError("ROUTE_NOT_ACCEPTABLE")
    if manifest["route"] == "delegate" and report(root)["status"] != "READY_FOR_ACCEPTANCE":
        raise ValueError("WORKER_NOT_READY")
    review = read(review_path)
    if review.get("verdict") not in ("accepted", "rejected"):
        raise ValueError("EXPLICIT_VERDICT_REQUIRED")
    required_text(review.get("reviewer"))
    required_text(review.get("reason"))
    if review["verdict"] == "accepted":
        if review.get("criteria_met") != contract["acceptance"]:
            raise ValueError("ALL_CRITERIA_REQUIRED")
        if not review.get("evidence"):
            raise ValueError("REVIEW_EVIDENCE_REQUIRED")
    evidence = {}
    for path in review.get("evidence", []):
        resolved = Path(path).resolve(strict=True)
        evidence[str(resolved)] = digest(resolved)
    Journal(root).reserve(
        "acceptance", review=review, evidence_hashes=evidence, review_sha256=digest(review_path)
    )
    return report(root)


def report(root):
    root, manifest, contract = load(root)
    status = {
        "delegate": "PREPARED",
        "direct": "DIRECT",
        "clarify": "NEEDS_DECISION",
        "blocked": "BLOCKED",
    }[manifest["route"]]
    terminal = read(root / "terminal.json") if (root / "terminal.json").exists() else {}
    if terminal:
        status = terminal["status"]
    elif (root / "worker.reserved.json").exists():
        # A stale RUNNING claim is never treated as proof of a live process.
        status = "IN_PROGRESS_OR_UNKNOWN"
    usage = {}
    for role in ROLES:
        path = root / ("observation-" + role + ".reserved.json")
        usage[role] = read(path)["observation"] if path.exists() else dict(state="unknown")
    if manifest["route"] != "delegate":
        usage["worker"] = dict(state="not_used")
    elif terminal.get("worker_sha256"):
        if digest(root / "worker.json") != terminal["worker_sha256"]:
            raise ValueError("WORKER_EVIDENCE_CHANGED")
        result = read(root / "worker.json")
        usage["worker"] = dict(
            state="observed" if result.get("modelUsage") else "unknown",
            model_usage=result.get("modelUsage"),
            api_estimate_usd=result.get("total_cost_usd"),
            actual_charge_usd=None,
            elapsed_seconds=terminal["elapsed_seconds"],
        )
    from stage_fallback import view as fallback_view

    fallback = fallback_view(root)
    usage["fallback_worker"] = dict(state="unknown" if fallback else "not_used")
    if fallback:
        status = fallback["status"]
    acceptance = root / "acceptance.reserved.json"
    if acceptance.exists():
        recorded = read(acceptance)
        changed = [
            p
            for p, sha in recorded["evidence_hashes"].items()
            if not Path(p).is_file() or digest(p) != sha
        ]
        status = (
            "EVIDENCE_CHANGED"
            if changed or status == "EVIDENCE_CHANGED"
            else recorded["review"]["verdict"].upper()
        )
    return dict(
        schema_version=1,
        status=status,
        route=manifest["route"],
        reason=contract["routing"]["reason"],
        task=contract["task"],
        run=str(root),
        attempt_ceiling=1,
        retry_allowed=False,
        terminal=terminal,
        fallback=fallback,
        roles=usage,
        full_route_usage_complete=all(
            v["state"] == "not_used"
            or (v["state"] == "observed" and not v.get("coverage", "").startswith("partial"))
            for v in usage.values()
        ),
        subscription_quota_attribution="UNKNOWN",
        savings="UNPROVEN",
    )


def snapshot(session_log, destination):
    """Extract counters only; never copy messages, credentials or account balances."""
    path = Path(session_log).resolve(strict=True)
    session, latest = None, None
    with path.open() as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except ValueError:
                continue  # An active JSONL writer may have an unfinished final line.
            payload = event.get("payload", {})
            if event.get("type") == "session_meta":
                session = payload.get("id")
            if event.get("type") != "event_msg" or payload.get("type") != "token_count":
                continue
            counts = (payload.get("info") or {}).get("total_token_usage")
            if not isinstance(counts, dict) or not counts:
                continue
            for value in counts.values():
                number(value)
            rate = payload.get("rate_limits") or {}
            primary = rate.get("primary") or {}
            latest = dict(
                timestamp=event.get("timestamp"),
                tokens=counts,
                quota_snapshot={
                    k: primary.get(k) for k in ("used_percent", "window_minutes", "resets_at")
                },
            )
    if not session or not latest:
        raise ValueError("SESSION_OR_COUNTERS_UNAVAILABLE")
    result = dict(
        session_id=session, source=str(path), **latest, coverage="through_last_flushed_counter_only"
    )
    destination = Path(destination).resolve()
    Journal(destination.parent).reserve(destination.name, snapshot=result)
    return result


def measure(root, role, before_path, after_path):
    """Record one caller-declared role interval; do not infer complete turn coverage."""
    before = read(before_path)["snapshot"]
    after = read(after_path)["snapshot"]
    if before["session_id"] != after["session_id"] or before["source"] != after["source"]:
        raise ValueError("DIFFERENT_PHYSICAL_SESSIONS")
    if set(before["tokens"]) != set(after["tokens"]):
        raise ValueError("COUNTER_SCHEMA_CHANGED")
    delta = {key: number(after["tokens"][key] - value) for key, value in before["tokens"].items()}
    value = dict(
        state="observed",
        source=after["source"],
        tokens=delta,
        coverage="partial_through_last_flushed_counter",
        timestamps=[before["timestamp"], after["timestamp"]],
        quota_snapshots=[before["quota_snapshot"], after["quota_snapshot"]],
        quota_attribution="UNKNOWN_SHARED_ACCOUNT_AND_POSSIBLE_CONCURRENCY",
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "observation.json"
        path.write_text(json.dumps(value))
        return observe(root, role, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("contract")
    prep.add_argument("--project", required=True)
    prep.add_argument("--run", required=True)
    run = commands.add_parser("run")
    run.add_argument("directory")
    run.add_argument("--binary", required=True)
    run.add_argument("--authority", required=True)
    review = commands.add_parser("accept")
    review.add_argument("directory")
    review.add_argument("review")
    obs = commands.add_parser("observe")
    obs.add_argument("directory")
    obs.add_argument("role", choices=ROLES)
    obs.add_argument("observation")
    commands.add_parser("report").add_argument("directory")
    snap = commands.add_parser("snapshot")
    snap.add_argument("session_log")
    snap.add_argument("destination", help="Fresh marker basename; .reserved.json is appended")
    measured = commands.add_parser("measure")
    measured.add_argument("directory")
    measured.add_argument("role", choices=ROLES)
    measured.add_argument("before")
    measured.add_argument("after")
    fallback = commands.add_parser("fallback-reserve")
    fallback.add_argument("directory")
    fallback.add_argument("evidence")
    dispatch = commands.add_parser("fallback-dispatched")
    dispatch.add_argument("directory")
    dispatch.add_argument("--agent", required=True)
    dispatch.add_argument("--model", required=True)
    completed = commands.add_parser("fallback-complete")
    completed.add_argument("directory")
    completed.add_argument("result")
    args = parser.parse_args(argv)
    if args.action.startswith("fallback-"):
        import stage_fallback

        if args.action == "fallback-reserve":
            result = stage_fallback.reserve(args.directory, args.evidence)
        elif args.action == "fallback-dispatched":
            result = stage_fallback.dispatched(args.directory, args.agent, args.model)
        else:
            result = stage_fallback.complete(args.directory, args.result)
        print(json.dumps(result, indent=2))
        return 2 if result["status"] in ("BLOCKED", "EVIDENCE_CHANGED") else 0
    if args.action == "snapshot":
        print(json.dumps(snapshot(args.session_log, args.destination), indent=2))
        return 0
    if args.action == "measure":
        result = measure(args.directory, args.role, args.before, args.after)
    elif args.action == "prepare":
        result = prepare(args.contract, args.project, args.run)
    elif args.action == "run":
        result = execute(args.directory, args.binary, args.authority)
    elif args.action == "accept":
        result = accept(args.directory, args.review)
    elif args.action == "observe":
        result = observe(args.directory, args.role, args.observation)
    else:
        result = report(args.directory)
    print(json.dumps(result, indent=2))
    return 2 if result["status"] in ("BLOCKED", "UNKNOWN", "EVIDENCE_CHANGED", "REJECTED") else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps(dict(status="BLOCKED", reason=str(error))))
        sys.exit(2)
