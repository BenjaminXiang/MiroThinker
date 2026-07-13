# Slice Contract: s6c-typed-domain-projection-green

## Status

Accepted at `2026-07-13T09:56:27Z`. S5G first closed the shared temporal interface; Task 6.3 then
completed four-domain inclusion, explicit typed roots and all catalog subobjects, exact
assertion/decision lineage, packaged catalog parity, C2_0009 storage/restart, and direct-SQL safety.
The merged specification/code-quality and migration/write-safety review closed every finding and
has zero open Critical/Important issues.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.3`
- Depends on: Accepted aggregate S5, Task 6.1 catalog, and Task 6.2 RED
- Migration parent: `C2_0008`; this slice owns `C2_0009` as the single linear descendant.

## Goal

Implement reproducible typed current Professor, Company, Paper, and Patent
projections plus the four versioned inclusion-policy adapters over retained S5
assertions/decisions and resolved identities. Persist release-scoped current
projections and typed business sub-objects in the isolated Canonical V2 schemas
without importing execution artifacts, weakening append-only history, or
creating a global completeness gate.

## User effect

- Every included object has a domain-typed current representation suitable for
  validation, display, exact lookup, structured filtering, later semantic
  projection, and evidence audit.
- Approved seed/export/skeleton scope and offline incremental validation produce
  the inclusion effects frozen by Task 6.2; Web-only or out-of-scope evidence
  remains available as evidence but is not silently promoted.
- Missing optional enrichment stays visible as quality/limitation information;
  it does not erase otherwise valid domain objects.
- Every projected field and sub-object traces to the exact retained assertion and
  current canonical decision that selected it.

## Lean execution

- This slice contract and OpenSpec Task 6.3 are the only implementation-plan
  sources.
- Work vertically: turn one Task 6.2 scenario GREEN, then complete its sibling
  domain cases, then add typed projection behavior, then add isolated durable
  persistence and rollback.
- Run focused tests while iterating. Perform one merged specification/code-
  quality review for Task 6.3 plus one focused migration/write-safety review.
- Run broad no-database/migration regression and the formal safety checkpoint
  once before the task commit.

## Product module seams

### Domain inclusion

`src.data_agents.canonical_v2.domain_inclusion` implements the already-frozen
deep module:

```python
DomainInclusionEngine.evaluate(
    InclusionBatchRequest
) -> DomainInclusionResult
```

Four domain policies remain internal adapters. The module accepts only explicit
typed inputs, performs no storage/provider/query mutation, reuses shared
`PolicyReference`/`PolicyDecision`, and returns deterministic content-bound
results.

### Typed projection

`src.data_agents.canonical_v2.domain_projection` exposes one package-internal
deep module:

```python
DomainProjectionBuilder.project(
    DomainProjectionRequest
) -> DomainProjectionResult
```

The request binds one release/run/as-of, the installed catalog version/hash,
active canonical identities and exact source assignments, retained assertions,
accepted/current S5 decision history, and inclusion results. The result contains
exactly four explicit Pydantic projection families, typed sub-objects, rejected
projection diagnostics, manifests/counts/hashes, and assertion/decision lineage.
It never accepts precomputed untyped domain JSON as canonical truth.

`src.data_agents.canonical_v2.domain_projection_postgres` is the sole explicit
offline/disposable adapter for release-scoped persistence and restart loading.
It does not alter active release pointers.

## Product catalog rule

- Runtime code SHALL load an immutable packaged catalog/config under product
  `src/` or approved product config, with exact schema/catalog/content identity
  matching Accepted Task 6.1.
- Product code SHALL NOT import or open `.agents/runs`.
- The Accepted Task 6.1 artifact remains verification evidence. Tests compare
  its content identity to the packaged catalog without making the execution
  artifact a runtime dependency.
- Catalog fields/sub-objects SHALL map to explicit typed models and physical
  columns/typed child records. Do not introduce EAV field/value storage or a
  generic graph/summary property as the canonical domain representation.

## Typed projection invariants

- Exactly four root projection types: Professor, Company, Paper, Patent.
- Shared envelope: release, canonical identity, entity type, display/core facts,
  source assertion/decision lineage, observation/update metadata, quality
  signals, projection/catalog version, and deterministic content hash.
- Domain fields and all 28 frozen sub-object types follow the Accepted catalog's
  value/cardinality/requiredness/temporal/evidence semantics.
- Date-only and instant validity retain distinct precision through typed input,
  content identity, lineage equality, persistence, and restart. UTC-midnight
  coercion and unversioned cross-precision comparison are forbidden.
- Requiredness is proportional: canonical identity/envelope requirements fail
  closed; fields conditional on accepted evidence are optional when absent and
  do not receive placeholders.
- Unknown catalog fields, wrong-domain paths, duplicate scalar selections,
  dangling assertions/decisions, mismatched release/identity, unsupported
  sub-object members, invalid time/cardinality, and unselected evidence fail
  closed.
- Competing assertions/history remain in S5; current projections copy only exact
  selected values plus their decision/assertion references and never mutate
  history.
- Input order does not change projection bytes, hashes, manifests, or persisted
  restart results.

## Physical storage and migration

- Add one new reversible migration after `C2_0008` for typed release-scoped
  current projection roots and typed sub-object storage in the four domain
  schemas, plus required manifest/lineage constraints.
- Common/filterable scalar facts use typed columns. Typed lists may use typed
  arrays where semantically scalar-many. Business sub-objects use typed child
  rows with stable IDs/parent FKs; JSONB/EAV may not replace the catalog's typed
  field/sub-object contract.
- Writes require the existing explicit disposable/offline target guard and one
  candidate release/build run. No upsert may mutate an existing different
  content hash; idempotent identical replay is allowed, conflicting replay fails
  atomically, and partial failure leaves no root/sub-object subset.
- FK, release/domain identity, lineage, uniqueness, append-only, time, content-
  hash, and parent-child invariants must hold in adapter and direct SQL paths.
- Upgrade/downgrade is exercised only on an owned real disposable database.
  Populated downgrade must refuse or be proven lossless under the migration
  contract; no durable Candidate migration is authorized in this task.

## Vertical TDD increments

1. Professor/Paper inclusion GREEN, including no runtime institution whitelist
   and roster discovery distinct from authorship.
2. Patent/Company inclusion GREEN, including full approved export scope,
   skeleton admission, four-dimension incremental review/exclusion, manifest
   integrity, determinism, and Web-only non-promotion.
3. Explicit four-domain Pydantic current projections and all catalog sub-object
   shapes from synthetic retained S5 histories; negative sibling matrix.
4. Product catalog packaging/hash parity and wheel inclusion without `.agents`
   runtime access.
5. `C2_0009` real-disposable persistence, direct-SQL constraints, restart,
   idempotency/conflict/rollback/concurrency, upgrade/downgrade safety.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/` domain inclusion,
  projection, storage, and packaged catalog/config files.
