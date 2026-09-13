# Verification: add-session-audit-enrichment (W5 用户会话审计增强)

Change: `openspec/changes/add-session-audit-enrichment/`
Branch: `feat/admin-audit-logs` · Worktree: `.worktrees/admin-audit-logs`
Contract: `verification-contract.md` (written before any production-code edit)
Date: 2026-09-14

Layered evidence below: ① new tests written this slice, ② pre-existing regression suites
before/after, ③ real-interaction evidence on a scratch port. Aggregate "all green" counts are not
used as evidence anywhere.

---

## ① New tests written this slice — 3 files / 28 tests, all pass

Command:
`cd apps/admin-console && uv run pytest -q -p no:randomly tests/test_canonical_v2_access_log_migration.py tests/test_canonical_v2_access_log_filters_export_stats.py tests/test_purge_access_logs_retention.py`
Result: **28 passed in 0.59s**.

| File | Tests | What it locks | Fixture source |
|---|---|---|---|
| `tests/test_canonical_v2_access_log_migration.py` | 4 | Legacy database (built with the verbatim pre-W5 DDL + `canonical-v2-access-log-v1` marker) gains `user_identity` in place; every pre-existing row/value survives; legacy rows read as `anonymous`; the marker stays v1 so a pre-W5 reader still opens the file (rollback contract); repeated opens are idempotent; existing indexes survive and the new identity filter works on migrated data | Constructed legacy SQLite file (real file, real DDL) |
| `tests/test_canonical_v2_access_log_filters_export_stats.py` | 17 | `X-Remote-User` capture at the record choke point (present → value, absent → `anonymous`), fail-open when the store write fails; identity normalization (trim/120-cap/blank→anonymous); identity exposed on list + detail; time-range filtering (date-only, offset-bearing datetimes, `until`-only); AND-combination of status+query_type+identity+window; the empty-`query_type` bucket; empty page for unknown identity; the 4xx matrix (malformed/naive/`since`>`until`/over-long/empty identity); CSV+JSONL export equals session-detail content field-by-field; export honours filters, reports truncation and refuses unknown format; statistics reconciled against direct SQL over `turns`; default 30-day window, empty window, `top_limit` bounds | Constructed scenario (4 identities/sessions × statuses/types/days) |
| `tests/test_purge_access_logs_retention.py` | 7 | The real `deploy/purge-access-logs.sh` resolves retention as positional arg > env > managed settings file > 90 (all four levels), reports the winning source, warns + falls back on invalid/unreadable values, skips a missing database, and deletes sessions emptied by the window | Real script executed via `subprocess` against scratch SQLite files + scratch settings files |

### RED → GREEN

`red-run-before-change.txt` is the same three files run with the six production files stashed
(pre-change code), `--continue-on-collection-errors`:

```
10 failed, 1 passed, 1 error in 0.36s
ERROR tests/test_canonical_v2_access_log_filters_export_stats.py   (ImportError: cannot import name 'ANONYMOUS_IDENTITY')
FAILED tests/test_canonical_v2_access_log_migration.py::test_legacy_database_migrates_in_place_without_data_loss
FAILED tests/test_canonical_v2_access_log_migration.py::test_migrated_database_stays_readable_by_the_pre_w5_reader
FAILED tests/test_canonical_v2_access_log_migration.py::test_reopening_a_migrated_database_is_idempotent
FAILED tests/test_canonical_v2_access_log_migration.py::test_migration_keeps_indexes_and_new_identity_filter_works
FAILED tests/test_purge_access_logs_retention.py::test_managed_settings_file_drives_the_purge_window
FAILED tests/test_purge_access_logs_retention.py::test_environment_outranks_the_settings_file
FAILED tests/test_purge_access_logs_retention.py::test_positional_argument_outranks_everything
FAILED tests/test_purge_access_logs_retention.py::test_missing_settings_file_falls_back_to_the_default
FAILED tests/test_purge_access_logs_retention.py::test_invalid_configured_values_warn_and_fall_back
FAILED tests/test_purge_access_logs_retention.py::test_purge_also_removes_sessions_emptied_by_the_window
```

