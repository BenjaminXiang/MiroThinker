# Slice Contract: s6g-path-eligibility-green

## Status

Accepted at `2026-07-13T14:18:02Z`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.7`
- Depends on: Accepted Task 6.3/S6c typed projections, Task 6.5/S6E2 relationships, and Task 6.6/S6F
  path-eligibility RED.

## Goal

Implement one deterministic package-internal
`PathEligibilityEngine.evaluate(PathEligibilityRequest) -> PathEligibilityResult` seam that emits
one versioned shared `PolicyDecision` per published user path, visible soft limitations/gaps, named
path-scoped hard exclusions, and exact merged-identity redirect output without consulting or
creating a global `ready` value.

## Non-goals

- Persistence, migration, release publication, retrieval execution, Milvus/indexing, providers,
  query/answer behavior, UI/admin work, or product/data/index cutover.
- Reimplementing domain inclusion, domain projection, relationship projection, or identity
  resolution.
- Treating ordinary enrichment gaps as hard exclusions or source-potential catalog rows as built
  relationships.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/path_eligibility.py`
- `apps/miroflow-agent/tests/canonical_v2/test_path_eligibility_contract.py`
- This slice contract and Task 6.7 acceptance/verification/status artifacts after GREEN.

## Forbidden changes

- Shared contracts, the Accepted catalog, C2_0001-C2_0010, database/Milvus/provider state, release
  pointers, or public build/read/answer/publication interfaces.
- A compatibility `ready` field, query-time identity mutation, reversed canonical relationship
  storage, global broken-reference poisoning, or a current projection for a merged predecessor.

## Expected unchanged behavior

- Inclusion remains a separate shared `PolicyDecision` with `path=None`.
- Task 6.3 projection and Task 6.5 relationship inputs remain immutable typed evidence.
- Paper domain identity status remains separate from shared canonical lifecycle state.
- Accepted Task 6.6 canonical endpoint orientation and all eight request directions remain exact.

## Required checks

- Preserve the Accepted baseline: normal Task 6.6 execution is exactly five strict xfails; forced
  RED is exactly five missing-target failures before implementation.
- During GREEN, exact-target tests fail for real missing/incorrect interface behavior; after
  removing only obsolete RED wrappers, all five scenario families pass.
- Add integrity coverage for release/policy/subject/path/evidence continuity, relationship
  orientation, redirect topology, duplicate inputs, and unsupported published paths discovered
  during review.
- Focused tests, full no-external Canonical V2, catalog/shared baseline, Ruff, Pyright, strict
  OpenSpec, diff/scope/secret, and merged specification/code-quality review pass.

## Evidence to update

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- `openspec/change-ledger.md`
- `.agents/portfolio.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`

## Stop conditions

- Correct behavior requires changing the Accepted catalog, shared `PolicyDecision`, Task 6.3/6.5
  output semantics, storage schema, public interface, or product retrieval policy not stated in the
  active OpenSpec/RED contract.
- One path cannot be evaluated without a global readiness decision, ordinary quality must become a
  hard exclusion, or merge resolution cannot identify exactly one existing survivor.

## Done means

- Five Task 6.6 scenarios are GREEN through one deep module; each published path has one versioned,
  evidence-bound decision; limitations/gaps and hard exclusions remain distinct; all eight
  traversals and merge redirect are exact; review has zero open Critical/Important findings; Task
  6.7 and its acceptance criteria are checked in one independent Accepted commit.

## Rollback note

Revert the independent slice commit. No migration, database, release, or index rollback is needed.
