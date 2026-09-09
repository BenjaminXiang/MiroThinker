## ADDED Requirements

### Requirement: Refreshed blocked evidence records source-remediation context

The system MUST preserve source-remediation context when a P5
source-remediation run keeps a seed in `fetch_blocked`. It MUST preserve the
existing response-shape evidence and also record the
source-remediation context needed by operators: original URL, replacement URLs
that were evaluated, rejection reason for each replacement candidate, and the
final operator-facing next action.

#### Scenario: Replacement unavailable is diagnosable

- **GIVEN** seed id 5 still fails against the current CSSE URL
- **AND** no official replacement source is accepted
- **WHEN** P5 records a `fetch_blocked` outcome
- **THEN** the evidence includes HTTP/browser diagnostics for the current URL
- **AND** it includes the evaluated replacement candidates and why they were not
  accepted
- **AND** the outcome remains distinct from `parser_low_quality`
