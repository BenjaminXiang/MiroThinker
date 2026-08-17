# Acceptance: prof-seed-admin-console

## 1. Spec validation

- [x] `openspec validate prof-seed-admin-console` exits 0
- [x] No `## Why` / `## What Changes` warning from the CLI (proposal.md
  conforms to current OpenSpec convention)
- [x] `specs/professor-seed-management/spec.md` uses `## ADDED
  Requirements` delta header (this is a new capability; no
  MODIFIED/REMOVED present)

## 2. Schema acceptance (after T1)

- [x] `apps/miroflow-agent/alembic/versions/V022_professor_seed.py`
  exists; up-migration creates `professor_seed` table with exactly the
  columns named in the Schema Requirement
- [x] `\d professor_seed` in psql shows: `id` (PK), `school`,
  `department`, `seed_url`, `last_run_at`, `last_run_status`,
  `created_at`, `updated_at` — and nothing else
- [x] CHECK constraint on `last_run_status` enforces 5 enum values
  (verified by `INSERT … last_run_status='garbage'` failing)
- [x] Down-migration drops the table cleanly
- [x] Test `apps/admin-console/tests/test_migration_v022.py` passes
  *(schema-only V022 migration coverage; no `tests/alembic/` convention
  exists in this repo)*

## 3. Endpoint acceptance (after T2)

- [x] `GET /api/seeds` returns sorted list (verify by 5-row fixture)
- [x] `POST /api/seeds` with valid body returns 201 + new row
- [x] `POST /api/seeds` with invalid URL returns 422
- [x] `PUT /api/seeds/{id}` with `last_run_status` in body silently
  ignores it (verified: GET after PUT shows unchanged status)
- [x] `DELETE /api/seeds/{id}` returns 204; subsequent `GET` returns 404
- [x] `POST /api/seeds/{id}/trigger` on `never_run` returns 202;
  subsequent GET shows `in_progress`
- [x] `POST /api/seeds/{id}/trigger` on `in_progress` returns 409
- [x] `POST /api/seeds/{id}/trigger` on `adapter_missing` returns 422
  while no adapter is registered; returns 202 if a matching adapter is
  registered later
- [x] OpenAPI `/docs` lists all 5 endpoints with correct schemas
- [x] Integration tests in `apps/admin-console/tests/test_seeds_api.py`
  cover every Scenario in the spec (count = ~14 scenarios)

## 4. Frontend acceptance (after T3)

- [x] `/admin/seeds` route renders table with all 6 visible columns
  (school / department / seed_url / last_run_at / last_run_status /
  actions)
- [x] Add modal validates URL format client-side before POST
- [x] Edit modal hides `last_run_at` and `last_run_status` from inputs
- [x] Delete confirmation prompt blocks accidental deletes
- [x] 立即爬取 button is disabled when row is `in_progress`; for
  `adapter_missing` it remains clickable so the backend can re-check
  whether an adapter has since been registered
- [x] After clicking 立即爬取, the row's `last_run_status` updates to
  `in_progress` within 1s (no manual refresh)
- [x] When any row is `in_progress`, the page polls every 10s and
  refreshes
- [x] Status colors: success=green, failure=red, in_progress=yellow
  spinner, never_run=gray, adapter_missing=orange
- [x] `just frontend-fresh` builds without errors
- [x] Manual screenshot of admin page attached to PR description

## 5. Pipeline acceptance (after T4)

