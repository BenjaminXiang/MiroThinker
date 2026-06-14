# Spec Delta: professor-seed-management

## ADDED Requirements

### Requirement: Adapter availability is row-level and named

Adapter availability for a professor seed MUST be evaluated at the individual
seed row level. A seed is considered adapter-covered only when
`resolve_seed_adapter_name()` returns a non-null named adapter or registered API
path for that seed's current URL.

Generic parser success without a named resolver result MUST NOT unblock a seed
from `adapter_missing`.

#### Scenario: Registered adapter unblocks an adapter-missing seed

- **GIVEN** a seed has `last_run_status='adapter_missing'`
- **AND** a new named adapter now matches the seed's current URL
- **WHEN** the admin trigger endpoint re-checks adapter availability
- **THEN** the endpoint accepts the trigger with HTTP 202
- **AND** the seed is flipped to `in_progress`

#### Scenario: Generic parser does not unblock without resolver coverage

- **GIVEN** a seed URL can be parsed by generic extraction helpers
- **AND** no named adapter or API path is registered for the seed URL
- **WHEN** the admin trigger endpoint re-checks adapter availability
- **THEN** the endpoint still returns HTTP 422 `adapter_missing`
- **AND** no pipeline task is enqueued
