# W2 current-state evidence (read-only, captured 2026-09-14 before any edit)

Slice: `add-admin-jobs-console` (W2 任务运行面) on branch `feat/admin-jobs-console`
(parent `feat/admin-audit-logs` @ `08b8e4d9`).

Command set used: `git worktree list`, `crontab -l`, `ls deploy/`, grep over
`apps/admin-console/backend/**` + `apps/miroflow-agent/scripts/**`, and read-only reads of the
18188 launcher files in the (untouched) `canonical-v2-s11-consolidation` worktree.

## 1. What "任务" exists today

| Fact | Evidence |
|---|---|
| No scheduler is running: crontab has exactly two entries — backup `17 3 * * *` and access-log purge `41 3 * * *`. No collection entry. | `crontab -l` |
| `deploy/cron/` does not exist; §5.2's declarative cron table (`mirothinker-collect`) was never created. | `ls deploy/cron` → No such file or directory |
| The only in-repo scheduler (`backend/seed_cron.py`, APScheduler professor monthly rescrape) has no caller on the V2 shell. | `main.py` router list |
| The §5.3 collection scripts all exist under `apps/miroflow-agent/scripts/`: `run_company_news_ingest.py`, `run_company_official_product_capture.py`, `run_paper_search_backfill.py`, `run_paper_summary_zh_backfill.py`, `run_paper_doi_verify.py`, `run_profile_bio_rescrape.py`, `run_homepage_paper_ingest.py`. | `ls apps/miroflow-agent/scripts/` |
| §4-C3 task-ops actions exist only on the **unmounted** legacy SPA router: `POST /api/pipeline/runs/{run_id}/milvus-backfill`, `POST /api/pipeline/runs/{run_id}/retrieval-validation` (`backend/api/pipeline.py`). The V2 shell does not include that router, so both are 404 today. | `main.py` includes chat/operations/consumers/corrections/manual-recall/access-logs/admin-config only; `api/{path:path}` catch-all returns 404 |

## 2. Script entry points and idempotency facts (for a fixed-argument whitelist)

| Script | Entry | Writes by default? | Notes |
|---|---|---|---|
| `run_company_news_ingest.py` | `--priority top200|others|all`, `--connector …`, `--dry-run` | writes rows | web-search (Serper) quota sensitive |
| `run_company_official_product_capture.py` | `--input/--sheet-name/--limit/--max-pages/--dry-run/--output` | writes | bounded by `--limit` (default 20) |
| `run_paper_search_backfill.py` | `--limit`, `--dry-run`, … | writes | academic API quota |
| `run_paper_summary_zh_backfill.py` | `--limit`, … | writes | LLM quota |
| `run_paper_doi_verify.py` | `--limit`, `--dry-run` | writes | LLM quota |
| `run_profile_bio_rescrape.py` | dry-run **is the default**; writes need `--apply --confirm-real-db` | no | crawler + LLM |
| `run_homepage_paper_ingest.py` | `--resume` (`nargs="?"`), `--dry-run`, `--limit` | writes | resumable |
| `scripts/run_milvus_backfill.py` | `--domain {paper,professor,company,patent}`, `--milvus-uri`, `--dry-run`, `--limit` | writes | **requires `DATABASE_URL`** (`sys.stderr.write("DATABASE_URL is required for Milvus backfill.")`) |
| `apps/admin-console/scripts/host_e2e_agentic_rag.sh` | `bash` + env `HOST_E2E_BASE_URL`/`HOST_E2E_LOG_FILE` | runs the live e2e suite | **PG-shaped**: `DEFAULT_DATABASE_URL="postgresql://miroflow:miroflow@localhost:15432/miroflow_real"` |

## 3. `pipeline_run` and the serving host

- `pipeline_run` is a Postgres table (`src/data_agents/storage/postgres/pipeline_run.py`); every
  historical use of it in W2's target area (SPA pipeline router) writes through `get_pg_conn`.
- The 18188 service process is launched by `serve_s12e_port.py` → `complete_candidate_runner.py`
  with `--database-url postgresql://miroflow@127.0.0.1:55458/…` as a **CLI argument**; the runner
  sets no `DATABASE_URL` / `CANONICAL_V2_DATABASE_URL` environment variable (grep over
  `complete_candidate_runner.py`).
- W1 (`add-admin-config-center`) `canonical_v2_admin_status.py:508-517` already reports
  `collection_history` as `unavailable("…pipeline_run history lives in the build/release database,
  not on the serving host")`.
- **Consequence for W2**: run history cannot come from `pipeline_run`. It must be a serving-side
  store. Confirmed storage convention: the two serving-side SQLite files live next to each other and
  are addressed by env (`CANONICAL_V2_ACCESS_LOG_DB`, `CANONICAL_V2_CORRECTIONS_DB`), both emitted by
  the pinned `serve-18188-command.sh` and both under
  `/var/tmp/mirothinker-canonical-v2-s12f/`. W2 follows the same pattern with
  `CANONICAL_V2_JOBS_DB` (+ a documented same-directory default derived from the access-log DB).

## 4. W1 surface reused (no second configuration source)

`ManagedSettingsStore` (`apps/miroflow-agent/src/data_agents/canonical_v2/managed_config.py`) already
carries everything W2's gate needs — no schema change is required:

- `collection.enabled.{company,paper,patent,professor}` (bool) → per-task switch source
- `collection.max_web_searches_per_run` (default 200) → web-search quota cap
- `collection.max_llm_calls_per_run` (default 500) → LLM quota cap
- `collection.window_start_hour_utc` / `window_end_hour_utc` (default 17/22 UTC = 01:00–06:00 CST)

`GET/PATCH /api/canonical-v2/admin/config` remains the only write path for these values.

## 5. Existing page/nav convention

`admin.html` (W1) and `logs.html` (W5) each carry the same four-link top nav
(`chat / browse / logs / admin`) as copy-pasted markup; `browse.html` has its own tabs layout and no
top nav. W2 adds a fifth page `jobs.html` with the same nav block and appends the link to the two
existing nav blocks.

## 6. Facts that differ from §5.2/§5.3 in the source plan

1. §5.2 "运行记录落 pipeline_run 表（已有）" does not hold on the serving host — see §3. W2 records
   runs in serving-side SQLite and leaves PG sync as a future decision.
2. §5.3 rows list `run_profile_bio_rescrape.py` as the monthly write task, but the script is
   **dry-run by default**; the whitelist entry therefore has to state `--apply --confirm-real-db`
   explicitly (recorded here so the choice is visible, not implicit).
3. §5.3's 论文 row pairs two scripts under one cadence; W2 declares them as two tasks with the same
   cadence so a failure can be attributed to one of them.
4. §3.2(d)'s "下次运行时间" has no source yet because no cron is installed (§1). W2 therefore
   *declares* the cadence in the task registry and computes the next fire time from that declaration;
   the installed schedule remains W6's cron table.
5. §5.5's "每脚本每轮 max calls" instrumentation does not exist inside the scripts today. W2
   enforces the *gate* (cap == 0 ⇒ refuse) and passes the effective caps to the child process as
   declared env contract; per-call counting inside the scripts is W6 work.
