# Slice Contract: s7a-release-lifecycle-red

## Status

Accepted at `2026-07-14T02:39:06Z` after exact normal/forced RED, regression, static, strict, and
independent-review checks passed. Task 7.2 is Ready; no S7 implementation has started.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `7.1`
- Depends on: Accepted S6R1-S6R5 and historical Aggregate S6

## Goal

Freeze the smallest observable RED contract for the already-specified `KnowledgeBuild.build(...)`
and `ReleasePublication.verify/promote/rollback(...)` seams: isolated failed candidates, immutable
deterministic manifests with public/auxiliary projection hashes, parity-mismatch refusal, one-release
atomic promotion, and auditable rollback.

## Non-goals

- No `KnowledgeBuild` or `ReleasePublication` implementation.
- No PostgreSQL schema/migration, canonical/published projection, Milvus collection/index, active
  pointer/alias, provider, candidate-data, commit, push, PR, archive, or cutover write.
- No Task 7.2+ implementation and no S8/S9 behavior.

## Allowed scope

- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_interface.py`.
- `apps/miroflow-agent/tests/canonical_v2/test_release_publication_interface.py`.
- This Slice Contract plus Task 7.1 RED verification/evidence/status artifacts.
- Shared-contract reads only; shared production contracts may not change in this RED slice.

## Forbidden changes

- New external method beyond the design-frozen `build`, `verify`, `promote`, and `rollback` methods;
  package-internal ephemeral composition factories may wire fixture adapters to the same real code
  path but are not consumer-facing product seams.
- Product semantics, public-domain/reference scope, release schema, persistence, candidate/index state,
  or active release state.
- Weakening strict xfail masking or treating a typo/nested missing dependency as the expected RED.

## Expected unchanged behavior

- S6R remains Accepted with four public domains, internal Person/Technology auxiliaries, and no
  canonical Product-capability relationship.
- The complete no-external Canonical V2 suite continues to have no real failure; Task 7.1 adds only
  named strict future-interface xfails.
- Existing shared `BuildManifest`, `CandidateRelease`, `ReleaseVerification`, and `PublishedRelease`
  models remain immutable and unchanged.

## Required checks

- Focused normal RED reports exactly five strict xfails across the two release-interface files.
- Focused forced RED reports exactly five guarded missing-target sentinels caused by the two exact
  absent target modules and no unrelated or nested-dependency failure.
- Existing shared/release contract controls pass.
- Complete no-external Canonical V2 has no real failure; only named future-interface xfails remain.
- Ruff check/format, Pyright, strict OpenSpec, `git diff --check`, production-scope, secret, and
  generated-cache checks pass.
- Independent review reports zero open Critical/Important findings.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, agent links, and portfolio only if Task 7.1 becomes Accepted.

## Stop conditions

- The tests require a new product meaning or public interface not already frozen in design/OpenSpec.
- RED masking accepts an unrelated error, or a forced RED does not fail for the exact absent target
  module.
- Any implementation, database/index/pointer write, or Critical/Important review finding appears.

## Done means

- Task 7.1's six named behaviors are represented by five minimal observable strict RED scenarios.
- Normal and forced RED evidence, regression/static/strict checks, and independent review pass.
- The RED slice is Accepted without claiming Task 7.2+ implementation; S7B/Task 7.2 becomes Ready.

## Rollback note

Revert the two test-file additions and this evidence/status update. No runtime or external state
exists to roll back.

## Acceptance evidence

- Normal focused RED: exactly `5 xfailed`, each named Task 7.1 and guarded by an exact target-module
  sentinel.
- Forced RED: expected exit 1 with exactly five failures caused by absent `knowledge_build` or
  `release_publication`; nested missing dependencies cannot be masked.
- Shared manifest/release controls: `16 passed`.
- Complete no-external Canonical V2: `265 passed, 139 skipped, 7 expected xfailed`; five are the
  Task 7.1 release REDs and two remain the future KnowledgeRead/KnowledgeAnswer interfaces.
- Ruff check/format passed for both owner files; Pyright returned `0 errors, 0 warnings, 0
  informations`. Strict OpenSpec, `git diff --check`, scope, generated-cache, and high-confidence
  secret checks passed.
- Initial review found two Important false-GREEN/masking defects; re-review then found one Important
  missing intermediate promotion-state assertion. All three were repaired. Final review returned
  `Ready` with zero Critical, zero Important, and one nonblocking representative-coverage Minor.
- The Minor is intentionally deferred: this RED uses Company/Person and extra-point representatives;
  Tasks 7.3/7.4 own the full public/Person/Technology and missing/extra/stale/cross-release matrices.
