# Codex-native Sol/Astra route

Use inside Codex with native collaboration tools. Python only prepares and verifies
local evidence; it cannot create native roles. Do not replace unavailable tools
with CLI, external APIs, an inherited context, another model or sidebar chats.
Claude remains the default when native routing was not requested.

The explicit profile is worker `gpt-6.1-sol` and reviewer `gpt-6-astra`, medium.
The spec uses the existing repository schema and worker model. Native selection
records tool arguments and the returned canonical agent ID; backend identity stays
unobserved. This is an explicit evidence basis, distinct from the strict CLI gate.
One worker, one fresh reviewer, no repair/retry. A spawn failure or unknown submission
consumes its reservation; never blindly resend under a new run name.

All commands below run relative to the plugin root. They launch no models. Use one
fresh run directory and record returned tool evidence accurately, never from prose.

## Selection reason

`native-prepare` accepts optional `--selection-reason` with exactly
`owner_request`, `tool_requirement`, `task_family_evidence`, `default_policy`,
or `unknown` (the default). The Python API is
`native_route.prepare(spec, project, run, *, selection_reason="unknown")`.
Invalid types or values fail before any run creation or reservation. For example:

```sh
python3 -B scripts/taskroute.py native-prepare SPEC --project PROJECT --run RUN --selection-reason owner_request
```

The reason is operator-supplied bounded metadata, never raw prompt text or proof
of route quality, backend identity, savings, or G1-G5 qualification. It is stored
only in the native manifest and final receipt; receipt readback validates the enum
and binds it to the manifest and existing evidence hashes. The repository spec
and Claude route schema are unchanged, and Claude remains the default.
Pre-feature saved native manifests and receipts that omit the reason read back as
`unknown` without rewriting archived artifacts. Removing a reason from a new
receipt or changing it against the manifest fails readback.

## Workflow

1. Confirm the approved contract, delegation authority, tools and usage budget.
   Trusted local code only. Native role scopes are instructions plus post-effect
   hash checks, not hostile-code containment. No install/auth or canonical apply.
   Prepare:

   ```sh
   python3 -B scripts/taskroute.py native-prepare SPEC --project PROJECT --run RUN
   python3 -B scripts/taskroute.py native-reserve RUN worker
   ```

   `native-reserve ... worker` first verifies SQLite create/commit/read in a fresh
   disposable scratch directory using the generated policy. A failed readiness
   check stops before the role reservation and model submission. Both native and
   Claude policies allow metadata only for exact ancestors of their owned roots;
   file contents, writes outside scratch and network remain restricted. Claude
   preflight performs the same real SQLite operation before its launch. These are
   bounded readiness checks, not a general containment guarantee.

   Preparation has no Codex CLI dependency. Reservation returns the exact model,
   effort, fresh-context setting, prompt path and disposable workspace. Before
   spawning, read worker-prompt.txt verbatim (including exact normalized argv,
   timeouts and workspace cwd for all declared checks); do not paste history or worker/advisor
   messages into a fresh role's context. Do not let a child delegate another child.

2. Call `collaboration.spawn_agent` once with a unique task_name, `fork_turns="none"`,
   `model="gpt-6.1-sol"`, `reasoning_effort="medium"` and the prepared worker prompt.
   Capture the actual returned canonical task_name:

   ```sh
   python3 -B scripts/taskroute.py native-dispatch RUN worker --agent RETURNED_AGENT --model gpt-6.1-sol
   ```

   Wait with `collaboration.wait_agent`, at most 60 seconds per wait to keep the
   owner informed; use completion notifications rather than repeated source/log
   inspection. Only the worker writes the candidate. If terminal is unknown, stop;
   no second writer or re-dispatch. When the worker completes, save its actual final
   text to WORKER_RESULT outside workspace, including the single TASKROUTE_RESULT
   line. The helper never verifies the semantic truth of a copied tool transcript.

3. Run the declared host checks and freeze the candidate:

   ```sh
   python3 -B scripts/taskroute.py native-worker-complete RUN WORKER_RESULT
   ```

   This consumes the only check batch, enforces declared/frozen and canonical
   inputs, executes unchanged commands in disposable macOS-sandbox copies, saves
   file hashes and prepares review-workspace/reviewer-prompt.txt. Host check failures
   stop; no code repair. Do not add a prompt to a still-running author. Assess check
   adequacy when designing the contract; passing narrow checks is not full semantics.

4. Reserve the reviewer only after CANDIDATE_FROZEN:

   ```sh
   python3 -B scripts/taskroute.py native-reserve RUN reviewer
   ```

   Read reviewer-prompt.txt and call `collaboration.spawn_agent` exactly once with
   a new unique task_name, `fork_turns="none"`, `model="gpt-6-astra"`,
   `reasoning_effort="medium"`. Reviewer inspects only the copied candidate, frozen
   TASK.md, checks.json and exact criteria; no author conversation or model claims.
   No candidate writes while reviewing or after completion. Reviewer may inspect
   bytes and execute trusted checks in a separate disposable copy if needed;
   it must distinguish its own execution from host evidence. No nested delegation.

   ```sh
   python3 -B scripts/taskroute.py native-dispatch RUN reviewer --agent RETURNED_AGENT --model gpt-6-astra
   ```

   Wait for completion. Save the actual final report to REVIEW_RESULT outside
   workspace, preserving exactly one TASKROUTE_REVIEW line. No formatting resend,
   new reviewer or correction on CHANGES/UNKNOWN/malformed output.

5. Validate findings, both frozen copies and the result:

   ```sh
   python3 -B scripts/taskroute.py native-finish RUN REVIEW_RESULT
   python3 -B scripts/taskroute.py native-receipt RUN
   ```

   Finish requires distinct recorded native agents, checks bound to current files,
   unchanged reviewer copy and exact complete AC/non-goal findings. Negative or
   incomplete review returns BLOCKED. Receipt reread performs no model or check
   effect and rejects changed candidates, review copies, exact final texts,
   check/dispatch records and prepared contexts against saved evidence digests,
   and compares the returned diff and candidate hashes with verified inputs. A failed command's own blocker is primary;
   do not expect a success receipt or automatically retry it.

6. Lead reads every criterion finding and limitations against intended behavior;
   independently resolves any contradiction and inspects the linked diff/artifacts.
   READY_FOR_LEAD_REVIEW is not owner semantic acceptance or canonical apply.
   Report who implemented, who ran checks, who reviewed, result and artifact links.
   Stop the bounded cycle. Any apply/commit/publication remains a separate action.

## Evidence and limits

Run retains reservations, recorded worker/reviewer dispatch, actual final texts,
check logs/hashes, isolated review copy, structured review findings and diff.
No backend model identity, token use, subscription quota or actual charge is inferred;
unknown fields are null. Native agent task names are platform handles, not invented
physical session IDs. Helper data is operator-supplied; an offline fixture cannot
prove that a role was actually launched or that its recorded profile was observed.

The real manual canary on 2026-10-04 completed Sol edits/worker check, host check and
exact-byte oracle, fresh Astra APPROVE and unchanged hashes. Packaging is verified
with deterministic fixtures, not a second live qualification or general quality claim.
The former `--route sol-astra` CLI adapter remains separately blocked at missing
native model identity; no receipt conversion or consumed-attempt reuse is allowed.
