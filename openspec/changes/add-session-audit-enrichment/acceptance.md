# Acceptance: add-session-audit-enrichment (W5 用户会话审计增强)

Acceptance line under test (verbatim, `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §6, W5 row):

> 新老库无损升级（旧行身份为空显示匿名）；组合过滤（时间+状态+query_type+身份）结果正确；
> 导出与页面所见一致（抽样比对）；统计数字与 turns 表 SQL 对账一致

Rollback line (same row): 增量列 + 增量过滤/导出，回滚即摘除新功能（记录列保留无害）。

Evidence: `.agents/runs/admin-audit-logs-w5/` (contract, RED run, before/after suites, scratch smoke).
Branch `feat/admin-audit-logs`, worktree `.worktrees/admin-audit-logs`, not pushed, not deployed.

| # | Acceptance criterion | Verdict | Evidence |
|---|---|---|---|
| A1 | 新老库无损升级：旧库（v1，无身份列）原地加列，旧行一条不丢、值不变 | **Pass** | `test_canonical_v2_access_log_migration.py` (4 tests) — fixture built with the verbatim pre-W5 DDL; `scratch-18289-db-before.json` vs `scratch-18289-db-after.json` on a copy of the live database: marker `canonical-v2-access-log-v1` unchanged, columns only appended (`user_identity`), sessions 918→920 / turns 1530→1532 (the +2 are the smoke writes) |
| A2 | 旧行身份为空时页面显示「匿名」 | **Pass** | Reads normalize legacy `NULL`/blank via `COALESCE(NULLIF(user_identity,''),'anonymous')`; migration test asserts `identities == ("anonymous",)` and `turn.user_identity == "anonymous"` for legacy rows; the page renders `匿名` for the `anonymous` marker (`identityLabel`) |
| A3 | 回滚安全（设计文档的回滚线：摘除新功能即可，记录列保留无害） | **Pass** | Schema marker deliberately not bumped; `test_migrated_database_stays_readable_by_the_pre_w5_reader` reads the migrated file with the pre-W5 column list and asserts `marker == 'canonical-v2-access-log-v1'`; the new column is nullable and never selected by pre-W5 code |
| A4 | 组合过滤（时间 + 状态 + query_type + 身份）结果正确 | **Pass** | `test_sessions_filter_combines_status_query_type_and_identity`, `test_sessions_filter_by_time_range`, `test_sessions_query_type_empty_bucket_is_filterable`, `test_sessions_unknown_identity_is_an_empty_page`; scratch: HTTP `total=40` == direct SQL `40`, empty-`query_type` bucket 34 == 34 |
| A5 | 非法参数 4xx（不静默降级） | **Pass** | `test_sessions_reject_invalid_filter_values` (8 cases), `test_export_rejects_unknown_format_and_out_of_range_cap`, `test_statistics_honour_filters_and_reject_bad_limits`; scratch: naive datetime → 422 `since must carry an explicit UTC offset`, `since>until` → 422, `format=xlsx` → 422 |
| A6 | 导出与页面所见一致（抽样比对） | **Pass** | `test_export_csv_matches_what_the_page_shows`, `test_export_jsonl_matches_what_the_page_shows`, `test_export_honours_the_active_filters_and_reports_truncation`; scratch: 1071 CSV rows == 1071 JSONL rows, 11 sampled turns (3 busiest sessions + 2 smoke sessions) compared field-by-field against `/sessions/{id}` → **0 mismatches** (`scratch-18289-checks.json`) |
| A7 | 统计数字与 `turns` 表 SQL 对账一致 | **Pass** | `test_statistics_reconcile_with_direct_sql`, `test_statistics_default_window_and_empty_window`; scratch: totals/error-rate/daily/query-type/identity/Top-query all equal direct SQL aggregates (6/6) on 1071 real turns / 644 sessions |
| A8 | 保留期进配置中心可配、默认 90 天不变、清理脚本读它 | **Pass** | `test_purge_access_logs_retention.py` (7 tests: arg > env > file > 90, invalid → warn + 90, real deletion through the real script); scratch: config API reports `45 / source=file`, purge reports `retention_days=45 source=file` and `retention_days=90 source=default` without settings, and a 20-day window really deletes (461 turns / 276 sessions) |
| A9 | fail-open 记录链不回归 | **Pass** | Pre-existing `test_record_turn_is_fail_open_on_error` unchanged and green; new `test_record_access_turn_without_header_is_anonymous_and_fail_open` drives the real choke point with a broken store and asserts no exception; `test_duplicate_turn_id_is_idempotent` unchanged |
| A10 | 不记 IP（D5 隐私最小化） | **Pass** | `test_recorded_payload_never_carries_network_identifiers`; scratch assertion 6: no ip/addr/user-agent/cookie column, and an IP regex finds 0 hits across detail, list, CSV, JSONL, config responses and 200 stored rows (`scratch-18289-checks.json`) |
| A11 | `/logs` 扩展而非新页面 | **Pass** | `logs.html` extended in place (filters, overview panel, export buttons, retention line, identity labels); `GET /logs` → 200 (`scratch-18289-page-logs.html`); no new page, no new front-end stack, no `innerHTML` |
| A12 | No regression in the pre-existing suite | **Pass** | before 96F/1024P/29S/122E vs after 96F/1052P/29S/122E; failure-set `comm` diff = 0 new / 0 fixed (`failures-new.txt`, `failures-fixed.txt` empty); 0 access-log/purge failures |

## Not verified (explicit)

1. **Not deployed.** No hot update to `release/customer-test`, no 18188 restart, no nginx admin-zone
   change; the live service still runs pre-W5 code. W5's "counts as fixed" is demonstrated on a
   scratch port (18289) over a copy of live data, not on the live entry.
2. **Chat endpoint not driven end-to-end.** The bare V2 shell has no serving-pack runtime; the
   `X-Remote-User` path was exercised over real HTTP through the real `_record_access_turn` choke
   point that the chat endpoint calls, not through a full chat turn.
3. **No browser DOM assertion.** The page is served and reviewed; widget behavior was not asserted in
   a real browser.
4. **Not exercised:** multi-user auth_basic identities in the real nginx zone; a migrated *live*
   database (only a byte copy); retention changes made through the `/admin` page (the config API was
   read, and the write path is W1's already-verified contract).
5. **Pre-existing, out of scope, recorded not fixed:** `_record_access_turn` builds `latency_ms`
   before entering the store's try/except, so a naive `started_at` raises `TypeError` there
   (unreachable in production, where the timestamp is always `_utc_now()`).

## Rollback

- Code: revert the branch (or drop the new routes). The identity column may stay; pre-W5 code reads
  the migrated database unchanged (A3).
- Data: no destructive migration, no backfill, no rewrite of existing rows. The only data mutation is
  the additive column.
- Retention: the purge script's new resolution defaults to 90 days when no managed setting exists, so
  reverting the script restores the old behavior exactly.
