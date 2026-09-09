# Verification: p0-schema-readiness

Date: 2026-05-23

## Scope

P0 removes the schema-readiness blocker for later professor split
backfill and seed E2E work. It does not implement new school-specific
seed adapters.

## Diagnosis

Reported symptom:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic current -v`
  failed before repair with:
  `Can't locate revision identified by 'V027'`.
- Direct schema inspection showed `miroflow_real.alembic_version='V027'`
  while `professor.paper_summary` and `professor.patent_summary` were
  missing.

Root cause:

- The current main worktree had newly added untracked migrations using
  revision IDs V024 and V025.
- The local real database had already been stamped through a different
  V024-V027 chain from `.worktrees/paper-pipeline-cleanup`.
- This duplicated/reused migration numbering and made the main worktree
  unable to resolve `miroflow_real`'s current revision.

Invariant:

- The main worktree must contain a single linear Alembic chain matching
  any revision already stamped in local runtime databases, and new
  migrations must extend rather than reuse those revision IDs.

## Changes

Restored migrations:

- `apps/miroflow-agent/alembic/versions/V024_extend_professor_paper_link_tier_evidence.py`
- `apps/miroflow-agent/alembic/versions/V025_add_professor_admin_action.py`
- `apps/miroflow-agent/alembic/versions/V026_allow_page_only_patent_number.py`
- `apps/miroflow-agent/alembic/versions/V027_repair_professor_paper_link_tier_constraint.py`

Renumbered migrations:

- `V024_extend_paper_canonical_source_page_flow.py` moved to
  `V028_extend_paper_canonical_source_page_flow.py`.
- `V025_add_professor_output_summary_fields.py` moved to
  `V029_add_professor_output_summary_fields.py`.

Regression coverage:

- Added `apps/miroflow-agent/tests/storage/test_alembic_revision_lineage.py`.
- Moved paper canonical source migration test to
  `apps/miroflow-agent/tests/storage/test_v028_migration.py`.
- Moved professor summary migration test to
  `apps/miroflow-agent/tests/storage/test_v029_migration.py`.

## RED

- `uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py -q -n0`
  - Result: failed before repair.
  - Failure: missing
    `V024_extend_professor_paper_link_tier_evidence.py`.

## GREEN

No database URL:

- `uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v028_migration.py tests/storage/test_v029_migration.py -q -n0`
  - Result: 3 passed, 3 skipped.
  - Skips were expected because no `DATABASE_URL_TEST` or `DATABASE_URL`
    was set for DDL behavior tests.

Fresh temporary database:

- Created temporary DB:
  `miroflow_test_alembic_lineage_1779561355`.
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_alembic_lineage_1779561355 uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v028_migration.py tests/storage/test_v029_migration.py -q -n0`
  - Result: 6 passed.
  - Evidence: Alembic upgraded from base through V029, including V024,
    V025, V026, V027, V028, and V029.

Final focused matrix:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_alembic_lineage_1779561355 uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v028_migration.py tests/storage/test_v029_migration.py tests/scripts/test_run_milvus_backfill.py tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_quality_filter.py -q -n0`
  - Result: 46 passed.

Lint:

- `uv run --no-sync ruff check alembic/versions/V024_extend_professor_paper_link_tier_evidence.py alembic/versions/V025_add_professor_admin_action.py alembic/versions/V026_allow_page_only_patent_number.py alembic/versions/V027_repair_professor_paper_link_tier_constraint.py alembic/versions/V028_extend_paper_canonical_source_page_flow.py alembic/versions/V029_add_professor_output_summary_fields.py tests/storage/test_alembic_revision_lineage.py tests/storage/test_v028_migration.py tests/storage/test_v029_migration.py`
  - Result: passed, `All checks passed!`.

## Real DB Upgrade

- `uv run --no-sync alembic heads`
  - Result: `V029 (head)`.
- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic current -v`
  - Result before upgrade after lineage repair: current revision resolved
    as V027.
- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic upgrade head`
  - Result: upgraded V027 -> V028 -> V029.
- Final current check:
  `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic current -v`
  - Result: current revision is `V029 (head)`.
- Post-upgrade schema inspection:
  - `alembic_version`: `V029`
  - `professor` summary columns:
    `paper_summary`, `patent_summary`
  - Sample professor selected for E2E:
    `PROF-0012FFC9DEC2`, `毛润泽`, `profile_summary_len=658`.

## P0 E2E

Invalid sample:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_milvus_backfill.py --domain professor --id PROF-043D2EEA0159 --limit 1 --batch-size 1 --milvus-uri /tmp/p0-prof-milvus-real-sample-20260523.db --rebuild`
  - Result: command exited 0 but selected no rows:
    `profs_total=0`.
  - Not counted as E2E evidence because the professor id did not exist.

Valid sample:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_milvus_backfill.py --domain professor --id PROF-0012FFC9DEC2 --limit 1 --batch-size 1 --milvus-uri /tmp/p0-prof-milvus-real-sample-20260523.db --rebuild`
  - Result: passed.
  - Embedding endpoint returned HTTP 200 for identity and research
    batches.
  - Output:
    `{"profs_total": 1, "profs_processed": 1, "profs_skipped": 0, "profs_with_errors": 0, "collection_counts": {"professor_identity_profiles": 1, "professor_research_profiles": 1, "professor_profiles": 0}, "dry_run": false, ...}`.

