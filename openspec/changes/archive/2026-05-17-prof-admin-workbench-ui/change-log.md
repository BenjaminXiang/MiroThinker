# Change Log: prof-admin-workbench-ui

## 2026-05-14 — Child scaffolded

- Created the child OpenSpec artifact set from the
  `prof-admin-workbench` parent.
- Sequenced this child after the backend quality rework and fact
  backfill so the UI can render both diagnosis and populated canonical
  facts where available.
- Added explicit API-test-first and child-spec review gates.

## 2026-05-15 — Child review decisions

- Reviewed the child against the completed `prof-quality-status-rework`
  implementation and the scaffolded `prof-fact-extraction-expansion`
  contract.
- Pinned marking actor source to the `X-Admin-Actor` request header,
  falling back to `admin-console` when no auth-backed actor is present.
- Pinned frontend routing to the existing `/:domain/:id` route shape:
  professor records delegate to a dedicated workbench component, while
  company, paper, and patent continue using the generic detail viewer.

## 2026-05-15 — Implementation and verification

- Added the reversible `V025_add_professor_admin_action` migration.
- Added the `/api/admin/professor` triage, detail, and mark endpoints.
- Added API contract coverage for list filtering/sorting, seven-section
  detail payloads, and all three marking actions.
- Added the professor-specific React workbench route, render tests, and
  API client calls.
- Ran the local browser walkthrough against a seeded test professor and
  recorded screenshot evidence under
  `.agents/runs/prof-admin-workbench-ui/`.
