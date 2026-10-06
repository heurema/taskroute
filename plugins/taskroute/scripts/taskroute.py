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

from runtime import check_policy

SCRIPTS = Path(__file__).resolve().parent


def preparation_failure(error, project, destination, *, stage="preparation", **context):
    from backlog import capture_preparation

    failure = dict(
        status="BLOCKED",
        stage=stage,
        primary="local_failure",
        reason=str(error),
        error_type=type(error).__name__,
        model_calls=0,
        automatic_retry=False,
        readiness="NOT_READY",
        observed_model=None,
        accepted_model=None,
        usage=None,
        backlog=capture_preparation(project, destination, error, stage=stage, **context),
    )
    error.taskroute_failure = failure
    return failure


def prepare(
    spec_path: str | Path,
    project: str | Path,
    destination: str | Path,
    *,
    route: str = "claude",
    observe: bool = False,
    probes: bool = False,
    review_repair: bool = False,
    max_checks: int | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
) -> dict:
    try:
        return _prepare(
            spec_path,
            project,
            destination,
            route=route,
            observe=observe,
            probes=probes,
            review_repair=review_repair,
            max_checks=max_checks,
            project_id=project_id,
            task_id=task_id,
        )
    except Exception as error:
        stage = getattr(error, "taskroute_stage", "preparation")
        failure = preparation_failure(
            error, project, destination, stage=stage, project_id=project_id, task_id=task_id
        )
        if stage == "preflight":
            try:
                for name in ("preflight.json", "packet-error.json"):
                    (Path(destination) / name).write_text(json.dumps(failure, indent=2))
            except OSError as write_error:
                failure["run_receipt"] = dict(
                    status="NOT_SAVED", error_type=type(write_error).__name__
                )
        raise


