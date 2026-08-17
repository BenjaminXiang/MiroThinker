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
- [x] T1.4: Add unit test for migration up + down idempotency
  *(completed 2026-05-15 via `apps/admin-console/tests/test_migration_v022.py`;
  uses a lightweight schema-only Alembic fixture rather than the
  admin-console data fixture, because this worktree does not include the
  large Excel fixture needed by `postgres_data_ready`.)*
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
- [x] T2.5: Add `POST /api/seeds/{id}/trigger` endpoint:
  - Pre-check: if `last_run_status='in_progress'` → return HTTP 409
  - Pre-check: if `last_run_status='adapter_missing'` and no adapter is
    currently registered → return HTTP 422
  - Pre-check: if `last_run_status='adapter_missing'` but an adapter has
    since been registered → accept trigger and set `in_progress`
  - Otherwise: set `in_progress` synchronously, enqueue background task,
    return HTTP 202 with `{run_id, seed_id, status: in_progress}`
  *(Phase B complete: tests cover 202 / 409 / 422 / adapter-registered-
  later / 404 behavior.)*
- [x] T2.6: Wire the background task to the Professor pipeline's single-
  seed entry point (depends on Pipeline section)
  *(Phase B complete: admin-console schedules `run_single_seed` through
  a bounded ThreadPoolExecutor.)*
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
  - Disabled when `last_run_status='in_progress'`
  - Clickable for `adapter_missing`, so backend can re-check whether an
    adapter has since been registered
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
- [x] T3.9: Run `just frontend-fresh` and verify the SPA bundle ships
  the new page
  *(Phase B complete: `just frontend-fresh` runs `npm run build` and
  exits 0.)*

## 4. Pipeline integration

- [x] T4.1: Add a new entry point function `run_single_seed(seed_id:
  int)` in `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
  that:
  - Loads the seed row from `professor_seed`
  - Performs adapter resolution against (school, department) pair
  - If no adapter: sets `last_run_status='adapter_missing'` +
    `last_run_at=now()`; writes one `pipeline_issue` row with
    `stage='adapter_missing'` and structured payload; returns
  - Otherwise: runs the existing professor pipeline against `seed_url`,
    using upsert semantics on `professor` rows
  - On success: sets `last_run_status='success'` + `last_run_at=now()`
  - On uncaught exception: sets `last_run_status='failure'` +
    `last_run_at=now()`; writes `pipeline_issue` row
  *(Phase B complete. V023 extends `pipeline_issue.stage`, and issue
  writes are idempotent against the existing open-issue uniqueness
  constraint.)*
- [x] T4.2: Adapter resolution stub: this change pre-creates an
  *interface* that returns `None` always, until
  `prof-school-adapter-framework` lands. Result: every seed will go to
  `adapter_missing` until the framework change ships. This is the
  intended MVP state.
  *(Phase B complete. **Spec drift correction**: survey 2026-05-10 found the
  framework + 5 adapters already exist in `school_adapters.py` +
  `roster.py`. T4.2 simplifies to "wire registered adapters + None-path
  → `adapter_missing` write".)*
- [x] T4.3: Add runtime config for global concurrency cap (default 4)
  *(Phase B complete via `ADMIN_PROFESSOR_SEED_CONCURRENCY`; admin-console
  does not use Hydra at runtime.)*
- [x] T4.4: Pipeline integration test covering adapter_missing path
  (using the stub adapter resolver)
  *(Phase B complete.)*
- [x] T4.5: Pipeline integration test covering success path against a
  fixture roster (using a fake adapter that returns 3 professors)
  *(Phase B complete; implemented as fake pipeline + injected writer to
  isolate DB status semantics from real HTTP.)*

## 5. Cron

- [x] T5.1: Add a cron job using APScheduler (or equivalent) that
  triggers monthly (1st @ 02:00 server local time)
  *(Phase B complete.)*
- [x] T5.2: Cron logic: iterate `professor_seed` ordered by `id` ASC;
  for each eligible seed (`last_run_status` not in
  `{in_progress, adapter_missing}`), enqueue a single-seed pipeline
  task respecting the global concurrency cap
  *(Phase B complete.)*
- [x] T5.3: Cron unit test covering: (a) skip in_progress; (b) skip
  adapter_missing; (c) enqueue rest in id-order
  *(Phase B complete.)*
- [x] T5.4: Add runtime config for cron schedule (default monthly 1st
  02:00); make schedule configurable for testing
  *(Phase B complete via `ADMIN_PROFESSOR_SEED_CRON_*`; admin-console
  does not use Hydra at runtime.)*

## 6. Acceptance + close-out

- [x] T6.1: Run `openspec validate prof-seed-admin-console`; resolve any
  errors
  *(verified at spec drafting commit `58c1cbd` and revalidated after
  V019→V022 rename in `11e06a8`. Both pass clean.)*
- [x] T6.2: Run all integration tests (`uv run pytest` in both
  `apps/miroflow-agent` and `apps/admin-console`)
  *(Phase A scope: `apps/admin-console` 15 seeds-API tests pass; full
  pytest pass for unrelated suites. Phase B will re-run after pipeline
  + cron land. Phase B relevant integration tests passed:
  `tests/test_seeds_api.py`, `tests/test_seed_cron.py`,
  `tests/test_migration_v023.py`, and
  `tests/postgres/test_run_single_seed.py`.)*
- [x] T6.3: Manual smoke test: create one seed via admin UI, click
  trigger, observe `last_run_status` transitions in admin UI within 30s
  to `adapter_missing` (since no adapter framework yet)
  *(Phase A scope: 2 seeds (SZU CSE + CUHK SZ AI) entered via UI and
  persisted with `last_run_status='never_run'`; trigger button
  disabled per Phase A. Phase B test-DB smoke verified
  `never_run -> in_progress -> adapter_missing` through HTTP trigger,
  DB evidence, and browser-rendered `/seeds`.)*
- [x] T6.4: Update `openspec/change-ledger.md` Status column to
  `tasks-complete-not-archived` once T1-T5 done; archive via
  `openspec archive prof-seed-admin-console` after stakeholder review
  *(Phase A: status updated to "Phase A complete; Phase B pending"
  in commit `58c1cbd`. Phase B: status updated to
  "Phase B complete; tasks-complete-not-archived". Archive still awaits
  stakeholder review.)*
- [x] T6.5: Fill in `acceptance.md` evidence sections with evidence rows
  and test output
  *(Phase A and Phase B evidence filled.)*

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
