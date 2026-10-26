## ADDED Requirements

### Requirement: The overlay follows the allowlist file

The serving process MUST reload the projection overlay when the configured file
changes, without a restart. When the file is unchanged, the loaded instance MUST
be reused.

#### Scenario: New allowlist published

- **WHEN** the file's mtime or size changes
- **THEN** the next claim uses the new records

#### Scenario: Unchanged file

- **WHEN** the file is untouched
- **THEN** the same overlay instance is reused

### Requirement: Publishing is atomic

Replacing the allowlist MUST be a rename over the target; a reader MUST never
observe a partially written file.

#### Scenario: Publish during traffic

- **WHEN** the wrapper publishes a new allowlist while claims are being rendered
- **THEN** each claim sees either the old or the new file, never a truncated one
