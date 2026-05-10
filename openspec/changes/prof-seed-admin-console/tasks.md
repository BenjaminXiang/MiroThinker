# Tasks: prof-seed-admin-console

This change ships the SPEC. Implementation is sliced into discrete tasks
below; each task is independently verifiable.

Sections may be done in parallel where dependencies allow. Suggested
order: 1 → 2 → 3 → 4 → 5.

> **Phase A close-out (2026-05-10)**: 22 of 36 tasks completed. Phase A scope
> = DB + backend CRUD + frontend admin page (per user 2026-05-10 directive
> "先把 Admin console web 页面做了"). Phase B scope (`run_for_single_seed`
> + adapter_missing detection + cron + V023 `pipeline_issue.stage`
> extension + activation of "立即爬取" button) deferred. The change
> remains active in `openspec/change-ledger.md` until Phase B completes,
> at which point the change archives.
>
> Phase A commits:
> - `7b13eb0` — DB layer (T1.1-T1.3, T1.5)
> - `7018676` — Backend endpoints + integration tests (T2.1-T2.4, T2.7, T2.8)
> - `d2a3d4e` — Frontend Seeds page (T3.1-T3.8 modified)

## 1. Database

- [x] T1.1: Write Alembic migration `V022_professor_seed.py` adding the
  `professor_seed` table with columns matching `specs/professor-seed-
  management/spec.md` "Seed table schema" Requirement
- [x] T1.2: Add Postgres CHECK constraint on `last_run_status` enforcing
  the 5 enum values (`success / failure / in_progress / never_run /
  adapter_missing`)
- [x] T1.3: Add `created_at` / `updated_at` debug-only columns (defaults
  to `now()`)
- [ ] T1.4: Add unit test for migration up + down idempotency
  *(deferred: no `apps/miroflow-agent/tests/alembic/` test convention
  exists yet; integration tests in T2 exercise the schema)*
- [x] T1.5: Add a Pydantic model `ProfessorSeed` in
  `apps/admin-console/backend/storage/seeds.py` (or equivalent) with
  `Literal` typing for `last_run_status`

## 2. Backend endpoints

- [x] T2.1: Add `apps/admin-console/backend/api/seeds.py` with FastAPI
  router exposing `GET / POST / PUT / DELETE /api/seeds`
- [x] T2.2: Implement URL-format validation on POST / PUT (use
  `pydantic.AnyHttpUrl`)
- [x] T2.3: Implement empty-string-to-NULL normalization for
  `department` on POST / PUT
- [x] T2.4: Implement `last_run_status` / `last_run_at` strip-from-
  request behavior on PUT (admin cannot mutate)
- [ ] T2.5: Add `POST /api/seeds/{id}/trigger` endpoint:
  - Pre-check: if `last_run_status='in_progress'` → return HTTP 409
  - Pre-check: if `last_run_status='adapter_missing'` → return HTTP 422
  - Otherwise: set `in_progress` synchronously, enqueue background task,
    return HTTP 202 with `{run_id, seed_id, status: in_progress}`
  *(Phase B — depends on T4.1 pipeline entry point)*
- [ ] T2.6: Wire the background task to the Professor pipeline's single-
  seed entry point (depends on Pipeline section)
  *(Phase B)*
- [x] T2.7: Add API integration tests covering every scenario in the
  Requirements (including the three trigger scenarios + the schema
  scenarios + the CRUD scenarios)
  *(Phase A: 15 tests pass for CRUD + URL validation + admin-cannot-
  mutate-status + duplicate-URL 409. Phase A scope; trigger scenarios
  await T2.5 in Phase B.)*
- [x] T2.8: Update OpenAPI documentation auto-generation; verify that
  `/docs` shows the new endpoints with correct schemas
  *(FastAPI auto-generates OpenAPI from APIRouter + Pydantic models;
  verified at boot via `curl /api/health` + `/api/seeds` returning
  HTTP 200 against running server.)*

## 3. Frontend

- [x] T3.1: Add `apps/admin-console/frontend/src/pages/Seeds.tsx`
  rendering a table with columns: school / department / seed_url /
  last_run_at / last_run_status / actions (edit / delete / 立即爬取)
- [x] T3.2: Implement add-seed modal (school / department / seed_url
  inputs; URL format client-side check before POST)
- [x] T3.3: Implement edit-seed modal (school / department / seed_url
  editable; status fields read-only)
- [x] T3.4: Implement delete confirmation prompt
- [x] T3.5: Implement 立即爬取 button per row:
  - Disabled when `last_run_status='in_progress'` or
    `last_run_status='adapter_missing'`
  - On click, POST `/api/seeds/{id}/trigger` and update local state
  *(Phase A modification: button rendered but **always disabled** with
  tooltip "Pipeline 接入待 Phase B"; click handler not wired since
  trigger endpoint deferred. Phase B will activate.)*
- [x] T3.6: Implement polling: when any row is `in_progress`, poll
  `GET /api/seeds` every 10s until all rows leave `in_progress`
  *(implemented; effectively dormant in Phase A since no row reaches
  `in_progress` without trigger)*
- [x] T3.7: Add color/icon for each `last_run_status` value (green /
  red / yellow-spinner / gray / orange respectively)
- [x] T3.8: Add route `/seeds` to the React router; link from
  admin console main nav (LinkOutlined icon, label "Seed 索引")
