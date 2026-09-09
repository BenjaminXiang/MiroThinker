# Slice Contract: s7c-candidate-projection-green

## Status

Accepted at `2026-07-14T06:57:15Z`. The focused RED/GREEN cycle, complete regression/static/package/
safety gates, and one independent review passed with zero Critical/Important findings. Task 7.4 is
the next Ready critical-path slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `7.3`
- Depends on: Accepted S6R/Tasks 6.9-6.11 and Accepted S7B/Task 7.2

## Goal

Compose one pure, release-scoped typed projection bundle from the exact replayable four-domain and
internal Person/Technology S6R results. Produce owner-local deterministic manifests for exactly four
public populations and three internal auxiliary populations without receiving or changing active
release pointers.

## Non-goals

- No Task 7.4 index RED, `IndexProjectionManifest`, Professor identity/research index split, or
  missing/extra/stale/cross-release point matrix.
- No Task 7.5 lookup/vector chunks, embedding, Milvus/public lookup builder, full index rebuild, or
  complete `KnowledgeBuild` materializer wiring.
- No Task 7.6 parity, authorization, publication, promotion, rollback, or active-pointer adapter.
- No relationship/path-eligibility recomputation, `ManifestSection`, PostgreSQL migration/durable
  adapter, provider, Industry Brief, Product-capability fact, commit, push, PR, archive, or cutover.

## Allowed scope

- New `apps/miroflow-agent/src/data_agents/canonical_v2/candidate_projection.py`.
- Four minimal Task 7.3 RED/GREEN scenarios appended to
  `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` so they
  reuse its accepted real closed-graph fixtures without copying or extracting roughly 1,200 lines.
- This Slice Contract and Task 7.3 verification/status evidence after acceptance.

## Forbidden changes

- `contracts.py`, `knowledge_build.py`, S6 domain/internal/relationship/path implementation,
  migrations, databases, indexes, release publication, active state, or consumer-facing deep-module
  interfaces.
- Accepting content hashes without calling the existing exact
  `validate_internal_reference_projection_result(request, result)` replay validator.
- Omitting empty owner envelopes: the output must distinguish an empty population from an absent
  population by always emitting exactly seven projection manifests.
- Treating Person, Technology concept, Technology route, Product, or Industry Brief as a fifth public
  inclusion domain.

## Expected unchanged behavior

- Company, Paper, Patent, and Professor remain the complete public-domain set.
- Resolved Person and Technology records retain exact evidence/decision/source/time lineage;
  unresolved references create no projection record.
- S7B KnowledgeBuild remains Accepted and isolated; Task 7.6 ReleasePublication and future
  KnowledgeRead/KnowledgeAnswer tests remain named expected RED.

## Required checks

- Initial focused normal RED is exactly four strict xfails; forced RED is exactly four guarded
  missing-target failures for the absent `candidate_projection` module and no nested dependency.
- Final Task 7.3 focused scenarios pass and prove: complete 4+3 ownership, owner-local deterministic
  hashes/counts/versions, real Person and Technology typed records, unresolved-reference exclusion,
  exact closed-graph replay, and cross-release refusal.
- Complete internal-reference regression, S7B/Publication sibling interfaces, shared contracts, and
  complete no-external Canonical V2 pass with only the four untouched future-interface xfails.
- Ruff check/format, complete Canonical V2 Pyright, fresh import/wheel inclusion, strict OpenSpec,
  `git diff --check`, production-scope, secret, and generated-cache checks pass.
- One independent review reports zero open Critical/Important findings; Minor/YAGNI is recorded and
  nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, agent links, acceptance, and portfolio only after Task 7.3 is
  Accepted.

## Stop conditions

- GREEN requires a fabricated/placeholder index manifest, a new public product meaning, or any
  Task 7.4+ persistence/publication behavior.
- Existing S6R request/result cannot be replayed exactly, or Task 7.3 cannot enforce exactly four
  public plus three internal owners using the existing shared `ProjectionManifest`.
- A required check exposes a real Accepted-slice regression or an unresolved Critical/Important
  review finding.

## Done means

- Four real-fixture scenarios pass through the pure Task 7.3 composition seam.
- The result contains typed public/Person/Technology records plus exactly seven manifests whose
  release, scope, owner, version, count, and owner-local content hash match their records.
- Unresolved references remain upstream diagnostics and never become records; no pointer-capable or
  index/publication dependency exists.
- Required regression/static/strict/package/review checks pass, evidence is persisted, and Task
  7.3/S7C is Accepted with Task 7.4 selected next.

## Plan

1. Append four exact-target strict RED scenarios using `_resolved_person_graph`,
   `_technology_graph`, `_unresolved_person_graph`, and `_request`; run normal and forced RED.
2. Add one pure `compose_candidate_projections(CandidateProjectionRequest)` module with strict input
   replay, exact owner partitioning, owner-local hashes, and self-hashed typed result; no ABC,
   adapter, storage, or index placeholder.
3. Remove only the four Task 7.3 xfail markers, run focused/sibling/full/static/package/safety gates,
   obtain one independent review, and repair only Critical/Important findings.
4. Persist acceptance evidence and select Task 7.4. Commit/push/PR/cutover remain unauthorized.

## Rollback note

Delete the new pure module and revert the four owner-test and evidence/status additions. No database,
index, pointer, provider, or external state exists to roll back.

## Acceptance evidence

- Pre-implementation normal RED was exactly `4 xfailed`; forced RED was exactly four guarded
  missing-target failures for the absent `candidate_projection` module.
- Final focused Task 7.3 was `4 passed`; the complete Internal Reference contract was `28 passed`.
  The real fixtures cover four one-record public domains plus one resolved Person, one Company plus
  two Technology concepts/one route, and two unresolved same-name Person references that create no
  Person population.
- An owner-local mutation scenario keeps all four public manifest hashes byte-identical when only a
  Technology route becomes unresolved, while the route count/hash and complete bundle hash change.
  Cross-release input and a tampered closed result fail before any output exists.
- KnowledgeBuild plus ReleasePublication remained `3 passed, 2 expected xfailed`; shared contracts
  were `16 passed`; complete no-external Canonical V2 was `272 passed, 139 skipped, 4 expected
  xfailed`, exactly KnowledgeRead, KnowledgeAnswer, and two Task 7.6 cases.
- Focused Ruff check/format passed; complete Canonical V2 Pyright returned `0 errors, 0 warnings, 0
  informations`. A fresh 268-entry wheel includes `candidate_projection.py` and
  `knowledge_build.py` with no `.agents` entry. Strict OpenSpec, `git diff --check`, scope, secret,
  and generated-cache checks passed.
- Independent review returned Accept with zero Critical, zero Important, and zero Minor. Task
  7.4-7.6 index/lookup/publication work is correctly deferred YAGNI and does not block acceptance.
- No new Release/Milvus acceptance checkbox closes yet: Task 7.4/7.5 still own Professor index
  semantics and actual lookup/vector projections. Task 7.3 is Accepted at 42/80 and Task 7.4 is
  Ready. No database, index, pointer, provider, commit, push, PR, archive, publication, or cutover
  write occurred.
