> **Version 0.3.1 — October 6, 2026.** Local historical metrics collection is
> included alongside native delivery and availability fallback. Collect counters
> and quota observations without a model call; accepted work and causal savings
> remain unknown. See [metrics collection](docs/metrics.md).

# TaskRoute 0.3.1

A local Codex plugin for bounded Claude Code delivery: change declared project files,
run declared checks, get a separate read-only review, then return a compact evidence packet
for Codex to accept. No daemon, API key setup, automatic apply, or automatic retry.

Design decisions live in [delivery and verification principles](docs/verification-design.md):
complete bounded outcomes, independent evidence, author-owned corrections and
phase-appropriate reasoning. Proposed model combinations remain unqualified hypotheses.

## Supported scope

- macOS with `sandbox-exec`, Python 3.11+, and an already installed/authenticated
  Claude Code CLI. The originating profile used Claude Code 2.1.283 and
  `claude-opus-5-5`, medium. Other CLI versions/models are not qualified by this release.
- Repository mode: declared UTF-8 input and writable files, with frozen check commands.
  No language allowlist, function boundary, or required directory layout. Existing
  files can change and new files can be created; deletion and binary candidate files
  are not supported. Existing local dependency trees, including native binaries,
  can be copied into each isolated check through optional `check_environment`.
- Frontend checks: frozen dependencies, pinned runtime executables, disposable
  caches and explicitly declared loopback ports. External network and installation
  stay denied. See [frontend and browser checks](docs/frontend-checks.md).
- Legacy Python-function mode: one existing function under `src/`, stdlib unittest
  checks under `tests/`; original behavior must fail the added worker tests.
- One coordinator, one separate reviewer, at most three verification attempts,
  12 parent turns and 600 seconds for Claude in the base mode. No code correction
  loop after review in base mode; opt-in review-repair mode below permits one author
  correction. Experimental probe mode permits one reviewer-format correction.
- Tests are run with the qualified macOS policy and a stripped environment.
  This is for trusted project code, not a secure sandbox for hostile code.
- Session data and generated results stay in the caller-selected local run folder.
  Claude receives the declared code/contract using existing account access.

This is an experimental release of a narrowly verified workflow. It is not a
universal application builder or a semantic drift detector. Hooks restrict effects;
they do not prove that an action advances the user's intent. A completed process
or READY packet is not task acceptance. Counters are not subscription charges.

## Use in Codex

Load this directory as a local plugin through your Codex plugin installation flow.
The bundled `taskroute` skill explains when and how to invoke the scripts. This
repository does not install itself, change accounts or register a marketplace.
See https://developers.openai.com/codex/plugins for supported installation options.
The ordinary flow uses the skill; users do not need to memorize CLI commands.

## Script interface

No pip installation is required. Paths below are relative to this plugin root.

```sh
python3 -B scripts/taskroute.py prepare examples/task-batches/task.json \
  --project examples/task-batches --run /tmp/taskroute-example
python3 -B scripts/taskroute.py preflight /tmp/taskroute-example
```

Preparation and preflight make no model calls. Use a fresh run directory each time.
Preflight checks workspace write access, pinned test executables and a stdlib
read/write probe inside the existing macOS test boundary before any provider call.
Optional `check_environment` verifies declared local dependency trees and runtime
executables; only frozen loopback ports can be opened. Undeclared capabilities,
external network and installation are rejected. System runtime transitive dependencies
and provider auth/availability remain unverified.
A failed preparation records BLOCKED in preflight.json and packet-error.json.
The direct generated launcher rechecks readiness before reserving a provider attempt.
Failure receipts preserve the primary native reason and unknown identity/usage;
missing checks/review artifacts are secondary. Prior terminal receipts are preserved.
The launcher waits for process completion once; it does not poll provider status.
Provider instructions/hooks do not establish an OS sandbox or timeout equivalence.

After authorizing delegation, this command starts the one reserved live attempt:

```sh
python3 -B scripts/taskroute.py run /tmp/taskroute-example
```

The command waits for completion and emits a bounded JSON packet. In a model tool
host, wait on the same process with up to 60-second yields; do not relaunch or poll
logs through repeated model turns. Review the diff, tests and full reviewer text.
The candidate remains under the run folder's `workspace`; no source changes are
applied to the project. Applying a reviewed candidate is a separate authorized step.

