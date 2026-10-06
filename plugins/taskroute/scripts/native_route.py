"""Deterministic support for Codex-native roles; never launches a model itself."""

import difflib
import json
import shlex
import sys
from pathlib import Path

import repository_task as repository
from runtime import Journal, check_policy, sqlite_readiness
from task_contract import _record, assess, review_instruction, task_text

PROFILES = {"worker": "gpt-6.1-sol", "reviewer": "gpt-6-astra"}
SELECTION_REASONS = (
    "owner_request",
    "tool_requirement",
    "task_family_evidence",
    "default_policy",
    "unknown",
)


def validate_selection_reason(reason):
    if type(reason) is not str or reason not in SELECTION_REASONS:
        raise ValueError("INVALID_NATIVE_SELECTION_REASON")
    return reason


def save(root, name, value):
    with (root / name).open("x") as stream:
        json.dump(value, stream, indent=2)


def load(root):
    root = Path(root).resolve()
    m = json.loads((root / "manifest.json").read_text())
    if m.get("route") != "codex-native" or m.get("profiles") != PROFILES:
        raise ValueError("INVALID_NATIVE_MANIFEST")
    validate_selection_reason(m.get("selection_reason", "unknown"))
    return root, m, json.loads((root / "originals.json").read_text())


def prepare(spec_path, project, destination, *, selection_reason="unknown"):
    selection_reason = validate_selection_reason(selection_reason)
    project, root = Path(project).resolve(), Path(destination).absolute()
    if root.exists():
        raise ValueError("RUN_DIRECTORY_ALREADY_EXISTS")
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ValueError("UNSUPPORTED_PLATFORM")
    spec = json.loads(Path(spec_path).read_text())
    if spec.get("mode") != "repository" or spec.get("model") != PROFILES["worker"]:
        raise ValueError("NATIVE_REQUIRES_SOL_REPOSITORY_CONTRACT")
    spec = repository.validate(spec, project)
    originals = {n: (project / n).read_bytes().decode("utf-8") for n in spec["files"]}
    root.mkdir(parents=True)
    root = root.resolve()
    workspace = root / "workspace"
    workspace.mkdir()
    (root / "scratch").mkdir()
    for name, body in originals.items():
        p = workspace / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode())
    (workspace / "TASK.md").write_text(task_text(spec))
    m = dict(
        spec,
        route="codex-native",
        selection_reason=selection_reason,
        profiles=PROFILES,
        effort="medium",
        workspace=str(workspace),
        project_root=str(project),
        max_checks=1,
        canonical_source_hashes={n: repository.digest(b) for n, b in originals.items()},
    )
    from check_environment import policy_options
    from check_environment import prepare as prepare_environment

    prepare_environment(root, m)
    if m.get("check_environment"):
        m["source_hashes"] = dict(m["canonical_source_hashes"])
        m["verify_command"] = shlex.join(
            [
                sys.executable,
                "-B",
                str(Path(__file__).with_name("verify_structured_flow.py")),
                str(root),
            ]
        )
    save(root, "manifest.json", m)
    save(root, "originals.json", originals)
    (root / "test.sb").write_text(check_policy(workspace, root / "scratch", **policy_options(m)))
    prompt = (
        task_text(m)
        + "\nWork only in "
        + str(workspace)
        + ". Sole candidate writer. Writable paths: "
        + json.dumps(m["writable_paths"])
        + ". Read TASK.md and declared inputs: "
        + json.dumps(m["files"])
        + "\nDeclared checks (cwd is this workspace): "
        + json.dumps([{k: c[k] for k in ("name", "argv", "timeout_seconds")} for c in m["checks"]])
        + "\nPreserve frozen inputs. Execute only declared checks, once each, and report command/exit status. No nested agents, other models, network, installs, auth, canonical apply, commits or retries. Stop on failure. Host reruns frozen checks and supplies an independent reviewer. Finish with exactly one single-line TASKROUTE_RESULT: JSON object with only status (READY_FOR_LEAD or BLOCKED) and nonempty reason."
    )
    if m.get("check_environment"):
        prompt = prompt.replace(
            "Execute only declared checks, once each, and report command/exit status.",
            "Run this exact frozen verifier once for all declared checks: "
            + m["verify_command"]
            + ". It supplies isolated dependency copies and the declared loopback policy. "
            + "Report its check receipt; do not execute the check commands separately.",
        )
    (root / "worker-prompt.txt").write_text(prompt)
    return dict(status="PREPARED", run=str(root), model_calls=0, route="codex-native")


