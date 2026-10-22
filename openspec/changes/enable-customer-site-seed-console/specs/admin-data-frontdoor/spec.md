# Spec delta: admin-data-frontdoor (customer-site seed console)

## ADDED Requirements

### Requirement: Seed console works without a build-time DATABASE_URL

The customer serving node SHALL expose the professor-seed registry (list/create/update/delete,
preview/sample/full trigger, run history) using a seed-only DSN, while the build-time
`DATABASE_URL` remains unset and the ops/upload surfaces remain unavailable.

#### Scenario: Seed list loads

- **WHEN** an operator opens `/seeds`
- **THEN** the page lists the `professor_seed` rows from `miroflow_collection_v1`
- **AND** the ops/upload surfaces still report `postgres_unavailable`

#### Scenario: Preview trigger runs

- **WHEN** an operator clicks “检查名册” / “开始抓取” on a seed
- **THEN** `admin-seed-refresh` is triggered through the shared gate
- **AND** the child receives `DATABASE_URL=miroflow_collection_v1`
- **AND** the run appears in the seed page history

#### Scenario: No seed DSN

- **WHEN** neither `CANONICAL_V2_SEED_DATABASE_URL` nor the console DSN is configured
- **THEN** the seed endpoints keep returning `console_database_not_configured`