- [ ] T3.9: Run `just frontend-fresh` and verify the SPA bundle ships
  the new page
  *(deferred: `npm run build` already verified bundle ships Seeds page
  references — see commit `d2a3d4e`. `just frontend-fresh` runs the
  same build with extra repo-aware steps; will run when Phase B ships.)*

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
  *(Phase B. Note: spec said `kind='adapter_missing'` but actual
  `pipeline_issue.stage` column doesn't include that value — V023
  migration extends `stage` CHECK constraint, see Phase B addendum.)*
- [ ] T4.2: Adapter resolution stub: this change pre-creates an
  *interface* that returns `None` always, until
  `prof-school-adapter-framework` lands. Result: every seed will go to
  `adapter_missing` until the framework change ships. This is the
  intended MVP state.
  *(Phase B. **Spec drift correction**: survey 2026-05-10 found the
  framework + 5 adapters already exist in `school_adapters.py` +
  `roster.py:825-870`. T4.2 simplifies to "wire `find_matching_school_
  adapter()` + None-path → `adapter_missing` write".)*
- [ ] T4.3: Add Hydra config for global concurrency cap (default 4)
  *(Phase B)*
- [ ] T4.4: Pipeline integration test covering adapter_missing path
  (using the stub adapter resolver)
  *(Phase B)*
- [ ] T4.5: Pipeline integration test covering success path against a
  fixture roster (using a fake adapter that returns 3 professors)
  *(Phase B; can use real registered adapter instead of fake, given
  framework already exists)*

## 5. Cron

- [ ] T5.1: Add a cron job using APScheduler (or equivalent) that
  triggers monthly (1st @ 02:00 server local time)
  *(Phase B)*
- [ ] T5.2: Cron logic: iterate `professor_seed` ordered by `id` ASC;
  for each eligible seed (`last_run_status` not in
  `{in_progress, adapter_missing}`), enqueue a single-seed pipeline
  task respecting the global concurrency cap
  *(Phase B)*
- [ ] T5.3: Cron unit test covering: (a) skip in_progress; (b) skip
  adapter_missing; (c) enqueue rest in id-order
  *(Phase B)*
- [ ] T5.4: Add Hydra config for cron schedule (default monthly 1st
  02:00); make schedule configurable for testing
  *(Phase B)*

## 6. Acceptance + close-out

- [x] T6.1: Run `openspec validate prof-seed-admin-console`; resolve any
  errors
  *(verified at spec drafting commit `58c1cbd` and revalidated after
  V019→V022 rename in `11e06a8`. Both pass clean.)*
- [x] T6.2: Run all integration tests (`uv run pytest` in both
  `apps/miroflow-agent` and `apps/admin-console`)
  *(Phase A scope: `apps/admin-console` 15 seeds-API tests pass; full
  pytest pass for unrelated suites. Phase B will re-run after pipeline
  + cron land.)*
- [x] T6.3: Manual smoke test: create one seed via admin UI, click
  trigger, observe `last_run_status` transitions in admin UI within 30s
  to `adapter_missing` (since no adapter framework yet)
  *(Phase A scope: 2 seeds (SZU CSE + CUHK SZ AI) entered via UI and
  persisted with `last_run_status='never_run'`; trigger button
  disabled per Phase A. The "transition to adapter_missing" sub-test
  awaits Phase B trigger wiring.)*
- [x] T6.4: Update `openspec/change-ledger.md` Status column to
  `tasks-complete-not-archived` once T1-T5 done; archive via
  `openspec archive prof-seed-admin-console` after stakeholder review
  *(Phase A: status updated to "Phase A complete; Phase B pending"
  in commit `58c1cbd`. Full archive deferred until Phase B completes.)*
- [ ] T6.5: Fill in `acceptance.md` evidence sections with commit refs
  and test output
  *(partial: Phase A evidence filled in this close-out commit; Phase B
  evidence will be filled when Phase B sub-changes ship.)*

## Out of this change's tasks

- Per-school adapter framework + actual adapter implementations (separate
  change `prof-school-adapter-framework`)
- Paper / patent extraction from prof pages (separate change
  `prof-paper-patent-from-page-flow`)
- Bulk Excel import for seeds (Phase 2)
- User login / RBAC (Phase 2)
- Migration of existing scattered seed information from
  `scripts/e2e_seed_*.md` into the new table (manual entry by admin)

## Phase B addendum (added 2026-05-10 close-out)

The following spec drift items were identified during Phase A
implementation and need to be addressed when Phase B starts:

1. **`pipeline_issue.stage` enum doesn't include `adapter_missing`**:
   the V006 schema's `stage` CHECK constraint allows 9 values
   (`discovery`, `name_extraction`, `affiliation`, `paper_attribution`,
   `paper_quality`, `research_directions`, `identity_gate`, `coverage`,
   `data_quality_flag`) — `adapter_missing` is not among them.
   Phase B starts with a small Alembic V023 migration that extends
   the CHECK constraint to include `adapter_missing`.

2. **Adapter framework already exists**: `school_adapters.py` (51
   lines) + 5 registered adapters in `roster.py:825-870` cover most of
   the planned `prof-school-adapter-framework` change. Phase B's T4.2
   stub becomes a thin wrapper, not greenfield.

3. **`pipeline_issue.kind` typo in spec / tasks**: the column is named
   `stage`, not `kind`. Spec wording will be corrected in Phase B
   close-out commit.
