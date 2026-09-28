![TaskRoute — Delegate the work. Keep the verdict.](plugins/taskroute/assets/flow.svg)

# TaskRoute

**Let Claude handle a bounded coding task. Get back work Codex can verify.**

You and Codex agree on the outcome. Claude implements it, runs the tests, and
brings in a separate reviewer. Codex receives the actual diff, test evidence, and
complete review, then accepts the result or explains the blocker.

TaskRoute packages that handoff as a small, local **Codex plugin**.

## What comes back

- **The change:** an isolated candidate and its exact diff.
- **The checks:** worker tests plus a separate run of your frozen acceptance tests.
- **The review:** a separate read-only Claude agent's findings, in full.
- **The decision:** Codex's acceptance or a concrete blocker.

A run has explicit limits. An uncertain submission is never automatically resent.
Your original project is left intact; applying the accepted change stays a separate step.

<details>
<summary>See the flow in 13 seconds</summary>

![A condensed replay of the verified TaskRoute run](media/taskroute-demo.gif)

An event-based replay of the installed 0.1.1 check, with timing compressed.
This is not a screen recording. [Verification details](VERIFICATION.md).

</details>

## Why this exists

Delegation only helps if coordinating it costs less than doing the work yourself.
TaskRoute keeps waiting out of repeated model turns and brings back one compact
evidence packet instead of making Codex reconstruct the entire execution log.

In one new-task comparison, both routes passed the same 20 acceptance tests:

| Codex workload | Direct implementation | TaskRoute |
|---|---:|---:|
| Input tokens excluding cache | 24,257 | 9,867 |
| Output tokens | 2,817 | 467 |
| Elapsed time | 99.6 s | 99.5 s |

These are measurements of two clean execution sessions, not guaranteed savings.
Shared experiment preparation is excluded from this table; it was material.
Token counts do not establish subscription quota savings. This is a small sample,
with visible tests and sequential runs, not a broad benchmark.

## Try a small, real task

After installing the plugin, ask Codex:

> Use TaskRoute to implement this Python function. Agree on the behavior and
> acceptance tests first, then delegate the implementation and review to Claude.
> Return the diff, checks, and your decision.

The included [dependency planner example](plugins/taskroute/examples/task-batches/task.json)
provides a complete contract and frozen tests. The [usage guide](plugins/taskroute/README.md)
explains local installation and the script interface.

## Deliberately small

**Current scope:** macOS, Python 3.11+, stdlib unittest projects, one existing
function per task, and an already authenticated Claude Code installation.

One coordinator. One separate reviewer. Up to three check attempts. A bounded
600-second Claude run. No daemon or service to operate.

TaskRoute does not yet support arbitrary full applications, automatic code
application, or semantic drift detection during execution. The tool restrictions
are useful boundaries, not a security sandbox for hostile code.

## Built to inspect

The runtime uses the Python standard library. Ruff checks style and common errors.
Offline regression tests exercise both saved accepted scenarios, the full launch
with a fake provider, replay prevention, and checks that survive Python optimization.

```sh
ruff check plugins/taskroute
ruff format --check plugins/taskroute
python3 -B -m unittest discover -s plugins/taskroute/tests
```

[How it works and how to use it](plugins/taskroute/README.md) ·
[Plugin source](plugins/taskroute/scripts) · [MIT license](LICENSE)
