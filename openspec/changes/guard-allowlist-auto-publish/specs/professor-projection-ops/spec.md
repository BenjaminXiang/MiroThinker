## ADDED Requirements

### Requirement: Unattended publish is bounded

An automatic allowlist publish MUST refuse when the new list is too small
(< 300 records) or shrinks by more than 10% versus the live list, leaving the
live file untouched and exiting non-zero.

#### Scenario: A refresh returns far fewer professors

- **WHEN** the new allowlist has 400 records and 536 are live
- **THEN** the wrapper exits 4 and publishes nothing

#### Scenario: Normal week

- **WHEN** the new list has at least 300 records and shrinks by at most 10%
- **THEN** it is published atomically and the previous file is kept as `.prev`

### Requirement: Rollback is one file

The previous generation MUST remain readable next to the live file so an operator
can restore it without re-running the refresh.

#### Scenario: Bad publish spotted later

- **WHEN** an operator restores `professor-projection-allowlist.json.prev`
- **THEN** the next claim uses the restored records (the overlay hot-reloads)
