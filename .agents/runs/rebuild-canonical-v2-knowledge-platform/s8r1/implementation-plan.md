# S8R1 Release-scoped Technology Relationship Traversal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:test-driven-development` for the
> RED/GREEN sequence and `superpowers:verification-before-completion` before Candidate/Accepted
> claims. Execute inline with one writer because both production files and the owner test are shared
> with prior S8 slices. Do not Commit.

**Goal:** Execute the accepted Product-to-Technology relationship graph as a release-bound
Technology-route-to-Company retrieval lane without adding storage, public domains, or capability
inference.

**Architecture:** Deepen the existing `KnowledgeRead` module. A relationship-only request carries
the accepted planner path plus its Technology reference query. The isolated adapter reuses the S7K
relationship pair and existing index/internal replay authority, reconstructs the exact evidence
chain in memory, and emits content-bound Company candidates whose claims remain Product-scoped. The
release wrapper replays and checks the result after the unchanged execution/fusion machinery.

**Tech Stack:** Python 3.12, Pydantic v2 contracts, pytest, uv, Ruff, Pyright, OpenSpec.

---

## File map

- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`:
  one strict S8R1 vertical owner plus the smallest reusable eligibility/bundle fixture parameters.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`:
  omission-preserving relationship request fields, relationship trace, and explicit traced-output
  validation.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`:
  relationship replay authority, adapter, composition wiring, and release-bound postvalidation.
- Update only after Candidate review:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`,
  `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`,
  `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`,
  `.agents/portfolio.md`, and the code-grounded mainline plan.
- Create after final verification:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r1/verification-receipt.json`.

## Task 1: Review and freeze the contract

- [x] Dispatch one independent contract/deep-module review and one independent test-feasibility
  review against the Specified contract, current source, and S7K/S8 predecessors.
- [x] Repair only Critical/Important findings. Record nonblocking Minor/YAGNI without adding new
  acceptance gates.
- [x] Mark the Slice Contract `Ready` only after both reviews report zero open Critical/Important.
- [x] Re-run strict OpenSpec validation before changing tests:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
```

Expected: exit `0`.

## Task 2: Write and observe the exact RED

**Test file:**
`apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Add `_MissingIsolatedRelationshipLookupAdapter` and a resolver that checks, before fixture
  acquisition, exactly:

```python
required_lane_fields = {"relationship_paths", "relationship_reference_queries"}
required_symbols = {
    "create_isolated_relationship_lookup_adapter",
    "LocalRelationshipTrace",
}
```

- [x] Add
  `test_s8r1_release_scoped_technology_relationship_traversal`. Build a real S7K bundle from
  `_technology_relationship_authority`, a matching `IndexProjectionRequest`, an empty release-owned
  institution catalog, the real release-bound planner, and a relationship+Web plan. Do not provide a
  positive relationship adapter from the test.
- [x] Keep exact RED ordering by declaring only `request: pytest.FixtureRequest` on the test and
  resolving the S8R1 symbols before lazily acquiring `tmp_path` and `monkeypatch` through
  `request.getfixturevalue(...)`.
- [x] Freeze these observable families in the one owner group:

  - request propagation/omission and legacy LaneRequest hash compatibility;
  - all three current relationship states and exact Product claim shape;
  - authoritative-zero versus legacy-zero behavior;
  - path/query/release/as-of/type/decision/evidence/anchor/Product/Company/eligibility negatives;
  - admitted-with-nonempty-limitations and path-specific excluded Company eligibility (no
    fabricated limited/review fixture);
  - hostile post-delegate relationship/fusion/handle output;
  - zero Product capability and zero physical relationship read.

- [x] Verify the unchanged literal baseline first:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8v2_absent_selector_preserves_literal_legacy_payloads_and_hashes -q
```

Expected: exactly `1 passed`.

- [x] Run normal RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r1_release_scoped_technology_relationship_traversal -q
```

Expected: exactly one strict xfail and no fixture/target acquisition.

- [x] Run forced RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider --runxfail \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r1_release_scoped_technology_relationship_traversal -q
```

Expected: exactly one failure at `_MissingIsolatedRelationshipLookupAdapter`; no later assertion or
fixture failure.

## Task 3: Carry the relationship request and trace

**Production file:** `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`

- [x] Add the two default-empty fields and omit them from serialized identity when empty:

```python
class LaneRequest(_ContentModel):
    # existing fields remain unchanged
    relationship_paths: tuple[RelationshipPathProposal, ...] = ()
    relationship_reference_queries: tuple[InternalReferenceQuery, ...] = ()
```

The model validator permits non-empty values only on `lane == "relationship"`, requires their
query releases to match the request, and forbids public-population or non-Technology reference
queries. `_lane_request` copies `plan.relationship_paths` plus only the plan's
`reference_type == "technology_route"` queries to the relationship lane; every other lane receives
empty tuples.

