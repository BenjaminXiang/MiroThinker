# Spec: paper-pipeline-cleanup

> Capability: Legacy external-database paper discovery is retired so
> professor-page extraction remains the only production paper discovery
> source.

## ADDED Requirements

### Requirement: Production code must not call retired paper discovery

Production source MUST NOT import or invoke external-database paper
discovery functions that generate candidate papers by professor or
author identity. Retired discovery includes hybrid, Crossref author
search, Semantic Scholar author search, ORCID paper discovery, Google
Scholar profile discovery, and CV-PDF paper-list discovery when used as
candidate-list discovery.

Enrichment helpers MAY remain importable when they enrich an already
discovered paper canonical row by DOI or identifier.

#### Scenario: Forbidden hybrid import is rejected

- **GIVEN** a production module imports
  `discover_professor_paper_candidates_from_hybrid_sources`
- **WHEN** the forbidden-import guard runs
- **THEN** the guard fails
- **AND** the failure identifies the importing file

#### Scenario: Enrichment helper remains allowed

- **GIVEN** a module imports `enrich_paper_with_hybrid_sources`
- **WHEN** the forbidden-import guard runs
- **THEN** the import is allowed because it enriches an existing paper
  row rather than discovering papers by author

### Requirement: Legacy release scripts cannot advertise retired path

Scripts intended for release or E2E verification MUST NOT present
hybrid or Semantic Scholar author discovery as the current release
pipeline. A retained legacy script MUST clearly warn and point to the
page-first ingest path.

#### Scenario: Old release E2E is not a mainline path

- **GIVEN** an operator inspects available paper release commands
- **WHEN** they run the current paper release path
- **THEN** it uses page-first homepage ingest
- **AND** it does not call retired author-profile discovery
