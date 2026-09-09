# Slice Contract: S8R4 Release-scoped Displayed Paper-to-Professor Attribution Traversal

## Status

Accepted at `2026-07-20T08:53:38Z` after Candidate verification and independent final review
reported `C=0/I=0/M=0/YAGNI=0`. In Progress began at `2026-07-20T07:40:49Z` from Ready contract
SHA-256 `508c8dee26a945673d4b9c28983cc835cf99fa4848e1a18a068e379d996cad78` and plan SHA-256
`d4cf58734edcd37d7ddb0e6b27b682ae0d7d063d2174e92e167dd66ca0748b47`. Ready was approved at
`2026-07-20T07:25:40Z` from reviewed Specified contract SHA-256
`aaf3235ec2ec364df341fded1d66b9e05f2b268a08292d610d35213ac97d36e3` and plan SHA-256
`e848c5247040195c2bfa748fb55563b42dfae40fff2f82ecab0f002f70db3f84`. Minor/YAGNI remain
non-blocking; no additional theoretical review gate is authorized for this slice. Task 8.3 and the
formal `56/80` ledger remain unchanged.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Requirement: `specs/evidence-first-query-orchestration/spec.md` — structured validated paths,
  bounded release-scoped relationship recall, honest enumeration, and complete traceability
- Semantic guard: `specs/paper-identity-status/spec.md` — attribution rejection does not reject
  Paper existence
- OpenSpec task: `8.3` (one inverse public direction only; remains unchecked)
- Depends on: Accepted S6 relationship catalog/projection/path eligibility, S7 candidate/index/
  release authority, S7K generic relationship publication, S8P2, S8E1, S8L2, S8R1, S8R2, S8R3
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r4/dependency-audit.md`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r4/implementation-plan.md`

## Goal

Execute one inverse public relationship direction through the existing `KnowledgeRead.execute`:

```text
planner relationship type: professor_authored_paper
planner direction:         paper_to_professor
planner source/target:     paper -> professor
canonical relationship:   professor_attributed_to_paper@canonical-v2-relationship-v1
canonical orientation:    professor -> paper
execution orientation:    inverse
```

Select only accepted current canonical attributions whose exact Paper target is one displayed Paper
and whose exact Professor source is an accepted public projection. Return the Professor projection.
The planner alias SHALL NOT become the claim predicate, create `paper_has_author`, reverse the
canonical claim, or imply authorship beyond retained attribution evidence.

## Non-goals

- Do not implement Patent-to-Company, Professor/Company, Professor/Patent, or aggregate Task 8.3.
- Do not infer relationships from PaperAuthor, names, ORCID, internal Person, projected ID lists, or
  current Web.
- Do not create a new public API, planner alias, relation type, factory, storage adapter, registry,
  migration, release format, or physical read path.
- Do not generalize all relationship traversal, refactor Accepted trace classes, or reopen S8R3.
- Do not make exhaustive-completeness claims for an open-world representative result.

## Request contract

Add exact package-private path constant:

```python
_PAPER_TO_PROFESSOR_QUERY_PATH = (
    "professor_authored_paper",
    "paper_to_professor",
    "paper",
    "professor",
)
```

Planner endpoint validation SHALL be finite and direction-aware. A policy may contain both accepted
directions for the same planner relationship type. Unknown type remains
`unsupported_relationship_path`; a direction absent from that type's allowed direction set remains
`unsupported_relationship_direction`; source/target mismatch remains
`unsupported_relationship_path`. Existing accepted planner outcomes and serialized plans remain
unchanged.

The public plan has `domains=("professor",)`, independent `relationship` and optional `web` lanes,
no internal reference query, one non-empty displayed Paper ID, and exactly one matching protected
`displayed_entity_set`. `relationship_enumeration_policy` is exact-equal to the plan enumeration
policy and `as_of`; it is `representative`, open-world, non-exhaustive, continuation-available, and
contains no finite-universe or exhaustive member claim. A plan retaining a relationship path while
removing the relationship lane fails before delegate/Web effects.

At the package-internal direct adapter seam, no displayed ID returns zero; one syntactically valid
but current-release-unknown ID returns zero; a known non-Paper/internal ID returns zero; more than
one ID fails. At public execution, missing, empty, duplicate, multiple, known wrong-type, internal,
or protected-set-drift source authority fails before effects. A bare unknown displayed ID carries no
origin release and is an authoritative current-bundle zero; an independently planned Web lane may
still run. Explicit plan/LaneRequest/bundle/release authority mismatch fails closed.

Valid zero results include authoritative-empty relationship authority, a valid Paper with no
matching accepted attribution, a nonmatching relationship family, rejected/non-current
attribution, excluded endpoint, unsupported multi-reference member, and `max_candidates == 0`.