- [x] Add `LocalRelationshipTrace` to the `LocalEvidenceTrace` discriminated union. Its public
fields implement the exact lineage axes frozen in the Slice Contract, with
`path="relationship_traversal"` and `execution_lane="relationship"`. The trace validator derives
`raw_candidate_id`, `evidence_id`, and `content_sha256` using `_canonical_sha256`, rejects a
non-Product subject, rejects a relationship status/type mismatch, requires sorted unique lineage,
and requires visible limitations for `limited` eligibility.
- [x] Update `_local_projection_locator` with an explicit `LocalRelationshipTrace` branch using the
canonical relationship ID. Do not add `document_id` or `point_id` to the relationship trace.
- [x] Add explicit traced relationship branches to `_valid_local_projection_item` and
`_valid_local_projection_candidate`. Require request/trace hash equality, exact Product claim,
Company locator identity, relationship state, anchor IDs, eligibility limitations plus any exact
snapshot flag, and one lane/candidate/evidence identity. Preserve the existing `trace is None`
compatibility path for S8RF/S8RG.
- [x] Re-run the literal baseline and normal RED. The baseline remains `1 passed`; the RED remains
the same direct missing-factory xfail because no isolated adapter exists yet.

## Task 4: Build the in-memory relationship authority and adapter

**Production file:** `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`

- [x] Add `_RELATIONSHIP_ADAPTER_VERSION = "canonical-v2-isolated-relationship-v1"` and include
`"relationship"` in the isolated execution-lane type only after its adapter is installed.
- [x] Add `_RelationshipAuthority` containing the validated S7K request/result, replayed complete
candidate result, and reused `_InternalReferenceAuthority`. Construction performs exact typed copies,
replays the installed relationship projector, replays `compose_candidate_projections` from the
relationship internal pair, and requires complete equality with
`internal_authority.index_request.candidate_projection_result`.
- [x] Validate a relationship request as exactly one frozen path and exactly one Technology query:

```text
technology_company_relationship / technology_to_company /
technology_route -> company
```

Require one selected route, the three exact relationship states, relationship evidence required,
definition evidence retained, no state promotion, exact alias/route identity, and one release. Also
require a non-null timezone-aware query `as_of`, a non-null enumeration policy, and exact
`scope == enumeration_policy.scope` plus `as_of == enumeration_policy.as_of` before delegate/Web
effects.
- [x] Reconstruct each result only from `current_relationships`. Resolve and compare the exact
relationship type/version, candidate outcome, accepted typed decision, retained reference, public
SourceAssertion/source record, Technology route/anchor, Product typed subobject, root Company, and
Company `verified_relationship_traversal` eligibility decision. Derive the raw Company ID only from
the Technology anchor, use it to locate the Product/Company/eligibility authorities, and separately
require the source endpoint parent to equal `f"canonical:company:{root_company_id}"` without parsing
that endpoint. Return `admitted` and copy its exact limitations; retain defensive typed `limited`
support without claiming the complete Accepted S7 public graph can produce it; a path-specific
`excluded` result emits no candidate. `DomainInclusionResult` forbids limited inclusion, and S7 path
quality signals remain `PolicyOutcome.admitted` with visible nonempty limitations. Do not invent a
limited or `review` fixture or reopen Accepted S7 semantics.
- [x] Select the Technology anchor from the route projection's exact `source_anchor_ids` and require
  its `technology_source_identity_id`, Product/root IDs, and source record to match. Enforce
  `retained.source_record_ref == source_assertion.source_record_id` and membership in
  `anchor.source_record_ids`. Resolve retained references only from the current relationship's
  `selected_evidence_refs`; do not interpret the candidate outcome's typed-assertion ID as a retained
  reference ID.
- [x] Build one relationship trace/evidence/candidate per admitted current relationship. Keep the
claim subject equal to the Product stable reference and use Company identity only for the displayed
object. Sort deterministically before `max_candidates`. The real-planner/public-execute positive uses
equal time. For a later direct-adapter request or fully revalidated wrapper-plan copy, append the
relationship result timestamp in canonical UTC `Z` form; the frozen fixture's exact flag is
`relationship_snapshot_as_of:2026-07-13T17:00:00Z`. Earlier/later tests update query and
enumeration-policy `as_of` coherently, and also plan/enumeration timestamps for wrapper execution;
reject an earlier query.
- [x] Expose only:

```python
def create_isolated_relationship_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    index_projection_request: IndexProjectionRequest,
    release_institution_catalog: InstitutionCatalog,
) -> Callable[[LaneRequest], RetrievalLaneResult]: ...
```

The returned adapter validates the request before building output and performs no physical lookup.

