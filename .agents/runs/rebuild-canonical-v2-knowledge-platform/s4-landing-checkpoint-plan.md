# Plan: S4 Landing Review and Checkpoint

## Task contract

- Goal: independently review tasks 4.1-4.4 as one immutable landing dependency, then create a
  content-addressed PostgreSQL checkpoint and prove that it restores to the same logical database
  state in a second isolated target before any canonical construction begins.
- Expected behavior / invariant: the checkpoint binds the exact Accepted S2B gate, Task 4.4 commit,
  six-family replay hashes, database target identity, schema fingerprint, every user-table row
  count/content hash, landing lineage/error aggregates, and the raw dump hash. A successful restore
  has a distinct PostgreSQL system identifier and byte-identical logical snapshot.
- Context: OpenSpec task 4.5 after reviewable Task 4.4 commit
  `cef42a1e075d30c5a0e179f34ab543b4878edabd`; the isolated candidate is at
  C2_0004 with only the bounded landing matrix and no canonical, domain, publication, or index data.
- Constraints: one Task 4.5 commit, test-first checkpoint logic, no original/recovery-source write,
  no original Milvus client, no candidate downgrade or mutable landing operation, no canonical
  construction, and no production-like target or promotion.
- Done when: no Critical/Important landing-review finding remains; a raw custom-format dump and
  committed manifest exist under a named external read-only checkpoint root; a fresh network-none,
  no-port, tmpfs PostgreSQL target restores the dump and matches schema/table/lineage hashes; the
  restore target is destroyed without adding a Docker volume; all acceptance and regression checks
  pass; task 4.5 and S4 are Accepted and committed alone.
- Out of scope: assertions, identity resolution, canonical decisions, domain projections,
  recollection, release/index construction, consumer migration, source cleanup, or cutover.

## Checkpoint design

- Add a task-scoped checkpoint tool under `s4e/`; production modules and public interfaces do not
  gain a backup API.
- Require the exact Accepted S2B gate before reading the candidate and bind the exact committed
  matrix/replay-summary hashes. Fail before dump creation on any mismatch.
- Capture a pre-dump logical snapshot, stream `pg_dump --format=custom --serializable-deferrable`
  from the exact named candidate to an atomic external file, then capture a post-dump snapshot. The
  two source snapshots must match.
- Hash every user table as sorted PostgreSQL `to_jsonb(row)::text` lines, so the snapshot is order
  independent but remains duplicate sensitive. Include the independent normalized schema-only dump
  fingerprint and explicit landing lineage/status/error aggregates.
- Restore into a newly named `pgvector/pgvector:pg16` container and a distinctly named disposable
  database with `network=none`, no published ports, `restart=no`, tmpfs PGDATA, a bounded local Unix
  socket only, and no persistent/anonymous volume. Full schema/table/logical parity—not reuse of the
  source database name—proves fidelity, while the disposable marker and distinct PostgreSQL system
  identifier prove target independence.
- Compare the complete restored logical snapshot and schema fingerprint to the frozen source
  snapshot, recheck the raw dump hash, destroy the restore target in `finally`, and prove the Docker
  volume set and candidate snapshot did not change.
- Keep the binary dump outside Git. Commit only its path/size/SHA-256, deterministic logical
  summaries, restore evidence, review disposition, and acceptance record.

## Implementation slices

- \[x\] Complete the read-only independent review of Task 4.4 and the S4 acceptance checklist.
- \[x\] Add focused RED tests for exact checkpoint inputs, source stability, table hashing, restore
  independence/isolation, logical parity, and strict evidence serialization.
- \[x\] Implement the minimum task-scoped checkpoint/snapshot/restore tool and make focused tests
  GREEN.
- \[x\] Re-run the six-family replay idempotently and require byte identity with the committed Task
  4.4 summary before checkpointing.
- \[x\] Create the external dump/manifest, restore it in the fresh isolated target, compare every
  summary/hash, remove the restore target, and freeze the checkpoint root read-only.
- \[x\] Resolve review findings, run focused and expanded Canonical V2/S1/S2/S2B/static/OpenSpec/source
  checks, update acceptance/evidence, accept S4, and commit only Task 4.5.

## Invariants

- Original `pgtest` stays paused on the recorded volume; original Milvus is hash-checked only and is
  never opened by a client.
- The durable candidate is read for checkpointing. The only permitted candidate write path in this
  task is an exact idempotent Task 4.4 replay through the accepted `EvidenceLanding` interface; row
  counts and content hashes must not change.
- Restore writes occur only after the fresh container/database name, marker, network, ports, restart
  policy, tmpfs PGDATA, system identifier, and Docker-volume baseline are proved.
- No dump or restore result can accept a non-empty knowledge/domain/publish/ops business table.
- A hash-only dump without independent restore parity cannot accept S4.

## Rollback note

- Revert the Task 4.5 commit to remove the tool/evidence status. The external checkpoint is immutable
  recovery evidence and is not deleted by rollback. A failed temporary restore container/socket is
  removed without modifying the source candidate. Canonical construction does not start in this
  task.
