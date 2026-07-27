"""Typed query planning and evidence retrieval for the Canonical V2 read seam.

This module intentionally keeps provider and persistence concerns behind injected
ports.  Its public surface is the immutable planning/read contract plus two
ephemeral factories used by the synthetic acceptance harness.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from time import monotonic
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import (
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from .contracts import ContractModel


_ZERO_SHA256 = "0" * 64
_PUBLIC_DOMAINS = ("professor", "company", "paper", "patent")
_INFORMATION_CLASSES = frozenset({"A", "B", "C", "D", "E", "G"})
_SUPPORTED_LANES = frozenset(
    {
        "exact",
        "structured",
        "lexical",
        "vector",
        "relationship",
        "internal_reference",
        "web",
    }
)
_RELATIONSHIP_ENDPOINTS = {
    ("company_has_patent", "company_to_patent"): ("company", "patent"),
    ("company_has_patent", "patent_to_company"): ("patent", "company"),
    ("professor_authored_paper", "professor_to_paper"): ("professor", "paper"),
    ("professor_authored_paper", "paper_to_professor"): ("paper", "professor"),
    ("professor_company_role", "professor_to_company"): ("professor", "company"),
    ("professor_company_role", "company_to_professor"): ("company", "professor"),
    ("person_company_role", "person_to_company"): ("person", "company"),
    ("technology_company_relationship", "technology_to_company"): (
        "technology_route",
        "company",
    ),
}
_COMPANY_TO_PATENT_QUERY_PATH = (
    "company_has_patent",
    "company_to_patent",
    "company",
    "patent",
)
_PATENT_TO_COMPANY_QUERY_PATH = (
    "company_has_patent",
    "patent_to_company",
    "patent",
    "company",
)
_PROFESSOR_TO_PAPER_QUERY_PATH = (
    "professor_authored_paper",
    "professor_to_paper",
    "professor",
    "paper",
)
_PAPER_TO_PROFESSOR_QUERY_PATH = (
    "professor_authored_paper",
    "paper_to_professor",
    "paper",
    "professor",
)
_PROFESSOR_TO_COMPANY_QUERY_PATH = (
    "professor_company_role",
    "professor_to_company",
    "professor",
    "company",
)
_COMPANY_TO_PROFESSOR_QUERY_PATH = (
    "professor_company_role",
    "company_to_professor",
    "company",
    "professor",
)
_PUBLIC_RELATIONSHIP_QUERY_PATHS = frozenset(
    {
        _COMPANY_TO_PATENT_QUERY_PATH,
        _PATENT_TO_COMPANY_QUERY_PATH,
        _PROFESSOR_TO_PAPER_QUERY_PATH,
        _PAPER_TO_PROFESSOR_QUERY_PATH,
        _PROFESSOR_TO_COMPANY_QUERY_PATH,
        _COMPANY_TO_PROFESSOR_QUERY_PATH,
    }
)
_TECHNOLOGY_RELATIONSHIP_STATES = {
    "entity_discusses_or_mentions_technology": "discussion_or_mention",
    "entity_claims_adoption_of_technology": "claimed_adoption",
    "entity_demonstrates_use_of_technology": "demonstrated_use",
}


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class _ContentModel(ContractModel):
    """Immutable value whose hash binds its complete normalized content."""

    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def bind_content(self) -> _ContentModel:
        expected = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 == _ZERO_SHA256:
            object.__setattr__(self, "content_sha256", expected)
        elif self.content_sha256 != expected:
            raise ValueError("content_sha256 must bind the complete normalized value")
        return self


class InvalidRetrievalPlanError(ValueError):
    """A recorded plan proposal violated a server-owned planning invariant."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class MissingAmbiguityPolicyError(ValueError):
    """Ambiguity candidates require an explicitly injected policy."""


class KnowledgeReadIntegrityError(ValueError):
    """A read implementation rejected its bound release or physical evidence."""


class QueryPlanningPolicy(_ContentModel):
    policy_id: str
    policy_version: str
    public_domains: tuple[str, ...]
    supported_lanes: tuple[str, ...]
    supported_relationship_paths: tuple[tuple[str, str], ...]
    max_candidates: int = Field(ge=0)
    max_provider_calls: int = Field(ge=0)
    max_planning_attempts: int = Field(ge=0)
    official_web_domains: tuple[str, ...] = ()

    @field_validator("official_web_domains")
    @classmethod
    def validate_official_web_domains(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value or value != value.strip().lower() for value in values):
            raise ValueError(
                "official Web domains must be canonical non-empty host names"
            )
        if values != tuple(sorted(set(values))):
            raise ValueError("official Web domains must be sorted and unique")
        return values

    @model_serializer(mode="wrap")
    def serialize_optional_official_domains(self, handler: Any) -> Any:
        data = handler(self)
        if not self.official_web_domains:
            data.pop("official_web_domains", None)
        return data


class InstitutionCatalogEntry(ContractModel):
    canonical_id: str
    canonical_name: str
    aliases: tuple[str, ...] = ()


class InstitutionCatalog(_ContentModel):
    catalog_id: str
    catalog_version: str
    release_id: str
    entries: tuple[InstitutionCatalogEntry, ...]


class FiniteEnumerationUniverse(_ContentModel):
    universe_id: str
    release_id: str
    scope: str
    member_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    as_of: datetime


class EnumerationPlanningContext(ContractModel):
    requested: bool
    scope: str
    as_of: datetime
    finite_universe: FiniteEnumerationUniverse | None
    required_member_ids: tuple[str, ...] = ()


class CandidateDiscriminator(ContractModel):
    kind: str
    value: str
    evidence_ids: tuple[str, ...] = ()


class AmbiguityCandidate(_ContentModel):
    # S8 planning shape.
    candidate_id: str | None = None
    entity_type: str | None = None
    canonical_id: str | None = None
    display_name: str | None = None
    evidence_ids: tuple[str, ...] = ()
    evidence_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    protected_constraint_conflicts: tuple[str, ...] = ()
    discriminators: tuple[CandidateDiscriminator, ...] = ()
    # Already-Accepted S9 display/selection shape.
    handle_id: str | None = None
    discriminator: str | None = None
    viable: bool | None = None
    protected_constraint_conflict: bool | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> AmbiguityCandidate:
        planning_shape = any(
            value is not None
            for value in (
                self.candidate_id,
                self.entity_type,
                self.canonical_id,
                self.display_name,
                self.evidence_confidence,
                self.model_confidence,
            )
        ) or bool(self.protected_constraint_conflicts or self.discriminators)
        successor_shape = any(
            value is not None
            for value in (
                self.handle_id,
                self.discriminator,
                self.viable,
                self.protected_constraint_conflict,
            )
        )
        if planning_shape == successor_shape:
            raise ValueError("ambiguity candidate must use exactly one complete shape")
        if planning_shape and any(
            value is None
            for value in (
                self.candidate_id,
                self.entity_type,
                self.canonical_id,
                self.display_name,
                self.evidence_confidence,
                self.model_confidence,
            )
        ):
            raise ValueError("planning ambiguity candidate shape is incomplete")
        if successor_shape and any(
            value is None
            for value in (
                self.handle_id,
                self.discriminator,
                self.viable,
                self.protected_constraint_conflict,
            )
        ):
            raise ValueError("successor ambiguity candidate shape is incomplete")
        return self


class AmbiguityPolicy(_ContentModel):
    policy_id: str
    policy_version: str
    entity_type: str
    minimum_evidence_count: int = Field(ge=0)
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    minimum_lead_margin: float = Field(ge=0.0, le=1.0)


class QueryPlanningRequest(ContractModel):
    request_id: str
    release_id: str
    original_query: str
    as_of: datetime
    displayed_entity_ids: tuple[str, ...] = ()
    displayed_entity_names: tuple[str, ...] = ()
    enumeration_context: EnumerationPlanningContext | None = None
    ambiguity_candidates: tuple[AmbiguityCandidate, ...] = ()
    original_query_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")
    ambiguity_candidate_manifest_sha256: str = Field(
        default=_ZERO_SHA256,
        pattern=r"^[0-9a-f]{64}$",
    )
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def bind_request(self) -> QueryPlanningRequest:
        if self.displayed_entity_names and len(self.displayed_entity_names) != len(
            self.displayed_entity_ids
        ):
            raise ValueError(
                "displayed entity names must align with displayed entity IDs"
            )
        if any(
            not name.strip() or name != name.strip()
            for name in self.displayed_entity_names
        ):
            raise ValueError("displayed entity names must be normalized and non-empty")
        query_hash = hashlib.sha256(self.original_query.encode("utf-8")).hexdigest()
        manifest_hash = _canonical_sha256(
            [
                (candidate.candidate_id, candidate.content_sha256)
                for candidate in self.ambiguity_candidates
            ]
        )
        if self.original_query_sha256 not in {_ZERO_SHA256, query_hash}:
            raise ValueError("original_query_sha256 does not bind original_query")
        if self.ambiguity_candidate_manifest_sha256 not in {
            _ZERO_SHA256,
            manifest_hash,
        }:
            raise ValueError("ambiguity candidate manifest does not bind candidates")
        object.__setattr__(self, "original_query_sha256", query_hash)
        object.__setattr__(self, "ambiguity_candidate_manifest_sha256", manifest_hash)
        expected = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 not in {_ZERO_SHA256, expected}:
            raise ValueError("content_sha256 does not bind planning request")
        object.__setattr__(self, "content_sha256", expected)
        return self


class QueryViewProposal(_ContentModel):
    view_id: str
    kind: str
    text: str
    original_query_sha256: str
    retained_protected_values: tuple[str, ...] = ()
    producer_kind: str
    producer_version: str
    protected_slot_ids: tuple[str, ...] = ()
    bound_entity_ids: tuple[str, ...] = ()
    bound_entity_names: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_bound_entities(self) -> QueryViewProposal:
        if self.bound_entity_names and len(self.bound_entity_names) != len(
            self.bound_entity_ids
        ):
            raise ValueError("bound entity names must align with bound entity IDs")
        if any(
            not name.strip() or name != name.strip() for name in self.bound_entity_names
        ):
            raise ValueError("bound entity names must be normalized and non-empty")
        return self


class RelationshipPathProposal(ContractModel):
    relationship_type_id: str
    direction: str
    source_type: str
    target_type: str


class MaterialQuestionPart(ContractModel):
    part_id: str
    text: str
    subject_id: str
    predicate: str
    requested_value: str
    material: bool = True
    answer_scoped: bool = False


