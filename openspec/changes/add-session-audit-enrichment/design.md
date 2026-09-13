# Design: add-session-audit-enrichment

## 1. Constraints that shape the design

- **Fail-open recording chain** (`canonical_v2_access_log.py` docstring, `_record_access_turn`): a
  logging failure must never break a chat turn. Any migration or schema decision therefore has to
  fail into "no logging", never into "chat error", and must not require the chat path to know about
  the schema at all.
- **Two live databases in the field** (v1, no identity column) plus an unknown number of future ones.
  The upgrade must be in place, idempotent, and lossless.
- **The cron purge script is stdlib-only** (`python3 - <<'PY'` heredoc, no `uv`, no application
  import) and runs unattended at 03:41. It must never fail closed in a way that deletes more than
  intended.
- **Privacy minimization (D5)**: identity only, no IP.
- **No new page, no new front-end stack** (plan §3.1: `/logs` is extended).

## 2. Identity storage, anonymous marker, and the migration/rollback decision

**Stored value.** `turns.user_identity TEXT NULL` holds the *effective identity*: the trimmed
`X-Remote-User` header value, truncated to 120 characters, or the literal marker `anonymous` when
the header is absent or blank. Reads normalize legacy `NULL`/empty to the same marker with
`COALESCE(NULLIF(user_identity, ''), 'anonymous')`, so "pre-migration row" and "public-zone visitor"
render identically — which is the honest reading: neither is an authenticated identity.

**Why not store `NULL` for anonymous.** A single non-null marker keeps every read path (filter,
export header, statistics, page) free of tri-state logic, and makes the SQL that the reconciliation
test compares against identical to the SQL the endpoint runs.

