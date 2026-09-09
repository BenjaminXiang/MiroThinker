# Verification

## Commands

- `uv run --no-sync pytest tests/test_admin_professor_api.py::test_admin_professor_detail_extracts_research_overview_from_raw_profile -q`
  - Result before fix: failed, showing the extractor returned SIGS tab navigation text instead of the research paragraph.
  - Result after fix: passed.
- `uv run --no-sync pytest tests/test_admin_professor_api.py -q`
  - Result: 6 passed, 1 skipped.
- `uv run --no-sync ruff check backend/api/admin_professors.py tests/test_admin_professor_api.py`
  - Result: all checks passed.
- `npm run test -- src/pages/ProfessorWorkbench.test.tsx`
  - Result: 1 test file passed, 3 tests passed.
- `npm run test`
  - Result: 2 test files passed, 4 tests passed.
- `npm run build`
  - Result: passed; Vite reported the existing large chunk warning.
- `openspec validate professor-detail-readability --strict`
  - Result: change is valid.
- `curl -sS -o /tmp/prof_detail_823d.json -w '%{http_code}\n' http://127.0.0.1:5180/api/admin/professor/PROF-823D4761D493`
  - Result: 200.
- `agent-browser --session prof-detail wait --text '研究领域介绍'`
  - Result: found the text.
- `agent-browser --session prof-detail wait --text 'My research focuses on developing trustworthy artificial intelligence for medical image analysis'`
  - Result: found the text.
- `agent-browser --session prof-detail snapshot -c`
  - Result: page showed grouped research overview, research topics, academic positions, education, work experience, awards, cleaned summary, and source evidence.
- `curl -sS -o /tmp/prof_detail_823d_100.json -w '%{http_code}\n' http://100.64.0.4:5180/api/admin/professor/PROF-823D4761D493`
  - Result: 502 from this execution environment.

## Runtime

- Restarted the admin backend on port `18188` with `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real`.
- Left the existing frontend dev server on port `5180` running.
