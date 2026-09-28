# Installation instructions for Codex

The human provides a repository URL or local checkout and asks you to install
TaskRoute. Perform the installation yourself; do not hand back a list of terminal
commands for the human to execute.

## Select a fixed version

1. Resolve the supplied source. If no URL or folder is available, ask only for
   that source; never guess a repository owner or URL.
2. Use the requested version. Otherwise choose the latest stable `vX.Y.Z` Git
   tag available from that source. The current verified plugin is **v0.1.1**.
   Work from a separate checkout or archive of the selected tag; preserve any
   existing checkout and its uncommitted changes. Never install floating `main`
   while reporting that a release was installed.
3. The plugin is `plugins/taskroute/`. Confirm that its manifest version matches
   the selected release and verify every entry in `RELEASE.json` against the
   actual file contents before copying or installing it. Missing or mismatched
   files block installation. An integrity manifest is not a publisher signature.

## Check prerequisites

Confirm macOS, Python 3.11+, `sandbox-exec`, and the local Codex and Claude Code
CLIs. This release needs existing Claude authentication. Check existing access
read-only when needed; do not start login, install missing tools, change billing,
or issue credentials as part of plugin installation. Report the exact missing
prerequisite if one is absent. There are no Python runtime packages to install.

## Register and install locally

Use Codex's installed plugin-creation/installation tooling when available. The
verified local route is a personal marketplace and native `codex plugin add`.
Inspect existing entries first and preserve unrelated plugins and settings.

- Place the selected plugin files under `~/plugins/taskroute`, or reuse that
  directory only if it is already the matching managed TaskRoute source. Preserve
  the previous managed version for rollback. Do not overwrite an unrelated folder.
- The default personal marketplace file is
  `~/.agents/plugins/marketplace.json`. For this default location, Codex resolves
  `./plugins/taskroute` to `~/plugins/taskroute`, not beneath `.agents/plugins`.
- Use the host's marketplace helper to add the `taskroute` entry. For hosts without
  that helper, use the supported local marketplace configuration below. Merge the
  entry into an existing marketplace rather than replacing its contents, and keep
  its actual name. Stop if the same name already points at an unrelated source.

A new personal marketplace has this shape:

```json
{
  "name": "personal",
  "interface": {"displayName": "Personal"},
  "plugins": [{
    "name": "taskroute",
    "source": {"source": "local", "path": "./plugins/taskroute"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity"
  }]
}
```

Run `codex plugin add taskroute@personal`, substituting the existing marketplace
name if different. The default personal marketplace is discovered automatically;
there is no need to add another global marketplace source. For same-version local
development updates, follow the host's cachebuster/reinstall procedure rather
than silently editing the installed cache. Tagged releases are immutable.

## Verify before declaring success

- Inspect `codex plugin list --json`: TaskRoute must be installed, enabled, and
  report the selected version and intended source.
- Use the installed plugin path returned by the installer. Verify its release
  file digests again. Do not test a source checkout and call that an installed test.
- Run its offline suite with Python's unittest discovery from the installed
  plugin root. No Ruff installation is required to use the plugin.
- Report the version, tag/commit, installed path, checks, and any limitation.
  Explain that a new Codex chat loads the installed skill.
- A live example is a separate model-consuming action. Run one only if the human
  also requests a live check; installation alone does not authorize it. Use the
  installed skill, one coordinator and one reviewer, with no automatic resend.

To undo installation, use the native plugin removal command for the exact
TaskRoute entry. Preserve unrelated configuration and user task results. To roll
back a version, reinstall the previous fixed release through the same route.
