## ADDED Requirements

### Requirement: P9 refreshes split Professor collections

The Professor split-index retrieval contract MUST support a P9 refresh that
rebuilds the identity and research collections from current canonical
Professor rows. The refresh MUST preserve the existing collection names and
payload shapes.

#### Scenario: Default Professor refresh targets split collections

- **WHEN** P9 runs the Professor index backfill without a single collection
  override
- **THEN** the refresh targets `professor_identity_profiles`
- **AND** the refresh targets `professor_research_profiles`
- **AND** it does not require the legacy `professor_profiles` collection

#### Scenario: Refreshed split payloads retain traceability metadata

- **WHEN** Professor identity and research payloads are written during P9
- **THEN** payloads include the Professor id and quality status metadata
- **AND** the research payload includes research directions and summary fields
- **AND** the identity payload includes name, institution, department, title,
  and profile identity text
