# Native stage workflow

The lead (Astra when selected by the owner) decides; the owner states the task.
There is no replacement coordinator model, learned router, daemon or LLM monitor.
This packaged implementation is offline-tested. It has not been qualified with a
live provider through this entrypoint. The previously accepted native fix predates this runner.

## Lead responsibilities

1. Read the current project checkpoint, applicable instructions and existing
   task/spec. Keep that source authoritative; no OpenSpec migration is required.
2. Record `routing` before implementation. `agreed=false` means discuss the missing
   decision. Unavailable required checks block implementation. Otherwise delegate
   a coherent agreed stage when handoff is worthwhile. Do an already-understood
   small correction directly when preparation/transfer is comparable to the work.
   State a concrete reason. These are coordinator judgments, not measured size
   thresholds or proof of savings. The owner does not fill these fields.
3. Prepare one contract and fresh run. Set exact requested model and permitted tools;
   do not infer a universal model. Use medium effort unless a hard decision needs more.
   Reuse project checks and include the actual browser oracle when relevant.
4. Before dispatch, verify explicit authority, exact project/source, CLI, writable
   scope and existing work. Preserve a usable baseline/backup of scoped files; do
   not assume a clean git HEAD. Record that preflight in the authority receipt.
   `--authority` records this already-established authority; writing it does not
   create permission. No global install, live trial or fifth browser attempt is
   authorized by this procedure.
5. Execute once and wait on the same process/session with a bounded wait. Do not
   read logs repeatedly, relaunch, or send status requests to another model. Code
   waits for exit and bounds time/output. Claude owns implementation/checks and
   at most one understood repair in this turn; no child or additional reviewer is
   launched by this first implementation. Consult only a consequential unresolved
   question under separate existing authority.
6. Inspect returned changes/check evidence once. `READY_FOR_ACCEPTANCE` means only
   transport/identity/permission checks passed. Independently decide every criterion;
   replay a focused check when evidence is insufficient. Record accepted/rejected
   with evidence paths, including changed files and check outputs. Unknown/failed
   runs stay in reports; no automatic repair or retry follows rejection.
7. Report result, remaining gaps, measured role usage and unknown quota/cost.
   The owner sees this compact result, not the contract/receipt management work.

## CLI

Use `python3 -B scripts/taskroute.py stage` from the plugin root. All preparation,
reporting, acceptance and observation commands are local. Only `run` can launch a
provider, with the exact CLI binary and authority receipt supplied by the lead.

```sh
python3 -B scripts/taskroute.py stage prepare CONTRACT.json --project PROJECT --run FRESH_RUN
python3 -B scripts/taskroute.py stage run FRESH_RUN --binary CLAUDE_BINARY --authority PREFLIGHT.txt
python3 -B scripts/taskroute.py stage accept FRESH_RUN REVIEW.json
python3 -B scripts/taskroute.py stage report FRESH_RUN
```

Contract fields (example values are not an authorization):

```json
{
  "task": "Fix the agreed batch cleanup defect",
  "source_ref": "existing project task or OpenSpec path",
  "scope": "Named implementation files and local check outputs only",
  "acceptance": ["Original reproduction passes; no weakened assertion"],
  "routing": {
    "agreed": true,
    "checks_available": true,
    "handoff_worthwhile": true,
    "reason": "One understood implementation stage with executable acceptance"
  },
  "model": "exact-owner-selected-model-id",
  "effort": "medium",
  "timeout_seconds": 900,
  "allowed_tools": ["Read", "Glob", "Grep", "Edit", "Write", "Bash(python3 -B check.py)"],
  "instructions": "Exact scope, non-goals, existing checks, permitted commands and evidence location"
}
```

The launcher uses a fresh safe-mode Claude print process, no resume/persistence,
no child tool, `dontAsk`, explicit tools and a sanitized environment. The permissions
and instructions are **not an OS sandbox**. `Edit`/`Write` tool allowances in this
example are broad: scope-specific policy and baseline inspection remain necessary.
Network/install/publication prohibitions are instructions; Bash can execute code.
Do not claim enforcement equivalent to the older isolated strict runner.

One project writer marker coordinates **only this stage entrypoint**. It cannot
exclude an editor, another chat or the legacy runner. Verify no external writer.
A lost parent or uncertain process creation leaves a marker and consumed attempt;
inspect original process/evidence, never remove it as an automatic recovery step.
Cancellation/timeout kills the known process group; a hard parent kill can leave
remote effects unknown. No session is resumed or blindly resent.

Acceptance file:

```json
{
  "verdict": "accepted",
  "reviewer": "lead identity",
  "reason": "Independent inspection and relevant check evidence",
  "criteria_met": ["Original reproduction passes; no weakened assertion"],
  "evidence": ["/absolute/changed-file", "/absolute/check-output"]
}
```

A rejected verdict does not require all criteria. Acceptance is an explicit lead
attestation, not an automated semantic verifier. Evidence hashes bind the recorded
verdict to those files; changed/deleted evidence invalidates its current report.

