# Verification: prof-seed-admin-console

## 2026-05-12 seed validation preflight

Scope:
- Validate live seeds added through `/seeds`.
- Fix only the discovery priority issue that prevented existing adapters from
  running.
- Do not write professor rows, do not enable trigger, and do not run full E2E.

Commands and outcomes:

- `curl -sS http://127.0.0.1:18088/api/health`
  - Result: `{"status":"ok"}`

- DB query against `postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real`
  - Result: `professor_seed` has 15 rows; status distribution
    `never_run=15`.

- `agent-browser open http://127.0.0.1:5180/seeds && agent-browser get count 'tbody tr'`
  - Result: page renders 15 seed rows.

- `curl -sS -i -X POST http://127.0.0.1:18088/api/seeds/9/trigger`
  - Result: HTTP 405 Method Not Allowed, confirming Phase B trigger is not
    wired yet.

- `uv run pytest tests/data_agents/professor/test_roster_validation.py::test_discover_professor_seeds_prefers_roster_entries_for_roster_like_urls -q`
  - Red result before fix: 2 failed; formal discovery returned
    `direct_profile_seed_fetched` / `师资列表`.
  - Green result after fix: 2 passed.

- `uv run pytest tests/data_agents/professor/test_roster_validation.py -k "prefers_roster_entries_for_roster_like_urls or direct_profile or uses_sigs_api or uses_hit_api or discover_cuhk_seed" -q`
  - Result: 20 passed.

- `uv run python scripts/run_professor_crawler_e2e.py --seed-doc /tmp/mirothinker_seed_smoke/admin_console_all_seeds_v2.md --output /tmp/mirothinker_seed_smoke/admin_console_all_seeds_v3_after_priority_fix.json --skip-profile-fetch --timeout 25`
  - Result: 15 seeds, 1766 discovered, 1766 unique, 0 failed fetches,
    2 unresolved.

Per-seed classification after the priority fix:

| Seed | Adapter/path | Count | Classification |
|---|---:|---:|---|
| SUSTech school-wide | sustech-roster | 988 | supported |
| HIT CS | generic | 1 | parser_low_quality |
| HIT IC | generic | 3 | parser_low_quality |
| SZU chem | szu-teacher-family | 0 | parser_low_quality |
| SZU swift | szu-teacher-family | 9 | supported |
| SZU math | szu-teacher-family | 101 | supported |
| SZU cmce | szu-teacher-family | 123 | supported |
| SZU cmse | szu-teacher-family | 102 | supported |
| SZU cpoe | szu-teacher-family | 36 | supported |
| SZU bio | szu-teacher-family | 15 | supported |
| SZU ceie | szu-teacher-family | 3 | parser_low_quality |
| SZU csse | szu-teacher-family | 0 | parser_low_quality |
| SIGS school-wide | sigs_teacher_api | 250 | supported |
| CUHK AI | cuhk_teacher_search | 37 | supported |
| CUHK SDS | cuhk_teacher_search | 98 | supported |

Execution lessons:
- Keep school/department adapters explicit; do not attempt one universal
  crawler.
- Preserve existing supported paths (SUSTech, SIGS, CUHK, and supported SZU
  pages).
- Only inspect and change low-quality seeds next: HIT CS, HIT IC, SZU chem,
  SZU ceie, SZU csse.
- Do not wire `run_single_seed`/trigger until low-quality seeds either have
  targeted adapters or are explicitly classified as `adapter_missing`.

## 2026-05-12 targeted adapter follow-up

Additional commands and outcomes:

- `uv run pytest tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_supports_hitsz_college_faculty_links tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_supports_szu_chemistry_plain_name_links tests/data_agents/professor/test_roster_validation.py::test_discover_professor_seeds_continues_ceie_category_pages_after_academician_page -q`
  - Red result before targeted adapters: 3 failed.
  - Green result after targeted adapters: 3 passed.

- `uv run pytest tests/data_agents/professor/test_roster_validation.py -k "hitsz_college or szu_chemistry or ceie_category or prefers_roster_entries_for_roster_like_urls or direct_profile or uses_sigs_api or uses_hit_api or discover_cuhk_seed or supports_szu_nested_jsml_profile_links or supports_szu_relative_info_profile_links" -q`
  - Result: 25 passed.

- `uv run python scripts/run_professor_crawler_e2e.py --seed-doc /tmp/mirothinker_seed_smoke/admin_console_all_seeds_v2.md --output /tmp/mirothinker_seed_smoke/admin_console_all_seeds_v5_after_chem_narrow.json --skip-profile-fetch --timeout 25`
  - Result: 15 seeds, 1982 discovered, 1982 unique, 0 failed fetches,
    1 unresolved.

