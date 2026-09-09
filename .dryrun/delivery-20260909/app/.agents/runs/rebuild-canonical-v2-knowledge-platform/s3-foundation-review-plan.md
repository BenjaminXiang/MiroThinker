# Plan: S3 Foundation Review and Acceptance

## Task contract

- Goal: independently decide whether the complete S3 database/interface foundation is safe for S4
  and later builders to depend on, repairing only acceptance-blocking foundation defects found by
  objective review.
- Expected behavior / invariant: shared public types do not drift; evidence lineage is hash-bound;
  append-only history rejects destructive row and bulk mutation; decision reversal/supersession can
  retain cross-release lineage; structured-LLM decisions retain an auditable trace; all writes stay
  inside an explicitly marked disposable or isolated-candidate database.
- Context: OpenSpec task 3.5 after Accepted tasks 3.1-3.4, commits `905ca35..e7fffe2`.
- Constraints: no original/recovery-source write, no provider or Milvus client, no S4 adapter or
  domain implementation, no production-like promotion, and no edit to the accepted S2B evidence.
- Done when: independent review findings have RED/GREEN evidence, the isolated candidate is at the
  reviewed head with zero business rows, all S1-S3/static/OpenSpec/source-safety checks pass, S3 is
  Accepted, and task 3.5 is committed alone.
- Out of scope: landing ingestion, canonical build orchestration, typed domain projections,
  publication implementation, and any active-release/index mutation.

## Implementation slices

- [x] Review `a581ff5..e7fffe2` against the OpenSpec design/specs, shared contracts, DDL, tests, and
      accepted predecessor evidence; classify findings by user/operational effect.
- [x] Add focused RED coverage for each acceptance-blocking defect and prove the failure on current
      code/current C2_0002 in an explicitly marked disposable database.
- [x] Implement the smallest shared-contract/interface/migration repair, using a new forward
      revision rather than rewriting Accepted migration history.
- [x] Re-run focused GREEN plus downgrade/re-upgrade, contract/interface RED, target-safety,
      S2/S2B admission, static checks, strict OpenSpec, and source/candidate invariants.
- [x] Record the independent review disposition and remaining non-blocking risks; accept S3 only if
      no Critical/Important finding remains.
- [x] Stage only Task 3.5 files, review the staged diff, and make one task-level commit.

## Invariants

- Original `pgtest` remains paused on its recorded volume; original Milvus stays unopened and its
  recorded SHA-256 remains unchanged.
- Destructive review tests use only a newly created exact-identity `disposable` database. The durable
  candidate is only forward-upgraded after GREEN and is never downgraded by a test.
- C2_0001/C2_0002 remain immutable history. Any repair is a new reversible revision.
- Task 3.1's five interface cases remain strict intentional RED until their owning modules exist.
- No later S4 behavior is made GREEN in this task.

## Rollback note

- Before S4 data exists, downgrade the isolated candidate from the new repair revision to C2_0002,
  or revert this task-level commit. Disposable review databases are dropped after verification.
