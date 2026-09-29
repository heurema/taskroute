# Explicit lead return

`python3 scripts/taskroute.py repair PRIOR_RUN FINDING.json --run FRESH_RETURN`

Requires an ended repository run with acceptance packet and candidate matching its
checked hashes. The owner authorizes the return; this command is not auto-recovery.
A fresh coordinator receives the original contract, candidate and finding, never the
old transcript. It acts as correction author using the existing profile; this slice
does not add a separate Sonnet developer. Independent review uses the existing gate.

FINDING.json fields: `criterion` (existing acceptance ID), `expected`, `observed`,
`reproduction` (nonempty text), `regression_files` (new relative file names to text),
`checks` (additional check objects using the existing schema). Existing checks and
criteria cannot be removed. New regression files are frozen, never writable.
Use an empty checks array only when existing checks discover and execute these
regressions (for example a new Go test file). Demonstrate that they fail the rejected
candidate before dispatch. Review supplied code/commands as executable inputs.
No new network/install permissions. The existing total check timeout cap applies.

The return directory holds source, spec, finding and delivery. A one-shot reservation
on the parent prohibits a second return, even under another destination name.
Child returns are refused. Preparation failures do not authorize automatic retries.
At most one coordinator, three verifier calls and two independent review rounds
within 900 seconds. Existing provider timeout/unknown-effect handling is unchanged.

Packet diff is relative to the rejected candidate; return_context binds its hashes
and the parent packet hash, and includes the short finding. All original criteria,
checks and full reviewer findings still apply. The packet is evidence, not automatic
lead acceptance. Exposed regression passing is not proof of universal correctness.
