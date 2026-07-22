# Slice Contract: S8R3 Release-scoped Displayed Professor-to-Paper Attribution Traversal

## Status

Accepted at `2026-07-20T02:13:12Z`. Ready was frozen at `2026-07-19T22:53:22Z` from reviewed Specified contract SHA-256
`31eb604d75865118f7125a1231876bd72b54151aaf4492a52e094447dc246c9f` and plan SHA-256
`3a6cf522f9812903582e73b7246bbc5119bd81c7504e5455409241c508a450ab`. Three independent
reviews report zero open Critical/Important; the final contract review reports
`C=0/I=0/M=0/YAGNI=0`. The exact RED, bounded GREEN/hostile matrix, predecessor regressions,
complete no-external suite, static/build parity, and frozen-target checks are recorded. Candidate
review closed one path/lane Important through RED/GREEN and targeted re-review; final implementation,
spec-repair, and evidence reviews all report `C=0/I=0/M=0/YAGNI=0` and allow acceptance.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Requirements: `specs/evidence-first-query-orchestration/spec.md` — structured validated paths,
  bounded release-scoped relationship recall, honest enumeration, and complete traceability
- Required semantic guard: `specs/paper-identity-status/spec.md` — attribution rejection does not
  reject Paper existence
- OpenSpec task: `8.3` (one real relationship predecessor only; remains unchecked)
- Depends on: Accepted S6 relationship catalog/projection/path eligibility, S7 candidate/index/
  release authority, S7K generic relationship publication, S8P2, S8E1, S8L2, S8R1, and S8R2
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r3/dependency-audit.md`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r3/implementation-plan.md`

## Goal

Execute one public relationship family through the existing `KnowledgeRead.execute` interface:

```text
planner relationship type: professor_authored_paper
planner direction:         professor_to_paper
planner source/target:     professor -> paper
canonical relationship:   professor_attributed_to_paper@canonical-v2-relationship-v1
canonical orientation:    professor -> paper
execution orientation:    forward
```

Select only accepted current canonical attributions whose exact source endpoint is one displayed
Professor and whose exact target endpoint is an accepted Paper. Return the Paper projection. The
planner name SHALL NOT become the claim predicate, create `paper_has_author`, or imply authorship
beyond the retained attribution evidence.

## Request contract

Reuse the existing omission-preserving `LaneRequest.relationship_enumeration_policy`. Populate it
only for the exact S8R3 path (in addition to the accepted S8R2 path), and require exact equality with
the plan enumeration policy and `as_of`. S8R1 literal JSON/hashes and S8R2 trace JSON/hashes SHALL
remain unchanged.

The public plan has `domains=("paper",)`, independent `relationship` and `web` lanes, no internal
reference query, one non-empty displayed Professor ID, and exactly one matching protected
`displayed_entity_set`. The enumeration policy is exactly `representative`, open-world,
non-exhaustive, continuation available, and contains no finite-universe or required/eligible-member
claim. An earlier query than the relationship snapshot fails closed.

At the package-internal direct adapter seam, no displayed ID returns zero; one syntactically valid
but current-release-unknown ID returns zero; a known non-Professor or internal ID returns zero; more
than one ID fails. At public `KnowledgeRead.execute`, missing, empty, duplicate, multiple, known
wrong-type, internal, or protected-set-drift source authority fails before delegate/Web effects.
Only an explicit plan/LaneRequest/bundle/typed-authority release mismatch is a cross-release error;
a bare displayed ID carries no origin release, so absence from the current bundle is always an
authoritative local zero. The independently planned Web lane may still run for that zero.

Valid zero results include an authoritative-empty relationship authority, a valid Professor with no
matching accepted attribution, only a same-name/PaperAuthor/internal-Person relation, a rejected or
non-current attribution, an excluded endpoint, and `max_candidates == 0`.

Both `confirmed` and `unverified` current Papers may return when endpoint eligibility is returnable.
An unverified/partial Paper's exact path limitations, including `identity_unverified`, remain visible
in candidate quality flags. A rejected Paper has no returnable current public projection; a merged
Paper does not occupy a result position and only its accepted survivor may return.

## Release authority and evidence chain

Reuse `_RelationshipAuthority` and `create_isolated_relationship_lookup_adapter`; add no second
factory, adapter seam, physical relationship read, or storage interface. The clean test-owned S8R3
graph contains one Professor projection, one Paper projection, and one exact accepted relationship
chain:

