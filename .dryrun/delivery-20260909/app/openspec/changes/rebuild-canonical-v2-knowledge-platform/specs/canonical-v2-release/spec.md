## ADDED Requirements

### Requirement: Every build produces an immutable candidate release

A Canonical V2 build SHALL produce a candidate release identified by an immutable manifest. The
manifest SHALL identify input source batches, parser/policy/model versions, object and relationship
counts/hashes, eligibility results, published projections, and expected index projections.

#### Scenario: Rebuild is repeated from the same evidence and versions
- **WHEN** the same accepted evidence and deterministic version set are rebuilt
- **THEN** deterministic manifest sections and projection hashes match
- **AND** any LLM-dependent decision difference is explicitly traceable rather than hidden

### Requirement: Candidate data is isolated from the active release

Building, enriching, indexing, or rejecting a candidate SHALL NOT partially change the active
canonical, published, or vector release.

#### Scenario: Candidate index build fails halfway
- **WHEN** a candidate Milvus build fails after writing only part of its expected points
- **THEN** the active database and active Milvus aliases remain on the prior accepted release
- **AND** the failed candidate remains inspectable and retryable or discardable

### Requirement: Milvus is a reproducible versioned projection

Every vector point or chunk SHALL identify its canonical object, canonical release, projection
policy/schema, embedding model, and content hash. Milvus content SHALL NOT be treated as an
independent canonical fact source.

#### Scenario: Paper chunk is inspected
- **WHEN** a Paper vector point is returned or audited
- **THEN** its metadata identifies the Paper, release, projection version, embedding model, and
  embedded content hash

### Requirement: Internal Person and Technology projections remain release-scoped auxiliaries

Any internal Person or Technology lookup/vector projection SHALL identify its accepted Canonical
release, projection schema/policy, content hash, and source public-domain evidence. Such a projection
SHALL NOT create a fifth public-domain inclusion population or independently promoted business-domain
index. Every projection/index manifest SHALL carry a machine-validated scope discriminator that
separates `public_domain` from `internal_auxiliary`; internal auxiliaries SHALL identify their owning
reference type and SHALL NOT masquerade as a Professor, Company, Paper, or Patent publication.

#### Scenario: Internal Person projection is rebuilt
- **WHEN** accepted Company-personnel evidence or Person identity decisions change
- **THEN** the internal Person projection is rebuilt/versioned with the owning release
- **AND** Professor, Company, Paper, and Patent remain the only public-domain publication populations

### Requirement: Initial and policy-changing releases rebuild indexes fully

The system SHALL build new versioned indexes fully for the first Canonical V2 release and any change
to vector schema, embedding model, or path-eligibility policy. A later ordinary data update MAY use a
versioned incremental refresh only when deterministic reconciliation proves deletion, update, and
admission parity; scheduled full reconciliation SHALL remain available.

#### Scenario: Eligibility policy changes
- **WHEN** a semantic-recall eligibility policy version changes
- **THEN** the affected index projection is fully rebuilt under the new policy
- **AND** old and new policy points are not mixed in one accepted projection

### Requirement: Promotion requires deterministic canonical-index parity

Before promotion, the system SHALL compare expected and actual eligible entity/chunk IDs, counts,
content hashes, projection versions, and release IDs. Any unexplained missing, extra, stale, or
cross-release point SHALL block promotion.

#### Scenario: Milvus contains an extra stale point
- **WHEN** candidate parity finds a vector point not expected by the candidate release manifest
- **THEN** promotion is rejected
- **AND** the discrepancy is reported with enough identity/version information to repair it

### Requirement: Promotion switches one accepted release atomically

Only a candidate with accepted verification evidence SHALL be promotable. Promotion SHALL switch
database serving projections and vector aliases/pointers to one release without exposing a mixed
release to new requests.

#### Scenario: Accepted release is promoted
- **WHEN** an authorized operator promotes an accepted candidate
- **THEN** new requests resolve canonical, published, and vector content from the same release
- **AND** no request is intentionally routed to a candidate/active mixture

### Requirement: Accepted release can roll back without rewriting evidence

The prior accepted release and verification manifest SHALL remain available until rollback policy
permits retirement. Rollback SHALL restore serving/index pointers and SHALL NOT delete or mutate
landing evidence or candidate decision history.

#### Scenario: Post-promotion hard invariant fails
- **WHEN** a promoted release is rolled back after detecting a hard invariant violation
- **THEN** new requests use the prior accepted release
- **AND** the rejected release and its evidence remain auditable

### Requirement: Destructive database paths fail closed on target identity

Migration, rebuild, reset, and destructive integration-test paths SHALL require an explicit database
target and SHALL verify that the target is the expected disposable or isolated candidate database.
They SHALL NOT fall back to a generic environment `DATABASE_URL` when a test/recovery target is
required.

#### Scenario: Test environment also contains a real database URL
- **WHEN** a destructive migration test receives an explicit disposable test DSN while a different
  generic database environment variable is present
- **THEN** only the explicit disposable target may be used
- **AND** the operation fails before writes if target identity cannot be proven