class AssessmentIntent(ContractModel):
    """Open assessment goal plus explicit user-provided criteria for one turn."""

    kind: str = Field(min_length=1)
    user_criteria: tuple[str, ...] = ()

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("assessment intent kind must be non-empty")
        return normalized

    @field_validator("user_criteria", mode="before")
    @classmethod
    def normalize_user_criteria(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        normalized: list[str] = []
        for criterion in value:
            if not isinstance(criterion, str):
                return value
            stripped = criterion.strip()
            if not stripped:
                raise ValueError("assessment user criteria must be non-empty")
            normalized.append(stripped)
        if len(normalized) != len(set(normalized)):
            raise ValueError("assessment user criteria must be unique")
        return tuple(normalized)


class RecordedPlanningProposal(_ContentModel):
    proposal_id: str
    request_sha256: str
    schema_version: Literal["retrieval-plan-proposal-v1"]
    model_id: str
    prompt_version: str
    behavior_class: Literal["A", "B", "C", "D", "E", "F", "G", "control"]
    interaction_mode: Literal[
        "information_retrieval",
        "ordinary_refusal",
        "safety_guidance",
        "interface_control",
    ]
    domains: tuple[str, ...]
    lanes: tuple[str, ...]
    query_views: tuple[QueryViewProposal, ...] = ()
    relationship_paths: tuple[RelationshipPathProposal, ...] = ()
    material_parts: tuple[MaterialQuestionPart, ...] = ()
    max_candidates: int = Field(ge=0)
    max_provider_calls: int = Field(ge=0)
    enumeration_mode: (
        Literal[
            "exhaustive_bounded",
            "required_members",
            "representative",
        ]
        | None
    ) = None
    internal_reference_targets: tuple[Literal["person", "technology_route"], ...] = ()
    web_mode: Literal["disabled", "universal", "official_only"] | None = None
    allowed_web_domains: tuple[str, ...] = ()
    max_web_results: int = Field(default=0, ge=0)
    assessment_intent: AssessmentIntent | None = None
    professor_vector_view: Literal["identity", "research", "both"] | None = None

    @model_serializer(mode="wrap")
    def serialize_optional_intent(self, handler: Any) -> Any:
        data = handler(self)
        if not self.material_parts:
            data.pop("material_parts", None)
        if self.assessment_intent is None:
            data.pop("assessment_intent", None)
        if self.professor_vector_view is None:
            data.pop("professor_vector_view", None)
        return data

    @model_validator(mode="after")
    def validate_unique_plan_axes(self) -> RecordedPlanningProposal:
        if len(self.lanes) != len(set(self.lanes)):
            raise ValueError("planning proposal lanes must be unique")
        if len(self.domains) != len(set(self.domains)):
            raise ValueError("planning proposal domains must be unique")
        view_ids = tuple(view.view_id for view in self.query_views)
        if len(view_ids) != len(set(view_ids)):
            raise ValueError("planning proposal view IDs must be unique")
        part_ids = tuple(part.part_id for part in self.material_parts)
        if len(part_ids) != len(set(part_ids)):
            raise ValueError("planning proposal material-part IDs must be unique")
        if any(not part.material for part in self.material_parts):
            raise ValueError("planning proposal answer parts must be material")
        non_information_execution = bool(
            self.relationship_paths
            or self.internal_reference_targets
            or self.material_parts
            or self.enumeration_mode is not None
        )
        professor_vector_execution = (
            self.interaction_mode == "information_retrieval"
            and "professor" in self.domains
            and "vector" in self.lanes
        )
        if professor_vector_execution and self.professor_vector_view is None:
            raise ValueError(
                "Professor vector planning requires a typed projection view"
            )
        if not professor_vector_execution and self.professor_vector_view is not None:
            raise ValueError(
                "Professor vector view is valid only for Professor vector planning"
            )
        if self.interaction_mode == "information_retrieval":
            if (
                self.behavior_class not in _INFORMATION_CLASSES
                or not self.domains
                or "web" not in self.lanes
                or self.web_mode not in {None, "universal"}
                or self.max_provider_calls <= 0
                or (self.max_web_results <= 0 and self.max_candidates <= 0)
            ):
                raise ValueError(
                    "information proposal must use A-E/G with public domains and Universal Web"
                )
        elif self.interaction_mode == "ordinary_refusal":
            if (
                self.behavior_class != "F"
                or self.domains
                or self.lanes
                or self.web_mode not in {None, "disabled"}
                or self.allowed_web_domains
                or self.max_web_results
                or non_information_execution
            ):
                raise ValueError("ordinary refusal cannot contain retrieval execution")
        elif self.interaction_mode == "interface_control":
            if (
                self.behavior_class != "control"
                or self.domains
                or self.lanes
                or self.web_mode not in {None, "disabled"}
                or self.allowed_web_domains
                or self.max_web_results
                or non_information_execution
            ):
                raise ValueError("interface control cannot contain retrieval execution")
        else:
            if self.behavior_class != "F" or self.domains or non_information_execution:
                raise ValueError(
                    "safety guidance must remain an F no-public-domain policy"
                )
            if self.web_mode == "official_only":
                if (
                    self.lanes != ("web",)
                    or not self.allowed_web_domains
                    or self.max_provider_calls <= 0
                    or self.max_web_results <= 0
                ):
                    raise ValueError(
                        "official safety lookup requires one bounded allowlisted Web lane"
                    )
            elif (
                self.lanes
                or self.web_mode not in {None, "disabled"}
                or self.allowed_web_domains
                or self.max_web_results
            ):
                raise ValueError("default safety guidance cannot execute Web retrieval")
        if (
            self.assessment_intent is not None
            and self.interaction_mode != "information_retrieval"
        ):
            raise ValueError("assessment intent belongs only to information retrieval")
        return self


class ProtectedSlot(ContractModel):
    slot_id: str = ""
    kind: str
    value: str | None = None
    raw_text: str | None = None
    entity_ids: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def normalize_slot(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        raw_text = data.get("raw_text")
        normalized = data.get("value")
        if raw_text is None:
            raw_text = normalized or ""
            data["raw_text"] = raw_text
        if normalized is None:
            normalized = raw_text
            data["value"] = normalized
        if not data.get("slot_id"):
            identity = {
                "kind": data.get("kind"),
                "value": normalized,
                "entity_ids": list(data.get("entity_ids", ())),
            }
            data["slot_id"] = f"protected-slot:sha256:{_canonical_sha256(identity)}"
        return data


class StructuredConstraints(ContractModel):
    displayed_entity_ids: tuple[str, ...] = ()
    geography: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()


class WebSearchPolicy(ContractModel):
    mode: Literal["disabled", "universal", "official_only"]
    max_provider_calls: int = Field(default=0, ge=0)
    timeout_ms: int = Field(default=0, ge=0)
    max_results: int = Field(default=0, ge=0)
    allowed_domains: tuple[str, ...] = ()


class EnumerationPolicy(ContractModel):
    mode: str
    scope: str
    as_of: datetime
    finite_universe_id: str | None = None
    eligible_member_ids: tuple[str, ...] = ()
    required_member_ids: tuple[str, ...] = ()
    exhaustive: bool = False
    continuation_state: str = "available"
    # S8S compatibility names.
    finite_universe_source: str | None = None
    finite_universe_ids: tuple[str, ...] = ()


class PlanningTrace(ContractModel):
    proposal_id: str
    proposal_sha256: str


class PlanningReleaseBinding(_ContentModel):
    release_id: str = Field(min_length=1)
    publication_state: Literal["active", "rolled_back"]
    published_release_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_verification_evidence_ids: tuple[str, ...]
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_projection_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_projection_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_projection_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    internal_reference_projection_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    institution_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("publication_verification_evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values or values != tuple(sorted(set(values))):
            raise ValueError(
                "publication verification evidence IDs must be non-empty and sorted"
            )
        return values


class InstitutionOccurrence(ContractModel):
    raw_text: str
    start: int
    end: int


class InstitutionCandidate(ContractModel):
    canonical_id: str
    canonical_name: str


class InstitutionSlot(ContractModel):
    resolution_state: str
    canonical_id: str | None
    candidate_ids: tuple[str, ...] = ()
    occurrences: tuple[InstitutionOccurrence, ...]
    catalog_sha256: str
    catalog_version: str
    release_id: str
    candidates: tuple[InstitutionCandidate, ...] = ()


class RewritePolicy(ContractModel):
    generic_topic_stopwords: tuple[str, ...] = ()


class LaneQuery(ContractModel):
    lane: str
    release_id: str
    catalog_sha256: str
    pure_topic_text: str
    query_text: str
    institution_constraint_ids: tuple[str, ...] = ()


class AmbiguityCandidateTrace(ContractModel):
    candidate_id: str
    canonical_id: str | None
    display_name: str | None
    candidate_sha256: str
    evidence_ids: tuple[str, ...]
    evidence_count: int
    evidence_confidence: float
    model_confidence: float | None = None
    protected_constraint_conflicts: tuple[str, ...] = ()
    eligible: bool
    rejection_reason: str | None
    discriminators: tuple[CandidateDiscriminator, ...] = ()


class AmbiguityDecision(_ContentModel):
    # S8 planner/handoff shape.
    mode: str | None = None
    selected_canonical_id: str | None = None
    reason_code: str | None = None
    policy_id: str | None = None
    policy_version: str
    policy_sha256: str | None = None
    request_sha256: str | None = None
    candidate_manifest_sha256: str | None = None
    candidate_traces: tuple[AmbiguityCandidateTrace, ...] = ()
    qualifying_candidate_ids: tuple[str, ...] = ()
    viable_alternative_ids: tuple[str, ...] = ()
    observed_lead_margin: float | None = None
    # Already-Accepted S9 shape.
    decision_id: str | None = None
    outcome: str | None = None
    candidates: tuple[AmbiguityCandidate, ...] = ()
    selected_handle_id: str | None = None
    viable_alternative_handle_ids: tuple[str, ...] = ()
    decision_trace_id: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> AmbiguityDecision:
        planning_shape = any(
            value is not None
            for value in (
                self.mode,
                self.selected_canonical_id,
                self.reason_code,
                self.policy_id,
                self.policy_sha256,
                self.request_sha256,
                self.candidate_manifest_sha256,
                self.observed_lead_margin,
            )
        ) or bool(
            self.candidate_traces
            or self.qualifying_candidate_ids
            or self.viable_alternative_ids
        )
        successor_shape = any(
            value is not None
            for value in (
                self.decision_id,
                self.outcome,
                self.selected_handle_id,
                self.decision_trace_id,
            )
        ) or bool(self.candidates or self.viable_alternative_handle_ids)
        if planning_shape == successor_shape:
            raise ValueError("ambiguity decision must use exactly one complete shape")
        if planning_shape and any(
            value is None
            for value in (
                self.mode,
                self.reason_code,
                self.policy_id,
                self.policy_sha256,
                self.request_sha256,
                self.candidate_manifest_sha256,
            )
        ):
            raise ValueError("planning ambiguity decision shape is incomplete")
        if successor_shape and any(
            value is None
            for value in (
                self.decision_id,
                self.outcome,
                self.decision_trace_id,
            )
        ):
            raise ValueError("successor ambiguity decision shape is incomplete")
        return self


class InternalReferenceFact(_ContentModel):
    field: str
    value: str
    evidence_ids: tuple[str, ...]


class PersonReferenceRecord(_ContentModel):
    reference_id: str
    release_id: str
    resolution_state: str
    canonical_person_id: str | None
    public_domain_evidence_ids: tuple[str, ...]
    typed_facts: tuple[InternalReferenceFact, ...]


class TechnologyRouteRecord(_ContentModel):
    reference_id: str
    release_id: str
    canonical_route_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    definition_evidence_ids: tuple[str, ...]


class ReferenceTrace(ContractModel):
    reference_id: str
    resolution_state: str
    failed_filter_fields: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    eligible_for_identity_filter: bool = False
    eligible_for_traversal: bool = False


class InternalReferenceQuery(ContractModel):
    reference_type: str
    release_id: str
    typed_filters: tuple[InternalReferenceFact, ...] = ()
    eligible_reference_ids: tuple[str, ...] = ()
    excluded_reference_ids: tuple[str, ...] = ()
    originating_public_evidence_ids: tuple[str, ...] = ()
    nonmatching_reference_traces: tuple[ReferenceTrace, ...] = ()
    unresolved_reference_traces: tuple[ReferenceTrace, ...] = ()
    reference_content_sha256s: tuple[tuple[str, str], ...] = ()
    public_population: bool = False
    canonical_route_ids: tuple[str, ...] = ()
    resolved_aliases: tuple[tuple[str, str], ...] = ()
    relationship_states: tuple[str, ...] = ()
    scope: str | None = None
    as_of: datetime | None = None
    definition_evidence_ids: tuple[str, ...] = ()
    route_content_sha256s: tuple[tuple[str, str], ...] = ()
    definition_evidence_required: bool = False
    relationship_evidence_required: bool = False
    allowed_state_promotions: tuple[str, ...] = ()
    state_semantics: tuple[tuple[str, str], ...] = ()
    enumeration_policy: EnumerationPolicy | None = None


class UnresolvedTechnologyTerm(ContractModel):
    raw_text: str
    canonical_route_id: str | None
    search_view_id: str
    gap_reason: str


class SupplementalBudget(ContractModel):
    max_wall_time_ms: int = Field(ge=0)
    max_provider_calls: int = Field(ge=0)
    max_retries: int = Field(ge=0)
    max_cost_units: float = Field(ge=0.0)


class WebSnapshotPayload(ContractModel):
    snapshot_id: str
    content: bytes


class WebHandleReplay(ContractModel):
    handle: WebEntityHandle
    snapshot_payloads: tuple[WebSnapshotPayload, ...]
    observed_live_content_sha256: str
    replayed_at: datetime


class RetrievalPlan(_ContentModel):
    plan_id: str = "retrieval-plan:unspecified"
    plan_version: str
    request_sha256: str | None = None
    original_query: str
    behavior_class: str
    interaction_mode: str = "information_retrieval"
    release_id: str
    as_of: datetime | None = None
    domains: tuple[str, ...]
    protected_slots: tuple[ProtectedSlot, ...]
    lanes: tuple[str, ...]
    max_candidates: int = Field(ge=0)
    web_required: bool
    web_policy: WebSearchPolicy = WebSearchPolicy(mode="disabled")
    freshness_material: bool = False
    query_views: tuple[QueryViewProposal, ...] = ()
    relationship_paths: tuple[RelationshipPathProposal, ...] = ()
    structured_constraints: StructuredConstraints = StructuredConstraints()
    enumeration_policy: EnumerationPolicy | None = None
    material_parts: tuple[MaterialQuestionPart, ...] = ()
    supplemental_budget: SupplementalBudget | None = None
    retained_web_handles: tuple[WebEntityHandle, ...] = ()
    web_handle_replays: tuple[WebHandleReplay, ...] = ()
    handle_operation: str | None = None
    session_id: str | None = None
    planning_trace: PlanningTrace | None = None
    release_binding: PlanningReleaseBinding | None = None
    assessment_intent: AssessmentIntent | None = None
    professor_vector_view: Literal["identity", "research", "both"] | None = None
    allowed_operations: tuple[str, ...] = ()
    institution_slots: tuple[InstitutionSlot, ...] = ()
    rewrite_policy: RewritePolicy = RewritePolicy()
    pure_topic_text: str | None = None
    lane_queries: tuple[LaneQuery, ...] = ()
    ambiguity_decision: AmbiguityDecision | None = None
    internal_reference_queries: tuple[InternalReferenceQuery, ...] = ()
    unresolved_technology_terms: tuple[UnresolvedTechnologyTerm, ...] = ()

    @model_serializer(mode="wrap")
    def serialize_optional_planning_fields(self, handler: Any) -> Any:
        data = handler(self)
        if self.release_binding is None:
            data.pop("release_binding", None)
        if self.assessment_intent is None:
            data.pop("assessment_intent", None)
        if self.professor_vector_view is None:
            data.pop("professor_vector_view", None)
        return data

    @model_validator(mode="after")
    def validate_ambiguity_execution_gate(self) -> RetrievalPlan:
        if len(self.lanes) != len(set(self.lanes)):
            raise ValueError("retrieval plan lanes must be unique")
        if any(lane not in _SUPPORTED_LANES for lane in self.lanes):
            raise ValueError("retrieval plan contains an unsupported lane")
        if any(domain not in _PUBLIC_DOMAINS for domain in self.domains):
            raise ValueError("retrieval plan contains a non-public domain")
        lane_query_lanes = tuple(query.lane for query in self.lane_queries)
        if len(lane_query_lanes) != len(set(lane_query_lanes)):
            raise ValueError("retrieval plan lane queries must have unique lanes")
        if any(query.release_id != self.release_id for query in self.lane_queries):
            raise ValueError("retrieval plan lane query uses another release")
        if any(query.lane not in self.lanes for query in self.lane_queries):
            raise ValueError("retrieval plan lane query does not belong to the plan")
        if self.release_binding is not None:
            if self.release_binding.release_id != self.release_id:
                raise ValueError(
                    "release binding must match the retrieval plan release"
                )
            if any(
                slot.release_id != self.release_id
                or slot.catalog_sha256
                != self.release_binding.institution_catalog_sha256
                for slot in self.institution_slots
            ):
                raise ValueError(
                    "institution slot must match the release-bound institution catalog"
                )
            if any(
                query.catalog_sha256 != self.release_binding.institution_catalog_sha256
                for query in self.lane_queries
            ):
                raise ValueError(
                    "lane query catalog must match the release-bound institution catalog"
                )
            if any(
                query.release_id != self.release_id
                for query in self.internal_reference_queries
            ):
                raise ValueError(
                    "internal reference query must match the release-bound plan release"
                )
            if any(
                query.public_population for query in self.internal_reference_queries
            ):
                raise ValueError(
                    "release-bound internal reference query cannot be a public population"
                )
        if (
            self.ambiguity_decision is not None
            and self.ambiguity_decision.mode == "blocking"
        ):
            if (
                self.interaction_mode != "blocking_clarification"
                or self.lanes
                or self.web_policy.mode != "disabled"
            ):
                raise ValueError(
                    "blocking ambiguity requires a no-lane blocking clarification plan"
                )
        planner_owned = any(
            value is not None
            for value in (
                self.planning_trace,
                self.release_binding,
                self.assessment_intent,
            )
        )
        professor_vector_execution = (
            self.interaction_mode == "information_retrieval"
            and "professor" in self.domains
            and "vector" in self.lanes
        )
        if (
            planner_owned
            and professor_vector_execution
            and self.professor_vector_view is None
        ):
            raise ValueError(
                "planner-owned Professor vector plan requires a typed projection view"
            )
        if not professor_vector_execution and self.professor_vector_view is not None:
            raise ValueError(
                "Professor vector view is valid only for Professor vector execution"
            )
        if not planner_owned:
            return self
        if self.web_required != ("web" in self.lanes):
            raise ValueError("planner-owned Web requirement must match its lanes")
        if self.freshness_material != ("web" in self.lanes):
            raise ValueError("planner-owned freshness requirement must match its lanes")
        if self.interaction_mode == "handle_replay":
            session_id = self.session_id
            replay_handles = tuple(replay.handle for replay in self.web_handle_replays)
            if (
                self.lanes
                or self.web_required
                or self.freshness_material
                or self.web_policy != WebSearchPolicy(mode="disabled")
                or self.assessment_intent is not None
                or self.material_parts
                or self.release_binding is None
                or session_id is None
                or not session_id.strip()
                or any(
                    handle.session_id != session_id
                    for handle in (*self.retained_web_handles, *replay_handles)
                )
            ):
                raise ValueError(
                    "planner-owned handle replay must be lane-free, disabled-Web, "
                    "non-assessment, and session-bound"
                )
            return self
        if self.interaction_mode == "blocking_clarification":
            if (
                self.behavior_class not in _INFORMATION_CLASSES
                or self.lanes
                or self.web_policy.mode != "disabled"
                or self.web_required
            ):
                raise ValueError(
                    "server-derived blocking clarification must disable execution"
                )
            return self
        if self.interaction_mode == "information_retrieval":
            if (
                self.behavior_class not in _INFORMATION_CLASSES
                or not self.domains
                or "web" not in self.lanes
                or self.web_policy.mode != "universal"
            ):
                raise ValueError(
                    "planner-owned information plan must use A-E/G and Universal Web"
                )
        elif self.interaction_mode == "ordinary_refusal":
            if (
                self.behavior_class != "F"
                or self.domains
                or self.lanes
                or self.web_policy.mode != "disabled"
                or self.assessment_intent is not None
                or self.material_parts
            ):
                raise ValueError("planner-owned refusal cannot execute retrieval")
        elif self.interaction_mode == "interface_control":
            if (
                self.behavior_class != "control"
                or self.domains
                or self.lanes
                or self.web_policy.mode != "disabled"
                or self.assessment_intent is not None
                or self.material_parts
            ):
                raise ValueError(
                    "planner-owned interface control cannot execute retrieval"
                )
        elif self.interaction_mode == "safety_guidance":
            if (
                self.behavior_class != "F"
                or self.domains
                or self.assessment_intent is not None
                or self.material_parts
            ):
                raise ValueError(
                    "planner-owned safety guidance must remain F and non-assessment"
                )
            if self.web_policy.mode == "official_only":
                if (
                    self.lanes != ("web",)
                    or not self.web_policy.allowed_domains
                    or self.web_policy.max_provider_calls <= 0
                    or self.web_policy.max_results <= 0
                    or self.allowed_operations != ("official_policy_lookup",)
                ):
                    raise ValueError(
                        "planner-owned official safety lookup must remain bounded and allowlisted"
                    )
            elif (
                self.lanes
                or self.web_policy.mode != "disabled"
                or self.allowed_operations
            ):
                raise ValueError("planner-owned default safety guidance cannot use Web")
        else:
            raise ValueError("planner-owned plan has an unsupported interaction mode")
        return self


class EvidenceClaimBinding(ContractModel):
    subject_id: str
    predicate: str
    value: str
    status: str | None = None


class WebEvidenceSnapshot(ContractModel):
    snapshot_id: str
    content_sha256: str
    retrieved_at: datetime
    byte_length: int


class LocalProjectionTrace(ContractModel):
    """Content-bound lineage for one public local projection evidence item."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: str = Field(min_length=1)
    canonical_object_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    domain: Literal["company", "paper", "patent", "professor"]
    projection_id: str = Field(min_length=1)
    projection_scope: Literal["public_domain"] = "public_domain"
    path: Literal["exact_lookup"] = "exact_lookup"
    execution_lane: Literal["exact", "structured", "lexical"] = "exact"
    projection_view: str = Field(min_length=1)
    projection_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    eligibility_policy_version: str = Field(min_length=1)
    eligibility_decision_id: str = Field(min_length=1)
    eligibility_outcome: Literal["admitted", "limited"]
    eligibility_limitations: tuple[str, ...] = ()
    source_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lookup_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence_ids: tuple[str, ...] = Field(min_length=1)
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "eligibility_limitations",
        "source_evidence_ids",
        "publication_verification_evidence_ids",
    )
    @classmethod
    def validate_sorted_unique_lineage(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value for value in values):
            raise ValueError("local projection lineage values must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError(
                "local projection lineage values must be sorted and unique"
            )
        return values

    @model_validator(mode="after")
    def bind_trace(self) -> LocalProjectionTrace:
        if self.eligibility_outcome == "limited" and not self.eligibility_limitations:
            raise ValueError("limited local projection requires a visible limitation")
        lineage = self.model_dump(
            mode="json",
            exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
        )
        identity_lineage = dict(lineage)
        if self.execution_lane == "exact":
            identity_lineage.pop("execution_lane")
        expected_candidate_id = (
            f"local-exact-candidate:sha256:{_canonical_sha256(identity_lineage)}"
        )
        if self.raw_candidate_id not in {"", expected_candidate_id}:
            raise ValueError("raw_candidate_id does not bind local projection lineage")
        object.__setattr__(self, "raw_candidate_id", expected_candidate_id)
        expected_evidence_id = (
            "local-projection-evidence:sha256:"
            f"{_canonical_sha256((identity_lineage, expected_candidate_id))}"
        )
        if self.evidence_id not in {"", expected_evidence_id}:
            raise ValueError("evidence_id does not bind local projection lineage")
        object.__setattr__(self, "evidence_id", expected_evidence_id)
        content = self.model_dump(mode="json", exclude={"content_sha256"})
        if self.execution_lane == "exact":
            content.pop("execution_lane")
        expected_content_sha256 = _canonical_sha256(content)
        if self.content_sha256 not in {_ZERO_SHA256, expected_content_sha256}:
            raise ValueError("content_sha256 does not bind local projection trace")
        object.__setattr__(self, "content_sha256", expected_content_sha256)
        return self


class LocalVectorTrace(ContractModel):
    """Content-bound lineage for one public local vector evidence item."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    point_id: str = Field(min_length=1)
    canonical_object_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    domain: Literal["company", "paper", "patent", "professor"]
    projection_id: str = Field(min_length=1)
    projection_scope: Literal["public_domain"] = "public_domain"
    path: Literal["semantic_recall"] = "semantic_recall"
    execution_lane: Literal["vector"] = "vector"
    projection_view: str = Field(min_length=1)
    projection_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    eligibility_policy_version: str = Field(min_length=1)
    eligibility_decision_id: str = Field(min_length=1)
    eligibility_outcome: Literal["admitted", "limited"]
    eligibility_limitations: tuple[str, ...] = ()
    source_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedded_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence_ids: tuple[str, ...] = Field(min_length=1)
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    lane_query_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_embedding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    similarity_score: float = Field(ge=-1.0, le=1.0)
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "eligibility_limitations",
        "source_evidence_ids",
        "publication_verification_evidence_ids",
    )
    @classmethod
    def validate_sorted_unique_lineage(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value for value in values):
            raise ValueError("local vector lineage values must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError("local vector lineage values must be sorted and unique")
        return values

    @field_validator("similarity_score")
    @classmethod
    def validate_finite_similarity(cls, value: float) -> float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("local vector similarity score must be numeric")
        if not float("-inf") < float(value) < float("inf"):
            raise ValueError("local vector similarity score must be finite")
        return value

    @model_validator(mode="after")
    def bind_trace(self) -> LocalVectorTrace:
        if self.eligibility_outcome == "limited" and not self.eligibility_limitations:
            raise ValueError(
                "limited local vector evidence requires a visible limitation"
            )
        lineage = self.model_dump(
            mode="json",
            exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
        )
        expected_candidate_id = (
            f"local-vector-candidate:sha256:{_canonical_sha256(lineage)}"
        )
        if self.raw_candidate_id not in {"", expected_candidate_id}:
            raise ValueError("raw_candidate_id does not bind local vector lineage")
        object.__setattr__(self, "raw_candidate_id", expected_candidate_id)
        expected_evidence_id = (
            "local-vector-evidence:sha256:"
            f"{_canonical_sha256((lineage, expected_candidate_id))}"
        )
        if self.evidence_id not in {"", expected_evidence_id}:
            raise ValueError("evidence_id does not bind local vector lineage")
        object.__setattr__(self, "evidence_id", expected_evidence_id)
        content = self.model_dump(mode="json", exclude={"content_sha256"})
        expected_content_sha256 = _canonical_sha256(content)
        if self.content_sha256 not in {_ZERO_SHA256, expected_content_sha256}:
            raise ValueError("content_sha256 does not bind local vector trace")
        object.__setattr__(self, "content_sha256", expected_content_sha256)
        return self


class LocalInternalReferenceTrace(ContractModel):
    """Content-bound internal claim plus one separate public-origin locator."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    projection_id: str = Field(min_length=1)
    projection_scope: Literal["internal_auxiliary"] = "internal_auxiliary"
    reference_type: Literal["person", "technology_route"]
    internal_reference_id: str = Field(min_length=1)
    internal_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_record_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    internal_lookup_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    internal_lookup_source_evidence_ids: tuple[str, ...] = Field(min_length=1)
    public_origin_domain: Literal["company", "paper", "patent", "professor"]
    public_origin_canonical_id: str = Field(min_length=1)
    public_origin_anchor_id: str = Field(min_length=1)
    public_origin_anchor_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_origin_root_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lane_request_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_subject_id: str = Field(min_length=1)
    claim_predicate: str = Field(min_length=1)
    claim_value: str = Field(min_length=1)
    claim_evidence_ids: tuple[str, ...] = Field(min_length=1)
    matched_filter_facts: tuple[InternalReferenceFact, ...] = ()
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    snippet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Literal["internal_reference_lookup"] = "internal_reference_lookup"
    execution_lane: Literal["internal_reference"] = "internal_reference"
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "internal_lookup_source_evidence_ids",
        "claim_evidence_ids",
        "publication_verification_evidence_ids",
    )
    @classmethod
    def validate_sorted_unique_lineage(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value for value in values):
            raise ValueError("internal reference lineage values must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError(
                "internal reference lineage values must be sorted and unique"
            )
        return values

    @model_validator(mode="after")
    def bind_trace(self) -> LocalInternalReferenceTrace:
        if self.reference_type == "person":
            expected_fact_evidence = tuple(
                sorted(
                    {
                        evidence_id
                        for fact in self.matched_filter_facts
                        for evidence_id in fact.evidence_ids
                    }
                )
            )
            if (
                not self.matched_filter_facts
                or self.claim_subject_id != self.internal_reference_id
                or self.claim_predicate != "internal_person_filter_match"
                or self.claim_value != self.internal_projection_content_sha256
                or self.claim_evidence_ids != expected_fact_evidence
            ):
                raise ValueError("Person internal reference trace claim differs")
        elif (
            self.matched_filter_facts
            or self.claim_subject_id != self.internal_reference_id
            or self.claim_predicate != "definition"
        ):
            raise ValueError("Technology internal reference trace claim differs")

        lineage = self.model_dump(
            mode="json",
            exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
        )
        candidate_lineage = dict(lineage)
        candidate_lineage.pop("public_origin_anchor_id")
        candidate_lineage.pop("public_origin_anchor_content_sha256")
        expected_candidate_id = (
            "local-internal-reference-candidate:sha256:"
            f"{_canonical_sha256(candidate_lineage)}"
        )
        if self.raw_candidate_id not in {"", expected_candidate_id}:
            raise ValueError(
                "raw_candidate_id does not bind internal reference lineage"
            )
        object.__setattr__(self, "raw_candidate_id", expected_candidate_id)
        expected_evidence_id = (
            "local-internal-reference-evidence:sha256:"
            f"{_canonical_sha256((lineage, expected_candidate_id))}"
        )
        if self.evidence_id not in {"", expected_evidence_id}:
            raise ValueError("evidence_id does not bind internal reference lineage")
        object.__setattr__(self, "evidence_id", expected_evidence_id)
        content = self.model_dump(mode="json", exclude={"content_sha256"})
        expected_content_sha256 = _canonical_sha256(content)
        if self.content_sha256 not in {_ZERO_SHA256, expected_content_sha256}:
            raise ValueError("content_sha256 does not bind internal reference trace")
        object.__setattr__(self, "content_sha256", expected_content_sha256)
        return self


class LocalRelationshipTrace(ContractModel):
    """Content-bound Product-to-Technology proof with a public Company locator."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    release_id: str = Field(min_length=1)
    lane_request_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_projection_run_id: str = Field(min_length=1)
    relationship_projection_schema_version: str = Field(min_length=1)
    relationship_registry_version: str = Field(min_length=1)
    relationship_registry_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_snapshot_as_of: datetime
    query_as_of: datetime
    query_relationship_type_id: Literal["technology_company_relationship"] = (
        "technology_company_relationship"
    )
    query_direction: Literal["technology_to_company"] = "technology_to_company"
    query_source_type: Literal["technology_route"] = "technology_route"
    query_target_type: Literal["company"] = "company"
    technology_route_id: str = Field(min_length=1)
    technology_route_projection_id: str = Field(min_length=1)
    technology_route_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_relationship_id: str = Field(min_length=1)
    current_relationship_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_id: str = Field(min_length=1)
    relationship_decision_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_state: Literal["accepted"] = "accepted"
    relationship_type_id: str = Field(min_length=1)
    relationship_type_version: str = Field(min_length=1)
    relationship_source_endpoint: str = Field(min_length=1)
    relationship_source_endpoint_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_source_parent_canonical_identity_ref: str = Field(min_length=1)
    relationship_target_endpoint: str = Field(min_length=1)
    relationship_target_endpoint_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_role_bindings: tuple[tuple[str, str], ...] = Field(min_length=1)
    selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    relationship_valid_from: Any | None = None
    relationship_valid_to: Any | None = None
    relationship_state: Literal[
        "discussion_or_mention",
        "claimed_adoption",
        "demonstrated_use",
    ]
    retained_reference_id: str = Field(min_length=1)
    retained_reference_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retained_assertion_id: str = Field(min_length=1)
    retained_source_record_id: str = Field(min_length=1)
    public_assertion_id: str = Field(min_length=1)
    public_assertion_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_record_id: str = Field(min_length=1)
    technology_anchor_id: str = Field(min_length=1)
    technology_anchor_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    technology_anchor_source_identity_id: str = Field(min_length=1)
    product_subobject_id: str = Field(min_length=1)
    product_subobject_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    root_company_id: str = Field(min_length=1)
    root_company_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    root_company_display_name: str = Field(min_length=1)
    path_eligibility_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    eligibility_decision_id: str = Field(min_length=1)
    eligibility_policy_id: str = Field(min_length=1)
    eligibility_policy_version: str = Field(min_length=1)
    eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    eligibility_policy_effective_at: datetime
    eligibility_outcome: Literal["admitted", "limited"]
    eligibility_limitations: tuple[str, ...] = ()
    eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    eligibility_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    claim_subject_id: str = Field(min_length=1)
    claim_predicate: str = Field(min_length=1)
    claim_value: str = Field(min_length=1)
    claim_status: str = Field(min_length=1)
    snippet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Literal["relationship_traversal"] = "relationship_traversal"
    execution_lane: Literal["relationship"] = "relationship"
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "publication_verification_evidence_ids",
        "selected_evidence_refs",
        "eligibility_limitations",
        "eligibility_hard_exclusion_codes",
        "eligibility_supporting_assertion_ids",
    )
    @classmethod
    def validate_sorted_unique_lineage(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value for value in values):
            raise ValueError("relationship lineage values must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError("relationship lineage values must be sorted and unique")
        return values

    @field_validator("relationship_role_bindings")
    @classmethod
    def validate_role_bindings(
        cls,
        values: tuple[tuple[str, str], ...],
    ) -> tuple[tuple[str, str], ...]:
        if any(not role or not value for role, value in values):
            raise ValueError("relationship role bindings must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError("relationship role bindings must be sorted and unique")
        return values

    @model_validator(mode="after")
    def bind_trace(self) -> LocalRelationshipTrace:
        expected_state = _TECHNOLOGY_RELATIONSHIP_STATES.get(self.relationship_type_id)
        expected_route_ref = f"canonical:technology_route:{self.technology_route_id}"
        expected_company_ref = f"canonical:company:{self.root_company_id}"
        if (
            expected_state is None
            or self.relationship_state != expected_state
            or self.claim_status != expected_state
            or self.claim_predicate != self.relationship_type_id
        ):
            raise ValueError("relationship trace type/state/claim differs")
        if (
            self.technology_route_projection_id != self.technology_route_id
            or self.relationship_target_endpoint != expected_route_ref
            or self.claim_value != expected_route_ref
        ):
            raise ValueError("relationship trace Technology route differs")
        if (
            self.relationship_source_endpoint != self.product_subobject_id
            or self.claim_subject_id != self.product_subobject_id
            or self.relationship_source_parent_canonical_identity_ref
            != expected_company_ref
        ):
            raise ValueError("relationship trace requires one Product-scoped subject")
        if self.retained_reference_id not in self.selected_evidence_refs:
            raise ValueError("relationship trace retained reference was not selected")
        if (
            self.retained_assertion_id != self.public_assertion_id
            or self.retained_source_record_id != self.source_record_id
        ):
            raise ValueError("relationship trace retained source lineage differs")
        if self.eligibility_outcome == "limited":
            if not self.eligibility_limitations:
                raise ValueError(
                    "limited relationship eligibility requires visible limitations"
                )
        if self.eligibility_hard_exclusion_codes:
            raise ValueError("returned relationship cannot carry hard exclusions")

        lineage = self.model_dump(
            mode="json",
            exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
        )
        expected_candidate_id = (
            f"local-relationship-candidate:sha256:{_canonical_sha256(lineage)}"
        )
        if self.raw_candidate_id not in {"", expected_candidate_id}:
            raise ValueError("raw_candidate_id does not bind relationship lineage")
        object.__setattr__(self, "raw_candidate_id", expected_candidate_id)
        expected_evidence_id = (
            "local-relationship-evidence:sha256:"
            f"{_canonical_sha256((lineage, expected_candidate_id))}"
        )
        if self.evidence_id not in {"", expected_evidence_id}:
            raise ValueError("evidence_id does not bind relationship lineage")
        object.__setattr__(self, "evidence_id", expected_evidence_id)
        expected_content_sha256 = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 not in {_ZERO_SHA256, expected_content_sha256}:
            raise ValueError("content_sha256 does not bind relationship trace")
        object.__setattr__(self, "content_sha256", expected_content_sha256)
        return self


class LocalCanonicalRelationshipTrace(ContractModel):
    """Content-bound canonical Company-to-Patent traversal proof."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    release_id: str = Field(min_length=1)
    lane_request_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_enumeration_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    displayed_entity_ids: tuple[str, ...] = Field(min_length=1)
    displayed_company_id: str = Field(min_length=1)
    protected_slot_id: str = Field(min_length=1)
    protected_slot_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_as_of: datetime
    query_relationship_type_id: Literal["company_has_patent"] = "company_has_patent"
    query_direction: Literal["company_to_patent"] = "company_to_patent"
    query_source_type: Literal["company"] = "company"
    query_target_type: Literal["patent"] = "patent"
    relationship_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_projection_run_id: str = Field(min_length=1)
    relationship_projection_schema_version: str = Field(min_length=1)
    relationship_registry_version: str = Field(min_length=1)
    relationship_registry_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_snapshot_as_of: datetime
    canonical_relationship_id: str = Field(min_length=1)
    current_relationship_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_input_id: str = Field(min_length=1)
    relationship_decision_id: str = Field(min_length=1)
    relationship_decision_state: Literal["accepted"] = "accepted"
    relationship_type_id: Literal["patent_has_applicant"] = "patent_has_applicant"
    relationship_type_version: Literal["canonical-v2-relationship-v1"] = (
        "canonical-v2-relationship-v1"
    )
    relationship_source_endpoint: str = Field(min_length=1)
    relationship_target_endpoint: str = Field(min_length=1)
    relationship_role_bindings: tuple[tuple[str, str], ...] = Field(min_length=1)
    selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    relationship_valid_from: Any | None = None
    relationship_valid_to: Any | None = None
    projection_candidate_id: str = Field(min_length=1)
    projection_candidate_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_candidate_observed_at: datetime
    projection_candidate_source_event_time: datetime | None = None
    projection_candidate_assertion_input_id: str = Field(min_length=1)
    projection_candidate_decision_input_id: str = Field(min_length=1)
    typed_assertion_id: str = Field(min_length=1)
    typed_assertion_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    typed_assertion_observed_at: datetime
    typed_assertion_source_event_time: datetime | None = None
    typed_assertion_source_record_ref: str = Field(min_length=1)
    candidate_outcome_candidate_id: str = Field(min_length=1)
    candidate_outcome_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_outcome_retained_assertion_id: str = Field(min_length=1)
    candidate_outcome_decision_id: str = Field(min_length=1)
    candidate_outcome_projected_relationship_id: str = Field(min_length=1)
    typed_decision_id: str = Field(min_length=1)
    typed_decision_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    typed_decision_selected_assertion_ids: tuple[str, ...] = Field(min_length=1)
    typed_decision_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    current_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    retained_reference_id: str = Field(min_length=1)
    retained_reference_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retained_assertion_id: str = Field(min_length=1)
    retained_source_record_id: str = Field(min_length=1)
    public_assertion_id: str = Field(min_length=1)
    public_assertion_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_assertion_observed_at: datetime
    public_assertion_source_event_time: datetime | None = None
    source_record_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    company_stable_reference: str = Field(min_length=1)
    company_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_display_name: str = Field(min_length=1)
    patent_id: str = Field(min_length=1)
    patent_stable_reference: str = Field(min_length=1)
    patent_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_display_name: str = Field(min_length=1)
    applicant_subobject_id: str = Field(min_length=1)
    applicant_subobject_projection_content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    applicant_parent_patent_id: str = Field(min_length=1)
    applicant_canonical_company_id: str = Field(min_length=1)
    applicant_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    applicant_source_record_id: str = Field(min_length=1)
    company_path_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_traversal_directions: tuple[str, ...] = Field(min_length=1)
    company_relationship_decision_ids: tuple[str, ...] = Field(min_length=1)
    company_eligibility_decision_id: str = Field(min_length=1)
    company_eligibility_policy_id: str = Field(min_length=1)
    company_eligibility_policy_version: str = Field(min_length=1)
    company_eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_eligibility_outcome: Literal["admitted", "limited"]
    company_eligibility_limitations: tuple[str, ...] = ()
    company_eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    company_eligibility_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    patent_path_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_traversal_directions: tuple[str, ...] = Field(min_length=1)
    patent_relationship_decision_ids: tuple[str, ...] = Field(min_length=1)
    patent_eligibility_decision_id: str = Field(min_length=1)
    patent_eligibility_policy_id: str = Field(min_length=1)
    patent_eligibility_policy_version: str = Field(min_length=1)
    patent_eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_eligibility_outcome: Literal["admitted", "limited"]
    patent_eligibility_limitations: tuple[str, ...] = ()
    patent_eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    patent_eligibility_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    candidate_domain: Literal["patent"] = "patent"
    candidate_canonical_id: str = Field(min_length=1)
    candidate_display_name: str = Field(min_length=1)
    candidate_identity_kind: Literal["canonical"] = "canonical"
    candidate_resolution_state: Literal["resolved"] = "resolved"
    candidate_reference_type: None = None
    candidate_origin_public_evidence_ids: tuple[str, ...] = Field(min_length=1)
    candidate_quality_flags: tuple[str, ...] = ()
    candidate_raw_score: float = 1.0
    claim_subject_id: str = Field(min_length=1)
    claim_predicate: Literal["patent_has_applicant"] = "patent_has_applicant"
    claim_value: str = Field(min_length=1)
    claim_status: Literal["accepted"] = "accepted"
    relationship_state: Literal["accepted"] = "accepted"
    snippet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Literal["canonical_relationship_traversal"] = (
        "canonical_relationship_traversal"
    )
    execution_lane: Literal["relationship"] = "relationship"
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "publication_verification_evidence_ids",
        "displayed_entity_ids",
        "selected_evidence_refs",
        "typed_decision_selected_assertion_ids",
        "typed_decision_selected_evidence_refs",
        "current_selected_evidence_refs",
        "applicant_supporting_assertion_ids",
        "company_traversal_directions",
        "company_relationship_decision_ids",
        "company_eligibility_limitations",
        "company_eligibility_hard_exclusion_codes",
        "company_eligibility_supporting_assertion_ids",
        "patent_traversal_directions",
        "patent_relationship_decision_ids",
        "patent_eligibility_limitations",
        "patent_eligibility_hard_exclusion_codes",
        "patent_eligibility_supporting_assertion_ids",
        "candidate_origin_public_evidence_ids",
        "candidate_quality_flags",
    )
    @classmethod
    def validate_sorted_unique_canonical_lineage(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value for value in values):
            raise ValueError("canonical relationship lineage values must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError(
                "canonical relationship lineage values must be sorted and unique"
            )
        return values

    @field_validator("relationship_role_bindings")
    @classmethod
    def validate_canonical_role_bindings(
        cls,
        values: tuple[tuple[str, str], ...],
    ) -> tuple[tuple[str, str], ...]:
        if any(not role or not value for role, value in values):
            raise ValueError("canonical relationship role bindings must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError(
                "canonical relationship role bindings must be sorted and unique"
            )
        return values

    @model_validator(mode="after")
    def bind_canonical_relationship_trace(self) -> LocalCanonicalRelationshipTrace:
        expected_company_ref = f"canonical:company:{self.company_id}"
        expected_patent_ref = f"canonical:patent:{self.patent_id}"
        if (
            self.displayed_entity_ids != (self.company_id,)
            or self.displayed_company_id != self.company_id
            or self.company_stable_reference != expected_company_ref
            or self.patent_stable_reference != expected_patent_ref
        ):
            raise ValueError(
                "canonical relationship displayed/end-point identity differs"
            )
        if (
            self.relationship_source_endpoint != expected_patent_ref
            or self.relationship_target_endpoint != expected_company_ref
            or self.relationship_role_bindings != (("applicant", expected_company_ref),)
        ):
            raise ValueError(
                "canonical relationship Patent applicant orientation differs"
            )
        if (
            self.projection_candidate_assertion_input_id != self.typed_assertion_id
            or self.projection_candidate_decision_input_id
            != self.relationship_decision_input_id
            or self.candidate_outcome_candidate_id != self.projection_candidate_id
            or self.candidate_outcome_retained_assertion_id != self.typed_assertion_id
            or self.typed_assertion_id not in self.typed_decision_selected_assertion_ids
            or self.candidate_outcome_decision_id != self.typed_decision_id
            or self.candidate_outcome_projected_relationship_id
            != self.canonical_relationship_id
            or self.typed_decision_id != self.relationship_decision_id
        ):
            raise ValueError(
                "canonical relationship candidate/decision continuity differs"
            )
        if (
            self.retained_reference_id not in self.selected_evidence_refs
            or self.retained_reference_id
            not in self.typed_decision_selected_evidence_refs
            or self.retained_reference_id not in self.current_selected_evidence_refs
            or self.retained_assertion_id != self.public_assertion_id
            or self.typed_assertion_source_record_ref != self.retained_source_record_id
            or self.retained_source_record_id != self.source_record_id
            or self.source_record_id != self.applicant_source_record_id
        ):
            raise ValueError("canonical relationship retained source lineage differs")
        if (
            self.applicant_parent_patent_id != self.patent_id
            or self.applicant_canonical_company_id != self.company_id
            or self.public_assertion_id not in self.applicant_supporting_assertion_ids
        ):
            raise ValueError(
                "canonical relationship Patent applicant subobject differs"
            )
        if (
            self.company_traversal_directions != ("company_to_patent",)
            or self.patent_traversal_directions != ("patent_to_company",)
            or self.company_relationship_decision_ids
            != (self.relationship_decision_id,)
            or self.patent_relationship_decision_ids != (self.relationship_decision_id,)
            or self.company_eligibility_hard_exclusion_codes
            or self.patent_eligibility_hard_exclusion_codes
        ):
            raise ValueError("canonical relationship endpoint eligibility differs")
        if (
            self.company_eligibility_outcome == "limited"
            and not self.company_eligibility_limitations
        ) or (
            self.patent_eligibility_outcome == "limited"
            and not self.patent_eligibility_limitations
        ):
            raise ValueError(
                "limited canonical relationship eligibility must be visible"
            )
        expected_origin_ids = self.applicant_supporting_assertion_ids
        if (
            self.candidate_canonical_id != self.patent_id
            or self.candidate_display_name != self.patent_display_name
            or self.candidate_origin_public_evidence_ids != expected_origin_ids
            or self.claim_subject_id != expected_patent_ref
            or self.claim_value != expected_company_ref
        ):
            raise ValueError("canonical relationship candidate/claim differs")
        if self.query_as_of < self.relationship_snapshot_as_of:
            raise ValueError("canonical relationship query predates its snapshot")
        limitations = tuple(
            sorted(
                set(self.company_eligibility_limitations)
                | set(self.patent_eligibility_limitations)
            )
        )
        freshness_flags = ()
        if self.query_as_of > self.relationship_snapshot_as_of:
            canonical = (
                self.relationship_snapshot_as_of.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            freshness_flags = (f"relationship_snapshot_as_of:{canonical}",)
        expected_quality_flags = tuple(sorted({*limitations, *freshness_flags}))
        if self.candidate_quality_flags != expected_quality_flags:
            raise ValueError("canonical relationship candidate quality flags differ")
        if self.candidate_raw_score != 1.0:
            raise ValueError("canonical relationship candidate score differs")

        lineage = self.model_dump(
            mode="json",
            exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
        )
        expected_candidate_id = (
            "local-canonical-relationship-candidate:sha256:"
            f"{_canonical_sha256(lineage)}"
        )
        if self.raw_candidate_id not in {"", expected_candidate_id}:
            raise ValueError(
                "raw_candidate_id does not bind canonical relationship lineage"
            )
        object.__setattr__(self, "raw_candidate_id", expected_candidate_id)
        expected_evidence_id = (
            "local-canonical-relationship-evidence:sha256:"
            f"{_canonical_sha256((lineage, expected_candidate_id))}"
        )
        if self.evidence_id not in {"", expected_evidence_id}:
            raise ValueError("evidence_id does not bind canonical relationship lineage")
        object.__setattr__(self, "evidence_id", expected_evidence_id)
        expected_content_sha256 = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 not in {_ZERO_SHA256, expected_content_sha256}:
            raise ValueError(
                "content_sha256 does not bind canonical relationship trace"
            )
        object.__setattr__(self, "content_sha256", expected_content_sha256)
        return self


class LocalPatentCompanyRelationshipTrace(ContractModel):
    """Content-bound inverse Patent-to-Company applicant traversal proof."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    release_id: str = Field(min_length=1)
    lane_request_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_enumeration_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    displayed_entity_ids: tuple[str, ...] = Field(min_length=1)
    displayed_patent_id: str = Field(min_length=1)
    protected_slot_id: str = Field(min_length=1)
    protected_slot_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_as_of: datetime
    query_relationship_type_id: Literal["company_has_patent"] = "company_has_patent"
    query_direction: Literal["patent_to_company"] = "patent_to_company"
    query_source_type: Literal["patent"] = "patent"
    query_target_type: Literal["company"] = "company"
    relationship_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_projection_run_id: str = Field(min_length=1)
    relationship_projection_schema_version: str = Field(min_length=1)
    relationship_registry_version: str = Field(min_length=1)
    relationship_registry_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_snapshot_as_of: datetime
    canonical_relationship_id: str = Field(min_length=1)
    current_relationship_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_input_id: str = Field(min_length=1)
    relationship_decision_id: str = Field(min_length=1)
    relationship_decision_state: Literal["accepted"] = "accepted"
    relationship_type_id: Literal["patent_has_applicant"] = "patent_has_applicant"
    relationship_type_version: Literal["canonical-v2-relationship-v1"] = (
        "canonical-v2-relationship-v1"
    )
    relationship_source_endpoint: str = Field(min_length=1)
    relationship_target_endpoint: str = Field(min_length=1)
    relationship_role_bindings: tuple[tuple[str, str], ...] = Field(min_length=1)
    selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    relationship_valid_from: Any | None = None
    relationship_valid_to: Any | None = None
    projection_candidate_id: str = Field(min_length=1)
    projection_candidate_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_candidate_observed_at: datetime
    projection_candidate_source_event_time: datetime | None = None
    projection_candidate_assertion_input_id: str = Field(min_length=1)
    projection_candidate_decision_input_id: str = Field(min_length=1)
    typed_assertion_id: str = Field(min_length=1)
    typed_assertion_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    typed_assertion_observed_at: datetime
    typed_assertion_source_event_time: datetime | None = None
    typed_assertion_source_record_ref: str = Field(min_length=1)
    candidate_outcome_candidate_id: str = Field(min_length=1)
    candidate_outcome_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_outcome_retained_assertion_id: str = Field(min_length=1)
    candidate_outcome_decision_id: str = Field(min_length=1)
    candidate_outcome_projected_relationship_id: str = Field(min_length=1)
    typed_decision_id: str = Field(min_length=1)
    typed_decision_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    typed_decision_selected_assertion_ids: tuple[str, ...] = Field(min_length=1)
    typed_decision_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    current_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    retained_reference_id: str = Field(min_length=1)
    retained_reference_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retained_assertion_id: str = Field(min_length=1)
    retained_source_record_id: str = Field(min_length=1)
    public_assertion_id: str = Field(min_length=1)
    public_assertion_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_assertion_observed_at: datetime
    public_assertion_source_event_time: datetime | None = None
    source_record_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    company_stable_reference: str = Field(min_length=1)
    company_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_display_name: str = Field(min_length=1)
    patent_id: str = Field(min_length=1)
    patent_stable_reference: str = Field(min_length=1)
    patent_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_display_name: str = Field(min_length=1)
    applicant_subobject_id: str = Field(min_length=1)
    applicant_subobject_projection_content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    applicant_parent_patent_id: str = Field(min_length=1)
    applicant_canonical_company_id: str = Field(min_length=1)
    applicant_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    applicant_source_record_id: str = Field(min_length=1)
    company_path_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_traversal_directions: tuple[str, ...] = Field(min_length=1)
    company_relationship_decision_ids: tuple[str, ...] = Field(min_length=1)
    company_eligibility_decision_id: str = Field(min_length=1)
    company_eligibility_policy_id: str = Field(min_length=1)
    company_eligibility_policy_version: str = Field(min_length=1)
    company_eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_eligibility_outcome: Literal["admitted", "limited"]
    company_eligibility_limitations: tuple[str, ...] = ()
    company_eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    company_eligibility_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    patent_path_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_traversal_directions: tuple[str, ...] = Field(min_length=1)
    patent_relationship_decision_ids: tuple[str, ...] = Field(min_length=1)
    patent_eligibility_decision_id: str = Field(min_length=1)
    patent_eligibility_policy_id: str = Field(min_length=1)
    patent_eligibility_policy_version: str = Field(min_length=1)
    patent_eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    patent_eligibility_outcome: Literal["admitted", "limited"]
    patent_eligibility_limitations: tuple[str, ...] = ()
    patent_eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    patent_eligibility_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    candidate_domain: Literal["company"] = "company"
    candidate_canonical_id: str = Field(min_length=1)
    candidate_display_name: str = Field(min_length=1)
    candidate_identity_kind: Literal["canonical"] = "canonical"
    candidate_resolution_state: Literal["resolved"] = "resolved"
    candidate_reference_type: None = None
    candidate_origin_public_evidence_ids: tuple[str, ...] = Field(min_length=1)
    candidate_quality_flags: tuple[str, ...] = ()
    candidate_raw_score: float = 1.0
    claim_subject_id: str = Field(min_length=1)
    claim_predicate: Literal["patent_has_applicant"] = "patent_has_applicant"
    claim_value: str = Field(min_length=1)
    claim_status: Literal["accepted"] = "accepted"
    relationship_state: Literal["accepted"] = "accepted"
    snippet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Literal["patent_company_relationship_traversal"] = (
        "patent_company_relationship_traversal"
    )
    execution_lane: Literal["relationship"] = "relationship"
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "publication_verification_evidence_ids",
        "displayed_entity_ids",
        "selected_evidence_refs",
        "typed_decision_selected_assertion_ids",
        "typed_decision_selected_evidence_refs",
        "current_selected_evidence_refs",
        "applicant_supporting_assertion_ids",
        "company_traversal_directions",
        "company_relationship_decision_ids",
        "company_eligibility_limitations",
        "company_eligibility_hard_exclusion_codes",
        "company_eligibility_supporting_assertion_ids",
        "patent_traversal_directions",
        "patent_relationship_decision_ids",
        "patent_eligibility_limitations",
        "patent_eligibility_hard_exclusion_codes",
        "patent_eligibility_supporting_assertion_ids",
        "candidate_origin_public_evidence_ids",
        "candidate_quality_flags",
    )
    @classmethod
    def validate_sorted_unique_patent_company_lineage(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value for value in values):
            raise ValueError(
                "Patent-Company relationship lineage values must be non-empty"
            )
        if values != tuple(sorted(set(values))):
            raise ValueError(
                "Patent-Company relationship lineage values must be sorted and unique"
            )
        return values

    @field_validator("relationship_role_bindings")
    @classmethod
    def validate_patent_company_role_bindings(
        cls,
        values: tuple[tuple[str, str], ...],
    ) -> tuple[tuple[str, str], ...]:
        if any(not role or not value for role, value in values):
            raise ValueError(
                "Patent-Company relationship role bindings must be non-empty"
            )
        if values != tuple(sorted(set(values))):
            raise ValueError(
                "Patent-Company relationship role bindings must be sorted and unique"
            )
        return values

    @model_validator(mode="after")
    def bind_patent_company_relationship_trace(
        self,
    ) -> LocalPatentCompanyRelationshipTrace:
        expected_company_ref = f"canonical:company:{self.company_id}"
        expected_patent_ref = f"canonical:patent:{self.patent_id}"
        if (
            self.displayed_entity_ids != (self.patent_id,)
            or self.displayed_patent_id != self.patent_id
            or self.company_stable_reference != expected_company_ref
            or self.patent_stable_reference != expected_patent_ref
        ):
            raise ValueError("Patent-Company displayed/end-point identity differs")
        if (
            self.relationship_source_endpoint != expected_patent_ref
            or self.relationship_target_endpoint != expected_company_ref
            or self.relationship_role_bindings != (("applicant", expected_company_ref),)
        ):
            raise ValueError("Patent-Company applicant orientation differs")
        if (
            self.projection_candidate_assertion_input_id != self.typed_assertion_id
            or self.projection_candidate_decision_input_id
            != self.relationship_decision_input_id
            or self.candidate_outcome_candidate_id != self.projection_candidate_id
            or self.candidate_outcome_retained_assertion_id != self.typed_assertion_id
            or self.typed_assertion_id not in self.typed_decision_selected_assertion_ids
            or self.candidate_outcome_decision_id != self.typed_decision_id
            or self.candidate_outcome_projected_relationship_id
            != self.canonical_relationship_id
            or self.typed_decision_id != self.relationship_decision_id
        ):
            raise ValueError("Patent-Company candidate/decision continuity differs")
        if (
            self.retained_reference_id not in self.selected_evidence_refs
            or self.retained_reference_id
            not in self.typed_decision_selected_evidence_refs
            or self.retained_reference_id not in self.current_selected_evidence_refs
            or self.retained_assertion_id != self.public_assertion_id
            or self.typed_assertion_source_record_ref != self.retained_source_record_id
            or self.retained_source_record_id != self.source_record_id
            or self.source_record_id != self.applicant_source_record_id
        ):
            raise ValueError("Patent-Company retained source lineage differs")
        if (
            self.applicant_parent_patent_id != self.patent_id
            or self.applicant_canonical_company_id != self.company_id
            or self.public_assertion_id not in self.applicant_supporting_assertion_ids
        ):
            raise ValueError("Patent-Company applicant subobject differs")
        if (
            self.company_traversal_directions != ("company_to_patent",)
            or self.patent_traversal_directions != ("patent_to_company",)
            or self.company_relationship_decision_ids
            != (self.relationship_decision_id,)
            or self.patent_relationship_decision_ids != (self.relationship_decision_id,)
            or self.company_eligibility_hard_exclusion_codes
            or self.patent_eligibility_hard_exclusion_codes
        ):
            raise ValueError("Patent-Company endpoint eligibility differs")
        if (
            self.company_eligibility_outcome == "limited"
            and not self.company_eligibility_limitations
        ) or (
            self.patent_eligibility_outcome == "limited"
            and not self.patent_eligibility_limitations
        ):
            raise ValueError("limited Patent-Company eligibility must be visible")
        expected_origin_ids = self.applicant_supporting_assertion_ids
        if (
            self.candidate_canonical_id != self.company_id
            or self.candidate_display_name != self.company_display_name
            or self.candidate_origin_public_evidence_ids != expected_origin_ids
            or self.claim_subject_id != expected_patent_ref
            or self.claim_value != expected_company_ref
        ):
            raise ValueError("Patent-Company candidate/claim differs")
        if self.query_as_of < self.relationship_snapshot_as_of:
            raise ValueError("Patent-Company query predates its snapshot")
        limitations = tuple(
            sorted(
                set(self.company_eligibility_limitations)
                | set(self.patent_eligibility_limitations)
            )
        )
        freshness_flags = ()
        if self.query_as_of > self.relationship_snapshot_as_of:
            canonical = (
                self.relationship_snapshot_as_of.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            freshness_flags = (f"relationship_snapshot_as_of:{canonical}",)
        expected_quality_flags = tuple(sorted({*limitations, *freshness_flags}))
        if self.candidate_quality_flags != expected_quality_flags:
            raise ValueError("Patent-Company candidate quality flags differ")
        if self.candidate_raw_score != 1.0:
            raise ValueError("Patent-Company candidate score differs")

        lineage = self.model_dump(
            mode="json",
            exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
        )
        expected_candidate_id = (
            "local-patent-company-relationship-candidate:sha256:"
            f"{_canonical_sha256(lineage)}"
        )
        if self.raw_candidate_id not in {"", expected_candidate_id}:
            raise ValueError(
                "raw_candidate_id does not bind Patent-Company relationship lineage"
            )
        object.__setattr__(self, "raw_candidate_id", expected_candidate_id)
        expected_evidence_id = (
            "local-patent-company-relationship-evidence:sha256:"
            f"{_canonical_sha256((lineage, expected_candidate_id))}"
        )
        if self.evidence_id not in {"", expected_evidence_id}:
            raise ValueError(
                "evidence_id does not bind Patent-Company relationship lineage"
            )
        object.__setattr__(self, "evidence_id", expected_evidence_id)
        expected_content_sha256 = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 not in {_ZERO_SHA256, expected_content_sha256}:
            raise ValueError(
                "content_sha256 does not bind Patent-Company relationship trace"
            )
        object.__setattr__(self, "content_sha256", expected_content_sha256)
        return self


class LocalProfessorPaperRelationshipTrace(ContractModel):
    """Content-bound canonical Professor-to-Paper attribution proof."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    release_id: str = Field(min_length=1)
    lane_request_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_enumeration_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    displayed_entity_ids: tuple[str, ...] = Field(min_length=1)
    displayed_professor_id: str = Field(min_length=1)
    protected_slot_id: str = Field(min_length=1)
    protected_slot_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_as_of: datetime
    query_relationship_type_id: Literal["professor_authored_paper"] = (
        "professor_authored_paper"
    )
    query_direction: Literal["professor_to_paper"] = "professor_to_paper"
    query_source_type: Literal["professor"] = "professor"
    query_target_type: Literal["paper"] = "paper"
    relationship_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_projection_run_id: str = Field(min_length=1)
    relationship_projection_schema_version: str = Field(min_length=1)
    relationship_registry_version: str = Field(min_length=1)
    relationship_registry_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_snapshot_as_of: datetime
    canonical_relationship_id: str = Field(min_length=1)
    current_relationship_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_input_id: str = Field(min_length=1)
    relationship_decision_input_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_id: str = Field(min_length=1)
    relationship_decision_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_state: Literal["accepted"] = "accepted"
    relationship_type_id: Literal["professor_attributed_to_paper"] = (
        "professor_attributed_to_paper"
    )
    relationship_type_version: Literal["canonical-v2-relationship-v1"] = (
        "canonical-v2-relationship-v1"
    )
    relationship_source_endpoint: str = Field(min_length=1)
    relationship_target_endpoint: str = Field(min_length=1)
    relationship_role_bindings: tuple[tuple[str, str], ...] = ()
    relationship_effective_time_semantics: Literal["observed_at"] = "observed_at"
    selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    relationship_valid_from: Any | None = None
    relationship_valid_to: Any | None = None
    projection_candidate_id: str = Field(min_length=1)
    projection_candidate_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_candidate_observed_at: datetime
    projection_candidate_source_event_time: datetime | None = None
    projection_candidate_assertion_input_id: str = Field(min_length=1)
    projection_candidate_assertion_input_kind: Literal[
        "shared_source_relationship_assertion"
    ] = "shared_source_relationship_assertion"
    projection_candidate_decision_input_id: str = Field(min_length=1)
    projection_candidate_evidence_metadata: dict[str, JsonValue]
    relationship_evidence_kind: Literal[
        "professor_page_or_identity_attribution_assertion"
    ] = "professor_page_or_identity_attribution_assertion"
    shared_assertion_id: str = Field(min_length=1)
    shared_assertion_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shared_assertion_source_record_id: str = Field(min_length=1)
    shared_assertion_source_identity_id: str = Field(min_length=1)
    shared_assertion_target_identity_id: str = Field(min_length=1)
    shared_assertion_evidence_refs: tuple[str, ...] = Field(min_length=1)
    shared_assertion_attributes_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shared_assertion_observed_at: datetime
    shared_assertion_source_event_time: datetime | None = None
    shared_assertion_valid_from: Any | None = None
    shared_assertion_valid_to: Any | None = None
    source_assignment_id: str = Field(min_length=1)
    source_assignment_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_assignment_source_identity_id: str = Field(min_length=1)
    source_assignment_canonical_identity_id: str = Field(min_length=1)
    source_assignment_entity_type: Literal["professor"] = "professor"
    source_assignment_source_record_refs: tuple[str, ...] = Field(min_length=1)
    target_assignment_id: str = Field(min_length=1)
    target_assignment_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_assignment_source_identity_id: str = Field(min_length=1)
    target_assignment_canonical_identity_id: str = Field(min_length=1)
    target_assignment_entity_type: Literal["paper"] = "paper"
    target_assignment_source_record_refs: tuple[str, ...] = Field(min_length=1)
    candidate_outcome_candidate_id: str = Field(min_length=1)
    candidate_outcome_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_outcome_retained_assertion_id: str = Field(min_length=1)
    candidate_outcome_decision_id: str = Field(min_length=1)
    candidate_outcome_projected_relationship_id: str = Field(min_length=1)
    candidate_outcome_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    decision_input_candidate_assertion_ids: tuple[str, ...] = Field(min_length=1)
    decision_input_selected_assertion_ids: tuple[str, ...] = Field(min_length=1)
    decision_input_conflicting_assertion_ids: tuple[str, ...] = ()
    decision_input_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    decision_candidate_assertion_ids: tuple[str, ...] = Field(min_length=1)
    decision_selected_assertion_ids: tuple[str, ...] = Field(min_length=1)
    decision_conflicting_assertion_ids: tuple[str, ...] = ()
    decision_source_canonical_identity_id: str = Field(min_length=1)
    decision_target_canonical_identity_id: str = Field(min_length=1)
    decision_release_id: str = Field(min_length=1)
    current_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    retained_reference_id: str = Field(min_length=1)
    retained_reference_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retained_assertion_id: str = Field(min_length=1)
    retained_source_record_id: str = Field(min_length=1)
    retained_artifact_refs: tuple[str, ...] = ()
    professor_id: str = Field(min_length=1)
    professor_stable_reference: str = Field(min_length=1)
    professor_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    professor_display_name: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    paper_stable_reference: str = Field(min_length=1)
    paper_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_display_name: str = Field(min_length=1)
    paper_domain_identity_status: Literal["confirmed", "unverified"]
    professor_path_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    professor_traversal_directions: tuple[str, ...] = Field(min_length=1)
    professor_relationship_decision_ids: tuple[str, ...] = Field(min_length=1)
    professor_eligibility_decision_id: str = Field(min_length=1)
    professor_eligibility_policy_id: str = Field(min_length=1)
    professor_eligibility_policy_version: str = Field(min_length=1)
    professor_eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    professor_eligibility_outcome: Literal["admitted", "limited"]
    professor_eligibility_limitations: tuple[str, ...] = ()
    professor_eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    professor_eligibility_supporting_assertion_ids: tuple[str, ...] = Field(
        min_length=1
    )
    paper_path_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_traversal_directions: tuple[str, ...] = Field(min_length=1)
    paper_relationship_decision_ids: tuple[str, ...] = Field(min_length=1)
    paper_eligibility_decision_id: str = Field(min_length=1)
    paper_eligibility_policy_id: str = Field(min_length=1)
    paper_eligibility_policy_version: str = Field(min_length=1)
    paper_eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_eligibility_outcome: Literal["admitted", "limited"]
    paper_eligibility_limitations: tuple[str, ...] = ()
    paper_eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    paper_eligibility_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    candidate_domain: Literal["paper"] = "paper"
    candidate_canonical_id: str = Field(min_length=1)
    candidate_display_name: str = Field(min_length=1)
    candidate_identity_kind: Literal["canonical"] = "canonical"
    candidate_resolution_state: Literal["resolved"] = "resolved"
    candidate_reference_type: None = None
    candidate_origin_public_evidence_ids: tuple[str, ...] = Field(min_length=1)
    candidate_quality_flags: tuple[str, ...] = ()
    candidate_raw_score: float = 1.0
    claim_subject_id: str = Field(min_length=1)
    claim_predicate: Literal["professor_attributed_to_paper"] = (
        "professor_attributed_to_paper"
    )
    claim_value: str = Field(min_length=1)
    claim_status: Literal["accepted"] = "accepted"
    relationship_state: Literal["accepted"] = "accepted"
    evidence_source_locator: str = Field(min_length=1)
    evidence_source_nature: Literal["local"] = "local"
    evidence_source_authority: Literal["canonical_release"] = "canonical_release"
    evidence_observed_at: datetime
    snippet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Literal["professor_paper_relationship_traversal"] = (
        "professor_paper_relationship_traversal"
    )
    execution_lane: Literal["relationship"] = "relationship"
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator("projection_candidate_evidence_metadata", mode="before")
    @classmethod
    def normalize_professor_paper_metadata(cls, value: object) -> object:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))

    @field_validator(
        "publication_verification_evidence_ids",
        "displayed_entity_ids",
        "selected_evidence_refs",
        "shared_assertion_evidence_refs",
        "candidate_outcome_selected_evidence_refs",
        "decision_input_selected_evidence_refs",
        "current_selected_evidence_refs",
        "professor_traversal_directions",
        "professor_relationship_decision_ids",
        "professor_eligibility_limitations",
        "professor_eligibility_hard_exclusion_codes",
        "professor_eligibility_supporting_assertion_ids",
        "paper_traversal_directions",
        "paper_relationship_decision_ids",
        "paper_eligibility_limitations",
        "paper_eligibility_hard_exclusion_codes",
        "paper_eligibility_supporting_assertion_ids",
        "candidate_origin_public_evidence_ids",
        "candidate_quality_flags",
    )
    @classmethod
    def validate_professor_paper_sorted_unique(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value for value in values):
            raise ValueError("Professor-Paper trace values must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError("Professor-Paper trace values must be sorted and unique")
        return values

    @model_validator(mode="after")
    def bind_professor_paper_trace(self) -> LocalProfessorPaperRelationshipTrace:
        expected_professor_ref = f"canonical:professor:{self.professor_id}"
        expected_paper_ref = f"canonical:paper:{self.paper_id}"
        if (
            self.displayed_entity_ids != (self.professor_id,)
            or self.displayed_professor_id != self.professor_id
            or self.professor_stable_reference != expected_professor_ref
            or self.paper_stable_reference != expected_paper_ref
            or self.relationship_source_endpoint != expected_professor_ref
            or self.relationship_target_endpoint != expected_paper_ref
            or self.relationship_role_bindings
        ):
            raise ValueError("Professor-Paper displayed/endpoint identity differs")
        expected_attributes: dict[str, JsonValue] = {
            "candidate_id": self.projection_candidate_id,
            "evidence_refs": list(self.shared_assertion_evidence_refs),
            "evidence_metadata": self.projection_candidate_evidence_metadata,
            "role_bindings": {},
        }
        if self.shared_assertion_attributes_content_sha256 != _canonical_sha256(
            expected_attributes
        ):
            raise ValueError("Professor-Paper shared assertion attributes differ")
        if (
            self.projection_candidate_assertion_input_id != self.shared_assertion_id
            or self.projection_candidate_decision_input_id
            != self.relationship_decision_input_id
            or self.shared_assertion_source_identity_id
            != self.source_assignment_source_identity_id
            or self.shared_assertion_target_identity_id
            != self.target_assignment_source_identity_id
            or self.source_assignment_canonical_identity_id != self.professor_id
            or self.target_assignment_canonical_identity_id != self.paper_id
            or self.shared_assertion_source_record_id
            not in self.source_assignment_source_record_refs
            or self.shared_assertion_source_record_id
            not in self.target_assignment_source_record_refs
        ):
            raise ValueError("Professor-Paper candidate/assertion assignment differs")
        if (
            self.candidate_outcome_candidate_id != self.projection_candidate_id
            or self.candidate_outcome_retained_assertion_id != self.shared_assertion_id
            or self.candidate_outcome_decision_id != self.relationship_decision_id
            or self.candidate_outcome_projected_relationship_id
            != self.canonical_relationship_id
            or self.decision_input_candidate_assertion_ids
            != (self.shared_assertion_id,)
            or self.decision_input_selected_assertion_ids != (self.shared_assertion_id,)
            or self.decision_input_conflicting_assertion_ids
            or self.decision_candidate_assertion_ids != (self.shared_assertion_id,)
            or self.decision_selected_assertion_ids != (self.shared_assertion_id,)
            or self.decision_conflicting_assertion_ids
            or self.decision_source_canonical_identity_id != self.professor_id
            or self.decision_target_canonical_identity_id != self.paper_id
            or self.decision_release_id != self.release_id
        ):
            raise ValueError("Professor-Paper outcome/decision continuity differs")
        expected_evidence_refs = (self.retained_reference_id,)
        if (
            self.selected_evidence_refs != expected_evidence_refs
            or self.shared_assertion_evidence_refs != expected_evidence_refs
            or self.candidate_outcome_selected_evidence_refs != expected_evidence_refs
            or self.decision_input_selected_evidence_refs != expected_evidence_refs
            or self.current_selected_evidence_refs != expected_evidence_refs
            or self.retained_artifact_refs
        ):
            raise ValueError("Professor-Paper retained evidence continuity differs")
        if (
            self.professor_traversal_directions != ("professor_to_paper",)
            or self.paper_traversal_directions != ("paper_to_professor",)
            or self.professor_relationship_decision_ids
            != (self.relationship_decision_id,)
            or self.paper_relationship_decision_ids != (self.relationship_decision_id,)
            or self.professor_eligibility_hard_exclusion_codes
            or self.paper_eligibility_hard_exclusion_codes
        ):
            raise ValueError("Professor-Paper endpoint eligibility differs")
        if (
            self.professor_eligibility_outcome == "limited"
            and not self.professor_eligibility_limitations
        ) or (
            self.paper_eligibility_outcome == "limited"
            and not self.paper_eligibility_limitations
        ):
            raise ValueError("limited Professor-Paper eligibility must be visible")
        if (
            self.candidate_canonical_id != self.paper_id
            or self.candidate_display_name != self.paper_display_name
            or self.candidate_origin_public_evidence_ids
            != self.decision_selected_assertion_ids
            or self.claim_subject_id != expected_professor_ref
            or self.claim_value != expected_paper_ref
            or self.candidate_raw_score != 1.0
        ):
            raise ValueError("Professor-Paper candidate/claim differs")
        if self.query_as_of < self.relationship_snapshot_as_of:
            raise ValueError("Professor-Paper query predates its snapshot")
        limitations = tuple(
            sorted(
                set(self.professor_eligibility_limitations)
                | set(self.paper_eligibility_limitations)
            )
        )
        freshness_flags = ()
        if self.query_as_of > self.relationship_snapshot_as_of:
            freshness_flags = (
                _relationship_snapshot_quality_flag(self.relationship_snapshot_as_of),
            )
        if self.candidate_quality_flags != tuple(
            sorted({*limitations, *freshness_flags})
        ):
            raise ValueError("Professor-Paper candidate quality flags differ")
        expected_locator = (
            f"canonical-v2-isolated:{self.target_id}:{self.canonical_relationship_id}"
        )
        if (
            self.evidence_source_locator != expected_locator
            or self.evidence_observed_at != self.relationship_snapshot_as_of
        ):
            raise ValueError("Professor-Paper evidence source envelope differs")

        lineage = self.model_dump(
            mode="json",
            exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
        )
        expected_candidate_id = (
            "local-professor-paper-relationship-candidate:sha256:"
            f"{_canonical_sha256(lineage)}"
        )
        if self.raw_candidate_id not in {"", expected_candidate_id}:
            raise ValueError("raw_candidate_id does not bind Professor-Paper lineage")
        object.__setattr__(self, "raw_candidate_id", expected_candidate_id)
        expected_evidence_id = (
            "local-professor-paper-relationship-evidence:sha256:"
            f"{_canonical_sha256((lineage, expected_candidate_id))}"
        )
        if self.evidence_id not in {"", expected_evidence_id}:
            raise ValueError("evidence_id does not bind Professor-Paper lineage")
        object.__setattr__(self, "evidence_id", expected_evidence_id)
        expected_content_sha256 = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 not in {_ZERO_SHA256, expected_content_sha256}:
            raise ValueError("content_sha256 does not bind Professor-Paper trace")
        object.__setattr__(self, "content_sha256", expected_content_sha256)
        return self


class LocalPaperProfessorRelationshipTrace(ContractModel):
    """Content-bound inverse Paper-to-Professor attribution proof."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    release_id: str = Field(min_length=1)
    lane_request_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_enumeration_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    displayed_entity_ids: tuple[str, ...] = Field(min_length=1)
    displayed_paper_id: str = Field(min_length=1)
    protected_slot_id: str = Field(min_length=1)
    protected_slot_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_as_of: datetime
    query_relationship_type_id: Literal["professor_authored_paper"] = (
        "professor_authored_paper"
    )
    query_direction: Literal["paper_to_professor"] = "paper_to_professor"
    query_source_type: Literal["paper"] = "paper"
    query_target_type: Literal["professor"] = "professor"
    relationship_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_projection_run_id: str = Field(min_length=1)
    relationship_projection_schema_version: str = Field(min_length=1)
    relationship_registry_version: str = Field(min_length=1)
    relationship_registry_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_snapshot_as_of: datetime
    canonical_relationship_id: str = Field(min_length=1)
    current_relationship_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_input_id: str = Field(min_length=1)
    relationship_decision_input_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_id: str = Field(min_length=1)
    relationship_decision_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_decision_state: Literal["accepted"] = "accepted"
    relationship_type_id: Literal["professor_attributed_to_paper"] = (
        "professor_attributed_to_paper"
    )
    relationship_type_version: Literal["canonical-v2-relationship-v1"] = (
        "canonical-v2-relationship-v1"
    )
    relationship_source_endpoint: str = Field(min_length=1)
    relationship_target_endpoint: str = Field(min_length=1)
    relationship_role_bindings: tuple[tuple[str, str], ...] = ()
    relationship_effective_time_semantics: Literal["observed_at"] = "observed_at"
    selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    relationship_valid_from: Any | None = None
    relationship_valid_to: Any | None = None
    projection_candidate_id: str = Field(min_length=1)
    projection_candidate_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_candidate_observed_at: datetime
    projection_candidate_source_event_time: datetime | None = None
    projection_candidate_assertion_input_id: str = Field(min_length=1)
    projection_candidate_assertion_input_kind: Literal[
        "shared_source_relationship_assertion"
    ] = "shared_source_relationship_assertion"
    projection_candidate_decision_input_id: str = Field(min_length=1)
    projection_candidate_evidence_metadata: dict[str, JsonValue]
    relationship_evidence_kind: Literal[
        "professor_page_or_identity_attribution_assertion"
    ] = "professor_page_or_identity_attribution_assertion"
    shared_assertion_id: str = Field(min_length=1)
    shared_assertion_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shared_assertion_source_record_id: str = Field(min_length=1)
    shared_assertion_source_identity_id: str = Field(min_length=1)
    shared_assertion_target_identity_id: str = Field(min_length=1)
    shared_assertion_evidence_refs: tuple[str, ...] = Field(min_length=1)
    shared_assertion_attributes_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    shared_assertion_observed_at: datetime
    shared_assertion_source_event_time: datetime | None = None
    shared_assertion_valid_from: Any | None = None
    shared_assertion_valid_to: Any | None = None
    source_assignment_id: str = Field(min_length=1)
    source_assignment_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_assignment_source_identity_id: str = Field(min_length=1)
    source_assignment_canonical_identity_id: str = Field(min_length=1)
    source_assignment_entity_type: Literal["professor"] = "professor"
    source_assignment_source_record_refs: tuple[str, ...] = Field(min_length=1)
    target_assignment_id: str = Field(min_length=1)
    target_assignment_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_assignment_source_identity_id: str = Field(min_length=1)
    target_assignment_canonical_identity_id: str = Field(min_length=1)
    target_assignment_entity_type: Literal["paper"] = "paper"
    target_assignment_source_record_refs: tuple[str, ...] = Field(min_length=1)
    candidate_outcome_candidate_id: str = Field(min_length=1)
    candidate_outcome_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_outcome_retained_assertion_id: str = Field(min_length=1)
    candidate_outcome_decision_id: str = Field(min_length=1)
    candidate_outcome_projected_relationship_id: str = Field(min_length=1)
    candidate_outcome_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    decision_input_candidate_assertion_ids: tuple[str, ...] = Field(min_length=1)
    decision_input_selected_assertion_ids: tuple[str, ...] = Field(min_length=1)
    decision_input_conflicting_assertion_ids: tuple[str, ...] = ()
    decision_input_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    decision_candidate_assertion_ids: tuple[str, ...] = Field(min_length=1)
    decision_selected_assertion_ids: tuple[str, ...] = Field(min_length=1)
    decision_conflicting_assertion_ids: tuple[str, ...] = ()
    decision_source_canonical_identity_id: str = Field(min_length=1)
    decision_target_canonical_identity_id: str = Field(min_length=1)
    decision_release_id: str = Field(min_length=1)
    current_selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    retained_reference_id: str = Field(min_length=1)
    retained_reference_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retained_assertion_id: str = Field(min_length=1)
    retained_source_record_id: str = Field(min_length=1)
    retained_artifact_refs: tuple[str, ...] = ()
    professor_id: str = Field(min_length=1)
    professor_stable_reference: str = Field(min_length=1)
    professor_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    professor_display_name: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    paper_stable_reference: str = Field(min_length=1)
    paper_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_display_name: str = Field(min_length=1)
    paper_domain_identity_status: Literal["confirmed", "unverified"]
    professor_path_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    professor_traversal_directions: tuple[str, ...] = Field(min_length=1)
    professor_relationship_decision_ids: tuple[str, ...] = Field(min_length=1)
    professor_eligibility_decision_id: str = Field(min_length=1)
    professor_eligibility_policy_id: str = Field(min_length=1)
    professor_eligibility_policy_version: str = Field(min_length=1)
    professor_eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    professor_eligibility_outcome: Literal["admitted", "limited"]
    professor_eligibility_limitations: tuple[str, ...] = ()
    professor_eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    professor_eligibility_supporting_assertion_ids: tuple[str, ...] = Field(
        min_length=1
    )
    paper_path_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_traversal_directions: tuple[str, ...] = Field(min_length=1)
    paper_relationship_decision_ids: tuple[str, ...] = Field(min_length=1)
    paper_eligibility_decision_id: str = Field(min_length=1)
    paper_eligibility_policy_id: str = Field(min_length=1)
    paper_eligibility_policy_version: str = Field(min_length=1)
    paper_eligibility_policy_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    paper_eligibility_outcome: Literal["admitted", "limited"]
    paper_eligibility_limitations: tuple[str, ...] = ()
    paper_eligibility_hard_exclusion_codes: tuple[str, ...] = ()
    paper_eligibility_supporting_assertion_ids: tuple[str, ...] = Field(min_length=1)
    candidate_domain: Literal["professor"] = "professor"
    candidate_canonical_id: str = Field(min_length=1)
    candidate_display_name: str = Field(min_length=1)
    candidate_identity_kind: Literal["canonical"] = "canonical"
    candidate_resolution_state: Literal["resolved"] = "resolved"
    candidate_reference_type: None = None
    candidate_origin_public_evidence_ids: tuple[str, ...] = Field(min_length=1)
    candidate_quality_flags: tuple[str, ...] = ()
    candidate_raw_score: float = 1.0
    claim_subject_id: str = Field(min_length=1)
    claim_predicate: Literal["professor_attributed_to_paper"] = (
        "professor_attributed_to_paper"
    )
    claim_value: str = Field(min_length=1)
    claim_status: Literal["accepted"] = "accepted"
    relationship_state: Literal["accepted"] = "accepted"
    evidence_source_locator: str = Field(min_length=1)
    evidence_source_nature: Literal["local"] = "local"
    evidence_source_authority: Literal["canonical_release"] = "canonical_release"
    evidence_observed_at: datetime
    snippet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Literal["paper_professor_relationship_traversal"] = (
        "paper_professor_relationship_traversal"
    )
    execution_lane: Literal["relationship"] = "relationship"
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator("projection_candidate_evidence_metadata", mode="before")
    @classmethod
    def normalize_paper_professor_metadata(cls, value: object) -> object:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))

    @field_validator(
        "publication_verification_evidence_ids",
        "displayed_entity_ids",
        "selected_evidence_refs",
        "shared_assertion_evidence_refs",
        "candidate_outcome_selected_evidence_refs",
        "decision_input_selected_evidence_refs",
        "current_selected_evidence_refs",
        "professor_traversal_directions",
        "professor_relationship_decision_ids",
        "professor_eligibility_limitations",
        "professor_eligibility_hard_exclusion_codes",
        "professor_eligibility_supporting_assertion_ids",
        "paper_traversal_directions",
        "paper_relationship_decision_ids",
        "paper_eligibility_limitations",
        "paper_eligibility_hard_exclusion_codes",
        "paper_eligibility_supporting_assertion_ids",
        "candidate_origin_public_evidence_ids",
        "candidate_quality_flags",
    )
    @classmethod
    def validate_paper_professor_sorted_unique(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value for value in values):
            raise ValueError("Paper-Professor trace values must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError("Paper-Professor trace values must be sorted and unique")
        return values

    @model_validator(mode="after")
    def bind_paper_professor_trace(self) -> LocalPaperProfessorRelationshipTrace:
        expected_professor_ref = f"canonical:professor:{self.professor_id}"
        expected_paper_ref = f"canonical:paper:{self.paper_id}"
        if (
            self.displayed_entity_ids != (self.paper_id,)
            or self.displayed_paper_id != self.paper_id
            or self.professor_stable_reference != expected_professor_ref
            or self.paper_stable_reference != expected_paper_ref
            or self.relationship_source_endpoint != expected_professor_ref
            or self.relationship_target_endpoint != expected_paper_ref
            or self.relationship_role_bindings
        ):
            raise ValueError("Paper-Professor displayed/endpoint identity differs")
        expected_attributes: dict[str, JsonValue] = {
            "candidate_id": self.projection_candidate_id,
            "evidence_refs": list(self.shared_assertion_evidence_refs),
            "evidence_metadata": self.projection_candidate_evidence_metadata,
            "role_bindings": {},
        }
        if self.shared_assertion_attributes_content_sha256 != _canonical_sha256(
            expected_attributes
        ):
            raise ValueError("Paper-Professor shared assertion attributes differ")
        if (
            self.projection_candidate_assertion_input_id != self.shared_assertion_id
            or self.projection_candidate_decision_input_id
            != self.relationship_decision_input_id
            or self.shared_assertion_source_identity_id
            != self.source_assignment_source_identity_id
            or self.shared_assertion_target_identity_id
            != self.target_assignment_source_identity_id
            or self.source_assignment_canonical_identity_id != self.professor_id
            or self.target_assignment_canonical_identity_id != self.paper_id
            or self.shared_assertion_source_record_id
            not in self.source_assignment_source_record_refs
            or self.shared_assertion_source_record_id
            not in self.target_assignment_source_record_refs
        ):
            raise ValueError("Paper-Professor candidate/assertion assignment differs")
        if (
            self.candidate_outcome_candidate_id != self.projection_candidate_id
            or self.candidate_outcome_retained_assertion_id != self.shared_assertion_id
            or self.candidate_outcome_decision_id != self.relationship_decision_id
            or self.candidate_outcome_projected_relationship_id
            != self.canonical_relationship_id
            or self.decision_input_candidate_assertion_ids
            != (self.shared_assertion_id,)
            or self.decision_input_selected_assertion_ids != (self.shared_assertion_id,)
            or self.decision_input_conflicting_assertion_ids
            or self.decision_candidate_assertion_ids != (self.shared_assertion_id,)
            or self.decision_selected_assertion_ids != (self.shared_assertion_id,)
            or self.decision_conflicting_assertion_ids
            or self.decision_source_canonical_identity_id != self.professor_id
            or self.decision_target_canonical_identity_id != self.paper_id
            or self.decision_release_id != self.release_id
        ):
            raise ValueError("Paper-Professor outcome/decision continuity differs")
        expected_evidence_refs = (self.retained_reference_id,)
        if (
            self.selected_evidence_refs != expected_evidence_refs
            or self.shared_assertion_evidence_refs != expected_evidence_refs
            or self.candidate_outcome_selected_evidence_refs != expected_evidence_refs
            or self.decision_input_selected_evidence_refs != expected_evidence_refs
            or self.current_selected_evidence_refs != expected_evidence_refs
            or self.retained_artifact_refs
        ):
            raise ValueError("Paper-Professor retained evidence continuity differs")
        if (
            self.professor_traversal_directions != ("professor_to_paper",)
            or self.paper_traversal_directions != ("paper_to_professor",)
            or self.professor_relationship_decision_ids
            != (self.relationship_decision_id,)
            or self.paper_relationship_decision_ids != (self.relationship_decision_id,)
            or self.professor_eligibility_hard_exclusion_codes
            or self.paper_eligibility_hard_exclusion_codes
        ):
            raise ValueError("Paper-Professor endpoint eligibility differs")
        if (
            self.professor_eligibility_outcome == "limited"
            and not self.professor_eligibility_limitations
        ) or (
            self.paper_eligibility_outcome == "limited"
            and not self.paper_eligibility_limitations
        ):
            raise ValueError("limited Paper-Professor eligibility must be visible")
        if (
            self.candidate_canonical_id != self.professor_id
            or self.candidate_display_name != self.professor_display_name
            or self.candidate_origin_public_evidence_ids
            != self.decision_selected_assertion_ids
            or self.claim_subject_id != expected_professor_ref
            or self.claim_value != expected_paper_ref
            or self.candidate_raw_score != 1.0
        ):
            raise ValueError("Paper-Professor candidate/claim differs")
        if self.query_as_of < self.relationship_snapshot_as_of:
            raise ValueError("Paper-Professor query predates its snapshot")
        limitations = tuple(
            sorted(
                set(self.professor_eligibility_limitations)
                | set(self.paper_eligibility_limitations)
            )
        )
        freshness_flags = ()
        if self.query_as_of > self.relationship_snapshot_as_of:
            freshness_flags = (
                _relationship_snapshot_quality_flag(self.relationship_snapshot_as_of),
            )
        if self.candidate_quality_flags != tuple(
            sorted({*limitations, *freshness_flags})
        ):
            raise ValueError("Paper-Professor candidate quality flags differ")
        expected_locator = (
            f"canonical-v2-isolated:{self.target_id}:{self.canonical_relationship_id}"
        )
        if (
            self.evidence_source_locator != expected_locator
            or self.evidence_observed_at != self.relationship_snapshot_as_of
        ):
            raise ValueError("Paper-Professor evidence source envelope differs")

        lineage = self.model_dump(
            mode="json",
            exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
        )
        expected_candidate_id = (
            "local-paper-professor-relationship-candidate:sha256:"
            f"{_canonical_sha256(lineage)}"
        )
        if self.raw_candidate_id not in {"", expected_candidate_id}:
            raise ValueError("raw_candidate_id does not bind Paper-Professor lineage")
        object.__setattr__(self, "raw_candidate_id", expected_candidate_id)
        expected_evidence_id = (
            "local-paper-professor-relationship-evidence:sha256:"
            f"{_canonical_sha256((lineage, expected_candidate_id))}"
        )
        if self.evidence_id not in {"", expected_evidence_id}:
            raise ValueError("evidence_id does not bind Paper-Professor lineage")
        object.__setattr__(self, "evidence_id", expected_evidence_id)
        expected_content_sha256 = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 not in {_ZERO_SHA256, expected_content_sha256}:
            raise ValueError("content_sha256 does not bind Paper-Professor trace")
        object.__setattr__(self, "content_sha256", expected_content_sha256)
        return self


class LocalSourceRelationshipTrace(ContractModel):
    """Compact proof for a source-bound canonical relationship traversal."""

    target_id: str = Field(min_length=1)
    target_marker_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    index_result_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_verification_evidence_ids: tuple[str, ...] = Field(min_length=1)
    release_id: str = Field(min_length=1)
    lane_request_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_enumeration_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    displayed_entity_ids: tuple[str, ...] = Field(min_length=1, max_length=1)
    displayed_entity_id: str = Field(min_length=1)
    protected_slot_id: str = Field(min_length=1)
    protected_slot_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_as_of: datetime
    query_relationship_type_id: str = Field(min_length=1)
    query_direction: str = Field(min_length=1)
    query_source_type: Literal["company", "paper", "patent", "professor"]
    query_target_type: Literal["company", "paper", "patent", "professor"]
    relationship_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_snapshot_as_of: datetime
    canonical_relationship_id: str = Field(min_length=1)
    current_relationship_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_type_id: str = Field(min_length=1)
    relationship_type_version: Literal["canonical-v2-relationship-v1"]
    physical_direction: Literal["forward", "inverse"]
    physical_source_id: str = Field(min_length=1)
    physical_source_type: Literal["company", "paper", "patent", "professor"]
    physical_target_id: str = Field(min_length=1)
    physical_target_type: Literal["company", "paper", "patent", "professor"]
    relationship_role_bindings: tuple[tuple[str, str], ...] = ()
    selected_evidence_refs: tuple[str, ...] = Field(min_length=1)
    projection_candidate_id: str = Field(min_length=1)
    projection_candidate_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assertion_kind: Literal[
        "shared_source_relationship_assertion", "typed_relationship_assertion"
    ]
    assertion_id: str = Field(min_length=1)
    assertion_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_record_id: str = Field(min_length=1)
    relationship_decision_id: str = Field(min_length=1)
    relationship_decision_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_outcome_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_canonical_id: str = Field(min_length=1)
    candidate_domain: Literal["company", "paper", "patent", "professor"]
    candidate_display_name: str = Field(min_length=1)
    candidate_projection_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_origin_public_evidence_ids: tuple[str, ...] = Field(min_length=1)
    candidate_quality_flags: tuple[str, ...] = ()
    claim_subject_id: str = Field(min_length=1)
    claim_predicate: str = Field(min_length=1)
    claim_value: str = Field(min_length=1)
    claim_status: Literal["accepted"] = "accepted"
    snippet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path: Literal["source_relationship_traversal"] = "source_relationship_traversal"
    execution_lane: Literal["relationship"] = "relationship"
    raw_candidate_id: str = ""
    evidence_id: str = ""
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "publication_verification_evidence_ids",
        "selected_evidence_refs",
        "candidate_origin_public_evidence_ids",
        "candidate_quality_flags",
    )
    @classmethod
    def validate_sorted_unique_source_lineage(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        if any(not value for value in values) or values != tuple(sorted(set(values))):
            raise ValueError("source relationship lineage must be sorted and unique")
        return values

    @field_validator("relationship_role_bindings")
    @classmethod
    def validate_source_role_bindings(
        cls, values: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        if any(not role or not value for role, value in values):
            raise ValueError("source relationship role bindings must be non-empty")
        if values != tuple(sorted(set(values))):
            raise ValueError(
                "source relationship role bindings must be sorted and unique"
            )
        return values

    @model_validator(mode="after")
    def bind_source_relationship_trace(self) -> LocalSourceRelationshipTrace:
        physical_paths = {
            _COMPANY_TO_PATENT_QUERY_PATH: ("patent_has_applicant", "inverse"),
            _PATENT_TO_COMPANY_QUERY_PATH: ("patent_has_applicant", "forward"),
            _PROFESSOR_TO_PAPER_QUERY_PATH: (
                "professor_attributed_to_paper",
                "forward",
            ),
            _PAPER_TO_PROFESSOR_QUERY_PATH: (
                "professor_attributed_to_paper",
                "inverse",
            ),
            _PROFESSOR_TO_COMPANY_QUERY_PATH: ("professor_company_role", "forward"),
            _COMPANY_TO_PROFESSOR_QUERY_PATH: ("professor_company_role", "inverse"),
        }
        query_path = (
            self.query_relationship_type_id,
            self.query_direction,
            self.query_source_type,
            self.query_target_type,
        )
        expected = physical_paths.get(query_path)
        displayed_ref = f"canonical:{self.query_source_type}:{self.displayed_entity_id}"
        candidate_ref = (
            f"canonical:{self.query_target_type}:{self.candidate_canonical_id}"
        )
        physical_ids = (
            (self.physical_source_id, self.physical_target_id)
            if self.physical_direction == "forward"
            else (self.physical_target_id, self.physical_source_id)
        )
        physical_types = (
            (self.physical_source_type, self.physical_target_type)
            if self.physical_direction == "forward"
            else (self.physical_target_type, self.physical_source_type)
        )
        if (
            expected != (self.relationship_type_id, self.physical_direction)
            or self.displayed_entity_ids != (self.displayed_entity_id,)
            or physical_ids != (self.displayed_entity_id, self.candidate_canonical_id)
            or physical_types != (self.query_source_type, self.query_target_type)
            or self.candidate_domain != self.query_target_type
            or self.claim_subject_id != displayed_ref
            or self.claim_predicate != self.relationship_type_id
            or self.claim_value != candidate_ref
        ):
            raise ValueError("source relationship path/endpoints/claim differ")
        if self.query_as_of < self.relationship_snapshot_as_of:
            raise ValueError("source relationship query predates its snapshot")
        freshness_flags = ()
        if self.query_as_of > self.relationship_snapshot_as_of:
            canonical = (
                self.relationship_snapshot_as_of.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            freshness_flags = (f"relationship_snapshot_as_of:{canonical}",)
        if self.candidate_quality_flags != freshness_flags:
            raise ValueError("source relationship candidate quality flags differ")

        lineage = self.model_dump(
            mode="json", exclude={"raw_candidate_id", "evidence_id", "content_sha256"}
        )
        candidate_id = (
            f"local-source-relationship-candidate:sha256:{_canonical_sha256(lineage)}"
        )
        if self.raw_candidate_id not in {"", candidate_id}:
            raise ValueError(
                "raw_candidate_id does not bind source relationship lineage"
            )
        object.__setattr__(self, "raw_candidate_id", candidate_id)
        evidence_id = (
            "local-source-relationship-evidence:sha256:"
            f"{_canonical_sha256((lineage, candidate_id))}"
        )
        if self.evidence_id not in {"", evidence_id}:
            raise ValueError("evidence_id does not bind source relationship lineage")
        object.__setattr__(self, "evidence_id", evidence_id)
        content_sha256 = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 not in {_ZERO_SHA256, content_sha256}:
            raise ValueError("content_sha256 does not bind source relationship trace")
        object.__setattr__(self, "content_sha256", content_sha256)
        return self


LocalEvidenceTrace = Annotated[
    LocalProjectionTrace
    | LocalVectorTrace
    | LocalInternalReferenceTrace
    | LocalRelationshipTrace
    | LocalCanonicalRelationshipTrace
    | LocalPatentCompanyRelationshipTrace
    | LocalProfessorPaperRelationshipTrace
    | LocalPaperProfessorRelationshipTrace
    | LocalSourceRelationshipTrace,
    Field(discriminator="path"),
]


class EvidenceItem(ContractModel):
    evidence_id: str
    object_id: str
    domain: str
    lane: str
    source_nature: str
    source_locator: str
    snippet: str
    score: float
    source_authority: str = "other"
    observed_at: datetime | None = None
    claim_binding: EvidenceClaimBinding | None = None
    web_snapshot: WebEvidenceSnapshot | None = None
    local_projection_trace: LocalEvidenceTrace | None = None


class RetrievalLaneResult(ContractModel):
    items: tuple[EvidenceItem, ...] = ()
    candidates: tuple[RecallCandidate, ...] = ()
    web_snapshot_payloads: tuple[WebSnapshotPayload, ...] = ()


class RecallCandidate(ContractModel):
    raw_candidate_id: str
    display_name: str
    domain: str
    identity_kind: str
    canonical_id: str | None
    reference_type: str | None = None
    resolution_state: str
    relationship_state: str | None = None
    origin_public_evidence_ids: tuple[str, ...] = ()
    query_view: str
    lane: str
    attempt: int
    release_id: str
    adapter_version: str
    provider_version: str | None = None
    raw_score: float
    quality_flags: tuple[str, ...] = ()
    evidence: tuple[EvidenceItem, ...]


class IdentityFusionGroup(ContractModel):
    canonical_id: str
    raw_candidate_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    confidence: float
    rationale: str


class IdentityFusionProposal(ContractModel):
    decision_input_sha256: str
    schema_version: str
    model_id: str
    prompt_version: str
    groups: tuple[IdentityFusionGroup, ...]


class RerankProposal(ContractModel):
    decision_input_sha256: str
    schema_version: str
    model_id: str
    prompt_version: str
    ordered_result_ids: tuple[str, ...]
    rationale: str


class MaterialPartProposal(ContractModel):
    part_id: str
    outcome: Literal["supported", "conflicting", "missing"]
    evidence_ids: tuple[str, ...]
    rationale: str
    uncertainty: str
    confidence: float = Field(ge=0.0, le=1.0)


class SufficiencyProposal(ContractModel):
    decision_input_sha256: str
    schema_version: str
    decision_id: str
    parts: tuple[MaterialPartProposal, ...]

    @model_validator(mode="after")
    def validate_unique_parts(self) -> SufficiencyProposal:
        part_ids = tuple(part.part_id for part in self.parts)
        if len(part_ids) != len(set(part_ids)):
            raise ValueError("sufficiency proposal contains duplicate part IDs")
        return self


class SupplementalLaneResult(ContractModel):
    items: tuple[EvidenceItem, ...]
    elapsed_ms: int = Field(ge=0)
    cost_units: float = Field(ge=0.0, allow_inf_nan=False)
    retryable: bool


class WebSnapshotPolicy(_ContentModel):
    policy_id: str
    policy_version: str
    max_bytes: int = Field(gt=0)


class CanonicalEntityHandle(ContractModel):
    kind: Literal["canonical"] = "canonical"
    canonical_id: str
    domain: str
    display_name: str
    evidence_ids: tuple[str, ...]


class WebEntityHandle(ContractModel):
    kind: Literal["web"] = "web"
    handle_id: str
    domain: str
    display_name: str
    evidence_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    resolution_state: str
    candidate_canonical_ids: tuple[str, ...]
    originating_query: str
    origin_lane: str
    origin_attempt: int
    session_id: str | None = None
    expires_at: datetime | None = None


class EvidenceConflict(ContractModel):
    conflict_id: str
    subject_id: str
    predicate: str
    evidence_ids: tuple[str, ...]
    material: bool
    fusion_decision_id: str | None


class IndustryBriefIntent(ContractModel):
    release_id: str
    scope: str
    as_of: datetime
    route_ids: tuple[str, ...]
    enumeration_mode: str


class TypedTraversalRequest(ContractModel):
    path_id: str
    source_domain: str
    target_domain: str
    relationship_type: str
    direction: str


class ContinuationCandidate(ContractModel):
    candidate_id: str
    reason: str
    label: str
    operation: str
    target_kind: str
    target_handle_ids: tuple[str, ...]
    constraint_pairs: tuple[tuple[str, str], ...]
    relation_type: str | None
    coverage_state: str | None = None
    evidence_ids: tuple[str, ...]
    available: bool


class RequiredMemberOutcome(ContractModel):
    member_id: str
    outcome: str
    evidence_ids: tuple[str, ...]
    reason: str | None = None


class EnumerationCoverage(ContractModel):
    mode: str
    scope: str
    as_of: datetime
    checked_ids: tuple[str, ...]
    eligible_ids: tuple[str, ...]
    retrieved_ids: tuple[str, ...]
    displayed_ids: tuple[str, ...]
    omitted_ids: tuple[str, ...]
    unknown_ids: tuple[str, ...]
    unknown_scope: bool
    checked_count: int
    eligible_count: int
    retrieved_count: int
    displayed_count: int
    omitted_count: int
    unknown_count: int | None
    exhaustive: bool
    accounting_complete: bool
    required_member_outcomes: tuple[RequiredMemberOutcome, ...]
    continuation_state: str
    continuation_required: bool


class CandidateTrace(ContractModel):
    raw_candidate_id: str
    query_view: str
    lane: str
    attempt: int
    release_id: str
    adapter_version: str
    provider_version: str | None
    raw_score: float
    evidence_ids: tuple[str, ...]
    disposition: str
    selected_result_id: str | None = None


class AuxiliaryTrace(ContractModel):
    raw_candidate_id: str
    reference_type: str
    origin_public_evidence_ids: tuple[str, ...]
    relationship_state: str | None = None
    public_population: bool = False
    eligible: bool = True


class RetrievalTrace(ContractModel):
    query_view: str
    lane: str
    attempt: int
    release_id: str
    candidate_count: int
    status: str = "succeeded"
    failure_kind: str | None = None
    source_scope: str | None = None
    phase: str = "initial"
    material_part_ids: tuple[str, ...] = ()


class Limitation(ContractModel):
    code: str
    lane: str | None = None
    material: bool = False
    impact: str | None = None
    material_part_ids: tuple[str, ...] = ()
    reason: str | None = None


class FusedCandidate(ContractModel):
    result_id: str
    canonical_id: str | None
    display_name: str
    domain: str
    raw_candidate_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]
    quality_flags: tuple[str, ...]
    raw_score: float
    identity_kind: str
    resolution_state: str
    origin_lane: str
    origin_attempt: int
    adapter_versions: tuple[str, ...]
    provider_versions: tuple[str, ...]


class DecisionReceipt(ContractModel):
    mode: str
    decision_input_sha256: str | None = None
    degradation_reason: str | None = None


class ConstraintFailure(ContractModel):
    slot_kind: str
    required_value: str
    observed_values: tuple[str, ...]


class ConstraintReceipt(ContractModel):
    raw_candidate_ids: tuple[str, ...]
    outcome: str
    failed_slots: tuple[ConstraintFailure, ...]
    aggregated_evidence_ids: tuple[str, ...]


class SufficiencyPartDecision(ContractModel):
    part_id: str
    outcome: Literal["supported", "conflicting", "missing"]
    evidence_ids: tuple[str, ...]
    rationale: str
    uncertainty: str
    confidence: float = Field(ge=0.0, le=1.0)
    answer_scoped: bool
    canonical: bool


class SufficiencyReport(ContractModel):
    decision_input_sha256: str
    parts: tuple[SufficiencyPartDecision, ...]
    complete: bool


class SupplementalBudgetReceipt(ContractModel):
    exhausted: bool
    exhaustion_reason: str | None
    exhausted_axis: str | None
    limit_value: float | int | None
    used_value: float | int | None
    provider_calls: int
    retry_count: int
    elapsed_ms: int
    cost_units: float
    attempt_count: int


class SnapshotReceipt(ContractModel):
    snapshot_id: str
    status: str
    reason_code: str | None = None
    observed_byte_length: int | None = None


class HandleReplayReceipt(ContractModel):
    handle_id: str
    status: str
    accepted_snapshot_sha256: str | None
    observed_live_content_sha256: str | None
    continuity_established: bool


class AcceptedIdentityLookupResult(ContractModel):
    release_id: str
    canonical_id: str
    accepted: bool
    evidence_ids: tuple[str, ...]


class WebHandleResolutionProposal(ContractModel):
    decision_input_sha256: str
    schema_version: str
    handle_id: str
    accepted_release_id: str
    canonical_id: str
    canonical_evidence_ids: tuple[str, ...]
    retained_snapshot_ids: tuple[str, ...]
    resolution_state: str
    rationale: str


class HandleResolutionReceipt(ContractModel):
    handle_id: str
    status: str
    reason_code: str | None
    accepted_release_id: str
    canonical_id: str | None
    retained_snapshot_ids: tuple[str, ...]
    read_only: bool
    canonical_mutation_count: int = 0
    index_mutation_count: int = 0
    source_mapping_mutation_count: int = 0


class EvidenceSet(ContractModel):
    release_id: str
    original_query: str
    protected_slots: tuple[ProtectedSlot, ...]
    items: tuple[EvidenceItem, ...]
    traces: tuple[RetrievalTrace, ...]
    limitations: tuple[Limitation, ...]
    candidate_traces: tuple[CandidateTrace, ...] = ()
    auxiliary_traces: tuple[AuxiliaryTrace, ...] = ()
    fused_candidates: tuple[FusedCandidate, ...] = ()
    constraint_receipts: tuple[ConstraintReceipt, ...] = ()
    fusion_receipt: DecisionReceipt | None = None
    rerank_receipt: DecisionReceipt | None = None
    entity_handles: tuple[CanonicalEntityHandle | WebEntityHandle, ...] = ()
    sufficiency_report: SufficiencyReport | None = None
    enumeration_coverage: EnumerationCoverage | None = None
    supplemental_budget_receipt: SupplementalBudgetReceipt | None = None
    continuation_reasons: tuple[str, ...] = ()
    handle_replay_receipts: tuple[HandleReplayReceipt, ...] = ()
    live_referent_handle_ids: tuple[str, ...] = ()
    handle_resolution_receipts: tuple[HandleResolutionReceipt, ...] = ()
    snapshot_receipts: tuple[SnapshotReceipt, ...] = ()
    material_conflicts: tuple[EvidenceConflict, ...] = ()
    material_parts: tuple[MaterialQuestionPart, ...] = ()
    industry_brief_intent: IndustryBriefIntent | None = None
    requested_traversal: TypedTraversalRequest | None = None
    ambiguity_decision: AmbiguityDecision | None = None
    continuation_candidates: tuple[ContinuationCandidate, ...] = ()


def _entity_handle_id(handle: CanonicalEntityHandle | WebEntityHandle) -> str:
    return handle.canonical_id if handle.kind == "canonical" else handle.handle_id


def _successor_handle_evidence(
    handle: CanonicalEntityHandle | WebEntityHandle,
    *,
    plan: RetrievalPlan,
    item_by_id: Mapping[str, EvidenceItem],
    now: datetime,
) -> tuple[str, ...] | None:
    evidence_ids = tuple(dict.fromkeys(handle.evidence_ids))
    if not evidence_ids or len(evidence_ids) != len(handle.evidence_ids):
        return None
    if any(evidence_id not in item_by_id for evidence_id in evidence_ids):
        return None
    if isinstance(handle, WebEntityHandle):
        snapshot_ids = tuple(dict.fromkeys(handle.evidence_snapshot_ids))
        if (
            not plan.session_id
            or handle.session_id != plan.session_id
            or handle.expires_at is None
            or now >= handle.expires_at
            or not snapshot_ids
            or len(snapshot_ids) != len(handle.evidence_snapshot_ids)
        ):
            return None
        retained_snapshot_ids = {
            item.web_snapshot.snapshot_id
            for evidence_id in evidence_ids
            if (item := item_by_id[evidence_id]).source_nature == "current_web"
            and item.web_snapshot is not None
        }
        if not set(snapshot_ids) <= retained_snapshot_ids:
            return None
    return evidence_ids


def _successor_handle_matches_subject(
    handle: CanonicalEntityHandle | WebEntityHandle,
    *,
    subject_id: str,
    evidence_ids: tuple[str, ...],
    item_by_id: Mapping[str, EvidenceItem],
) -> bool:
    if isinstance(handle, CanonicalEntityHandle):
        return handle.canonical_id == subject_id
    object_ids = {item_by_id[evidence_id].object_id for evidence_id in evidence_ids}
    return len(object_ids) == 1 and (
        handle.handle_id == subject_id or subject_id in object_ids
    )


def _continuation_candidate(
    *,
    reason: str,
    label: str,
    operation: str,
    target_kind: str,
    target_handle_ids: tuple[str, ...],
    constraint_pairs: tuple[tuple[str, str], ...],
    coverage_state: str | None,
    evidence_ids: tuple[str, ...],
) -> ContinuationCandidate:
    content = {
        "reason": reason,
        "label": label,
        "operation": operation,
        "target_kind": target_kind,
        "target_handle_ids": target_handle_ids,
        "constraint_pairs": constraint_pairs,
        "relation_type": None,
        "coverage_state": coverage_state,
        "evidence_ids": evidence_ids,
        "available": True,
    }
    return ContinuationCandidate(
        candidate_id=("continuation-candidate:sha256:" + _canonical_sha256(content)),
        **content,
    )


def _materialize_requested_traversal(
    plan: RetrievalPlan,
) -> TypedTraversalRequest | None:
    if plan.planning_trace is None or len(plan.relationship_paths) != 1:
        return None
    path = plan.relationship_paths[0]
    path_tuple = (
        path.relationship_type_id,
        path.direction,
        path.source_type,
        path.target_type,
    )
    typed_relationship = {
        _COMPANY_TO_PATENT_QUERY_PATH: ("patent_has_applicant", "inverse"),
        _PATENT_TO_COMPANY_QUERY_PATH: ("patent_has_applicant", "forward"),
        _PROFESSOR_TO_PAPER_QUERY_PATH: (
            "professor_attributed_to_paper",
            "forward",
        ),
        _PAPER_TO_PROFESSOR_QUERY_PATH: (
            "professor_attributed_to_paper",
            "inverse",
        ),
        _PROFESSOR_TO_COMPANY_QUERY_PATH: ("professor_company_role", "forward"),
        _COMPANY_TO_PROFESSOR_QUERY_PATH: ("professor_company_role", "inverse"),
    }.get(path_tuple)
    if typed_relationship is None:
        return None
    relationship_type, direction = typed_relationship
    return TypedTraversalRequest(
        path_id=path.direction,
        source_domain=path.source_type,
        target_domain=path.target_type,
        relationship_type=relationship_type,
        direction=direction,
    )


def _materialize_successor_handoff(
    plan: RetrievalPlan,
    result: EvidenceSet,
    *,
    now: datetime,
) -> EvidenceSet:
    decision = result.ambiguity_decision
    if (
        decision is not None
        and decision.mode == "blocking"
        and plan.planning_trace is not None
    ):
        decision_input = {
            "release_id": result.release_id,
            "original_query": result.original_query,
            "planning_decision_sha256": decision.content_sha256,
            "outcome": "blocked",
        }
        decision_id = "ambiguity-decision:sha256:" + _canonical_sha256(decision_input)
        successor_decision = AmbiguityDecision(
            policy_version=decision.policy_version,
            decision_id=decision_id,
            outcome="blocked",
            candidates=(),
            selected_handle_id=None,
            viable_alternative_handle_ids=(),
            decision_trace_id=(
                "ambiguity-trace:sha256:"
                + _canonical_sha256(
                    {
                        "decision_id": decision_id,
                        "planning_decision_sha256": decision.content_sha256,
                    }
                )
            ),
        )
        return result.model_copy(
            update={
                "ambiguity_decision": successor_decision,
                "continuation_candidates": (),
            }
        )

    item_by_id = {item.evidence_id: item for item in result.items}
    valid_handle_evidence = {
        _entity_handle_id(handle): evidence_ids
        for handle in result.entity_handles
        if (
            evidence_ids := _successor_handle_evidence(
                handle,
                plan=plan,
                item_by_id=item_by_id,
                now=now,
            )
        )
        is not None
    }
    handle_by_id = {
        _entity_handle_id(handle): handle for handle in result.entity_handles
    }
    constraint_pairs = tuple(
        dict.fromkeys(
            (slot.kind, value)
            for slot in result.protected_slots
            if (value := slot.value)
        )
    )
    candidates: list[ContinuationCandidate] = []
    for reason in result.continuation_reasons:
        if reason == "evidence_gap":
            report = result.sufficiency_report
            if report is None:
                continue
            unresolved_part_ids = tuple(
                part.part_id for part in report.parts if part.outcome != "supported"
            )
            material_part_by_id = {part.part_id: part for part in result.material_parts}
            if not unresolved_part_ids or any(
                part_id not in material_part_by_id for part_id in unresolved_part_ids
            ):
                continue
            subject_ids = tuple(
                dict.fromkeys(
                    material_part_by_id[part_id].subject_id
                    for part_id in unresolved_part_ids
                )
            )
            if len(subject_ids) != 1:
                continue
            subject_id = subject_ids[0]
            matching_handle_ids = tuple(
                handle_id
                for handle_id, evidence_ids in valid_handle_evidence.items()
                if _successor_handle_matches_subject(
                    handle_by_id[handle_id],
                    subject_id=subject_id,
                    evidence_ids=evidence_ids,
                    item_by_id=item_by_id,
                )
            )
            if len(matching_handle_ids) != 1:
                continue
            handle_id = matching_handle_ids[0]
            candidates.append(
                _continuation_candidate(
                    reason=reason,
                    label="Search for targeted evidence",
                    operation="targeted_evidence_search",
                    target_kind="current_handle",
                    target_handle_ids=(handle_id,),
                    constraint_pairs=constraint_pairs,
                    coverage_state=None,
                    evidence_ids=valid_handle_evidence[handle_id],
                )
            )
            continue

        if reason != "budget_exhausted":
            continue
        receipt = result.supplemental_budget_receipt
        if (
            receipt is None
            or not receipt.exhausted
            or not receipt.exhausted_axis
            or receipt.exhaustion_reason != receipt.exhausted_axis
            or not any(
                limitation.code == "supplemental_budget_exhausted"
                and limitation.material
                and limitation.reason == receipt.exhausted_axis
                for limitation in result.limitations
            )
        ):
            continue
        evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for handle_id in handle_by_id
                if handle_id in valid_handle_evidence
                for evidence_id in valid_handle_evidence[handle_id]
            )
        )
        if not evidence_ids:
            continue
        candidates.append(
            _continuation_candidate(
                reason=reason,
                label="Resume the bounded search",
                operation="resume_bounded_search",
                target_kind="current_result_set",
                target_handle_ids=(),
                constraint_pairs=constraint_pairs,
                coverage_state=(
                    None
                    if result.enumeration_coverage is None
                    else result.enumeration_coverage.continuation_state
                ),
                evidence_ids=evidence_ids,
            )
        )
    return result.model_copy(
        update={
            "continuation_candidates": tuple(candidates),
            "requested_traversal": _materialize_requested_traversal(plan),
        }
    )


def _validate_recorded(value: Any, model_type: type[Any]) -> Any:
    if isinstance(value, model_type):
        return model_type.model_validate(value.model_dump(mode="json"))
    return model_type.model_validate(value)


_EXPLICIT_ORGANIZATION_PREFIXES = (
    "请介绍一下",
    "请介绍",
    "我关注的是",
    "我说的是",
    "我指的是",
    "这里指的是",
    "介绍一下",
    "介绍",
    "我想了解",
    "帮我查一下",
    "帮我查",
)
_ORGANIZATION_NAME_SUFFIXES = (
    "有限责任公司",
    "股份有限公司",
    "有限公司",
    "公司",
    "科技",
)


def _explicit_organization_name(query: str) -> str | None:
    value = query.strip().rstrip("？?。！!").strip()
    for prefix in _EXPLICIT_ORGANIZATION_PREFIXES:
        if not value.startswith(prefix):
            continue
        name = value[len(prefix) :].strip()
        name = re.sub(
            r"(?:的)?(?:相关)?(?:信息|资料|情况|介绍)\s*$",
            "",
            name,
        ).strip()
        if (
            2 <= len(name) <= 80
            and "的" not in name
            and not any(marker in name for marker in ("哪些", "什么", "如何", "是否"))
            and (
                name.endswith(_ORGANIZATION_NAME_SUFFIXES)
                or (name.endswith("机器人") and len(name) > len("机器人"))
            )
        ):
            return name
    return None


def _extract_protected_slots(
    request: QueryPlanningRequest,
) -> tuple[ProtectedSlot, ...]:
    query = request.original_query
    explicit_organization_name = _explicit_organization_name(query)
    slots: list[ProtectedSlot] = []
    for match in re.finditer(r"(?<!\d)(20\d{2})(?!\d)", query):
        slots.append(
            ProtectedSlot(kind="year", value=match.group(1), raw_text=match.group(1))
        )
    for geography in ("深圳", "广州", "上海", "北京"):
        if geography in query and not (
            explicit_organization_name is not None
            and geography in explicit_organization_name
        ):
            slots.append(
                ProtectedSlot(kind="geography", value=geography, raw_text=geography)
            )
    for match in re.finditer(r"“([^”]+)”", query):
        slots.append(
            ProtectedSlot(
                kind="explicit_name",
                value=match.group(1),
                raw_text=match.group(1),
            )
        )
    for match in re.finditer(r"CN[0-9A-Z]+", query):
        slots.append(
            ProtectedSlot(
                kind="exact_identifier",
                value=match.group(0),
                raw_text=match.group(0),
            )
        )
    for match in re.finditer(r"(?:不要包含|不含|排除)([^，。]+)", query):
        term = match.group(1).strip()
        slots.append(ProtectedSlot(kind="negation", value=term, raw_text=term))
    if "公司到专利" in query:
        slots.append(
            ProtectedSlot(
                kind="relationship_direction",
                value="company_to_patent",
                raw_text="公司到专利",
            )
        )
    if request.displayed_entity_ids:
        slots.append(
            ProtectedSlot(
                kind="displayed_entity_set",
                value="displayed_entity_set",
                raw_text="",
                entity_ids=request.displayed_entity_ids,
            )
        )
    return tuple(slots)


def _retention_values(slots: Sequence[ProtectedSlot]) -> tuple[str, ...]:
    values: list[str] = []
    for slot in slots:
        if slot.kind == "displayed_entity_set":
            values.extend(slot.entity_ids)
        elif slot.value:
            values.append(slot.value)
    return tuple(values)


def _resolve_institutions(
    query: str,
    catalog: InstitutionCatalog,
) -> tuple[tuple[InstitutionSlot, ...], tuple[tuple[int, int], ...]]:
    by_term: dict[str, list[InstitutionCatalogEntry]] = {}
    for entry in catalog.entries:
        for term in (entry.canonical_name, *entry.aliases):
            by_term.setdefault(term, []).append(entry)

    matches: list[tuple[int, int, str, tuple[InstitutionCatalogEntry, ...]]] = []
    for term, entries in by_term.items():
        start = query.find(term)
        while start >= 0:
            matches.append((start, start + len(term), term, tuple(entries)))
            start = query.find(term, start + 1)
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
    selected: list[tuple[int, int, str, tuple[InstitutionCatalogEntry, ...]]] = []
    for candidate in matches:
        start, end, _, _ = candidate
        if any(
            start < kept_end and end > kept_start
            for kept_start, kept_end, *_ in selected
        ):
            continue
        selected.append(candidate)

    occupied = [(start, end) for start, end, *_ in selected]
    for match in re.finditer(r"[\u4e00-\u9fff]{2,12}大学", query):
        start, end = match.span()
        if any(
            start < kept_end and end > kept_start for kept_start, kept_end in occupied
        ):
            continue
        selected.append((start, end, match.group(0), ()))
        occupied.append((start, end))
    selected.sort(key=lambda item: item[0])

    groups: list[
        tuple[
            tuple[str, str | None, tuple[str, ...]],
            list[InstitutionOccurrence],
            tuple[InstitutionCatalogEntry, ...],
        ]
    ] = []
    positions: dict[tuple[str, str | None, tuple[str, ...]], int] = {}
    for start, end, raw_text, entries in selected:
        ids = tuple(sorted(entry.canonical_id for entry in entries))
        if len(ids) == 1:
            key = ("resolved", ids[0], ())
        elif ids:
            key = ("ambiguous", None, ids)
        else:
            key = ("unresolved", None, ())
        occurrence = InstitutionOccurrence(raw_text=raw_text, start=start, end=end)
        if key in positions:
            groups[positions[key]][1].append(occurrence)
        else:
            positions[key] = len(groups)
            groups.append((key, [occurrence], entries))

    entries_by_id = {entry.canonical_id: entry for entry in catalog.entries}
    slots: list[InstitutionSlot] = []
    for (state, canonical_id, candidate_ids), occurrences, _ in groups:
        ids = candidate_ids or ((canonical_id,) if canonical_id else ())
        candidates = tuple(
            InstitutionCandidate(
                canonical_id=item_id,
                canonical_name=entries_by_id[item_id].canonical_name,
            )
            for item_id in ids
        )
        slots.append(
            InstitutionSlot(
                resolution_state=state,
                canonical_id=canonical_id,
                candidate_ids=candidate_ids,
                occurrences=tuple(occurrences),
                catalog_sha256=catalog.content_sha256,
                catalog_version=catalog.catalog_version,
                release_id=catalog.release_id,
                candidates=candidates,
            )
        )
    spans = tuple(
        (occurrence.start, occurrence.end)
        for slot in slots
        for occurrence in slot.occurrences
    )
    return tuple(slots), spans


def _pure_topic(query: str, spans: Sequence[tuple[int, int]]) -> str:
    if not spans:
        return query
    value = query
    for start, end in sorted(spans, reverse=True):
        value = value[:start] + value[end:]
    for token in ("有哪些", "比较", "和", "的"):
        value = value.replace(token, "")
    value = re.sub(r"[，。、“”\s]+", "", value)
    return value


def _build_enumeration_policy(
    request: QueryPlanningRequest,
    proposal: RecordedPlanningProposal,
) -> EnumerationPolicy | None:
    context = request.enumeration_context
    if context is None or not context.requested:
        return None
    if context.finite_universe is not None:
        if context.finite_universe.release_id != request.release_id:
            raise InvalidRetrievalPlanError("enumeration_universe_release_mismatch")
        if proposal.enumeration_mode != "exhaustive_bounded":
            raise InvalidRetrievalPlanError("false_exhaustive_enumeration")
        universe = context.finite_universe
        return EnumerationPolicy(
            mode="exhaustive_bounded",
            scope=context.scope,
            as_of=context.as_of,
            finite_universe_id=universe.universe_id,
            eligible_member_ids=universe.member_ids,
            finite_universe_source=universe.universe_id,
            finite_universe_ids=universe.member_ids,
            exhaustive=True,
            continuation_state="complete",
        )
    if context.required_member_ids:
        if proposal.enumeration_mode != "required_members":
            raise InvalidRetrievalPlanError("false_exhaustive_enumeration")
        return EnumerationPolicy(
            mode="required_members",
            scope=context.scope,
            as_of=context.as_of,
            required_member_ids=context.required_member_ids,
            continuation_state="available",
        )
    if proposal.enumeration_mode == "exhaustive_bounded":
        raise InvalidRetrievalPlanError("false_exhaustive_enumeration")
    return EnumerationPolicy(
        mode="representative",
        scope=context.scope,
        as_of=context.as_of,
        exhaustive=False,
        continuation_state="available",
    )


def _decide_ambiguity(
    request: QueryPlanningRequest,
    policy: AmbiguityPolicy,
) -> AmbiguityDecision:
    if any(
        candidate.entity_type != policy.entity_type
        for candidate in request.ambiguity_candidates
    ):
        raise InvalidRetrievalPlanError("ambiguity_entity_type_mismatch")
    traces: list[AmbiguityCandidateTrace] = []
    eligible: list[AmbiguityCandidate] = []
    for candidate in request.ambiguity_candidates:
        conflicts = candidate.protected_constraint_conflicts
        evidence_confidence = candidate.evidence_confidence or 0.0
        is_eligible = (
            len(candidate.evidence_ids) >= policy.minimum_evidence_count
            and evidence_confidence >= policy.confidence_threshold
            and not conflicts
        )
        if conflicts:
            rejection = "protected_constraint_conflict"
        elif len(candidate.evidence_ids) < policy.minimum_evidence_count:
            rejection = "insufficient_evidence"
        elif evidence_confidence < policy.confidence_threshold:
            rejection = "below_confidence_threshold"
        else:
            rejection = None
        if is_eligible:
            eligible.append(candidate)
        traces.append(
            AmbiguityCandidateTrace(
                candidate_id=candidate.candidate_id or "",
                canonical_id=candidate.canonical_id,
                display_name=candidate.display_name,
                candidate_sha256=candidate.content_sha256,
                evidence_ids=candidate.evidence_ids,
                evidence_count=len(candidate.evidence_ids),
                evidence_confidence=evidence_confidence,
                model_confidence=candidate.model_confidence,
                protected_constraint_conflicts=conflicts,
                eligible=is_eligible,
                rejection_reason=rejection,
                discriminators=candidate.discriminators,
            )
        )

    ranked = sorted(
        eligible,
        key=lambda item: (-(item.evidence_confidence or 0.0), item.candidate_id or ""),
    )
    if not ranked:
        mode = "blocking"
        reason = "no_candidate"
        selected = None
        qualifying: tuple[str, ...] = ()
        observed_margin = None
    else:
        lead = ranked[0]
        alternatives = [
            candidate
            for candidate in request.ambiguity_candidates
            if candidate.candidate_id != lead.candidate_id
            and candidate.evidence_ids
            and not candidate.protected_constraint_conflicts
        ]
        runner = max(
            alternatives,
            key=lambda item: item.evidence_confidence or 0.0,
            default=None,
        )
        observed_margin = (
            (lead.evidence_confidence or 0.0) - (runner.evidence_confidence or 0.0)
            if runner is not None
            else None
        )
        if (
            runner is not None
            and observed_margin is not None
            and observed_margin < policy.minimum_lead_margin
        ):
            mode = "blocking"
            reason = "multiple_candidates"
            selected = None
            qualifying = tuple(
                candidate.candidate_id or ""
                for candidate in request.ambiguity_candidates
                if candidate in eligible
            )
        else:
            mode = "non_blocking"
            reason = "dominant_candidate"
            selected = lead.canonical_id
            qualifying = (lead.candidate_id or "",)
    viable = ()
    if mode == "non_blocking":
        viable = tuple(
            candidate.candidate_id or ""
            for candidate in request.ambiguity_candidates
            if candidate.canonical_id != selected
            and candidate.evidence_ids
            and not candidate.protected_constraint_conflicts
        )
    return AmbiguityDecision(
        mode=mode,
        selected_canonical_id=selected,
        reason_code=reason,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        policy_sha256=policy.content_sha256,
        request_sha256=request.content_sha256,
        candidate_manifest_sha256=request.ambiguity_candidate_manifest_sha256,
        candidate_traces=tuple(traces),
        qualifying_candidate_ids=qualifying,
        viable_alternative_ids=viable,
        observed_lead_margin=observed_margin,
    )


def _person_reference_query(
    request: QueryPlanningRequest,
    records: Sequence[PersonReferenceRecord],
    institution_slots: Sequence[InstitutionSlot],
    institution_catalog: InstitutionCatalog,
) -> InternalReferenceQuery | None:
    specs: list[tuple[str, str]] = []
    query = request.original_query
    resolved_institution_ids = tuple(
        dict.fromkeys(
            slot.canonical_id
            for slot in institution_slots
            if slot.resolution_state == "resolved" and slot.canonical_id is not None
        )
    )
    catalog_entries = {
        entry.canonical_id: entry for entry in institution_catalog.entries
    }
    if (
        any(term in query for term in ("毕业", "就读", "教育背景"))
        and len(resolved_institution_ids) == 1
    ):
        specs.append(
            (
                "education",
                catalog_entries[resolved_institution_ids[0]].canonical_name,
            )
        )
    if "创始人" in query:
        specs.append(("company_role", "founder"))
    if "深圳企业" in query:
        specs.append(("geography", "深圳"))
    if not specs:
        return None

    eligible: list[PersonReferenceRecord] = []
    nonmatching: list[ReferenceTrace] = []
    unresolved: list[ReferenceTrace] = []
    for record in records:
        if record.release_id != request.release_id:
            raise InvalidRetrievalPlanError("person_reference_release_mismatch")
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
            evidence_ids=source_facts.get(
                (field, value),
                InternalReferenceFact(field=field, value=value, evidence_ids=()),
            ).evidence_ids,
        )
        for field, value in specs
    )
    return InternalReferenceQuery(
        reference_type="person",
        release_id=request.release_id,
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
            (record.reference_id, record.content_sha256) for record in records
        ),
        public_population=False,
    )