```text
RelationshipProjectionRequest.candidates
  -> exact RelationshipProjectionCandidate
  -> exact shared RelationshipAssertion in source identity space
  -> exact Professor and Paper SourceCanonicalAssignment records
  -> exact RelationshipDecisionInput
  -> exact RelationshipCandidateOutcome
  -> exact shared canonical RelationshipDecision
  -> CurrentRelationshipProjection
  -> selected RetainedAssertionReference
  -> exact Professor public projection
  -> exact Paper public projection
  -> Professor professor_to_paper eligibility
  -> Paper paper_to_professor eligibility
```

The installed type/version must be exact, source/target endpoints must be canonical Professor/Paper,
and roles must be empty. Candidate `evidence_metadata` is round-tripped as exact normalized JSON; the
catalog does not require an `attribution_basis` key. If that key exists, it is preserved exactly and
never synthesized, sorted, or interpreted as a business role. The shared assertion attributes must
equal the relationship module's exact continuity payload: candidate ID, the sorted retained evidence
references, the same full evidence metadata, and empty role bindings.

The S8R3-supported shape contains exactly one evidence binding of kind
`professor_page_or_identity_attribution_assertion`, exactly one retained assertion reference, and
zero retained artifact references. That reference is the source-evidence registry authority; S8R3
does not add an unsupported requirement that its `assertion_id` also appear in the public-domain
projection's `SourceAssertion` collection. The shared assertion's source record must be covered by
both exact source-canonical assignments. An otherwise valid accepted attribution with multiple
assertion or artifact references is an unsupported open-world member for this minimal slice: omit
that candidate and continue, preserve representative/non-exhaustive coverage and continuation, and
do not classify the entire release authority as corrupt. Candidate, shared assertion, assignments,
input/current decisions, outcome, current projection, retained evidence, release, registry, and all
canonical model hashes must replay exactly for every returned candidate.

`relationship_evidence_kind` equals the candidate's sole evidence binding kind.
`relationship_effective_time_semantics` equals the current projection's effective time semantics
and the installed relationship type's time semantics; all three are exactly `observed_at`.

Do not infer the edge from `paper_has_author`, a PaperAuthor subobject, an internal Person identity,
a name/ORCID match, or `PaperProjection.professor_ids`. Those values may coexist in the fixture but
are not sufficient authority. Rejecting the attribution suppresses this traversal only; it does not
invalidate or remove the Paper projection from other lanes.

Both endpoints require one exact direction-bound `verified_relationship_traversal` result tied to
the same current relationship decision. `admitted` returns; model-valid `limited` returns with the
sorted/deduplicated union of visible limitations; `excluded` yields zero; review/other outcomes fail
closed. A later query adds one canonical `relationship_snapshot_as_of:<UTC timestamp>` quality flag.

Each endpoint result is paired positionally with its exact
`IndexProjectionRequest.public_path_eligibility_requests` member and must equal a fresh
`PathEligibilityEngine` replay of that request. The Professor request binds the same release,
`typed:professor:<id>` projection, domain `professor`, direction `professor_to_paper`, current
relationship decision, and `domain_identity_status is None`. The Paper request binds the same
release, `typed:paper:<id>` projection, domain `paper`, direction `paper_to_professor`, current
relationship decision, and a status in `{confirmed, unverified}`. Trace
`paper_domain_identity_status` equals that exact Paper request field; it SHALL NOT be inferred from
the presence or absence of an `identity_unverified` limitation. A request/result/status crosswire
fails closed.

## Result and trace contract

Add exactly one `LocalProfessorPaperRelationshipTrace` union variant with
`path="professor_paper_relationship_traversal"` and
`execution_lane="relationship"`. Its complete field set is frozen below; implementation SHALL NOT
add optional catch-all fields or reuse the S8R2 discriminator:

