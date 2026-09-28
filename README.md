![TaskRoute — Delegate the work. Keep the verdict.](plugins/taskroute/assets/flow.svg)

# TaskRoute

**Let Claude handle a bounded coding task. Get back work Codex can verify.**

You and Codex agree on the outcome. Claude implements it, runs the tests, and
brings in a separate reviewer. Codex checks the result and returns a clear decision.

TaskRoute is a local **Codex plugin** that keeps this handoff in one workflow.

## What you get

- **Working code** in a separate copy of your project.
- **Test results** checked against the agreed requirements.
- **An independent review** with the findings included.
- **A clear outcome:** accepted work or an explanation of what blocked it.

Your original files stay unchanged until you decide to apply the result.

<details>
<summary>See the flow in 13 seconds</summary>

![A condensed replay of a verified TaskRoute run](media/taskroute-demo.gif)

A shortened replay of a real run's events, with timing compressed.
This is not a screen recording. [What we verified](VERIFICATION.md).

</details>

## Install with Codex

Send Codex this prompt **along with the repository link or your local folder**:

```text
Install TaskRoute from the repository or folder I am sharing.
Follow INSTALL.md, preserve my existing setup, and verify the installation.
Tell me when it is ready and whether I need to open a new chat.
Do not run a live coding task yet.
```

Codex handles the installation. You do not need to run terminal commands.

## Give it a task

Once installed, ask Codex:

> Use TaskRoute to implement this Python function. Agree on the behavior and
> tests first, then delegate the implementation and review to Claude.
> Return the changes, checks, and your decision.

The aim is to spend less Codex effort coordinating implementation and reviewing
logs. Early examples show promising reductions in execution tokens; overall
savings depend on the task and preparation. [See the measurements](VERIFICATION.md).

**Start small:** the current release supports bounded Python function changes on
macOS and requires an existing Claude Code setup. It is not yet a general-purpose
workflow for building entire applications. [Supported scope and usage](plugins/taskroute/README.md).

[Installation guide for Codex](INSTALL.md) · [What's changed](CHANGELOG.md) ·
[Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
