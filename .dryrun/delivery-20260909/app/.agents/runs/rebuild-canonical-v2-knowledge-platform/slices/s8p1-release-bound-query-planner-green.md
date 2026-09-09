# Slice Contract: s8p1-release-bound-query-planner-green

## Status

Accepted at `2026-07-16T08:02:11Z` as a Task 8.2 predecessor only. Exact RED was `2 xfailed, 46
deselected`; both forced failures were the direct missing-factory sentinel. Final focused/shared/
query-owner/read-owner/full results are `2 passed`, `46 passed, 2 skipped`, `4 passed`, `16 passed`,
and `334 passed, 141 skipped, 0 xfailed`. Static, strict, package/source-parity, scope/secret/cache,
and frozen-target checks pass. Independent review plus targeted repair review leaves zero open
Critical/Important findings. Task 8.2 remains unchecked, the formal ledger remains `55/80`, and
S8P2 is the next Ready successor. S2C3C2 remains an external review gate only for reviewed claim-
level calibration/oracle execution; it did not block this deterministic release-binding slice.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.2` (release-binding predecessor only; Task 8.2 remains unchecked)
- Accepted dependencies: S6R5/Tasks 6.9-6.11, aggregate S7/Tasks 7.1-7.7, S8Q1 query-planning RED,
  S8RG synthetic planner/read mechanics, and S8L1/S8L2 physical release-bound lookup adapters
- Successor: S8P2 owns proposal taxonomy/safety cross-field validation and assessment intent/user-
  criteria capture; only the complete accepted Task 8.2 obligation may update `tasks.md`

## Goal

Add one package-internal factory through the existing query-planning seam:

```python
create_isolated_release_query_planner(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    index_projection_request: IndexProjectionRequest,
    release_institution_catalog: InstitutionCatalog,
    planning_policy: QueryPlanningPolicy,
    proposal_provider: Callable[[QueryPlanningRequest], object],
    ambiguity_policy: AmbiguityPolicy | None = None,
) -> _QueryPlanner
```

The factory shall:

1. Revalidate exact same-class values for the release bundle, serviceable publication, index
   request, institution catalog, planning policy, and optional ambiguity policy. Reject unsupported
   public-domain or lane policy before any proposal-provider call.
2. Replay the complete `IndexProjectionRequest` through the real ephemeral S7 index builder and
   require exact equality with `release_bundle.index_result`. Require one release plus exact build-
   run continuity inside the candidate/internal request-result graph and exact public/internal/
   manifest/index continuity. The manifest's top-level `KnowledgeBuild` run remains a distinct,
   already-content-bound orchestration run and is not falsely equated with the projection sub-run.
   Recompute the complete `BuildManifest.manifest_sha256`; do not trust the model-valid stored hash.
3. Accept one release-scoped institution catalog only when its institution ID set and each entry's
   canonical-name-plus-alias set exactly equal institution names observed for that ID in accepted
   typed public projections. Reject invented or missing per-ID names. The same observed label may
   legitimately belong to more than one ID and must remain an ambiguous catalog alias rather than
   being rejected merely because it is shared.
4. Derive resolved and unresolved `PersonReferenceRecord` values exclusively from the replayed S6R
   Person projections, evidence anchors, and typed public projections. Education, Company role, and
   Company geography facts retain accepted assertion/evidence IDs. Unresolved references remain
   separate and cannot satisfy identity filters or traversal. If one resolved Person spans multiple
   Company roots, suppress geography under the current flat fact shape rather than combining a role
   from one Company with geography from another.
5. Derive `TechnologyRouteRecord` values exclusively from replayed S6R route projections, retaining
   accepted route identity, preferred name, aliases, definition evidence, and deterministic derived-
   record identity. The exact source projection set remains bound by
   `PlanningReleaseBinding.internal_reference_projection_result_sha256`.
6. Delegate proposal interpretation to the existing ephemeral planner, reject a planning request
   whose release differs before provider invocation, and return the existing `RetrievalPlan` shape
   with a content-bound `PlanningReleaseBinding` covering publication, bundle/manifest/index,
   candidate/internal projection, institution catalog, and planning-policy identities. The
   `RetrievalPlan` model itself rejects a binding release different from `plan.release_id`, any
   institution-slot or lane-query release/catalog cross-wire, any internal-query release cross-wire,
   and any release-bound internal query relabeled as a public population.
7. Preserve the legacy ephemeral planner serialization/hash shape when no release binding exists.

## Non-goals

- Do not close Task 8.2. S8P2 still owns finite behavior/interaction/Web/safety proposal taxonomies,
  cross-field validation, and lightweight assessment intent/user criteria. `AssessmentIntent.kind`
  remains an open non-empty value under ADR-022 rather than joining those finite taxonomies.
- Do not implement Task 8.1 calibration, Task 8.3 lane execution, Task 8.5 fusion/rerank/Web-handle
  lifecycle, Task 8.7 sufficiency, Task 8.8 aggregate acceptance, S9 answer/session behavior, S10,
  S11, or S12.
- Do not add a public Person or Technology domain, a canonical Product-capability relationship, a
  global institution registry, a hardcoded institution-name/alias stopword list, a second planner
  service, or a generic release framework.
- Do not call live LLM/Web/embedding/rerank providers or write PostgreSQL, Milvus, candidate state,
  release pointers, source evidence, or production-like targets.
- Do not Commit, Push, create a PR, archive the change, promote a release, or Cutover.

## Allowed scope

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` only for the optional
  `PlanningReleaseBinding`, legacy-none serialization preservation, and catalog-driven Person
  education filtering needed by the release-derived records.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for the one
  release-bound planner factory, closed-graph replay validation, catalog validation, and internal
  record derivation.
- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`
  for one real combined Person+Technology S6/S7 fixture, exact `IndexProjectionRequest` exposure,
  and two vertical S8P1 contract groups.
- Modify `apps/miroflow-agent/tests/canonical_v2/test_knowledge_query_planning_contract.py` only if
  the existing synthetic Person owner must receive its already-defined institution catalog instead
  of relying on name-specific parsing; no assertion weakening or new S8P2 behavior is allowed.
- Update this contract, `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p1/`, existing
  verification/change-log/agent-links/portfolio/mainline-plan evidence after Candidate review.
  `tasks.md` and `acceptance.md` remain unchanged.

## Forbidden changes

- Any migration, database/index/release-publication/source/provider/admin/chat/answer/gap module,
  original source, recovery source, or Accepted S6R/S7 contract semantics.
- Caller-supplied `PersonReferenceRecord` or `TechnologyRouteRecord` parameters on the isolated
  release factory; post-merging independent Pydantic results; a test-local final planner; hand-built
  returned plans; `model_construct` trust; broad exception fallbacks; `importorskip`; runtime
  `pytest.xfail`; live credentials/network; or reference prose/model memory as truth.
- Silent task/acceptance checkbox changes, calibrated ambiguity values, assessment dimensions,
  scores, weights, global registries, or taxonomy/safety ownership from S8P2.

## Expected unchanged behavior

- The existing synthetic `create_ephemeral_query_planner` remains available and all four S8Q1
  owners stay GREEN. Existing plans without a release binding serialize and hash exactly as before.
- S8L1 exact and S8L2 structured physical lookup behavior and their candidate/evidence identities
  remain GREEN. Adding internal Technology to the shared real fixture does not expose an internal
  auxiliary as a public lookup result.
- The 16 KnowledgeRead owners, 13 KnowledgeAnswer owners, and all prior no-external Canonical V2
  tests remain GREEN.
- Before GREEN, the two S8P1 tests fail only through the absent exact factory symbol and do not
  acquire the physical fixture. After GREEN, the shared file increases from `44 passed, 2 skipped`
  to `46 passed, 2 skipped`, absent concurrent work.
- Original PostgreSQL/Milvus/forensic sources, the recovery lab, active release/index pointers, and
  the formal `55/80` ledger remain unchanged.

## RED contract

Add `_MissingIsolatedReleaseQueryPlannerFactory` and a lazy symbol resolver for exactly:

```text
src.data_agents.canonical_v2.knowledge_read_isolated.create_isolated_release_query_planner
```

Both tests resolve the symbol before `request.getfixturevalue("isolated_lookup_target_bundle")`.

1. `test_release_scoped_query_planner_binds_replayed_person_technology_and_catalog` freezes one
   representative pre-change ephemeral plan's exact serialized JSON and `content_sha256`, then uses one real
   combined S6/S7 release and proves an observed `SUSTech` alias resolves to
   `institution:sustech`, a resolved founder/education/Shenzhen Person query uses typed evidence,
   unresolved real references remain separate and ineligible, `vision servo` resolves to the
   accepted Technology route/definition lineage, internal references remain non-public, the release
   binding contains exact content identities, binding/plan/catalog cross-wires are model-invalid,
   and the legacy snapshot remains byte/value identical.
2. `test_release_scoped_query_planner_rejects_release_graph_catalog_and_policy_crosswires_before_provider`
   proves zero provider calls for a cross-release planning request/publication, same-release but
   Person-only or Technology-only index request, invented/missing catalog alias, fifth public domain,
   unsupported lane, a stale model-valid manifest hash, and other model-valid same-class tampering.

Exact pre-GREEN outcomes:

- focused normal: `2 xfailed, 46 deselected`;
- focused `--runxfail`: `2 failed, 46 deselected`;
- both failures are direct `_MissingIsolatedReleaseQueryPlannerFactory` sentinels;
- physical fixture acquisition count is zero.

## Required checks

- RED exact outcomes above, plus the unchanged existing shared-file tests pass while the two new
  tests remain strict xfails.
- Focused GREEN: exactly `2 passed`; S8L1 focused `1 passed`; S8L2 focused `1 passed`.
- Complete shared physical/release file: expected `46 passed, 2 skipped`.
- Existing query-planning owner: `4 passed`; complete KnowledgeRead owner matrix: `16 passed`.
- Complete no-external Canonical V2: expected `334 passed, 141 skipped, 0 xfailed`, with actual counts
  recorded and no real failure.
- Ruff check/format for changed files, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/generated-cache, and frozen-
  source checks pass.
- One merged independent review ends with zero open Critical/Important findings. Minor/YAGNI is
  recorded and nonblocking unless it proves an explicit Spec/safety violation or current model-valid
  bypass.

## Evidence to update

- This Slice Contract and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p1/verification-receipt.json`.
- Existing `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- Existing OpenSpec `change-log.md` and `agent-links.md` after acceptance.
- Existing `.agents/portfolio.md` and code-grounded mainline plan after acceptance.
- Do not modify `tasks.md` or `acceptance.md` for S8P1.

## Stop conditions

- Exact S7 replay cannot prove one closed Person+Technology graph without changing an Accepted S7
  public contract or post-merging independent results.
- Correct release binding requires persistence, a live provider, reviewed S2C truth, calibrated
  thresholds, original/production-like state, or a product semantic absent from OpenSpec/ADRs.
- The isolated factory cannot reject graph/catalog/policy/request crosswires before provider calls;
  unresolved references become identities; internal references become public; existing owners
  regress; or a Critical/Important finding remains.
- The work expands into S8P2 taxonomy/assessment, S8 runtime lanes, S9, consumer migration, or an
  unauthorized Commit/Push/PR/Cutover.

## Done means

- Both exact REDs are observed, then become GREEN through one release-bound factory using only a
  replayed Accepted S7 graph and validated catalog/policy inputs.
- Focused/sibling/full/static/strict/package/source checks and one independent review satisfy the
  Required checks with zero open Critical/Important findings.
- S8P1 is Accepted only as a Task 8.2 predecessor. Task 8.2 remains unchecked, the ledger remains
  `55/80`, and S8P2 becomes the next Ready successor.

## Acceptance evidence

- Receipt: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p1/verification-receipt.json`
- Production hashes: `knowledge_read.py=f44080fe...3981`,
  `knowledge_read_isolated.py=60d0de62...2d50`
- Final review: zero Critical/Important; exact evidence/hash and shared-institution-alias test gaps
  were repaired and re-reviewed.
- No task/acceptance checkbox, provider, database/index/source, active pointer, Commit, Push, PR,
  archive, promotion, or Cutover changed.

## Rollback note

Remove the S8P1 factory, optional release-binding trace, two tests/fixture additions, and S8P1-only
evidence. The Accepted S8L1/S8L2 adapters, existing ephemeral planner, external state, and task ledger
need no rollback.
