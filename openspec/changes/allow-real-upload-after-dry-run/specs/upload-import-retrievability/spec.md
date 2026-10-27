## ADDED Requirements

### Requirement: A dry run never blocks a real import

A successful dry run of a file MUST NOT cause a later real upload of the same
content to be rejected as a duplicate.

#### Scenario: Verify then commit

- **WHEN** a dry run of a workbook succeeded and the same file is then uploaded
  for real
- **THEN** the real upload is admitted (202) and a job is triggered

#### Scenario: Same mode still deduplicates

- **WHEN** a real upload is running or succeeded for a domain
- **THEN** another real upload of the same content returns 409
