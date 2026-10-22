# Acceptance: enable-customer-site-seed-console

| # | Criterion | Evidence |
|---|---|---|
| A1 | Seed DSN resolves without `DATABASE_URL` | `resolve_seed_dsn()` returns `postgresql://miroflow@127.0.0.1:5432/miroflow_collection_v1`; service env has the seed DSN and no `DATABASE_URL` |
| A2 | Seed API no longer 503s | live `get_seed_pg_conn()` + `list_seeds()` returns 185 rows |
| A3 | Preview and sample trigger run | preview `a616cf22…` seed 95 success; sample `3cddc244…` `succeeded`, `items_processed=1`; job-path `abe9de28…` succeeded |
| A4 | Ops/upload remain unavailable | `task_views()` ops `postgres_unavailable`; `DATABASE_URL` absent |
| A5 | Serving unaffected | `/api/health`, `/main`, `/chat` 200 |
| A6 | Tests | seed API tests 6 passed / 2 skipped; `ruff check` clean |

## Rollback

Remove `CANONICAL_V2_SEED_DATABASE_URL`, restore `console_dsn.py` / `canonical_v2_seeds.py` /
`seeds.py` from `.bak-seed-*`, restart.
