## ADDED Requirements

### Requirement: P7 full results must be audited before P9

The controlled full recollection contract MUST require P8 post-full audit before
any P9 publish, index, or RAG refresh stage uses the P7 full-run output.

#### Scenario: P9 waits for P8 audit

- **WHEN** P7 full recollection has completed
- **THEN** P9 publish/index work is not considered ready until P8 audit evidence
  exists
- **AND** the P8 handoff lists any full-run rows requiring remediation