## Repository task contract

`examples/repository/task.json` is a runnable, language-neutral file task. Codex
prepares the contract from the user's intent; users do not need to write JSON.

```json
{
  "mode": "repository",
  "contract": "Support the requested behavior while preserving compatibility.",
  "acceptance": [
    {"id": "AC1", "text": "The requested behavior works.", "evidence": ["check:project tests", "review"]}
  ],
  "non_goals": [{"id": "NG1", "text": "Do not change existing error messages."}],
  "check_inputs": ["app/main_test.go", "go.mod"],
  "files": ["app/main.go", "go.mod", "app/main_test.go"],
  "writable_paths": ["app/main.go", "app/helper.go"],
  "checks": [
    {"name": "project tests", "argv": ["go", "test", "./app"], "timeout_seconds": 60}
  ],
  "permissions": {"network": false, "install": false},
  "model": "claude-opus-5-5"
}
```

The Go command is an example, not a required toolchain. Use the actual project's
checks and existing tools. Acceptance may be tests, builds, linters or a scripted
artifact check. The lead must judge whether these prove the requested outcome.
A declared browser script can establish a specific DOM behavior in an existing
browser. Visual quality, arbitrary application delivery and model competence still
need their own evidence.

- `acceptance`: nonempty list of unique IDs, concrete criteria and required evidence
  references. References are `check:<declared name>`, `file:<declared path>`, or
  `review`. Every required reference must appear in the review findings. Referenced
  artifacts must exist. This validates coverage, not whether a claim is true.
- `non_goals`: explicit IDs and boundaries; an empty list is allowed when appropriate.
- `check_inputs`: explicit test/config/oracle inputs, a subset of `files` disjoint
  from `writable_paths`. Empty is allowed for checks with no project-side oracle.
  This does not discover dynamic dependencies. Writable source files may legitimately
  appear in check argv; the runner does not ban normal compiler/interpreter usage.
- `files`: explicit existing text files to copy. No directories/globs or symlinks.
- `writable_paths`: existing inputs allowed to change, plus optional new files.
  Everything else stays frozen. Keep acceptance tests/configs read-only; the runner
  cannot infer which files an arbitrary program consumes or whether checks are adequate.
- `checks`: named argv arrays, never shell strings. The executable is resolved and
  hashed at preparation. Each command gets a fresh copy, stripped environment,
  scratch-local HOME/TMPDIR and a timeout (1–120 seconds, 120 seconds total).
  A check needing build steps should use one reviewed script. Outputs stay in scratch.
- `permissions`: currently only offline execution without dependency installation.
  Other values fail before dispatch; this contract does not grant new authority.

Commands execute trusted project/worker code. Explicit argv is not a security sandbox:
interpreters and build scripts can execute other programs. The existing macOS policy
blocks network and constrains writes, but is not hostile-code isolation. PATH is minimal;
use available executable paths where necessary. Missing tools, dependencies or blocked
reads are capability failures, never a reason to silently loosen containment.

The complete acceptance contract is frozen in TASK.md. The coordinator runs checks
before requesting a separate reviewer; the gate requires passing receipts for the
current candidate. Collection retains both terminal outcomes and the complete diff.
Only complete positive findings proceed to independent re-execution of all checks.
Evidence remains bound to the candidate's file hashes.
Passing checks does not itself prove task completion. No mandatory red/green rule is
imposed on refactors or documentation work; regression checks should expose the defect.

## In-progress observer (experimental)

**Not qualified:** the first live historical replay missed a known violation. The
barrier and correction mechanics have offline coverage; successful live semantic
catch/correction has not been demonstrated. Enable only for an explicitly authorized
experiment. The evidence-handoff fix after that attempt is offline-tested only.

