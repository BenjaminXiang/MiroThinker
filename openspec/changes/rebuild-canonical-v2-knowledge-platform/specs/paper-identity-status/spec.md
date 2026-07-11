## MODIFIED Requirements

### Requirement: Paper identity-status values and default

The system SHALL represent each canonical Paper identity decision with the states
`{confirmed, unverified, rejected, merged}`. A newly included Paper SHALL begin as `unverified`
unless accepted identity evidence confirms it during the same candidate build. The state SHALL be a
versioned canonical identity decision and SHALL NOT depend on preserving the V020 physical column.

#### Scenario: New Paper has no accepted strong identity evidence
- **WHEN** a newly included Paper has source-grounded title/authorship but no accepted strong
  identifier or equivalent identity decision
- **THEN** its canonical identity state is `unverified`
- **AND** path eligibility is evaluated separately

### Requirement: Identity-status reflects resolved-identifier provenance

The system SHALL set a Paper identity to `confirmed` only when the accepted release records the
supporting identifier or equivalent strong identity assertions, source evidence, resolution policy,
and decision trace. A fixed provider list SHALL NOT substitute for retained provenance.

#### Scenario: DOI resolution confirms a Paper
- **WHEN** a trusted DOI assertion resolves to the Paper under the accepted identity policy
- **THEN** the Paper identity is `confirmed`
- **AND** the confirmation identifies the DOI evidence and resolution decision

#### Scenario: Professor-page-only Paper remains unverified
- **WHEN** a Professor page supplies a plausible Paper record but no accepted strong identity
  assertion confirms it
- **THEN** the Paper identity remains `unverified`
- **AND** the Professor-page evidence is retained

### Requirement: Rejected or merged papers are excluded from retrieval

A `rejected` Paper identity SHALL be hard-excluded from all user retrieval paths. A `merged` Paper
identity SHALL not appear as an independent result and SHALL resolve only to an eligible canonical
survivor with merge lineage. An `unverified` Paper SHALL NOT be globally excluded; exact lookup,
verified relationship traversal, semantic recall, recommendation, and ranking SHALL each apply their
versioned path-eligibility policy and limitations.

#### Scenario: Rejected Paper is absent
- **WHEN** any user retrieval path evaluates a Paper with identity state `rejected`
- **THEN** the Paper is not returned as an active result

#### Scenario: Merged Paper resolves to survivor
- **WHEN** an old or source identity resolves to a `merged` Paper
- **THEN** retrieval follows the merge to the eligible canonical survivor
- **AND** the merged identity does not occupy a separate result position

#### Scenario: Unverified Paper is exactly requested
- **WHEN** an `unverified` Paper has usable source-grounded facts and matches an exact request
- **THEN** the exact path may return it with an identity limitation
- **AND** semantic/recommendation eligibility remains independently evaluated

### Requirement: Identity-status rejection is reversible

Paper identity rejection and merge decisions SHALL be versioned, evidence-backed, and reversible by
a later accepted release. Reversal SHALL preserve the prior decision and rationale. Identity state
SHALL remain distinct from ordinary content quality and enrichment signals.

#### Scenario: Strong identity evidence reverses a rejection
- **WHEN** a later accepted release establishes that a previously rejected Paper identity is valid
- **THEN** the current identity decision may transition away from `rejected`
- **AND** the prior rejection remains in decision history

#### Scenario: Identity rejection does not erase content evidence
- **WHEN** a Paper identity is rejected
- **THEN** its source assertions and content evidence remain in landing/knowledge history
- **AND** they are not published as an active Paper result

### Requirement: Rejections carry evidence and run_id

Every applied Paper identity or Professor-Paper relationship rejection SHALL identify the affected
identity or relationship, supporting evidence, structured decision confidence/rationale, policy and
model versions when used, and producing build/review run.

#### Scenario: Relationship attribution is rejected
- **WHEN** an accepted build rejects a Professor-Paper attribution
- **THEN** the relationship decision records evidence, confidence, rationale, versions, and run
- **AND** the Paper identity is not rejected unless a separate Paper identity decision supports it

## ADDED Requirements

### Requirement: Same-person rejection changes attribution, not Paper existence

Rejecting the hypothesis that a Paper author is a particular Professor SHALL transition the affected
Professor-Paper relationship assertion or decision. It SHALL NOT by itself reject the Paper identity
or assert that the Paper does not exist.

#### Scenario: Last Professor attribution is rejected
- **WHEN** the same-person decision rejects the last accepted Professor-Paper attribution for an
  otherwise plausible Paper
- **THEN** the attribution becomes rejected or unresolved according to policy
- **AND** the Paper identity retains the state supported by its own evidence

## REMOVED Requirements

### Requirement: LLM same-person-gate rejection transitions identity_status

**Reason**: The legacy behavior conflates rejection of one Professor attribution with rejection of
the Paper's existence/identity, causing relationship uncertainty to hard-exclude potentially valid
Papers.

**Migration**: Rebuild old gate decisions as relationship decisions. Recompute Paper identity from
Paper-specific identifier and source assertions under the Canonical V2 identity policy.

### Requirement: Identity-status scan is dry-run by default behind an independent flag

**Reason**: A table-mutating V020 scan and independent environment flag are implementation-specific
to the replaced schema and bypass candidate-release isolation.

**Migration**: Run Paper identity and relationship decisions inside an isolated candidate build;
review the complete decision artifact and promote only an accepted release.
