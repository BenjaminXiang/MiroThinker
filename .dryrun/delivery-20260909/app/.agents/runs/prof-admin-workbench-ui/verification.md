# Verification: prof-admin-workbench-ui

## Pending

This child run workspace was created by the `prof-admin-workbench`
parent close-out (T2.3) on 2026-05-23.

Implementation and E2E evidence must be added here when the
`prof-admin-workbench-ui` phase starts. Do not mark this child complete
until its own `tasks.md`, `acceptance.md`, and verification commands are
updated with current evidence.

## 2026-05-23 - T1 Review Gate and T2 Migration

Scope:
- T1.1 re-review child spec after upstream quality/fact/lifecycle/schema work.
- T1.2 confirm actor source for marking actions.
- T1.3 confirm frontend route strategy.
- T2.1-T2.3 verify `professor_admin_action` migration, downgrade, action enum,
  and professor foreign key.

Review gate decisions:
- Upstream dependencies are available as archived/current contracts:
  `prof-quality-status-rework`, `prof-fact-extraction-expansion`,
  `prof-lifecycle-state`, and current schema head V032.
- Marking action actor source is explicit request-body `actor`, defaulting to
  `admin-console` until auth exists.
- Frontend keeps URL shape `/:domain/:id`; professor detail renders the
  professor workbench, and other domains remain on the generic detail viewer.

