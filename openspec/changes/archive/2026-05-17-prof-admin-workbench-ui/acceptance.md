# Acceptance: prof-admin-workbench-ui

## 1. Spec validation

- [x] `openspec validate prof-admin-workbench-ui` exits 0.
- [x] Child spec review is complete before implementation starts.

Evidence:

- `openspec validate prof-admin-workbench-ui` passed on 2026-05-15.
- Child review decisions are recorded in `design.md` and
  `change-log.md`.

## 2. Migration

- [x] `professor_admin_action` exists with action, actor, note,
  observed watermark, and created timestamp.
- [x] Migration downgrade is reversible.
- [x] `observed_data_updated_at` is populated from the canonical
  watermark that includes external open issues.

Evidence:

- `PYTHONPATH=/home/longxiang/MiroThinker UV_INDEX_URL=https://pypi.org/simple DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run pytest tests/test_migration_v025.py tests/test_admin_professor_api.py -q`
  passed with `10 passed`.
- `tests/test_migration_v025.py` verifies upgrade, action enum,
  foreign key behavior, and downgrade removal.
- `tests/test_admin_professor_api.py` verifies mark action rows and
  canonical watermark population.

## 3. Admin API

- [x] Triage list supports filtering by `quality_status`.
- [x] Triage list supports filtering by reason rule id.
- [x] Triage list supports sorting by open issue count.
- [x] Detail endpoint returns identity, contact, research/output,
  experience, cleaned summary, sources/evidence, and quality diagnosis.
- [x] `confirm_ready` appends an action row and updates
  `quality_status`.
- [x] `send_to_review` appends an action row and updates
  `quality_status`.
- [x] `flag_recrawl` appends an action row and pipeline issue without
  changing `quality_status`.

Evidence:

- `tests/test_admin_professor_api.py` covers the triage list filters,
  open-issue sorting, seven-section detail payload, and all three mark
  actions.

## 4. Frontend

- [x] Quality diagnosis is visible on initial workbench render.
- [x] Marking buttons are visible and call the admin API.
- [x] Per-field provenance is reachable from key fields.
- [x] Experience section renders populated facts when available.
- [x] Experience section renders `not_extracted` placeholders when facts
  are absent.

Evidence:

- `npm test` passed for `ProfessorWorkbench.test.tsx`; it asserts the
  diagnosis banner, three mark buttons, populated experience, field
  provenance text, and `not_extracted` placeholder state.
- `npm run build` passed.
- Local browser walkthrough loaded
  `/professor/PROF-BROWSER-WORKBENCH`; the backend served the SPA,
  assets, and `/api/admin/professor/PROF-BROWSER-WORKBENCH` with 200
  responses.
- Screenshot evidence:
  `.agents/runs/prof-admin-workbench-ui/professor-workbench.png`.
