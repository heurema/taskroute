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
