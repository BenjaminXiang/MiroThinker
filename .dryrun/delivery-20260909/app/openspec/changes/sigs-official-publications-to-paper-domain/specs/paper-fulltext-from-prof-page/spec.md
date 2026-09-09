## ADDED Requirements

### Requirement: SIGS official publication entries preserve direct PDF evidence

The professor-page paper ingest path MUST preserve direct PDF links found near SIGS official publication entries after author-prefixed citation parsing.

#### Scenario: SIGS publication entry links a direct PDF

- **GIVEN** a SIGS official publication entry contains a direct PDF link near the citation text
- **WHEN** homepage publication extraction and homepage paper ingest process the entry
- **THEN** the paper candidate carries the PDF URL as full-text evidence
- **AND** the professor-page PDF fetch path can attempt extraction subject to existing PDF fetch policy caps
