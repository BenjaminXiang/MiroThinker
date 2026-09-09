# Slice Contract: s4c-evidence-landing-postgres

## Status

Accepted at `2026-07-11T19:42:20Z`. This slice implements OpenSpec task 4.3 against Accepted task
4.2 commit `c9929d5`. It does not authorize Task 4.4 actual-source replay or any durable-candidate
write.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `4.3`
- Depends on: Accepted task 4.2 at commit `c9929d5`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4-landing-persistence-plan.md`

## Goal

Make immutable landing evidence restart-safe and cross-process replayable in explicit isolated
PostgreSQL while preserving the small Task 4.2 public seam and all typed degradation behavior.

## Non-goals

- Replay actual forensic, historical, Milvus, or collected-response sources.
- Upgrade or populate the durable isolated candidate.
- Build source assertions, identity, canonical/domain projections, releases, or indexes.
- Add acquisition/provider clients, runtime consumers, or production cutover behavior.
- Accept S4; tasks 4.4 and 4.5 remain separate.

## Allowed scope

- EvidenceLanding repository-seam refactor and one PostgreSQL repository adapter/factory.
- One new reversible Canonical V2 migration after C2_0003.
- Focused Task 4.3 integration tests and synchronized Canonical V2 migration fixtures.
- Synthetic bytes only; one newly created exact-marked disposable database in the existing
  network-none/no-port S3 PostgreSQL container.
- This plan/slice plus OpenSpec task/change log and verification evidence.

## Forbidden changes

- Any original/recovery/durable-candidate database write, original Milvus client, or source replay.
- Generic `DATABASE_URL` fallback, implicit target identity, or write before Accepted gate proof.
- Historical migration rewrite, irreversible migration, or schema work beyond durable landing
  semantics required by task 4.3.
- Direct canonical/publication/index mutation, dependency addition, or legacy runtime/API change.

## Expected unchanged behavior

- Task 4.2 ephemeral tests and all accepted S1–S3/S2B behavior remain GREEN.
- KnowledgeBuild, KnowledgeRead, KnowledgeAnswer, and ReleasePublication remain strict RED.
- The durable candidate remains C2_0003 with 24 tables and zero business rows.

## Required checks

- RED is observed for missing C2_0004 and PostgreSQL composition before implementation.
- Real disposable tests prove restart/replay, exact idempotency, same-run conflict, concurrent same-
  run serialization, ordered typed errors, parent lineage, atomic rollback, and immutable rows.
- C2_0004 upgrades/downgrades/re-upgrades only the disposable target and restores current head.
- Task 4.2, expanded Canonical V2, S1, S2/S2B, Ruff format/check, Pyright, strict OpenSpec, staged
  diff, formal backup gate, original hashes/pause, recovery isolation, and read-only candidate state
  pass after the final write.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- C2_0003 cannot express the required durable behavior with one bounded forward migration.
- A test target cannot be independently proven disposable before migration/landing writes.
- Correctness requires actual source replay, a durable-candidate write, a later-slice interface, or a
  product decision absent from approved OpenSpec.
- Atomicity, append-only history, or exact replay cannot be proven through public behavior plus real
  database state.

## Done means

- Independent PostgreSQL-backed instances reconstruct identical receipts/records and never rewrite
  prior artifact/parser/record/error/run history.
- All failure/concurrency cases are transactionally closed with zero partial visibility.
- The disposable database is dropped, source/candidate invariants match, task 4.3 is Accepted and
  committed alone, and task 4.4 has not started in the same commit.

## Acceptance checkpoint

- Initial real RED was exactly `6 failed`: absent C2_0004, PostgreSQL module, and persistence error
  type. Subsequent self-review RED covered relative gate paths, nonempty C2_0003 upgrade, and
  non-standard JSON constants before their shared fixes.
- Final real disposable migration/landing verification is `34 passed`; focused ephemeral landing is
  `17 passed`; default Canonical V2 is `41 passed, 32 skipped, 4 xfailed`.
- S1 is `10 passed, 5 skipped`; S2/S2B is `32 passed`; Ruff check/format, Pyright, strict OpenSpec,
  diff checks, and the forced future-module RED boundary pass.
- Before deletion, the disposable was C2_0004 with 25 tables, 153 constraints, 46 non-internal
  triggers, required parser/order columns, and zero business rows. It is now absent.
- Formal gate/source invariants remain unchanged; the durable candidate was read-only and remains
  C2_0003 with 24 tables and zero rows. No actual source, Milvus, provider, canonical, publication,
  index, dependency, or legacy runtime behavior changed.
