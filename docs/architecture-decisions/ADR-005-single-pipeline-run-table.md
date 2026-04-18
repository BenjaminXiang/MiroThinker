---
id: ADR-005
title: Single `pipeline_run` table, not four separate run-tracking tables
status: accepted
date: 2026-04-17
plan: docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
supersedes: docs/plans/2026-04-17-004-shenzhen-stem-knowledge-graph-retrieval-and-ops-architecture-plan.md (partial)
---

# ADR-005: Single `pipeline_run` table

## Context

Plan 004 proposed four separate tables to track asynchronous work:

- `import_batch` — xlsx import batches
- `pipeline_run` — generic pipeline runs
- `seed_refresh_run` — seed crawler runs
- `projection_build_run` — answer-pack build runs

Each table's schema was ~80% identical:
`(run_id, started_at, finished_at, status, items_processed, items_failed,
error_summary)` plus a small kind-specific field or two.

Review (scope-guardian persona, 2026-04-17) flagged this as duplicate
modeling. See `docs/plans/2026-04-17-005...§11.5 附录 E r2 增量裁剪`.

## Decision

Keep **two** tables:

1. **`import_batch`** — xlsx-specific. Unique `(seed_id, file_content_hash)`
   for idempotent re-imports. Columns specific to xlsx ingestion
   (`rows_read`, `records_new`, `records_updated`, etc.).
2. **`pipeline_run`** — polymorphic. A `run_kind` enum discriminates the
   kind of work (`import_xlsx`, `roster_crawl`, `profile_enrichment`,
   `news_refresh`, `team_resolver`, `paper_link_resolver`,
   `projection_build`, `answer_readiness_eval`, `quality_scan`). Kind-
   specific fields live in `run_scope jsonb`.

A single xlsx import creates BOTH rows: a `pipeline_run` (kind=`import_xlsx`,
the orchestration run) AND an `import_batch` (the xlsx-specific artifact).
They share a semantic parent-child relationship via `pipeline_run.run_scope`
carrying the batch_id, though we don't FK it (reduces coupling).

## Rationale

- **Four tables had 80% overlap.** Writing the same migration / repo /
  dashboard query four times costs engineering cycles for no benefit.
- **`import_batch` genuinely differs.** xlsx ingestion has a unique
  idempotency key (`file_content_hash`), diff semantics, row-level lineage
  counts. Merging it into `pipeline_run` would either require nullable
  specialty columns on every row (ugly) or force lineage queries through
  a JSON field (slow).
- **JSONB `run_scope` covers remaining kind variance.** Examples:
  - `run_kind=roster_crawl` → `run_scope={"institution":"SUSTech","seed_id":"..."}`.
  - `run_kind=projection_build` → `run_scope={"projection_type":"company_answer_pack","entity_ids":[...]}`.
  - `run_kind=news_refresh` → `run_scope={"company_ids":[...],"tier_filter":"trusted"}`.
- **Dashboard filter on `run_kind`** gives per-kind views without separate
  tables. One index `(run_kind, started_at DESC)` backs the common query.

## Consequences

Positive:
- One migration file per cross-cutting change to run-tracking.
- Dashboard "Pipelines" tab is a single table scan with filters.
- Parent-child run hierarchy (via `parent_run_id`) works uniformly across
  kinds (e.g., a `news_refresh` master run spawning per-company children).

Negative:
- Kind-specific fields in `run_scope jsonb` are not indexed by default;
  we add GIN index on `run_scope` only if a specific kind's filter query
  becomes slow.
- Schema-level type safety across kinds is weaker than separate tables
  would provide. We mitigate this in application code with per-kind
  Pydantic `RunScope*` models.

## Related

- ADR-003 (FTS/vector indexing; deferred to Phase 2b)
- `apps/miroflow-agent/alembic/versions/V001_init_source_layer.py` —
  both tables and their CHECK enums defined here.
- Plan §6.1 `import_batch` and `pipeline_run`.
