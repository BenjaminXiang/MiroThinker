# Slice Contract: s7b-knowledge-build-green

## Status

Accepted at `2026-07-14T06:00:15Z`. The exact KnowledgeBuild RED was reconfirmed before
implementation, the three owner scenarios are GREEN, all Required checks pass, and the independent
review reports zero Critical/Important findings. Task 7.3 is the next Ready critical-path slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `7.2`
- Depends on: Accepted S7A/Task 7.1 and Accepted S6R1-S6R5

## Goal

Implement the smallest deep `KnowledgeBuild` module that composes already-materialized,
release-scoped sections into one deterministic immutable `BuildManifest` and isolated
`CandidateRelease` without changing any active release pointer.

## Non-goals

- No Task 7.3 public-domain or internal Person/Technology projection production.
- No Task 7.4/7.5 canonical or Milvus index build, parity matrix, or provider integration.
- No Task 7.6 `ReleasePublication`, verification, promotion, rollback, or pointer write.
- No PostgreSQL schema/migration, durable adapter, commit, push, PR, archive, or cutover.

## Allowed scope

- New `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build.py`.
- Existing `apps/miroflow-agent/tests/canonical_v2/test_knowledge_build_interface.py` only for
  Task 7.2 GREEN and narrowly necessary immutable/collision/atomicity regression assertions.
- This Slice Contract and Task 7.2 verification/status evidence after acceptance.

## Forbidden changes

- Any consumer-facing method beyond `KnowledgeBuild.build(BuildCandidateRequest) ->
  CandidateRelease`; a package-internal ephemeral composition factory may inject test adapters.
- New release/publication module, repository port, database/index adapter, active-pointer method, or
  duplicate shared manifest/candidate type.
- Any change to shared Canonical V2 contracts unless an observed blocker makes the existing Task 7.2
  contract impossible; stop and re-plan instead.
- Weakening the two Task 7.6 ReleasePublication strict xfails or future KnowledgeRead/KnowledgeAnswer
  REDs.

## Expected unchanged behavior

- S6R remains Accepted with four public domains plus internal Person/Technology auxiliaries.
- Candidate construction remains isolated: active canonical, published-projection, and index release
  identifiers are byte-for-byte unchanged on success and failure.
- Task 7.6 ReleasePublication scenarios remain named expected RED; no external state is written.

## Required checks

- Exact forced KnowledgeBuild RED initially fails for the absent target module, then all three owner
  scenarios pass after implementation.
- KnowledgeBuild plus ReleasePublication reports three passed and two named expected xfails.
- Shared release/manifest contract controls and relevant sibling release tests pass.
- Complete no-external Canonical V2 has no real failure and exactly the untouched future-interface
  xfails remain.
- Ruff check/format, Pyright, strict OpenSpec, `git diff --check`, production-scope, secret, and
  generated-cache checks pass.
- One independent review reports zero open Critical/Important findings; Minor/YAGNI is recorded and
  nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, agent links, and portfolio only after Task 7.2 is Accepted.

## Stop conditions

- GREEN requires Task 7.3 projection production, Task 7.4/7.5 indexing, Task 7.6 publication, or a
  new public product meaning.
- Candidate/manifest construction cannot be made deterministic, deeply immutable, collision-safe,
  and all-or-nothing within the existing shared contracts.
- A required check exposes a real S6R regression or an unresolved Critical/Important review finding.

## Done means

- The three S7A KnowledgeBuild scenarios are GREEN through the real `KnowledgeBuild.build` path.
- The manifest binds all named inputs and complete materialized release sections; nested version and
  count maps produced by this module reject mutation without changing shared field types.
- Failures stay inspectable/retryable, partial candidates are not published, and same-ID conflicts
  cannot overwrite immutable stores.
- Required regression/static/strict checks and independent review pass, evidence is persisted, and
  Task 7.2/S7B is Accepted with Task 7.3 selected next.

## Rollback note

Delete the new module and revert the owner-test and evidence/status additions. No database, index,
pointer, provider, or external state exists to roll back.

## Acceptance evidence

- Pre-implementation normal RED was exactly `3 xfailed`; forced RED was exactly three guarded
  missing-target failures for the absent `knowledge_build` module.
- Final KnowledgeBuild owner verification was `3 passed`; KnowledgeBuild plus ReleasePublication
  was `3 passed, 2 expected xfailed`, with both xfails still owned by Task 7.6.
- Shared contracts were `16 passed`; complete no-external Canonical V2 was `268 passed, 139 skipped,
  4 expected xfailed`, exactly KnowledgeRead, KnowledgeAnswer, and two ReleasePublication cases.
- Focused Ruff check/format passed; complete Canonical V2 Pyright returned `0 errors, 0 warnings, 0
  informations`. Strict OpenSpec, `git diff --check`, scope, secret, and generated-cache checks
  passed.
- A fresh 267-entry wheel contains `knowledge_build.py` and no `.agents` entry. No PostgreSQL,
  Milvus, provider, candidate-data, or active-pointer resource was used.
- Independent review returned zero Critical, zero Important, zero Minor, and one nonblocking YAGNI:
  durable transaction/failure-receipt design remains owned by a future durable adapter slice.
- Task 7.2 is Accepted at 41/80. Task 7.3 is Ready. No commit, push, PR, archive, publication, or
  cutover occurred.