- [x] `run_single_seed(seed_id)` exists in
  `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
- [x] Calling `run_single_seed()` for a seed without registered adapter
  results in:
  - `professor_seed.last_run_status='adapter_missing'`
  - `professor_seed.last_run_at` set to within 1s of call
  - exactly one open `pipeline_issue` row with
    `stage='adapter_missing'`
  - no Tier 2/3 network calls (verified via mock or no-network test
    environment)
- [x] Calling `run_single_seed()` for a seed with mock adapter returning
  3 professors results in:
  - 3 professor rows existing in canonical (insert) or updated (upsert)
  - `professor_seed.last_run_status='success'`
  - `professor_seed.last_run_at` set to completion time
- [x] Runtime config knob for global concurrency cap exists (default 4)
- [x] Tests `tests/postgres/test_run_single_seed.py` pass

## 6. Cron acceptance (after T5)

- [x] APScheduler (or equivalent) is wired to run monthly 1st @ 02:00
  server local time
- [x] Cron iterates seeds in `id` ASC order
- [x] Cron skips `last_run_status` in `{in_progress, adapter_missing}`
- [x] Cron respects concurrency cap (4 concurrent runs)
- [x] Runtime config knob for cron schedule exists (default monthly 1st
  02:00)
- [x] Cron unit tests in `apps/admin-console/tests/test_seed_cron.py` pass

## 7. End-to-end smoke (T6.3)

- [x] Fresh local env: bring up admin console + Postgres
- [x] Create one seed via admin UI: school="SUSTech", department=NULL,
  seed_url="https://example.com/test"
- [x] Click 立即爬取
- [x] Within 30s, observe in admin UI:
  - last_run_status transitions: never_run → in_progress →
    adapter_missing
  - last_run_at populated
  - One open row in `pipeline_issue` with `stage='adapter_missing'`

## 8. Non-goals not violated

- [x] No file under `apps/miroflow-agent/src/data_agents/paper/` or
  `apps/miroflow-agent/src/data_agents/patent/` was touched
- [x] No code in `apps/admin-console/backend/api/chat.py` was touched
- [x] No new field added to existing `professor` / `paper` / `patent` /
  `professor_paper_link` / `professor_patent_link` tables
- [x] No Milvus collection added or modified by this change (double
  collection split is a separate change `prof-double-milvus-collection`)
- [x] No user login / auth code added
- [x] No bulk Excel import code added

These non-goal checks are evaluated for this change slice, not for the
aggregate implementation worktree that later included paper follow-up
changes.

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

### T2 — Endpoints (Phase A complete; trigger T2.5/T2.6 complete)
- Endpoint code commit ref: `7018676`
- Test output: 15 passed, 1 warning (psycopg_pool DeprecationWarning,
  pre-existing) in 4.78s — `apps/admin-console/tests/test_seeds_api.py`
- Scenarios covered: department-level / school-wide / invalid URL
  reject / blank school reject / list sorted / get 404 / update with
  status fields ignored / update 404 / update duplicate URL 409 /
  delete 204 / delete 404 / create duplicate URL 409 / whitespace
  department NULL normalization
- Phase B trigger endpoint verification:
  `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seeds_api.py -q`
  -> 20 passed, 6 warnings.
- Trigger scenarios covered: 202 accepted and synchronously sets
  `in_progress`; 409 on double-click while `in_progress`; 422 on
  `adapter_missing` with no adapter; 202 on `adapter_missing` after a
  matching adapter is registered; 404 missing seed.

### T3 — Frontend (Phase A complete; trigger button activated in Phase B)
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
- Phase B frontend verification: `npm run build` in
  `apps/admin-console/frontend` -> TypeScript + Vite production build
  succeeded; Vite emitted only the existing large chunk warning.
- Repository command verification: `just frontend-fresh` -> exits 0 and
  runs the same TypeScript + Vite production build successfully.
- Button behavior updated: disabled only while `in_progress`; clickable
  for `adapter_missing` so backend can re-check adapter availability.

### T4 — Pipeline (Phase B complete)
- Pipeline integration files:
  `apps/miroflow-agent/src/data_agents/professor/adapter_resolution.py`,
  `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`,
  `apps/miroflow-agent/alembic/versions/V023_extend_pipeline_issue_adapter_missing.py`.
- Test output:
  `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0`
  -> 4 passed.
- Red/green evidence for idempotent issue writing:
  `test_run_single_seed_deduplicates_repeated_open_adapter_missing_issue`
  first failed on `uq_pipeline_issue_open`, then passed after
  `ON CONFLICT DO NOTHING`.
- V023 stage acceptance:
  `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_migration_v023.py -q`
  in `apps/admin-console` -> 2 passed. Covers accepting
  `stage='adapter_missing'` and downgrading existing adapter-missing
  issues to `stage='discovery'` before restoring the V022 CHECK
  constraint.
- Phase B preflight evidence (2026-05-12, no DB writes):
  * Admin seed registry contains 15 rows, all `last_run_status='never_run'`.
  * Browser smoke: `/seeds` renders 15 table rows; `POST /api/seeds/9/trigger`
    returns HTTP 405 because trigger endpoint is not implemented yet.
  * Discovery priority regression fixed before trigger wiring: roster-like
    seeds now prefer existing school/roster adapters over direct-profile
    noise. Targeted red/green test:
    `uv run pytest tests/data_agents/professor/test_roster_validation.py::test_discover_professor_seeds_prefers_roster_entries_for_roster_like_urls -q`
    first failed on `direct_profile_seed_fetched` returning `师资列表`, then
    passed after the guard change.
  * Existing successful paths were rechecked and still passed:
    `uv run pytest tests/data_agents/professor/test_roster_validation.py -k
    "prefers_roster_entries_for_roster_like_urls or direct_profile or
    uses_sigs_api or uses_hit_api or discover_cuhk_seed" -q` -> 20 passed.
  * Real non-mutating roster-only smoke from the 15 admin seeds after the
    priority fix:
    `uv run python scripts/run_professor_crawler_e2e.py --seed-doc
    /tmp/mirothinker_seed_smoke/admin_console_all_seeds_v2.md --output
    /tmp/mirothinker_seed_smoke/admin_console_all_seeds_v3_after_priority_fix.json
    --skip-profile-fetch --timeout 25` -> 15 seeds, 1766 discovered,
    1766 unique, 0 failed fetches, 2 unresolved.
  * Before the priority fix, the same admin-seed roster-only smoke found only
    398 profiles because SUSTech/SZU roster pages were misclassified as
    direct-profile seeds.
  * Per-seed support classification after the fix:
    supported = 10 (`SUSTech`, `SIGS`, `CUHK AI`, `CUHK SDS`, `SZU` swift,
    math, cmce, cmse, cpoe, bio); parser_low_quality = 5 (`HIT CS`,
    `HIT IC`, `SZU chem`, `SZU ceie`, `SZU csse`); adapter_missing = 0.
  * Targeted adapter follow-up (2026-05-12, still no DB writes): added only
    low-quality page-structure handling for `HIT CS`, `HIT IC`, `SZU chem`,
    and `SZU ceie`; did not change already supported SUSTech/SIGS/CUHK/SZU
    math/cmce/cmse/cpoe/bio/swift paths.
  * Targeted tests:
    `uv run pytest tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_supports_hitsz_college_faculty_links
    tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_supports_szu_chemistry_plain_name_links
    tests/data_agents/professor/test_roster_validation.py::test_discover_professor_seeds_continues_ceie_category_pages_after_academician_page
    -q` -> 3 passed.
  * Broader protection tests:
    `uv run pytest tests/data_agents/professor/test_roster_validation.py -k
    "hitsz_college or szu_chemistry or ceie_category or
    prefers_roster_entries_for_roster_like_urls or direct_profile or
    uses_sigs_api or uses_hit_api or discover_cuhk_seed or
    supports_szu_nested_jsml_profile_links or
    supports_szu_relative_info_profile_links" -q` -> 25 passed.
  * Real non-mutating roster-only smoke after targeted adapters:
    `uv run python scripts/run_professor_crawler_e2e.py --seed-doc
    /tmp/mirothinker_seed_smoke/admin_console_all_seeds_v2.md --output
    /tmp/mirothinker_seed_smoke/admin_console_all_seeds_v5_after_chem_narrow.json
    --skip-profile-fetch --timeout 25` -> 15 seeds, 1982 discovered,
    1982 unique, 0 failed fetches, 1 unresolved.
  * Post-targeted classification: supported = 14; parser_low_quality = 1
    (`SZU csse`, fetch blocked by HTTP 412 JS challenge); adapter_missing = 0.
    `SZU csse` should not be forced through generic parsing; Phase B should
    mark it as fetch failure / pipeline_issue until a browser/challenge-safe
    adapter exists.
  * Execution rule for Phase B: do not assume one crawler fits all schools or
    departments. Preserve currently supported adapters/paths and add targeted
    school/department adapters only for parser_low_quality or adapter_missing
    seeds.

