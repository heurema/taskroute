# Contributing

The maintained plugin is in `plugins/taskroute/`. Its runtime uses the Python
standard library and targets Python 3.11+ on macOS. Keep changes small and preserve
the existing bounded workflow before adding new capabilities.

## Local checks

Run these from the repository root, using an existing Ruff installation:

```sh
ruff check plugins/taskroute
ruff format --check plugins/taskroute
python3 -B -m unittest discover -s plugins/taskroute/tests
```

To format a change, use `ruff format plugins/taskroute`. The release was checked
with Ruff 0.15.2; its configuration lives in `plugins/taskroute/pyproject.toml`.
Ruff is a development tool, not a plugin runtime dependency. If you need to install
development tools, use a project-local environment.

The tests include two saved accepted artifacts, a fake-provider end-to-end launch,
replay prevention and integrity checks. They run offline. The macOS sandbox tests
must pass on macOS; skipped platform tests do not qualify another operating system.

## Preserve the delivery contract

- Reserve attempts before provider effects; do not add automatic retries for unknown outcomes.
- Keep independent checks and final semantic acceptance separate from process completion.
- Retain full reviewer findings and freeze the candidate when review starts.
- Add behavior tests for relevant changes. Keep saved regression fixtures intact unless
  deliberately revising their documented contract.
- Live provider tests consume model allowance and require explicit authorization.
  Offline success does not prove live provider compatibility.

## Release checks

Run the local checks and the available Codex plugin/skill validators. Verify the
package from a clean copy, refresh `RELEASE.json` file digests for the new release,
and ensure the manifest version matches the new tag. Record changes in
[CHANGELOG.md](CHANGELOG.md) and live verification, when performed, in
[VERIFICATION.md](VERIFICATION.md). Never rewrite an existing release tag.

Keep credentials, personal paths, private session logs and development artifacts
out of published files. Follow [INSTALL.md](INSTALL.md) when testing installation;
test the installed copy rather than silently falling back to the source checkout.

## Privacy gate before every commit

This repository uses **prek**, the Rust implementation of pre-commit, with a local
hook backed by **Gitleaks 8.30.0** and a small Python privacy scanner. With those
existing tools available, install the repository hook once:

```sh
prek install
```

Every commit scans the **complete staged file snapshot**, not just changed lines
or the current working copy. Checks cover standard secret patterns, private keys,
absolute user-home paths, email addresses and phone-like strings. Reserved example
email domains are permitted. Findings show object IDs, line numbers and rule names;
they never print the matched value. A missing scanner or scan failure blocks the
commit. Run a historical file audit with:

```sh
python3 scripts/check_privacy.py --history
python3 -B -m unittest discover -s scripts/tests
```

An optional `.git/privacy-terms.json` contains a JSON list of additional private
names or identifiers. It stays local and is never committed. CI cannot see this
private list; generic rules remain active there. Do not copy personal identifiers
into public tests, configuration or documentation to build a blocklist.

The lightweight GitHub workflow scans the checkout and historical file contents;
it does not run models or the macOS delivery tests. Its tool download is pinned by
version and checksum. It will run after publication; adding the workflow locally
does not prove a hosted run succeeded or enable branch protection.

By owner decision, existing author/committer/tag metadata is preserved and is
**outside this file-content gate**. Local experiments excluded by Git are also
outside the committed snapshot. Pattern matching cannot identify every possible
personal fact, image pixel or unknown credential format; review public media and
unusual binary formats separately. Local hooks are a guardrail, not an unbypassable
security boundary. CI supplies an additional check when the repository is hosted.
