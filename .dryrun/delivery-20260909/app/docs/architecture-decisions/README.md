# Architecture Decision Records

One ADR per significant technical decision that the code alone can't fully
explain. Short, dated, and referenced back from the code it governs.

| ID | Title | Status | Phase |
|----|-------|--------|-------|
| [ADR-001](./ADR-001-postgres-driver.md) | Postgres driver — psycopg3 | accepted | 0 |
| ADR-002 | Embedding model selection | deferred | 2b |
| ADR-003 | Chinese full-text search strategy | deferred | 2b |
| ADR-004 | Scheduler — APScheduler (Postgres jobstore) | deferred | 2 |
| [ADR-005](./ADR-005-single-pipeline-run-table.md) | Single `pipeline_run` table | accepted | 0 |
| [ADR-012](./ADR-012-canonical-v2-preserve-temporal-precision.md) | Canonical V2 preserves temporal precision | accepted | Canonical V2 S5G/S6 |
| [ADR-013](./ADR-013-canonical-v2-hybrid-enumeration-coverage.md) | Canonical V2 uses hybrid enumeration coverage | accepted | Canonical V2 S8/S9 |
| [ADR-014](./ADR-014-canonical-v2-internal-person-projection.md) | Canonical V2 keeps Person internal to the four public domains | accepted | Canonical V2 S6R/S7/S8 |
| [ADR-015](./ADR-015-canonical-v2-internal-technology-model.md) | Canonical V2 uses an internal versioned Technology model | accepted | Canonical V2 S6R/S7/S8/S9 |
| [ADR-016](./ADR-016-product-capability-remains-answer-scoped.md) | Product capability remains answer-scoped | accepted | Canonical V2 S8/S9/S10 |
| [ADR-017](./ADR-017-web-only-entities-use-session-handles.md) | Web-only entities use evidence-bound session handles | accepted | Canonical V2 S8/S9 |
| [ADR-018](./ADR-018-machine-readable-claim-level-case-contract.md) | Acceptance uses machine-readable claim-level case contracts | accepted | Canonical V2 S2C/S8/S9/S12 |
| [ADR-019](./ADR-019-conditional-structured-continuation-offers.md) | Answers use conditional structured continuation offers | accepted | Canonical V2 S8/S9 |
| [ADR-020](./ADR-020-local-safety-questions-use-safety-guidance.md) | Local safety questions use narrow safety guidance | accepted | Canonical V2 S2C/S8/S9 |
| [ADR-021](./ADR-021-confidence-gated-entity-ambiguity.md) | Entity ambiguity uses confidence-gated answer or clarification | accepted | Canonical V2 S2C/S8/S9 |
| [ADR-022](./ADR-022-llm-selected-assessment-dimensions.md) | Assessments use per-turn LLM-selected dimensions | accepted | Canonical V2 S2C/S8/S9 |

## Conventions

- **File name**: `ADR-NNN-short-slug.md`.
- **Frontmatter**: `id`, `title`, `status` (proposed / accepted / deferred /
  superseded), `date`, `plan` (path to the plan that drove the decision).
- **Short**: 1-2 pages max. If more is needed, it's probably a design doc,
  not an ADR.
- **Status `deferred`**: we know the decision will be needed but punt until
  its phase. Leave a placeholder entry in this index so future-you remembers
  to revisit.

## What not to ADR

- Implementation details already clear from the code.
- Choices that have only one reasonable option (no alternatives analysis adds value).
- Stylistic preferences (those go in a style guide, not here).
