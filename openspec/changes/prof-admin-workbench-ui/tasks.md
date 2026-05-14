# Tasks: prof-admin-workbench-ui

## 1. Child spec review gate

- [ ] T1.1: Review this child spec after
  `prof-quality-status-rework` and the fact-extraction contract are
  scaffolded.
- [ ] T1.2: Confirm the exact actor source for marking actions.
- [ ] T1.3: Confirm frontend route strategy for professor detail.

## 2. Migration

- [ ] T2.1: Add the `professor_admin_action` migration.
- [ ] T2.2: Add downgrade path.
- [ ] T2.3: Add migration tests for action enum and foreign key.

## 3. Admin API

- [ ] T3.1: Add `/api/admin/professor` triage list endpoint.
- [ ] T3.2: Add `/api/admin/professor/{id}` rich detail endpoint.
- [ ] T3.3: Add `/api/admin/professor/{id}/mark` endpoint.
- [ ] T3.4: Add contract tests for list filters and sorting.
- [ ] T3.5: Add contract tests for seven-section detail payload.
- [ ] T3.6: Add marking endpoint tests for all three actions.

## 4. Frontend

- [ ] T4.1: Add professor-specific workbench component.
- [ ] T4.2: Route professor detail to the new component while leaving
  other domains on the generic viewer.
- [ ] T4.3: Render diagnosis banner and marking actions.
- [ ] T4.4: Render provenance affordances for key fields.
- [ ] T4.5: Add frontend render tests for populated and
  `not_extracted` experience states.

## 5. Verification

- [ ] T5.1: Run admin-console API tests.
- [ ] T5.2: Run frontend lint/test/build where tooling is present.
- [ ] T5.3: Run a browser walkthrough against the local admin console.
- [ ] T5.4: Record screenshots or route evidence in
  `.agents/runs/prof-admin-workbench-ui/`.
