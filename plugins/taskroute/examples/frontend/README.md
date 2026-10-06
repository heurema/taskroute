# Local frontend qualification

This is a bounded check-chain example, not a model-quality benchmark or RideCheck
implementation. It uses an existing Node/npm, Vite 8.3, Vitest 5.0 and Tailwind 4.3
toolchain plus an existing Google Chrome installation. Do not install tools as a
fallback or run the browser driver without the TaskRoute verifier.

The contract declares all eight source/check files, a separate existing
`node_modules` dependency root, Node/Chrome executables, `.vite`/`.vite-temp` caches
and one local port. Copy compatible existing dependencies into a disposable project
before preparation; do not commit dependencies or run outputs. Change executable
paths and the port to actual existing host capabilities before freezing the contract.

The tests, native build and browser check run in separate copies. Browser acceptance
loads the real local page, selects a row, focuses it, scrolls the list and refreshes;
the resulting DOM must report preserved selection, focus and scroll. The build uses
actual native Rolldown/Tailwind dependencies. No network except the declared local
endpoint is required. Chrome's inner sandbox is disabled only because the TaskRoute
outer macOS check policy supplies the boundary; profile/socket paths are owned and
temporary. This is trusted local-code verification, not hostile-code isolation.

See [the environment contract](../../docs/frontend-checks.md). Preparation and the
frozen verifier make no model calls. A no-change qualification may preserve all
source bytes; it does not need an artificial edit or an independent model review.

Current browser qualification: **UNVERIFIED**. Unit tests and the native build
passed. The last local browser attempt cleared nested sandbox initialization but
timed out without a captured DOM acceptance marker. Preserve that failure and the
attempt ceiling; the example is not browser acceptance evidence yet.
