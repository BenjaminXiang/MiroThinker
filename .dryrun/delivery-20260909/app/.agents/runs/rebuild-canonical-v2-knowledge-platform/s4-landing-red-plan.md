# Plan: Task 4.1 Immutable Landing RED

## Task contract

- Goal: freeze executable RED behavior for evidence byte identity/copy lineage, parser-version
  replay, partial/corrupt preservation, and zero placeholder fact invention before implementing
  EvidenceLanding or its source adapters.
- Expected behavior / invariant: callers use the approved `EvidenceLanding.ingest/stream` seam;
  downstream-visible records retain exact artifact/parser/run/locator/error identity; mismatch or
  unreadable input never becomes invented evidence or active canonical state.
- Context: OpenSpec task 4.1 after complete S3 acceptance at commit `607e558`.
- Constraints: test/docs only; no production module, migration, database, source file, Milvus,
  provider, dependency, or S4 replay write.
- Done when: focused normal pytest reports exactly four strict xfails; forced RED reports exactly
  four missing-module failures with no collection/setup failure; S1-S3/S2B/static/OpenSpec/source
  invariants remain green; task 4.1 is Accepted and committed alone.
- Out of scope: EvidenceLanding implementation, adapter parsing code, Postgres persistence, bounded
  source-matrix replay, checkpoint dump, and task 4.2+ behavior.

## Approved RED design

- Exercise a future concrete ephemeral composition through only public `ingest/stream` behavior.
  The composition is a deterministic test adapter around the real landing core, not a local test
  subclass that fabricates the expected result.
- Use a representative historical-JSONL input grammar only to express readable, external-missing,
  and corrupt record outcomes. Task 4.2 owns the adapter implementation and broader source families.
- Retain the shared S3 `SourceRecord` type. New landing request/receipt/error/parser-reference types
  remain storage-independent and must not expose table names, SQL calls, filesystem layout, or
  implementation order.
- Keep four independent cases so a partial implementation cannot hide one failed invariant behind
  an aggregate scenario.

## Alternatives considered

1. Local `RecordingLanding` subclass: smallest test, but it would become GREEN when only types
   exist and would not drive real behavior. Rejected for Task 4.1.
2. Direct C2_0003 SQL assertions: strong persistence evidence, but duplicates Task 3.4 and leaks the
   4.3 repository choice. Rejected for this RED slice.
3. Concrete ephemeral conformance through `ingest/stream`: selected because it drives the deep
   module while keeping storage/providers replaceable; 4.3 will add real Postgres evidence.

## Implementation slices

- [x] Add four strict RED scenarios for hash/copy identity, parser-version replay, partial/corrupt
      quarantine, and no invented placeholders/canonical side effects.
- [x] Run normal focused pytest and prove exactly four strict xfails.
- [x] Run focused `--runxfail` and prove exactly four `ModuleNotFoundError` failures for the absent
      EvidenceLanding module, not syntax, fixture, assertion, or collection errors.
- [x] Run existing Task 3.1 interfaces, shared contracts, S1/S2/S2B/static/OpenSpec checks, and final
      source/candidate read-only invariants.
- [x] Record evidence, mark task 4.1 Accepted, stage only this task, and make one task-level commit.
      Do not start task 4.2 in the same commit.

## Invariants

- Original `pgtest` stays paused; original Milvus remains unopened and hash-only.
- Candidate stays C2_0003 with zero business rows; no disposable DB is created for a test-only RED.
- The S3 shared contracts and C2 history remain unchanged.
- Intentional RED catches only the absent future module. Any different failure blocks acceptance.

## Rollback note

- Revert the Task 4.1 test/docs commit. No runtime, schema, database, source, or provider state needs
  rollback.
