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


def prepare(
    spec_path: str | Path,
    project: str | Path,
    destination: str | Path,
    *,
    observe: bool = False,
    probes: bool = False,
    review_repair: bool = False,
    project_id: str | None = None,
    task_id: str | None = None,
) -> dict:
    observe = observe or probes
    spec = json.loads(Path(spec_path).read_text())
    project = Path(project).resolve()
    destination = Path(destination).absolute()
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ValueError("UNSUPPORTED_PLATFORM: macOS sandbox-exec required")
    if destination.exists():
        raise ValueError("RUN_DIRECTORY_ALREADY_EXISTS")
    binary = shutil.which("claude")
    if not binary:
        raise ValueError("CLAUDE_NOT_INSTALLED")
    mode = spec.get("mode", "python-function")
    if mode == "repository":
        from repository_task import validate

        spec = validate(spec, project)
        originals = {name: (project / name).read_text() for name in spec["files"]}
    elif mode == "python-function":
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
            if (
                p.is_absolute()
                or ".." in p.parts
                or not p.parts
                or p.parts[0] not in ("src", "tests")
            ):
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
        if not isinstance(spec.get("model"), str) or not spec["model"].strip():
            raise ValueError("INVALID_MODEL")
        pattern = spec.get("test_pattern")
        if (
            not isinstance(pattern, str)
            or "/" in pattern
            or not fnmatch.fnmatch(Path(spec["test_target"]).name, pattern)
        ):
            raise ValueError("INVALID_TEST_PATTERN")
        if not any(
            n.startswith("tests/") and fnmatch.fnmatch(Path(n).name, pattern) for n in files
        ):
            raise ValueError("MISSING_FROZEN_TESTS")
        originals = {name: (project / name).read_text() for name in files}
        from verify_structured_flow import outside

        outside(originals[spec["target"]], spec["target_function"])
        ast.parse(originals[spec["target"]])
    else:
        raise ValueError("UNSUPPORTED_TASK_MODE")
    if observe and mode != "repository":
        raise ValueError("OBSERVER_REQUIRES_REPOSITORY_MODE")
    if review_repair and (mode != "repository" or observe):
        raise ValueError("REVIEW_REPAIR_REQUIRES_REPOSITORY_WITHOUT_OBSERVER")
    from backlog import TOKEN

    if any(value is not None and not TOKEN.fullmatch(value) for value in (project_id, task_id)):
        raise ValueError("INVALID_BACKLOG_ID")
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
    if observe:
        m.update(
            observer_enabled=True,
            observer_strategy="probes" if probes else "reading",
            review_gate_enabled=probes,
            max_observer_calls=2,
            observer_seconds=120,
            max_parent_turns=18,
            wall_seconds=900,
        )
    if review_repair:
        m.update(
            review_repair_enabled=True,
            review_gate_enabled=True,
            max_child_launches=2,
            max_parent_turns=24,
            wall_seconds=900,
        )
    m["backlog_context"] = {
        k: v for k, v in {"project_id": project_id, "task_id": task_id}.items() if v is not None
    }
    m["canonical_source_hashes"] = dict(m["source_hashes"])
    (r / "manifest.json").write_text(json.dumps(m, indent=2))
    (r / "originals.json").write_text(json.dumps(originals))
    from task_contract import COORDINATOR_INSTRUCTION, REVIEW_INSTRUCTION, task_text

    (w / "TASK.md").write_text(task_text(spec) if mode == "repository" else spec["contract"])
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
    if probes or review_repair:
        settings["hooks"]["SubagentStop"] = [
            {
                "matcher": "reviewer",
                "hooks": [{"type": "command", "command": command("review_gate.py"), "timeout": 10}],
            }
        ]
    (r / "settings.json").write_text(json.dumps(settings))
    if mode == "repository":
        scope = "Only edit these declared paths: " + json.dumps(spec["writable_paths"])
        evidence = "Read TASK.md, checks.json and all declared files: " + json.dumps(
            sorted(set(spec["files"]) | set(spec["writable_paths"]))
        )
        scope += (
            ". Meet the contract and preserve all frozen checks. Declared commands: "
            + json.dumps(spec["checks"])
        )
    else:
        scope = f"Only edit {spec['target']}:{spec['target_function']} and {spec['test_target']}. Add exactly {spec['worker_test_methods']} unittest methods exposing the original behavior (at most 16 failures on original)."
        evidence = f"Read TASK.md, {spec['target']}, {spec['test_target']}, frozen tests in tests/ and checks.json."
    agents = {
        "reviewer": {
            "description": "Independent read-only task review.",
            "prompt": evidence
            + " Return APPROVE or CHANGES with evidence and limitations. No edits, shell or nested agents.",
            "tools": ["Read"],
            "model": "inherit",
            "maxTurns": 6,
        }
    }
    if mode == "repository":
        agents["reviewer"]["prompt"] += "\n" + REVIEW_INSTRUCTION
    if probes or review_repair:
        agents["reviewer"]["maxTurns"] = 8
        agents["reviewer"]["prompt"] += (
            "\nA deterministic completion hook checks your structured report. If it blocks completion, provide one corrected complete JSON record, retaining truthful findings. This is formatting correction only; no new tools or code edits."
        )
    (r / "agents.json").write_text(json.dumps(agents))
    prompt = (
        spec["contract"]
        + "\n"
        + scope
        + " Read only declared workspace files. No arbitrary shell commands; the only Bash command is:\n"
        + m["verify_command"]
        + "\nAt most three checks; stop on harness/transport errors. When checks pass, launch exactly one foreground reviewer with Agent/Task subagent_type reviewer. Include the entire contract and exact workspace evidence paths. "
        + evidence
        + " No nested agents. If review requests changes, stop BLOCKED. No writes after review begins. Return READY_FOR_LEAD or BLOCKED with checks/review/limitations. No installs, login, research, retries, canonical apply or external actions.\n"
    )
    if mode == "repository":
        prompt += (
            "\nRead all criteria and non-goals in TASK.md before working.\n"
            + COORDINATOR_INSTRUCTION
        )
    if observe:
        prompt += "\nThe verifier includes a mandatory independent observer BEFORE tests. Its result carries the observer verdict. checks.json exists only AFTER verification; do not treat a pre-verification missing file as a hook failure. On OBSERVER_STOP, read its findings and correct the candidate within the SAME contract; do not hand this routine correction back to the owner. Then call the same verifier. At most two observer calls; one correction opportunity; unchanged snapshots reuse the verdict. On observer error/ceiling stop BLOCKED without retry. You may not bypass observation. Final review remains separate and starts only after observer CONTINUE plus passing tests. No edits after final review.\n"
    if probes:
        prompt += "\nObservation runs a frozen independent executable probe harness in a disposable copy. It is generated once, never rewritten after your correction. Failures include actual execution evidence. Correct the implementation, not the probe or the contract. Probe UNKNOWN means untested, not a passed criterion; final reviewer must assess those gaps.\n"
    if probes:
        prompt += "\nReviewer completion is validated inside its session with at most one formatting correction. Do not accept an abbreviated report: every criterion and non-goal must be present. If the final report is still incomplete or negative, finish BLOCKED. No second reviewer."
    if review_repair:
        prompt = prompt.replace(
            "launch exactly one foreground reviewer",
            "launch one foreground reviewer for each permitted review round",
        )
        prompt = prompt.replace(
            "If review requests changes, stop BLOCKED. No writes after review begins.",
            "Writes are frozen while a reviewer runs and after final review.",
        )
        prompt = prompt.replace(
            "Stop BLOCKED if review requests changes, evidence is missing, or the task needs",
            "Stop BLOCKED if the final review requests changes, evidence is missing, or the task needs",
        )
        prompt += "\nOne author-owned review repair is permitted. If the first reviewer returns a complete CHANGES report, read its findings, correct only declared source, rerun ALL unchanged checks with the exact verifier, then launch one fresh foreground reviewer with the full contract and prior findings. Never ask the reviewer to edit code. No second code repair after re-review; stop BLOCKED on another negative or malformed final report. At most two reviewer launches, one code-repair phase, three verifier calls total. No observer in this mode. A first APPROVE ends review: no extra reviewer or edits.\n"
        agents["reviewer"]["prompt"] += (
            "\nchecks.json is a host-generated receipt: snapshot validation enforces frozen inputs unchanged from originals before checks. Assess its hashes and results as host integrity evidence; do not claim to have executed commands yourself. For a re-review independently inspect the whole current candidate and prior findings; previous approval never transfers across edits.\n"
        )
        (r / "agents.json").write_text(json.dumps(agents))
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
                "version": "0.2.0",
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
    for action in ("prepare", "deliver"):
        p = sub.add_parser(action)
        p.add_argument("--receipt-only", action="store_true")
        p.add_argument("spec")
        p.add_argument("--project", required=True)
        p.add_argument("--run", required=True)
        p.add_argument(
            "--observe",
            action="store_true",
            help="Enable independent pre-check observation and one correction opportunity",
        )
        p.add_argument(
            "--probe", action="store_true", help="Experimental frozen executable observation"
        )
        p.add_argument(
            "--review-repair",
            action="store_true",
            help="Experimental one author repair after independent review",
        )
        p.add_argument("--project-id", help="Stable opaque backlog project identifier")
        p.add_argument("--task-id", help="Root task identifier shared across retries")
    p = sub.add_parser("repair", help="One explicit lead return; no chat-history replay")
    p.add_argument("--receipt-only", action="store_true")
    p.add_argument("parent")
    p.add_argument("finding")
    p.add_argument("--run", required=True)
    for name in ["preflight", "run", "receipt"]:
        p = sub.add_parser(name)
        p.add_argument("directory")
        p.add_argument("--receipt-only", action="store_true")
    args = parser.parse_args()
    if args.action == "receipt":
        from delivery_receipt import receipt

        run = Path(args.directory).resolve()
        result = receipt(json.loads((run / "acceptance-packet.json").read_text()), run)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "CLAUDE_VERIFIED" else 2
    if args.action == "repair":
        from return_task import prepare_return

        args.directory = prepare_return(args.parent, args.finding, args.run)["run"]
    if args.action in ("prepare", "deliver"):
        prepared = prepare(
            args.spec,
            args.project,
            args.run,
            observe=args.observe,
            probes=args.probe,
            review_repair=args.review_repair,
            project_id=args.project_id,
            task_id=args.task_id,
        )
        if args.action == "prepare":
            print(json.dumps(prepared))
            return 0
        args.directory = prepared["run"]
    command = [
        sys.executable,
        "-B",
        str(SCRIPTS / "compact_delivery_packet.py"),
        str(Path(args.directory).resolve()),
        "--preflight" if args.action == "preflight" else "--launch",
    ]
    if args.receipt_only:
        command.append("--receipt-only")
    elif args.action in ("deliver", "repair"):
        command.append("--lead-view")
    return subprocess.run(command).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}))
        sys.exit(2)
