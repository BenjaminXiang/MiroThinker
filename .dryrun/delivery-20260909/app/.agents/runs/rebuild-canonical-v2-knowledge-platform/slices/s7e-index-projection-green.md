# Slice Contract: s7e-index-projection-green

## Status

Accepted at `2026-07-14T10:22:52Z`. S6R/Tasks 6.9-6.11, S7C/Task 7.3, and S7D/Task 7.4 were
Accepted predecessors; every Required check passed and the final independent review gate reported
zero Critical and zero Important findings.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `7.5`
- Depends on: Accepted S6R/Tasks 6.9-6.11, Accepted S7C/Task 7.3, and Accepted S7D/Task 7.4

## Goal

Implement the smallest release-scoped lookup/vector index module that turns one exactly replayable
S7C candidate plus its public path-eligibility results into deterministic lookup documents, vector
points, and versioned manifests. Perform and read back the first full Canonical V2 build on a fresh,
explicitly marked isolated lookup/Milvus Lite target without reading or changing active release
pointers.

## Non-goals

- No Task 7.6 canonical/published/index reconciliation, `ReleasePublication`, verification record,
  authorization, promotion, rollback, active alias, or pointer transition.
- No Task 7.7 rollback rehearsal or accepted DB/index parity claim.
- No ordinary incremental write optimization, live embedding provider, fixed physical collection
  name, public vector dimension contract, legacy payload compatibility, consumer migration, commit,
  push, PR, archive, or cutover.

## Allowed scope

- New `apps/miroflow-agent/src/data_agents/canonical_v2/index_projection.py` for the frozen pure
  `IndexProjectionBuilder` contract and package-internal lookup/index write seam.
- One narrowly scoped package-internal isolated adapter module if keeping pymilvus/SQLite target
  mechanics out of the pure module materially deepens the interface.
- Remove only the three Task 7.5 `index_projection` strict-xfail wrappers in
  `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`.
- Append focused adapter scenarios to the existing
  `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` owner
  file for public lookup materialization/readback, target admission, full isolated Milvus Lite
  write/readback, and original-target refusal.
- This Slice Contract plus Task 7.5 verification/status evidence after acceptance.

## Forbidden changes

- `contracts.py`, S6/S6R production modules, `candidate_projection.py`, `knowledge_build.py`,
  migrations, legacy vectorizers/backfill scripts/stores, `release_publication.py`, or active state.
- Opening `apps/miroflow-agent/milvus.db`, accepting a relative/generic/environment-fallback target,
  connecting to a network Milvus endpoint, or dropping/overwriting any unmarked target.
- Treating internal Person or Technology as a public domain, or materializing unresolved references.
- Treating caller-supplied `build_mode=full` as sufficient when initial/schema/embedding/eligibility
  state independently requires a full rebuild.
- Weakening, deleting, or making GREEN any of the three Task 7.6 ReleasePublication strict REDs.

## Expected unchanged behavior

- Company, Paper, Patent, and Professor remain exactly the four public-domain populations.
- Candidate and PathEligibility inputs are accepted only after exact replay; semantic exclusion is
  path-specific and does not erase an otherwise eligible exact public lookup record.
- Professor identity and research vector views remain typed and separate; physical names are opaque.
- Candidate success/failure cannot change active canonical, published, or index release identifiers.

## Required checks

- Reconfirm normal and forced pre-implementation RED for exactly the three absent
  `index_projection` targets; then make exactly those three scenarios GREEN.
- Focused pure behavior proves exact candidate/path replay, complete eight-manifest vector ownership,
  deterministic stable point identity/hashes, typed Professor identity/research content, internal
  Person/Technology evidence anchors, semantic exclusion, and derived full-rebuild admission.
- Public lookup materialization/readback proves exactly four public plus three internal owner
  envelopes including empty owners, release/version/content binding, evidence-anchored Person/
  Technology records, and no fifth public domain.
- A fresh absolute, marked, isolated non-original target passes the Accepted S2B gate before client
  open and immediately before first write; deterministic recorded embeddings build and read back all
  eligible points in real Milvus Lite plus all lookup records. The receipt binds release, target,
  owner counts, point/document IDs and hashes, projection/schema/embedding/eligibility versions, and
  full-rebuild state.
- Missing/relative/network/original/unmarked targets fail before client open. Hash-only original
  Milvus pre/post checks match; active canonical/published/index identifiers remain unchanged.
