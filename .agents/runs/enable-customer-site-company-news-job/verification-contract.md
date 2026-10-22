# Verification contract: enable-customer-site-company-news-job

Change: `openspec/changes/enable-customer-site-company-news-job/`

## RED before implementation

- R1: `company-news-ingest` manual run fails in 3 ms with `FileNotFoundError: 'uv'`
  (`job_run.stderr_excerpt`), `breaker_open=1`.
- R2: customer candidate DB has no `company_news_item`; `miroflow_collection_v1` does not exist.
- R3: `/jobs` shows `next_run_at` = 10:00 for `schedule_display` 02:00 (UTC/local mismatch).
- R4: no cron/timer writes `trigger_source='schedule'`; `job_run` has only manual rows.

## GREEN checks

| ID | Check | Command / evidence |
|---|---|---|
| G1 | New DB + 42 tables | `information_schema.tables` count 42; required tables exist |
| G2 | ETL counts | `company=7089`, `company_snapshot=7089`, `company_news_item=0`; duplicate credit codes = 0 |
| G3 | Bounded direct run | `--priority all --limit 2 --connector serper`; `company_news_item > 0`; `pipeline_run` row |
| G4 | Runner rewrite | `job_run.command_json[0]` is the service venv Python; no `uv` error |
| G5 | Job DSN | child `DATABASE_URL` = `miroflow_collection_v1`; console `postgres.available=false` unchanged |
| G6 | Page manual run | `job_run.status='succeeded'`, items > 0, breaker reset/clear |
| G7 | Schedule run | wrapper invocation writes `trigger_source='schedule'` and `succeeded` |
| G8 | Timezone | `next_run_at` Monday 02:00 local (`Asia/Shanghai`) |
| G9 | Serving health | `/api/health` 200, `/main` 200, `/chat` real turn |
| G10 | Docs | user manual/tutorial/PDF + internal ops manual updated; OpenSpec acceptance filled |

## Regression

- Jobs unit tests (`uv run` rewrite, job DSN, timezone).
- Admin console jobs tests.
- `/chat` one real turn; no retrieval/answer change.
