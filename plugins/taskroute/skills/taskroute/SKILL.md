---
name: taskroute
description: Delegate bounded repository changes to installed Claude Code with independent review and compact evidence for Codex acceptance. Use when the user wants Claude to implement and check a development task, regardless of language. Requires declared files and executable acceptance checks on macOS; no network or installation.
---

# TaskRoute

Use `scripts/taskroute.py` relative to the plugin root (`../..`). Do not inspect
runner source, old transcripts, manifests or README on the normal delivery path.

1. Agree the outcome, boundaries and acceptance with the owner. Reuse an existing
   approved spec unchanged. If one is missing, consult the README schema once;
   check design belongs to preparation, not repeated execution. Never expand
   permissions or waive a known violation. Executable checks remain trusted inputs.
2. Delegate once with `deliver SPEC --project PROJECT --run FRESH_RUN --receipt-only`.
   For an authorized return: `repair PRIOR_RUN FINDING.json --run FRESH_RETURN --receipt-only`;
   consult [return format](../../docs/lead-return.md) only to create a missing finding.
   Existing qualified setup does not need rediscovery. No installs, login or auth
   changes. Use the requested model or the existing Opus medium profile; no implicit
   model switching. The current coordinator also authors code; no Sonnet split yet.
3. Wait in one tool script; resume the SAME yielded cell with 60000 ms, no short
   model-level polls or repeated log reads. Emit only final output. Host timeouts
   may still yield. Substitute a safely quoted authorized command below.

   ```javascript
   // @exec: {"yield_time_ms": 60000, "max_output_tokens": 18000}
   let result = await tools.exec_command({cmd: command, yield_time_ms: 1000, max_output_tokens: 18000});
   let output = result.output;
   while (result.session_id) {
     result = await tools.write_stdin({session_id: result.session_id, chars: "", yield_time_ms: 60000, max_output_tokens: 18000});
     output += result.output;
   }
   text({exit_code: result.exit_code, output});
   ```

4. Read the receipt's result, check status, ALL structured review findings and
   limitations against intent. Claude owns implementation, checks and independent
   code review. Do not routinely reread code or full review: open the linked evidence
   only for a specific missing, contradictory or high-impact unresolved finding.
   `CLAUDE_VERIFIED` is delegated verification, not independent Astra acceptance;
   say who checked it. Missing evidence or a known violation blocks delivery, even
   if the reviewer wrote APPROVE. Never suppress findings to keep an answer short.
5. Report the outcome, important limits and artifact link briefly. No automatic
   apply, commit, publication, resend, history replay or follow-up cycle. Unknown
   effects stop the route. Repairs require the original checks as well as regressions.

The runner reserves before provider effects and records local backlog observations.
Report backlog NOT_SAVED. For an evidenced semantic flow failure consult
[backlog](../../docs/backlog.md); never load its history routinely or fix entries
without authority. Explicit experimental modes are in
[experimental modes](../../docs/experimental-modes.md); verification design is in
[principles](../../docs/verification-design.md), read when defining inadequate checks,
not merely because an already-qualified task has a boundary case.

Detailed mode remains available without `--receipt-only`. `receipt RUN` reads an
existing completed packet without model calls, checks or new effects. No universal
quality guarantee or subscription saving follows from a green receipt.