def _technology_reference_query(
    request: QueryPlanningRequest,
    routes: Sequence[TechnologyRouteRecord],
    enumeration_policy: EnumerationPolicy | None,
) -> tuple[InternalReferenceQuery | None, tuple[UnresolvedTechnologyTerm, ...]]:
    if any(route.release_id != request.release_id for route in routes):
        raise InvalidRetrievalPlanError("technology_route_release_mismatch")
    matches: list[tuple[int, str, TechnologyRouteRecord]] = []
    for route in routes:
        terms = (route.canonical_name, *route.aliases)
        found = [(request.original_query.find(term), term) for term in terms]
        found = [(position, term) for position, term in found if position >= 0]
        if found:
            position, raw = min(found)
            matches.append((position, raw, route))
    matches.sort(key=lambda item: item[0])
    unresolved: list[UnresolvedTechnologyTerm] = []
    for match in re.finditer(r"确认([^，。及]+路线)是否已解析", request.original_query):
        raw = match.group(1)
        if not any(raw in (route.canonical_name, *route.aliases) for route in routes):
            unresolved.append(
                UnresolvedTechnologyTerm(
                    raw_text=raw,
                    canonical_route_id=None,
                    search_view_id=f"technology-search:sha256:{_canonical_sha256(raw)}",
                    gap_reason="unresolved_technology_term",
                )
            )
    if not matches:
        return None, tuple(unresolved)
    selected = [route for _, _, route in matches]
    query = InternalReferenceQuery(
        reference_type="technology_route",
        release_id=request.release_id,
        canonical_route_ids=tuple(route.canonical_route_id for route in selected),
        resolved_aliases=tuple(
            (raw, route.canonical_route_id) for _, raw, route in matches
        ),
        relationship_states=(
            "discussion_or_mention",
            "claimed_adoption",
            "demonstrated_use",
        ),
        scope=(
            request.enumeration_context.scope if request.enumeration_context else None
        ),
        as_of=request.as_of,
        definition_evidence_ids=tuple(
            evidence_id
            for route in selected
            for evidence_id in route.definition_evidence_ids
        ),
        route_content_sha256s=tuple(
            (route.reference_id, route.content_sha256) for route in selected
        ),
        definition_evidence_required=True,
        relationship_evidence_required=True,
        allowed_state_promotions=(),
        state_semantics=(
            ("discussion_or_mention", "non_adoption"),
            ("claimed_adoption", "claimed_only"),
            ("demonstrated_use", "demonstrated_only"),
        ),
        enumeration_policy=enumeration_policy,
        public_population=False,
    )
    return query, tuple(unresolved)


