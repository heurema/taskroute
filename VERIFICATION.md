# Version 0.2.0 verification

The current minimal-lead route completed one fresh live scenario using the same
specification, seed, frozen checks and model profiles as the preceding compact run.
Codex used gpt-6-astra; Claude used claude-opus-5-5, medium. The coordinator authored
the code and used a separate reviewer; there is no separate implementation agent.

| Execution measurement | Previous compact route | Minimal lead |
| --- | ---: | ---: |
| Uncached Codex input tokens | 21,065 | 11,125 |
| Codex output tokens | 1,660 | 1,090 |
| Cached Codex input tokens | 225,152 | 133,632 |
| Elapsed seconds | 420.903 | 331.226 |

Uncached input fell 47.2%; output fell 34.3%. Receipt assessment used 1,455 input
tokens versus 13,200. These are execution-session measurements, not subscription
quota or billing savings. Additional experiment-host work was 10,691 uncached input
and 3,789 output tokens to the checkpoint; its reporting tail was not measured.
This is one sample and a historical comparison, not a general performance guarantee.

Frozen Go checks, 650 invalid-root cases and the paired boundary oracle (184 allowed,
124 forbidden cases) passed. Separate review approved. Equal host probes passed
ordinary output, direct/chained symlink rejection and readable relative roots under
a non-searchable ancestor. Earlier false approvals below remain relevant limits.
`CLAUDE_VERIFIED` does not establish a new independent Codex semantic review.

The release passes 80 deterministic offline tests, Ruff and plugin/skill validators.
The complete staged snapshot is privacy-checked before tagging. Native Git catalog add/refresh/reinstall commands
were verified against official documentation and installed CLI help. Remote v0.2.0
installation and unattended updating are not established by those checks; publication
and testing the installed copy are separate steps.

# Historical verification (superseded status, retained evidence)

The sections below describe earlier checkpoints, including failed and incomplete
runs. Their status statements apply to those runs, not the current release summary.

# Local backlog MVP

68 offline tests pass, including duplicate/conflicting events, independent recurrence,
concurrent writers, severity ordering, privacy-shaped input, capture failure reporting,
recovered format incidents and real runner error capture. Two historical false approvals
were filed into the local registry as two episodes of one task/project; filing each
twice did not inflate counts. No live model call, installation or public issue.
Capture is bounded: pre-manifest failures and abrupt process death are not covered;
semantic findings require the skill/lead record step. No automatic semantic grouping.

# Paired-boundary repair accepted

A frozen filesystem-identity oracle checks 184 permitted and 124 forbidden path
cases with exact output expectations. It rejects both known faulty implementations
(56 over-rejections and 88 under-rejections). One live repair completed in 158.592s:
author checks, independent review, independent rerun and lead CLI acceptance passed.
The original Go and invalid-root checks remain passing. Initial lead demo hit a
3-second process timeout; one disclosed local recheck passed, with failure retained.
This qualifies a finite known repair, not all inputs, post-review repair or savings.
See the packaged path-boundary example and verification-design guidance.

# Bounded review repair: partial live evidence

58 offline tests pass, including complete two-review transitions and negative guards.
One controlled live run returned first-review findings to the author, but the repair
broke frozen tests and positive controls. It stopped at three checks, without a second
review (229.425 seconds). No accepted live repaired delivery or efficiency gain claim.
The known candidate, unchanged checks and failure are retained; no install or apply.

# Strengthened verification: internal rejection observed

A fresh run with an independent original-input property and obligation-aware prompts
completed in 315.372 seconds. Observer caught a symlink defect; coordinator repaired
it; identical probe and both checks passed. Independent reviewer then rejected a
remaining symlink-root violation, and collection blocked readiness. Lead execution
confirmed the finding. This is successful internal rejection, not accepted delivery.
53 offline tests pass. Post-review author correction remains unsupported; no install
or savings claim. Historical runs below retain their original results.

# Verification-design study

A bounded offline four-variant study showed existing green tests missed 72 invalid-root
violations among 664 OS-invalid generated inputs. A reusable independent property
check rejected that candidate and accepted a suffix-preserving variant; the old
examples remain necessary to detect another faulty variant. No model calls or
canonical fix, universal mutation-score or full-delivery qualification claim.
See the plugin's verification-design guidance for the reusable preparation method.

# Integrated Bflow rejected at final acceptance

One fresh implementation ran through executable observation, internal correction,
checks, complete independent review and collector in 178.330 seconds. Lead acceptance
then reproduced invalid-root normalization and **rejected AC2**, despite green tests
and review approval. The mechanism is observed end to end; accepted delivery and
general reliability remain unproven. No install or savings claim.

# Controlled review-format recovery accepted

One live controlled format-fault run passed: native same-reviewer correction produced
a complete report; collector and independent Go checks passed; lead accepted the
bounded review packet. 89.984 seconds, no source changes or observer generation.
This closes the known format-recovery gap but is not a single fresh full delivery
run or evidence of general reliability/savings. Installed plugin remains 0.1.1.

