# Tasks: prof-seed-admin-console

This change ships the SPEC. Implementation is sliced into discrete tasks
below; each task is independently verifiable.

Sections may be done in parallel where dependencies allow. Suggested
order: 1 → 2 → 3 → 4 → 5.

## 1. Database

- [ ] T1.1: Write Alembic migration `V022_professor_seed.py` adding the
  `professor_seed` table with columns matching `specs/professor-seed-
  management/spec.md` "Seed table schema" Requirement
- [ ] T1.2: Add Postgres CHECK constraint on `last_run_status` enforcing
  the 5 enum values (`success / failure / in_progress / never_run /
  adapter_missing`)
- [ ] T1.3: Add `created_at` / `updated_at` debug-only columns (defaults
  to `now()`)
- [ ] T1.4: Add unit test for migration up + down idempotency
- [ ] T1.5: Add a Pydantic model `ProfessorSeed` in
  `apps/admin-console/backend/storage/seeds.py` (or equivalent) with
  `Literal` typing for `last_run_status`

## 2. Backend endpoints

- [ ] T2.1: Add `apps/admin-console/backend/api/seeds.py` with FastAPI
  router exposing `GET / POST / PUT / DELETE /api/seeds`
- [ ] T2.2: Implement URL-format validation on POST / PUT (use
  `pydantic.AnyHttpUrl`)
- [ ] T2.3: Implement empty-string-to-NULL normalization for
  `department` on POST / PUT
- [ ] T2.4: Implement `last_run_status` / `last_run_at` strip-from-
  request behavior on PUT (admin cannot mutate)
- [ ] T2.5: Add `POST /api/seeds/{id}/trigger` endpoint:
  - Pre-check: if `last_run_status='in_progress'` → return HTTP 409
  - Pre-check: if `last_run_status='adapter_missing'` → return HTTP 422
  - Otherwise: set `in_progress` synchronously, enqueue background task,
    return HTTP 202 with `{run_id, seed_id, status: in_progress}`
- [ ] T2.6: Wire the background task to the Professor pipeline's single-
  seed entry point (depends on Pipeline section)
- [ ] T2.7: Add API integration tests covering every scenario in the
  Requirements (including the three trigger scenarios + the schema
  scenarios + the CRUD scenarios)
- [ ] T2.8: Update OpenAPI documentation auto-generation; verify that
  `/docs` shows the new endpoints with correct schemas

## 3. Frontend

- [ ] T3.1: Add `apps/admin-console/frontend/src/pages/Seeds.tsx`
  rendering a table with columns: school / department / seed_url /
  last_run_at / last_run_status / actions (edit / delete / 立即爬取)
- [ ] T3.2: Implement add-seed modal (school / department / seed_url
  inputs; URL format client-side check before POST)
- [ ] T3.3: Implement edit-seed modal (school / department / seed_url
  editable; status fields read-only)
- [ ] T3.4: Implement delete confirmation prompt
- [ ] T3.5: Implement 立即爬取 button per row:
  - Disabled when `last_run_status='in_progress'` or
    `last_run_status='adapter_missing'`
  - On click, POST `/api/seeds/{id}/trigger` and update local state
- [ ] T3.6: Implement polling: when any row is `in_progress`, poll
  `GET /api/seeds` every 10s until all rows leave `in_progress`
- [ ] T3.7: Add color/icon for each `last_run_status` value (green /
  red / yellow-spinner / gray / orange respectively)
- [ ] T3.8: Add route `/admin/seeds` to the React router; link from
  admin console main nav
- [ ] T3.9: Run `just frontend-fresh` and verify the SPA bundle ships
  the new page

## 4. Pipeline integration

- [ ] T4.1: Add a new entry point function `run_single_seed(seed_id:
  int)` in `apps/miroflow-agent/src/data_agents/professor/pipeline.py`
  (or equivalent) that:
  - Loads the seed row from `professor_seed`
  - Performs adapter resolution against (school, department) pair
  - If no adapter: sets `last_run_status='adapter_missing'` +
    `last_run_at=now()`; writes one `pipeline_issue` row with
    `kind='adapter_missing'` and structured payload; returns
  - Otherwise: runs the existing professor pipeline against `seed_url`,
    using upsert semantics on `professor` rows
  - On success: sets `last_run_status='success'` + `last_run_at=now()`
  - On uncaught exception: sets `last_run_status='failure'` +
    `last_run_at=now()`; writes `pipeline_issue` row
- [ ] T4.2: Adapter resolution stub: this change pre-creates an
  *interface* that returns `None` always, until
  `prof-school-adapter-framework` lands. Result: every seed will go to
  `adapter_missing` until the framework change ships. This is the
  intended MVP state.
- [ ] T4.3: Add Hydra config for global concurrency cap (default 4)
- [ ] T4.4: Pipeline integration test covering adapter_missing path
  (using the stub adapter resolver)
- [ ] T4.5: Pipeline integration test covering success path against a
  fixture roster (using a fake adapter that returns 3 professors)

## 5. Cron

- [ ] T5.1: Add a cron job using APScheduler (or equivalent) that
  triggers monthly (1st @ 02:00 server local time)
- [ ] T5.2: Cron logic: iterate `professor_seed` ordered by `id` ASC;
  for each eligible seed (`last_run_status` not in
  `{in_progress, adapter_missing}`), enqueue a single-seed pipeline
  task respecting the global concurrency cap
- [ ] T5.3: Cron unit test covering: (a) skip in_progress; (b) skip
  adapter_missing; (c) enqueue rest in id-order
- [ ] T5.4: Add Hydra config for cron schedule (default monthly 1st
  02:00); make schedule configurable for testing

## 6. Acceptance + close-out

- [ ] T6.1: Run `openspec validate prof-seed-admin-console`; resolve any
  errors
- [ ] T6.2: Run all integration tests (`uv run pytest` in both
  `apps/miroflow-agent` and `apps/admin-console`)
- [ ] T6.3: Manual smoke test: create one seed via admin UI, click
  trigger, observe `last_run_status` transitions in admin UI within 30s
  to `adapter_missing` (since no adapter framework yet)
- [ ] T6.4: Update `openspec/change-ledger.md` Status column to
  `tasks-complete-not-archived` once T1-T5 done; archive via
  `openspec archive prof-seed-admin-console` after stakeholder review
- [ ] T6.5: Fill in `acceptance.md` evidence sections with commit refs
  and test output

## Out of this change's tasks

- Per-school adapter framework + actual adapter implementations (separate
  change `prof-school-adapter-framework`)
- Paper / patent extraction from prof pages (separate change
  `prof-paper-patent-from-page-flow`)
- Bulk Excel import for seeds (Phase 2)
- User login / RBAC (Phase 2)
- Migration of existing scattered seed information from
  `scripts/e2e_seed_*.md` into the new table (manual entry by admin)