- `agent-browser open 'https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1'`
  - Result: navigation failed with `net::ERR_CONNECTION_CLOSED`.

- `curl -k 'https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1'`
  - Result: HTTP 412 with JS challenge page.

- `uv run ruff check src/data_agents/professor/discovery.py src/data_agents/professor/roster.py tests/data_agents/professor/test_roster_validation.py`
  - Result: all checks passed.

- `openspec validate prof-seed-admin-console`
  - Result: valid.

- `git diff --check`
  - Result: no whitespace errors.

Updated per-seed classification after targeted adapters:

| Seed | Adapter/path | Count | Classification |
|---|---:|---:|---|
| SUSTech school-wide | sustech-roster | 988 | supported |
| HIT CS | hitsz-college-teacher-family | 96 | supported |
| HIT IC | hitsz-college-teacher-family | 30 | supported |
| SZU chem | szu-teacher-family | 57 | supported |
| SZU swift | szu-teacher-family | 9 | supported |
| SZU math | szu-teacher-family | 101 | supported |
| SZU cmce | szu-teacher-family | 123 | supported |
| SZU cmse | szu-teacher-family | 102 | supported |
| SZU cpoe | szu-teacher-family | 36 | supported |
| SZU bio | szu-teacher-family | 15 | supported |
| SZU ceie | szu-teacher-family | 40 | supported |
| SZU csse | szu-teacher-family | 0 | parser_low_quality / fetch_blocked |
| SIGS school-wide | sigs_teacher_api | 250 | supported |
| CUHK AI | cuhk_teacher_search | 37 | supported |
| CUHK SDS | cuhk_teacher_search | 98 | supported |

Additional execution lessons:
- The next implementation step should not attempt to bypass the CSSE 412
  challenge with generic parsing.
- `run_single_seed` should distinguish unsupported adapters from fetch-blocked
  seeds: current CSSE has an adapter-family match but fetch fails, so it should
  be surfaced as failure/pipeline_issue rather than `adapter_missing`.

## 2026-05-12 Phase B implementation verification

Commands and outcomes:

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_run_single_seed.py::test_run_single_seed_deduplicates_repeated_open_adapter_missing_issue -q -n0`
  - Red result before fix: failed on `uq_pipeline_issue_open` duplicate
    open issue.
  - Green result after fix: 1 passed.

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0`
  - Result: 4 passed.

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seeds_api.py -q`
  - Result: 20 passed, 6 warnings.

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seed_cron.py -q`
  - Initial Phase B result: 1 passed, 4 warnings.
  - Close-out result after adding schedule/concurrency assertions:
    3 passed, 4 warnings.
  - Note: DB migration/fixture tests must run serially on the shared
    `miroflow_test_mock` database; a parallel attempt raced on Alembic DDL
    and failed with duplicate `seed_registry` type/table creation.

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_migration_v023.py::test_v023_downgrade_preserves_adapter_missing_issues_as_discovery -q`
  - Red result before fix: downgrade failed restoring the V022 CHECK
    constraint while rows still had `stage='adapter_missing'`.
  - Green result after fix: 1 passed.

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_migration_v023.py -q`
  - Result: 2 passed, 4 warnings.

- `uv run --no-sync ruff check backend/api/seeds.py backend/storage/seeds.py backend/seed_cron.py backend/main.py tests/test_seeds_api.py tests/test_seed_cron.py tests/test_migration_v023.py`
  - Result: all checks passed.

- `uv run --no-sync ruff check src/data_agents/professor/adapter_resolution.py src/data_agents/professor/seed_runner.py tests/postgres/test_run_single_seed.py alembic/versions/V023_extend_pipeline_issue_adapter_missing.py`
  - Result: all checks passed.

- `uv run --no-sync pytest tests/data_agents/professor/test_roster_validation.py -k "hitsz_college or szu_chemistry or ceie_category or prefers_roster_entries_for_roster_like_urls or direct_profile or uses_sigs_api or uses_hit_api or discover_cuhk_seed or supports_szu_nested_jsml_profile_links or supports_szu_relative_info_profile_links" -q`
  - Result: 25 passed.

- `just frontend-fresh`
  - Result: TypeScript + Vite production build succeeded. Vite emitted the
    existing large chunk warning only.

- `openspec validate prof-seed-admin-console`
  - Result: `Change 'prof-seed-admin-console' is valid`.

Broad-suite note:

- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest -q` in `apps/admin-console`
  - Result before V023 downgrade fix: 280 passed, 29 skipped, 24 failed,
    1 error.
  - The error was Phase-B-related (`V023` downgrade could not restore the
    old CHECK constraint with existing adapter-missing rows) and was fixed
    by converting such rows to `stage='discovery'` during downgrade.
  - The remaining 24 failures are outside this Phase B slice and match
    current admin/data API test drift patterns (`/api/data` response shape,
    stale frontend freshness warning expectations, upload logging capture).
    They were not broadened into this seed-management change.

Live test-DB smoke:

- Applied migrations to `miroflow_test_mock` with
  `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync alembic upgrade head`.
- Started admin backend on `http://0.0.0.0:18188` with cron disabled:
  `DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock ADMIN_PROFESSOR_SEED_CRON_ENABLED=0 CHAT_USE_RETRIEVAL_SERVICE=0 uv run --no-sync uvicorn backend.main:app --host 0.0.0.0 --port 18188`.
- `curl -sS http://127.0.0.1:18188/api/health`
  - Result: `{"status":"ok"}`.
- `POST /api/seeds` with `NoAdapter University`
  - Result: row created with `last_run_status='never_run'`.
- `POST /api/seeds/1/trigger`
  - Result: HTTP 202, response status `in_progress`, run id
    `e9e314e0-6533-46e4-989d-b7d861de9df0`.
- `GET /api/seeds/1`
  - Result: `last_run_status='adapter_missing'`, `last_run_at` populated.
- DB query after background task:
  - Result: `pipeline_issue.stage='adapter_missing'`, evidence contains
    seed id/school/url/run_id; matching `pipeline_run` is `failed` with
    `items_failed=1`.
- Browser smoke:
  - `agent-browser --session phase-b-seeds open http://127.0.0.1:18188/seeds`
  - `agent-browser --session phase-b-seeds get count 'tbody tr'`
  - Result: 1 rendered row; state shows `缺 adapter / adapter_missing`.
  - Screenshot: `/tmp/mirothinker_phase_b_seed_page.png`.

Real local runtime:

- Read-only Alembic version probe:
  - `miroflow_real: V022`
  - `miroflow_test_mock: None` after test fixture teardown.
- Applied Phase B schema to the real local admin database:
  `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic upgrade head`
  - Result: upgraded `V022 -> V023`.
- Started current admin backend against `miroflow_real` on
  `http://0.0.0.0:18188` with:
  `DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real CHAT_USE_RETRIEVAL_SERVICE=0 uv run --no-sync uvicorn backend.main:app --host 0.0.0.0 --port 18188`.
- `curl -sS http://127.0.0.1:18188/api/health`
  - Result: `{"status":"ok"}`.
- `curl -sS http://127.0.0.1:18188/api/seeds`
  - Result: returns the real seed registry rows, including the manually
    entered university/department URLs.

## 2026-05-13 repeat verification and real-runtime smoke

Service/port posture:

- `ss -ltnp | rg '(:18188|:5180|:18088)' || true`
  - Result: `18188` current uvicorn backend and `5180` Vite frontend were
    listening; no `18088` listener.

Repeat verification:

- `openspec validate prof-seed-admin-console`
  - Result: `Change 'prof-seed-admin-console' is valid`.
- `DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/test_seeds_api.py tests/test_seed_cron.py tests/test_migration_v023.py -q`
  in `apps/admin-console`
  - Initial repeat-verification result: 23 passed, 6 warnings.
  - Close-out result after adding schedule/concurrency assertions:
    25 passed, 6 warnings.
- `DATABASE_URL_TEST=...miroflow_test_mock uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0`
  in `apps/miroflow-agent`
  - Result: environment failure before test body. The shared test DB had
    stale V001 objects while Alembic attempted a base upgrade
    (`seed_registry` duplicate PostgreSQL type/table).
- Retried the same `tests/postgres/test_run_single_seed.py` command against a
  one-off clean database created via psycopg and dropped after the run.
  - Result: 4 passed.
- `uv run --no-sync ruff check backend/api/seeds.py backend/storage/seeds.py backend/seed_cron.py backend/main.py tests/test_seeds_api.py tests/test_seed_cron.py tests/test_migration_v023.py`
  in `apps/admin-console`
  - Result: all checks passed.
- `uv run --no-sync ruff check src/data_agents/professor/adapter_resolution.py src/data_agents/professor/seed_runner.py tests/postgres/test_run_single_seed.py alembic/versions/V023_extend_pipeline_issue_adapter_missing.py`
  in `apps/miroflow-agent`
  - Result: all checks passed.
