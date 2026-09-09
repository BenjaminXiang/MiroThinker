# professor-lifecycle-state Specification

## Purpose
Model whether a professor record is current, archived, or merged
independently from the record's data-quality status.

## Requirements
### Requirement: Lifecycle state is separate from quality

The system MUST persist professor lifecycle separately from
`quality_status`. Valid lifecycle states MUST include `active`,
`archived`, and `merged_to_other_school`.

#### Scenario: Archived record can be ready

- **GIVEN** a professor record is no longer active at the school
- **AND** its historical data is source-grounded and internally
  consistent
- **WHEN** quality is evaluated
- **THEN** lifecycle may be `archived`
- **AND** `quality_status` may remain `ready`

### Requirement: Retrieval defaults to active lifecycle

Professor retrieval MUST default to active professor records unless the
caller explicitly asks for archived or merged records.

#### Scenario: Archived professor excluded by default

- **GIVEN** a professor is `lifecycle_state="archived"`
- **WHEN** a normal professor search runs
- **THEN** the archived record is not returned unless explicitly
  requested
