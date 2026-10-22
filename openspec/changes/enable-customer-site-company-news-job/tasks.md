# Tasks: enable-customer-site-company-news-job

Status legend: `[ ]` pending, `[~]` in progress, `[x]` done with evidence.

## 1. Setup

- [x] 1.1 Create OpenSpec change (proposal, design, spec delta, tasks, acceptance).
- [x] 1.2 Create `.agents/runs/enable-customer-site-company-news-job/verification-contract.md`.
- [x] 1.3 Create human plan/log under `docs/plans/` and register in `docs/plans/index.md`.
- [x] 1.4 Add the change to `openspec/change-ledger.md`.

## 2. Data plane

- [x] 2.1 Dump schema-only from `gpu01:miroflow_collection_v1`; create customer DB
      `miroflow_collection_v1`; verify 42 tables.
- [x] 2.2 Run canonical → raw ETL for `company`/`company_snapshot`; verify 7,089/7,089 rows,
      no duplicate credit codes, 5-row spot check.
- [x] 2.3 Add `DeepSeekNewsConnector` (C: domestic DeepSeek Search, no overseas Serper payment)
      and validate with the service venv Python: 比亚迪股份有限公司 -> `news_fetched=5`,
      `news_inserted=5`; 深圳市尚锐科技有限公司 -> 0 (no recent news; old/encyclopedia/report
      results filtered). `company_news_item` = 5. Evidence: human log Round 3.

## 3. Job runtime

- [x] 3.1 Add `MIROTHINKER_JOB_PYTHON` / `MIROTHINKER_JOB_DATABASE_URL` /
      `MIROTHINKER_JOB_TIMEZONE` handling in `jobs.py`.
- [x] 3.2 Resolve `uv run python` to the service venv Python before recording the run.
- [x] 3.3 Pass the job-only DSN through `build_job_runtime`; console `DATABASE_URL` unchanged.
- [x] 3.4 Compute `next_run_at` in the configured local timezone.
- [x] 3.5 Add/adjust unit tests; run relevant jobs tests.

## 4. Deployment

- [x] 4.1 Back up `jobs.py`, `canonical_v2_jobs.py`, `run.sh`, crontab.
- [x] 4.2 Add the three env exports to `run.sh`.
- [x] 4.3 Restart `miro-fullstack-v2`; verify `/api/health`, `/main`, `/chat`.
- [x] 4.4 Trigger `company-news-ingest` from `/jobs`; verify succeeded + rows.
      Evidence: run `b25e184e…`, 200 companies, 68 fetched/inserted, exit 0, 566s;
      `company_news_item` 5 → 73.
- [x] 4.5 Install `run_scheduled_job.py` and the Monday 02:00 cron; run the wrapper manually;
      verify `trigger_source='schedule'` and succeeded.
      Evidence: cron installed; wrapper run `7b908575…` recorded `trigger_source=schedule`
      (skipped `outside_window` at 15:44 CST because the gate allows 17–22 UTC);
      fixed-clock test `test_scheduled_monday_0200_cst_is_inside_the_collection_window`
      proves Monday 02:00 CST (18:00 UTC) is inside the window.

## 5. Docs / acceptance

- [x] 5.1 Update user manual + illustrated tutorial: company news job is now local/weekly;
      other tasks remain platform-side.
- [x] 5.2 Regenerate the illustrated PDF.
- [x] 5.3 Update internal ops manual with DB/ETL/job DSN/cron/timezone/rollback.
- [x] 5.4 Fill acceptance evidence and verification.md; append human log.
