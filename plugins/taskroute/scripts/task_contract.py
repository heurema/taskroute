"""Explicit acceptance criteria and fail-closed structured delivery findings."""

import json
import re

REVIEW_INSTRUCTION = """Finish with exactly one single-line TASKROUTE_REVIEW: JSON object:
{"verdict":"APPROVE|CHANGES","acceptance":[{"id":"AC1","status":"MET|NOT_MET|UNKNOWN","evidence":["check:name"],"detail":"Observed evidence, not just a claim"}],"non_goals":[{"id":"NG1","status":"KEPT|BROKEN|UNKNOWN","detail":"Evidence"}]}
Include every acceptance and non-goal ID exactly once. Evidence must include every
reference required by that criterion in TASK.md. Use UNKNOWN for missing evidence;
do not infer success from exit zero alone. Assess adequacy of the declared checks.
For compound criteria, account for each behavioral obligation in detail; a passing
narrow probe does not establish the whole criterion. Identify the independent oracle,
executed input domain and remaining gaps. Source-only findings must say so explicitly.
A known contradiction of a mandatory requirement is NOT_MET, never a non-blocking
risk you can waive. Only the owner may change requirements. Repairs must preserve
original-input semantics and pass unchanged regression/property checks.
Do not return APPROVE if any criterion is not MET or any non-goal is not KEPT."""
COORDINATOR_INSTRUCTION = """Finish with exactly one single-line TASKROUTE_RESULT: JSON object:
{"status":"READY_FOR_LEAD|BLOCKED","reason":"Evidence or the specific blocker"}.
Stop BLOCKED if review requests changes, evidence is missing, or the task needs
undeclared files, commands or permissions. Do not weaken the contract or checks.
Before coding, identify the important obligations and the declared evidence for each.
After correcting a defect, rerun all frozen checks; fixing its motivating example
alone is insufficient. Preserve original-input validity and meaning across transforms.
The author repairs code; independent review assesses it and cannot waive violations."""


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _items(rows, fields, required):
    if not isinstance(rows, list) or (required and not rows):
        raise ValueError("INVALID_CRITERIA")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("INVALID_CRITERION")
        identifier = row["id"]
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_-]{0,63}", identifier
        ):
            raise ValueError("INVALID_CRITERION_ID")
        if identifier in seen or not _text(row["text"]):
            raise ValueError("DUPLICATE_OR_EMPTY_CRITERION")
        seen.add(identifier)
    return seen


def validate_contract(spec):
    acceptance = _items(spec["acceptance"], {"id", "text", "evidence"}, True)
    non_goals = _items(spec["non_goals"], {"id", "text"}, False)
    if acceptance & non_goals:
        raise ValueError("DUPLICATE_CRITERION_ID")
    references = {"review"} | {"check:" + c["name"] for c in spec["checks"]}
    references |= {"file:" + n for n in set(spec["files"]) | set(spec["writable_paths"])}
    for criterion in spec["acceptance"]:
        refs = criterion["evidence"]
        if (
            not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or ref not in references for ref in refs)
            or len(refs) != len(set(refs))
        ):
            raise ValueError("INVALID_EVIDENCE_REFERENCE")
    frozen = spec["check_inputs"]
    if (
        not isinstance(frozen, list)
        or any(not isinstance(n, str) for n in frozen)
        or len(frozen) != len(set(frozen))
        or not set(frozen) <= set(spec["files"])
        or set(frozen) & set(spec["writable_paths"])
    ):
        raise ValueError("INVALID_FROZEN_CHECK_INPUTS")


def task_text(spec):
    fields = {k: spec[k] for k in ("acceptance", "non_goals", "check_inputs")}
    return (
        spec["contract"]
        + "\n\nAcceptance contract (frozen):\n"
        + json.dumps(fields, indent=2)
        + "\n"
    )


def _record(text, marker):
    if not isinstance(text, str):
        raise ValueError("MISSING_STRUCTURED_OUTCOME")
    lines = [line[len(marker) :].strip() for line in text.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise ValueError("MISSING_OR_DUPLICATE_STRUCTURED_OUTCOME")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_OUTCOME_KEY")
            result[key] = value
        return result

    value = json.loads(lines[0], object_pairs_hook=unique_keys)
    if not isinstance(value, dict):
        raise ValueError("INVALID_STRUCTURED_OUTCOME")
    return value


def _findings(rows, criteria, fields, states):
    if not isinstance(rows, list):
        raise ValueError("INVALID_FINDINGS")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("INVALID_FINDING")
        if not isinstance(row["id"], str) or row["id"] in result:
            raise ValueError("DUPLICATE_FINDING")
        if row["status"] not in states or not _text(row["detail"]):
            raise ValueError("INVALID_FINDING_STATUS_OR_DETAIL")
        result[row["id"]] = row
    if set(result) != {c["id"] for c in criteria}:
        raise ValueError("INCOMPLETE_FINDINGS")
    return result


def assess(spec, review_text, coordinator_text, bodies):
    """Validate claims and references, not their semantic truth."""
    reasons, review, coordinator = [], None, None
    try:
        coordinator = _record(coordinator_text, "TASKROUTE_RESULT:")
        if (
            set(coordinator) != {"status", "reason"}
            or coordinator["status"] not in ("READY_FOR_LEAD", "BLOCKED")
            or not _text(coordinator["reason"])
        ):
            raise ValueError("INVALID_COORDINATOR_OUTCOME")
        if coordinator["status"] == "BLOCKED":
            reasons.append("COORDINATOR_BLOCKED")
    except (ValueError, TypeError) as error:
        reasons.append(
            "COORDINATOR_OUTCOME_INVALID: "
            + (str(error) if type(error) is ValueError else type(error).__name__)
        )
    try:
        review = _record(review_text, "TASKROUTE_REVIEW:")
        if set(review) != {"verdict", "acceptance", "non_goals"} or review["verdict"] not in (
            "APPROVE",
            "CHANGES",
        ):
            raise ValueError("INVALID_REVIEW_VERDICT")
        ac = _findings(
            review["acceptance"],
            spec["acceptance"],
            {"id", "status", "evidence", "detail"},
            ("MET", "NOT_MET", "UNKNOWN"),
        )
        ng = _findings(
            review["non_goals"],
            spec["non_goals"],
            {"id", "status", "detail"},
            ("KEPT", "BROKEN", "UNKNOWN"),
        )
        if review["verdict"] != "APPROVE":
            reasons.append("REVIEW_REQUESTS_CHANGES")
        for criterion in spec["acceptance"]:
            row = ac[criterion["id"]]
            if row["status"] != "MET":
                reasons.append("CRITERION_NOT_MET: " + criterion["id"])
            refs = row["evidence"]
            if (
                not isinstance(refs, list)
                or any(not isinstance(ref, str) for ref in refs)
                or len(refs) != len(set(refs))
                or set(refs) != set(criterion["evidence"])
            ):
                reasons.append("EVIDENCE_INCOMPLETE: " + criterion["id"])
            for ref in criterion["evidence"]:
                if ref.startswith("file:") and ref[5:] not in bodies:
                    reasons.append("EVIDENCE_FILE_MISSING: " + criterion["id"])
        for identifier, row in ng.items():
            if row["status"] != "KEPT":
                reasons.append("NON_GOAL_NOT_KEPT: " + identifier)
    except (ValueError, TypeError, KeyError) as error:
        reasons.append(
            "REVIEW_OUTCOME_INVALID: "
            + (str(error) if type(error) is ValueError else type(error).__name__)
        )
    return dict(reasons=reasons, reviewer_outcome=review, coordinator_outcome=coordinator)
