"""Prepare or execute one isolated, bounded delivery. Python 3.11+, macOS."""

import argparse
import ast
import fnmatch
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def prepare(spec_path: str | Path, project: str | Path, destination: str | Path) -> dict:
    spec = json.loads(Path(spec_path).read_text())
    project = Path(project).resolve()
    destination = Path(destination).absolute()
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ValueError("UNSUPPORTED_PLATFORM: macOS sandbox-exec required")
    if destination.exists():
        raise ValueError("RUN_DIRECTORY_ALREADY_EXISTS")
    files = spec["files"]
    if (
        type(files) is not list
        or not files
        or any(type(n) is not str for n in files)
        or len(files) != len(set(files))
    ):
        raise ValueError("INVALID_FILES")
    for name in [*files, spec["test_target"]]:
        p = Path(name)
        if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] not in ("src", "tests"):
            raise ValueError("INVALID_RELATIVE_PATH")
        if not (project / p).resolve().is_relative_to(project):
            raise ValueError("SOURCE_PATH_ESCAPE")
    if (
        spec["target"] not in files
        or spec["test_target"] in files
        or (project / spec["test_target"]).exists()
    ):
        raise ValueError("INVALID_EDIT_TARGETS")
    for field in ["independent_test_count", "worker_test_methods"]:
        if type(spec[field]) is not int or spec[field] < 1:
            raise ValueError("INVALID_TEST_COUNT")
    if not spec["target_function"].isidentifier() or not spec["contract"].strip():
        raise ValueError("INVALID_CONTRACT")
    binary = shutil.which("claude")
    if not binary:
        raise ValueError("CLAUDE_NOT_INSTALLED")
    if not isinstance(spec.get("model"), str) or not spec["model"].strip():
        raise ValueError("INVALID_MODEL")
    pattern = spec.get("test_pattern")
    if (
        not isinstance(pattern, str)
        or "/" in pattern
        or not fnmatch.fnmatch(Path(spec["test_target"]).name, pattern)
    ):
        raise ValueError("INVALID_TEST_PATTERN")
    if not any(n.startswith("tests/") and fnmatch.fnmatch(Path(n).name, pattern) for n in files):
        raise ValueError("MISSING_FROZEN_TESTS")
    originals = {name: (project / name).read_text() for name in files}
    from verify_structured_flow import outside

    outside(originals[spec["target"]], spec["target_function"])
    ast.parse(originals[spec["target"]])
    destination.mkdir(parents=True)
    r = destination.resolve()
    w = r / "workspace"
    w.mkdir()
    (r / "scratch").mkdir()
    for name, body in originals.items():
        p = w / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)

    def command(script):
        return shlex.join([sys.executable, "-B", str(SCRIPTS / script), str(r)])

    m = dict(
        spec,
        project_root=str(project),
        workspace=str(w),
        python=sys.executable,
        claude_binary=str(Path(binary).resolve()),
        max_checks=3,
        max_parent_turns=12,
        max_child_launches=1,
        wall_seconds=600,
        effort="medium",
        verify_command=command("verify_structured_flow.py"),
        source_hashes={n: hashlib.sha256(b.encode()).hexdigest() for n, b in originals.items()},
    )
    m["canonical_source_hashes"] = dict(m["source_hashes"])
    (r / "manifest.json").write_text(json.dumps(m, indent=2))
    (r / "originals.json").write_text(json.dumps(originals))
    (w / "TASK.md").write_text(spec["contract"])
    settings = {
        "autoMemoryEnabled": False,
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("guard_structured_flow.py"),
                            "timeout": 10,
                        }
                    ],
                }
            ]
        },
    }
    (r / "settings.json").write_text(json.dumps(settings))
    agents = {
        "reviewer": {
            "description": "Independent read-only task review.",
            "prompt": f"Read TASK.md, {spec['target']}, {spec['test_target']}, frozen tests in tests/ and {w / 'checks.json'}. Return APPROVE or CHANGES with evidence and limitations. No edits, shell or nested agents.",
            "tools": ["Read"],
            "model": "inherit",
            "maxTurns": 6,
        }
    }
    (r / "agents.json").write_text(json.dumps(agents))
    prompt = (
        spec["contract"]
        + f"\nOnly edit {spec['target']}:{spec['target_function']} and {spec['test_target']}. Read only declared workspace files. Add exactly {spec['worker_test_methods']} unittest methods exposing the original behavior (at most 16 failures on original). No arbitrary shell commands; the only Bash command is:\n{m['verify_command']}\nAt most three checks; stop on harness/transport errors. When checks pass, launch exactly one foreground reviewer with Agent/Task subagent_type reviewer. Include the entire contract and exact workspace evidence paths; frozen tests are in "
        + str(w / "tests")
        + ". No nested agents. If review requests changes, stop BLOCKED. No writes after review begins. Return READY_FOR_LEAD or BLOCKED with checks/review/limitations. No installs, login, research, retries, canonical apply or external actions.\n"
    )
    (r / "prompt.txt").write_text(prompt)
    template = (SCRIPTS / "launch_template.py").read_text()
    (r / "launch.py").write_text(
        "import sys\nsys.path.insert(0, " + repr(str(SCRIPTS)) + ")\n" + template
    )
    # Preserve the qualified macOS test boundary; no claim of hostile-code isolation.
    policy = '(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(deny file-read* (subpath "/Users"))\n'
    policy += (
        "(allow file-read* (subpath "
        + json.dumps(str(w))
        + ") (subpath "
        + json.dumps(str(r / "scratch"))
        + "))\n"
    )
    policy += (
        "(allow file-write* (subpath "
        + json.dumps(str(r / "scratch"))
        + ') (literal "/dev/null"))\n'
    )
    (r / "test.sb").write_text(policy)
    (r / "preflight.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "version": "0.1.1",
                "meaning": "Local preparation only; no provider call or authority grant",
            }
        )
    )
    from compact_delivery_packet import preflight

    preflight(r)
    return {"status": "PREPARED", "run": str(r), "model_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("spec")
    p.add_argument("--project", required=True)
    p.add_argument("--run", required=True)
    for name in ["preflight", "run"]:
        p = sub.add_parser(name)
        p.add_argument("directory")
    args = parser.parse_args()
    if args.action == "prepare":
        print(json.dumps(prepare(args.spec, args.project, args.run)))
        return 0
    command = [
        sys.executable,
        "-B",
        str(SCRIPTS / "compact_delivery_packet.py"),
        str(Path(args.directory).resolve()),
        "--preflight" if args.action == "preflight" else "--launch",
    ]
    return subprocess.run(command).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}))
        sys.exit(2)