class _QueryPlanner:
    """Package-internal query-planning implementation seam."""

    def plan(self, request: QueryPlanningRequest) -> RetrievalPlan:
        raise NotImplementedError


class _EphemeralQueryPlanner(_QueryPlanner):
    def __init__(
        self,
        *,
        planning_policy: QueryPlanningPolicy,
        institution_catalog: InstitutionCatalog,
        proposal_provider: Callable[[QueryPlanningRequest], Any],
        ambiguity_policy: AmbiguityPolicy | None,
        person_references: tuple[PersonReferenceRecord, ...],
        technology_routes: tuple[TechnologyRouteRecord, ...],
    ) -> None:
        self._policy = planning_policy
        self._catalog = institution_catalog
        self._provider = proposal_provider
        self._ambiguity_policy = ambiguity_policy
        self._person_references = person_references
        self._technology_routes = technology_routes

    def plan(self, request: QueryPlanningRequest) -> RetrievalPlan:
        request = QueryPlanningRequest.model_validate(request.model_dump(mode="json"))
        if self._catalog.release_id != request.release_id:
            raise InvalidRetrievalPlanError("catalog_release_mismatch")
        proposal_value = self._provider(request)
        try:
            proposal = _validate_recorded(proposal_value, RecordedPlanningProposal)
        except (TypeError, ValueError, ValidationError) as exc:
            raise InvalidRetrievalPlanError("invalid_planning_proposal") from exc
        if proposal.request_sha256 != request.content_sha256:
            raise InvalidRetrievalPlanError("proposal_request_mismatch")
        if (
            proposal.max_candidates > self._policy.max_candidates
            or proposal.max_provider_calls > self._policy.max_provider_calls
            or proposal.max_web_results > self._policy.max_candidates
        ):
            raise InvalidRetrievalPlanError("budget_exceeded")
        if any(
            domain not in _PUBLIC_DOMAINS or domain not in self._policy.public_domains
            for domain in proposal.domains
        ):
            raise InvalidRetrievalPlanError(
                "internal_reference_promoted_to_public_domain"
            )
        if any(lane not in self._policy.supported_lanes for lane in proposal.lanes):
            raise InvalidRetrievalPlanError("unsupported_operation")
        if proposal.web_mode == "official_only" and not set(
            proposal.allowed_web_domains
        ) <= set(self._policy.official_web_domains):
            raise InvalidRetrievalPlanError("unsupported_official_web_domain")
        supported_by_type: dict[str, set[str]] = {}
        for relationship_type, direction in self._policy.supported_relationship_paths:
            supported_by_type.setdefault(relationship_type, set()).add(direction)
        for path in proposal.relationship_paths:
            if path.relationship_type_id == "product_has_capability":
                raise InvalidRetrievalPlanError(
                    "unsupported_product_capability_relation"
                )
            supported_directions = supported_by_type.get(path.relationship_type_id)
            if supported_directions is None:
                raise InvalidRetrievalPlanError("unsupported_relationship_path")
            if path.direction not in supported_directions:
                raise InvalidRetrievalPlanError("unsupported_relationship_direction")
            if _RELATIONSHIP_ENDPOINTS.get(
                (path.relationship_type_id, path.direction)
            ) != (
                path.source_type,
                path.target_type,
            ):
                raise InvalidRetrievalPlanError("unsupported_relationship_path")

        slots = _extract_protected_slots(request)
        required_values = set(_retention_values(slots))
        for view in proposal.query_views:
            if view.original_query_sha256 != request.original_query_sha256:
                raise InvalidRetrievalPlanError("query_view_request_mismatch")
            if not required_values <= set(view.retained_protected_values):
                raise InvalidRetrievalPlanError("lost_protected_slot")
            if any(
                slot.kind != "displayed_entity_set"
                and bool(slot.raw_text)
                and (slot.raw_text or "") not in view.text
                for slot in slots
            ):
                raise InvalidRetrievalPlanError("lost_protected_slot")

        enumeration = _build_enumeration_policy(request, proposal)
        is_information = proposal.interaction_mode == "information_retrieval"
        ambiguity = None
        if is_information:
            if self._ambiguity_policy is not None:
                ambiguity = _decide_ambiguity(request, self._ambiguity_policy)
            elif request.ambiguity_candidates:
                raise MissingAmbiguityPolicyError

        institution_slots, institution_spans = (
            _resolve_institutions(request.original_query, self._catalog)
            if is_information
            else ((), ())
        )
        blocking_institution = any(
            slot.resolution_state == "ambiguous" for slot in institution_slots
        )
        blocking_ambiguity = ambiguity is not None and ambiguity.mode == "blocking"
        interaction_mode = (
            "blocking_clarification"
            if is_information and (blocking_institution or blocking_ambiguity)
            else proposal.interaction_mode
        )
        lanes = () if interaction_mode == "blocking_clarification" else proposal.lanes

        query_views: tuple[QueryViewProposal, ...] = tuple(
            QueryViewProposal.model_validate(
                {
                    **view.model_dump(mode="json", exclude={"content_sha256"}),
                    "protected_slot_ids": tuple(slot.slot_id for slot in slots),
                    "bound_entity_ids": (
                        request.displayed_entity_ids
                        if view.kind == "contextual"
                        else view.bound_entity_ids
                    ),
                }
            )
            for view in proposal.query_views
        )
        serving_view = next(
            (view for view in proposal.query_views if view.kind == "serving_search"),
            None,
        )
        pure_topic = (
            serving_view.text
            if serving_view is not None
            else _pure_topic(request.original_query, institution_spans)
        )
        resolved_institutions = tuple(
            slot.canonical_id
            for slot in institution_slots
            if slot.canonical_id is not None
        )
        lane_queries = (
            tuple(
                LaneQuery(
                    lane=lane,
                    release_id=request.release_id,
                    catalog_sha256=self._catalog.content_sha256,
                    pure_topic_text=pure_topic,
                    query_text=f"{pure_topic} [lane={lane}]",
                    institution_constraint_ids=resolved_institutions,
                )
                for lane in lanes
            )
            if interaction_mode != "blocking_clarification"
            else ()
        )

        internal_queries: list[InternalReferenceQuery] = []
        unresolved_terms: tuple[UnresolvedTechnologyTerm, ...] = ()
        if "person" in proposal.internal_reference_targets:
            person_query = _person_reference_query(
                request,
                self._person_references,
                institution_slots,
                self._catalog,
            )
            if person_query is not None:
                internal_queries.append(person_query)
        if "technology_route" in proposal.internal_reference_targets:
            technology_query, unresolved_terms = _technology_reference_query(
                request,
                self._technology_routes,
                enumeration,
            )
            if technology_query is not None:
                internal_queries.append(technology_query)

        if interaction_mode == "blocking_clarification":
            web_policy = WebSearchPolicy(mode="disabled")
        elif proposal.web_mode == "official_only":
            web_policy = WebSearchPolicy(
                mode="official_only",
                max_provider_calls=proposal.max_provider_calls,
                timeout_ms=1_500,
                max_results=proposal.max_web_results,
                allowed_domains=proposal.allowed_web_domains,
            )
        elif proposal.interaction_mode == "information_retrieval":
            web_policy = WebSearchPolicy(
                mode="universal",
                max_provider_calls=proposal.max_provider_calls,
                timeout_ms=1_500,
                max_results=proposal.max_web_results or proposal.max_candidates,
                allowed_domains=proposal.allowed_web_domains,
            )
        else:
            web_policy = WebSearchPolicy(mode="disabled")
        allowed_operations = (
            ("official_policy_lookup",) if web_policy.mode == "official_only" else ()
        )
        structured = StructuredConstraints(
            displayed_entity_ids=request.displayed_entity_ids,
            geography=tuple(
                slot.value or "" for slot in slots if slot.kind == "geography"
            ),
            excluded_terms=tuple(
                slot.value or "" for slot in slots if slot.kind == "negation"
            ),
        )
        return RetrievalPlan(
            plan_id=f"retrieval-plan:sha256:{request.content_sha256}",
            plan_version="retrieval-plan-v1",
            request_sha256=request.content_sha256,
            original_query=request.original_query,
            behavior_class=proposal.behavior_class,
            interaction_mode=interaction_mode,
            release_id=request.release_id,
            as_of=request.as_of,
            domains=proposal.domains,
            protected_slots=slots,
            lanes=lanes,
            max_candidates=proposal.max_candidates,
            web_required="web" in lanes,
            web_policy=web_policy,
            freshness_material="web" in lanes,
            query_views=query_views,
            relationship_paths=proposal.relationship_paths,
            structured_constraints=structured,
            enumeration_policy=enumeration,
            material_parts=proposal.material_parts,
            planning_trace=PlanningTrace(
                proposal_id=proposal.proposal_id,
                proposal_sha256=proposal.content_sha256,
            ),
            assessment_intent=proposal.assessment_intent,
            professor_vector_view=(
                proposal.professor_vector_view
                if interaction_mode != "blocking_clarification"
                else None
            ),
            allowed_operations=allowed_operations,
            institution_slots=institution_slots,
            rewrite_policy=RewritePolicy(generic_topic_stopwords=()),
            pure_topic_text=pure_topic,
            lane_queries=lane_queries,
            ambiguity_decision=ambiguity,
            internal_reference_queries=tuple(internal_queries),
            unresolved_technology_terms=unresolved_terms,
        )


