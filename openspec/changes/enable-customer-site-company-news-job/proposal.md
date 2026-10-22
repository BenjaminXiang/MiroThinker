# Proposal: enable-customer-site-company-news-job

## Why

The customer site (`100.64.0.96`) currently exposes the admin Jobs page but cannot run
`company-news-ingest`:

- the task argv is `uv run python ...`, while the host has no `uv`;
- the serving candidate DB has only `canonical_v2_alembic_version`, so the script has no
  `company`, `company_snapshot` or `company_news_item` tables and no `DATABASE_URL`;
- no W6 scheduler is installed, so the declared weekly cadence never fires; the jobs history is
  empty until an operator manually clicks and fails.

Two manual runs failed in 3 ms with `FileNotFoundError: 'uv'`, and the task is now breaker-open
(`consecutive_failures=2`). The product decision (2026-10-22) is to make this **one** task run
locally on a weekly schedule (option B), without changing the serving candidate DB or the serving
pack.

## What Changes

- Add a dedicated raw collection database on the customer PG (`miroflow_collection_v1`) created
  from the existing 42-table collection schema; populate `company` and `company_snapshot` from
  the canonical company projection already present on the host.
- Add a **DeepSeek Search** news connector (domestic key; no overseas Serper payment) with
  encyclopedia/registry/report noise filtering; Serper remains optional/fallback only.
- Make the job runner execute the service venv Python instead of `uv` and hand the child a
  job-only `DATABASE_URL` (the console's own PG status is unchanged).
- Add a weekly cron wrapper for `company-news-ingest` at Monday 02:00 server-local time.
- Fix `next_run_at` to be computed in the configured local timezone.
- Scope: **only `company-news-ingest`**. Other collection/import/seed/ops tasks remain
  platform-side and out of scope.

## Capabilities

### Modified Capabilities

- `admin-jobs-console` — customer-site `company-news-ingest` execution, job-only DB DSN,
  local-time next fire, scheduled trigger.

## Impact

- New customer DB and ~7k ETL rows; no change to the serving candidate DB, serving pack, index,
  retrieval, answer, or `/chat`.
- Service restart required for the code/env change (6–10 minutes).
- Rollback: remove cron, revert `jobs.py`/`run.sh`, restart, drop the new DB.
