# Design: prof-lifecycle-state

## Scope

Add lifecycle state to professor canonical data:

- `active`: current record for this school.
- `archived`: no longer active at this school but retained for history.
- `merged_to_other_school`: this record should resolve to another
  canonical professor record or school context.

The implementation uses additive columns on `professor`:

- `lifecycle_state text NOT NULL DEFAULT 'active'`
- `lifecycle_merged_into_id text NULL`, a self-reference to
  `professor.professor_id`

This keeps lifecycle separate from `quality_status` while avoiding a
second table for the MVP persistence shape. Auditability is handled by
the explicit admin/backfill lifecycle helper and the existing
`professor_admin_action` table. Rollback drops the additive columns.

## Quality interaction

Lifecycle does not replace quality. A record can be
`lifecycle_state=archived` and `quality_status=ready` if the historical
data is source-grounded. The quality evaluator may raise
`needs_review` only when lifecycle evidence contradicts active
canonical facts.

## Admin and retrieval

Admin surfaces must show lifecycle state separately. Retrieval defaults
to active records unless the query or endpoint explicitly asks for
historical/archived records.

## Rollback

The lifecycle field is additive. Rollback sets all rows to active or
ignores the field from readers until the migration is reverted.
