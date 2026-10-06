# Explicit Sol/Astra CLI route

Status: live canary BLOCKED at CODEX_IDENTITY_UNKNOWN on 2026-10-04.
Use the separately requested [native route](native-route.md) inside Codex.

Opt-in local CLI adapter; Claude remains the default. Repository contracts and
frozen checks use the existing schema. Set spec `model` to `gpt-6.1-sol`; the
independent reviewer profile is `gpt-6-astra`, both medium. No model fallback.

```sh
python3 -B scripts/taskroute.py prepare task.json --project PROJECT --run FRESH_RUN --route sol-astra
# Only after separate authority for two product model calls:
python3 -B scripts/taskroute.py run FRESH_RUN --receipt-only
python3 -B scripts/taskroute.py receipt FRESH_RUN
```

`deliver ... --route sol-astra` combines prepare/run and has provider effects.
Preparation has zero model calls. Existing `repair`, observer/probe/review-repair
modes remain Claude-only; the new route has one worker, one reviewer and one host
check batch, with no code repair or resend. Extra rounds need a separately designed
contract. The old route's hooks and receipts are unchanged.

Codex `exec --ignore-user-config --ignore-rules --ephemeral` starts each role
fresh, with workspace-write for the author and read-only for the reviewer.
The environment strips key/model/endpoint overrides. Auth stays in the existing
Codex account; no credential issuance. The CLI sandbox is a workspace boundary,
not the Claude route's per-file tool hook. Trusted local tasks only; frozen-input
and scope violations are detected after worker execution and block review.
No hostile-code containment or successful transport qualification is claimed.

The host snapshots declared files, executes unchanged checks in disposable copies
under the existing offline macOS sandbox, and sends a copied frozen candidate,
criteria, hashes and check receipt to an independent session. Worker prose and
prior sessions are excluded from reviewer context. Source or review-copy mutation,
reused physical session, missing/negative/incomplete findings, wrong or unknown
model identity and uncertain submission stop the route. Reservations precede
provider effects; replay never resends. One deadline covers nonblocking prompt
submission, stdout capture and process wait, including pipe backpressure. Inspect `*-launch.json`, `*.jsonl`, role
receipts and `codex-receipt.json` for the primary failure.

Native `thread.started` may lack a model field. The adapter then records observed
and accepted model as null and returns CODEX_IDENTITY_UNKNOWN. Requested argv or
the assistant's model claim cannot fill this gap. The single live canary reached native turn.completed but thread.started provided
no model field. It stopped before checks or reviewer launch; actual worker model
and reviewer capability remain UNVERIFIED.
Software fixtures with explicit identity test the gate, not its live availability.
Usage, actual charge and subscription quota remain separate; unavailable is null.
READY_FOR_LEAD_REVIEW requires human semantic acceptance and never canonical apply.

## Consumed live canary

The prepared canary was run once and is consumed; do not resend it. Its original
recipe was `examples/repository/task.json` copied into disposable storage, changing only
`model` to `gpt-6.1-sol`; project is `examples/repository`. Freeze that spec and
source hashes, then prepare a fresh run as above. The exact launch argv/prompt
builder is `codex_route.argv`/`run`; the whole-route and role attempt reservations
are created durably before effects. Do not consume a live reservation during
preparation. Authority needed: at most one Sol worker and one Astra reviewer,
600 seconds each, no retry, no installation/login or canonical changes. Stop at
first failure, including missing model evidence; do not add an identity probe.
Success must show distinct native sessions, accepted identities, source-bound
passing checks and complete APPROVE. This implementation session and its Astra
code review do not constitute that product canary.
