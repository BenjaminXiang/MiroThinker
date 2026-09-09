# Slice Contract: s3d-schema-integrity-migration

## Status

Accepted at `2026-07-11T17:48:21Z` under the user's objective-verification self-approval
authorization. A marked disposable database carried every destructive integration/rollback test and
was removed after evidence capture. The durable isolated candidate received only a gate-checked
forward C2_0001→C2_0002 upgrade and remains empty.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `3.4`
- Depends on: Accepted task 3.3
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s3-schema-integrity-plan.md`

## Goal

Add real PostgreSQL migration/integration coverage for foreign keys, logical uniqueness,
append-only evidence, reversible identity decisions, release scoping, consistent release pointers,
and migration rollback. Implement the smallest shared-storage revision needed to make those
observable constraints GREEN.

## User / operator effect

Later landing/build/publication adapters cannot silently create orphan evidence, replay duplicate
parser outputs, rewrite historical facts/decisions, join identities across releases, mix serving
release IDs, or leave the candidate unusable after a failed migration rollback.

## Non-goals

- Implement `EvidenceLanding`, `KnowledgeBuild`, `KnowledgeRead`, `KnowledgeAnswer`, or
  `ReleasePublication` behavior.
- Define Professor, Company, Paper, or Patent business fields/projections.
- Implement parsers, identity algorithms, LLM adjudication, eligibility policies, gap workflows,
  Milvus projections, promotion authorization, or Web/query behavior.
- Replay any source, create canonical business data, or publish an accepted release.
- Modify the legacy V001–V042 migration chain or any original/recovery database.

## Allowed scope

- `apps/miroflow-agent/canonical_v2_alembic/versions/C2_0002_create_shared_storage.py`.
- `apps/miroflow-agent/tests/canonical_v2/test_database_integrity.py`.
- `apps/miroflow-agent/scripts/canonical_v2_schema_fingerprint.py` and its focused regression test,
  solely to make schema-dump evidence deterministic across PostgreSQL 16 random control tokens.
- Narrow reusable DDL helpers local to the C2_0002 revision only if they reduce repeated invariant
  mistakes without becoming runtime interfaces.
- This slice/plan, OpenSpec task/change log, and verification evidence.
- Destructive test writes to only a newly created
  `miroflow_canonical_v2_s3d_disposable` database with the exact `disposable` marker, inside the
  existing network-none/no-port S3B PostgreSQL container.
- After GREEN, one schema-only upgrade of `miroflow_canonical_v2_candidate_s3b` through its dedicated
  Unix socket, after exact gate/name/marker/network/volume proof. Tests never downgrade this durable
  candidate.

## Shared storage boundary

- `landing`: immutable artifacts, parser runs, source records, and typed source errors.
- `knowledge`: releases, policies, source identities, source assertions, canonical identities and
  field/identity/relationship decisions plus their evidence/endpoint joins.
- `publish`: build/section manifests and the single consistent serving-release pointer.
- `ops` and typed domain schemas remain available but receive no table in this task.

## Required observable invariants

- Every child record references an existing parent; release-scoped canonical endpoints use composite
  foreign keys so an endpoint from another release cannot satisfy the relation.
- Parser-run record locators and assertion fingerprints are unique in their logical scope while the
  same real identity ID may be represented independently in different candidate releases.
- Landing artifacts/records/errors, source assertions, and decision history reject `UPDATE` and
  `DELETE`; correction is a new record/decision.
- A reverse identity decision references an existing decision in the same release; the original
  decision remains present and immutable.
- The active serving pointer references existing releases and requires canonical, publish, and
  index release IDs to equal its one active release.
- Downgrade from C2_0002 removes only its tables/functions and returns to the accepted C2_0001 eight-
  schema baseline; re-upgrade restores constraints and leaves the candidate at C2_0002.

## Forbidden changes

- Original `pgtest`, port `15432`, its source volume, recovery checkpoint DBs, S2B volumes, or
  original Milvus client/file mutation.
- Generic `DATABASE_URL`/`DATABASE_URL_TEST` target fallback.
- `DROP ... CASCADE` against business schemas; downgrade must name C2_0002 objects in dependency
  order and preserve all eight baseline schemas.
- Storing typed domain business facts only as generic assertion JSON.
- Direct source replay or durable fixture rows: integration tests roll back their data transactions.
- Runtime dependencies, APIs, consumers, provider calls, or protected root instructions/glossary.

## Required RED cases

1. Candidate head is C2_0001 rather than required C2_0002.
2. Required shared tables do not exist, so FK/uniqueness/append-only/reversal/release tests fail at
   their first real SQL interaction rather than passing against mocks.
3. No C2_0002 downgrade/re-upgrade path exists.

## Required checks

- Real disposable tests use psycopg transactions/savepoints and roll back fixture data.
- Focused run proves head/tables, FK, uniqueness, append-only, reversal, cross-release rejection,
  pointer consistency, downgrade to C2_0001, and final re-upgrade to C2_0002.
- Migration history remains a single linear Canonical V2 branch, independent of V042.
- Task 3.1 strict RED, Task 3.2 gate/static baseline, Task 3.3 contracts, S1, and S2/S2B regressions
  pass; no broad legacy migration suite receives an inherited DSN.
- Ruff, Pyright, strict OpenSpec, and diff checks pass.
- Formal S2B admission and original/disposable/candidate identities/hashes match before and after
  writes; the disposable database is dropped only after evidence is captured and candidate upgrade
  succeeds.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

## Stop conditions

- Any gate, database name/marker, network/port, volume, or source invariant differs.
- A test needs a typed domain field, provider, index, or module behavior owned by S4+.
- Constraint design would reject ordinary incomplete/uncertain evidence rather than preserve it.
- Migration rollback requires dropping the baseline schemas, using CASCADE, or deleting fixture/data
  outside the explicit test transaction.
- The same defect recurs after a fix without a sibling-pattern audit.

## Done means

- C2_0002 and its real integration suite are GREEN, reversible, and leave the isolated candidate at
  C2_0002 with zero durable fixture/business rows.
- All scoped regressions/static/safety checks and source/target invariants pass.
- Task 3.4 is Accepted and committed alone; Task 3.5 has not started in the same commit.

## Acceptance checkpoint

- Initial real RED was `7 failed`: two failures for absent `C2_0002` revision and five undefined-
  table failures across the real SQL paths. No mock, collection, fixture, or unrelated setup failure
  established RED.
- The first C2_0002 GREEN was `7 passed`. Deep self-review then added source/copy hash coexistence,
  mutable operational metadata, and manifest/release hash binding; the old DDL produced the intended
  `3 failed, 6 passed`, and the repaired DDL produced `9 passed`.
- `C2_0002` creates 24 shared tables across `landing`, `knowledge`, and `publish`, with 126 named
  constraints and 19 append-only triggers. It leaves all typed domain and `ops` schemas empty.
- Real tests prove parent FKs, parser replay/assertion uniqueness, identical-byte source/copy
  lineage, append-only artifact/assertion/decision history, updatable parser/source-identity
  operational metadata, same-release identity reversal, cross-release relationship rejection,
  release/manifest binding, single-release pointer checks, transaction rollback, and exact
  C2_0002→C2_0001→C2_0002 migration rollback.
- The disposable and durable candidate both reported C2_0002, 24 tables, zero rows, 126 constraints,
  and 19 triggers. Their deterministic normalized schema fingerprint matched at
  `ffeb1c92cb6dbc5ee9475b37142f632250b21dd97beb5da02a7f0642a64b6faf` over 50,032 bytes.
- PostgreSQL 16 raw `pg_dump` hashes were proved nondeterministic because of per-run
  `\\restrict`/`\\unrestrict` tokens. A tested fingerprint helper removes only those two control
  lines. The corrected C2_0001 fingerprint is
  `4c9df650d4f039ca9ba67ff6169ef44c839e0610528c2b27c4338eeeddf454c3` over 3,054 bytes.
- The sibling audit also repaired Task 3.2's baseline test: it now requires a disposable marker,
  targets C2_0001 rather than dynamic head, and restores the current head in `finally`. It cannot
  downgrade the durable candidate as the history grows.
- Real database/migration/fingerprint verification reported `13 passed`; normal no-DB Canonical V2
  reported `23 passed, 10 skipped, 5 xfailed`; S1 reported `9 passed`; S2/S2B reported `32 passed`.
  Ruff, Pyright, strict OpenSpec, formal gate, and diff checks passed.
- The test-only `miroflow_canonical_v2_s3d_disposable` database was dropped after evidence. Durable
  candidate `miroflow_canonical_v2_candidate_s3b` remains network-none/no-port at C2_0002, 24 tables,
  zero rows, system identifier `7661313446684311592`.
- Original `pgtest` stayed paused on its exact volume, recovery lab stayed network-none/no-port, and
  original Milvus/salvage hashes matched. No source replay, domain data, provider, index, runtime, or
  production-like write occurred.

## Pattern-fix report

- Reported cases fixed: nondeterministic schema-dump hash evidence; baseline rollback test coupled to
  a durable candidate and dynamic head.
- Defect class: volatile tool-output bytes treated as content identity, plus destructive migration
  tests whose target/revision scope widened as the migration graph grew.
- Sibling patterns searched: repository schema-dump/hash claims and Canonical V2 Alembic
  upgrade/downgrade integration tests.
- Sibling issues found/fixed: two Task 3.2 raw-hash claims and one candidate-bound baseline test.
- Not fixed and why: no other repository schema-dump hash or Canonical V2 destructive test matched
  the defect class.
- New invariant/helper/test: `canonical_v2_schema_fingerprint.py`, two normalization/CLI tests, and
  a disposable-only baseline test that restores current head.
- Remaining systemic risk: future dump evidence must use the helper; future destructive migration
  tests must provision an explicit disposable DB rather than reuse a populated candidate.
