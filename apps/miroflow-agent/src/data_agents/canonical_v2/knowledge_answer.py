"""Grounded answer contracts for the Canonical V2 answer seam.

The module owns validation of model-proposed claims.  Read-side evidence and
handle records are re-exported so callers use the accepted KnowledgeRead
shapes rather than answer-local duplicates.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import logging
import re
from types import MappingProxyType
from typing import Any, Literal

_logger = logging.getLogger(__name__)

from pydantic import Field, ValidationError, model_serializer, model_validator

from .contracts import ContractModel
from .knowledge_read import (
    AmbiguityCandidate,
    AmbiguityDecision,
    AssessmentIntent,
    CanonicalEntityHandle,
    ContinuationCandidate,
    EnumerationCoverage,
    EvidenceClaimBinding,
    EvidenceConflict,
    EvidenceItem,
    EvidenceSet,
    IndustryBriefIntent,
    LocalCanonicalRelationshipTrace,
    LocalPaperProfessorRelationshipTrace,
    LocalPatentCompanyRelationshipTrace,
    LocalProfessorPaperRelationshipTrace,
    LocalSourceRelationshipTrace,
    MaterialQuestionPart,
    ProtectedSlot,
    TypedTraversalRequest,
    WebEntityHandle,
    WebEvidenceSnapshot,
)


_ZERO_SHA256 = "0" * 64
_ANSWER_SELECTION_SCHEMA = "answer-selection-v1"
_ASSESSMENT_SELECTION_SCHEMA = "assessment-selection-v1"
_OFFICIAL_SAFETY_PREDICATES = frozenset(
    {
        "official_help_contact",
        "official_reporting_channel",
        "official_policy_reference",
    }
)
_OFFICIAL_CONTACT_PATTERN = re.compile(r"^\+?[0-9][0-9 ()-]{2,31}$")
_OFFICIAL_REFERENCE_PATTERN = re.compile(
    r"^https://[A-Za-z0-9.-]+(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?$"
)
_MAX_OFFICIAL_REFERENCE_LENGTH = 128
_OPAQUE_PROJECTION_PREDICATES = frozenset({"canonical_projection", "semantic_recall"})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CONTINUATION_OPTION_POLICY: Mapping[str, tuple[str, str, str]] = MappingProxyType(
    {
        "broad_scope": (
            "narrow_scope",
            "current_result_set",
            "Narrow the current result set",
        ),
        "ambiguity": (
            "switch_candidate",
            "current_handle",
            "Switch to another candidate",
        ),
        "partial_coverage": (
            "continue_coverage",
            "current_result_set",
            "Continue coverage",
        ),
        "evidence_gap": (
            "targeted_evidence_search",
            "current_handle",
            "Search for targeted evidence",
        ),
        "budget_exhausted": (
            "resume_bounded_search",
            "current_result_set",
            "Resume the bounded search",
        ),
        "eligible_next_hop": (
            "traverse_relationship",
            "current_handle",
            "Explore the available relationship",
        ),
    }
)


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


def _revalidate(value: Any, model_type: type[Any]) -> Any:
    """Validate even same-class instances created through ``model_construct``."""

    if isinstance(value, model_type):
        return model_type.model_validate(value.model_dump(mode="json"))
    return model_type.model_validate(value)


class ContinuationSelection(ContractModel):
    offer_id: str
    option_id: str


class SessionDirective(ContractModel):
    transition: Literal["continue", "topic_switch"] = "continue"
    referent: Literal[
        "none", "active_anchor", "displayed_result_set", "displayed_member"
    ] = "none"
    displayed_ordinal: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_ordinal_iff_displayed_member(self) -> SessionDirective:
        if (self.referent == "displayed_member") != (
            self.displayed_ordinal is not None
        ):
            raise ValueError(
                "displayed_ordinal is required iff referent is displayed_member"
            )
        return self


class SafetyGuidanceDirective(ContractModel):
    mode: Literal["static", "official_snapshot"]
    official_evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_official_evidence_shape(self) -> SafetyGuidanceDirective:
        if len(self.official_evidence_ids) != len(set(self.official_evidence_ids)):
            raise ValueError("official evidence IDs must be unique")
        if len(self.official_evidence_ids) > 3:
            raise ValueError(
                "official safety guidance accepts at most three evidence IDs"
            )
        if self.mode == "static" and self.official_evidence_ids:
            raise ValueError("static safety guidance cannot cite evidence")
        if self.mode == "official_snapshot" and not self.official_evidence_ids:
            raise ValueError("official snapshot guidance requires evidence")
        return self


class TurnRequest(ContractModel):
    session_id: str
    turn_id: str
    query: str
    release_id: str
    evidence_set: EvidenceSet
    assessment_intent: AssessmentIntent | None = None
    continuation_selection: ContinuationSelection | None = None
    session_directive: SessionDirective | None = None
    safety_guidance: SafetyGuidanceDirective | None = None
    # Web-only soft subject anchor from the planner request: carried through
    # to the context receipt so the prose correction judges the answer
    # against it instead of a mis-anchored look-alike session anchor.
    soft_context_subject: str | None = None
    content_sha256: str = Field(default=_ZERO_SHA256, pattern=r"^[0-9a-f]{64}$")

    @model_serializer(mode="wrap")
    def serialize_optional_request_fields(self, handler: Any) -> Any:
        data = handler(self)
        if self.soft_context_subject is None:
            data.pop("soft_context_subject", None)
        return data

    @model_validator(mode="before")
    @classmethod
    def revalidate_evidence_set(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        evidence_set = data.get("evidence_set")
        if evidence_set is None:
            return data
        try:
            data["evidence_set"] = _revalidate(evidence_set, EvidenceSet)
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValueError("evidence_set must be a validated EvidenceSet") from exc
        return data

    @model_validator(mode="after")
    def bind_request_content(self) -> TurnRequest:
        if self.query != self.evidence_set.original_query:
            raise ValueError("query must match evidence_set.original_query")
        if self.release_id != self.evidence_set.release_id:
            raise ValueError("release_id must match evidence_set.release_id")
        if self.soft_context_subject is not None and (
            not self.soft_context_subject.strip()
            or self.soft_context_subject != self.soft_context_subject.strip()
        ):
            raise ValueError("soft context subject must be normalized and non-empty")
        expected = _canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 == _ZERO_SHA256:
            object.__setattr__(self, "content_sha256", expected)
        elif self.content_sha256 != expected:
            raise ValueError("content_sha256 must bind the complete TurnRequest")
        return self


class MaterialClaimProposal(ContractModel):
    claim_id: str
    claim_type: str = "material_fact"
    text: str
    subject_id: str | None = None
    predicate: str | None = None
    value: str | None = None
    subject_handle_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    outcome: str = "supported"
    source_natures: tuple[str, ...] = ()
    synthesis: bool = False
    answer_scoped: bool = False
    canonical: bool = False
    confirmed: bool = True
    uncertainty: str | None = None
    status: str | None = None


class AnswerSelectionProposal(ContractModel):
    selection_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str
    decision_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    decision_run_id: str = Field(min_length=1)
    answer_text: str
    claims: tuple[MaterialClaimProposal, ...] = ()
    displayed_handle_ids: tuple[str, ...] = ()
    displayed_entity_ids: tuple[str, ...] = ()
    coverage_claim: str | None = None
    continuation_candidate_ids: tuple[str, ...] = ()


class AssessmentEvidenceBinding(ContractModel):
    evidence_id: str
    subject_id: str
    predicate: str
    value: str
    status: str | None = None


class AssessmentDimensionProposal(ContractModel):
    name: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_ids: tuple[str, ...]
    evidence_bindings: tuple[AssessmentEvidenceBinding, ...] = ()
    outcome: str
    conclusion: str | None
    uncertainty: str


class AssessmentSelectionProposal(ContractModel):
    selection_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str
    decision_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    decision_run_id: str = Field(min_length=1)
    dimensions: tuple[AssessmentDimensionProposal, ...]
    conditional_synthesis: str


class MaterialClaim(ContractModel):
    claim_id: str
    text: str
    evidence_ids: tuple[str, ...]
    source_natures: tuple[str, ...]
    synthesis: bool
    claim_type: str = "material_fact"
    subject_id: str | None = None
    predicate: str | None = None
    value: str | None = None
    subject_handle_ids: tuple[str, ...] = ()
    outcome: str = "supported"
    answer_scoped: bool = False
    canonical: bool = False
    confirmed: bool = True
    uncertainty: str | None = None
    status: str | None = None


class ClaimEvidenceMapping(ContractModel):
    claim_id: str
    subject_id: str | None
    predicate: str | None
    value: str | None
    evidence_ids: tuple[str, ...]
    status: str | None = None


class Citation(ContractModel):
    evidence_id: str
    source_nature: str
    source_locator: str
    observed_at: datetime | None = None
    web_snapshot_id: str | None = None
    retrieved_at: datetime | None = None


class AnswerLimitation(ContractModel):
    code: str
    reason: str | None = None
    material: bool = False
    stage: str | None = None
    failure_kind: str | None = None
    material_part_id: str | None = None
    handle_id: str | None = None
    requested_path_id: str | None = None


class AssessmentDimension(ContractModel):
    name: str
    rationale: str
    evidence_ids: tuple[str, ...]
    outcome: str
    conclusion: str | None
    uncertainty: str


class AssessmentFrame(ContractModel):
    intent_kind: str
    dimensions: tuple[AssessmentDimension, ...]
    conditional_synthesis: str
    answer_scoped: bool = True
    canonical: bool = False


class IndustryRouteSummary(ContractModel):
    route_id: str
    definition: str
    evidence_ids: tuple[str, ...]


class IndustryRelationshipFinding(ContractModel):
    subject_id: str
    route_id: str
    status: str
    evidence_ids: tuple[str, ...]


class IndustryBrief(ContractModel):
    release_id: str
    scope: str
    as_of: datetime
    route_ids: tuple[str, ...]
    route_summaries: tuple[IndustryRouteSummary, ...]
    relationship_findings: tuple[IndustryRelationshipFinding, ...]
    displayed_entity_ids: tuple[str, ...]
    enumeration_coverage: EnumerationCoverage
    coverage_claim: str
    claims: tuple[MaterialClaim, ...]
    claim_evidence_map: tuple[ClaimEvidenceMapping, ...]
    citations: tuple[Citation, ...]
    conflicts: tuple[EvidenceConflict, ...]
    limitations: tuple[AnswerLimitation, ...]
    derived: bool = True
    canonical: bool = False
    public_domains: tuple[str, ...] = ("professor", "company", "paper", "patent")
    internal_reference_types: tuple[str, ...] = ("technology_route",)


EntityHandle = CanonicalEntityHandle | WebEntityHandle


class DisplayedResultSet(ContractModel):
    result_set_id: str
    handles: tuple[EntityHandle, ...]
    handle_ids: tuple[str, ...]
    enumeration_mode: str | None = None
    continuation_state: str | None = None


class ResolvedReferent(ContractModel):
    kind: str
    handle_ids: tuple[str, ...]
    result_set_id: str | None = None
    enumeration_mode: str | None = None
    continuation_state: str | None = None


class TraversalReceipt(ContractModel):
    path_id: str
    source_handle_ids: tuple[str, ...]
    target_handle_ids: tuple[str, ...]


class ContinuationOption(ContractModel):
    option_id: str
    label: str
    operation: str
    target_handle_ids: tuple[str, ...] = ()
    result_set_id: str | None = None
    constraint_pairs: tuple[tuple[str, str], ...] = ()
    relation_type: str | None = None
    evidence_ids: tuple[str, ...] = ()
    source_candidate_id: str | None = None
    discriminator: str | None = None


class ContinuationOffer(ContractModel):
    offer_id: str
    reasons: tuple[str, ...]
    options: tuple[ContinuationOption, ...]
    selection_kind: str = "continuation_selection"


class InterpretationNotice(ContractModel):
    selected_handle_id: str
    decision_trace_id: str


class ContextReceipt(ContractModel):
    active_anchor: EntityHandle | None = None
    displayed_result_set: DisplayedResultSet | None = None
    resolved_referent: ResolvedReferent | None = None
    resolved_evidence_ids: tuple[str, ...] = ()
    active_constraints: tuple[ProtectedSlot, ...] = ()
    traversed_path_ids: tuple[str, ...] = ()
    transition_kind: str = "turn"
    selected_option_id: str | None = None
    selected_operation: str | None = None
    performed_operation: str | None = None
    ambiguity_decision_trace_ids: tuple[str, ...] = ()
    # Web-only soft subject of this turn, mirrored from the TurnRequest; the
    # prose correction judges against it when the session anchor may be a
    # mis-anchored look-alike. Popped from serialization when absent.
    soft_context_subject: str | None = None

    @model_serializer(mode="wrap")
    def serialize_optional_receipt_fields(self, handler: Any) -> Any:
        data = handler(self)
        if self.soft_context_subject is None:
            data.pop("soft_context_subject", None)
        return data


class SelectorDecisionTrace(ContractModel):
    stage: Literal["answer_selection", "assessment_selection"]
    schema_version: str
    selection_input_sha256: str
    outcome: Literal["accepted", "degraded"]
    decision_id: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    decision_run_id: str | None = None
    failure_kind: str | None = None


class TurnResult(ContractModel):
    session_id: str
    turn_id: str
    release_id: str
    original_query: str | None = Field(default=None, exclude=True)
    answer_text: str
    claims: tuple[MaterialClaim, ...] = ()
    limitations: tuple[AnswerLimitation, ...] = ()
    suggested_followups: tuple[str, ...] = ()
    claim_evidence_map: tuple[ClaimEvidenceMapping, ...] = ()
    citations: tuple[Citation, ...] = ()
    conflicts: tuple[EvidenceConflict, ...] = ()
    enumeration_coverage: EnumerationCoverage | None = None
    assessment_frame: AssessmentFrame | None = None
    industry_brief: IndustryBrief | None = None
    context_receipt: ContextReceipt | None = None
    traversal_receipt: TraversalReceipt | None = None
    continuation_offer: ContinuationOffer | None = None
    interpretation_notice: InterpretationNotice | None = None
    selector_traces: tuple[SelectorDecisionTrace, ...] = ()
    response_mode: str = "answer"
    render_mode: str = "proposal"
    fallback_sha256: str | None = None


class ProseSynthesisResult(ContractModel):
    """Internal result from the single final prose call; never serialized publicly.

    ``supersedes_streamed_draft`` marks the one legitimate case where the
    returned answer differs from the already-published streamed draft: the
    stream path's off-anchor correction replaced the FINAL answer after the
    drifted chunks went out. The knowledge_answer stream guard exempts marked
    results from its published-vs-final equality check so the SSE answer
    event can supersede the draft. It stays unset on the non-stream path and
    on every fail-open branch.
    """

    answer_text: str = Field(min_length=1)
    selected_claim_ids: tuple[str, ...] = ()
    selected_handle_ids: tuple[str, ...] = ()
    supersedes_streamed_draft: bool = False

    @model_validator(mode="after")
    def require_unique_selections(self) -> ProseSynthesisResult:
        if len(self.selected_claim_ids) != len(set(self.selected_claim_ids)):
            raise ValueError("selected claim IDs must be unique")
        if len(self.selected_handle_ids) != len(set(self.selected_handle_ids)):
            raise ValueError("selected handle IDs must be unique")
        return self


class KnowledgeAnswer(ABC):
    """Small external seam for Canonical V2 answer orchestration."""

    # Optional token-level prose progress sink. The chat adapter assigns this
    # on the session instance around a streaming turn; it is never a
    # constructor argument. The sink returns ``True`` only after the text is
    # public, and its abort hook discards buffered downstream state belonging
    # to a failed attempt. Renderers exposing ``stream(result, *, on_chunk)``
    # are duck-typed into the streaming path when this is set; plain callable
    # renderers keep the synchronous path untouched.
    prose_progress: Callable[[str], bool] | None = None
    prose_progress_abort: Callable[[], None] | None = None

    @abstractmethod
    def answer(self, turn: TurnRequest) -> TurnResult:
        """Validate one turn and return only server-grounded answer state."""


AnswerSelector = Callable[[TurnRequest], Any]


def _default_proposal(request: TurnRequest) -> AnswerSelectionProposal:
    return AnswerSelectionProposal(
        selection_input_sha256=request.content_sha256,
        schema_version=_ANSWER_SELECTION_SCHEMA,
        decision_id=f"answer-selection:{request.turn_id}:default",
        model_id="server-deterministic",
        prompt_version="answer-default-v1",
        decision_run_id=f"answer-default-run:{request.turn_id}",
        answer_text="No supported material claims are available.",
    )


def _ground_claim(
    proposal: MaterialClaimProposal,
    *,
    evidence_set: EvidenceSet,
    selector_claim_ids: frozenset[str],
) -> MaterialClaim | None:
    if _claim_text_exposes_structured_only_value(
        proposal,
        evidence_set=evidence_set,
        selector_claim_ids=selector_claim_ids,
    ):
        return None
    evidence_by_id = {item.evidence_id: item for item in evidence_set.items}
    if not proposal.evidence_ids or any(
        evidence_id not in evidence_by_id for evidence_id in proposal.evidence_ids
    ):
        return None
    if len(proposal.evidence_ids) != len(set(proposal.evidence_ids)):
        return None
    evidence = tuple(
        evidence_by_id[evidence_id] for evidence_id in proposal.evidence_ids
    )
    if (
        evidence_set.industry_brief_intent is not None
        and proposal.claim_type == "technology_relationship"
        and evidence_set.enumeration_coverage is not None
        and proposal.subject_id not in evidence_set.enumeration_coverage.displayed_ids
    ):
        return None
    structured = all(
        isinstance(value, str) and bool(value.strip())
        for value in (proposal.subject_id, proposal.predicate, proposal.value)
    )
    if not structured:
        return None
    if proposal.outcome not in {"supported", "conflicting_evidence"}:
        return None
    material_conflicts = tuple(
        conflict
        for conflict in evidence_set.material_conflicts
        if conflict.material
        and conflict.subject_id == proposal.subject_id
        and conflict.predicate == proposal.predicate
    )
    if proposal.outcome == "conflicting_evidence":
        matching_conflict = next(
            (
                conflict
                for conflict in material_conflicts
                if conflict.evidence_ids == proposal.evidence_ids
            ),
            None,
        )
        if matching_conflict is None:
            return None
        conflict_bindings = tuple(item.claim_binding for item in evidence)
        if any(
            binding is None
            or binding.subject_id != proposal.subject_id
            or binding.predicate != proposal.predicate
            for binding in conflict_bindings
        ):
            return None
        if (
            len(
                {
                    (binding.value, binding.status)
                    for binding in conflict_bindings
                    if binding is not None
                }
            )
            < 2
        ):
            return None
    elif material_conflicts:
        return None
    elif proposal.claim_type == "model_inference":
        if not (
            proposal.outcome == "supported"
            and proposal.synthesis
            and proposal.answer_scoped
            and not proposal.confirmed
            and proposal.uncertainty
        ):
            return None
        if any(
            item.claim_binding is None
            or not item.claim_binding.subject_id.strip()
            or not item.claim_binding.predicate.strip()
            or not item.claim_binding.value.strip()
            for item in evidence
        ):
            return None
    else:
        for item in evidence:
            binding = item.claim_binding
            if binding is None or (
                binding.subject_id,
                binding.predicate,
                binding.value,
                binding.status,
            ) != (
                proposal.subject_id,
                proposal.predicate,
                proposal.value,
                proposal.status,
            ):
                return None
    source_natures = tuple(dict.fromkeys(item.source_nature for item in evidence))
    return MaterialClaim(
        claim_id=proposal.claim_id,
        claim_type=proposal.claim_type,
        text=proposal.text,
        subject_id=proposal.subject_id,
        predicate=proposal.predicate,
        value=proposal.value,
        subject_handle_ids=proposal.subject_handle_ids,
        evidence_ids=proposal.evidence_ids,
        outcome=proposal.outcome,
        source_natures=source_natures,
        synthesis=proposal.synthesis,
        answer_scoped=proposal.answer_scoped,
        canonical=False,
        confirmed=proposal.confirmed,
        uncertainty=proposal.uncertainty,
        status=proposal.status,
    )


def _text_contains_structured_only_value(text: str, value: str) -> bool:
    if ":" in value or len(value) >= 16:
        return value in text
    return (
        re.search(
            rf"(?<![A-Za-z0-9_:-]){re.escape(value)}(?![A-Za-z0-9_:-])",
            text,
        )
        is not None
    )


def _evidence_set_structured_only_values(evidence_set: EvidenceSet) -> frozenset[str]:
    values: set[str] = {item.evidence_id for item in evidence_set.items}
    for item in evidence_set.items:
        binding = item.claim_binding
        if binding is not None and (
            (
                binding.predicate in _OPAQUE_PROJECTION_PREDICATES
                and _SHA256_PATTERN.fullmatch(binding.value)
            )
            or binding.value.startswith(("canonical:", "reference:"))
        ):
            values.add(binding.value)
    for candidate in evidence_set.continuation_candidates:
        values.update((candidate.candidate_id, candidate.reason, candidate.operation))
    return frozenset(value for value in values if value)


def _claim_text_exposes_structured_only_value(
    proposal: MaterialClaimProposal,
    *,
    evidence_set: EvidenceSet,
    selector_claim_ids: frozenset[str],
) -> bool:
    values = set(_evidence_set_structured_only_values(evidence_set))
    values.update(selector_claim_ids)
    return any(
        _text_contains_structured_only_value(proposal.text, value) for value in values
    )


def _unsupported_product_claim(part: MaterialQuestionPart) -> MaterialClaim:
    return MaterialClaim(
        claim_id=f"claim:{part.part_id}:unsupported",
        claim_type="product_capability",
        text="Direct evidence for the named Product capability is unavailable.",
        subject_id=part.subject_id,
        predicate=part.predicate,
        value=part.requested_value,
        subject_handle_ids=(part.subject_id,),
        evidence_ids=(),
        outcome="unsupported",
        source_natures=(),
        synthesis=False,
        answer_scoped=True,
        canonical=False,
        confirmed=False,
        uncertainty="direct Product-bound status evidence is missing",
        status=None,
    )


def _attributed_claim(
    *,
    request: TurnRequest,
    item: EvidenceItem,
    selector_claim_ids: frozenset[str],
    index: int,
) -> MaterialClaim | None:
    """Build a grounding-checked claim directly from an attributed web item.

    Used when the selector's own claims did not bind the conversation scope:
    the item's claim binding supplies the claim skeleton and ``_ground_claim``
    re-verifies evidence presence, binding consistency, and text hygiene, so
    the fallback stays behind the same guardrails as selector claims.
    """
    binding = item.claim_binding
    if binding is None:
        return None
    return _ground_claim(
        MaterialClaimProposal(
            claim_id=f"claim:attributed:{request.turn_id}:{index}",
            text=item.snippet[:240],
            subject_id=binding.subject_id,
            predicate=binding.predicate,
            value=binding.value,
            status=binding.status,
            subject_handle_ids=(),
            evidence_ids=(item.evidence_id,),
            source_natures=(item.source_nature,),
            synthesis=False,
        ),
        evidence_set=request.evidence_set,
        selector_claim_ids=selector_claim_ids,
    )


def _mapping(claim: MaterialClaim) -> ClaimEvidenceMapping:
    return ClaimEvidenceMapping(
        claim_id=claim.claim_id,
        subject_id=claim.subject_id,
        predicate=claim.predicate,
        value=claim.value,
        evidence_ids=claim.evidence_ids,
        status=claim.status,
    )


def _citation(item: EvidenceItem) -> Citation:
    snapshot = item.web_snapshot
    return Citation(
        evidence_id=item.evidence_id,
        source_nature=item.source_nature,
        source_locator=item.source_locator,
        observed_at=item.observed_at,
        web_snapshot_id=None if snapshot is None else snapshot.snapshot_id,
        retrieved_at=None if snapshot is None else snapshot.retrieved_at,
    )


def _official_safety_text(item: EvidenceItem) -> str | None:
    binding = item.claim_binding
    if binding is None:
        return None
    value = binding.value.strip()
    if binding.predicate == "official_help_contact":
        if _OFFICIAL_CONTACT_PATTERN.fullmatch(value) is None:
            return None
        return f"Official help contact: {value}"
    if binding.predicate not in {
        "official_reporting_channel",
        "official_policy_reference",
    }:
        return None
    if (
        len(value) > _MAX_OFFICIAL_REFERENCE_LENGTH
        or _OFFICIAL_REFERENCE_PATTERN.fullmatch(value) is None
    ):
        return None
    label = (
        "reporting channel"
        if binding.predicate == "official_reporting_channel"
        else "policy reference"
    )
    return f"Official {label}: {value}"


AssessmentSelector = Callable[[TurnRequest], Any]
ProseRenderer = Callable[[Any], Any]


@dataclass(frozen=True)
class _AssessmentBuild:
    frame: AssessmentFrame | None
    limitations: tuple[AnswerLimitation, ...] = ()
    traces: tuple[SelectorDecisionTrace, ...] = ()


def _degraded_selector_trace(
    request: TurnRequest,
    *,
    stage: Literal["answer_selection", "assessment_selection"],
    schema_version: str,
    failure_kind: str,
) -> SelectorDecisionTrace:
    return SelectorDecisionTrace(
        stage=stage,
        schema_version=schema_version,
        selection_input_sha256=request.content_sha256,
        outcome="degraded",
        failure_kind=failure_kind,
    )


def _assessment_limitation(
    *,
    code: str,
    failure_kind: str,
    reason: str | None = None,
) -> AnswerLimitation:
    return AnswerLimitation(
        code=code,
        reason=reason,
        material=True,
        stage="assessment_selection",
        failure_kind=failure_kind,
    )


def _assessment_synthesis(
    dimensions: tuple[AssessmentDimension, ...],
) -> str:
    if not dimensions:
        return "No assessment dimension has sufficient current-turn evidence."
    outcomes = ", ".join(
        f"{dimension.name}: {dimension.outcome}" for dimension in dimensions
    )
    return f"Assessment is conditional on current-turn evidence ({outcomes})."


def _build_assessment_frame(
    request: TurnRequest,
    selector: AssessmentSelector | None,
) -> _AssessmentBuild:
    intent = request.assessment_intent
    if intent is None or selector is None:
        return _AssessmentBuild(frame=None)
    try:
        proposal = _revalidate(selector(request), AssessmentSelectionProposal)
    except TimeoutError:
        failure_kind = "timeout"
        return _AssessmentBuild(
            frame=None,
            limitations=(
                _assessment_limitation(
                    code="assessment_selection_rejected",
                    failure_kind=failure_kind,
                ),
            ),
            traces=(
                _degraded_selector_trace(
                    request,
                    stage="assessment_selection",
                    schema_version=_ASSESSMENT_SELECTION_SCHEMA,
                    failure_kind=failure_kind,
                ),
            ),
        )
    except (TypeError, ValueError, ValidationError):
        failure_kind = "invalid_output"
        return _AssessmentBuild(
            frame=None,
            limitations=(
                _assessment_limitation(
                    code="assessment_selection_rejected",
                    failure_kind=failure_kind,
                ),
            ),
            traces=(
                _degraded_selector_trace(
                    request,
                    stage="assessment_selection",
                    schema_version=_ASSESSMENT_SELECTION_SCHEMA,
                    failure_kind=failure_kind,
                ),
            ),
        )
    if (
        proposal.selection_input_sha256 != request.content_sha256
        or proposal.schema_version != _ASSESSMENT_SELECTION_SCHEMA
    ):
        failure_kind = (
            "input_binding_mismatch"
            if proposal.selection_input_sha256 != request.content_sha256
            else "schema_mismatch"
        )
        return _AssessmentBuild(
            frame=None,
            limitations=(
                _assessment_limitation(
                    code="assessment_selection_rejected",
                    failure_kind=failure_kind,
                ),
            ),
            traces=(
                _degraded_selector_trace(
                    request,
                    stage="assessment_selection",
                    schema_version=_ASSESSMENT_SELECTION_SCHEMA,
                    failure_kind=failure_kind,
                ),
            ),
        )

    evidence_by_id = {item.evidence_id: item for item in request.evidence_set.items}
    proposed_by_name = {dimension.name: dimension for dimension in proposal.dimensions}
    selected = (
        tuple(proposed_by_name.get(name) for name in intent.user_criteria)
        if intent.user_criteria
        else tuple(proposal.dimensions[:3])
    )
    dimensions: list[AssessmentDimension] = []
    limitations: list[AnswerLimitation] = []
    for index, candidate in enumerate(selected):
        name = (
            intent.user_criteria[index]
            if intent.user_criteria
            else candidate.name
            if candidate is not None
            else "assessment"
        )
        rejected = candidate is None
        failure_kind = "missing_dimension"
        if candidate is not None:
            ids = candidate.evidence_ids
            bindings = candidate.evidence_bindings
            rejected = (
                not ids
                or len(ids) != len(set(ids))
                or len(ids) != len(bindings)
                or any(evidence_id not in evidence_by_id for evidence_id in ids)
            )
            failure_kind = "evidence_binding_mismatch"
            if not rejected:
                for evidence_id, proposed_binding in zip(ids, bindings, strict=True):
                    item = evidence_by_id[evidence_id]
                    binding = item.claim_binding
                    if binding is None or (
                        proposed_binding.evidence_id,
                        proposed_binding.subject_id,
                        proposed_binding.predicate,
                        proposed_binding.value,
                        proposed_binding.status,
                    ) != (
                        evidence_id,
                        binding.subject_id,
                        binding.predicate,
                        binding.value,
                        binding.status,
                    ):
                        rejected = True
                        break
            if not rejected:
                material_conflicts = tuple(
                    conflict
                    for conflict in request.evidence_set.material_conflicts
                    if conflict.material
                    and any(
                        proposed_binding.subject_id == conflict.subject_id
                        and proposed_binding.predicate == conflict.predicate
                        for proposed_binding in bindings
                    )
                )
                if candidate.outcome == "supported":
                    rejected = (
                        not candidate.conclusion
                        or not candidate.uncertainty
                        or bool(material_conflicts)
                    )
                    failure_kind = "supported_outcome_invalid"
                elif candidate.outcome == "conflicting_evidence":
                    rejected = (
                        not candidate.conclusion
                        or not candidate.uncertainty
                        or not any(
                            conflict.evidence_ids == ids
                            and all(
                                binding.subject_id == conflict.subject_id
                                and binding.predicate == conflict.predicate
                                for binding in bindings
                            )
                            for conflict in material_conflicts
                        )
                    )
                    failure_kind = "conflict_outcome_invalid"
                elif candidate.outcome == "insufficient_evidence":
                    rejected = candidate.conclusion is not None
                    failure_kind = "insufficient_outcome_invalid"
                else:
                    rejected = True
                    failure_kind = "unsupported_outcome"
        if rejected:
            dimensions.append(
                AssessmentDimension(
                    name=name,
                    rationale=(
                        "The requested dimension has no supporting current-turn evidence."
                        if candidate is None
                        else candidate.rationale
                    ),
                    evidence_ids=(),
                    outcome="insufficient_evidence",
                    conclusion=None,
                    uncertainty="No retained current-turn evidence supports this dimension.",
                )
            )
            limitations.append(
                _assessment_limitation(
                    code="assessment_dimension_rejected",
                    failure_kind=failure_kind,
                    reason=name,
                )
            )
            continue
        assert candidate is not None
        dimensions.append(
            AssessmentDimension(
                name=name,
                rationale=candidate.rationale,
                evidence_ids=candidate.evidence_ids,
                outcome=candidate.outcome,
                conclusion=candidate.conclusion,
                uncertainty=candidate.uncertainty,
            )
        )
    exact_dimensions = tuple(dimensions)
    if limitations:
        trace = _degraded_selector_trace(
            request,
            stage="assessment_selection",
            schema_version=_ASSESSMENT_SELECTION_SCHEMA,
            failure_kind="dimension_rejected",
        )
    else:
        trace = SelectorDecisionTrace(
            stage="assessment_selection",
            schema_version=proposal.schema_version,
            selection_input_sha256=request.content_sha256,
            outcome="accepted",
            decision_id=proposal.decision_id,
            model_id=proposal.model_id,
            prompt_version=proposal.prompt_version,
            decision_run_id=proposal.decision_run_id,
        )
    return _AssessmentBuild(
        frame=AssessmentFrame(
            intent_kind=intent.kind,
            dimensions=exact_dimensions,
            conditional_synthesis=_assessment_synthesis(exact_dimensions),
        ),
        limitations=tuple(limitations),
        traces=(trace,),
    )


def _build_industry_brief(
    request: TurnRequest,
    *,
    claims: tuple[MaterialClaim, ...],
    mappings: tuple[ClaimEvidenceMapping, ...],
    citations: tuple[Citation, ...],
    conflicts: tuple[EvidenceConflict, ...],
    limitations: tuple[AnswerLimitation, ...],
) -> IndustryBrief | None:
    intent = request.evidence_set.industry_brief_intent
    coverage = request.evidence_set.enumeration_coverage
    if intent is None or coverage is None:
        return None
    route_summaries: list[IndustryRouteSummary] = []
    for route_id in intent.route_ids:
        definition = next(
            (
                claim
                for claim in claims
                if claim.subject_id == route_id and claim.predicate == "definition"
            ),
            None,
        )
        if definition is not None:
            route_summaries.append(
                IndustryRouteSummary(
                    route_id=route_id,
                    definition=definition.value or definition.text,
                    evidence_ids=definition.evidence_ids,
                )
            )

    evidence_by_id = {item.evidence_id: item for item in request.evidence_set.items}
    findings_by_subject: dict[str, IndustryRelationshipFinding] = {}
    for claim in claims:
        if (
            claim.claim_type != "technology_relationship"
            or claim.subject_id not in coverage.displayed_ids
        ):
            continue
        if claim.outcome == "conflicting_evidence":
            route_values = tuple(
                dict.fromkeys(
                    item.claim_binding.value
                    for evidence_id in claim.evidence_ids
                    if (item := evidence_by_id[evidence_id]).claim_binding is not None
                )
            )
            route_id = route_values[0] if len(route_values) == 1 else "conflicting"
            status = "conflicting"
        else:
            route_id = claim.value or "unknown"
            status = claim.status or "unknown"
        findings_by_subject[claim.subject_id] = IndustryRelationshipFinding(
            subject_id=claim.subject_id,
            route_id=route_id,
            status=status,
            evidence_ids=claim.evidence_ids,
        )
    displayed_entity_ids = tuple(
        subject_id
        for subject_id in coverage.displayed_ids
        if subject_id in findings_by_subject
    )
    return IndustryBrief(
        release_id=request.release_id,
        scope=intent.scope,
        as_of=intent.as_of,
        route_ids=intent.route_ids,
        route_summaries=tuple(route_summaries),
        relationship_findings=tuple(
            findings_by_subject[subject_id] for subject_id in displayed_entity_ids
        ),
        displayed_entity_ids=displayed_entity_ids,
        enumeration_coverage=coverage,
        coverage_claim=coverage.mode,
        claims=claims,
        claim_evidence_map=mappings,
        citations=citations,
        conflicts=conflicts,
        limitations=limitations,
    )


def _material_gap_sentence(
    part: MaterialQuestionPart,
    *,
    outcome: Literal["missing", "conflicting"],
    chinese: bool,
) -> str:
    if part.predicate == "current_revenue" and re.fullmatch(
        r"[0-9]{4}", part.requested_value
    ):
        label = (
            f"{part.requested_value} 年当前营收"
            if chinese
            else f"{part.requested_value} current revenue"
        )
    else:
        label = "关键部分" if chinese else "the material part of the question"
    if chinese:
        return (
            f"目前公开信息较为有限，暂未能确认问题中的 {label}。"
            if outcome == "missing"
            else f"目前公开信息对问题中的 {label}存在不一致说法，暂未能确认。"
        )
    return (
        f"Public information is currently too limited to confirm {label}."
        if outcome == "missing"
        else f"Public information currently conflicts on {label}."
    )


def _material_gap_outputs(
    evidence_set: EvidenceSet,
    *,
    existing_limitations: tuple[AnswerLimitation, ...],
) -> tuple[tuple[AnswerLimitation, ...], tuple[str, ...]]:
    report = evidence_set.sufficiency_report
    if report is None:
        return (), ()
    part_by_id = {part.part_id: part for part in evidence_set.material_parts}
    owned_part_ids = {
        limitation.material_part_id
        for limitation in existing_limitations
        if limitation.material and limitation.material_part_id is not None
    }
    limitations: list[AnswerLimitation] = []
    sentences: list[str] = []
    chinese = re.search(r"[\u3400-\u9fff]", evidence_set.original_query) is not None
    for decision in report.parts:
        part = part_by_id.get(decision.part_id)
        if (
            part is None
            or not part.material
            or decision.outcome == "supported"
            or part.part_id in owned_part_ids
        ):
            continue
        outcome = decision.outcome
        limitations.append(
            AnswerLimitation(
                code=(
                    "material_evidence_missing"
                    if outcome == "missing"
                    else "material_evidence_conflicting"
                ),
                reason=decision.rationale,
                material=True,
                stage="sufficiency",
                material_part_id=part.part_id,
            )
        )
        sentences.append(_material_gap_sentence(part, outcome=outcome, chinese=chinese))
        owned_part_ids.add(part.part_id)
    return tuple(limitations), tuple(sentences)


def _enumeration_coverage_sentences(
    coverage: EnumerationCoverage | None,
) -> tuple[str, ...]:
    """Deterministic disclosure for open-world list answers.

    The prose path receives the same accounting through its payload; this
    sentence keeps the deterministic and fallback render modes honest about
    representative (non-exhaustive) enumeration.
    """
    if coverage is None or coverage.mode != "representative":
        return ()
    if coverage.displayed_count < coverage.retrieved_count:
        accounting = (
            f"共检索到 {coverage.retrieved_count} 个相关结果，"
            f"本次展示其中 {coverage.displayed_count} 个"
        )
    else:
        accounting = f"共检索到 {coverage.retrieved_count} 个相关结果并全部展示"
    return (f"{accounting}，为代表性结果而非穷尽列表。",)


def _append_required_sentences(text: str, sentences: tuple[str, ...]) -> str:
    rendered = text
    for sentence in sentences:
        if sentence not in rendered:
            rendered = f"{rendered}\n{sentence}" if rendered else sentence
    return rendered


_DETERMINISTIC_ANSWER_MAX_CLAIMS = 10
_DETERMINISTIC_ANSWER_MAX_CHARS = 2000
# Soft non-refusal fallback: the chat always answers and never bounces the
# question back to the user, even when nothing can be confirmed directly.
_SOFT_FALLBACK_ANSWER_TEXT = (
    "关于该主体的公开信息目前较为有限，暂未能确认您问的具体内容。"
)
# Deterministic/fallback rendering must never publish raw search dumps:
# source-locator tails (；来源：https://…) and document-mill page text
# (淘豆网/原创力文档/豆丁网/…) are stripped from each grounded point.
# Link-seeking questions keep the tails because the verified locator IS the
# answer there.
_DETERMINISTIC_SOURCE_TAIL_MARKERS = ("；来源：", " 来源：", "\n来源：")
_DETERMINISTIC_RAW_DUMP_MARKERS = (
    "淘豆网",
    "原创力文档",
    "原创力文",
    "豆丁网",
    "道客巴巴",
    "百度文库",
    "book118",
    # Generic content-farm / login-wall / download-bait markers: pages that
    # carry them are never usable answer content, whatever the site name.
    "登录后查看更多",
    "立即下载",
    "开通VIP",
    "上传人",
    "文档编号",
    "搜题",
)


def claim_text_is_raw_dump(text: str) -> bool:
    """True when a claim text is a content-farm/login-wall page dump that must
    never reach the prose prompt or the deterministic fallback."""
    return any(marker in text for marker in _DETERMINISTIC_RAW_DUMP_MARKERS)
# Cap each rendered point above the construction limits (web snippets are
# cut at 240 chars, local fields at 160) so a grounded abstract survives the
# deterministic rendering while multi-field claims stay bounded.
_DETERMINISTIC_CLAIM_TEXT_LIMIT = 200
_LINK_SEEKING_QUERY_MARKERS = ("链接", "网址", "官网", "url", "URL")


def _split_deterministic_source_tail(text: str) -> tuple[str, str]:
    """Split a claim text into its descriptive head and source-locator tail."""
    for marker in _DETERMINISTIC_SOURCE_TAIL_MARKERS:
        index = text.rfind(marker)
        if index > 0:
            return text[:index], text[index:]
    return text, ""


def _clean_deterministic_claim_text(
    text: str,
    *,
    keep_source_tails: bool,
) -> str | None:
    """One readable grounded point, or None for raw page dumps."""
    head, tail = _split_deterministic_source_tail(text)
    head = head.strip()
    if not keep_source_tails:
        tail = ""
    if not head or claim_text_is_raw_dump(head):
        return None
    if len(head) + len(tail) > _DETERMINISTIC_CLAIM_TEXT_LIMIT:
        head = (
            head[: max(_DETERMINISTIC_CLAIM_TEXT_LIMIT - len(tail), 0)].rstrip()
            + "……"
        )
    return f"{head}{tail}"


def _deterministic_answer_text(
    claims: tuple[MaterialClaim, ...],
    *,
    required_sentences: tuple[str, ...] = (),
    keep_source_tails: bool = False,
) -> str:
    if not claims:
        answer = _SOFT_FALLBACK_ANSWER_TEXT
    else:
        lines: list[str] = []
        for claim in claims:
            cleaned = _clean_deterministic_claim_text(
                claim.text,
                keep_source_tails=keep_source_tails,
            )
            if cleaned is not None:
                lines.append(f"- {cleaned}")
        if not lines:
            answer = _SOFT_FALLBACK_ANSWER_TEXT
        else:
            truncated = len(lines) > _DETERMINISTIC_ANSWER_MAX_CLAIMS
            answer = "\n".join(lines[:_DETERMINISTIC_ANSWER_MAX_CLAIMS])
            if truncated:
                answer += (
                    f"\n……（其余 {len(lines) - _DETERMINISTIC_ANSWER_MAX_CLAIMS} 条"
                    "候选省略）"
                )
            if len(answer) > _DETERMINISTIC_ANSWER_MAX_CHARS:
                answer = answer[:_DETERMINISTIC_ANSWER_MAX_CHARS] + "……"
    return _append_required_sentences(answer, required_sentences)


_PUBLISHED_PARTIAL_MIN_CHARS = 800


def _published_prose_fallback(
    result: TurnResult,
    emitted: list[str],
    *,
    failure_kind: str,
) -> TurnResult | None:
    """已发布即事实（G7 修复原则 1）： substantial prose reached the user,
    no late failure may replace it with the deterministic template — the
    shipped answer IS the published prose."""
    text = "".join(emitted).strip()
    if len(text) < _PUBLISHED_PARTIAL_MIN_CHARS:
        return None
    limitation = AnswerLimitation(
        code="prose_synthesis_failed",
        material=False,
        stage="prose",
        failure_kind=f"{failure_kind}:shipped_published_prose",
    )
    return result.model_copy(
        update={
            "answer_text": text,
            "render_mode": "prose_partial",
            "limitations": (*result.limitations, limitation),
        }
    )


def _degraded_fallback_text(result: TurnResult) -> str:
    """原则 2/4：兜底答案必须自标降级，不冒充完整回答。"""
    return f"（以下为基于本地数据的简要信息）\n{result.answer_text}"


def _structured_only_public_values(
    result: TurnResult,
    evidence_set: EvidenceSet,
) -> frozenset[str]:
    values = set(_evidence_set_structured_only_values(evidence_set))
    values.update(claim.claim_id for claim in result.claims)
    offer = result.continuation_offer
    if offer is not None:
        values.add(offer.offer_id)
        values.update(offer.reasons)
        for option in offer.options:
            values.update((option.option_id, option.operation))
            if option.source_candidate_id is not None:
                values.add(option.source_candidate_id)
    receipt = result.context_receipt
    if receipt is not None:
        values.update(receipt.traversed_path_ids)
        values.update(
            value
            for value in (
                receipt.selected_option_id,
                receipt.selected_operation,
                receipt.performed_operation,
            )
            if value is not None
        )
    return frozenset(value for value in values if value)


def _prose_contains_structured_only_value(
    prose: str,
    *,
    result: TurnResult,
    evidence_set: EvidenceSet,
) -> bool:
    return any(
        _text_contains_structured_only_value(prose, value)
        for value in _structured_only_public_values(result, evidence_set)
    )


_STRUCTURED_ONLY_TOKEN_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_:-"
)


class _StructuredOnlyProseStreamGuard:
    """Publish only text proven safe against this turn's structured values."""

    def __init__(self, values: frozenset[str]) -> None:
        self._substring_values = tuple(
            value for value in values if ":" in value or len(value) >= 16
        )
        self._bounded_values = tuple(
            value for value in values if ":" not in value and len(value) < 16
        )
        self._tail = ""
        self._tail_left_is_token = False

    @staticmethod
    def _is_token_char(value: str) -> bool:
        return value in _STRUCTURED_ONLY_TOKEN_CHARS

    def _left_is_token(self, data: str, start: int) -> bool:
        if start == 0:
            return self._tail_left_is_token
        return self._is_token_char(data[start - 1])

    def _unsafe_start(self, data: str, *, end_is_boundary: bool) -> int | None:
        earliest: int | None = None
        for value in self._substring_values:
            start = data.find(value)
            if start >= 0 and (earliest is None or start < earliest):
                earliest = start
        for value in self._bounded_values:
            search_from = 0
            while True:
                start = data.find(value, search_from)
                if start < 0:
                    break
                end = start + len(value)
                left_is_boundary = not self._left_is_token(data, start)
                right_is_boundary = (
                    end_is_boundary
                    if end == len(data)
                    else not self._is_token_char(data[end])
                )
                if left_is_boundary and right_is_boundary:
                    if earliest is None or start < earliest:
                        earliest = start
                    break
                search_from = start + 1
        return earliest

    def _pending_start(self, data: str) -> int | None:
        earliest: int | None = None
        for value in self._substring_values:
            max_prefix = min(len(value) - 1, len(data))
            for prefix_length in range(max_prefix, 0, -1):
                if data.endswith(value[:prefix_length]):
                    start = len(data) - prefix_length
                    if earliest is None or start < earliest:
                        earliest = start
                    break
        for value in self._bounded_values:
            max_prefix = min(len(value), len(data))
            for prefix_length in range(max_prefix, 0, -1):
                if not data.endswith(value[:prefix_length]):
                    continue
                start = len(data) - prefix_length
                if not self._left_is_token(data, start):
                    if earliest is None or start < earliest:
                        earliest = start
                    break
        return earliest

    def _safe_prefix_end(self, data: str, requested_end: int) -> int:
        end = requested_end
        while end:
            unsafe_start = self._unsafe_start(
                data[:end],
                end_is_boundary=True,
            )
            if unsafe_start is None:
                return end
            end = unsafe_start
        return 0

    def feed(self, text: str, *, publish: Callable[[str], None]) -> None:
        if not text:
            return
        data = self._tail + text
        unsafe_start = self._unsafe_start(data, end_is_boundary=False)
        if unsafe_start is not None:
            safe_end = self._safe_prefix_end(data, unsafe_start)
            self._tail = ""
            if safe_end:
                publish(data[:safe_end])
            raise ValueError("prose stream failed safety validation")

        pending_start = self._pending_start(data)
        if pending_start is None:
            self._tail = ""
            self._tail_left_is_token = self._is_token_char(data[-1])
            publish(data)
            return

        safe_end = self._safe_prefix_end(data, pending_start)
        self._tail = data[safe_end:]
        self._tail_left_is_token = self._left_is_token(data, safe_end)
        if safe_end:
            publish(data[:safe_end])

    def flush(self, *, publish: Callable[[str], None]) -> None:
        data = self._tail
        self._tail = ""
        if not data:
            return
        unsafe_start = self._unsafe_start(data, end_is_boundary=True)
        if unsafe_start is not None:
            safe_end = self._safe_prefix_end(data, unsafe_start)
            if safe_end:
                publish(data[:safe_end])
            raise ValueError("prose stream failed safety validation")
        self._tail_left_is_token = self._is_token_char(data[-1])
        publish(data)


