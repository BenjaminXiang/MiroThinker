# Proposal: add-session-audit-enrichment

## Why

The authoritative product plan
(`docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §1.4, §4 **D5**, §6 **W5**)
scopes user-session auditing as an independent slice of the wrap-up. `/logs` already replays sessions
and turns, but it cannot answer the four audit questions an operator actually asks: *who* asked,
*when*, *which kind* of question, and *what is the aggregate shape* of usage over a window. There is
also no way to leave the page with the data (no CSV/JSONL) and no way to see or change how long
records are kept.

The five gaps (§1.4) are: (1) no user identity dimension, (2) no time-range or `query_type` filter,
(3) no export, (4) no overview statistics, (5) the 90-day retention is hard-coded in the purge script
and invisible on the page.

Current-state facts verified read-only against the two live access-log databases on 2026-09-14
(`/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3`: 960 sessions / 1599 turns;
`/var/tmp/mirothinker-data-v2/access-logs.sqlite3`: 557 sessions / 696 turns), both at
`schema_version = canonical-v2-access-log-v1`:

- `turns` has 14 columns and no identity column; `sessions` has no identity column either.
- Observed `query_type` values are **composite**: `canonical_v2:A:answer` (1471),
  `canonical_v2:G:clarification_only` (86), `canonical_v2:F:safety_guidance` (6), and `''` (36).
  §1.4's shorthand "query_type（A–G）" is a *behavior class embedded in a string*, not a bare letter —
  the filter contract below is written against what is actually stored, and the page's `query_type`
  picker is populated from observed values rather than a hard-coded A–G list.
- `turns.started_at` carries an index (`turns_started_at`) that no HTTP surface uses.
- The live databases are the "new and old" migration cases this slice must not damage.

W1 (`add-admin-config-center`) already ships `paths.access_log_retention_days` in the managed
settings schema (default 90, env `CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS`). This slice supplies the
missing **reading end** (the cron purge script) instead of inventing a second configuration source.

## What Changes

Behavior-affecting: new public admin API surface, an additive access-log data-contract change, and a
new operator-visible page behavior. No retrieval, fusion, rerank, answer, or serving-pack behavior is
touched; the chat recording path stays fail-open.

1. **Record side** — `turns.user_identity` (an additive nullable column) stores the authenticated
   identity taken from the `X-Remote-User` header (the nginx `auth_basic` zone). No header, or a
   blank header, records the literal marker `anonymous`. **No IP address, cookie, or user-agent is
   recorded** (D5 privacy minimization).
2. **Lossless in-place migration** — an existing v1 database gains the column by `ALTER TABLE` at
   open time; existing rows keep `NULL` and are read as `anonymous`. The schema marker is
   deliberately **not** bumped (see `design.md` §2): a rollback to pre-W5 code still opens the
   migrated database, which is the plan's declared rollback path.
3. **Filter side** — `GET .../access-logs/sessions` gains `since`, `until`, `query_type`, and
   `identity` parameters that combine (AND) with the existing `q` / `status`.
4. **Export** — `GET .../access-logs/export?format=csv|jsonl` emits exactly the turns of the
   currently matching sessions under the same filter set, bounded by `max_turns`.
5. **Statistics** — `GET .../access-logs/stats` reports sessions/turns per UTC day, the `query_type`
   distribution, the error rate, Top queries, and the observed identities, over an explicit or
   default (last 30 days) window.
6. **Retention** — `deploy/purge-access-logs.sh` resolves its retention window as
   *positional argument > `CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS` > managed settings file `paths.access_log_retention_days` > 90*
   (stdlib only — the cron job must not import the application stack), and `/logs` displays the
   effective value and its source.
7. **Page** — `logs.html` is extended (no new page): filter row, overview panel, export buttons,
   retention line, and identity display; anonymous/unauthenticated history renders as "匿名".

## Capabilities
### Added Capabilities
- `session-audit-log` — identity capture, lossless migration, combined filtering, export,
  statistics, and the retention read path for the Canonical V2 access log.

### Modified Capabilities
- None. `add-admin-config-center`'s managed-settings schema is consumed as-is (no new field, no
  schema change); the access-log read API is extended additively under the same admin prefix.

## Impact

- `apps/admin-console/backend/services/canonical_v2_access_log.py` (identity column + migration,
  combined filters, export rows, statistics).
- `apps/admin-console/backend/api/canonical_v2_chat.py` (read `X-Remote-User` at the single record
  choke point).
- `apps/admin-console/backend/api/canonical_v2_access_logs.py` (filter validation, `/stats`,
  `/export`).
- `apps/admin-console/backend/static/logs.html` (filters, overview, export, retention line).
- `deploy/purge-access-logs.sh` (retention resolution), `deploy/README.md` (documented behavior).
- New tests: `apps/admin-console/tests/test_canonical_v2_access_log_filters_export_stats.py`,
  `apps/admin-console/tests/test_canonical_v2_access_log_migration.py`,
  `apps/admin-console/tests/test_purge_access_logs_retention.py`.
- No serving-pack change, no retrieval change, no `release/customer-test` hot update, no new
  dependency, no new page, no front-end stack change.

## Out of Scope

Jobs/uploads/seeds surfaces (W2/W3), issues/workbench/SPA retirement (W4), periodic collection (W6),
release pipeline (W7). Also out of scope: recording IP addresses, per-turn request forensics beyond
the authenticated identity, and any change to who may reach these endpoints (they stay behind the
existing `/api/canonical-v2/admin/*` admin-zone rule).

## Status

Proposed 2026-09-14. Implementation and verification land in the same slice; evidence in
`.agents/runs/admin-audit-logs-w5/`.

## Human doc cross-link

- Plan entry: `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §1.4 / §4 D5 / §6 (W5 row)
- Slice log (Chinese, append-only): `docs/plans/2026-09-14-session-audit-log.md`
