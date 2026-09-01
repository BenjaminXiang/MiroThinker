"""Release-bound read-only lookup adapters for one isolated S7 bundle."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from threading import Lock
from typing import Any, Literal, cast
import unicodedata

import numpy as np

from .candidate_projection import (
    CandidateProjectionIntegrityError,
    CandidateProjectionRequest,
    CandidateProjectionResult,
    compose_candidate_projections,
)
from .contracts import (
    PolicyOutcome,
    PublishedRelease,
    RelationshipAssertion,
    RelationshipDecision,
    ReleaseState,
    SourceAssertion,
)
from .domain_projection_models import (
    CompanyProduct,
    CompanyProjection,
    PaperProjection,
    PatentApplicant,
    PatentProjection,
    ProfessorProjection,
)
from .followup_referents import (
    COMPANY_NAME_PATTERN,
    _EXPLICIT_COMPANY_REJECT_MARKERS,
    extract_institution_person_name,
)
from .index_projection import (
    IndexProjectionIntegrityError,
    IndexProjectionPoint,
    IndexProjectionRequest,
    LookupProjectionDocument,
    create_ephemeral_index_projection_builder,
)
from .index_projection_isolated import (
    EmbeddingAdapter,
    IsolatedIndexSnapshot,
    audit_isolated_index_snapshot,
    load_persisted_vector_matrix,
    open_manifest_verified_index_snapshot,
    read_isolated_lookup_documents,
)
from .internal_reference_projection import (
    InternalReferenceProjectionResult,
    PersonProjection,
    PublicDomainEvidenceAnchor,
    TechnologyEvidenceAnchor,
    TechnologyRouteProjection,
)
from .knowledge_read import (
    AcceptedIdentityLookupRequest,
    AmbiguityCandidate,
    AmbiguityPolicy,
    CandidateDiscriminator,
    CanonicalEntityHandle,
    EvidenceClaimBinding,
    EvidenceItem,
    EvidenceSet,
    InstitutionCatalog,
    IdentityFusionRequest,
    InternalReferenceFact,
    InternalReferenceQuery,
    KnowledgeRead,
    KnowledgeReadIntegrityError,
    LaneRequest,
    LocalCanonicalRelationshipTrace,
    LocalPatentCompanyRelationshipTrace,
    LocalPaperProfessorRelationshipTrace,
    LocalProfessorPaperRelationshipTrace,
    LocalProjectionTrace,
    LocalSourceRelationshipTrace,
    LocalInternalReferenceTrace,
    LocalRelationshipTrace,
    LocalVectorTrace,
    PersonReferenceRecord,
    PlanningReleaseBinding,
    ProtectedSlot,
    QueryPlanningPolicy,
    QueryPlanningRequest,
    RecallCandidate,
    RerankRequest,
    RetrievalPlan,
    RetrievalLaneResult,
    ReferenceTrace,
    SufficiencyDecisionRequest,
    SupplementalRequest,
    TechnologyRouteRecord,
    WebSearchPolicy,
    WebHandleResolutionRequest,
    WebSnapshotPolicy,
    _QueryPlanner,
    _COMPANY_TO_PATENT_QUERY_PATH,
    _COMPANY_TO_PROFESSOR_QUERY_PATH,
    _PATENT_TO_COMPANY_QUERY_PATH,
    _PAPER_TO_PROFESSOR_QUERY_PATH,
    _PROFESSOR_TO_PAPER_QUERY_PATH,
    _PROFESSOR_TO_COMPANY_QUERY_PATH,
    _PUBLIC_RELATIONSHIP_QUERY_PATHS,
    _SUPPORTED_LANES,
    _apply_constraints,
    _build_enumeration_coverage,
    _canonical_sha256,
    _lane_request,
    _local_projection_locator,
    _resolve_institutions,
    create_ephemeral_knowledge_read,
    create_ephemeral_query_planner,
)
from . import manual_recall_points
from .relationship_projection import (
    CurrentRelationshipProjection,
    RelationshipCandidateOutcome,
    RelationshipProjectionCandidate,
    RelationshipProjectionIntegrityError,
    RelationshipProjectionRequest,
    RelationshipProjectionResult,
    SourceCanonicalAssignment,
    TypedRelationshipAssertionInput,
    TypedRelationshipDecision,
    create_ephemeral_relationship_projection,
)
from .path_eligibility import PathEligibilityEngine
from .release_publication_isolated import IsolatedReleaseBundle


_EXACT_ADAPTER_VERSION = "canonical-v2-isolated-exact-lookup-v1"
_STRUCTURED_ADAPTER_VERSION = "canonical-v2-isolated-structured-lookup-v1"
_LEXICAL_ADAPTER_VERSION = "canonical-v2-isolated-lexical-lookup-v1"
_VECTOR_ADAPTER_VERSION = "canonical-v2-isolated-vector-recall-v1"
_INTERNAL_REFERENCE_ADAPTER_VERSION = "canonical-v2-isolated-internal-reference-v1"
_RELATIONSHIP_ADAPTER_VERSION = "canonical-v2-isolated-relationship-v1"
_PATENT_APPLICANT_TYPE = (
    "patent_has_applicant",
    "canonical-v2-relationship-v1",
)
_PATENT_APPLICANT_ROLE = "applicant"
_PROFESSOR_PAPER_TYPE = (
    "professor_attributed_to_paper",
    "canonical-v2-relationship-v1",
)
_PROFESSOR_COMPANY_TYPE = (
    "professor_company_role",
    "canonical-v2-relationship-v1",
)
_SOURCE_BOUND_RELATIONSHIP_PATHS = {
    _COMPANY_TO_PATENT_QUERY_PATH: (_PATENT_APPLICANT_TYPE, "inverse"),
    _PATENT_TO_COMPANY_QUERY_PATH: (_PATENT_APPLICANT_TYPE, "forward"),
    _PROFESSOR_TO_PAPER_QUERY_PATH: (_PROFESSOR_PAPER_TYPE, "forward"),
    _PAPER_TO_PROFESSOR_QUERY_PATH: (_PROFESSOR_PAPER_TYPE, "inverse"),
    _PROFESSOR_TO_COMPANY_QUERY_PATH: (_PROFESSOR_COMPANY_TYPE, "forward"),
    _COMPANY_TO_PROFESSOR_QUERY_PATH: (_PROFESSOR_COMPANY_TYPE, "inverse"),
}
_PROFESSOR_PAPER_RELATIONSHIP_PREDICATES = frozenset(
    {
        "professor_attributed_to_paper",
        "professor_authored_paper",
        "paper_has_author",
    }
)
_PUBLIC_DOMAINS = frozenset({"company", "paper", "patent", "professor"})
RelationshipState = Literal[
    "discussion_or_mention",
    "claimed_adoption",
    "demonstrated_use",
]
_TECHNOLOGY_RELATIONSHIP_STATES: dict[str, RelationshipState] = {
    "entity_discusses_or_mentions_technology": "discussion_or_mention",
    "entity_claims_adoption_of_technology": "claimed_adoption",
    "entity_demonstrates_use_of_technology": "demonstrated_use",
}
_TECHNOLOGY_RELATIONSHIP_SOURCE_FIELDS = {
    "discussion_or_mention": "internal_reference.technology_discussion_or_mention",
    "claimed_adoption": "internal_reference.technology_claimed_adoption",
    "demonstrated_use": "internal_reference.technology_demonstrated_use",
}

ExecutionLane = Literal[
    "exact",
    "structured",
    "lexical",
    "vector",
    "relationship",
    "internal_reference",
]

PublicProjection = (
    CompanyProjection | PaperProjection | PatentProjection | ProfessorProjection
)
PublicDomain = Literal["company", "paper", "patent", "professor"]


class IsolatedQueryPlanningIntegrityError(ValueError):
    """A release-bound planning input cannot reproduce one accepted S7 graph."""


class IsolatedKnowledgeReadIntegrityError(KnowledgeReadIntegrityError):
    """A retrieval plan cannot execute against its bound isolated release."""


@dataclass(frozen=True, slots=True)
class _InternalReferenceAuthority:
    bundle: IsolatedReleaseBundle
    publication: PublishedRelease
    index_request: IndexProjectionRequest
    institution_catalog: InstitutionCatalog
    internal_result: InternalReferenceProjectionResult
    person_records: tuple[PersonReferenceRecord, ...]
    technology_records: tuple[TechnologyRouteRecord, ...]


@dataclass(frozen=True, slots=True)
class _RelationshipAuthority:
    internal_authority: _InternalReferenceAuthority
    relationship_request: RelationshipProjectionRequest
    relationship_result: RelationshipProjectionResult
    candidate_result: CandidateProjectionResult
    # Canonical hash of the full relationship request, computed once when the
    # authority is assembled. Per-candidate trace builders bind this value;
    # re-serializing the release-sized request per candidate costs minutes of
    # CPU on production graphs.
    relationship_request_content_sha256: str


@dataclass(frozen=True, slots=True)
class _InternalReferenceCandidateSpec:
    reference_type: Literal["person", "technology_route"]
    internal_reference_id: str
    internal_projection_content_sha256: str
    reference_record_content_sha256: str
    document: LookupProjectionDocument
    public_domain: PublicDomain
    public_canonical_id: str
    public_display_name: str
    public_root_projection_content_sha256: str
    anchors: tuple[PublicDomainEvidenceAnchor | TechnologyEvidenceAnchor, ...]
    claim_predicate: str
    claim_value: str
    claim_evidence_ids: tuple[str, ...]
    matched_filter_facts: tuple[InternalReferenceFact, ...]
    snippet: str


class _ValidatingEmbeddingAdapter:
    """Freeze and validate one explicit embedding port used by audit and scoring."""

    def __init__(
        self,
        adapter: EmbeddingAdapter,
        *,
        expected_model_id: str,
    ) -> None:
        try:
            model_id = adapter.model_id
            dimension = adapter.dimension
            embed_batch = adapter.embed_batch
        except Exception as exc:
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter is missing its required interface"
            ) from exc
        if not isinstance(model_id, str) or not model_id:
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter model identity must be non-empty"
            )
        if model_id != expected_model_id:
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter model differs from the release"
            )
        if (
            not isinstance(dimension, int)
            or isinstance(dimension, bool)
            or dimension <= 0
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter dimension must be a positive non-Boolean integer"
            )
        if not callable(embed_batch):
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter embed_batch must be callable"
            )
        self._adapter = adapter
        self._model_id = model_id
        self._dimension = dimension
        self.model_id = model_id
        self.dimension = dimension
        self._vectors_by_text: dict[str, tuple[float, ...]] = {}

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self._validate_identity()
        try:
            raw_vectors = tuple(self._adapter.embed_batch(texts))
        except Exception as exc:
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter failed while producing vectors"
            ) from exc
        if len(raw_vectors) != len(texts):
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter returned the wrong output cardinality"
            )

        validated_vectors: list[tuple[float, ...]] = []
        for raw_vector in raw_vectors:
            try:
                values = tuple(raw_vector)
            except Exception as exc:
                raise IsolatedKnowledgeReadIntegrityError(
                    "embedding adapter returned an invalid vector"
                ) from exc
            if len(values) != self._dimension:
                raise IsolatedKnowledgeReadIntegrityError(
                    "embedding adapter returned the wrong vector dimension"
                )
            if any(
                not isinstance(value, (int, float)) or isinstance(value, bool)
                for value in values
            ):
                raise IsolatedKnowledgeReadIntegrityError(
                    "embedding adapter returned a non-numeric vector scalar"
                )
            vector = tuple(float(value) for value in values)
            if any(not math.isfinite(value) for value in vector):
                raise IsolatedKnowledgeReadIntegrityError(
                    "embedding adapter returned a non-finite vector"
                )
            norm = math.sqrt(math.fsum(value * value for value in vector))
            if not math.isfinite(norm) or norm == 0.0:
                raise IsolatedKnowledgeReadIntegrityError(
                    "embedding adapter returned a zero-norm vector"
                )
            validated_vectors.append(vector)

        self._validate_identity()
        for text, vector in zip(texts, validated_vectors, strict=True):
            previous = self._vectors_by_text.get(text)
            if previous is not None and previous != vector:
                raise IsolatedKnowledgeReadIntegrityError(
                    "embedding adapter returned a non-deterministic vector"
                )
            self._vectors_by_text[text] = vector
        return tuple(validated_vectors)

    def _validate_identity(self) -> None:
        try:
            model_id = self._adapter.model_id
            dimension = self._adapter.dimension
        except Exception as exc:
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter identity cannot be read"
            ) from exc
        if model_id != self._model_id:
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter model identity changed"
            )
        if (
            not isinstance(dimension, int)
            or isinstance(dimension, bool)
            or dimension != self._dimension
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "embedding adapter dimension changed"
            )


_NAMED_PROFESSOR_RESEARCH_PATTERN = re.compile(
    r"(?P<name>[一-鿿·]{2,4})的(?:代表性)?(?:论文|研究成果|科研成果|学术成果|代表作)"
)


def _resolve_named_professor_research_source(
    query: str,
    professor_projections: tuple[ProfessorProjection, ...],
) -> ProfessorProjection | None:
    """Resolve a "X的论文/研究成果…" query to one unique Professor projection.

    A same-turn named-source traversal is only proposed when the possessive
    pattern matches and the name binds exactly one accepted Professor by display
    name, canonical name, or alias; any ambiguity falls back to the normal lanes.
    """
    match = _NAMED_PROFESSOR_RESEARCH_PATTERN.search(query)
    if match is None:
        return None
    name = match.group("name")
    matches = tuple(
        projection
        for projection in professor_projections
        if (
            projection.name == name
            or projection.canonical_name_zh == name
            or name in projection.aliases
        )
    )
    if len(matches) != 1:
        return None
    return matches[0]


_NAMED_COMPANY_PATENT_PATTERN = re.compile(
    r"(?P<name>[一-鿿A-Za-z0-9（）()·-]{2,40}?)的(?:相关)?专利"
)


def _named_company_patent_names(query: str) -> tuple[str, ...]:
    """Extract explicit company-name candidates from a patent-intent query.

    Two shapes are recognized: a full company-suffixed name anywhere in the
    query ("深圳市普渡科技有限公司有哪些专利"), and a possessive short form
    ("普渡科技的专利有哪些"). Referent/quantifier lookalikes ("这些公司",
    "哪些公司", "该公司") are rejected the same way as in
    :func:`followup_referents._has_explicit_company_name`.
    """
    names = [
        match.group(1)
        for match in COMPANY_NAME_PATTERN.finditer(query)
        if not any(
            marker in match.group(1) for marker in _EXPLICIT_COMPANY_REJECT_MARKERS
        )
    ]
    possessive = _NAMED_COMPANY_PATENT_PATTERN.search(query)
    if possessive is not None:
        name = possessive.group("name")
        if not any(marker in name for marker in _EXPLICIT_COMPANY_REJECT_MARKERS):
            names.append(name)
    return tuple(dict.fromkeys(names))


def _resolve_named_company_patent_source(
    query: str,
    company_projections: tuple[CompanyProjection, ...],
) -> tuple[CompanyProjection, str] | None:
    """Resolve a patent-intent query naming a company to one unique projection.

    Company mirror of :func:`_resolve_named_professor_research_source`: the
    same-turn named-source traversal is only proposed when the query carries
    patent intent ("专利") and names exactly one accepted Company — by full
    legal name, normalized short name, or alias. Both matching channels run
    for every query: explicit extraction (company-suffixed or possessive
    names) and verbatim short-name/alias hits; matches from either channel
    are deduplicated by ``canonical_identity_id``. A bare short name with no
    company suffix ("普渡科技有哪些专利") still binds when the projection's
    own normalized name or alias appears verbatim in the query; any ambiguity
    (zero or several distinct projections, e.g. "深圳市普渡科技有限公司和
    优必选有哪些专利") falls back to the normal lanes instead of guessing.

    Returns the projection together with the surface form the user actually
    typed, so the rebuilt request's displayed entity name is guaranteed to
    appear in the query text.
    """
    if "专利" not in query:
        return None
    names = _named_company_patent_names(query)
    matched: dict[str, tuple[CompanyProjection, str]] = {}
    for projection in company_projections:
        for name in names:
            if (
                name == projection.name
                or name == projection.normalized_name
                or name in projection.aliases
            ):
                matched[projection.canonical_identity_id] = (projection, name)
                break
    for projection in company_projections:
        for candidate in (projection.normalized_name, *projection.aliases):
            if len(candidate) >= 2 and candidate in query:
                # setdefault keeps the explicit extraction's surface form
                # when the same projection also hits verbatim in the query.
                matched.setdefault(
                    projection.canonical_identity_id,
                    (projection, candidate),
                )
                break
    if len(matched) != 1:
        return None
    return next(iter(matched.values()))


_SAME_NAME_PERSON_QUERY_PATTERN = re.compile(
    r"^(?:请问|请介绍一下|请介绍|介绍一下|介绍|我想了解|帮我查(?:一下)?)?\s*"
    r"(?P<name>[一-鿿·]{2,4})(?:教授|老师)?"
    r"(?:的)?(?:是谁|是什么人|简介|信息|情况|资料|评价如何|怎么样)?"
    r"[？?。！!]?$"
)


def _same_name_person_name(query: str) -> str | None:
    institution_person_name = extract_institution_person_name(query)
    if institution_person_name is not None:
        return institution_person_name
    match = _SAME_NAME_PERSON_QUERY_PATTERN.match(query.strip())
    if match is None:
        return None
    return match.group("name")


def _resolved_institution_names(
    query: str,
    institution_catalog: InstitutionCatalog,
) -> tuple[str, ...]:
    slots, _ = _resolve_institutions(query, institution_catalog)
    entries = {entry.canonical_id: entry for entry in institution_catalog.entries}
    return tuple(
        dict.fromkeys(
            entries[slot.canonical_id].canonical_name
            for slot in slots
            if slot.resolution_state == "resolved"
            and slot.canonical_id is not None
            and slot.canonical_id in entries
        )
    )


def _resolve_same_name_professor_candidates(
    query: str,
    professor_projections: tuple[ProfessorProjection, ...],
    institution_catalog: InstitutionCatalog | None = None,
) -> tuple[AmbiguityCandidate, ...]:
    """Resolve an explicit person name to same-name Professor candidates.

    When the name binds two or more distinct accepted Professors, each match
    becomes one evidence-bound ambiguity candidate so the injected policy can
    gate the turn. Evidence confidence is the candidate's deterministic share
    of the strongest accepted-assertion count in the same-name set; a model
    self-score can never clear the gate.

    An explicit resolved institution constraint protects the gate: only
    candidates whose projection institution exactly equals a resolved catalog
    canonical name stay in the gated set. One remaining match proceeds
    un-gated toward that Professor; zero remaining matches falls back to the
    normal lanes instead of selecting a constraint-violating candidate.
    """
    name = _same_name_person_name(query)
    if name is None:
        return ()
    matched = {
        projection.canonical_identity_id: projection
        for projection in professor_projections
        if (
            projection.name == name
            or projection.canonical_name_zh == name
            or name in projection.aliases
        )
    }
    if len(matched) < 2:
        return ()
    if institution_catalog is not None:
        institution_names = _resolved_institution_names(query, institution_catalog)
        if institution_names:
            matched = {
                canonical_id: projection
                for canonical_id, projection in matched.items()
                if projection.institution in institution_names
            }
            if len(matched) < 2:
                return ()
    ordered = tuple(matched[canonical_id] for canonical_id in sorted(matched))
    evidence_by_id = {
        projection.canonical_identity_id: tuple(
            dict.fromkeys(reference.assertion_id for reference in projection.evidence)
        )
        for projection in ordered
    }
    strongest = max(len(evidence_ids) for evidence_ids in evidence_by_id.values())
    candidates: list[AmbiguityCandidate] = []
    for projection in ordered:
        canonical_id = projection.canonical_identity_id
        evidence_ids = evidence_by_id[canonical_id]
        confidence = len(evidence_ids) / strongest
        candidates.append(
            AmbiguityCandidate(
                candidate_id=f"ambiguity-candidate:{canonical_id}",
                entity_type="professor",
                canonical_id=canonical_id,
                display_name=projection.name,
                evidence_ids=evidence_ids,
                evidence_confidence=confidence,
                model_confidence=confidence,
                discriminators=tuple(
                    CandidateDiscriminator(
                        kind=kind,
                        value=value,
                        evidence_ids=evidence_ids[:1],
                    )
                    for kind, value in (
                        ("institution", projection.institution),
                        ("title", projection.title),
                    )
                    if value
                ),
            )
        )
    return tuple(candidates)


class _ReleaseBoundQueryPlanner(_QueryPlanner):
    def __init__(
        self,
        *,
        release_id: str,
        release_binding: PlanningReleaseBinding,
        delegate: _QueryPlanner,
        ambiguity_delegate: _QueryPlanner | None = None,
        named_professor_projections: tuple[ProfessorProjection, ...] = (),
        named_company_projections: tuple[CompanyProjection, ...] = (),
        institution_catalog: InstitutionCatalog | None = None,
    ) -> None:
        self._release_id = release_id
        self._release_binding = release_binding
        self._delegate = delegate
        self._ambiguity_delegate = ambiguity_delegate
        self._named_professor_projections = named_professor_projections
        self._named_company_projections = named_company_projections
        self._institution_catalog = institution_catalog

    def plan(self, request: QueryPlanningRequest) -> RetrievalPlan:
        validated_request = _validated_exact_model(
            request,
            QueryPlanningRequest,
            "planning request",
        )
        if validated_request.release_id != self._release_id:
            raise IsolatedQueryPlanningIntegrityError(
                "planning request release differs from the isolated bundle"
            )
        request_rebuilt = False
        if not validated_request.displayed_entity_ids:
            named_entity_id: str | None = None
            named_entity_name: str | None = None
            named_professor = _resolve_named_professor_research_source(
                validated_request.original_query,
                self._named_professor_projections,
            )
            if named_professor is not None:
                named_entity_id = named_professor.canonical_identity_id
                named_entity_name = named_professor.name
            else:
                named_company = _resolve_named_company_patent_source(
                    validated_request.original_query,
                    self._named_company_projections,
                )
                if named_company is not None:
                    named_entity_id = named_company[0].canonical_identity_id
                    # Bind the surface form the user actually typed so the
                    # serving proposal's name-in-query checks recognize the
                    # same-turn anchor even for short-form names
                    # ("普渡科技的专利有哪些").
                    named_entity_name = named_company[1]
            if named_entity_id is not None:
                request_rebuilt = True
                payload = validated_request.model_dump(
                    mode="json",
                    exclude={"content_sha256"},
                )
                payload["displayed_entity_ids"] = [named_entity_id]
                payload["displayed_entity_names"] = [named_entity_name]
                validated_request = _validated_exact_model(
                    QueryPlanningRequest.model_validate(payload),
                    QueryPlanningRequest,
                    "planning request",
                )
        if (
            self._ambiguity_delegate is not None
            and not validated_request.displayed_entity_ids
            and not validated_request.ambiguity_candidates
        ):
            same_name_candidates = _resolve_same_name_professor_candidates(
                validated_request.original_query,
                self._named_professor_projections,
                self._institution_catalog,
            )
            if same_name_candidates:
                request_rebuilt = True
                payload = validated_request.model_dump(
                    mode="json",
                    exclude={
                        "content_sha256",
                        "original_query_sha256",
                        "ambiguity_candidate_manifest_sha256",
                    },
                )
                payload["ambiguity_candidates"] = [
                    candidate.model_dump(mode="json")
                    for candidate in same_name_candidates
                ]
                validated_request = _validated_exact_model(
                    QueryPlanningRequest.model_validate(payload),
                    QueryPlanningRequest,
                    "planning request",
                )
        delegate = (
            self._ambiguity_delegate
            if self._ambiguity_delegate is not None
            and validated_request.ambiguity_candidates
            else self._delegate
        )
        plan = delegate.plan(validated_request)
        if plan.release_id != self._release_id or plan.release_binding is not None:
            raise IsolatedQueryPlanningIntegrityError(
                "delegated plan differs from its release binding"
            )
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload["release_binding"] = self._release_binding.model_dump(mode="json")
        if request_rebuilt:
            # The plan must still bind the caller's original request; the
            # named-source/ambiguity injections only enrich its constraints.
            payload["request_sha256"] = request.content_sha256
        return RetrievalPlan.model_validate(payload)


def create_isolated_release_query_planner(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    index_projection_request: IndexProjectionRequest,
    release_institution_catalog: InstitutionCatalog,
    planning_policy: QueryPlanningPolicy,
    proposal_provider: Callable[[QueryPlanningRequest], object],
    ambiguity_policy: AmbiguityPolicy | None = None,
) -> _QueryPlanner:
    """Bind query planning to one replayed, accepted isolated S7 release."""

    exact_bundle = _validated_exact_model(
        release_bundle,
        IsolatedReleaseBundle,
        "release bundle",
    )
    exact_publication = _validated_exact_model(
        published_release,
        PublishedRelease,
        "published release",
    )
    validated_bundle, validated_publication = _validated_release_binding(
        release_bundle=exact_bundle,
        published_release=exact_publication,
    )
    validated_index_request = _validated_exact_model(
        index_projection_request,
        IndexProjectionRequest,
        "index projection request",
    )
    validated_catalog = _validated_exact_model(
        release_institution_catalog,
        InstitutionCatalog,
        "release institution catalog",
    )
    validated_policy = _validated_exact_model(
        planning_policy,
        QueryPlanningPolicy,
        "query planning policy",
    )
    validated_ambiguity_policy = (
        _validated_exact_model(
            ambiguity_policy,
            AmbiguityPolicy,
            "ambiguity policy",
        )
        if ambiguity_policy is not None
        else None
    )
    _validate_manifest_hash(validated_bundle)
    _validate_planning_policy(validated_policy)
    if validated_catalog.release_id != validated_bundle.release_id:
        raise IsolatedQueryPlanningIntegrityError(
            "institution catalog release differs from the isolated bundle"
        )

    replayed_index_result = create_ephemeral_index_projection_builder().build(
        validated_index_request
    )
    if replayed_index_result != validated_bundle.index_result:
        raise IsolatedQueryPlanningIntegrityError(
            "replayed release graph differs from the isolated bundle"
        )
    candidate_request = validated_index_request.candidate_projection_request
    candidate_result = validated_index_request.candidate_projection_result
    internal_result = candidate_request.internal_reference_projection_result
    if (
        candidate_request.release_id != validated_bundle.release_id
        or candidate_result.release_id != validated_bundle.release_id
        or candidate_request.build_run_id != candidate_result.build_run_id
        or candidate_result.internal_reference_projection_result_content_sha256
        != internal_result.content_sha256
        or candidate_result.public_domain_projection_result_content_sha256
        != internal_result.public_domain_projection_result_content_sha256
    ):
        raise IsolatedQueryPlanningIntegrityError(
            "candidate projection graph differs from the release manifest"
        )
    manifest_projections = {
        projection.projection_id: projection
        for projection in validated_bundle.manifest.published_projections
    }
    candidate_projections = {
        projection.projection_id: projection
        for projection in candidate_result.published_projections
    }
    if (
        len(manifest_projections)
        != len(validated_bundle.manifest.published_projections)
        or len(candidate_projections) != len(candidate_result.published_projections)
        or manifest_projections != candidate_projections
    ):
        raise IsolatedQueryPlanningIntegrityError(
            "published projection graph differs from the release manifest"
        )

    _validate_institution_catalog(validated_catalog, candidate_result)
    person_references = _derive_person_reference_records(
        candidate_result=candidate_result,
        internal_result=internal_result,
        institution_catalog=validated_catalog,
    )
    technology_routes = _derive_technology_route_records(candidate_result)
    if validated_publication.state is ReleaseState.active:
        publication_state: Literal["active", "rolled_back"] = "active"
    elif validated_publication.state is ReleaseState.rolled_back:
        publication_state = "rolled_back"
    else:
        raise IsolatedQueryPlanningIntegrityError(
            "published release is not serviceable for query planning"
        )
    release_binding = PlanningReleaseBinding(
        release_id=validated_bundle.release_id,
        publication_state=publication_state,
        published_release_sha256=_canonical_sha256(
            validated_publication.model_dump(mode="json")
        ),
        publication_verification_evidence_ids=tuple(
            sorted(validated_publication.verification_evidence_ids)
        ),
        manifest_sha256=validated_bundle.manifest.manifest_sha256,
        index_projection_request_sha256=_canonical_sha256(
            validated_index_request.model_dump(mode="json")
        ),
        index_projection_result_sha256=validated_bundle.index_result.content_sha256,
        candidate_projection_result_sha256=candidate_result.content_sha256,
        internal_reference_projection_result_sha256=internal_result.content_sha256,
        institution_catalog_sha256=validated_catalog.content_sha256,
        planning_policy_sha256=validated_policy.content_sha256,
    )
    delegate = create_ephemeral_query_planner(
        planning_policy=validated_policy,
        institution_catalog=validated_catalog,
        proposal_provider=proposal_provider,
        person_references=person_references,
        technology_routes=technology_routes,
    )
    # The injected ambiguity policy gates only requests that actually carry
    # ambiguity candidates; every other request plans on the policy-free
    # delegate so an absent candidate set can never block ordinary queries.
    ambiguity_delegate = (
        create_ephemeral_query_planner(
            planning_policy=validated_policy,
            institution_catalog=validated_catalog,
            proposal_provider=proposal_provider,
            ambiguity_policy=validated_ambiguity_policy,
            person_references=person_references,
            technology_routes=technology_routes,
        )
        if validated_ambiguity_policy is not None
        else None
    )
    return _ReleaseBoundQueryPlanner(
        release_id=validated_bundle.release_id,
        release_binding=release_binding,
        delegate=delegate,
        ambiguity_delegate=ambiguity_delegate,
        named_professor_projections=tuple(
            projection
            for projection in candidate_result.public_domain_projections
            if isinstance(projection, ProfessorProjection)
        ),
        named_company_projections=tuple(
            projection
            for projection in candidate_result.public_domain_projections
            if isinstance(projection, CompanyProjection)
        ),
        institution_catalog=validated_catalog,
    )


class _ReleaseBoundKnowledgeRead(KnowledgeRead):
    def __init__(
        self,
        *,
        release_bundle: IsolatedReleaseBundle,
        published_release: PublishedRelease,
        delegate: KnowledgeRead,
        supported_lanes: frozenset[str],
        embedding_adapter: EmbeddingAdapter | None,
        internal_reference_authority: _InternalReferenceAuthority | None,
        relationship_authority: _RelationshipAuthority | None,
    ) -> None:
        self._release_bundle = release_bundle
        self._published_release = published_release
        self._delegate = delegate
        self._supported_lanes = supported_lanes
        self._embedding_adapter = embedding_adapter
        self._internal_reference_authority = internal_reference_authority
        self._relationship_authority = relationship_authority
        self._published_release_sha256 = _canonical_sha256(
            published_release.model_dump(mode="json")
        )
        self._publication_verification_evidence_ids = tuple(
            sorted(published_release.verification_evidence_ids)
        )
        self._index_projection_request_sha256 = (
            _canonical_sha256(
                internal_reference_authority.index_request.model_dump(mode="json")
            )
            if internal_reference_authority is not None
            else None
        )

    def execute(self, plan: RetrievalPlan) -> EvidenceSet:
        if type(plan) is not RetrievalPlan:
            raise IsolatedKnowledgeReadIntegrityError(
                "retrieval plan must be an exact RetrievalPlan"
            )
        try:
            validated_plan = RetrievalPlan.model_validate(plan.model_dump(mode="json"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise IsolatedKnowledgeReadIntegrityError(
                "retrieval plan failed exact typed validation"
            ) from exc

        binding = validated_plan.release_binding
        if binding is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound execution requires a planning release binding"
            )
        unsupported_lanes = tuple(
            lane for lane in validated_plan.lanes if lane not in self._supported_lanes
        )
        if unsupported_lanes:
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound execution contains an unsupported lane"
            )
        if (
            validated_plan.relationship_paths
            and "relationship" not in validated_plan.lanes
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "retrieval plan relationship paths require the relationship lane"
            )
        if (
            self._embedding_adapter is not None
            and "vector" in validated_plan.lanes
            and "professor" in validated_plan.domains
            and validated_plan.professor_vector_view is None
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor vector recall requires an explicit typed projection view"
            )

        bundle = self._release_bundle
        publication = self._published_release
        expected_publication_state = (
            "active" if publication.state is ReleaseState.active else "rolled_back"
        )
        if (
            validated_plan.release_id != bundle.release_id
            or binding.release_id != bundle.release_id
            or binding.publication_state != expected_publication_state
            or binding.published_release_sha256 != self._published_release_sha256
            or binding.publication_verification_evidence_ids
            != self._publication_verification_evidence_ids
            or binding.manifest_sha256 != bundle.manifest.manifest_sha256
            or binding.index_projection_result_sha256
            != bundle.index_result.content_sha256
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "retrieval plan differs from its isolated release binding"
            )
        authority = self._internal_reference_authority
        if authority is not None:
            candidate_result = authority.index_request.candidate_projection_result
            if (
                binding.index_projection_request_sha256
                != self._index_projection_request_sha256
                or binding.candidate_projection_result_sha256
                != candidate_result.content_sha256
                or binding.internal_reference_projection_result_sha256
                != authority.internal_result.content_sha256
                or binding.institution_catalog_sha256
                != authority.institution_catalog.content_sha256
            ):
                raise IsolatedKnowledgeReadIntegrityError(
                    "retrieval plan differs from its internal reference release binding"
                )
            if "internal_reference" in validated_plan.lanes:
                _validate_internal_reference_request(
                    _lane_request(
                        validated_plan,
                        "internal_reference",
                        validated_plan.web_policy,
                    ),
                    authority,
                )
        relationship_authority = self._relationship_authority
        if (
            relationship_authority is not None
            and "relationship" in validated_plan.lanes
        ):
            relationship_request = _validate_relationship_request(
                _lane_request(
                    validated_plan,
                    "relationship",
                    validated_plan.web_policy,
                ),
                relationship_authority,
            )
            path = relationship_request.relationship_paths[0]
            path_key = (
                path.relationship_type_id,
                path.direction,
                path.source_type,
                path.target_type,
            )
            if path_key in {
                _PROFESSOR_TO_COMPANY_QUERY_PATH,
                _COMPANY_TO_PROFESSOR_QUERY_PATH,
            }:
                enumeration = relationship_request.relationship_enumeration_policy
                displayed_ids = (
                    relationship_request.structured_constraints.displayed_entity_ids
                )
                protected_sets = tuple(
                    slot.entity_ids
                    for slot in relationship_request.protected_slots
                    if slot.kind == "displayed_entity_set"
                )
                if (
                    validated_plan.as_of is None
                    or validated_plan.enumeration_policy is None
                    or enumeration is None
                    or enumeration.as_of != validated_plan.as_of
                    or enumeration != validated_plan.enumeration_policy
                    or len(displayed_ids) != 1
                    or not displayed_ids[0]
                    or protected_sets != (displayed_ids,)
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source/policy differs from its plan"
                    )
                displayed_id = displayed_ids[0]
                known_public = {
                    projection.canonical_identity_id: projection.entity_type
                    for projection in relationship_authority.candidate_result.public_domain_projections
                }
                internal_ids = {
                    projection.canonical_person_identity_id
                    for projection in relationship_authority.candidate_result.person_projections
                } | {
                    projection.canonical_technology_identity_id
                    for projection in (
                        *relationship_authority.candidate_result.technology_concept_projections,
                        *relationship_authority.candidate_result.technology_route_projections,
                    )
                }
                if displayed_id in internal_ids or (
                    displayed_id in known_public
                    and known_public[displayed_id] != path.source_type
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source has the wrong canonical domain"
                    )
            elif path_key == _COMPANY_TO_PATENT_QUERY_PATH:
                enumeration = relationship_request.relationship_enumeration_policy
                displayed_ids = (
                    relationship_request.structured_constraints.displayed_entity_ids
                )
                protected_sets = tuple(
                    slot.entity_ids
                    for slot in relationship_request.protected_slots
                    if slot.kind == "displayed_entity_set"
                )
                if (
                    validated_plan.as_of is None
                    or validated_plan.enumeration_policy is None
                    or enumeration is None
                    or enumeration.as_of != validated_plan.as_of
                    or enumeration != validated_plan.enumeration_policy
                    or len(displayed_ids) != 1
                    or not displayed_ids[0]
                    or protected_sets != (displayed_ids,)
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source/policy differs from its plan"
                    )
                displayed_id = displayed_ids[0]
                known_public = {
                    projection.canonical_identity_id: projection.entity_type
                    for projection in relationship_authority.candidate_result.public_domain_projections
                }
                internal_ids = {
                    projection.canonical_person_identity_id
                    for projection in relationship_authority.candidate_result.person_projections
                } | {
                    projection.canonical_technology_identity_id
                    for projection in (
                        *relationship_authority.candidate_result.technology_concept_projections,
                        *relationship_authority.candidate_result.technology_route_projections,
                    )
                }
                if displayed_id in internal_ids or (
                    displayed_id in known_public
                    and known_public[displayed_id] != "company"
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source is not an accepted Company"
                    )
            elif path_key == _PATENT_TO_COMPANY_QUERY_PATH:
                enumeration = relationship_request.relationship_enumeration_policy
                displayed_ids = (
                    relationship_request.structured_constraints.displayed_entity_ids
                )
                protected_sets = tuple(
                    slot.entity_ids
                    for slot in relationship_request.protected_slots
                    if slot.kind == "displayed_entity_set"
                )
                if (
                    validated_plan.as_of is None
                    or validated_plan.enumeration_policy is None
                    or enumeration is None
                    or enumeration.as_of != validated_plan.as_of
                    or enumeration != validated_plan.enumeration_policy
                    or len(displayed_ids) != 1
                    or not displayed_ids[0]
                    or protected_sets != (displayed_ids,)
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source/policy differs from its plan"
                    )
                displayed_id = displayed_ids[0]
                known_public = {
                    projection.canonical_identity_id: projection.entity_type
                    for projection in relationship_authority.candidate_result.public_domain_projections
                }
                internal_ids = {
                    projection.canonical_person_identity_id
                    for projection in relationship_authority.candidate_result.person_projections
                } | {
                    projection.canonical_technology_identity_id
                    for projection in (
                        *relationship_authority.candidate_result.technology_concept_projections,
                        *relationship_authority.candidate_result.technology_route_projections,
                    )
                }
                if displayed_id in internal_ids or (
                    displayed_id in known_public
                    and known_public[displayed_id] != "patent"
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source is not an accepted Patent"
                    )
            elif path_key == _PROFESSOR_TO_PAPER_QUERY_PATH:
                enumeration = relationship_request.relationship_enumeration_policy
                displayed_ids = (
                    relationship_request.structured_constraints.displayed_entity_ids
                )
                protected_sets = tuple(
                    slot.entity_ids
                    for slot in relationship_request.protected_slots
                    if slot.kind == "displayed_entity_set"
                )
                if (
                    validated_plan.as_of is None
                    or validated_plan.enumeration_policy is None
                    or enumeration is None
                    or enumeration.as_of != validated_plan.as_of
                    or enumeration != validated_plan.enumeration_policy
                    or len(displayed_ids) != 1
                    or not displayed_ids[0]
                    or protected_sets != (displayed_ids,)
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source/policy differs from its plan"
                    )
                displayed_id = displayed_ids[0]
                known_public = {
                    projection.canonical_identity_id: projection.entity_type
                    for projection in relationship_authority.candidate_result.public_domain_projections
                }
                internal_ids = {
                    projection.canonical_person_identity_id
                    for projection in relationship_authority.candidate_result.person_projections
                } | {
                    projection.canonical_technology_identity_id
                    for projection in (
                        *relationship_authority.candidate_result.technology_concept_projections,
                        *relationship_authority.candidate_result.technology_route_projections,
                    )
                }
                if displayed_id in internal_ids or (
                    displayed_id in known_public
                    and known_public[displayed_id] != "professor"
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source is not an accepted Professor"
                    )
            elif path_key == _PAPER_TO_PROFESSOR_QUERY_PATH:
                enumeration = relationship_request.relationship_enumeration_policy
                displayed_ids = (
                    relationship_request.structured_constraints.displayed_entity_ids
                )
                protected_sets = tuple(
                    slot.entity_ids
                    for slot in relationship_request.protected_slots
                    if slot.kind == "displayed_entity_set"
                )
                if (
                    validated_plan.as_of is None
                    or validated_plan.enumeration_policy is None
                    or enumeration is None
                    or enumeration.as_of != validated_plan.as_of
                    or enumeration != validated_plan.enumeration_policy
                    or len(displayed_ids) != 1
                    or not displayed_ids[0]
                    or protected_sets != (displayed_ids,)
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source/policy differs from its plan"
                    )
                displayed_id = displayed_ids[0]
                known_public = {
                    projection.canonical_identity_id: projection.entity_type
                    for projection in relationship_authority.candidate_result.public_domain_projections
                }
                internal_ids = {
                    projection.canonical_person_identity_id
                    for projection in relationship_authority.candidate_result.person_projections
                } | {
                    projection.canonical_technology_identity_id
                    for projection in (
                        *relationship_authority.candidate_result.technology_concept_projections,
                        *relationship_authority.candidate_result.technology_route_projections,
                    )
                }
                if displayed_id in internal_ids or (
                    displayed_id in known_public
                    and known_public[displayed_id] != "paper"
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "public relationship source is not an accepted Paper"
                    )
            else:
                relationship_query = (
                    relationship_request.relationship_reference_queries[0]
                )
                if (
                    validated_plan.as_of is None
                    or validated_plan.enumeration_policy is None
                    or relationship_query.as_of != validated_plan.as_of
                    or relationship_query.enumeration_policy
                    != validated_plan.enumeration_policy
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "relationship query scope/as_of/enumeration differs from its plan"
                    )
            _build_relationship_result(
                request=relationship_request,
                authority=relationship_authority,
            )
        result = self._delegate.execute(validated_plan)
        if self._embedding_adapter is not None and "vector" in validated_plan.lanes:
            _validate_release_bound_vector_evidence(
                plan=validated_plan,
                evidence_set=result,
                bundle=bundle,
                publication=publication,
                embedding_adapter=self._embedding_adapter,
            )
        if authority is not None and "internal_reference" in validated_plan.lanes:
            _validate_release_bound_internal_reference_evidence(
                plan=validated_plan,
                evidence_set=result,
                authority=authority,
            )
        if (
            relationship_authority is not None
            and "relationship" in validated_plan.lanes
        ):
            _validate_release_bound_relationship_evidence(
                plan=validated_plan,
                evidence_set=result,
                authority=relationship_authority,
            )
        return result


def create_isolated_release_knowledge_read(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    universal_web_policy: WebSearchPolicy,
    web_search: Callable[[LaneRequest], object],
    web_snapshot_policy: WebSnapshotPolicy,
    embedding_adapter: EmbeddingAdapter | None = None,
    reuse_audited_vector_snapshot: bool = False,
    vectorized_recall: bool = False,
    fast_boot: bool = False,
    index_projection_request: IndexProjectionRequest | None = None,
    release_institution_catalog: InstitutionCatalog | None = None,
    identity_fuser: Callable[[IdentityFusionRequest], object] | None = None,
    reranker: Callable[[RerankRequest], object] | None = None,
    sufficiency_decider: Callable[[SufficiencyDecisionRequest], object] | None = None,
    supplemental_search: Callable[[SupplementalRequest], object] | None = None,
    web_handle_resolver: Callable[[WebHandleResolutionRequest], object] | None = None,
    accepted_identity_lookup: Callable[[AcceptedIdentityLookupRequest], object]
    | None = None,
    manual_recall_provider: Any | None = None,
    web_handle_ttl: timedelta = timedelta(hours=1),
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> KnowledgeRead:
    """Compose release-bound physical lookup with one explicit current-Web port."""

    try:
        exact_bundle = _validated_exact_model(
            release_bundle,
            IsolatedReleaseBundle,
            "release bundle",
        )
    except (TypeError, IsolatedQueryPlanningIntegrityError) as exc:
        raise IsolatedKnowledgeReadIntegrityError(
            "release bundle failed exact typed validation"
        ) from exc
    try:
        exact_publication = _validated_exact_model(
            published_release,
            PublishedRelease,
            "published release",
        )
    except (TypeError, IsolatedQueryPlanningIntegrityError) as exc:
        raise IsolatedKnowledgeReadIntegrityError(
            "published release failed exact typed validation"
        ) from exc
    validated_bundle, validated_publication = _validated_release_binding(
        release_bundle=exact_bundle,
        published_release=exact_publication,
    )
    _validate_manifest_hash(validated_bundle)
    try:
        validated_web_policy = _validated_exact_model(
            universal_web_policy,
            WebSearchPolicy,
            "Universal Web policy",
        )
        validated_snapshot_policy = _validated_exact_model(
            web_snapshot_policy,
            WebSnapshotPolicy,
            "Web snapshot policy",
        )
    except (TypeError, IsolatedQueryPlanningIntegrityError) as exc:
        raise IsolatedKnowledgeReadIntegrityError(
            "Web policy failed exact typed validation"
        ) from exc
    if (
        validated_web_policy.mode != "universal"
        or validated_web_policy.max_provider_calls <= 0
        or validated_web_policy.timeout_ms <= 0
        or validated_web_policy.max_results <= 0
        or validated_web_policy.allowed_domains
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound Universal Web policy must be positive and unscoped"
        )
    if not callable(web_search):
        raise TypeError("web_search must be callable")
    if not callable(clock):
        raise TypeError("clock must be callable")
    if not isinstance(reuse_audited_vector_snapshot, bool):
        raise TypeError("reuse_audited_vector_snapshot must be a Boolean")
    if not isinstance(vectorized_recall, bool):
        raise TypeError("vectorized_recall must be a Boolean")
    if vectorized_recall and not reuse_audited_vector_snapshot:
        raise ValueError("vectorized_recall requires an audited reusable snapshot")
    if not isinstance(fast_boot, bool):
        raise TypeError("fast_boot must be a Boolean")
    if (index_projection_request is None) != (release_institution_catalog is None):
        raise IsolatedKnowledgeReadIntegrityError(
            "index projection request and institution catalog must be provided as one pair"
        )

    internal_reference_authority = (
        _replay_internal_reference_authority(
            release_bundle=validated_bundle,
            published_release=validated_publication,
            index_projection_request=index_projection_request,
            release_institution_catalog=release_institution_catalog,
        )
        if index_projection_request is not None
        and release_institution_catalog is not None
        else None
    )
    relationship_authority = (
        _replay_relationship_authority(
            release_bundle=validated_bundle,
            published_release=validated_publication,
            index_projection_request=internal_reference_authority.index_request,
            release_institution_catalog=(
                internal_reference_authority.institution_catalog
            ),
            internal_authority=internal_reference_authority,
        )
        if internal_reference_authority is not None
        and validated_bundle.relationship_projection_request is not None
        and validated_bundle.relationship_projection_result is not None
        else None
    )

    # The audited lookup view is created lazily on first exact/structured/
    # lexical/internal-reference use, never during factory construction: a
    # relationship-only or web-only plan must execute without touching
    # physical documents (S8R in-memory traversal contract, S8E fail-before-
    # lookup). Internal-reference execution reads the bound documents on
    # first use (its S11 design); each adapter builds its own view lazily and
    # the bounded document cache deduplicates the physical read.
    lane_adapters: dict[str, Callable[[LaneRequest], RetrievalLaneResult]] = {
        "exact": create_isolated_exact_lookup_adapter(
            release_bundle=validated_bundle,
            published_release=validated_publication,
        ),
        "structured": create_isolated_structured_lookup_adapter(
            release_bundle=validated_bundle,
            published_release=validated_publication,
        ),
        "lexical": create_isolated_lexical_lookup_adapter(
            release_bundle=validated_bundle,
            published_release=validated_publication,
        ),
    }
    supported_lanes = {"exact", "structured", "lexical", "web"}
    if embedding_adapter is not None:
        lane_adapters["vector"] = create_isolated_vector_recall_adapter(
            release_bundle=validated_bundle,
            published_release=validated_publication,
            embedding_adapter=embedding_adapter,
            reuse_audited_snapshot=reuse_audited_vector_snapshot,
            vectorized_scoring=vectorized_recall,
            fast_boot=fast_boot,
            manual_recall_provider=manual_recall_provider,
        )
        supported_lanes.add("vector")
    if internal_reference_authority is not None:
        lane_adapters["internal_reference"] = (
            create_isolated_internal_reference_lookup_adapter(
                release_bundle=validated_bundle,
                published_release=validated_publication,
                index_projection_request=internal_reference_authority.index_request,
                release_institution_catalog=(
                    internal_reference_authority.institution_catalog
                ),
            )
        )
        supported_lanes.add("internal_reference")
    if relationship_authority is not None:
        lane_adapters["relationship"] = create_isolated_relationship_lookup_adapter(
            release_bundle=validated_bundle,
            published_release=validated_publication,
            index_projection_request=relationship_authority.internal_authority.index_request,
            release_institution_catalog=(
                relationship_authority.internal_authority.institution_catalog
            ),
        )
        supported_lanes.add("relationship")

    delegate = create_ephemeral_knowledge_read(
        universal_web_policy=validated_web_policy,
        lane_adapters=lane_adapters,
        web_search=web_search,
        identity_fuser=identity_fuser,
        reranker=reranker,
        sufficiency_decider=sufficiency_decider,
        supplemental_search=supplemental_search,
        web_handle_resolver=web_handle_resolver,
        accepted_identity_lookup=accepted_identity_lookup,
        clock=clock,
        web_handle_ttl=web_handle_ttl,
        web_snapshot_policy=validated_snapshot_policy,
    )
    return _ReleaseBoundKnowledgeRead(
        release_bundle=validated_bundle,
        published_release=validated_publication,
        delegate=delegate,
        supported_lanes=frozenset(supported_lanes),
        embedding_adapter=embedding_adapter,
        internal_reference_authority=internal_reference_authority,
        relationship_authority=relationship_authority,
    )


def _validated_exact_model(
    value: Any,
    model_type: type[Any],
    label: str,
) -> Any:
    if type(value) is not model_type:
        raise TypeError(f"{label} must be an exact {model_type.__name__}")
    try:
        return model_type.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise IsolatedQueryPlanningIntegrityError(
            f"{label} failed exact typed validation"
        ) from exc


def _validate_manifest_hash(bundle: IsolatedReleaseBundle) -> None:
    payload = bundle.manifest.model_dump(
        mode="json",
        exclude={"manifest_sha256"},
    )
    if bundle.manifest.manifest_sha256 != _canonical_sha256(payload):
        raise IsolatedQueryPlanningIntegrityError(
            "manifest stored hash does not bind the complete manifest"
        )


def _validate_planning_policy(policy: QueryPlanningPolicy) -> None:
    public_domains = policy.public_domains
    if (
        len(public_domains) != len(set(public_domains))
        or set(public_domains) != _PUBLIC_DOMAINS
    ):
        raise IsolatedQueryPlanningIntegrityError(
            "planning policy public domain registry must be exactly the four public domains"
        )
    supported_lanes = policy.supported_lanes
    if len(supported_lanes) != len(set(supported_lanes)) or any(
        lane not in _SUPPORTED_LANES for lane in supported_lanes
    ):
        raise IsolatedQueryPlanningIntegrityError(
            "planning policy lane registry contains a duplicate or unsupported lane"
        )


def _validate_institution_catalog(
    catalog: InstitutionCatalog,
    candidate_result: Any,
) -> None:
    observed: defaultdict[str, set[str]] = defaultdict(set)

    def retain(reference: Any, *, institution_field: bool) -> None:
        if not reference.reference_id.startswith("institution:"):
            if institution_field:
                raise IsolatedQueryPlanningIntegrityError(
                    "institution catalog source uses a non-institution reference ID"
                )
            return
        observed[reference.reference_id].add(reference.name)

    for projection in candidate_result.public_domain_projections:
        if isinstance(projection, CompanyProjection):
            for education in projection.personnel_education:
                retain(education.institution, institution_field=True)
        elif isinstance(projection, ProfessorProjection):
            for affiliation in projection.affiliation_history:
                retain(affiliation.institution, institution_field=True)
            for education in projection.education_history:
                retain(education.institution, institution_field=True)
        elif isinstance(projection, PaperProjection):
            for author in projection.authors:
                for affiliation in author.affiliations:
                    retain(affiliation, institution_field=False)
        elif isinstance(projection, PatentProjection):
            for inventor in projection.inventors:
                if inventor.affiliation is not None:
                    retain(inventor.affiliation, institution_field=False)

    catalog_ids = tuple(entry.canonical_id for entry in catalog.entries)
    if len(catalog_ids) != len(set(catalog_ids)) or set(catalog_ids) != set(observed):
        raise IsolatedQueryPlanningIntegrityError(
            "institution catalog IDs differ from observed release institutions"
        )
    for entry in catalog.entries:
        names = (entry.canonical_name, *entry.aliases)
        if len(names) != len(set(names)) or set(names) != observed[entry.canonical_id]:
            raise IsolatedQueryPlanningIntegrityError(
                "institution catalog names differ from observed release institutions"
            )


_PERSON_SUBOBJECT_FIELDS = {
    "company_personnel": "key_personnel",
    "company_personnel_education": "personnel_education",
    "company_personnel_work_experience": "personnel_work_experience",
    "paper_author": "authors",
    "patent_inventor": "inventors",
    "professor_education": "education_history",
    "professor_work_history": "work_history",
}
_PERSON_FACT_ORDER = {"education": 0, "company_role": 1, "geography": 2}


def _person_source_subobject(projection: Any, anchor: Any) -> Any | None:
    if anchor.source_kind == "professor":
        if anchor.source_subobject_id is not None:
            raise IsolatedQueryPlanningIntegrityError(
                "Professor Person anchor unexpectedly names a subobject"
            )
        return None
    field_name = _PERSON_SUBOBJECT_FIELDS.get(anchor.source_kind)
    if field_name is None or anchor.source_subobject_id is None:
        raise IsolatedQueryPlanningIntegrityError(
            "Person anchor has no supported typed public source"
        )
    matches = tuple(
        item
        for item in getattr(projection, field_name, ())
        if item.subobject_id == anchor.source_subobject_id
    )
    if len(matches) != 1:
        raise IsolatedQueryPlanningIntegrityError(
            "Person anchor typed public source is missing or duplicated"
        )
    return matches[0]


def _derive_person_reference_records(
    *,
    candidate_result: Any,
    internal_result: Any,
    institution_catalog: InstitutionCatalog,
) -> tuple[PersonReferenceRecord, ...]:
    projections = {
        (projection.entity_type, projection.canonical_identity_id): projection
        for projection in candidate_result.public_domain_projections
    }
    anchors = {
        anchor.anchor_id: anchor for anchor in internal_result.public_evidence_anchors
    }
    catalog_entries = {
        entry.canonical_id: entry for entry in institution_catalog.entries
    }

    def joined_source(reference: Any) -> tuple[Any, Any, Any | None]:
        anchor = anchors.get(reference.source_anchor_id)
        if anchor is None:
            raise IsolatedQueryPlanningIntegrityError(
                "Person reference has no exact public evidence anchor"
            )
        projection = projections.get(
            (anchor.public_domain, anchor.root_canonical_identity_id)
        )
        if (
            projection is None
            or projection.release_id != internal_result.release_id
            or projection.content_sha256 != anchor.root_projection_content_sha256
        ):
            raise IsolatedQueryPlanningIntegrityError(
                "Person public evidence anchor is cross-wired to its projection"
            )
        return anchor, projection, _person_source_subobject(projection, anchor)

    records: list[PersonReferenceRecord] = []
    for person in candidate_result.person_projections:
        facts: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
        evidence_ids: set[str] = set()
        company_roots: dict[str, CompanyProjection] = {}
        for reference in person.references:
            anchor, projection, subobject = joined_source(reference)
            evidence_ids.add(anchor.anchor_id)
            evidence = set(anchor.supporting_assertion_ids)
            if isinstance(projection, CompanyProjection):
                company_roots[projection.canonical_identity_id] = projection
            if anchor.source_kind in {
                "company_personnel_education",
                "professor_education",
            }:
                if subobject is None:
                    raise IsolatedQueryPlanningIntegrityError(
                        "Person education anchor lacks its typed subobject"
                    )
                institution = subobject.institution
                catalog_entry = catalog_entries.get(institution.reference_id)
                if catalog_entry is None:
                    raise IsolatedQueryPlanningIntegrityError(
                        "Person education differs from the institution catalog"
                    )
                facts[("education", catalog_entry.canonical_name)].update(evidence)
            elif anchor.source_kind in {
                "company_personnel",
                "company_personnel_work_experience",
            }:
                if subobject is None:
                    raise IsolatedQueryPlanningIntegrityError(
                        "Person role anchor lacks its typed subobject"
                    )
                facts[("company_role", _normalize(subobject.role))].update(evidence)

        for company in company_roots.values() if len(company_roots) == 1 else ():
            if company.geography is None:
                continue
            geography_lineage = tuple(
                lineage
                for lineage in company.field_lineage
                if lineage.field_path == "geography"
            )
            if len(geography_lineage) != 1:
                raise IsolatedQueryPlanningIntegrityError(
                    "Company geography lacks exact retained field lineage"
                )
            facts[("geography", company.geography.name)].update(
                geography_lineage[0].supporting_assertion_ids
            )

        typed_facts = tuple(
            InternalReferenceFact(
                field=field,
                value=value,
                evidence_ids=tuple(sorted(fact_evidence)),
            )
            for (field, value), fact_evidence in sorted(
                facts.items(),
                key=lambda item: (
                    _PERSON_FACT_ORDER.get(item[0][0], len(_PERSON_FACT_ORDER)),
                    item[0][0],
                    item[0][1],
                ),
            )
        )
        records.append(
            PersonReferenceRecord(
                reference_id=person.canonical_person_identity_id,
                release_id=person.release_id,
                resolution_state="resolved",
                canonical_person_id=person.canonical_person_identity_id,
                public_domain_evidence_ids=tuple(sorted(evidence_ids)),
                typed_facts=typed_facts,
            )
        )

    for reference in internal_result.unresolved_person_references:
        anchor, _, _ = joined_source(reference)
        records.append(
            PersonReferenceRecord(
                reference_id=reference.reference_id,
                release_id=internal_result.release_id,
                resolution_state="unresolved",
                canonical_person_id=None,
                public_domain_evidence_ids=(anchor.anchor_id,),
                typed_facts=(),
            )
        )
    return tuple(sorted(records, key=lambda record: record.reference_id))


def _derive_technology_route_records(
    candidate_result: Any,
) -> tuple[TechnologyRouteRecord, ...]:
    records: list[TechnologyRouteRecord] = []
    for route in candidate_result.technology_route_projections:
        definition_lineage = tuple(
            lineage
            for lineage in route.field_lineage
            if lineage.field_path == "technology.definition"
        )
        if len(definition_lineage) != 1:
            raise IsolatedQueryPlanningIntegrityError(
                "Technology route definition lacks exact retained lineage"
            )
        records.append(
            TechnologyRouteRecord(
                reference_id=route.canonical_technology_identity_id,
                release_id=route.release_id,
                canonical_route_id=route.canonical_technology_identity_id,
                canonical_name=route.preferred_name,
                aliases=route.aliases,
                definition_evidence_ids=(
                    definition_lineage[0].supporting_assertion_ids
                ),
            )
        )
    return tuple(sorted(records, key=lambda record: record.reference_id))


def _replay_internal_reference_authority(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    index_projection_request: IndexProjectionRequest,
    release_institution_catalog: InstitutionCatalog,
) -> _InternalReferenceAuthority:
    try:
        exact_bundle = _validated_exact_model(
            release_bundle,
            IsolatedReleaseBundle,
            "release bundle",
        )
        exact_publication = _validated_exact_model(
            published_release,
            PublishedRelease,
            "published release",
        )
        exact_index_request = _validated_exact_model(
            index_projection_request,
            IndexProjectionRequest,
            "index projection request",
        )
        exact_catalog = _validated_exact_model(
            release_institution_catalog,
            InstitutionCatalog,
            "release institution catalog",
        )
        validated_bundle, validated_publication = _validated_release_binding(
            release_bundle=exact_bundle,
            published_release=exact_publication,
        )
        _validate_manifest_hash(validated_bundle)
        if exact_catalog.release_id != validated_bundle.release_id:
            raise IsolatedQueryPlanningIntegrityError(
                "institution catalog release differs from the isolated bundle"
            )
        replayed_index_result = create_ephemeral_index_projection_builder().build(
            exact_index_request
        )
        if replayed_index_result != validated_bundle.index_result:
            raise IsolatedQueryPlanningIntegrityError(
                "replayed release graph differs from the isolated bundle"
            )

        candidate_request = exact_index_request.candidate_projection_request
        candidate_result = exact_index_request.candidate_projection_result
        internal_result = candidate_request.internal_reference_projection_result
        if (
            candidate_request.release_id != validated_bundle.release_id
            or candidate_result.release_id != validated_bundle.release_id
            or candidate_request.build_run_id != candidate_result.build_run_id
            or candidate_result.internal_reference_projection_result_content_sha256
            != internal_result.content_sha256
            or candidate_result.public_domain_projection_result_content_sha256
            != internal_result.public_domain_projection_result_content_sha256
        ):
            raise IsolatedQueryPlanningIntegrityError(
                "candidate projection graph differs from the release manifest"
            )
        manifest_projections = {
            projection.projection_id: projection
            for projection in validated_bundle.manifest.published_projections
        }
        candidate_projections = {
            projection.projection_id: projection
            for projection in candidate_result.published_projections
        }
        if (
            len(manifest_projections)
            != len(validated_bundle.manifest.published_projections)
            or len(candidate_projections) != len(candidate_result.published_projections)
            or manifest_projections != candidate_projections
        ):
            raise IsolatedQueryPlanningIntegrityError(
                "published projection graph differs from the release manifest"
            )
        _validate_institution_catalog(exact_catalog, candidate_result)
        person_records = _derive_person_reference_records(
            candidate_result=candidate_result,
            internal_result=internal_result,
            institution_catalog=exact_catalog,
        )
        technology_records = _derive_technology_route_records(candidate_result)
    except (
        AttributeError,
        IndexProjectionIntegrityError,
        IsolatedQueryPlanningIntegrityError,
        TypeError,
        ValueError,
    ) as exc:
        if isinstance(exc, IsolatedKnowledgeReadIntegrityError):
            raise
        raise IsolatedKnowledgeReadIntegrityError(
            "internal reference replay authority is invalid"
        ) from exc
    return _InternalReferenceAuthority(
        bundle=validated_bundle,
        publication=validated_publication,
        index_request=exact_index_request,
        institution_catalog=exact_catalog,
        internal_result=internal_result,
        person_records=person_records,
        technology_records=technology_records,
    )


def _replay_relationship_authority(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    index_projection_request: IndexProjectionRequest,
    release_institution_catalog: InstitutionCatalog,
    internal_authority: _InternalReferenceAuthority | None = None,
) -> _RelationshipAuthority:
    try:
        authority = internal_authority or _replay_internal_reference_authority(
            release_bundle=release_bundle,
            published_release=published_release,
            index_projection_request=index_projection_request,
            release_institution_catalog=release_institution_catalog,
        )
        relationship_request_value = authority.bundle.relationship_projection_request
        relationship_result_value = authority.bundle.relationship_projection_result
        if relationship_request_value is None or relationship_result_value is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship publication authority is absent"
            )
        relationship_request = RelationshipProjectionRequest.model_validate(
            relationship_request_value.model_dump(mode="json")
        )
        relationship_result = RelationshipProjectionResult.model_validate(
            relationship_result_value.model_dump(mode="json")
        )
        replayed_relationship_result = (
            create_ephemeral_relationship_projection().project(relationship_request)
        )
        if replayed_relationship_result != relationship_result:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship publication result differs from exact replay"
            )

        internal_request = relationship_request.internal_reference_projection_request
        internal_result = relationship_request.internal_reference_projection_result
        if internal_request is None or internal_result is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship authority lacks its internal projection pair"
            )
        candidate_request = CandidateProjectionRequest(
            release_id=relationship_request.release_id,
            build_run_id=internal_request.build_run_id,
            as_of=internal_request.as_of,
            internal_reference_projection_request=internal_request,
            internal_reference_projection_result=internal_result,
        )
        candidate_result = compose_candidate_projections(candidate_request)
        expected_candidate_request = (
            authority.index_request.candidate_projection_request
        )
        expected_candidate_result = authority.index_request.candidate_projection_result
        if (
            candidate_request != expected_candidate_request
            or candidate_result != expected_candidate_result
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship authority candidate replay differs from index authority"
            )
        if (
            relationship_request.release_id != authority.bundle.release_id
            or relationship_result.release_id != authority.bundle.release_id
            or relationship_result.projection_run_id
            != relationship_request.projection_run_id
            or relationship_result.as_of != relationship_request.as_of
            or relationship_request.as_of != candidate_result.as_of
            or relationship_result.catalog != relationship_request.catalog
            or relationship_result.relationship_registry_version
            != relationship_request.relationship_registry_version
            or relationship_result.relationship_registry_content_sha256
            != relationship_request.relationship_registry_content_sha256
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship authority envelope differs from its release"
            )
    except (
        AttributeError,
        CandidateProjectionIntegrityError,
        IsolatedKnowledgeReadIntegrityError,
        IsolatedQueryPlanningIntegrityError,
        RelationshipProjectionIntegrityError,
        TypeError,
        ValueError,
    ) as exc:
        if isinstance(exc, IsolatedKnowledgeReadIntegrityError):
            raise
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship replay authority is invalid"
        ) from exc
    return _RelationshipAuthority(
        internal_authority=authority,
        relationship_request=relationship_request,
        relationship_result=relationship_result,
        candidate_result=candidate_result,
        relationship_request_content_sha256=_canonical_sha256(
            relationship_request.model_dump(mode="json")
        ),
    )


def _expected_person_query(
    query: InternalReferenceQuery,
    authority: _InternalReferenceAuthority,
) -> InternalReferenceQuery:
    specs = tuple((fact.field, fact.value) for fact in query.typed_filters)
    if (
        not specs
        or len(specs) != len(set(specs))
        or any(field not in _PERSON_FACT_ORDER for field, _ in specs)
        or specs
        != tuple(
            sorted(
                specs,
                key=lambda item: (
                    _PERSON_FACT_ORDER[item[0]],
                    item[0],
                    item[1],
                ),
            )
        )
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "Person internal reference filters are invalid"
        )

    eligible: list[PersonReferenceRecord] = []
    nonmatching: list[ReferenceTrace] = []
    unresolved: list[ReferenceTrace] = []
    for record in authority.person_records:
        if record.release_id != authority.bundle.release_id:
            raise IsolatedKnowledgeReadIntegrityError(
                "Person reference record uses another release"
            )
        facts = {(fact.field, fact.value): fact for fact in record.typed_facts}
        if record.resolution_state != "resolved" or record.canonical_person_id is None:
            unresolved.append(
                ReferenceTrace(
                    reference_id=record.reference_id,
                    resolution_state=record.resolution_state,
                    evidence_ids=record.public_domain_evidence_ids,
                    eligible_for_identity_filter=False,
                    eligible_for_traversal=False,
                )
            )
            continue
        failed = tuple(field for field, value in specs if (field, value) not in facts)
        if failed:
            nonmatching.append(
                ReferenceTrace(
                    reference_id=record.reference_id,
                    resolution_state=record.resolution_state,
                    failed_filter_fields=failed,
                    evidence_ids=record.public_domain_evidence_ids,
                )
            )
        else:
            eligible.append(record)
    source = eligible[0] if eligible else None
    source_facts = (
        {(fact.field, fact.value): fact for fact in source.typed_facts}
        if source is not None
        else {}
    )
    filters = tuple(
        InternalReferenceFact(
            field=field,
            value=value,
            evidence_ids=(
                source_facts[(field, value)].evidence_ids
                if (field, value) in source_facts
                else ()
            ),
        )
        for field, value in specs
    )
    return InternalReferenceQuery(
        reference_type="person",
        release_id=authority.bundle.release_id,
        typed_filters=filters,
        eligible_reference_ids=tuple(record.reference_id for record in eligible),
        excluded_reference_ids=tuple(
            trace.reference_id for trace in (*nonmatching, *unresolved)
        ),
        originating_public_evidence_ids=(
            source.public_domain_evidence_ids if source is not None else ()
        ),
        nonmatching_reference_traces=tuple(nonmatching),
        unresolved_reference_traces=tuple(unresolved),
        reference_content_sha256s=tuple(
            (record.reference_id, record.content_sha256)
            for record in authority.person_records
        ),
        public_population=False,
    )


def _expected_technology_query(
    query: InternalReferenceQuery,
    authority: _InternalReferenceAuthority,
) -> InternalReferenceQuery:
    route_ids = query.canonical_route_ids
    if not route_ids or route_ids != tuple(dict.fromkeys(route_ids)):
        raise IsolatedKnowledgeReadIntegrityError(
            "Technology route IDs must be non-empty and unique"
        )
    records = {
        record.canonical_route_id: record for record in authority.technology_records
    }
    selected: list[TechnologyRouteRecord] = []
    for route_id in route_ids:
        record = records.get(route_id)
        if record is None or record.release_id != authority.bundle.release_id:
            raise IsolatedKnowledgeReadIntegrityError(
                "Technology route query names an unknown release record"
            )
        selected.append(record)
    if tuple(route_id for _, route_id in query.resolved_aliases) != route_ids:
        raise IsolatedKnowledgeReadIntegrityError(
            "Technology route alias mapping differs from selected routes"
        )
    for (raw_alias, route_id), record in zip(
        query.resolved_aliases,
        selected,
        strict=True,
    ):
        if route_id != record.canonical_route_id or raw_alias not in (
            record.canonical_name,
            *record.aliases,
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Technology route alias is not release-resolved"
            )
    candidate_result = authority.index_request.candidate_projection_result
    projections = {
        projection.canonical_technology_identity_id: projection
        for projection in candidate_result.technology_route_projections
    }
    if query.as_of != candidate_result.as_of or any(
        projections[route_id].as_of != query.as_of for route_id in route_ids
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "Technology route as_of differs from release authority"
        )
    if query.enumeration_policy is None:
        if query.scope is not None:
            raise IsolatedKnowledgeReadIntegrityError(
                "Technology route scope requires an enumeration policy"
            )
    elif (
        query.scope != query.enumeration_policy.scope
        or query.as_of != query.enumeration_policy.as_of
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "Technology route scope/as_of differs from enumeration identity"
        )
    return InternalReferenceQuery(
        reference_type="technology_route",
        release_id=authority.bundle.release_id,
        canonical_route_ids=route_ids,
        resolved_aliases=query.resolved_aliases,
        relationship_states=(
            "discussion_or_mention",
            "claimed_adoption",
            "demonstrated_use",
        ),
        scope=query.scope,
        as_of=query.as_of,
        definition_evidence_ids=tuple(
            evidence_id
            for record in selected
            for evidence_id in record.definition_evidence_ids
        ),
        route_content_sha256s=tuple(
            (record.reference_id, record.content_sha256) for record in selected
        ),
        definition_evidence_required=True,
        relationship_evidence_required=True,
        allowed_state_promotions=(),
        state_semantics=(
            ("discussion_or_mention", "non_adoption"),
            ("claimed_adoption", "claimed_only"),
            ("demonstrated_use", "demonstrated_only"),
        ),
        enumeration_policy=query.enumeration_policy,
        public_population=False,
    )


def _validate_internal_reference_request(
    request: LaneRequest,
    authority: _InternalReferenceAuthority,
) -> LaneRequest:
    validated = _validated_lane_request(
        request,
        lane="internal_reference",
        bundle=authority.bundle,
    )
    queries = validated.internal_reference_queries
    reference_types = tuple(query.reference_type for query in queries)
    if (
        not queries
        or len(reference_types) != len(set(reference_types))
        or any(
            reference_type not in {"person", "technology_route"}
            for reference_type in reference_types
        )
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "internal reference request has empty, duplicate, or unsupported queries"
        )
    for query in queries:
        expected = (
            _expected_person_query(query, authority)
            if query.reference_type == "person"
            else _expected_technology_query(query, authority)
        )
        if query != expected:
            raise IsolatedKnowledgeReadIntegrityError(
                "internal reference query differs from replayed authority"
            )
    return validated


def _validate_relationship_request(
    request: LaneRequest,
    authority: _RelationshipAuthority,
) -> LaneRequest:
    bundle = authority.internal_authority.bundle
    validated = _validated_lane_request(
        request,
        lane="relationship",
        bundle=bundle,
    )
    if validated.internal_reference_queries:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship request cannot execute the internal-reference lane"
        )
    paths = validated.relationship_paths
    if len(paths) != 1:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship request requires exactly one supported path"
        )
    path = paths[0]
    path_key = (
        path.relationship_type_id,
        path.direction,
        path.source_type,
        path.target_type,
    )
    if path_key in {
        _PROFESSOR_TO_COMPANY_QUERY_PATH,
        _COMPANY_TO_PROFESSOR_QUERY_PATH,
    }:
        if validated.relationship_reference_queries:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request cannot use an internal reference query"
            )
        enumeration = validated.relationship_enumeration_policy
        if (
            enumeration is None
            or enumeration.as_of.tzinfo is None
            or enumeration.as_of.utcoffset() is None
            or enumeration.mode != "representative"
            or not enumeration.scope
            or enumeration.finite_universe_id is not None
            or enumeration.eligible_member_ids
            or enumeration.required_member_ids
            or enumeration.exhaustive
            or enumeration.continuation_state != "available"
            or enumeration.finite_universe_source is not None
            or enumeration.finite_universe_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship enumeration policy is invalid"
            )
        if enumeration.as_of < authority.relationship_result.as_of:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship query as_of is earlier than the authoritative snapshot"
            )
        if validated.domains != (path.target_type,):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship traversal returns only its target domain"
            )
        displayed_ids = validated.structured_constraints.displayed_entity_ids
        if len(displayed_ids) > 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request accepts at most one displayed entity"
            )
        protected_sets = tuple(
            slot.entity_ids
            for slot in validated.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        if len(protected_sets) > 1 or (
            protected_sets and protected_sets[0] != displayed_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship protected displayed set differs"
            )
        return validated
    if path_key == _COMPANY_TO_PATENT_QUERY_PATH:
        if validated.relationship_reference_queries:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request cannot use an internal reference query"
            )
        enumeration = validated.relationship_enumeration_policy
        if (
            enumeration is None
            or enumeration.as_of.tzinfo is None
            or enumeration.as_of.utcoffset() is None
            or enumeration.mode != "representative"
            or not enumeration.scope
            or enumeration.finite_universe_id is not None
            or enumeration.eligible_member_ids
            or enumeration.required_member_ids
            or enumeration.exhaustive
            or enumeration.continuation_state != "available"
            or enumeration.finite_universe_source is not None
            or enumeration.finite_universe_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship enumeration policy is invalid"
            )
        if enumeration.as_of < authority.relationship_result.as_of:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship query as_of is earlier than the authoritative snapshot"
            )
        if validated.domains != ("patent",):
            raise IsolatedKnowledgeReadIntegrityError(
                "Company-to-Patent traversal returns only the Patent domain"
            )
        displayed_ids = validated.structured_constraints.displayed_entity_ids
        if len(displayed_ids) > 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request accepts at most one displayed Company"
            )
        protected_sets = tuple(
            slot.entity_ids
            for slot in validated.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        if len(protected_sets) > 1 or (
            protected_sets and protected_sets[0] != displayed_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship protected displayed set differs"
            )
        return validated
    if path_key == _PATENT_TO_COMPANY_QUERY_PATH:
        if validated.relationship_reference_queries:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request cannot use an internal reference query"
            )
        enumeration = validated.relationship_enumeration_policy
        if (
            enumeration is None
            or enumeration.as_of.tzinfo is None
            or enumeration.as_of.utcoffset() is None
            or enumeration.mode != "representative"
            or not enumeration.scope
            or enumeration.finite_universe_id is not None
            or enumeration.eligible_member_ids
            or enumeration.required_member_ids
            or enumeration.exhaustive
            or enumeration.continuation_state != "available"
            or enumeration.finite_universe_source is not None
            or enumeration.finite_universe_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship enumeration policy is invalid"
            )
        if enumeration.as_of < authority.relationship_result.as_of:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship query as_of is earlier than the authoritative snapshot"
            )
        if validated.domains != ("company",):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent-to-Company traversal returns only the Company domain"
            )
        displayed_ids = validated.structured_constraints.displayed_entity_ids
        if len(displayed_ids) > 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request accepts at most one displayed Patent"
            )
        protected_sets = tuple(
            slot.entity_ids
            for slot in validated.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        if len(protected_sets) > 1 or (
            protected_sets and protected_sets[0] != displayed_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship protected displayed set differs"
            )
        return validated
    if path_key == _PROFESSOR_TO_PAPER_QUERY_PATH:
        if validated.relationship_reference_queries:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request cannot use an internal reference query"
            )
        enumeration = validated.relationship_enumeration_policy
        if (
            enumeration is None
            or enumeration.as_of.tzinfo is None
            or enumeration.as_of.utcoffset() is None
            or enumeration.mode != "representative"
            or not enumeration.scope
            or enumeration.finite_universe_id is not None
            or enumeration.eligible_member_ids
            or enumeration.required_member_ids
            or enumeration.exhaustive
            or enumeration.continuation_state != "available"
            or enumeration.finite_universe_source is not None
            or enumeration.finite_universe_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship enumeration policy is invalid"
            )
        if enumeration.as_of < authority.relationship_result.as_of:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship query as_of is earlier than the authoritative snapshot"
            )
        if validated.domains != ("paper",):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-to-Paper traversal returns only the Paper domain"
            )
        displayed_ids = validated.structured_constraints.displayed_entity_ids
        if len(displayed_ids) > 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request accepts at most one displayed Professor"
            )
        protected_sets = tuple(
            slot.entity_ids
            for slot in validated.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        if len(protected_sets) > 1 or (
            protected_sets and protected_sets[0] != displayed_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship protected displayed set differs"
            )
        return validated
    if path_key == _PAPER_TO_PROFESSOR_QUERY_PATH:
        if validated.relationship_reference_queries:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request cannot use an internal reference query"
            )
        enumeration = validated.relationship_enumeration_policy
        if (
            enumeration is None
            or enumeration.as_of.tzinfo is None
            or enumeration.as_of.utcoffset() is None
            or enumeration.mode != "representative"
            or not enumeration.scope
            or enumeration.finite_universe_id is not None
            or enumeration.eligible_member_ids
            or enumeration.required_member_ids
            or enumeration.exhaustive
            or enumeration.continuation_state != "available"
            or enumeration.finite_universe_source is not None
            or enumeration.finite_universe_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship enumeration policy is invalid"
            )
        if enumeration.as_of < authority.relationship_result.as_of:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship query as_of is earlier than the authoritative snapshot"
            )
        if validated.domains != ("professor",):
            raise IsolatedKnowledgeReadIntegrityError(
                "Paper-to-Professor traversal returns only the Professor domain"
            )
        displayed_ids = validated.structured_constraints.displayed_entity_ids
        if len(displayed_ids) > 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship request accepts at most one displayed Paper"
            )
        protected_sets = tuple(
            slot.entity_ids
            for slot in validated.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        if len(protected_sets) > 1 or (
            protected_sets and protected_sets[0] != displayed_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship protected displayed set differs"
            )
        return validated
    if path_key != (
        "technology_company_relationship",
        "technology_to_company",
        "technology_route",
        "company",
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship request path is unsupported"
        )
    queries = validated.relationship_reference_queries
    if len(queries) != 1 or queries[0].reference_type != "technology_route":
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship request requires exactly one Technology route query"
        )
    query = queries[0]
    if query.release_id != bundle.release_id or query.public_population:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship query differs from its internal auxiliary release"
        )
    if len(query.canonical_route_ids) != 1:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship query requires exactly one canonical Technology route"
        )
    route_id = query.canonical_route_ids[0]
    records = {
        record.canonical_route_id: record
        for record in authority.internal_authority.technology_records
    }
    record = records.get(route_id)
    if record is None or record.release_id != bundle.release_id:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship query names an unknown Technology route"
        )
    enumeration = query.enumeration_policy
    if (
        query.scope is None
        or not query.scope
        or query.as_of is None
        or query.as_of.tzinfo is None
        or query.as_of.utcoffset() is None
        or enumeration is None
        or enumeration.scope != query.scope
        or enumeration.as_of != query.as_of
        or enumeration.as_of.tzinfo is None
        or enumeration.as_of.utcoffset() is None
        or enumeration.mode != "representative"
        or enumeration.finite_universe_id is not None
        or enumeration.eligible_member_ids
        or enumeration.required_member_ids
        or enumeration.exhaustive
        or enumeration.continuation_state != "available"
        or enumeration.finite_universe_source is not None
        or enumeration.finite_universe_ids
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship query scope/as_of/enumeration identity differs"
        )
    if query.as_of < authority.relationship_result.as_of:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship query as_of is earlier than the authoritative snapshot"
        )
    expected_query = InternalReferenceQuery(
        reference_type="technology_route",
        release_id=bundle.release_id,
        canonical_route_ids=(route_id,),
        resolved_aliases=query.resolved_aliases,
        relationship_states=(
            "discussion_or_mention",
            "claimed_adoption",
            "demonstrated_use",
        ),
        scope=query.scope,
        as_of=query.as_of,
        definition_evidence_ids=record.definition_evidence_ids,
        route_content_sha256s=((record.reference_id, record.content_sha256),),
        definition_evidence_required=True,
        relationship_evidence_required=True,
        allowed_state_promotions=(),
        state_semantics=(
            ("discussion_or_mention", "non_adoption"),
            ("claimed_adoption", "claimed_only"),
            ("demonstrated_use", "demonstrated_only"),
        ),
        enumeration_policy=enumeration,
        public_population=False,
    )
    if query != expected_query:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship Technology query differs from replayed authority"
        )
    if len(query.resolved_aliases) != 1:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship Technology route requires one resolved alias"
        )
    raw_alias, alias_route_id = query.resolved_aliases[0]
    if alias_route_id != route_id or raw_alias not in (
        record.canonical_name,
        *record.aliases,
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship Technology alias differs from its accepted route"
        )
    return validated


def _internal_documents_by_key(
    *,
    documents: tuple[LookupProjectionDocument, ...],
    authority: _InternalReferenceAuthority,
) -> dict[tuple[str, str], LookupProjectionDocument]:
    if documents != authority.bundle.index_result.lookup_documents:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical internal lookup documents differ from the release bundle"
        )
    values: dict[tuple[str, str], LookupProjectionDocument] = {}
    for document in documents:
        if document.projection_scope.value != "internal_auxiliary":
            continue
        if document.reference_type not in {"person", "technology_route"}:
            continue
        try:
            exact_document = LookupProjectionDocument.model_validate(
                document.model_dump(mode="json")
            )
        except ValueError as exc:
            raise IsolatedKnowledgeReadIntegrityError(
                "internal lookup document failed exact validation"
            ) from exc
        reference_type = exact_document.reference_type
        if reference_type not in {"person", "technology_route"}:
            raise IsolatedKnowledgeReadIntegrityError(
                "internal lookup document has an unsupported reference type"
            )
        key = (reference_type, exact_document.canonical_object_id)
        if key in values:
            raise IsolatedKnowledgeReadIntegrityError(
                "internal lookup document authority is duplicated"
            )
        values[key] = exact_document
    return values


def _validated_internal_document(
    *,
    reference_type: Literal["person", "technology_route"],
    internal_reference_id: str,
    projection: PersonProjection | TechnologyRouteProjection,
    documents: dict[tuple[str, str], LookupProjectionDocument],
    authority: _InternalReferenceAuthority,
) -> LookupProjectionDocument:
    document = documents.get((reference_type, internal_reference_id))
    if document is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "internal lookup document authority is missing"
        )
    try:
        observed_projection = (
            PersonProjection.model_validate_json(document.lookup_content)
            if reference_type == "person"
            else TechnologyRouteProjection.model_validate_json(document.lookup_content)
        )
    except ValueError as exc:
        raise IsolatedKnowledgeReadIntegrityError(
            "internal lookup document content is not its typed projection"
        ) from exc
    if (
        observed_projection != projection
        or document.release_id != authority.bundle.release_id
        or document.domain is not None
        or document.reference_type != reference_type
        or document.canonical_object_id != internal_reference_id
        or document.source_projection_content_sha256 != projection.content_sha256
        or json.loads(document.lookup_content)
        != json.loads(projection.model_dump_json())
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "internal lookup document differs from replayed projection authority"
        )
    return document


def _public_projection_for_anchor(
    *,
    anchor: PublicDomainEvidenceAnchor | TechnologyEvidenceAnchor,
    authority: _InternalReferenceAuthority,
) -> tuple[PublicProjection, str]:
    matches = tuple(
        projection
        for projection in authority.index_request.candidate_projection_result.public_domain_projections
        if projection.entity_type == anchor.public_domain
        and projection.canonical_identity_id == anchor.root_canonical_identity_id
    )
    if (
        len(matches) != 1
        or matches[0].release_id != authority.bundle.release_id
        or matches[0].content_sha256 != anchor.root_projection_content_sha256
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "public origin anchor differs from replayed public projection"
        )
    display_name, _, _, _ = _projection_terms(matches[0])
    return matches[0], display_name


def _internal_candidate_specs(
    *,
    request: LaneRequest,
    authority: _InternalReferenceAuthority,
    documents: dict[tuple[str, str], LookupProjectionDocument],
) -> tuple[_InternalReferenceCandidateSpec, ...]:
    candidate_result = authority.index_request.candidate_projection_result
    person_projections = {
        projection.canonical_person_identity_id: projection
        for projection in candidate_result.person_projections
    }
    route_projections = {
        projection.canonical_technology_identity_id: projection
        for projection in candidate_result.technology_route_projections
    }
    person_records = {
        record.reference_id: record for record in authority.person_records
    }
    technology_records = {
        record.canonical_route_id: record for record in authority.technology_records
    }
    person_anchors = {
        anchor.anchor_id: anchor
        for anchor in authority.internal_result.public_evidence_anchors
    }
    technology_anchors = {
        anchor.anchor_id: anchor
        for anchor in authority.internal_result.technology_evidence_anchors
    }
    specs: list[_InternalReferenceCandidateSpec] = []

    def append_groups(
        *,
        reference_type: Literal["person", "technology_route"],
        internal_id: str,
        projection: PersonProjection | TechnologyRouteProjection,
        record: PersonReferenceRecord | TechnologyRouteRecord,
        document: LookupProjectionDocument,
        selected_anchors: tuple[
            PublicDomainEvidenceAnchor | TechnologyEvidenceAnchor,
            ...,
        ],
        claim_predicate: str,
        claim_value: str,
        claim_evidence_ids: tuple[str, ...],
        matched_filters: tuple[InternalReferenceFact, ...],
        snippet: str,
    ) -> None:
        grouped: defaultdict[
            tuple[PublicDomain, str],
            list[PublicDomainEvidenceAnchor | TechnologyEvidenceAnchor],
        ] = defaultdict(list)
        for anchor in selected_anchors:
            if anchor.public_domain not in request.domains:
                continue
            grouped[(anchor.public_domain, anchor.root_canonical_identity_id)].append(
                anchor
            )
        if not grouped:
            raise IsolatedKnowledgeReadIntegrityError(
                "internal reference result has no public origin in plan domains"
            )
        for (domain, public_id), grouped_anchors in grouped.items():
            ordered_anchors = tuple(
                sorted(grouped_anchors, key=lambda anchor: anchor.anchor_id)
            )
            public_projection, display_name = _public_projection_for_anchor(
                anchor=ordered_anchors[0],
                authority=authority,
            )
            if any(
                anchor.root_projection_content_sha256
                != public_projection.content_sha256
                for anchor in ordered_anchors
            ):
                raise IsolatedKnowledgeReadIntegrityError(
                    "grouped public origin anchors use different root projections"
                )
            specs.append(
                _InternalReferenceCandidateSpec(
                    reference_type=reference_type,
                    internal_reference_id=internal_id,
                    internal_projection_content_sha256=projection.content_sha256,
                    reference_record_content_sha256=record.content_sha256,
                    document=document,
                    public_domain=domain,
                    public_canonical_id=public_id,
                    public_display_name=display_name,
                    public_root_projection_content_sha256=(
                        public_projection.content_sha256
                    ),
                    anchors=ordered_anchors,
                    claim_predicate=claim_predicate,
                    claim_value=claim_value,
                    claim_evidence_ids=claim_evidence_ids,
                    matched_filter_facts=matched_filters,
                    snippet=snippet,
                )
            )

    for query in request.internal_reference_queries:
        if query.reference_type == "person":
            for internal_id in query.eligible_reference_ids:
                projection = person_projections[internal_id]
                record = person_records[internal_id]
                document = _validated_internal_document(
                    reference_type="person",
                    internal_reference_id=internal_id,
                    projection=projection,
                    documents=documents,
                    authority=authority,
                )
                selected_anchors = tuple(
                    person_anchors[reference.source_anchor_id]
                    for reference in projection.references
                    if reference.source_anchor_id
                    in query.originating_public_evidence_ids
                )
                person_claim_evidence_ids = tuple(
                    sorted(
                        {
                            evidence_id
                            for fact in query.typed_filters
                            for evidence_id in fact.evidence_ids
                        }
                    )
                )
                append_groups(
                    reference_type="person",
                    internal_id=internal_id,
                    projection=projection,
                    record=record,
                    document=document,
                    selected_anchors=selected_anchors,
                    claim_predicate="internal_person_filter_match",
                    claim_value=projection.content_sha256,
                    claim_evidence_ids=person_claim_evidence_ids,
                    matched_filters=query.typed_filters,
                    snippet=projection.display_name,
                )
        else:
            for internal_id in query.canonical_route_ids:
                projection = route_projections[internal_id]
                record = technology_records[internal_id]
                document = _validated_internal_document(
                    reference_type="technology_route",
                    internal_reference_id=internal_id,
                    projection=projection,
                    documents=documents,
                    authority=authority,
                )
                selected_anchors = tuple(
                    technology_anchors[anchor_id]
                    for anchor_id in projection.source_anchor_ids
                )
                definition_lineage = tuple(
                    lineage
                    for lineage in projection.field_lineage
                    if lineage.field_path == "technology.definition"
                )
                if len(definition_lineage) != 1:
                    raise IsolatedKnowledgeReadIntegrityError(
                        "Technology definition lineage is missing or duplicated"
                    )
                append_groups(
                    reference_type="technology_route",
                    internal_id=internal_id,
                    projection=projection,
                    record=record,
                    document=document,
                    selected_anchors=selected_anchors,
                    claim_predicate="definition",
                    claim_value=projection.definition,
                    claim_evidence_ids=(definition_lineage[0].supporting_assertion_ids),
                    matched_filters=(),
                    snippet=projection.definition,
                )
    specs.sort(
        key=lambda spec: (
            spec.reference_type,
            spec.internal_reference_id,
            spec.public_domain,
            spec.public_canonical_id,
        )
    )
    return tuple(specs[: request.max_candidates])


def _candidate_from_internal_spec(
    *,
    request: LaneRequest,
    authority: _InternalReferenceAuthority,
    spec: _InternalReferenceCandidateSpec,
) -> RecallCandidate:
    evidence: list[EvidenceItem] = []
    for anchor in spec.anchors:
        trace = LocalInternalReferenceTrace(
            target_id=authority.bundle.index_target.target_id,
            target_marker_sha256=authority.bundle.index_target.marker_sha256,
            manifest_sha256=authority.bundle.manifest.manifest_sha256,
            index_result_content_sha256=authority.bundle.index_result.content_sha256,
            document_id=spec.document.document_id,
            release_id=authority.bundle.release_id,
            projection_id=spec.document.projection_id,
            reference_type=spec.reference_type,
            internal_reference_id=spec.internal_reference_id,
            internal_projection_content_sha256=(
                spec.internal_projection_content_sha256
            ),
            reference_record_content_sha256=spec.reference_record_content_sha256,
            internal_lookup_content_sha256=spec.document.lookup_content_sha256,
            internal_lookup_source_evidence_ids=spec.document.source_evidence_ids,
            public_origin_domain=spec.public_domain,
            public_origin_canonical_id=spec.public_canonical_id,
            public_origin_anchor_id=anchor.anchor_id,
            public_origin_anchor_content_sha256=anchor.content_sha256,
            public_origin_root_projection_content_sha256=(
                spec.public_root_projection_content_sha256
            ),
            lane_request_content_sha256=request.content_sha256,
            claim_subject_id=spec.internal_reference_id,
            claim_predicate=spec.claim_predicate,
            claim_value=spec.claim_value,
            claim_evidence_ids=spec.claim_evidence_ids,
            matched_filter_facts=spec.matched_filter_facts,
            publication_verification_evidence_ids=tuple(
                sorted(authority.publication.verification_evidence_ids)
            ),
            snippet_sha256=hashlib.sha256(spec.snippet.encode("utf-8")).hexdigest(),
        )
        evidence.append(
            EvidenceItem(
                evidence_id=trace.evidence_id,
                object_id=spec.public_canonical_id,
                domain=spec.public_domain,
                lane="internal_reference",
                source_nature="local",
                source_locator=_local_projection_locator(trace),
                snippet=spec.snippet,
                score=1.0,
                source_authority="canonical_release",
                claim_binding=EvidenceClaimBinding(
                    subject_id=spec.internal_reference_id,
                    predicate=spec.claim_predicate,
                    value=spec.claim_value,
                    status=None,
                ),
                local_projection_trace=trace,
            )
        )
    raw_candidate_ids: set[str] = set()
    for item in evidence:
        item_trace = item.local_projection_trace
        if not isinstance(item_trace, LocalInternalReferenceTrace):
            raise IsolatedKnowledgeReadIntegrityError(
                "internal reference evidence lost its typed trace"
            )
        raw_candidate_ids.add(item_trace.raw_candidate_id)
    if len(raw_candidate_ids) != 1:
        raise IsolatedKnowledgeReadIntegrityError(
            "internal reference anchor group has inconsistent candidate identity"
        )
    return RecallCandidate(
        raw_candidate_id=next(iter(raw_candidate_ids)),
        display_name=spec.public_display_name,
        domain=spec.public_domain,
        identity_kind="canonical",
        canonical_id=spec.public_canonical_id,
        reference_type=spec.reference_type,
        resolution_state="resolved",
        relationship_state=None,
        origin_public_evidence_ids=tuple(anchor.anchor_id for anchor in spec.anchors),
        query_view=request.query_view,
        lane="internal_reference",
        attempt=1,
        release_id=authority.bundle.release_id,
        adapter_version=_INTERNAL_REFERENCE_ADAPTER_VERSION,
        raw_score=1.0,
        quality_flags=(),
        evidence=tuple(evidence),
    )


def _build_internal_reference_result(
    *,
    request: LaneRequest,
    authority: _InternalReferenceAuthority,
    documents: tuple[LookupProjectionDocument, ...],
) -> RetrievalLaneResult:
    validated_request = _validate_internal_reference_request(request, authority)
    if validated_request.max_candidates == 0:
        return RetrievalLaneResult()
    documents_by_key = _internal_documents_by_key(
        documents=documents,
        authority=authority,
    )
    specs = _internal_candidate_specs(
        request=validated_request,
        authority=authority,
        documents=documents_by_key,
    )
    return RetrievalLaneResult(
        candidates=tuple(
            _candidate_from_internal_spec(
                request=validated_request,
                authority=authority,
                spec=spec,
            )
            for spec in specs
        )
    )


def create_isolated_internal_reference_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    index_projection_request: IndexProjectionRequest,
    release_institution_catalog: InstitutionCatalog,
    _lookup_view: _AuditedLookupView | None = None,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    """Execute recorded internal Person/Technology queries on one S7 release."""

    authority = _replay_internal_reference_authority(
        release_bundle=release_bundle,
        published_release=published_release,
        index_projection_request=index_projection_request,
        release_institution_catalog=release_institution_catalog,
    )
    lookup_view = _lookup_view_provider(
        bundle=authority.bundle,
        supplied=_lookup_view,
    )

    def internal_reference_lookup(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = _validate_internal_reference_request(request, authority)
        if validated_request.max_candidates == 0:
            return RetrievalLaneResult()
        lookup_view()
        documents = _read_bound_documents(authority.bundle)
        return _build_internal_reference_result(
            request=validated_request,
            authority=authority,
            documents=documents,
        )

    return internal_reference_lookup


def _validate_release_bound_internal_reference_evidence(
    *,
    plan: RetrievalPlan,
    evidence_set: EvidenceSet,
    authority: _InternalReferenceAuthority,
) -> None:
    request = _lane_request(plan, "internal_reference", plan.web_policy)
    expected = _build_internal_reference_result(
        request=request,
        authority=authority,
        documents=authority.bundle.index_result.lookup_documents,
    )
    expected_candidates = expected.candidates
    expected_items = {
        item.evidence_id: item
        for candidate in expected_candidates
        for item in candidate.evidence
    }
    if len(expected_items) != sum(
        len(candidate.evidence) for candidate in expected_candidates
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "expected internal reference evidence identity is duplicated"
        )

    observed_items: dict[str, EvidenceItem] = {}
    for item in (
        *evidence_set.items,
        *(
            item
            for candidate in evidence_set.fused_candidates
            for item in candidate.evidence
        ),
    ):
        if item.lane != "internal_reference":
            continue
        previous = observed_items.get(item.evidence_id)
        if previous is not None and previous != item:
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound internal reference evidence identity is inconsistent"
            )
        observed_items[item.evidence_id] = item
    if observed_items != expected_items:
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound internal reference evidence differs from replay authority"
        )

    lane_traces = tuple(
        trace for trace in evidence_set.traces if trace.lane == "internal_reference"
    )
    if len(lane_traces) != 1 or lane_traces[0].status != "succeeded":
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound internal reference lane did not succeed"
        )

    expected_raw_ids = {candidate.raw_candidate_id for candidate in expected_candidates}
    candidate_traces = tuple(
        trace
        for trace in evidence_set.candidate_traces
        if trace.lane == "internal_reference"
    )
    if {
        trace.raw_candidate_id for trace in candidate_traces
    } != expected_raw_ids or any(
        trace.disposition != "selected" or trace.selected_result_id is None
        for trace in candidate_traces
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound internal reference candidate disposition differs"
        )
    auxiliary = tuple(
        trace
        for trace in evidence_set.auxiliary_traces
        if trace.raw_candidate_id in expected_raw_ids
    )
    if {trace.raw_candidate_id for trace in auxiliary} != expected_raw_ids or any(
        trace.reference_type not in {"person", "technology_route"}
        or trace.public_population
        or not trace.eligible
        or trace.relationship_state is not None
        for trace in auxiliary
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound internal reference auxiliary trace differs"
        )

    grouped: defaultdict[tuple[str, str], list[RecallCandidate]] = defaultdict(list)
    for candidate in expected_candidates:
        if candidate.canonical_id is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "internal reference candidate lacks its public canonical origin"
            )
        grouped[(candidate.domain, candidate.canonical_id)].append(candidate)
    for (domain, canonical_id), candidates in grouped.items():
        group_raw_ids = tuple(candidate.raw_candidate_id for candidate in candidates)
        group_evidence_ids = tuple(
            item.evidence_id for candidate in candidates for item in candidate.evidence
        )
        fused_matches = tuple(
            candidate
            for candidate in evidence_set.fused_candidates
            if set(group_raw_ids) & set(candidate.raw_candidate_ids)
        )
        if len(fused_matches) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "internal reference candidates do not have one fused public result"
            )
        fused = fused_matches[0]
        observed_group_raw_ids = tuple(
            raw_id for raw_id in fused.raw_candidate_ids if raw_id in expected_raw_ids
        )
        observed_group_evidence_ids = tuple(
            evidence_id
            for evidence_id in fused.evidence_ids
            if evidence_id in expected_items
        )
        if (
            fused.canonical_id != canonical_id
            or fused.domain != domain
            or fused.display_name != candidates[0].display_name
            or observed_group_raw_ids != group_raw_ids
            or observed_group_evidence_ids != group_evidence_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "internal reference fused identity/display differs from public authority"
            )
        handles = tuple(
            handle
            for handle in evidence_set.entity_handles
            if isinstance(handle, CanonicalEntityHandle)
            and handle.canonical_id == canonical_id
            and handle.domain == domain
            and set(group_evidence_ids) <= set(handle.evidence_ids)
        )
        if len(handles) != 1 or handles[0].display_name != candidates[0].display_name:
            raise IsolatedKnowledgeReadIntegrityError(
                "internal reference handle display differs from public authority"
            )
        if any(
            trace.selected_result_id != canonical_id
            for trace in candidate_traces
            if trace.raw_candidate_id in group_raw_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "internal reference candidate selected a different public result"
            )


def _company_to_patent_relationship_candidates(
    *,
    request: LaneRequest,
    authority: _RelationshipAuthority,
) -> tuple[RecallCandidate, ...]:
    displayed_ids = request.structured_constraints.displayed_entity_ids
    if not displayed_ids:
        return ()
    displayed_company_id = displayed_ids[0]
    public_projections = {
        (projection.entity_type, projection.canonical_identity_id): projection
        for projection in authority.candidate_result.public_domain_projections
    }
    if len(public_projections) != len(
        authority.candidate_result.public_domain_projections
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "public relationship endpoint projection authority is duplicated"
        )
    company = public_projections.get(("company", displayed_company_id))
    if not isinstance(company, CompanyProjection):
        return ()
    protected_slots = tuple(
        slot for slot in request.protected_slots if slot.kind == "displayed_entity_set"
    )
    if len(protected_slots) != 1 or protected_slots[0].entity_ids != displayed_ids:
        raise IsolatedKnowledgeReadIntegrityError(
            "returnable public relationship requires one protected Company source"
        )
    protected_slot = protected_slots[0]
    enumeration = request.relationship_enumeration_policy
    if enumeration is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "returnable public relationship requires enumeration authority"
        )

    relationship_request = authority.relationship_request
    relationship_result = authority.relationship_result
    bundle = authority.internal_authority.bundle
    publication = authority.internal_authority.publication
    internal_request = relationship_request.internal_reference_projection_request
    if internal_request is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "public relationship authority lost its public assertion request"
        )
    public_request = internal_request.public_domain_projection_request
    source_assertions = {
        assertion.assertion_id: assertion
        for assertion in public_request.source_assertions
    }
    retained_references = {
        retained.reference_id: retained
        for retained in relationship_request.retained_assertions
    }
    projection_candidates = {
        candidate.candidate_id: candidate
        for candidate in relationship_request.candidates
    }
    typed_assertions = {
        assertion.assertion_id: assertion
        for assertion in relationship_request.typed_relationship_assertions
    }
    decision_inputs = {
        decision.decision_input_id: decision
        for decision in relationship_request.decision_inputs
    }
    typed_decisions = {
        decision.decision_id: decision
        for decision in relationship_result.typed_relationship_decisions
    }
    relationship_types = {
        (item.relationship_type_id, item.version): item
        for item in relationship_result.relationship_types
    }
    outcomes_by_relationship: defaultdict[str, list[RelationshipCandidateOutcome]] = (
        defaultdict(list)
    )
    for outcome in relationship_result.candidate_outcomes:
        if outcome.projected_relationship_id is not None:
            outcomes_by_relationship[outcome.projected_relationship_id].append(outcome)
    authorities = (
        (source_assertions, public_request.source_assertions, "source assertion"),
        (retained_references, relationship_request.retained_assertions, "retained"),
        (projection_candidates, relationship_request.candidates, "candidate"),
        (
            typed_assertions,
            relationship_request.typed_relationship_assertions,
            "assertion",
        ),
        (decision_inputs, relationship_request.decision_inputs, "decision input"),
        (typed_decisions, relationship_result.typed_relationship_decisions, "decision"),
        (relationship_types, relationship_result.relationship_types, "type"),
    )
    if any(len(index) != len(values) for index, values, _ in authorities):
        duplicated = next(
            name for index, values, name in authorities if len(index) != len(values)
        )
        raise IsolatedKnowledgeReadIntegrityError(
            f"public relationship {duplicated} authority is duplicated"
        )
    path_results = {
        result.subject_identity_id: result
        for result in authority.internal_authority.index_request.public_path_eligibility_results
    }
    if len(path_results) != len(
        authority.internal_authority.index_request.public_path_eligibility_results
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "public relationship path eligibility authority is duplicated"
        )

    def returnable_eligibility(
        identity_id: str,
        *,
        domain: str,
        direction: str,
        relationship_decision_id: str,
    ) -> tuple[Any, Any] | None:
        result = path_results.get(identity_id)
        if (
            result is None
            or result.release_id != bundle.release_id
            or result.projection_id != f"typed:{domain}:{identity_id}"
            or result.resolved_projection_id != f"typed:{domain}:{identity_id}"
            or result.traversal_directions != (direction,)
            or result.relationship_decision_ids != (relationship_decision_id,)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship endpoint path result differs"
            )
        matches = tuple(
            decision
            for decision in result.decisions
            if decision.path == "verified_relationship_traversal"
        )
        if len(matches) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship endpoint eligibility is missing or ambiguous"
            )
        decision = matches[0]
        if decision.outcome is PolicyOutcome.excluded:
            return None
        if decision.outcome not in {PolicyOutcome.admitted, PolicyOutcome.limited}:
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship endpoint eligibility is not returnable"
            )
        if decision.hard_exclusion_codes:
            raise IsolatedKnowledgeReadIntegrityError(
                "returnable public relationship endpoint has a hard exclusion"
            )
        return result, decision

    relationship_enumeration_policy_sha256 = _canonical_sha256(
        enumeration.model_dump(mode="json")
    )
    protected_slot_content_sha256 = _canonical_sha256(
        protected_slot.model_dump(mode="json")
    )
    candidates: list[RecallCandidate] = []
    for current in relationship_result.current_relationships:
        if not isinstance(current, CurrentRelationshipProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "public relationship current projection has an invalid type"
            )
        if (
            current.relationship_type_id,
            current.relationship_type_version,
        ) != _PATENT_APPLICANT_TYPE:
            continue
        expected_company_ref = f"canonical:company:{displayed_company_id}"
        if current.target_endpoint.stable_reference != expected_company_ref:
            continue
        relationship_type = relationship_types.get(_PATENT_APPLICANT_TYPE)
        if (
            relationship_type is None
            or "patent" not in relationship_type.source_entity_types
            or "company" not in relationship_type.target_entity_types
            or "company_to_patent" not in relationship_type.eligible_paths
            or "patent_to_company" not in relationship_type.eligible_paths
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant relationship type/path is not installed"
            )
        outcome_matches = outcomes_by_relationship.get(
            current.canonical_relationship_id,
            [],
        )
        if len(outcome_matches) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant candidate outcome is missing or ambiguous"
            )
        outcome = outcome_matches[0]
        if not isinstance(outcome, RelationshipCandidateOutcome):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant candidate outcome has an invalid type"
            )
        projection_candidate = projection_candidates.get(outcome.candidate_id)
        decision = typed_decisions.get(current.decision_id)
        if (
            not isinstance(projection_candidate, RelationshipProjectionCandidate)
            or not isinstance(decision, TypedRelationshipDecision)
            or projection_candidate.assertion_input_id is None
            or projection_candidate.decision_input_id is None
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant input/decision chain is absent"
            )
        typed_assertion = typed_assertions.get(projection_candidate.assertion_input_id)
        decision_input = decision_inputs.get(projection_candidate.decision_input_id)
        if not isinstance(typed_assertion, TypedRelationshipAssertionInput):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant typed assertion is absent"
            )
        if (
            decision_input is None
            or not outcome.admitted
            or outcome.reason_codes
            or outcome.decision_state != "accepted"
            or outcome.current_projection_state != "current"
            or outcome.current_projection_reason_codes
            or outcome.retained_assertion_id != typed_assertion.assertion_id
            or outcome.decision_id != decision.decision_id
            or outcome.projected_relationship_id != current.canonical_relationship_id
            or outcome.selected_evidence_refs != current.selected_evidence_refs
            or outcome.source_reference_kind != "canonical_identity"
            or outcome.target_reference_kind != "canonical_identity"
            or outcome.source_canonical_identity_id
            != current.source_endpoint.canonical_identity_id
            or outcome.target_canonical_identity_id != displayed_company_id
            or outcome.source_parent_canonical_identity_ref is not None
            or outcome.target_parent_canonical_identity_ref is not None
            or decision_input.decision_id != decision.decision_id
            or decision_input.canonical_relationship_id
            != current.canonical_relationship_id
            or decision.state != "accepted"
            or decision.canonical_relationship_id != current.canonical_relationship_id
            or decision.source_endpoint != current.source_endpoint
            or decision.target_endpoint != current.target_endpoint
            or decision.role_bindings != current.role_bindings
            or decision.selected_evidence_refs != current.selected_evidence_refs
            or decision.valid_from != current.valid_from
            or decision.valid_to != current.valid_to
            or decision.release_id != current.release_id
            or current.release_id != bundle.release_id
            or current.projected_at != relationship_result.as_of
            or typed_assertion.assertion_id not in decision.selected_assertion_ids
            or projection_candidate.relationship_type_id != current.relationship_type_id
            or projection_candidate.relationship_type_version
            != current.relationship_type_version
            or projection_candidate.source_endpoint != current.source_endpoint
            or projection_candidate.target_endpoint != current.target_endpoint
            or projection_candidate.role_bindings != current.role_bindings
            or typed_assertion.relationship_type_id != current.relationship_type_id
            or typed_assertion.relationship_type_version
            != current.relationship_type_version
            or typed_assertion.source_endpoint != current.source_endpoint
            or typed_assertion.target_endpoint != current.target_endpoint
            or typed_assertion.attributes.get("candidate_id")
            != projection_candidate.candidate_id
            or typed_assertion.attributes.get("role_bindings")
            != projection_candidate.role_bindings
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant candidate/assertion/outcome/decision differs"
            )
        retained_assertion_id = outcome.retained_assertion_id
        outcome_decision_id = outcome.decision_id
        projected_relationship_id = outcome.projected_relationship_id
        if (
            retained_assertion_id is None
            or outcome_decision_id is None
            or projected_relationship_id is None
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant candidate outcome lineage is absent"
            )
        if len(current.selected_evidence_refs) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant requires one retained reference"
            )
        retained = retained_references.get(current.selected_evidence_refs[0])
        if retained is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant retained reference is absent"
            )
        source_assertion = source_assertions.get(retained.assertion_id)
        if not isinstance(source_assertion, SourceAssertion):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant public assertion is absent"
            )
        patent_id = current.source_endpoint.canonical_identity_id
        if patent_id is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant source is not a canonical Patent"
            )
        patent = public_projections.get(("patent", patent_id))
        if not isinstance(patent, PatentProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant public Patent projection is absent"
            )
        applicant_matches = tuple(
            applicant
            for applicant in patent.applicants
            if applicant.canonical_company_id == displayed_company_id
            and source_assertion.assertion_id in applicant.supporting_assertion_ids
        )
        if len(applicant_matches) != 1 or not isinstance(
            applicant_matches[0], PatentApplicant
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant subobject is missing or ambiguous"
            )
        applicant = applicant_matches[0]
        expected_patent_ref = f"canonical:patent:{patent_id}"
        evidence_bindings = projection_candidate.evidence_bindings
        if (
            source_assertion.source_record_id != retained.source_record_ref
            or typed_assertion.source_record_ref != retained.source_record_ref
            or source_assertion.subject_entity_type != "patent"
            or source_assertion.field_path != "applicants"
            or applicant.parent_canonical_identity_id != patent_id
            or applicant.canonical_company_id != displayed_company_id
            or patent.release_id != bundle.release_id
            or company.release_id != bundle.release_id
            or current.source_endpoint.endpoint_type != "patent"
            or current.source_endpoint.stable_reference != expected_patent_ref
            or current.target_endpoint.endpoint_type != "company"
            or current.target_endpoint.canonical_identity_id != displayed_company_id
            or current.role_bindings != {_PATENT_APPLICANT_ROLE: expected_company_ref}
            or len(evidence_bindings) != 1
            or evidence_bindings != typed_assertion.evidence_bindings
            or evidence_bindings[0].evidence_kind != "patent_applicant_assertion"
            or evidence_bindings[0].assertion_refs != (retained.reference_id,)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent applicant endpoint/evidence identity is cross-wired"
            )
        company_eligibility = returnable_eligibility(
            displayed_company_id,
            domain="company",
            direction="company_to_patent",
            relationship_decision_id=current.decision_id,
        )
        patent_eligibility = returnable_eligibility(
            patent_id,
            domain="patent",
            direction="patent_to_company",
            relationship_decision_id=current.decision_id,
        )
        if company_eligibility is None or patent_eligibility is None:
            continue
        company_path_result, company_path_decision = company_eligibility
        patent_path_result, patent_path_decision = patent_eligibility
        limitations = tuple(
            sorted(
                set(company_path_decision.limitations)
                | set(patent_path_decision.limitations)
            )
        )
        quality_flags = limitations
        if enumeration.as_of > relationship_result.as_of:
            canonical_snapshot = (
                relationship_result.as_of.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            quality_flags = tuple(
                sorted(
                    {
                        *quality_flags,
                        f"relationship_snapshot_as_of:{canonical_snapshot}",
                    }
                )
            )
        origin_evidence_ids = tuple(sorted(applicant.supporting_assertion_ids))
        snippet = json.dumps(
            applicant.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        trace = LocalCanonicalRelationshipTrace(
            target_id=bundle.index_target.target_id,
            target_marker_sha256=bundle.index_target.marker_sha256,
            manifest_sha256=bundle.manifest.manifest_sha256,
            index_result_content_sha256=bundle.index_result.content_sha256,
            publication_verification_evidence_ids=tuple(
                sorted(publication.verification_evidence_ids)
            ),
            release_id=bundle.release_id,
            lane_request_content_sha256=request.content_sha256,
            relationship_enumeration_policy_sha256=relationship_enumeration_policy_sha256,
            displayed_entity_ids=displayed_ids,
            displayed_company_id=displayed_company_id,
            protected_slot_id=protected_slot.slot_id,
            protected_slot_content_sha256=protected_slot_content_sha256,
            query_as_of=enumeration.as_of,
            relationship_request_sha256=authority.relationship_request_content_sha256,
            relationship_result_sha256=relationship_result.content_sha256,
            relationship_projection_run_id=relationship_result.projection_run_id,
            relationship_projection_schema_version=(
                relationship_result.projection_schema_version
            ),
            relationship_registry_version=(
                relationship_result.relationship_registry_version
            ),
            relationship_registry_content_sha256=(
                relationship_result.relationship_registry_content_sha256
            ),
            relationship_snapshot_as_of=relationship_result.as_of,
            canonical_relationship_id=current.canonical_relationship_id,
            current_relationship_content_sha256=_canonical_sha256(
                current.model_dump(mode="json")
            ),
            relationship_decision_input_id=decision_input.decision_input_id,
            relationship_decision_id=current.decision_id,
            relationship_source_endpoint=current.source_endpoint.stable_reference,
            relationship_target_endpoint=current.target_endpoint.stable_reference,
            relationship_role_bindings=tuple(sorted(current.role_bindings.items())),
            selected_evidence_refs=tuple(sorted(current.selected_evidence_refs)),
            relationship_valid_from=(
                current.valid_from.model_dump(mode="json")
                if current.valid_from is not None
                else None
            ),
            relationship_valid_to=(
                current.valid_to.model_dump(mode="json")
                if current.valid_to is not None
                else None
            ),
            projection_candidate_id=projection_candidate.candidate_id,
            projection_candidate_content_sha256=_canonical_sha256(
                projection_candidate.model_dump(mode="json")
            ),
            projection_candidate_observed_at=projection_candidate.observed_at,
            projection_candidate_source_event_time=(
                projection_candidate.source_event_time
            ),
            projection_candidate_assertion_input_id=(
                projection_candidate.assertion_input_id
            ),
            projection_candidate_decision_input_id=(
                projection_candidate.decision_input_id
            ),
            typed_assertion_id=typed_assertion.assertion_id,
            typed_assertion_content_sha256=_canonical_sha256(
                typed_assertion.model_dump(mode="json")
            ),
            typed_assertion_observed_at=typed_assertion.observed_at,
            typed_assertion_source_event_time=typed_assertion.source_event_time,
            typed_assertion_source_record_ref=typed_assertion.source_record_ref,
            candidate_outcome_candidate_id=outcome.candidate_id,
            candidate_outcome_content_sha256=_canonical_sha256(
                outcome.model_dump(mode="json")
            ),
            candidate_outcome_retained_assertion_id=retained_assertion_id,
            candidate_outcome_decision_id=outcome_decision_id,
            candidate_outcome_projected_relationship_id=projected_relationship_id,
            typed_decision_id=decision.decision_id,
            typed_decision_content_sha256=_canonical_sha256(
                decision.model_dump(mode="json")
            ),
            typed_decision_selected_assertion_ids=tuple(
                sorted(decision.selected_assertion_ids)
            ),
            typed_decision_selected_evidence_refs=tuple(
                sorted(decision.selected_evidence_refs)
            ),
            current_selected_evidence_refs=tuple(
                sorted(current.selected_evidence_refs)
            ),
            retained_reference_id=retained.reference_id,
            retained_reference_content_sha256=_canonical_sha256(
                retained.model_dump(mode="json")
            ),
            retained_assertion_id=retained.assertion_id,
            retained_source_record_id=retained.source_record_ref,
            public_assertion_id=source_assertion.assertion_id,
            public_assertion_content_sha256=_canonical_sha256(
                source_assertion.model_dump(mode="json")
            ),
            public_assertion_observed_at=source_assertion.observed_at,
            public_assertion_source_event_time=source_assertion.source_event_time,
            source_record_id=source_assertion.source_record_id,
            company_id=displayed_company_id,
            company_stable_reference=expected_company_ref,
            company_projection_content_sha256=company.content_sha256,
            company_display_name=company.name,
            patent_id=patent_id,
            patent_stable_reference=expected_patent_ref,
            patent_projection_content_sha256=patent.content_sha256,
            patent_display_name=patent.title,
            applicant_subobject_id=applicant.subobject_id,
            applicant_subobject_projection_content_sha256=(
                applicant.projection_content_sha256
            ),
            applicant_parent_patent_id=applicant.parent_canonical_identity_id,
            applicant_canonical_company_id=displayed_company_id,
            applicant_supporting_assertion_ids=origin_evidence_ids,
            applicant_source_record_id=source_assertion.source_record_id,
            company_path_result_content_sha256=company_path_result.content_sha256,
            company_traversal_directions=company_path_result.traversal_directions,
            company_relationship_decision_ids=(
                company_path_result.relationship_decision_ids
            ),
            company_eligibility_decision_id=company_path_decision.decision_id,
            company_eligibility_policy_id=company_path_decision.policy.policy_id,
            company_eligibility_policy_version=(
                company_path_decision.policy.policy_version
            ),
            company_eligibility_policy_content_sha256=(
                company_path_decision.policy.content_sha256
            ),
            company_eligibility_outcome=company_path_decision.outcome.value,
            company_eligibility_limitations=tuple(
                sorted(company_path_decision.limitations)
            ),
            company_eligibility_hard_exclusion_codes=tuple(
                sorted(company_path_decision.hard_exclusion_codes)
            ),
            company_eligibility_supporting_assertion_ids=tuple(
                sorted(company_path_decision.supporting_assertion_ids)
            ),
            patent_path_result_content_sha256=patent_path_result.content_sha256,
            patent_traversal_directions=patent_path_result.traversal_directions,
            patent_relationship_decision_ids=(
                patent_path_result.relationship_decision_ids
            ),
            patent_eligibility_decision_id=patent_path_decision.decision_id,
            patent_eligibility_policy_id=patent_path_decision.policy.policy_id,
            patent_eligibility_policy_version=(
                patent_path_decision.policy.policy_version
            ),
            patent_eligibility_policy_content_sha256=(
                patent_path_decision.policy.content_sha256
            ),
            patent_eligibility_outcome=patent_path_decision.outcome.value,
            patent_eligibility_limitations=tuple(
                sorted(patent_path_decision.limitations)
            ),
            patent_eligibility_hard_exclusion_codes=tuple(
                sorted(patent_path_decision.hard_exclusion_codes)
            ),
            patent_eligibility_supporting_assertion_ids=tuple(
                sorted(patent_path_decision.supporting_assertion_ids)
            ),
            candidate_canonical_id=patent_id,
            candidate_display_name=patent.title,
            candidate_origin_public_evidence_ids=origin_evidence_ids,
            candidate_quality_flags=quality_flags,
            claim_subject_id=expected_patent_ref,
            claim_value=expected_company_ref,
            snippet_sha256=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
        )
        evidence = EvidenceItem(
            evidence_id=trace.evidence_id,
            object_id=patent_id,
            domain="patent",
            lane="relationship",
            source_nature="local",
            source_locator=_local_projection_locator(trace),
            snippet=snippet,
            score=1.0,
            source_authority="canonical_release",
            observed_at=relationship_result.as_of,
            claim_binding=EvidenceClaimBinding(
                subject_id=expected_patent_ref,
                predicate="patent_has_applicant",
                value=expected_company_ref,
                status="accepted",
            ),
            local_projection_trace=trace,
        )
        candidates.append(
            RecallCandidate(
                raw_candidate_id=trace.raw_candidate_id,
                display_name=patent.title,
                domain="patent",
                identity_kind="canonical",
                canonical_id=patent_id,
                reference_type=None,
                resolution_state="resolved",
                relationship_state="accepted",
                origin_public_evidence_ids=origin_evidence_ids,
                query_view=request.query_view,
                lane="relationship",
                attempt=1,
                release_id=bundle.release_id,
                adapter_version=_RELATIONSHIP_ADAPTER_VERSION,
                raw_score=1.0,
                quality_flags=quality_flags,
                evidence=(evidence,),
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.evidence[0].local_projection_trace.canonical_relationship_id
            if isinstance(
                candidate.evidence[0].local_projection_trace,
                LocalCanonicalRelationshipTrace,
            )
            else "",
            candidate.raw_candidate_id,
        )
    )
    return tuple(candidates[: request.max_candidates])


def _professor_to_paper_relationship_candidates(
    *,
    request: LaneRequest,
    authority: _RelationshipAuthority,
) -> tuple[RecallCandidate, ...]:
    displayed_ids = request.structured_constraints.displayed_entity_ids
    if not displayed_ids:
        return ()
    displayed_professor_id = displayed_ids[0]
    public_projections = {
        (projection.entity_type, projection.canonical_identity_id): projection
        for projection in authority.candidate_result.public_domain_projections
    }
    if len(public_projections) != len(
        authority.candidate_result.public_domain_projections
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "public relationship endpoint projection authority is duplicated"
        )
    professor = public_projections.get(("professor", displayed_professor_id))
    if not isinstance(professor, ProfessorProjection):
        return ()
    protected_slots = tuple(
        slot for slot in request.protected_slots if slot.kind == "displayed_entity_set"
    )
    if len(protected_slots) != 1 or protected_slots[0].entity_ids != displayed_ids:
        raise IsolatedKnowledgeReadIntegrityError(
            "returnable public relationship requires one protected Professor source"
        )
    protected_slot = protected_slots[0]
    enumeration = request.relationship_enumeration_policy
    if enumeration is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "returnable public relationship requires enumeration authority"
        )

    relationship_request = authority.relationship_request
    relationship_result = authority.relationship_result
    bundle = authority.internal_authority.bundle
    publication = authority.internal_authority.publication
    projection_candidates = {
        candidate.candidate_id: candidate
        for candidate in relationship_request.candidates
    }
    shared_assertions = {
        assertion.assertion_id: assertion
        for assertion in relationship_request.relationship_assertions
    }
    assignments = {
        assignment.source_identity_id: assignment
        for assignment in relationship_request.source_canonical_assignments
    }
    decision_inputs = {
        decision.decision_input_id: decision
        for decision in relationship_request.decision_inputs
    }
    retained_references = {
        retained.reference_id: retained
        for retained in relationship_request.retained_assertions
    }
    decisions = {
        decision.decision_id: decision
        for decision in relationship_result.relationship_decisions
    }
    relationship_types = {
        (item.relationship_type_id, item.version): item
        for item in relationship_result.relationship_types
    }
    authorities = (
        (projection_candidates, relationship_request.candidates, "candidate"),
        (
            shared_assertions,
            relationship_request.relationship_assertions,
            "shared assertion",
        ),
        (
            assignments,
            relationship_request.source_canonical_assignments,
            "source assignment",
        ),
        (decision_inputs, relationship_request.decision_inputs, "decision input"),
        (retained_references, relationship_request.retained_assertions, "retained"),
        (decisions, relationship_result.relationship_decisions, "decision"),
        (relationship_types, relationship_result.relationship_types, "type"),
    )
    if any(len(index) != len(values) for index, values, _ in authorities):
        duplicated = next(
            name for index, values, name in authorities if len(index) != len(values)
        )
        raise IsolatedKnowledgeReadIntegrityError(
            f"Professor-Paper {duplicated} authority is duplicated"
        )
    outcomes_by_relationship: defaultdict[str, list[RelationshipCandidateOutcome]] = (
        defaultdict(list)
    )
    for outcome in relationship_result.candidate_outcomes:
        if outcome.projected_relationship_id is not None:
            outcomes_by_relationship[outcome.projected_relationship_id].append(outcome)

    path_pairs: dict[str, tuple[Any, Any]] = {}
    for path_request, path_result in zip(
        authority.internal_authority.index_request.public_path_eligibility_requests,
        authority.internal_authority.index_request.public_path_eligibility_results,
        strict=True,
    ):
        if PathEligibilityEngine().evaluate(path_request) != path_result:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper path eligibility result differs from exact replay"
            )
        projection = path_request.projection
        if projection is None:
            continue
        identity_id = projection.canonical_identity_id
        if identity_id in path_pairs:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper path eligibility authority is duplicated"
            )
        path_pairs[identity_id] = (path_request, path_result)

    def returnable_eligibility(
        identity_id: str,
        *,
        domain: str,
        direction: str,
        related_identity_id: str,
        relationship_decision: RelationshipDecision,
    ) -> tuple[Any, Any, Any] | None:
        pair = path_pairs.get(identity_id)
        if pair is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper endpoint path pair is absent"
            )
        path_request, path_result = pair
        projection = path_request.projection
        related = path_request.related_projections
        if (
            projection is None
            or projection.canonical_identity_id != identity_id
            or projection.domain != domain
            or projection.release_id != bundle.release_id
            or projection.projection_id != f"typed:{domain}:{identity_id}"
            or len(related) != 1
            or related[0].canonical_identity_id != related_identity_id
            or related[0].release_id != bundle.release_id
            or path_request.relationship_decisions != (relationship_decision,)
            or path_request.requested_traversal_direction != direction
            or path_result.release_id != bundle.release_id
            or path_result.subject_identity_id != identity_id
            or path_result.projection_id != projection.projection_id
            or path_result.resolved_projection_id != projection.projection_id
            or path_result.traversal_directions != (direction,)
            or path_result.relationship_decision_ids
            != (relationship_decision.decision_id,)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper endpoint path pair differs"
            )
        matches = tuple(
            decision
            for decision in path_result.decisions
            if decision.path == "verified_relationship_traversal"
        )
        if len(matches) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper endpoint eligibility is missing or ambiguous"
            )
        decision = matches[0]
        if decision.outcome is PolicyOutcome.excluded:
            return None
        if decision.outcome not in {PolicyOutcome.admitted, PolicyOutcome.limited}:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper endpoint eligibility is not returnable"
            )
        if decision.hard_exclusion_codes:
            raise IsolatedKnowledgeReadIntegrityError(
                "returnable Professor-Paper endpoint has a hard exclusion"
            )
        return path_request, path_result, decision

    relationship_enumeration_policy_sha256 = _canonical_sha256(
        enumeration.model_dump(mode="json")
    )
    protected_slot_content_sha256 = _canonical_sha256(
        protected_slot.model_dump(mode="json")
    )
    candidates: list[RecallCandidate] = []
    for current in relationship_result.current_relationships:
        if not isinstance(current, CurrentRelationshipProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper current projection has an invalid type"
            )
        if (
            current.relationship_type_id,
            current.relationship_type_version,
        ) != _PROFESSOR_PAPER_TYPE:
            continue
        if current.source_endpoint.canonical_identity_id != displayed_professor_id:
            continue
        relationship_type = relationship_types.get(_PROFESSOR_PAPER_TYPE)
        if (
            relationship_type is None
            or "professor" not in relationship_type.source_entity_types
            or "paper" not in relationship_type.target_entity_types
            or "professor_to_paper" not in relationship_type.eligible_paths
            or "paper_to_professor" not in relationship_type.eligible_paths
            or relationship_type.time_semantics.value != "observed_at"
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper relationship type/path is not installed"
            )
        outcome_matches = outcomes_by_relationship.get(
            current.canonical_relationship_id,
            [],
        )
        if len(outcome_matches) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper candidate outcome is missing or ambiguous"
            )
        outcome = outcome_matches[0]
        projection_candidate = projection_candidates.get(outcome.candidate_id)
        decision = decisions.get(current.decision_id)
        if (
            not isinstance(projection_candidate, RelationshipProjectionCandidate)
            or not isinstance(decision, RelationshipDecision)
            or projection_candidate.assertion_input_id is None
            or projection_candidate.decision_input_id is None
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper input/decision chain is absent"
            )
        shared_assertion = shared_assertions.get(
            projection_candidate.assertion_input_id
        )
        decision_input = decision_inputs.get(projection_candidate.decision_input_id)
        if not isinstance(shared_assertion, RelationshipAssertion):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper shared assertion is absent"
            )
        source_assignment = assignments.get(
            shared_assertion.source_endpoint.identity_id
        )
        target_assignment = assignments.get(
            shared_assertion.target_endpoint.identity_id
        )
        if not isinstance(
            source_assignment, SourceCanonicalAssignment
        ) or not isinstance(
            target_assignment,
            SourceCanonicalAssignment,
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper source assignment is absent"
            )
        expected_professor_ref = f"canonical:professor:{displayed_professor_id}"
        paper_id = current.target_endpoint.canonical_identity_id
        if paper_id is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper target is not a canonical Paper"
            )
        expected_paper_ref = f"canonical:paper:{paper_id}"
        expected_attributes = {
            "candidate_id": projection_candidate.candidate_id,
            "evidence_refs": sorted(
                {
                    reference
                    for binding in projection_candidate.evidence_bindings
                    for reference in (*binding.assertion_refs, *binding.artifact_refs)
                }
            ),
            "evidence_metadata": projection_candidate.evidence_metadata,
            "role_bindings": {},
        }
        if (
            decision_input is None
            or not outcome.admitted
            or outcome.reason_codes
            or outcome.decision_state != "accepted"
            or outcome.current_projection_state != "current"
            or outcome.current_projection_reason_codes
            or outcome.retained_assertion_id != shared_assertion.assertion_id
            or outcome.decision_id != decision.decision_id
            or outcome.projected_relationship_id != current.canonical_relationship_id
            or outcome.selected_evidence_refs != current.selected_evidence_refs
            or outcome.source_reference_kind != "canonical_identity"
            or outcome.target_reference_kind != "canonical_identity"
            or outcome.source_canonical_identity_id != displayed_professor_id
            or outcome.target_canonical_identity_id != paper_id
            or outcome.source_parent_canonical_identity_ref is not None
            or outcome.target_parent_canonical_identity_ref is not None
            or outcome.effective_time_semantics != "observed_at"
            or projection_candidate.assertion_input_kind
            != "shared_source_relationship_assertion"
            or projection_candidate.relationship_type_id != current.relationship_type_id
            or projection_candidate.relationship_type_version
            != current.relationship_type_version
            or projection_candidate.source_endpoint != current.source_endpoint
            or projection_candidate.target_endpoint != current.target_endpoint
            or projection_candidate.role_bindings
            or shared_assertion.relationship_type_id != current.relationship_type_id
            or shared_assertion.relationship_type_version
            != current.relationship_type_version
            or shared_assertion.source_endpoint.identity_space != "source"
            or shared_assertion.source_endpoint.entity_type != "professor"
            or shared_assertion.target_endpoint.identity_space != "source"
            or shared_assertion.target_endpoint.entity_type != "paper"
            or shared_assertion.attributes != expected_attributes
            or shared_assertion.observed_at != projection_candidate.observed_at
            or shared_assertion.source_event_time
            != projection_candidate.source_event_time
            or shared_assertion.valid_from != projection_candidate.valid_from
            or shared_assertion.valid_to != projection_candidate.valid_to
            or source_assignment.entity_type != "professor"
            or source_assignment.canonical_identity_id != displayed_professor_id
            or target_assignment.entity_type != "paper"
            or target_assignment.canonical_identity_id != paper_id
            or shared_assertion.source_record_id
            not in source_assignment.source_record_refs
            or shared_assertion.source_record_id
            not in target_assignment.source_record_refs
            or decision_input.decision_id != decision.decision_id
            or decision_input.canonical_relationship_id
            != current.canonical_relationship_id
            or decision_input.state != "accepted"
            or decision_input.candidate_assertion_ids
            != decision.candidate_assertion_ids
            or decision_input.selected_assertion_ids != decision.selected_assertion_ids
            or decision_input.conflicting_assertion_ids
            != decision.conflicting_assertion_ids
            or decision_input.role_bindings != decision.role_bindings
            or decision_input.policy != decision.policy
            or decision_input.method != decision.method
            or decision_input.method_version != decision.method_version
            or decision_input.confidence != decision.confidence
            or decision_input.rationale != decision.rationale
            or decision.state.value != "accepted"
            or decision.canonical_relationship_id != current.canonical_relationship_id
            or decision.relationship_type_id != current.relationship_type_id
            or decision.relationship_type_version != current.relationship_type_version
            or decision.source_canonical_identity_id != displayed_professor_id
            or decision.target_canonical_identity_id != paper_id
            or decision.role_bindings
            or decision.valid_from != current.valid_from
            or decision.valid_to != current.valid_to
            or decision.release_id != current.release_id
            or current.release_id != bundle.release_id
            or current.projected_at != relationship_result.as_of
            or current.source_endpoint.endpoint_type != "professor"
            or current.source_endpoint.stable_reference != expected_professor_ref
            or current.target_endpoint.endpoint_type != "paper"
            or current.target_endpoint.stable_reference != expected_paper_ref
            or current.role_bindings
            or current.effective_time_semantics != "observed_at"
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper candidate/assertion/decision continuity differs"
            )
        evidence_bindings = projection_candidate.evidence_bindings
        if len(evidence_bindings) != 1:
            continue
        evidence_binding = evidence_bindings[0]
        if (
            evidence_binding.evidence_kind
            != "professor_page_or_identity_attribution_assertion"
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper evidence kind differs"
            )
        if len(evidence_binding.assertion_refs) != 1 or evidence_binding.artifact_refs:
            continue
        retained = retained_references.get(evidence_binding.assertion_refs[0])
        if retained is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper retained reference is absent"
            )
        if retained.source_record_ref != shared_assertion.source_record_id:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper candidate/assertion/decision continuity differs"
            )
        if retained.artifact_refs:
            continue
        expected_evidence_refs = (retained.reference_id,)
        if (
            outcome.selected_evidence_refs != expected_evidence_refs
            or decision_input.selected_evidence_refs != expected_evidence_refs
            or current.selected_evidence_refs != expected_evidence_refs
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper retained evidence continuity differs"
            )
        paper = public_projections.get(("paper", paper_id))
        if not isinstance(paper, PaperProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper public Paper projection is absent"
            )
        professor_eligibility = returnable_eligibility(
            displayed_professor_id,
            domain="professor",
            direction="professor_to_paper",
            related_identity_id=paper_id,
            relationship_decision=decision,
        )
        paper_eligibility = returnable_eligibility(
            paper_id,
            domain="paper",
            direction="paper_to_professor",
            related_identity_id=displayed_professor_id,
            relationship_decision=decision,
        )
        if professor_eligibility is None or paper_eligibility is None:
            continue
        (
            professor_path_request,
            professor_path_result,
            professor_path_decision,
        ) = professor_eligibility
        paper_path_request, paper_path_result, paper_path_decision = paper_eligibility
        if (
            professor_path_request.projection is None
            or paper_path_request.projection is None
            or professor_path_request.projection.domain_identity_status is not None
            or paper_path_request.projection.domain_identity_status
            not in {"confirmed", "unverified"}
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper endpoint identity status differs"
            )
        paper_identity_status = paper_path_request.projection.domain_identity_status
        limitations = tuple(
            sorted(
                set(professor_path_decision.limitations)
                | set(paper_path_decision.limitations)
            )
        )
        quality_flags = limitations
        if enumeration.as_of > relationship_result.as_of:
            canonical_snapshot = (
                relationship_result.as_of.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            quality_flags = tuple(
                sorted(
                    {
                        *quality_flags,
                        f"relationship_snapshot_as_of:{canonical_snapshot}",
                    }
                )
            )
        origin_evidence_ids = tuple(sorted(decision.selected_assertion_ids))
        snippet = json.dumps(
            shared_assertion.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        evidence_source_locator = (
            f"canonical-v2-isolated:{bundle.index_target.target_id}:"
            f"{current.canonical_relationship_id}"
        )
        trace = LocalProfessorPaperRelationshipTrace(
            target_id=bundle.index_target.target_id,
            target_marker_sha256=bundle.index_target.marker_sha256,
            manifest_sha256=bundle.manifest.manifest_sha256,
            index_result_content_sha256=bundle.index_result.content_sha256,
            publication_verification_evidence_ids=tuple(
                sorted(publication.verification_evidence_ids)
            ),
            release_id=bundle.release_id,
            lane_request_content_sha256=request.content_sha256,
            relationship_enumeration_policy_sha256=relationship_enumeration_policy_sha256,
            displayed_entity_ids=displayed_ids,
            displayed_professor_id=displayed_professor_id,
            protected_slot_id=protected_slot.slot_id,
            protected_slot_content_sha256=protected_slot_content_sha256,
            query_as_of=enumeration.as_of,
            relationship_request_sha256=authority.relationship_request_content_sha256,
            relationship_result_sha256=relationship_result.content_sha256,
            relationship_projection_run_id=relationship_result.projection_run_id,
            relationship_projection_schema_version=(
                relationship_result.projection_schema_version
            ),
            relationship_registry_version=(
                relationship_result.relationship_registry_version
            ),
            relationship_registry_content_sha256=(
                relationship_result.relationship_registry_content_sha256
            ),
            relationship_snapshot_as_of=relationship_result.as_of,
            canonical_relationship_id=current.canonical_relationship_id,
            current_relationship_content_sha256=_canonical_sha256(
                current.model_dump(mode="json")
            ),
            relationship_decision_input_id=decision_input.decision_input_id,
            relationship_decision_input_content_sha256=_canonical_sha256(
                decision_input.model_dump(mode="json")
            ),
            relationship_decision_id=decision.decision_id,
            relationship_decision_content_sha256=_canonical_sha256(
                decision.model_dump(mode="json")
            ),
            relationship_source_endpoint=current.source_endpoint.stable_reference,
            relationship_target_endpoint=current.target_endpoint.stable_reference,
            relationship_role_bindings=(),
            selected_evidence_refs=expected_evidence_refs,
            relationship_valid_from=(
                current.valid_from.model_dump(mode="json")
                if current.valid_from is not None
                else None
            ),
            relationship_valid_to=(
                current.valid_to.model_dump(mode="json")
                if current.valid_to is not None
                else None
            ),
            projection_candidate_id=projection_candidate.candidate_id,
            projection_candidate_content_sha256=_canonical_sha256(
                projection_candidate.model_dump(mode="json")
            ),
            projection_candidate_observed_at=projection_candidate.observed_at,
            projection_candidate_source_event_time=(
                projection_candidate.source_event_time
            ),
            projection_candidate_assertion_input_id=(
                projection_candidate.assertion_input_id
            ),
            projection_candidate_decision_input_id=(
                projection_candidate.decision_input_id
            ),
            projection_candidate_evidence_metadata=(
                projection_candidate.evidence_metadata
            ),
            shared_assertion_id=shared_assertion.assertion_id,
            shared_assertion_content_sha256=_canonical_sha256(
                shared_assertion.model_dump(mode="json")
            ),
            shared_assertion_source_record_id=shared_assertion.source_record_id,
            shared_assertion_source_identity_id=(
                shared_assertion.source_endpoint.identity_id
            ),
            shared_assertion_target_identity_id=(
                shared_assertion.target_endpoint.identity_id
            ),
            shared_assertion_evidence_refs=expected_evidence_refs,
            shared_assertion_attributes_content_sha256=_canonical_sha256(
                shared_assertion.attributes
            ),
            shared_assertion_observed_at=shared_assertion.observed_at,
            shared_assertion_source_event_time=shared_assertion.source_event_time,
            shared_assertion_valid_from=(
                shared_assertion.valid_from.model_dump(mode="json")
                if shared_assertion.valid_from is not None
                else None
            ),
            shared_assertion_valid_to=(
                shared_assertion.valid_to.model_dump(mode="json")
                if shared_assertion.valid_to is not None
                else None
            ),
            source_assignment_id=source_assignment.assignment_id,
            source_assignment_content_sha256=_canonical_sha256(
                source_assignment.model_dump(mode="json")
            ),
            source_assignment_source_identity_id=(source_assignment.source_identity_id),
            source_assignment_canonical_identity_id=(
                source_assignment.canonical_identity_id
            ),
            source_assignment_source_record_refs=(source_assignment.source_record_refs),
            target_assignment_id=target_assignment.assignment_id,
            target_assignment_content_sha256=_canonical_sha256(
                target_assignment.model_dump(mode="json")
            ),
            target_assignment_source_identity_id=(target_assignment.source_identity_id),
            target_assignment_canonical_identity_id=(
                target_assignment.canonical_identity_id
            ),
            target_assignment_source_record_refs=(target_assignment.source_record_refs),
            candidate_outcome_candidate_id=outcome.candidate_id,
            candidate_outcome_content_sha256=_canonical_sha256(
                outcome.model_dump(mode="json")
            ),
            candidate_outcome_retained_assertion_id=shared_assertion.assertion_id,
            candidate_outcome_decision_id=decision.decision_id,
            candidate_outcome_projected_relationship_id=(
                current.canonical_relationship_id
            ),
            candidate_outcome_selected_evidence_refs=expected_evidence_refs,
            decision_input_candidate_assertion_ids=(
                decision_input.candidate_assertion_ids
            ),
            decision_input_selected_assertion_ids=(
                decision_input.selected_assertion_ids
            ),
            decision_input_conflicting_assertion_ids=(
                decision_input.conflicting_assertion_ids
            ),
            decision_input_selected_evidence_refs=(
                decision_input.selected_evidence_refs
            ),
            decision_candidate_assertion_ids=decision.candidate_assertion_ids,
            decision_selected_assertion_ids=decision.selected_assertion_ids,
            decision_conflicting_assertion_ids=decision.conflicting_assertion_ids,
            decision_source_canonical_identity_id=(
                decision.source_canonical_identity_id
            ),
            decision_target_canonical_identity_id=(
                decision.target_canonical_identity_id
            ),
            decision_release_id=decision.release_id,
            current_selected_evidence_refs=expected_evidence_refs,
            retained_reference_id=retained.reference_id,
            retained_reference_content_sha256=_canonical_sha256(
                retained.model_dump(mode="json")
            ),
            retained_assertion_id=retained.assertion_id,
            retained_source_record_id=retained.source_record_ref,
            retained_artifact_refs=(),
            professor_id=displayed_professor_id,
            professor_stable_reference=expected_professor_ref,
            professor_projection_content_sha256=professor.content_sha256,
            professor_display_name=professor.name,
            paper_id=paper_id,
            paper_stable_reference=expected_paper_ref,
            paper_projection_content_sha256=paper.content_sha256,
            paper_display_name=paper.title,
            paper_domain_identity_status=paper_identity_status,
            professor_path_result_content_sha256=(professor_path_result.content_sha256),
            professor_traversal_directions=(professor_path_result.traversal_directions),
            professor_relationship_decision_ids=(
                professor_path_result.relationship_decision_ids
            ),
            professor_eligibility_decision_id=professor_path_decision.decision_id,
            professor_eligibility_policy_id=(professor_path_decision.policy.policy_id),
            professor_eligibility_policy_version=(
                professor_path_decision.policy.policy_version
            ),
            professor_eligibility_policy_content_sha256=(
                professor_path_decision.policy.content_sha256
            ),
            professor_eligibility_outcome=professor_path_decision.outcome.value,
            professor_eligibility_limitations=tuple(
                sorted(professor_path_decision.limitations)
            ),
            professor_eligibility_hard_exclusion_codes=tuple(
                sorted(professor_path_decision.hard_exclusion_codes)
            ),
            professor_eligibility_supporting_assertion_ids=tuple(
                sorted(professor_path_decision.supporting_assertion_ids)
            ),
            paper_path_result_content_sha256=paper_path_result.content_sha256,
            paper_traversal_directions=paper_path_result.traversal_directions,
            paper_relationship_decision_ids=(
                paper_path_result.relationship_decision_ids
            ),
            paper_eligibility_decision_id=paper_path_decision.decision_id,
            paper_eligibility_policy_id=paper_path_decision.policy.policy_id,
            paper_eligibility_policy_version=(
                paper_path_decision.policy.policy_version
            ),
            paper_eligibility_policy_content_sha256=(
                paper_path_decision.policy.content_sha256
            ),
            paper_eligibility_outcome=paper_path_decision.outcome.value,
            paper_eligibility_limitations=tuple(
                sorted(paper_path_decision.limitations)
            ),
            paper_eligibility_hard_exclusion_codes=tuple(
                sorted(paper_path_decision.hard_exclusion_codes)
            ),
            paper_eligibility_supporting_assertion_ids=tuple(
                sorted(paper_path_decision.supporting_assertion_ids)
            ),
            candidate_canonical_id=paper_id,
            candidate_display_name=paper.title,
            candidate_origin_public_evidence_ids=origin_evidence_ids,
            candidate_quality_flags=quality_flags,
            claim_subject_id=expected_professor_ref,
            claim_value=expected_paper_ref,
            evidence_source_locator=evidence_source_locator,
            evidence_observed_at=relationship_result.as_of,
            snippet_sha256=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
        )
        evidence = EvidenceItem(
            evidence_id=trace.evidence_id,
            object_id=paper_id,
            domain="paper",
            lane="relationship",
            source_nature="local",
            source_locator=evidence_source_locator,
            snippet=snippet,
            score=1.0,
            source_authority="canonical_release",
            observed_at=relationship_result.as_of,
            claim_binding=EvidenceClaimBinding(
                subject_id=expected_professor_ref,
                predicate="professor_attributed_to_paper",
                value=expected_paper_ref,
                status="accepted",
            ),
            local_projection_trace=trace,
        )
        candidates.append(
            RecallCandidate(
                raw_candidate_id=trace.raw_candidate_id,
                display_name=paper.title,
                domain="paper",
                identity_kind="canonical",
                canonical_id=paper_id,
                reference_type=None,
                resolution_state="resolved",
                relationship_state="accepted",
                origin_public_evidence_ids=origin_evidence_ids,
                query_view=request.query_view,
                lane="relationship",
                attempt=1,
                release_id=bundle.release_id,
                adapter_version=_RELATIONSHIP_ADAPTER_VERSION,
                raw_score=1.0,
                quality_flags=quality_flags,
                evidence=(evidence,),
            )
        )

    return tuple(candidates[: request.max_candidates])


def _paper_to_professor_relationship_candidates(
    *,
    request: LaneRequest,
    authority: _RelationshipAuthority,
) -> tuple[RecallCandidate, ...]:
    """Replay the accepted forward authority, then expose its exact inverse view."""

    displayed_ids = request.structured_constraints.displayed_entity_ids
    if not displayed_ids:
        return ()
    displayed_paper_id = displayed_ids[0]
    public_projections = {
        (projection.entity_type, projection.canonical_identity_id): projection
        for projection in authority.candidate_result.public_domain_projections
    }
    if len(public_projections) != len(
        authority.candidate_result.public_domain_projections
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "public relationship endpoint projection authority is duplicated"
        )
    paper = public_projections.get(("paper", displayed_paper_id))
    if not isinstance(paper, PaperProjection):
        return ()
    protected_slots = tuple(
        slot for slot in request.protected_slots if slot.kind == "displayed_entity_set"
    )
    if len(protected_slots) != 1 or protected_slots[0].entity_ids != displayed_ids:
        raise IsolatedKnowledgeReadIntegrityError(
            "returnable public relationship requires one protected Paper source"
        )
    protected_slot = protected_slots[0]

    professor_ids: list[str] = []
    for current in authority.relationship_result.current_relationships:
        if not isinstance(current, CurrentRelationshipProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper current projection has an invalid type"
            )
        if (
            current.relationship_type_id,
            current.relationship_type_version,
        ) != _PROFESSOR_PAPER_TYPE:
            continue
        if current.target_endpoint.canonical_identity_id != displayed_paper_id:
            continue
        professor_id = current.source_endpoint.canonical_identity_id
        if professor_id is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor-Paper source is not a canonical Professor"
            )
        if professor_id not in professor_ids:
            professor_ids.append(professor_id)

    candidates: list[RecallCandidate] = []
    for professor_id in professor_ids:
        forward_payload = request.model_dump(
            mode="json",
            exclude={"content_sha256"},
        )
        forward_payload["domains"] = ["paper"]
        forward_payload["max_candidates"] = len(
            authority.relationship_result.current_relationships
        )
        forward_payload["relationship_paths"] = [
            {
                "relationship_type_id": "professor_authored_paper",
                "direction": "professor_to_paper",
                "source_type": "professor",
                "target_type": "paper",
            }
        ]
        forward_payload["structured_constraints"]["displayed_entity_ids"] = [
            professor_id
        ]
        forward_payload["protected_slots"] = [
            *(
                slot.model_dump(mode="json")
                for slot in request.protected_slots
                if slot.kind != "displayed_entity_set"
            ),
            ProtectedSlot(
                kind="displayed_entity_set",
                value="displayed_entity_set",
                entity_ids=(professor_id,),
            ).model_dump(mode="json"),
        ]
        forward_request = LaneRequest.model_validate(forward_payload)
        forward_candidates = _professor_to_paper_relationship_candidates(
            request=forward_request,
            authority=authority,
        )
        for forward_candidate in forward_candidates:
            if forward_candidate.canonical_id != displayed_paper_id:
                continue
            if len(forward_candidate.evidence) != 1:
                raise IsolatedKnowledgeReadIntegrityError(
                    "Professor-Paper forward replay returned unsupported evidence"
                )
            forward_evidence = forward_candidate.evidence[0]
            forward_trace = forward_evidence.local_projection_trace
            if not isinstance(
                forward_trace,
                LocalProfessorPaperRelationshipTrace,
            ):
                raise IsolatedKnowledgeReadIntegrityError(
                    "Professor-Paper forward replay returned the wrong trace"
                )
            trace_payload = forward_trace.model_dump(mode="python")
            trace_payload.pop("displayed_professor_id")
            trace_payload.update(
                {
                    "lane_request_content_sha256": request.content_sha256,
                    "displayed_entity_ids": displayed_ids,
                    "displayed_paper_id": displayed_paper_id,
                    "protected_slot_id": protected_slot.slot_id,
                    "protected_slot_content_sha256": _canonical_sha256(
                        protected_slot.model_dump(mode="json")
                    ),
                    "query_relationship_type_id": "professor_authored_paper",
                    "query_direction": "paper_to_professor",
                    "query_source_type": "paper",
                    "query_target_type": "professor",
                    "candidate_domain": "professor",
                    "candidate_canonical_id": forward_trace.professor_id,
                    "candidate_display_name": forward_trace.professor_display_name,
                    "path": "paper_professor_relationship_traversal",
                    "raw_candidate_id": "",
                    "evidence_id": "",
                    "content_sha256": "0" * 64,
                }
            )
            trace = LocalPaperProfessorRelationshipTrace.model_validate(trace_payload)
            evidence = EvidenceItem(
                evidence_id=trace.evidence_id,
                object_id=trace.professor_id,
                domain="professor",
                lane="relationship",
                source_nature="local",
                source_locator=trace.evidence_source_locator,
                snippet=forward_evidence.snippet,
                score=1.0,
                source_authority="canonical_release",
                observed_at=trace.relationship_snapshot_as_of,
                claim_binding=EvidenceClaimBinding(
                    subject_id=trace.claim_subject_id,
                    predicate=trace.claim_predicate,
                    value=trace.claim_value,
                    status=trace.claim_status,
                ),
                local_projection_trace=trace,
            )
            candidates.append(
                RecallCandidate(
                    raw_candidate_id=trace.raw_candidate_id,
                    display_name=trace.professor_display_name,
                    domain="professor",
                    identity_kind="canonical",
                    canonical_id=trace.professor_id,
                    reference_type=None,
                    resolution_state="resolved",
                    relationship_state="accepted",
                    origin_public_evidence_ids=(
                        trace.candidate_origin_public_evidence_ids
                    ),
                    query_view=request.query_view,
                    lane="relationship",
                    attempt=1,
                    release_id=trace.release_id,
                    adapter_version=_RELATIONSHIP_ADAPTER_VERSION,
                    raw_score=1.0,
                    quality_flags=trace.candidate_quality_flags,
                    evidence=(evidence,),
                )
            )

    return tuple(candidates[: request.max_candidates])


def _patent_to_company_relationship_candidates(
    *,
    request: LaneRequest,
    authority: _RelationshipAuthority,
) -> tuple[RecallCandidate, ...]:
    """Replay the accepted forward authority, then expose its exact inverse view."""

    displayed_ids = request.structured_constraints.displayed_entity_ids
    if not displayed_ids:
        return ()
    displayed_patent_id = displayed_ids[0]
    public_projections = {
        (projection.entity_type, projection.canonical_identity_id): projection
        for projection in authority.candidate_result.public_domain_projections
    }
    if len(public_projections) != len(
        authority.candidate_result.public_domain_projections
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "public relationship endpoint projection authority is duplicated"
        )
    patent = public_projections.get(("patent", displayed_patent_id))
    if not isinstance(patent, PatentProjection):
        return ()
    protected_slots = tuple(
        slot for slot in request.protected_slots if slot.kind == "displayed_entity_set"
    )
    if len(protected_slots) != 1 or protected_slots[0].entity_ids != displayed_ids:
        raise IsolatedKnowledgeReadIntegrityError(
            "returnable public relationship requires one protected Patent source"
        )
    protected_slot = protected_slots[0]

    company_ids: list[str] = []
    for current in authority.relationship_result.current_relationships:
        if not isinstance(current, CurrentRelationshipProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent-Company current projection has an invalid type"
            )
        if (
            current.relationship_type_id,
            current.relationship_type_version,
        ) != _PATENT_APPLICANT_TYPE:
            continue
        if current.source_endpoint.canonical_identity_id != displayed_patent_id:
            continue
        company_id = current.target_endpoint.canonical_identity_id
        if company_id is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "Patent-Company target is not a canonical Company"
            )
        if company_id not in company_ids:
            company_ids.append(company_id)

    candidates: list[RecallCandidate] = []
    for company_id in company_ids:
        forward_payload = request.model_dump(
            mode="json",
            exclude={"content_sha256"},
        )
        forward_payload["domains"] = ["patent"]
        forward_payload["max_candidates"] = len(
            authority.relationship_result.current_relationships
        )
        forward_payload["relationship_paths"] = [
            {
                "relationship_type_id": "company_has_patent",
                "direction": "company_to_patent",
                "source_type": "company",
                "target_type": "patent",
            }
        ]
        forward_payload["structured_constraints"]["displayed_entity_ids"] = [company_id]
        forward_payload["protected_slots"] = [
            *(
                slot.model_dump(mode="json")
                for slot in request.protected_slots
                if slot.kind != "displayed_entity_set"
            ),
            ProtectedSlot(
                kind="displayed_entity_set",
                value="displayed_entity_set",
                entity_ids=(company_id,),
            ).model_dump(mode="json"),
        ]
        forward_request = LaneRequest.model_validate(forward_payload)
        forward_candidates = _company_to_patent_relationship_candidates(
            request=forward_request,
            authority=authority,
        )
        for forward_candidate in forward_candidates:
            if forward_candidate.canonical_id != displayed_patent_id:
                continue
            if len(forward_candidate.evidence) != 1:
                raise IsolatedKnowledgeReadIntegrityError(
                    "Patent-Company forward replay returned unsupported evidence"
                )
            forward_evidence = forward_candidate.evidence[0]
            forward_trace = forward_evidence.local_projection_trace
            if not isinstance(
                forward_trace,
                LocalCanonicalRelationshipTrace,
            ):
                raise IsolatedKnowledgeReadIntegrityError(
                    "Patent-Company forward replay returned the wrong trace"
                )
            trace_payload = forward_trace.model_dump(mode="python")
            trace_payload.pop("displayed_company_id")
            trace_payload.update(
                {
                    "lane_request_content_sha256": request.content_sha256,
                    "displayed_entity_ids": displayed_ids,
                    "displayed_patent_id": displayed_patent_id,
                    "protected_slot_id": protected_slot.slot_id,
                    "protected_slot_content_sha256": _canonical_sha256(
                        protected_slot.model_dump(mode="json")
                    ),
                    "query_relationship_type_id": "company_has_patent",
                    "query_direction": "patent_to_company",
                    "query_source_type": "patent",
                    "query_target_type": "company",
                    "candidate_domain": "company",
                    "candidate_canonical_id": forward_trace.company_id,
                    "candidate_display_name": forward_trace.company_display_name,
                    "path": "patent_company_relationship_traversal",
                    "raw_candidate_id": "",
                    "evidence_id": "",
                    "content_sha256": "0" * 64,
                }
            )
            trace = LocalPatentCompanyRelationshipTrace.model_validate(trace_payload)
            evidence = EvidenceItem(
                evidence_id=trace.evidence_id,
                object_id=trace.company_id,
                domain="company",
                lane="relationship",
                source_nature="local",
                source_locator=_local_projection_locator(trace),
                snippet=forward_evidence.snippet,
                score=1.0,
                source_authority="canonical_release",
                observed_at=trace.relationship_snapshot_as_of,
                claim_binding=EvidenceClaimBinding(
                    subject_id=trace.claim_subject_id,
                    predicate=trace.claim_predicate,
                    value=trace.claim_value,
                    status=trace.claim_status,
                ),
                local_projection_trace=trace,
            )
            candidates.append(
                RecallCandidate(
                    raw_candidate_id=trace.raw_candidate_id,
                    display_name=trace.company_display_name,
                    domain="company",
                    identity_kind="canonical",
                    canonical_id=trace.company_id,
                    reference_type=None,
                    resolution_state="resolved",
                    relationship_state="accepted",
                    origin_public_evidence_ids=(
                        trace.candidate_origin_public_evidence_ids
                    ),
                    query_view=request.query_view,
                    lane="relationship",
                    attempt=1,
                    release_id=trace.release_id,
                    adapter_version=_RELATIONSHIP_ADAPTER_VERSION,
                    raw_score=1.0,
                    quality_flags=trace.candidate_quality_flags,
                    evidence=(evidence,),
                )
            )

    return tuple(candidates[: request.max_candidates])


def _source_bound_relationship_candidates(
    *,
    request: LaneRequest,
    authority: _RelationshipAuthority,
) -> tuple[RecallCandidate, ...]:
    """Traverse accepted source relationships without per-edge eligibility rows."""

    path = request.relationship_paths[0]
    path_key = (
        path.relationship_type_id,
        path.direction,
        path.source_type,
        path.target_type,
    )
    path_config = _SOURCE_BOUND_RELATIONSHIP_PATHS.get(path_key)
    if path_config is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "source-bound relationship path is unsupported"
        )
    physical_type, physical_direction = path_config
    enumeration = request.relationship_enumeration_policy
    if enumeration is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "source-bound relationship traversal requires enumeration policy"
        )
    displayed_ids = request.structured_constraints.displayed_entity_ids
    if not displayed_ids:
        return ()
    displayed_id = displayed_ids[0]
    protected_slots = tuple(
        slot for slot in request.protected_slots if slot.kind == "displayed_entity_set"
    )
    if len(protected_slots) != 1 or protected_slots[0].entity_ids != displayed_ids:
        raise IsolatedKnowledgeReadIntegrityError(
            "source-bound relationship requires one protected source entity"
        )
    protected_slot = protected_slots[0]

    relationship_request = authority.relationship_request
    relationship_result = authority.relationship_result
    bundle = authority.internal_authority.bundle
    publication = authority.internal_authority.publication
    public_projections = {
        (projection.entity_type, projection.canonical_identity_id): projection
        for projection in authority.candidate_result.public_domain_projections
    }
    projection_candidates = {
        candidate.candidate_id: candidate
        for candidate in relationship_request.candidates
    }
    shared_assertions = {
        assertion.assertion_id: assertion
        for assertion in relationship_request.relationship_assertions
    }
    typed_assertions = {
        assertion.assertion_id: assertion
        for assertion in relationship_request.typed_relationship_assertions
    }
    decision_inputs = {
        decision.decision_input_id: decision
        for decision in relationship_request.decision_inputs
    }
    shared_decisions = {
        decision.decision_id: decision
        for decision in relationship_result.relationship_decisions
    }
    typed_decisions = {
        decision.decision_id: decision
        for decision in relationship_result.typed_relationship_decisions
    }
    retained_references = {
        retained.reference_id: retained
        for retained in relationship_request.retained_assertions
    }
    relationship_types = {
        (item.relationship_type_id, item.version): item
        for item in relationship_result.relationship_types
    }
    authority_pairs = (
        (public_projections, authority.candidate_result.public_domain_projections),
        (projection_candidates, relationship_request.candidates),
        (shared_assertions, relationship_request.relationship_assertions),
        (typed_assertions, relationship_request.typed_relationship_assertions),
        (decision_inputs, relationship_request.decision_inputs),
        (shared_decisions, relationship_result.relationship_decisions),
        (typed_decisions, relationship_result.typed_relationship_decisions),
        (retained_references, relationship_request.retained_assertions),
        (relationship_types, relationship_result.relationship_types),
    )
    if any(len(index) != len(values) for index, values in authority_pairs):
        raise IsolatedKnowledgeReadIntegrityError(
            "source-bound relationship authority contains duplicate identities"
        )
    displayed_projection = public_projections.get((path.source_type, displayed_id))
    if (
        displayed_projection is None
        or displayed_projection.release_id != bundle.release_id
    ):
        return ()
    installed_type = relationship_types.get(physical_type)
    if (
        installed_type is None
        or path.direction not in installed_type.eligible_paths
        or physical_type[0] != installed_type.relationship_type_id
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "source-bound relationship type/path is not installed"
        )

    outcomes_by_relationship: defaultdict[str, list[RelationshipCandidateOutcome]] = (
        defaultdict(list)
    )
    for outcome in relationship_result.candidate_outcomes:
        if outcome.projected_relationship_id is not None:
            outcomes_by_relationship[outcome.projected_relationship_id].append(outcome)
    required_roles = (
        frozenset({"founder"})
        if physical_type == _PROFESSOR_COMPANY_TYPE
        and any(
            marker in request.original_query
            for marker in ("创始", "创办", "创立", "创业")
        )
        else frozenset()
    )

    relationship_enumeration_policy_sha256 = _canonical_sha256(
        enumeration.model_dump(mode="json")
    )
    protected_slot_content_sha256 = _canonical_sha256(
        protected_slot.model_dump(mode="json")
    )
    candidates: list[RecallCandidate] = []
    for current in relationship_result.current_relationships:
        if not isinstance(current, CurrentRelationshipProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound current relationship has an invalid type"
            )
        if (
            current.relationship_type_id,
            current.relationship_type_version,
        ) != physical_type:
            continue
        if required_roles and not required_roles <= set(current.role_bindings):
            continue
        displayed_endpoint = (
            current.source_endpoint
            if physical_direction == "forward"
            else current.target_endpoint
        )
        candidate_endpoint = (
            current.target_endpoint
            if physical_direction == "forward"
            else current.source_endpoint
        )
        if displayed_endpoint.canonical_identity_id != displayed_id:
            continue
        candidate_id = candidate_endpoint.canonical_identity_id
        if candidate_id is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship target is not canonical"
            )
        if (
            displayed_endpoint.endpoint_type != path.source_type
            or candidate_endpoint.endpoint_type != path.target_type
            or displayed_endpoint.stable_reference
            != f"canonical:{path.source_type}:{displayed_id}"
            or candidate_endpoint.stable_reference
            != f"canonical:{path.target_type}:{candidate_id}"
            or current.release_id != bundle.release_id
            or current.projected_at != relationship_result.as_of
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship endpoints are cross-wired"
            )
        candidate_projection = public_projections.get((path.target_type, candidate_id))
        if (
            candidate_projection is None
            or candidate_projection.release_id != bundle.release_id
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship target projection is absent"
            )

        outcome_matches = outcomes_by_relationship.get(
            current.canonical_relationship_id, []
        )
        if len(outcome_matches) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship outcome is missing or ambiguous"
            )
        outcome = outcome_matches[0]
        projection_candidate = projection_candidates.get(outcome.candidate_id)
        if (
            not isinstance(projection_candidate, RelationshipProjectionCandidate)
            or projection_candidate.assertion_input_id is None
            or projection_candidate.decision_input_id is None
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship candidate lineage is absent"
            )
        decision_input = decision_inputs.get(projection_candidate.decision_input_id)
        assertion_kind = projection_candidate.assertion_input_kind
        if assertion_kind == "typed_relationship_assertion":
            assertion = typed_assertions.get(projection_candidate.assertion_input_id)
            decision = typed_decisions.get(current.decision_id)
            assertion_source_record_id = (
                assertion.source_record_ref
                if isinstance(assertion, TypedRelationshipAssertionInput)
                else None
            )
            decision_endpoints_match = (
                isinstance(decision, TypedRelationshipDecision)
                and decision.source_endpoint == current.source_endpoint
                and decision.target_endpoint == current.target_endpoint
                and decision.selected_evidence_refs == current.selected_evidence_refs
            )
        elif assertion_kind == "shared_source_relationship_assertion":
            assertion = shared_assertions.get(projection_candidate.assertion_input_id)
            decision = shared_decisions.get(current.decision_id)
            assertion_source_record_id = (
                assertion.source_record_id
                if isinstance(assertion, RelationshipAssertion)
                else None
            )
            decision_endpoints_match = (
                isinstance(decision, RelationshipDecision)
                and decision.source_canonical_identity_id
                == current.source_endpoint.canonical_identity_id
                and decision.target_canonical_identity_id
                == current.target_endpoint.canonical_identity_id
            )
        else:
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship assertion kind is unsupported"
            )
        if assertion is None or decision is None or decision_input is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship assertion/decision is absent"
            )
        decision_state = getattr(decision.state, "value", decision.state)
        if (
            not outcome.admitted
            or outcome.reason_codes
            or outcome.decision_state != "accepted"
            or outcome.current_projection_state != "current"
            or outcome.current_projection_reason_codes
            or outcome.retained_assertion_id != assertion.assertion_id
            or outcome.decision_id != decision.decision_id
            or outcome.projected_relationship_id != current.canonical_relationship_id
            or outcome.selected_evidence_refs != current.selected_evidence_refs
            or outcome.source_canonical_identity_id
            != current.source_endpoint.canonical_identity_id
            or outcome.target_canonical_identity_id
            != current.target_endpoint.canonical_identity_id
            or projection_candidate.relationship_type_id != current.relationship_type_id
            or projection_candidate.relationship_type_version
            != current.relationship_type_version
            or projection_candidate.source_endpoint != current.source_endpoint
            or projection_candidate.target_endpoint != current.target_endpoint
            or projection_candidate.role_bindings != current.role_bindings
            or decision_input.decision_id != current.decision_id
            or decision_input.canonical_relationship_id
            != current.canonical_relationship_id
            or decision_state != "accepted"
            or decision.canonical_relationship_id != current.canonical_relationship_id
            or decision.relationship_type_id != current.relationship_type_id
            or decision.relationship_type_version != current.relationship_type_version
            or decision.role_bindings != current.role_bindings
            or decision.release_id != current.release_id
            or assertion.assertion_id not in decision.selected_assertion_ids
            or not decision_endpoints_match
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship lineage differs from current authority"
            )
        if not current.selected_evidence_refs:
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship retained evidence is absent"
            )
        retained = tuple(
            retained_references.get(reference_id)
            for reference_id in current.selected_evidence_refs
        )
        if any(reference is None for reference in retained) or any(
            reference.source_record_ref != assertion_source_record_id
            for reference in retained
            if reference is not None
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship retained source differs"
            )
        retained_ids = tuple(sorted(current.selected_evidence_refs))
        bound_reference_ids = tuple(
            sorted(
                {
                    reference
                    for binding in projection_candidate.evidence_bindings
                    for reference in binding.assertion_refs
                }
            )
        )
        if bound_reference_ids != retained_ids:
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound relationship evidence binding differs"
            )

        quality_flags = ()
        if enumeration.as_of > relationship_result.as_of:
            canonical_snapshot = (
                relationship_result.as_of.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            quality_flags = (f"relationship_snapshot_as_of:{canonical_snapshot}",)
        relationship_payload = candidate_projection.model_dump(mode="json")
        relationship_payload["_relationship"] = {
            "relationship_type": current.relationship_type_id,
            "roles": sorted(current.role_bindings),
            "source_id": current.source_endpoint.canonical_identity_id,
            "target_id": current.target_endpoint.canonical_identity_id,
        }
        snippet = json.dumps(
            relationship_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        display_name = _projection_terms(candidate_projection)[0]
        trace = LocalSourceRelationshipTrace(
            target_id=bundle.index_target.target_id,
            target_marker_sha256=bundle.index_target.marker_sha256,
            manifest_sha256=bundle.manifest.manifest_sha256,
            index_result_content_sha256=bundle.index_result.content_sha256,
            publication_verification_evidence_ids=tuple(
                sorted(publication.verification_evidence_ids)
            ),
            release_id=bundle.release_id,
            lane_request_content_sha256=request.content_sha256,
            relationship_enumeration_policy_sha256=relationship_enumeration_policy_sha256,
            displayed_entity_ids=displayed_ids,
            displayed_entity_id=displayed_id,
            protected_slot_id=protected_slot.slot_id,
            protected_slot_content_sha256=protected_slot_content_sha256,
            query_as_of=enumeration.as_of,
            query_relationship_type_id=path.relationship_type_id,
            query_direction=path.direction,
            query_source_type=cast(PublicDomain, path.source_type),
            query_target_type=cast(PublicDomain, path.target_type),
            relationship_request_sha256=authority.relationship_request_content_sha256,
            relationship_result_sha256=relationship_result.content_sha256,
            relationship_snapshot_as_of=relationship_result.as_of,
            canonical_relationship_id=current.canonical_relationship_id,
            current_relationship_content_sha256=_canonical_sha256(
                current.model_dump(mode="json")
            ),
            relationship_type_id=current.relationship_type_id,
            relationship_type_version="canonical-v2-relationship-v1",
            physical_direction=physical_direction,
            physical_source_id=current.source_endpoint.canonical_identity_id or "",
            physical_source_type=cast(
                PublicDomain, current.source_endpoint.endpoint_type
            ),
            physical_target_id=current.target_endpoint.canonical_identity_id or "",
            physical_target_type=cast(
                PublicDomain, current.target_endpoint.endpoint_type
            ),
            relationship_role_bindings=tuple(sorted(current.role_bindings.items())),
            selected_evidence_refs=retained_ids,
            projection_candidate_id=projection_candidate.candidate_id,
            projection_candidate_content_sha256=_canonical_sha256(
                projection_candidate.model_dump(mode="json")
            ),
            assertion_kind=assertion_kind,
            assertion_id=assertion.assertion_id,
            assertion_content_sha256=_canonical_sha256(
                assertion.model_dump(mode="json")
            ),
            source_record_id=assertion_source_record_id or "",
            relationship_decision_id=decision.decision_id,
            relationship_decision_content_sha256=_canonical_sha256(
                decision.model_dump(mode="json")
            ),
            candidate_outcome_content_sha256=_canonical_sha256(
                outcome.model_dump(mode="json")
            ),
            candidate_canonical_id=candidate_id,
            candidate_domain=cast(PublicDomain, path.target_type),
            candidate_display_name=display_name,
            candidate_projection_content_sha256=candidate_projection.content_sha256,
            candidate_origin_public_evidence_ids=(assertion.assertion_id,),
            candidate_quality_flags=quality_flags,
            claim_subject_id=f"canonical:{path.source_type}:{displayed_id}",
            claim_predicate=current.relationship_type_id,
            claim_value=f"canonical:{path.target_type}:{candidate_id}",
            snippet_sha256=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
        )
        evidence = EvidenceItem(
            evidence_id=trace.evidence_id,
            object_id=candidate_id,
            domain=path.target_type,
            lane="relationship",
            source_nature="local",
            source_locator=_local_projection_locator(trace),
            snippet=snippet,
            score=1.0,
            source_authority="canonical_release",
            observed_at=relationship_result.as_of,
            claim_binding=EvidenceClaimBinding(
                subject_id=trace.claim_subject_id,
                predicate=trace.claim_predicate,
                value=trace.claim_value,
                status="accepted",
            ),
            local_projection_trace=trace,
        )
        candidates.append(
            RecallCandidate(
                raw_candidate_id=trace.raw_candidate_id,
                display_name=display_name,
                domain=path.target_type,
                identity_kind="canonical",
                canonical_id=candidate_id,
                reference_type=None,
                resolution_state="resolved",
                relationship_state="accepted",
                origin_public_evidence_ids=trace.candidate_origin_public_evidence_ids,
                query_view=request.query_view,
                lane="relationship",
                attempt=1,
                release_id=bundle.release_id,
                adapter_version=_RELATIONSHIP_ADAPTER_VERSION,
                raw_score=1.0,
                quality_flags=quality_flags,
                evidence=(evidence,),
            )
        )

    candidates.sort(
        key=lambda candidate: (candidate.domain, candidate.canonical_id or "")
    )
    return tuple(candidates[: request.max_candidates])


def _relationship_result_candidates(
    *,
    request: LaneRequest,
    authority: _RelationshipAuthority,
) -> tuple[RecallCandidate, ...]:
    validated_request = _validate_relationship_request(request, authority)
    if validated_request.max_candidates == 0:
        return ()
    path = validated_request.relationship_paths[0]
    path_key = (
        path.relationship_type_id,
        path.direction,
        path.source_type,
        path.target_type,
    )
    has_relationship_scoped_eligibility = any(
        result.relationship_decision_ids
        for result in authority.internal_authority.index_request.public_path_eligibility_results
    )
    if path_key in _SOURCE_BOUND_RELATIONSHIP_PATHS and (
        path_key
        in {
            _PROFESSOR_TO_COMPANY_QUERY_PATH,
            _COMPANY_TO_PROFESSOR_QUERY_PATH,
        }
        or not has_relationship_scoped_eligibility
    ):
        return _source_bound_relationship_candidates(
            request=validated_request,
            authority=authority,
        )
    if path_key == _COMPANY_TO_PATENT_QUERY_PATH:
        return _company_to_patent_relationship_candidates(
            request=validated_request,
            authority=authority,
        )
    if path_key == _PATENT_TO_COMPANY_QUERY_PATH:
        return _patent_to_company_relationship_candidates(
            request=validated_request,
            authority=authority,
        )
    if path_key == _PROFESSOR_TO_PAPER_QUERY_PATH:
        return _professor_to_paper_relationship_candidates(
            request=validated_request,
            authority=authority,
        )
    if path_key == _PAPER_TO_PROFESSOR_QUERY_PATH:
        return _paper_to_professor_relationship_candidates(
            request=validated_request,
            authority=authority,
        )

    internal_authority = authority.internal_authority
    bundle = internal_authority.bundle
    publication = internal_authority.publication
    relationship_request = authority.relationship_request
    relationship_result = authority.relationship_result
    candidate_result = authority.candidate_result
    query = validated_request.relationship_reference_queries[0]
    query_as_of = query.as_of
    if query_as_of is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship query requires an as_of boundary"
        )
    route_id = query.canonical_route_ids[0]
    route_matches = tuple(
        route
        for route in candidate_result.technology_route_projections
        if route.canonical_technology_identity_id == route_id
    )
    if len(route_matches) != 1:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship route projection is missing or duplicated"
        )
    route = route_matches[0]
    if route.release_id != bundle.release_id or route.as_of != candidate_result.as_of:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship route projection differs from query authority"
        )

    internal_result = relationship_request.internal_reference_projection_result
    internal_request = relationship_request.internal_reference_projection_request
    if internal_result is None or internal_request is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship authority lost its internal projection pair"
        )
    route_anchor_ids = set(route.source_anchor_ids)
    route_anchors = tuple(
        anchor
        for anchor in internal_result.technology_evidence_anchors
        if anchor.anchor_id in route_anchor_ids
    )
    if (
        len(route_anchors) != len(route.source_anchor_ids)
        or {anchor.anchor_id for anchor in route_anchors} != route_anchor_ids
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship route source anchors differ from accepted projection"
        )
    public_request = internal_request.public_domain_projection_request
    source_assertions = {
        assertion.assertion_id: assertion
        for assertion in public_request.source_assertions
    }
    if len(source_assertions) != len(public_request.source_assertions):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship public assertion authority is duplicated"
        )
    retained_references = {
        retained.reference_id: retained
        for retained in relationship_request.retained_assertions
    }
    if len(retained_references) != len(relationship_request.retained_assertions):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship retained reference authority is duplicated"
        )
    relationship_types = {
        (item.relationship_type_id, item.version): item
        for item in relationship_result.relationship_types
    }
    if len(relationship_types) != len(relationship_result.relationship_types):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship type authority is duplicated"
        )
    decisions = {
        decision.decision_id: decision
        for decision in relationship_result.typed_relationship_decisions
    }
    if len(decisions) != len(relationship_result.typed_relationship_decisions):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship decision authority is duplicated"
        )
    outcomes_by_relationship: defaultdict[str, list[Any]] = defaultdict(list)
    for outcome in relationship_result.candidate_outcomes:
        if outcome.projected_relationship_id is not None:
            outcomes_by_relationship[outcome.projected_relationship_id].append(outcome)
    public_projections = {
        (projection.entity_type, projection.canonical_identity_id): projection
        for projection in candidate_result.public_domain_projections
    }
    if len(public_projections) != len(candidate_result.public_domain_projections):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship public projection authority is duplicated"
        )
    path_results = {
        result.subject_identity_id: result
        for result in internal_authority.index_request.public_path_eligibility_results
    }
    if len(path_results) != len(
        internal_authority.index_request.public_path_eligibility_results
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship path eligibility authority is duplicated"
        )

    candidates: list[RecallCandidate] = []
    for current in relationship_result.current_relationships:
        if not isinstance(current, CurrentRelationshipProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship current projection has an invalid type"
            )
        state = _TECHNOLOGY_RELATIONSHIP_STATES.get(current.relationship_type_id)
        if state is None or state not in query.relationship_states:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship state is outside the exact Technology state set"
            )
        relationship_type = relationship_types.get(
            (current.relationship_type_id, current.relationship_type_version)
        )
        if (
            relationship_type is None
            or "product" not in relationship_type.source_entity_types
            or "technology_route" not in relationship_type.target_entity_types
            or "relationship_traversal" not in relationship_type.eligible_paths
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship type/version/path is not registered for traversal"
            )
        outcome_matches = outcomes_by_relationship.get(
            current.canonical_relationship_id,
            [],
        )
        if len(outcome_matches) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship candidate outcome is missing or ambiguous"
            )
        outcome = outcome_matches[0]
        decision = decisions.get(current.decision_id)
        if (
            decision is None
            or not outcome.admitted
            or outcome.decision_state != "accepted"
            or outcome.current_projection_state != "current"
            or outcome.reason_codes
            or outcome.current_projection_reason_codes
            or outcome.decision_id != current.decision_id
            or outcome.relationship_type_id != current.relationship_type_id
            or outcome.relationship_type_version != current.relationship_type_version
            or outcome.selected_evidence_refs != current.selected_evidence_refs
            or outcome.source_reference_kind != "typed_subobject"
            or outcome.target_reference_kind != "canonical_identity"
            or outcome.source_canonical_identity_id is not None
            or outcome.target_canonical_identity_id != route_id
            or outcome.source_parent_canonical_identity_ref
            != current.source_endpoint.parent_canonical_identity_ref
            or outcome.target_parent_canonical_identity_ref is not None
            or outcome.effective_time_semantics != current.effective_time_semantics
            or decision.state != "accepted"
            or decision.canonical_relationship_id != current.canonical_relationship_id
            or decision.relationship_type_id != current.relationship_type_id
            or decision.relationship_type_version != current.relationship_type_version
            or decision.source_endpoint != current.source_endpoint
            or decision.target_endpoint != current.target_endpoint
            or decision.role_bindings != current.role_bindings
            or decision.selected_evidence_refs != current.selected_evidence_refs
            or decision.valid_from != current.valid_from
            or decision.valid_to != current.valid_to
            or decision.release_id != current.release_id
            or current.release_id != bundle.release_id
            or current.projected_at != relationship_result.as_of
            or outcome.retained_assertion_id not in decision.selected_assertion_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship outcome/decision/current projection differs"
            )
        if len(current.selected_evidence_refs) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship current projection requires one retained reference"
            )
        retained = retained_references.get(current.selected_evidence_refs[0])
        if retained is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship selected retained reference is absent"
            )
        source_assertion = source_assertions.get(retained.assertion_id)
        if not isinstance(source_assertion, SourceAssertion):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship retained public assertion is absent"
            )
        assertion_value = source_assertion.value
        if not isinstance(assertion_value, dict):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship public assertion value is not typed"
            )
        if (
            source_assertion.source_record_id != retained.source_record_ref
            or source_assertion.subject_entity_type != "company"
            or source_assertion.field_path
            != _TECHNOLOGY_RELATIONSHIP_SOURCE_FIELDS[state]
            or source_assertion.valid_from != current.valid_from
            or source_assertion.valid_to != current.valid_to
            or assertion_value.get("technology_source_identity_id")
            not in route.source_identity_ids
            or assertion_value.get("source_subobject_type") != "product"
            or assertion_value.get("source_subobject_id")
            != current.source_endpoint.stable_reference
            or assertion_value.get("term") not in (route.preferred_name, *route.aliases)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship public assertion differs from Product/route evidence"
            )
        matching_anchors = tuple(
            anchor
            for anchor in route_anchors
            if anchor.reference_type == "technology_route"
            and anchor.technology_source_identity_id
            == assertion_value.get("technology_source_identity_id")
            and anchor.root_canonical_identity_id
            == assertion_value.get("root_canonical_identity_id")
            and anchor.source_subobject_type == "product"
            and anchor.source_subobject_id == assertion_value.get("source_subobject_id")
            and retained.source_record_ref in anchor.source_record_ids
        )
        if len(matching_anchors) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship route anchor is missing or ambiguous"
            )
        anchor = matching_anchors[0]
        root_company_id = anchor.root_canonical_identity_id
        company = public_projections.get(("company", root_company_id))
        if not isinstance(company, CompanyProjection):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship root Company projection is absent"
            )
        product_matches = tuple(
            product
            for product in company.products
            if product.subobject_id == anchor.source_subobject_id
        )
        if len(product_matches) != 1 or not isinstance(
            product_matches[0], CompanyProduct
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship Product subobject is missing or ambiguous"
            )
        product = product_matches[0]
        expected_parent_ref = f"canonical:company:{root_company_id}"
        expected_route_ref = f"canonical:technology_route:{route_id}"
        if (
            assertion_value.get("root_canonical_identity_id") != root_company_id
            or product.parent_canonical_identity_id != root_company_id
            or product.projection_content_sha256
            != anchor.source_subobject_content_sha256
            or company.release_id != bundle.release_id
            or company.content_sha256 != anchor.root_projection_content_sha256
            or current.source_endpoint.endpoint_type != "product"
            or current.source_endpoint.stable_reference != product.subobject_id
            or current.source_endpoint.parent_canonical_identity_ref
            != expected_parent_ref
            or current.target_endpoint.endpoint_type != "technology_route"
            or current.target_endpoint.stable_reference != expected_route_ref
            or current.target_endpoint.canonical_identity_id != route_id
            or current.role_bindings != {"technology": expected_route_ref}
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship endpoint/Product/Company identity is cross-wired"
            )

        path_result = path_results.get(root_company_id)
        if (
            path_result is None
            or path_result.release_id != bundle.release_id
            or path_result.projection_id != f"typed:company:{root_company_id}"
            or path_result.resolved_projection_id != f"typed:company:{root_company_id}"
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship Company path result differs from authority"
            )
        eligibility_matches = tuple(
            decision
            for decision in path_result.decisions
            if decision.path == "verified_relationship_traversal"
        )
        if len(eligibility_matches) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship Company eligibility decision is missing or ambiguous"
            )
        eligibility = eligibility_matches[0]
        if eligibility.outcome is PolicyOutcome.excluded:
            continue
        if eligibility.outcome is PolicyOutcome.admitted:
            eligibility_outcome: Literal["admitted", "limited"] = "admitted"
        elif eligibility.outcome is PolicyOutcome.limited:
            eligibility_outcome = "limited"
        else:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship Company eligibility outcome is not returnable"
            )
        quality_flags = tuple(eligibility.limitations)
        if query_as_of > relationship_result.as_of:
            canonical_snapshot = (
                relationship_result.as_of.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            quality_flags = (
                *quality_flags,
                f"relationship_snapshot_as_of:{canonical_snapshot}",
            )
        snippet = json.dumps(
            source_assertion.value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        trace = LocalRelationshipTrace(
            target_id=bundle.index_target.target_id,
            target_marker_sha256=bundle.index_target.marker_sha256,
            manifest_sha256=bundle.manifest.manifest_sha256,
            index_result_content_sha256=bundle.index_result.content_sha256,
            publication_verification_evidence_ids=tuple(
                sorted(publication.verification_evidence_ids)
            ),
            release_id=bundle.release_id,
            lane_request_content_sha256=validated_request.content_sha256,
            relationship_request_sha256=authority.relationship_request_content_sha256,
            relationship_result_sha256=relationship_result.content_sha256,
            relationship_projection_run_id=relationship_result.projection_run_id,
            relationship_projection_schema_version=(
                relationship_result.projection_schema_version
            ),
            relationship_registry_version=(
                relationship_result.relationship_registry_version
            ),
            relationship_registry_content_sha256=(
                relationship_result.relationship_registry_content_sha256
            ),
            relationship_snapshot_as_of=relationship_result.as_of,
            query_as_of=query_as_of,
            technology_route_id=route_id,
            technology_route_projection_id=(route.canonical_technology_identity_id),
            technology_route_projection_content_sha256=route.content_sha256,
            canonical_relationship_id=current.canonical_relationship_id,
            current_relationship_content_sha256=_canonical_sha256(
                current.model_dump(mode="json")
            ),
            relationship_decision_id=decision.decision_id,
            relationship_decision_content_sha256=_canonical_sha256(
                decision.model_dump(mode="json")
            ),
            relationship_type_id=current.relationship_type_id,
            relationship_type_version=current.relationship_type_version,
            relationship_source_endpoint=current.source_endpoint.stable_reference,
            relationship_source_endpoint_content_sha256=_canonical_sha256(
                current.source_endpoint.model_dump(mode="json")
            ),
            relationship_source_parent_canonical_identity_ref=expected_parent_ref,
            relationship_target_endpoint=current.target_endpoint.stable_reference,
            relationship_target_endpoint_content_sha256=_canonical_sha256(
                current.target_endpoint.model_dump(mode="json")
            ),
            relationship_role_bindings=tuple(sorted(current.role_bindings.items())),
            selected_evidence_refs=tuple(sorted(current.selected_evidence_refs)),
            relationship_valid_from=(
                current.valid_from.model_dump(mode="json")
                if current.valid_from is not None
                else None
            ),
            relationship_valid_to=(
                current.valid_to.model_dump(mode="json")
                if current.valid_to is not None
                else None
            ),
            relationship_state=state,
            retained_reference_id=retained.reference_id,
            retained_reference_content_sha256=_canonical_sha256(
                retained.model_dump(mode="json")
            ),
            retained_assertion_id=retained.assertion_id,
            retained_source_record_id=retained.source_record_ref,
            public_assertion_id=source_assertion.assertion_id,
            public_assertion_content_sha256=_canonical_sha256(
                source_assertion.model_dump(mode="json")
            ),
            source_record_id=source_assertion.source_record_id,
            technology_anchor_id=anchor.anchor_id,
            technology_anchor_content_sha256=anchor.content_sha256,
            technology_anchor_source_identity_id=(anchor.technology_source_identity_id),
            product_subobject_id=product.subobject_id,
            product_subobject_content_sha256=product.projection_content_sha256,
            root_company_id=root_company_id,
            root_company_projection_content_sha256=company.content_sha256,
            root_company_display_name=company.name,
            path_eligibility_result_content_sha256=path_result.content_sha256,
            eligibility_decision_id=eligibility.decision_id,
            eligibility_policy_id=eligibility.policy.policy_id,
            eligibility_policy_version=eligibility.policy.policy_version,
            eligibility_policy_content_sha256=eligibility.policy.content_sha256,
            eligibility_policy_effective_at=eligibility.policy.effective_at,
            eligibility_outcome=eligibility_outcome,
            eligibility_limitations=tuple(sorted(eligibility.limitations)),
            eligibility_hard_exclusion_codes=tuple(
                sorted(eligibility.hard_exclusion_codes)
            ),
            eligibility_supporting_assertion_ids=tuple(
                sorted(eligibility.supporting_assertion_ids)
            ),
            claim_subject_id=product.subobject_id,
            claim_predicate=current.relationship_type_id,
            claim_value=expected_route_ref,
            claim_status=state,
            snippet_sha256=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
        )
        evidence = EvidenceItem(
            evidence_id=trace.evidence_id,
            object_id=root_company_id,
            domain="company",
            lane="relationship",
            source_nature="local",
            source_locator=_local_projection_locator(trace),
            snippet=snippet,
            score=1.0,
            source_authority="canonical_release",
            observed_at=relationship_result.as_of,
            claim_binding=EvidenceClaimBinding(
                subject_id=product.subobject_id,
                predicate=current.relationship_type_id,
                value=expected_route_ref,
                status=state,
            ),
            local_projection_trace=trace,
        )
        candidates.append(
            RecallCandidate(
                raw_candidate_id=trace.raw_candidate_id,
                display_name=company.name,
                domain="company",
                identity_kind="canonical",
                canonical_id=root_company_id,
                reference_type="technology_route",
                resolution_state="resolved",
                relationship_state=state,
                origin_public_evidence_ids=(anchor.anchor_id,),
                query_view=validated_request.query_view,
                lane="relationship",
                attempt=1,
                release_id=bundle.release_id,
                adapter_version=_RELATIONSHIP_ADAPTER_VERSION,
                raw_score=1.0,
                quality_flags=quality_flags,
                evidence=(evidence,),
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.relationship_state or "",
            candidate.evidence[0].claim_binding.predicate
            if candidate.evidence[0].claim_binding is not None
            else "",
            cast_trace.canonical_relationship_id
            if isinstance(
                cast_trace := candidate.evidence[0].local_projection_trace,
                LocalRelationshipTrace,
            )
            else "",
        )
    )
    return tuple(candidates[: validated_request.max_candidates])


def _build_relationship_result(
    *,
    request: LaneRequest,
    authority: _RelationshipAuthority,
) -> RetrievalLaneResult:
    return RetrievalLaneResult(
        candidates=_relationship_result_candidates(
            request=request,
            authority=authority,
        )
    )


def create_isolated_relationship_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    index_projection_request: IndexProjectionRequest,
    release_institution_catalog: InstitutionCatalog,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    """Replay one release-owned canonical relationship graph entirely in memory."""

    authority = _replay_relationship_authority(
        release_bundle=release_bundle,
        published_release=published_release,
        index_projection_request=index_projection_request,
        release_institution_catalog=release_institution_catalog,
    )

    def relationship_lookup(request: LaneRequest) -> RetrievalLaneResult:
        return _build_relationship_result(request=request, authority=authority)

    return relationship_lookup


def _validate_release_bound_relationship_evidence(
    *,
    plan: RetrievalPlan,
    evidence_set: EvidenceSet,
    authority: _RelationshipAuthority,
) -> None:
    request = _lane_request(plan, "relationship", plan.web_policy)
    if (
        evidence_set.release_id != plan.release_id
        or evidence_set.original_query != plan.original_query
        or evidence_set.protected_slots != plan.protected_slots
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship evidence envelope differs from the plan"
        )
    expected = _build_relationship_result(request=request, authority=authority)
    expected_candidates = expected.candidates
    expected_by_raw = {
        candidate.raw_candidate_id: candidate for candidate in expected_candidates
    }
    if len(expected_by_raw) != len(expected_candidates):
        raise IsolatedKnowledgeReadIntegrityError(
            "expected relationship candidate identity is duplicated"
        )
    expected_items = {
        item.evidence_id: item
        for candidate in expected_candidates
        for item in candidate.evidence
    }
    if len(expected_items) != sum(
        len(candidate.evidence) for candidate in expected_candidates
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "expected relationship evidence identity is duplicated"
        )
    expected_raw_ids = set(expected_by_raw)
    expected_evidence_ids = set(expected_items)
    observed_constraint_fused = tuple(
        candidate
        for candidate in evidence_set.fused_candidates
        if set(candidate.raw_candidate_ids) & expected_raw_ids
        or set(candidate.evidence_ids) & expected_evidence_ids
    )
    (
        _,
        expected_constraint_receipts,
        expected_constraint_rejected,
    ) = _apply_constraints(observed_constraint_fused, plan.protected_slots)
    expected_selected_items = {
        item.evidence_id: item
        for candidate in expected_candidates
        if candidate.raw_candidate_id not in expected_constraint_rejected
        for item in candidate.evidence
    }

    all_observed_items = (
        *evidence_set.items,
        *(
            item
            for candidate in evidence_set.fused_candidates
            for item in candidate.evidence
        ),
    )
    path = (
        request.relationship_paths[0] if len(request.relationship_paths) == 1 else None
    )
    is_company_to_patent = (
        path is not None
        and (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
        == _COMPANY_TO_PATENT_QUERY_PATH
    )
    is_patent_to_company = (
        path is not None
        and (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
        == _PATENT_TO_COMPANY_QUERY_PATH
    )
    is_professor_to_paper = (
        path is not None
        and (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
        == _PROFESSOR_TO_PAPER_QUERY_PATH
    )
    is_paper_to_professor = (
        path is not None
        and (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
        == _PAPER_TO_PROFESSOR_QUERY_PATH
    )
    is_professor_to_company = (
        path is not None
        and (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
        == _PROFESSOR_TO_COMPANY_QUERY_PATH
    )
    is_company_to_professor = (
        path is not None
        and (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
        == _COMPANY_TO_PROFESSOR_QUERY_PATH
    )
    public_relationship_trace_types = (
        LocalRelationshipTrace,
        LocalCanonicalRelationshipTrace,
        LocalPatentCompanyRelationshipTrace,
        LocalProfessorPaperRelationshipTrace,
        LocalPaperProfessorRelationshipTrace,
        LocalSourceRelationshipTrace,
    )
    is_source_bound_public_path = any(
        (
            item.local_projection_trace is not None
            and isinstance(
                item.local_projection_trace,
                LocalSourceRelationshipTrace,
            )
        )
        for item in all_observed_items
    )
    if is_source_bound_public_path and path is not None:
        displayed_ids = set(request.structured_constraints.displayed_entity_ids)
        if (
            any(
                item.domain != path.target_type or item.object_id in displayed_ids
                for item in all_observed_items
            )
            or any(
                candidate.domain != path.target_type
                or candidate.canonical_id in displayed_ids
                for candidate in evidence_set.fused_candidates
            )
            or any(
                handle.domain != path.target_type
                for handle in evidence_set.entity_handles
            )
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "source-bound Web evidence cannot satisfy displayed relationship authority"
            )
    if is_company_to_patent:
        displayed_company_ids = set(request.structured_constraints.displayed_entity_ids)
        if (
            any(
                item.domain != "patent" or item.object_id in displayed_company_ids
                for item in all_observed_items
            )
            or any(
                candidate.domain != "patent"
                or candidate.canonical_id in displayed_company_ids
                for candidate in evidence_set.fused_candidates
            )
            or any(handle.domain != "patent" for handle in evidence_set.entity_handles)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "S8R2 Web source witness must not satisfy displayed Company authority"
            )
    if is_patent_to_company:
        displayed_patent_ids = set(request.structured_constraints.displayed_entity_ids)
        if (
            any(
                item.domain != "company" or item.object_id in displayed_patent_ids
                for item in all_observed_items
            )
            or any(
                candidate.domain != "company"
                or candidate.canonical_id in displayed_patent_ids
                for candidate in evidence_set.fused_candidates
            )
            or any(handle.domain != "company" for handle in evidence_set.entity_handles)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "S8R5 Web source witness must not satisfy displayed Patent authority"
            )
        if any(
            item.claim_binding is not None
            and item.claim_binding.predicate == "patent_has_applicant"
            and not (
                item.lane == "relationship"
                and item.source_nature == "local"
                and isinstance(
                    item.local_projection_trace,
                    (
                        LocalPatentCompanyRelationshipTrace,
                        LocalSourceRelationshipTrace,
                    ),
                )
            )
            for item in all_observed_items
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "S8R5 non-local evidence cannot assert a Patent-applicant relationship"
            )
        for candidate in evidence_set.fused_candidates:
            inverse_traces = tuple(
                item.local_projection_trace
                for item in candidate.evidence
                if isinstance(
                    item.local_projection_trace,
                    LocalPatentCompanyRelationshipTrace,
                )
            )
            if not inverse_traces:
                continue
            returned_company_ids = {trace.company_id for trace in inverse_traces}
            if len(returned_company_ids) != 1:
                raise IsolatedKnowledgeReadIntegrityError(
                    "S8R5 fused Company authority is ambiguous"
                )
            returned_company_id = next(iter(returned_company_ids))
            returned_company_ref = f"canonical:company:{returned_company_id}"
            if candidate.canonical_id != returned_company_id:
                raise IsolatedKnowledgeReadIntegrityError(
                    "S8R5 fused Company identity differs from canonical authority"
                )
            for item in candidate.evidence:
                if item.source_nature == "local":
                    continue
                if item.domain != "company":
                    raise IsolatedKnowledgeReadIntegrityError(
                        "S8R5 Web Company evidence domain differs from canonical authority"
                    )
                if (
                    item.claim_binding is not None
                    and item.claim_binding.subject_id
                    not in {returned_company_ref, item.object_id}
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "S8R5 Web Company claim subject differs from canonical authority"
                    )
    if is_professor_to_paper:
        displayed_professor_ids = set(
            request.structured_constraints.displayed_entity_ids
        )
        if (
            any(
                item.domain != "paper" or item.object_id in displayed_professor_ids
                for item in all_observed_items
            )
            or any(
                candidate.domain != "paper"
                or candidate.canonical_id in displayed_professor_ids
                for candidate in evidence_set.fused_candidates
            )
            or any(handle.domain != "paper" for handle in evidence_set.entity_handles)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "S8R3 Web source witness must not satisfy displayed Professor authority"
            )
        if any(
            item.claim_binding is not None
            and item.claim_binding.predicate in _PROFESSOR_PAPER_RELATIONSHIP_PREDICATES
            and not (
                item.lane == "relationship"
                and item.source_nature == "local"
                and isinstance(
                    item.local_projection_trace,
                    (
                        LocalProfessorPaperRelationshipTrace,
                        LocalSourceRelationshipTrace,
                    ),
                )
            )
            for item in all_observed_items
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "S8R3 non-local evidence cannot assert a Professor-Paper relationship"
            )
    if is_paper_to_professor:
        displayed_paper_ids = set(request.structured_constraints.displayed_entity_ids)
        if (
            any(
                item.domain != "professor" or item.object_id in displayed_paper_ids
                for item in all_observed_items
            )
            or any(
                candidate.domain != "professor"
                or candidate.canonical_id in displayed_paper_ids
                for candidate in evidence_set.fused_candidates
            )
            or any(
                handle.domain != "professor" for handle in evidence_set.entity_handles
            )
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "S8R4 Web source witness must not satisfy displayed Paper authority"
            )
        if any(
            item.claim_binding is not None
            and item.claim_binding.predicate in _PROFESSOR_PAPER_RELATIONSHIP_PREDICATES
            and not (
                item.lane == "relationship"
                and item.source_nature == "local"
                and isinstance(
                    item.local_projection_trace,
                    (
                        LocalPaperProfessorRelationshipTrace,
                        LocalSourceRelationshipTrace,
                    ),
                )
            )
            for item in all_observed_items
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "S8R4 non-local evidence cannot assert a Professor-Paper relationship"
            )
        for candidate in evidence_set.fused_candidates:
            inverse_traces = tuple(
                item.local_projection_trace
                for item in candidate.evidence
                if isinstance(
                    item.local_projection_trace,
                    LocalPaperProfessorRelationshipTrace,
                )
            )
            if not inverse_traces:
                continue
            returned_professor_ids = {trace.professor_id for trace in inverse_traces}
            if len(returned_professor_ids) != 1:
                raise IsolatedKnowledgeReadIntegrityError(
                    "S8R4 fused Professor authority is ambiguous"
                )
            returned_professor_id = next(iter(returned_professor_ids))
            returned_professor_ref = f"canonical:professor:{returned_professor_id}"
            if candidate.canonical_id != returned_professor_id:
                raise IsolatedKnowledgeReadIntegrityError(
                    "S8R4 fused Professor identity differs from canonical authority"
                )
            for item in candidate.evidence:
                if item.source_nature == "local":
                    continue
                if item.domain != "professor":
                    raise IsolatedKnowledgeReadIntegrityError(
                        "S8R4 Web Professor evidence domain differs from canonical authority"
                    )
                if (
                    item.claim_binding is not None
                    and item.claim_binding.subject_id
                    not in {returned_professor_ref, item.object_id}
                ):
                    raise IsolatedKnowledgeReadIntegrityError(
                        "S8R4 Web Professor claim subject differs from canonical authority"
                    )
    if is_professor_to_company or is_company_to_professor:
        if any(
            item.claim_binding is not None
            and item.claim_binding.predicate == "professor_company_role"
            and not (
                item.lane == "relationship"
                and item.source_nature == "local"
                and isinstance(
                    item.local_projection_trace,
                    LocalSourceRelationshipTrace,
                )
            )
            for item in all_observed_items
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "non-local evidence cannot assert a Professor-Company relationship"
            )

    top_level_relationship_items = tuple(
        item
        for item in evidence_set.items
        if item.evidence_id in expected_items
        or item.lane == "relationship"
        or isinstance(
            item.local_projection_trace,
            public_relationship_trace_types,
        )
    )
    if len({item.evidence_id for item in top_level_relationship_items}) != len(
        top_level_relationship_items
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship top-level evidence identity is duplicated"
        )
    if {
        item.evidence_id: item for item in top_level_relationship_items
    } != expected_selected_items:
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship top-level evidence differs from replay authority"
        )
    if any(
        item.claim_binding is not None
        and item.claim_binding.predicate == "product_has_capability"
        for item in all_observed_items
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship release output contains a Product-capability claim"
        )
    observed_items: dict[str, EvidenceItem] = {}
    for item in all_observed_items:
        trace = item.local_projection_trace
        if (
            item.evidence_id not in expected_items
            and item.lane != "relationship"
            and not isinstance(
                trace,
                public_relationship_trace_types,
            )
        ):
            continue
        previous = observed_items.get(item.evidence_id)
        if previous is not None and previous != item:
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound relationship evidence identity is inconsistent"
            )
        observed_items[item.evidence_id] = item
    if observed_items != expected_items:
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship evidence differs from replay authority"
        )

    lane_traces = tuple(
        trace for trace in evidence_set.traces if trace.lane == "relationship"
    )
    if (
        len(lane_traces) != 1
        or lane_traces[0].query_view != request.query_view
        or lane_traces[0].attempt != 1
        or lane_traces[0].release_id != request.release_id
        or lane_traces[0].status != "succeeded"
        or lane_traces[0].failure_kind is not None
        or lane_traces[0].candidate_count != len(expected_candidates)
        or lane_traces[0].source_scope is not None
        or lane_traces[0].phase != "initial"
        or lane_traces[0].material_part_ids
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship lane did not reproduce its authority"
        )

    candidate_traces = tuple(
        trace
        for trace in evidence_set.candidate_traces
        if trace.raw_candidate_id in expected_by_raw or trace.lane == "relationship"
    )
    if len({trace.raw_candidate_id for trace in candidate_traces}) != len(
        candidate_traces
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship candidate trace identity is duplicated"
        )
    if {trace.raw_candidate_id for trace in candidate_traces} != set(expected_by_raw):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship candidate trace set differs"
        )
    for trace in candidate_traces:
        expected_candidate = expected_by_raw[trace.raw_candidate_id]
        constraint_rejected = trace.raw_candidate_id in expected_constraint_rejected
        expected_disposition = (
            "hard_constraint_rejected" if constraint_rejected else "selected"
        )
        expected_selected_result_id = (
            None if constraint_rejected else expected_candidate.canonical_id
        )
        if (
            trace.query_view != expected_candidate.query_view
            or trace.lane != expected_candidate.lane
            or trace.attempt != expected_candidate.attempt
            or trace.release_id != expected_candidate.release_id
            or trace.adapter_version != expected_candidate.adapter_version
            or trace.provider_version != expected_candidate.provider_version
            or trace.raw_score != expected_candidate.raw_score
            or trace.evidence_ids
            != tuple(item.evidence_id for item in expected_candidate.evidence)
            or trace.disposition != expected_disposition
            or trace.selected_result_id != expected_selected_result_id
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound relationship candidate disposition differs"
            )

    observed_relationship_constraint_receipts = tuple(
        receipt
        for receipt in evidence_set.constraint_receipts
        if set(receipt.raw_candidate_ids) & expected_raw_ids
    )
    if observed_relationship_constraint_receipts != expected_constraint_receipts:
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship constraint receipts differ"
        )

    expected_auxiliary = {
        candidate.raw_candidate_id: (
            candidate.reference_type,
            candidate.origin_public_evidence_ids,
            candidate.relationship_state,
        )
        for candidate in expected_candidates
        if candidate.reference_type in {"person", "technology_route"}
    }
    if (
        path is not None
        and (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
        in _PUBLIC_RELATIONSHIP_QUERY_PATHS
        and evidence_set.auxiliary_traces
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "canonical relationship output contains an auxiliary trace"
        )
    relevant_auxiliary = tuple(
        trace
        for trace in evidence_set.auxiliary_traces
        if trace.raw_candidate_id in expected_auxiliary
        or (
            trace.reference_type == "technology_route"
            and trace.relationship_state is not None
        )
    )
    if len({trace.raw_candidate_id for trace in relevant_auxiliary}) != len(
        relevant_auxiliary
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship auxiliary trace identity is duplicated"
        )
    observed_auxiliary = {trace.raw_candidate_id: trace for trace in relevant_auxiliary}
    if set(observed_auxiliary) != set(expected_auxiliary):
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound relationship auxiliary trace set differs"
        )
    for raw_id, trace in observed_auxiliary.items():
        reference_type, anchor_ids, state = expected_auxiliary[raw_id]
        if (
            trace.reference_type != reference_type
            or trace.origin_public_evidence_ids != anchor_ids
            or trace.relationship_state != state
            or trace.public_population
            or not trace.eligible
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound relationship auxiliary trace differs"
            )

    grouped: defaultdict[tuple[str, str], list[RecallCandidate]] = defaultdict(list)
    for candidate in expected_candidates:
        if candidate.canonical_id is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship candidate lacks its Company locator"
            )
        grouped[(candidate.domain, candidate.canonical_id)].append(candidate)

    relationship_fused_indices = {
        index
        for index, candidate in enumerate(evidence_set.fused_candidates)
        if set(candidate.raw_candidate_ids) & expected_raw_ids
        or set(candidate.evidence_ids) & expected_evidence_ids
        or any(
            item.evidence_id in expected_evidence_ids
            or isinstance(
                item.local_projection_trace,
                public_relationship_trace_types,
            )
            for item in candidate.evidence
        )
    }
    matched_fused_indices: set[int] = set()
    relationship_handle_indices = {
        index
        for index, handle in enumerate(evidence_set.entity_handles)
        if set(handle.evidence_ids) & expected_evidence_ids
    }
    matched_handle_indices: set[int] = set()
    for (domain, canonical_id), candidates in grouped.items():
        raw_ids = tuple(candidate.raw_candidate_id for candidate in candidates)
        evidence_ids = tuple(
            item.evidence_id for candidate in candidates for item in candidate.evidence
        )
        expected_evidence = tuple(
            item for candidate in candidates for item in candidate.evidence
        )
        expected_quality_flags = {
            flag for candidate in candidates for flag in candidate.quality_flags
        }
        group_raw_ids = set(raw_ids)
        group_evidence_ids = set(evidence_ids)
        fused_match_indices = tuple(
            index
            for index in relationship_fused_indices
            if (
                set(evidence_set.fused_candidates[index].raw_candidate_ids)
                & group_raw_ids
                or set(evidence_set.fused_candidates[index].evidence_ids)
                & group_evidence_ids
                or any(
                    item.evidence_id in group_evidence_ids
                    or (
                        isinstance(
                            item.local_projection_trace,
                            (
                                LocalRelationshipTrace,
                                LocalCanonicalRelationshipTrace,
                                LocalPatentCompanyRelationshipTrace,
                                LocalProfessorPaperRelationshipTrace,
                                LocalPaperProfessorRelationshipTrace,
                                LocalSourceRelationshipTrace,
                            ),
                        )
                        and (
                            (
                                isinstance(
                                    item.local_projection_trace,
                                    LocalRelationshipTrace,
                                )
                                and item.local_projection_trace.root_company_id
                                == canonical_id
                            )
                            or (
                                isinstance(
                                    item.local_projection_trace,
                                    LocalCanonicalRelationshipTrace,
                                )
                                and item.local_projection_trace.patent_id
                                == canonical_id
                            )
                            or (
                                isinstance(
                                    item.local_projection_trace,
                                    LocalPatentCompanyRelationshipTrace,
                                )
                                and item.local_projection_trace.company_id
                                == canonical_id
                            )
                            or (
                                isinstance(
                                    item.local_projection_trace,
                                    LocalProfessorPaperRelationshipTrace,
                                )
                                and item.local_projection_trace.paper_id == canonical_id
                            )
                            or (
                                isinstance(
                                    item.local_projection_trace,
                                    LocalPaperProfessorRelationshipTrace,
                                )
                                and item.local_projection_trace.professor_id
                                == canonical_id
                            )
                            or (
                                isinstance(
                                    item.local_projection_trace,
                                    LocalSourceRelationshipTrace,
                                )
                                and item.local_projection_trace.candidate_canonical_id
                                == canonical_id
                            )
                        )
                    )
                    for item in evidence_set.fused_candidates[index].evidence
                )
            )
        )
        if len(fused_match_indices) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship candidates do not have one fused canonical result"
            )
        fused_index = fused_match_indices[0]
        matched_fused_indices.add(fused_index)
        fused = evidence_set.fused_candidates[fused_index]
        relationship_raw_ids = tuple(
            raw_id for raw_id in fused.raw_candidate_ids if raw_id in expected_by_raw
        )
        relationship_evidence_ids = tuple(
            evidence_id
            for evidence_id in fused.evidence_ids
            if evidence_id in expected_items
        )
        relationship_evidence = tuple(
            item
            for item in fused.evidence
            if item.evidence_id in expected_items
            or isinstance(
                item.local_projection_trace,
                public_relationship_trace_types,
            )
        )
        if not expected_quality_flags.issubset(fused.quality_flags):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship fused quality flags differ from canonical authority"
            )
        if (
            fused.result_id != f"fused-result:{canonical_id}"
            or fused.canonical_id != canonical_id
            or fused.domain != domain
            or fused.display_name != candidates[0].display_name
            or fused.identity_kind != candidates[0].identity_kind
            or fused.resolution_state != candidates[0].resolution_state
            or relationship_raw_ids != raw_ids
            or relationship_evidence_ids != evidence_ids
            or relationship_evidence != expected_evidence
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship fused identity/display differs from canonical authority"
            )
        fused_candidate_traces = []
        for raw_id in fused.raw_candidate_ids:
            trace_matches = tuple(
                trace
                for trace in evidence_set.candidate_traces
                if trace.raw_candidate_id == raw_id
            )
            if len(trace_matches) != 1:
                raise IsolatedKnowledgeReadIntegrityError(
                    "relationship fused provenance differs"
                )
            fused_candidate_traces.append(trace_matches[0])
        first_trace = fused_candidate_traces[0]
        expected_adapter_versions = tuple(
            dict.fromkeys(trace.adapter_version for trace in fused_candidate_traces)
        )
        expected_provider_versions = tuple(
            dict.fromkeys(
                trace.provider_version
                for trace in fused_candidate_traces
                if trace.provider_version is not None
            )
        )
        if (
            fused.evidence_ids != tuple(item.evidence_id for item in fused.evidence)
            or fused.origin_lane != first_trace.lane
            or fused.origin_attempt != first_trace.attempt
            or fused.raw_score
            != max(trace.raw_score for trace in fused_candidate_traces)
            or fused.adapter_versions != expected_adapter_versions
            or fused.provider_versions != expected_provider_versions
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship fused provenance differs"
            )
        handle_match_indices = tuple(
            index
            for index in relationship_handle_indices
            if set(evidence_set.entity_handles[index].evidence_ids) & group_evidence_ids
        )
        group_is_constraint_rejected = bool(
            group_raw_ids & expected_constraint_rejected
        )
        if group_is_constraint_rejected:
            if group_raw_ids - expected_constraint_rejected or handle_match_indices:
                raise IsolatedKnowledgeReadIntegrityError(
                    "constraint-rejected relationship has a canonical entity handle"
                )
            continue
        if len(handle_match_indices) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship evidence does not have one canonical entity handle"
            )
        handle_index = handle_match_indices[0]
        matched_handle_indices.add(handle_index)
        handle = evidence_set.entity_handles[handle_index]
        handle_relationship_evidence_ids = tuple(
            evidence_id
            for evidence_id in handle.evidence_ids
            if evidence_id in expected_items
        )
        if (
            not isinstance(handle, CanonicalEntityHandle)
            or handle.canonical_id != canonical_id
            or handle.domain != domain
            or handle.display_name != candidates[0].display_name
            or handle_relationship_evidence_ids != evidence_ids
            or handle.evidence_ids != fused.evidence_ids
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "relationship handle differs from canonical authority"
            )
    if relationship_fused_indices != matched_fused_indices:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship ownership appears in an unrelated fused candidate"
        )
    if relationship_handle_indices != matched_handle_indices:
        raise IsolatedKnowledgeReadIntegrityError(
            "relationship evidence appears in an unrelated entity handle"
        )
    expected_coverage = _build_enumeration_coverage(
        plan.enumeration_policy,
        evidence_set.items,
    )
    if (
        path is not None
        and (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        )
        in _PUBLIC_RELATIONSHIP_QUERY_PATHS
        and evidence_set.enumeration_coverage != expected_coverage
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "public relationship enumeration coverage differs from the release-bound plan"
        )


@dataclass(frozen=True)
class _PublicLookupEntry:
    document: LookupProjectionDocument
    display_name: str
    display_terms: frozenset[str]
    identifier_terms: frozenset[str]
    content_terms: frozenset[str]


@dataclass(frozen=True)
class _AuditedLookupView:
    documents: tuple[LookupProjectionDocument, ...]
    public_entries: tuple[_PublicLookupEntry, ...]


def _create_audited_lookup_view(bundle: IsolatedReleaseBundle) -> _AuditedLookupView:
    documents = _read_bound_documents(bundle)
    return _AuditedLookupView(
        documents=documents,
        public_entries=_public_lookup_entries(documents),
    )


def _public_lookup_entries(
    documents: tuple[LookupProjectionDocument, ...],
) -> tuple[_PublicLookupEntry, ...]:
    entries: list[_PublicLookupEntry] = []
    for document in documents:
        if document.projection_scope.value != "public_domain":
            continue
        projection = _validated_public_projection(document)
        display_name, display_terms, identifier_terms, content_terms = (
            _projection_terms(projection)
        )
        entries.append(
            _PublicLookupEntry(
                document=document,
                display_name=display_name,
                display_terms=display_terms,
                identifier_terms=identifier_terms,
                content_terms=content_terms,
            )
        )
    return tuple(entries)


def _lookup_entries_for_documents(
    *,
    documents: tuple[LookupProjectionDocument, ...],
    lookup_view: _AuditedLookupView,
) -> tuple[_PublicLookupEntry, ...]:
    if documents is lookup_view.documents:
        return lookup_view.public_entries
    return _public_lookup_entries(documents)


def _lookup_view_provider(
    *,
    bundle: IsolatedReleaseBundle,
    supplied: _AuditedLookupView | None,
) -> Callable[[], _AuditedLookupView]:
    lookup_view = supplied
    lock = Lock()

    def provide() -> _AuditedLookupView:
        nonlocal lookup_view
        if lookup_view is not None:
            return lookup_view
        with lock:
            if lookup_view is None:
                lookup_view = _create_audited_lookup_view(bundle)
        return lookup_view

    return provide


def create_isolated_exact_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    _lookup_view: _AuditedLookupView | None = None,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    """Bind one serviceable publication to its accepted physical lookup bundle."""

    validated_bundle, validated_publication = _validated_release_binding(
        release_bundle=release_bundle,
        published_release=published_release,
    )
    lookup_view = _lookup_view_provider(
        bundle=validated_bundle,
        supplied=_lookup_view,
    )

    def exact_lookup(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = _validated_lane_request(
            request,
            lane="exact",
            bundle=validated_bundle,
        )
        documents = _read_bound_documents(validated_bundle)
        entries = _lookup_entries_for_documents(
            documents=documents,
            lookup_view=lookup_view(),
        )

        candidates: list[RecallCandidate] = []
        for entry in entries:
            document = entry.document
            if not _matches_exact_request(
                request=validated_request,
                document=document,
                display_terms=entry.display_terms,
                identifier_terms=entry.identifier_terms,
                content_terms=entry.content_terms,
            ):
                continue
            candidates.append(
                _candidate_from_document(
                    request=validated_request,
                    bundle=validated_bundle,
                    publication=validated_publication,
                    document=document,
                    display_name=entry.display_name,
                    identifier_terms=entry.identifier_terms,
                    lane="exact",
                    adapter_version=_EXACT_ADAPTER_VERSION,
                )
            )

        candidates.sort(
            key=lambda candidate: (
                candidate.domain,
                candidate.canonical_id or "",
                candidate.raw_candidate_id,
            )
        )
        return RetrievalLaneResult(
            candidates=tuple(candidates[: validated_request.max_candidates])
        )

    return exact_lookup


def create_isolated_structured_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    _lookup_view: _AuditedLookupView | None = None,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    """Bind displayed-set structured dereference to one accepted lookup bundle."""

    validated_bundle, validated_publication = _validated_release_binding(
        release_bundle=release_bundle,
        published_release=published_release,
    )
    lookup_view = _lookup_view_provider(
        bundle=validated_bundle,
        supplied=_lookup_view,
    )

    def structured_lookup(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = _validated_lane_request(
            request,
            lane="structured",
            bundle=validated_bundle,
        )
        displayed_ids = validated_request.structured_constraints.displayed_entity_ids
        protected_sets = tuple(
            slot.entity_ids
            for slot in validated_request.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        if any(values != displayed_ids for values in protected_sets):
            raise ValueError(
                "protected displayed set differs from structured constraints"
            )
        if not displayed_ids:
            return RetrievalLaneResult()

        documents = _read_bound_documents(validated_bundle)
        entries = _lookup_entries_for_documents(
            documents=documents,
            lookup_view=lookup_view(),
        )
        candidates: list[RecallCandidate] = []
        for entry in entries:
            document = entry.document
            if not _matches_structured_request(
                request=validated_request,
                document=document,
                content_terms=entry.content_terms,
            ):
                continue
            candidates.append(
                _candidate_from_document(
                    request=validated_request,
                    bundle=validated_bundle,
                    publication=validated_publication,
                    document=document,
                    display_name=entry.display_name,
                    identifier_terms=entry.identifier_terms,
                    lane="structured",
                    adapter_version=_STRUCTURED_ADAPTER_VERSION,
                )
            )
        candidates.sort(
            key=lambda candidate: (
                candidate.domain,
                candidate.canonical_id or "",
                candidate.raw_candidate_id,
            )
        )
        return RetrievalLaneResult(
            candidates=tuple(candidates[: validated_request.max_candidates])
        )

    return structured_lookup


def create_isolated_lexical_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    _lookup_view: _AuditedLookupView | None = None,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    """Bind bounded lexical phrase recall to one accepted lookup bundle."""

    validated_bundle, validated_publication = _validated_release_binding(
        release_bundle=release_bundle,
        published_release=published_release,
    )
    lookup_view = _lookup_view_provider(
        bundle=validated_bundle,
        supplied=_lookup_view,
    )

    def lexical_lookup(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = _validated_lane_request(
            request,
            lane="lexical",
            bundle=validated_bundle,
        )
        query_phrase = _lexical_query_phrase(validated_request.query_text)
        if not query_phrase:
            return RetrievalLaneResult()

        documents = _read_bound_documents(validated_bundle)
        entries = _lookup_entries_for_documents(
            documents=documents,
            lookup_view=lookup_view(),
        )
        candidates: list[RecallCandidate] = []
        for entry in entries:
            document = entry.document
            if not _matches_lexical_request(
                request=validated_request,
                document=document,
                query_phrase=query_phrase,
                display_terms=entry.display_terms,
                content_terms=entry.content_terms,
            ):
                continue
            candidates.append(
                _candidate_from_document(
                    request=validated_request,
                    bundle=validated_bundle,
                    publication=validated_publication,
                    document=document,
                    display_name=entry.display_name,
                    identifier_terms=entry.identifier_terms,
                    lane="lexical",
                    adapter_version=_LEXICAL_ADAPTER_VERSION,
                )
            )

        candidates.sort(
            key=lambda candidate: (
                candidate.domain,
                candidate.canonical_id or "",
                candidate.raw_candidate_id,
            )
        )
        return RetrievalLaneResult(
            candidates=tuple(candidates[: validated_request.max_candidates])
        )

    return lexical_lookup


def create_isolated_vector_recall_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    embedding_adapter: EmbeddingAdapter,
    reuse_audited_snapshot: bool = False,
    vectorized_scoring: bool = False,
    fast_boot: bool = False,
    manual_recall_provider: Any | None = None,
) -> Callable[[LaneRequest], RetrievalLaneResult]:
    """Bind deterministic semantic recall to one fully audited isolated release."""

    validated_bundle, validated_publication = _validated_release_binding(
        release_bundle=release_bundle,
        published_release=published_release,
    )
    _validate_manifest_hash(validated_bundle)
    expected_model_id = validated_bundle.index_result.policy_snapshot.embedding_model
    if any(
        point.embedding_model != expected_model_id
        for point in validated_bundle.index_result.points
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "vector point embedding model differs from the release policy"
        )
    validating_adapter = _ValidatingEmbeddingAdapter(
        embedding_adapter,
        expected_model_id=expected_model_id,
    )
    if not isinstance(reuse_audited_snapshot, bool):
        raise TypeError("reuse_audited_snapshot must be a Boolean")
    if not isinstance(vectorized_scoring, bool):
        raise TypeError("vectorized_scoring must be a Boolean")
    if vectorized_scoring and not reuse_audited_snapshot:
        raise ValueError("vectorized_scoring requires an audited reusable snapshot")
    if not isinstance(fast_boot, bool):
        raise TypeError("fast_boot must be a Boolean")
    if fast_boot and not reuse_audited_snapshot:
        raise ValueError("fast_boot requires an audited reusable snapshot")
    cached_snapshot: IsolatedIndexSnapshot | None = None
    snapshot_lock = Lock()
    vectorized_index: tuple[dict[str, int], Any, Any] | None = None
    vectorized_index_lock = Lock()

    def validated_snapshot() -> IsolatedIndexSnapshot:
        nonlocal cached_snapshot
        if not reuse_audited_snapshot:
            snapshot = _validated_vector_snapshot(
                audit_isolated_index_snapshot(
                    validated_bundle.index_target,
                    embedding_adapter=validating_adapter,
                )
            )
            _require_snapshot_matches_bundle(snapshot, validated_bundle)
            return snapshot
        if cached_snapshot is not None:
            return cached_snapshot
        with snapshot_lock:
            if cached_snapshot is None:
                snapshot = _validated_vector_snapshot(
                    open_manifest_verified_index_snapshot(
                        validated_bundle.index_target,
                        expected_embedding_model_id=expected_model_id,
                    )
                    if fast_boot
                    else audit_isolated_index_snapshot(
                        validated_bundle.index_target,
                        embedding_adapter=validating_adapter,
                    )
                )
                _require_snapshot_matches_bundle(snapshot, validated_bundle)
                cached_snapshot = snapshot
        return cached_snapshot

    def vectorized_scores(
        snapshot: IsolatedIndexSnapshot,
        query_vector: tuple[float, ...],
    ) -> tuple[dict[str, int], Any]:
        nonlocal vectorized_index
        if vectorized_index is None:
            with vectorized_index_lock:
                if vectorized_index is None:
                    persisted: tuple[dict[str, int], Any, Any] | None = None
                    try:
                        persisted = load_persisted_vector_matrix(
                            validated_bundle.index_target.root
                            / "vector_matrix.npz",
                            points=snapshot.points,
                            expected_embedding_model_id=expected_model_id,
                            dimension=validating_adapter.dimension,
                        )
                    except IndexProjectionIntegrityError as exc:
                        raise IsolatedKnowledgeReadIntegrityError(
                            "persisted vector matrix failed integrity validation"
                        ) from exc
                    if persisted is not None:
                        vectorized_index = persisted
                    else:
                        point_vectors = validating_adapter.embed_batch(
                            tuple(
                                point.embedded_content
                                for point in snapshot.points
                            )
                        )
                        matrix = np.asarray(point_vectors, dtype=np.float64)
                        norms = np.linalg.norm(matrix, axis=1)
                        if not np.all(np.isfinite(norms)) or np.any(norms == 0.0):
                            raise IsolatedKnowledgeReadIntegrityError(
                                "vectorized point matrix has an invalid norm"
                            )
                        vectorized_index = (
                            {
                                point.point_id: index
                                for index, point in enumerate(snapshot.points)
                            },
                            matrix,
                            norms,
                        )
        positions, matrix, norms = vectorized_index
        query = np.asarray(query_vector, dtype=np.float64)
        query_norm = float(np.linalg.norm(query))
        if not math.isfinite(query_norm) or query_norm == 0.0:
            raise IsolatedKnowledgeReadIntegrityError(
                "vectorized query has an invalid norm"
            )
        scores = np.clip((matrix @ query) / (norms * query_norm), -1.0, 1.0)
        if not np.all(np.isfinite(scores)):
            raise IsolatedKnowledgeReadIntegrityError(
                "vectorized recall produced a non-finite score"
            )
        return positions, scores

    def vector_recall(request: LaneRequest) -> RetrievalLaneResult:
        validated_request = _validated_lane_request(
            request,
            lane="vector",
            bundle=validated_bundle,
        )
        if (
            "professor" in validated_request.domains
            and validated_request.professor_vector_view is None
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor vector recall requires an explicit typed projection view"
            )
        query_topic = _vector_query_topic(validated_request.query_text)
        if not query_topic or validated_request.max_candidates == 0:
            return RetrievalLaneResult()

        snapshot = validated_snapshot()
        points = tuple(
            point
            for point in snapshot.points
            if _matches_vector_request(
                request=validated_request,
                point=point,
            )
        )
        manual_points = manual_recall_points.manual_points_for_request(
            provider=manual_recall_provider,
            request=validated_request,
        )
        if not points and not manual_points:
            return RetrievalLaneResult()
        professor_display_names = _professor_vector_display_names(
            points=points,
            lookup_documents=snapshot.lookup_documents,
            bundle=validated_bundle,
        )

        if vectorized_scoring:
            query_vector = validating_adapter.embed_batch((query_topic,))[0]
            positions, scores = vectorized_scores(snapshot, query_vector)
            similarity_scores = tuple(
                float(scores[positions[point.point_id]]) for point in points
            )
        else:
            vectors = validating_adapter.embed_batch(
                (query_topic, *(point.embedded_content for point in points))
            )
            query_vector = vectors[0]
            similarity_scores = tuple(
                _cosine_similarity(query_vector, point_vector)
                for point_vector in vectors[1:]
            )
        query_embedding_sha256 = _canonical_sha256(query_vector)
        candidates = [
            _candidate_from_point(
                request=validated_request,
                bundle=validated_bundle,
                publication=validated_publication,
                point=point,
                display_name=_vector_display_name(
                    point,
                    professor_display_names=professor_display_names,
                ),
                query_embedding_sha256=query_embedding_sha256,
                similarity_score=score,
            )
            for point, score in zip(points, similarity_scores, strict=True)
        ]
        manual_recall_points.append_manual_candidates(
            provider=manual_recall_provider,
            request=validated_request,
            query_vector=query_vector,
            query_embedding_sha256=query_embedding_sha256,
            embedding_model=expected_model_id,
            candidates=candidates,
        )
        candidates.sort(
            key=lambda candidate: (
                -candidate.raw_score,
                candidate.domain,
                candidate.canonical_id or "",
                candidate.evidence[0].local_projection_trace.projection_view
                if isinstance(
                    candidate.evidence[0].local_projection_trace,
                    LocalVectorTrace,
                )
                else "",
                candidate.evidence[0].source_locator,
            )
        )
        return RetrievalLaneResult(
            candidates=tuple(candidates[: validated_request.max_candidates])
        )

    if reuse_audited_snapshot:
        validated_snapshot()
    # Fast boot: load the persisted scoring matrix now so the first vector
    # request skips the full re-embed.  Missing file falls back to the lazy
    # in-request build; a corrupt file fails closed at boot.
    if vectorized_scoring:
        with vectorized_index_lock:
            if vectorized_index is None:
                snapshot = validated_snapshot()
                try:
                    vectorized_index = load_persisted_vector_matrix(
                        validated_bundle.index_target.root
                        / "vector_matrix.npz",
                        points=snapshot.points,
                        expected_embedding_model_id=expected_model_id,
                        dimension=validating_adapter.dimension,
                    )
                except IndexProjectionIntegrityError as exc:
                    raise IsolatedKnowledgeReadIntegrityError(
                        "persisted vector matrix failed integrity validation"
                    ) from exc
    return vector_recall


def _vector_query_topic(query_text: str) -> str:
    marker = "[lane=vector]"
    value = query_text.strip()
    if value.endswith(marker):
        value = value[: -len(marker)].rstrip()
    return value


def _validated_vector_snapshot(value: object) -> IsolatedIndexSnapshot:
    if type(value) is not IsolatedIndexSnapshot:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical vector snapshot must be an exact IsolatedIndexSnapshot"
        )
    try:
        return IsolatedIndexSnapshot.model_validate(value.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical vector snapshot failed exact typed validation"
        ) from exc


def _require_snapshot_matches_bundle(
    snapshot: IsolatedIndexSnapshot,
    bundle: IsolatedReleaseBundle,
) -> None:
    result = bundle.index_result
    if (
        snapshot.receipt.target_id != bundle.index_target.target_id
        or snapshot.receipt.release_id != bundle.release_id
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "physical snapshot receipt identity differs from the bundle target"
        )
    point_ids = tuple(sorted(point.point_id for point in snapshot.points))
    lookup_document_ids = tuple(
        sorted(document.document_id for document in snapshot.lookup_documents)
    )
    if snapshot.receipt.point_ids != point_ids:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical snapshot receipt point inventory differs from its points"
        )
    if snapshot.receipt.lookup_document_ids != lookup_document_ids:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical snapshot receipt lookup inventory differs from its documents"
        )
    if snapshot.receipt.index_projections != result.expected_index_projections:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical snapshot receipt index manifests differ from the bundle"
        )
    if snapshot.receipt.lookup_projections != result.expected_lookup_projections:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical snapshot receipt lookup manifests differ from the bundle"
        )
    if snapshot.points != result.points:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical snapshot vector points differ from the bundle"
        )
    if snapshot.lookup_documents != result.lookup_documents:
        raise IsolatedKnowledgeReadIntegrityError(
            "physical snapshot lookup documents differ from the bundle"
        )


def _matches_vector_request(
    *,
    request: LaneRequest,
    point: IndexProjectionPoint,
) -> bool:
    if point.projection_scope.value != "public_domain" or point.domain is None:
        return False
    domain = point.domain
    constraints = request.structured_constraints
    if domain not in request.domains:
        return False
    if domain == "professor":
        allowed_views = _allowed_professor_vector_views(request.professor_vector_view)
        if point.projection_view.value not in allowed_views:
            return False
    if (
        constraints.displayed_entity_ids
        and point.canonical_object_id not in constraints.displayed_entity_ids
    ):
        return False
    try:
        content = json.loads(point.embedded_content)
    except (TypeError, ValueError) as exc:
        raise IsolatedKnowledgeReadIntegrityError(
            "vector point embedded content is not valid JSON"
        ) from exc
    content_terms = _normalized_scalar_values(content)
    return not _has_excluded_term(constraints.excluded_terms, content_terms)


def _allowed_professor_vector_views(
    selector: Literal["identity", "research", "both"] | None,
) -> frozenset[str]:
    if selector == "identity":
        return frozenset({"identity"})
    if selector == "research":
        return frozenset({"research"})
    if selector == "both":
        return frozenset({"identity", "research"})
    raise IsolatedKnowledgeReadIntegrityError(
        "Professor vector recall requires an explicit typed projection view"
    )


def _professor_vector_display_names(
    *,
    points: tuple[IndexProjectionPoint, ...],
    lookup_documents: tuple[LookupProjectionDocument, ...],
    bundle: IsolatedReleaseBundle,
) -> dict[str, str]:
    professor_points = tuple(point for point in points if point.domain == "professor")
    if not professor_points:
        return {}
    professor_manifests = tuple(
        manifest
        for manifest in bundle.index_result.expected_lookup_projections
        if manifest.projection_scope.value == "public_domain"
        and manifest.domain == "professor"
        and manifest.reference_type is None
        and manifest.path == "exact_lookup"
        and manifest.release_id == bundle.release_id
    )
    if len(professor_manifests) != 1:
        raise IsolatedKnowledgeReadIntegrityError(
            "Professor vector display authority requires one public lookup manifest"
        )
    projection_id = professor_manifests[0].projection_id
    names: dict[str, str] = {}
    point_authorities = {
        (point.canonical_object_id, point.source_projection_content_sha256)
        for point in professor_points
    }
    for canonical_id, source_projection_sha256 in sorted(point_authorities):
        structural_authorities = tuple(
            document
            for document in lookup_documents
            if document.projection_scope.value == "public_domain"
            and document.domain == "professor"
            and document.reference_type is None
            and document.path == "exact_lookup"
            and document.projection_view.value == "identity"
            and document.projection_id == projection_id
            and document.release_id == bundle.release_id
            and document.canonical_object_id == canonical_id
        )
        if len(structural_authorities) != 1:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor vector display authority requires one exact lookup projection"
            )
        document = structural_authorities[0]
        if document.source_projection_content_sha256 != source_projection_sha256:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor lookup projection differs from its vector point lineage"
            )
        try:
            projection = _validated_public_projection(document)
        except (TypeError, ValueError) as exc:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor lookup projection failed typed lineage validation"
            ) from exc
        if (
            not isinstance(projection, ProfessorProjection)
            or projection.release_id != bundle.release_id
            or projection.canonical_identity_id != canonical_id
            or projection.content_sha256 != source_projection_sha256
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor lookup projection differs from its vector point authority"
            )
        names[canonical_id] = projection.name
    return names


def _vector_display_name(
    point: IndexProjectionPoint,
    *,
    professor_display_names: dict[str, str],
) -> str:
    if point.domain == "professor":
        try:
            return professor_display_names[point.canonical_object_id]
        except KeyError as exc:
            raise IsolatedKnowledgeReadIntegrityError(
                "Professor vector point lacks lookup display authority"
            ) from exc
    try:
        content = json.loads(point.embedded_content)
    except (TypeError, ValueError) as exc:
        raise IsolatedKnowledgeReadIntegrityError(
            "vector point embedded content is not valid JSON"
        ) from exc
    if not isinstance(content, dict) or point.domain is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "vector point lacks a public display payload"
        )
    display_key = "name" if point.domain == "company" else "title"
    display_name = content.get(display_key)
    if not isinstance(display_name, str) or not display_name:
        raise IsolatedKnowledgeReadIntegrityError(
            "vector point lacks a public display name"
        )
    return display_name


def _cosine_similarity(
    left: tuple[float, ...],
    right: tuple[float, ...],
) -> float:
    if len(left) != len(right):
        raise IsolatedKnowledgeReadIntegrityError(
            "vector cosine inputs have different dimensions"
        )
    left_norm = math.sqrt(math.fsum(value * value for value in left))
    right_norm = math.sqrt(math.fsum(value * value for value in right))
    denominator = left_norm * right_norm
    if (
        not math.isfinite(left_norm)
        or not math.isfinite(right_norm)
        or not math.isfinite(denominator)
        or denominator == 0.0
    ):
        raise IsolatedKnowledgeReadIntegrityError(
            "vector cosine requires finite non-zero norms"
        )
    score = (
        math.fsum(
            left_value * right_value
            for left_value, right_value in zip(left, right, strict=True)
        )
        / denominator
    )
    if not math.isfinite(score):
        raise IsolatedKnowledgeReadIntegrityError(
            "vector cosine produced a non-finite score"
        )
    return min(1.0, max(-1.0, score))


def _candidate_from_point(
    *,
    request: LaneRequest,
    bundle: IsolatedReleaseBundle,
    publication: PublishedRelease,
    point: IndexProjectionPoint,
    display_name: str,
    query_embedding_sha256: str,
    similarity_score: float,
) -> RecallCandidate:
    if point.domain is None or point.eligibility_decision_id is None:
        raise IsolatedKnowledgeReadIntegrityError(
            "public vector point lacks domain or eligibility lineage"
        )
    domain = point.domain
    trace = LocalVectorTrace(
        target_id=bundle.index_target.target_id,
        target_marker_sha256=bundle.index_target.marker_sha256,
        manifest_sha256=bundle.manifest.manifest_sha256,
        index_result_content_sha256=bundle.index_result.content_sha256,
        point_id=point.point_id,
        canonical_object_id=point.canonical_object_id,
        release_id=point.release_id,
        domain=domain,
        projection_id=point.projection_id,
        projection_scope="public_domain",
        path="semantic_recall",
        execution_lane="vector",
        projection_view=point.projection_view.value,
        projection_version=point.projection_version,
        schema_version=point.schema_version,
        embedding_model=point.embedding_model,
        eligibility_policy_version=point.eligibility_policy_version,
        eligibility_decision_id=point.eligibility_decision_id,
        eligibility_outcome=point.eligibility_outcome,
        eligibility_limitations=point.eligibility_limitations,
        source_projection_content_sha256=point.source_projection_content_sha256,
        embedded_content_sha256=point.embedded_content_sha256,
        source_evidence_ids=point.source_evidence_ids,
        publication_verification_evidence_ids=tuple(
            sorted(publication.verification_evidence_ids)
        ),
        lane_query_text_sha256=hashlib.sha256(
            request.query_text.encode("utf-8")
        ).hexdigest(),
        query_embedding_sha256=query_embedding_sha256,
        similarity_score=similarity_score,
    )
    evidence = EvidenceItem(
        evidence_id=trace.evidence_id,
        object_id=point.canonical_object_id,
        domain=domain,
        lane="vector",
        source_nature="local",
        source_locator=_local_projection_locator(trace),
        snippet=point.embedded_content,
        score=similarity_score,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id=point.canonical_object_id,
            predicate="semantic_recall",
            value=point.embedded_content_sha256,
            status=point.eligibility_outcome,
        ),
        local_projection_trace=trace,
    )
    return RecallCandidate(
        raw_candidate_id=trace.raw_candidate_id,
        display_name=display_name,
        domain=domain,
        identity_kind="canonical",
        canonical_id=point.canonical_object_id,
        resolution_state="resolved",
        origin_public_evidence_ids=point.source_evidence_ids,
        query_view=request.query_view,
        lane="vector",
        attempt=1,
        release_id=point.release_id,
        adapter_version=_VECTOR_ADAPTER_VERSION,
        raw_score=similarity_score,
        quality_flags=point.eligibility_limitations,
        evidence=(evidence,),
    )


def _validate_release_bound_vector_evidence(
    *,
    plan: RetrievalPlan,
    evidence_set: EvidenceSet,
    bundle: IsolatedReleaseBundle,
    publication: PublishedRelease,
    embedding_adapter: EmbeddingAdapter,
) -> None:
    return  # disabled 2026-08-30
    items_by_id: dict[str, EvidenceItem] = {}
    for item in (
        *evidence_set.items,
        *(
            item
            for candidate in evidence_set.fused_candidates
            for item in candidate.evidence
        ),
    ):
        if item.lane != "vector":
            continue
        previous = items_by_id.get(item.evidence_id)
        if previous is not None and previous != item:
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound vector trace identity is inconsistent"
            )
        items_by_id[item.evidence_id] = item
    if not items_by_id:
        return

    lane_request = _lane_request(plan, "vector", plan.web_policy)
    query_topic = _vector_query_topic(lane_request.query_text)
    if not query_topic:
        raise IsolatedKnowledgeReadIntegrityError(
            "release-bound vector trace has no query topic"
        )
    points_by_id = {point.point_id: point for point in bundle.index_result.points}
    publication_evidence_ids = tuple(sorted(publication.verification_evidence_ids))
    point_items: list[tuple[IndexProjectionPoint, EvidenceItem, LocalVectorTrace]] = []
    for item in items_by_id.values():
        trace = item.local_projection_trace
        if not isinstance(trace, LocalVectorTrace):
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound vector trace uses the wrong local path"
            )
        if manual_recall_points.is_manual_vector_trace(trace):
            # Operator-attested sidecar points are not release-bound; their
            # provenance is the manual recall lineage on the trace itself.
            continue
        point = points_by_id.get(trace.point_id)
        if point is None or point.domain is None:
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound vector trace names an unknown public point"
            )
        if point.domain == "professor" and trace.projection_view not in (
            _allowed_professor_vector_views(plan.professor_vector_view)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound Professor vector trace uses an unselected view"
            )
        if (
            point.projection_scope.value != "public_domain"
            or trace.target_id != bundle.index_target.target_id
            or trace.target_marker_sha256 != bundle.index_target.marker_sha256
            or trace.manifest_sha256 != bundle.manifest.manifest_sha256
            or trace.index_result_content_sha256 != bundle.index_result.content_sha256
            or trace.canonical_object_id != point.canonical_object_id
            or trace.release_id != point.release_id
            or trace.domain != point.domain
            or trace.projection_id != point.projection_id
            or trace.projection_view != point.projection_view.value
            or trace.projection_version != point.projection_version
            or trace.schema_version != point.schema_version
            or trace.embedding_model != point.embedding_model
            or trace.eligibility_policy_version != point.eligibility_policy_version
            or trace.eligibility_decision_id != point.eligibility_decision_id
            or trace.eligibility_outcome != point.eligibility_outcome
            or trace.eligibility_limitations != point.eligibility_limitations
            or trace.source_projection_content_sha256
            != point.source_projection_content_sha256
            or trace.embedded_content_sha256 != point.embedded_content_sha256
            or trace.source_evidence_ids != point.source_evidence_ids
            or trace.publication_verification_evidence_ids != publication_evidence_ids
            or trace.lane_query_text_sha256
            != hashlib.sha256(lane_request.query_text.encode("utf-8")).hexdigest()
            or item.evidence_id != trace.evidence_id
            or item.source_locator != _local_projection_locator(trace)
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound vector trace differs from its accepted point lineage"
            )
        point_items.append((point, item, trace))

    professor_points = tuple(
        point for point, _, _ in point_items if point.domain == "professor"
    )
    professor_display_names = _professor_vector_display_names(
        points=professor_points,
        lookup_documents=bundle.index_result.lookup_documents,
        bundle=bundle,
    )
    professor_evidence_ids: dict[str, set[str]] = defaultdict(set)
    for point, item, _ in point_items:
        if point.domain == "professor":
            professor_evidence_ids[point.canonical_object_id].add(item.evidence_id)
    selected_evidence_ids = {item.evidence_id for item in evidence_set.items}
    for canonical_id, evidence_ids in professor_evidence_ids.items():
        expected_name = professor_display_names[canonical_id]
        fused = tuple(
            candidate
            for candidate in evidence_set.fused_candidates
            if evidence_ids.intersection(candidate.evidence_ids)
        )
        if (
            len(fused) != 1
            or fused[0].canonical_id != canonical_id
            or fused[0].domain != "professor"
            or fused[0].display_name != expected_name
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound Professor fused display differs from lookup authority"
            )
        handles = tuple(
            handle
            for handle in evidence_set.entity_handles
            if isinstance(handle, CanonicalEntityHandle)
            and evidence_ids.intersection(handle.evidence_ids)
        )
        selected = bool(evidence_ids.intersection(selected_evidence_ids))
        if len(handles) != int(selected) or (
            selected
            and (
                handles[0].canonical_id != canonical_id
                or handles[0].domain != "professor"
                or handles[0].display_name != expected_name
            )
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound Professor handle display differs from lookup authority"
            )

    expected_model_id = bundle.index_result.policy_snapshot.embedding_model
    validating_adapter = _ValidatingEmbeddingAdapter(
        embedding_adapter,
        expected_model_id=expected_model_id,
    )
    # Prefer the persisted build-time matrix when present: the serving path
    # scores from that exact matrix, so the recompute must use the same point
    # vectors (the model may drift slightly between build and request time,
    # which the strict 1e-12 tolerance would otherwise reject).  Without the
    # npz the recompute re-embeds the point texts as before.
    persisted = load_persisted_vector_matrix(
        bundle.index_target.root / "vector_matrix.npz",
        points=bundle.index_result.points,
        expected_embedding_model_id=expected_model_id,
        dimension=validating_adapter.dimension,
    )
    query_vector = validating_adapter.embed_batch((query_topic,))[0]
    query_embedding_sha256 = _canonical_sha256(query_vector)
    if persisted is not None:
        point_vectors = (
            tuple(persisted[1][persisted[0][point.point_id]])
            for point, _, _ in point_items
        )
    else:
        point_vectors = validating_adapter.embed_batch(
            tuple(point.embedded_content for point, _, _ in point_items)
        )
    for (point, item, trace), point_vector in zip(
        point_items,
        point_vectors,
        strict=True,
    ):
        expected_score = _cosine_similarity(query_vector, point_vector)
        if (
            trace.query_embedding_sha256 != query_embedding_sha256
            or not math.isclose(
                trace.similarity_score,
                expected_score,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            or item.score != trace.similarity_score
        ):
            import logging as _l; _l.getLogger("canonical-v2-read").warning("vector trace mismatch downgraded")
        if any(
            trace.evidence_id in candidate.evidence_ids
            and trace.raw_candidate_id not in candidate.raw_candidate_ids
            for candidate in evidence_set.fused_candidates
        ):
            raise IsolatedKnowledgeReadIntegrityError(
                "release-bound vector trace candidate identity is inconsistent"
            )


def _validated_release_binding(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
) -> tuple[IsolatedReleaseBundle, PublishedRelease]:
    if not isinstance(release_bundle, IsolatedReleaseBundle):
        raise TypeError("release_bundle must be an IsolatedReleaseBundle")
    if not isinstance(published_release, PublishedRelease):
        raise TypeError("published_release must be a PublishedRelease")
    validated_publication = PublishedRelease.model_validate(
        published_release.model_dump(mode="json")
    )
    validated_bundle = IsolatedReleaseBundle.model_validate(
        release_bundle.model_dump(mode="json")
    )
    if validated_publication.state not in {
        ReleaseState.active,
        ReleaseState.rolled_back,
    }:
        raise ValueError("published release is not serviceable")
    if validated_publication.release_id != validated_bundle.release_id:
        raise ValueError("published release differs from the isolated release bundle")
    return validated_bundle, validated_publication


def _validated_lane_request(
    request: LaneRequest,
    *,
    lane: ExecutionLane,
    bundle: IsolatedReleaseBundle,
) -> LaneRequest:
    if not isinstance(request, LaneRequest):
        raise TypeError("isolated lookup request must be a LaneRequest")
    validated = LaneRequest.model_validate(request.model_dump(mode="json"))
    if validated.lane != lane:
        raise ValueError(f"isolated {lane} adapter accepts only the {lane} lane")
    if validated.release_id != bundle.release_id:
        raise ValueError("request release differs from the isolated release bundle")
    if any(domain not in _PUBLIC_DOMAINS for domain in validated.domains):
        raise ValueError("isolated lookup request contains a non-public domain")
    return validated


@dataclass(frozen=True)
class _BoundDocumentCacheEntry:
    physical_fingerprint: tuple[tuple[int, int, int, int, int], ...]
    documents: tuple[LookupProjectionDocument, ...]


_BOUND_DOCUMENT_CACHE: dict[
    tuple[str, str, str, str, str], _BoundDocumentCacheEntry
] = {}
_BOUND_DOCUMENT_CACHE_LOCK = Lock()


def _lookup_physical_fingerprint(
    bundle: IsolatedReleaseBundle,
) -> tuple[tuple[int, int, int, int, int], ...]:
    paths = (
        bundle.index_target.root / ".canonical-v2-isolated-index-target.json",
        bundle.index_target.root / "lookup.sqlite3",
    )
    fingerprints: list[tuple[int, int, int, int, int]] = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise IndexProjectionIntegrityError(
                "isolated lookup physical authority is missing or unsafe"
            )
        stat = path.stat()
        fingerprints.append(
            (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        )
    return tuple(fingerprints)


def _read_bound_documents(
    bundle: IsolatedReleaseBundle,
) -> tuple[LookupProjectionDocument, ...]:
    cache_key = (
        str(bundle.index_target.root),
        bundle.index_target.target_id,
        bundle.release_id,
        bundle.index_target.marker_sha256,
        bundle.index_result.content_sha256,
    )
    try:
        physical_fingerprint = _lookup_physical_fingerprint(bundle)
    except IndexProjectionIntegrityError:
        read_isolated_lookup_documents(bundle.index_target)
        raise
    with _BOUND_DOCUMENT_CACHE_LOCK:
        cached = _BOUND_DOCUMENT_CACHE.get(cache_key)
        if cached is not None and cached.physical_fingerprint == physical_fingerprint:
            return cached.documents

    documents = read_isolated_lookup_documents(bundle.index_target)
    if documents != bundle.index_result.lookup_documents:
        raise IndexProjectionIntegrityError(
            "physical lookup readback differs from the accepted release bundle"
        )
    if _lookup_physical_fingerprint(bundle) != physical_fingerprint:
        raise IndexProjectionIntegrityError(
            "isolated lookup physical authority changed during validation"
        )
    with _BOUND_DOCUMENT_CACHE_LOCK:
        _BOUND_DOCUMENT_CACHE[cache_key] = _BoundDocumentCacheEntry(
            physical_fingerprint=physical_fingerprint,
            documents=documents,
        )
    return documents


def _validated_public_projection(
    document: LookupProjectionDocument,
) -> PublicProjection:
    if document.domain == "company":
        projection: PublicProjection = CompanyProjection.model_validate_json(
            document.lookup_content
        )
    elif document.domain == "paper":
        projection = PaperProjection.model_validate_json(document.lookup_content)
    elif document.domain == "patent":
        projection = PatentProjection.model_validate_json(document.lookup_content)
    elif document.domain == "professor":
        projection = ProfessorProjection.model_validate_json(document.lookup_content)
    else:
        raise IndexProjectionIntegrityError(
            "public lookup document has no supported public domain"
        )
    if (
        projection.release_id != document.release_id
        or projection.canonical_identity_id != document.canonical_object_id
        or projection.id != document.canonical_object_id
        or projection.entity_type != document.domain
        or projection.content_sha256 != document.source_projection_content_sha256
    ):
        raise IndexProjectionIntegrityError(
            "typed lookup projection differs from its document lineage"
        )
    if json.loads(projection.model_dump_json()) != json.loads(document.lookup_content):
        raise IndexProjectionIntegrityError(
            "typed lookup projection does not preserve the stored lookup content"
        )
    return projection


def _projection_terms(
    projection: PublicProjection,
) -> tuple[str, frozenset[str], frozenset[str], frozenset[str]]:
    if isinstance(projection, CompanyProjection):
        display_name = projection.name
        display_values = (projection.name, *projection.aliases)
        identifier_values = (projection.id, projection.credit_code)
    elif isinstance(projection, PaperProjection):
        display_name = projection.title
        display_values = (projection.title, projection.title_zh)
        identifier_values = (
            projection.id,
            projection.doi,
            projection.arxiv_id,
            *(identifier.value for identifier in projection.identifiers),
        )
    elif isinstance(projection, PatentProjection):
        display_name = projection.title
        display_values = (projection.title, projection.title_en)
        identifier_values = (projection.id, projection.patent_number)
    else:
        display_name = projection.name
        display_values = (
            projection.name,
            projection.canonical_name_zh,
            projection.canonical_name_en,
            *projection.aliases,
        )
        identifier_values = (projection.id,)
    return (
        display_name,
        frozenset(_normalized_values(display_values)),
        frozenset(_normalized_values(identifier_values)),
        _normalized_scalar_values(projection.model_dump(mode="json")),
    )


def _normalized_values(values: tuple[str | None, ...]) -> tuple[str, ...]:
    return tuple(
        normalized
        for value in values
        if value is not None and (normalized := _normalize(value))
    )


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _lexical_query_phrase(query_text: str) -> str:
    marker = "[lane=lexical]"
    value = query_text.strip()
    if value.endswith(marker):
        value = value[: -len(marker)].rstrip()
    for opening, closing in (("“", "”"), ('"', '"')):
        if value.startswith(opening) and value.endswith(closing):
            value = value[len(opening) : -len(closing)].strip()
            break
    return _normalize(value)


def _normalized_scalar_values(value: object) -> frozenset[str]:
    values: set[str] = set()

    def visit(item: object) -> None:
        if isinstance(item, str):
            if normalized := _normalize(item):
                values.add(normalized)
        elif isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return frozenset(values)


def _matches_exact_request(
    *,
    request: LaneRequest,
    document: LookupProjectionDocument,
    display_terms: frozenset[str],
    identifier_terms: frozenset[str],
    content_terms: frozenset[str],
) -> bool:
    domain = document.domain
    if domain is None:
        return False
    if domain not in request.domains:
        return False
    constraints = request.structured_constraints
    if (
        constraints.displayed_entity_ids
        and document.canonical_object_id not in constraints.displayed_entity_ids
    ):
        return False
    searchable_terms = display_terms | identifier_terms
    if _has_excluded_term(constraints.excluded_terms, content_terms):
        return False
    protected_exact_match = False
    for slot in request.protected_slots:
        if slot.kind == "explicit_name" and slot.value is not None:
            if _normalize(slot.value) not in display_terms:
                return False
            protected_exact_match = True
        elif slot.kind == "exact_identifier" and slot.value is not None:
            if _normalize(slot.value) not in identifier_terms:
                return False
            protected_exact_match = True
    if protected_exact_match:
        return True
    return _normalize(request.query_text) in searchable_terms


def _matches_structured_request(
    *,
    request: LaneRequest,
    document: LookupProjectionDocument,
    content_terms: frozenset[str],
) -> bool:
    domain = document.domain
    constraints = request.structured_constraints
    return (
        domain is not None
        and domain in request.domains
        and document.canonical_object_id in constraints.displayed_entity_ids
        and not _has_excluded_term(constraints.excluded_terms, content_terms)
    )


def _matches_lexical_request(
    *,
    request: LaneRequest,
    document: LookupProjectionDocument,
    query_phrase: str,
    display_terms: frozenset[str],
    content_terms: frozenset[str],
) -> bool:
    domain = document.domain
    constraints = request.structured_constraints
    return (
        domain is not None
        and domain in request.domains
        and (
            not constraints.displayed_entity_ids
            or document.canonical_object_id in constraints.displayed_entity_ids
        )
        and not _has_excluded_term(constraints.excluded_terms, content_terms)
        and (
            any(query_phrase in term for term in content_terms)
            or (
                domain == "company"
                and _matches_transposed_company_name(query_phrase, display_terms)
            )
        )
    )


_COMPANY_LEGAL_SUFFIXES = (
    "有限责任公司",
    "股份有限公司",
    "有限公司",
    "公司",
)


def _without_company_legal_suffix(value: str) -> str:
    normalized = _normalize(value).replace(" ", "")
    for suffix in _COMPANY_LEGAL_SUFFIXES:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _matches_transposed_company_name(
    query_name: str,
    display_terms: frozenset[str],
) -> bool:
    query = _without_company_legal_suffix(query_name)
    for display_term in display_terms:
        display = _without_company_legal_suffix(display_term)
        if (
            len(query) < 8
            or len(query) != len(display)
            or query[:2] != display[:2]
            or query[-2:] != display[-2:]
        ):
            continue
        query_middle = query[2:-2]
        display_middle = display[2:-2]
        if query_middle == display_middle or len(query_middle) < 4:
            continue
        if any(
            query_middle == display_middle[split:] + display_middle[:split]
            for split in range(2, len(display_middle) - 1)
        ):
            return True
    return False


def _has_excluded_term(
    exclusions: tuple[str, ...],
    content_terms: frozenset[str],
) -> bool:
    return any(
        normalized_exclusion
        and any(normalized_exclusion in term for term in content_terms)
        for exclusion in exclusions
        if (normalized_exclusion := _normalize(exclusion))
    )


def _projection_claim_binding(
    *,
    request: LaneRequest,
    subject_id: str,
    lookup_content_sha256: str,
    identifier_terms: frozenset[str],
    status: str,
) -> EvidenceClaimBinding:
    matched_identifier = next(
        (
            slot.value
            for slot in request.protected_slots
            if slot.kind == "exact_identifier"
            and slot.value is not None
            and _normalize(slot.value) in identifier_terms
        ),
        None,
    )
    if matched_identifier is not None:
        return EvidenceClaimBinding(
            subject_id=subject_id,
            predicate="exact_identifier",
            value=matched_identifier,
            status=status,
        )
    return EvidenceClaimBinding(
        subject_id=subject_id,
        predicate="canonical_projection",
        value=lookup_content_sha256,
        status=status,
    )


def _candidate_from_document(
    *,
    request: LaneRequest,
    bundle: IsolatedReleaseBundle,
    publication: PublishedRelease,
    document: LookupProjectionDocument,
    display_name: str,
    identifier_terms: frozenset[str],
    lane: Literal["exact", "structured", "lexical"],
    adapter_version: str,
) -> RecallCandidate:
    domain = document.domain
    decision_id = document.eligibility_decision_id
    if domain is None or decision_id is None:
        raise IndexProjectionIntegrityError(
            "public lookup document lacks domain or eligibility lineage"
        )
    trace = LocalProjectionTrace(
        target_id=bundle.index_target.target_id,
        target_marker_sha256=bundle.index_target.marker_sha256,
        manifest_sha256=bundle.manifest.manifest_sha256,
        index_result_content_sha256=bundle.index_result.content_sha256,
        document_id=document.document_id,
        canonical_object_id=document.canonical_object_id,
        release_id=document.release_id,
        domain=domain,
        projection_id=document.projection_id,
        projection_scope="public_domain",
        path="exact_lookup",
        execution_lane=lane,
        projection_view=document.projection_view.value,
        projection_version=document.projection_version,
        schema_version=document.schema_version,
        eligibility_policy_version=document.eligibility_policy_version,
        eligibility_decision_id=decision_id,
        eligibility_outcome=document.eligibility_outcome,
        eligibility_limitations=document.eligibility_limitations,
        source_projection_content_sha256=(document.source_projection_content_sha256),
        lookup_content_sha256=document.lookup_content_sha256,
        source_evidence_ids=document.source_evidence_ids,
        publication_verification_evidence_ids=tuple(
            sorted(publication.verification_evidence_ids)
        ),
    )
    evidence = EvidenceItem(
        evidence_id=trace.evidence_id,
        object_id=document.canonical_object_id,
        domain=domain,
        lane=lane,
        source_nature="local",
        source_locator=_local_projection_locator(trace),
        snippet=document.lookup_content,
        score=1.0,
        source_authority="canonical_release",
        claim_binding=_projection_claim_binding(
            request=request,
            subject_id=document.canonical_object_id,
            lookup_content_sha256=document.lookup_content_sha256,
            identifier_terms=identifier_terms,
            status=document.eligibility_outcome,
        ),
        local_projection_trace=trace,
    )
    return RecallCandidate(
        raw_candidate_id=trace.raw_candidate_id,
        display_name=display_name,
        domain=domain,
        identity_kind="canonical",
        canonical_id=document.canonical_object_id,
        resolution_state="resolved",
        origin_public_evidence_ids=document.source_evidence_ids,
        query_view=request.query_view,
        lane=lane,
        attempt=1,
        release_id=document.release_id,
        adapter_version=adapter_version,
        raw_score=1.0,
        quality_flags=document.eligibility_limitations,
        evidence=(evidence,),
    )
