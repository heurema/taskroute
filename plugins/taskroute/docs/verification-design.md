# Delivery and verification principles

Status: adopted design principles; model/effort combinations below are hypotheses,
not implemented per-role routing or qualified defaults. These principles do not
expand tool access, installation authority or experiment ceilings.

## Outcome and ownership

Delegate a complete bounded outcome, with the smallest useful end-to-end result,
acceptance conditions and genuine stop conditions. Resolve ambiguities that change
the result before implementation; more effort cannot settle the owner's intent.
Keep a compact task/evidence checkpoint in a file. A progress update alone is not a
reason to return the task to the owner. Continue necessary authorized work within
the declared budget; stop on acceptance, a real blocker or the reserved ceiling.

The author repairs the artifact they produced. A developer corrects code after
independent findings; a reviewer corrects their own malformed report. The coordinator
routes findings and verifies completion. Do not add a new agent for every failure.
Logical roles are separate responsibilities, not a mandatory number of processes.
Final acceptance is independent from the author's and reviewer's claims.

## Model, effort and capability

Select model and effort for the work phase and risk, not one universal setting.
Clear implementation may need less reasoning than designing adversarial checks or
resolving a difficult domain question. Higher effort may improve edge-case work but
cannot replace an oracle, tool access, a clear requirement or a failed actual check.

| Role | Selection requirement | Required evidence/capability |
| --- | --- | --- |
| Bounded implementation | Lowest-cost qualified profile for the task | Declared source edits and real relevant checks |
| Difficult verification/oracle design | Profile qualified for adversarial reasoning | Executable properties/counterexamples, or independent deterministic execution of generated checks |
| Final review/acceptance | Risk-dependent independent profile | Actual diff, check receipts, unresolved obligations and authority boundaries |

### Replaceable model profiles

Keep stable role requirements separate from replaceable provider/model profiles.
A profile records the exact model ID, provider adapter, supported effort and tools,
limits, dated pricing assumptions and qualification evidence. Effort labels are
provider-specific; the same label does not imply equal capability across models.
Task contracts specify outcomes and evidence, not permanent model generations.

A model upgrade should change the selected profile, not the contract, role ownership
or acceptance rules. Reuse the existing task-level model selection where supported;
per-role profile configuration is a design target, not an implemented registry.
Only a protocol/capability change should require adapter work. Preserve the previous
profile for rollback and record the requested and observed model for every run.

For an authorized replacement, check identity/tool compatibility, then run a bounded
comparison against frozen representative acceptance checks. Promote only for the
scope supported by evidence; a newer name, lower advertised price or one successful
probe is insufficient. Reevaluate after material model, price or capability changes,
without adding a periodic service. Existing authority and attempt limits still apply.

Dated candidate examples (September 29, 2026): Sonnet 5.5 medium for bounded
implementation and Opus 5.5 high for difficult verification. These are replaceable
hypotheses, not role names, permanent defaults or dependencies on those generations.

Current runner retains its existing model
and medium effort; reviewer inherits the model and has Read-only tools. The observer
has a single-criterion probe limit. Do not describe these as phase-specific routing
or broad verification coverage. Do not silently change models, effort or capabilities.
Validate exact model identity, platform/version support and authority before changes.

Use low effort only where feedback and checks make it suitable. xhigh/max must earn
their extra work in evaluation. Avoid generic "think harder" instructions. Existing
baseline instructions, not vendor examples, control installation and network access.

## Design evidence before implementation

A contract describes the required result. A reviewer claiming MET and a green test
command are evidence inputs, not a proof that every contractual statement was tested.
The runner validates receipts, identity, hashes and scope; it cannot decide whether
an arbitrary oracle encodes the user's intent correctly.

For a behavior-changing task, identify independent obligations inside broad criteria.
For each important obligation record a compact verification row in the existing task
note: expected property, input domain, independent oracle, executable check, and
what remains untested. Do this before implementation. Keep original criterion IDs;
use subclaim labels in the note when helpful. Do not invent new product requirements.

For a restrictive change, define the permitted behavior it must preserve alongside
what it must reject. Generate paired boundary cases from an independent relation
(identity, authorization, ordering, conservation, etc.), not an enumeration of
incident strings. A positive control must exercise the changed transformation too;
a simple unrelated happy path does not test over-rejection. Prove sensitivity to
both under- and over-rejecting faulty variants. Record finite-domain limits.
See the [executable path-boundary example](../examples/path-boundary/README.md).

Choose checks in proportion to the risk:

- Concrete examples establish required user scenarios and discovered regressions.
- Invariants check conditions across generated inputs. Generate equivalence classes
  and combinations; record the seed or deterministic domain and minimal failing case.
- Metamorphic checks compare related inputs only under explicit preconditions. For
  example, representation changes may preserve a resource only if that equivalence
  was established; lexical path normalization is not filesystem equivalence.
- Differential checks use an independent trusted implementation or platform behavior,
  where the contract adopts that behavior. Copying implementation logic into the
  oracle can reproduce the same defect and prove nothing.
- Targeted mutation/fault seeding tests the tests: freeze a few plausible wrong
  implementations or disabled safeguards, and require detection of the relevant
  violation. Surviving and equivalent mutations need interpretation. No universal
  mutation-score threshold, exhaustive proof or mandatory new tool installation.
- Include positive controls so rejecting everything cannot satisfy rejection rules.
  Preserve existing checks: a new property may miss defects those examples catch.

Freeze independent acceptance scripts/configs in `check_inputs`, outside writable
paths. Run them through the existing `checks` interface in disposable copies. No new
agent or separate runtime is required. After any code repair rerun the unchanged
properties and regression checks, not just the single counterexample that failed.
The author's extra tests are useful additions; they cannot weaken the frozen oracle.

An observer's one passing probe covers its executed cases only. It cannot certify
all clauses of a broad criterion. Missing verification stays unobserved; justify
source-only review explicitly where execution is impractical. A known contradiction
of a mandatory requirement is CHANGES/BLOCKED even if rare or described as a risk.
The reviewer cannot waive it. Changing the requirement belongs to the owner.

The detailed adequacy of a test plan remains a reasoning task. These instructions
improve it; they are not an implemented automatic semantic-coverage verifier. A
run is not promoted to reliable or efficient based on formatting, test count, code
coverage percentage, one mutation score, or one successful exposed example.


## Qualification and accounting

Before promoting a profile, freeze the task outcome, acceptance oracles and attempt
budgets. Compare accepted outcomes on tasks not used to tune the profile; retain
failed attempts and report preparation, repairs, review, lead effort and wall time.
Change one factor at a time when attributing a gain. Native token counts and API
list-price estimates are not subscription charges or Codex quota savings.

Sources informing the hypotheses (reviewed September 29, 2026):
- [Building with Claude Sonnet 5.5](https://claude.dev/blog/building-with-claude-sonnet-5-5/), September 28.
- [Getting the most out of Opus 5.5](https://claude.dev/blog/getting-the-most-out-of-opus-5-5/), September 22.
- [Spending your effort](https://claude.dev/blog/spending-your-effort/), September 25;
  [author's X article](https://x.com/trq212/status/2103576349499855160).

These are vendor guidance and selected experiments, not local qualification. Recheck
time-sensitive API/CLI claims. Prompting principles cannot guarantee compliance or
semantic correctness; explicit runtime limits and actual acceptance evidence remain.
