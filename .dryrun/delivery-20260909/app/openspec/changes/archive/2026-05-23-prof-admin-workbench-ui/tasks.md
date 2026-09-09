# Tasks: prof-admin-workbench-ui

## 1. Child spec review gate

- [x] T1.1: Review this child spec after
  `prof-quality-status-rework` and the fact-extraction contract are
  scaffolded.
- [x] T1.2: Confirm the exact actor source for marking actions.
- [x] T1.3: Confirm frontend route strategy for professor detail.

## 2. Migration

- [x] T2.1: Add the `professor_admin_action` migration.
- [x] T2.2: Add downgrade path.
- [x] T2.3: Add migration tests for action enum and foreign key.

## 3. Admin API

- [x] T3.1: Add `/api/admin/professor` triage list endpoint.
- [x] T3.2: Add `/api/admin/professor/{id}` rich detail endpoint.
- [x] T3.3: Add `/api/admin/professor/{id}/mark` endpoint.
- [x] T3.4: Add contract tests for list filters and sorting.
- [x] T3.5: Add contract tests for seven-section detail payload.
- [x] T3.6: Add marking endpoint tests for all three actions.
- [x] T3.7: Remove, disable, or redirect generic professor
  `quality_status` edits in `apps/admin-console/backend/api/domains.py`
  so professor quality changes cannot bypass `professor_admin_action`.
- [x] T3.8: Add a regression test proving professor quality edits from
  the generic domain API are blocked or routed through the marking
  endpoint, while non-professor domain edits keep their current
  contract.

## 4. Frontend

- [x] T4.1: Add professor-specific workbench component.
- [x] T4.2: Route professor detail to the new component while leaving
  other domains on the generic viewer.
- [x] T4.3: Render diagnosis banner and marking actions.
- [x] T4.4: Render provenance affordances for key fields.
- [x] T4.5: Remove or disable the generic professor quality dropdown in
  the old record-detail editor once the professor workbench route is
  active.
- [x] T4.6: Add frontend render tests for populated and
  `not_extracted` experience states.

## 5. Verification

- [x] T5.1: Run admin-console API tests.
- [x] T5.2: Run frontend lint/test/build where tooling is present.
- [x] T5.3: Run a browser walkthrough against the local admin console.
- [x] T5.4: Verify professor quality changes create
  `professor_admin_action` rows and cannot be overwritten silently by
  generic editor save.
- [x] T5.5: Record screenshots or route evidence in
  `.agents/runs/prof-admin-workbench-ui/`.