The one passing pre-change test is `test_missing_database_is_skipped` (behavior unchanged by design).
After the change the same command is **28 passed** (GREEN), i.e. every RED is closed.

---

## ② Pre-existing regression suites — before vs after on this branch

Both runs: `cd apps/admin-console && uv run pytest -q -p no:randomly`, full output saved.

| Run | Result | File |
|---|---|---|
| Before (commit `852a85b7`, W5 changes absent) | **96 failed, 1024 passed, 29 skipped, 122 errors** in 188.81s | `full-suite-before.txt` / `failures-before.txt` (218 lines) |
| After (W5 working tree) | **96 failed, 1052 passed, 29 skipped, 122 errors** in 183.12s | `full-suite-after.txt` / `failures-after.txt` (218 lines) |

- passed **+28** = exactly the new test file count; failed/errors identical.
- `comm` diff: `failures-new.txt` = **0 bytes**, `failures-fixed.txt` = **0 bytes** → **zero new failures,
  zero removed**.
- Access-log / purge scoped check: `grep -E "access_log|purge_access" failures-after.txt | wc -l` = **0**.
- The 218 pre-existing FAILED/ERROR lines are unrelated to this change: they are the same set W1
  recorded on its own branch and are environment/data-dependent English-language lines
  (`test_review_workspace`, `test_chat_v1`, `test_admin_professor_api`, `test_seeds_api`, …), i.e. the
  branch's baseline red, not a W5 regression. No attempt was made to fix them (out of scope).
- Focused cluster re-check (not the full suite): access-log store/api/migration/filters-export-stats +
  purge + admin-config + managed-settings store → **86 passed in 0.84s**.

Runs of the full suite this session: 2 (before, after) — no repeated re-runs.

---

## ③ Scratch-port real interaction (port 18289, never 18188)

Harness: `scratch-18289-smoke.sh` + `scratch_18289_server.py` + `scratch-18289-checks.py`.
Setup: real `backend.main.app` (bare V2 shell) + a **real `AccessLogStore`** over a **read-only copy**
of the live database `/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3`
(`/tmp/w5-scratch/data/access-logs-copy.sqlite3`), scratch managed settings at
`/tmp/w5-scratch/managed/settings.json`. Nothing live was read-write; the live 18188 process was not
restarted and still answers `GET /api/health → 200` after the smoke. The scratch server was stopped
afterwards (18188-only listener remains).

21 real HTTP calls, statuses in `scratch-18289-status.txt`: page + reads `200`, invalid filters `422`,
unknown export format `422`, everything else `200`. Six assertions, computed in
`scratch-18289-checks.json` (all **PASS**):

