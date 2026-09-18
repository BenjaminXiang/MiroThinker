# Tasks: connect-collection-line

## A · Console DSN contract (single source)

- \[ \] A1 `backend/deps.py`: `resolve_console_dsn()` — the only reader of
  `DATABASE_URL` / `DATABASE_URL_TEST`; returns `str | None`; blank strings count as
  unset. → verify: unit tests for both names, precedence, blank handling.
- \[ \] A2 `backend/main.py`: resolve once at start, carry on `app.state`, hand the
  value to the jobs gate; log configured/not-configured (never the DSN itself).
  → verify: app test for both states.
- \[ \] A3 Repoint the reachable readers at the resolved value:
  `canonical_v2_seeds._seed_connection`, the uploads precheck path
  (`canonical_v2_uploads` → `upload._resolve_upload_dsn`), and
  `canonical_v2_admin_status`'s build-database freshness text. → verify: with only
  `CANONICAL_V2_DATABASE_URL` set, the console reports its database unavailable and
  gated endpoints answer a stable 503 (never 500).
- \[ \] A4 `PostgresProbe.ENV_ORDER` drops `CANONICAL_V2_DATABASE_URL` and gains
  `resolved_dsn()`; probe and injection share it. → verify: probe tests for the two
  accepted names and the now-ignored one.

## B · Gate injects the DSN into spawned jobs

- \[ \] B1 `JobRuntime._execute` injects `DATABASE_URL` (when resolved) into the child
  env beside the four existing keys. → verify: runner test asserts the key, its
  absence when unresolved, and keeps the existing "env is never persisted" assertion
  green.

## C · Provisioning and wiring (this deployment)

- \[ \] C1 Create `miroflow_collection_v1` with the destructive-target marker; apply
  alembic to head (`V042`); verify the five key tables and a real `list_seeds` read.
  → verify: commands + observed output in the run evidence.
- \[ \] C2 systemd drop-in `database-url.conf` carrying the console DSN;
  `daemon-reload`; restart; wait for `/api/health`. → verify: boot log + health 200.
- \[ \] C3 Live-line verification: `/seeds` 200 with an empty list; create → update →
  delete a real seed; `/jobs` shows the run; `/upload` precheck green.

## D · Roster import and adapter coverage

- \[ \] D1 `apps/admin-console/scripts/import_professor_seeds.py` (idempotent,
  dry-run default, `--apply` to write): parse with `parse_roster_seed_markdown()`,
  skip by `seed_url` via `get_seed_by_url`, report created/skipped/unresolved.
  → verify: unit tests against a temporary schema + a dry run over the local corpus.
- \[ \] D2 pkusz registry matcher with a test; corrected URLs for the two wrong-shaped
  SZTU entries in the roster sources; re-run the classifier → 39/39 resolve.

## E · Entry honesty and failure visibility

- \[ \] E1 `nav_auth.js` hides `[data-requires-postgres]` entries when the console
  database is unconfigured; `main.html` marks `/seeds` and `/upload`.
  → verify: page-shell test.
- \[ \] E2 `/upload` button and copy agree in the degraded state.
- \[ \] E3 `GET /api/canonical-v2/admin/seeds/{id}/runs` carries `status`,
  `exit_code`, `stderr_excerpt`; `seeds.html` renders the reason for a failed row.
  → verify: API test + page-shell test.

## F · Verification

- \[ \] F1 Targeted suites green; full `apps/admin-console` before/after with zero new
  failures.
- \[ \] F2 One real `preview` and one `sample` (limit=5) run on the live line; quota
  actually spent reported.
- \[ \] F3 Evidence under `.agents/runs/connect-collection-line/`; ledger row ticked;
  human log appended; index line updated.
