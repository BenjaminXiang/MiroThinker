# Verification: enable-customer-site-seed-console

Date: 2026-10-22 (Asia/Shanghai)
Customer host: `100.64.0.96` / `/root/deploy/fullstack-v2`

## 1. Code

- `backend/console_dsn.py`: `SEED_DATABASE_URL_ENV` + `resolve_seed_dsn()`; precedence
  seed DSN > `DATABASE_URL` > `DATABASE_URL_TEST`.
- `backend/api/canonical_v2_seeds.py`: explicit seed DSN bypasses the Postgres probe;
  `_seed_connection()` uses the seed DSN.
- `backend/api/seeds.py`: `get_seed_pg_conn` (used by all 6 `/api/seeds` routes);
  `_run_seed_task` uses `resolve_seed_dsn()`.
- Customer `run.sh`:
  `export CANONICAL_V2_SEED_DATABASE_URL="$MIROTHINKER_JOB_DATABASE_URL"`; `DATABASE_URL` remains
  unset.

## 2. Tests

- `test_canonical_v2_seeds_api.py`: 6 passed, 2 skipped (Postgres integration skipped).
- `test_seeds_api.py`: 30 skipped (no disposable PG in this checkout).
- New regression `test_seed_dsn_env_bypasses_the_postgres_gate`: explicit seed DSN passes with
  `postgres=false`.
- `ruff check` clean; formatted.

## 3. Live seed connection

With `CANONICAL_V2_SEED_DATABASE_URL` pointing at `miroflow_collection_v1`:

```text
seeds=185
first=95 中山大学（深圳） https://ae.sysu.edu.cn/teacher/HeXin
```

This exercises `seeds.get_seed_pg_conn()` + `list_seeds()` against the live collection DB.

## 4. Service

Restart `miro-fullstack-v2` after deploying the three files and `run.sh`; boot ~10–12 minutes.
`/api/health`, `/main`, `/chat` are re-checked after boot. Ops/upload must remain
`postgres_unavailable` because `DATABASE_URL` is still unset.

## 5. Seed trigger

- Live legacy `/api/seeds` path (`trigger_seed_run(95, preview)`):
  `status_code=202`, run `a616cf22-11be-4dc1-8853-1a49c6c6cc05`; seed 95
  `last_run_status=success`, `last_run_at` set.
- Live legacy `/api/seeds` sample crawl (`trigger_seed_run(95, sample, limit=5)`):
  `status_code=202`, run `3cddc244-6329-4f0c-aea2-8bbcfcf28369`;
  `pipeline_run.status=succeeded`, `items_processed=1`.
- Job-path `admin-seed-refresh` run `abe9de28-32eb-4036-af44-bb78fe7d8784`:
  `succeeded`, `items_processed=1`, `seed_status=success`, `trigger_mode=preview`.
- These cover the page button (`/api/seeds`) preview/sample and the job history surface.

## 6. Isolation

- Service env contains `CANONICAL_V2_SEED_DATABASE_URL` and `MIROTHINKER_JOB_DATABASE_URL`,
  but **no** `DATABASE_URL`.
- `task_views()` still reports all three ops tasks `postgres_unavailable`.
- Service: `active`, PID `1589741`, `/api/health` 200; external `/main`, `/chat` 200.
