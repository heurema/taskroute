# Frontend and browser checks

Use for a repository contract whose acceptance needs an existing frontend toolchain
or local browser. Source and writable files remain declared UTF-8 text. Dependency
trees are a separate check capability: native binaries are never decoded as source
or exposed as writable candidate files. No installation or live model call is part
of preparation. The code and declared commands must be trusted.

## Contract

The optional repository field `check_environment` contains:

```json
{
  "dependency_roots": ["web/node_modules"],
  "executables": ["/opt/homebrew/bin/node"],
  "loopback_ports": [5198],
  "cache_paths": ["web/node_modules/.vite", "web/node_modules/.vite-temp"],
  "cache_environment": {"APP_CACHE": "web/check-cache"}
}
```

Choose the real installed tools and existing project paths. The example Node path
is a host convention, not a required installation destination. `checks[].argv[0]`
is resolved and pinned as before; `executables` adds absolute runtime tools needed
by commands such as npm. Their resolved parent directories enter the stripped PATH.
Unknown fields and arbitrary environment overrides are rejected. The native Codex
route uses the same normalized environment and exact frozen verifier.

Dependency roots must be directories inside the project, disjoint from source and
writable paths and from each other. The tree digest binds bytes, relative paths,
executable modes and contained relative symlinks. Escaping, absolute or dangling
symlinks and special files are rejected. Preparation creates a sealed local copy;
each check receives a fresh disposable copy. Source, snapshot and non-cache copy
changes invalidate the result. System libraries used by installed tools are not
fully pinned by this mechanism.

Cache paths must be strict descendants of a dependency root. They are omitted from
the sealed tree and may be generated only in a disposable check copy. Declare actual
caches, never package code. Cache environment keys have the form `APP_CACHE` or
`APP_CACHE_DIR`; values are relative disposable paths disjoint from source/dependency
roots. This supports projects whose Vite configuration reads a cache-path variable.
No credentials or provider configuration are inherited.

Loopback access is optional and restricted to at most four explicit ports
1024–65535. Only these local endpoints can be bound and connected. Keep
`permissions.network` and `permissions.install` false: external network and package
installation remain denied. A busy port fails the check; it does not authorize
changing a frozen command or stopping an unrelated service.

## Browser boundary

The [frontend example](../examples/frontend/README.md) contains a Vite/Tailwind
build, Vitest test and a headless Chrome DOM oracle for selection, focus and scroll
after refresh. It requires existing matching dependencies and Chrome; it downloads
nothing. No general browser installation, visual quality or model qualification
is implied.

Checks with declared local ports receive an owned short temporary directory for
browser profiles and Unix sockets. The runtime sets `TMPDIR` and
`MAC_CHROMIUM_TMPDIR` to that directory: Chromium on macOS uses the latter for its
socket path. Unix socket effects stay scoped to that directory. Each receipt binds
the actual generated policy digest. Process-group cleanup runs even when the command
exits normally, and the temporary directory is removed.

Chrome cannot initialize its own macOS sandbox inside the enclosing sandbox-exec
policy. The example therefore uses `--no-sandbox` under TaskRoute's existing OS
check policy, with a fresh profile and disabled background networking. It must be
invoked through the frozen verifier; do not launch this example unrestricted or
reuse a personal profile. This boundary is for trusted local code, not hostile
pages or arbitrary downloaded content.

Preparation readiness checks executable/dependency integrity and actual SQLite
create/commit/read. It does not execute application checks or prove a browser starts.
Before dispatch, the lead must establish any required missing toolchain/browser
capability in a disposable local qualification. A browser FAIL or missing oracle
blocks acceptance; a passing build cannot replace it. Preserve failed receipts and
attempt ceilings; old consumed manifests are never replayed.
