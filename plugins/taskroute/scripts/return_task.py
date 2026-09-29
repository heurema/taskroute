"""Prepare one explicit lead return from bound artifacts, without chat history."""

import hashlib
import json
from pathlib import Path

from repository_task import paths, validate
from runtime import Journal

FIELDS = (
    "mode",
    "contract",
    "files",
    "writable_paths",
    "checks",
    "model",
    "permissions",
    "acceptance",
    "non_goals",
    "check_inputs",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare_return(parent, finding_path, destination):
    from taskroute import prepare

    parent = Path(parent).resolve()
    destination = Path(destination).absolute()
    if destination.exists():
        raise ValueError("RETURN_DIRECTORY_EXISTS")
    if (parent / "return-context.json").exists():
        raise ValueError("RETURN_CEILING")
    manifest = json.loads((parent / "manifest.json").read_text())
    if manifest["mode"] != "repository":
        raise ValueError("RETURN_REQUIRES_REPOSITORY")
    if json.loads((parent / "terminal.json").read_text()).get("status") != "ENDED":
        raise ValueError("PARENT_NOT_ENDED")
    packet_bytes = (parent / "acceptance-packet.json").read_bytes()
    packet = json.loads(packet_bytes)
    hashes = packet.get("file_hashes", {})
    checked = json.loads((parent / "workspace/checks.json").read_text())
    if checked.get("status") != "PASS" or checked.get("file_hashes") != hashes:
        raise ValueError("PARENT_CHECK_BINDING_MISMATCH")
    if not set(hashes) <= set(manifest["files"]) | set(manifest["writable_paths"]):
        raise ValueError("PARENT_SCOPE_MISMATCH")
    finding_bytes = Path(finding_path).read_bytes()
    finding = json.loads(finding_bytes)
    required = {"criterion", "expected", "observed", "reproduction", "regression_files", "checks"}
    if set(finding) != required or any(
        not isinstance(finding[k], str) or not finding[k].strip()
        for k in ("criterion", "expected", "observed", "reproduction")
    ):
        raise ValueError("INVALID_RETURN_FINDING")
    if finding["criterion"] not in {c["id"] for c in manifest["acceptance"]}:
        raise ValueError("UNKNOWN_RETURN_CRITERION")
    regressions = finding["regression_files"]
    if (
        not isinstance(regressions, dict)
        or not regressions
        or not isinstance(finding["checks"], list)
    ):
        raise ValueError("RETURN_NEEDS_REGRESSION")
    paths(list(regressions))
    if any(not isinstance(v, str) for v in regressions.values()):
        raise ValueError("INVALID_REGRESSION_BODY")
    bodies = {}
    for name, expected in packet["file_hashes"].items():
        paths([name])
        path = parent / "workspace" / name
        if path.is_symlink() or not path.resolve().is_relative_to(parent / "workspace"):
            raise ValueError("PARENT_PATH_ESCAPE")
        data = path.read_bytes()
        if digest(data) != expected:
            raise ValueError("PARENT_CANDIDATE_CHANGED")
        bodies[name] = data.decode()
    if not set(manifest["files"]) <= set(bodies):
        raise ValueError("PARENT_FILES_MISSING")
    if set(regressions) & (set(bodies) | set(manifest["writable_paths"])):
        raise ValueError("RETURN_CANNOT_REPLACE_INPUTS")
    spec = {k: manifest[k] for k in FIELDS}
    spec["files"] = list(bodies) + list(regressions)
    spec["check_inputs"] = list(spec["check_inputs"]) + list(regressions)
    spec["checks"] = [
        {k: c[k] for k in ("name", "argv", "timeout_seconds")} for c in spec["checks"]
    ] + finding["checks"]
    notice = {k: finding[k] for k in ("criterion", "expected", "observed", "reproduction")}
    spec["contract"] += (
        "\n\nLead return: "
        + json.dumps(notice)
        + (
            "\nCorrect this known violation without narrowing the original contract. "
            "Run ALL original and added regression checks. Independent reviewer must "
            "explicitly assess the returned finding; a known violation is never APPROVE."
        )
    )
    spec["acceptance"] = [dict(c, evidence=list(c["evidence"])) for c in spec["acceptance"]]
    for criterion in spec["acceptance"]:
        if criterion["id"] == finding["criterion"]:
            criterion["evidence"] += ["check:" + c["name"] for c in finding["checks"]]
    # A single explicit return per parent, even if called with a different destination.
    Journal(parent).reserve("lead-return", finding_sha256=digest(finding_bytes))
    destination.mkdir(parents=True)
    source = destination / "source"
    source.mkdir()
    for name, body in {**bodies, **regressions}.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    validate(spec, source.resolve())
    spec_path = destination / "task.json"
    spec_path.write_text(json.dumps(spec, indent=2))
    context = dict(
        parent_packet_sha256=digest(packet_bytes),
        baseline_hashes=packet["file_hashes"],
        finding=notice,
        finding_sha256=digest(finding_bytes),
        review_scope="Full original contract; delta from rejected candidate",
    )
    (destination / "finding.json").write_bytes(finding_bytes)
    result = prepare(
        spec_path,
        source,
        destination / "delivery",
        review_repair=True,
        project_id=manifest.get("backlog_context", {}).get("project_id"),
        task_id=manifest.get("backlog_context", {}).get("task_id"),
    )
    run = Path(result["run"])
    (run / "return-context.json").write_text(json.dumps(context, indent=2))
    return result
