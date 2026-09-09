# S8P1 Release-bound Query Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use the active OpenSpec contract and
> `superpowers:test-driven-development`; execute inline in the current authorized worktree because
> shared fixture/public-type edits require one writer. Do not commit.

**Goal:** Build one package-internal query planner whose institution, Person, and Technology inputs
are proven to come from the exact accepted S7 release graph rather than caller-injected same-release
records.

**Architecture:** Extend the existing isolated read adapter module with one factory. It revalidates
and replays the full `IndexProjectionRequest`, validates the release institution catalog against
observed typed projections, derives internal reference records from the replayed S6R graph, then
delegates to the existing ephemeral planner. A compact optional content-bound trace records the
release lineage while preserving the prior serialized/hash shape when absent.

**Tech Stack:** Python 3.12, Pydantic v2 immutable contracts, pytest strict xfail RED/GREEN,
Canonical V2 S6R/S7 projection builders, Ruff, Pyright, OpenSpec.

---

### Task 1: Freeze the two exact RED groups over one real combined S7 graph

**Files:**

- Modify: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] **Step 1: Add the exact missing-symbol sentinel and lazy resolver**

  Add `_MissingIsolatedReleaseQueryPlannerFactory` beside the S8L1/S8L2 sentinels. Add
  `_isolated_release_query_planner_factory()` that first imports the existing isolated module and
  then returns `create_isolated_release_query_planner`; only an `AttributeError` whose name exactly
  matches that symbol becomes the sentinel. Nested import failures and other missing attributes
  propagate.

- [x] **Step 2: Build the combined graph through real existing builders**

  Extract one test helper for the existing Company Product plus the three Technology relationship
  assertions. Give `_resolved_person_graph` an opt-in `include_technology_anchor=False` parameter.
  Only when true, add:

  ```python
  geography = {"reference_id": "geography:shenzhen", "name": "深圳"}
  product = _typed_member(..., field_path="product", subobject_id="product:robot-arm", ...)
  professor education name = "南方科技大学"
  company education name = "SUSTech"
  ```

  plus the same content-bound Product and Technology relationship assertions consumed by
  `_technology_graph`. Include the two existing real unresolved `Wei Zhang` Paper-author/Patent-
  inventor references in this opt-in graph with distinct source/reference IDs so the combined
  identity run contains both resolved and unresolved Person outcomes. Add
  `_resolved_person_technology_candidate_bundle()` that combines this one public graph and Person
  identity result with the real Technology identity request/result/locators, invokes
  `InternalReferenceProjectionBuilder.project`, then invokes the real candidate composer. Do not
  merge two completed Pydantic results.

- [x] **Step 3: Make the physical release fixture use and expose the combined request**

  Parameterize `_task7_7_release_values` with an optional candidate-bundle factory whose default
  remains `_resolved_person_candidate_bundle`; do not change S7H rehearsal inputs globally. Only
  `isolated_lookup_target_bundle` supplies `_resolved_person_technology_candidate_bundle`. Add the
  exact `IndexProjectionRequest` under `fixture["index_request"]`. Keep all existing dynamic
  manifest, index, point, lookup, and release assertions unchanged.

- [x] **Step 4: Add the positive release-bound vertical test**

  Resolve the factory before acquiring the fixture. Create one active `PublishedRelease`, an
  `InstitutionCatalog` entry with canonical name `南方科技大学` and observed alias `SUSTech`, and a
  four-public-domain/supported-lane `QueryPlanningPolicy`. Use a recorded proposal for an information
  query containing `SUSTech毕业`, `深圳企业`, `创始人`, and `vision servo` with representative
  enumeration. Assert exact release-binding hashes, resolved institution ID, typed Person facts and
  evidence, eligible resolved Person, accepted route ID/alias/definition evidence, non-public
  internal reference queries, explicit unresolved/ineligible Person traces, stable plan identity,
  and legacy no-binding serialization.

- [x] **Step 5: Add the fail-before-provider crosswire test**

  Resolve the factory before acquiring the fixture. Use a provider that increments a counter then
  raises. Cover cross-release publication/request, same-release Person-only request, same-release
  Technology-only request, missing/invented institution names, fifth public domain, unsupported
  lane, stale `BuildManifest.manifest_sha256`, and same-class content tampering. Assert the counter
  remains zero for every case and the exact rejection category identifies release, graph, catalog,
  manifest, or policy rather than provider behavior.

- [x] **Step 6: Mark only the two new tests strict xfail**

  Use `pytest.mark.xfail(raises=_MissingIsolatedReleaseQueryPlannerFactory, strict=True, ...)` on
  those two functions. Resolve the factory before all fixture access so their RED cannot be caused by
  physical setup.

### Task 2: Prove the exact RED and fixture compatibility

**Files:**

