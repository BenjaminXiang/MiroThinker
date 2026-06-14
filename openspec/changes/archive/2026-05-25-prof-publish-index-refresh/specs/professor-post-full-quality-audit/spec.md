## ADDED Requirements

### Requirement: P9 consumes P8 readiness as a preflight gate

Any P9 Professor publish, index, or RAG refresh stage MUST consume the current
P8 post-full quality audit as a preflight gate. The P9 stage MUST preserve the
P8 audit evidence and MUST stop before refresh when P8 reports P9 blockers.

#### Scenario: P9 records the current P8 gate result

- **WHEN** P9 begins
- **THEN** it runs the current P8 post-full audit command
- **AND** it records `p9_readiness`, `p9_blockers`, known field defects, and
  residual risk summaries in P9 acceptance evidence

#### Scenario: P9 stops on P8 blockers

- **WHEN** the current P8 audit reports a non-empty `p9_blockers` list
- **THEN** P9 does not execute publish, index, or RAG refresh commands
- **AND** P9 records the blocking items for remediation
