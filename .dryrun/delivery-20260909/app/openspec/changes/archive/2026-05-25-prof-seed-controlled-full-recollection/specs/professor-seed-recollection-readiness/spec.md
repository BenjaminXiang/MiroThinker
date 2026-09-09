## ADDED Requirements

### Requirement: P7 full execution consumes full-ready P6 rows only

The Professor seed readiness contract MUST be the gate for P7 full execution.
Only rows whose latest readiness matrix entry has
`full_recollection_allowed=true` may enter controlled full recollection.

#### Scenario: P6 full-ready row enters P7

- **WHEN** a seed's latest readiness matrix row recommends `full`
- **AND** `full_recollection_allowed=true`
- **THEN** P7 may select that seed for controlled full recollection

#### Scenario: Non-ready row is rejected

- **WHEN** a seed's latest readiness matrix row recommends `blocked`,
  `preview`, or `sample`
- **THEN** P7 MUST NOT select that seed for full recollection