Commands:
- `openspec validate prof-admin-workbench-ui --strict`
  - Result: `Change 'prof-admin-workbench-ui' is valid`.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_prof_admin_v025_codex uv run --no-sync pytest tests/storage/test_v025_migration.py tests/storage/test_alembic_revision_lineage.py -q -n0`
  - Setup: created temporary database `miroflow_test_prof_admin_v025_codex`.
  - Result: `5 passed in 4.18s`.
  - Teardown: dropped temporary database
    `miroflow_test_prof_admin_v025_codex`.
- `uv run --no-sync ruff check tests/storage/test_v025_migration.py alembic/versions/V025_add_professor_admin_action.py tests/storage/test_alembic_revision_lineage.py`
  - Result: `All checks passed!`.

Artifacts updated:
- `openspec/changes/prof-admin-workbench-ui/design.md`
- `openspec/changes/prof-admin-workbench-ui/change-log.md`
- `openspec/changes/prof-admin-workbench-ui/tasks.md`
- `openspec/changes/prof-admin-workbench-ui/acceptance.md`
- `apps/miroflow-agent/tests/storage/test_v025_migration.py`

Status:
- T1.1-T1.3 complete.
- T2.1-T2.3 complete.
- T3 admin API remains pending.
- P4 seed adapter coverage remains blocked by missing
  `prof-seed-adapter-coverage` OpenSpec owner; no seed crawler production code
  was edited in this slice.

## 2026-05-23 - T3 Admin API

Scope:
- T3.1 add `/api/admin/professor` triage list endpoint.
- T3.2 add `/api/admin/professor/{id}` rich detail endpoint.
- T3.3 add `/api/admin/professor/{id}/mark` endpoint.
- T3.4-T3.6 add contract tests for list/detail/marking behavior.
- T3.7-T3.8 block generic professor `quality_status` bypass while preserving
  non-professor generic quality edits.

RED:
- `uv run --no-sync pytest tests/test_admin_professor_api.py tests/test_domains_postgres.py::test_patch_professor_quality_status_requires_admin_mark_endpoint tests/test_domains_postgres.py::test_patch_company_quality_status_keeps_generic_contract -q`
  - Result: `5 failed, 1 passed`.
  - Expected failures:
    - `/api/admin/professor` was routed through the generic domain catch-all and
      returned 422.
    - `/api/admin/professor/{id}` returned the SPA fallback HTML instead of JSON.
    - `/api/admin/professor/{id}/mark` returned 405.
    - Generic professor `quality_status` patch did not raise the required audit
      bypass error.

GREEN:
- `uv run --no-sync pytest tests/test_admin_professor_api.py tests/test_domains_postgres.py::test_patch_professor_quality_status_requires_admin_mark_endpoint tests/test_domains_postgres.py::test_patch_company_quality_status_keeps_generic_contract -q`
  - Result: `7 passed, 4 warnings in 0.05s`.
  - Warnings: existing FastAPI `on_event` deprecation warnings from
    `backend/main.py`.
- `uv run --no-sync ruff check backend/api/admin_professors.py backend/api/domains.py backend/main.py tests/test_admin_professor_api.py tests/test_domains_postgres.py`
  - Result: `All checks passed!`.

Artifacts updated:
- `apps/admin-console/backend/api/admin_professors.py`
- `apps/admin-console/backend/main.py`
- `apps/admin-console/backend/api/domains.py`
- `apps/admin-console/tests/test_admin_professor_api.py`
- `apps/admin-console/tests/test_domains_postgres.py`
- `openspec/changes/prof-admin-workbench-ui/tasks.md`
- `openspec/changes/prof-admin-workbench-ui/acceptance.md`

Status:
- T3.1-T3.8 complete.
- T4 frontend workbench remains pending.

## 2026-05-23 - T4 Frontend Implementation Partial

Scope:
- T4.1 add professor-specific workbench component.
- T4.2 route professor detail to the new component while other domains stay on
  the generic viewer.
- T4.3 render diagnosis banner and marking actions.
- T4.4 render provenance affordances for key fields.
- T4.5 remove the generic professor quality dropdown by routing professor
  detail away from `GenericRecordDetail`.

Implementation:
- Added `ProfessorWorkbench.tsx`.
- Added `fetchAdminProfessorDetail` and `markAdminProfessor` frontend API
  helpers.
- `RecordDetail.tsx` now dispatches `domain === "professor"` to
  `ProfessorWorkbench`; company/paper/patent remain on the generic detail
  viewer.

Verification:
- `npm run build`
  - Result: passed.
  - Output summary: `tsc -b && vite build`, `3051 modules transformed`,
    build completed in `5.88s`.
  - Warning: existing Vite chunk-size warning for a bundle larger than 500 kB.

Status:
- T4.1-T4.5 complete by implementation and build verification.
- T4.6 remains pending because the frontend has no installed test runner or
  `npm test` script. Do not mark T4 complete until render-test coverage is added
  or an OpenSpec-approved browser walkthrough replacement is recorded.

## 2026-05-23 - T4.6 Frontend Render Tests

Scope:
- Add frontend render tests for populated professor workbench state.
- Add frontend render tests for `not_extracted` experience state.
- Add route coverage proving professor detail uses the workbench instead of the
  generic record editor.

Initial RED:
- `npm test`
  - Result: failed before test environment polyfills were added.
  - Root cause: jsdom did not provide browser APIs required by Ant Design
    responsive and style helpers (`window.matchMedia`, pseudo-element
    `getComputedStyle` calls), so the workbench failed during mount.

GREEN:
- `npm test`
  - Result: `1 passed (1)`, `3 passed (3)`.
- `npm run build`
  - Result: passed.
  - Output summary: `tsc -b && vite build`, `3051 modules transformed`,
    build completed in `6.10s`.
  - Warning: existing Vite chunk-size warning for a bundle larger than 500 kB.
- `uv run --no-sync pytest tests/test_admin_professor_api.py tests/test_domains_postgres.py::test_patch_professor_quality_status_requires_admin_mark_endpoint tests/test_domains_postgres.py::test_patch_company_quality_status_keeps_generic_contract -q`
  - Result: `7 passed, 4 warnings in 0.04s`.
  - Warnings: existing FastAPI `on_event` deprecation warnings from
    `backend/main.py`.
- `uv run --no-sync ruff check backend/api/admin_professors.py backend/api/domains.py backend/main.py tests/test_admin_professor_api.py tests/test_domains_postgres.py`
  - Result: `All checks passed!`.

Artifacts updated:
- `apps/admin-console/frontend/package.json`
- `apps/admin-console/frontend/package-lock.json`
- `apps/admin-console/frontend/src/pages/ProfessorWorkbench.test.tsx`
- `apps/admin-console/frontend/src/pages/ProfessorWorkbench.tsx`
- `openspec/changes/prof-admin-workbench-ui/tasks.md`
- `openspec/changes/prof-admin-workbench-ui/acceptance.md`

Status:
- T4.6 complete.
- T5 final verification and browser walkthrough remain pending.

## 2026-05-23 - T5 Final Verification and Browser Walkthrough

Scope:
- Run final admin API and frontend verification.
- Run browser walkthrough against local admin console.
- Verify marking creates `professor_admin_action` rows.
- Verify generic professor quality edits cannot silently overwrite the marking
  workflow.

Pattern repair:
- Reported case: browser preflight against a migrated V032 Postgres database
  returned 500 for `/api/admin/professor/PROF-ADMIN-1`.
- Root cause: `backend/api/admin_professors.py` selected `p.email`, but the
  current `professor` table has no physical `email` column.
- Invariant: professor contact data in admin detail comes from active
  `professor_fact` rows with `fact_type = 'contact'`, matching the canonical
  writer contract.
- Sibling search:
  - `rg -n "p\\.email|professor\\.email|email" apps/admin-console/backend apps/admin-console/tests apps/miroflow-agent/alembic/versions`
    found the admin-professor detail query as the only direct `p.email`
    schema violation.
  - Searches over admin-professor SQL and professor migrations confirmed
    contact email belongs to the fact model, not the `professor` table.
- Fix level: Level 4 schema-contract repair with migrated-schema regression.

RED:
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_prof_admin_browser_codex uv run --no-sync pytest tests/test_admin_professor_api.py::test_admin_professor_detail_and_mark_use_migrated_schema -q`
  - Result: failed with `psycopg.errors.UndefinedColumn: column p.email does not exist`.

