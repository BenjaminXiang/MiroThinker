# Acceptance Evidence

## Requirement: Research overview is visible and source-grounded

- Evidence: `uv run --no-sync pytest tests/test_admin_professor_api.py::test_admin_professor_detail_extracts_research_overview_from_raw_profile -q` failed before the fix when the raw text began with SIGS-style tab navigation labels.
- Evidence: The same command passed after the API skipped navigation-label matches and extracted the first valid research section body.
- Evidence: `curl http://127.0.0.1:5180/api/admin/professor/PROF-823D4761D493` returned `research_output.research_overview` with Ahmed Elazab's full official research paragraph beginning with `My research focuses on developing trustworthy artificial intelligence for medical image analysis`.

## Requirement: Professor detail facts are grouped by user-facing meaning

- Evidence: `npm run test -- src/pages/ProfessorWorkbench.test.tsx` passed with assertions for `研究领域介绍`, `研究方向`, `学术兼职`, `教育经历`, `工作经历`, and `荣誉奖项`.
- Evidence: `agent-browser --session prof-detail snapshot -c` showed Ahmed Elazab's page grouped into research overview, research topics, academic positions, education, work experience, awards, cleaned summary, and source evidence sections.

## Requirement: Existing detail actions and quality diagnostics continue to work

- Evidence: `uv run --no-sync pytest tests/test_admin_professor_api.py -q` passed with 6 passed, 1 skipped.
- Evidence: `npm run test` passed with 2 test files and 4 tests passed.
- Evidence: `npm run build` passed for the admin console frontend.
- Evidence: `uv run --no-sync ruff check backend/api/admin_professors.py tests/test_admin_professor_api.py` passed.
- Evidence: `openspec validate professor-detail-readability --strict` passed.
