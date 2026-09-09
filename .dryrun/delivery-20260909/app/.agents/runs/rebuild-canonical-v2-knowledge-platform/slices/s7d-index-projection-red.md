# Slice Contract: s7d-index-projection-red

## Status

Accepted at `2026-07-14T08:11:49Z`. All exact RED, regression, static, strict, package, safety, and
independent-review gates passed with zero open Critical/Important findings. Task 7.5 is Ready; no
index or publication implementation exists.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `7.4`
- Depends on: Accepted S6R/Tasks 6.9-6.11 and Accepted S7C/Task 7.3

## Goal

Freeze the smallest observable contract for release-scoped vector/index projections before their
Task 7.5 implementation: exact candidate and path-eligibility binding, point-level release/object/
content/version metadata, derived full-rebuild admission, typed Professor identity/research intent,
repairable missing/extra/stale/cross-release discrepancies, and evidence-anchored internal Person/
Technology auxiliaries that create no fifth public domain.

## Non-goals

- No `index_projection.py`, `ReleasePublication`, Milvus/public-lookup builder, embedding/provider,
  physical collection, database/index/pointer, authorization, promotion, rollback, commit, push, PR,
  archive, or cutover implementation.
- No vector dimension, exact text serialization, fixed collection name, legacy payload compatibility,
  ordinary incremental optimization, or durable adapter contract.
- No Task 7.5-7.7 GREEN or Release/Milvus acceptance checkbox.

## Allowed scope

- Three strict RED scenarios appended to
  `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`, reusing
  its accepted real Person/Technology closed-graph fixtures.
- One point-level parity RED scenario appended to
  `apps/miroflow-agent/tests/canonical_v2/test_release_publication_interface.py`; existing release
  RED fixtures may receive typed expected/actual point inventories where needed to remove aggregate-
  manifest ambiguity.
- This Slice Contract and Task 7.4 verification/status evidence after acceptance.
- Production Canonical V2 modules and shared contracts are read-only in this RED slice.

## Forbidden changes

- A production index module or local fake comparator that makes any Task 7.4 scenario GREEN.
- A public fifth-domain path-eligibility input for Person or Technology; their admission must remain
  internal, release-scoped, resolved, and anchored to accepted public-domain evidence.
- Caller-controlled `full_rebuild=True` as proof. Initial, schema-changing, embedding-changing, and
  path-policy-changing releases must derive their full-rebuild requirement from prior/current
  version snapshots.
- Professor intent inferred from a physical collection name or by parsing a projection ID.
- Aggregate-only parity counters without point/object/projection/release/version/content repair
  evidence.

## Expected unchanged behavior

- Company, Paper, Patent, and Professor remain the complete public-domain set.
- S7C continues to emit exactly four public plus three internal candidate projection populations
  without active-pointer access.
- S7B KnowledgeBuild remains isolated; the existing Task 7.6 ReleasePublication and future
  KnowledgeRead/KnowledgeAnswer tests remain named expected RED.
- No external database, index, provider, or active release state changes.

## Required checks

- The four selected Task 7.4 scenarios report exactly four strict xfails: three exact absent
  `index_projection` targets and one exact absent `release_publication` target.
- Forced RED reports exactly four failures caused by those exact missing target modules; a typo,
  nested missing dependency, or unrelated exception is not masked.
- The complete two owner files report `28 passed, 6 xfailed` before Task 7.5.
- Shared manifest/release controls pass, and the complete no-external Canonical V2 suite has no real
  failure with only eight named future-interface xfails.
- Ruff check/format, complete Canonical V2 Pyright, strict OpenSpec, `git diff --check`, production-
  scope, secret, generated-cache, and package-content checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI is recorded and
  nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, agent links, code-grounded plan, and portfolio only after
  Task 7.4 becomes Accepted.

## Stop conditions

- A test requires a new product meaning, consumer-facing deep module, public fifth domain, or shared
  contract change not already frozen by OpenSpec.
- RED masking accepts an unrelated failure, or a point defect cannot be classified exclusively from
  typed expected/actual inventories.
- Any implementation/external write or unresolved Critical/Important review finding appears.

## Done means

- Four minimal strict RED scenarios cover all named Task 7.4 obligations without implementing them.
- Public path eligibility is replayable and typed; internal auxiliary admission is separately
  evidence-anchored; Professor intent is typed; rebuild reasons are derived; parity details are
  point-level and repairable.
- Required RED/regression/static/strict/package/safety/review checks pass and Task 7.4/S7D is
  Accepted with Task 7.5 selected next.

## Plan

1. Add exact-target sentinels and the three index-builder scenarios plus one release point-parity
   matrix; run normal and forced RED.
2. Run owner, shared, complete no-external, static, strict, package, scope, secret, and cache checks.
3. Obtain one independent review and repair only Critical/Important findings.
4. Persist acceptance evidence and select Task 7.5. Commit/push/PR/cutover remain unauthorized.

## Rollback note

Revert the four strict RED scenarios and this evidence/status update. No runtime or external state
exists to roll back.

## Acceptance evidence

- The four selected scenarios finish as exactly `4 xfailed`; forced `--runxfail` finishes as exactly
  four failures caused by three exact missing `index_projection` targets and one exact missing
  `release_publication` target. No nested dependency or unrelated exception is masked.
- The owner files finish as `28 passed, 6 xfailed`. KnowledgeBuild/ReleasePublication sibling
  interfaces finish as `3 passed, 3 xfailed`; shared contracts finish as `16 passed`.
- Complete no-external Canonical V2 finishes as `272 passed, 139 skipped, 8 xfailed`. The expected
  set is exactly three Task 7.4 index REDs, three ReleasePublication REDs, KnowledgeRead, and
  KnowledgeAnswer.
- Real accepted fixtures exercise four public records plus one internal Person, one Company plus two
  Technology concepts/one Technology route, exact CandidateProjection and PathEligibility replay,
  a real semantic-recall exclusion that removes Paper and changes its manifest, and initial/schema/
  embedding/eligibility full-rebuild admission.
- The point contract freezes exact scope/owner/object/view populations, typed Professor identity and
  research content, distinct opaque Professor projection joins, source/embedded hashes, public versus
  internal policy versions, Person/Technology public-evidence anchors, and deterministic expected/
  actual manifests. Point parity exclusively classifies missing/extra/stale/cross-release defects and
  retains exact expected/actual release/version/content repair evidence without changing pointers.
- Ruff check/format and complete Canonical V2 Pyright pass with zero findings. Strict OpenSpec,
  `git diff --check`, production-scope, high-confidence secret, and generated-cache checks pass. A
  fresh 268-entry wheel retains S7B/S7C modules, includes no `.agents`, and correctly contains no
  Task 7.4/7.6 implementation module.
- Independent review initially found five Important false-green gaps: incomplete point content
  evidence, replaceable eligible populations/Person ownership, ignored eligibility outcomes,
  collapsible Professor manifests, and manifest policy inconsistency. All were repaired. Final
  review returns zero Critical, zero Important, zero Minor, and two nonblocking YAGNI notes: do not
  split the long fixture or freeze physical collection/vector-dimension/durable-adapter details now.
- Task 7.4 is Accepted at 43/80 and Task 7.5 is Ready. Release/Milvus acceptance boxes remain open;
  no production module, database, index, pointer, provider, commit, push, PR, archive, publication,
  or cutover write occurred.