def frozen(root, m, originals):
    bodies = repository.snapshot(m, originals)
    checks = json.loads((root / "native-checks.json").read_text())
    if checks.get("status") != "PASS" or checks["file_hashes"] != {
        n: repository.digest(b) for n, b in bodies.items()
    }:
        raise ValueError("NATIVE_CANDIDATE_CHANGED")
    return bodies, checks


def reserve(directory, role):
    root, m, originals = load(directory)
    if role not in PROFILES:
        raise ValueError("INVALID_NATIVE_ROLE")
    if (root / "native-receipt.json").exists():
        raise ValueError("NATIVE_RUN_TERMINAL")
    if role == "reviewer":
        frozen(root, m, originals)
    else:
        repository.snapshot(m, originals)
        repository.check_tools(m)
        sqlite_readiness(root, sys.executable, [str(Path(m["workspace"]) / n) for n in m["files"]])
    Journal(root).reserve("native-" + role, model_requested=PROFILES[role], fresh=True)
    return dict(
        status="RESERVED_SUBMISSION_UNCERTAIN",
        role=role,
        model=PROFILES[role],
        effort=m["effort"],
        fork_turns="none",
        prompt=str(root / (role + "-prompt.txt")),
        workspace=m["workspace"] if role == "worker" else str(root / "review-workspace"),
        automatic_retry=False,
    )


def dispatch(directory, role, agent, model):
    root, m, _ = load(directory)
    if role not in PROFILES or model != m["profiles"][role]:
        raise ValueError("NATIVE_DISPATCH_PROFILE_MISMATCH")
    if not isinstance(agent, str) or not agent.startswith("/root/") or len(agent) > 300:
        raise ValueError("INVALID_NATIVE_AGENT_ID")
    if not (root / ("native-" + role + ".reserved.json")).exists():
        raise ValueError("NATIVE_DISPATCH_NOT_RESERVED")
    if role == "reviewer":
        prior = json.loads((root / "worker-dispatch.json").read_text())
        if agent == prior["agent"]:
            raise ValueError("NATIVE_AGENT_REUSED")
    result = dict(
        status="DISPATCH_RECORDED",
        role=role,
        agent=agent,
        requested_model=model,
        recorded_tool_selection=model,
        observed_backend_model=None,
        identity_basis="Operator-recorded native tool arguments and returned canonical agent ID",
    )
    save(root, role + "-dispatch.json", result)
    return result


def worker_complete(directory, result_path):
    root, m, originals = load(directory)
    if not (root / "worker-dispatch.json").exists():
        raise ValueError("MISSING_NATIVE_WORKER_DISPATCH")
    if (root / "native-reviewer.reserved.json").exists():
        raise ValueError("NATIVE_WRITES_FROZEN")
    Journal(root).reserve("native-checks")
    text = Path(result_path).read_text()
    (root / "worker-result.txt").write_text(text)
    record = _record(text, "TASKROUTE_RESULT:")
    if (
        set(record) != {"status", "reason"}
        or record["status"] != "READY_FOR_LEAD"
        or not isinstance(record["reason"], str)
        or not record["reason"].strip()
    ):
        raise ValueError("NATIVE_WORKER_BLOCKED_OR_INVALID")
    bodies = repository.snapshot(m, originals)
    if m.get("check_environment"):
        worker_checks = json.loads((Path(m["workspace"]) / "checks.json").read_text())
        if worker_checks.get("status") != "PASS" or worker_checks.get("file_hashes") != {
            n: repository.digest(b) for n, b in bodies.items()
        }:
            raise ValueError("NATIVE_WORKER_CHECKS_UNAVAILABLE")
    checks = repository.execute(root, m, bodies, "native-check")
    if any(c["exit_code"] != 0 for c in checks):
        raise ValueError("NATIVE_CHECKS_FAILED")
    if repository.snapshot(m, originals) != bodies:
        raise ValueError("CANDIDATE_CHANGED_DURING_CHECKS")
    result = dict(
        status="PASS",
        checks=checks,
        file_hashes={n: repository.digest(b) for n, b in bodies.items()},
    )
    save(root, "native-checks.json", result)
    review_space = root / "review-workspace"
    review_space.mkdir()
    for n, body in bodies.items():
        p = review_space / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode())
    (review_space / "TASK.md").write_text(task_text(m))
    save(review_space, "checks.json", result)
    prompt = (
        task_text(m)
        + "\n"
        + review_instruction(m)
        + "\nFresh independent read-only review in "
        + str(review_space)
        + ". Inspect all candidate files and checks.json. Candidate hashes: "
        + json.dumps(result["file_hashes"])
        + ". Assess declared checks' adequacy and original input/newline semantics. No edits, children, other models, network, install/auth, commits or retries. Host ran checks; do not claim your own execution. Emit one complete report; stop on negative/unknown findings."
    )
    (root / "reviewer-prompt.txt").write_text(prompt)
    return dict(
        status="CANDIDATE_FROZEN",
        **{k: v for k, v in result.items() if k != "status"},
        reviewer_workspace=str(review_space),
    )