def create_ephemeral_query_planner(
    *,
    planning_policy: QueryPlanningPolicy,
    institution_catalog: InstitutionCatalog,
    proposal_provider: Callable[[QueryPlanningRequest], Any],
    ambiguity_policy: AmbiguityPolicy | None = None,
    person_references: tuple[PersonReferenceRecord, ...] = (),
    technology_routes: tuple[TechnologyRouteRecord, ...] = (),
) -> _QueryPlanner:
    """Create an in-memory planner around recorded, content-bound ports."""

    return _EphemeralQueryPlanner(
        planning_policy=QueryPlanningPolicy.model_validate(
            planning_policy.model_dump(mode="json")
        ),
        institution_catalog=InstitutionCatalog.model_validate(
            institution_catalog.model_dump(mode="json")
        ),
        proposal_provider=proposal_provider,
        ambiguity_policy=(
            AmbiguityPolicy.model_validate(ambiguity_policy.model_dump(mode="json"))
            if ambiguity_policy is not None
            else None
        ),
        person_references=tuple(
            PersonReferenceRecord.model_validate(record.model_dump(mode="json"))
            for record in person_references
        ),
        technology_routes=tuple(
            TechnologyRouteRecord.model_validate(route.model_dump(mode="json"))
            for route in technology_routes
        ),
    )


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
    professor_vector_view: Literal["identity", "research", "both"] | None = None
    internal_reference_queries: tuple[InternalReferenceQuery, ...] = ()
    relationship_paths: tuple[RelationshipPathProposal, ...] = ()
    relationship_reference_queries: tuple[InternalReferenceQuery, ...] = ()
    relationship_enumeration_policy: EnumerationPolicy | None = None
    bound_entity_ids: tuple[str, ...] = ()
    bound_entity_names: tuple[str, ...] = ()

    @model_serializer(mode="wrap")
    def serialize_optional_lane_fields(self, handler: Any) -> Any:
        data = handler(self)
        if self.professor_vector_view is None:
            data.pop("professor_vector_view", None)
        if not self.internal_reference_queries:
            data.pop("internal_reference_queries", None)
        if not self.relationship_paths:
            data.pop("relationship_paths", None)
        if not self.relationship_reference_queries:
            data.pop("relationship_reference_queries", None)
        if self.relationship_enumeration_policy is None:
            data.pop("relationship_enumeration_policy", None)
        return data

    @model_validator(mode="after")
    def validate_professor_vector_view(self) -> LaneRequest:
        if self.professor_vector_view is not None and not (
            self.lane == "vector"
            and self.interaction_mode == "information_retrieval"
            and "professor" in self.domains
        ):
            raise ValueError(
                "Professor vector view is valid only on a Professor vector request"
            )
        if self.internal_reference_queries and self.lane != "internal_reference":
            raise ValueError(
                "internal reference queries are valid only on the internal_reference lane"
            )
        if any(
            query.release_id != self.release_id
            for query in self.internal_reference_queries
        ):
            raise ValueError("internal reference query uses another release")
        if any(query.public_population for query in self.internal_reference_queries):
            raise ValueError("internal reference query cannot be a public population")
        if (
            self.relationship_paths or self.relationship_reference_queries
        ) and self.lane != "relationship":
            raise ValueError(
                "relationship paths and queries are valid only on the relationship lane"
            )
        if any(
            query.release_id != self.release_id
            for query in self.relationship_reference_queries
        ):
            raise ValueError("relationship reference query uses another release")
        if any(
            query.public_population for query in self.relationship_reference_queries
        ):
            raise ValueError(
                "relationship reference query cannot be a public population"
            )
        if any(
            query.reference_type != "technology_route"
            for query in self.relationship_reference_queries
        ):
            raise ValueError("relationship reference query must use technology_route")
        path_keys = tuple(
            (
                path.relationship_type_id,
                path.direction,
                path.source_type,
                path.target_type,
            )
            for path in self.relationship_paths
        )
        if self.relationship_enumeration_policy is not None and not (
            self.lane == "relationship"
            and len(path_keys) == 1
            and path_keys[0] in _PUBLIC_RELATIONSHIP_QUERY_PATHS
        ):
            raise ValueError(
                "relationship enumeration policy belongs only to the exact "
                "public relationship path"
            )
        if self.bound_entity_names and len(self.bound_entity_names) != len(
            self.bound_entity_ids
        ):
            raise ValueError("bound entity names must align with bound entity IDs")
        if any(
            not name.strip() or name != name.strip() for name in self.bound_entity_names
        ):
            raise ValueError("bound entity names must be normalized and non-empty")
        return self


class IdentityFusionRequest(_ContentModel):
    release_id: str
    raw_candidate_ids: tuple[str, ...]
    candidates: tuple[RecallCandidate, ...]


class RerankRequest(_ContentModel):
    release_id: str
    original_query: str
    eligible_candidates: tuple[FusedCandidate, ...]


class SufficiencyDecisionRequest(_ContentModel):
    plan_id: str
    release_id: str
    original_query: str
    material_parts: tuple[MaterialQuestionPart, ...]
    evidence: tuple[EvidenceItem, ...]


class SupplementalRequest(_ContentModel):
    plan_id: str
    release_id: str
    material_part_ids: tuple[str, ...]
    query_view: str


class AcceptedIdentityLookupRequest(_ContentModel):
    release_id: str
    canonical_id: str


class WebHandleResolutionRequest(_ContentModel):
    handle: WebEntityHandle
    accepted_release_id: str
    evidence_snapshot_ids: tuple[str, ...]


def _lane_request(
    plan: RetrievalPlan,
    lane: str,
    web_policy: WebSearchPolicy,
) -> LaneRequest:
    lane_query = next(
        (query for query in plan.lane_queries if query.lane == lane),
        None,
    )
    serving_view = next(
        (view for view in plan.query_views if view.kind == "serving_search"),
        None,
    )
    return LaneRequest(
        lane=lane,
        release_id=plan.release_id,
        query_view="view:original",
        original_query=plan.original_query,
        behavior_class=plan.behavior_class,
        interaction_mode=plan.interaction_mode,
        web_policy=web_policy,
        query_text=(
            lane_query.query_text if lane_query is not None else plan.original_query
        ),
        domains=plan.domains,
        protected_slots=plan.protected_slots,
        structured_constraints=plan.structured_constraints,
        max_candidates=plan.max_candidates,
        professor_vector_view=(
            plan.professor_vector_view if lane == "vector" else None
        ),
        internal_reference_queries=(
            plan.internal_reference_queries if lane == "internal_reference" else ()
        ),
        relationship_paths=(plan.relationship_paths if lane == "relationship" else ()),
        relationship_reference_queries=(
            tuple(
                query
                for query in plan.internal_reference_queries
                if query.reference_type == "technology_route"
            )
            if lane == "relationship"
            else ()
        ),
        relationship_enumeration_policy=(
            plan.enumeration_policy
            if lane == "relationship"
            and len(plan.relationship_paths) == 1
            and (
                plan.relationship_paths[0].relationship_type_id,
                plan.relationship_paths[0].direction,
                plan.relationship_paths[0].source_type,
                plan.relationship_paths[0].target_type,
            )
            in _PUBLIC_RELATIONSHIP_QUERY_PATHS
            else None
        ),
        bound_entity_ids=(
            serving_view.bound_entity_ids if serving_view is not None else ()
        ),
        bound_entity_names=(
            serving_view.bound_entity_names if serving_view is not None else ()
        ),
    )


def _local_projection_locator(trace: LocalEvidenceTrace) -> str:
    if isinstance(
        trace,
        (
            LocalRelationshipTrace,
            LocalCanonicalRelationshipTrace,
            LocalPatentCompanyRelationshipTrace,
            LocalProfessorPaperRelationshipTrace,
            LocalPaperProfessorRelationshipTrace,
            LocalSourceRelationshipTrace,
        ),
    ):
        local_id = trace.canonical_relationship_id
    elif isinstance(trace, LocalVectorTrace):
        local_id = trace.point_id
    else:
        local_id = trace.document_id
    return f"canonical-v2-isolated:{trace.target_id}:{local_id}"


def _relationship_snapshot_quality_flag(value: datetime) -> str:
    canonical = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return f"relationship_snapshot_as_of:{canonical}"


def _projection_identifier_values(snippet: str, domain: str) -> frozenset[str]:
    try:
        payload = json.loads(snippet)
    except (json.JSONDecodeError, TypeError):
        return frozenset()
    if not isinstance(payload, dict):
        return frozenset()

    values: list[object] = [payload.get("id")]
    if domain == "company":
        values.append(payload.get("credit_code"))
    elif domain == "paper":
        values.extend((payload.get("doi"), payload.get("arxiv_id")))
        identifiers = payload.get("identifiers")
        if isinstance(identifiers, list):
            values.extend(
                identifier.get("value")
                for identifier in identifiers
                if isinstance(identifier, dict)
            )
    elif domain == "patent":
        values.append(payload.get("patent_number"))

    return frozenset(
        " ".join(value.casefold().split())
        for value in values
        if isinstance(value, str) and value.strip()
    )


def _valid_exact_identifier_projection_claim(
    *,
    claim: EvidenceClaimBinding,
    request: LaneRequest,
    snippet: str,
    domain: str,
) -> bool:
    if claim.predicate != "exact_identifier" or not isinstance(claim.value, str):
        return False
    normalized_claim = " ".join(claim.value.casefold().split())
    requested_identifiers = {
        " ".join(slot.value.casefold().split())
        for slot in request.protected_slots
        if slot.kind == "exact_identifier"
        and isinstance(slot.value, str)
        and slot.value.strip()
    }
    return (
        normalized_claim in requested_identifiers
        and normalized_claim in _projection_identifier_values(snippet, domain)
    )


