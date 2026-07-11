## ADDED Requirements

### Requirement: Product and acceptance failures create typed knowledge gaps

The system SHALL be able to record no-result, insufficient-evidence, repeated current-Web
dependence, missing-relationship, user-feedback, and benchmark-failure gaps. Each gap SHALL identify
the query/answer trace, release, affected domain/path, observed symptom, and available evidence.

#### Scenario: Local answer repeatedly depends on Web
- **WHEN** accepted telemetry shows that a frequently used in-scope query family repeatedly needs
  current-Web evidence because local facts are absent
- **THEN** the system records or updates a coverage/enrichment gap tied to the affected domain and
  query family

### Requirement: Gap classification distinguishes ownership

A gap SHALL distinguish at least knowledge coverage, identity, source conflict/freshness,
relationship, path reach, retrieval precision, context, synthesis, index parity, and provider
availability classes. Structured LLM judgment MAY propose classification and remediation, but the
record SHALL retain confidence and review state.

#### Scenario: Entity exists but relation path cannot reach it
- **WHEN** evidence proves both entities exist but the required typed relationship is absent or
  ineligible
- **THEN** the gap is classified as relationship/reach rather than entity coverage

### Requirement: Online evidence cannot directly close a canonical gap

An online Web or LLM result SHALL NOT close a canonical knowledge gap or mutate active canonical
state. Closing a canonical gap SHALL require an offline landing/build/release process with accepted
evidence.

#### Scenario: Web finds a missing Company fact
- **WHEN** current Web search supplies a fact absent from local canonical
- **THEN** the current answer may cite the Web fact
- **AND** the canonical gap remains open until a reviewed offline release accepts the assertion

### Requirement: Gap remediation is traceable to an accepted release

The system SHALL link recollection, reparsing, identity repair, relationship repair, enrichment,
query-policy change, or index repair performed for a gap to the gap and producing candidate release.
A gap SHALL close only when acceptance evidence demonstrates the intended user/operational effect.

#### Scenario: Missing relationship is added
- **WHEN** an accepted release adds the source-grounded relationship and the relation-path scenario
  passes
- **THEN** the gap records the accepted release and verification evidence before closing

### Requirement: Gap prioritization reflects product value and observed demand

Gap reports SHALL expose frequency/demand, affected PRD scenario families, severity, available
source evidence, and estimated owning lane so operators can prioritize high-impact remediation. The
system SHALL NOT treat every incomplete field as equal priority.

#### Scenario: Rare optional field and frequent failed relation compete
- **WHEN** operators review both gaps
- **THEN** the report exposes the user demand and PRD impact needed to prioritize the frequent failed
  relation without hiding the optional-field gap
