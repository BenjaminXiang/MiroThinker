# Verification: prof-lifecycle-state

## 2026-05-23 schema slice

Scope:
- T1.1: storage shape selected.
- T1.2: reversible migration added.
- T1.3: schema tests/assertions added.

Storage decision:
- Add `professor.lifecycle_state text NOT NULL DEFAULT 'active'`.
- Add `professor.lifecycle_merged_into_id text NULL` with a self-FK to
  `professor.professor_id`.
- Keep lifecycle separate from `quality_status`.

TDD RED:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v030_migration.py -q -n0`
- Result: failed as expected because
  `V030_add_professor_lifecycle_state.py` did not exist.
- Failure evidence:
  `Missing migration file for V030: V030_add_professor_lifecycle_state.py`
  and `FileNotFoundError` for the same path.

TDD GREEN, no DB:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v030_migration.py -q -n0`
- Result: 2 passed, 3 skipped.
- Skips: DB-backed migration tests skipped because neither
  `DATABASE_URL_TEST` nor `DATABASE_URL` was set.

Temporary DB setup:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync python - <<'PY' ...`
- Result: created `miroflow_test_lifecycle_1779561926`.

TDD GREEN, temporary Postgres DB:
- Command:
  `cd apps/miroflow-agent && DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_1779561926 uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v030_migration.py -q -n0`
- Result: 5 passed.
- Evidence: full Alembic chain upgraded from base through V030, then
  downgraded from V030 back to base during test teardown.

Temporary DB cleanup:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync python - <<'PY' ...`
- Result: dropped `miroflow_test_lifecycle_1779561926`.

Files covered:
- `apps/miroflow-agent/alembic/versions/V030_add_professor_lifecycle_state.py`
- `apps/miroflow-agent/tests/storage/test_v030_migration.py`
- `apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py`

Pending:
- T2 writer/default/update helper behavior.
- T3 quality and active-default retrieval behavior.
- T4 admin/API lifecycle exposure and audit evidence.
- Final OpenSpec validation and phase E2E after behavior slices land.

## 2026-05-23 writer slice

Scope:
- T2.1: canonical writes default to `active`.
- T2.2: explicit lifecycle update helper for admin/backfill use.
- T2.3: normal pipeline refresh preserves explicit `archived` or merged
  state without evidence.

TDD RED:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/storage/test_v030_migration.py tests/professor/test_canonical_writer.py::test_write_new_professor_defaults_lifecycle_to_active tests/professor/test_canonical_writer.py::test_set_professor_lifecycle_state_updates_state_and_audit tests/professor/test_canonical_writer.py::test_normal_professor_refresh_preserves_explicit_archived_lifecycle -q -n0`
- Result: failed during collection as expected because
  `set_professor_lifecycle_state` did not exist.
- Failure evidence: `ImportError: cannot import name
  'set_professor_lifecycle_state'`.

TDD GREEN, no DB:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/storage/test_v030_migration.py tests/professor/test_canonical_writer.py::test_write_new_professor_defaults_lifecycle_to_active tests/professor/test_canonical_writer.py::test_set_professor_lifecycle_state_updates_state_and_audit tests/professor/test_canonical_writer.py::test_normal_professor_refresh_preserves_explicit_archived_lifecycle -q -n0`
- Result: 1 passed, 7 skipped.
- Skips: DB-backed migration/writer tests skipped because neither
  `DATABASE_URL_TEST` nor `DATABASE_URL` was set.

Temporary DB setup:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync python - <<'PY' ...`
- Result: created `miroflow_test_lifecycle_writer_1779562166`.

Temporary DB first run:
- Command:
  `cd apps/miroflow-agent && DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_writer_1779562166 uv run --no-sync pytest tests/storage/test_v030_migration.py tests/professor/test_canonical_writer.py::test_write_new_professor_defaults_lifecycle_to_active tests/professor/test_canonical_writer.py::test_set_professor_lifecycle_state_updates_state_and_audit tests/professor/test_canonical_writer.py::test_normal_professor_refresh_preserves_explicit_archived_lifecycle -q -n0`
- Result: 5 passed, 3 errors.
- Cause: existing writer fixture's seed loader reads `DATABASE_URL`, not
  `DATABASE_URL_TEST`.

TDD GREEN, temporary Postgres DB:
- Command:
  `cd apps/miroflow-agent && DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_writer_1779562166 DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_writer_1779562166 uv run --no-sync pytest tests/storage/test_v030_migration.py tests/professor/test_canonical_writer.py::test_write_new_professor_defaults_lifecycle_to_active tests/professor/test_canonical_writer.py::test_set_professor_lifecycle_state_updates_state_and_audit tests/professor/test_canonical_writer.py::test_normal_professor_refresh_preserves_explicit_archived_lifecycle -q -n0`
- Result: 8 passed.

Temporary DB cleanup:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync python - <<'PY' ...`
- Result: dropped `miroflow_test_lifecycle_writer_1779562166`.

