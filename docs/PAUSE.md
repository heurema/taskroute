# Paused experiment checkpoint — October 1, 2026

Status: **PAUSED_OWNER_DIRECTED**. Complete delivery-route qualification remains
**NOT_QUALIFIED**. This is a preservation checkpoint, not a new release or a
successful full-route experiment. No automatic continuation is authorized.

## Why paused

- The owner reports improved quality and lower usage since Sol 6.1 became available.
- Coordinating the work directly inside Codex is simpler for the owner.

These are practical owner observations; no new comparative measurement was run.

## Preserved implementation

The existing plugin supports declared repository/file/check contracts, a separate
candidate copy, one reserved Claude attempt, an independent read-only reviewer,
frozen candidate-bound checks and compact delivery receipts. Explicit correction
and a capture-only local failure backlog are available. LF/CRLF/mixed source bytes
are preserved. Historical finite accepted scenarios and failed deliveries remain
recorded in [VERIFICATION](../VERIFICATION.md); they do not qualify every route.

This checkpoint saves the previously local runner and review-contract repairs:

- Preparation probes workspace writes, pinned executables and basic stdlib
  read/write capability inside the existing macOS check sandbox before effects.
  Additional dependency roots and network exceptions are rejected.
- Generated launchers recheck readiness before reserving an attempt. Startup
  uncertainty never triggers a resend. Prior terminal receipts survive replay.
- Native failures such as `error_max_turns` are evaluated before success-only
  checks/review artifacts. Missing artifacts are secondary, not the primary cause.
  Malformed, truncated and duplicate terminal/result records fail closed.
- Failure receipts leave observed/accepted identity and usage unknown. The launcher
  waits once for process completion. Instructions/hooks do not prove OS containment.
- Reviewer guidance derives exact IDs and complete record shape from the validated
  task. Extra, missing, duplicate or misplaced IDs remain rejected by the unchanged
  hard gate. `UNKNOWN` cannot be converted into an accepted criterion.
- Regression fixtures retain the saved invented-ID failure and its review hash.
  Only a sanitized task/review/code excerpt is included; host-specific executable
  metadata, personal paths, native session transcripts and private run logs are not.

There are 27 additional tests compared with the previously committed 82-test
plugin suite: workspace/check-environment preflight, primary failure ordering,
launch completion/replay/startup guards and exact reviewer-contract behavior.

## Local verification on October 1

| Check | Observed result | Limit |
| --- | --- | --- |
| Plugin suite on macOS host | 109 tests passed, 12.700 seconds, no skips | Offline fixtures and fake providers only |
| Privacy-scanner tests on macOS host | 7 tests passed, 1.034 seconds, no skips | Tests of the file-content gate |
| Ruff lint and formatting | PASS | Plugin source and tests |
| Source/fixture syntax and diff whitespace | PASS | No provider quality claim |
| Complete staged snapshot privacy scan | PASS, 65 Git objects | Pattern-based scan plus manual review |
| Publishable branch ancestor history | PASS, 195 Git objects | Single-branch local export; no private refs |

The first plugin run inside the outer restricted execution environment ran 109
tests and failed with 1 failure and 25 errors, primarily from unavailable nested
sandbox execution. The first privacy test run had 1 error in its disposable Git
commit. These are retained failures, not passes. One host retry of the same offline
suites passed, with the inner project sandbox unchanged and no mocked substitute
for native integration. Raw check output stays outside the published snapshot.

An audit of all local Git references found two matches in earlier unpublished test
snapshots: a package path resembling an email and a fictional home path. Neither
object is reachable from the saved branch ancestry; both were removed from the
current fixture snapshot. The all-local-reference scan is not recorded as passing.
Only the explicit branch is pushed; local snapshots and unrelated refs are excluded.
The branch ancestor history and the complete new file snapshot pass their gates.

No real model invocation, paid experiment, installation, authentication, account,
permission configuration, production action or working-project edit was performed
by this preservation cycle. Existing local evidence is preserved but not published.

## Remaining limitations

- The saved real review with an invented acceptance ID remains **NOT_QUALIFIED**;
  prompt fidelity on a real model after the repair is **UNKNOWN**. Guidance is not
  provider-enforced JSON schema.
- Full Claude-owned preparation, separate coordinator/developer ownership and
  same-author continuation are not established by host-run tests or transport.
- A meaningful early direction gate has not been qualified as a reliable semantic
  supervisor. Final green tests/review have historically missed contract defects.
- Required DB/browser environments and project acceptance must be declared and
  qualified before implementation; fallback host delivery does not qualify the
  complete TaskRoute chain.
- Whole-worker containment, child shutdown and unknown external effects are not
  proven by instruction hooks or a parent process timeout. Transitive check
  dependencies and current provider authentication/availability are unverified.
- A compact receipt or `CLAUDE_VERIFIED` is not independent semantic acceptance,
  universal correctness, billing savings or subscription-quota savings. Failed
  episodes and unknown usage/cost attribution must remain visible.

## Resume sequence

1. Obtain an explicit owner resume with a bounded outcome and authority. Read this
   checkpoint and current local PLAN/HANDOFF; older next actions are suspended.
2. Keep this code snapshot separate from published version 0.2.2. It is saved on
   `codex/pause-checkpoint-2026-10-01`; release digests/tags were not refreshed.
   Do not install it as a qualified release or move the default distribution branch
   without a separate release decision and the required checks.
3. Before any separately authorized real invocation, establish the required local
   sandbox/dependency/DB/browser execution paths and freeze one approved task's
   requirements, source hashes, roles, evidence and attempt/repair ceilings.
4. Verify the repaired review prompt on a fresh, bounded authorized task; never
   replay a consumed run or filter invented IDs to make a receipt pass. Stop at
   the first conclusive receipt or blocker.
5. To qualify the parent route, demonstrate Claude-owned preparation (G1), actual
   coordinator/developer/reviewer/correction evidence (G2), an early direction gate
   (G3), pre-established complete acceptance environments (G4), and all obligations
   plus final review and Codex-intervention accounting against one candidate (G5).
   Component or fixture success closes only that component's gap.

The immediate next action after this save is **stay paused**, not step 3 or 4.
Resume requires owner direction; no new paid comparison, automatic repair,
authentication change or background experiment is scheduled.

## Publication and rollback

Publish only the safe checkpoint, current plugin diff, tests and ignore rules to
the existing repository branch. Do not force-push or rewrite release tags. Read back
that branch's SHA and compare it with the saved local commit. A later rollback is a
reviewed revert on this branch; the published default branch/release stays intact.
