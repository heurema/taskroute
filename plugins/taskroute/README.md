# TaskRoute 0.1.0

A local Codex plugin for bounded Claude Code delivery: implement a Python function,
run tests, get a separate read-only review, then return a compact evidence packet
for Codex to accept. No daemon, API key setup, automatic apply, or automatic retry.

## Supported scope

- macOS with `sandbox-exec`, Python 3.11+, and an already installed/authenticated
  Claude Code CLI. The originating profile used Claude Code 2.1.283 and
  `claude-opus-5-5`, medium. Other CLI versions/models are not qualified by this release.
- One existing Python function in a declared `src/` file; stdlib-only unittest
  checks in `tests/`. The original behavior must fail the added worker tests.
- One coordinator, one separate reviewer, at most three verification attempts,
  12 parent turns and 600 seconds for Claude. No correction loop after review.
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
After authorizing delegation, this command starts the one reserved live attempt:

```sh
python3 -B scripts/taskroute.py run /tmp/taskroute-example
```

The command waits for completion and emits a bounded JSON packet. In a model tool
host, wait on the same process with up to 60-second yields; do not relaunch or poll
logs through repeated model turns. Review the diff, tests and full reviewer text.
The candidate remains under the run folder's `workspace`; no source changes are
applied to the project. Applying a reviewed candidate is a separate authorized step.

## Task specification

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

The suite replays two saved accepted artifacts through preparation, scope checks,
worker-test verification and independent acceptance: 45 receipt cases and 20
batch-planning cases, plus eight worker tests each. Transport/reviewer records in
these replay tests are explicitly synthetic: passing proves packaging behavior,
not a new live model evaluation. The two original live scenarios were accepted
before extraction. The packaged CLI has not received a new live provider test or
Codex installation test; those remain release limitations.

The implementation preserves reservations, no automatic retry, compact evidence,
independent checks and bounded waiting from the qualified local workflow. Public
fixtures contain code and tests, not private session logs. `RELEASE.json` records
file digests. Future updates should run this suite and preserve the 0.1.0 release
for rollback. Token savings are workload-dependent and are not guaranteed.
