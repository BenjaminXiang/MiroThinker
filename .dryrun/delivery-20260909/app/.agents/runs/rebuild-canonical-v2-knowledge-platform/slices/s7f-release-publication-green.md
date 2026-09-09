# Slice Contract: s7f-release-publication-green

## Status

Accepted at `2026-07-14T11:00:20Z`. S7E/Task 7.5 and every earlier S7 predecessor were Accepted at
44/80; every Required check passed and the final independent re-review gate reported zero Critical
and zero Important findings.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `7.6`
- Depends on: Accepted S7A-S7E/Tasks 7.1-7.5

## Goal

Implement the smallest package-internal `ReleasePublication` module that deterministically verifies
one candidate manifest against actual index manifests and point inventories, persists mutually
exclusive missing/extra/stale/cross-release repair evidence, refuses unaccepted promotion, switches
the injected canonical/published/index snapshot to one accepted release on an explicit `promote`
call, and restores the recorded prior snapshot on `rollback`.

## Non-goals

- No Task 7.7 real database/lookup/Milvus reconciliation, isolated alias/pointer adapter, or physical
  rollback rehearsal.
- No production-like promotion, cutover, live operator authorization/ACL/token system, durable
  transaction/repository, migration, network service, consumer migration, release retirement, or
  cleanup framework.
- No candidate, projection, lookup, vector, embedding, or index rebuild; no commit, push, PR,
  archive, or cutover.

## Allowed scope

- New `apps/miroflow-agent/src/data_agents/canonical_v2/release_publication.py` implementing the
  frozen `verify`, `promote`, and `rollback` interface plus one package-internal ephemeral composition
  factory over explicitly injected manifests, point inventories, stores, state, history, and clock.
- Remove only the three Task 7.6 strict-xfail wrappers in
  `apps/miroflow-agent/tests/canonical_v2/test_release_publication_interface.py` after their exact RED
  is recorded; append only focused current-contract regression scenarios if a model-valid Spec or
  safety bypass is found.
- This Slice Contract plus Task 7.6 verification/status evidence only after acceptance.

## Forbidden changes

- `contracts.py`, `knowledge_build.py`, `candidate_projection.py`, `index_projection.py`,
  `index_projection_isolated.py`, migrations, legacy release/index code, active product state, or
  OpenSpec product semantics.
- Opening or writing original PostgreSQL/Milvus, any production-like target, or any real alias/
  pointer; reading environment fallback configuration or accepting implicit target identity.
- Auto-promotion, mixed canonical/published/index release state, promotion without a stored accepted
  verification for the exact release, or deletion/mutation of candidate/verification/discrepancy
  evidence during rollback.
- Taking Task 7.7 ownership or weakening its isolated parity/rollback acceptance boxes.

## Expected unchanged behavior

- `KnowledgeBuild`, candidate projection, and index projection remain immutable construction seams
  with no active-pointer capability.
- Shared `ReleaseVerification` and `PublishedRelease` remain the exact public contract types; no
  shared-contract widening is needed.
- Verify is read-only with respect to the injected three-release snapshot. Calling `promote` is the
  current explicitly authorized in-process action; there is no implicit or automatic promotion.
- Original sources, recovery evidence, active product state, and all Task 7.7+ behavior remain
  unchanged.

## Required checks

- Pre-GREEN normal RED is exactly three strict xfails; forced RED is exactly three failures caused by
  the absent `src.data_agents.canonical_v2.release_publication` target and no nested dependency.
- Focused GREEN makes the three original owner scenarios pass: aggregate/point mismatch retains
  repair evidence and blocks promotion; exact parity permits one explicit atomic three-snapshot
  promotion and rollback; missing/extra/stale/cross-release points are classified exactly once with
  repairable identity/version/content details. Three focused review regressions additionally prove
  forged matching aggregate hashes are rejected, manifest/inventory count drift persists evidence,
  and stale evidence retains complete expected/actual point snapshots.
- Candidate manifest/verification/history/discrepancy evidence remains inspectable; verify never
  changes release state; rejected promotion is an exact no-op; rollback restores the recorded prior
  release without mutating retained evidence.
- KnowledgeBuild plus ReleasePublication is nine passes; S7E owner plus ReleasePublication is 46
  passes; shared contracts pass. Complete no-external Canonical V2 has no real failure and only the
  named KnowledgeRead/KnowledgeAnswer future-interface xfails.
