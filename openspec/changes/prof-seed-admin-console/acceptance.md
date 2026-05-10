# Acceptance: prof-seed-admin-console

## 1. Spec validation

- [ ] `openspec validate prof-seed-admin-console` exits 0
- [ ] No `## Why` / `## What Changes` warning from the CLI (proposal.md
  conforms to current OpenSpec convention)
- [ ] `specs/professor-seed-management/spec.md` uses `## ADDED
  Requirements` delta header (this is a new capability; no
  MODIFIED/REMOVED present)

## 2. Schema acceptance (after T1)

- [ ] `apps/miroflow-agent/alembic/versions/V022_professor_seed.py`
  exists; up-migration creates `professor_seed` table with exactly the
  columns named in the Schema Requirement
- [ ] `\d professor_seed` in psql shows: `id` (PK), `school`,
  `department`, `seed_url`, `last_run_at`, `last_run_status`,
  `created_at`, `updated_at` — and nothing else
- [ ] CHECK constraint on `last_run_status` enforces 5 enum values
  (verified by `INSERT … last_run_status='garbage'` failing)
- [ ] Down-migration drops the table cleanly
- [ ] Test `tests/alembic/test_v022_professor_seed.py` passes

## 3. Endpoint acceptance (after T2)

- [ ] `GET /api/seeds` returns sorted list (verify by 5-row fixture)
- [ ] `POST /api/seeds` with valid body returns 201 + new row
- [ ] `POST /api/seeds` with invalid URL returns 422
- [ ] `PUT /api/seeds/{id}` with `last_run_status` in body silently
  ignores it (verified: GET after PUT shows unchanged status)
- [ ] `DELETE /api/seeds/{id}` returns 204; subsequent `GET` returns 404
- [ ] `POST /api/seeds/{id}/trigger` on `never_run` returns 202;
  subsequent GET shows `in_progress`
- [ ] `POST /api/seeds/{id}/trigger` on `in_progress` returns 409
- [ ] `POST /api/seeds/{id}/trigger` on `adapter_missing` returns 422
- [ ] OpenAPI `/docs` lists all 5 endpoints with correct schemas
- [ ] Integration tests in `apps/admin-console/tests/test_seeds_api.py`
  cover every Scenario in the spec (count = ~14 scenarios)

## 4. Frontend acceptance (after T3)

- [ ] `/admin/seeds` route renders table with all 6 visible columns
  (school / department / seed_url / last_run_at / last_run_status /
  actions)
- [ ] Add modal validates URL format client-side before POST
- [ ] Edit modal hides `last_run_at` and `last_run_status` from inputs
- [ ] Delete confirmation prompt blocks accidental deletes
- [ ] 立即爬取 button is disabled when row is `in_progress` or
  `adapter_missing`
- [ ] After clicking 立即爬取, the row's `last_run_status` updates to
  `in_progress` within 1s (no manual refresh)
- [ ] When any row is `in_progress`, the page polls every 10s and
  refreshes
- [ ] Status colors: success=green, failure=red, in_progress=yellow
  spinner, never_run=gray, adapter_missing=orange
- [ ] `just frontend-fresh` builds without errors
- [ ] Manual screenshot of admin page attached to PR description

## 5. Pipeline acceptance (after T4)

- [ ] `run_single_seed(seed_id)` exists in
  `apps/miroflow-agent/src/data_agents/professor/pipeline.py`
- [ ] Calling `run_single_seed()` for a seed without registered adapter
  results in:
  - `professor_seed.last_run_status='adapter_missing'`
  - `professor_seed.last_run_at` set to within 1s of call
  - exactly one new `pipeline_issue` row with `kind='adapter_missing'`
  - no Tier 2/3 network calls (verified via mock or no-network test
    environment)
- [ ] Calling `run_single_seed()` for a seed with mock adapter returning
  3 professors results in:
  - 3 professor rows existing in canonical (insert) or updated (upsert)
  - `professor_seed.last_run_status='success'`
  - `professor_seed.last_run_at` set to completion time
- [ ] Hydra config knob for global concurrency cap exists (default 4)
- [ ] Tests `tests/data_agents/professor/test_run_single_seed.py` pass

## 6. Cron acceptance (after T5)

- [ ] APScheduler (or equivalent) is wired to run monthly 1st @ 02:00
  server local time
- [ ] Cron iterates seeds in `id` ASC order
- [ ] Cron skips `last_run_status` in `{in_progress, adapter_missing}`
- [ ] Cron respects concurrency cap (4 concurrent runs)
- [ ] Hydra config knob for cron schedule exists (default monthly 1st
  02:00)