### T5 — Cron (Phase B complete)
- Cron files:
  `apps/admin-console/backend/seed_cron.py`,
  `apps/admin-console/backend/main.py`.
- Test output:
  `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seed_cron.py -q`
  -> 3 passed, 4 warnings.
- Cron iterates seeds by id, skips `in_progress` and `adapter_missing`,
  and reuses the same trigger path as manual runs.
- Schedule config: `ADMIN_PROFESSOR_SEED_CRON_ENABLED`,
  `ADMIN_PROFESSOR_SEED_CRON_DAY`,
  `ADMIN_PROFESSOR_SEED_CRON_HOUR`,
  `ADMIN_PROFESSOR_SEED_CRON_MINUTE`,
  `ADMIN_PROFESSOR_SEED_CRON_TIMEZONE`.
- Concurrency config: `ADMIN_PROFESSOR_SEED_CONCURRENCY`, default 4.

### T7 — Smoke (Phase B complete on test DB)
- Local smoke test result: admin-console started on
  http://0.0.0.0:8123 (free port; 8000 occupied); `/api/health` HTTP
  200 `{"status":"ok"}`; `/api/seeds` HTTP 200 returning 2 user-
  entered rows; `/seeds` SPA route HTTP 200 + browser-rendered Variant
  C UI confirmed by user 2026-05-10
