# Slice Contract: s3e-foundation-review

## Status

Accepted at `2026-07-11T18:22:18Z` under the user's objective-verification self-approval
authorization. Every Critical/Important review finding has RED/GREEN evidence and is repaired. This
acceptance does not authorize S4 ingestion or any source, publication, or index write.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `3.5`
- Depends on: Accepted tasks 3.1-3.4 through commit `e7fffe2`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s3-foundation-review-plan.md`

## Goal

Review the full S3 interface/database foundation as a later-builder dependency, reproduce any
acceptance-blocking defect, repair its defect class without rewriting accepted history, and promote
S3 to Accepted only on fresh objective evidence.

## Non-goals

- Implement any of the five deep modules or begin immutable landing replay.
- Define Professor, Company, Paper, or Patent business tables.
- Persist complete S5-S10 behavior that properly belongs to later slices.
- Change accepted corpus, thresholds, backup/restore evidence, or source inventories.
- Promote a release, build/open Milvus, call Web/LLM providers, or write original/recovery sources.

## Allowed scope

- S3 shared contracts and strict RED interface tests under
  `apps/miroflow-agent/{src/data_agents/canonical_v2,tests/canonical_v2}`.
- A new forward-only Canonical V2 repair revision and focused real integration tests.
- This slice/plan, OpenSpec task/change log, verification contract/evidence, and an independent S3
  review note.
- Destructive tests only in a newly created, exact-marked
  `miroflow_canonical_v2_s3d_disposable` database within the existing network-none/no-port S3
  PostgreSQL container.
- After GREEN, one guarded forward upgrade of the zero-row durable isolated candidate.

## Forbidden changes

- Rewrite C2_0001 or C2_0002.
- Connect to or write the original `pgtest`, recovery restore target, or any unmarked database.
- Downgrade or insert fixture/business rows into the durable isolated candidate.
- Modify original/backup/restore bytes, use a Milvus client, call external providers, or start S4.
- Broaden into domain schemas, repositories, adapter orchestration, or consumer migration.

## Expected unchanged behavior

- Accepted S1, S2, S2B, and tasks 3.1-3.4 evidence remains valid.
- Existing application/chat/retrieval behavior and legacy schemas remain untouched.
- The five future deep-module tests remain strict `xfail` for only missing module seams.

## Required checks

- Focused RED/GREEN evidence for every retained review finding.
- Real disposable migration upgrade/downgrade/re-upgrade with exact target and backup gate.
- Full Canonical V2 S3 tests, S1 target safety, S2/S2B tests, Ruff, Pyright, strict OpenSpec, and
  staged diff checks.
- Fresh formal backup-gate/source invariants and read-only original/candidate identity/hash/isolation
  checks after the last write.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s3-foundation-review.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- A finding requires a product choice not already determined by OpenSpec.
- Repair requires S4+ behavior, broad schema redesign, source/provider/Milvus access, or an unsafe
  target.
- Original/source invariants differ, formal S2B admission fails, or the disposable identity cannot
  be proved before write.
- A Critical/Important finding remains unresolved after bounded repair and verification.

## Done means

- Review findings are reproducible and repaired or explicitly shown non-blocking with evidence.
- The public type seam, evidence lineage, history/reversal, release scope, and migration rollback
  foundation are coherent enough for S4 to depend on.
- The candidate is at the reviewed head with zero durable business rows; the review database is
  absent; original/source invariants are unchanged.
- Task 3.5 and all S3 are Accepted and committed alone; S4 has not begun in the same commit.

## Acceptance checkpoint

- Review disposition and effect-based finding matrix:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s3-foundation-review.md`.
- C2_0003 is a new reversible forward revision; C2_0001/C2_0002 were not rewritten.
- Full default Canonical V2 verification was `47 passed, 5 xfailed`; forced interface RED was exactly
  five missing-module failures. Real migration downgrade/re-upgrade, S1, S2/S2B, Ruff, Pyright,
  strict OpenSpec, and diff checks passed.
- Disposable/candidate schema fingerprints matched at
  `7d85702ecb0e84cbbbbbc175f88c4b735190e53f4a576c72e49088899dd94991`; the candidate is C2_0003
  with 24 tables, zero rows, 141 constraints, 44 triggers, and three LLM-trace columns.
- The disposable database is absent. Formal S2B admission and original source/container/hash
  invariants remained unchanged. S4 has not started.
