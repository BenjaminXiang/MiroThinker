# Slice Contract: s6f-path-eligibility-red

## Status

Accepted at `2026-07-12T17:22:49Z` against Accepted Task 6.1 commit `e6e6403`.
The five exact-target RED scenario families, one merged specification/code-quality review, and
focused test-only checkpoint are closed with zero open Critical or Important findings. This slice
does not implement or claim the future Task 6.3 typed projections, Task 6.5 accepted relationship
decisions, or Task 6.7 path-eligibility policy.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.6`
- Depends on: Accepted Task 6.1 at commit `e6e6403`

## Goal

Define five observable scenario families through one future package-internal seam:
`PathEligibilityEngine.evaluate(PathEligibilityRequest) -> PathEligibilityResult`. The request
explicitly consumes a future Task 6.3 typed current projection and inclusion decision plus future
Task 6.5 relationship decisions; the RED fixtures describe those inputs without implementing them.
Projection fixtures keep shared canonical lifecycle state separate from Paper-domain
`identity_status`.

## Published user paths

The complete Task 6.6 user-path registry is:

- `exact_lookup`
- `structured_filter`
- `verified_relationship_traversal`
- `semantic_recall`
- `recommendation`
- `ranking`

`audit_lineage`, `identity_resolution`, and other catalog-internal paths are not published user
paths and cannot satisfy this registry.

## Required scenarios

1. Partial but source-grounded Professor, Company, Paper, and Patent projections remain reachable
   by exact lookup with visible limitations.
2. Accepted relationships keep their Task 6.1 catalog source/target orientation while remaining
   traversable in all eight frozen cross-domain request directions when ordinary endpoint
   enrichment is incomplete. A rejected Professor-Paper attribution blocks only that traversal;
   the independently valid Paper remains exactly reachable.
3. Missing enrichment, partial summaries, ordinary uncertainty, and stale non-material facts are
   soft quality signals, never unnamed hard exclusions.
4. Every published path honors applicable named hard invariants. `broken_reference` excludes only
   paths that depend on that reference. A request for a merged predecessor consumes its identity
   redirect plus only the survivor's current projection/inclusion and returns one eligible survivor.
5. Inclusion and all six named path decisions remain independent; each path decision carries its
   applicable path-eligibility policy version and does not consume one legacy global `ready` value.

## Allowed scope

- `apps/miroflow-agent/tests/canonical_v2/test_path_eligibility_contract.py`
- This slice contract.

## Forbidden changes

- Any file under `apps/miroflow-agent/src/`, shared contracts, migrations, or the frozen Task 6.1
  catalog.
- OpenSpec task/evidence status, database, Milvus, provider, source, candidate, or runtime changes.
- A local fake eligibility result or assertions against SQL, tables, collections, or internal call
  order.

## Required checks

- Observe each scenario failing for the exact absent
  `src.data_agents.canonical_v2.path_eligibility` module before retaining the next scenario.
- Focused normal pytest reports exactly five strict xfails.
- Focused `--runxfail` reports exactly five `_MissingTargetModule` failures directly caused by the
  exact absent target; nested missing dependencies fail normally.
- Focused Ruff and Pyright pass.

## Stop conditions

- A scenario invents a Task 6.3 projection or Task 6.5 relationship implementation instead of
  declaring it as future input.
- A source-potential catalog outcome is treated as a built relationship.
- Ordinary incompleteness becomes a hard exclusion; attribution rejection rejects Paper existence;
  a canonical edge reverses its registered endpoints; `broken_reference` globally poisons unrelated
  paths; or a merged identity receives a current projection/admitted inclusion instead of resolving
  through survivor lineage.
- Correct RED requires production/shared/migration/catalog/database/provider changes.

## Done means

Five strict RED scenarios express Task 6.6 through the future seam; normal and forced RED shapes and
focused static checks are exact. Task 6.6 is Accepted when the integrator records its task and
verification evidence; Tasks 6.3, 6.5, and 6.7 remain separate GREEN owners.

## Acceptance checkpoint

- Five strict scenarios cover four-domain partial exact reach, all eight registered cross-domain
  traversal directions, ordinary soft-quality signals, path-scoped named hard exclusions, merged-ID
  survivor redirect, and six-path independence from global `ready`.
- Shared canonical lifecycle state remains separate from Paper `identity_status`. Accepted
  relationship fixtures preserve catalog source/target orientation even for inverse user traversal;
  rejected Professor-Paper attribution blocks only that traversal and not Paper exact lookup.
- `broken_reference` affects only paths using the broken reference. Wrong identity, terminal
  rejection, unsafe exposure, and no usable source-grounded facts carry evidence-bound named
  exclusions. A merged predecessor has no current projection or admitted inclusion and resolves to
  exactly one survivor through a shared identity decision.
- The one merged review initially found five Important semantic defects: state conflation, reversed
  canonical edges, global broken-reference poisoning, a false merged current projection, and
  attribution/identity coupling. The same review closed all five; final status has no open Critical
  or Important findings.
- Focused normal pytest reports exactly `5 xfailed`; forced RED reports exactly five direct
  `_MissingTargetModule` failures for `src.data_agents.canonical_v2.path_eligibility`. Ruff
  check/format, Pyright, Accepted Task 6.1 catalog/shared contracts, strict OpenSpec, and diff/scope
  checks pass at integration checkpoint.
- No production/shared-contract/migration/database/source/Candidate/Milvus/provider/runtime state
  changed. The tests declare future Task 6.3/6.5 outputs as typed inputs without implementing them.
