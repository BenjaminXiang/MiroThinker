# S8L1 Release-Scoped Exact Lookup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect one serviceable, release-matched S7 isolated release bundle to the existing S8RG
exact lane with typed local projection/evidence traceability and no writes.

**Architecture:** Add one package-internal adapter factory in `knowledge_read_isolated.py`. It
revalidates `PublishedRelease` and `IsolatedReleaseBundle`, reads through the real S7 immutable
lookup reader, requires exact physical-versus-bundle document equality, revalidates public typed
projection content, performs bounded exact matching over the unique validated lane-query text, and
returns normal `RecallCandidate` values. The existing `KnowledgeRead` remains the only public
orchestrator; additive internal request/trace fields carry plan constraints and content-bound S7
lineage.

**Tech Stack:** Python 3.12, Pydantic v2 immutable contracts, SQLite immutable readback through S7,
pytest, Ruff, Pyright, OpenSpec.

---

### Task 1: Freeze the real release-scoped exact adapter contract

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [ ] **Step 1: Extract the existing real S7 target setup without changing its assertions**

Create a module-scoped `isolated_lookup_target_bundle` fixture with `tmp_path_factory`. Move only the
current candidate/request/target/builder/build setup from
`test_index_projection_performs_full_readback_on_marked_isolated_target` into the fixture and return
the validated `IsolatedReleaseBundle`, `result`, `receipt`, original Milvus identity/hash, and target
file hashes. Use S7I's accepted helper option to give `company-robotics` one exact-path limitation,
then keep every existing S7 assertion in that test and make it consume the fixture.

- [ ] **Step 2: Add one strict missing-boundary vertical RED group**

Add an exact import helper for
`src.data_agents.canonical_v2.knowledge_read_isolated` that converts only a direct target
`ModuleNotFoundError` into `_MissingIsolatedKnowledgeReadModule`; nested dependency errors propagate.
Mark the new test strict-xfail only while the target is absent. Import the target before calling
`request.getfixturevalue("isolated_lookup_target_bundle")`, so the missing-module RED does not build
the physical fixture.

The group constructs an active `PublishedRelease`, composes the future adapter through
`create_ephemeral_knowledge_read(lane_adapters={"exact": adapter})`, and executes an information-
retrieval plan with an explicit Company name and a recorded empty Web adapter. Assert one selected
Company, exact target/document/release/projection/content/source-evidence lineage, local source
nature, correct candidate disposition, eligibility limitation retention, no internal auxiliary,
and unchanged input/index bytes. In the same group directly exercise the fail-closed cases with:

```python
wrong_release = published.model_copy(
    update={
        "release_id": "cross-release-r0",
        "canonical_release_id": "cross-release-r0",
        "published_projection_release_id": "cross-release-r0",
        "index_release_id": "cross-release-r0",
    }
)
unmarked = release_bundle.model_copy(
    update={"index_target": target.model_copy(update={"root": unmarked_root})}
)
internal_id = next(
    item.canonical_object_id
    for item in result.lookup_documents
    if item.projection_scope.value == "internal_auxiliary"
)
```

Assert wrong/model-invalid publication rejects before the unmarked root is read; a same-release
`rolled_back` publication remains readable; a model-valid bundle snapshot that differs from the
physical readback is rejected; same-release unmarked target fails its real marker check; and querying
`internal_id` on the public exact adapter returns no candidate.

- [ ] **Step 3: Prove exact RED**

Run from `apps/miroflow-agent`:

```bash
uv run pytest -n0 -q --tb=short \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k 'release_scoped_exact_lookup'
uv run pytest -n0 -q --tb=short --runxfail \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k 'release_scoped_exact_lookup'
```

Expected: normal execution is exactly `1 xfailed`; forced execution is exactly `1 failed` at the
direct `_MissingIsolatedKnowledgeReadModule` sentinel. The fixture must not be acquired during RED.

