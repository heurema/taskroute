"""Language-neutral file contracts and bounded project checks for trusted code."""

import contextlib
import difflib
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from runtime import Journal, bounded_check, check_policy
from task_contract import assess, task_text, validate_contract

RESERVED = {"TASK.md", "checks.json", ".git"}


def digest(body):
    return hashlib.sha256(body.encode()).hexdigest()


def paths(values):
    if not isinstance(values, list) or len(values) != len(set(values)):
        raise ValueError("INVALID_PATH_LIST")
    for name in values:
        if not isinstance(name, str) or not name:
            raise ValueError("INVALID_RELATIVE_PATH")
        p = Path(name)
        if (
            p.is_absolute()
            or str(p) != name
            or ".." in p.parts
            or any(part in RESERVED for part in p.parts)
            or "\\" in name
        ):
            raise ValueError("INVALID_RELATIVE_PATH")
    return values


def validate(spec, project):
    """Validate before creating a run or executing any project command."""
    required = {
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
    }
    if not required <= set(spec) or not set(spec) <= required | {"check_environment"}:
        raise ValueError("INVALID_REPOSITORY_FIELDS")
    for field in ("contract", "model"):
        if not isinstance(spec[field], str) or not spec[field].strip():
            raise ValueError("INVALID_CONTRACT")
    if spec["permissions"] != {"network": False, "install": False}:
        raise ValueError("UNSUPPORTED_PERMISSIONS: offline checks; no dependency installation")
    inputs, writable = paths(spec["files"]), paths(spec["writable_paths"])
    if not inputs or not writable:
        raise ValueError("EMPTY_FILE_SCOPE")
    names = set(inputs) | set(writable)
    for name in names:
        p = project / name
        if any(x.is_symlink() for x in [p, *p.parents]):
            raise ValueError("SOURCE_SYMLINK")
        if not p.resolve().is_relative_to(project):
            raise ValueError("SOURCE_PATH_ESCAPE")
        if name not in inputs and p.exists():
            raise ValueError("EXISTING_WRITE_TARGET_NOT_INPUT")
        if any(Path(other) in Path(name).parents for other in names):
            raise ValueError("FILE_DIRECTORY_COLLISION")
    checks = spec["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("MISSING_CHECKS")
    normalized = []
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"name", "argv", "timeout_seconds"}:
            raise ValueError("INVALID_CHECK")
        name, argv, timeout = check["name"], check["argv"], check["timeout_seconds"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("INVALID_CHECK_NAME")
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(a, str) or not a or "\0" in a for a in argv)
        ):
            raise ValueError("INVALID_CHECK_ARGV")
        if type(timeout) is not int or not 1 <= timeout <= 120:
            raise ValueError("INVALID_CHECK_TIMEOUT")
        binary = shutil.which(argv[0])
        if not binary:
            raise ValueError("CHECK_TOOL_UNAVAILABLE: " + name)
        binary = Path(binary).resolve()
        if binary.is_relative_to(project):
            raise ValueError("CHECK_TOOL_INSIDE_PROJECT: use an external interpreter")
        normalized.append(
            dict(
                check,
                argv=[str(binary), *argv[1:]],
                executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            )
        )
    if sum(c["timeout_seconds"] for c in normalized) > 120:
        raise ValueError("CHECK_TIME_BUDGET_EXCEEDED")
    if len({c["name"] for c in normalized}) != len(normalized):
        raise ValueError("DUPLICATE_CHECK_NAME")
    validate_contract(spec)
    if "check_environment" in spec:
        from check_environment import validate as validate_environment

        spec = dict(
            spec,
            check_environment=validate_environment(spec["check_environment"], project, list(names)),
        )
    return dict(spec, checks=normalized)


def check_tools(m):
    from check_environment import verify

    verify(m)
    for check in m["checks"]:
        binary = Path(check["argv"][0])
        if (
            not os.access(binary, os.X_OK)
            or hashlib.sha256(binary.read_bytes()).hexdigest() != check["executable_sha256"]
        ):
            raise ValueError("CHECK_TOOL_CHANGED")


def snapshot(m, originals):
    w = Path(m["workspace"])
    allowed = set(originals) | set(m["writable_paths"]) | {"TASK.md", "checks.json"}
    for p in w.rglob("*"):
        if p.is_symlink() or (p.is_file() and str(p.relative_to(w)) not in allowed):
            raise ValueError("UNDECLARED_WORKSPACE_FILE")
    if (w / "TASK.md").read_text() != task_text(m):
        raise ValueError("CONTRACT_CHANGED")
    bodies = {}
    for name in set(originals) | set(m["writable_paths"]):
        p = w / name
        if p.exists():
            bodies[name] = p.read_bytes().decode("utf-8")
        elif name in originals:
            raise ValueError("SOURCE_DELETION_UNSUPPORTED")
    for name, body in originals.items():
        if name not in m["writable_paths"] and bodies[name] != body:
            raise ValueError("FROZEN_INPUT_CHANGED")
    for name, expected in m["canonical_source_hashes"].items():
        if hashlib.sha256((Path(m["project_root"]) / name).read_bytes()).hexdigest() != expected:
            raise ValueError("CANONICAL_SOURCE_CHANGED")
    for name in set(m["writable_paths"]) - set(originals):
        if (Path(m["project_root"]) / name).exists():
            raise ValueError("CANONICAL_NEW_PATH_CONFLICT")
    return bodies


