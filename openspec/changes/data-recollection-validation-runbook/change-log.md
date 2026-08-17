# Change Log: data-recollection-validation-runbook

## 2026-05-17 — proposal created

- Created the OpenSpec change for safe cleanup, recollection, and
  validation after the 2026-05-17 archive batch.
- Scoped this change to runbook/script/report behavior. It does not
  change collection semantics, schemas, or Milvus collection schemas.

## 2026-05-17 — runbook helper implemented

- Added `apps/miroflow-agent/scripts/run_data_recollection_validation.py`
  with `init-workspace`, `cleanup-preview`, `plan-batch`, and
  `generate-report` subcommands.
- Added unit tests for default non-destructive cleanup preview,
  destructive cleanup confirmation, protected cleanup scope, bounded
  batch planning, full-run sample evidence gating, and report structure.
- Created run workspace
  `.agents/runs/data-recollection-validation-runbook/20260517Tdata-recollection-apply/`.
- Did not run destructive cleanup, seed recollection, Milvus refresh, or
  RAG sanity checks.