### Task 2: Carry exact-lane constraints and structured local lineage

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [ ] **Step 1: Add the optional local projection trace**

Add this immutable model immediately before `EvidenceItem` and an optional field on the evidence:

```python
class LocalProjectionTrace(ContractModel):
    target_id: str
    target_marker_sha256: str
    manifest_sha256: str
    index_result_content_sha256: str
    document_id: str
    canonical_object_id: str
    release_id: str
    domain: str
    projection_id: str
    projection_scope: Literal["public_domain"]
    path: Literal["exact_lookup"]
    projection_view: str
    projection_version: str
    schema_version: str
    eligibility_policy_version: str
    eligibility_decision_id: str
    eligibility_outcome: Literal["admitted", "limited"]
    eligibility_limitations: tuple[str, ...]
    source_projection_content_sha256: str
    lookup_content_sha256: str
    source_evidence_ids: tuple[str, ...]
    publication_verification_evidence_ids: tuple[str, ...]
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = "0" * 64


class EvidenceItem(ContractModel):
    # existing fields unchanged
    local_projection_trace: LocalProjectionTrace | None = None
```

- [ ] **Step 2: Validate and pass only existing plan-owned exact inputs through `LaneRequest`**

In `RetrievalPlan.validate_ambiguity_execution_gate`, require `lane_queries` to have unique lanes,
the plan release, and lanes already present in `plan.lanes`. Add `query_text`, `domains`,
`protected_slots`, `structured_constraints`, and `max_candidates` to `LaneRequest`. Select the unique
matching lane query and otherwise fall back to the original query:

```python
class LaneRequest(_ContentModel):
    lane: str
    release_id: str
    query_view: str
    original_query: str
    behavior_class: str
    interaction_mode: str
    web_policy: WebSearchPolicy
    query_text: str
    domains: tuple[str, ...]
    protected_slots: tuple[ProtectedSlot, ...]
    structured_constraints: StructuredConstraints
    max_candidates: int = Field(ge=0)


def _lane_request(plan: RetrievalPlan, lane: str, web_policy: WebSearchPolicy) -> LaneRequest:
    lane_query = next((item for item in plan.lane_queries if item.lane == lane), None)
    return LaneRequest(
        lane=lane,
        release_id=plan.release_id,
        query_view="view:original",
        original_query=plan.original_query,
        behavior_class=plan.behavior_class,
        interaction_mode=plan.interaction_mode,
        web_policy=web_policy,
        query_text=(lane_query.query_text if lane_query is not None else plan.original_query),
        domains=plan.domains,
        protected_slots=plan.protected_slots,
        structured_constraints=plan.structured_constraints,
        max_candidates=plan.max_candidates,
    )
```

- [ ] **Step 3: Run the existing KnowledgeRead owners**

```bash
uv run pytest -n0 -q --tb=short \
  tests/canonical_v2/test_knowledge_read_atomic_green_contract.py \
  tests/canonical_v2/test_knowledge_read_interface.py \
  tests/canonical_v2/test_knowledge_query_planning_contract.py \
  tests/canonical_v2/test_knowledge_read_universal_web_contract.py \
  tests/canonical_v2/test_knowledge_read_sufficiency_retry_contract.py \
  tests/canonical_v2/test_knowledge_read_retrieval_fusion_contract.py
```

Expected: exactly `16 passed`, with no xfail/XPASS/skip.

### Task 3: Implement the package-internal exact adapter

**Files:**
- Create: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`
- Test: `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [ ] **Step 1: Revalidate publication/target before any read**

Implement `create_isolated_exact_lookup_adapter` so construction revalidates both same-class values,
accepts the two model-valid serviceable states (`ReleaseState.active` and
`ReleaseState.rolled_back`), and requires exact equality of publication canonical/published/index
IDs and `release_bundle.release_id`. A hostile same-class value with any other state or parity must
fail revalidation. Capture only validated copies in the closure. On every call, use the real reader
and require its tuple to equal `release_bundle.index_result.lookup_documents` before mapping.

