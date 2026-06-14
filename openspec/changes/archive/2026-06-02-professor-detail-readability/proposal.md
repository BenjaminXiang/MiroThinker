## Why

Professor detail pages are currently hard to use for quality review because the workbench renders every `professor_fact` row in a single "research/output" table. For SIGS profiles such as Ahmed Elazab, this mixes research topics, education, work experience, awards, academic positions, contact, and homepage rows while omitting the official long research overview that is already stored in `profile_raw_text`.

## What Changes

- Add a readable `research_overview` field to the admin professor detail payload, extracted from official raw profile text when available.
- Reorganize the professor detail workbench so research topics, research overview, academic positions, education, work experience, awards, papers, and patents are shown in meaningful sections instead of one mixed fact table.
- Keep source/evidence and admin actions visible.
- Do not change canonical storage, summary generation, scraping, or quality-status semantics.

## Capabilities

### New Capabilities

- `professor-detail-readability`: Make professor detail pages readable for profile-summary and scrape-quality review.

### Modified Capabilities

- `professor-admin-workbench-ui`: The workbench detail view must group persisted facts by user-facing meaning and surface available official research overview text.

## Impact

- Affected backend code: `apps/admin-console/backend/api/admin_professors.py`.
- Affected frontend code: `apps/admin-console/frontend/src/pages/ProfessorWorkbench.tsx`, `apps/admin-console/frontend/src/api.ts`.
- Affected tests: admin professor API tests and ProfessorWorkbench frontend tests.
- No database migration, data refresh, or public `/api/professor/{id}` change.
