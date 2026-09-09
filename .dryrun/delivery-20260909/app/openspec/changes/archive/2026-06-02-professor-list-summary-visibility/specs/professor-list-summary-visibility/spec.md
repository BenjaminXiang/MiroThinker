## ADDED Requirements

### Requirement: Professor list shows profile summary previews
The admin professor list MUST render a readable preview of each professor's `summary_fields.profile_summary` when the field is present.

#### Scenario: Summary preview appears in professor list
- **WHEN** an operator opens `/professor` and the list API returns a row with `summary_fields.profile_summary`
- **THEN** the row displays that profile summary in the professor list

#### Scenario: Missing summary remains visible as missing
- **WHEN** an operator opens `/professor` and the list API returns a row with no `summary_fields.profile_summary`
- **THEN** the row displays a missing-value placeholder for the summary preview