- `apps/miroflow-agent/canonical_v2_alembic/versions/C2_0009_*.py`.
- Focused Canonical V2 domain projection/inclusion/Postgres/migration tests.
- Existing Task 6.2 tests where a contract defect is proven during GREEN.
- This slice plus Task 6.3 verification/task/change-log/acceptance evidence.

## Forbidden changes

- Legacy domain, chat, query, retrieval, admin, Milvus, publication, provider, or
  consumer code.
- Task 6.1 evidence catalog/builder/validator bytes, original/recovery/landing
  evidence, durable Candidate database, or active release/index pointers.
- Task 6.4/6.5 relationship execution, Task 6.6/6.7 path eligibility, S7 release
  build/publication, or S8 institution/query rewriting.
- Runtime import/read of `.agents`, institution-name enumeration, workbook-case
  hardcoding, placeholders for missing facts, one global `ready`, EAV/generic-
  graph canonical storage, or pre-launch ID compatibility work.

## Required checks

- L1: nearest active inclusion/projection/storage test for each increment.
- L2: all Task 6.2 inclusion tests GREEN; complete four-domain projection tests;
  Accepted S5 decision/identity/temporal contracts; Task 6.1 catalog contracts.
- Focused real disposable PostgreSQL migration/store suite with explicit target
  identity, upgrade/downgrade/restart/rollback/direct-SQL/idempotency/conflict
  evidence and owned cleanup.
- One merged Task 6.3 spec/code-quality review and one focused migration/write-
  safety review, both with zero open Critical/Important findings.
- Commit checkpoint: relevant Canonical V2/S1/S2B/S4 no-DB and migration checks,
  Ruff, Pyright, wheel contents, strict OpenSpec, formal backup gate, explicit
  target/source/Candidate audit, diff/secret/cache/scope, and cleanup.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,acceptance.md,change-log.md}`

## Stop conditions

- A catalog field/sub-object cannot receive an explicit typed representation
  without inventing product semantics.
- Required typed/filterable facts would be stored only in untyped JSON/EAV or a
  generic graph.
- Inclusion behavior conflicts with the Accepted Task 6.2 RED contract.
- Projection cannot bind every current value to one exact accepted S5 decision
  and retained assertion set.
- A second migration head appears, a target is missing/ambiguous/non-disposable,
  populated rollback is lossy, or direct SQL bypasses invariants.
- Correctness requires legacy/runtime/relationship/path/publication changes or
  any original/recovery/durable-Candidate write.
- Correctness requires changing the Accepted S5 shared temporal contract before
  Task 5.7/S5G is independently specified and Accepted.

## Done means

- Task 6.2 is fully GREEN through product code; four explicit typed root
  projections and all frozen domain sub-objects are reproducible, content-bound,
  evidence/decision-traceable, persist/restart identically in a real disposable,
  and package without `.agents` runtime dependence.
- The reversible migration and adapter pass focused safety review and all task
  checks; one merged task review has zero open Critical/Important findings.
- Task 6.3 is Accepted and committed alone. No relationship/path/release/index/
  query/answer behavior or durable Candidate state is mixed into the checkpoint.
