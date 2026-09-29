"""Trusted task verifier: inspect scope, then execute worker tests in OS sandbox."""

import ast
import hashlib
import json
import sys
from pathlib import Path

from runtime import bounded_check, unittest_script


def read_stats(path, process):
    if process["stop_reason"] is not None:
        raise ValueError(process["stop_reason"])
    if not path.is_file() or path.is_symlink():
        raise ValueError("MISSING_TEST_RESULT")
    try:
        stats = json.loads(path.read_text())
    except (ValueError, UnicodeError) as exc:
        raise ValueError("INVALID_TEST_RESULT") from exc
    fields = {"tests", "failures", "errors", "skips"}
    if (
        not isinstance(stats, dict)
        or set(stats) != fields
        or any(type(stats[k]) is not int or stats[k] < 0 for k in fields)
    ):
        raise ValueError("INVALID_TEST_RESULT")
    if stats["tests"] == 0 or stats["skips"] >= stats["tests"]:
        raise ValueError("NO_ACTIVE_TESTS")
    expected = int(bool(stats["failures"] or stats["errors"]))
    if process["returncode"] != expected:
        raise ValueError("TEST_EXIT_MISMATCH")
    return stats


def outside(source, function="normalize_session"):
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function]
    if len(nodes) != 1:
        raise ValueError("TARGET_FUNCTION_NOT_UNIQUE")
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    return (
        "".join(lines[: node.lineno - 1] + lines[node.end_lineno :]),
        ast.dump(node.args),
        ast.dump(node.returns) if node.returns is not None else None,
    )


def verify(root):
    ROOT = Path(root).resolve()
    M = json.loads((ROOT / "manifest.json").read_text())
    WORK = Path(M["workspace"])
    ORIGINALS = json.loads((ROOT / "originals.json").read_text())
    if M.get("mode") == "repository":
        from repository_task import verify as verify_repository

        return verify_repository(ROOT, M, ORIGINALS)
    previous = sorted(ROOT.glob("check-receipt-*.json"))
    if len(previous) >= M["max_checks"]:
        raise ValueError("CHECK_CEILING")
    number = len(previous) + 1
    reservation = ROOT / f"check-receipt-{number}.json"
    with reservation.open("x") as stream:
        json.dump({"status": "RESERVED"}, stream)
    source = (WORK / M["target"]).read_text()
    function = M.get("target_function", "normalize_session")
    if not (outside(source, function) == outside(ORIGINALS[M["target"]], function)):
        raise ValueError("OUTSIDE_FUNCTION_CHANGE")
    for name, original in ORIGINALS.items():
        path = WORK / name
        if not (path.is_file() and (not path.is_symlink())):
            raise ValueError("MISSING_OR_SYMLINK_SOURCE")
        if name != M["target"]:
            if not (path.read_text() == original):
                raise ValueError("READ_ONLY_SOURCE_CHANGED")
    allowed = {*ORIGINALS, M["test_target"], "TASK.md", "checks.json"}
    if not (
        all(
            not p.is_symlink() and (not p.is_file() or str(p.relative_to(WORK)) in allowed)
            for p in WORK.rglob("*")
        )
    ):
        raise ValueError("UNDECLARED_FILE")
    test = (WORK / M["test_target"]).read_text()
    checks = {}
    for label, code, pattern in [
        ("original", ORIGINALS[M["target"]], Path(M["test_target"]).name),
        ("candidate", source, M.get("test_pattern", "test_claude_accounting*.py")),
    ]:
        copy = ROOT / "scratch" / f"check-{number}-{label}"
        copy.mkdir(parents=True)
        for name, body in {**ORIGINALS, M["target"]: code, M["test_target"]: test}.items():
            path = copy / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        stats_path = copy / "test-result.json"
        script = unittest_script(pattern, "test-result.json")
        command = [
            "/usr/bin/sandbox-exec",
            "-f",
            str(ROOT / "test.sb"),
            M["python"],
            "-B",
            "-c",
            script,
        ]
        result = bounded_check(command, copy, 30)
        (ROOT / f"check-{number}-{label}.log").write_text(result["feedback"])
        stats = read_stats(stats_path, result)
        for name, body in {**ORIGINALS, M["target"]: code, M["test_target"]: test}.items():
            if not ((copy / name).read_text() == body):
                raise ValueError("TEST_INPUT_MUTATED")
        checks[label] = {
            "stats": stats,
            "exit_code": result["returncode"],
            "stop_reason": result["stop_reason"],
            "summary": result["feedback"][-1800:],
        }
    success = (
        checks["original"]["exit_code"] == 1
        and checks["candidate"]["exit_code"] == 0
        and all(x["stop_reason"] is None for x in checks.values())
    )
    result = {
        "status": "PASS" if success else "FAIL",
        "checks": checks,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "test_sha256": hashlib.sha256(test.encode()).hexdigest(),
    }
    reservation.write_text(json.dumps(result, indent=2))
    (WORK / "checks.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    return 0 if success else 1


def main():
    root = Path(sys.argv[1]).resolve()
    try:
        return verify(root)
    except Exception as exc:
        result = {"status": "BLOCKED", "reason": str(exc), "error_type": type(exc).__name__}
        # Preserve the reserved attempt and any partial logs; do not retry.
        (root / "verifier-error.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        return 2


if __name__ == "__main__":
    sys.exit(main())
