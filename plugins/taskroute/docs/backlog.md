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
Preparation and local preflight blockers are also captured before a manifest;
see below. Abrupt process death and arbitrary worker mistakes are not automatically
captured. Semantic lead findings
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

## Preparation and preflight failures

The shared `prepare` API and the `prepare`/`deliver` CLI record local preparation
errors automatically. CLI `native-prepare` and manifest-free `preflight` use the
same capture. A blocker stays `BLOCKED`, with `model_calls=0`, no retry and a
separate `backlog.status` of `SAVED` or `NOT_SAVED`. The API still raises its
original exception; its `taskroute_failure` attribute carries that receipt.

Capture requires neither a manifest nor a runner directory. Sanitized immutable
evidence lives in `DB_PATH.evidence/preparation-EVENT_KEY.json`; the registry
stores codes and its filename. It never stores source bytes, prompts, raw
exception text or absolute paths. Unicode decoding errors have the stable code
`NON_UTF8_INPUT`. Invalid JSON, missing inputs and other local errors have bounded
codes; these are triage observations, not confirmed TaskRoute defects.

Explicit project/task IDs are preserved when valid. Otherwise project identity
is derived from the project path and task identity stays unknown. Manifest-free
`preflight` has no project context and records `project_id=unknown`, `task_id=null`.
Run identity is the hash of the requested path, not evidence that a run exists.
Existing runner directories remain untouched by manifest-free capture.

One event identity is project + requested run + stage + `blocked`. Exact replay
is idempotent; changed codes or evidence return `NOT_SAVED` without overwriting
the original. Concurrent identical captures publish one complete private file
and one occurrence. Evidence is retained if the database save fails, allowing
an explicit exact replay. Evidence or database failure never replaces the
primary preparation error or grants automatic retry/repair authority.

Successful preparation creates no failure record. This capture does not add
binary inputs, dependency roots or browser execution capability. Installed
copies need their own authorized update before they gain the new behavior.

## Explicit feedback intake

Select a completed interaction and supply sanitized evidence yourself; no chat
hook or automatic semantic classification. Commands require an explicit database:

```sh
python3 -B scripts/taskroute.py feedback-ingest selected.json --db DISPOSABLE_DB
python3 -B scripts/taskroute.py feedback-show --db DISPOSABLE_DB
```

Input has exactly `project_id`, `task_id`, `run_id`, `event_id`, `completed` (true),
`provenance` (user/quote/unknown), `source` (reference/sha256), `message`, `result`,
`classification` (kind/basis/evidence), and `proposal`. IDs are opaque codes.
Classification kinds: correction/new_request/question/quoted_report/unknown;
basis: human/recorded. Classification is supplied evidence, not machine inference.
Source reference/hash is a supplied attestation of the original artifact, not a
claim that intake fetched or independently verified it. The sanitized research
example uses the current research file's actual hash and labels its paraphrase.

A proposal is null or has exactly problem/expected/target/repair/check/rollback,
all bounded nonempty text. State target `unknown` when causality is unproven.
Quote provenance overrides a correction label to quoted_report; unknown provenance
stays unknown. Ordinary questions/new requests/quotes/unknowns return
NOT_ACTIONABLE with no occurrence. A correction lacking a proposal returns UNKNOWN.
Every validated event keeps an immutable sidecar, including negative/unknown events,
so changed reclassification of the same identity conflicts. Only an evidenced
correction saves a backlog occurrence. Explicit reclassification needs a new event ID.

Details live in `DB_PATH.evidence/feedback-EVENT_KEY.json`, referenced by the
existing occurrence evidence field; the observed code binds its content hash.
No schema migration or second database. Replay matches the entire payload;
changed source, classification, proposal or grouping conflicts. A failed SQLite
save returns NOT_SAVED and keeps the sidecar so exact replay can recover. A sidecar
write failure blocks the command; never report SAVED. Inspection reports missing
or changed evidence as EVIDENCE_UNAVAILABLE. Never edit evidence in place.
These private local artifacts can contain selected text; sanitize before ingestion.
No proposal is applied, no instructions/memory/permissions edited, no model called.