Files covered:
- `apps/miroflow-agent/alembic/versions/V030_add_professor_lifecycle_state.py`
- `apps/miroflow-agent/src/data_agents/professor/canonical_writer.py`
- `apps/miroflow-agent/src/data_agents/canonical/professor.py`
- `apps/miroflow-agent/tests/storage/test_v030_migration.py`
- `apps/miroflow-agent/tests/professor/test_canonical_writer.py`

Pending:
- T3 quality and active-default retrieval behavior.
- T4 admin/API lifecycle exposure and audit evidence.
- Final OpenSpec validation and phase E2E after behavior slices land.

## 2026-05-23 quality/retrieval slice

Scope:
- T3.1: professor quality evaluator inputs read lifecycle separately.
- T3.2: lifecycle alone does not force non-ready quality.
- T3.3: professor retrieval defaults to active lifecycle records.
- T3.4: tests cover active, archived-ready, and merged cases.

TDD RED:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/data_agents/professor/test_professor_quality_status_rework.py::test_archived_professor_can_remain_ready_when_source_grounded tests/data_agents/service/test_retrieval_quality_filter.py::test_professor_lifecycle_defaults_to_active_when_quality_filter_disabled tests/data_agents/service/test_retrieval_quality_filter.py::test_professor_lifecycle_filter_can_request_archived_records -q -n0`
- Result: 3 failed.
- Failure evidence:
  `ProfessorCanonicalState.__init__() got an unexpected keyword argument
  'lifecycle_state'`, default retrieval returned archived records, and an
  explicit archived lifecycle filter returned no records because lifecycle
  metadata was not fetched.

TDD GREEN:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/data_agents/professor/test_professor_quality_status_rework.py::test_archived_professor_can_remain_ready_when_source_grounded tests/data_agents/service/test_retrieval_quality_filter.py::test_professor_lifecycle_defaults_to_active_when_quality_filter_disabled tests/data_agents/service/test_retrieval_quality_filter.py::test_professor_lifecycle_filter_can_request_archived_records -q -n0`
- Result: 3 passed.

Merged-case and broader focused check:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/data_agents/professor/test_professor_quality_status_rework.py tests/data_agents/service/test_retrieval_quality_filter.py -q -n0`
- Result: 24 passed.

Files covered:
- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
- `apps/miroflow-agent/src/data_agents/service/retrieval.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_professor_quality_status_rework.py`
- `apps/miroflow-agent/tests/data_agents/service/test_retrieval_quality_filter.py`

Pending:
- T4 admin/API lifecycle exposure and audit evidence.
- Final OpenSpec validation and phase E2E after behavior slices land.

## 2026-05-23 admin/API slice

Scope:
- T4.1: expose lifecycle state in professor admin detail payload.
- T4.2: add filtering by lifecycle state where appropriate.
- T4.3: add audit evidence for lifecycle changes.

TDD RED:
- Command:
  `cd apps/admin-console && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy uv run --no-sync pytest tests/test_domains_postgres.py::test_professor_released_object_exposes_lifecycle_separate_from_quality tests/test_domains_postgres.py::test_update_professor_lifecycle_records_admin_run_and_audit -q`
- Result: 2 failed as expected.
- Failure evidence: professor released object had no `lifecycle_state`;
  `backend.api.domains` had no `update_professor_lifecycle` endpoint.

TDD GREEN, unit:
- Command:
  `cd apps/admin-console && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy uv run --no-sync pytest tests/test_domains_postgres.py::test_professor_released_object_exposes_lifecycle_separate_from_quality tests/test_domains_postgres.py::test_update_professor_lifecycle_records_admin_run_and_audit -q`
- Result: 2 passed.

Broader admin domain unit/redirect check:
- Command:
  `cd apps/admin-console && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy uv run --no-sync pytest tests/test_domains_postgres.py tests/test_data_redirect.py -q`
- Result: 32 passed.

Temporary DB setup:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync python - <<'PY' ...`
- Result: created `miroflow_test_lifecycle_api_1779563051`.

