# Local metrics collection

Use for requested historical/weekly usage reports. Run the collector directly;
there is no model call, background service, task classifier or subscription-price
estimator. The lead chooses the requested period and executes the command; the
owner does not need to prepare inventories or copy chat logs.

From the plugin root:

```sh
python3 -B scripts/taskroute.py metrics \
  --start 2026-09-29T00:00:00+03:00 \
  --end 2026-10-06T00:00:00+03:00 \
  --output-dir /existing/local/reports/fresh-week
```

Start is inclusive, end exclusive; both require an explicit UTC offset. Daily
buckets use Europe/Moscow. Choose complete days when comparing historical periods.
The output directory must be fresh; existing reports are never overwritten.

Default roots are the current user's `.codex/sessions`, `.codex/archived_sessions`
and `.claude/projects`. Optional repeated `--codex-root` and `--claude-root` replace
that provider's defaults. Check `sources.json` for missing roots; absence is not zero
usage. Discovery selects JSONL files modified at or after the start, then filters
individual events by their timestamps. Files with misleading old modification times,
cloud/deleted histories and unsaved Claude calls can be absent.

The command saves:

- `inventory.json`: input paths and frozen byte-prefix lengths;
- `sources.json`: discovered roots or replay source;
- `report.json`: response counters, grouped daily volumes, coverage gaps and quota snapshots;
- `report.html`: a static readable summary with no external resources;
- `providers.csv`, `sessions.csv`, `projects.csv`, `models.csv`, `days.csv`: complete
  workload tables (empty tables omitted). CSV source labels are formula-neutralized.

Replay the original frozen file prefixes into another fresh output directory:

```sh
python3 -B scripts/taskroute.py metrics \
  --inventory /existing/local/reports/fresh-week/inventory.json \
  --start 2026-09-29T00:00:00+03:00 \
  --end 2026-10-06T00:00:00+03:00 \
  --output-dir /existing/local/reports/replayed-week
```

Compare report JSON or source prefix hashes to detect changed input. Inventories
freeze lengths, not the contents themselves; source files can still be altered or
removed. Do not silently call mismatched replays identical.

## Interpretation

Codex uses per-response `token_usage_record` records belonging to the current
session, deduplicated by response ID. Foreign-thread inherited history is excluded;
conflicting response counters are quarantined. Model labels come from turn
configuration, not backend attestations. Cumulative token-count records supply
quota snapshots/coverage only and are not added again to per-response tokens.

Claude uses message IDs with logged model and token counters. Monotone progressive
updates replace an earlier version of that message; conflicting observations are
excluded. These message totals are not added to inclusive CLI terminal totals.

Reasoning tokens are a subset of Codex output. Cached Codex input is a subset of
input. Claude cache-read/cache-create are separate counters. Report provider/model
volumes separately; do not present their unweighted sum as a subscription charge.

Quota snapshots are shared-account observations. The HTML report separates observed
reset dates, limit IDs, slots and window lengths. Small timestamp jitter does not
establish a new billing window. A changed reset date, lowered percentage or missing
snapshot does not establish a refund, account change or measured savings. Do not
subtract percentages across different or uncertain windows.

This collector does not infer task identity, independently accepted work, owner
minutes or what an alternative route would have cost. Those values remain UNKNOWN.
A session containing a TaskRoute receipt may also contain unrelated work. Local
coverage is not a guarantee of complete subscription coverage.

Only numeric usage and bounded source/session/model metadata are retained; message
bodies and account balances are not copied. Reports contain local paths and session
IDs, so keep them local unless the owner explicitly authorizes sharing.

## Verification and rollback

The original seven-day local pilot was replayed byte-identically and selected
session totals matched cumulative counters. Packaged fixtures cover deduplication,
foreign history, conflicting usage, partial lines, date boundaries, Claude updates,
frozen prefixes, safe HTML and CLI output preservation. This proves importer behavior,
not causal savings or complete billing coverage.

No scheduled collection is enabled by installation. To return to the previous
plugin, use the documented native pinned-catalog procedure with `v0.3.1`; preserve
report directories. Never edit an installed cache manually.

## Workload hotspots and service history

The report ranks the top ten sessions, projects and models separately for each
provider by uncached input, output and response count. Shares use the complete
observed provider cohort, not just the top ten. Expand the desired ranking in HTML;
CSV exports contain every row. Session IDs identify chats; they do not identify
accepted tasks. A session can span multiple projects or configured models.

Normalized tables retain uncached input, cache read, cache write and output as
separate metrics. Mean uncached input per response is descriptive, not full context
size. No token weights or dollar prices are assumed. High volume identifies where
to investigate; it does not prove wasted work, polling, quality or causal savings.

Optionally add `--account-usage /path/to/account.json` to import a previously saved
Codex `account/usage/read` receipt. The JSON must contain `observed_at` (with offset),
`method`, empty `params`, and `response.result.dailyUsageBuckets` with `startDate`
and nonnegative integer `tokens`. Null buckets mean unavailable. Duplicate dates
are rejected. Only date labels from the start date inclusive to the end date
exclusive are selected; partial-day periods cannot be aligned to these buckets.
The report stores the snapshot hash and observation timestamp, not credentials.

Service history is a separate section. Its timezone, reporting lag and parity with
the website are not established. Never add it to local totals, subtract the two as
missing usage, or turn it into per-chat subscription charges. This import is offline;
it does not fetch or refresh an account. Claude personal server history and exact
subscription attribution remain unavailable. No stale stats-cache is imported.
