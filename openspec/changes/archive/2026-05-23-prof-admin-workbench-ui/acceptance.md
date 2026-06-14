# Acceptance: prof-admin-workbench-ui

## 1. Spec validation

- [x] `openspec validate prof-admin-workbench-ui` exits 0.
- [x] Child spec review is complete before implementation starts.

## 2. Migration

- [x] `professor_admin_action` exists with action, actor, note,
  observed watermark, and created timestamp.
- [x] Migration downgrade is reversible.
- [x] `observed_data_updated_at` is populated from the canonical
  watermark that includes external open issues.

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
- [x] Generic professor quality edits in the four-domain record editor
  are removed, disabled, or redirected through the marking endpoint.
- [x] Professor quality changes initiated from the admin UI are
  auditable through `professor_admin_action`.

## 4. Frontend

- [x] Quality diagnosis is visible on initial workbench render.
- [x] Marking buttons are visible and call the admin API.
- [x] Per-field provenance is reachable from key fields.
- [x] Experience section renders populated facts when available.
- [x] Experience section renders `not_extracted` placeholders when facts
  are absent.
- [x] The old generic professor quality dropdown is absent or disabled
  once the professor workbench route is active.
