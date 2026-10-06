"""Opt-in fresh Codex CLI route. Offline fixtures do not qualify live transport."""

import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import repository_task as repository
from runtime import Journal, check_policy, clean_environment
from task_contract import _record, assess, review_instruction, task_text

PROFILES = {"worker": "gpt-6.1-sol", "reviewer": "gpt-6-astra"}


def write(root, name, value):
    (root / name).write_text(json.dumps(value, indent=2))


def load(root):
    m = json.loads((root / "manifest.json").read_text())
    if m.get("route") != "sol-astra" or m.get("profiles") != PROFILES:
        raise ValueError("INVALID_CODEX_ROUTE")
    return m, json.loads((root / "originals.json").read_text())


def prepare(spec_path, project, destination):
    project, root = Path(project).resolve(), Path(destination).absolute()
    if root.exists():
        raise ValueError("RUN_DIRECTORY_ALREADY_EXISTS")
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ValueError("UNSUPPORTED_PLATFORM")
    binary = shutil.which("codex")
    if not binary:
        raise ValueError("CODEX_NOT_INSTALLED")
    spec = json.loads(Path(spec_path).read_text())
    if spec.get("mode") != "repository":
        raise ValueError("CODEX_REQUIRES_REPOSITORY_MODE")
    # Route profiles override no legacy receipt: the explicit spec must agree.
    if spec.get("model") != PROFILES["worker"]:
        raise ValueError("WORKER_PROFILE_MISMATCH")
    spec = repository.validate(spec, project)
    originals = {n: (project / n).read_bytes().decode("utf-8") for n in spec["files"]}
    root.mkdir(parents=True)
    root = root.resolve()
    w = root / "workspace"
    w.mkdir()
    (root / "scratch").mkdir()
    for n, body in originals.items():
        p = w / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode())
    (w / "TASK.md").write_text(task_text(spec))
    m = dict(
        spec,
        route="sol-astra",
        profiles=PROFILES,
        project_root=str(project),
        workspace=str(w),
        canonical_source_hashes={n: repository.digest(b) for n, b in originals.items()},
        codex_binary=str(Path(binary).resolve()),
        max_checks=1,
        wall_seconds=600,
    )
    from check_environment import policy_options
    from check_environment import prepare as prepare_environment

    prepare_environment(root, m)
    write(root, "manifest.json", m)
    write(root, "originals.json", originals)
    policy = check_policy(w, root / "scratch", **policy_options(m))
    (root / "test.sb").write_text(policy)
    write(
        root, "preflight.json", dict(status="PREPARED", model_calls=0, live_capability="UNVERIFIED")
    )
    return dict(status="PREPARED", run=str(root), route="sol-astra", model_calls=0)


def argv(m, role, workspace):
    return [
        m["codex_binary"],
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--skip-git-repo-check",
        "--json",
        "--color",
        "never",
        "-m",
        m["profiles"][role],
        "-c",
        'model_reasoning_effort="medium"',
        "-s",
        "workspace-write" if role == "worker" else "read-only",
        "-C",
        str(workspace),
        "-",
    ]


