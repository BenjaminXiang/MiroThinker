## ADDED Requirements

### Requirement: The export is byte-deterministic

Exporting the same database snapshot twice MUST produce identical bytes and
therefore identical member hashes.

#### Scenario: Re-export

- **WHEN** the exporter runs twice against the same snapshot
- **THEN** both outputs have the same sha256

### Requirement: Exported rows pass the build's mapper

Every exported record MUST pass the build's released-objects mapper; the
validator MUST report per-domain acceptance counts and the first failures.

#### Scenario: Schema drift

- **WHEN** a field the mapper requires is missing
- **THEN** the validator fails that record and names the field

### Requirement: The build stays source-agnostic

The build MUST consume a manifest whose members may come from the database
export or from an external bundle, without code changes.

#### Scenario: Mixed manifest

- **WHEN** professors come from the export and patents from the old bundle
- **THEN** the build ingests both