## Measurement without polling a model

Worker terminal JSON contributes observed model counters, elapsed time and
API-equivalent estimate even on a model/identity failure with readable output.
Never promote a rejected model to the accepted identity. Missing/malformed terminal
usage and interrupted calls remain unknown, never zero. Actual charge and
subscription debit are separate and unavailable unless separately evidenced.

For Codex, take compact local counter snapshots around the measured interval:

```sh
python3 -B scripts/taskroute.py stage snapshot EXACT_SESSION.jsonl /existing/path/before
python3 -B scripts/taskroute.py stage snapshot EXACT_SESSION.jsonl /existing/path/after
python3 -B scripts/taskroute.py stage measure RUN preparation /existing/path/before.reserved.json /existing/path/after.reserved.json
```

Only numeric counters, session identity, source path, timestamp and primary quota
window are retained; no messages or account balances. This importer supports the
observed `event_msg/token_count/info/total_token_usage` format. Other schemas fail
closed. A role interval must use the same physical session and monotone counters.
The final active turn may not have flushed: imported deltas are explicitly partial,
not full-route accounting. Shared-account quota snapshots cannot attribute a debit
to this stage, particularly with concurrent chats. No savings percentage is derived.

`observe RUN ROLE OBSERVATION.json` records one immutable observation per role:
preparation, direct_work, advice, review, acceptance, repair. Worker usage is derived.
Use `state: observed` with numeric `tokens` and `source`, `not_used` only when the
role really was absent, otherwise `unknown`. Optional `elapsed_seconds`,
`owner_minutes`, `actual_charge_usd`, `api_estimate_usd` remain separate. Never mark
an incomplete interval complete or count the same interval under two roles. Observed
role records are attestations; they do not independently prove accounting coverage.
`full_route_usage_complete` describes declared observation coverage, not billing
attribution or comparative benefit. A direct change still needs direct_work usage.

The final report always displays `savings: UNPROVEN`. Comparing accepted cohorts,
reliable closed-turn lead capture and live native qualification remain evidence gaps.
After updating the plugin, use a fresh chat to load its current instructions. Existing
chats can keep earlier loaded instructions; installation does not rewrite their context.


## Availability fallback: Claude -> native Sol 6.1

The lead handles this without asking the owner to pick a model each time. This
procedure authorizes one fresh native child for the fallback of an already-authorized
stage, with no nested delegation, resume, retry, second fallback or return to Claude.
It does not authorize a test generation merely to check availability.

Trigger only on confirmed quota exhaustion (including the five-hour window), empty
balance, service unavailability or a missing CLI before submission. A generic error,
network timeout, permission denial, unknown response or poor result is insufficient.
The lead inspects the primary terminal receipt and source files first. No pending
process/effects may remain. Preserve inspected partial work; never replay an uncertain
side effect. Confirmation is a lead attestation backed by saved evidence, not a
text classifier guessing from any occurrence of the word "limit".

1. Save availability JSON with `reason` (`quota_exhausted`, `balance_exhausted`,
   `service_unavailable`, `cli_unavailable`), `confirmed: true`, `prior_effects`
   (`none` or `inspected_partial_work`), `lead`, `assessment` and `evidence` (absolute
   paths). For a missing CLI before submission, also provide its absolute `binary`.
   Include the terminal response and inspected partial-work evidence in the assessment.
2. Run `stage fallback-reserve RUN EVIDENCE.json` before calling a native tool.
   Code checks primary terminal/evidence, excludes unknown/timeout paths, reserves
   the single fallback, retains a project writer marker and returns a compact prompt.
3. Read that prompt. Call native `spawn_agent` once with `model: gpt-6.1-sol`,
   `reasoning_effort: medium`, `fork_turns: none`; include the explicit project,
   scope, checks, prior effects and no-child restriction. Do not copy the full chat.
   If native tools/model selection are unavailable, stop. Do not substitute a CLI
   or another provider. A tool rejection still consumes the reserved attempt.
4. Record the returned canonical agent with
   `stage fallback-dispatched RUN --agent /root/ACTUAL_ID --model gpt-6.1-sol`.
   Wait on that child with bounded native waits; no progress-reading loop or extra
   model coordinator. The recorded tool selection is not observed backend identity.
5. Once the child ends, save its terminal output and a JSON receipt with `agent`,
   `ended: true`, `status: ready|blocked`, `summary` and `evidence` paths. Run
   `stage fallback-complete RUN RESULT.json`. Missing end evidence keeps the marker
   and unknown state. Inspect actual changed files/checks and use ordinary `stage
   accept` afterward. Ended/ready alone never accepts the task.

The report retains Claude usage and adds a distinct fallback state/model-selection
record. Native fallback tokens remain UNKNOWN until separately observed; backend
identity remains unavailable. Do not bill a recorded native selection as an observed
provider model, or treat the failed primary attempt as free.
