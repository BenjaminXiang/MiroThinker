# Slice Contract: s3c-shared-typed-contracts

## Status

Accepted at `2026-07-11T17:15:42Z` under the user's objective-verification self-approval
authorization. This acceptance covers only the storage-independent typed values and validators; it
does not authorize a database migration, candidate build, landing replay, provider call, or release-
state change.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `3.3`
- Depends on: Accepted task 3.2
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s3-shared-contracts-plan.md`

## Goal

Define one strict shared Pydantic contract surface for Canonical V2 evidence, assertions, decisions,
identities, relationships, policies, gaps, releases, and manifests. The types must preserve the
approved domain distinctions while remaining independent of Postgres tables, provider clients, and
future orchestration implementations.

## User / operator effect

Every later builder, reviewer, publication path, and audit view exchanges the same validated
concepts: evidence cannot be mistaken for a canonical fact, conflicting assertions survive
selection, identity/relationship decisions remain reversible and traceable, ordinary quality gaps
remain soft, and a release manifest can account for the whole candidate.

## Ubiquitous-language boundaries

- `EvidenceArtifact` is byte-addressed source material; `SourceRecord` is one parser output;
  `SourceAssertion` is one source-provided field claim. None is a canonical value.
- `CanonicalDecision` selects or leaves unresolved retained assertions; it never deletes them.
- `SourceIdentity` names an object as a source knew it; `CanonicalIdentity` represents the resolved
  real-world object; `IdentityDecision` records link/create/merge/split/reject/reversal lineage.
- `RelationshipType` is catalog metadata; `RelationshipAssertion` is source-grounded evidence;
  `RelationshipDecision` is the canonical relation decision. Derived/session relations are marked
  as different layers and cannot masquerade as canonical source facts.
- `PolicyReference` identifies a versioned rule; `PolicyDecision` records admission, limitation,
  review, or a named hard exclusion. Inclusion and each retrieval path stay distinct.
- `KnowledgeGap` is an observed product/operations gap, not a missing-field synonym. Resolution
  requires an accepted release plus verification evidence.
- `CandidateRelease` is mutable workflow state only by replacement/versioning; `BuildManifest` and
  projection manifests are immutable content identities. Publication/reconciliation types must keep
  one release identity across canonical, publish, and index projections.

## Non-goals

- Define Professor, Company, Paper, or Patent business fields; those remain typed-domain work.
- Create SQLAlchemy models, tables, Alembic revisions, repositories, adapters, or serializers tied
  to physical storage.
- Implement the five Task 3.1 deep-module interfaces or make their strict RED tests GREEN.
- Encode every future relationship name, source kind, field path, or policy in a closed enum.
- Use a single global quality/readiness gate or reject ordinary incompleteness.
- Modify `CONTEXT.md`; the approved glossary already contains the terms this slice implements.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/contracts.py`.
- Focused tests under `apps/miroflow-agent/tests/canonical_v2/test_shared_contracts.py`.
- This slice/plan, OpenSpec task/change log, and verification evidence.

## Contract-wide invariants

- Models reject unknown fields, use timezone-aware timestamps, validate SHA-256 identities, and are
  frozen at the object interface.
- IDs are opaque non-empty strings; the contract does not force legacy IDs or UUIDs.
- Ordinary absence remains representable with optional values/limitations; validators enforce only
  hard semantic contradictions required by OpenSpec.
- Selected/accepted decisions cite retained assertions; unresolved decisions retain competing
  assertion IDs; split/merge/reversal lineage is explicit.
- Canonical relationship types declare endpoint types, direction, roles, evidence/time semantics,
  allowed states, and eligible paths. Derived/session layers cannot carry source assertion IDs.
- Excluded policy decisions cite named hard invariants; limited decisions state limitations.
- Closed gaps cite an accepted release and verification evidence.
- Manifest sections retain source/parser/policy/model/decision/object/relationship/eligibility/
  publication/index identities, counts, and hashes without depending on collection/table names.

## Required RED cases

1. The shared `canonical_v2.contracts` module is absent.
2. Artifact/record/assertion models cannot yet preserve chain of custody and temporal evidence.
3. Decision/identity/relationship models cannot yet express conflicts, merge/split reversal, or
   relationship-layer separation.
4. Policy/gap/release/manifest models cannot yet reject unnamed hard exclusion, unverifiable gap
   closure, or mixed release manifests.

## Required checks

- Focused contract tests cover valid round trips plus invalid semantic contradictions for every
  family named in task 3.3.
- JSON-mode model dumps remain serializable and retain evidence/release/version IDs.
- Task 3.1 remains exactly five strict xfails; Task 3.2 gate/baseline tests pass without another DB
  migration cycle unless needed for regression confidence.
- S1 safety and S2/S2B tests pass; strict OpenSpec and `git diff --check` pass.
- Ruff and Pyright pass for all touched Python.
- Original source and accepted candidate-target invariants remain unchanged; no database/Milvus/
  provider command is required by the implementation tests.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

## Stop conditions

- A model requires a physical table/column/collection/provider decision.
- A validator turns ordinary incompleteness into an unnamed hard exclusion.
- A generic assertion value becomes the only representation of typed domain facts.
- Relationship/identity/gap state cannot retain evidence, decision version, or reversal/release
  lineage required by OpenSpec.
- Task 3.1 interface implementation or Task 3.4 migration becomes necessary.

## Done means

- Every family named in task 3.3 has a strict shared model and observable invariant coverage.
- Valid partial/conflicting histories serialize; semantic contradictions fail with specific errors.
- No runtime, database, provider, source, or accepted candidate state changes.
- Task 3.3 is Accepted and committed alone; Task 3.4 has not started in the same commit.

## Acceptance checkpoint

- Focused RED reported exactly `15 failed`; every failure was
  `ModuleNotFoundError: src.data_agents.canonical_v2.contracts`, with no collection, fixture, or
  syntax error.
- The shared seam contains 26 frozen extra-forbid Pydantic models and 20 workflow enums. Opaque IDs
  and catalog identifiers remain open strings, while SHA-256, aware time, confidence, count,
  decision, policy, gap, release, and parity contradictions are validated.
- Fifteen focused tests pass across artifact/record/assertion lineage, selected/unresolved values,
  merge/split/reversal identities, three relationship layers, soft limitations vs named hard
  exclusions, all required gap classes, proven gap closure, and one-release manifests/publication.
- Pyright initially rejected Python enum member name `split` because it conflicts with `str.split`.
  The member name became `split_identity` while the external JSON value remains exactly `"split"`;
  focused tests and Pyright then passed.
- Expanded Canonical V2 regression reported `21 passed, 1 skipped, 5 xfailed`; the skipped test is
  the intentionally opt-in real migration cycle, and the five xfails remain Task 3.1's unimplemented
  deep-module seams. S1 reported `9 passed`; S2/S2B reported `32 passed`.
- Ruff passed and Pyright reported zero findings; strict OpenSpec, formal 50-source admission, and
  diff checks passed. Read-only target inspection retained system identifier `7661313446684311592`,
  revision `C2_0001`, eight schemas, and zero business tables.
- Original `pgtest` stayed paused on its exact volume, the recovery lab stayed network-none/no-port,
  and original Milvus/salvage hashes matched. No DB migration/write, Milvus client, provider, source,
  dependency, runtime, or `CONTEXT.md` change occurred.