## Release authority and evidence chain

Reuse `_RelationshipAuthority` and `create_isolated_relationship_lookup_adapter`; add no second
factory or physical relationship read. Replay the exact S8R3 authority chain entirely in memory:

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

The installed type/version is exact, canonical endpoints remain Professor-to-Paper, roles are empty,
and effective-time semantics are exactly `observed_at`. Candidate evidence metadata and the shared
assertion continuity payload round-trip exactly. The only supported evidence shape has one binding
of kind `professor_page_or_identity_attribution_assertion`, one retained assertion reference, and
zero artifacts. A structurally valid relation with more retained references/artifacts is omitted as
an unsupported open-world member; it does not corrupt the entire release or permit an exhaustive
claim.

Do not require equality between the source-space shared relationship assertion ID and an unrelated
public-domain `SourceAssertion` namespace. The retained reference and its source record must bind to
the shared assertion and both exact source-canonical assignments. Every returned candidate must
replay exact candidate/assertion/assignment/input/outcome/decision/current/reference/release/
registry/model hashes.

Both endpoints require one exact direction-bound `verified_relationship_traversal` result tied to
the same current relationship decision. `admitted` returns; `limited` returns with the sorted unique
union of visible limitations; `excluded` yields zero; review/other outcomes fail closed. A query
later than the snapshot adds the one canonical snapshot flag; an earlier query fails closed.

Each result is paired positionally with its exact `IndexProjectionRequest` path request and equals a
fresh `PathEligibilityEngine` replay. The Professor request binds domain `professor`, direction
`professor_to_paper`, the returned Professor, the displayed Paper as related projection, and
`domain_identity_status is None`. The Paper request binds domain `paper`, direction
`paper_to_professor`, the displayed Paper, the returned Professor as related projection, and status
in `{confirmed, unverified}`. Trace `paper_domain_identity_status` copies that exact Paper request
field and is never inferred from a limitation code.

## Result and trace contract

Add exactly one `LocalPaperProfessorRelationshipTrace` union variant with
`path="paper_professor_relationship_traversal"` and `execution_lane="relationship"`. Its fields are
the S8R3 evidence-chain fields with these exact inverse observable semantics:

```python
class LocalPaperProfessorRelationshipTrace(ContractModel):
    # Release/query envelope.
    target_id: str
    target_marker_sha256: str
    manifest_sha256: str
    index_result_content_sha256: str
    publication_verification_evidence_ids: tuple[str, ...]
    release_id: str
    lane_request_content_sha256: str
    relationship_enumeration_policy_sha256: str
    displayed_entity_ids: tuple[str, ...]
    displayed_paper_id: str
    protected_slot_id: str
    protected_slot_content_sha256: str
    query_as_of: datetime
    query_relationship_type_id: Literal["professor_authored_paper"]
    query_direction: Literal["paper_to_professor"]
    query_source_type: Literal["paper"]
    query_target_type: Literal["professor"]

    # Installed relationship authority/current projection.
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

    # Candidate/shared assertion/source assignments/decision continuity.
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

    # Retained evidence and public endpoints.
    retained_reference_id: str
    retained_reference_content_sha256: str
    retained_assertion_id: str
    retained_source_record_id: str
    retained_artifact_refs: tuple[str, ...]
    professor_id: str
    professor_stable_reference: str
    professor_projection_content_sha256: str
    professor_display_name: str
    paper_id: str
    paper_stable_reference: str
    paper_projection_content_sha256: str
    paper_display_name: str
    paper_domain_identity_status: Literal["confirmed", "unverified"]

    # Direction-bound endpoint eligibility.
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

    # Returned Professor candidate and canonical-orientation claim.
    candidate_domain: Literal["professor"]
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
    path: Literal["paper_professor_relationship_traversal"]
    execution_lane: Literal["relationship"]
    raw_candidate_id: str
    evidence_id: str
    content_sha256: str
```

Required bindings:

- `displayed_entity_ids == (paper_id,) == (displayed_paper_id,)`;
- canonical endpoints and claim remain
  `canonical:professor:<professor_id> -> canonical:paper:<paper_id>`;
- returned candidate/object/domain/handle are the Professor, never the displayed Paper;
- candidate display name equals the accepted Professor projection display name;
- candidate origin evidence equals the exact selected canonical relationship assertions;
- endpoint directions remain Professor `professor_to_paper` and Paper `paper_to_professor`;
- all tuple lineage is non-empty where required, sorted, unique, and content-bound;
- `raw_candidate_id`, `evidence_id`, and `content_sha256` use the existing deterministic canonical-
  relationship prefixes and exclude only themselves exactly as in S8R3.

## Constraint, Web, fusion, and coverage contract

