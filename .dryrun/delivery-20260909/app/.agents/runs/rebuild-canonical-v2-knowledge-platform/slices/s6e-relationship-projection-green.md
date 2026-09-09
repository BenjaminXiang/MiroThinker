# Slice Contract: s6e-relationship-projection-green

## Status

Accepted at `2026-07-13T12:35:08Z` after prerequisite S6A2 catalog source rebind `0e052c7`. This is
the pure projection sub-slice of Task 6.5; it does not complete Task 6.5 until a separate persistence
slice is Accepted. Merged specification/code review has zero open Critical/Important findings.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.5`
- Depends on: Accepted aggregate S5, Task 6.1 relationship catalog, Task 6.3 typed domain
  projections at `6ce1837`, and Task 6.4 strict RED at `f1caaea`

## Goal

Implement one package-internal deep module that turns retained, catalog-bound relationship inputs
into deterministic admitted/rejected outcomes and current canonical relationship projections while
preserving endpoint, assertion, decision, evidence, role, state, and temporal continuity.

## Non-goals

- Relationship persistence, migrations, release publication, retrieval/path eligibility, Milvus,
  providers, admin/UI, or product/data/index cutover.
- Catalog, aggregate S5 contract, or Task 6.3 typed projection changes.
- Derived/session relation computation or promotion to canonical facts.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/relationship_projection.py`
- `apps/miroflow-agent/tests/canonical_v2/test_relationship_projection_contract.py`
- This slice contract and Task 6.5 verification/status artifacts after GREEN.

## Forbidden changes

- Shared contracts, catalog content/builder/validator, domain projection implementation/models,
  migrations, PostgreSQL adapters, schemas, original `pgtest`, Milvus, or recovery artifacts.
- New public `KnowledgeBuild` methods or caller-visible orchestration.
- Reading `.agents` paths from product code or accepting caller-supplied source-potential labels.

## Expected unchanged behavior

- Tasks 5.1-5.7 and 6.1-6.4/6.6 Accepted contracts remain green.
- Date-only and timezone-aware instant validity retain their exact S5G shapes.
- Four-domain typed projections remain content-bound and immutable.
- Rejected, unresolved, superseded, absent, insufficient-evidence, derived, and session inputs do not
  fabricate current canonical relationships.

## Implementation slices

1. Define immutable request/result models and validate installed catalog identity plus retained input
   uniqueness and referential closure.
2. Validate typed endpoints against exact Task 6.3 projection roots/subobjects, then enforce catalog
   direction, role, state, temporal, and evidence-kind constraints.
3. Preserve shared canonical assertion/decision continuity for four-domain roots and typed retained
   continuity for registry/subobject/lineage endpoints; project only accepted current outcomes.
4. Remove the nine strict xfail markers only after their complete scenario groups pass.

## Required checks

- Focused Task 6.4 contract: nine scenario groups pass with no xfail/XPASS.
- Accepted Task 6.1 catalog/shared-contract baseline remains green.
- Full `tests/canonical_v2` no-external-dependency suite passes with only Task 6.6's five expected
  xfails.
- Ruff format/check and app-environment Pyright pass for changed Python files.
- `openspec validate rebuild-canonical-v2-knowledge-platform --strict`, `git diff --check`, scope,
  secret, and merged specification/code review pass.

## Evidence to update

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- `openspec/change-ledger.md`
- `.agents/portfolio.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`

## Stop conditions

- GREEN requires new semantics absent from OpenSpec or the Accepted catalog/RED contract.
- Correctness requires changing a shared/public contract, Task 6.3 projection shape, persistence,
  schema, migration, retrieval, or release behavior.
- A typed endpoint cannot be proven against the supplied content-bound domain projection registry.
- Verification exposes an unrelated Accepted-slice regression or ambiguous expected behavior.

## Done means

- All nine relationship scenario groups pass through `RelationshipProjection.project(...)`.
- The module has one behavior interface; catalog loading, input closure, validation, and deterministic
  projection remain implementation details.
- Task 6.5 has exact GREEN/static/full-suite evidence, zero open Critical/Important review findings,
  and an independent local Accepted commit.

## Rollback note

Revert the independent Task 6.5 commit; no database, index, release pointer, or external state is
mutated by this slice.
