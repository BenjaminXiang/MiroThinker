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
