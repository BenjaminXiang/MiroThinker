## MODIFIED Requirements

### Requirement: Professor vectors are split by intent

The system SHALL maintain release-versioned Professor identity and research index projections.
Identity projections SHALL represent stable identity and affiliation facts. Research projections
SHALL represent research topics, profile synthesis, and eligible Paper/Patent-derived research
signals. Each projection SHALL identify the canonical Professor, release, projection policy,
embedding model, and content hash. Physical collection names are not public compatibility
requirements.

#### Scenario: Research projection excludes identity dominance
- **WHEN** a Professor has identity, affiliation, research topics, and eligible research summaries
- **THEN** the research projection emphasizes research topics and summaries
- **AND** identity-only text does not dominate the embedded content
- **AND** projection metadata retains release and canonical identity traceability

#### Scenario: Identity projection remains exact-name useful
- **WHEN** an identity projection is built
- **THEN** it includes the accepted name, aliases needed for retrieval, institution, department, and
  title facts
- **AND** it does not depend on research enrichment being complete

### Requirement: Retrieval routes by query intent

A validated retrieval plan SHALL select the Professor identity projection, research projection, or
both according to query intent and protected constraints. When both are searched, fusion SHALL
deduplicate canonical identities and retain per-projection traceability.

#### Scenario: Expert-finding query uses research projection
- **WHEN** a user asks for Professors working on a research topic
- **THEN** the plan queries the research projection

#### Scenario: Name lookup uses identity projection
- **WHEN** a user asks for a named Professor
- **THEN** the plan queries the identity projection or exact typed store as required
- **AND** incomplete research enrichment does not hide a valid identity match

#### Scenario: Ambiguous mixed query uses both projections
- **WHEN** a query combines an ambiguous Professor name with a research topic
- **THEN** the plan may query both identity and research projections
- **AND** fusion returns one canonical candidate per Professor with traceable contributing evidence

## ADDED Requirements

### Requirement: Candidate release builds and verifies split Professor projections

Each Canonical V2 candidate release SHALL build the expected Professor identity and research
projections under the release's path-eligibility and embedding policy. Promotion SHALL require
deterministic parity between eligible canonical Professors/content and actual projection points.

#### Scenario: Research eligibility changes
- **WHEN** a candidate changes the Professor research eligibility policy
- **THEN** it rebuilds the affected research projection fully
- **AND** promotion is blocked on missing, extra, stale, or cross-release points

## REMOVED Requirements

### Requirement: P9 refreshes split Professor collections

**Reason**: P9, fixed collection names, and legacy payload compatibility are implementation details
of the pre-launch index pipeline and conflict with versioned release/index publication.

**Migration**: Build release-versioned identity and research projections, verify manifest parity,
and promote serving aliases only with the accepted Canonical V2 release.
