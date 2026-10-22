# Proposal: enable-customer-site-seed-console

## Why

The customer `/seeds` page (教授采集源) is unusable because the console process has no
`DATABASE_URL`; the page reports `seeds_require_postgres` / `console_database_not_configured`.
The raw collection DB already has `professor_seed` (185 rows) and the seed-refresh job can run with
the job DSN.

Setting `DATABASE_URL` would also enable the three ops tasks and the upload surface, which the
serving node cannot support. The seed page needs a **seed-only** DSN.

## What Changes

- Add `CANONICAL_V2_SEED_DATABASE_URL` and `resolve_seed_dsn()` in `backend/console_dsn.py`.
- Make the V2 seed router (`canonical_v2_seeds.py`) and the legacy `/api/seeds` router
  (`seeds.py`) use this DSN for the seed surface only.
- Keep the ops/upload `PostgresProbe` on `DATABASE_URL`; they stay unavailable.
- Export the new variable in the customer `run.sh` pointing at `miroflow_collection_v1`.
- Restart and verify the seed list, preview trigger and job history.

## Capabilities

### Modified Capabilities

- `admin-data-frontdoor` — seed registry DB resolution on a serving-only node.

## Impact

- Seed CRUD and trigger read/write `miroflow_collection_v1`; no serving candidate DB/pack changes.
- Ops/upload surfaces remain disabled (no `DATABASE_URL`).
- Rollback: remove the env export, restore the three backend files from `.bak-seed-*`, restart.
