# professor-admin-workbench-ui Specification

## Purpose
TBD - created by archiving change prof-admin-workbench-ui. Update Purpose after archive.
## Requirements
### Requirement: Admin triage list

The admin API MUST expose a paginated professor triage list under
`/api/admin/professor`. The list MUST include quality status, open
issue count, latest admin action, official-source presence, and reason
rule ids where available.

The list MUST support filtering and sorting by quality status, reason
rule id, open issue count, latest admin action, and official-source
presence.

#### Scenario: Filter to needs_review

- **GIVEN** professors span multiple quality statuses
- **WHEN** the admin filters the triage list to `needs_review`
- **THEN** only anomaly-review professors are returned

### Requirement: Rich professor detail payload

The admin API MUST expose `/api/admin/professor/{id}` with identity,
contact, research/output, experience, cleaned summary,
sources/evidence, and quality diagnosis sections. The existing lean
`/api/professor/{id}` endpoint MUST remain unchanged.

#### Scenario: Quality diagnosis is visible in detail payload

- **GIVEN** a professor has non-ready quality reasons
- **WHEN** the admin detail endpoint is called
- **THEN** the response includes `quality_diagnosis.status` and
  `quality_diagnosis.reasons`

### Requirement: Lightweight marking actions

The admin API MUST support `confirm_ready`, `send_to_review`, and
`flag_recrawl` marking actions. Each action MUST append a
`professor_admin_action` row with actor, note, timestamp, and observed
canonical watermark.

`confirm_ready` and `send_to_review` MUST update `quality_status`.
`flag_recrawl` MUST write a pipeline issue using an existing stage
value and MUST NOT change `quality_status`.

#### Scenario: flag_recrawl does not change status

- **GIVEN** a professor is `low_confidence`
- **WHEN** an admin records `flag_recrawl`
- **THEN** the professor remains `low_confidence`
- **AND** an admin action row and pipeline issue row are written

### Requirement: Workbench frontend

The professor detail route MUST render a professor-specific audit
workbench with the quality diagnosis visible on initial render and
provenance reachable from key fields.

#### Scenario: Experience placeholder remains contract-compatible

- **GIVEN** no structured experience facts exist for a professor
- **WHEN** the workbench renders the experience section
- **THEN** it renders a `not_extracted` state without breaking the
  layout