- `just frontend-fresh`
  - Result: TypeScript + Vite production build succeeded; Vite emitted only
    the existing large chunk warning.

Real `miroflow_real` smoke:

- `GET /api/health` through both `18188` and `5180`
  - Result: both returned HTTP 200 `{"status":"ok"}`.
- `GET /api/seeds` through both `18188` and `5180`
  - Result: 15 rows from both, identical SHA-256
    `77033f56db7eec4e93d0ae7a150ff8b0246749f67ebaec865d826ff323161ad1`.
- Created temporary no-adapter seed:
  - `id=23`
  - school `PhaseB Smoke 20260513T031005Z`
  - URL `https://phase-b-smoke-20260513t031005z.invalid/roster`
  - Result: HTTP 201 with `last_run_status='never_run'`.
- `POST /api/seeds/23/trigger`
  - Result: HTTP 202, `status='in_progress'`,
    `run_id=8adc87fe-0ee4-4a94-af95-a8e3d3cbbf5a`.
- Immediate `GET /api/seeds/23`
  - Result: `last_run_status='in_progress'`, `last_run_at=NULL`.
- Polling `GET /api/seeds/23`
  - Result: reached `last_run_status='adapter_missing'` with
    `last_run_at=2026-05-13T03:10:05.064719Z`.
- DB audit query:
  - Result: exactly one unresolved `pipeline_issue` row with
    `stage='adapter_missing'`, `severity='medium'`, structured
    `{seed_id, school, department, seed_url, run_id}` evidence.
  - Result: exactly one matching `pipeline_run` row with
    `run_kind='roster_crawl'`, `status='failed'`, `items_failed=1`,
    `error_summary={'error':'adapter_missing','seed_id':23}`.
- Re-trigger while still `adapter_missing`:
  - Result: HTTP 422 with `{error, seed_id, school, department}` payload.
  - Follow-up DB count remained one open adapter-missing issue; no duplicate
    issue was created.
- Cleanup:
  - `DELETE /api/seeds/23` returned HTTP 204.
  - Follow-up `GET /api/seeds/23` returned HTTP 404.
  - Audit rows were intentionally retained:
    `seed23_adapter_missing_issues=1`, `seed23_pipeline_runs=1`.

UI smoke:

- `agent-browser --session phase-b-repeat open http://127.0.0.1:5180/seeds`
  followed by `wait --text "Seed 索引"` and `get count "tbody tr"`.
  - Result: page rendered, row count = 15.
  - Snapshot confirmed the customer-facing `5180` UI shows the same seed
    registry and row actions (`立即爬取`, `编辑`, `删除`).

Note:

- One browser check attempted to wait for the temporary seed text after the
  API cleanup had already deleted that row; it timed out. This was a smoke
  harness race, not a backend/UI regression. The UI smoke was rerun against
  the stable real seed list and passed.

Audit-trail retention decision:

- Earlier real-runtime smoke seed `22` was deleted from `professor_seed`,
  but its tagged audit rows remain: `pipeline_issue=1`, `pipeline_run=1`.
- Repeat smoke seed `23` was also deleted from `professor_seed`, and its
  tagged audit rows remain: `pipeline_issue=1`, `pipeline_run=1`.
- Decision: retain both sets as real `miroflow_real` Phase B smoke evidence.
  They are tagged by `seed_id` and no longer appear on the seed management
  page, so they do not pollute current seed operations.

## 2026-05-13 post-commit full-suite baseline

Scope:

- Record a broad-suite baseline after the Phase B + T7.5 commit stack.
- Do not repair historical suite drift in this evidence slice.
- Strip proxy environment variables before both commands:
  `http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`, `all_proxy`,
  and `ALL_PROXY`.

Commands and outcomes:

- `cd apps/miroflow-agent && uv run --no-sync pytest -q --tb=no`
  - Full log: `/tmp/miroflow-agent-full-pytest-20260513.log`.
  - Result: 13 failed, 1734 passed, 85 skipped, 1 xfailed, 1 warning,
    1 error in 107.54s.
  - Exit code: 1.
  - Baseline remains red. The reported failing/error tests are in the
    existing V021 migration, patent release, company/patent retrieval,
    Milvus-lite retrieval, professor publish dedupe, and patent release
    E2E areas; they are outside the Phase B seed-management and T7.5
    quality-status wiring slices.

- `cd apps/admin-console && uv run --no-sync pytest -q --tb=no`
  - Full log: `/tmp/admin-console-full-pytest-20260513.log`.
  - Result: 220 passed, 116 skipped, 12 warnings in 2.57s.
  - Exit code: 0.