def execute(root, m, bodies, label):
    """Each check gets a fresh disposable copy; outputs are never applied."""
    check_tools(m)
    from check_environment import (
        environment_values,
        executable_paths,
        install_copy,
        policy_options,
        verify_copy,
    )

    results = []
    for i, check in enumerate(m["checks"]):
        copy = root / "scratch" / f"{label}-{i}"
        copy.mkdir(parents=True)
        for name, body in bodies.items():
            p = copy / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body.encode("utf-8"))
        install_copy(root, m, copy)
        local_browser = bool((m.get("check_environment") or {}).get("loopback_ports"))
        temporary = (
            tempfile.TemporaryDirectory(prefix="tr-", dir="/private/tmp")
            if local_browser
            else contextlib.nullcontext(None)
        )
        with temporary as directory:
            policy = root / "test.sb"
            if directory:
                # Short, owned paths avoid the macOS Unix socket path length limit.
                policy = root / f"{label}-{i}.sb"
                policy.write_text(
                    check_policy(
                        Path(m["workspace"]),
                        root / "scratch",
                        **policy_options(m),
                        temporary_paths=[directory],
                    )
                )
            policy_sha256 = hashlib.sha256(policy.read_bytes()).hexdigest()
            proc = bounded_check(
                ["/usr/bin/sandbox-exec", "-f", str(policy), *check["argv"]],
                copy,
                check["timeout_seconds"],
                extra_paths=executable_paths(m),
                cache_environment=environment_values(m, copy),
                temporary_directory=directory,
            )
        (root / f"{label}-{i}.log").write_text(proc["feedback"])
        verify_copy(m, copy)
        for name, body in bodies.items():
            p = copy / name
            if p.is_symlink() or not p.is_file() or p.read_bytes() != body.encode("utf-8"):
                raise ValueError("CHECK_INPUT_MUTATED")
        results.append(
            dict(
                name=check["name"],
                argv=check["argv"],
                exit_code=proc["returncode"],
                stop_reason=proc["stop_reason"],
                policy_sha256=policy_sha256,
                summary=proc["feedback"][-1800:],
            )
        )
        if proc["stop_reason"]:
            raise ValueError(proc["stop_reason"])
    check_tools(m)
    return results


def scope_evidence(m, originals, bodies, checks):
    """Host-owned scope evidence, without copying unrelated baseline bodies."""
    baseline = {n: digest(b) for n, b in originals.items()}
    if baseline != m["source_hashes"]:
        raise ValueError("REVIEW_BASELINE_CHANGED")
    return dict(
        baseline_hashes=baseline,
        candidate_hashes={n: digest(b) for n, b in bodies.items()},
        writable_originals={n: originals.get(n) for n in m["writable_paths"]},
        changed_paths=sorted(n for n in bodies if bodies[n] != originals.get(n)),
        diff="".join(
            "".join(
                difflib.unified_diff(
                    originals.get(n, "").splitlines(True),
                    bodies[n].splitlines(True),
                    fromfile=n + " (original)",
                    tofile=n,
                )
            )
            for n in sorted(bodies)
        ),
        checks={k: checks[k] for k in ("status", "checks", "file_hashes")},
    )


def validate_scope_evidence(root, m, originals, bodies, checks):
    if not m.get("review_evidence_required"):
        return None
    receipts = sorted(root.glob("check-receipt-*.json"))
    if not receipts or json.loads(receipts[-1].read_text()) != checks:
        raise ValueError("REVIEW_CHECK_RECEIPT_MISMATCH")
    number = receipts[-1].stem.removeprefix("check-receipt-")
    path = root / f"review-evidence-{number}.json"
    if (
        checks.get("status") != "PASS"
        or checks.get("file_hashes") != {n: digest(b) for n, b in bodies.items()}
        or checks.get("review_evidence_path") != str(path)
        or path.is_symlink()
        or not path.is_file()
    ):
        raise ValueError("REVIEW_EVIDENCE_UNAVAILABLE_OR_STALE")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != checks.get("review_evidence_sha256") or json.loads(
        raw
    ) != scope_evidence(m, originals, bodies, checks):
        raise ValueError("REVIEW_EVIDENCE_CHANGED")
    return path