Only the local S8R4 trace's displayed Paper may satisfy `displayed_entity_set`; that source evidence
is not a returned Paper candidate. Every other protected constraint applies to the returned
Professor and Professor-scoped fused evidence. A Paper-only term in relationship evidence cannot
satisfy or reject a Professor exact identifier/negation constraint.

Current Web may provide same-Professor evidence and fuse by the accepted Professor identity. It may
not provide the displayed Paper witness, manufacture canonical IDs, assert a Professor-Paper
relationship, replace retained local authority, or introduce a Paper object/handle into the inverse
result. Top-level/fused evidence IDs, raw candidate IDs, handles, snapshots, receipts, and candidate
traces must remain collision-free and exactly replayable.

The Web lane accepts only the finite identity states `canonical`, `web_candidate`, and `web_only`.
Direct `canonical` evidence binds the exact Canonical object; `web_candidate` may retain an
evidence-subject alias while proposing an already accepted local Canonical ID; `web_only` remains
unresolved with no Canonical ID. Unknown or inconsistent state combinations fail as invalid lane
output. After fusion, S8R4 requires the fused Canonical ID and domain to be the returned Professor.
A non-local claim subject may be that Professor's Canonical reference or its own evidence alias;
another Canonical Professor subject fails release-bound postvalidation.

Enumeration coverage accounts returned Professor IDs only: checked, eligible, retrieved, displayed,
omitted, and unknown fields remain honest, representative, open-world, non-exhaustive, accounting-
complete, and continuation-required. Authoritative zero is distinct from integrity failure.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`
- S8R4-owned artifacts under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r4/` and this contract
- Existing portfolio/mainline-plan/verification/change-log/agent-links status summaries only after
  Candidate/Accepted evidence exists

## Forbidden changes

- `tasks.md` or `acceptance.md` checkbox/semantic changes
- S8R1/S8R2/S8R3 trace fields, discriminators, literal hashes, or accepted behavior
- Public API/schema/release/catalog/path-eligibility/persistence changes
- Original PostgreSQL, Milvus, forensic sources, production/business data, provider effects
- Commit, Push, PR, Archive, promotion, pointer activation, or Cutover

## Expected unchanged behavior

- All Accepted S1-S8R3 owners and serialized literals remain exact.
- Other planner aliases/directions retain their accepted success/failure semantics.
- Professor-to-Paper remains forward and returns Paper; Company-to-Patent remains applicant-only;
  Technology traversal remains unchanged.
- Query lanes without this exact path cannot construct or accept the inverse trace.
- Paper existence/identity and Professor existence remain independent of attribution acceptance.

## Required checks

1. Exact normal and forced sentinel RED.
2. Focused S8R4 GREEN with warnings as errors.
3. S8R1 literal plus S8R1/S8R2/S8R3/S8R4 exact matrix.
4. Exact S7K/S8P1/S8P2/S8E1/S8L2/S8R predecessor matrix.
5. Complete relevant relationship/path/release/planning/physical-owner checks.
6. Complete no-external Canonical V2 suite.
7. Ruff check and format-check, Pyright, changed-file `py_compile`, strict OpenSpec.
8. `git diff --check`, untracked whitespace, offline lock/wheel/source parity, generated-cache and
   wheel cleanup, frozen original-source hash/state checks, and secret/forbidden-marker scans.
9. Independent contract, implementation, and final evidence reviews with zero open
   Critical/Important. Minor/YAGNI are recorded but do not block.

## Evidence to update

- This contract and `s8r4/implementation-plan.md`
- `s8r4/verification-receipt.json` after Candidate evidence exists
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/portfolio.md` and the code-grounded mainline plan
- OpenSpec `change-log.md` and `agent-links.md`
- Keep OpenSpec `tasks.md`, `acceptance.md`, Task 8.3, and ledger `56/80` unchanged

## Stop conditions

Stop this slice, without marking the global goal blocked, if implementation requires a new relation
type, public API/schema, physical data read/write, evidence inference absent from the frozen
authority, modification of an Accepted trace, or a product decision about attribution semantics.
An external reviewer timeout, S2C3C2 human gate, optional provider absence, or an independently Ready
later slice is not a global-goal blocker.

## Done means

The exact inverse planner path executes deterministically through public `KnowledgeRead.execute`,
returns only fully traced Professor candidates from one displayed Paper, preserves canonical claim
orientation and open-world coverage, rejects the hostile matrix before or after effects as required,
passes all Required checks, receives zero-Critical/Important independent acceptance, and records an
Accepted receipt without checking aggregate Task 8.3 or performing forbidden actions.

## Rollback note

Before acceptance, remove only S8R4-owned additions in the two read modules, vertical owner test,
and S8R4 artifacts. No migration, release pointer, original source, provider, or external target
rollback is required.