- All three Task 7.6 ReleasePublication scenarios remain strict xfails. Owner, sibling, shared, and
  complete no-external Canonical V2 suites have no real failure and only named future-interface
  xfails.
- Ruff check/format, complete Canonical V2 Pyright, fresh import/wheel inclusion, strict OpenSpec,
  `git diff --check`, production-scope, high-confidence secret, generated-cache, and frozen-source
  checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI is recorded and
  nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- A content-addressed Task 7.5 isolated rebuild receipt under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7e/`.
- OpenSpec `tasks.md`, `acceptance.md`, `change-log.md`, agent links, code-grounded plan, and portfolio
  only after Task 7.5 is Accepted.

## Stop conditions

- The frozen interface cannot support public lookup plus vector construction without a new product
  meaning or shared public contract.
- A real isolated target cannot be proven distinct from the original before opening, or the Accepted
  S2B gate cannot be revalidated before its first write.
- GREEN requires `ReleasePublication`, active aliases/pointers, promotion/rollback, live provider,
  legacy compatibility, or an unrelated module change.
- Any Required check exposes a real Accepted-slice regression or an unresolved Critical/Important
  finding.

## Done means

- The three S7D index scenarios are GREEN through the real `IndexProjectionBuilder.build` path.
- Versioned lookup and vector projections are deterministic, read back exactly from one fresh
  isolated full build, preserve four-public/three-internal ownership and Professor intent, and carry
  exact release/object/content/policy/schema/model/evidence metadata.
- Original sources and active release state are unchanged, the required regression/static/package/
  safety gates pass, evidence is persisted, and Task 7.5/S7E is Accepted with Task 7.6 selected next.

## Plan

1. Re-run the three exact normal/forced RED scenarios and freeze their failure identities.
2. Implement the pure projection/lookup contract, remove only its three xfail wrappers, and reach
   focused GREEN.
3. Implement the guarded package-internal isolated lookup/Milvus Lite adapter and exercise one fresh
   full build/readback using deterministic recorded embeddings.
4. Run focused, sibling, complete, static, strict, package, and safety gates; obtain independent
   review and repair only Critical/Important findings.
5. Persist the receipt and acceptance evidence, mark Task 7.5 Accepted, and make Task 7.6 Ready.

## Rollback note

Delete the new Task 7.5 modules, remove the appended adapter scenarios, restore the three exact xfail
wrappers, and revert this slice/evidence/status delta. The isolated test target is owned and
disposable; no active pointer, original source, database, provider, or production-like resource
requires rollback.

## Acceptance evidence

- Pre-implementation normal RED was exactly three `index_projection` xfails; forced RED was exactly
  three absent-target failures. The same three scenarios are now GREEN through the production
  builder, and all three Task 7.6 `ReleasePublication` scenarios remain strict xfails.
- Final owner verification is `40 passed`; owner plus Task 7.6 interface verification is
  `40 passed, 3 xfailed`. Complete no-external Canonical V2 is `284 passed, 139 skipped, 5 xfailed`:
  only KnowledgeRead, KnowledgeAnswer, and the three Task 7.6 scenarios remain expected RED.
- A fresh retained isolated target run passed `1 passed in 12.98s`; its content-addressed evidence is
  `../s7e/isolated-index-rebuild-receipt.json`. It records six real Milvus Lite points, five SQLite
  lookup documents, eight vector owner manifests, seven lookup owner manifests, exact readback,
  S2B admission, and unchanged frozen targets.
- Complete Canonical V2 Ruff and Pyright pass; the three S7E files pass focused format. A fresh
  270-entry wheel includes both index modules and excludes `.agents`. Strict OpenSpec,
  `git diff --check`, source/write-boundary, high-confidence secret, generated-cache, import, and
  frozen-source checks pass.
- Original Milvus remains SHA-256
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc` and original `pgtest`
  remains paused on volume `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`.
- Three independent final reviews report zero Critical and zero Important findings. Recorded Minors
  and YAGNI—receipt root binding, aggregate-manifest limits, illustrative in-memory active state,
  durable failure cleanup, production adapters, and fixture splitting—are nonblocking; Task 7.6
  retains complete point-level reconciliation and all release-publication ownership.
- No commit, push, PR, publication, promotion, rollback, archive, or cutover was performed.
