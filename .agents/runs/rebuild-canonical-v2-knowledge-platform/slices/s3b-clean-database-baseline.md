# Slice Contract: s3b-clean-database-baseline

## Status

Accepted at `2026-07-11T16:58:23Z` under the user's objective-verification self-approval
authorization. The first target write followed a successful exact S2B admission and source-
invariant check. This acceptance covers only the independent empty namespace baseline; it does not
accept Task 3.3 types, Task 3.4 business tables/constraints, landing data, or a publishable release.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `3.2`
- Depends on: Accepted task 2.6/S2B and Accepted task 3.1
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s3-database-baseline-plan.md`

## Goal

Create a clean Canonical V2 migration baseline, independent of the V001–V042 history, and apply it
to one new explicitly identified isolated PostgreSQL candidate. The baseline creates only the
physical namespace boundary needed by later typed-contract and schema tasks.

## User / operator effect

Canonical V2 construction starts in a database that cannot silently inherit, migrate, or mutate the
legacy/recovery databases. Later landing, knowledge, domain, publication, and operations work has a
clear home without committing the product to V042 tables or a generic graph.

## Non-goals

- Create artifact, assertion, identity, relationship, domain-object, release, review, or gap tables.
- Implement Task 3.3 shared types or Task 3.4 integrity constraints.
- Replay, parse, recollect, enrich, publish, index, or cut over data.
- Modify the historical `apps/miroflow-agent/alembic/` V001–V042 chain.
- Connect to or change original/recovery-evidence PostgreSQL or Milvus targets.

## Allowed scope

- A separate Canonical V2 Alembic config, environment, template, and base revision under
  `apps/miroflow-agent/`.
- A narrow reusable pre-write S2B admission verifier under
  `apps/miroflow-agent/src/data_agents/canonical_v2/`.
- Focused baseline/gate tests under `apps/miroflow-agent/tests/canonical_v2/`.
- One new network-none/no-port PostgreSQL container, one named labeled volume, one host-local Unix
  socket directory, and one database marked `isolated-candidate`.
- This slice/plan, OpenSpec task/change log, and verification evidence.

## Baseline namespace contract

- Shared evidence/input: `landing`.
- Shared canonical semantics: `knowledge`.
- Typed domains: `professor`, `company`, `paper`, and `patent`.
- Serving and operations: `publish` and `ops`.
- `public` contains no legacy/domain table; it may contain only the separately named Canonical V2
  Alembic version table.
- The baseline revision creates namespaces only. Later tasks own all business tables and integrity
  contracts.

## Intended isolated target

- Database: `miroflow_canonical_v2_candidate_s3b`.
- Marker:
  `miroflow:destructive-target:v1:isolated-candidate:miroflow_canonical_v2_candidate_s3b`.
- Container: `canonical-v2-s3b-pg-20260711` using `pgvector/pgvector:pg16`.
- Persistent storage: a newly created named volume carrying labels for this slice, target kind, and
  exact database identity.
- Connectivity: Docker network mode `none`, zero published ports, and a dedicated host-local Unix
  socket directory only.
- The target must not reuse `pgtest`, either recovery checkpoint database, any S1 disposable
  database, the S2B materialization/probe volumes, or any original/recovery source volume.

## Forbidden changes

- Original `pgtest`, port `15432`, or volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- Recovery databases `miroflow_recovery_candidate` and `miroflow_recovery_candidate_verify`.
- Original `apps/miroflow-agent/milvus.db` client access or any Milvus mutation.
- Generic `DATABASE_URL`/`DATABASE_URL_TEST` fallback for target or gate selection.
- `DROP ... CASCADE` in the namespace baseline; unexpected residual objects must block downgrade.
- Dependencies, runtime retrieval/chat/admin behavior, provider calls, or source data.

## Expected unchanged behavior

- The V001–V042 Alembic history, configuration, and existing runtime consumers remain unchanged.
- Task 3.1 remains intentional strict RED for the five unimplemented deep-module interfaces.
- Accepted S2/S2B artifacts and frozen sources remain byte-identical.

## Required RED cases

1. No separate Canonical V2 Alembic history/config exists.
2. No exact accepted-backup verifier exists at the migration boundary.
3. A missing, changed, or non-accepted S2B artifact rejects migration before engine connection.
4. The real isolated target initially has no Canonical V2 revision or namespace baseline.

## Required checks

- Pure tests prove the new history has exactly one independent base/head and does not reference V042.
- Admission tests prove exact S2B evidence passes and missing/tampered evidence fails closed.
- Real PostgreSQL downgrade/base, upgrade/head, namespace/revision inspection, downgrade, and final
  re-upgrade pass using only the explicit isolated-candidate DSN and marker.
- The candidate has exactly the eight required business schemas, no business tables yet, no legacy
  public tables, and the expected Canonical V2 revision.
- Normal Task 3.1 behavior remains five xfails; S1 target safety and S2/S2B suites pass.
- Ruff, Pyright, strict OpenSpec, and `git diff --check` pass.
- The formal S2B gate, original pause/volume, recovery-lab isolation, Milvus hash, and salvage hash
  pass before and after database work.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

## Stop conditions

- The accepted S2B gate fails or any accepted evidence hash changes.
- The proposed container, volume, database, marker, network, port, or socket identity differs from
  this contract before first write.
- Any connection resolves to a TCP port, forbidden database, recovery checkpoint, or unmarked DB.
- Implementing the baseline requires a business table/field/constraint decision owned by 3.3/3.4.
- Upgrade or downgrade invokes the V001–V042 history.
- Original-source pause/hash/identity changes.

## Done means

- The independent base revision and fail-closed admission boundary are GREEN.
- The new isolated candidate is left at the accepted Canonical V2 baseline head after a successful
  downgrade/re-upgrade rehearsal.
- Target identity/isolation, schema/revision inspection, regression checks, and source invariants
  are recorded.
- Task 3.2 is Accepted and committed alone; Task 3.3 has not started in the same commit.

## Acceptance checkpoint

- The pre-write S2B command returned `state=accepted`, `source_count=50`, backup manifest
  `a14c1eab…e59c8`, and restore verification `98826e8d…d231`; original PostgreSQL/Milvus/salvage
  invariants matched immediately before and after the slice.
- RED was observed as `6 failed, 1 skipped`: five failures for the absent typed gate module and one
  for the absent independent Alembic root. After the empty isolated target existed, the real test
  independently failed only because that same Alembic root was absent; the DB still had zero public
  tables and zero Canonical V2 schemas.
- The target is container `canonical-v2-s3b-pg-20260711` (network `none`, ports `{}`, restart `no`),
  named volume `canonical-v2-s3b-pgdata-20260711`, and database
  `miroflow_canonical_v2_candidate_s3b` with the exact `isolated-candidate` marker. The database
  system identifier is `7661313446684311592`.
- An initial `0770` Unix-socket attempt excluded the host because the postgres child retained GID
  999 rather than the requested supplemental group. No migration ran. The same empty target volume
  was remounted with a `0777` socket inside a host directory restricted to `0770`; network and port
  isolation remained unchanged, and the real DSN then passed.
- The real integration test successfully ran base → `C2_0001` → base → `C2_0001`. Final state has
  exactly the eight contracted schemas, zero business tables, only
  `public.canonical_v2_alembic_version`, and schema-only dump SHA-256
  `9605da198e468fe5bbf2d87270be411b9663d639d6fa1b427c6593401585f09b`.
- Canonical V2 tests reported `7 passed, 5 xfailed`; S1 target safety `9 passed`; S2/S2B `32 passed`;
  Ruff and Pyright were clean; strict OpenSpec and diff checks passed.
