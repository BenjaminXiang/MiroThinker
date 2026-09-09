# S8R5 Release-scoped Displayed Patent-to-Company Traversal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` after this slice becomes Ready. Use
> `superpowers:test-driven-development` for RED/GREEN and
> `superpowers:verification-before-completion` before Candidate/Accepted claims. Steps use checkbox
> syntax for tracking. One writer owns the two production modules and vertical owner test. Do not
> Commit.

**Goal:** Execute one displayed Patent-to-Company applicant traversal from the Accepted S8R2
release authority through public `KnowledgeRead.execute`.

**Architecture:** Add one finite planner direction and a dedicated public trace for the inverse
view of S8R2's public direction while preserving the canonical Patent-to-Company applicant
orientation. Reuse S8R2's exact in-memory authority and forward replay, return a Company candidate,
and keep the displayed Patent as the only protected source witness.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv, Ruff, Pyright, OpenSpec.

---

## State gate

This plan is **Accepted** at `2026-07-20T09:38:32Z` after Candidate verification and targeted
re-review reported `C=0/I=0/M=0/YAGNI=0`. It became Ready at `2026-07-20T09:00:14Z`; Task 8.3 and
the formal ledger remain unchanged at `56/80`.

- [x] S8R4 contract and receipt both say Accepted.
- [x] One lean S8R5 contract/plan review reports zero open Critical/Important.
- [x] One wording Minor was repaired before Ready; no additional review loop was added.
- [x] Strict OpenSpec validation exits `0`.

No Commit, Push, PR, Archive, promotion, or Cutover step belongs to this plan.

## File map

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`: exact planner path,
  omission-preserving lane policy, dedicated trace, source-witness constraint handling, and local
  trace/fusion/coverage validation.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`: exact request
  validation, S8R2 authority replay into a Company candidate, dispatch, and release pre/
  postvalidation.
- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`:
  one S8R5 vertical owner reusing S8R2 helpers.
- Update only S8R5 receipt/evidence and existing status summaries after Candidate/Accepted evidence
  exists. Keep `tasks.md`, `acceptance.md`, existing slices, and ledger `56/80` unchanged.

## Task 1: Freeze Specified and transition to Ready

- [x] Confirm S8R4 Accepted from both its slice contract and verification receipt; if either is not
  Accepted, stop before code/test edits.
- [x] Review the exact four-axis path, canonical claim, applicant-only role/evidence/subobject,
  source-witness, Web, coverage, zero, and hostile boundaries in the S8R5 contract.
- [x] Repair only Critical/Important contract findings. Record Minor/YAGNI without creating a new
  gate.
- [x] Run:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
```

Expected: exit `0`.

- [x] Mark this contract and plan Ready with the reviewed hashes and UTC timestamp. Do not change
  OpenSpec tasks/acceptance.

## Task 2: Write and observe one exact RED

**Test:**
`apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Add `_MissingS8R5PatentCompanyTraversal` and a seam check requiring
  `LocalPatentCompanyRelationshipTrace` with exact
  `path="patent_company_relationship_traversal"` and `execution_lane="relationship"`.
- [x] Resolve the seam before acquiring `tmp_path`, `monkeypatch`, building a release, or invoking
  any adapter/Web effect.
- [x] Add one strict-xfail owner named:

```python
def test_s8r5_executes_release_scoped_patent_to_company_applicant_traversal(
    request: pytest.FixtureRequest,
) -> None:
    ...
```

- [x] Reuse `_company_patent_relationship_authority`, `_s8r2_index_projection_request`, the S7K
  release helper, and the S8R2 institution catalog. Do not create a second positive authority.
- [x] Build an exact plan with:

```python
RelationshipPathProposal(
    relationship_type_id="company_has_patent",
    direction="patent_to_company",
    source_type="patent",
    target_type="company",
)
```

and `domains=("company",)`, displayed ID `("patent-ada",)`, relationship/Web lanes, and a
representative enumeration policy.
- [x] Run normal RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r5_executes_release_scoped_patent_to_company_applicant_traversal -q
```

Expected: exactly one strict xfail at the S8R5 seam sentinel.

Observed: `62 deselected, 1 xfailed in 2.68s` at the exact missing trace seam.

