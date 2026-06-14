# Design: prof-admin-workbench-ui

## Scope

This child change adds the admin-facing professor workbench after the
quality evaluator and fact backfill are available. It is additive:
existing lean domain APIs remain unchanged, and the new operational
surface lives under `/api/admin/professor/*`.

## Migration

Add `professor_admin_action`:

- `action_id`;
- `professor_id`;
- `action` (`confirm_ready`, `send_to_review`, `flag_recrawl`);
- `actor`;
- `note`;
- `observed_data_updated_at`;
- `created_at`.

The migration is additive and reversible. `observed_data_updated_at`
stores the canonical watermark at action time: professor, facts,
affiliations, and external open `pipeline_issue` activity.

## API

`GET /api/admin/professor` returns a paginated triage list with:

- professor id and display name;
- institution;
- `quality_status`;
- open issue count;
- latest admin action;
- official-source presence;
- top reason rule ids where available.

It supports filtering and sorting by quality status, reason rule id,
open issue count, latest admin action, and official-source presence.

`GET /api/admin/professor/{id}` returns seven sections:

- identity;
- contact;
- research and output;
- experience;
- cleaned summary;
- sources and evidence;
- quality diagnosis.

`POST /api/admin/professor/{id}/mark` accepts `confirm_ready`,
`send_to_review`, or `flag_recrawl`.

`confirm_ready` and `send_to_review` append an action row and update
`quality_status`. `flag_recrawl` appends an action row and writes a
`pipeline_issue` with an existing stage value; it does not change
`quality_status`.

Generic professor quality edits in the existing domain-detail API must
be reconciled with this action model. After this change ships,
professor `quality_status` changes initiated from the admin UI must go
through `/api/admin/professor/{id}/mark` so the action is auditable and
watermark-bound. The generic four-domain record editor may remain for
non-professor domains, but it must not provide an unaudited bypass for
professor quality decisions.

## Frontend

The workbench uses a single-column Layout A:

- quality diagnosis banner at the top;
- marking action buttons in the banner;
- identity, contact, research/output, summary, experience, and sources
  sections below;
- provenance is reachable from the relevant field without leaving the
  page.

If `prof-fact-extraction-expansion` has populated experience facts, the
experience section renders them. If not, the same API contract can
return `status: "not_extracted"` placeholders.

## Review gate decisions

This child spec was re-reviewed after `prof-quality-status-rework` and
`prof-fact-extraction-expansion` were archived. The backend quality engine,
structured facts, profile summaries, lifecycle state, and V032 schema are now
available as upstream contracts for this child.

Actor source:

- Until authentication exists in the admin console, marking endpoints MUST use
  an explicit request-body `actor` with default `admin-console`.
- The actor MUST be persisted verbatim in `professor_admin_action.actor`.
- Future authenticated-user integration may replace the default, but it must not
  remove the persisted actor field or append-only audit row.

Frontend route strategy:

- Keep the stable detail URL shape `/:domain/:id`.
- The professor detail route MUST render the professor workbench for
  `domain === "professor"`.
- Company, paper, and patent detail routes MUST continue using the generic
  record detail viewer.
- The old generic professor quality dropdown must be absent, disabled, or
  redirected through the marking endpoint once the professor workbench route is
  active.

## Tests

API contract tests precede frontend work. Frontend tests should verify
that the diagnosis banner is visible on initial render and that the
experience section handles both populated facts and `not_extracted`.
Tests must also prove the legacy generic professor quality edit path is
removed, disabled, or redirected to the marking endpoint.