def _handle_id(handle: EntityHandle) -> str:
    return handle.canonical_id if handle.kind == "canonical" else handle.handle_id


def _physical_traversal_authorized(
    item: EvidenceItem,
    *,
    release_id: str,
    target_id: str,
    source_ids: tuple[str, ...],
    traversal: TypedTraversalRequest,
) -> bool:
    trace = item.local_projection_trace
    if type(trace) is LocalSourceRelationshipTrace:
        source_id = trace.displayed_entity_id
        traced_target_id = trace.candidate_canonical_id
        endpoint_target_id = trace.candidate_canonical_id
        query_tuple = (
            trace.query_relationship_type_id,
            trace.query_direction,
            trace.query_source_type,
            trace.query_target_type,
        )
        traversal_tuple = (
            trace.query_direction,
            trace.query_source_type,
            trace.query_target_type,
            trace.relationship_type_id,
            trace.physical_direction,
        )
    elif type(trace) is LocalCanonicalRelationshipTrace:
        source_id = trace.displayed_company_id
        traced_target_id = trace.candidate_canonical_id
        endpoint_target_id = trace.patent_id
        query_tuple = (
            "company_has_patent",
            "company_to_patent",
            "company",
            "patent",
        )
        traversal_tuple = (
            "company_to_patent",
            "company",
            "patent",
            "patent_has_applicant",
            "inverse",
        )
    elif type(trace) is LocalPatentCompanyRelationshipTrace:
        source_id = trace.displayed_patent_id
        traced_target_id = trace.candidate_canonical_id
        endpoint_target_id = trace.company_id
        query_tuple = (
            "company_has_patent",
            "patent_to_company",
            "patent",
            "company",
        )
        traversal_tuple = (
            "patent_to_company",
            "patent",
            "company",
            "patent_has_applicant",
            "forward",
        )
    elif type(trace) is LocalProfessorPaperRelationshipTrace:
        source_id = trace.displayed_professor_id
        traced_target_id = trace.candidate_canonical_id
        endpoint_target_id = trace.paper_id
        query_tuple = (
            "professor_authored_paper",
            "professor_to_paper",
            "professor",
            "paper",
        )
        traversal_tuple = (
            "professor_to_paper",
            "professor",
            "paper",
            "professor_attributed_to_paper",
            "forward",
        )
    elif type(trace) is LocalPaperProfessorRelationshipTrace:
        source_id = trace.displayed_paper_id
        traced_target_id = trace.candidate_canonical_id
        endpoint_target_id = trace.professor_id
        query_tuple = (
            "professor_authored_paper",
            "paper_to_professor",
            "paper",
            "professor",
        )
        traversal_tuple = (
            "paper_to_professor",
            "paper",
            "professor",
            "professor_attributed_to_paper",
            "inverse",
        )
    else:
        return False

    binding = item.claim_binding
    return (
        trace.release_id == release_id
        and source_id in source_ids
        and trace.displayed_entity_ids == (source_id,)
        and target_id == traced_target_id == endpoint_target_id
        and item.object_id == target_id
        and item.evidence_id == trace.evidence_id
        and (
            trace.query_relationship_type_id,
            trace.query_direction,
            trace.query_source_type,
            trace.query_target_type,
        )
        == query_tuple
        and (
            traversal.path_id,
            traversal.source_domain,
            traversal.target_domain,
            traversal.relationship_type,
            traversal.direction,
        )
        == traversal_tuple
        and trace.relationship_type_id == trace.claim_predicate
        and binding
        == EvidenceClaimBinding(
            subject_id=trace.claim_subject_id,
            predicate=trace.claim_predicate,
            value=trace.claim_value,
            status=trace.claim_status,
        )
    )