def _valid_local_projection_item(
    item: EvidenceItem,
    request: LaneRequest,
) -> bool:
    trace = item.local_projection_trace
    if trace is None:
        return True
    claim = item.claim_binding
    if isinstance(trace, LocalSourceRelationshipTrace):
        policy = request.relationship_enumeration_policy
        path_keys = tuple(
            (
                path.relationship_type_id,
                path.direction,
                path.source_type,
                path.target_type,
            )
            for path in request.relationship_paths
        )
        protected_slots = tuple(
            slot
            for slot in request.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        return (
            path_keys
            == (
                (
                    trace.query_relationship_type_id,
                    trace.query_direction,
                    trace.query_source_type,
                    trace.query_target_type,
                ),
            )
            and policy is not None
            and trace.relationship_enumeration_policy_sha256
            == _canonical_sha256(policy.model_dump(mode="json"))
            and trace.displayed_entity_ids
            == request.structured_constraints.displayed_entity_ids
            and len(protected_slots) == 1
            and protected_slots[0].slot_id == trace.protected_slot_id
            and _canonical_sha256(protected_slots[0].model_dump(mode="json"))
            == trace.protected_slot_content_sha256
            and protected_slots[0].entity_ids == trace.displayed_entity_ids
            and request.lane == item.lane == "relationship"
            and item.source_nature == "local"
            and item.source_authority == "canonical_release"
            and item.evidence_id == trace.evidence_id
            and item.object_id == trace.candidate_canonical_id
            and item.domain == trace.candidate_domain
            and request.domains == (trace.candidate_domain,)
            and trace.release_id == request.release_id
            and trace.lane_request_content_sha256 == request.content_sha256
            and item.source_locator == _local_projection_locator(trace)
            and item.score == 1.0
            and item.observed_at == trace.relationship_snapshot_as_of
            and hashlib.sha256(item.snippet.encode("utf-8")).hexdigest()
            == trace.snippet_sha256
            and claim
            == EvidenceClaimBinding(
                subject_id=trace.claim_subject_id,
                predicate=trace.claim_predicate,
                value=trace.claim_value,
                status=trace.claim_status,
            )
        )
    if isinstance(trace, LocalPaperProfessorRelationshipTrace):
        policy = request.relationship_enumeration_policy
        paths = tuple(
            (
                path.relationship_type_id,
                path.direction,
                path.source_type,
                path.target_type,
            )
            for path in request.relationship_paths
        )
        protected_slots = tuple(
            slot
            for slot in request.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        return (
            paths == (_PAPER_TO_PROFESSOR_QUERY_PATH,)
            and policy is not None
            and trace.relationship_enumeration_policy_sha256
            == _canonical_sha256(policy.model_dump(mode="json"))
            and trace.displayed_entity_ids
            == request.structured_constraints.displayed_entity_ids
            and len(protected_slots) == 1
            and protected_slots[0].slot_id == trace.protected_slot_id
            and _canonical_sha256(protected_slots[0].model_dump(mode="json"))
            == trace.protected_slot_content_sha256
            and protected_slots[0].entity_ids == trace.displayed_entity_ids
            and request.lane == "relationship"
            and item.lane == "relationship"
            and item.source_nature == trace.evidence_source_nature == "local"
            and item.source_authority
            == trace.evidence_source_authority
            == "canonical_release"
            and item.evidence_id == trace.evidence_id
            and item.object_id == trace.professor_id
            and item.domain == "professor"
            and request.domains == ("professor",)
            and trace.release_id == request.release_id
            and trace.lane_request_content_sha256 == request.content_sha256
            and item.source_locator == trace.evidence_source_locator
            and item.source_locator == _local_projection_locator(trace)
            and item.score == trace.candidate_raw_score == 1.0
            and item.observed_at
            == trace.evidence_observed_at
            == trace.relationship_snapshot_as_of
            and hashlib.sha256(item.snippet.encode("utf-8")).hexdigest()
            == trace.snippet_sha256
            and claim is not None
            and claim.subject_id == trace.claim_subject_id
            and claim.predicate == trace.claim_predicate
            and claim.value == trace.claim_value
            and claim.status == trace.claim_status
        )
    if isinstance(trace, LocalProfessorPaperRelationshipTrace):
        policy = request.relationship_enumeration_policy
        paths = tuple(
            (
                path.relationship_type_id,
                path.direction,
                path.source_type,
                path.target_type,
            )
            for path in request.relationship_paths
        )
        protected_slots = tuple(
            slot
            for slot in request.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        return (
            paths == (_PROFESSOR_TO_PAPER_QUERY_PATH,)
            and policy is not None
            and trace.relationship_enumeration_policy_sha256
            == _canonical_sha256(policy.model_dump(mode="json"))
            and trace.displayed_entity_ids
            == request.structured_constraints.displayed_entity_ids
            and len(protected_slots) == 1
            and protected_slots[0].slot_id == trace.protected_slot_id
            and _canonical_sha256(protected_slots[0].model_dump(mode="json"))
            == trace.protected_slot_content_sha256
            and protected_slots[0].entity_ids == trace.displayed_entity_ids
            and request.lane == "relationship"
            and item.lane == "relationship"
            and item.source_nature == trace.evidence_source_nature == "local"
            and item.source_authority
            == trace.evidence_source_authority
            == "canonical_release"
            and item.evidence_id == trace.evidence_id
            and item.object_id == trace.paper_id
            and item.domain == "paper"
            and request.domains == ("paper",)
            and trace.release_id == request.release_id
            and trace.lane_request_content_sha256 == request.content_sha256
            and item.source_locator == trace.evidence_source_locator
            and item.source_locator == _local_projection_locator(trace)
            and item.score == trace.candidate_raw_score == 1.0
            and item.observed_at
            == trace.evidence_observed_at
            == trace.relationship_snapshot_as_of
            and hashlib.sha256(item.snippet.encode("utf-8")).hexdigest()
            == trace.snippet_sha256
            and claim is not None
            and claim.subject_id == trace.claim_subject_id
            and claim.predicate == trace.claim_predicate
            and claim.value == trace.claim_value
            and claim.status == trace.claim_status
        )
    if isinstance(trace, LocalPatentCompanyRelationshipTrace):
        policy = request.relationship_enumeration_policy
        paths = tuple(
            (
                path.relationship_type_id,
                path.direction,
                path.source_type,
                path.target_type,
            )
            for path in request.relationship_paths
        )
        protected_slots = tuple(
            slot
            for slot in request.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        return (
            paths == (_PATENT_TO_COMPANY_QUERY_PATH,)
            and policy is not None
            and trace.relationship_enumeration_policy_sha256
            == _canonical_sha256(policy.model_dump(mode="json"))
            and trace.displayed_entity_ids
            == request.structured_constraints.displayed_entity_ids
            and len(protected_slots) == 1
            and protected_slots[0].slot_id == trace.protected_slot_id
            and _canonical_sha256(protected_slots[0].model_dump(mode="json"))
            == trace.protected_slot_content_sha256
            and protected_slots[0].entity_ids == trace.displayed_entity_ids
            and request.lane == "relationship"
            and item.lane == "relationship"
            and item.source_nature == "local"
            and item.source_authority == "canonical_release"
            and item.evidence_id == trace.evidence_id
            and item.object_id == trace.company_id
            and item.domain == "company"
            and request.domains == ("company",)
            and trace.release_id == request.release_id
            and trace.lane_request_content_sha256 == request.content_sha256
            and item.source_locator == _local_projection_locator(trace)
            and item.score == trace.candidate_raw_score == 1.0
            and item.observed_at == trace.relationship_snapshot_as_of
            and hashlib.sha256(item.snippet.encode("utf-8")).hexdigest()
            == trace.snippet_sha256
            and claim is not None
            and claim.subject_id == trace.claim_subject_id
            and claim.predicate == trace.claim_predicate
            and claim.value == trace.claim_value
            and claim.status == trace.claim_status
        )
    if isinstance(trace, LocalCanonicalRelationshipTrace):
        policy = request.relationship_enumeration_policy
        paths = tuple(
            (
                path.relationship_type_id,
                path.direction,
                path.source_type,
                path.target_type,
            )
            for path in request.relationship_paths
        )
        protected_slots = tuple(
            slot
            for slot in request.protected_slots
            if slot.kind == "displayed_entity_set"
        )
        return (
            paths == (_COMPANY_TO_PATENT_QUERY_PATH,)
            and policy is not None
            and trace.relationship_enumeration_policy_sha256
            == _canonical_sha256(policy.model_dump(mode="json"))
            and trace.displayed_entity_ids
            == request.structured_constraints.displayed_entity_ids
            and len(protected_slots) == 1
            and protected_slots[0].slot_id == trace.protected_slot_id
            and _canonical_sha256(protected_slots[0].model_dump(mode="json"))
            == trace.protected_slot_content_sha256
            and protected_slots[0].entity_ids == trace.displayed_entity_ids
            and request.lane == "relationship"
            and item.lane == "relationship"
            and item.source_nature == "local"
            and item.source_authority == "canonical_release"
            and item.evidence_id == trace.evidence_id
            and item.object_id == trace.patent_id
            and item.domain == "patent"
            and request.domains == ("patent",)
            and trace.release_id == request.release_id
            and trace.lane_request_content_sha256 == request.content_sha256
            and item.source_locator == _local_projection_locator(trace)
            and item.score == trace.candidate_raw_score == 1.0
            and item.observed_at == trace.relationship_snapshot_as_of
            and hashlib.sha256(item.snippet.encode("utf-8")).hexdigest()
            == trace.snippet_sha256
            and claim is not None
            and claim.subject_id == trace.claim_subject_id
            and claim.predicate == trace.claim_predicate
            and claim.value == trace.claim_value
            and claim.status == trace.claim_status
        )
    if isinstance(trace, LocalRelationshipTrace):
        paths = tuple(
            path
            for path in request.relationship_paths
            if (
                path.relationship_type_id == trace.query_relationship_type_id
                and path.direction == trace.query_direction
                and path.source_type == trace.query_source_type
                and path.target_type == trace.query_target_type
            )
        )
        queries = tuple(
            query
            for query in request.relationship_reference_queries
            if query.reference_type == "technology_route"
            and trace.technology_route_id in query.canonical_route_ids
        )
        return (
            len(paths) == 1
            and len(queries) == 1
            and request.lane == "relationship"
            and item.lane == "relationship"
            and item.source_nature == "local"
            and item.source_authority == "canonical_release"
            and item.evidence_id == trace.evidence_id
            and item.object_id == trace.root_company_id
            and item.domain == "company"
            and "company" in request.domains
            and trace.release_id == request.release_id == queries[0].release_id
            and trace.lane_request_content_sha256 == request.content_sha256
            and item.source_locator == _local_projection_locator(trace)
            and item.score == 1.0
            and item.observed_at == trace.relationship_snapshot_as_of
            and hashlib.sha256(item.snippet.encode("utf-8")).hexdigest()
            == trace.snippet_sha256
            and claim is not None
            and claim.subject_id == trace.claim_subject_id
            and claim.predicate == trace.claim_predicate
            and claim.value == trace.claim_value
            and claim.status == trace.claim_status
            and claim.predicate != "product_has_capability"
        )
    if isinstance(trace, LocalInternalReferenceTrace):
        matching_queries = tuple(
            query
            for query in request.internal_reference_queries
            if query.reference_type == trace.reference_type
        )
        if len(matching_queries) != 1:
            return False
        query = matching_queries[0]
        if trace.reference_type == "person":
            query_valid = (
                trace.internal_reference_id in query.eligible_reference_ids
                and trace.matched_filter_facts == query.typed_filters
                and trace.claim_evidence_ids
                == tuple(
                    sorted(
                        {
                            evidence_id
                            for fact in query.typed_filters
                            for evidence_id in fact.evidence_ids
                        }
                    )
                )
            )
        else:
            query_valid = (
                trace.internal_reference_id in query.canonical_route_ids
                and not trace.matched_filter_facts
                and set(trace.claim_evidence_ids) <= set(query.definition_evidence_ids)
            )
        return (
            query_valid
            and request.lane == "internal_reference"
            and item.lane == "internal_reference"
            and item.source_nature == "local"
            and item.source_authority == "canonical_release"
            and item.evidence_id == trace.evidence_id
            and item.object_id == trace.public_origin_canonical_id
            and item.domain == trace.public_origin_domain
            and trace.public_origin_domain in request.domains
            and trace.release_id == request.release_id == query.release_id
            and trace.lane_request_content_sha256 == request.content_sha256
            and item.source_locator == _local_projection_locator(trace)
            and item.score == 1.0
            and hashlib.sha256(item.snippet.encode("utf-8")).hexdigest()
            == trace.snippet_sha256
            and claim is not None
            and claim.subject_id == trace.claim_subject_id
            and claim.predicate == trace.claim_predicate
            and claim.value == trace.claim_value
            and claim.status is None
            and (
                trace.reference_type != "technology_route"
                or item.snippet == trace.claim_value
            )
        )
    common_valid = (
        request.lane == trace.execution_lane
        and item.lane == trace.execution_lane
        and item.source_nature == "local"
        and item.source_authority == "canonical_release"
        and item.evidence_id == trace.evidence_id
        and item.object_id == trace.canonical_object_id
        and item.domain == trace.domain
        and trace.domain in request.domains
        and trace.release_id == request.release_id
        and item.source_locator == _local_projection_locator(trace)
        and claim is not None
        and claim.subject_id == trace.canonical_object_id
        and claim.status == trace.eligibility_outcome
    )
    if not common_valid or claim is None:
        return False
    snippet_sha256 = hashlib.sha256(item.snippet.encode("utf-8")).hexdigest()
    if isinstance(trace, LocalVectorTrace):
        return (
            snippet_sha256 == trace.embedded_content_sha256
            and hashlib.sha256(request.query_text.encode("utf-8")).hexdigest()
            == trace.lane_query_text_sha256
            and item.score == trace.similarity_score
            and claim.predicate == "semantic_recall"
            and claim.value == trace.embedded_content_sha256
        )
    return (
        snippet_sha256 == trace.lookup_content_sha256
        and item.score == 1.0
        and (
            (
                claim.predicate == "canonical_projection"
                and claim.value == trace.lookup_content_sha256
            )
            or _valid_exact_identifier_projection_claim(
                claim=claim,
                request=request,
                snippet=item.snippet,
                domain=item.domain,
            )
        )
    )


def _valid_local_projection_candidate(
    candidate: RecallCandidate,
    request: LaneRequest,
) -> bool:
    traces = tuple(
        item.local_projection_trace
        for item in candidate.evidence
        if item.local_projection_trace is not None
    )
    if not traces:
        return True
    if len(traces) != len(candidate.evidence):
        return False
    source_relationship_traces = tuple(
        trace for trace in traces if isinstance(trace, LocalSourceRelationshipTrace)
    )
    if source_relationship_traces:
        if len(source_relationship_traces) != len(traces):
            return False
        canonical_ids = {
            trace.candidate_canonical_id for trace in source_relationship_traces
        }
        domains = {trace.candidate_domain for trace in source_relationship_traces}
        display_names = {
            trace.candidate_display_name for trace in source_relationship_traces
        }
        candidate_ids = {trace.raw_candidate_id for trace in source_relationship_traces}
        displayed_ids = {
            trace.displayed_entity_id for trace in source_relationship_traces
        }
        protected_slots = {
            (trace.protected_slot_id, trace.protected_slot_content_sha256)
            for trace in source_relationship_traces
        }
        origin_ids = tuple(
            sorted(
                {
                    evidence_id
                    for trace in source_relationship_traces
                    for evidence_id in trace.candidate_origin_public_evidence_ids
                }
            )
        )
        quality_flags = tuple(
            dict.fromkeys(
                flag
                for trace in source_relationship_traces
                for flag in trace.candidate_quality_flags
            )
        )
        return (
            request.lane == candidate.lane == "relationship"
            and len(canonical_ids) == 1
            and candidate.canonical_id == next(iter(canonical_ids))
            and len(domains) == 1
            and candidate.domain == next(iter(domains))
            and request.domains == (candidate.domain,)
            and len(display_names) == 1
            and candidate.display_name == next(iter(display_names))
            and len(candidate_ids) == 1
            and candidate.raw_candidate_id == next(iter(candidate_ids))
            and len(displayed_ids) == 1
            and len(protected_slots) == 1
            and candidate.reference_type is None
            and candidate.identity_kind == "canonical"
            and candidate.resolution_state == "resolved"
            and candidate.relationship_state == "accepted"
            and candidate.release_id == request.release_id
            and candidate.query_view == request.query_view
            and candidate.attempt == 1
            and candidate.origin_public_evidence_ids == origin_ids
            and candidate.quality_flags == quality_flags
            and candidate.raw_score == 1.0
            and all(item.score == candidate.raw_score for item in candidate.evidence)
        )
    paper_professor_traces = tuple(
        trace
        for trace in traces
        if isinstance(trace, LocalPaperProfessorRelationshipTrace)
    )
    if paper_professor_traces:
        if len(paper_professor_traces) != len(traces):
            return False
        professor_ids = {trace.professor_id for trace in paper_professor_traces}
        display_names = {
            trace.professor_display_name for trace in paper_professor_traces
        }
        candidate_ids = {trace.raw_candidate_id for trace in paper_professor_traces}
        paper_ids = {trace.displayed_paper_id for trace in paper_professor_traces}
        policy_hashes = {
            trace.relationship_enumeration_policy_sha256
            for trace in paper_professor_traces
        }
        protected_slots = {
            (trace.protected_slot_id, trace.protected_slot_content_sha256)
            for trace in paper_professor_traces
        }
        origin_ids = tuple(
            sorted(
                {
                    evidence_id
                    for trace in paper_professor_traces
                    for evidence_id in trace.candidate_origin_public_evidence_ids
                }
            )
        )
        quality_flags = tuple(
            dict.fromkeys(
                flag
                for trace in paper_professor_traces
                for flag in trace.candidate_quality_flags
            )
        )
        return (
            request.lane == "relationship"
            and candidate.lane == "relationship"
            and len(professor_ids) == 1
            and candidate.canonical_id == next(iter(professor_ids))
            and candidate.domain == "professor"
            and request.domains == ("professor",)
            and len(display_names) == 1
            and candidate.display_name == next(iter(display_names))
            and len(candidate_ids) == 1
            and candidate.raw_candidate_id == next(iter(candidate_ids))
            and len(paper_ids) == 1
            and len(policy_hashes) == 1
            and len(protected_slots) == 1
            and candidate.reference_type is None
            and candidate.identity_kind == "canonical"
            and candidate.resolution_state == "resolved"
            and candidate.relationship_state == "accepted"
            and candidate.release_id == request.release_id
            and candidate.query_view == request.query_view
            and candidate.attempt == 1
            and candidate.origin_public_evidence_ids == origin_ids
            and candidate.quality_flags == quality_flags
            and candidate.raw_score == 1.0
            and all(item.score == candidate.raw_score for item in candidate.evidence)
        )
    professor_paper_traces = tuple(
        trace
        for trace in traces
        if isinstance(trace, LocalProfessorPaperRelationshipTrace)
    )
    if professor_paper_traces:
        if len(professor_paper_traces) != len(traces):
            return False
        paper_ids = {trace.paper_id for trace in professor_paper_traces}
        display_names = {trace.paper_display_name for trace in professor_paper_traces}
        candidate_ids = {trace.raw_candidate_id for trace in professor_paper_traces}
        professor_ids = {
            trace.displayed_professor_id for trace in professor_paper_traces
        }
        policy_hashes = {
            trace.relationship_enumeration_policy_sha256
            for trace in professor_paper_traces
        }
        protected_slots = {
            (trace.protected_slot_id, trace.protected_slot_content_sha256)
            for trace in professor_paper_traces
        }
        origin_ids = tuple(
            sorted(
                {
                    evidence_id
                    for trace in professor_paper_traces
                    for evidence_id in trace.candidate_origin_public_evidence_ids
                }
            )
        )
        quality_flags = tuple(
            dict.fromkeys(
                flag
                for trace in professor_paper_traces
                for flag in trace.candidate_quality_flags
            )
        )
        return (
            request.lane == "relationship"
            and candidate.lane == "relationship"
            and len(paper_ids) == 1
            and candidate.canonical_id == next(iter(paper_ids))
            and candidate.domain == "paper"
            and request.domains == ("paper",)
            and len(display_names) == 1
            and candidate.display_name == next(iter(display_names))
            and len(candidate_ids) == 1
            and candidate.raw_candidate_id == next(iter(candidate_ids))
            and len(professor_ids) == 1
            and len(policy_hashes) == 1
            and len(protected_slots) == 1
            and candidate.reference_type is None
            and candidate.identity_kind == "canonical"
            and candidate.resolution_state == "resolved"
            and candidate.relationship_state == "accepted"
            and candidate.release_id == request.release_id
            and candidate.query_view == request.query_view
            and candidate.attempt == 1
            and candidate.origin_public_evidence_ids == origin_ids
            and candidate.quality_flags == quality_flags
            and candidate.raw_score == 1.0
            and all(item.score == candidate.raw_score for item in candidate.evidence)
        )
    patent_company_traces = tuple(
        trace
        for trace in traces
        if isinstance(trace, LocalPatentCompanyRelationshipTrace)
    )
    if patent_company_traces:
        if len(patent_company_traces) != len(traces):
            return False
        company_ids = {trace.company_id for trace in patent_company_traces}
        display_names = {trace.company_display_name for trace in patent_company_traces}
        candidate_ids = {trace.raw_candidate_id for trace in patent_company_traces}
        patent_ids = {trace.displayed_patent_id for trace in patent_company_traces}
        policy_hashes = {
            trace.relationship_enumeration_policy_sha256
            for trace in patent_company_traces
        }
        protected_slots = {
            (trace.protected_slot_id, trace.protected_slot_content_sha256)
            for trace in patent_company_traces
        }
        origin_ids = tuple(
            sorted(
                {
                    evidence_id
                    for trace in patent_company_traces
                    for evidence_id in trace.candidate_origin_public_evidence_ids
                }
            )
        )
        quality_flags = tuple(
            dict.fromkeys(
                flag
                for trace in patent_company_traces
                for flag in trace.candidate_quality_flags
            )
        )
        return (
            request.lane == "relationship"
            and candidate.lane == "relationship"
            and len(company_ids) == 1
            and candidate.canonical_id == next(iter(company_ids))
            and candidate.domain == "company"
            and request.domains == ("company",)
            and len(display_names) == 1
            and candidate.display_name == next(iter(display_names))
            and len(candidate_ids) == 1
            and candidate.raw_candidate_id == next(iter(candidate_ids))
            and len(patent_ids) == 1
            and len(policy_hashes) == 1
            and len(protected_slots) == 1
            and candidate.reference_type is None
            and candidate.identity_kind == "canonical"
            and candidate.resolution_state == "resolved"
            and candidate.relationship_state == "accepted"
            and candidate.release_id == request.release_id
            and candidate.query_view == request.query_view
            and candidate.attempt == 1
            and candidate.origin_public_evidence_ids == origin_ids
            and candidate.quality_flags == quality_flags
            and candidate.raw_score == 1.0
            and all(item.score == candidate.raw_score for item in candidate.evidence)
        )
    canonical_relationship_traces = tuple(
        trace for trace in traces if isinstance(trace, LocalCanonicalRelationshipTrace)
    )
    if canonical_relationship_traces:
        if len(canonical_relationship_traces) != len(traces):
            return False
        patent_ids = {trace.patent_id for trace in canonical_relationship_traces}
        display_names = {
            trace.patent_display_name for trace in canonical_relationship_traces
        }
        candidate_ids = {
            trace.raw_candidate_id for trace in canonical_relationship_traces
        }
        company_ids = {
            trace.displayed_company_id for trace in canonical_relationship_traces
        }
        policy_hashes = {
            trace.relationship_enumeration_policy_sha256
            for trace in canonical_relationship_traces
        }
        protected_slots = {
            (trace.protected_slot_id, trace.protected_slot_content_sha256)
            for trace in canonical_relationship_traces
        }
        origin_ids = tuple(
            sorted(
                {
                    evidence_id
                    for trace in canonical_relationship_traces
                    for evidence_id in trace.candidate_origin_public_evidence_ids
                }
            )
        )
        quality_flags = tuple(
            dict.fromkeys(
                flag
                for trace in canonical_relationship_traces
                for flag in trace.candidate_quality_flags
            )
        )
        return (
            request.lane == "relationship"
            and candidate.lane == "relationship"
            and len(patent_ids) == 1
            and candidate.canonical_id == next(iter(patent_ids))
            and candidate.domain == "patent"
            and request.domains == ("patent",)
            and len(display_names) == 1
            and candidate.display_name == next(iter(display_names))
            and len(candidate_ids) == 1
            and candidate.raw_candidate_id == next(iter(candidate_ids))
            and len(company_ids) == 1
            and len(policy_hashes) == 1
            and len(protected_slots) == 1
            and candidate.reference_type is None
            and candidate.identity_kind == "canonical"
            and candidate.resolution_state == "resolved"
            and candidate.relationship_state == "accepted"
            and candidate.release_id == request.release_id
            and candidate.query_view == request.query_view
            and candidate.attempt == 1
            and candidate.origin_public_evidence_ids == origin_ids
            and candidate.quality_flags == quality_flags
            and candidate.raw_score == 1.0
            and all(item.score == candidate.raw_score for item in candidate.evidence)
        )
    relationship_traces = tuple(
        trace for trace in traces if isinstance(trace, LocalRelationshipTrace)
    )
    if relationship_traces:
        if len(relationship_traces) != len(traces):
            return False
        root_ids = {trace.root_company_id for trace in relationship_traces}
        display_names = {
            trace.root_company_display_name for trace in relationship_traces
        }
        candidate_ids = {trace.raw_candidate_id for trace in relationship_traces}
        states = {trace.relationship_state for trace in relationship_traces}
        route_ids = {trace.technology_route_id for trace in relationship_traces}
        anchor_ids = tuple(trace.technology_anchor_id for trace in relationship_traces)
        limitations = tuple(
            sorted(
                {
                    limitation
                    for trace in relationship_traces
                    for limitation in trace.eligibility_limitations
                }
            )
        )
        snapshot_times = {
            trace.relationship_snapshot_as_of for trace in relationship_traces
        }
        query_times = {trace.query_as_of for trace in relationship_traces}
        freshness_flags = (
            (_relationship_snapshot_quality_flag(next(iter(snapshot_times))),)
            if len(snapshot_times) == 1
            and len(query_times) == 1
            and next(iter(query_times)) > next(iter(snapshot_times))
            else ()
        )
        return (
            request.lane == "relationship"
            and candidate.lane == "relationship"
            and len(root_ids) == 1
            and candidate.canonical_id == next(iter(root_ids))
            and candidate.domain == "company"
            and "company" in request.domains
            and len(display_names) == 1
            and candidate.display_name == next(iter(display_names))
            and len(candidate_ids) == 1
            and candidate.raw_candidate_id == next(iter(candidate_ids))
            and len(states) == 1
            and candidate.relationship_state == next(iter(states))
            and len(route_ids) == 1
            and candidate.reference_type == "technology_route"
            and len(snapshot_times) == 1
            and len(query_times) == 1
            and candidate.identity_kind == "canonical"
            and candidate.resolution_state == "resolved"
            and candidate.release_id == request.release_id
            and candidate.query_view == request.query_view
            and candidate.attempt == 1
            and anchor_ids == tuple(sorted(set(anchor_ids)))
            and candidate.origin_public_evidence_ids == anchor_ids
            and candidate.quality_flags == (*limitations, *freshness_flags)
            and candidate.raw_score == 1.0
            and all(item.score == candidate.raw_score for item in candidate.evidence)
        )
    internal_traces = tuple(
        trace for trace in traces if isinstance(trace, LocalInternalReferenceTrace)
    )
    if internal_traces:
        if len(internal_traces) != len(traces):
            return False
        object_ids = {trace.public_origin_canonical_id for trace in internal_traces}
        domains = {trace.public_origin_domain for trace in internal_traces}
        candidate_ids = {trace.raw_candidate_id for trace in internal_traces}
        reference_types = {trace.reference_type for trace in internal_traces}
        internal_ids = {trace.internal_reference_id for trace in internal_traces}
        anchor_ids = tuple(trace.public_origin_anchor_id for trace in internal_traces)
        return (
            request.lane == "internal_reference"
            and candidate.lane == "internal_reference"
            and len(object_ids) == 1
            and candidate.canonical_id == next(iter(object_ids))
            and len(domains) == 1
            and candidate.domain == next(iter(domains))
            and candidate.domain in request.domains
            and len(candidate_ids) == 1
            and candidate.raw_candidate_id == next(iter(candidate_ids))
            and len(reference_types) == 1
            and candidate.reference_type == next(iter(reference_types))
            and len(internal_ids) == 1
            and candidate.identity_kind == "canonical"
            and candidate.resolution_state == "resolved"
            and candidate.relationship_state is None
            and candidate.release_id == request.release_id
            and candidate.query_view == request.query_view
            and candidate.attempt == 1
            and anchor_ids == tuple(sorted(set(anchor_ids)))
            and candidate.origin_public_evidence_ids == anchor_ids
            and candidate.quality_flags == ()
            and all(item.score == candidate.raw_score for item in candidate.evidence)
        )
    public_traces = tuple(
        trace
        for trace in traces
        if isinstance(trace, (LocalProjectionTrace, LocalVectorTrace))
    )
    if len(public_traces) != len(traces):
        return False
    object_ids = {trace.canonical_object_id for trace in public_traces}
    domains = {trace.domain for trace in public_traces}
    candidate_ids = {trace.raw_candidate_id for trace in public_traces}
    execution_lanes = {trace.execution_lane for trace in public_traces}
    source_evidence_ids = tuple(
        sorted(
            {
                evidence_id
                for trace in public_traces
                for evidence_id in trace.source_evidence_ids
            }
        )
    )
    limitations = tuple(
        sorted(
            {
                limitation
                for trace in public_traces
                for limitation in trace.eligibility_limitations
            }
        )
    )
    return (
        len(execution_lanes) == 1
        and candidate.lane == next(iter(execution_lanes))
        and candidate.lane == request.lane
        and len(object_ids) == 1
        and candidate.canonical_id == next(iter(object_ids))
        and len(domains) == 1
        and candidate.domain == next(iter(domains))
        and candidate.domain in request.domains
        and len(candidate_ids) == 1
        and candidate.raw_candidate_id == next(iter(candidate_ids))
        and candidate.release_id == request.release_id
        and candidate.origin_public_evidence_ids == source_evidence_ids
        and candidate.quality_flags == limitations
        and all(item.score == candidate.raw_score for item in candidate.evidence)
    )


def _domain_allowed(locator: str, allowed_domains: Sequence[str]) -> bool:
    host = (urlparse(locator).hostname or "").lower()
    return any(
        host == domain or host.endswith(f".{domain}") for domain in allowed_domains
    )


def _default_groups(
    candidates: Sequence[RecallCandidate],
) -> tuple[tuple[str | None, tuple[RecallCandidate, ...]], ...]:
    order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], list[RecallCandidate]] = {}
    for candidate in candidates:
        if (
            candidate.reference_type == "person"
            and candidate.resolution_state != "resolved"
        ):
            continue
        key = (
            ("canonical", candidate.canonical_id)
            if candidate.canonical_id is not None
            else ("raw", candidate.raw_candidate_id)
        )
        typed_key = (key[0], key[1] or "")
        if typed_key not in grouped:
            order.append(typed_key)
            grouped[typed_key] = []
        grouped[typed_key].append(candidate)
    return tuple(
        (
            (key[1] if key[0] == "canonical" else None),
            tuple(grouped[key]),
        )
        for key in order
    )


def _unique_items(items: Sequence[EvidenceItem]) -> tuple[EvidenceItem, ...]:
    seen: set[str] = set()
    values: list[EvidenceItem] = []
    for item in items:
        if item.evidence_id not in seen:
            seen.add(item.evidence_id)
            values.append(item)
    return tuple(values)


def _fused_candidate(
    canonical_id: str | None,
    candidates: Sequence[RecallCandidate],
) -> FusedCandidate:
    first = candidates[0]
    evidence = _unique_items(
        [item for candidate in candidates for item in candidate.evidence]
    )
    quality_flags = tuple(
        dict.fromkeys(
            flag for candidate in candidates for flag in candidate.quality_flags
        )
    )
    result_token = canonical_id or _canonical_sha256(
        tuple(candidate.raw_candidate_id for candidate in candidates)
    )
    return FusedCandidate(
        result_id=f"fused-result:{result_token}",
        canonical_id=canonical_id,
        display_name=first.display_name,
        domain=first.domain,
        raw_candidate_ids=tuple(candidate.raw_candidate_id for candidate in candidates),
        evidence_ids=tuple(item.evidence_id for item in evidence),
        evidence=evidence,
        quality_flags=quality_flags,
        raw_score=max(candidate.raw_score for candidate in candidates),
        identity_kind=first.identity_kind,
        resolution_state=first.resolution_state,
        origin_lane=first.lane,
        origin_attempt=first.attempt,
        adapter_versions=tuple(
            dict.fromkeys(candidate.adapter_version for candidate in candidates)
        ),
        provider_versions=tuple(
            dict.fromkeys(
                candidate.provider_version
                for candidate in candidates
                if candidate.provider_version is not None
            )
        ),
    )


def _apply_constraints(
    fused: Sequence[FusedCandidate],
    slots: Sequence[ProtectedSlot],
) -> tuple[
    tuple[FusedCandidate, ...],
    tuple[ConstraintReceipt, ...],
    frozenset[str],
]:
    eligible: list[FusedCandidate] = []
    receipts: list[ConstraintReceipt] = []
    rejected_raw_ids: set[str] = set()
    for candidate in fused:
        primary_identity_ids = (
            (candidate.canonical_id,) if candidate.canonical_id is not None else ()
        )
        evidence_subject_ids = (
            tuple(
                item.claim_binding.subject_id
                for item in candidate.evidence
                if item.claim_binding is not None
            )
            if candidate.canonical_id is None or len(candidate.raw_candidate_ids) > 1
            else ()
        )
        canonical_relationship_traces = tuple(
            item.local_projection_trace
            for item in candidate.evidence
            if isinstance(
                item.local_projection_trace,
                LocalCanonicalRelationshipTrace,
            )
        )
        displayed_entity_witness_ids: tuple[str, ...] = ()
        if canonical_relationship_traces:
            witness_ids = {
                trace.displayed_company_id for trace in canonical_relationship_traces
            }
            protected_identities = {
                (trace.protected_slot_id, trace.protected_slot_content_sha256)
                for trace in canonical_relationship_traces
            }
            if len(witness_ids) == 1 and len(protected_identities) == 1:
                displayed_entity_witness_ids = (next(iter(witness_ids)),)
        patent_company_traces = tuple(
            item.local_projection_trace
            for item in candidate.evidence
            if isinstance(
                item.local_projection_trace,
                LocalPatentCompanyRelationshipTrace,
            )
        )
        professor_paper_traces = tuple(
            item.local_projection_trace
            for item in candidate.evidence
            if isinstance(
                item.local_projection_trace,
                LocalProfessorPaperRelationshipTrace,
            )
        )
        constraint_subject_ids = tuple(
            dict.fromkeys((*primary_identity_ids, *evidence_subject_ids))
        )
        constraint_items = tuple(candidate.evidence)
        source_relationship_traces = tuple(
            item.local_projection_trace
            for item in candidate.evidence
            if isinstance(
                item.local_projection_trace,
                LocalSourceRelationshipTrace,
            )
        )
        if source_relationship_traces:
            witness_ids = {
                trace.displayed_entity_id for trace in source_relationship_traces
            }
            protected_identities = {
                (trace.protected_slot_id, trace.protected_slot_content_sha256)
                for trace in source_relationship_traces
            }
            candidate_ids = {
                trace.candidate_canonical_id for trace in source_relationship_traces
            }
            candidate_domains = {
                trace.candidate_domain for trace in source_relationship_traces
            }
            if (
                len(witness_ids) == 1
                and len(protected_identities) == 1
                and len(candidate_ids) == 1
                and len(candidate_domains) == 1
                and candidate.canonical_id == next(iter(candidate_ids))
            ):
                displayed_entity_witness_ids = (next(iter(witness_ids)),)
                canonical_id = next(iter(candidate_ids))
                domain = next(iter(candidate_domains))
                candidate_subject_ids = (
                    canonical_id,
                    f"canonical:{domain}:{canonical_id}",
                )
                constraint_subject_ids = candidate_subject_ids
                constraint_items = tuple(
                    item
                    for item in candidate.evidence
                    if not isinstance(
                        item.local_projection_trace,
                        LocalSourceRelationshipTrace,
                    )
                    and item.object_id == canonical_id
                    and item.domain == domain
                    and (
                        item.claim_binding is None
                        or item.claim_binding.subject_id in candidate_subject_ids
                    )
                )
        if patent_company_traces:
            witness_ids = {trace.displayed_patent_id for trace in patent_company_traces}
            protected_identities = {
                (trace.protected_slot_id, trace.protected_slot_content_sha256)
                for trace in patent_company_traces
            }
            company_ids = {trace.company_id for trace in patent_company_traces}
            if (
                len(witness_ids) == 1
                and len(protected_identities) == 1
                and len(company_ids) == 1
                and candidate.canonical_id == next(iter(company_ids))
            ):
                displayed_entity_witness_ids = (next(iter(witness_ids)),)
                company_id = next(iter(company_ids))
                company_subject_ids = (company_id, f"canonical:company:{company_id}")
                constraint_subject_ids = company_subject_ids
                constraint_items = tuple(
                    item
                    for item in candidate.evidence
                    if not isinstance(
                        item.local_projection_trace,
                        LocalPatentCompanyRelationshipTrace,
                    )
                    and item.object_id == company_id
                    and item.domain == "company"
                    and (
                        item.claim_binding is None
                        or item.claim_binding.subject_id in company_subject_ids
                    )
                )
        if professor_paper_traces:
            witness_ids = {
                trace.displayed_professor_id for trace in professor_paper_traces
            }
            protected_identities = {
                (trace.protected_slot_id, trace.protected_slot_content_sha256)
                for trace in professor_paper_traces
            }
            paper_ids = {trace.paper_id for trace in professor_paper_traces}
            if (
                len(witness_ids) == 1
                and len(protected_identities) == 1
                and len(paper_ids) == 1
                and candidate.canonical_id == next(iter(paper_ids))
            ):
                displayed_entity_witness_ids = (next(iter(witness_ids)),)
                paper_id = next(iter(paper_ids))
                paper_subject_ids = (paper_id, f"canonical:paper:{paper_id}")
                constraint_subject_ids = paper_subject_ids
                constraint_items = tuple(
                    item
                    for item in candidate.evidence
                    if not isinstance(
                        item.local_projection_trace,
                        LocalProfessorPaperRelationshipTrace,
                    )
                    and item.object_id == paper_id
                    and item.domain == "paper"
                    and (
                        item.claim_binding is None
                        or item.claim_binding.subject_id in paper_subject_ids
                    )
                )
        paper_professor_traces = tuple(
            item.local_projection_trace
            for item in candidate.evidence
            if isinstance(
                item.local_projection_trace,
                LocalPaperProfessorRelationshipTrace,
            )
        )
        if paper_professor_traces:
            witness_ids = {trace.displayed_paper_id for trace in paper_professor_traces}
            protected_identities = {
                (trace.protected_slot_id, trace.protected_slot_content_sha256)
                for trace in paper_professor_traces
            }
            professor_ids = {trace.professor_id for trace in paper_professor_traces}
            if (
                len(witness_ids) == 1
                and len(protected_identities) == 1
                and len(professor_ids) == 1
                and candidate.canonical_id == next(iter(professor_ids))
            ):
                displayed_entity_witness_ids = (next(iter(witness_ids)),)
                professor_id = next(iter(professor_ids))
                professor_subject_ids = (
                    professor_id,
                    f"canonical:professor:{professor_id}",
                )
                constraint_subject_ids = professor_subject_ids
                constraint_items = tuple(
                    item
                    for item in candidate.evidence
                    if not isinstance(
                        item.local_projection_trace,
                        LocalPaperProfessorRelationshipTrace,
                    )
                    and item.object_id == professor_id
                    and item.domain == "professor"
                    and (
                        item.claim_binding is None
                        or item.claim_binding.subject_id in professor_subject_ids
                    )
                )
        failures = _constraint_failures(
            slots=slots,
            identity_ids=primary_identity_ids,
            claim_subject_ids=constraint_subject_ids,
            domain=candidate.domain,
            display_name=candidate.display_name,
            items=constraint_items,
            displayed_entity_witness_ids=displayed_entity_witness_ids,
        )
        outcome = "rejected" if failures else "accepted"
        receipts.append(
            ConstraintReceipt(
                raw_candidate_ids=candidate.raw_candidate_ids,
                outcome=outcome,
                failed_slots=tuple(failures),
                aggregated_evidence_ids=candidate.evidence_ids,
            )
        )
        if failures:
            rejected_raw_ids.update(candidate.raw_candidate_ids)
        else:
            eligible.append(candidate)
    return tuple(eligible), tuple(receipts), frozenset(rejected_raw_ids)


def _apply_direct_item_constraints(
    items: Sequence[EvidenceItem],
    slots: Sequence[ProtectedSlot],
) -> tuple[tuple[EvidenceItem, ...], tuple[ConstraintReceipt, ...]]:
    grouped: dict[str, list[EvidenceItem]] = {}
    order: list[str] = []
    for item in items:
        if item.object_id not in grouped:
            order.append(item.object_id)
            grouped[item.object_id] = []
        grouped[item.object_id].append(item)
    admitted: list[EvidenceItem] = []
    receipts: list[ConstraintReceipt] = []
    for object_id in order:
        object_items = grouped[object_id]
        display_name = next(
            (
                item.claim_binding.value
                for item in object_items
                if item.claim_binding is not None
                and item.claim_binding.predicate == "display_name"
            ),
            object_id,
        )
        failures = _constraint_failures(
            slots=slots,
            identity_ids=(object_id,),
            claim_subject_ids=(object_id,),
            domain=object_items[0].domain,
            display_name=display_name,
            items=object_items,
        )
        receipts.append(
            ConstraintReceipt(
                raw_candidate_ids=(f"direct-object:{object_id}",),
                outcome=("rejected" if failures else "accepted"),
                failed_slots=tuple(failures),
                aggregated_evidence_ids=tuple(
                    item.evidence_id for item in object_items
                ),
            )
        )
        if not failures:
            admitted.extend(object_items)
    return tuple(admitted), tuple(receipts)


def _constraint_failures(
    *,
    slots: Sequence[ProtectedSlot],
    identity_ids: Sequence[str],
    claim_subject_ids: Sequence[str],
    domain: str,
    display_name: str,
    items: Sequence[EvidenceItem],
    displayed_entity_witness_ids: Sequence[str] = (),
) -> list[ConstraintFailure]:
    failures: list[ConstraintFailure] = []
    normalized_identity_ids = tuple(dict.fromkeys(identity_ids))
    normalized_claim_subject_ids = tuple(dict.fromkeys(claim_subject_ids))
    normalized_displayed_witness_ids = tuple(
        dict.fromkeys(displayed_entity_witness_ids)
    )
    for slot in slots:
        if slot.kind == "geography" and slot.value:
            observed = tuple(
                dict.fromkeys(
                    (
                        *(
                            item.claim_binding.value
                            for item in items
                            if item.claim_binding is not None
                            and item.claim_binding.predicate == "geography"
                            and item.claim_binding.subject_id
                            in normalized_claim_subject_ids
                        ),
                        *(
                            fact.value
                            for item in items
                            if item.claim_binding is not None
                            and item.claim_binding.predicate
                            == "internal_person_filter_match"
                            and isinstance(
                                item.local_projection_trace,
                                LocalInternalReferenceTrace,
                            )
                            and item.local_projection_trace.reference_type == "person"
                            and item.claim_binding.subject_id
                            == item.local_projection_trace.internal_reference_id
                            for fact in item.local_projection_trace.matched_filter_facts
                            if fact.field == "geography" and fact.evidence_ids
                        ),
                    )
                )
            )
            if slot.value not in observed:
                failures.append(
                    ConstraintFailure(
                        slot_kind=slot.kind,
                        required_value=slot.value,
                        observed_values=observed,
                    )
                )
        elif slot.kind == "displayed_entity_set" and slot.entity_ids:
            displayed_ids = tuple(
                dict.fromkeys(
                    (*normalized_identity_ids, *normalized_displayed_witness_ids)
                )
            )
            if not set(displayed_ids) & set(slot.entity_ids):
                failures.append(
                    ConstraintFailure(
                        slot_kind=slot.kind,
                        required_value="|".join(slot.entity_ids),
                        observed_values=displayed_ids,
                    )
                )
        elif slot.kind == "exact_identifier" and slot.value:
            observed_identifiers = tuple(
                dict.fromkeys(
                    item.claim_binding.value
                    for item in items
                    if item.claim_binding is not None
                    and item.claim_binding.predicate
                    in {"exact_identifier", "identifier", "patent_number"}
                    and item.claim_binding.subject_id in normalized_claim_subject_ids
                )
            )
            identity_matches = any(
                slot.value == identity_id or identity_id.endswith(f":{slot.value}")
                for identity_id in normalized_identity_ids
            )
            encoded_identifiers = tuple(
                identity_id.rsplit(":", 1)[-1]
                for identity_id in normalized_identity_ids
                if domain == "patent"
                and re.fullmatch(
                    r"[A-Z]{2}[A-Z0-9]*[0-9][A-Z0-9]*",
                    identity_id.rsplit(":", 1)[-1],
                )
            )
            encoded_identity_conflicts = bool(encoded_identifiers) and not any(
                slot.value == identifier for identifier in encoded_identifiers
            )
            applies = domain == "patent" or bool(observed_identifiers)
            if (
                not normalized_identity_ids
                or encoded_identity_conflicts
                or (
                    applies
                    and slot.value not in observed_identifiers
                    and not identity_matches
                )
            ):
                failures.append(
                    ConstraintFailure(
                        slot_kind=slot.kind,
                        required_value=slot.value,
                        observed_values=(
                            encoded_identifiers
                            or observed_identifiers
                            or (display_name, *normalized_identity_ids)
                        ),
                    )
                )
        elif slot.kind == "negation" and slot.value:
            searchable = (
                display_name,
                *normalized_identity_ids,
                *(item.snippet for item in items),
                *(
                    item.claim_binding.value
                    for item in items
                    if item.claim_binding is not None
                ),
            )
            if any(slot.value in value for value in searchable):
                failures.append(
                    ConstraintFailure(
                        slot_kind=slot.kind,
                        required_value=f"exclude:{slot.value}",
                        observed_values=(slot.value,),
                    )
                )
    return failures


def _candidate_trace(candidate: RecallCandidate) -> CandidateTrace:
    disposition = (
        "unresolved_reference"
        if candidate.reference_type == "person"
        and candidate.resolution_state != "resolved"
        else "recalled"
    )
    return CandidateTrace(
        raw_candidate_id=candidate.raw_candidate_id,
        query_view=candidate.query_view,
        lane=candidate.lane,
        attempt=candidate.attempt,
        release_id=candidate.release_id,
        adapter_version=candidate.adapter_version,
        provider_version=candidate.provider_version,
        raw_score=candidate.raw_score,
        evidence_ids=tuple(item.evidence_id for item in candidate.evidence),
        disposition=disposition,
    )


def _auxiliary_trace(candidate: RecallCandidate) -> AuxiliaryTrace | None:
    if candidate.reference_type not in {"person", "technology_route"}:
        return None
    return AuxiliaryTrace(
        raw_candidate_id=candidate.raw_candidate_id,
        reference_type=candidate.reference_type,
        origin_public_evidence_ids=candidate.origin_public_evidence_ids,
        relationship_state=candidate.relationship_state,
        public_population=False,
        eligible=candidate.resolution_state == "resolved",
    )


def _snapshot_hash(snapshot_id: str) -> str | None:
    candidate = snapshot_id.rsplit(":", 1)[-1]
    return candidate if re.fullmatch(r"[0-9a-f]{64}", candidate) else None


def _admit_initial_snapshot(
    item: EvidenceItem,
    *,
    payload_by_snapshot: Mapping[str, bytes],
    policy: WebSnapshotPolicy,
) -> tuple[EvidenceItem | None, SnapshotReceipt, str | None]:
    snapshot = item.web_snapshot
    if snapshot is None:
        return (
            None,
            SnapshotReceipt(
                snapshot_id=f"missing:{item.evidence_id}",
                status="rejected",
                reason_code="snapshot_missing",
            ),
            "snapshot_missing",
        )
    payload = payload_by_snapshot.get(snapshot.snapshot_id)
    if payload is None:
        return (
            None,
            SnapshotReceipt(
                snapshot_id=snapshot.snapshot_id,
                status="rejected",
                reason_code="payload_missing",
            ),
            "payload_missing",
        )
    observed_length = len(payload)
    if observed_length > policy.max_bytes:
        return (
            None,
            SnapshotReceipt(
                snapshot_id=snapshot.snapshot_id,
                status="rejected",
                reason_code="max_bytes_exceeded",
                observed_byte_length=observed_length,
            ),
            "max_bytes_exceeded",
        )
    observed_hash = hashlib.sha256(payload).hexdigest()
    if (
        observed_hash != snapshot.content_sha256
        or _snapshot_hash(snapshot.snapshot_id) != snapshot.content_sha256
    ):
        return (
            None,
            SnapshotReceipt(
                snapshot_id=snapshot.snapshot_id,
                status="rejected",
                reason_code="content_hash_mismatch",
                observed_byte_length=observed_length,
            ),
            "content_hash_mismatch",
        )
    recomputed = snapshot.model_copy(
        update={
            "content_sha256": observed_hash,
            "byte_length": observed_length,
        }
    )
    return (
        item.model_copy(update={"web_snapshot": recomputed}),
        SnapshotReceipt(
            snapshot_id=snapshot.snapshot_id,
            status="accepted",
            observed_byte_length=observed_length,
        ),
        None,
    )


def _build_sufficiency(
    plan: RetrievalPlan,
    items: tuple[EvidenceItem, ...],
    decider: Callable[[SufficiencyDecisionRequest], Any] | None,
) -> SufficiencyReport | None:
    if not plan.material_parts:
        return None
    request = SufficiencyDecisionRequest(
        plan_id=plan.plan_id,
        release_id=plan.release_id,
        original_query=plan.original_query,
        material_parts=plan.material_parts,
        evidence=items,
    )
    proposals: dict[str, MaterialPartProposal] = {}
    if decider is not None:
        try:
            raw_value = decider(request)
        except (TimeoutError, ConnectionError):
            value = None
        else:
            try:
                value = _validate_recorded(raw_value, SufficiencyProposal)
            except ValidationError:
                value = None
        if value is not None and value.decision_input_sha256 == request.content_sha256:
            proposals = {part.part_id: part for part in value.parts}
    evidence_by_id = {item.evidence_id: item for item in items}
    decisions: list[SufficiencyPartDecision] = []
    for part in plan.material_parts:
        proposal = proposals.get(part.part_id)
        if proposal is None:
            outcome = "missing"
            evidence_ids: tuple[str, ...] = ()
            rationale = "No admissible structured sufficiency decision was recorded."
            uncertainty = "high"
            confidence = 0.0
        else:
            admitted = tuple(
                evidence_id
                for evidence_id in proposal.evidence_ids
                if evidence_id in evidence_by_id
            )
            outcome = proposal.outcome
            evidence_ids = admitted
            rationale = proposal.rationale
            uncertainty = proposal.uncertainty
            confidence = proposal.confidence
            if len(admitted) != len(proposal.evidence_ids):
                outcome = "missing"
                evidence_ids = ()
                rationale = (
                    "The proposed evidence is not present in the retained result."
                )
                uncertainty = "high"
                confidence = min(confidence, 0.5)
        if outcome in {"supported", "conflicting"}:
            directly_bound = tuple(
                evidence_id
                for evidence_id in evidence_ids
                if (
                    (binding := evidence_by_id[evidence_id].claim_binding) is not None
                    and binding.subject_id == part.subject_id
                    and binding.predicate == part.predicate
                    and (
                        binding.value == part.requested_value
                        or binding.value.startswith(f"{part.requested_value}:")
                    )
                )
            )
            if not directly_bound or directly_bound != evidence_ids:
                outcome = "missing"
                evidence_ids = ()
                rationale = (
                    "The proposed evidence is not directly bound to this material part."
                )
                uncertainty = "high"
                confidence = min(confidence, 0.5)
        if part.answer_scoped and part.predicate == "capability":
            direct_values: list[str] = []
            for evidence_id in evidence_ids:
                item = evidence_by_id[evidence_id]
                binding = item.claim_binding
                if (
                    binding is not None
                    and binding.subject_id == part.subject_id
                    and binding.predicate == part.predicate
                    and binding.value == part.requested_value
                    and item.source_nature in {"local", "current_web"}
                ):
                    direct_values.append(evidence_id)
            direct = tuple(direct_values)
            if outcome != "supported" or direct != evidence_ids or not direct:
                outcome = "missing"
                evidence_ids = ()
                rationale = (
                    "No direct retained evidence binds the named Product to the "
                    "requested capability."
                )
                uncertainty = "high"
                confidence = min(confidence, 0.5)
        decisions.append(
            SufficiencyPartDecision(
                part_id=part.part_id,
                outcome=outcome,
                evidence_ids=evidence_ids,
                rationale=rationale,
                uncertainty=uncertainty,
                confidence=confidence,
                answer_scoped=part.answer_scoped,
                canonical=False,
            )
        )
    return SufficiencyReport(
        decision_input_sha256=request.content_sha256,
        parts=tuple(decisions),
        complete=all(decision.outcome == "supported" for decision in decisions),
    )


def _unique_object_ids(items: Sequence[EvidenceItem]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.object_id for item in items))


def _build_enumeration_coverage(
    policy: EnumerationPolicy | None,
    items: tuple[EvidenceItem, ...],
) -> EnumerationCoverage | None:
    if policy is None:
        return None
    available = _unique_object_ids(items)
    evidence_by_object: dict[str, tuple[str, ...]] = {}
    for object_id in available:
        evidence_by_object[object_id] = tuple(
            item.evidence_id for item in items if item.object_id == object_id
        )
    universe = policy.finite_universe_ids or policy.eligible_member_ids
    if policy.mode == "exhaustive_bounded":
        retrieved = tuple(object_id for object_id in available if object_id in universe)
        missing = tuple(
            object_id for object_id in universe if object_id not in retrieved
        )
        checked = retrieved
        eligible = retrieved
        displayed = retrieved
        unknown_scope = False
        exhaustive = not missing
        accounting_complete = not missing
        continuation_state = "complete" if not missing else "universe_unchecked"
        continuation_required = bool(missing)
        outcomes: tuple[RequiredMemberOutcome, ...] = ()
    elif policy.mode == "required_members":
        checked = policy.required_member_ids
        retrieved = tuple(
            object_id
            for object_id in policy.required_member_ids
            if object_id in available
        )
        eligible = retrieved
        displayed = retrieved
        missing = tuple(
            object_id
            for object_id in policy.required_member_ids
            if object_id not in retrieved
        )
        unknown_scope = False
        exhaustive = False
        accounting_complete = True
        continuation_state = "required_member_unresolved" if missing else "complete"
        continuation_required = bool(missing)
        outcomes = tuple(
            RequiredMemberOutcome(
                member_id=member_id,
                outcome=("included" if member_id in retrieved else "unsupported"),
                evidence_ids=evidence_by_object.get(member_id, ()),
                reason=(
                    None
                    if member_id in retrieved
                    else "No retained evidence supports this required member."
                ),
            )
            for member_id in policy.required_member_ids
        )
    else:
        checked = available
        eligible = available
        retrieved = available
        displayed = available
        missing = ()
        unknown_scope = True
        exhaustive = False
        accounting_complete = True
        continuation_state = "open_world"
        continuation_required = True
        outcomes = ()
    return EnumerationCoverage(
        mode=policy.mode,
        scope=policy.scope,
        as_of=policy.as_of,
        checked_ids=checked,
        eligible_ids=eligible,
        retrieved_ids=retrieved,
        displayed_ids=displayed,
        omitted_ids=missing,
        unknown_ids=missing,
        unknown_scope=unknown_scope,
        checked_count=len(checked),
        eligible_count=len(eligible),
        retrieved_count=len(retrieved),
        displayed_count=len(displayed),
        omitted_count=len(missing),
        unknown_count=(None if unknown_scope else len(missing)),
        exhaustive=exhaustive,
        accounting_complete=accounting_complete,
        required_member_outcomes=outcomes,
        continuation_state=continuation_state,
        continuation_required=continuation_required,
    )


def _run_supplemental(
    plan: RetrievalPlan,
    report: SufficiencyReport | None,
    search: Callable[[SupplementalRequest], Any] | None,
) -> tuple[
    tuple[EvidenceItem, ...],
    tuple[RetrievalTrace, ...],
    SupplementalBudgetReceipt | None,
    tuple[Limitation, ...],
    tuple[str, ...],
]:
    if report is None or plan.supplemental_budget is None or search is None:
        return (), (), None, (), ()
    unresolved_ids = tuple(
        part.part_id for part in report.parts if part.outcome != "supported"
    )
    if not unresolved_ids:
        return (), (), None, (), ()
    part_by_id = {part.part_id: part for part in plan.material_parts}
    request = SupplementalRequest(
        plan_id=plan.plan_id,
        release_id=plan.release_id,
        material_part_ids=unresolved_ids,
        query_view=" | ".join(part_by_id[part_id].text for part_id in unresolved_ids),
    )
    budget = plan.supplemental_budget
    if budget.max_provider_calls <= 0:
        receipt = SupplementalBudgetReceipt(
            exhausted=True,
            exhaustion_reason="provider_calls",
            exhausted_axis="provider_calls",
            limit_value=budget.max_provider_calls,
            used_value=0,
            provider_calls=0,
            retry_count=0,
            elapsed_ms=0,
            cost_units=0.0,
            attempt_count=0,
        )
        return (
            (),
            (),
            receipt,
            (
                Limitation(
                    code="supplemental_budget_exhausted",
                    material=True,
                    material_part_ids=unresolved_ids,
                    reason="provider_calls",
                ),
            ),
            ("evidence_gap", "budget_exhausted"),
        )
    failure_kind: str | None = None
    started_at = monotonic()
    try:
        raw_result = search(request)
    except TimeoutError:
        failure_kind = "timeout"
        result = SupplementalLaneResult(
            items=(),
            elapsed_ms=int((monotonic() - started_at) * 1_000),
            cost_units=0.0,
            retryable=False,
        )
    except ConnectionError:
        failure_kind = "connection_failure"
        result = SupplementalLaneResult(
            items=(),
            elapsed_ms=int((monotonic() - started_at) * 1_000),
            cost_units=0.0,
            retryable=False,
        )
    else:
        try:
            result = _validate_recorded(raw_result, SupplementalLaneResult)
        except ValidationError:
            failure_kind = "invalid_output"
            result = SupplementalLaneResult(
                items=(),
                elapsed_ms=int((monotonic() - started_at) * 1_000),
                cost_units=0.0,
                retryable=False,
            )
    observed_elapsed_ms = int((monotonic() - started_at) * 1_000)
    if observed_elapsed_ms > result.elapsed_ms:
        result = result.model_copy(update={"elapsed_ms": observed_elapsed_ms})
    if any(
        item.domain not in _PUBLIC_DOMAINS
        or item.lane != "supplemental"
        or item.source_nature == "current_web"
        or (
            item.claim_binding is not None
            and item.claim_binding.predicate == "product_has_capability"
        )
        for item in result.items
    ):
        failure_kind = "invalid_output"
        result = result.model_copy(update={"items": ()})
    axis: str | None
    limit: float | int | None
    used: float | int | None
    if result.elapsed_ms > budget.max_wall_time_ms:
        axis = "wall_time"
        limit = budget.max_wall_time_ms
        used = result.elapsed_ms
    elif 1 >= budget.max_provider_calls:
        axis = "provider_calls"
        limit = budget.max_provider_calls
        used = 1
    elif result.retryable and 0 >= budget.max_retries:
        axis = "retries"
        limit = budget.max_retries
        used = 0
    elif result.cost_units > budget.max_cost_units:
        axis = "cost"
        limit = budget.max_cost_units
        used = result.cost_units
    else:
        axis = None
        limit = None
        used = None
    trace = RetrievalTrace(
        query_view=request.query_view,
        lane="supplemental",
        attempt=1,
        release_id=plan.release_id,
        candidate_count=len(result.items),
        status=("unavailable" if failure_kind is not None else "succeeded"),
        failure_kind=failure_kind,
        phase="supplemental",
        material_part_ids=unresolved_ids,
    )
    receipt = SupplementalBudgetReceipt(
        exhausted=axis is not None,
        exhaustion_reason=axis,
        exhausted_axis=axis,
        limit_value=limit,
        used_value=used,
        provider_calls=1,
        retry_count=0,
        elapsed_ms=result.elapsed_ms,
        cost_units=result.cost_units,
        attempt_count=1,
    )
    supplemental_limitations = (
        (
            Limitation(
                code="supplemental_budget_exhausted",
                material=True,
                material_part_ids=unresolved_ids,
                reason=axis,
            ),
        )
        if axis is not None
        else ()
    )
    if failure_kind is not None:
        supplemental_limitations = (
            Limitation(
                code="supplemental_unavailable",
                material=True,
                material_part_ids=unresolved_ids,
                reason=failure_kind,
            ),
            *supplemental_limitations,
        )
    continuation_reasons = (
        ("evidence_gap", "budget_exhausted") if axis is not None else ("evidence_gap",)
    )
    return (
        result.items,
        (trace,),
        receipt,
        supplemental_limitations,
        continuation_reasons,
    )


class _InvalidLaneOutput(ValueError):
    pass


class KnowledgeRead:
    """Public evidence-retrieval seam."""

    def execute(self, plan: RetrievalPlan) -> EvidenceSet:
        raise NotImplementedError


class _EphemeralKnowledgeRead(KnowledgeRead):
    def __init__(
        self,
        *,
        universal_web_policy: WebSearchPolicy,
        lane_adapters: Mapping[str, Callable[[LaneRequest], Any]] | None,
        local_search: Callable[[LaneRequest], Any] | None,
        web_search: Callable[[LaneRequest], Any] | None,
        identity_fuser: Callable[[IdentityFusionRequest], Any] | None,
        reranker: Callable[[RerankRequest], Any] | None,
        sufficiency_decider: Callable[[SufficiencyDecisionRequest], Any] | None,
        supplemental_search: Callable[[SupplementalRequest], Any] | None,
        web_handle_resolver: Callable[[WebHandleResolutionRequest], Any] | None,
        accepted_identity_lookup: Callable[[AcceptedIdentityLookupRequest], Any] | None,
        clock: Callable[[], datetime],
        web_handle_ttl: timedelta,
        web_snapshot_policy: WebSnapshotPolicy | None,
    ) -> None:
        self._universal_web_policy = universal_web_policy
        self._lane_adapters = dict(lane_adapters or {})
        self._local_search = local_search
        self._web_search = web_search
        self._identity_fuser = identity_fuser
        self._reranker = reranker
        self._sufficiency_decider = sufficiency_decider
        self._supplemental_search = supplemental_search
        self._web_handle_resolver = web_handle_resolver
        self._accepted_identity_lookup = accepted_identity_lookup
        self._clock = clock
        self._web_handle_ttl = web_handle_ttl
        self._web_snapshot_policy = web_snapshot_policy

    def _empty(self, plan: RetrievalPlan) -> EvidenceSet:
        result = EvidenceSet(
            release_id=plan.release_id,
            original_query=plan.original_query,
            protected_slots=plan.protected_slots,
            items=(),
            traces=(),
            limitations=(),
            ambiguity_decision=plan.ambiguity_decision,
            material_parts=plan.material_parts,
        )
        return _materialize_successor_handoff(
            plan,
            result,
            now=self._clock(),
        )

    def _execute_handle_replay(self, plan: RetrievalPlan) -> EvidenceSet:
        handles = list(plan.retained_web_handles)
        replay_receipts: list[HandleReplayReceipt] = []
        resolution_receipts: list[HandleResolutionReceipt] = []
        limitations: list[Limitation] = []
        live_ids: list[str] = []
        replay_by_handle = {
            replay.handle.handle_id: replay for replay in plan.web_handle_replays
        }
        continuous: set[str] = set()
        for handle in handles:
            replay = replay_by_handle.get(handle.handle_id)
            accepted_hash = (
                _snapshot_hash(handle.evidence_snapshot_ids[0])
                if handle.evidence_snapshot_ids
                else None
            )
            if not handle.evidence_snapshot_ids:
                status = "snapshot_mismatch"
                limitation_code = "web_snapshot_mismatch"
            elif handle.session_id is None or handle.expires_at is None:
                status = "invalid_handle_context"
                limitation_code = "web_handle_execution_context_missing"
            elif replay is None or replay.handle != handle:
                status = "snapshot_mismatch"
                limitation_code = (
                    "web_handle_replay_mismatch"
                    if replay is not None
                    else "web_snapshot_mismatch"
                )
            else:
                payloads = {
                    payload.snapshot_id: payload.content
                    for payload in replay.snapshot_payloads
                }
                payload_valid = all(
                    snapshot_id in payloads
                    and hashlib.sha256(payloads[snapshot_id]).hexdigest()
                    == _snapshot_hash(snapshot_id)
                    for snapshot_id in handle.evidence_snapshot_ids
                )
                if not payload_valid:
                    status = "snapshot_mismatch"
                    limitation_code = "web_snapshot_mismatch"
                elif (
                    accepted_hash is not None
                    and replay.observed_live_content_sha256 != accepted_hash
                ):
                    status = "provider_content_changed"
                    limitation_code = "web_provider_content_changed"
                elif (
                    handle.expires_at is not None and self._clock() > handle.expires_at
                ):
                    status = "expired"
                    limitation_code = "web_handle_expired"
                else:
                    status = "accepted"
                    limitation_code = None
                    continuous.add(handle.handle_id)
                    live_ids.append(handle.handle_id)
            replay_receipts.append(
                HandleReplayReceipt(
                    handle_id=handle.handle_id,
                    status=status,
                    accepted_snapshot_sha256=accepted_hash,
                    observed_live_content_sha256=(
                        replay.observed_live_content_sha256 if replay else None
                    ),
                    continuity_established=status == "accepted",
                )
            )
            if limitation_code is not None:
                limitations.append(Limitation(code=limitation_code, material=True))

        if (
            plan.handle_operation == "resolve_read_only"
            and self._web_handle_resolver is not None
            and self._accepted_identity_lookup is not None
        ):
            for index, handle in enumerate(tuple(handles)):
                if handle.handle_id not in continuous:
                    continue
                request = WebHandleResolutionRequest(
                    handle=handle,
                    accepted_release_id=plan.release_id,
                    evidence_snapshot_ids=handle.evidence_snapshot_ids,
                )
                try:
                    raw_proposal = self._web_handle_resolver(request)
                except (TimeoutError, ConnectionError):
                    proposal = None
                else:
                    try:
                        proposal = _validate_recorded(
                            raw_proposal,
                            WebHandleResolutionProposal,
                        )
                    except ValidationError:
                        proposal = None
                reason: str | None = None
                cross_wired = False
                lookup: AcceptedIdentityLookupResult | None = None
                if (
                    proposal is None
                    or proposal.decision_input_sha256 != request.content_sha256
                ):
                    reason = "input_binding_mismatch"
                    cross_wired = True
                elif proposal.handle_id != handle.handle_id:
                    reason = "handle_mismatch"
                    cross_wired = True
                elif proposal.accepted_release_id != plan.release_id:
                    reason = "accepted_release_mismatch"
                    cross_wired = True
                elif proposal.retained_snapshot_ids != handle.evidence_snapshot_ids:
                    reason = "snapshot_lineage_mismatch"
                    cross_wired = True
                elif proposal.resolution_state != "resolved":
                    reason = "invalid_resolution_state"
                    cross_wired = True
                else:
                    lookup_request = AcceptedIdentityLookupRequest(
                        release_id=plan.release_id,
                        canonical_id=proposal.canonical_id,
                    )
                    try:
                        raw_lookup = self._accepted_identity_lookup(lookup_request)
                    except (TimeoutError, ConnectionError):
                        lookup = None
                    else:
                        try:
                            lookup = _validate_recorded(
                                raw_lookup,
                                AcceptedIdentityLookupResult,
                            )
                        except ValidationError:
                            lookup = None
                    if (
                        lookup is None
                        or lookup.release_id != plan.release_id
                        or lookup.canonical_id != proposal.canonical_id
                        or not lookup.accepted
                    ):
                        reason = "unaccepted_canonical_identity"
                    elif lookup.evidence_ids != proposal.canonical_evidence_ids:
                        reason = "canonical_evidence_mismatch"
                if reason is None and proposal is not None:
                    handles[index] = handle.model_copy(
                        update={
                            "resolution_state": "resolved",
                            "candidate_canonical_ids": (proposal.canonical_id,),
                        }
                    )
                    status = "accepted"
                    canonical_id: str | None = proposal.canonical_id
                    accepted_release = proposal.accepted_release_id
                    retained_snapshots = proposal.retained_snapshot_ids
                else:
                    status = "rejected"
                    canonical_id = (
                        proposal.canonical_id if proposal is not None else None
                    )
                    accepted_release = (
                        proposal.accepted_release_id
                        if proposal is not None
                        else plan.release_id
                    )
                    retained_snapshots = (
                        proposal.retained_snapshot_ids
                        if proposal is not None
                        else handle.evidence_snapshot_ids
                    )
                    if cross_wired:
                        limitations.append(
                            Limitation(
                                code="web_handle_resolution_cross_wired",
                                material=True,
                            )
                        )
                resolution_receipts.append(
                    HandleResolutionReceipt(
                        handle_id=handle.handle_id,
                        status=status,
                        reason_code=reason,
                        accepted_release_id=accepted_release,
                        canonical_id=canonical_id,
                        retained_snapshot_ids=retained_snapshots,
                        read_only=True,
                    )
                )
        result = EvidenceSet(
            release_id=plan.release_id,
            original_query=plan.original_query,
            protected_slots=plan.protected_slots,
            items=(),
            traces=(),
            limitations=tuple(limitations),
            entity_handles=tuple(handles),
            handle_replay_receipts=tuple(replay_receipts),
            live_referent_handle_ids=tuple(live_ids),
            handle_resolution_receipts=tuple(resolution_receipts),
            ambiguity_decision=plan.ambiguity_decision,
        )
        return _materialize_successor_handoff(
            plan,
            result,
            now=self._clock(),
        )

    def _effective_lanes(
        self,
        plan: RetrievalPlan,
    ) -> tuple[tuple[str, ...], WebSearchPolicy]:
        if (
            plan.interaction_mode == "information_retrieval"
            and plan.behavior_class in _INFORMATION_CLASSES
        ):
            lanes = plan.lanes if "web" in plan.lanes else (*plan.lanes, "web")
            return lanes, self._universal_web_policy
        if plan.web_policy.mode == "official_only" and "web" in plan.lanes:
            return plan.lanes, plan.web_policy
        return plan.lanes, WebSearchPolicy(mode="disabled")

    def _adapter_for(self, lane: str) -> Callable[[LaneRequest], Any] | None:
        if lane in self._lane_adapters:
            return self._lane_adapters[lane]
        if lane == "web":
            return self._web_search
        return self._local_search

    def _invoke_lane(
        self,
        plan: RetrievalPlan,
        lane: str,
        web_policy: WebSearchPolicy,
    ) -> tuple[RetrievalLaneResult | None, str | None]:
        adapter = self._adapter_for(lane)
        if adapter is None:
            return None, "invalid_output"
        request = _lane_request(plan, lane, web_policy)
        try:
            raw_result = adapter(request)
        except TimeoutError:
            return None, "timeout"
        except ConnectionError:
            return None, "connection_failure"
        try:
            result = _validate_recorded(raw_result, RetrievalLaneResult)
            all_items = (
                *result.items,
                *(
                    item
                    for candidate in result.candidates
                    for item in candidate.evidence
                ),
            )
            if any(
                item.lane != request.lane
                or item.domain not in _PUBLIC_DOMAINS
                or not _valid_local_projection_item(item, request)
                or (
                    item.claim_binding is not None
                    and item.claim_binding.predicate == "product_has_capability"
                )
                for item in all_items
            ):
                raise _InvalidLaneOutput("evidence item is cross-wired to another lane")
            if lane == "web" and any(
                item.source_nature != "current_web" for item in all_items
            ):
                raise _InvalidLaneOutput(
                    "Web lane evidence must retain current-Web source nature"
                )
            if lane == "web" and any(
                candidate.identity_kind
                not in {"canonical", "web_candidate", "web_only"}
                or (
                    candidate.identity_kind == "canonical"
                    and (
                        candidate.canonical_id is None
                        or candidate.resolution_state != "resolved"
                        or any(
                            item.object_id != candidate.canonical_id
                            for item in candidate.evidence
                        )
                    )
                )
                or (
                    candidate.identity_kind == "web_candidate"
                    and (
                        candidate.canonical_id is None
                        or candidate.resolution_state != "resolved"
                    )
                )
                or (
                    candidate.identity_kind == "web_only"
                    and (
                        candidate.canonical_id is not None
                        or candidate.resolution_state != "unresolved"
                    )
                )
                or any(item.domain != candidate.domain for item in candidate.evidence)
                for candidate in result.candidates
            ):
                raise _InvalidLaneOutput("Web candidate identity binding differs")
            if any(
                candidate.lane != request.lane
                or candidate.release_id != request.release_id
                or candidate.query_view != request.query_view
                or candidate.attempt != 1
                or candidate.domain not in _PUBLIC_DOMAINS
                or not _valid_local_projection_candidate(candidate, request)
                for candidate in result.candidates
            ):
                raise _InvalidLaneOutput(
                    "recall candidate is cross-wired to its request"
                )
            if lane == "web" and any(
                item.source_nature == "current_web" and item.web_snapshot is None
                for item in result.items
            ):
                raise _InvalidLaneOutput("current Web evidence requires a snapshot")
            return result, None
        except (ValidationError, _InvalidLaneOutput):
            return None, "invalid_output"

    def execute(self, plan: RetrievalPlan) -> EvidenceSet:
        plan = RetrievalPlan.model_validate(plan.model_dump(mode="json"))
        if plan.interaction_mode == "handle_replay":
            return self._execute_handle_replay(plan)
        if plan.interaction_mode in {
            "ordinary_refusal",
            "blocking_clarification",
            "interface_control",
        }:
            return self._empty(plan)
        if (
            plan.interaction_mode == "safety_guidance"
            and plan.web_policy.mode != "official_only"
        ):
            return self._empty(plan)

        lanes, effective_web_policy = self._effective_lanes(plan)
        outcomes: dict[str, tuple[RetrievalLaneResult | None, str | None]] = {}
        if lanes:
            executor = ThreadPoolExecutor(max_workers=max(1, len(lanes)))
            futures = {}
            for lane in lanes:
                if (
                    lane == "web"
                    and effective_web_policy.mode != "disabled"
                    and effective_web_policy.max_provider_calls <= 0
                ):
                    outcomes[lane] = (None, "budget_exhausted")
                else:
                    futures[lane] = executor.submit(
                        self._invoke_lane,
                        plan,
                        lane,
                        effective_web_policy if lane == "web" else plan.web_policy,
                    )
            try:
                result_order = sorted(lanes, key=lambda item: item != "web")
                for lane in result_order:
                    if lane in outcomes:
                        continue
                    timeout_seconds = (
                        effective_web_policy.timeout_ms / 1_000
                        if lane == "web"
                        and effective_web_policy.mode != "disabled"
                        and effective_web_policy.timeout_ms > 0
                        else None
                    )
                    try:
                        outcomes[lane] = futures[lane].result(timeout=timeout_seconds)
                    except TimeoutError:
                        outcomes[lane] = (None, "timeout")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        traces: list[RetrievalTrace] = []
        limitations: list[Limitation] = []
        direct_items: list[EvidenceItem] = []
        candidates: list[RecallCandidate] = []
        recalled_candidates: list[RecallCandidate] = []
        official_policy_rejected: set[str] = set()
        result_limit_rejected: set[str] = set()
        payload_by_snapshot: dict[str, bytes] = {}
        for lane in lanes:
            result, failure = outcomes[lane]
            if failure is not None or result is None:
                traces.append(
                    RetrievalTrace(
                        query_view="view:original",
                        lane=lane,
                        attempt=1,
                        release_id=plan.release_id,
                        candidate_count=0,
                        status="unavailable",
                        failure_kind=failure,
                        source_scope=(
                            effective_web_policy.mode if lane == "web" else None
                        ),
                    )
                )
                if lane == "web" and effective_web_policy.mode != "disabled":
                    limitations.append(
                        Limitation(
                            code="current_web_unavailable",
                            lane="web",
                            material=True,
                            impact="freshness",
                        )
                    )
                continue
            lane_items = result.items
            recalled_candidates.extend(result.candidates)
            if lane == "web" and effective_web_policy.mode == "official_only":
                lane_items = tuple(
                    item
                    for item in lane_items
                    if item.source_authority == "official"
                    and _domain_allowed(
                        item.source_locator,
                        effective_web_policy.allowed_domains,
                    )
                )
                lane_candidates: tuple[RecallCandidate, ...] = tuple(
                    candidate.model_copy(
                        update={
                            "evidence": tuple(
                                item
                                for item in candidate.evidence
                                if item.source_nature == "current_web"
                                and item.source_authority == "official"
                                and _domain_allowed(
                                    item.source_locator,
                                    effective_web_policy.allowed_domains,
                                )
                            )
                        }
                    )
                    for candidate in result.candidates
                )
                official_policy_rejected.update(
                    candidate.raw_candidate_id
                    for candidate in lane_candidates
                    if not candidate.evidence
                )
            else:
                lane_candidates = result.candidates
            if lane == "web" and effective_web_policy.mode != "disabled":
                result_limit = max(0, effective_web_policy.max_results)
                lane_items = lane_items[:result_limit]
                remaining = max(0, result_limit - len(lane_items))
                result_limit_rejected.update(
                    candidate.raw_candidate_id
                    for candidate in lane_candidates[remaining:]
                )
                lane_candidates = lane_candidates[:remaining]
            direct_items.extend(lane_items)
            candidates.extend(lane_candidates)
            payload_by_snapshot.update(
                {
                    payload.snapshot_id: payload.content
                    for payload in result.web_snapshot_payloads
                }
            )
            traces.append(
                RetrievalTrace(
                    query_view="view:original",
                    lane=lane,
                    attempt=1,
                    release_id=plan.release_id,
                    candidate_count=len(result.items) + len(result.candidates),
                    status="succeeded",
                    source_scope=(effective_web_policy.mode if lane == "web" else None),
                )
            )

        raw_candidate_ids = tuple(
            candidate.raw_candidate_id for candidate in recalled_candidates
        )
        evidence_by_id: dict[str, EvidenceItem] = {}
        evidence_collision = False
        for item in (
            *direct_items,
            *(item for candidate in recalled_candidates for item in candidate.evidence),
        ):
            prior = evidence_by_id.get(item.evidence_id)
            if prior is not None and prior != item:
                evidence_collision = True
                break
            evidence_by_id[item.evidence_id] = item
        if len(raw_candidate_ids) != len(set(raw_candidate_ids)) or evidence_collision:
            result = EvidenceSet(
                release_id=plan.release_id,
                original_query=plan.original_query,
                protected_slots=plan.protected_slots,
                items=(),
                traces=tuple(traces),
                limitations=(
                    *limitations,
                    Limitation(
                        code=(
                            "duplicate_raw_candidate_id"
                            if len(raw_candidate_ids) != len(set(raw_candidate_ids))
                            else "conflicting_evidence_id"
                        ),
                        material=True,
                    ),
                ),
                ambiguity_decision=plan.ambiguity_decision,
                material_parts=plan.material_parts,
            )
            return _materialize_successor_handoff(
                plan,
                result,
                now=self._clock(),
            )

        snapshot_receipts: list[SnapshotReceipt] = []
        admitted_direct_items: list[EvidenceItem] = []
        for item in direct_items:
            if self._web_snapshot_policy is None or item.source_nature != "current_web":
                admitted_direct_items.append(item)
                continue
            admitted, receipt, reason = _admit_initial_snapshot(
                item,
                payload_by_snapshot=payload_by_snapshot,
                policy=self._web_snapshot_policy,
            )
            snapshot_receipts.append(receipt)
            if admitted is None:
                limitations.append(
                    Limitation(
                        code="web_snapshot_rejected",
                        lane="web",
                        material=True,
                        reason=reason,
                    )
                )
            else:
                admitted_direct_items.append(admitted)
        direct_items = admitted_direct_items
        if (
            plan.ambiguity_decision is not None
            and plan.ambiguity_decision.mode == "non_blocking"
            and plan.ambiguity_decision.selected_canonical_id is not None
        ):
            direct_items = [
                item
                for item in direct_items
                if item.object_id == plan.ambiguity_decision.selected_canonical_id
            ]
        direct_items_tuple, direct_constraint_receipts = _apply_direct_item_constraints(
            direct_items,
            plan.protected_slots,
        )
        direct_object_ids = tuple(
            dict.fromkeys(item.object_id for item in direct_items_tuple)
        )[: plan.max_candidates]
        direct_items = [
            item for item in direct_items_tuple if item.object_id in direct_object_ids
        ]
        direct_result_count = len(direct_object_ids)

        accepted_local_ids = {
            candidate.canonical_id
            for candidate in candidates
            if candidate.lane != "web" and candidate.canonical_id is not None
        }
        candidates = [
            (
                candidate.model_copy(
                    update={
                        "canonical_id": None,
                        "identity_kind": "web_only",
                        "resolution_state": "unresolved",
                    }
                )
                if candidate.lane == "web"
                and candidate.canonical_id is not None
                and candidate.canonical_id not in accepted_local_ids
                else candidate
            )
            for candidate in candidates
        ]

        selection_candidates = tuple(candidates)
        trace_candidates = tuple(recalled_candidates)
        candidate_trace_values = {
            candidate.raw_candidate_id: _candidate_trace(candidate)
            for candidate in trace_candidates
        }
        auxiliary = tuple(
            trace
            for candidate in trace_candidates
            if (trace := _auxiliary_trace(candidate)) is not None
        )
        forced_dispositions: dict[str, str] = {
            raw_id: "result_limit_rejected" for raw_id in result_limit_rejected
        }
        forced_dispositions.update(
            {raw_id: "official_policy_rejected" for raw_id in official_policy_rejected}
        )
        admitted_candidates: list[RecallCandidate] = []
        for candidate in selection_candidates:
            if candidate.raw_candidate_id in official_policy_rejected:
                continue
            current_web_items = tuple(
                item
                for item in candidate.evidence
                if item.source_nature == "current_web"
            )
            if any(item.web_snapshot is None for item in current_web_items):
                forced_dispositions[candidate.raw_candidate_id] = "snapshot_missing"
                limitations.append(
                    Limitation(code="web_snapshot_rejected", lane="web", material=True)
                )
                continue
            if self._web_snapshot_policy is None or not current_web_items:
                admitted_candidates.append(candidate)
                continue
            admitted_evidence: list[EvidenceItem] = []
            rejected = False
            for item in candidate.evidence:
                if item.source_nature != "current_web":
                    admitted_evidence.append(item)
                    continue
                admitted, receipt, reason = _admit_initial_snapshot(
                    item,
                    payload_by_snapshot=payload_by_snapshot,
                    policy=self._web_snapshot_policy,
                )
                snapshot_receipts.append(receipt)
                if admitted is None:
                    disposition = {
                        "payload_missing": "snapshot_payload_missing",
                        "max_bytes_exceeded": "snapshot_oversize",
                        "content_hash_mismatch": "snapshot_hash_mismatch",
                        "snapshot_missing": "snapshot_missing",
                    }[reason or "snapshot_missing"]
                    forced_dispositions[candidate.raw_candidate_id] = disposition
                    limitations.append(
                        Limitation(
                            code="web_snapshot_rejected",
                            lane="web",
                            material=True,
                            reason=reason,
                        )
                    )
                    rejected = True
                    break
                admitted_evidence.append(admitted)
            if not rejected:
                admitted_candidates.append(
                    candidate.model_copy(update={"evidence": tuple(admitted_evidence)})
                )

        candidates = admitted_candidates
        fusion_request = IdentityFusionRequest(
            release_id=plan.release_id,
            raw_candidate_ids=tuple(
                candidate.raw_candidate_id for candidate in candidates
            ),
            candidates=tuple(candidates),
        )
        groups = _default_groups(candidates)
        fusion_receipt = DecisionReceipt(mode="deterministic_fallback")
        if self._identity_fuser is not None and candidates:
            degradation: str | None = None
            try:
                raw_proposal = self._identity_fuser(fusion_request)
            except TimeoutError:
                proposal = None
                degradation = "timeout"
            except ConnectionError:
                proposal = None
                degradation = "connection_failure"
            else:
                try:
                    proposal = _validate_recorded(
                        raw_proposal,
                        IdentityFusionProposal,
                    )
                except ValidationError:
                    proposal = None
            proposed_groups: list[tuple[str | None, tuple[RecallCandidate, ...]]] = []
            candidate_by_id = {
                candidate.raw_candidate_id: candidate for candidate in candidates
            }
            if proposal is None:
                if degradation is None:
                    degradation = "invalid_output"
            elif proposal.decision_input_sha256 != fusion_request.content_sha256:
                degradation = "input_binding_mismatch"
            else:
                proposed_canonical_ids = tuple(
                    group.canonical_id for group in proposal.groups
                )
                if len(proposed_canonical_ids) != len(set(proposed_canonical_ids)):
                    degradation = "conflicting_accepted_canonical_ids"
                flattened = tuple(
                    raw_id
                    for group in proposal.groups
                    for raw_id in group.raw_candidate_ids
                )
                if degradation is None and (
                    len(flattened) != len(set(flattened))
                    or set(flattened) != set(candidate_by_id)
                ):
                    degradation = "invalid_grouping"
                elif degradation is None:
                    for group in proposal.groups:
                        members = tuple(
                            candidate_by_id[item] for item in group.raw_candidate_ids
                        )
                        accepted_ids = {
                            member.canonical_id
                            for member in members
                            if member.canonical_id is not None
                        }
                        if (
                            len(accepted_ids) > 1
                            or (accepted_ids and group.canonical_id not in accepted_ids)
                            or (not accepted_ids and group.canonical_id is not None)
                        ):
                            degradation = "conflicting_accepted_canonical_ids"
                            break
                        proposed_groups.append((group.canonical_id, members))
            if degradation is None:
                groups = tuple(proposed_groups)
                fusion_receipt = DecisionReceipt(
                    mode="recorded_structured",
                    decision_input_sha256=fusion_request.content_sha256,
                )
            else:
                fusion_receipt = DecisionReceipt(
                    mode="deterministic_fallback",
                    decision_input_sha256=fusion_request.content_sha256,
                    degradation_reason=degradation,
                )

        fused = tuple(
            _fused_candidate(canonical_id, members) for canonical_id, members in groups
        )
        eligible, candidate_constraint_receipts, constraint_rejected = (
            _apply_constraints(
                fused,
                plan.protected_slots,
            )
        )
        constraint_receipts = (
            *direct_constraint_receipts,
            *candidate_constraint_receipts,
        )
        ambiguity_alternatives: set[str] = set()
        if (
            plan.ambiguity_decision is not None
            and plan.ambiguity_decision.mode == "non_blocking"
            and plan.ambiguity_decision.selected_canonical_id is not None
        ):
            selected_id = plan.ambiguity_decision.selected_canonical_id
            selected: list[FusedCandidate] = []
            for candidate in eligible:
                if candidate.canonical_id == selected_id:
                    selected.append(candidate)
                else:
                    ambiguity_alternatives.update(candidate.raw_candidate_ids)
            eligible = tuple(selected)

        ordered = eligible
        rerank_receipt = DecisionReceipt(mode="deterministic_fallback")
        if self._reranker is not None and eligible:
            rerank_request = RerankRequest(
                release_id=plan.release_id,
                original_query=plan.original_query,
                eligible_candidates=eligible,
            )
            degradation = None
            try:
                raw_rerank = self._reranker(rerank_request)
            except TimeoutError:
                rerank = None
                degradation = "timeout"
            except ConnectionError:
                rerank = None
                degradation = "connection_failure"
            else:
                try:
                    rerank = _validate_recorded(raw_rerank, RerankProposal)
                except ValidationError:
                    rerank = None
                    degradation = "invalid_output"
            result_by_id = {candidate.result_id: candidate for candidate in eligible}
            if rerank is not None:
                if rerank.decision_input_sha256 != rerank_request.content_sha256:
                    degradation = "input_binding_mismatch"
                elif any(
                    item not in result_by_id for item in rerank.ordered_result_ids
                ):
                    degradation = "unknown_candidate"
                elif len(rerank.ordered_result_ids) != len(
                    set(rerank.ordered_result_ids)
                ):
                    degradation = "duplicate_candidate"
                elif not rerank.ordered_result_ids:
                    degradation = "invalid_output"
                else:
                    ordered = tuple(
                        result_by_id[item] for item in rerank.ordered_result_ids
                    )
            if degradation is None:
                rerank_receipt = DecisionReceipt(
                    mode="recorded_structured",
                    decision_input_sha256=rerank_request.content_sha256,
                )
            else:
                rerank_receipt = DecisionReceipt(
                    mode="deterministic_fallback",
                    decision_input_sha256=rerank_request.content_sha256,
                    degradation_reason=degradation,
                )

        candidate_limit = max(0, plan.max_candidates - direct_result_count)
        ordered = ordered[:candidate_limit]

        entity_handles: list[CanonicalEntityHandle | WebEntityHandle] = []
        selected_handle_by_raw: dict[str, str] = {}
        selected_items: list[EvidenceItem] = []
        non_handleable_raw: set[str] = set()
        for candidate in ordered:
            if candidate.canonical_id is not None:
                handle: CanonicalEntityHandle | WebEntityHandle = CanonicalEntityHandle(
                    canonical_id=candidate.canonical_id,
                    domain=candidate.domain,
                    display_name=candidate.display_name,
                    evidence_ids=candidate.evidence_ids,
                )
                public_id = candidate.canonical_id
            else:
                snapshot_ids = tuple(
                    dict.fromkeys(
                        item.web_snapshot.snapshot_id
                        for item in candidate.evidence
                        if item.web_snapshot is not None
                    )
                )
                if (
                    not snapshot_ids
                    or plan.session_id is None
                    or not any(
                        item.source_nature == "current_web"
                        for item in candidate.evidence
                    )
                ):
                    non_handleable_raw.update(candidate.raw_candidate_ids)
                    continue
                handle_id = (
                    "web-handle:sha256:"
                    f"{_canonical_sha256((candidate.raw_candidate_ids, snapshot_ids, candidate.evidence_ids, candidate.domain, candidate.display_name, plan.original_query, candidate.origin_lane, candidate.origin_attempt, candidate.adapter_versions, candidate.provider_versions, plan.session_id))}"
                )
                handle = WebEntityHandle(
                    handle_id=handle_id,
                    domain=candidate.domain,
                    display_name=candidate.display_name,
                    evidence_snapshot_ids=snapshot_ids,
                    evidence_ids=candidate.evidence_ids,
                    resolution_state=candidate.resolution_state,
                    candidate_canonical_ids=(),
                    originating_query=plan.original_query,
                    origin_lane=candidate.origin_lane,
                    origin_attempt=candidate.origin_attempt,
                    session_id=plan.session_id,
                    expires_at=self._clock() + self._web_handle_ttl,
                )
                public_id = handle_id
            entity_handles.append(handle)
            selected_items.extend(candidate.evidence)
            for raw_id in candidate.raw_candidate_ids:
                selected_handle_by_raw[raw_id] = public_id

        final_candidate_traces: list[CandidateTrace] = []
        for raw_candidate in trace_candidates:
            trace = candidate_trace_values[raw_candidate.raw_candidate_id]
            if raw_candidate.raw_candidate_id in forced_dispositions:
                disposition = forced_dispositions[raw_candidate.raw_candidate_id]
                selected_result_id = None
            elif trace.disposition == "unresolved_reference":
                disposition = trace.disposition
                selected_result_id = None
            elif raw_candidate.raw_candidate_id in constraint_rejected:
                disposition = "hard_constraint_rejected"
                selected_result_id = None
            elif raw_candidate.raw_candidate_id in ambiguity_alternatives:
                disposition = "ambiguity_alternative"
                selected_result_id = None
            elif raw_candidate.raw_candidate_id in non_handleable_raw:
                disposition = "unresolved_identity"
                selected_result_id = None
            elif raw_candidate.raw_candidate_id in selected_handle_by_raw:
                disposition = "selected"
                selected_result_id = selected_handle_by_raw[
                    raw_candidate.raw_candidate_id
                ]
            else:
                disposition = "not_selected"
                selected_result_id = None
            final_candidate_traces.append(
                trace.model_copy(
                    update={
                        "disposition": disposition,
                        "selected_result_id": selected_result_id,
                    }
                )
            )

        items = _unique_items((*direct_items, *selected_items))
        sufficiency = _build_sufficiency(
            plan,
            items,
            self._sufficiency_decider,
        )
        (
            supplemental_items,
            supplemental_traces,
            budget_receipt,
            supplemental_limitations,
            continuation_reasons,
        ) = _run_supplemental(
            plan,
            sufficiency,
            self._supplemental_search,
        )
        supplemental_items, supplemental_constraint_receipts = (
            _apply_direct_item_constraints(
                supplemental_items,
                plan.protected_slots,
            )
        )
        constraint_receipts = (
            *constraint_receipts,
            *supplemental_constraint_receipts,
        )
        existing_result_ids = set(direct_object_ids)
        existing_result_ids.update(
            handle.canonical_id
            for handle in entity_handles
            if isinstance(handle, CanonicalEntityHandle)
        )
        remaining_result_slots = max(
            0,
            plan.max_candidates - direct_result_count - len(entity_handles),
        )
        admitted_new_ids: list[str] = []
        bounded_supplemental_items: list[EvidenceItem] = []
        for item in supplemental_items:
            if item.object_id in existing_result_ids:
                bounded_supplemental_items.append(item)
            elif item.object_id in admitted_new_ids:
                bounded_supplemental_items.append(item)
            elif len(admitted_new_ids) < remaining_result_slots:
                admitted_new_ids.append(item.object_id)
                bounded_supplemental_items.append(item)
        supplemental_items = tuple(bounded_supplemental_items)
        items = _unique_items((*items, *supplemental_items))
        if supplemental_items:
            sufficiency = _build_sufficiency(
                plan,
                items,
                self._sufficiency_decider,
            )
            if sufficiency is not None and sufficiency.complete:
                continuation_reasons = tuple(
                    reason
                    for reason in continuation_reasons
                    if reason != "evidence_gap"
                )
        traces.extend(supplemental_traces)
        limitations.extend(supplemental_limitations)
        coverage = _build_enumeration_coverage(plan.enumeration_policy, items)
        result = EvidenceSet(
            release_id=plan.release_id,
            original_query=plan.original_query,
            protected_slots=plan.protected_slots,
            items=items,
            traces=tuple(traces),
            limitations=tuple(limitations),
            candidate_traces=tuple(final_candidate_traces),
            auxiliary_traces=auxiliary,
            fused_candidates=fused,
            constraint_receipts=constraint_receipts,
            fusion_receipt=fusion_receipt,
            rerank_receipt=rerank_receipt,
            entity_handles=tuple(entity_handles),
            sufficiency_report=sufficiency,
            enumeration_coverage=coverage,
            supplemental_budget_receipt=budget_receipt,
            continuation_reasons=continuation_reasons,
            snapshot_receipts=tuple(snapshot_receipts),
            material_parts=plan.material_parts,
            ambiguity_decision=plan.ambiguity_decision,
        )
        return _materialize_successor_handoff(
            plan,
            result,
            now=self._clock(),
        )


def create_ephemeral_knowledge_read(
    *,
    universal_web_policy: WebSearchPolicy,
    lane_adapters: Mapping[str, Callable[[LaneRequest], Any]] | None = None,
    local_search: Callable[[LaneRequest], Any] | None = None,
    web_search: Callable[[LaneRequest], Any] | None = None,
    identity_fuser: Callable[[IdentityFusionRequest], Any] | None = None,
    reranker: Callable[[RerankRequest], Any] | None = None,
    sufficiency_decider: Callable[[SufficiencyDecisionRequest], Any] | None = None,
    supplemental_search: Callable[[SupplementalRequest], Any] | None = None,
    web_handle_resolver: Callable[[WebHandleResolutionRequest], Any] | None = None,
    accepted_identity_lookup: Callable[[AcceptedIdentityLookupRequest], Any]
    | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    web_handle_ttl: timedelta = timedelta(hours=1),
    web_snapshot_policy: WebSnapshotPolicy | None = None,
) -> KnowledgeRead:
    """Create an in-memory KnowledgeRead with explicit provider boundaries."""

    if web_handle_ttl.total_seconds() < 0:
        raise ValueError("web_handle_ttl must be non-negative")
    return _EphemeralKnowledgeRead(
        universal_web_policy=WebSearchPolicy.model_validate(
            universal_web_policy.model_dump(mode="json")
        ),
        lane_adapters=lane_adapters,
        local_search=local_search,
        web_search=web_search,
        identity_fuser=identity_fuser,
        reranker=reranker,
        sufficiency_decider=sufficiency_decider,
        supplemental_search=supplemental_search,
        web_handle_resolver=web_handle_resolver,
        accepted_identity_lookup=accepted_identity_lookup,
        clock=clock,
        web_handle_ttl=web_handle_ttl,
        web_snapshot_policy=(
            WebSnapshotPolicy.model_validate(
                web_snapshot_policy.model_dump(mode="json")
            )
            if web_snapshot_policy is not None
            else None
        ),
    )


# Resolve annotations that intentionally bridge the S8 and already-Accepted S9 shapes.
for _model in (WebHandleReplay, RetrievalPlan, RetrievalLaneResult):
    _model.model_rebuild()
