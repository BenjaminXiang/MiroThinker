# Plan: Task 4.2 EvidenceLanding and Source Adapters

## Task contract

- Goal: implement the approved `EvidenceLanding.ingest/stream` deep module and deterministic source
  adapters for verified WAL/FPI salvage rows, historical JSONL/JSON/CSV/XLSX/SQLite, verified Milvus
  copy records, and already-collected response envelopes.
- Expected behavior / invariant: exact bytes are verified before state change; artifacts and parser
  runs are immutable/replayable; readable partial data and typed errors survive; source adapters
  never invent placeholders or mutate active canonical/publication state.
- Context: OpenSpec task 4.2 after Accepted task 4.1 RED commit `b3428dc` and Accepted S3 C2_0003.
- Constraints: use an ephemeral repository in this task; no C2 migration/Postgres persistence until
  task 4.3, no real source/recovery/Milvus/provider access, and no task 4.4 matrix replay.
- Done when: Task 4.1 and new adapter-family tests are GREEN without xfail; the remaining four deep
  modules stay strict RED; all regressions/static/OpenSpec/source invariants pass; task 4.2 is
  Accepted and committed alone.
- Out of scope: durable Postgres repository, actual source-matrix ingestion, domain assertions,
  identity/canonical build, publication/index, and provider acquisition.

## Deep-module design

- `evidence_landing.py` owns storage-independent requests/receipts/errors, adapter protocol, the
  public abstract `EvidenceLanding` seam, a concrete service, and an ephemeral composition factory.
- `evidence_adapters.py` owns format-specific parsing only. It returns immutable record drafts; the
  service owns hashes, artifact identity, parser/run/record identity, replay retention, and stream
  visibility.
- The ephemeral repository is an internal deterministic adapter used for Task 4.2 conformance. It
  is replaced behind the same service boundary by Task 4.3; callers never see table names or storage
  operations.
- IDs are deterministic opaque hashes of stable input identities, not legacy IDs. Replaying the same
  artifact with a new parser/run creates new parse/record identities while retaining prior output.
- Parent/copy references are verified against already registered artifact hash identity before parse.
  Any content mismatch, unknown parent, unsupported source kind, duplicate locator, or parser fault
  fails before publishing a partial run into the stream.

## Adapter boundary

- `historical_jsonl`, `historical_json`, `historical_csv`, `historical_xlsx`, and
  `historical_sqlite` parse supplied immutable bytes. SQLite opens only a temporary byte copy in
  immutable read-only mode; XLSX uses read-only workbook mode.
- `wal_fpi_salvage` consumes verified recovery record envelopes (`record_locator`, readable fields,
  typed field errors). It does not interpret or open original WAL/PGDATA.
- `milvus_copy_records` consumes exported records from a verified copy and rejects original/hash-only
  Milvus source kinds. It never opens a Milvus client.
- `collected_response` consumes an already-acquired JSON response envelope; no network/provider call
  exists in this module.
- Missing ordinary optional values are omitted, not replaced. Explicit unreadable-external markers
  become typed field errors and partial records.

## Implementation slices

- [x] Add RED adapter-family tests for WAL/FPI envelope preservation, JSON/CSV/XLSX/SQLite parsing,
      verified-copy-only Milvus records, and collected-response provenance.
- [x] Implement strict typed request/receipt/parser/draft contracts and the abstract/concrete landing
      service with deterministic ephemeral immutable state.
- [x] Implement the source adapters and make Task 3.1 EvidenceLanding plus all Task 4.1/4.2 cases
      GREEN; remove only their intentional xfail markers.
- [x] Self-review hash/parent/idempotency/rollback/error paths and add sibling regressions for any
      escaped defect.
- [x] Run focused and expanded Canonical V2, S1, S2/S2B, Ruff, Pyright, strict OpenSpec, and final
      source/candidate invariants.
- [x] Record evidence, mark task 4.2 Accepted, stage only this task, and commit. Do not start task
      4.3 in the same commit.

## Invariants

- No source adapter opens original `pgtest`, original Milvus, recovery database, Web, or provider.
- No adapter creates `CanonicalIdentity`, canonical decisions, publication rows, or active release.
- The Task 4.1 public effects remain stronger than any format-specific convenience.
- C2_0003 and its zero-row durable candidate remain unchanged.
- No new dependency is added; use installed/standard-library readers only.

## Rollback note

- Revert the Task 4.2 commit. The implementation is ephemeral and creates no durable database,
  source, index, provider, or release state.
