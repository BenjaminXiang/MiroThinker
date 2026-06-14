# professor-retrieval-index-split Specification

## Purpose
Define the professor retrieval contract for separate identity and
research vector indexes, including query-intent routing and traceable
fusion for ambiguous professor queries.
## Requirements
### Requirement: Professor vectors are split by intent

The system MUST maintain separate professor identity and research vector
collections. Identity vectors MUST embed stable identity and affiliation
fields. Research vectors MUST embed research topics, profile summary,
paper summary, and patent summary.

#### Scenario: Research vector excludes identity-heavy text

- **GIVEN** a professor has name, institution, department, research
  topics, and paper summary
- **WHEN** the research vector input is built
- **THEN** research topics and summaries are included
- **AND** identity-only fields do not dominate the text

### Requirement: Retrieval routes by query intent

Professor retrieval MUST choose identity or research collection based on
query intent. Ambiguous queries MAY search both and fuse results while
preserving traceability.

#### Scenario: Expert-finding query uses research collection

- **GIVEN** a user asks for professors working on a research topic
- **WHEN** professor retrieval runs
- **THEN** it queries `professor_research_profiles`

#### Scenario: Name lookup uses identity collection

- **GIVEN** a user asks for a named professor
- **WHEN** professor retrieval runs
- **THEN** it queries `professor_identity_profiles`

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

