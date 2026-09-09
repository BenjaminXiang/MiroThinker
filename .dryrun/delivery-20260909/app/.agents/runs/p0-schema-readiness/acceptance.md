# Acceptance: p0-schema-readiness

## Migration lineage

- [x] Main worktree Alembic head was V029 at the initial P0 close-out.
- [x] The main worktree contained a linear V024-V029 migration chain:
  V024 tier evidence, V025 professor admin action, V026 page-only
  patent number, V027 tier constraint repair, V028 paper canonical
  source, V029 professor output summary fields.
- [x] A regression test fails if the recent V024-V029 chain is broken or
  if revision IDs are duplicated.
- [x] Current main worktree Alembic head is V032 after later archived
  changes added V030 lifecycle state, V031 raw PDF provenance, and V032
  professor-patent evidence URL columns.
- [x] The migration chain remains linear through V032.

## Real DB readiness

- [x] `miroflow_real` resolves its stamped V027 revision after the missing
  migration files are restored.
- [x] `miroflow_real` is upgraded to V029.
- [x] `miroflow_real.professor` includes nullable `paper_summary` and
  `patent_summary` columns.
- [x] `miroflow_real` is upgraded to V032.
- [x] `miroflow_real.professor` includes `lifecycle_state` and
  `lifecycle_merged_into_id`.
- [x] `miroflow_real.paper_full_text` includes raw PDF provenance columns.
- [x] `miroflow_real.professor_patent_link` includes `evidence_url` and
  `evidence_anchor`.

## P0 E2E

- [x] A bounded real-DB professor split backfill sample writes one row to
  `professor_identity_profiles`.
- [x] The same sample writes one row to `professor_research_profiles`.
- [x] The sample writes to a temporary Milvus file, not the production
  Milvus file.
- [x] The same bounded professor split backfill sample still passes after
  upgrading `miroflow_real` to V032.

## Out of scope / gate

- [x] Seed adapter implementation is not performed in P0 because adding or
  enabling school-specific adapters is behavior-affecting and no active
  `prof-seed-adapter-coverage` OpenSpec change exists.