- [x] Run forced RED:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider --runxfail \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r5_executes_release_scoped_patent_to_company_applicant_traversal -q
```

Expected: exactly one failure at the sentinel before fixture/effect acquisition.

Observed: `1 failed, 62 deselected in 1.27s`; the sole failure was the exact sentinel before
fixture/effect acquisition. After the trace seam existed, the real RED was the exact unsupported
relationship request path (`1 failed, 62 deselected in 3.31s`).

## Task 3: Carry the exact request and trace contract

**Production:**
`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`

- [x] Add `_PATENT_TO_COMPANY_QUERY_PATH` and the exact finite endpoint mapping; keep the planner's
  existing unknown-type, unsupported-direction, and endpoint-drift error categories.
- [x] Add the path to the two exact `relationship_enumeration_policy` allowlists in `LaneRequest`
  validation and `_lane_request`; preserve absent-field serialization for every other lane/path.
- [x] Add a dedicated `LocalPatentCompanyRelationshipTrace`, not a mutation of S8R2's trace. Bind:
  displayed Patent; canonical Patent-to-Company endpoints; exact singleton applicant role; complete
  S8R2 replay lineage; exact PatentApplicant/source record; both directional eligibility results;
  returned Company candidate; canonical claim; quality flags; and distinct content-derived raw/
  evidence IDs.
- [x] Extend `LocalEvidenceTrace`, local locator/item validation, constraint source-witness handling,
  fused-trace agreement, and enumeration ownership for the new trace only.
- [x] Remove the xfail marker only after the trace seam exists, rerun the focused owner, and record
  the next genuine RED. The expected next RED is unsupported request path/dispatch, not a fixture
  or serializer regression.

## Task 4: Implement minimal S8R2 authority reuse

**Production:**
`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`

- [x] Import the exact path constant and trace class.
- [x] Extend `_validate_relationship_request` with one exact Patent-to-Company branch. Require
  `domains=("company",)`, one optional-at-direct/exactly-one-at-public displayed Patent, one equal
  protected set, representative policy/as-of equality, and zero relationship-reference queries.
- [x] Add `_patent_to_company_relationship_candidates` with this bounded algorithm:

```text
1. Validate the displayed Patent public projection and protected source slot.
2. Read current patent_has_applicant relations in authority order whose Patent source is displayed.
3. For each exact Company target, create an internal forward Company-to-Patent LaneRequest.
4. Set that internal replay bound to the finite authoritative current-relationship count, never the
   caller's result cap, then call `_company_to_patent_relationship_candidates`.
5. Keep only the candidate for the displayed Patent.
6. Transform its complete S8R2 trace into LocalPatentCompanyRelationshipTrace.
7. Emit the Company EvidenceItem/RecallCandidate and apply the caller's `max_candidates` only here,
   after exact displayed-Patent filtering.
```

- [x] Preserve the canonical claim exactly as Patent `patent_has_applicant` Company. Do not emit a
  planner alias or reverse predicate.
- [x] Require exact `{"applicant": company_ref}`, `patent_applicant_assertion`, Patent
  `SourceAssertion.field_path="applicants"`, and the exact `PatentApplicant`. Reject
  owner/assignee/inventor/extra roles and all alternate evidence/subobjects.
- [x] Reuse both S8R2 endpoint eligibility pairs, limitations, exclusion behavior, and snapshot flag.
  Perform no physical/store/provider read and add no factory or registry.
- [x] Dispatch only the exact `_PATENT_TO_COMPANY_QUERY_PATH` to this helper.

## Task 5: Extend release-bound validation and the vertical matrix

**Production:**
`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`

**Test:**
`apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`

- [x] Before delegate/Web effects validate the path/lane, Company output domain, displayed Patent,
  protected set, policy/as-of/release authority, and exact lane-request copy.
- [x] After delegate execution rebuild expected local output from `_RelationshipAuthority` and
  require exact raw/evidence/trace ownership, fused Company identity/display, canonical handle,
  constraint receipts, quality flags, and representative coverage.
- [x] Positive assertions must prove: returned `company-robotics`; source witness `patent-ada`;
  canonical type/version/endpoints; exact applicant role; exact retained/public assertion and
  PatentApplicant; both endpoint eligibility results; Company object/fusion/handle; and canonical
  Patent-to-Company claim.
- [x] Add the bounded zero/error matrix:
  authoritative zero; valid Patent without a matching relation; release-unknown direct/public
  source; known wrong-type/internal/missing/multiple/protected-drift public source; excluded/limited
  endpoint; max zero; nonmatching family; earlier/equal/later snapshot; wrong path/domain/lane/
  policy; and zero physical reads.
- [x] Add a multi-Patent ordering regression: the same Company has a non-displayed Patent before the
  displayed Patent in authoritative order and caller `max_candidates == 1`; the displayed Patent
  still returns the Company because internal replay must not consume the caller cap.
- [x] Add hostile cases for owner/assignee/inventor or extra role, wrong evidence kind/field/
  subobject/source record, relation/decision/endpoint cross-wire, altered trace/claim/candidate,
  missing/extra/duplicate evidence ownership, forged handle, cross-lane ID reuse, and exhaustive
  coverage forgery.
- [x] Prove a Web Patent cannot satisfy the displayed source witness or fabricate the relation.
  Allow legitimate same-Company Web evidence to fuse without owning local relationship evidence.
- [x] Reject direct `canonical` Web evidence whose domain/object differs from the returned Company,
  `web_only`/unknown identity states that carry its Canonical ID, and any `web_candidate` claim
  subject bound to another Canonical Company. Preserve a legitimate same-Company
  evidence-subject alias through fusion.
- [x] Run focused GREEN with warnings as errors:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider -W error \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k s8r5_executes_release_scoped_patent_to_company_applicant_traversal -q
```

