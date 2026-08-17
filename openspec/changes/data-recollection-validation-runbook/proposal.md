## Why

The collection and cleaning code paths are now complete enough to stop
debugging against legacy verification rows. We need a bounded,
repeatable recollection and validation runbook so old data can be
discarded, new data can be collected through the fixed flows, and the
result can be judged by evidence rather than ad hoc row counts.

## What Changes

- Add an operator runbook contract for clearing disposable verification
  data and recollecting professor, paper, patent, summary, and Milvus
  data through the archived fixed flows.
- Define safety gates before destructive cleanup: target database,
  dry-run preview, backup/export checkpoint, and explicit scope.
- Define bounded seed execution batches with sample/limit controls
  before any full seed run.
- Define post-run validation outputs: seed status summary, pipeline
  issue taxonomy, quality-status distribution, fact/profile-summary
  coverage, professor-paper/patent link evidence, summary_zh readiness,
  Milvus refresh evidence, and RAG retrieval sanity checks.
- Keep implementation focused on scripts/docs/reports. This change does
  not alter the collection semantics that were archived on 2026-05-17.

## Capabilities

### New Capabilities

- `data-recollection-validation`: Operator contract for safe data
  cleanup, recollection, and evidence-based validation after collection
  pipeline fixes.

### Modified Capabilities

- None.

## Impact

- Affected areas: `apps/miroflow-agent/scripts/`, optional
  `.agents/runs/data-recollection-validation-runbook/`, and operator
  documentation under this change.
- May execute destructive SQL only when explicitly pointed at the
  intended non-production verification database and after a dry-run
  report is produced.
- No API contract, schema, Milvus schema, or collection algorithm
  changes are expected.
