# Changelog

## 0.3.0 — 2026-10-06

- Add coordinator-recorded native stage routing, a single bounded Claude process,
  independent acceptance and explicit partial usage observations.
- Add one native Sol6.1 fallback after confirmed Claude unavailability and resolved
  primary effects; retain failed-primary cost and stop on unknown submission.
- Document coordinator-owned decisions and scoped plugin updates.

- Snapshot existing native frontend dependencies for fresh isolated check copies,
  pin runtime executables, scope disposable caches and explicit local ports, and
  provide a Vite/Tailwind/Vitest/browser example. Browser qualification pending.
- Capture sanitized preparation/preflight failures before a run manifest exists,
  with immutable local evidence and exact/concurrent replay deduplication.
- Preserve reviewer baseline/diff evidence and SQLite readiness before effects;
  align worker prompts with explicit acceptance-check budgets.
- Package the requested native Codex worker/reviewer route and selected correction
  feedback intake; the separate CLI route remains live-blocked at missing identity.
- Preserve live qualification and savings as unproven; packaging and installation
  do not promote offline fixtures to live delivery evidence.

## 0.2.2 — 2026-09-29

- Preserve UTF-8 source bytes including CRLF, LF and mixed line endings during
  preparation, candidate checks, check copies and explicit returns.
- Fix false `CANONICAL_SOURCE_CHANGED` failures for unchanged CRLF inputs without
  weakening source integrity or frozen-input checks.
- Add newline-preservation and real-mutation rejection regressions. Previously
  prepared affected runs must be prepared again in a fresh directory.

## 0.2.1 — 2026-09-29

- Isolate both fake-provider integration suites in per-test temporary backlog databases.
- Assert that expected replay rejections reach the isolated database, including child
  CLI processes. Preserve the caller's backlog configuration and existing records.
- No delivery behavior change; existing uncertain-provenance records are not deleted.

## 0.2.0 — 2026-09-29

Git tag: `v0.2.0`.

- Support language-neutral repository contracts with declared writable files,
  acceptance criteria, frozen project checks and evidence bound to candidate hashes.
- Add a single delivery entrypoint and minimal receipts retaining every structured
  review finding. `CLAUDE_VERIFIED` is delegated verification, not independent Codex review.
- Add bounded author-owned review repair and explicit artifact-bound return for
  correction with a fresh reviewer, without replaying the previous conversation.
- Add a local capture-only failure backlog with idempotent occurrences and recurrence counts.
- Strengthen paired permitted/forbidden boundary checks; retain observer/probe modes
  as experimental, not qualified defaults.
- Add a native GitHub marketplace and agent-operated installation/update instructions.
- Freeze 80 offline tests and one minimal-lead live scenario with successful checks
  and host probes. Measured execution token reductions are workload-specific;
  no universal quality or subscription savings claim. See [verification](VERIFICATION.md).

## 0.1.1 — 2026-09-28

Git tag: `v0.1.1`.

- Verify installation and a complete live run through the installed plugin.
- Add explicit integrity checks that remain active under Python optimization.
- Prevent candidate writes after review starts and validate the target before launch.
- Add Ruff configuration, consistent formatting and regression coverage: 18 offline tests.
- Add a workflow illustration and a condensed replay of the verified run.

See [verification details](VERIFICATION.md) for results and limitations.

## 0.1.0 — 2026-09-28

Git tag: `v0.1.0`.

- Package the bounded Claude workflow as a local Codex plugin with a bundled skill.
- Include isolated preparation, one coordinator, one reviewer and compact acceptance evidence.
- Freeze two accepted-artifact regressions and 15 offline tests.

## Version policy

Release tags `vX.Y.Z` are immutable and match the plugin manifest. The default
branch distributes released plugin snapshots; develop runtime changes on branches
and publish a new version before moving the distribution channel. Documentation-only
changes need not change the plugin version. Never modify a released tag.

Native catalog updates are explicit. Floating installs follow the default branch;
pinned installs retain their selected ref. Keep prior tags for rollback. Local
release preparation is distinct from publishing the branch/tag to GitHub.