- [ ] Cron unit tests in `tests/cron/test_professor_seed_cron.py` pass

## 7. End-to-end smoke (T6.3)

- [ ] Fresh local env: bring up admin console + Postgres
- [ ] Create one seed via admin UI: school="SUSTech", department=NULL,
  seed_url="https://example.com/test"
- [ ] Click 立即爬取
- [ ] Within 30s, observe in admin UI:
  - last_run_status transitions: never_run → in_progress →
    adapter_missing
  - last_run_at populated
  - One row in `pipeline_issue` with `kind='adapter_missing'`

## 8. Non-goals not violated

- [ ] No file under `apps/miroflow-agent/src/data_agents/paper/` or
  `apps/miroflow-agent/src/data_agents/patent/` was touched
- [ ] No code in `apps/admin-console/backend/api/chat.py` was touched
- [ ] No new field added to existing `professor` / `paper` / `patent` /
  `professor_paper_link` / `professor_patent_link` tables
- [ ] No Milvus collection added or modified by this change (double
  collection split is a separate change `prof-double-milvus-collection`)
- [ ] No user login / auth code added
- [ ] No bulk Excel import code added

## Evidence

> Filled during implementation by the executing agent.

### T1 — Database (Phase A complete)
- Migration commit ref: `7b13eb0`
- Schema verification: `\d professor_seed` shows 8 columns (id / school /
  department / seed_url / last_run_at / last_run_status / created_at /
  updated_at); CHECK constraint enforces 5-value enum; 4 indices
  (pkey, status filter, unique seed_url, school filter)
- Smoke test: storage-helper roundtrip (create / list / get / update /
  delete + URL uniqueness + CHECK reject) all passed via direct
  psycopg connection

### T2 — Endpoints (Phase A complete; trigger T2.5/T2.6 deferred)
- Endpoint code commit ref: `7018676`
- Test output: 15 passed, 1 warning (psycopg_pool DeprecationWarning,
  pre-existing) in 4.78s — `apps/admin-console/tests/test_seeds_api.py`
- Scenarios covered: department-level / school-wide / invalid URL
  reject / blank school reject / list sorted / get 404 / update with
  status fields ignored / update 404 / update duplicate URL 409 /
  delete 204 / delete 404 / create duplicate URL 409 / whitespace
  department NULL normalization
- Trigger endpoint scenarios (3) await Phase B

### T3 — Frontend (Phase A complete; trigger button disabled)
- Frontend commit ref: `d2a3d4e`
- Build verification: `npm run build` clean (tsc -b + vite build, 0
  errors, ~6s); SPA bundle includes "Seed 索引" + "seed-page" CSS
  classes (verified via grep on `dist/assets/index-*.{js,css}`)
- Manual UI smoke: user added 2 seeds via http://localhost:8123/seeds
  in browser session 2026-05-10:
  * 深圳大学 / 计算机与软件学院 / `https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1` / never_run
  * 香港中文大学（深圳） / 人工智能学院 / `https://sai.cuhk.edu.cn/teacher-search?...` / never_run
- Variant C (Swiss Operations) design preserved: 4px top rule, italic
  red accent on "索引", summary stat strip, filter pills, mono URL
  pills, status raw-name suffix

### T4 — Pipeline (Phase B; not started)
- Pipeline integration commit ref: (Phase B)
- Test output: (Phase B)

### T5 — Cron (Phase B; not started)
- Cron commit ref: (Phase B)
- Test output: (Phase B)

### T7 — Smoke (Phase A partial; Phase B trigger transition deferred)
- Local smoke test result: admin-console started on
  http://0.0.0.0:8123 (free port; 8000 occupied); `/api/health` HTTP
  200 `{"status":"ok"}`; `/api/seeds` HTTP 200 returning 2 user-
  entered rows; `/seeds` SPA route HTTP 200 + browser-rendered Variant
  C UI confirmed by user 2026-05-10
- Trigger transition (`never_run → in_progress → adapter_missing`)
  not yet observed; awaits Phase B trigger endpoint + adapter
  resolution wiring

## Failure modes that block archive

- T2 trigger endpoint accepts a request that the spec says should be
  rejected → spec / impl mismatch → fix impl; do not archive
- T4 adapter resolution stub somehow runs Tier 2/3 even when adapter
  missing → critical bug; do not archive
- Cron fires more than monthly → schedule misconfigured; fix and archive
- Frontend polling loop creates infinite recursion → broken; fix
- spec validation fails after implementation → spec / impl drift; either
  update spec (with another change) or update impl