An alternative `prepare ... --probe` generates one frozen executable counterexample
harness, then runs the same harness on at most two candidate versions. It uses
Python stdlib to exercise the declared project tools; candidate language is unrestricted.
Generation is bounded to 120 seconds, each probe execution to 60 seconds. No regeneration
or repair after error. FAIL stops before declared checks; UNKNOWN remains untested.
Generation now targets one criterion with <=4000 characters of source. Unprobed
criteria remain UNKNOWN. After an initial generation timeout, a compact live replay
caught a known defect and the coordinator corrected it; the identical probe and
Go tests passed. Final delivery was rejected for incomplete reviewer JSON. This
alternative remains **NOT QUALIFIED** for routine full delivery; one controlled
catch/correction is not evidence of general or unseen detection reliability.

Use `prepare ... --observe` for a repository task to enable an independent
pre-check observer. Preparation is still offline. During `run`, the verifier
launches a fresh tools-disabled Claude context BEFORE executing declared checks.
It receives actual candidate file contents and the frozen criteria/non-goals,
not a coordinator summary. No constant model polling or observation per keystroke.

- `STOP` returns actionable criterion-bound findings to the coordinator. No tests
  or final review run. The coordinator can correct within the same contract and
  invoke verification again; the owner does not relay routine feedback.
- `CONTINUE` binds clearance to the current files, contract and check configuration.
  A changed candidate requires new observation. Identical snapshots reuse the
  recorded outcome without another model call.
- At most two observer calls (120 seconds each), one correction opportunity, one
  coordinator (900 seconds / 18 turns), three test attempts and one separate final
  reviewer. Final-review CHANGES still stops; there is no unlimited repair loop.
- Missing, malformed, wrong-model, unknown or timed-out observation fails closed;
  reserved calls cannot be silently retried. Observer findings do not grant scope
  expansion. Final review and collection require current CONTINUE clearance.

This is a discrete checkpoint during execution, before tests and final review,
not continuous semantic monitoring. A model may miss defects or produce false
alarms. The deterministic barrier enforces the verdict, not its semantic accuracy.
See the verification record for live qualification; offline fixtures alone do not
prove that an observer will discover a new deviation.

In probe mode, reviewer completion is checked inside its session. A malformed
positive report gets one formatting correction in the same agent; semantic negatives
still stop. Repeated malformed output is rejected by the collector. A subsequent controlled format-fault replay succeeded: the same reviewer corrected
its report, the collector and independent checks passed, and the review packet was
accepted. This qualifies known format recovery, not a fresh full implementation
route or general semantic supervision. A subsequent fresh integrated implementation completed the mechanism but was rejected
at final semantic acceptance: invalid root paths were silently normalized to valid
parents. Passing a narrow probe and review did not prove all criteria. Accepted full
delivery remains unqualified.

Acceptance quality depends on the oracle and input domain, not merely test count or
reviewer agreement. See [verification design](docs/verification-design.md) for
proportionate invariant, generated-input and targeted mutation checks. Use existing
frozen `check_inputs` and `checks`; no additional agent or testing framework is required.

## Outcomes and stop rules

The runner supplies exact response instructions to each role. The reviewer ends
with one `TASKROUTE_REVIEW:` line containing a JSON object:

```json
{"verdict":"APPROVE","acceptance":[{"id":"AC1","status":"MET","evidence":["check:project tests","review"],"detail":"Describe the actual check results and code reviewed."}],"non_goals":[{"id":"NG1","status":"KEPT","detail":"Describe the compatibility evidence."}]}
```

Every criterion appears exactly once. Criteria use `MET`, `NOT_MET` or `UNKNOWN`;
non-goals use `KEPT`, `BROKEN` or `UNKNOWN`. The overall verdict is `APPROVE` or
`CHANGES`. The coordinator ends with one `TASKROUTE_RESULT:` line:

```json
{"status":"READY_FOR_LEAD","reason":"All criteria have evidence and review approves."}
```

Use `BLOCKED` with a concrete reason if evidence is missing, review requests changes,
or work requires a different scope, command or permission. Do not silently change
the contract. Negative, malformed, duplicate or incomplete findings produce
`NEEDS_LEAD_DECISION`, retain evidence/reasons, skip redundant independent checks
and exit nonzero. Missing/failed transport or check-integrity evidence remains `BLOCKED`.
Only a positive complete packet can be `READY_FOR_LEAD_REVIEW`; Codex still decides
semantic acceptance. Acceptance does not automatically apply or publish the candidate.

