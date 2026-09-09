## ADDED Requirements

### Requirement: P6 trigger recommendations respect bounded modes

P6 MUST use the existing `preview`, `sample`, and `full` trigger modes when
recommending next actions for Professor seed operations.

The default recommendation for a resolver-covered seed without current bounded
evidence MUST be a bounded mode. An unbounded `full` recommendation MUST only
appear after successful post-P5 sample evidence and MUST still require a later
explicit operator confirmation before execution.

#### Scenario: Default recommendation is bounded

- **WHEN** a seed has a named resolver but lacks post-P5 sample evidence
- **THEN** the P6 recommendation is not `full`
- **AND** the recommendation records the bounded mode needed next

#### Scenario: Full recommendation remains confirmation-gated

- **WHEN** a seed is recommended as `full` by the P6 planner
- **THEN** the matrix records the bounded sample run that justifies it
- **AND** P6 does not execute the full run automatically

### Requirement: P6 verification records skipped unsafe operations

P6 verification MUST explicitly record that destructive cleanup and unbounded
bulk full runs were skipped. The record MUST include the reason and the next
stage that would own those operations if approved.

#### Scenario: Unsafe operation is skipped with reason

- **WHEN** P6 verification is written
- **THEN** it states that cleanup and unbounded full recollection were not run
- **AND** it identifies the later-stage approval point for those operations

