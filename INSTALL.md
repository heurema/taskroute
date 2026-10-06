# Installation and updates for Codex

Act on the user's install/update request; do not ask them to clone a repository or
run commands. The canonical source is https://github.com/heurema/taskroute.
The repository catalog is `.agents/plugins/marketplace.json`, named `taskroute`.
The plugin identifier is `taskroute@taskroute`. Current release: **0.3.0**.

## Prerequisites and authority

Check macOS, Python 3.11+, `sandbox-exec`, Codex with native `plugin marketplace`
commands, and an existing authenticated Claude Code installation. No Python runtime
packages are required. Missing tools, login or account changes need separate
permission; report the missing prerequisite without installing or authenticating.
Plugin installation does not authorize a live model task.

Inspect `codex plugin marketplace list --json` and `codex plugin list --json`
first. Preserve unrelated sources and settings. If `taskroute` already resolves to
a different repository, stop instead of replacing it. Record the previous version,
source and revision before an update for rollback.

## Install without a user-managed checkout

Use the native Codex CLI (resolve the installed executable on this host):

```sh
codex plugin marketplace add heurema/taskroute
codex plugin add taskroute@taskroute
```

Codex downloads and manages the Git catalog and plugin cache. The repository's
default branch is the update channel; this is a floating channel, not a tag pin.
Inspect the fetched manifest and `RELEASE.json` before running package code. Verify
all listed SHA-256 digests and the matching version. Digests are integrity checks,
not a publisher signature. If the remote catalog is unavailable, report that
publication is pending; do not silently substitute another source.

## Update

For an existing canonical floating catalog:

```sh
codex plugin marketplace upgrade taskroute --json
codex plugin add taskroute@taskroute
```

Refreshing the catalog and reinstalling the plugin are separate steps. Check both
results and the installed version; a refreshed catalog alone is not an updated
installation. Do not run an unscoped upgrade of every marketplace.

Official documentation describes explicit refresh/reinstall. Automatic background
updating of custom Git catalogs has not been verified. Do not add a daemon, cron job
or heartbeat to simulate it. The user can ask Codex to update at any time.

## Pinned installs and older personal installations

For a fresh pinned catalog, run:

```sh
codex plugin marketplace add heurema/taskroute --ref v0.3.0
codex plugin add taskroute@taskroute
```

A pin stays
fixed; do not claim that refresh selects the latest release. To change an existing
pin, inspect this CLI's marketplace removal/re-add help and preserve its previous
source/ref; never silently change a pin to a floating channel.

An older `taskroute@personal` installation is a different identifier. Install and
verify the canonical replacement first, then remove only the old TaskRoute entry
with the native plugin removal command as part of the requested migration. Preserve
other personal plugins, source files, run directories and the local failure backlog.
If the old copy has local changes, preserve it and report the conflict before removal.
Do not edit the installed cache by hand.

## Verify the installed copy

- Inspect native plugin listing: expected source, enabled installation and version.
  If the listing omits version, read the installed manifest; never infer it.
- Resolve the installed path returned by Codex, verify `RELEASE.json` file hashes
  there, and run `python3 -B -m unittest discover -s tests` from that plugin root.
  Do not substitute tests of a development checkout.
- Report installed version, source revision, checks and limitations. Open a new
  Codex chat to load the new skill. No live task is part of these offline checks.

Rollback: reinstall the recorded previous release through a pinned catalog using
the native commands for this host. Preserve user data. Uninstall removes only the
exact TaskRoute plugin entry, not task outputs or unrelated marketplace settings.

## Native mechanism references

- [Codex plugin packaging and repository catalogs](https://developers.openai.com/plugins/build/plugins)
- [Codex CLI reference](https://developers.openai.com/codex/cli/reference)

Verified on 2026-09-29: native GitHub installation of published v0.2.0, installed
file hashes, all 80 installed-copy tests, catalog refresh and same-version reinstall.
Future-version migration and unattended updates remain unverified. See
[verification evidence](VERIFICATION.md).
