# Acceptance: prof-admin-workbench-ui

## 1. Spec validation

- [ ] `openspec validate prof-admin-workbench-ui` exits 0.
- [ ] Child spec review is complete before implementation starts.

## 2. Migration

- [ ] `professor_admin_action` exists with action, actor, note,
  observed watermark, and created timestamp.
- [ ] Migration downgrade is reversible.
- [ ] `observed_data_updated_at` is populated from the canonical
  watermark that includes external open issues.

## 3. Admin API

- [ ] Triage list supports filtering by `quality_status`.
- [ ] Triage list supports filtering by reason rule id.
- [ ] Triage list supports sorting by open issue count.
- [ ] Detail endpoint returns identity, contact, research/output,
  experience, cleaned summary, sources/evidence, and quality diagnosis.
- [ ] `confirm_ready` appends an action row and updates
  `quality_status`.
- [ ] `send_to_review` appends an action row and updates
  `quality_status`.
- [ ] `flag_recrawl` appends an action row and pipeline issue without
  changing `quality_status`.

## 4. Frontend

- [ ] Quality diagnosis is visible on initial workbench render.
- [ ] Marking buttons are visible and call the admin API.
- [ ] Per-field provenance is reachable from key fields.
- [ ] Experience section renders populated facts when available.
- [ ] Experience section renders `not_extracted` placeholders when facts
  are absent.