## Task 5: Wire release composition and postvalidation

**Production file:** `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`

- [x] In `create_isolated_release_knowledge_read`, build `_RelationshipAuthority` only when the S7K
  pair and the exact index/catalog pair are both present. Add the relationship adapter and supported
  lane only in that case. An authoritative-zero pair is installed; legacy no-pair remains
  unsupported.
- [x] Before delegate/Web execution, require the relationship query's scope, `as_of`, and enumeration
  identity to equal the release-bound plan's corresponding identity. A coherently changed direct
  adapter request remains valid; a wrapper plan must change both levels coherently.
- [x] Extend `_ReleaseBoundKnowledgeRead` with optional relationship authority. Before delegate
  execution, validate the relationship LaneRequest whenever the plan contains the lane. After
  delegate execution, rebuild expected in-memory relationship output and compare every observed
  relationship evidence item, raw candidate disposition, auxiliary trace/state, fused Company
  identity/display/evidence/identity-kind/resolution, and canonical handle. Require every expected
  relationship raw ID, evidence ID, and `LocalRelationshipTrace` to belong to exactly one
  authoritative fused Company and canonical handle; allow unrelated other-lane output and
  other-lane evidence on that legitimate Company. Reject unexpected Product-capability evidence.
- [x] Build every hostile delegate object with `model_validate` and recompute content-derived trace,
  candidate, and evidence identities. Do not use unchecked `model_copy(update=...)` as evidence that
  a bypass is model-valid.
- [x] Do not call `_read_bound_documents`, a relationship repository, Web, or provider from
  authority construction or relationship postvalidation.
- [x] Run focused GREEN with warnings as errors:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r1_release_scoped_technology_relationship_traversal -q
```

Expected: exactly `1 passed`.

## Task 6: Proportional regression and static verification

- [x] Run the corrected exact predecessor matrix (the original shorthand omitted valid owners):

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k 'release_bundle_binds_exact_relationship_publication_authority_before_effects or release_scoped_query_planner or s8p2_release_bound_planner or s8e1_release_bound_knowledge_read or release_scoped_exact_lookup or release_scoped_structured_lookup or s8l3_release_scoped_lexical or s8v1_release_scoped_vector or s8v2_ or s8ir1_release_scoped_internal_reference or s8r1_release_scoped_technology_relationship' -q
```

Record actual pass/skip counts.

- [x] Run the complete physical/release owner:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py -q
```

- [x] Run the relationship pure owner and release-publication owner:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_relationship_projection_contract.py \
  tests/canonical_v2/test_release_publication_interface.py -q
```

- [x] Run all KnowledgeRead/query-planning owners and the complete no-external Canonical V2 suite
using the exclusions already recorded in the verification contract. Every pytest invocation must
retain `-o addopts='' -p no:cacheprovider`; record the exact collection/pass/skip/warning counts.
- [x] Run Ruff check/format check, changed-file `py_compile`, complete Canonical V2 Pyright, strict
OpenSpec, and `git diff --check`. Build the locked offline wheel, prove the two production source
hashes equal their wheel entries, and prove tests/`.agents` are absent.
- [x] Recheck original Milvus SHA-256, original `pgtest` paused state/volume identity, recovery-lab
network/ports/restart policy, active pointer state, S7K pair hashes, and exact worktree branch/HEAD.
- [x] Remove only S8R1-owned generated wheel/temp/cache outputs after the receipt records their
hashes. Do not clean unrelated/user files.

## Task 7: Independent implementation review and acceptance

- [x] Dispatch one independent implementation review against the Ready contract and current diff.
- [x] For each Critical/Important finding, first add or extend a failing regression inside the S8R1
owner, observe the expected RED, repair the implementation, rerun focused GREEN, then request one
targeted re-review. Record Minor/YAGNI without blocking unless escalation rules apply.
- [x] After zero open Critical/Important, rerun every Required check whose input changed.
- [x] Write the secret-free verification receipt with exact commands/outcomes, current hashes,
review findings, cleanup proof, frozen-target proof, and forbidden actions list.
- [x] Synchronize verification/change-log/agent-links/portfolio/mainline-plan evidence, mark S8R1
Accepted, and keep `tasks.md`, `acceptance.md`, and formal `56/80` unchanged.
- [x] Return to the outer mission loop and perform a fresh dependency audit for the next smallest
real Task 8.3 relationship family. Do not stop or mark the persistent goal complete/blocked merely
because S8R1 is Accepted.

## Rollback checkpoint

Rollback is file-local: remove the S8R1 additions from the two read modules and owner test, then
remove only S8R1 evidence. No database/index/source/pointer rollback exists because this Slice owns
no external mutation. Checkpoints are file hashes and the dirty-worktree diff; commits are forbidden.
