# Tasks: enable-customer-site-seed-console

- [x] 1.1 Add `CANONICAL_V2_SEED_DATABASE_URL` + `resolve_seed_dsn()`.
- [x] 1.2 Use the seed DSN in the V2 seed router (`require_postgres`, `_seed_connection`).
- [x] 1.3 Use the seed DSN in the legacy `/api/seeds` connection dependency and background run.
- [x] 1.4 Export the variable in the customer `run.sh`; do not set `DATABASE_URL`.
- [x] 1.5 Add the seed-DSN regression test; run seed tests + ruff.
- [x] 1.6 Deploy the three backend files and restart.
- [x] 1.7 Verify `/seeds` lists 185 rows; trigger a preview and see a run.
- [x] 1.8 Verify ops/upload remain `postgres_unavailable`; `/api/health`, `/main`, `/chat` 200.
- [x] 1.9 Update ops/user docs and human log.