@dataclass
class _SessionState:
    release_id: str
    handles: dict[str, EntityHandle] = field(default_factory=dict)
    evidence_by_id: dict[str, EvidenceItem] = field(default_factory=dict)
    result_sets: dict[str, DisplayedResultSet] = field(default_factory=dict)
    active_anchor: EntityHandle | None = None
    displayed_result_set: DisplayedResultSet | None = None
    active_constraints: tuple[ProtectedSlot, ...] = ()
    traversed_path_ids: tuple[str, ...] = ()
    ambiguity_decision_trace_ids: tuple[str, ...] = ()
    last_offer: ContinuationOffer | None = None
    soft_context_subject: str | None = None


@dataclass(frozen=True)
class _SessionAdvance:
    context_receipt: ContextReceipt
    traversal_receipt: TraversalReceipt | None
    continuation_offer: ContinuationOffer | None
    interpretation_notice: InterpretationNotice | None
    response_mode: str
    allowed_subject_ids: frozenset[str]
    limitations: tuple[AnswerLimitation, ...] = ()
    suppress_claims: bool = False


# Subject prefix minted by the serving layer for question-scoped person-criteria
# aggregates (mirrors ``_PERSON_CRITERIA_PART_PREFIX`` in
# ``knowledge_serving_isolated``; kept local to avoid a serving->answer import
# cycle, and pinned equal by the multiturn contract test). Such claims aggregate
# per-candidate findings under a synthetic subject, so they can never equal a
# displayed handle id.
_QUESTION_SCOPED_SUBJECT_PREFIXES = ("serving-person-criteria:",)


