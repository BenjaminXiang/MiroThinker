## ADDED Requirements

### Requirement: Canonical V2 keeps domain knowledge strongly typed

The system SHALL expose typed canonical Professor, Company, Paper, and Patent objects and their
PRD-required business sub-objects. Shared provenance and relationship machinery SHALL NOT replace
typed domain fields needed for validation, filtering, display, or analysis.

#### Scenario: Patent filtering uses typed facts
- **WHEN** a query filters patents by patent type and publication year
- **THEN** the filter is evaluated against typed Patent facts
- **AND** it does not depend on extracting those values from an untyped summary or graph property

### Requirement: Domain inclusion follows the authoritative PRD

Each domain SHALL apply its own versioned inclusion policy. Professor inclusion SHALL follow the
approved Shenzhen institution seed roster; Paper inclusion SHALL follow Professor-roster-anchored
discovery; Patent inclusion SHALL accept the approved platform export scope without pre-filtering by
topic or linkage; Company inclusion SHALL accept approved skeleton batches plus independently
validated Shenzhen innovation companies.

#### Scenario: National Web result stays outside local Company canonical
- **WHEN** a current-Web query returns a relevant non-Shenzhen Company that is not in an approved
  skeleton batch and does not satisfy the Company inclusion policy
- **THEN** it may support the current answer as Web evidence
- **AND** it is not automatically included as a canonical Company

### Requirement: Source assertions are retained independently of canonical values

Every source-provided field or relationship assertion SHALL remain linked to its landing evidence,
source identity, observation time, and decision history. Selecting a canonical value SHALL NOT
delete or overwrite competing assertions.

#### Scenario: Official page and historical record disagree
- **WHEN** an official page and a historical recovered row assert different current titles for one
  Professor
- **THEN** both assertions remain queryable for audit
- **AND** the canonical decision identifies which assertion supports the current projection

### Requirement: Canonical selection combines deterministic constraints and structured LLM judgment

Canonical selection SHALL first enforce deterministic identity, source, time, and field-specific
constraints. It MAY use a schema-validated LLM decision to compare surviving assertions. Each
selection SHALL record supporting evidence, decision method/version, confidence, rationale, and any
unresolved conflict.

#### Scenario: Sources remain materially ambiguous
- **WHEN** deterministic constraints and structured LLM judgment cannot reliably choose between two
  material assertions
- **THEN** the system preserves an unresolved conflict
- **AND** it does not silently flatten the values into one unsupported fact

### Requirement: Canonical identity resolution is reversible

Strong identifiers and high-confidence composite evidence SHALL support automatic identity
resolution. Ambiguous cases SHALL use structured LLM judgment and, for high-impact unresolved cases,
review. Merge and split decisions SHALL preserve source identities, evidence, decision lineage, and
reversal history.

#### Scenario: Historical mistaken merge is split
- **WHEN** accepted evidence proves that one historical identity represented two real-world objects
- **THEN** the rebuilt release contains two canonical identities
- **AND** source facts and relationships are reassigned through an auditable split decision

### Requirement: Canonical relationships use a typed extensible catalog

Each canonical relationship SHALL use a registered type defining source and target types, direction,
role semantics, evidence obligations, allowed state, and applicable time semantics. The catalog
SHALL cover PRD-required identity/lifecycle, organization/role, scholarly output, intellectual
property, Company business/product/event, taxonomy/topic/geography, and evidence/lineage families.

#### Scenario: Professor founded a Company
- **WHEN** evidence supports that a Professor founded a Company
- **THEN** the canonical relationship identifies the Professor, Company, founder role, evidence,
  confidence/state, and applicable time information
- **AND** it is distinguishable from employment, advice, investment, or generic cooperation

### Requirement: Derived and session relations are not canonical facts

The system SHALL represent similarity, ranking, trend, representative-result selection, and other
reproducible computations as release-scoped derived relations. It SHALL represent referents,
displayed result sets, active constraints, and conversation paths as session relations. Neither
category SHALL be represented as a source-grounded canonical relationship.

#### Scenario: Similar Paper recommendation changes after re-embedding
- **WHEN** a new embedding release changes Paper similarity order
- **THEN** the derived recommendation may change without changing canonical Paper facts or
  source-grounded relationships

### Requirement: Inclusion and path eligibility are separate

The system SHALL evaluate retrieval eligibility by named, versioned path. Exact lookup, verified
relationship traversal, semantic recall, recommendation, and ranking SHALL NOT share one global
`ready` interpretation. Eligibility results SHALL carry limitations and policy version.

#### Scenario: Incomplete identified Paper is exactly requested
- **WHEN** an included Paper has a stable identity and source-grounded title but lacks enrichment
- **THEN** exact lookup may return the Paper with a visible limitation
- **AND** semantic recommendation eligibility is evaluated independently

### Requirement: Ordinary quality gaps are soft signals

Missing enrichment, partial summaries, ordinary uncertainty, or stale non-material fields SHALL
normally affect score, disclosure, review, or enrichment rather than exclude an object. Hard
exclusion SHALL require a named invariant such as wrong identity, terminal merge/rejection, unsafe
exposure, broken reference, or no usable source-grounded facts.

#### Scenario: Professor profile summary is incomplete
- **WHEN** an included Professor has verified identity and affiliation but an incomplete profile
  summary
- **THEN** the Professor remains available to an appropriate exact or structured path
- **AND** the gap is disclosed or queued for enrichment rather than hidden by a global gate

### Requirement: Canonical temporal semantics are proportional to product meaning

Every assertion SHALL retain observation/fetch time and SHALL retain source publication/event time
when present. Naturally changing facts SHALL support validity start/end when known. Static fields
without time-dependent meaning SHALL NOT be required to implement full bitemporal history.

#### Scenario: Professor changes institution
- **WHEN** accepted evidence establishes a Professor's move from one institution to another
- **THEN** the current projection shows the new affiliation
- **AND** the prior affiliation and its validity/evidence remain available for history and audit
