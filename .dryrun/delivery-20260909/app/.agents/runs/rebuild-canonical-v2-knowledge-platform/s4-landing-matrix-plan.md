# Task 4.4 Bounded Evidence Matrix Implementation Plan

## Task contract

- Goal: replay one real, bounded representative from each required landing family into the isolated
  Canonical V2 candidate and prove exact input lineage plus deterministic record/error summaries.
- Expected invariant: only Accepted S2B backup/restore bytes are read; every derived export names a
  registered restore parent; original PostgreSQL/Milvus paths remain unopened; landing writes affect
  only the explicitly marked isolated candidate.
- Context: tasks 4.1-4.3 and C2_0004 are accepted; the durable candidate remains empty at C2_0003.
- Constraints: TDD, one Task 4.4 commit, no live provider call, no canonical/publish/index write, no
  candidate downgrade, and no source mutation.
- Done when: the six-family matrix, input/output hashes, counts, typed errors, parent chain, restart
  replay, candidate identity, and source invariants all match a committed deterministic checkpoint.
- Out of scope: full-corpus ingestion, recollection, canonical construction, landing-slice acceptance
  or checkpoint dump (Task 4.5), and production-like promotion.

## Plan

- Files/areas: `EvidenceLanding` artifact registration, bounded SQLite/recorded-response adapter
  behavior, a task-scoped S4D replay tool/test/matrix, Task 4.4 evidence and OpenSpec status.
- Implementation slices:
  1. Add RED tests for streaming file-manifest registration, parent lineage, source-manifest
     verification, bounded deterministic extraction, and summary mismatch rejection.
  2. Implement registration and task-scoped materializers behind testable seams.
  3. Dry-run the real six-family matrix, freeze its derived hashes/counts/errors, and rerun RED/GREEN.
  4. Recheck the exact S2B gate and candidate identity, upgrade C2_0003 to C2_0004, replay once, then
     restart/replay idempotently and compare checkpoint bytes.
  5. Run focused, expanded, static, OpenSpec, source/candidate invariant, and diff checks; update
     evidence and commit only Task 4.4 files.
- Tests/checks: focused S4D unit/real-Postgres tests, existing landing tests, Canonical V2 suite,
  S1/S2/S2B regression, Ruff, Pyright, strict OpenSpec, `git diff --check`, exact source hashes.
- Invariants: no placeholder facts; partial WAL/cache fields retain typed errors; no active release or
  canonical rows; no original Milvus client; Docker extraction uses network-none/read-only/tmpfs and
  creates no anonymous persistent volume.
- Rollback note: before candidate replay, revert code/docs normally. After replay, do not delete or
  mutate immutable landing rows; reject/discard the isolated candidate as a unit. Task 4.5 owns its
  dump/checkpoint.

## Progress

- [x] Freeze the six concrete Accepted-S2B source members and bounded selectors.
- [x] Add and satisfy registration, adapter, manifest, materializer, preflight, and strict-JSON RED.
- [x] Run two byte-identical real-source observe passes and freeze entry summaries.
- [x] Prove the streaming registration path on a real disposable C2_0004 database.
- [x] Recheck the gate/target, forward-upgrade the empty candidate, and replay the matrix.
- [x] Re-run durable replay idempotently with byte-identical summaries and unchanged row counts.
- [x] Run focused/broad PostgreSQL, Canonical V2, S1, S2/S2B, static, OpenSpec, diff, and source-
  invariant checks; update evidence for the Task 4.4 commit.