EVIDENCE_FILES = (
    "manifest.json",
    "originals.json",
    "native-checks.json",
    "worker-dispatch.json",
    "reviewer-dispatch.json",
    "worker-result.txt",
    "reviewer-result.txt",
    "worker-prompt.txt",
    "reviewer-prompt.txt",
)


def evidence_hashes(root):
    return {
        name: repository.digest((root / name).read_bytes().decode("utf-8"))
        for name in EVIDENCE_FILES
    }


def validate_review_copy(root, m, bodies, checks):
    review_space = root / "review-workspace"
    expected = {**bodies, "TASK.md": task_text(m), "checks.json": json.dumps(checks, indent=2)}
    actual = {
        str(p.relative_to(review_space)): p.read_bytes().decode()
        for p in review_space.rglob("*")
        if p.is_file()
    }
    if any(p.is_symlink() for p in review_space.rglob("*")) or actual != expected:
        raise ValueError("NATIVE_REVIEW_COPY_CHANGED")


def candidate_diff(originals, bodies):
    return "".join(
        "".join(
            difflib.unified_diff(
                originals.get(n, "").splitlines(True),
                bodies[n].splitlines(True),
                fromfile=n + " (original)",
                tofile=n,
            )
        )
        for n in sorted(bodies)
    )


def finish(directory, result_path):
    root, m, originals = load(directory)
    dispatches = {
        role: json.loads((root / (role + "-dispatch.json")).read_text()) for role in PROFILES
    }
    if dispatches["worker"]["agent"] == dispatches["reviewer"]["agent"]:
        raise ValueError("NATIVE_AGENT_REUSED")
    Journal(root).reserve("native-finish")
    bodies, checks = frozen(root, m, originals)
    validate_review_copy(root, m, bodies, checks)
    review = Path(result_path).read_text()
    (root / "reviewer-result.txt").write_text(review)
    outcome = assess(m, review, (root / "worker-result.txt").read_text(), bodies)
    diff = candidate_diff(originals, bodies)
    result = dict(
        diff=diff,
        evidence_root=str(root),
        status="BLOCKED" if outcome["reasons"] else "READY_FOR_LEAD_REVIEW",
        route="codex-native",
        selection_reason=m.get("selection_reason", "unknown"),
        assessment=outcome,
        dispatches=dispatches,
        file_hashes=checks["file_hashes"],
        checks=checks["checks"],
        evidence_hashes=evidence_hashes(root),
        actual_charge=None,
        subscription_quota=None,
        token_usage=None,
        backend_model=None,
        limitations=[
            "Native dispatch selection is recorded, not backend attestation",
            "Fresh context and read-only roles rely on native tool orchestration plus hash checks",
            "Requires lead semantic acceptance; no canonical apply",
            "No replay or repair",
        ],
    )
    save(root, "native-receipt.json", result)
    return result


def receipt(directory):
    root, m, originals = load(directory)
    bodies, checks = frozen(root, m, originals)
    saved = json.loads((root / "native-receipt.json").read_text())
    reason = validate_selection_reason(saved.get("selection_reason", "unknown"))
    if reason != m.get("selection_reason", "unknown") or (
        "selection_reason" in m and "selection_reason" not in saved
    ):
        raise ValueError("NATIVE_RECEIPT_EVIDENCE_CHANGED")
    if saved.get("evidence_hashes") != evidence_hashes(root):
        raise ValueError("NATIVE_RECEIPT_EVIDENCE_CHANGED")
    validate_review_copy(root, m, bodies, checks)
    outcome = assess(
        m,
        (root / "reviewer-result.txt").read_text(),
        (root / "worker-result.txt").read_text(),
        bodies,
    )
    expected_status = "BLOCKED" if outcome["reasons"] else "READY_FOR_LEAD_REVIEW"
    if (
        saved.get("diff") != candidate_diff(originals, bodies)
        or saved.get("file_hashes") != checks["file_hashes"]
        or saved["status"] != expected_status
        or saved["assessment"] != outcome
        or saved["checks"] != checks["checks"]
        or saved["dispatches"]
        != {role: json.loads((root / (role + "-dispatch.json")).read_text()) for role in PROFILES}
    ):
        raise ValueError("NATIVE_RECEIPT_EVIDENCE_CHANGED")
    return dict(saved, selection_reason=reason)
