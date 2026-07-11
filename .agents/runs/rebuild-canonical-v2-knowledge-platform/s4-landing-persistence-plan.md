# Plan: Task 4.3 Durable Evidence Landing

## Task contract

- Goal: persist Task 4.2 artifact manifests, parser runs, ordered source records, typed errors, and
  parent/copy lineage in isolated PostgreSQL without changing the `EvidenceLanding.ingest/stream`
  caller seam.
- Expected behavior / invariant: independent processes observe the same immutable replay; one run ID
  is idempotent only for the exact request/output; a transaction failure exposes no partial artifact,
  parser run, record, error, or ingest-run state.
- Context: OpenSpec task 4.3 after Accepted task 4.2 commit `c9929d5`; C2_0003 has the base landing
  tables but no persisted ingest-run identity, parser options, or record ordinal.
- Constraints: all writes require the exact Accepted S2B gate and explicit marked target; real tests
  use only a new disposable database. The durable C2_0003 candidate is read-only in this task.
- Done when: a fresh PostgreSQL-backed composition passes restart, replay, concurrency, conflict,
  partial/error, lineage, rollback, and append-only tests; regressions/static/OpenSpec/source
  invariants pass; task 4.3 is Accepted and committed alone.
- Out of scope: actual source-matrix replay, candidate population/upgrade, assertions/identity,
  canonical/domain construction, publication/index, provider calls, or production-like cutover.

## Storage design

- Refactor Task 4.2 behind a small repository protocol: pre-parse admissibility, atomic prepared-run
  commit, and ordered batch stream. The ephemeral and PostgreSQL adapters share all hashing,
  parsing, typed construction, and caller-visible behavior.
- Add reversible `C2_0004` storage needed for durable semantics:
  - immutable `landing.ingest_run` records run ID, batch/artifact/parse identities, exact request and
    output fingerprints, landing status, byte/record counts, observation and commit times;
  - `landing.parser_run.parser_options` retains the exact parser configuration;
  - `landing.source_record.record_ordinal` retains parser output order independently of locator text;
  - foreign keys, checks, uniqueness, and append-only/immutable triggers close cross-process drift.
- The PostgreSQL adapter re-verifies the Accepted backup gate before every write connection, verifies
  explicit database name/marker and C2_0004 revision, then serializes identical run IDs with a
  transaction-scoped advisory lock.
- Exact repeated runs return the persisted receipt without duplicate rows. A conflicting request or
  output for the same run ID raises `EvidenceIntegrityError`; no existing row is rewritten.
- `stream` reconstructs shared `SourceRecord` values plus ordered typed errors from committed rows and
  returns detached Pydantic snapshots.

## Implementation slices

- [x] Add a Task 4.3 RED revision contract plus real disposable integration scenarios.
- [x] Add reversible C2_0004 DDL and synchronize existing migration fixtures/contracts.
- [x] Refactor the core to a repository seam while keeping all Task 4.2 tests GREEN.
- [x] Implement explicit-target PostgreSQL repository/factory and transactional error mapping.
- [x] Run focused RED/GREEN, real concurrency/rollback, full Canonical V2/S1/S2, static/OpenSpec,
      schema rollback, and final source/candidate invariants.
- [x] Record evidence, accept task 4.3, drop the disposable database, stage only this task, and
      commit. Do not start task 4.4 in the same commit.

## Invariants

- The original `pgtest`, original Milvus, recovery databases, and durable candidate are never write
  targets and are not opened by repository tests.
- Backup admission and target identity are checked before the first PostgreSQL landing write.
- No `UPDATE`, `DELETE`, `TRUNCATE`, upsert-overwrite, or replace semantics touch immutable landing
  history; parser-run completion is the only bounded mutable operational transition already allowed
  by C2_0003.
- Database JSON, errors, order, parser configuration, and hash/lineage values round-trip without
  caller-visible loss or invention.
- No new dependency is added.

## Rollback note

- Revert the Task 4.3 commit. C2_0004 downgrade removes only the new empty ingest-run table and new
  landing columns/triggers on an explicitly disposable target. No durable candidate upgrade occurs
  in this task.
