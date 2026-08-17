## 1. Cleanup Planning And Safety Gates

- [x] 1.1 Create a recollection run workspace layout under
  `.agents/runs/data-recollection-validation-runbook/` with placeholders
  for environment fingerprint, cleanup preview, batch execution, and
  validation evidence.
- [x] 1.2 Add a cleanup preview command or script that reports target
  database fingerprint, Alembic revision, affected tables, affected row
  counts, and dry-run/destructive mode.
- [x] 1.3 Add tests proving cleanup preview is non-destructive by
  default.
- [x] 1.4 Add tests proving destructive cleanup requires explicit target
  confirmation and refuses to run when confirmation is missing.
- [x] 1.5 Document the allowed cleanup scope for disposable verification
  rows and explicitly exclude source backfills, seed definitions, schema
  history, and archived OpenSpec evidence.

## 2. Bounded Recollection Batch

- [x] 2.1 Define the sample seed batch contract: explicit seed ids,
  sample/limit controls, expected runtime fields, and stop conditions.
- [x] 2.2 Add or document a bounded runner that invokes the existing
  seed, homepage paper, homepage patent, summary, and Milvus refresh
  paths without changing their semantics.
- [ ] 2.3 Capture seed status transitions, pipeline run ids, elapsed
  time, processed counts, and failure reasons in the run workspace.
- [x] 2.4 Add tests or dry-run checks proving a full run is blocked until
  sample evidence exists.

## 3. Evidence Report Generation

- [x] 3.1 Add SQL/report sections for seed status summary and pipeline
  issue taxonomy grouped by stage and issue type.
- [x] 3.2 Add SQL/report sections for professor quality-status
  distribution, fact coverage, profile summary coverage, and admin
  action/manual override checks.
- [x] 3.3 Add SQL/report sections for professor-paper links,
  professor-patent links, evidence source types, match reasons, and
  title-only patent rows.
- [x] 3.4 Add SQL/report sections for paper summary readiness,
  boilerplate rejection count, promotion-to-ready count, and summary
  length distribution.
- [x] 3.5 Add Milvus refresh and retrieval sanity sections, including
  target paper ids, chunks inserted/refreshed, sample queries, top-k
  results, and skipped-check rationale.
- [x] 3.6 Add a final data-readiness verdict that distinguishes
  code-path pass, data-readiness pass, and incomplete evidence.

## 4. Verification And Close-out

- [x] 4.1 Run unit tests for cleanup safety and report generation.
- [ ] 4.2 Run the cleanup command in dry-run mode against the intended
  local verification database and record output.
- [ ] 4.3 Run one bounded sample recollection batch only after dry-run
  evidence is present.
- [ ] 4.4 Generate the recollection validation report and attach it to
  `.agents/runs/data-recollection-validation-runbook/verification.md`.
- [x] 4.5 Run `openspec validate data-recollection-validation-runbook`
  and `git diff --check`.
- [x] 4.6 Update `openspec/change-ledger.md` status and archive only
  after stakeholder review of the first recollection report.