**Why not denormalize onto `sessions`.** The session's identity is derived (`SELECT DISTINCT
user_identity ... WHERE session_id = ?`, same shape as the existing `statuses` derivation). One
writer, one source of truth, no backfill.

**Why the schema marker is not bumped.** `_initialize_schema` refuses to open a database whose
`schema_version` differs from `SCHEMA_VERSION`. Bumping the marker to `v2` would make a rollback to
pre-W5 code refuse to open a migrated database — i.e. rollback would disable access logging
altogether, contradicting the plan's rollback line ("回滚即摘除新功能（记录列保留无害）"). Instead:

- the marker keeps naming the **base** schema (`canonical-v2-access-log-v1`);
- the additive column is detected **structurally** (`PRAGMA table_info(turns)`), and added when
  missing, inside the same transaction as the rest of the schema bootstrap;
- old code reading the migrated database still works: it never `SELECT *`s and never names
  `user_identity`, so the extra column is inert. Pre-W5 recording behavior resumes, identity just
  stops being captured.

This keeps the migration detection honest (it is driven by the actual table shape, not a promise)
and keeps both directions — upgrade and rollback — non-destructive. `SCHEMA_VERSION` continues to
guard the base shape, and a genuinely incompatible future change still bumps it.

**Failure mode.** If the `ALTER` cannot run (read-only or corrupt database), the store constructor
raises, the runner's `_compose_access_log_store` degrades to `None`, and chat keeps working with no
audit trail — the pre-existing fail-open contract. Nothing is half-migrated: the `ALTER` and the
marker write share one transaction.

## 3. Filter semantics

All filters are **session-level** and combine with AND. A session matches when it has *at least one
turn* satisfying each active constraint. Constraints are not required to be satisfied by the same
turn (a session that had an error on turn 2 and a `G` turn 5 matches `status=error & query_type=G`).

| Parameter | Turn-level predicate |
|---|---|
| `q` | `session.first_query LIKE %q%` OR any turn `query LIKE %q%` (unchanged) |
| `status` | `status = ?` (unchanged) |
| `query_type` | `query_type = ?` (exact, including the empty string for turns with no recorded type) |
| `identity` | `COALESCE(NULLIF(user_identity,''),'anonymous') = ?` |
| `since` / `until` | `started_at >= since AND started_at <= until` |

**Time bounds.** `started_at` is stored as a fixed-width UTC ISO-8601 string
(`...T13:11:10.743251+00:00`), so lexicographic comparison is the correct comparison and uses the
existing `turns_started_at` index. Accepted inputs: `YYYY-MM-DD` (a whole inclusive UTC day —
`since` → `T00:00:00+00:00`, `until` → `T23:59:59.999999+00:00`) or an ISO-8601 datetime **with an
explicit offset** (converted to UTC). A naive datetime is rejected: silently assuming a timezone in
an audit query is the failure mode this slice exists to remove. `since > until` is rejected.

**`query_type` picker is data-driven.** Because stored values are composite
(`canonical_v2:<behavior_class>:<response_mode>`), the page must not hard-code A–G. The `/stats`
response carries the observed `query_types` (and `identities`) facet lists, and the picker is built
from them; the API contract itself accepts any exact stored value, so the letter-level view remains
reachable (`query_type=canonical_v2:A:answer`).

## 4. Export contract

`GET /api/canonical-v2/admin/access-logs/export?format=csv|jsonl` reuses the *same* validation
helper as `/sessions`, plus `max_turns` (100..20000, default 5000). Rows are the turns of the
matching sessions, in the page's session order (`last_active_at DESC, session_id ASC`) and then
`turn_count ASC`, so a truncated export is a deterministic prefix. The response is an attachment
with `X-Access-Log-Sessions`, `X-Access-Log-Turns`, and `X-Access-Log-Truncated` headers.

CSV and JSONL carry the *same field set* the page renders per turn (identity, session id, turn
ordinal, `query_type`, status, timestamps, latency, answer style, question, answer, error detail,
citations, suggested follow-ups), so "export equals what the page shows" is a mechanical comparison
rather than a judgement call. UTF-8 without BOM, CSV with `\r\n` line terminators (Excel-friendly);
citations and follow-ups are JSON strings in CSV and native arrays in JSONL.

Rows are read under the store lock in one bounded query (`max_turns` ≤ 20000), so a long export
never blocks chat recording for the duration of a download.

## 5. Statistics definitions (must reconcile with SQL)

`GET /access-logs/stats` takes the same filter set plus `top_limit` (1..50, default 10). When `since`
is omitted the window defaults to the last 30 days (reported back as `window.since_defaulted`), so
an unfiltered call is bounded.

Statistics are computed **over turns** (not sessions): a turn is counted when it matches the window
and every active constraint. This differs deliberately from the session list (which matches a
session when *any* turn matches) and is stated in the spec so the two never have to agree.

- `totals.sessions` = `COUNT(DISTINCT session_id)`; `totals.turns` = `COUNT(*)`.
- `totals.errors` / `totals.interrupted` = per-status counts; `error_rate` = `errors / turns`,
  rounded to 4 decimals, `0.0` when there are no turns.
- `daily[]` = per UTC date of `started_at`: `{day, turns, sessions}`.
- `query_types[]` / `identities[]` = turn counts per exact `query_type` / effective identity.
- `top_queries[]` = turn counts per `TRIM(query)`.
- Every list is ordered by count descending then key ascending, so results are deterministic.

## 6. Retention read path

Source of truth stays W1's managed settings file. Resolution order for the purge script is
*positional argument > `CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS` > settings file
`paths.access_log_retention_days` > 90* — mirroring the loader's `env > file > default` precedence so
the page and the cron job can never disagree about the effective value. The script carries a small
stdlib reader (json + range check 1..3650); an unreadable file, an unexpected type, or an
out-of-range value falls back to 90 **with a warning on stderr** rather than failing the cron job or
extending retention silently. The script prints which source won, so the cron log answers "why did it
purge N days" without reading the code.

`/logs` displays the effective value and its source by reading the existing
`GET /api/canonical-v2/admin/config` (no new endpoint, no second configuration source); a failure
there degrades the line to "—" and never blocks the audit page.

## 7. Verification surface

Deterministic module + HTTP contract ⇒ RED is unit/contract level, and GREEN adds a real server
smoke on a scratch port with scratch databases.

1. **Migration (unit, real sqlite file)**: build a genuine v1 database with the pre-W5 DDL, insert
   rows, open it with the new store, and assert (a) the marker is unchanged, (b) old rows survive
   byte-for-byte on the fields that existed, (c) old rows read as `anonymous`, (d) new writes carry
   identity, (e) re-opening is idempotent, (f) the pre-W5 reader query set still works.
2. **Filter/export/stats (contract, HTTP)**: combination correctness per dimension, 4xx matrix,
   export-vs-detail equality on a sample, and statistics reconciled against direct SQL over the same
   fixture database.
3. **Fail-open**: a recording failure (naive timestamp) still records nothing and raises nothing; a
   chat-shaped record through the HTTP layer with and without `X-Remote-User`.
4. **Retention (integration)**: the real `deploy/purge-access-logs.sh` executed against a scratch
   database and scratch settings file for all four precedence levels, asserting the surviving row
   set.
5. **Real server**: scratch port 18289 (never 18188) with scratch env, exercising
   write→filter→export→stats with `X-Remote-User`, plus the `/logs` page load.

Mock boundaries: none for storage (real SQLite files); the HTTP tests use the app's own TestClient;
the smoke test uses a real uvicorn process and `curl`/HTTP calls. No oracle depends on wall-clock
time inside the store (all timestamps are fixture-controlled) except the statistics window default,
which is asserted through the returned `window` fields.