```python
class LocalProfessorPaperRelationshipTrace(ContractModel):
    # Release and query envelope.
    target_id: str
    target_marker_sha256: str
    manifest_sha256: str
    index_result_content_sha256: str
    publication_verification_evidence_ids: tuple[str, ...]
    release_id: str
    lane_request_content_sha256: str
    relationship_enumeration_policy_sha256: str
    displayed_entity_ids: tuple[str, ...]
    displayed_professor_id: str
    protected_slot_id: str
    protected_slot_content_sha256: str
    query_as_of: datetime
    query_relationship_type_id: Literal["professor_authored_paper"]
    query_direction: Literal["professor_to_paper"]
    query_source_type: Literal["professor"]
    query_target_type: Literal["paper"]

    # Installed relationship authority and current projection.
    relationship_request_sha256: str
    relationship_result_sha256: str
    relationship_projection_run_id: str
    relationship_projection_schema_version: str
    relationship_registry_version: str
    relationship_registry_content_sha256: str
    relationship_snapshot_as_of: datetime
    canonical_relationship_id: str
    current_relationship_content_sha256: str
    relationship_decision_input_id: str
    relationship_decision_input_content_sha256: str
    relationship_decision_id: str
    relationship_decision_content_sha256: str
    relationship_decision_state: Literal["accepted"]
    relationship_type_id: Literal["professor_attributed_to_paper"]
    relationship_type_version: Literal["canonical-v2-relationship-v1"]
    relationship_source_endpoint: str
    relationship_target_endpoint: str
    relationship_role_bindings: tuple[tuple[str, str], ...]
    relationship_effective_time_semantics: Literal["observed_at"]
    selected_evidence_refs: tuple[str, ...]
    relationship_valid_from: Any | None
    relationship_valid_to: Any | None

    # Candidate and shared source assertion continuity.
    projection_candidate_id: str
    projection_candidate_content_sha256: str
    projection_candidate_observed_at: datetime
    projection_candidate_source_event_time: datetime | None
    projection_candidate_assertion_input_id: str
    projection_candidate_assertion_input_kind: Literal[
        "shared_source_relationship_assertion"
    ]
    projection_candidate_decision_input_id: str
    projection_candidate_evidence_metadata: dict[str, JsonValue]
    relationship_evidence_kind: Literal[
        "professor_page_or_identity_attribution_assertion"
    ]
    shared_assertion_id: str
    shared_assertion_content_sha256: str
    shared_assertion_source_record_id: str
    shared_assertion_source_identity_id: str
    shared_assertion_target_identity_id: str
    shared_assertion_evidence_refs: tuple[str, ...]
    shared_assertion_attributes_content_sha256: str
    shared_assertion_observed_at: datetime
    shared_assertion_source_event_time: datetime | None
    shared_assertion_valid_from: Any | None
    shared_assertion_valid_to: Any | None

    # Exact source-to-canonical assignments.
    source_assignment_id: str
    source_assignment_content_sha256: str
    source_assignment_source_identity_id: str
    source_assignment_canonical_identity_id: str
    source_assignment_entity_type: Literal["professor"]
    source_assignment_source_record_refs: tuple[str, ...]
    target_assignment_id: str
    target_assignment_content_sha256: str
    target_assignment_source_identity_id: str
    target_assignment_canonical_identity_id: str
    target_assignment_entity_type: Literal["paper"]
    target_assignment_source_record_refs: tuple[str, ...]

    # Outcome and accepted decision continuity.
    candidate_outcome_candidate_id: str
    candidate_outcome_content_sha256: str
    candidate_outcome_retained_assertion_id: str
    candidate_outcome_decision_id: str
    candidate_outcome_projected_relationship_id: str
    candidate_outcome_selected_evidence_refs: tuple[str, ...]
    decision_input_candidate_assertion_ids: tuple[str, ...]
    decision_input_selected_assertion_ids: tuple[str, ...]
    decision_input_conflicting_assertion_ids: tuple[str, ...]
    decision_input_selected_evidence_refs: tuple[str, ...]
    decision_candidate_assertion_ids: tuple[str, ...]
    decision_selected_assertion_ids: tuple[str, ...]
    decision_conflicting_assertion_ids: tuple[str, ...]
    decision_source_canonical_identity_id: str
    decision_target_canonical_identity_id: str
    decision_release_id: str
    current_selected_evidence_refs: tuple[str, ...]

    # Retained source-evidence registry authority.
    retained_reference_id: str
    retained_reference_content_sha256: str
    retained_assertion_id: str
    retained_source_record_id: str
    retained_artifact_refs: tuple[str, ...]

    # Public endpoints.
    professor_id: str
    professor_stable_reference: str
    professor_projection_content_sha256: str
    professor_display_name: str
    paper_id: str
    paper_stable_reference: str
    paper_projection_content_sha256: str
    paper_display_name: str
    paper_domain_identity_status: Literal["confirmed", "unverified"]

    # Direction-bound eligibility for both endpoints.
    professor_path_result_content_sha256: str
    professor_traversal_directions: tuple[str, ...]
    professor_relationship_decision_ids: tuple[str, ...]
    professor_eligibility_decision_id: str
    professor_eligibility_policy_id: str
    professor_eligibility_policy_version: str
    professor_eligibility_policy_content_sha256: str
    professor_eligibility_outcome: Literal["admitted", "limited"]
    professor_eligibility_limitations: tuple[str, ...]
    professor_eligibility_hard_exclusion_codes: tuple[str, ...]
    professor_eligibility_supporting_assertion_ids: tuple[str, ...]
    paper_path_result_content_sha256: str
    paper_traversal_directions: tuple[str, ...]
    paper_relationship_decision_ids: tuple[str, ...]
    paper_eligibility_decision_id: str
    paper_eligibility_policy_id: str
    paper_eligibility_policy_version: str
    paper_eligibility_policy_content_sha256: str
    paper_eligibility_outcome: Literal["admitted", "limited"]
    paper_eligibility_limitations: tuple[str, ...]
    paper_eligibility_hard_exclusion_codes: tuple[str, ...]
    paper_eligibility_supporting_assertion_ids: tuple[str, ...]

    # Observable Paper candidate and claim.
    candidate_domain: Literal["paper"]
    candidate_canonical_id: str
    candidate_display_name: str
    candidate_identity_kind: Literal["canonical"]
    candidate_resolution_state: Literal["resolved"]
    candidate_reference_type: None
    candidate_origin_public_evidence_ids: tuple[str, ...]
    candidate_quality_flags: tuple[str, ...]
    candidate_raw_score: float
    claim_subject_id: str
    claim_predicate: Literal["professor_attributed_to_paper"]
    claim_value: str
    claim_status: Literal["accepted"]
    relationship_state: Literal["accepted"]
    evidence_source_locator: str
    evidence_source_nature: Literal["local"]
    evidence_source_authority: Literal["canonical_release"]
    evidence_observed_at: datetime
    snippet_sha256: str
    path: Literal["professor_paper_relationship_traversal"]
    execution_lane: Literal["relationship"]
    raw_candidate_id: str
    evidence_id: str
    content_sha256: str
```