Structured findings make omissions observable; they do not prove reviewer honesty
or understanding, adequate test coverage, or mid-execution semantic alignment.
The optional observer adds a discrete pre-check checkpoint, not a guarantee of semantic alignment.

## Legacy Python-function specification


`examples/task-batches/task.json` is a complete example. Required fields:

| Field | Meaning |
|---|---|
| `contract` | Outcome, exact behavior, boundaries and acceptance criteria |
| `files` | Explicit relative input files beneath `src/` or `tests/` |
| `target`, `target_function` | Existing production file and function allowed to change |
| `test_target` | New worker test file, not an existing input |
| `test_pattern` | unittest discovery pattern covering frozen and worker tests |
| `independent_test_count` | Expected frozen test method count |
| `worker_test_methods` | Required count of meaningful worker test methods |
| `model` | Exact installed/available Claude model identity to verify |

Do not include credentials, unrelated private files, or unreviewed test commands.
Preparation is a local prerequisite check, not provider availability validation.
Changing source inputs after preparation causes the launch to stop. Never reuse a
run after an unknown submission; preserve its evidence instead.

## Verification and provenance

```sh
python3 -B -m unittest discover -s tests
```

Legacy tests cover safety boundaries and replay two saved accepted artifacts through preparation, scope checks,
worker-test verification and independent acceptance: 45 receipt cases and 20
batch-planning cases, plus eight worker tests each. Transport/reviewer records in
these replay tests are explicitly synthetic: passing proves packaging behavior,
not a new live model evaluation. The two original live scenarios were accepted
before extraction. Installation and provider checks are separate from these offline tests; they
require an already authenticated local environment.

The implementation preserves reservations, no automatic retry, compact evidence,
independent checks and bounded waiting from the qualified local workflow. Public
fixtures contain code and tests, not private session logs. `RELEASE.json` records
file digests. Future updates should run this suite and preserve previous releases
for rollback. Token savings are workload-dependent and are not guaranteed.

## Bounded review repair (experimental)

For a repository task, `prepare ... --review-repair` permits one author-owned
correction after a complete negative first review. It cannot be combined with
`--observe` or `--probe` yet. It does not insert early checkpoints automatically.

The first review freezes edits while it runs. A well-formed negative report opens
one author repair phase. The author edits declared source, reruns all unchanged
checks, and requests a fresh independent read-only reviewer. Unchanged or unchecked
candidates cannot enter re-review. Previous approval never transfers across edits.
A first approval ends the route; no extra reviewer or edits. Malformed negative
reports, a second negative review, unknown effects or exhausted limits stop delivery.

Limits: one coordinator, two sequential reviewer launches, one repair phase,
three verifier calls, 24 parent turns, 900 seconds. Each reviewer may correct its
own report format once; it may never edit the implementation. The collector checks
native completion counts, edit timing, final review and candidate hashes before
independently rerunning checks. This mechanism does not prove semantic coverage.

## Local failure backlog

Delivery blockers and recovered review-format failures are recorded locally for
later triage; semantic lead findings can be added through the skill. No automatic
repair, model call or publication. Pass stable opaque `--project-id` and `--task-id`
at preparation to distinguish retries from independent tasks across projects.
See [backlog storage, commands and limits](docs/backlog.md).

### Existing approved contracts

Use `python3 scripts/taskroute.py deliver SPEC --project PROJECT --run FRESH_RUN`
to validate, prepare and execute once, returning one final evidence packet. Reuse
the spec rather than rewriting it. Existing `prepare` and `run` remain available.
The lead view omits echoed contract fields only; full review, findings, diff and
checks remain visible. The complete packet is retained in the run directory.
Follow the skill's single-script waiting pattern; host timeouts may still yield.

### Minimal lead work

Use `--receipt-only` on deliver, repair or run to return result, check statuses and
all structured review findings without source/diff or duplicated prose. Detailed
evidence stays in acceptance-packet.json. `receipt RUN` reads an existing packet
without launching models. CLAUDE_VERIFIED explicitly identifies delegated review,
not an independent Astra code-review verdict. Unknown or contradictory findings
require investigation; a short receipt cannot detect a reviewer lying about quality.
