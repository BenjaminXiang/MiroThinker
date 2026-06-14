## ADDED Requirements

### Requirement: Previously blocked seeds are remediated before P5 completion

The system MUST treat previously approved blocked professor seeds as visible
operational debt until a P5 remediation decision is recorded. P5 MUST attempt
official-source remediation for seed ids 5 and 25-28 and MUST
record whether each seed moved from blocked to runnable coverage or remained
blocked with refreshed evidence.

The existing P4 coverage guard semantics MUST remain intact: a blocked seed may
be classified, but it MUST NOT be reported as a successful crawl unless a named
adapter or registered source path produced usable roster candidates.

#### Scenario: Remediated seed becomes runnable

- **GIVEN** a previously blocked seed has an official replacement source
- **WHEN** the registered adapter parses usable roster candidates from that
  source
- **THEN** the seed is counted as runnable in P5 evidence
- **AND** the P5 matrix records the named resolver result and replacement URL

#### Scenario: Still-blocked seed remains visible

- **GIVEN** a previously blocked seed has no official reachable replacement
  source
- **WHEN** the P5 matrix is generated
- **THEN** the seed remains visible as blocked
- **AND** the matrix records refreshed blocked evidence rather than omitting the
  seed
