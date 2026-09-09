# Slice Contract: s6a2-catalog-source-rebind

## Status

Accepted at `2026-07-13T10:49:49Z`. The full source-binding and semantic-invariance matrix is green,
and merged specification/code review has zero open Critical/Important findings.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Corrective dependency of: Task 6.5 / S6E
- Root cause commit: Accepted S5G `5771abf`

## Goal

Rebind the frozen Task 6.1 catalog to the current Accepted OpenSpec authority bytes after S5G added
temporal-precision requirements to the design and canonical-knowledge spec, while proving that all
catalog semantics and every other authority binding remain unchanged.

## Non-goals

- Relationship type, field, subobject, scenario, citation, policy, or product behavior changes.
- Relationship projection/persistence implementation, migrations, database/index writes, release
  publication, or cutover.

## Allowed scope

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s6/domain-catalog-v1.json`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s6/build_domain_catalog.py` (authority
  identity constant only; no builder logic change)
- `apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/domain-catalog-v1.json`
- `apps/miroflow-agent/src/data_agents/canonical_v2/domain_catalog.py`
- `apps/miroflow-agent/tests/canonical_v2/test_relationship_projection_contract.py`
- This slice contract plus current-run verification/change-log evidence.

## Forbidden changes

- Catalog builder logic, validator/test semantics, authority content, source citations/ranges/terms,
  relationship/domain catalog rows, shared contracts, domain projections, migrations, or adapters.
- Weakening full-file SHA validation or excluding the two S5G-updated authority files.

## Expected unchanged behavior

- Exactly 14 authority sources remain bound; only the two S5G-edited source SHA values change.
- Catalog semantics remain 9 shared fields, 101 domain fields, 28 subobjects, 7 families, 34
  relationship types, 42 scenarios, 8 traversal directions, and 5 deferred owners.
- Review and packaged catalog JSON remain byte-identical.

## Required checks

- Pre-fix sibling scan reports exactly the two S5G authority drifts.
- Deterministic builder `--write` then `--check` succeeds without changing semantic catalog rows.
- Eight catalog tests plus sixteen shared-contract tests pass (`24 passed`).
- Review/runtime JSON are byte-identical; installed catalog imports with the new content/file hashes.
- Post-fix all-14-source sibling scan is empty.
- Ruff/Pyright for changed Python, strict OpenSpec, diff/scope/secret checks pass.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

## Stop conditions

- Rebuild changes any semantic catalog row, citation, source count, scenario count, or layer owner.
- More than the two known S5G authority hashes drift.
- A fix would weaken provenance validation or require a behavior/schema/database change.

## Done means

- The complete content-addressed catalog set binds the current Accepted authority bytes.
- The regression matrix is green, no semantic drift exists, and the corrective slice has an
  independent local commit.

## Rollback note

Revert the independent corrective commit. No external or database state changes.
