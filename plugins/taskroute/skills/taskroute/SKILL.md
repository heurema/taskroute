---
name: taskroute
description: Coordinate bounded repository delivery and collect local usage reports; use for Claude/Codex handoff, acceptance, historical metrics and selected corrections.
---

# TaskRoute

Use `scripts/taskroute.py` relative to the plugin root (`../..`). Reuse the approved
contract; agree missing scope/acceptance before dispatch. Checks are trusted inputs.
No installation, login, implicit model switch, automatic apply or publication.

For a request to coordinate an agreed implementation stage, the current lead owns
routing; do not ask the owner to classify small/large or choose a worker each time.
Use [native stage](../../docs/native-stage.md) for the new local stage workflow.
The packaged stage path is offline-tested, not live-qualified. Reading it does not
grant primary provider authority. For an already-authorized stage, confirmed Claude
unavailability uses the one native Sol6.1 child fallback in that procedure; the lead
handles the decision and records it. Unknown prior effects always stop.

For historical usage, weekly metrics or a savings report, use
[metrics collection](../../docs/metrics.md). It is a local read-only collector;
run it directly without a worker or model monitor. Do not infer accepted work or
subscription savings from counters. Installation does not schedule collection.

Choose the requested route before loading its procedure:

- **Native Codex / Sol with Astra:** use [native route](../../docs/native-route.md).
  It explicitly authorizes bounded child delegation as part of an owner-requested
  native task: one fresh Sol worker, then one fresh Astra reviewer, no nested child,
  repair or retry. The Python helper prepares/reserves/verifies; native collaboration
  tools launch roles. Model controls are recorded separately from backend UNKNOWN.
- **Claude (default):** deliver once with
  `deliver SPEC --project PROJECT --run FRESH_RUN --receipt-only`.
  For an authorized return use `repair PRIOR_RUN FINDING.json --run FRESH_RETURN
  --receipt-only`; read [return format](../../docs/lead-return.md) only to create a
  missing finding. Use the requested model or existing Opus medium profile.
  Claude owns implementation, checks and independent review. Wait on the same
  command/session; do not re-dispatch on timeout or repeatedly inspect logs.
- **Explicit CLI Sol/Astra experiment:** read [CLI contract](../../docs/sol-astra.md).
  This is live-blocked at missing model identity; native routing does not qualify it.
  Do not choose CLI as an implicit native fallback.
- **Selected feedback:** use `feedback-ingest`/`feedback-show` with explicit `--db`;
  read [backlog input](../../docs/backlog.md). Classification is human/recorded
  evidence and proposals never authorize model calls or instruction/memory changes.

For frontend/build/browser requirements, read [check environment](../../docs/frontend-checks.md)
while preparing the contract. Reuse existing dependencies and tools, declare required
local ports, and freeze the actual browser oracle. Do not enumerate binary dependency
files as UTF-8 source inputs or install missing tools. A build alone does not prove
browser behavior. Stop before model dispatch when required verification is unavailable.

Read the final receipt, ALL structured findings and limitations against intent.
CLAUDE_VERIFIED is delegated verification; native READY_FOR_LEAD_REVIEW needs lead
semantic acceptance. Neither an ended turn, passing checks nor reviewer APPROVE
waives a known violation. Missing or contradictory evidence blocks delivery.

Report the outcome, roles and artifact link. Unknown effects stop; no blind resend,
chat replay, automatic follow-up or silent attempt extension. Preserve original
checks on any separately authorized repair. No universal quality/savings claim.

Preparation/preflight blockers report backlog SAVED or NOT_SAVED even before a run
exists. Report NOT_SAVED; read backlog details only for an actual triage need.
Read [experimental modes](../../docs/experimental-modes.md) only when requested,
and [verification design](../../docs/verification-design.md) when defining checks.
Do not routinely load runner source or historical transcripts for a qualified path.
