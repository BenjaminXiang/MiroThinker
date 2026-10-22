# Verification: customer-site strict acceptance (2026-10-23)

Method: audit `job_run` rows (command, exit, summary), DB counts, cron, seed runs, key masks,
`task_views` availability, and rerun the relevant test suites. Service `active`, health 200.

## PASS

- `company-news-ingest`: run `b9f6141b…` succeeded, exit 0, 200/200 companies, 84 fetched,
  36 inserted; `company_news_item=109`.
- cron: `0 2 * * 1 … run_scheduled_job.py company-news-ingest`; next `2026-10-26T02:00+08:00`.
- 7 collection tasks: each latest run succeeded, exit 0, venv Python command with `--limit`;
  `task_views` all `available=true`.
- Seed: `professor_seed=185`; preview run `abe9de28…` succeeded; sample job
  `fcc493e7-4438-4f90-9d46-fee773a54023` succeeded, `items_processed=1`.
- DeepSeek: managed/legacy suffixes `…504b`, 0600; chat resolver suffix `…504b`;
  `GET https://api.deepseek.com/v1/models` 200; job env key matches.
- Excel: four-domain analysis high; live structured ingest verified for company (2), professor (1+
  seed), patent (1), paper (1); test rows cleaned; 18 tests passed.
- Admin: `operator=admin` manual news run succeeded; password not reset/verified.
- Tests: 125 passed / 2 skipped (jobs+seeds+excel+manual recall API); 37 passed (news).

## FAIL / blocked

- `/upload` structured page: requires build-time PG and missing `run_admin_upload_import.py`.
- 3 ops tasks: `postgres_unavailable`.
- Uploaded content chat auto-recall: manual provider active, lane appends 3 chunks (top cosine
  0.8754), but answer evidence retention drops them.
