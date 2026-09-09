# Slice Contract: s6r4-technology-relationship-green

## Status

Accepted at `2026-07-13T22:30:44Z` after the implementation, pure/full regression, real disposable
PostgreSQL, static, scope, and three independent review gates reached zero open Critical/Important
findings. No S7 work started; S6R5 aggregate S6 reacceptance is now Ready.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.10` (Technology/reference-relationship increment)
- Depends on: Accepted S6R3 Person reference projection

## Goal

Complete internal Technology concept/route projections and integrate resolved Person/Technology
endpoints into relationship projection through an explicit internal-reference registry, with exact
version coexistence and no Product-capability entailment.

## Non-goals

- No internal projection persistence, Milvus/public lookup builder, query planning, Industry Brief
  rendering, provider call, active pointer, or cutover.
- No new public domain or canonical Product-capability relation.

## Allowed scope

- `internal_reference_projection.py`, catalog loader/types, `relationship_projection.py`, and
  `relationship_projection_postgres.py` only for exact catalog `(id, version)` compatibility.
- Focused internal-reference, relationship, PostgreSQL-adapter, domain/path negative tests.
- No migration unless an independently reviewed stop/re-plan proves existing storage cannot retain
  exact versions; any approved migration would be new reversible `C2_0011`.

## Forbidden changes

- Historical migrations/catalog evidence, public inclusion/path domains, S7+ code, internal
  projection persistence by default, database/index/product writes, unchecked registry endpoints,
  Industry Brief as canonical, or Product capability inference.

## Expected unchanged behavior

- Four-domain projections remain the only public roots and their Accepted S6 tests stay GREEN.
- Existing relationship decisions/versions remain replayable and coexist with new versions.
- Internal reference projections are pure candidate-build outputs until S7 publishes auxiliaries.

## Required implementation effects

- TechnologyConcept/TechnologyRoute projections retain aliases, definitions, hierarchy, scope,
  source/time/release/content lineage and reject unresolved terms as canonical identities.
- Relations distinguish non-adoption discussion-or-mention, claimed adoption, and demonstrated use
  for allowed Company/Product/Paper/Patent endpoints.
- Relationship requests receive domain and internal-reference registries separately. Resolved
  internal endpoints validate against the latter; unresolved/unchecked registry values cannot become
  canonical relationship endpoints.
- Durable relationship catalog checks use exact `(relationship_type_id, version)` and permit old/new
  versions to coexist without conflict.
- Product-to-Technology evidence never creates or entails Product capability; Industry Brief is
  absent from canonical/reference projections.

## Required checks

- Observe applicable S6R1 RED groups fail before implementation and pass after minimal code.
- Focused Technology/reference and relationship pure suites; exact-version sibling matrix.
- Focused real disposable PostgreSQL relationship-adapter suite if adapter code changes, with
  explicit target identity, base unchanged, owned cleanup, and no migration rewrite.
- Complete four-domain/path/Product-capability negative tests, Ruff, Pyright, strict OpenSpec,
  diff/scope/secret/cache checks.
- Independent merged spec/code-quality review and focused persistence-safety review when applicable,
  with zero open Critical/Important findings.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- This slice status and RED/GREEN/PostgreSQL evidence.
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`; mark Task 6.10
  complete only when this slice is Accepted.

## Stop conditions

- Technology semantics need a fourth adoption state or new product decision absent from OpenSpec.
- Old/new relationship versions cannot coexist without historical migration rewrite.
- Internal endpoints require public-domain inclusion/path changes, unchecked registry values, or S7
  publication/index persistence.
- Any command cannot prove an explicit disposable target before writes.

## Done means

- All remaining S6R1 RED groups are GREEN through the shared internal-reference interface and explicit
  relationship registry.
- Technology semantics/versioning and Product-capability negatives pass; applicable persistence
  compatibility is proven; zero public-domain widening occurs.
- Required checks/reviews pass, this increment is Accepted, and Task 6.10 is marked complete.

## Rollback note

Revert Technology/relationship integration and exact-version adapter changes. Remove any owned
disposable database; no candidate/index/provider rollback is required.