Publication IDs, displayed IDs, evidence-reference projections, candidate origin IDs, quality
flags, limitations, exclusions, supporting assertion IDs, and the empty role-binding projection are
sorted and unique. Direction/relationship-decision tuples are exact singletons. Source-assignment
record refs and decision candidate/selected/conflicting assertion tuples preserve the exact accepted
model order while their full-model hashes prevent permutation. `relationship_role_bindings` and
`retained_artifact_refs` are exactly empty, and `candidate_raw_score` is exactly `1.0`. Candidate
origin evidence is exactly the shared decision's selected source-relationship assertion IDs. The
shared assertion attributes are reconstructed exactly from candidate ID, retained evidence refs,
`projection_candidate_evidence_metadata`, and empty roles before checking
`shared_assertion_attributes_content_sha256`. The supported candidate has exactly one selected
evidence reference.

Derive IDs exactly as follows:

```text
lineage = trace JSON excluding raw_candidate_id, evidence_id, content_sha256
raw_candidate_id = local-professor-paper-relationship-candidate:sha256:<sha256(lineage)>
evidence_id = local-professor-paper-relationship-evidence:sha256:<sha256((lineage, raw_candidate_id))>
content_sha256 = sha256(trace JSON excluding content_sha256)
```

Do not make accepted S8R2 fields optional or change its serializer/hash.

Emit one raw candidate per accepted current attribution before existing fusion:

```text
domain/display locator: paper / exact Paper canonical ID and title
claim subject:          canonical:professor:<Professor ID>
claim predicate:        professor_attributed_to_paper
claim value:            canonical:paper:<Paper ID>
claim status:           accepted
relationship_state:    accepted
```

The displayed Professor is a source-side constraint witness only. For this trace variant,
`displayed_entity_set` evaluates against the traced Professor. Domain, exact identifier, geography,
negation, and every other constraint evaluate against only the returned Paper identity and
Paper-scoped evidence; the Professor-scoped relationship claim/snippet cannot satisfy or reject
those constraints, including after same-Paper Web fusion. A Web Professor, mixed source witnesses,
an untraced candidate, or an unrelated lane cannot satisfy the protected set. Legitimate current-
Web evidence for the same returned Paper may fuse without changing canonical relationship
ownership. RED freezes same-Paper Web fusion with a Paper-target exact-identifier success and a
Professor-only negation term that must not reject the Paper.

`EvidenceItem.snippet` is the canonical JSON serialization of the selected shared
`RelationshipAssertion` (`ensure_ascii=False`, sorted keys, compact separators, no NaN). It SHALL
contain the canonical predicate and exact retained source metadata only; neither the planner alias
nor generated “authored/author” prose may enter it. The trace binds the exact snippet hash, source
locator/nature/authority/observed-at, and candidate origin assertion IDs.

