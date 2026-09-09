"""Typed, failure-safe knowledge-gap creation behind one record interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from .contracts import CanonicalDatetime
from .contracts import CandidateRelease
from .contracts import Confidence
from .contracts import ContractModel
from .contracts import GapClass
from .contracts import GapSeverity
from .contracts import GapStatus
from .contracts import KnowledgeGap
from .contracts import NonEmptyStr
from .contracts import NonNegativeInt
from .contracts import ReviewState
from .contracts import ReleaseState
from .contracts import ReleaseVerification
from .contracts import Sha256


POLICY_VERSION = "knowledge-gap-feedback-v1"


class GapTrigger(str, Enum):
    no_result = "no_result"
    insufficient_evidence = "insufficient_evidence"
    repeated_web_dependence = "repeated_web_dependence"
    recurring_product_capability = "recurring_product_capability"
    missing_relationship = "missing_relationship"
    user_feedback = "user_feedback"
    benchmark_failure = "benchmark_failure"
    index_parity = "index_parity"


class GapSignal(ContractModel):
    """Observation-only input; final gap outcomes remain module-owned."""

    signal_id: NonEmptyStr
    trigger: GapTrigger
    release_id: NonEmptyStr
    affected_domains: tuple[NonEmptyStr, ...] = Field(min_length=1)
    affected_paths: tuple[NonEmptyStr, ...] = ()
    query_trace_id: NonEmptyStr | None = None
    answer_trace_id: NonEmptyStr | None = None
    benchmark_case_id: NonEmptyStr | None = None
    telemetry_key: NonEmptyStr | None = None
    observed_symptom: NonEmptyStr
    evidence_ids: tuple[NonEmptyStr, ...] = ()
    demand_observation_ids: tuple[NonEmptyStr, ...] = ()
    observed_at: CanonicalDatetime

    @field_validator(
        "affected_domains",
        "affected_paths",
        "evidence_ids",
        "demand_observation_ids",
    )
    @classmethod
    def require_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("gap signal tuples must contain unique values")
        return values

    @model_validator(mode="after")
    def validate_observation(self) -> GapSignal:
        if not any(
            (
                self.query_trace_id,
                self.answer_trace_id,
                self.benchmark_case_id,
                self.telemetry_key,
            )
        ):
            raise ValueError(
                "gap signal requires a query, answer, benchmark, or telemetry trace"
            )
        if (
            self.trigger
            in {
                GapTrigger.repeated_web_dependence,
                GapTrigger.recurring_product_capability,
            }
            and len(self.demand_observation_ids) < 2
        ):
            raise ValueError(
                "repeated or recurring gap signals require at least two raw demand observations"
            )
        if (
            self.trigger is GapTrigger.recurring_product_capability
            and self.answer_trace_id is None
        ):
            raise ValueError(
                "recurring Product-capability demand requires an answer trace"
            )
        return self


class GapClassificationRequest(ContractModel):
    """Content-bound structured input for an optional classifier adapter."""

    policy_version: NonEmptyStr
    signal_id: NonEmptyStr
    trigger: GapTrigger
    release_id: NonEmptyStr
    affected_domains: tuple[NonEmptyStr, ...] = Field(min_length=1)
    affected_paths: tuple[NonEmptyStr, ...] = ()
    query_trace_id: NonEmptyStr | None = None
    answer_trace_id: NonEmptyStr | None = None
    benchmark_case_id: NonEmptyStr | None = None
    telemetry_key: NonEmptyStr | None = None
    observed_symptom: NonEmptyStr
    evidence_ids: tuple[NonEmptyStr, ...] = ()
    demand_observation_ids: tuple[NonEmptyStr, ...] = ()
    demand_count: NonNegativeInt
    scenario_families: tuple[NonEmptyStr, ...] = Field(min_length=1)
    observed_at: CanonicalDatetime
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_content_identity(self) -> GapClassificationRequest:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        if self.content_sha256 != _canonical_sha256(payload):
            raise ValueError(
                "classification request content_sha256 must bind the normalized input"
            )
        return self


class GapClassificationProposal(ContractModel):
    """Schema-validated proposal; it never owns lifecycle or resolution state."""

    classification_input_sha256: Sha256
    gap_class: GapClass
    confidence: Confidence
    proposed_owner: NonEmptyStr
    proposed_remediation: NonEmptyStr
    severity: GapSeverity
    rationale: NonEmptyStr


def _require_unique(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values")


def _require_content_identity(value: ContractModel, *, exclude: set[str]) -> None:
    payload = value.model_dump(mode="json", exclude=exclude)
    content_sha256 = getattr(value, "content_sha256")
    if content_sha256 != _canonical_sha256(payload):
        raise ValueError("content_sha256 must bind the complete normalized value")


class OfflineRemediationReceipt(ContractModel):
    """Reviewed offline work linked to one gap and one candidate release."""

    receipt_id: NonEmptyStr
    gap_id: NonEmptyStr
    remediation_kind: NonEmptyStr
    execution_mode: Literal["offline"]
    source_release_id: NonEmptyStr
    candidate_release_id: NonEmptyStr
    affected_domains: tuple[NonEmptyStr, ...] = Field(min_length=1)
    affected_paths: tuple[NonEmptyStr, ...] = ()
    offline_run_id: NonEmptyStr
    source_batch_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    landing_artifact_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    build_run_id: NonEmptyStr
    review_state: Literal["accepted"]
    review_evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    started_at: CanonicalDatetime
    completed_at: CanonicalDatetime
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_receipt(self) -> OfflineRemediationReceipt:
        _require_unique(self.affected_domains, "affected_domains")
        _require_unique(self.affected_paths, "affected_paths")
        _require_unique(self.source_batch_ids, "source_batch_ids")
        _require_unique(self.landing_artifact_ids, "landing_artifact_ids")
        _require_unique(self.review_evidence_ids, "review_evidence_ids")
        if self.started_at > self.completed_at:
            raise ValueError("remediation started_at must not be after completed_at")
        _require_content_identity(self, exclude={"content_sha256"})
        return self


class GapEffectVerification(ContractModel):
    """Acceptance evidence for the exact user or operational effect of a repair."""

    verification_id: NonEmptyStr
    gap_id: NonEmptyStr
    release_id: NonEmptyStr
    affected_domains: tuple[NonEmptyStr, ...] = Field(min_length=1)
    affected_paths: tuple[NonEmptyStr, ...] = ()
    query_trace_id: NonEmptyStr | None = None
    answer_trace_id: NonEmptyStr | None = None
    benchmark_case_id: NonEmptyStr | None = None
    scenario_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    accepted: bool
    evidence_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    verified_at: CanonicalDatetime
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_effect(self) -> GapEffectVerification:
        if not any((self.query_trace_id, self.answer_trace_id, self.benchmark_case_id)):
            raise ValueError("effect verification requires an affected trace")
        _require_unique(self.affected_domains, "affected_domains")
        _require_unique(self.affected_paths, "affected_paths")
        _require_unique(self.scenario_ids, "scenario_ids")
        _require_unique(self.evidence_ids, "evidence_ids")
        _require_content_identity(self, exclude={"content_sha256"})
        return self


class GapRemediationRequest(ContractModel):
    """Exact immutable transition input; callers cannot supply a final gap."""

    request_id: NonEmptyStr
    gap: KnowledgeGap
    remediation_receipt: OfflineRemediationReceipt
    candidate_release: CandidateRelease
    release_verification: ReleaseVerification | None
    effect_verification: GapEffectVerification | None
    requested_at: CanonicalDatetime
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_request_identity(self) -> GapRemediationRequest:
        _require_content_identity(self, exclude={"content_sha256"})
        return self


class GapRemediationResult(ContractModel):
    """Deterministic linked or resolved view over an immutable original gap."""

    transition_id: NonEmptyStr
    transition_state: Literal["linked", "resolved"]
    remediation_input_sha256: Sha256
    gap: KnowledgeGap
    remediation_receipt: OfflineRemediationReceipt
    release_verification: ReleaseVerification | None
    effect_verification: GapEffectVerification | None
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_result(self) -> GapRemediationResult:
        if self.transition_state == "linked":
            if self.gap.status is GapStatus.resolved:
                raise ValueError("linked remediation cannot return a resolved gap")
            if (
                self.release_verification is not None
                or self.effect_verification is not None
            ):
                raise ValueError(
                    "linked remediation cannot retain acceptance verification"
                )
        elif (
            self.gap.status is not GapStatus.resolved
            or self.release_verification is None
            or self.effect_verification is None
        ):
            raise ValueError(
                "resolved remediation requires a resolved gap and both verifications"
            )
        _require_content_identity(
            self,
            exclude={"content_sha256", "transition_id"},
        )
        return self


GapClassifier = Callable[[GapClassificationRequest], object]


class KnowledgeGapFeedback(ABC):
    """Create one initial typed gap without exposing classifier or storage stages."""

    @abstractmethod
    def record(self, signal: GapSignal) -> KnowledgeGap:
        """Validate and record one observed gap signal."""

    @abstractmethod
    def apply_remediation(
        self,
        request: GapRemediationRequest,
    ) -> GapRemediationResult:
        """Link reviewed offline work and resolve only with exact accepted evidence."""


_SCENARIO_FAMILY = {
    GapTrigger.no_result: "query:no_result",
    GapTrigger.insufficient_evidence: "answer:insufficient_evidence",
    GapTrigger.repeated_web_dependence: "query:web_dependence",
    GapTrigger.recurring_product_capability: "answer:product_capability",
    GapTrigger.missing_relationship: "query:relationship",
    GapTrigger.user_feedback: "operations:user_feedback",
    GapTrigger.benchmark_failure: "acceptance:benchmark_failure",
    GapTrigger.index_parity: "release:index_parity",
}


_DETERMINISTIC_OUTCOMES = {
    GapTrigger.no_result: (
        GapClass.knowledge_coverage,
        0.5,
        "knowledge_coverage",
        "review_no_result",
        GapSeverity.medium,
    ),
    GapTrigger.insufficient_evidence: (
        GapClass.knowledge_coverage,
        0.5,
        "knowledge_coverage",
        "collect_missing_evidence",
        GapSeverity.medium,
    ),
    GapTrigger.repeated_web_dependence: (
        GapClass.knowledge_coverage,
        0.9,
        "offline_evidence_enrichment",
        "collect_repeatedly_missing_local_evidence",
        GapSeverity.high,
    ),
    GapTrigger.recurring_product_capability: (
        GapClass.knowledge_coverage,
        0.95,
        "offline_evidence_enrichment",
        "collect_direct_product_capability_evidence",
        GapSeverity.high,
    ),
    GapTrigger.missing_relationship: (
        GapClass.relationship,
        0.9,
        "relationship_enrichment",
        "collect_missing_relationship_evidence",
        GapSeverity.medium,
    ),
    GapTrigger.user_feedback: (
        GapClass.context,
        0.35,
        "product_quality",
        "review_user_feedback",
        GapSeverity.medium,
    ),
    GapTrigger.benchmark_failure: (
        GapClass.retrieval_precision,
        0.5,
        "acceptance_quality",
        "review_benchmark_failure",
        GapSeverity.medium,
    ),
    GapTrigger.index_parity: (
        GapClass.index_parity,
        1.0,
        "release_index",
        "repair_index_parity",
        GapSeverity.high,
    ),
}


_PROTECTED_TRIGGERS = {
    GapTrigger.repeated_web_dependence,
    GapTrigger.recurring_product_capability,
    GapTrigger.missing_relationship,
    GapTrigger.index_parity,
}


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _classification_request(signal: GapSignal) -> GapClassificationRequest:
    demand_count = len(signal.demand_observation_ids) or 1
    payload = {
        "policy_version": POLICY_VERSION,
        "signal_id": signal.signal_id,
        "trigger": signal.trigger,
        "release_id": signal.release_id,
        "affected_domains": signal.affected_domains,
        "affected_paths": signal.affected_paths,
        "query_trace_id": signal.query_trace_id,
        "answer_trace_id": signal.answer_trace_id,
        "benchmark_case_id": signal.benchmark_case_id,
        "telemetry_key": signal.telemetry_key,
        "observed_symptom": signal.observed_symptom,
        "evidence_ids": signal.evidence_ids,
        "demand_observation_ids": signal.demand_observation_ids,
        "demand_count": demand_count,
        "scenario_families": (_SCENARIO_FAMILY[signal.trigger],),
        "observed_at": signal.observed_at,
    }
    json_payload = GapClassificationRequest.model_construct(
        **payload,
        content_sha256="0" * 64,
    ).model_dump(mode="json", exclude={"content_sha256"})
    return GapClassificationRequest(
        **payload,
        content_sha256=_canonical_sha256(json_payload),
    )


def _deterministic_proposal(
    request: GapClassificationRequest,
) -> GapClassificationProposal:
    gap_class, confidence, owner, remediation, severity = _DETERMINISTIC_OUTCOMES[
        request.trigger
    ]
    return GapClassificationProposal(
        classification_input_sha256=request.content_sha256,
        gap_class=gap_class,
        confidence=confidence,
        proposed_owner=owner,
        proposed_remediation=remediation,
        severity=severity,
        rationale=f"Deterministic initial policy for {request.trigger.value}.",
    )


def _revalidate_remediation_request(
    request: GapRemediationRequest,
) -> GapRemediationRequest:
    try:
        payload = request.model_dump(mode="python")
    except (AttributeError, TypeError) as exc:
        raise ValueError("remediation request must be a typed request") from exc
    return GapRemediationRequest.model_validate(payload)


def _validate_remediation_lineage(request: GapRemediationRequest) -> None:
    gap = request.gap
    receipt = request.remediation_receipt
    candidate = request.candidate_release

    if gap.status not in {GapStatus.open, GapStatus.in_review, GapStatus.planned}:
        raise ValueError("remediation requires an active unresolved gap")
    if gap.review_state not in {ReviewState.unreviewed, ReviewState.in_review}:
        raise ValueError("remediation requires an unresolved review state")
    if any(
        (
            gap.resolved_release_id,
            gap.resolved_release_state,
            gap.resolution_verification_ids,
        )
    ):
        raise ValueError("remediation input gap must not contain resolution evidence")
    if candidate.release_id == gap.release_id:
        raise ValueError("remediation candidate must differ from the source release")
    if request.requested_at < gap.updated_at:
        raise ValueError("remediation request cannot precede the current gap state")

    expected_receipt_values = (
        gap.gap_id,
        gap.release_id,
        candidate.release_id,
        gap.affected_domains,
        gap.affected_paths,
        candidate.run_id,
        candidate.source_batch_ids,
    )
    actual_receipt_values = (
        receipt.gap_id,
        receipt.source_release_id,
        receipt.candidate_release_id,
        receipt.affected_domains,
        receipt.affected_paths,
        receipt.build_run_id,
        receipt.source_batch_ids,
    )
    if actual_receipt_values != expected_receipt_values:
        raise ValueError("remediation receipt lineage does not match the gap and build")
    if receipt.started_at < gap.created_at:
        raise ValueError("remediation cannot start before the gap exists")
    if receipt.completed_at > request.requested_at:
        raise ValueError("remediation request cannot precede offline completion")


def _validate_accepted_resolution(request: GapRemediationRequest) -> None:
    candidate = request.candidate_release
    receipt = request.remediation_receipt
    release = request.release_verification
    effect = request.effect_verification
    gap = request.gap
    if release is None or effect is None:
        raise ValueError("accepted candidate resolution requires both verifications")
    if not release.accepted or not effect.accepted:
        raise ValueError("gap resolution requires accepted verification evidence")
    if (
        release.candidate_release_id != candidate.release_id
        or release.manifest_sha256 != candidate.manifest_sha256
    ):
        raise ValueError("release verification does not bind the exact candidate")
    if release.verified_at < receipt.completed_at:
        raise ValueError("release verification cannot precede offline remediation")

    expected_effect_values = (
        gap.gap_id,
        candidate.release_id,
        gap.affected_domains,
        gap.affected_paths,
        gap.query_trace_id,
        gap.answer_trace_id,
        gap.benchmark_case_id,
    )
    actual_effect_values = (
        effect.gap_id,
        effect.release_id,
        effect.affected_domains,
        effect.affected_paths,
        effect.query_trace_id,
        effect.answer_trace_id,
        effect.benchmark_case_id,
    )
    if actual_effect_values != expected_effect_values:
        raise ValueError("effect verification does not bind the original gap scope")
    if gap.benchmark_case_id is not None and effect.scenario_ids != (
        gap.benchmark_case_id,
    ):
        raise ValueError("effect verification must bind the exact benchmark scenario")
    if effect.verified_at <= release.verified_at:
        raise ValueError(
            "effect verification must follow accepted release verification"
        )
    if request.requested_at < effect.verified_at:
        raise ValueError(
            "remediation request cannot precede intended-effect verification"
        )


def _transition_gap(
    request: GapRemediationRequest,
    *,
    transition_state: Literal["linked", "resolved"],
    transitioned_at: datetime,
) -> KnowledgeGap:
    payload = request.gap.model_dump(mode="python")
    if transition_state == "linked":
        payload.update(
            status=GapStatus.planned,
            review_state=ReviewState.in_review,
            updated_at=transitioned_at,
            resolved_release_id=None,
            resolved_release_state=None,
            resolution_verification_ids=(),
        )
    else:
        release = request.release_verification
        effect = request.effect_verification
        if release is None or effect is None:  # pragma: no cover - guarded above
            raise ValueError("resolved transition requires both verifications")
        payload.update(
            status=GapStatus.resolved,
            review_state=ReviewState.accepted,
            updated_at=transitioned_at,
            resolved_release_id=request.candidate_release.release_id,
            resolved_release_state=ReleaseState.accepted,
            resolution_verification_ids=(
                *release.evidence_ids,
                *effect.evidence_ids,
            ),
        )
    return KnowledgeGap.model_validate(payload)


def _remediation_result(
    request: GapRemediationRequest,
    *,
    transition_state: Literal["linked", "resolved"],
    gap: KnowledgeGap,
) -> GapRemediationResult:
    payload = {
        "transition_state": transition_state,
        "remediation_input_sha256": request.content_sha256,
        "gap": gap,
        "remediation_receipt": request.remediation_receipt,
        "release_verification": request.release_verification,
        "effect_verification": request.effect_verification,
    }
    normalized = GapRemediationResult.model_construct(
        transition_id="pending",
        content_sha256="0" * 64,
        **payload,
    ).model_dump(mode="json", exclude={"content_sha256", "transition_id"})
    content_sha256 = _canonical_sha256(normalized)
    transition_identity = _canonical_sha256(
        {
            "remediation_input_sha256": request.content_sha256,
            "result_content_sha256": content_sha256,
        }
    )
    return GapRemediationResult(
        transition_id=f"gap-transition:{transition_identity}",
        content_sha256=content_sha256,
        **payload,
    )


class _EphemeralKnowledgeGapFeedback(KnowledgeGapFeedback):
    def __init__(
        self,
        *,
        classifier: GapClassifier | None,
        clock: Callable[[], datetime],
    ) -> None:
        self._classifier = classifier
        self._clock = clock
        self._remediation_results: dict[str, GapRemediationResult] = {}

    def _classify(
        self,
        request: GapClassificationRequest,
    ) -> GapClassificationProposal:
        fallback = _deterministic_proposal(request)
        if self._classifier is None:
            return fallback
        try:
            raw_candidate = self._classifier(request)
        except (ConnectionError, TimeoutError):
            return fallback
        try:
            candidate_payload = (
                raw_candidate.model_dump(mode="python")
                if isinstance(raw_candidate, GapClassificationProposal)
                else raw_candidate
            )
            candidate = GapClassificationProposal.model_validate(candidate_payload)
        except ValidationError:
            return fallback
        if candidate.classification_input_sha256 != request.content_sha256:
            return fallback
        if request.trigger in _PROTECTED_TRIGGERS:
            return fallback
        return candidate

    def record(self, signal: GapSignal) -> KnowledgeGap:
        request = _classification_request(signal)
        proposal = self._classify(request)
        gap_identity = _canonical_sha256(
            {
                "policy_version": POLICY_VERSION,
                "signal": signal.model_dump(mode="json"),
                "classification": proposal.model_dump(mode="json"),
            }
        )
        recorded_at = self._clock()
        return KnowledgeGap(
            gap_id=f"gap:{gap_identity}",
            gap_class=proposal.gap_class,
            status=GapStatus.open,
            release_id=signal.release_id,
            affected_domains=signal.affected_domains,
            affected_paths=signal.affected_paths,
            query_trace_id=signal.query_trace_id,
            answer_trace_id=signal.answer_trace_id,
            benchmark_case_id=signal.benchmark_case_id,
            telemetry_key=signal.telemetry_key,
            observed_symptom=signal.observed_symptom,
            evidence_ids=signal.evidence_ids,
            classification_confidence=proposal.confidence,
            review_state=ReviewState.unreviewed,
            proposed_owner=proposal.proposed_owner,
            proposed_remediation=proposal.proposed_remediation,
            demand_count=request.demand_count,
            scenario_families=request.scenario_families,
            severity=proposal.severity,
            created_at=recorded_at,
            updated_at=recorded_at,
        )

    def apply_remediation(
        self,
        request: GapRemediationRequest,
    ) -> GapRemediationResult:
        validated = _revalidate_remediation_request(request)
        _validate_remediation_lineage(validated)
        cached = self._remediation_results.get(validated.content_sha256)
        if cached is not None:
            return cached
        transitioned_at = self._clock()
        if transitioned_at < validated.requested_at:
            raise ValueError("transition clock cannot precede the remediation request")

        candidate_state = validated.candidate_release.state
        if candidate_state is ReleaseState.candidate:
            if (
                validated.release_verification is not None
                or validated.effect_verification is not None
            ):
                raise ValueError(
                    "candidate linkage cannot carry acceptance verification"
                )
            transition_state: Literal["linked", "resolved"] = "linked"
        elif candidate_state is ReleaseState.accepted:
            _validate_accepted_resolution(validated)
            transition_state = "resolved"
        else:
            raise ValueError("only candidate linkage or accepted resolution is allowed")

        transitioned_gap = _transition_gap(
            validated,
            transition_state=transition_state,
            transitioned_at=transitioned_at,
        )
        result = _remediation_result(
            validated,
            transition_state=transition_state,
            gap=transitioned_gap,
        )
        self._remediation_results[validated.content_sha256] = result
        return result


def create_ephemeral_knowledge_gap_feedback(
    *,
    classifier: GapClassifier | None = None,
    clock: Callable[[], datetime] | None = None,
) -> KnowledgeGapFeedback:
    """Compose the pure implementation with optional recorded external adapters."""

    return _EphemeralKnowledgeGapFeedback(
        classifier=classifier,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )


__all__ = [
    "GapEffectVerification",
    "GapClassificationProposal",
    "GapClassificationRequest",
    "GapClassifier",
    "GapRemediationRequest",
    "GapRemediationResult",
    "GapSignal",
    "GapTrigger",
    "KnowledgeGapFeedback",
    "OfflineRemediationReceipt",
    "create_ephemeral_knowledge_gap_feedback",
]