- Test: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] **Step 1: Run focused normal RED**

  Run:

  ```bash
  uv run pytest -n0 tests/canonical_v2/test_internal_reference_projection_contract.py \
    -k 'release_scoped_query_planner' -q --no-cov
  ```

  Expected: exactly `2 xfailed, 46 deselected`, no fixture creation/output failure.

- [x] **Step 2: Run forced RED**

  Run the same command with `--runxfail`.

  Expected: exactly `2 failed, 46 deselected`; both traces terminate directly at
  `_MissingIsolatedReleaseQueryPlannerFactory` for the exact symbol.

- [x] **Step 3: Run the unchanged shared owners while RED remains**

  Run the shared file excluding the two new names.

  Expected: `44 passed, 2 skipped, 2 deselected`; the combined fixture is valid through existing
  S6R/S7/S8L1/S8L2 behavior before production planner work begins.

### Task 3: Add the optional content-bound release trace without changing legacy plans

**Files:**

- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] **Step 1: Add `PlanningReleaseBinding`**

  Define a `_ContentModel` with these exact fields:

  ```python
  release_id: str
  publication_state: Literal["active", "rolled_back"]
  published_release_sha256: str
  publication_verification_evidence_ids: tuple[str, ...]
  manifest_sha256: str
  index_projection_request_sha256: str
  index_projection_result_sha256: str
  candidate_projection_result_sha256: str
  internal_reference_projection_result_sha256: str
  institution_catalog_sha256: str
  planning_policy_sha256: str
  ```

  Apply non-empty/SHA patterns where existing local contracts do. Add
  `RetrievalPlan.release_binding: PlanningReleaseBinding | None = None`.

- [x] **Step 2: Preserve legacy serialization and content identity**

  Before production editing, freeze one representative current ephemeral plan's exact serialized
  JSON and `content_sha256` as RED test constants. Add one `RetrievalPlan` wrap serializer that
  removes only `release_binding` when it is `None`. The inherited `_ContentModel` hash calculation
  then sees the historical payload for unbound plans and includes the complete binding for release-
  bound plans. The positive test compares the post-change legacy plan to the frozen constants and
  proves a bound plan changes when any binding identity changes.

  The frozen pre-change values are:

  ```text
  content_sha256 = c89a484f9a7fb39ff604859545d98ee76daac77346ab12b589b68d06b45d5675
  serialized JSON SHA-256 = e25a67563bd026475affcfc5a7bc20938c860a65dfb764f4da54a5a36bb0fefb
  ```

  They come from the plan fixture named `s8p1-legacy-snapshot` at
  `2026-07-16T06:30:00Z`; the RED test independently reconstructs that exact plan and checks both
  values before resolving the missing isolated factory.

- [x] **Step 3: Make Person education resolution catalog-driven**

  Replace the name-specific `南方科技大学毕业` branch with a helper that maps resolved institution
  slots to their catalog canonical names when the query expresses an education/graduation filter.
  Preserve founder and Shenzhen typed-filter behavior. Existing synthetic owner fixtures must pass
  an explicit catalog entry if required; do not add institution names/aliases to generic topic
  stopwords or production constants.

- [x] **Step 4: Enforce binding/plan cross-field consistency in the model**

  Extend the existing `RetrievalPlan` validator: when `release_binding` exists, its `release_id`
  equals `plan.release_id`; every institution slot and lane query uses the bound release/catalog;
  and every internal-reference query uses the bound release while remaining non-public. Add model-
  level negative assertions that rebuild otherwise content-valid payloads with those cross-wires and
  fail validation. Unbound legacy plans retain existing behavior.

### Task 4: Implement the isolated release-bound planner factory

**Files:**

- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`

- [x] **Step 1: Revalidate inputs before any provider call**

  Require exact instances and JSON round-trip validation for `IsolatedReleaseBundle`,
  `PublishedRelease`, `IndexProjectionRequest`, `InstitutionCatalog`, `QueryPlanningPolicy`, and
  optional `AmbiguityPolicy`. Reuse `_validated_release_binding`. Require exactly the four public
  domains, unique supported lanes, and no lane outside the existing server registry.

- [x] **Step 2: Replay and compare the complete S7 graph**

  First recompute `BuildManifest.manifest_sha256` from every field except the stored hash and reject
  stale same-class manifest values. Invoke
  `create_ephemeral_index_projection_builder().build(validated_index_request)`. Require exact
  equality with `validated_bundle.index_result`; require candidate/internal request-result release
  and projection-sub-run continuity, manifest published projections, and internal/public projection
  hashes to agree. Do not equate the manifest's top-level `KnowledgeBuild` run ID with the nested
  projection sub-run ID. Raise one narrow release-graph integrity error before constructing the
  delegated planner.

- [x] **Step 3: Validate the institution catalog against observed typed projections**

  Collect ID/name pairs only from typed institution-bearing fields and references whose namespace
  is `institution:`: Company personnel education, Professor affiliation/education, Paper author
  affiliations, and Patent inventor affiliations.
  Require the catalog ID set to equal observed IDs and each `{canonical_name, *aliases}` set to equal
  the observed names for that ID. Reject duplicates, invented aliases, and missing names. Permit a
  label observed under more than one ID so accepted ambiguous aliases remain representable.

- [x] **Step 4: Derive Person records**

  Join each resolved/unresolved Person reference to its exact `PublicDomainEvidenceAnchor` and typed
  root/subobject. Aggregate each resolved Person projection into one record. Derive education using
  the validated catalog canonical name, Company roles using normalized typed role values, and
  Company geography using the root projection's geography evidence. Merge duplicate facts only by
  exact `(field, value)` and sort/uniquify evidence IDs. Emit each unresolved reference separately
  with no canonical identity and no identity-eligible facts. Because the accepted flat fact record
  has no Company scope key, suppress geography when one Person spans multiple Company roots instead
  of creating a cross-Company role/geography Cartesian match.

- [x] **Step 5: Derive Technology route records**

  Convert every accepted route projection to one deterministic derived record using its canonical
  Technology identity, preferred name, aliases, release, and definition field-lineage assertion IDs.
  Bind the complete source projection set through
  `PlanningReleaseBinding.internal_reference_projection_result_sha256`; do not pretend the reduced
  record hash is the source projection hash. Do not infer adoption/capability or promote Technology
  into `domains`.

- [x] **Step 6: Construct and wrap the existing planner**

  Compute `PlanningReleaseBinding` from the revalidated values. Construct the existing ephemeral
  planner with only the derived Person/Technology records and validated catalog/policy. Wrap its
  `plan` method so request type/release is revalidated before provider invocation, base plan release
  must agree, and the returned `RetrievalPlan` is revalidated with the exact binding.

### Task 5: Remove the RED wrappers and reach focused GREEN

**Files:**

- Modify: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`
- Modify only if necessary: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_query_planning_contract.py`

- [x] **Step 1: Run forced tests before removing wrappers**

  Run focused `--runxfail`; both tests must now pass. If either fails, fix production code rather
  than weaken the asserted graph/catalog/release behavior.

- [x] **Step 2: Remove only the two strict xfail decorators**

  Keep sentinel/resolver integrity helpers as regression documentation unless Ruff proves them dead;
  do not alter prior accepted assertions.

- [x] **Step 3: Run focused and sibling GREEN**

  Run the two S8P1 tests, S8L1, S8L2, the complete shared file, the four query-planning owners, and
  the 16 KnowledgeRead owners. Expected counts are the Slice Contract values; record actual counts.

- [x] **Step 4: Refactor only after GREEN**

  Remove duplicate sorting/hash/lookup code inside the new factory, keep helpers private and
  responsibility-focused, then rerun the focused/shared/query-owner tests.

### Task 6: Verification, one review, and acceptance persistence

**Files:**

- Create after checks: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8p1/verification-receipt.json`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8p1-release-bound-query-planner-green.md`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`
- Modify after review: `.agents/portfolio.md`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/code-grounded-mainline-plan-2026-07-13.md`

- [x] **Step 1: Run proportional regression and static checks**

  Run complete no-external Canonical V2, changed-file Ruff check/format, `py_compile`, complete
  Canonical V2 Pyright, strict OpenSpec, and `git diff --check`. Record exact commands, exit codes,
  counts, and warnings.

- [x] **Step 2: Run package and frozen-boundary checks**

  Build a locked offline wheel, verify both read modules are present and tests/`.agents` are absent,
  compare wheel source hashes to the worktree, scan changed scope for secrets/generated caches, and
  re-check original Milvus hash plus frozen Postgres/recovery identities without opening or writing
  them.

- [x] **Step 3: Request one merged independent review**

  Review against this exact contract for Spec coverage, model-valid bypasses, test integrity, scope,
  evidence lineage, release consistency, no-fifth-domain/Product boundary, provider-before-validation
  order, and unnecessary abstraction. Repair Critical/Important findings only, add regression tests
  first, and re-review only those repairs. Record Minor/YAGNI without blocking.

- [x] **Step 4: Persist acceptance atomically**

  Write a secret-free receipt with current hashes/results. Mark S8P1 `Accepted` only after every
  Required check and zero Critical/Important review findings. Update verification/change-log/links/
  portfolio/mainline plan consistently. Leave `tasks.md`, `acceptance.md`, and the `55/80` ledger
  unchanged; identify S8P2 as the next Ready slice. Do not Commit, Push, PR, Archive, promote, or
  Cutover.