# Review completion validation

53 offline tests pass. One live run verified native same-reviewer continuation after
an incomplete report, but the repeated malformed schema was rejected. Concrete
schema feedback was repaired afterward and is offline-tested only. Full route
remains unqualified; installed version stays 0.1.1. No savings claim.

# Compact probe replay

46 offline tests pass. One controlled live replay demonstrated independent executable
detection, coordinator correction, identical-probe success and passing Go checks,
without host candidate edits. The final delivery was **not accepted**: the reviewer
omitted criteria from its structured report and the collector rejected it. Total
157.632 seconds; probe generation/execution 31.603 seconds, deterministic recheck
5.068 seconds without another model call. No unseen/general reliability or savings
claim; installed plugin remains 0.1.1. Historical failed attempts remain below.

# Executable observer experiment

44 offline tests pass, including real sandboxed probe fixtures, frozen reuse after
correction, failed generation/execution gates and mutation refusal. One live attempt
is **BLOCKED / NOT QUALIFIED**: probe generation exceeded its 120-second limit before
returning any source; no semantic detection, correction, tests or review occurred.
No automatic retry or timeout extension. Installed plugin remains 0.1.1.

# Observer checkpoint verification

Experimental pre-check observation has 40 passing offline tests. One live historical
replay is **NOT QUALIFIED**: the observer missed the known violation and the coordinator
stopped because its check output lacked explicit clearance. The output handoff was
fixed locally and regression-tested, without another live call. No accepted internal
catch/correction or natural mid-run drift detection is demonstrated. The installed
plugin remains 0.1.1. This experimental mode should not be treated as a reliable
semantic supervisor; independent executable counterexamples are the next hypothesis.

# Repository contract preview verification

Development version `0.2.0-dev.1`, September 29, 2026:

- 35 offline tests passed, including all 18 legacy regressions.
- Contract hardening covers missing/duplicate criteria, invented/missing evidence,
  writable check inputs, negative/unknown findings, malformed role outcomes and
  the green-tests plus CHANGES/BLOCKED counterexample. It verifies a decision packet
  with retained reasons rather than READY. Review before current passing checks is denied.
- A fake provider exercised prepare, launch reservation, candidate checks,
  synthetic separate-review evidence and independent packet collection.
- Real Go code passed declared compiler/execution checks twice (worker verification
  and independent collection) without a language adapter. This is local execution,
  not a live Claude run or broad Go-project qualification.
- Negative coverage includes frozen/undeclared files, escaping paths, symlinks,
  reviewer writes, failed checks, changed candidates/tools, input mutation,
  timeouts, unsupported permissions and repeated launch.
- Known remaining hardening: worker and acceptance copies share a scratch ancestor;
  fresh independent acceptance roots and live hook-failure behavior need verification
  before treating the new mode as an unattended execution boundary. Trusted code only.
- No automatic semantic mid-run deviation detection is implemented.
- New mode has not been installed, published or live-qualified. The installed
  stable plugin remains 0.1.1. No new savings or model-quality claim is made.

# Version 0.1.1 verification

The installed local plugin was exercised from a fresh Codex CLI session on
September 28, 2026. This is a release smoke test of the bundled example, not a
new performance benchmark or a hidden evaluation.

| Check | Result |
|---|---|
| Local installation | Installed and enabled as `taskroute@personal`, version 0.1.1 |
| Execution source | Installed plugin cache; no historical project runner |
| Example task | Dependency-aware batch planning |
| Coordinator and reviewer | One Claude coordinator and one separate read-only reviewer |
| Worker verification | 28/28, including eight added test methods |
| Independent acceptance | 20/20 frozen tests |
| Final Codex decision | ACCEPTED after inspecting diff, tests and review |
| Native run retries | None |
| Changes applied to original source | None |
| Whole smoke session | 144.3 seconds |
| Offline regression suite | 18 tests passed |
| Ruff lint and format | Passed with Ruff 0.15.2 |
| Plugin and skill structure | Validators passed |

The smoke session used 222,831 Codex input tokens, including 202,880 cached,
and 1,321 output tokens. This includes reading installation instructions and
preparing the example. It is not directly comparable to earlier prepared-arm
experiments. Subscription debit is unknown.

The reviewer inspected code and frozen tests but did not execute tests or
recompute hashes. The runner performed independent test execution and artifact
binding. The final Codex session checked the packet semantically. The example's
checks are visible; this does not prove arbitrary-task reliability or semantic
drift detection. No GitHub publication has occurred as part of this verification.

The README animation is a condensed replay of these observed stages, generated
from the verified event outcomes. It is not a screen capture or a timing benchmark.
Raw session logs stay local and are not included in this repository.

## Earlier execution comparison

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
