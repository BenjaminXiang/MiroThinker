# Acceptance: enable-customer-site-company-news-job

| # | Criterion | Evidence |
|---|---|---|
| A1 | Customer PG has `miroflow_collection_v1` with the 42-table collection schema | `information_schema` count = 42; `company` / `company_snapshot` / `company_news_item` exist (2026-10-22) |
| A2 | `company` = 7,089 rows, `company_snapshot` = 7,089, no duplicate `unified_credit_code` | SQL counts 7,089 / 7,089; duplicate query = 0 |
| A3 | Bounded DeepSeek run writes news | 比亚迪股份有限公司 `news_fetched=5` / `news_inserted=5`; full run `news_fetched=68` / `news_inserted=68`; `company_news_item` 5 → 73 |
| A4 | Job runner executes the service venv Python, not `uv` | `job_run.command_json = ["/root/deploy/fullstack-v2/.venv/bin/python","scripts/run_company_news_ingest.py"]`; `stderr` has no `FileNotFoundError: uv` |
| A5 | Job child receives the collection DB DSN; console PG status unchanged | wrapper env `DATABASE_URL=postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1`; console `PostgresProbe({}).describe() = {"available": False, "source": None}`; service env has `MIROTHINKER_JOB_DATABASE_URL` but no `DATABASE_URL` |
| A6 | `/jobs` manual `company-news-ingest` succeeds | run `b25e184e-9bfc-49d7-b5df-8559c45e73e5`: `status=succeeded`, `exit_code=0`, `duration_ms=566370`, 200/200 companies, 68 fetched/inserted (triggered through the same `JobRuntime.trigger` gate the page button calls) |
| A7 | Scheduled wrapper writes a `trigger_source='schedule'` run | wrapper run `7b908575-cfef-4c33-adc4-9c1d0e18655c`: `trigger_source=schedule`, `status=skipped`, `skip_reason=outside_window` at 15:44 CST (gate allows 17–22 UTC). Fixed-clock test `test_scheduled_monday_0200_cst_is_inside_the_collection_window` proves Monday 02:00 CST = 18:00 UTC is inside and records `inside_window=true`. First natural fire: 2026-10-26 02:00 CST. |
| A8 | `next_run_at` renders Monday 02:00 local | `task_views()` → `next_run_at=2026-10-26T02:00:00+08:00`, `schedule_display=每周一 02:00` |
| A9 | Serving unaffected | `/api/health` 200, `/main` 200, `/chat` 200 (external, 2026-10-22) |
| A10 | Docs/OpenSpec/human log updated | `docs/管理台操作手册.md`, `docs/管理台操作手册-图文版.md`, regenerated `artifacts/管理台操作手册-图文版.pdf` (22 pages), `docs/管理台运维手册.md` §7.3/§7.8, human log Round 4, this acceptance file |

## Rollback rehearsal

- Remove cron → restore `jobs.py` / `canonical_v2_jobs.py` / `run.sh` backups → restart → drop
  `miroflow_collection_v1`.
- Verify `/api/health`, `/main`, `/chat`; the serving candidate DB/pack/index are untouched.
