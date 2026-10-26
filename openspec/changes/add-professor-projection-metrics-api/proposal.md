# Proposal: add-professor-projection-metrics-api

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md` §3.7.

## Why

Gate 3.5 made the projection refresh one command and produced a metrics file, but
the only way to read it was a shell on the customer host. Gate 4 needs the numbers
visible where operators already look, and the refresh needs to run without a human.

## What Changes

1. `GET /api/canonical-v2/admin/professor-projection` serves the latest metrics
   JSON. Unset path → 503, missing file → 404, malformed → 500. Read-only: the
   console never triggers a refresh (that costs minutes of embedding calls).
2. `scripts/run_projection_refresh.py` is the cron entry point. It resolves the
   pack / output / metrics paths from the environment, projects the managed
   settings and secrets into the child environment (the embedding key lives in
   `code/config/managed/secrets.json`, not in the process env), runs the refresh,
   and publishes `metrics.json` where the endpoint reads it.

## Impact

- New admin API surface (behind the existing session gate); no change to chat.
- The scheduled job is additive: it writes files under `var/`, never touches the
  pack or the database.

## Out of scope

- A dedicated console page (the JSON endpoint is enough for the first slice).
- Changing the refresh contents or thresholds.