def _bind_claim_handles(
    claim: MaterialClaim,
    *,
    state: _SessionState,
    allowed_handle_ids: frozenset[str],
) -> MaterialClaim | None:
    evidence_ids = set(claim.evidence_ids)
    bound_handle_ids = tuple(
        handle_id
        for handle_id, handle in state.handles.items()
        if (not allowed_handle_ids or handle_id in allowed_handle_ids)
        and (
            handle_id == claim.subject_id
            or bool(evidence_ids.intersection(handle.evidence_ids))
        )
    )
    if (
        not bound_handle_ids
        and claim.subject_id is not None
        and claim.subject_id.startswith(_QUESTION_SCOPED_SUBJECT_PREFIXES)
    ):
        # A question-scoped aggregate describes findings about the entities in
        # the turn's scope in self-describing text; bind it to that scope so
        # the retained, grounded evidence reaches the answer instead of being
        # dropped for lacking a handle-shaped subject.
        bound_handle_ids = tuple(
            handle_id
            for handle_id in state.handles
            if not allowed_handle_ids or handle_id in allowed_handle_ids
        )
    if allowed_handle_ids and not bound_handle_ids:
        return None
    return claim.model_copy(update={"subject_handle_ids": bound_handle_ids})


def _merge_slots(
    existing: tuple[ProtectedSlot, ...],
    incoming: tuple[ProtectedSlot, ...],
) -> tuple[ProtectedSlot, ...]:
    merged: list[ProtectedSlot] = list(existing)
    seen = {(slot.kind, slot.value) for slot in existing}
    for slot in incoming:
        key = (slot.kind, slot.value)
        if key not in seen:
            merged.append(slot)
            seen.add(key)
    return tuple(merged)


