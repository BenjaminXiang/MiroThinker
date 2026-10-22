# Design: enable-customer-site-seed-console

## DSN resolution

```
CANONICAL_V2_SEED_DATABASE_URL
  > DATABASE_URL
  > DATABASE_URL_TEST
```

`resolve_seed_dsn()` lives in the leaf `backend/console_dsn.py` so both seed routers can import it
without dragging in the legacy retrieval stack.

## Surfaces

- `/api/seeds` (legacy router used by `seeds.html`): connection dependency changes from
  `get_pg_conn` to `get_seed_pg_conn`, which opens `resolve_seed_dsn()`.
- `/api/canonical-v2/admin/seeds` (V2 router): `require_postgres()` accepts an explicit
  `CANONICAL_V2_SEED_DATABASE_URL`; `_seed_connection()` uses the same DSN.
- Background seed runs (`seeds.py::_run_seed_task`) use `resolve_seed_dsn()`.
- The seed job `admin-seed-refresh` receives `DATABASE_URL` from `MIROTHINKER_JOB_DATABASE_URL`
  (collection DB), unchanged.

## Isolation

`PostgresProbe` still reads only `DATABASE_URL`; the ops tasks and the upload page keep their
existing `postgres_unavailable` state. No global `DATABASE_URL` is set.

## Deployment

`run.sh` exports:

```bash
export CANONICAL_V2_SEED_DATABASE_URL="$MIROTHINKER_JOB_DATABASE_URL"
```

Service restart required (10–12 minutes).

## Rollback

Remove the export, restore `console_dsn.py`, `canonical_v2_seeds.py`, `seeds.py` from
`.bak-seed-*`, restart.
