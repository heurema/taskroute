# Changelog

## Unreleased

- Make the main README a user-facing introduction with a copyable Codex installation prompt.
- Add detailed agent installation instructions in `INSTALL.md`.
- Separate release history, development checks and measurement details from the README.

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

Stable releases use fixed `vX.Y.Z` Git tags matching the plugin manifest version.
Tags are immutable; `main` may contain unreleased changes. Documentation-only
changes can remain unreleased without changing the installed plugin version.

The installer selects the requested tag or the latest stable tag available from
the supplied source. Request `v0.1.1` explicitly to pin that release. Updates are
explicit; TaskRoute does not replace itself automatically. Keep previous tags
available for rollback through the same installation workflow.
