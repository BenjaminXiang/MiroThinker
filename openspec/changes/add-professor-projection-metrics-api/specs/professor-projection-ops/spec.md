## ADDED Requirements

### Requirement: Projection metrics are readable from the console

The console MUST expose the latest refresh metrics as JSON at
`/api/canonical-v2/admin/professor-projection`, behind the existing admin session
gate. A missing configuration MUST answer 503, a missing file 404, and unreadable
content 500; none of these may raise an unhandled error.

#### Scenario: Metrics published

- **WHEN** `CANONICAL_V2_PROFESSOR_PROJECTION_METRICS` points at a valid file
- **THEN** the endpoint returns 200 and the file's JSON object

#### Scenario: Not configured or missing

- **WHEN** the variable is unset, or the file does not exist
- **THEN** the endpoint returns 503 or 404 respectively, with a bounded detail string

### Requirement: The refresh runs unattended

A scheduled run MUST be able to resolve its paths from the environment, obtain the
embedding credential from the managed secrets, run the refresh, and publish the
metrics file. A failure MUST exit non-zero and leave the previous metrics intact.

#### Scenario: Weekly run

- **WHEN** the wrapper runs with a pack, an output directory and a metrics path
- **THEN** it exits 0 only after the metrics file is published

#### Scenario: Missing pack

- **WHEN** the configured pack directory does not exist
- **THEN** the wrapper exits non-zero before calling the refresh