| # | Assertion | Real output | Evidence file |
|---|---|---|---|
| 1 | `X-Remote-User` write → identity visible | `POST /scratch/record` with `X-Remote-User: smoke-auditor` → 200; `sessions?identity=smoke-auditor` returns exactly that session with `identities=["smoke-auditor"]`; detail turn `user_identity="smoke-auditor"`; stored column value `smoke-auditor`; the header-less write stores `anonymous` | `scratch-18289-write-turn.json`, `scratch-18289-sessions-identity.json`, `scratch-18289-session-detail.json`, `scratch-18289-session-detail-anon.json` |
| 2 | Combined filter (window + `query_type` + identity + status) correct | HTTP `total=40` == direct SQL `40`; `query_type=""` bucket HTTP `34` == SQL `34`; naive datetime → `422 {"detail":"since must carry an explicit UTC offset"}`; `since`>`until` → `422 {"detail":"since must not be later than until"}` | `scratch-18289-filtered-combined.json`, `scratch-18289-filtered-empty-bucket.json`, `scratch-18289-filtered-invalid.json`, `scratch-18289-filtered-invalid-order.json` |
| 3 | Export equals what the page shows | 1071 CSV rows == 1071 JSONL rows; sample = 3 busiest sessions + the 2 smoke sessions = **11 turns compared field-by-field** against `/sessions/{id}` (identity, query, answer, status, error detail, latency, timestamps, citations, follow-ups) → **0 mismatches**; `format=xlsx` → 422 | `scratch-18289-checks.json`, `scratch-18289-export-sample.csv/.jsonl`, `scratch-18289-export-bad-format.json` |
| 4 | Statistics reconcile with the `turns` table | HTTP `{sessions:644, turns:1071, errors:18, interrupted:3, error_rate:0.0168}` == SQL `[1071, 644, 18, 3]`; per-day / query-type / identity / Top-query lists all equal the SQL aggregates (6/6 checks true); default window = 30 days (`since_defaulted=true`); empty window = zeros + `error_rate 0.0` | `scratch-18289-stats.json`, `scratch-18289-stats-default.json`, `scratch-18289-stats-empty.json` |
| 5 | Retention read from the managed configuration, default 90 unchanged | `GET /api/canonical-v2/admin/config` → `paths.access_log_retention_days = 45, source="file"`; purge with the scratch settings → `retention_days=45 source=file`; purge with no settings → `retention_days=90 source=default`; a 20-day window really deletes: `purged turns=461 sessions=276`, survivor days start at 2026-09-07 | `scratch-18289-admin-config.json`, `scratch-18289-purge.txt` |
| 6 | No IP recorded (privacy minimization) | `turns` columns contain no ip/addr/user-agent/cookie column; regex scan for `\d{1,3}(\.\d{1,3}){3}` finds **0** hits in session detail, session list, both export formats, the config response, and in 200 stored rows | `scratch-18289-checks.json`, `scratch-18289-db-after.json` |

Migration on real data (same copy, before → after): marker `canonical-v2-access-log-v1` →
`canonical-v2-access-log-v1` (**unchanged**), columns `…latency_ms` → `…latency_ms, user_identity`
(appended, none removed/reordered), sessions 918 → 920, turns 1530 → 1532 (+2 smoke writes) —
`scratch-18289-db-before.json` / `scratch-18289-db-after.json`.

Page artifact: `GET /logs → 200` with the extended page (`scratch-18289-page-logs.html`,
32 KB). Its inline script was syntax-checked with `node --check` (no `innerHTML`, matching the
existing static-page convention).

Two harness bugs were found and fixed during this step (they were in the **checks**, not the
product): CSV rows were parsed after `splitlines()` (breaking quoted newlines), and the first
combined-filter probe window (2026-09-01..02) is genuinely empty in the live corpus — the live
per-day distribution has a gap between 2026-08-19 and 2026-09-07. The corrected probe
(2026-08-10..13, 40 matching sessions) is what the numbers above report.

---

## Not verified (stated plainly)

1. **Not deployed.** No hot update to `release/customer-test`, no restart of 18188, no nginx
   admin-zone change. The change is verified on a scratch port against a copy; the live service
   still runs pre-W5 code.
2. **The chat endpoint itself was not driven end-to-end.** The bare V2 shell has no serving-pack
   runtime, so `POST /api/chat` cannot serve a turn there. Identity capture was exercised over real
   HTTP through the real `_record_access_turn` choke point (the single place the chat endpoint calls
   it), not through a full chat turn.
3. **No browser rendering assertion.** The page is served and its markup/JS were reviewed and
   syntax-checked; DOM behavior (overview tables, filter widgets) was not asserted in a real browser.
4. **Pre-existing fail-open gap observed, not fixed:** `_record_access_turn` computes `latency_ms`
   before calling the store, so a *naive* `started_at` raises `TypeError` outside the store's
   try/except. In production `started_at` always comes from `_utc_now()` (tz-aware), so this is
   unreachable; it is out of scope for this slice and is recorded here rather than patched.
5. The 218 pre-existing suite failures remain (env/data-dependent, unrelated to W5).
