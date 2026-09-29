# Using TaskRoute 0.2.0

[Install or update through Codex](INSTALL.md), then open a new chat. You describe
the outcome; Codex prepares the contract and invokes the installed skill.
No JSON or terminal commands are required from you.

## Delegate a repository change

```text
Use TaskRoute to implement this change: [desired behavior].
Preserve [existing behavior]. Agree on the writable files and acceptance checks,
then delegate implementation and independent review to Claude.
Return a short verification receipt and a link to the result.
```

Repository mode is language-neutral. Go, Python or another language can work when
its toolchain and dependencies are already available and the task fits declared
text files and executable checks. This is not arbitrary app delivery: binary files,
file deletion, dependency installation and network access are outside this mode.
macOS, Python 3.11+ and an existing Claude Code setup are required.

Claude's coordinator currently writes the implementation and runs the checks.
A separate read-only reviewer checks the candidate. There is no separate Sonnet
implementation agent in this release. Model selection remains configurable;
qualification of one profile does not qualify every model.

## Read the result

The default skill uses a compact receipt: outcome, check statuses, all structured
review findings, limitations and a link to detailed evidence. It avoids replaying
the conversation or reading all source files on every successful delivery.

`CLAUDE_VERIFIED` means Claude-side verification completed. It does not mean Codex
independently reviewed the entire implementation or that all possible defects were
excluded. A missing or contradictory finding still needs investigation. You can ask:

```text
Show the saved TaskRoute receipt for this run without launching another task.
```

The candidate remains in a separate workspace. Applying changes, committing and
publishing are separate actions; ask for them when you are ready.

## Return a concrete defect for correction

```text
Return this TaskRoute result for correction. Expected: [behavior].
Observed: [behavior]. Reproducer: [steps or failing input].
Keep the original checks and add a regression check for this defect.
Use the bounded repair flow and return a new verification receipt.
```

The return uses the rejected artifact, original contract and specific finding,
without replaying the old conversation. Original checks remain, new regressions
are frozen, and a fresh independent review checks the correction. One explicit
return per parent run is allowed; chained returns and blind retries are blocked.
Codex must first show that the regression detects the rejected candidate.

A separate opt-in mode lets an internal negative review trigger one author-owned
correction and re-review. It is bounded, not an unlimited fix loop. Observer and
probe modes remain experimental and are not needed for ordinary delivery.

## Keep workflow defects for later

```text
Record this evidenced TaskRoute workflow defect in its local backlog.
Link the saved evidence, group it with the same known issue if applicable,
and do not start fixing TaskRoute now.
```

The runner captures delivery blockers and recovered review-format failures;
semantic false approvals need an explicit lead record. This records defects in the
workflow, not every bug in a user's project. Repeated identical events are not
counted twice. Deliberate issue keys group cases across tasks and projects.
Severity takes precedence over recurrence when listing issues.

The backlog stays local, survives plugin updates and does not automatically fix,
publish or semantically merge reports. Preparation failures before a manifest and
abrupt process death are not covered. A capture failure is reported as `NOT_SAVED`.

## Evidence and limits

The published 0.2.0 package passed 80 offline tests from its installed GitHub copy.
One live minimal-receipt scenario reduced measured Codex execution tokens versus
the preceding compact route while passing the same checks and host probes. This
is a finite result, not a guarantee of quality or subscription savings.

[Measurements](VERIFICATION.md) · [Changes](CHANGELOG.md) ·
[Technical contract and commands](plugins/taskroute/README.md) ·
[Return format](plugins/taskroute/docs/lead-return.md) ·
[Backlog details](plugins/taskroute/docs/backlog.md)