def verify(root, m, originals):
    if m.get("observer_enabled"):
        from observer import observe

        bodies = snapshot(m, originals)
        observation = observe(root, m, bodies)
        if snapshot(m, originals) != bodies:
            raise ValueError("CANDIDATE_CHANGED_DURING_OBSERVATION")
        if observation["outcome"]["verdict"] == "STOP":
            print(
                json.dumps(
                    dict(
                        status="OBSERVER_STOP",
                        observation=observation["outcome"],
                        remaining_observer_calls=m["max_observer_calls"] - observation["number"],
                        instruction="Correct within contract, then invoke the verifier; no tests or final review ran.",
                    )
                )
            )
            return 1
    previous = list(root.glob("check-receipt-*.json"))
    if len(previous) >= m["max_checks"]:
        raise ValueError("CHECK_CEILING")
    number = len(previous) + 1
    reservation = root / f"check-receipt-{number}.json"
    with reservation.open("x") as stream:
        json.dump({"status": "RESERVED"}, stream)
    bodies = snapshot(m, originals)
    checks = execute(root, m, bodies, f"check-{number}")
    if snapshot(m, originals) != bodies:
        raise ValueError("CANDIDATE_CHANGED_DURING_CHECKS")
    result = dict(
        status="PASS" if all(c["exit_code"] == 0 for c in checks) else "FAIL",
        checks=checks,
        file_hashes={n: digest(b) for n, b in bodies.items()},
    )
    if m.get("observer_enabled"):
        result["observer"] = {
            "fingerprint": observation["fingerprint"],
            "number": observation["number"],
            "outcome": observation["outcome"],
        }
    if result["status"] == "PASS" and m.get("review_evidence_required"):
        evidence = root / f"review-evidence-{number}.json"
        raw = json.dumps(scope_evidence(m, originals, bodies, result), indent=2).encode()
        with evidence.open("xb") as stream:
            stream.write(raw)
        result["review_evidence_path"] = str(evidence)
        result["review_evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    reservation.write_text(json.dumps(result, indent=2))
    (Path(m["workspace"]) / "checks.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


def collect(root):
    from compact_delivery_packet import review_evidence

    m = json.loads((root / "manifest.json").read_text())
    originals = json.loads((root / "originals.json").read_text())
    bodies = snapshot(m, originals)
    checks = json.loads((Path(m["workspace"]) / "checks.json").read_text())
    hashes = {n: digest(b) for n, b in bodies.items()}
    if checks.get("status") != "PASS" or checks.get("file_hashes") != hashes:
        raise ValueError("CHECK_HASH_MISMATCH")
    receipts = sorted(root.glob("check-receipt-*.json"))
    if not receipts or json.loads(receipts[-1].read_text()) != checks:
        raise ValueError("CHECK_RECEIPT_MISMATCH")
    validate_scope_evidence(root, m, originals, bodies, checks)
    from observer import receipts as observer_receipts
    from observer import require_clearance

    require_clearance(root, m, bodies)
    review, result = review_evidence(root, m)
    Journal(root).reserve("packet-acceptance", scope="All declared project checks")
    assessment = assess(m, review, result.get("result"), bodies)
    independent = [] if assessment["reasons"] else execute(root, m, bodies, "packet-acceptance")
    if any(c["exit_code"] != 0 for c in independent):
        raise ValueError("INDEPENDENT_ACCEPTANCE_FAILED")
    if snapshot(m, originals) != bodies:
        raise ValueError("CANDIDATE_CHANGED_DURING_CHECKS")
    diff = "".join(
        "".join(
            difflib.unified_diff(
                originals.get(n, "").splitlines(True),
                bodies.get(n, "").splitlines(True),
                fromfile=n + " (original)",
                tofile=n,
            )
        )
        for n in sorted(set(originals) | set(bodies))
    )
    packet = dict(
        status="NEEDS_LEAD_DECISION" if assessment["reasons"] else "READY_FOR_LEAD_REVIEW",
        **assessment,
        coordinator_text=result.get("result"),
        acceptance=m["acceptance"],
        non_goals=m["non_goals"],
        check_inputs=m["check_inputs"],
        mode="repository",
        observations=observer_receipts(root),
        contract=m["contract"],
        independent_checks=independent,
        worker_checks=checks["checks"],
        file_hashes=hashes,
        writable_paths=m["writable_paths"],
        diff=diff,
        reviewer_text=review,
        model_usage=result["modelUsage"],
        evidence_root=str(root),
        limitations=[
            "Checks passing is not semantic acceptance; review findings need lead assessment",
            "Trusted code only; offline macOS checks, no dependency installation",
            "No language qualification or subscription savings inferred from this receipt",
        ],
    )
    if (root / "return-context.json").exists():
        context = json.loads((root / "return-context.json").read_text())
        if any(digest(originals.get(n, "")) != h for n, h in context["baseline_hashes"].items()):
            raise ValueError("RETURN_BASELINE_MISMATCH")
        packet["return_context"] = context
    raw = json.dumps(packet, ensure_ascii=False, indent=2)
    if len(raw.encode()) > 48000:
        raise ValueError("PACKET_SIZE_CAP")
    (root / "acceptance-packet.json").write_text(raw)
    return packet