def invoke(command, prompt, workspace, timeout):
    """Bounded native JSONL capture; no resume, retry, key or endpoint inheritance."""
    proc = subprocess.Popen(
        command,
        cwd=workspace,
        env=clean_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    data, deadline = bytearray(), time.monotonic() + timeout
    pending = memoryview(prompt.encode())
    offset = 0
    try:
        os.set_blocking(proc.stdin.fileno(), False)
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            sel.register(proc.stdin, selectors.EVENT_WRITE)
            while sel.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("CODEX_TIMEOUT")
                for key, _ in sel.select(min(0.1, remaining)):
                    if key.fileobj is proc.stdin:
                        try:
                            offset += os.write(key.fd, pending[offset : offset + 8192])
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            offset = len(pending)
                        if offset == len(pending):
                            sel.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        block = os.read(key.fd, 8192)
                        if not block:
                            sel.unregister(key.fileobj)
                        else:
                            data.extend(block)
                            if len(data) > 1048576:
                                raise ValueError("CODEX_OUTPUT_CAP")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("CODEX_TIMEOUT")
        try:
            code = proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("CODEX_TIMEOUT") from exc
        return code, data.decode("utf-8")
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        proc.stdout.close()
        proc.stdin.close()


def parse(code, text, requested):
    """Native reported identity only; argv and prose never prove observed model."""
    session, model, final, usage = None, None, [], None
    started, completed = 0, 0
    for line in text.splitlines():
        event = json.loads(line)
        kind = event.get("type")
        if kind in {"error", "turn.failed"}:
            raise ValueError("CODEX_NATIVE_FAILURE")
        if kind == "thread.started":
            started += 1
            session = event.get("thread_id")
            model = event.get("model")
        if kind == "turn.completed":
            completed += 1
            usage = event.get("usage")
        if kind == "item.completed" and event.get("item", {}).get("type") == "agent_message":
            final.append(event["item"].get("text", ""))
    if (
        code != 0
        or started != 1
        or completed != 1
        or not isinstance(session, str)
        or not session
        or not final
    ):
        raise ValueError("CODEX_INCOMPLETE_TERMINAL")
    identity = "UNKNOWN" if model is None else "ACCEPTED" if model == requested else "MISMATCH"
    return dict(
        session=session,
        requested_model=requested,
        observed_model=model,
        accepted_model=requested if identity == "ACCEPTED" else None,
        identity=identity,
        text="\n".join(final),
        usage=usage,
    )


def launch(root, m, role, prompt, workspace, transport=invoke):
    Journal(root).reserve("codex-" + role, requested_model=m["profiles"][role], fresh=True)
    command = argv(m, role, workspace)
    write(
        root,
        role + "-launch.json",
        dict(
            argv=command,
            prompt_sha256=repository.digest(prompt),
            state="SUBMISSION_UNCERTAIN",
            automatic_retry=False,
        ),
    )
    code, output = transport(command, prompt, workspace, m["wall_seconds"])
    (root / (role + ".jsonl")).write_text(output)
    result = parse(code, output, m["profiles"][role])
    write(root, role + "-receipt.json", result)
    if result["identity"] != "ACCEPTED":
        raise ValueError("CODEX_IDENTITY_" + result["identity"])
    return result


def run(directory, transport=invoke):
    root = Path(directory).resolve()
    m, originals = load(root)
    # One durable whole-route reservation, even if startup/terminal status is unknown.
    Journal(root).reserve("codex-route", route="sol-astra", automatic_retry=False)
    try:
        repository.snapshot(m, originals)
        prompt = (
            task_text(m)
            + "\nFinish with exactly one TASKROUTE_RESULT: JSON line with keys status (READY_FOR_LEAD or BLOCKED) and reason (nonempty string).\nEdit only "
            + json.dumps(m["writable_paths"])
            + ". No installs, network, agents, canonical apply or scope changes. Finish implementation; host runs frozen checks and a fresh independent reviewer."
        )
        worker = launch(root, m, "worker", prompt, Path(m["workspace"]), transport)
        worker_outcome = _record(worker["text"], "TASKROUTE_RESULT:")
        if (
            set(worker_outcome) != {"status", "reason"}
            or worker_outcome["status"] != "READY_FOR_LEAD"
            or not isinstance(worker_outcome["reason"], str)
            or not worker_outcome["reason"].strip()
        ):
            raise ValueError("WORKER_OUTCOME_BLOCKED_OR_INVALID")
        bodies = repository.snapshot(m, originals)
        hashes = {n: repository.digest(b) for n, b in bodies.items()}
        Journal(root).reserve("codex-checks")
        checks = repository.execute(root, m, bodies, "codex-check")
        if any(c["exit_code"] != 0 for c in checks):
            raise ValueError("CHECKS_FAILED")
        if repository.snapshot(m, originals) != bodies:
            raise ValueError("CANDIDATE_CHANGED_DURING_CHECKS")
        frozen = dict(status="PASS", checks=checks, file_hashes=hashes)
        write(root, "candidate.json", frozen)
        # Fresh independent read-only session sees only the copied candidate + checks.
        review_space = root / "review-workspace"
        review_space.mkdir()
        for n, body in bodies.items():
            p = review_space / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body.encode())
        (review_space / "TASK.md").write_text(task_text(m))
        write(review_space, "checks.json", frozen)
        review_prompt = (
            task_text(m)
            + "\n"
            + review_instruction(m)
            + "\nInspect all declared files and checks.json. Read-only; no tools that change files, no agents, installs or network. Findings bind to candidate "
            + json.dumps(hashes)
        )
        reviewer = launch(root, m, "reviewer", review_prompt, review_space, transport)
        if worker["session"] == reviewer["session"]:
            raise ValueError("REVIEW_SESSION_REUSED")
        expected = {**bodies, "TASK.md": task_text(m), "checks.json": json.dumps(frozen, indent=2)}
        actual = {
            str(p.relative_to(review_space)): p.read_bytes().decode()
            for p in review_space.rglob("*")
            if p.is_file()
        }
        if any(p.is_symlink() for p in review_space.rglob("*")) or actual != expected:
            raise ValueError("REVIEW_COPY_CHANGED")
        if repository.snapshot(m, originals) != bodies:
            raise ValueError("CANDIDATE_CHANGED_DURING_REVIEW")
        outcome = assess(m, reviewer["text"], worker["text"], bodies)
        if outcome["reasons"]:
            raise ValueError("REVIEW_REJECTED: " + json.dumps(outcome["reasons"]))
        result = dict(
            status="READY_FOR_LEAD_REVIEW",
            route="sol-astra",
            candidate=hashes,
            checks=checks,
            worker=worker,
            reviewer=reviewer,
            assessment=outcome,
            actual_charge=None,
            subscription_quota=None,
            live_qualification="UNVERIFIED",
            limitations=[
                "No canonical apply",
                "CLI sandbox is not per-file tool enforcement",
                "Model-reported findings require lead acceptance",
            ],
        )
    except Exception as exc:
        result = dict(
            status="BLOCKED",
            route="sol-astra",
            reason=str(exc),
            automatic_retry=False,
            submission="Inspect role launch/receipt evidence; missing terminal remains uncertain",
            live_qualification="UNVERIFIED",
        )
    write(root, "codex-receipt.json", result)
    return result
