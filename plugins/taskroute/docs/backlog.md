# Local failure backlog

Capture-only MVP. The database defaults to `~/.local/state/taskroute/backlog.sqlite3`,
shared across projects and installed versions. Override with `TASKROUTE_BACKLOG_DB`
or `backlog.py --db PATH`. No service, model call, auto-fix or external publication.
The first actual record creates the database. An empty list does not create it.

```sh
python3 -B scripts/backlog.py list
python3 -B scripts/backlog.py show review.false-approval
python3 -B scripts/backlog.py record occurrence.json
```

Minimal occurrence (every field required; `task_id` may be null when unknown):

```json
{
  "issue_key": "review.false-approval",
  "project_id": "project-01",
  "task_id": "root-task-01",
  "run_id": "run-02",
  "event_id": "lead-acceptance",
  "stage": "lead",
  "severity": "high",
  "expected": "preserve-valid-inputs",
  "observed": "over-rejection",
  "evidence": "lead-acceptance.json",
  "version": "0.2.0"
}
```

Only short identifiers/codes are accepted, not paths, source, prompts or raw logs.
Use opaque IDs, not personal or customer names; syntax validation cannot recognize
all sensitive strings. Keep the input record next to the local evidence. The database
stores its relative artifact name and run ID, not an absolute private path.

`prepare --project-id ID --task-id ID` supplies stable correlation. Without these,
project identity is a hash of the source path and task identity stays unknown;
independent task counts exclude unknowns. Explicit IDs are necessary to aggregate
multiple checkouts/copies as one project and retries as one root task.

Runner completion records terminal blockers and recovered FORMAT_CORRECTION events,
including when final delivery succeeds. CLI `capture RUN PACKET_JSON` can replay
receipts without invoking a model. Each run retains `backlog-capture.json`; returned
packets include its status. NOT_SAVED is visible and never changes task acceptance.
Preparation failures before a manifest, abrupt process death and arbitrary worker
mistakes are not automatically captured in this first version. Semantic lead findings
use the record command. Automatic signals are observations for triage, not proof
that TaskRoute caused the failure. Raw error text is never copied into the registry.

Unique event identity is project + run + stage + event ID. Repeating the same payload
is idempotent; changing its group/content gives a conflict instead of silent merging.
Same issue key groups observations; semantic deduplication is deliberate, not inferred
from similar wording. Different runs of one task add episodes but not independent tasks.
Sort order: severity (critical/high/medium/low), independent tasks, projects, recency.
Frequency is not failure rate; no denominator is inferred. There is no automatic
merge, repair, resolution workflow, retention purge or cross-machine sync in the MVP.
Records remain available for later triage, including after a workaround or known fix.