GREEN:
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_prof_admin_browser_codex uv run --no-sync pytest tests/test_admin_professor_api.py::test_admin_professor_detail_and_mark_use_migrated_schema -q`
  - Result: `1 passed, 5 warnings in 5.40s`.
  - Warnings: existing FastAPI `on_event` deprecations plus psycopg pool
    default-open deprecation.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_prof_admin_browser_codex uv run --no-sync pytest tests/test_admin_professor_api.py tests/test_domains_postgres.py::test_patch_professor_quality_status_requires_admin_mark_endpoint tests/test_domains_postgres.py::test_patch_company_quality_status_keeps_generic_contract -q`
  - Result: `8 passed, 5 warnings in 5.46s`.
- `uv run --no-sync ruff check backend/api/admin_professors.py backend/api/domains.py backend/main.py tests/test_admin_professor_api.py tests/test_domains_postgres.py`
  - Result: `All checks passed!`.
- `npm test`
  - Result: `1 passed (1)`, `3 passed (3)`.
- `npm run build`
  - Result: passed.
  - Output summary: `tsc -b && vite build`, `3051 modules transformed`,
    build completed in `6.22s`.
  - Warning: existing Vite chunk-size warning for a bundle larger than 500 kB.

Browser walkthrough:
- Temporary database:
  `miroflow_test_prof_admin_browser_codex`, upgraded to Alembic V032.
- Server:
  `ADMIN_PROFESSOR_SEED_CRON_ENABLED=0 DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_prof_admin_browser_codex uv run --no-sync uvicorn backend.main:app --host 127.0.0.1 --port 18195 --log-level info`
- URL:
  `http://127.0.0.1:18195/professor/PROF-ADMIN-1`
- Evidence:
  - Initial snapshot showed professor workbench, quality diagnosis,
    `ada@example.edu`, provenance links, populated experience row, and no
    generic edit button.
  - Clicked `确认就绪`, entered note `Browser walkthrough confirm_ready.`, and
    submitted.
  - Post-submit snapshot showed quality tag `就绪`, identity status `resolved`,
    and action-history row `confirm_ready / admin-console / Browser walkthrough
    confirm_ready.`.
  - Generic overwrite probe:
    `curl -X PATCH http://127.0.0.1:18195/api/professor/PROF-ADMIN-1 --data '{"quality_status":"needs_review"}'`
    returned HTTP `409` with
    `professor_quality_requires_mark_endpoint`.
  - Database probe after generic overwrite attempt returned
    `('ready', 'resolved')` for `professor.quality_status/identity_status` and
    one `professor_admin_action` row.
- Screenshots:
  - `.agents/runs/prof-admin-workbench-ui/browser-workbench-before.png`
  - `.agents/runs/prof-admin-workbench-ui/browser-workbench-after-confirm-ready.png`

Artifacts updated:
- `apps/admin-console/backend/api/admin_professors.py`
- `apps/admin-console/tests/test_admin_professor_api.py`
- `openspec/changes/prof-admin-workbench-ui/tasks.md`
- `openspec/changes/prof-admin-workbench-ui/acceptance.md`
- `openspec/changes/prof-admin-workbench-ui/change-log.md`
- `.agents/runs/prof-admin-workbench-ui/browser-workbench-before.png`
- `.agents/runs/prof-admin-workbench-ui/browser-workbench-after-confirm-ready.png`

Status:
- T5.1-T5.5 complete.
- `prof-admin-workbench-ui` implementation tasks are complete pending final
  OpenSpec validation.