- [ ] **Step 2: Revalidate public typed lookup content and match exact terms**

Map `company`, `paper`, `patent`, and `professor` to their existing typed projection models. For each
public lookup document, validate `lookup_content`, then require document/projection equality for
canonical object ID, release, domain, and source projection content hash. Extract:

```python
display terms = {
    company: name + aliases,
    paper: title + title_zh,
    patent: title + title_en,
    professor: name + canonical_name_zh + canonical_name_en + aliases,
}
identifier terms = canonical object/id plus Company credit code, Paper DOI/arXiv/identifier values,
Patent number, and Professor id.
```

Require all protected `explicit_name` and `exact_identifier` slots to match the corresponding term
family. When neither family exists, require normalized `request.query_text` to equal one complete
accepted display/identifier term. Apply displayed-set and excluded-term structured constraints,
filter by request domains, keep deterministic `(domain, canonical object, document)` order, and
apply `max_candidates`.

- [ ] **Step 3: Map every admitted document to normal candidate/evidence contracts**

Create candidate and evidence IDs from the complete bundle/document/eligibility lineage. Emit one
`canonical_projection` binding; exact names/identifiers are server-side match inputs rather than
invented factual assertions. Every item uses `source_nature="local"`, a target/document locator, the
immutable lookup JSON as snippet, score `1.0`, and the full `LocalProjectionTrace`. Return one
resolved canonical `RecallCandidate` per document with exact lane, view, attempt, release, adapter
version, the exact source evidence IDs, eligibility limitations as quality flags, and evidence tuple.

- [ ] **Step 4: Remove only the RED wrapper and prove focused GREEN**

```bash
uv run pytest -n0 -q --tb=short \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k 'release_scoped_exact_lookup'
```

Expected: exactly `1 passed`, with no xfail/XPASS/skip.

### Task 4: Verify, review, and accept S8L1 without checking Task 8.3

**Files:**
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8l1-release-scoped-exact-lookup-green.md`
- Add after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8l1/verification-receipt.json`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify after review: `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`
- Modify after review: `.agents/portfolio.md`
- Modify after review: `.agents/runs/rebuild-canonical-v2-knowledge-platform/code-grounded-mainline-plan-2026-07-13.md`

- [ ] **Step 1: Run focused, owner, and complete behavior checks**

Run the focused group, the complete shared S7/S8 test file, the exact 16 KnowledgeRead owners,
and `uv run pytest -n0 -q tests/canonical_v2`. Record actual counts and warnings; expected current
checkpoint is focused `1 passed`, shared file `43 passed, 2 skipped`, owners `16 passed`, and
complete `331 passed, 141 skipped, 0 xfailed`.

- [ ] **Step 2: Run static, strict, package, and frozen-source gates**

Run scoped Ruff check/format, `py_compile` on both production files, complete Canonical V2 Pyright,
strict OpenSpec, and `git diff --check`. Build a fresh locked offline wheel and verify both read
modules are included while tests/`.agents` are excluded. Repeat scope, high-confidence secret,
generated-cache, original Milvus SHA-256, paused original `pgtest` volume, and network-none/no-port
recovery checks used by S9C1.

- [ ] **Step 3: Obtain one merged independent review**

Lock production/test/contract hashes. Review release/state fail-before-read ordering, real S7 reader
use, typed content binding, exact matching, public/internal boundary, evidence trace, fixture
integrity, and scope. Fix only Critical/Important findings and run one targeted re-review. Record
Minor/YAGNI without blocking.

- [ ] **Step 4: Persist acceptance without changing the task ledger**

After zero open Critical/Important findings, mark only S8L1 Accepted; update verification/change-log/
links/portfolio/mainline-plan and the receipt; confirm `tasks.md` remains exactly `55/80`; rerun
strict OpenSpec and `git diff --check`. Do not stage, Commit, Push, open a PR, archive, promote, or
Cutover.
