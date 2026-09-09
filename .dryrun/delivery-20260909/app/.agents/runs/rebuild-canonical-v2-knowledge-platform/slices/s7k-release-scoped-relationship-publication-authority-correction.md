# Slice Contract: S7K Release-scoped Relationship Publication Authority Correction

## Status

Accepted at `2026-07-19T17:05:53Z`. Exact RED/GREEN, real disposable relationship-persistence,
shared physical/release/full no-external, static/package/frozen-target gates, receipt-first owned-
output cleanup, and evidence synchronization are complete. Contract reviews closed six Important;
implementation review closed two Important. Final targeted review reports zero Critical/Important/
Minor/YAGNI with `Accept`. The formal ledger remains `56/80`, Task 8.3 remains open, and S2C3C2
continues to gate reviewed calibration/oracle execution only. S8R1 release-scoped relationship
retrieval is the next Ready successor.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Corrects Accepted Tasks 7.2/7.3/7.6/7.7 under the existing immutable relationship-manifest,
  single-release publication, and Task 8.3 relationship-lane requirements
- Depends on: Accepted S6R relationship projection/replay/persistence, S7 candidate projections,
  release manifest/publication/rehearsal, and S8IR1
- Successor: S8R1 release-scoped relationship retrieval may become Ready only after S7K is Accepted
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7k/implementation-plan.md`

## Goal

Make the existing S6 `RelationshipProjectionRequest`/`RelationshipProjectionResult` pair an exact,
release-scoped publication authority at the S7 `IsolatedReleaseBundle` boundary without changing
the four-public/three-internal candidate projection model.

Add optional `relationship_projection_request` and `relationship_projection_result` fields to
`IsolatedReleaseBundle` with these rules:

- the pair is both present or both absent;
- an absent pair is allowed only as legacy compatibility for an existing zero-count relationship
  manifest and does not constitute relationship publication authority; every S8 relationship
  consumer must require a present pair, including for an authoritative zero-result release;
- a present pair is replayed through the installed pure relationship projector and must equal the
  supplied result exactly;
- a present relationship pair must itself contain the request's both-present internal-reference
  request/result pair and therefore use the installed combined registry;
- that internal-reference pair is replayed through `compose_candidate_projections`; the resulting
  seven public/internal projection manifests must equal the build manifest's seven published
  projection manifests exactly;
- the relationship manifest uses section ID `relationships` and binds the same release, the
  result's projection-schema version, `len(result.current_relationships)`, and
  `result.content_sha256`; registry identity/type versions remain bound by exact relationship replay
  and the result hash rather than overloading the manifest section version;
- publication-factory validation reconstructs each bundle through exact typed validation before
  any backup-gate access, target-marker/index read, database target validation/connection, state or
  release-registry access, or other external effect. `_validate_bundle_pair` returns the two fresh
  validated bundles and the factory replaces both caller-supplied objects before any later use,
  closing `model_construct`, mutation, and cross-wired-instance bypasses;
- publication-factory validation requires each caller input to have exact
  `IsolatedReleaseBundle` type and recomputes the canonical `BuildManifest` payload hash (excluding
  only `manifest_sha256`) before any effect. A self-consistent replacement relationship graph,
  relationship section, and seven-manifest set cannot retain a stale manifest hash.

## Non-goals

- No S8 relationship query adapter, traversal semantics, ranking, fusion, evidence trace, planner,
  answer/session/gap behavior, provider, or reviewed-corpus acceptance.
- No new relationship type, decision, projection, persistence repository, manifest type, public
  domain, Product-capability relationship, or path-eligibility policy.
- No change to candidate projection's four public plus three internal populations, relationship
  projector/store, index construction, database schema/migration, active pointer, or original/
  production-like target.
- No Task checkbox, aggregate S7/S8 acceptance, Commit, Push, PR, Archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/release_publication_isolated.py` for the two
  optional typed fields, pure exact replay/binding validation, and effect-before-validation guard.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  exact-symbol RED/GREEN group and the smallest reusable non-empty combined-registry relationship
  fixture extension.
- This contract, S7K plan/receipt, and S7K-only verification evidence. Existing verification,
  change-log, agent-links, portfolio, and mainline-plan artifacts may be synchronized only after
  Candidate review. Keep `tasks.md` and `acceptance.md` unchanged.

