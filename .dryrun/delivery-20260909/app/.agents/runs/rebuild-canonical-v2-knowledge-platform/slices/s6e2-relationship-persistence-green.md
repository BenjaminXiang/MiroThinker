# Slice Contract: s6e2-relationship-persistence-green

## Status

Accepted at `2026-07-13T13:54:12Z`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.5`
- Depends on: S6A2 catalog rebind `0e052c7` and Accepted pure relationship projection S6E
  `1702bdf`

## Goal

Persist and exactly reconstruct one validated relationship projection batch on an explicitly owned
disposable PostgreSQL target. Reuse the existing Canonical V2 shared relationship ledgers for
both-canonical assertions/decisions; add only the typed-endpoint, projection-run, candidate-outcome,
and unified-current surfaces that C2_0002-C2_0009 cannot represent.

## Non-goals

- Changing the Task 6.1 catalog, pure relationship semantics, domain projections, identity
  resolution, path eligibility, release publication, retrieval, Milvus, provider, admin/UI, or
  product/data/index cutover.
- Duplicating shared `relationship_assertion` or `relationship_decision` rows in a new generic table.
- Writing the base disposable database, original `pgtest`, original Milvus, or recovery artifacts.

## Allowed scope

- `apps/miroflow-agent/canonical_v2_alembic/versions/C2_0010_relationship_projections.py`
- `apps/miroflow-agent/src/data_agents/canonical_v2/relationship_projection.py` (content identity
  and persistence-facing invariants only)
- `apps/miroflow-agent/src/data_agents/canonical_v2/relationship_projection_postgres.py`
- `apps/miroflow-agent/tests/canonical_v2/test_relationship_projection_postgres.py`
- Narrow migration head/schema inventory expectations made stale by C2_0010.
- This slice contract and Task 6.5 acceptance/verification/status artifacts after GREEN.

## Forbidden changes

- Historical migration rewrites, existing shared relationship table replacement, catalog/domain
  schema changes, destructive fallback DSNs, environment-derived write targets, or active-release
  mutation.
- Weakening append-only, replay, content-hash, FK, temporal precision, candidate-release, backup
  gate, database marker, or direct-SQL integrity checks.

## Expected unchanged behavior

- Shared four-domain source assertions and decisions remain in the existing normalized C2 ledgers.
- Registry/subobject/lineage endpoints remain typed JSON references and never receive fabricated
  canonical identity IDs.
- Date-only validity remains JSON precision-bearing; legacy timestamp columns are used only for
  instant values where the existing shared ledger requires them.
- S6E pure projection, S6c domain projections, aggregate S5, and the 24-test catalog baseline remain
  unchanged and green.

## Migration / adapter contract

- C2_0010 is the sole descendant of C2_0009 and is reversible only while its new projection tables
  are empty; it never rewrites C2_0001-C2_0009.
- New append-only tables retain one projection run/result manifest, typed assertions, typed
  decisions, per-candidate outcomes, and one unified current relationship surface. Shared rows are
  linked to the existing ledgers, not copied into typed tables.
- Candidate-release triggers cover new release-scoped rows and existing relationship decisions/
  decision-assertion edges; post-active direct SQL inserts fail.
- `RelationshipProjectionStore.persist(request, result)` reprojects and requires exact equality,
  validates release/source/canonical/domain endpoint ownership, inserts atomically, and returns the
  exact durable reconstruction. `load(release_id, projection_run_id)` validates result hash,
  membership counts/fingerprints, and normalized ledgers before returning.
- Exact replay is a no-op; same release/run with changed content fails and rolls back. Concurrent
  exact replay converges under one advisory lock.

## Required checks

- Pure RED first: exact target adapter/migration absent or persistence contract fails for the named
  reason; no local fake may satisfy it.
- Real owned sibling database upgraded C2_0009 -> C2_0010: shared + typed batch round-trips exactly,
  restart load equals input, exact replay is unchanged, changed replay conflicts atomically, and
  rejected/non-current outcomes never appear in current rows.
- Real DB negative matrix: wrong database marker/expected name/target kind/backup gate, non-candidate
  release, dangling shared assignment/source record, dangling typed subobject where applicable,
  direct SQL post-active insert, update/delete/truncate, and downgrade with data fail closed.
- Fresh upgrade and empty downgrade/upgrade cycle pass; one linear Alembic head is C2_0010.
- Focused pure + PostgreSQL tests, full no-external Canonical V2, catalog/shared baseline, Ruff,
  Pyright, strict OpenSpec, diff/scope/secret, and merged specification/migration-safety review pass.

## Evidence to update

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- `openspec/change-ledger.md`
- `.agents/portfolio.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`

## Stop conditions

- Correct persistence requires changing the Accepted relationship catalog/pure behavior, public
  `KnowledgeBuild`, Task 6.3 domain models, or existing historical migration semantics.
- Shared rows can only be persisted by duplicating rather than using the existing ledger.
- A typed endpoint cannot retain exact reference kind/parent/lineage/evidence content.
- Target ownership or accepted backup evidence cannot be proved before the first write.
- Migration or replay verification exposes ambiguous behavior not fixed by OpenSpec/S5/S6 contracts.

## Done means

- Pure and real-PostgreSQL relationship projection surfaces round-trip exactly with restart,
  replay, transaction, append-only, candidate-release, temporal, and endpoint integrity evidence.
- Task 6.5 and canonical relationship acceptance items are checked with current evidence; merged
  review has zero open Critical/Important findings; an independent local Accepted commit exists.

## Rollback note

Before Accepted data exists, downgrade the owned disposable sibling to C2_0009. Otherwise revert the
slice commit and discard only the owned sibling; no active/original target is modified.