def _slots_from_pairs(pairs: tuple[tuple[str, str], ...]) -> tuple[ProtectedSlot, ...]:
    return tuple(ProtectedSlot(kind=kind, value=value) for kind, value in pairs)


class _EphemeralKnowledgeAnswer(KnowledgeAnswer):
    def __init__(
        self,
        *,
        answer_selector: AnswerSelector | None,
        assessment_selector: AssessmentSelector | None,
        prose_renderer: ProseRenderer | None,
    ) -> None:
        self._answer_selector = answer_selector
        self._assessment_selector = assessment_selector
        self._prose_renderer = prose_renderer
        self._sessions: dict[str, _SessionState] = {}

    def answer(self, turn: TurnRequest) -> TurnResult:
        request = _revalidate(turn, TurnRequest)
        if request.safety_guidance is not None:
            return self._render_safety_guidance(request)
        directive = request.session_directive or SessionDirective()
        existing_state = self._sessions.get(request.session_id)
        if (
            existing_state is not None
            and existing_state.release_id != request.release_id
            and directive.transition != "topic_switch"
        ):
            return self._session_release_mismatch(request)
        selector = self._answer_selector
        try:
            raw_proposal = (
                _default_proposal(request) if selector is None else selector(request)
            )
            proposal = _revalidate(raw_proposal, AnswerSelectionProposal)
        except TimeoutError:
            return self._degraded(request, reason="timeout")
        except (TypeError, ValueError, ValidationError):
            return self._degraded(request, reason="invalid_output")
        if proposal.selection_input_sha256 != request.content_sha256:
            return self._degraded(request, reason="input_binding_mismatch")
        if proposal.schema_version != _ANSWER_SELECTION_SCHEMA:
            return self._degraded(request, reason="schema_mismatch")
        answer_trace = SelectorDecisionTrace(
            stage="answer_selection",
            schema_version=proposal.schema_version,
            selection_input_sha256=request.content_sha256,
            outcome="accepted",
            decision_id=proposal.decision_id,
            model_id=proposal.model_id,
            prompt_version=proposal.prompt_version,
            decision_run_id=proposal.decision_run_id,
        )

        evidence_by_id = {item.evidence_id: item for item in request.evidence_set.items}
        selector_claim_ids = frozenset(claim.claim_id for claim in proposal.claims)
        grounded_before_session = tuple(
            grounded
            for claim in proposal.claims
            if (
                grounded := _ground_claim(
                    claim,
                    evidence_set=request.evidence_set,
                    selector_claim_ids=selector_claim_ids,
                )
            )
            is not None
        )
        product_parts = tuple(
            part
            for part in request.evidence_set.material_parts
            if part.answer_scoped and part.predicate == "capability"
        )
        session_key = request.session_id
        session_existed = session_key in self._sessions
        session_snapshot = (
            deepcopy(self._sessions[session_key]) if session_existed else None
        )

        def rollback_session() -> None:
            if session_existed:
                assert session_snapshot is not None
                self._sessions[session_key] = session_snapshot
            else:
                self._sessions.pop(session_key, None)

        def rollback_plain_prose_context(
            context: ContextReceipt | None,
        ) -> ContextReceipt | None:
            # An unframed renderer response has no final entity selection. Restore
            # the server-owned snapshot and rebuild the receipt from that state;
            # never retain a selector-only current-turn result set.
            rollback_session()
            if context is None:
                return None
            restored_state = self._sessions.get(session_key)
            if restored_state is None:
                return ContextReceipt(transition_kind=context.transition_kind)

            resolved = context.resolved_referent
            restored_handle_ids = frozenset(restored_state.handles)
            if resolved is not None and (
                resolved.kind not in {"active_anchor", "displayed_member", "result_set"}
                or not set(resolved.handle_ids) <= restored_handle_ids
                or (
                    resolved.result_set_id is not None
                    and resolved.result_set_id not in restored_state.result_sets
                )
            ):
                resolved = None
            resolved_evidence_ids = (
                ()
                if resolved is None
                else tuple(
                    dict.fromkeys(
                        evidence_id
                        for handle_id in resolved.handle_ids
                        for evidence_id in restored_state.handles[
                            handle_id
                        ].evidence_ids
                    )
                )
            )
            return self._context_receipt(
                restored_state,
                resolved_referent=resolved,
                resolved_evidence_ids=resolved_evidence_ids,
                transition_kind=context.transition_kind,
            )

        advance = self._advance_session(request, proposal)
        if advance.suppress_claims:
            grounded_claims: tuple[MaterialClaim, ...] = ()
        else:
            state = self._sessions[session_key]
            grounded_claims = tuple(
                bound
                for grounded in grounded_before_session
                if (
                    bound := _bind_claim_handles(
                        grounded,
                        state=state,
                        allowed_handle_ids=advance.allowed_subject_ids,
                    )
                )
                is not None
            )
        claims_list = list(grounded_claims)
        limitations: list[AnswerLimitation] = list(advance.limitations)
        for part in () if advance.suppress_claims else product_parts:
            supported = any(
                claim.claim_type == "product_capability"
                and claim.subject_id == part.subject_id
                and claim.predicate == part.predicate
                and claim.value == part.requested_value
                and claim.outcome == "supported"
                for claim in claims_list
            )
            if not supported:
                claims_list.append(_unsupported_product_claim(part))
                limitations.append(
                    AnswerLimitation(
                        code="direct_product_capability_evidence_missing",
                        material=True,
                        material_part_id=part.part_id,
                    )
                )
        claims = tuple(claims_list)
        resolved_referent = advance.context_receipt.resolved_referent
        if (
            proposal.claims
            and not claims
            and not advance.suppress_claims
            and (resolved_referent is None or resolved_referent.kind == "current_turn")
        ):
            attributed = tuple(
                item
                for item in request.evidence_set.items
                if item.claim_binding is not None
                and item.source_nature in {"current_web", "supplemental_web"}
            )
            if attributed:
                fallback_claims = tuple(
                    claim
                    for index, item in enumerate(attributed[:5])
                    if (
                        claim := _attributed_claim(
                            request=request,
                            item=item,
                            selector_claim_ids=selector_claim_ids,
                            index=index,
                        )
                    )
                    is not None
                )
                if fallback_claims:
                    limitations.append(
                        AnswerLimitation(
                            code="attributed_evidence_fallback",
                            material=False,
                            reason=(
                                "Selector claims did not bind the conversation scope; "
                                "answering from attributed web evidence instead."
                            ),
                        )
                    )
                    claims = fallback_claims
            if not claims:
                # Only a real degrade rolls the session back: a successful
                # attributed fallback answers through the normal pipeline and
                # keeps the turn's session state (prose scope commits and
                # follow-up turns depend on it).
                rollback_session()
                return self._degraded(
                    request,
                    reason="unsupported_material_claim",
                    additional_limitations=tuple(limitations),
                )
        gap_limitations, gap_sentences = _material_gap_outputs(
            request.evidence_set,
            existing_limitations=tuple(limitations),
        )
        limitations.extend(gap_limitations)
        coverage = request.evidence_set.enumeration_coverage
        if coverage is not None and coverage.unknown_scope:
            limitations.append(
                AnswerLimitation(
                    code="open_world_scope_unknown",
                    material=True,
                    reason="enumeration scope is open-world",
                )
            )
        retained_evidence_ids = tuple(
            dict.fromkeys(
                evidence_id for claim in claims for evidence_id in claim.evidence_ids
            )
        )
        mappings = tuple(_mapping(claim) for claim in claims)
        citations = tuple(
            _citation(evidence_by_id[value]) for value in retained_evidence_ids
        )
        conflicting_claim_keys = {
            (claim.subject_id, claim.predicate, claim.evidence_ids)
            for claim in claims
            if claim.outcome == "conflicting_evidence"
        }
        conflicts = tuple(
            conflict
            for conflict in request.evidence_set.material_conflicts
            if (conflict.subject_id, conflict.predicate, conflict.evidence_ids)
            in conflicting_claim_keys
        )
        assessment = _build_assessment_frame(
            request,
            self._assessment_selector,
        )
        limitations.extend(assessment.limitations)
        answer_limitations = tuple(limitations)
        industry_brief = _build_industry_brief(
            request,
            claims=claims,
            mappings=mappings,
            citations=citations,
            conflicts=conflicts,
            limitations=answer_limitations,
        )
        if not advance.suppress_claims:
            base_answer_text = _deterministic_answer_text(
                claims,
                keep_source_tails=any(
                    marker in request.query
                    for marker in _LINK_SEEKING_QUERY_MARKERS
                ),
            )
        elif (
            advance.response_mode == "clarification_only"
            and advance.continuation_offer is not None
            and advance.continuation_offer.options
        ):
            base_answer_text = "Please select one of the evidenced candidates."
        elif advance.response_mode == "clarification_only":
            base_answer_text = "Please provide one distinguishing detail so I can resolve the ambiguity."
        else:
            base_answer_text = (
                "The requested operation requires a resolved canonical handle."
            )
        answer_text = _append_required_sentences(
            base_answer_text,
            (*gap_sentences, *_enumeration_coverage_sentences(coverage)),
        )
        # Suggested followups come only from the validated, executable
        # continuation options (spec grounded-progressive-answer: suggestions
        # SHALL reflect available eligible relations and SHALL NOT assert a
        # relationship that has not been retrieved or shown to be available).
        suggested_followups = (
            tuple(option.label for option in advance.continuation_offer.options)
            if advance.continuation_offer is not None
            and advance.continuation_offer.options
            else ()
        )
        result = TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            original_query=request.query,
            answer_text=answer_text,
            claims=claims,
            suggested_followups=suggested_followups,
            limitations=answer_limitations,
            claim_evidence_map=mappings,
            citations=citations,
            conflicts=conflicts,
            enumeration_coverage=coverage,
            assessment_frame=assessment.frame,
            industry_brief=industry_brief,
            context_receipt=advance.context_receipt,
            traversal_receipt=advance.traversal_receipt,
            continuation_offer=advance.continuation_offer,
            interpretation_notice=advance.interpretation_notice,
            response_mode=advance.response_mode,
            selector_traces=(answer_trace, *assessment.traces),
            render_mode="deterministic_grounded",
        )
        if self._prose_renderer is None:
            return result
        # Normal answers use the prose renderer. Before any answer text is
        # published, renderer failures may reuse the bounded, server-owned
        # grounded result; after publication they must abort without fallback.
        rendered = None
        synthesis_error: BaseException | None = None
        answer_text_published = False
        progress_failed = False
        published_parts: list[str] = []
        structured_only_values = _structured_only_public_values(
            result,
            request.evidence_set,
        )

        def abort_prose_attempt() -> None:
            if self.prose_progress_abort is not None:
                self.prose_progress_abort()

        try:
            for _attempt in range(2):
                attempt_parts: list[str] = []
                progress_failed = False

                def publish_prose_chunk(chunk: str) -> None:
                    nonlocal answer_text_published, progress_failed
                    attempt_parts.append(chunk)
                    assert self.prose_progress is not None
                    try:
                        acknowledged = self.prose_progress(chunk)
                    except BaseException:
                        progress_failed = True
                        raise
                    if acknowledged is True:
                        answer_text_published = True

                try:
                    stream_fn = getattr(self._prose_renderer, "stream", None)
                    if stream_fn is not None and self.prose_progress is not None:
                        stream_guard = _StructuredOnlyProseStreamGuard(
                            structured_only_values
                        )

                        def guard_prose_chunk(chunk: str) -> None:
                            stream_guard.feed(chunk, publish=publish_prose_chunk)

                        rendered = stream_fn(result, on_chunk=guard_prose_chunk)
                        stream_guard.flush(publish=publish_prose_chunk)
                    else:
                        rendered = self._prose_renderer(result)
                except BaseException as exc:
                    abort_prose_attempt()
                    if (
                        isinstance(exc, TimeoutError)
                        and not answer_text_published
                        and not progress_failed
                    ):
                        synthesis_error = exc
                        continue
                    raise
                published_parts = attempt_parts
                break
            if rendered is None and published_parts:
                shipped = _published_prose_fallback(
                    result, published_parts, failure_kind="no_final_answer"
                )
                if shipped is not None:
                    return shipped
                abort_prose_attempt()
                raise ValueError("prose stream has no final answer")
            if rendered is None and isinstance(synthesis_error, TimeoutError):
                shipped = _published_prose_fallback(
                    result, published_parts, failure_kind="timeout"
                )
                if shipped is not None:
                    return shipped
                fallback_text = _degraded_fallback_text(result)
                prose_limitation = AnswerLimitation(
                    code="prose_synthesis_failed",
                    material=True,
                    stage="prose",
                    failure_kind="timeout",
                )
                return result.model_copy(
                    update={
                        "answer_text": fallback_text,
                        "limitations": (*result.limitations, prose_limitation),
                        "render_mode": "deterministic_fallback",
                        "fallback_sha256": _canonical_sha256(
                            {
                                "answer_text": fallback_text,
                                "claim_ids": [claim.claim_id for claim in claims],
                            }
                        ),
                    }
                )
        except (TypeError, ValueError, ValidationError):
            shipped = _published_prose_fallback(
                result, attempt_parts, failure_kind="invalid_output"
            )
            if shipped is not None:
                _logger.info(
                    "prose invalid_output superseded by published partial (%d chars)",
                    len("".join(attempt_parts)),
                )
                return shipped
            if answer_text_published or progress_failed:
                rollback_session()
                raise
            prose_limitation = AnswerLimitation(
                code="prose_synthesis_failed",
                material=True,
                stage="prose",
                failure_kind="invalid_output",
            )
            return result.model_copy(
                update={
                    "answer_text": _degraded_fallback_text(result),
                    "limitations": (*result.limitations, prose_limitation),
                    "render_mode": "deterministic_fallback",
                    "fallback_sha256": _canonical_sha256(
                        {
                            "answer_text": answer_text,
                            "claim_ids": [claim.claim_id for claim in claims],
                        }
                    ),
                }
            )
        except BaseException:
            rollback_session()
            raise

        try:
            rendered_text = (
                rendered.answer_text
                if isinstance(rendered, ProseSynthesisResult)
                else rendered
                if isinstance(rendered, str)
                else None
            )
            # A corrected FINAL answer legitimately differs from the published
            # drifted chunks when the renderer marked it as superseding the
            # streamed draft; every other mismatch still raises.
            supersedes_draft = (
                isinstance(rendered, ProseSynthesisResult)
                and rendered.supersedes_streamed_draft
            )
            if published_parts and (
                not isinstance(rendered_text, str)
                or (rendered_text != "".join(published_parts) and not supersedes_draft)
            ):
                raise ValueError("prose stream differs from its final answer")
            if isinstance(rendered_text, str) and _prose_contains_structured_only_value(
                rendered_text,
                result=result,
                evidence_set=request.evidence_set,
            ):
                if answer_text_published:
                    raise ValueError("published prose stream failed safety validation")
                abort_prose_attempt()
                fallback_text = _degraded_fallback_text(result)
                prose_limitation = AnswerLimitation(
                    code="prose_synthesis_failed",
                    material=True,
                    stage="prose",
                    failure_kind="unsafe_output",
                )
                return result.model_copy(
                    update={
                        "answer_text": fallback_text,
                        "limitations": (*result.limitations, prose_limitation),
                        "render_mode": "deterministic_fallback",
                        "fallback_sha256": _canonical_sha256(
                            {
                                "answer_text": fallback_text,
                                "claim_ids": [claim.claim_id for claim in claims],
                            }
                        ),
                    }
                )
            if isinstance(rendered, ProseSynthesisResult):
                try:
                    return self._apply_prose_synthesis(
                        request=request,
                        result=result,
                        synthesis=rendered,
                        # The prose renderer already owns insufficiency disclosure
                        # (coverage sentence, unnamed unconfirmed); the
                        # deterministic gap sentence is evidence jargon and stays
                        # only in deterministic/fallback text.
                        gap_sentences=(),
                    )
                except (TypeError, ValueError, ValidationError):
                    shipped = _published_prose_fallback(
                        result, attempt_parts, failure_kind="invalid_selection"
                    )
                    if shipped is not None:
                        _logger.info(
                            "prose invalid_selection superseded by published partial (%d chars)",
                            len("".join(attempt_parts)),
                        )
                        return shipped
                    if answer_text_published:
                        raise
                    abort_prose_attempt()
                    prose_limitation = AnswerLimitation(
                        code="prose_synthesis_failed",
                        material=True,
                        stage="prose",
                        failure_kind="invalid_selection",
                    )
                    return result.model_copy(
                        update={
                            "answer_text": _degraded_fallback_text(result),
                            "limitations": (*result.limitations, prose_limitation),
                            "render_mode": "deterministic_fallback",
                            "fallback_sha256": _canonical_sha256(
                                {
                                    "answer_text": answer_text,
                                    "claim_ids": [claim.claim_id for claim in claims],
                                }
                            ),
                        }
                    )
            if isinstance(rendered, str):
                restored_context = rollback_plain_prose_context(result.context_receipt)
                return result.model_copy(
                    update={
                        # Same split as the structured prose path: prose owns
                        # insufficiency wording; deterministic gap sentences stay
                        # out of prose-rendered answers.
                        "answer_text": rendered,
                        "context_receipt": restored_context,
                        "render_mode": "prose_renderer",
                    }
                )
            shipped = _published_prose_fallback(
                result, published_parts, failure_kind="unrecognized_rendered"
            )
            if shipped is not None:
                return shipped
            return result
        except BaseException:
            abort_prose_attempt()
            rollback_session()
            raise

    def _apply_prose_synthesis(
        self,
        *,
        request: TurnRequest,
        result: TurnResult,
        synthesis: ProseSynthesisResult,
        gap_sentences: tuple[str, ...],
    ) -> TurnResult:
        synthesis = _revalidate(synthesis, ProseSynthesisResult)
        claims_by_id = {claim.claim_id: claim for claim in result.claims}
        if not set(synthesis.selected_claim_ids) <= set(claims_by_id):
            raise ValueError("prose selected a claim outside the current turn")
        context = result.context_receipt
        if context is None:
            if synthesis.selected_handle_ids:
                raise ValueError("prose selected an entity without session context")
            available_handle_ids: frozenset[str] = frozenset()
        else:
            available_handle_ids = frozenset(
                (
                    *(
                        ()
                        if context.displayed_result_set is None
                        else context.displayed_result_set.handle_ids
                    ),
                    *(
                        ()
                        if context.active_anchor is None
                        else (_handle_id(context.active_anchor),)
                    ),
                )
            )
        if not set(synthesis.selected_handle_ids) <= available_handle_ids:
            raise ValueError("prose selected an entity outside the current turn")

        selected_claim_id_set = set(synthesis.selected_claim_ids)
        selected_claims = tuple(
            claim for claim in result.claims if claim.claim_id in selected_claim_id_set
        )
        selected_evidence_ids = frozenset(
            evidence_id
            for claim in selected_claims
            for evidence_id in claim.evidence_ids
        )
        selected_mappings = tuple(
            mapping
            for mapping in result.claim_evidence_map
            if mapping.claim_id in selected_claim_id_set
        )
        selected_citations = tuple(
            citation
            for citation in result.citations
            if citation.evidence_id in selected_evidence_ids
        )
        selected_conflicts = tuple(
            conflict
            for conflict in result.conflicts
            if set(conflict.evidence_ids) <= selected_evidence_ids
        )
        narrowed_context, narrowed_traversal = self._commit_prose_scope(
            request=request,
            context=context,
            selected_handle_ids=synthesis.selected_handle_ids,
            traversal=result.traversal_receipt,
        )
        return result.model_copy(
            update={
                "answer_text": _append_required_sentences(
                    synthesis.answer_text,
                    gap_sentences,
                ),
                "claims": selected_claims,
                "claim_evidence_map": selected_mappings,
                "citations": selected_citations,
                "conflicts": selected_conflicts,
                "context_receipt": narrowed_context,
                "traversal_receipt": narrowed_traversal,
                # Ambiguity offers ARE the current turn's output (clarification
                # choices or a bounded switch); only candidate-generated offers
                # are retired once prose commits the answer scope.
                "continuation_offer": (
                    result.continuation_offer
                    if result.continuation_offer is not None
                    and "ambiguity" in result.continuation_offer.reasons
                    else None
                ),
                "render_mode": "prose_renderer",
            }
        )

    def _commit_prose_scope(
        self,
        *,
        request: TurnRequest,
        context: ContextReceipt | None,
        selected_handle_ids: tuple[str, ...],
        traversal: TraversalReceipt | None,
    ) -> tuple[ContextReceipt | None, TraversalReceipt | None]:
        if context is None:
            return None, traversal
        if not selected_handle_ids:
            # An empty prose selection is an index-mapping failure, never a
            # deliberate "reject everything": keep the turn's retrieved set
            # instead of narrowing the session's displayed universe to nothing.
            return context, traversal
        state = self._sessions[request.session_id]
        selected_handles = tuple(state.handles[value] for value in selected_handle_ids)
        prior_set = context.displayed_result_set
        result_set_id = "result-set:sha256:" + _canonical_sha256(
            {
                "session_id": request.session_id,
                "turn_id": request.turn_id,
                "release_id": request.release_id,
                "handle_ids": list(selected_handle_ids),
                "selection": "final_prose",
            }
        )
        displayed = DisplayedResultSet(
            result_set_id=result_set_id,
            handles=selected_handles,
            handle_ids=selected_handle_ids,
            enumeration_mode=None if prior_set is None else prior_set.enumeration_mode,
            continuation_state=None
            if prior_set is None
            else prior_set.continuation_state,
        )
        state.displayed_result_set = displayed
        state.result_sets[result_set_id] = displayed
        if len(selected_handles) == 1 or state.active_anchor is None:
            # A single confirmed entity takes over the anchor; a multi-entity
            # answer only narrows the displayed set, so a list turn (papers,
            # suppliers) cannot silently re-anchor later person follow-ups to
            # its first member.
            state.active_anchor = selected_handles[0] if selected_handles else None
        resolved = ResolvedReferent(
            kind="current_turn",
            handle_ids=selected_handle_ids,
            result_set_id=result_set_id,
            enumeration_mode=displayed.enumeration_mode,
            continuation_state=displayed.continuation_state,
        )
        narrowed_context = context.model_copy(
            update={
                "active_anchor": state.active_anchor,
                "displayed_result_set": displayed,
                "resolved_referent": resolved,
            }
        )
        narrowed_traversal = (
            None
            if traversal is None
            else traversal.model_copy(
                update={
                    "target_handle_ids": tuple(
                        value
                        for value in traversal.target_handle_ids
                        if value in selected_handle_ids
                    )
                }
            )
        )
        return narrowed_context, narrowed_traversal

    def _advance_session(
        self,
        request: TurnRequest,
        proposal: AnswerSelectionProposal,
    ) -> _SessionAdvance:
        key = request.session_id
        directive = request.session_directive or SessionDirective()
        existed = key in self._sessions
        topic_switch = directive.transition == "topic_switch"
        if not existed or topic_switch:
            self._sessions[key] = _SessionState(release_id=request.release_id)
        state = self._sessions[key]
        # Per-turn soft subject: reset every turn so a later named-entity or
        # expansion turn never inherits a stale web-only anchor.
        state.soft_context_subject = request.soft_context_subject
        transition_kind = "topic_switch" if topic_switch else "turn"
        previous_result_set = state.displayed_result_set

        current_item_by_id = {
            item.evidence_id: item for item in request.evidence_set.items
        }
        for item in request.evidence_set.items:
            state.evidence_by_id[item.evidence_id] = item
        current_handles: dict[str, EntityHandle] = {}
        handle_limitations: list[AnswerLimitation] = []
        for handle in request.evidence_set.entity_handles:
            handle_id = _handle_id(handle)
            if (
                isinstance(handle, WebEntityHandle)
                and handle.session_id != request.session_id
            ):
                handle_limitations.append(
                    AnswerLimitation(
                        code="web_handle_session_mismatch",
                        material=True,
                        handle_id=handle.handle_id,
                    )
                )
                continue
            current_handles[handle_id] = handle
            state.handles[handle_id] = handle
        state.active_constraints = _merge_slots(
            state.active_constraints,
            request.evidence_set.protected_slots,
        )

        if request.continuation_selection is not None:
            return self._apply_continuation_selection(
                request,
                state,
                request.continuation_selection,
            )

        resolved_referent: ResolvedReferent | None = None
        resolved_evidence_ids: tuple[str, ...] = ()
        if (
            previous_result_set is not None
            and directive.referent == "displayed_member"
            and directive.displayed_ordinal is not None
        ):
            ordinal = directive.displayed_ordinal
            if len(previous_result_set.handle_ids) >= ordinal:
                selected_id = previous_result_set.handle_ids[ordinal - 1]
                resolved_referent = ResolvedReferent(
                    kind="displayed_member",
                    handle_ids=(selected_id,),
                    result_set_id=previous_result_set.result_set_id,
                    enumeration_mode=previous_result_set.enumeration_mode,
                    continuation_state=previous_result_set.continuation_state,
                )
                state.active_anchor = state.handles[selected_id]
                resolved_evidence_ids = state.active_anchor.evidence_ids
        elif (
            previous_result_set is not None
            and directive.referent == "displayed_result_set"
        ):
            resolved_referent = ResolvedReferent(
                kind="result_set",
                handle_ids=previous_result_set.handle_ids,
                result_set_id=previous_result_set.result_set_id,
                enumeration_mode=previous_result_set.enumeration_mode,
                continuation_state=previous_result_set.continuation_state,
            )
            resolved_evidence_ids = tuple(
                dict.fromkeys(
                    evidence_id
                    for handle in previous_result_set.handles
                    for evidence_id in handle.evidence_ids
                )
            )
        elif state.active_anchor is not None and directive.referent == "active_anchor":
            active_id = _handle_id(state.active_anchor)
            resolved_referent = ResolvedReferent(
                kind="active_anchor",
                handle_ids=(active_id,),
            )
            resolved_evidence_ids = state.active_anchor.evidence_ids

        decision = request.evidence_set.ambiguity_decision
        interpretation_notice: InterpretationNotice | None = None
        ambiguity_offer: ContinuationOffer | None = None
        if decision is not None and decision.decision_trace_id is not None:
            state.ambiguity_decision_trace_ids = tuple(
                dict.fromkeys(
                    (*state.ambiguity_decision_trace_ids, decision.decision_trace_id)
                )
            )
            if decision.outcome == "blocked":
                ambiguity_offer = self._ambiguity_offer(
                    request,
                    decision,
                    selection_kind="clarification_selection",
                )
                state.active_anchor = None
                state.last_offer = ambiguity_offer
                context = self._context_receipt(
                    state,
                    resolved_referent=resolved_referent,
                    resolved_evidence_ids=resolved_evidence_ids,
                    transition_kind=transition_kind,
                )
                return _SessionAdvance(
                    context_receipt=context,
                    traversal_receipt=None,
                    continuation_offer=ambiguity_offer,
                    interpretation_notice=None,
                    response_mode="clarification_only",
                    allowed_subject_ids=frozenset(),
                    limitations=tuple(handle_limitations),
                    suppress_claims=True,
                )
            if (
                decision.outcome == "selected"
                and decision.selected_handle_id is not None
            ):
                selected_handle = state.handles.get(decision.selected_handle_id)
                if selected_handle is not None:
                    state.active_anchor = selected_handle
                interpretation_notice = InterpretationNotice(
                    selected_handle_id=decision.selected_handle_id,
                    decision_trace_id=decision.decision_trace_id,
                )
                ambiguity_offer = self._ambiguity_offer(
                    request,
                    decision,
                    selection_kind="continuation_selection",
                )

        traversal = request.evidence_set.requested_traversal
        source_ids: tuple[str, ...] = ()
        if traversal is not None:
            if resolved_referent is not None and resolved_referent.kind == "result_set":
                source_ids = resolved_referent.handle_ids
            elif (
                state.active_anchor is not None
                and state.active_anchor.domain == traversal.source_domain
            ):
                source_ids = (_handle_id(state.active_anchor),)
            else:
                source_ids = tuple(
                    handle_id
                    for handle_id, handle in current_handles.items()
                    if handle.domain == traversal.source_domain
                )
        unresolved_source: WebEntityHandle | None = None
        for handle_id in source_ids:
            handle = state.handles.get(handle_id)
            if (
                isinstance(handle, WebEntityHandle)
                and handle.resolution_state == "unresolved"
            ):
                unresolved_source = handle
                break
        if traversal is not None and unresolved_source is not None:
            state.active_anchor = unresolved_source
            limitation = AnswerLimitation(
                code="unresolved_web_handle_cannot_traverse",
                material=True,
                handle_id=unresolved_source.handle_id,
                requested_path_id=traversal.path_id,
            )
            context = self._context_receipt(
                state,
                resolved_referent=resolved_referent,
                resolved_evidence_ids=resolved_evidence_ids,
                transition_kind=transition_kind,
                performed_operation="read_only_resolution_required",
            )
            state.last_offer = None
            return _SessionAdvance(
                context_receipt=context,
                traversal_receipt=None,
                continuation_offer=None,
                interpretation_notice=interpretation_notice,
                response_mode="answer",
                allowed_subject_ids=frozenset({unresolved_source.handle_id}),
                limitations=(limitation,),
                suppress_claims=True,
            )

        proposed_ids = tuple(dict.fromkeys(proposal.displayed_handle_ids))
        traversal_receipt: TraversalReceipt | None = None
        if traversal is not None:
            selected_ids = tuple(
                handle_id
                for handle_id in proposed_ids
                if handle_id in current_handles
                and current_handles[handle_id].domain == traversal.target_domain
                and self._is_traversal_target(
                    request,
                    target_id=handle_id,
                    source_ids=source_ids,
                    traversal=traversal,
                )
            )
            traversal_receipt = TraversalReceipt(
                path_id=traversal.path_id,
                source_handle_ids=source_ids,
                target_handle_ids=selected_ids,
            )
            state.traversed_path_ids = tuple(
                dict.fromkeys((*state.traversed_path_ids, traversal.path_id))
            )
            if state.active_anchor is None and source_ids:
                state.active_anchor = state.handles.get(source_ids[0])
            if resolved_referent is None and source_ids:
                resolved_referent = ResolvedReferent(
                    kind="active_anchor" if len(source_ids) == 1 else "result_set",
                    handle_ids=source_ids,
                    result_set_id=(
                        previous_result_set.result_set_id
                        if previous_result_set is not None
                        and source_ids == previous_result_set.handle_ids
                        else None
                    ),
                    enumeration_mode=(
                        previous_result_set.enumeration_mode
                        if previous_result_set is not None
                        and source_ids == previous_result_set.handle_ids
                        else None
                    ),
                    continuation_state=(
                        previous_result_set.continuation_state
                        if previous_result_set is not None
                        and source_ids == previous_result_set.handle_ids
                        else None
                    ),
                )
        else:
            selected_ids = tuple(
                handle_id for handle_id in proposed_ids if handle_id in current_handles
            )
            if decision is not None and decision.outcome == "selected":
                selected_ids = tuple(
                    handle_id
                    for handle_id in selected_ids
                    if handle_id == decision.selected_handle_id
                )

        current_result_set: DisplayedResultSet | None = None
        if selected_ids:
            coverage = request.evidence_set.enumeration_coverage
            result_set_id = "result-set:sha256:" + _canonical_sha256(
                {
                    "session_id": request.session_id,
                    "turn_id": request.turn_id,
                    "release_id": request.release_id,
                    "handle_ids": list(selected_ids),
                }
            )
            displayed_result_set = DisplayedResultSet(
                result_set_id=result_set_id,
                handles=tuple(state.handles[handle_id] for handle_id in selected_ids),
                handle_ids=selected_ids,
                enumeration_mode=None if coverage is None else coverage.mode,
                continuation_state=(
                    None if coverage is None else coverage.continuation_state
                ),
            )
            state.displayed_result_set = displayed_result_set
            state.result_sets[result_set_id] = displayed_result_set
            current_result_set = displayed_result_set
            if state.active_anchor is None or topic_switch:
                state.active_anchor = state.handles[selected_ids[0]]
            if resolved_referent is None:
                resolved_referent = ResolvedReferent(
                    kind="current_turn",
                    handle_ids=selected_ids,
                    result_set_id=result_set_id,
                    enumeration_mode=displayed_result_set.enumeration_mode,
                    continuation_state=displayed_result_set.continuation_state,
                )

        continuation_offer = ambiguity_offer or self._candidate_offer(
            request,
            proposal,
            current_handles=current_handles,
            current_item_by_id=current_item_by_id,
            current_result_set=current_result_set,
        )
        state.last_offer = continuation_offer
        allowed_subject_ids = frozenset((*source_ids, *selected_ids))
        if not allowed_subject_ids:
            if (
                directive.referent == "displayed_member"
                and state.active_anchor is not None
            ):
                # A member-scoped turn stays scoped to the selected member.
                allowed_subject_ids = frozenset({_handle_id(state.active_anchor)})
            else:
                # A follow-up whose current turn selected nothing still belongs
                # to the conversation's displayed universe: claims may bind any
                # member of the prior displayed set plus the anchor, never a
                # lone anchor.
                fallback_ids: list[str] = []
                if state.displayed_result_set is not None:
                    fallback_ids.extend(state.displayed_result_set.handle_ids)
                if state.active_anchor is not None:
                    anchor_id = _handle_id(state.active_anchor)
                    if anchor_id not in fallback_ids:
                        fallback_ids.append(anchor_id)
                allowed_subject_ids = frozenset(fallback_ids)
        context = self._context_receipt(
            state,
            resolved_referent=resolved_referent,
            resolved_evidence_ids=resolved_evidence_ids,
            transition_kind=transition_kind,
        )
        return _SessionAdvance(
            context_receipt=context,
            traversal_receipt=traversal_receipt,
            continuation_offer=continuation_offer,
            interpretation_notice=interpretation_notice,
            response_mode="answer",
            allowed_subject_ids=allowed_subject_ids,
            limitations=tuple(handle_limitations),
        )

    def _apply_continuation_selection(
        self,
        request: TurnRequest,
        state: _SessionState,
        selection: ContinuationSelection,
    ) -> _SessionAdvance:
        offer = state.last_offer
        if offer is None or offer.offer_id != selection.offer_id:
            raise ValueError("continuation selection must bind the active offer")
        option = next(
            (
                value
                for value in offer.options
                if value.option_id == selection.option_id
            ),
            None,
        )
        if option is None:
            raise ValueError("continuation selection must bind an offered option")
        target_ids = option.target_handle_ids
        selected_result_set: DisplayedResultSet | None = None
        if option.result_set_id is not None:
            selected_result_set = state.result_sets.get(option.result_set_id)
            if selected_result_set is None:
                raise ValueError("continuation result set is no longer available")
            target_ids = selected_result_set.handle_ids
        if target_ids and target_ids[0] not in state.handles:
            # The selection cannot execute: retrieval produced no evidenced
            # handle for the target (e.g., the entity is gone). Surface an
            # honest limitation instead of silently keeping the prior anchor
            # while recording the selection as if it had happened.
            state.last_offer = None
            limitation = AnswerLimitation(
                code="continuation_target_unavailable",
                material=True,
                handle_id=target_ids[0],
                reason="selected continuation target has no evidenced handle",
            )
            context = self._context_receipt(
                state,
                resolved_referent=None,
                resolved_evidence_ids=(),
                transition_kind=offer.selection_kind,
                performed_operation="continuation_target_unavailable",
            )
            return _SessionAdvance(
                context_receipt=context,
                traversal_receipt=None,
                continuation_offer=None,
                interpretation_notice=None,
                response_mode="answer",
                allowed_subject_ids=frozenset(),
                limitations=(limitation,),
                suppress_claims=True,
            )
        if target_ids:
            state.active_anchor = state.handles[target_ids[0]]
        state.active_constraints = _merge_slots(
            state.active_constraints,
            _slots_from_pairs(option.constraint_pairs),
        )
        resolved_referent = ResolvedReferent(
            kind="result_set"
            if selected_result_set is not None
            else "continuation_option",
            handle_ids=target_ids,
            result_set_id=None
            if selected_result_set is None
            else selected_result_set.result_set_id,
            enumeration_mode=(
                None
                if selected_result_set is None
                else selected_result_set.enumeration_mode
            ),
            continuation_state=(
                None
                if selected_result_set is None
                else selected_result_set.continuation_state
            ),
        )
        resolved_evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for handle_id in target_ids
                if handle_id in state.handles
                for evidence_id in state.handles[handle_id].evidence_ids
            )
        )
        state.last_offer = None
        context = self._context_receipt(
            state,
            resolved_referent=resolved_referent,
            resolved_evidence_ids=resolved_evidence_ids,
            transition_kind=offer.selection_kind,
            selected_option_id=option.option_id,
            selected_operation=option.operation,
        )
        return _SessionAdvance(
            context_receipt=context,
            traversal_receipt=None,
            continuation_offer=None,
            interpretation_notice=None,
            response_mode="answer",
            allowed_subject_ids=frozenset(target_ids),
        )

    @staticmethod
    def _is_traversal_target(
        request: TurnRequest,
        *,
        target_id: str,
        source_ids: tuple[str, ...],
        traversal: TypedTraversalRequest,
    ) -> bool:
        for item in request.evidence_set.items:
            binding = item.claim_binding
            if item.object_id != target_id or binding is None:
                continue
            if item.local_projection_trace is not None:
                if _physical_traversal_authorized(
                    item,
                    release_id=request.release_id,
                    target_id=target_id,
                    source_ids=source_ids,
                    traversal=traversal,
                ):
                    return True
                continue
            if binding.predicate != traversal.relationship_type:
                continue
            if (binding.subject_id in source_ids and binding.value == target_id) or (
                binding.subject_id == target_id and binding.value in source_ids
            ):
                return True
        return False

    def _ambiguity_offer(
        self,
        request: TurnRequest,
        decision: AmbiguityDecision,
        *,
        selection_kind: str,
    ) -> ContinuationOffer | None:
        candidate_by_id = {
            candidate.handle_id: candidate
            for candidate in decision.candidates
            if candidate.handle_id is not None and candidate.viable
        }
        options: list[ContinuationOption] = []
        for handle_id in decision.viable_alternative_handle_ids:
            candidate = candidate_by_id.get(handle_id)
            if candidate is None:
                continue
            options.append(
                ContinuationOption(
                    option_id=f"ambiguity-option:{decision.decision_id}:{len(options) + 1}",
                    label=f"Select {candidate.discriminator}",
                    operation=(
                        "select_candidate"
                        if selection_kind == "clarification_selection"
                        else "switch_candidate"
                    ),
                    target_handle_ids=(handle_id,),
                    evidence_ids=candidate.evidence_ids,
                    discriminator=candidate.discriminator,
                )
            )
        if not options:
            return None
        return ContinuationOffer(
            offer_id=(
                "continuation-offer:sha256:"
                + _canonical_sha256(
                    {
                        "session_id": request.session_id,
                        "turn_id": request.turn_id,
                        "decision_id": decision.decision_id,
                        "option_ids": [option.option_id for option in options],
                    }
                )
            ),
            reasons=("ambiguity",),
            options=tuple(options[:3]),
            selection_kind=selection_kind,
        )

    def _candidate_offer(
        self,
        request: TurnRequest,
        proposal: AnswerSelectionProposal,
        *,
        current_handles: Mapping[str, EntityHandle],
        current_item_by_id: Mapping[str, EvidenceItem],
        current_result_set: DisplayedResultSet | None,
    ) -> ContinuationOffer | None:
        candidates_by_id = {
            candidate.candidate_id: candidate
            for candidate in request.evidence_set.continuation_candidates
        }
        options: list[ContinuationOption] = []
        reasons: list[str] = []
        for candidate_id in proposal.continuation_candidate_ids:
            candidate = candidates_by_id.get(candidate_id)
            if candidate is None or not candidate.available:
                continue
            policy = _CONTINUATION_OPTION_POLICY.get(candidate.reason)
            if policy is None:
                continue
            expected_operation, expected_target_kind, neutral_label = policy
            if (candidate.operation, candidate.target_kind) != (
                expected_operation,
                expected_target_kind,
            ):
                continue
            if candidate.reason == "eligible_next_hop":
                if not candidate.relation_type:
                    continue
            elif candidate.relation_type is not None:
                continue
            candidate_evidence_ids = set(candidate.evidence_ids)
            if not candidate_evidence_ids or not candidate_evidence_ids <= set(
                current_item_by_id
            ):
                continue
            if candidate.target_kind == "current_handle":
                if not candidate.target_handle_ids or not set(
                    candidate.target_handle_ids
                ) <= set(current_handles):
                    continue
                target_evidence_ids = {
                    evidence_id
                    for handle_id in candidate.target_handle_ids
                    for evidence_id in current_handles[handle_id].evidence_ids
                }
                if not candidate_evidence_ids <= target_evidence_ids:
                    continue
                result_set_id = None
            elif candidate.target_kind == "current_result_set":
                if (
                    current_result_set is None
                    or not current_result_set.handle_ids
                    or candidate.target_handle_ids
                ):
                    continue
                displayed_evidence_ids = {
                    evidence_id
                    for handle in current_result_set.handles
                    for evidence_id in handle.evidence_ids
                }
                if not candidate_evidence_ids <= displayed_evidence_ids:
                    continue
                result_set_id = current_result_set.result_set_id
            else:
                continue
            options.append(
                ContinuationOption(
                    option_id=f"continuation-option:{candidate.candidate_id}",
                    label=neutral_label,
                    operation=candidate.operation,
                    target_handle_ids=candidate.target_handle_ids,
                    result_set_id=result_set_id,
                    constraint_pairs=candidate.constraint_pairs,
                    relation_type=candidate.relation_type,
                    evidence_ids=candidate.evidence_ids,
                    source_candidate_id=candidate.candidate_id,
                )
            )
            if candidate.reason not in reasons:
                reasons.append(candidate.reason)
            if len(options) == 3:
                break
        if not options:
            return None
        return ContinuationOffer(
            offer_id=(
                "continuation-offer:sha256:"
                + _canonical_sha256(
                    {
                        "session_id": request.session_id,
                        "turn_id": request.turn_id,
                        "option_ids": [option.option_id for option in options],
                    }
                )
            ),
            reasons=tuple(reasons),
            options=tuple(options),
        )

    @staticmethod
    def _context_receipt(
        state: _SessionState,
        *,
        resolved_referent: ResolvedReferent | None,
        resolved_evidence_ids: tuple[str, ...],
        transition_kind: str,
        selected_option_id: str | None = None,
        selected_operation: str | None = None,
        performed_operation: str | None = None,
    ) -> ContextReceipt:
        return ContextReceipt(
            active_anchor=state.active_anchor,
            displayed_result_set=state.displayed_result_set,
            resolved_referent=resolved_referent,
            resolved_evidence_ids=resolved_evidence_ids,
            active_constraints=state.active_constraints,
            traversed_path_ids=state.traversed_path_ids,
            transition_kind=transition_kind,
            selected_option_id=selected_option_id,
            selected_operation=selected_operation,
            performed_operation=performed_operation,
            ambiguity_decision_trace_ids=state.ambiguity_decision_trace_ids,
            soft_context_subject=state.soft_context_subject,
        )

    @staticmethod
    def _render_safety_guidance(request: TurnRequest) -> TurnResult:
        directive = request.safety_guidance
        assert directive is not None
        static_text = (
            "请远离涉嫌黄赌毒等违法活动的场所，注意人身与财产安全；"
            "如遇可疑情况，请通过官方求助或举报渠道（如 110、辖区派出所、"
            "政务服务热线）获取帮助。"
        )
        if directive.mode == "static":
            return TurnResult(
                session_id=request.session_id,
                turn_id=request.turn_id,
                release_id=request.release_id,
                answer_text=static_text,
                response_mode="safety_guidance",
                render_mode="deterministic_safety",
            )

        evidence_by_id = {item.evidence_id: item for item in request.evidence_set.items}
        admitted: list[tuple[EvidenceItem, str]] = []
        rejected_ids: list[str] = []
        for evidence_id in directive.official_evidence_ids:
            item = evidence_by_id.get(evidence_id)
            binding = None if item is None else item.claim_binding
            if (
                item is None
                or item.source_nature != "current_web"
                or item.source_authority != "official"
                or item.web_snapshot is None
                or binding is None
                or binding.predicate not in _OFFICIAL_SAFETY_PREDICATES
            ):
                rejected_ids.append(evidence_id)
                continue
            safe_text = _official_safety_text(item)
            if safe_text is None:
                rejected_ids.append(evidence_id)
                continue
            admitted.append((item, safe_text))

        claims = tuple(
            MaterialClaim(
                claim_id=f"safety-claim:{item.evidence_id}",
                claim_type="official_safety_reference",
                text=safe_text,
                subject_id=item.claim_binding.subject_id,
                predicate=item.claim_binding.predicate,
                value=item.claim_binding.value,
                evidence_ids=(item.evidence_id,),
                outcome="supported",
                source_natures=("current_web",),
                synthesis=False,
                answer_scoped=True,
                canonical=False,
                confirmed=True,
                status=item.claim_binding.status,
            )
            for item, safe_text in admitted
            if item.claim_binding is not None
        )
        limitations = tuple(
            AnswerLimitation(
                code="official_safety_evidence_rejected",
                reason=evidence_id,
                material=True,
                stage="safety_guidance",
                failure_kind="invalid_official_evidence",
            )
            for evidence_id in rejected_ids
        )
        answer_text = "\n".join((static_text, *(claim.text for claim in claims)))
        return TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text=answer_text,
            claims=claims,
            limitations=limitations,
            claim_evidence_map=tuple(_mapping(claim) for claim in claims),
            citations=tuple(_citation(item) for item, _ in admitted),
            response_mode="safety_guidance",
            render_mode="deterministic_safety",
        )

    @staticmethod
    def _session_release_mismatch(request: TurnRequest) -> TurnResult:
        answer_text = "The retained session belongs to a different release."
        return TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text=answer_text,
            limitations=(
                AnswerLimitation(
                    code="session_release_mismatch",
                    reason="use a typed topic switch before rebinding the session release",
                    material=True,
                    stage="session",
                    failure_kind="release_mismatch",
                ),
            ),
            render_mode="deterministic_fallback",
            fallback_sha256=_canonical_sha256(
                {"answer_text": answer_text, "reason": "release_mismatch"}
            ),
        )

    @staticmethod
    def _degraded(
        request: TurnRequest,
        *,
        reason: str,
        additional_limitations: tuple[AnswerLimitation, ...] = (),
        required_sentences: tuple[str, ...] = (),
    ) -> TurnResult:
        selection_limitation = AnswerLimitation(
            code="answer_selection_rejected",
            reason=reason,
            material=True,
            stage="answer_selection",
            failure_kind=reason,
        )
        base_limitations = (selection_limitation, *additional_limitations)
        gap_limitations, gap_sentences = _material_gap_outputs(
            request.evidence_set,
            existing_limitations=base_limitations,
        )
        answer_text = _append_required_sentences(
            _SOFT_FALLBACK_ANSWER_TEXT,
            (*required_sentences, *gap_sentences),
        )
        return TurnResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            release_id=request.release_id,
            answer_text=answer_text,
            limitations=(*base_limitations, *gap_limitations),
            selector_traces=(
                SelectorDecisionTrace(
                    stage="answer_selection",
                    schema_version=_ANSWER_SELECTION_SCHEMA,
                    selection_input_sha256=request.content_sha256,
                    outcome="degraded",
                    failure_kind=reason,
                ),
            ),
            render_mode="deterministic_fallback",
            fallback_sha256=_canonical_sha256(
                {"answer_text": answer_text, "reason": reason}
            ),
        )


