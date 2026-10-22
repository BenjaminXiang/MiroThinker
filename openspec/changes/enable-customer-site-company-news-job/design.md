# Design: enable-customer-site-company-news-job

## 1. Data plane (customer PG `127.0.0.1:5432`, container `miro-light-pg`)

### 1.1 New database

`miroflow_collection_v1` is created from a **schema-only** dump of the existing
`miroflow_collection_v1` on the build host (`gpu01`, `127.0.0.1:55458`, 42 tables, empty).
Existing customer DBs are untouched:

- `miroflow_candidate_v2_20260922_r1` — serving candidate, 1 table;
- `miroflow_candidate_v2_20260819_r1` — canonical 88-table DB, 7,089 companies;
- `miroflow_light_lane_r1` — light lane.

### 1.2 Canonical → raw ETL

Source: `miroflow_candidate_v2_20260819_r1.company.current_projection` (7,089 rows).

`company` mapping:

| raw column | source |
|---|---|
| `company_id` | `id` |
| `canonical_name` / `registered_name` | `name` |
| `unified_credit_code` | `credit_code`; duplicates set NULL (unique constraint allows many NULLs) |
| `aliases` | `aliases` text[] → jsonb |
| `website` / `website_host` | `website` / parsed netloc |
| `hq_province` | `geography->>'name'` |
| `is_shenzhen` | name/geography contains `深圳` |
| `country` | `'国内'` |
| `identity_status` | `'resolved'` |
| `profile_summary` / `technology_route_summary` / `quality_status` | same-named canonical fields |

`company_snapshot` one row per company:

- `snapshot_kind='website_crawl'` (avoids the `xlsx_import` source-row constraint);
- `company_name_xlsx=name`; `description=profile_summary`; `team_raw=team_description`;
- `star_rating`: quality heuristic (ready=5, partial=3, needs_review/low=1) — used only for
  `top200` ordering, documented as heuristic;
- `reported_news_count=0`; `raw_row_jsonb='{}'`; `snapshot_created_at=now()`.

FK prerequisites: one synthetic `seed_registry` row (`company-canonical-backfill-v1`,
`seed_kind='company_xlsx'`, `refresh_policy='weekly'`) and one synthetic `import_batch` row
(fixed UUID, `run_status='succeeded'`).

Validation: `company=7089`, `company_snapshot=7089`, `company_news_item=0`; no duplicate
`unified_credit_code`; 5-row spot check.

### 1.3 News source and small direct run

Serper is not used: the account has a negative credit balance and the customer cannot pay
overseas. The news source is **DeepSeek Search** (`POST /v1/tools/search`, the same domestic key
as the LLM), wrapped by a new `DeepSeekNewsConnector` in
`src/data_agents/company/news_connectors/deepseek.py`:

- query `"{company} 最新新闻 动态 -招聘 -招标"`, `ori_question` carries the original question;
- filters encyclopedia/company-registry/report/stock-quote noise;
- requires a company-name or core-name match; when `date` is absent, requires a news-like URL;
- `authority >= 2`; `date` must be within `since` (or absent for a news-like URL).

Validate with `--connector deepseek --company-id <id>`: 比亚迪股份有限公司 yields 5 rows;
深圳市尚锐科技有限公司 yields 0 (no recent news; old/encyclopedia/report results are filtered).
Serper remains in the `all` selection for future credit top-up but is not required.

## 2. Job runner

`apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py`:

- `JOB_PYTHON_ENV="MIROTHINKER_JOB_PYTHON"`, `JOB_DATABASE_URL_ENV="MIROTHINKER_JOB_DATABASE_URL"`,
  `JOB_TIMEZONE_ENV="MIROTHINKER_JOB_TIMEZONE"`.
- `JobRuntime` stores `job_python` (default `sys.executable`) and `job_database_url`.
- `trigger()` resolves `("uv","run","python",...)` to `(job_python, ...)` before `start_run`, so
  history records the real command and the child never needs `uv`.
- `_default_console_dsn()` returns `job_database_url` first; `_execute` already writes it to the
  child `DATABASE_URL`.
- `task_views()` calls `cron_next_fire(..., tz=job_timezone)`; `job_timezone` is
  `ZoneInfo(MIROTHINKER_JOB_TIMEZONE)` or the host local zone. `0 2 * * 1` then renders 02:00,
  not 10:00.

`backend/api/canonical_v2_jobs.py::build_job_runtime()` passes
`console_dsn=values.get("MIROTHINKER_JOB_DATABASE_URL")`.

## 3. Environment

`/root/deploy/fullstack-v2/run.sh` adds:

```bash
export MIROTHINKER_JOB_PYTHON="$B/.venv/bin/python"
export MIROTHINKER_JOB_DATABASE_URL="postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1"
export MIROTHINKER_JOB_TIMEZONE="Asia/Shanghai"
```

The console `DATABASE_URL` remains unset, so upload/seed/ops console status is unchanged.

## 4. Scheduler

New `apps/admin-console/scripts/run_scheduled_job.py`:

1. Set `sys.path` for the admin console + miroflow-agent packages.
2. `apply_managed_runtime_config(environ=env)` to load managed secrets/settings.
3. Ensure `MIROTHINKER_JOB_DATABASE_URL`, `CANONICAL_V2_JOBS_DB`, `CANONICAL_V2_ACCESS_LOG_DB`.
4. `runtime = build_job_runtime(environ=env)`.
5. `runtime.trigger(task_id, trigger_source="schedule", operator="scheduler")`.
6. `runtime.wait_for_idle(timeout=task.timeout_seconds + 120)`.
7. Print task/run/status only; no env/secret values.

Cron: `0 2 * * 1` (server local CST) for `company-news-ingest`, logging to
`var/jobs-cron.log`.

## 5. Rollback

1. Remove the cron line.
2. Restore `jobs.py`, `canonical_v2_jobs.py`, `run.sh` from timestamped backups.
3. Restart `miro-fullstack-v2`.
4. `DROP DATABASE miroflow_collection_v1` (after optional `pg_dump`).
5. Serving candidate DB/pack/index untouched.

## 6. Out of scope

Other collection/import/seed/ops tasks; serving/retrieval/answer behavior; canonical 88-table DB
migration; changes to the serving candidate DB.
