# Spec: professor-retrieval-index-split

> Capability: Professor retrieval uses separate identity and research
> vector indexes.

## ADDED Requirements

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
