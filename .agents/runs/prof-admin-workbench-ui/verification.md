# Verification: prof-admin-workbench-ui

Date: 2026-05-15

## TDD evidence

- Migration/API RED:
  `tests/test_migration_v025.py` and `tests/test_admin_professor_api.py`
  initially failed before `V025_add_professor_admin_action.py`,
  `backend/api/admin_professors.py`, and router wiring were added.
- Frontend RED:
  `npm test` initially failed before `ProfessorWorkbench.tsx` existed,
  then failed once on a missing React import in the test file.
- GREEN:
  The final verification commands below passed after implementation.

## Commands

- `PYTHONPATH=/home/longxiang/MiroThinker UV_INDEX_URL=https://pypi.org/simple DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run pytest tests/test_migration_v025.py tests/test_admin_professor_api.py -q`
  - Result: `10 passed`.
- `npm test`
  - Result: passed.
- `npm run build`
  - Result: passed; Vite emitted the existing large-chunk warning.
- `PYTHONPATH=/home/longxiang/MiroThinker UV_INDEX_URL=https://pypi.org/simple uv run ruff check backend/api/admin_professors.py backend/main.py tests/test_admin_professor_api.py tests/test_migration_v025.py`
  - Result: passed.
- `UV_INDEX_URL=https://pypi.org/simple uv run ruff check alembic/versions/V025_add_professor_admin_action.py`
  - Result: passed.
- `openspec validate prof-admin-workbench-ui`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Browser walkthrough

- Test database:
  `postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock`.
- Seed professor:
  `PROF-BROWSER-WORKBENCH`.
- Route:
  `http://127.0.0.1:18188/professor/PROF-BROWSER-WORKBENCH`.
- Backend evidence:
  the local admin server returned 200 for the SPA route, built JS/CSS
  assets, and `/api/admin/professor/PROF-BROWSER-WORKBENCH`.
- Render evidence:
  headless Chrome rendered the workbench with `Browser Workbench
  Professor`, `质量诊断`, `confirm_ready`, `send_to_review`,
  `flag_recrawl`, `Experience`, `PhD, Example University`, and
  `Sources And Evidence`.
- Screenshot:
  `.agents/runs/prof-admin-workbench-ui/professor-workbench.png`
  (`1440 x 1200` PNG).

Note: `agent-browser open` worked only when launched with a direct proxy
override, but follow-up snapshot commands selected an `about:blank` tab.
The walkthrough therefore used the same installed Chrome binary directly
with `--headless=new`, `--proxy-server=direct://`, and
`--proxy-bypass-list='*'`.
