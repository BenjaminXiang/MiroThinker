# Source Links: prof-admin-workbench-ui

## Parent and specs

- `openspec/changes/prof-admin-workbench/` — Epic parent contract.
- `openspec/changes/prof-quality-status-rework/` — evaluator and
  quality diagnosis source.
- `openspec/changes/prof-fact-extraction-expansion/` — experience fact
  source.

## Code to inspect before implementation

- `apps/admin-console/backend/api/domains.py` — current lean professor
  projection.
- `apps/admin-console/backend/api/*.py` — route patterns and test
  fixtures.
- `apps/admin-console/frontend/src/pages/RecordDetail.tsx` — current
  generic detail viewer.
- `apps/admin-console/frontend/src/pages/DomainList.tsx` — current
  list view.
- `apps/admin-console/tests/test_professor_api.py` — nearest backend
  API tests.
- `apps/admin-console/tests/` — admin-console test fixtures.