Temporary Postgres admin API integration:
- Command:
  `cd apps/admin-console && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_api_1779563051 DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_api_1779563051 uv run --no-sync pytest tests/test_professor_api.py::test_professor_domain_detail_exposes_lifecycle_separate_from_quality tests/test_professor_api.py::test_filter_professor_domain_by_lifecycle_state tests/test_professor_api.py::test_update_professor_lifecycle_records_audit_action -q`
- Result: 3 passed.
- Evidence: `/api/professor/{id}` exposes lifecycle separately from
  `quality_status`; `/api/professor` filters by `lifecycle_state`;
  `PATCH /api/professor/{id}/lifecycle` returns archived lifecycle while
  keeping `quality_status='ready'` and writes a
  `professor_admin_action` row.

Frontend build:
- Command:
  `cd apps/admin-console/frontend && npm run build`
- Result: passed. Vite emitted the existing chunk-size warning.

Files covered:
- `apps/admin-console/backend/api/domains.py`
- `apps/admin-console/backend/api/data.py`
- `apps/admin-console/frontend/src/api.ts`
- `apps/admin-console/frontend/src/components/LifecycleTag.tsx`
- `apps/admin-console/frontend/src/pages/DomainList.tsx`
- `apps/admin-console/frontend/src/pages/RecordDetail.tsx`
- `apps/admin-console/tests/test_domains_postgres.py`
- `apps/admin-console/tests/test_professor_api.py`

Pending:
- Final T5 migration/schema, professor quality, retrieval verification.
- Final OpenSpec validation and phase E2E after T5 commands run.

## 2026-05-23 final T5 verification

T5.1 migration/schema:
- Command:
  `cd apps/miroflow-agent && DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_api_1779563051 uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v030_migration.py -q -n0`
- Result: 6 passed.
- Evidence: V030 upgraded from the full Alembic chain and downgraded
  through base during test teardown.

T5.2 professor quality:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/data_agents/professor/test_professor_quality_status_rework.py -q -n0`
- Result: 12 passed.

T5.3 retrieval active-default behavior:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync pytest tests/data_agents/service/test_retrieval_quality_filter.py -q -n0`
- Result: 12 passed.

Admin/API focused checks:
- Command:
  `cd apps/admin-console && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy uv run --no-sync pytest tests/test_domains_postgres.py tests/test_data_redirect.py -q`
- Result: 32 passed.
- Command:
  `cd apps/admin-console && env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_api_1779563051 DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_lifecycle_api_1779563051 uv run --no-sync pytest tests/test_professor_api.py::test_professor_domain_detail_exposes_lifecycle_separate_from_quality tests/test_professor_api.py::test_filter_professor_domain_by_lifecycle_state tests/test_professor_api.py::test_update_professor_lifecycle_records_audit_action -q`
- Result: 3 passed.

Frontend build:
- Command:
  `cd apps/admin-console/frontend && npm run build`
- Result: passed. Vite emitted the existing chunk-size warning.

Lint:
- Command:
  `cd apps/admin-console && uv run --no-sync ruff check backend/api/domains.py backend/api/data.py tests/test_domains_postgres.py tests/test_professor_api.py`
- Result: passed.
- Command:
  `cd apps/miroflow-agent && uv run --no-sync ruff check src/data_agents/canonical/professor.py src/data_agents/professor/canonical_writer.py src/data_agents/professor/quality_gate.py src/data_agents/service/retrieval.py tests/storage/test_alembic_revision_lineage.py tests/storage/test_v030_migration.py tests/professor/test_canonical_writer.py tests/data_agents/professor/test_professor_quality_status_rework.py tests/data_agents/service/test_retrieval_quality_filter.py`
- Result: passed.

OpenSpec validation:
- Command:
  `openspec validate prof-lifecycle-state --strict && openspec validate --changes --strict`
- Result: `prof-lifecycle-state` valid; all 5 active changes passed.

Temporary DB cleanup:
- Command:
  `cd apps/miroflow-agent && uv run --no-sync python - <<'PY' ...`
- Result: dropped `miroflow_test_lifecycle_api_1779563051`.

Archive:
- Command:
  `openspec archive prof-lifecycle-state -y`
- Result: archived to
  `openspec/changes/archive/2026-05-23-prof-lifecycle-state/` and created
  `openspec/specs/professor-lifecycle-state/spec.md`.
- Follow-up command:
  `openspec validate --changes --strict && openspec validate --specs --strict`
- Result: after archive, 4 active changes passed and 8 specs passed.
- Follow-up command:
  `openspec validate --specs --strict`
- Result: 8 specs passed after replacing the generated `Purpose TBD`
  text in the archived main spec.
