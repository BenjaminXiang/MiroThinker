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

## Tests

API contract tests precede frontend work. Frontend tests should verify
that the diagnosis banner is visible on initial render and that the
experience section handles both populated facts and `not_extracted`.
