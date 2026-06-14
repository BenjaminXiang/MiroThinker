## ADDED Requirements

### Requirement: P6 readiness evidence extends the seed coverage matrix

After P5, Professor seed coverage evidence MUST distinguish adapter coverage
from recollection readiness. A seed with resolver coverage or approved blocked
evidence can satisfy the P4/P5 coverage guard, but it MUST NOT be considered
ready for full recollection unless the P6 readiness matrix explicitly records
`full_recollection_allowed=true`.

The P6 readiness matrix MUST include every current seed row and MUST reference
the coverage state used to derive the recommendation.

#### Scenario: Coverage is not full readiness

- **WHEN** a seed is `resolver_covered` in the adapter coverage guard
- **AND** it has no post-P5 successful bounded sample run
- **THEN** the P6 readiness matrix does not allow full recollection for that
  seed
- **AND** the next recommended mode is bounded

#### Scenario: Approved blocked row remains visible

- **WHEN** a seed is approved blocked in the coverage guard
- **THEN** the P6 readiness matrix includes the row
- **AND** the recommendation is `blocked` unless a later official replacement
  source has successful bounded evidence

### Requirement: P6 acceptance preserves row-level E2E evidence

P6 MUST preserve the row-level evidence discipline introduced by P4 and P5.
The acceptance evidence MUST include one row for every observed
`professor_seed` row with seed id, resolver result, coverage state,
recommended next mode, full recollection allowance, and evidence reference.

#### Scenario: Completion requires the P6 row matrix

- **WHEN** P6 completion is evaluated
- **THEN** `acceptance.md` contains a row-level P6 matrix for every observed
  seed
- **AND** `.agents/runs/prof-seed-recollection-readiness/verification.md`
  contains the command and result that generated or verified that matrix

