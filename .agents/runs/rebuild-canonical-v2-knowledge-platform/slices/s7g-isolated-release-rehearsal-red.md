# Slice Contract: s7g-isolated-release-rehearsal-red

## Status

Accepted at `2026-07-14T11:49:32Z`. Task 7.7 remains open at 45/80: this RED half freezes its exact
failure contract but does not complete the isolated rehearsal. S7H GREEN is the next Ready slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `7.7` (RED half only)
- Depends on: Accepted S7A-S7F/Tasks 7.1-7.6

## Goal

Freeze exactly three strict RED integration scenarios for the missing package-internal isolated
publication adapter: complete physical lookup/Milvus inventory plus disposable-PostgreSQL pointer
rehearsal; physical extra-point refusal with retained evidence and unchanged prior pointer; and
fail-closed database/index target identity before client open or pointer write.

## Non-goals

- No implementation of `release_publication_isolated`, complete physical inventory audit, PostgreSQL
  adapter, promotion, or rollback in this RED slice.
- No migration/schema change, durable candidate/recovery database use, production alias/pointer,
  production authorization, consumer wiring, S8 behavior, live provider, concurrency/2PC framework,
  release retirement, commit, push, PR, archive, or cutover.

## Allowed scope

- Append exactly three strict-xfail Task 7.7 scenarios and focused helpers to
  `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`, reusing
  its accepted S7E physical fixture builders instead of splitting or duplicating the large fixture.
- Freeze only the future package-internal
  `src.data_agents.canonical_v2.release_publication_isolated` composition surface and the additive
  complete-inventory audit required from `index_projection_isolated`.
- This Slice Contract plus RED verification/status evidence after acceptance; Task 7.7 itself stays
  unchecked.

## Forbidden changes

- Any production module, shared contract, migration, Accepted S7 module behavior, current xfail
  wrapper outside the three new scenarios, or existing OpenSpec acceptance checkbox.
- Opening original `pgtest` or original Milvus with a client; using the durable recovery candidates;
  reading generic `DATABASE_URL` as a test/rehearsal target; mutating retained S7E acceptance
  artifacts.
- Treating receipt-listed point IDs as a complete physical Milvus inventory, or accepting mixed
  canonical/published/index release IDs.
- Claiming Task 7.7/S7 complete or making real promotion/cutover behavior GREEN.

## Expected unchanged behavior

- S7E physical build/readback and S7F pure reconciliation/publication remain Accepted and unchanged.
- Task 7.7 GREEN will reuse `ReleasePublication.verify/promote/rollback`; RED adds no competing public
  release interface.
- Missing/extra/stale/cross-release classification, lookup ownership, original-source freeze, and the
  explicit authorization boundary remain unchanged.

## Required checks

- Normal focused execution reports exactly three strict xfails, each caused directly by absence of
  `src.data_agents.canonical_v2.release_publication_isolated`.
- Forced `--runxfail` execution reports exactly three `_MissingIsolatedReleasePublicationModule`
  failures for that exact absent target; nested dependencies, fixture errors, environment skips, or
  unrelated failures are not accepted RED.
- The frozen happy-path scenario requires a fresh marked disposable Postgres plus two fresh marked
  physical index roots, exact candidate verify, one atomic DB pointer promotion, serving reads from
  the candidate, rollback to one internally consistent prior release, and immutable evidence/index
  bytes.
- The frozen drift scenario injects one extra point only into a test-owned candidate Milvus after its
  successful receipt; a complete physical audit must surface `extra_points == 1`, block promotion,
  retain discrepancy evidence, and leave the Postgres pointer on the prior release.
- The frozen safety scenario requires explicit disposable database identity and marked index/release
  continuity, ignores generic `DATABASE_URL`, and fails malformed/original/unmarked/cross-wired
  targets before client open or pointer write.
- Existing S7F owner remains six passes; S7E owner remains 40 passes plus these three named REDs.
  Ruff check/format, Pyright, strict OpenSpec, `git diff --check`, scope/secret/cache, and frozen-source
  checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI is nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec change log, agent links, code-grounded plan, and portfolio only after RED acceptance; do
  not check Task 7.7 or close its rollback acceptance item.

## Stop conditions

- The three REDs require a new product meaning, migration, public contract, production-like target,
  or any change to an Accepted predecessor.
- A RED is hidden by environment skip, catches a nested dependency/error, or can pass without a
  complete physical inventory scan and real disposable pointer transaction in GREEN.
- Any check exposes an Accepted-slice regression, forbidden-target access, or unresolved Critical/
  Important finding.

## Done means

- Exactly three reviewable Task 7.7 scenarios fail for the exact absent isolated adapter and no other
  reason in normal/forced runs.
- Their future seam is sufficient to prove complete physical DB/index parity, atomic isolated
  pointer transition/rollback, and target safety without taking production/cutover ownership.
- Required static/scope/frozen-target checks and independent review pass; S7G RED is Accepted while
  Task 7.7 remains open and S7H GREEN is selected next.

## Acceptance evidence

- Normal focused execution returned exactly `3 xfailed`; forced `--runxfail` returned exactly three
  `_MissingIsolatedReleasePublicationModule` failures for the absent
  `src.data_agents.canonical_v2.release_publication_isolated` target. Target import precedes external
  environment preparation, so no skip or fixture failure can mask RED.
- S7E owner plus S7F publication returned `46 passed, 3 xfailed`; complete no-external Canonical V2
  returned `290 passed, 139 skipped, 5 xfailed`, with only these three Task 7.7 REDs plus the
  existing KnowledgeRead/KnowledgeAnswer REDs.
- Complete Ruff check, Canonical V2 Pyright, focused format, strict OpenSpec, `git diff --check`,
  scope/secret/cache, absent-target, frozen Milvus, and paused-Postgres checks passed. Original
  Milvus remains SHA-256 `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Two independent read-only reviews of test SHA-256
  `111dbaabe230932a31a3b5cd4879a0960611d7babf290604223036ffbc61477a` report zero Critical and zero
  Important findings. Fixture extraction, fixed fresh-database IDs, and duplicate physical
  missing/stale/cross-release cases are recorded Minor/YAGNI and do not block acceptance.
- No production module, external resource, pointer, database, index, migration, commit, push, PR,
  publication, rollback, archive, or cutover was created or changed by this RED slice.

## Plan

1. Add the exact target-module sentinel and three strict RED scenarios before external fixture setup.
2. Run normal/forced focused RED and prove exact failure identities.
3. Run sibling S7F/S7E, static, strict, scope, and frozen-target checks.
4. Obtain independent review, persist RED evidence, accept S7G, and create S7H GREEN next.

## Rollback note

Remove only the three Task 7.7 scenarios/helpers and this RED evidence/status delta. No production
module, schema, database, index, pointer, original source, or external resource is changed by RED.