## Seed Adapter Gate

- Current active OpenSpec changes after P0 are:
  `prof-admin-workbench-ui`, `paper-pdf-fulltext-ingest`,
  `patent-page-only-canonical`, `prof-lifecycle-state`, and
  `paper-homepage-enrichment-completion`.
- There is no active `prof-seed-adapter-coverage` or equivalent change.
- Per `AGENTS.md` OpenSpec gate, new school-specific seed adapters remain
  blocked until that behavior-affecting change exists.

OpenSpec validation after P0:

- `openspec validate --changes --strict`
  - Result: 5 passed, 0 failed.
- `openspec validate --specs --strict`
  - Result: 7 passed, 0 failed.

Cleanup:

- Temporary DB `miroflow_test_alembic_lineage_1779561355` was dropped
  after verification.

## Pattern-fix report

- Reported case fixed: yes, Alembic can resolve `miroflow_real`'s stamped
  V027 and upgrade it to current head V029.
- Defect class: L4 schema/state contract drift + C1 test-matrix gap.
- Invariant enforced: recent Alembic revisions must be unique and linear,
  and mainline migration history must contain revisions already stamped in
  local runtime DBs.
- Fix level applied: Level 4, migration boundary repair plus regression
  guard.

## Remaining Risk

- Archived evidence from earlier changes still contains historical
  references to V024/V025 command names from before the P0 renumbering.
  Those are historical logs, not current migration filenames.
- Seed adapter coverage remains gated by missing OpenSpec change and is
  not complete.

## 2026-05-23 - Current Head Catch-up to V032

Scope:
- Later archived changes extended the Alembic chain after the initial P0
  close-out. P0 schema readiness was rechecked against current head V032 before
  continuing staged E2E work.

Pre-check:
- `uv run --no-sync alembic heads`
  - Result: `V032 (head)`.
- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic current -v`
  - Result before catch-up: current revision was `V029`.

Temporary DB migration verification:
- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_p0_v032_codex uv run --no-sync pytest tests/storage/test_alembic_revision_lineage.py tests/storage/test_v030_migration.py tests/storage/test_v031_migration.py tests/storage/test_v032_migration.py -q -n0`
  - Setup: created temporary database `miroflow_test_p0_v032_codex`.
  - Result: `10 passed in 5.90s`.
  - Teardown: dropped temporary database `miroflow_test_p0_v032_codex`.
- `uv run --no-sync ruff check alembic/versions/V030_add_professor_lifecycle_state.py alembic/versions/V031_add_paper_full_text_raw_pdf_provenance.py alembic/versions/V032_add_professor_patent_link_evidence_url.py tests/storage/test_v030_migration.py tests/storage/test_v031_migration.py tests/storage/test_v032_migration.py tests/storage/test_alembic_revision_lineage.py`
  - Result: `All checks passed!`.

Real DB upgrade:
- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic upgrade head`
  - Result: upgraded `V029 -> V030 -> V031 -> V032`.
- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync alembic current -v`
  - Result: current revision is `V032 (head)`.
- Real DB schema inspection:
  - `alembic_version`: `V032`.
  - `professor`: `lifecycle_state`, `lifecycle_merged_into_id`,
    `paper_summary`, `patent_summary`.
  - `paper_full_text`: `pdf_byte_size`, `pdf_sha256`,
    `raw_pdf_storage_ref`.
  - `professor_patent_link`: `evidence_anchor`, `evidence_url`.
  - Professor constraints:
    `ck_professor_lifecycle_state`,
    `fk_professor_lifecycle_merged_into`.

Post-upgrade P0 E2E sample:
- Sample professor selected from `miroflow_real`:
  `PROF-0012FFC9DEC2`, `毛润泽`, `profile_summary_len=658`,
  `lifecycle_state=active`.
- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_milvus_backfill.py --domain professor --id PROF-0012FFC9DEC2 --limit 1 --batch-size 1 --milvus-uri /tmp/p0-v032-prof-milvus-real-sample-20260523.db --rebuild`
  - Result: passed.
  - Embedding endpoint returned HTTP 200 for identity and research batches.
  - Output:
    `{"profs_total": 1, "profs_processed": 1, "profs_skipped": 0, "profs_with_errors": 0, "collection_counts": {"professor_identity_profiles": 1, "professor_research_profiles": 1, "professor_profiles": 0}, "dry_run": false, ...}`.

Status:
- P0 schema readiness is current through V032.
- Seed adapter implementation remains gated by the missing
  `prof-seed-adapter-coverage` OpenSpec change.