Expected: exactly `1 passed` for the focused owner.

Observed final: `1 passed, 62 deselected in 8.45s` with warnings as errors. Candidate review added
the authoritative-cap ordering, same-Company Web alias, direct Canonical object crosswire, and
other-Canonical-Company subject regressions; targeted re-review then reported zero findings.

## Task 6: Proportional verification and acceptance

- [x] Run the exact relationship predecessor matrix:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  -k 's8r1_relationship_request_and_trace_literal_compatibility or s8r1_release_scoped_technology_relationship or s8r2_executes_release_scoped_company_to_patent_relationship_traversal or s8r3_executes_release_scoped_professor_to_paper_attribution_traversal or s8r4_executes_release_scoped_paper_to_professor_attribution_traversal or s8r5_executes_release_scoped_patent_to_company_applicant_traversal' -q
```

Expected: all selected tests pass with no xfail.

Observed final: `6 passed, 57 deselected in 163.98s`.

- [x] Run the complete physical/release owner and related relationship/path/release/planning owners:

```bash
cd apps/miroflow-agent
uv run pytest -o addopts='' -p no:cacheprovider \
  tests/canonical_v2/test_internal_reference_projection_contract.py \
  tests/canonical_v2/test_relationship_projection_contract.py \
  tests/canonical_v2/test_path_eligibility_contract.py \
  tests/canonical_v2/test_release_publication_interface.py \
  tests/canonical_v2/test_knowledge_query_planning_contract.py -q
```

Expected: all selected tests pass; existing intentional skips remain explained.

- [x] Run the complete no-external Canonical V2 suite using the repository's environment-unset
  command from the Accepted S8R2 receipt. Expected: zero failures.
- [x] Run:

```bash
cd apps/miroflow-agent
uv run ruff check src/data_agents/canonical_v2 tests/canonical_v2
uv run ruff format --check src/data_agents/canonical_v2 tests/canonical_v2
./.venv/bin/python -m py_compile \
  src/data_agents/canonical_v2/knowledge_read.py \
  src/data_agents/canonical_v2/knowledge_read_isolated.py \
  tests/canonical_v2/test_internal_reference_projection_contract.py
```

Expected: all exit `0`.

- [x] Run complete Canonical V2 Pyright with the Accepted S8R2 configuration; expect `0 errors`.
- [x] Run strict OpenSpec and repository hygiene checks:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: both exit `0`.

- [x] Confirm no original store/source/pointer changed, remove owned caches, and run a targeted
  secret/forbidden-marker scan over S8R5-owned files.
- [x] Write `s8r5/verification-receipt.json` only after Candidate evidence exists. Obtain one lean
  independent implementation/evidence review; zero Critical/Important permits Accepted, while
  Minor/YAGNI are recorded and remain non-blocking.
- [x] Mark S8R5 Accepted and synchronize only permitted status summaries. Keep Task 8.3 unchecked,
  ledger `56/80`, and all forbidden external/git actions unchanged.

Final broad evidence: complete no-external Canonical V2 `350 passed, 141 skipped` with three
intentional hostile-model serializer warnings in `198.96s`; complete Ruff/format, changed-file
compile, complete Canonical V2 Pyright, strict OpenSpec, diff/whitespace, package/source parity,
frozen-source, and forbidden-action checks pass.

## Invariants

- Applicant is never relabeled as owner, assignee, inventor, or generic organization.
- The planner alias never becomes the canonical predicate; the claim remains Patent-to-Company.
- The displayed Patent is source witness only; the returned candidate/handle/coverage member is the
  Company.
- S8R2 and every earlier Accepted serialized contract/hash remain exact.
- No online canonical mutation, physical relationship read, provider dependency in required local
  checks, Commit, Push, PR, promotion, or Cutover.

## Rollback note

Before acceptance, revert only S8R5 additions in the two read modules, the vertical owner test, and
S8R5 artifacts. No migration, release pointer, original source, provider, or external target
rollback is required.