- Ruff check/format, complete Canonical V2 Pyright, fresh import/wheel inclusion, strict OpenSpec,
  `git diff --check`, production-scope, high-confidence secret, generated-cache, frozen-source, and
  original-target checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI is recorded and
  nonblocking unless it is an explicit Spec violation, safety/data risk, or executable model-valid
  bypass.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `acceptance.md`, `change-log.md`, agent links, code-grounded plan, and portfolio
  only after Task 7.6 is Accepted.

## Stop conditions

- Exact reconciliation or atomic snapshot transition requires a new public contract/product meaning
  or a change to an Accepted predecessor.
- GREEN requires a real database/Milvus/pointer adapter, production-like authorization, Task 7.7
  rehearsal, migration, provider, consumer, or unrelated module change.
- A Required check exposes a real Accepted-slice regression, frozen-target mutation, or unresolved
  Critical/Important finding.

## Done means

- The three existing Task 7.6 RED scenarios are GREEN through the real package-internal module.
- Verification deterministically binds one candidate manifest, exact index manifests, and complete
  point inventories; every deviation is mutually exclusive, repairable, persisted, and blocks
  promotion.
- Only a stored accepted verification permits the explicit in-process promotion call; the injected
  three-release snapshot changes together and rollback restores its recorded prior release while all
  evidence remains auditable.
- Every Required check passes, review is zero Critical/Important, evidence/status is synchronized,
  Task 7.6/S7F is Accepted, and Task 7.7 is selected next without any real promotion or cutover.

## Plan

1. Record the exact normal/forced three-scenario RED and freeze current interfaces.
2. Implement the minimal pure reconciliation and ephemeral publication module; remove only the
   three xfail wrappers and reach focused GREEN.
3. Run combination, complete, static, package, safety, and frozen-target gates.
4. Obtain one independent review; repair only Critical/Important findings.
5. Persist acceptance evidence, mark Task 7.6 Accepted, and make Task 7.7 Ready.

## Rollback note

Delete `release_publication.py`, restore the three exact strict-xfail wrappers, and revert this
slice/evidence/status delta. The module owns only caller-injected ephemeral state; no external target,
database, index, alias, source, or production-like resource requires rollback.

## Acceptance evidence

- Pre-GREEN normal RED was exactly three strict xfails. The forced run produced exactly the three
  absent-target `_MissingTargetModule` failures. One concurrent normal/forced attempt hit a shared
  coverage-SQLite race; the unchanged normal command was rerun serially and produced the required
  `3 xfailed`, so the environmental attempt is not used as RED evidence.
- The three original REDs are GREEN. Review then produced three exact additional REDs: matching
  forged expected/actual aggregate hashes falsely accepted; actual manifest/point count drift raised
  before evidence persistence; and embedding-model staleness omitted its differing fields. All
  three are now GREEN, leaving focused owner verification at `6 passed`.
- Verification now binds expected and actual inventories independently using the exact S7E entity-ID
  and point-content hash algorithms plus count and manifest metadata. Point discrepancy evidence
  retains complete immutable expected/actual point snapshots, and every rejection persists before
  promotion is attempted.
- `KnowledgeBuild` plus ReleasePublication is `9 passed`; S7E owner plus ReleasePublication is
  `46 passed`; shared contracts are `16 passed`. Complete no-external Canonical V2 is
  `290 passed, 139 skipped, 2 xfailed`, with only the named KnowledgeRead and KnowledgeAnswer future
  interfaces remaining expected RED.
- Complete Canonical V2 Ruff and Pyright pass; the two S7F files pass format. Import identity proves
  shared `ReleaseVerification`/`PublishedRelease`. A fresh 271-entry wheel at
  `/var/tmp/canonical-v2-s7f-wheel-20260714T105913Z/miroflow_agent-0.1.0-py3-none-any.whl` has SHA-256
  `7f6986509d6b758920483f179e51c0a476774295e3018bd4889856301dab9316`, includes
  `release_publication.py`, and excludes `.agents`.
- Strict OpenSpec, `git diff --check`, production-scope, high-confidence secret, generated-cache,
  frozen-source, and original-target checks pass. Original Milvus remains SHA-256
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`; original `pgtest` remains
  paused on volume `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- Initial review found zero state/safety findings and three reconciliation Important findings. The
  three repairs were independently re-reviewed and closed; final aggregate is zero Critical and zero
  Important. Custom failing/concurrent MutableMapping transactions, production authorization,
  durable repositories, real pointer adapters, and Task 7.7 physical rehearsal remain nonblocking
  Minor/YAGNI.
- No real database/index/alias/pointer was read or changed by this module, and no commit, push, PR,
  production-like promotion, archive, or cutover occurred.
