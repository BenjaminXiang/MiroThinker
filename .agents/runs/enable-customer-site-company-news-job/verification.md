# Verification: enable-customer-site-company-news-job

Date: 2026-10-22 (Asia/Shanghai)
Deployment: `/root/deploy/fullstack-v2` on `100.64.0.96`
Service PID after restart: `2182359`; `systemctl is-active` = `active`.

## 1. Data plane

- `miroflow_collection_v1`: 42 tables.
- `company` = 7,089; `company_snapshot` = 7,089; duplicate `unified_credit_code` = 0.
- `company_news_item` before run = 5 (比亚迪 spot check).

## 2. Credential

- Managed store `/root/deploy/fullstack-v2/code/config/managed/secrets.json`:
  `llm.api_key` mask = `sk-…504b` (file 0600; backup `secrets.json.bak-*`).
- Legacy key files updated: `code/.deepseek_api_key`,
  `bootstrap/keys/.deepseek_api_key` (0600, backups kept).
- Local developer checkout: `.deepseek_api_key` and `apps/miroflow-agent/.env`
  updated to the same key (0600 backups `*.bak-*`); historical
  `.dryrun/delivery-20260909/secrets/.deepseek_api_key` left untouched.
- Scheduled wrapper `_prepare_environment()` contains `DEEPSEEK_API_KEY` ending `…504b`;
  `CHAT_LLM_PROFILE=deepseekv4flash`.
- Service process env has `MIROTHINKER_JOB_DATABASE_URL` / `MIROTHINKER_JOB_PYTHON`,
  no `DATABASE_URL`; console probe remains `{"available": false, "source": null}`.

## 3. Manual full run

Run `b25e184e-9bfc-49d7-b5df-8559c45e73e5` (trigger `manual`):

| Field | Value |
|---|---|
| status / exit | `succeeded` / `0` |
| duration | `566,370 ms` (~9m26s) |
| command | `["/root/deploy/fullstack-v2/.venv/bin/python","scripts/run_company_news_ingest.py"]` |
| companies | `200/200` |
| news fetched / inserted | `68 / 68` |
| companies with errors | `0` |
| `company_news_item` | 5 → 73 |

Serper returned `400 Not enough credits` for every company (warning only);
DeepSeek produced all 68 rows.

## 4. Scheduled path

- Cron installed (existing keepwarm preserved):
  `0 2 * * 1 cd /root/deploy/fullstack-v2 && .venv/bin/python code/apps/admin-console/scripts/run_scheduled_job.py company-news-ingest >> var/jobs-cron.log 2>&1`
- Wrapper run `7b908575-cfef-4c33-adc4-9c1d0e18655c`:
  `trigger_source=schedule`, `status=skipped`, `skip_reason=outside_window`
  (triggered 15:44 CST = 07:44 UTC; gate allows 17–22 UTC).
- `next_run_at` = `2026-10-26T02:00:00+08:00`; `schedule_display=每周一 02:00`.
- Fixed-clock regression test
  `test_scheduled_monday_0200_cst_is_inside_the_collection_window`:
  at `2026-10-26T18:00Z` with window 17–22, trigger succeeds and `inside_window=true`.
- First natural scheduled fire remains to be observed on 2026-10-26 02:00 CST.

## 5. Serving

External checks on 2026-10-22:

```text
https://gxzx-coze-api.idea.edu.cn/main        200
https://gxzx-coze-api.idea.edu.cn/chat        200
https://gxzx-coze-api.idea.edu.cn/api/health  200
```

Warm-up log: `health wait done after ~615s (http=200)`; restart started 15:20:45,
health 200 around 15:31. Non-fatal warning: Playwright headless chromium binary
missing (`/root/.cache/ms-playwright/...`), page-fetch tier may degrade; DeepSeek
news connector does not depend on it.

## 6. Tests

Repository worktree `canonical-v2-s11-consolidation`:

- `test_canonical_v2_jobs_runner.py`: 29 passed (includes venv runner replacement,
  job DSN, Asia/Shanghai `next_run_at`, Monday 02:00 window gate).
- `test_canonical_v2_jobs_api.py` + registry + store: 97 passed.
- Current branch `fix/p1-p8-systematic`:
  `test_news_connectors.py` + `test_run_company_news_ingest.py`: 37 passed
  (includes new DeepSeek filter tests).

## 7. Docs

- `docs/管理台操作手册.md` §0/§6/§11.3/§13 updated.
- `docs/管理台操作手册-图文版.md` §7/§12/§13 updated; PDF regenerated (22 pages).
- `docs/管理台运维手册.md` §7.3 table + §7.8 added.
- Human log Round 4 appended; OpenSpec tasks 3.x/4.x/5.x ticked.