## Forbidden changes

- `candidate_projection.py`, `relationship_projection.py`,
  `relationship_projection_postgres.py`, `index_projection*.py`, `knowledge_read*.py`, migrations,
  catalogs, public contracts outside `IsolatedReleaseBundle`, and unrelated tests.
- Copying relationship data into `CandidateProjectionResult`, inventing a second relationship
  receipt/store, trusting manifest metadata without pure replay, accepting a partial pair, or
  deriving relationship count from candidates/assertions rather than accepted current relations.
- Opening PostgreSQL/Milvus/index files before exact bundle validation, weakening target identity,
  changing active state, or masking an existing assertion with xfail/skip changes.

## Expected unchanged behavior

- Existing zero-relationship bundles remain valid for legacy publication compatibility when both
  new fields are absent and `relationship_set.record_count == 0`; their existing manifest/index
  identities and physical behavior do not change, but they cannot authorize an S8 relationship
  adapter. A newly authoritative zero-result relationship release carries and validates the pair.
- Public/internal projection populations and manifests, index points/manifests/targets, release
  lifecycle and rollback, relationship projection/persistence semantics, and all S8 real-lane
  behavior remain unchanged.
- The correction adds authority only; it performs no physical relationship read and makes no query
  lane available. Task 8.3 and the formal ledger remain open/unchanged.

## Required checks

- RED normal: exactly one strict xfail. Forced `--runxfail`: exactly one direct
  `_MissingS7KRelationshipPublicationAuthority` failure before fixture acquisition, database
  connection, or index-target access.
- GREEN focused: exactly one pass using a real combined-registry relationship request/result with
  accepted Technology discussion, claimed-adoption, and demonstrated-use current relationships.
  Exact JSON round-trip retains the pair and publication authority. A second compact present-pair
  case proves an authoritative zero-result release remains distinguishable from legacy no-pair
  compatibility.
- The focused group rejects: one missing pair member; absent pair with non-zero manifest count;
  a present relationship request without its internal-reference pair or without the combined
  registry; request/result release or as-of cross-wire; replay/result mismatch; relationship
  manifest section ID, release, projection-schema version, count, or hash drift; a relationship
  graph whose replayed seven projection manifests differ from the build manifest; and a
  stale manifest hash after otherwise self-consistent graph/section replacement; a bundle subclass;
  and a `model_construct`/cross-bundle bypass. Every hostile publication-factory case instruments
  the backup gate, target markers/index reads, target validation, PostgreSQL state/registry access,
  and other external seams and proves all effect counters remain zero.
- Existing zero-count S7 bundle construction remains GREEN. Run the S6 relationship pure owner and
  unchanged relationship-persistence owner, S7 candidate/index/publication physical owners, S8
  release-bound physical successors, and the complete no-external Canonical V2 suite.
- Complete Ruff/format, changed-file compile, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/
  target gates pass with actual counts recorded.
- One independent implementation review ends with zero open Critical/Important. Minor/YAGNI is
  recorded and does not block unless it proves a Spec, safety, or model-validation bypass.

## Evidence to update

- This contract and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s7k/verification-receipt.json`.
- Existing verification/change-log/agent-links/portfolio/mainline plan only after acceptance. Do
  not change `tasks.md` or `acceptance.md`.

## Stop conditions

- Exact replay cannot bind the existing S6 relationship result without changing relationship
  semantics/persistence, candidate projection populations, public APIs beyond the bundle, schema,
  index construction, or active pointers.
- A non-zero authority cannot be proven from the accepted combined-registry fixture, validation
  cannot precede all external effects, an existing S7/S8 owner regresses, original/production-like
  state changes, or a Critical/Important finding remains open.

## Done means

- One exact RED becomes one narrow release-authority GREEN; all affected owner/static/package/
  frozen-target checks pass and independent review has zero open Critical/Important findings.
- S7K is Accepted as a correction checkpoint with the ledger still `56/80` and Task 8.3 open;
  S8R1 may then start against the exact relationship authority.

## Rollback note

Remove the two optional bundle fields and exact relationship/candidate replay validation, remove the
focused fixture/tests and S7K evidence, and restore the prior zero-only fixture path. No schema,
stored relationship, index point, original target, task checkbox, or release pointer requires
rollback.