The evidence fields are exact, not implementation choices:

```text
evidence_source_locator = canonical-v2-isolated:<target_id>:<canonical_relationship_id>
evidence_source_nature = local
evidence_source_authority = canonical_release
evidence_observed_at = relationship_snapshot_as_of
```

Preserve the content-bound order of `RelationshipProjectionResult.current_relationships`, omit
nonmatching/nonreturnable/unsupported-shape members in that order, and apply `max_candidates` to the
raw relationship candidates before fusion. S8R3 introduces no ranking or reordering policy.

The wrapper SHALL replay the exact expected relationship result after delegate execution and reject
missing/extra/altered evidence, candidate traces, local relationship traces, fused ownership,
constraint receipts, auxiliary traces, handles, coverage, cross-lane raw/evidence ID reuse, or a
fabricated attribution. Representative coverage remains open-world, non-exhaustive, and continuation
required.

## Non-goals

- No Paper-to-Professor direction, `paper_has_author`, Person-backed author retrieval, Professor-to-
  Company/Patent, multi-Professor source set, generic path registry, or aggregate Task 8.3 closure.
- No authorship inference, name/ORCID inference, Paper existence mutation, planner heuristic,
  canonical build/mutation, or new relationship schema.
- No fusion/rerank/sufficiency algorithm change, Web-handle lifecycle, answer/session, reviewed
  corpus, provider, live network, migration, task checkbox, Commit, Push, PR, Archive, promotion, or
  Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r3/`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/code-grounded-mainline-plan-2026-07-13.md`
- `.agents/portfolio.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`

Keep `tasks.md`, `acceptance.md`, catalogs, relationship projection, path eligibility, release
publication, persistence, and external targets unchanged.

## Forbidden changes

- Any weakening or serializer/hash change to accepted S8R1/S8R2 contracts.
- Treating the planner alias as canonical, treating attribution as `paper_has_author`, deriving an
  edge from a Person/name/subobject/projected ID, or allowing roles on this relation.
- A second relationship adapter/factory, online canonical mutation, physical relationship lookup,
  production/source/Postgres/Milvus writes, or unrelated cleanup.

## Required checks

1. Exact S8R3 normal RED: one strict xfail at `_MissingS8R3ProfessorPaperTraversal`.
2. Exact forced RED: one failure at that exact sentinel before lazy fixtures/effects.
3. S8R1 literal compatibility and S8R1/S8R2 owners remain GREEN.
4. Focused S8R3 GREEN, including the same-Paper Web/Paper-constraint isolation cases, and exact
   predecessor matrix. The S8R3 hostile set includes one Paper-status/request/result crosswire.
5. Complete physical/release owner; relationship/path/release owners; all KnowledgeRead/planning
   owners; complete no-external Canonical V2 suite.
6. Complete Canonical V2 Ruff, format `--check`, Pyright, changed-file `py_compile`, strict OpenSpec,
   diff and untracked whitespace checks.
7. Offline lock/build/source parity, forbidden wheel-entry scan, owned-cache cleanup, frozen target
   hashes/state, and high-confidence secret-assignment scan.
8. Independent Candidate review with zero open Critical/Important. Minor/YAGNI are recorded and do
   not block.

Every pytest invocation uses `-o addopts='' -p no:cacheprovider`.

## Evidence to update

- S8R3 receipt with Ready/Candidate/Accepted hashes and exact commands/results
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/agent-links.md`
- `.agents/portfolio.md` and the code-grounded mainline plan

Do not change Task 8.3 or the formal `56/80` ledger for this slice.

## Stop conditions

Stop and re-plan if the exact alias-to-canonical mapping ceases to be unique, the accepted shared
relationship chain cannot bind the release graph, an API/schema/storage change beyond this
explicitly authorized `LocalEvidenceTrace` union variant and exact private path branch is required,
S8R1/S8R2 literal compatibility breaks, original sources would be touched, or any required review
retains a Critical/Important finding.

S2C3C2 is not a stop condition for this deterministic predecessor.

## Done means

One exact displayed Professor can retrieve only evidence-backed accepted attributed Papers through
the release-scoped public `KnowledgeRead.execute` relationship lane, with honest open-world coverage,
full replayable traceability, fail-closed hostile validation, unchanged accepted predecessors, all
required checks green, and independent zero-Critical/Important acceptance. Task 8.3 remains open.
