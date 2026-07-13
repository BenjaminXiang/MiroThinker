"""Deterministic offline domain-inclusion policies for Canonical V2.

The module is intentionally storage- and provider-independent.  It evaluates a
complete, evidence-bound batch produced by the offline build and returns shared
``PolicyDecision`` values.  Query-time callers must not use this module to
promote Web results into canonical data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal, cast

from pydantic import Field, JsonValue, field_validator, model_validator

from .contracts import (
    CanonicalDatetime,
    CanonicalIdentity,
    CanonicalIdentityState,
    ContractModel,
    EvidenceArtifact,
    NonEmptyStr,
    PolicyDecision,
    PolicyKind,
    PolicyOutcome,
    PolicyReference,
    Sha256,
    SourceAssertion,
    SourceIdentity,
    SourceIdentityState,
    SourceRecord,
)


Domain = Literal["company", "paper", "patent", "professor"]
ScopeKind = Literal[
    "company_skeleton",
    "paper_roster_discovery",
    "patent_export",
    "professor_seed",
]
EvidenceLane = Literal["offline_enrichment", "offline_landing", "query_time_web"]
CompanyDimensionName = Literal[
    "basic_identity",
    "innovation_business_relevance",
    "shenzhen_geography",
    "source_validation",
]
CompanyDimensionOutcome = Literal[
    "supported",
    "insufficient_evidence",
    "contradicted",
]

DOMAINS: tuple[Domain, ...] = ("company", "paper", "patent", "professor")
_SCOPE_BY_DOMAIN: dict[Domain, ScopeKind] = {
    "company": "company_skeleton",
    "paper": "paper_roster_discovery",
    "patent": "patent_export",
    "professor": "professor_seed",
}
_COMPANY_DIMENSIONS: frozenset[str] = frozenset(
    {
        "basic_identity",
        "innovation_business_relevance",
        "shenzhen_geography",
        "source_validation",
    }
)


class DomainInclusionIntegrityError(ValueError):
    """The supplied offline inclusion batch is internally inconsistent."""


def _canonical_sha256(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _unique(values: Iterable[str], label: str) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


class ApprovedSourceBatch(ContractModel):
    domain: Domain
    scope_kind: ScopeKind
    source_batch_id: NonEmptyStr
    artifact_id: NonEmptyStr
    artifact_content_sha256: Sha256

    @model_validator(mode="after")
    def validate_scope_domain(self) -> ApprovedSourceBatch:
        if _SCOPE_BY_DOMAIN[self.domain] != self.scope_kind:
            raise ValueError("approved source scope kind does not match its domain")
        return self


class ApprovedSourceScopeManifest(ContractModel):
    manifest_version: NonEmptyStr
    approved_batches: tuple[ApprovedSourceBatch, ...] = Field(min_length=1)
    created_at: CanonicalDatetime
    content_sha256: Sha256

    @field_validator("approved_batches")
    @classmethod
    def canonicalize_batches(
        cls, batches: tuple[ApprovedSourceBatch, ...]
    ) -> tuple[ApprovedSourceBatch, ...]:
        keys = tuple(
            (batch.domain, batch.scope_kind, batch.source_batch_id, batch.artifact_id)
            for batch in batches
        )
        if len(keys) != len(set(keys)):
            raise ValueError("approved source batches must be unique")
        return tuple(
            sorted(
                batches,
                key=lambda batch: (
                    batch.domain,
                    batch.scope_kind,
                    batch.source_batch_id,
                    batch.artifact_id,
                    batch.artifact_content_sha256,
                ),
            )
        )

    @model_validator(mode="after")
    def validate_content_hash(self) -> ApprovedSourceScopeManifest:
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"content_sha256"}),
        )
        if self.content_sha256 != _canonical_sha256(payload):
            raise ValueError("content_sha256 must bind the approved source manifest")
        return self


class CompanyValidationDimension(ContractModel):
    dimension: CompanyDimensionName
    outcome: CompanyDimensionOutcome
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("supporting_assertion_ids")
    @classmethod
    def validate_assertion_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_unique(values, "Company dimension assertion IDs")))


class IncrementalCompanyValidationDecision(ContractModel):
    decision_id: NonEmptyStr
    company_identity_id: NonEmptyStr
    policy: PolicyReference
    decision_run_id: NonEmptyStr
    decision_origin: Literal["offline_build"]
    dimensions: tuple[CompanyValidationDimension, ...] = Field(min_length=1)
    decided_at: CanonicalDatetime
    content_sha256: Sha256

    @field_validator("dimensions")
    @classmethod
    def canonicalize_dimensions(
        cls, values: tuple[CompanyValidationDimension, ...]
    ) -> tuple[CompanyValidationDimension, ...]:
        names = tuple(value.dimension for value in values)
        _unique(names, "Company validation dimensions")
        return tuple(sorted(values, key=lambda value: value.dimension))

    @model_validator(mode="after")
    def validate_decision(self) -> IncrementalCompanyValidationDecision:
        if self.policy.policy_kind is not PolicyKind.inclusion:
            raise ValueError("incremental Company validation requires inclusion policy")
        payload = cast(
            JsonValue,
            self.model_dump(
                mode="json",
                exclude={"decision_id", "content_sha256"},
            ),
        )
        expected_hash = _canonical_sha256(payload)
        if self.content_sha256 != expected_hash:
            raise ValueError("content_sha256 must bind the Company validation decision")
        if self.decision_id != f"company-validation:sha256:{expected_hash}":
            raise ValueError("decision_id must be content-addressed")
        return self


class InclusionCandidate(ContractModel):
    canonical_identity_id: NonEmptyStr
    domain: Domain
    source_identity_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    supporting_assertion_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    evidence_lane: EvidenceLane
    professor_anchor_identity_id: NonEmptyStr | None = None
    incremental_company_validation_decision_id: NonEmptyStr | None = None

    @field_validator(
        "source_identity_ids",
        "source_record_ids",
        "supporting_assertion_ids",
    )
    @classmethod
    def canonicalize_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_unique(values, "inclusion candidate IDs")))

    @model_validator(mode="after")
    def validate_domain_options(self) -> InclusionCandidate:
        if self.domain != "paper" and self.professor_anchor_identity_id is not None:
            raise ValueError("only Paper candidates may carry a Professor anchor")
        if (
            self.domain != "company"
            and self.incremental_company_validation_decision_id is not None
        ):
            raise ValueError("only Company candidates may carry incremental validation")
        return self


class InclusionBatchRequest(ContractModel):
    release_id: NonEmptyStr
    decision_run_id: NonEmptyStr
    evaluated_at: CanonicalDatetime
    policies: tuple[PolicyReference, ...]
    approved_source_scope_manifest: ApprovedSourceScopeManifest
    canonical_identities: tuple[CanonicalIdentity, ...]
    source_identities: tuple[SourceIdentity, ...]
    evidence_artifacts: tuple[EvidenceArtifact, ...]
    source_records: tuple[SourceRecord, ...]
    source_assertions: tuple[SourceAssertion, ...]
    candidates: tuple[InclusionCandidate, ...]
    included_professor_identity_ids: tuple[NonEmptyStr, ...] = ()
    incremental_company_validation_decisions: tuple[
        IncrementalCompanyValidationDecision, ...
    ] = ()

    @field_validator("included_professor_identity_ids")
    @classmethod
    def canonicalize_professor_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(_unique(values, "included Professor identity IDs")))


class DomainInclusionResult(ContractModel):
    release_id: NonEmptyStr
    decision_run_id: NonEmptyStr
    evaluated_at: CanonicalDatetime
    approved_source_scope_manifest_sha256: Sha256
    policy_decisions: tuple[PolicyDecision, ...]
    admitted_identity_ids_by_domain: dict[Domain, tuple[NonEmptyStr, ...]]
    review_identity_ids_by_domain: dict[Domain, tuple[NonEmptyStr, ...]]
    excluded_identity_ids_by_domain: dict[Domain, tuple[NonEmptyStr, ...]]
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_result(self) -> DomainInclusionResult:
        expected_domains = set(DOMAINS)
        for label, mapping in (
            ("admitted", self.admitted_identity_ids_by_domain),
            ("review", self.review_identity_ids_by_domain),
            ("excluded", self.excluded_identity_ids_by_domain),
        ):
            if set(mapping) != expected_domains:
                raise ValueError(
                    f"{label} outcome map must contain exactly four domains"
                )
            for domain, ids in mapping.items():
                if tuple(sorted(ids)) != ids or len(ids) != len(set(ids)):
                    raise ValueError(
                        f"{label} {domain} identities must be sorted unique"
                    )
        decision_ids = tuple(
            decision.subject_identity_id for decision in self.policy_decisions
        )
        if tuple(sorted(decision_ids)) != decision_ids or len(decision_ids) != len(
            set(decision_ids)
        ):
            raise ValueError(
                "policy decisions must be sorted with one decision per identity"
            )
        outcome_maps = {
            PolicyOutcome.admitted: self.admitted_identity_ids_by_domain,
            PolicyOutcome.review: self.review_identity_ids_by_domain,
            PolicyOutcome.excluded: self.excluded_identity_ids_by_domain,
        }
        accounted: dict[str, PolicyOutcome] = {}
        for outcome, mapping in outcome_maps.items():
            for identity_ids in mapping.values():
                for identity_id in identity_ids:
                    if identity_id in accounted:
                        raise ValueError(
                            "one identity cannot appear in multiple inclusion outcomes"
                        )
                    accounted[identity_id] = outcome
        if set(accounted) != set(decision_ids):
            raise ValueError(
                "inclusion outcome maps must account for every policy decision"
            )
        for decision in self.policy_decisions:
            if (
                decision.release_id != self.release_id
                or decision.policy.policy_kind is not PolicyKind.inclusion
                or decision.evaluated_at != self.evaluated_at
                or decision.outcome is PolicyOutcome.limited
                or accounted[decision.subject_identity_id] is not decision.outcome
            ):
                raise ValueError(
                    "inclusion decision does not match its result envelope/outcome map"
                )
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"content_sha256"}),
        )
        if self.content_sha256 != _canonical_sha256(payload):
            raise ValueError("content_sha256 must bind the complete inclusion result")
        return self


def create_approved_source_scope_manifest(
    *,
    manifest_version: str,
    approved_batches: tuple[ApprovedSourceBatch, ...],
    created_at: datetime,
) -> ApprovedSourceScopeManifest:
    canonical_batches = tuple(
        sorted(
            approved_batches,
            key=lambda batch: (
                batch.domain,
                batch.scope_kind,
                batch.source_batch_id,
                batch.artifact_id,
                batch.artifact_content_sha256,
            ),
        )
    )
    # Pydantic normalizes the datetime to UTC. Hash the normalized model payload,
    # not the caller's local-offset representation.
    normalized_created_at = created_at.astimezone(timezone.utc)
    provisional = ApprovedSourceScopeManifest.model_construct(
        manifest_version=manifest_version,
        approved_batches=canonical_batches,
        created_at=normalized_created_at,
        content_sha256="0" * 64,
    )
    normalized_content = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"content_sha256"}),
    )
    return ApprovedSourceScopeManifest(
        manifest_version=manifest_version,
        approved_batches=canonical_batches,
        created_at=normalized_created_at,
        content_sha256=_canonical_sha256(normalized_content),
    )


def create_incremental_company_validation_decision(
    *,
    company_identity_id: str,
    policy: PolicyReference,
    decision_run_id: str,
    decision_origin: Literal["offline_build"],
    dimensions: tuple[CompanyValidationDimension, ...],
    decided_at: datetime,
) -> IncrementalCompanyValidationDecision:
    canonical_dimensions = tuple(sorted(dimensions, key=lambda value: value.dimension))
    provisional = IncrementalCompanyValidationDecision.model_construct(
        decision_id="pending",
        company_identity_id=company_identity_id,
        policy=policy,
        decision_run_id=decision_run_id,
        decision_origin=decision_origin,
        dimensions=canonical_dimensions,
        decided_at=decided_at,
        content_sha256="0" * 64,
    )
    payload = cast(
        JsonValue,
        provisional.model_dump(
            mode="json",
            exclude={"decision_id", "content_sha256"},
        ),
    )
    content_sha256 = _canonical_sha256(payload)
    return IncrementalCompanyValidationDecision(
        decision_id=f"company-validation:sha256:{content_sha256}",
        company_identity_id=company_identity_id,
        policy=policy,
        decision_run_id=decision_run_id,
        decision_origin=decision_origin,
        dimensions=canonical_dimensions,
        decided_at=decided_at,
        content_sha256=content_sha256,
    )


def _policy_domain(policy: PolicyReference) -> Domain:
    for domain in DOMAINS:
        if policy.policy_id == f"canonical-v2-{domain}-inclusion":
            return domain
    raise DomainInclusionIntegrityError(
        f"unknown domain inclusion policy_id: {policy.policy_id}"
    )


def _decision_id(
    *,
    request: InclusionBatchRequest,
    candidate: InclusionCandidate,
    policy: PolicyReference,
    outcome: PolicyOutcome,
    limitations: tuple[str, ...],
    hard_exclusion_codes: tuple[str, ...],
) -> str:
    payload = cast(
        JsonValue,
        {
            "release_id": request.release_id,
            "decision_run_id": request.decision_run_id,
            "subject_identity_id": candidate.canonical_identity_id,
            "policy": policy.model_dump(mode="json"),
            "outcome": outcome.value,
            "limitations": list(limitations),
            "hard_exclusion_codes": list(hard_exclusion_codes),
            "supporting_assertion_ids": list(candidate.supporting_assertion_ids),
            "evaluated_at": request.evaluated_at.isoformat(),
            "manifest_sha256": request.approved_source_scope_manifest.content_sha256,
        },
    )
    return f"domain-inclusion:sha256:{_canonical_sha256(payload)}"


class DomainInclusionEngine:
    """Evaluate all four domain policies over one immutable offline batch."""

    def evaluate(self, request: InclusionBatchRequest) -> DomainInclusionResult:
        context = _ValidatedBatch(request)
        decisions: list[PolicyDecision] = []
        by_identity: dict[str, PolicyDecision] = {}

        professor_candidates = sorted(
            (
                candidate
                for candidate in request.candidates
                if candidate.domain == "professor"
            ),
            key=lambda candidate: candidate.canonical_identity_id,
        )
        for candidate in professor_candidates:
            decision = self._evaluate_manifest_membership(
                context,
                candidate,
                exclusion_code="outside_professor_inclusion_scope",
            )
            decisions.append(decision)
            by_identity[candidate.canonical_identity_id] = decision

        included_professors = set(request.included_professor_identity_ids)
        included_professors.update(
            identity_id
            for identity_id, decision in by_identity.items()
            if decision.outcome is PolicyOutcome.admitted
        )

        for candidate in sorted(
            (
                candidate
                for candidate in request.candidates
                if candidate.domain == "paper"
            ),
            key=lambda candidate: candidate.canonical_identity_id,
        ):
            in_scope = context.candidate_in_approved_scope(candidate)
            anchor = candidate.professor_anchor_identity_id
            anchor_asserted = any(
                assertion.field_path == "discovery.professor_anchor_identity_id"
                and assertion.value == anchor
                for assertion in context.candidate_assertions(candidate)
            )
            if in_scope and anchor in included_professors and anchor_asserted:
                decision = context.policy_decision(candidate, PolicyOutcome.admitted)
            else:
                decision = context.policy_decision(
                    candidate,
                    PolicyOutcome.excluded,
                    hard_exclusion_codes=("outside_paper_discovery_scope",),
                )
            decisions.append(decision)
            by_identity[candidate.canonical_identity_id] = decision

        for candidate in sorted(
            (
                candidate
                for candidate in request.candidates
                if candidate.domain == "patent"
            ),
            key=lambda candidate: candidate.canonical_identity_id,
        ):
            decision = self._evaluate_manifest_membership(
                context,
                candidate,
                exclusion_code="outside_patent_export_scope",
            )
            decisions.append(decision)
            by_identity[candidate.canonical_identity_id] = decision

        for candidate in sorted(
            (
                candidate
                for candidate in request.candidates
                if candidate.domain == "company"
            ),
            key=lambda candidate: candidate.canonical_identity_id,
        ):
            if context.candidate_in_approved_scope(candidate):
                decision = context.policy_decision(candidate, PolicyOutcome.admitted)
            else:
                decision = self._evaluate_incremental_company(context, candidate)
            decisions.append(decision)
            by_identity[candidate.canonical_identity_id] = decision

        decisions_tuple = tuple(
            sorted(decisions, key=lambda item: item.subject_identity_id)
        )
        admitted = _empty_domain_map()
        review = _empty_domain_map()
        excluded = _empty_domain_map()
        candidate_domain: dict[str, Domain] = {
            candidate.canonical_identity_id: cast(Domain, candidate.domain)
            for candidate in request.candidates
        }
        for decision in decisions_tuple:
            domain = candidate_domain[decision.subject_identity_id]
            if decision.outcome is PolicyOutcome.admitted:
                admitted[domain].append(decision.subject_identity_id)
            elif decision.outcome is PolicyOutcome.review:
                review[domain].append(decision.subject_identity_id)
            elif decision.outcome is PolicyOutcome.excluded:
                excluded[domain].append(decision.subject_identity_id)

        content: dict[str, Any] = {
            "release_id": request.release_id,
            "decision_run_id": request.decision_run_id,
            "evaluated_at": request.evaluated_at,
            "approved_source_scope_manifest_sha256": (
                request.approved_source_scope_manifest.content_sha256
            ),
            "policy_decisions": decisions_tuple,
            "admitted_identity_ids_by_domain": _freeze_domain_map(admitted),
            "review_identity_ids_by_domain": _freeze_domain_map(review),
            "excluded_identity_ids_by_domain": _freeze_domain_map(excluded),
        }
        hash_payload = DomainInclusionResult.model_construct(
            **content,
            content_sha256="0" * 64,
        ).model_dump(mode="json", exclude={"content_sha256"})
        return DomainInclusionResult(
            **content,
            content_sha256=_canonical_sha256(cast(JsonValue, hash_payload)),
        )

    @staticmethod
    def _evaluate_manifest_membership(
        context: _ValidatedBatch,
        candidate: InclusionCandidate,
        *,
        exclusion_code: str,
    ) -> PolicyDecision:
        if context.candidate_in_approved_scope(candidate):
            return context.policy_decision(candidate, PolicyOutcome.admitted)
        return context.policy_decision(
            candidate,
            PolicyOutcome.excluded,
            hard_exclusion_codes=(exclusion_code,),
        )

    @staticmethod
    def _evaluate_incremental_company(
        context: _ValidatedBatch,
        candidate: InclusionCandidate,
    ) -> PolicyDecision:
        decision_id = candidate.incremental_company_validation_decision_id
        if decision_id is None:
            return context.policy_decision(
                candidate,
                PolicyOutcome.excluded,
                hard_exclusion_codes=("outside_company_inclusion_scope",),
            )
        validation = context.company_validations.get(decision_id)
        if (
            validation is None
            or validation.company_identity_id != candidate.canonical_identity_id
        ):
            raise DomainInclusionIntegrityError(
                "incremental Company validation decision does not match its candidate"
            )
        dimensions = {item.dimension: item for item in validation.dimensions}
        if any(item.outcome == "contradicted" for item in dimensions.values()):
            return context.policy_decision(
                candidate,
                PolicyOutcome.excluded,
                hard_exclusion_codes=("outside_company_inclusion_scope",),
            )
        if set(dimensions) != _COMPANY_DIMENSIONS or any(
            item.outcome != "supported" for item in dimensions.values()
        ):
            return context.policy_decision(
                candidate,
                PolicyOutcome.review,
                limitations=("incremental_company_validation_incomplete",),
            )
        return context.policy_decision(candidate, PolicyOutcome.admitted)


def _empty_domain_map() -> dict[Domain, list[str]]:
    return {domain: [] for domain in DOMAINS}


def _freeze_domain_map(
    value: dict[Domain, list[str]],
) -> dict[Domain, tuple[str, ...]]:
    return {domain: tuple(sorted(value[domain])) for domain in DOMAINS}


def create_domain_inclusion_result(
    *,
    release_id: str,
    decision_run_id: str,
    evaluated_at: datetime,
    approved_source_scope_manifest_sha256: str,
    policy_decisions: tuple[PolicyDecision, ...],
    identity_domains: Mapping[str, Domain],
) -> DomainInclusionResult:
    """Content-bind an already evaluated, four-domain inclusion decision set."""

    decisions = tuple(
        sorted(policy_decisions, key=lambda item: item.subject_identity_id)
    )
    subjects = {decision.subject_identity_id for decision in decisions}
    if subjects != set(identity_domains):
        raise DomainInclusionIntegrityError(
            "identity domain mapping must exactly cover inclusion decisions"
        )
    admitted = _empty_domain_map()
    review = _empty_domain_map()
    excluded = _empty_domain_map()
    outcome_maps = {
        PolicyOutcome.admitted: admitted,
        PolicyOutcome.review: review,
        PolicyOutcome.excluded: excluded,
    }
    for decision in decisions:
        domain = identity_domains[decision.subject_identity_id]
        try:
            outcome_maps[decision.outcome][domain].append(decision.subject_identity_id)
        except KeyError as exc:
            raise DomainInclusionIntegrityError(
                "limited is not a canonical inclusion outcome"
            ) from exc
    content: dict[str, Any] = {
        "release_id": release_id,
        "decision_run_id": decision_run_id,
        "evaluated_at": evaluated_at,
        "approved_source_scope_manifest_sha256": (
            approved_source_scope_manifest_sha256
        ),
        "policy_decisions": decisions,
        "admitted_identity_ids_by_domain": _freeze_domain_map(admitted),
        "review_identity_ids_by_domain": _freeze_domain_map(review),
        "excluded_identity_ids_by_domain": _freeze_domain_map(excluded),
    }
    provisional = DomainInclusionResult.model_construct(
        **content,
        content_sha256="0" * 64,
    )
    payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"content_sha256"}),
    )
    return DomainInclusionResult(
        **content,
        content_sha256=_canonical_sha256(payload),
    )


class _ValidatedBatch:
    def __init__(self, request: InclusionBatchRequest) -> None:
        self.request = request
        self.policies = self._validate_policies()
        self.artifacts = self._index_unique(
            request.evidence_artifacts, "artifact_id", "evidence artifacts"
        )
        self.records = self._index_unique(
            request.source_records, "record_id", "source records"
        )
        self.source_identities = self._index_unique(
            request.source_identities, "source_identity_id", "source identities"
        )
        self.canonical_identities = self._index_unique(
            request.canonical_identities,
            "canonical_identity_id",
            "canonical identities",
        )
        self.assertions = self._index_unique(
            request.source_assertions, "assertion_id", "source assertions"
        )
        self.candidates = self._index_unique(
            request.candidates,
            "canonical_identity_id",
            "inclusion candidates",
        )
        self.company_validations = self._index_unique(
            request.incremental_company_validation_decisions,
            "decision_id",
            "incremental Company validation decisions",
        )
        self.approved_batches = {
            (
                batch.domain,
                batch.scope_kind,
                batch.source_batch_id,
                batch.artifact_id,
            ): batch
            for batch in request.approved_source_scope_manifest.approved_batches
        }
        self._validate_manifest_artifacts()
        self._validate_graph()

    @staticmethod
    def _index_unique(
        values: Iterable[Any], attribute: str, label: str
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for value in values:
            key = cast(str, getattr(value, attribute))
            if key in result:
                raise DomainInclusionIntegrityError(f"duplicate {label}: {key}")
            result[key] = value
        return result

    def _validate_policies(self) -> dict[Domain, PolicyReference]:
        policies: dict[Domain, PolicyReference] = {}
        for policy in self.request.policies:
            if policy.policy_kind is not PolicyKind.inclusion:
                raise DomainInclusionIntegrityError(
                    "domain inclusion request accepts only inclusion policies"
                )
            domain = _policy_domain(policy)
            if domain in policies:
                raise DomainInclusionIntegrityError(
                    f"duplicate domain inclusion policy: {domain}"
                )
            if policy.effective_at > self.request.evaluated_at:
                raise DomainInclusionIntegrityError(
                    f"domain inclusion policy is not yet effective: {domain}"
                )
            policies[domain] = policy
        if set(policies) != set(DOMAINS):
            raise DomainInclusionIntegrityError(
                "domain inclusion request requires exactly four domain policies"
            )
        return policies

    def _validate_manifest_artifacts(self) -> None:
        for batch in self.request.approved_source_scope_manifest.approved_batches:
            artifact = self.artifacts.get(batch.artifact_id)
            if artifact is None:
                raise DomainInclusionIntegrityError(
                    f"approved artifact is missing: {batch.artifact_id}"
                )
            if artifact.content_sha256 != batch.artifact_content_sha256:
                raise DomainInclusionIntegrityError(
                    "approved artifact content hash does not match source-scope manifest"
                )

    def _validate_graph(self) -> None:
        for record in self.records.values():
            if record.artifact_id not in self.artifacts:
                raise DomainInclusionIntegrityError(
                    f"source record references missing artifact: {record.record_id}"
                )
        for source_identity in self.source_identities.values():
            if source_identity.state is not SourceIdentityState.active:
                raise DomainInclusionIntegrityError(
                    "inclusion accepts only active source identities"
                )
            if not set(source_identity.source_record_ids) <= set(self.records):
                raise DomainInclusionIntegrityError(
                    f"source identity references missing records: {source_identity.source_identity_id}"
                )
        for canonical_identity in self.canonical_identities.values():
            if canonical_identity.release_id != self.request.release_id:
                raise DomainInclusionIntegrityError(
                    "canonical identity release does not match inclusion release"
                )
            if canonical_identity.state is not CanonicalIdentityState.active:
                raise DomainInclusionIntegrityError(
                    "inclusion accepts only active canonical identities"
                )
            if not set(canonical_identity.source_identity_ids) <= set(
                self.source_identities
            ):
                raise DomainInclusionIntegrityError(
                    "canonical identity references missing source identities"
                )
        for assertion in self.assertions.values():
            source_identity = self.source_identities.get(assertion.source_identity_id)
            if source_identity is None:
                raise DomainInclusionIntegrityError(
                    f"assertion references missing source identity: {assertion.assertion_id}"
                )
            if assertion.source_record_id not in source_identity.source_record_ids:
                raise DomainInclusionIntegrityError(
                    "assertion source record is not owned by its source identity"
                )
            if assertion.subject_entity_type != source_identity.entity_type:
                raise DomainInclusionIntegrityError(
                    "assertion entity type does not match its source identity"
                )
        for candidate in self.candidates.values():
            identity = self.canonical_identities.get(candidate.canonical_identity_id)
            if identity is None:
                raise DomainInclusionIntegrityError(
                    f"candidate references missing canonical identity: {candidate.canonical_identity_id}"
                )
            if identity.entity_type != candidate.domain:
                raise DomainInclusionIntegrityError(
                    "candidate domain does not match canonical identity entity type"
                )
            if set(candidate.source_identity_ids) != set(identity.source_identity_ids):
                raise DomainInclusionIntegrityError(
                    "candidate source identities do not match canonical identity ownership"
                )
            if not set(candidate.source_record_ids) <= set(self.records):
                raise DomainInclusionIntegrityError(
                    "candidate references missing source records"
                )
            if not set(candidate.supporting_assertion_ids) <= set(self.assertions):
                raise DomainInclusionIntegrityError(
                    "candidate references missing supporting assertions"
                )
            for assertion in self.candidate_assertions(candidate):
                if assertion.source_identity_id not in candidate.source_identity_ids:
                    raise DomainInclusionIntegrityError(
                        "candidate assertion belongs to another source identity"
                    )
                if assertion.source_record_id not in candidate.source_record_ids:
                    raise DomainInclusionIntegrityError(
                        "candidate assertion record is outside the candidate records"
                    )
            validation_id = candidate.incremental_company_validation_decision_id
            if validation_id is not None:
                validation = self.company_validations.get(validation_id)
                if (
                    validation is None
                    or validation.company_identity_id != candidate.canonical_identity_id
                ):
                    raise DomainInclusionIntegrityError(
                        "incremental Company validation decision does not match "
                        "its candidate"
                    )
                validation_assertion_ids = {
                    assertion_id
                    for dimension in validation.dimensions
                    for assertion_id in dimension.supporting_assertion_ids
                }
                if not validation_assertion_ids <= set(
                    candidate.supporting_assertion_ids
                ):
                    raise DomainInclusionIntegrityError(
                        "incremental Company validation evidence must be among "
                        "the candidate supporting assertions"
                    )
        referenced_validations = {
            candidate.incremental_company_validation_decision_id
            for candidate in self.candidates.values()
            if candidate.incremental_company_validation_decision_id is not None
        }
        if referenced_validations != set(self.company_validations):
            raise DomainInclusionIntegrityError(
                "incremental Company validations must be referenced exactly once "
                "by their candidates"
            )
        for identity_id in self.request.included_professor_identity_ids:
            identity = self.canonical_identities.get(identity_id)
            if identity is None or identity.entity_type != "professor":
                raise DomainInclusionIntegrityError(
                    "included Professor anchor must reference a Professor identity"
                )
        for validation in self.company_validations.values():
            if validation.policy != self.policies["company"]:
                raise DomainInclusionIntegrityError(
                    "incremental Company validation uses the wrong inclusion policy"
                )
            if validation.decided_at > self.request.evaluated_at:
                raise DomainInclusionIntegrityError(
                    "incremental Company validation is from the future"
                )
            assertion_ids = {
                assertion_id
                for dimension in validation.dimensions
                for assertion_id in dimension.supporting_assertion_ids
            }
            if not assertion_ids <= set(self.assertions):
                raise DomainInclusionIntegrityError(
                    "incremental Company validation references missing assertions"
                )

    def candidate_assertions(
        self, candidate: InclusionCandidate
    ) -> tuple[SourceAssertion, ...]:
        return tuple(
            self.assertions[assertion_id]
            for assertion_id in candidate.supporting_assertion_ids
        )

    def candidate_in_approved_scope(self, candidate: InclusionCandidate) -> bool:
        expected_scope = _SCOPE_BY_DOMAIN[candidate.domain]
        for assertion in self.candidate_assertions(candidate):
            record = self.records[assertion.source_record_id]
            key = (
                candidate.domain,
                expected_scope,
                record.source_batch_id,
                record.artifact_id,
            )
            if key in self.approved_batches:
                return True
        return False

    def policy_decision(
        self,
        candidate: InclusionCandidate,
        outcome: PolicyOutcome,
        *,
        limitations: tuple[str, ...] = (),
        hard_exclusion_codes: tuple[str, ...] = (),
    ) -> PolicyDecision:
        policy = self.policies[candidate.domain]
        return PolicyDecision(
            decision_id=_decision_id(
                request=self.request,
                candidate=candidate,
                policy=policy,
                outcome=outcome,
                limitations=limitations,
                hard_exclusion_codes=hard_exclusion_codes,
            ),
            policy=policy,
            subject_identity_id=candidate.canonical_identity_id,
            release_id=self.request.release_id,
            path=None,
            outcome=outcome,
            score=None,
            limitations=limitations,
            hard_exclusion_codes=hard_exclusion_codes,
            supporting_assertion_ids=candidate.supporting_assertion_ids,
            evaluated_at=self.request.evaluated_at,
        )


def create_ephemeral_domain_inclusion_engine() -> DomainInclusionEngine:
    """Return the pure in-process adapter used by offline builds and tests."""

    return DomainInclusionEngine()


__all__ = [
    "ApprovedSourceBatch",
    "ApprovedSourceScopeManifest",
    "CompanyValidationDimension",
    "DomainInclusionEngine",
    "DomainInclusionIntegrityError",
    "DomainInclusionResult",
    "InclusionBatchRequest",
    "InclusionCandidate",
    "IncrementalCompanyValidationDecision",
    "PolicyDecision",
    "PolicyReference",
    "create_approved_source_scope_manifest",
    "create_domain_inclusion_result",
    "create_ephemeral_domain_inclusion_engine",
    "create_incremental_company_validation_decision",
]