- Phase B live smoke against test DB:
  - Started admin backend on `http://0.0.0.0:18188` with
    `DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock`
    and `ADMIN_PROFESSOR_SEED_CRON_ENABLED=0`.
  - `POST /api/seeds` created `NoAdapter University` with
    `last_run_status='never_run'`.
  - `POST /api/seeds/1/trigger` returned HTTP 202 with status
    `in_progress`.
  - Follow-up `GET /api/seeds/1` showed
    `last_run_status='adapter_missing'` and populated `last_run_at`.
  - DB query confirmed one `pipeline_issue` row with
    `stage='adapter_missing'`, `severity='medium'`, structured seed
    evidence, and the matching `pipeline_run` closed as `failed` with
    `items_failed=1`.
  - Browser smoke: `agent-browser --session phase-b-seeds open
    http://127.0.0.1:18188/seeds`, row count = 1, rendered state =
    `缺 adapter / adapter_missing`, screenshot saved to
    `/tmp/mirothinker_phase_b_seed_page.png`.
- Real local runtime enablement:
  - `miroflow_real` was at Alembic `V022`; Phase B requires V023 for
    `pipeline_issue.stage='adapter_missing'`.
  - Ran `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic upgrade head`
    -> upgraded `V022 -> V023`.
  - Started current backend against `miroflow_real` on
    `http://0.0.0.0:18188`; `/api/health` returns `{"status":"ok"}`;
    `/api/seeds` returns the real manually entered seed registry.
- Repeat verification and real-runtime smoke (2026-05-13):
  - Active ports: `18188` backend/API and `5180` frontend; `18088` retired.
  - `openspec validate prof-seed-admin-console` -> valid.
  - Admin-console targeted tests:
    `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seeds_api.py tests/test_seed_cron.py tests/test_migration_v023.py -q`
    -> 25 passed, 6 warnings.
  - `run_single_seed` Postgres tests first exposed a dirty shared
    `miroflow_test_mock` migration state before the test body. Rerunning the
    same suite against a one-off clean test database -> 4 passed.
  - Admin-console and miroflow-agent targeted ruff checks -> all checks
    passed.
  - `just frontend-fresh` -> TypeScript + Vite production build succeeded
    with only the existing large chunk warning.
  - `18188/api/seeds` and `5180/api/seeds` both returned 15 rows with
    identical hash
    `77033f56db7eec4e93d0ae7a150ff8b0246749f67ebaec865d826ff323161ad1`.
  - Temporary `.invalid` seed `id=23` on `miroflow_real` verified the full
    adapter-missing chain: create 201 `never_run`; trigger 202
    `in_progress` with run id `8adc87fe-0ee4-4a94-af95-a8e3d3cbbf5a`;
    immediate GET still `in_progress`; terminal GET `adapter_missing` with
    `last_run_at=2026-05-13T03:10:05.064719Z`; one unresolved
    `pipeline_issue.stage='adapter_missing'`; one failed
    `pipeline_run.run_kind='roster_crawl'` with `items_failed=1`;
    repeated trigger returned 422 and did not create a duplicate open issue.
  - Seed `23` was deleted after smoke; its tagged audit
    `pipeline_issue` and `pipeline_run` rows were intentionally retained.
  - Browser smoke on `http://127.0.0.1:5180/seeds` rendered "Seed 索引" and
    15 table rows, confirming the customer-facing UI reads the same backend
    data as `18188`.

## Failure modes that block archive

- T2 trigger endpoint accepts a request that the spec says should be
  rejected → spec / impl mismatch → fix impl; do not archive
- T4 adapter resolution stub somehow runs Tier 2/3 even when adapter
  missing → critical bug; do not archive
- Cron fires more than monthly → schedule misconfigured; fix and archive
- Frontend polling loop creates infinite recursion → broken; fix
- spec validation fails after implementation → spec / impl drift; either
  update spec (with another change) or update impl
