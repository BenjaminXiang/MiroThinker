# Spec: patent-page-only-canonical

> Capability: Patent titles declared on professor pages can be
> preserved and enriched even when no patent number is present.

## ADDED Requirements

### Requirement: Title-only page patents are preserved

The system MUST persist title-only patent candidates extracted from
professor pages instead of dropping them or only filing a diagnostic
issue. The persisted object may be a canonical patent row or a patent
candidate row, depending on the storage decision.

#### Scenario: Title-only patent starts needs enrichment

- **GIVEN** a professor page lists a patent title with no patent number
- **WHEN** patent homepage ingest runs
- **THEN** the title and evidence URL are persisted
- **AND** the candidate status is `needs_enrichment`

### Requirement: Numbered patent matching remains strict

Patent candidates with patent numbers MUST continue to hard-match on
normalized patent number.

#### Scenario: Numbered patent updates existing row

- **GIVEN** an existing patent row has patent number `CN123`
- **WHEN** page ingest sees the same number
- **THEN** the existing row is updated
- **AND** no duplicate patent row is inserted