def _prepare(
    spec_path: str | Path,
    project: str | Path,
    destination: str | Path,
    *,
    route: str = "claude",
    observe: bool = False,
    probes: bool = False,
    review_repair: bool = False,
    max_checks: int | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
) -> dict:
    if route == "sol-astra":
        if max_checks is not None:
            raise ValueError("CODEX_UNSUPPORTED_CHECK_BUDGET")
        if observe or probes or review_repair or project_id or task_id:
            raise ValueError("CODEX_UNSUPPORTED_EXPERIMENTAL_OPTIONS")
        from codex_route import prepare as codex_prepare

        return codex_prepare(spec_path, project, destination)
    if route != "claude":
        raise ValueError("UNKNOWN_ROUTE")
    check_limit = 3 if max_checks is None else max_checks
    if type(check_limit) is not int or not 1 <= check_limit <= 3:
        raise ValueError("INVALID_CHECK_BUDGET: supported ceiling is 1..3")
    if review_repair and check_limit < 2:
        raise ValueError("REVIEW_REPAIR_REQUIRES_TWO_CHECK_BATCHES")
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
        originals = {name: (project / name).read_bytes().decode("utf-8") for name in spec["files"]}
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
        originals = {name: (project / name).read_bytes().decode("utf-8") for name in files}
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
        p.write_bytes(body.encode("utf-8"))

    def command(script):
        return shlex.join([sys.executable, "-B", str(SCRIPTS / script), str(r)])

    m = dict(
        spec,
        project_root=str(project),
        workspace=str(w),
        python=sys.executable,
        claude_binary=str(Path(binary).resolve()),
        max_checks=check_limit,
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
    if mode == "repository":
        m["review_evidence_required"] = True
    (r / "manifest.json").write_text(json.dumps(m, indent=2))
    (r / "originals.json").write_text(json.dumps(originals))
    from task_contract import COORDINATOR_INSTRUCTION, review_instruction, task_text

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
                "hooks": [
                    {
                        "type": "command",
                        "command": command("review_gate.py"),
                        "timeout": 10,
                    }
                ],
            }
        ]
    (r / "settings.json").write_text(json.dumps(settings))
    if mode == "repository":
        scope = "Only edit these declared paths: " + json.dumps(spec["writable_paths"])
        initial_reads = "Initially read TASK.md and existing declared source inputs: " + json.dumps(
            sorted(spec["files"])
        )
        evidence = (
            "After a PASS verifier batch, read the generated checks.json and candidate "
            "files; read optional writable paths only if created. Reviewer must also "
            "Read the exact review_evidence_path in checks.json. "
            "That host-generated immutable artifact contains writable originals (null for "
            "new files), the scoped diff, all baseline/candidate hashes and passing checks. "
            "Compare it with candidate source to assess preservation and scope; it is "
            "integrity evidence, not semantic acceptance or a future full-suite result. "
            "The coordinator must give that exact path to the reviewer."
        )
        scope += (
            ". Meet the contract and preserve all frozen checks. Declared commands: "
            + json.dumps(spec["checks"])
        )
    else:
        scope = f"Only edit {spec['target']}:{spec['target_function']} and {spec['test_target']}. Add exactly {spec['worker_test_methods']} unittest methods exposing the original behavior (at most 16 failures on original)."
        initial_reads = "Initially read TASK.md and existing declared source inputs: " + json.dumps(
            spec["files"]
        )
        evidence = f"After a PASS verifier batch, read checks.json, {spec['target']}, the created {spec['test_target']} and frozen tests."
    agents = {
        "reviewer": {
            "description": "Independent read-only task review.",
            "prompt": initial_reads
            + ". "
            + evidence
            + " Return APPROVE or CHANGES with evidence and limitations. No edits, shell or nested agents.",
            "tools": ["Read"],
            "model": "inherit",
            "maxTurns": 6,
        }
    }
    if mode == "repository":
        agents["reviewer"]["prompt"] += "\n" + review_instruction(spec)
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
        + "\n"
        + initial_reads
        + ". Do not read checks.json, review artifacts or nonexistent optional files before they are generated. "
        + "For requested changes, understand requirements/source, implement the changes, "
        + "then execute the acceptance check batch. Legitimate no-change tasks may check "
        + "without manufacturing edits.\n"
        + " Read only declared workspace files. No arbitrary shell commands; the only Bash command is:\n"
        + m["verify_command"]
        + f"\nAt most {m['max_checks']} verifier check batch(es); each batch runs all frozen declared checks. "
        + (
            "Single-check budget: after a FAIL acceptance check batch, no check rerun; stop BLOCKED. "
            if m["max_checks"] == 1
            else "Additional batches are available only for corrections authorized by the task or selected experimental mode, within the remaining budget. "
        )
        + "Check batches are separate from provider submissions; this limit grants no model retries or repair authority. Stop on harness/transport errors. When checks pass, launch exactly one foreground reviewer with Agent/Task subagent_type reviewer. Include the entire contract and exact evidence paths. "
        + evidence
        + " No nested agents. If review requests changes, stop BLOCKED. No writes after review begins. Return READY_FOR_LEAD or BLOCKED with checks/review/limitations. No installs, login, research, provider retries, canonical apply or external actions.\n"
    )
    if mode == "repository":
        prompt += (
            "\nRead all criteria and non-goals in TASK.md before working.\n"
            + COORDINATOR_INSTRUCTION
        )
    if observe:
        prompt += "\nObserver-only outcomes do not consume an acceptance check batch; the observer call/correction ceiling remains separate. Do not read checks.json after observer-only results before a check batch creates it.\n"
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
        prompt += f"\nOne author-owned review repair is permitted. If the first reviewer returns a complete CHANGES report, read its findings, correct only declared source, rerun ALL unchanged checks with the exact verifier within the remaining batch budget, then launch one fresh foreground reviewer with the full contract and prior findings. Never ask the reviewer to edit code. No second code repair after re-review; stop BLOCKED on another negative or malformed final report. At most two reviewer launches, one code-repair phase, {m['max_checks']} acceptance check batches total. No observer in this mode. A first APPROVE ends review: no extra reviewer or edits.\n"
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
    from check_environment import policy_options
    from check_environment import prepare as prepare_environment

    prepare_environment(r, m)
    (r / "test.sb").write_text(check_policy(w, r / "scratch", **policy_options(m)))
    (r / "preflight.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "version": "0.2.2",
                "meaning": "Local preparation only; no provider call or authority grant",
            }
        )
    )
    from compact_delivery_packet import preflight

    try:
        readiness = preflight(r)
    except Exception as exc:
        exc.taskroute_stage = "preflight"
        raise
    (r / "preflight.json").write_text(json.dumps(readiness, indent=2))
    return {"status": "PREPARED", "run": str(r), "model_calls": 0}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "stage":
        from stage import main as stage_main

        return stage_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("stage", help="Native stage routing, execution, acceptance and accounting")
    for action in ("prepare", "deliver"):
        p = sub.add_parser(action)
        p.add_argument("--route", choices=["claude", "sol-astra"], default="claude")
        p.add_argument("--receipt-only", action="store_true")
        p.add_argument(
            "--max-checks",
            type=int,
            choices=[1, 2, 3],
            help="Verifier batch ceiling, fixed before prompt rendering; default3",
        )
        p.add_argument("spec")
        p.add_argument("--project", required=True)
        p.add_argument("--run", required=True)
        p.add_argument(
            "--observe",
            action="store_true",
            help="Enable independent pre-check observation and one correction opportunity",
        )
        p.add_argument(
            "--probe",
            action="store_true",
            help="Experimental frozen executable observation",
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
    p = sub.add_parser("feedback-ingest")
    p.add_argument("item", type=Path)
    p.add_argument("--db", type=Path, required=True)
    p = sub.add_parser("feedback-show")
    p.add_argument("--db", type=Path, required=True)
    from native_route import SELECTION_REASONS

    p = sub.add_parser("native-prepare", help="Prepare a Codex-native task; no model call")
    p.add_argument("spec")
    p.add_argument("--project", required=True)
    p.add_argument("--run", required=True)
    p.add_argument(
        "--selection-reason",
        choices=SELECTION_REASONS,
        default="unknown",
        help="Bounded operator reason for native selection; not quality evidence",
    )
    for action in ("reserve", "dispatch", "worker-complete", "finish", "receipt"):
        p = sub.add_parser("native-" + action)
        p.add_argument("directory")
        if action in ("reserve", "dispatch"):
            p.add_argument("role", choices=["worker", "reviewer"])
        if action == "dispatch":
            p.add_argument("--agent", required=True)
            p.add_argument("--model", required=True)
        if action in ("worker-complete", "finish"):
            p.add_argument("result")
    args = parser.parse_args()
    if args.action.startswith("native-"):
        import native_route

        action = args.action.removeprefix("native-")
        if action == "prepare":
            try:
                result = native_route.prepare(
                    args.spec, args.project, args.run, selection_reason=args.selection_reason
                )
            except Exception as error:
                preparation_failure(error, args.project, args.run)
                raise
        elif action == "dispatch":
            result = native_route.dispatch(args.directory, args.role, args.agent, args.model)
        elif action == "reserve":
            result = native_route.reserve(args.directory, args.role)
        elif action == "worker-complete":
            result = native_route.worker_complete(args.directory, args.result)
        elif action == "finish":
            result = native_route.finish(args.directory, args.result)
        else:
            result = native_route.receipt(args.directory)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result["status"] == "BLOCKED" else 0
    if args.action in ("feedback-ingest", "feedback-show"):
        from feedback import ingest, inspect

        result = (
            ingest(args.db, json.loads(args.item.read_text()))
            if args.action == "feedback-ingest"
            else inspect(args.db)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if isinstance(result, dict) and result.get("status") == "NOT_SAVED" else 0
    if args.action in ("run", "receipt", "preflight"):
        directory = Path(args.directory).resolve()
        try:
            manifest = json.loads((directory / "manifest.json").read_text())
        except Exception as error:
            if args.action == "preflight":
                preparation_failure(error, None, directory, stage="preflight")
            raise
        if manifest.get("route") == "sol-astra":
            from codex_route import load, run

            if args.action == "run":
                result = run(directory)
            elif args.action == "receipt":
                result = json.loads((directory / "codex-receipt.json").read_text())
            else:
                load(directory)
                result = dict(status="PREPARED", live_capability="UNVERIFIED", model_calls=0)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] in ("PREPARED", "READY_FOR_LEAD_REVIEW") else 2
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
            **({"route": args.route} if args.route != "claude" else {}),
            **({"max_checks": args.max_checks} if args.max_checks is not None else {}),
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
        if args.route == "sol-astra":
            from codex_route import run

            result = run(args.directory)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "READY_FOR_LEAD_REVIEW" else 2
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
        print(
            json.dumps(
                getattr(error, "taskroute_failure", {"status": "BLOCKED", "reason": str(error)})
            )
        )
        sys.exit(2)