def create_ephemeral_knowledge_answer(
    *,
    answer_selector: AnswerSelector | None = None,
    assessment_selector: Callable[[TurnRequest], Any] | None = None,
    prose_renderer: Callable[[Any], Any] | None = None,
) -> KnowledgeAnswer:
    """Create an in-memory answer module without provider or durable state adapters."""

    return _EphemeralKnowledgeAnswer(
        answer_selector=answer_selector,
        assessment_selector=assessment_selector,
        prose_renderer=prose_renderer,
    )


__all__ = [
    "AmbiguityCandidate",
    "AmbiguityDecision",
    "AnswerSelectionProposal",
    "AssessmentDimensionProposal",
    "AssessmentEvidenceBinding",
    "AssessmentFrame",
    "AssessmentIntent",
    "AssessmentSelectionProposal",
    "CanonicalEntityHandle",
    "ContinuationCandidate",
    "ContinuationOffer",
    "ContinuationSelection",
    "EnumerationCoverage",
    "EvidenceClaimBinding",
    "EvidenceConflict",
    "EvidenceItem",
    "EvidenceSet",
    "IndustryBriefIntent",
    "IndustryBrief",
    "KnowledgeAnswer",
    "MaterialClaim",
    "MaterialClaimProposal",
    "MaterialQuestionPart",
    "ProtectedSlot",
    "SafetyGuidanceDirective",
    "SelectorDecisionTrace",
    "SessionDirective",
    "TurnRequest",
    "TurnResult",
    "TypedTraversalRequest",
    "WebEntityHandle",
    "WebEvidenceSnapshot",
    "create_ephemeral_knowledge_answer",
]
