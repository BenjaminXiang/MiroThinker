## ADDED Requirements

### Requirement: A factual short biography is acceptable

A professor profile summary MUST be accepted when it is at least 120 Chinese
characters and otherwise satisfies the contract; the 200-character floor is
retired because it forced padding.

#### Scenario: Enriched summary at 150 characters

- **WHEN** a synthesized biography has 150 characters of factual text
- **THEN** it passes the contract and is written

#### Scenario: Still too short

- **WHEN** the biography has 60 characters
- **THEN** it is rejected with `profile_summary_too_short`
