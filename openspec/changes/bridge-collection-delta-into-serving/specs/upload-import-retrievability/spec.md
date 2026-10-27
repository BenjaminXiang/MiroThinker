## ADDED Requirements

### Requirement: Imported rows are searchable without a rebuild

Records present in the collection database but absent from the serving pack MUST
be publishable into the serving recall store, and answers MUST be able to cite
them as a local source.

#### Scenario: A company exists only in the collection database

- **WHEN** the delta publisher runs and the service restarts
- **THEN** a question about that company returns a citation with
  `type: company` and `url: null` (a local source)

#### Scenario: Re-running the publisher

- **WHEN** the publisher runs twice for the same record
- **THEN** the store holds one record for it (deterministic id)

### Requirement: Publishing is reversible and bounded

Before publishing, the operator MUST have a copy of the store directory; the
publisher MUST be dry-runnable so the delta can be reviewed.

#### Scenario: Dry run

- **WHEN** the publisher is invoked with `--dry-run`
- **THEN** it prints the missing records and writes nothing
