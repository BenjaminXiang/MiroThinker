# Acceptance: prof-lifecycle-state

## Spec validation

- [x] `openspec validate prof-lifecycle-state` exits 0.

## Lifecycle

- [x] Professor lifecycle state is persisted separately from
  `quality_status`.
- [x] Archived, source-grounded records can remain `quality_status =
  ready`.
- [x] Retrieval defaults to active records.
- [x] Admin/API surfaces show lifecycle separately from quality.

## Evidence

- 2026-05-23 schema slice: V030 adds `professor.lifecycle_state` and
  `professor.lifecycle_merged_into_id` as additive columns separate from
  `quality_status`. Temporary-DB Alembic upgrade/downgrade and schema
  assertions passed. End-to-end lifecycle behavior remains pending until
  writer, quality/retrieval, and admin/API tasks are complete.
- 2026-05-23 writer slice: canonical professor writes default to `active`;
  explicit lifecycle updates use `set_professor_lifecycle_state`; normal
  professor refresh preserves explicit `archived` lifecycle. Temporary-DB
  writer tests passed. Quality/retrieval and admin/API behavior remain
  pending.
- 2026-05-23 quality/retrieval slice: quality input now reads lifecycle
  separately; archived and merged source-grounded records can remain
  `ready`; professor retrieval filters to `active` by default and allows
  explicit `lifecycle_state` filters for archived/merged records.
- 2026-05-23 admin/API slice: professor released-object payloads expose
  `lifecycle_state` and `lifecycle_merged_into_id` as top-level fields
  separate from `quality_status`; professor list supports
  `lifecycle_state` filtering; `PATCH /api/professor/{id}/lifecycle`
  writes `professor_admin_action(action='set_lifecycle_state')`; the
  admin UI renders lifecycle separately in professor list/detail.
- 2026-05-23 final verification: V030 migration/schema tests passed on
  temporary Postgres; professor quality tests passed; retrieval
  active-default lifecycle tests passed; admin-console targeted unit and
  temporary-DB API integration passed; frontend build passed; Ruff passed
  on touched Python files; `openspec validate prof-lifecycle-state
  --strict` and `openspec validate --changes --strict` passed.
