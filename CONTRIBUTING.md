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
