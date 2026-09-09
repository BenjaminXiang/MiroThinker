# Tasks: p0-schema-readiness

## 1. Migration lineage repair

- [x] T1.1: Reproduce the real DB Alembic lineage failure.
- [x] T1.2: Identify the missing stamped revisions and sibling migration
  files.
- [x] T1.3: Add a regression test guarding recent Alembic revision
  uniqueness and linearity.
- [x] T1.4: Restore the V024-V027 migration files already represented in
  `miroflow_real`.
- [x] T1.5: Renumber the newly archived paper-source and professor-summary
  migrations to V028 and V029.

## 2. Schema readiness verification

- [x] T2.1: Run fresh-DB migration tests through head.
- [x] T2.2: Verify `miroflow_real` can resolve its stamped V027 revision.
- [x] T2.3: Upgrade `miroflow_real` to current head V029.
- [x] T2.4: Verify `professor.paper_summary` and
  `professor.patent_summary` exist in `miroflow_real`.

## 3. P0 E2E

- [x] T3.1: Run a bounded professor split Milvus backfill sample from
  `miroflow_real` into a temporary Milvus file.
- [x] T3.2: Record identity/research collection counts.

## 4. Seed adapter gate

- [x] T4.1: Confirm seed adapter implementation remains gated by missing
  `prof-seed-adapter-coverage` OpenSpec change.

## 5. Current head catch-up after later archives

- [x] T5.1: Re-check current Alembic head after later archive work.
- [x] T5.2: Run V030-V032 migration/schema tests on a temporary database.
- [x] T5.3: Upgrade `miroflow_real` from V029 to current head V032.
- [x] T5.4: Verify V030-V032 schema columns and constraints exist in
  `miroflow_real`.
- [x] T5.5: Re-run the bounded professor split Milvus backfill sample
  from `miroflow_real` after the V032 upgrade.
