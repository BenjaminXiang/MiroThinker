"""Compose release-scoped typed projections without persistence or publication."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, cast

from pydantic import Field, JsonValue, ValidationError, model_validator

from .contracts import (
    CanonicalDatetime,
    ContractModel,
    NonEmptyStr,
    ProjectionManifest,
    ProjectionScope,
    Sha256,
)
from .domain_projection import DomainProjectionResult
from .domain_projection_models import (
    CompanyProjection,
    PaperProjection,
    PatentProjection,
    ProfessorProjection,
)
from .internal_reference_projection import (
    PERSON_REFERENCE_PROJECTION_VERSION,
    TECHNOLOGY_CONCEPT_PROJECTION_VERSION,
    TECHNOLOGY_ROUTE_PROJECTION_VERSION,
    InternalReferenceProjectionIntegrityError,
    InternalReferenceProjectionRequest,
    InternalReferenceProjectionResult,
    PersonProjection,
    TechnologyConceptProjection,
    TechnologyRouteProjection,
    validate_internal_reference_projection_result,
)


CANDIDATE_PROJECTION_SCHEMA_VERSION = "canonical-v2-candidate-projection-v1"
_PUBLIC_DOMAINS = ("company", "paper", "patent", "professor")
_INTERNAL_REFERENCE_TYPES = (
    "person",
    "technology_concept",
    "technology_route",
)

PublicDomainProjection = (
    CompanyProjection | PaperProjection | PatentProjection | ProfessorProjection
)


class CandidateProjectionIntegrityError(ValueError):
    """Candidate projection inputs cannot reproduce one closed release graph."""


class CandidateProjectionRequest(ContractModel):
    """Exact S6R request/result pair to compose for one candidate release."""

    release_id: NonEmptyStr
    build_run_id: NonEmptyStr
    as_of: CanonicalDatetime
    projection_schema_version: Literal["canonical-v2-candidate-projection-v1"] = (
        CANDIDATE_PROJECTION_SCHEMA_VERSION
    )
    internal_reference_projection_request: InternalReferenceProjectionRequest
    internal_reference_projection_result: InternalReferenceProjectionResult

    @model_validator(mode="after")
    def validate_one_candidate_release(self) -> CandidateProjectionRequest:
        internal_request = self.internal_reference_projection_request
        internal_result = self.internal_reference_projection_result
        public_request = internal_request.public_domain_projection_request
        public_result = internal_request.public_domain_projection_result
        if any(
            release_id != self.release_id
            for release_id in (
                internal_request.release_id,
                internal_result.release_id,
                public_request.release_id,
                public_result.release_id,
            )
        ):
            raise ValueError(
                "candidate projections must identify one candidate release"
            )
        if (
            internal_request.build_run_id != self.build_run_id
            or internal_result.build_run_id != self.build_run_id
        ):
            raise ValueError("candidate projections must identify one build run")
        if any(
            value != self.as_of
            for value in (
                internal_request.as_of,
                internal_result.as_of,
                public_request.as_of,
                public_result.as_of,
            )
        ):
            raise ValueError("candidate projections must identify one as_of")
        if (
            internal_result.public_domain_projection_result_content_sha256
            != public_result.content_sha256
        ):
            raise ValueError(
                "internal references must bind the exact public projection result"
            )
        return self


def _canonical_sha256(value: JsonValue) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_identity(
    record: PublicDomainProjection
    | PersonProjection
    | TechnologyConceptProjection
    | TechnologyRouteProjection,
) -> str:
    if isinstance(record, PersonProjection):
        return record.canonical_person_identity_id
    if isinstance(record, (TechnologyConceptProjection, TechnologyRouteProjection)):
        return record.canonical_technology_identity_id
    return record.canonical_identity_id


def _projection_manifest(
    *,
    release_id: str,
    owner: str,
    projection_scope: ProjectionScope,
    projection_kind: str,
    projection_version: str,
    records: tuple[
        PublicDomainProjection
        | PersonProjection
        | TechnologyConceptProjection
        | TechnologyRouteProjection,
        ...,
    ],
) -> ProjectionManifest:
    domain = cast(
        Literal["company", "paper", "patent", "professor"] | None,
        owner if projection_scope is ProjectionScope.public_domain else None,
    )
    reference_type = cast(
        Literal["person", "technology_concept", "technology_route"] | None,
        owner if projection_scope is ProjectionScope.internal_auxiliary else None,
    )
    content_sha256 = _canonical_sha256(
        {
            "projection_id": f"published:{owner}",
            "release_id": release_id,
            "projection_scope": projection_scope.value,
            "domain": domain,
            "reference_type": reference_type,
            "projection_kind": projection_kind,
            "path": None,
            "projection_version": projection_version,
            "records": [
                {
                    "identity_id": _record_identity(record),
                    "content_sha256": record.content_sha256,
                }
                for record in records
            ],
        }
    )
    return ProjectionManifest(
        projection_id=f"published:{owner}",
        release_id=release_id,
        projection_scope=projection_scope,
        projection_kind=projection_kind,
        domain=domain,
        reference_type=reference_type,
        path=None,
        projection_version=projection_version,
        record_count=len(records),
        content_sha256=content_sha256,
    )


def _published_projection_manifests(
    *,
    release_id: str,
    public_projection_version: str,
    public_domain_projections: tuple[PublicDomainProjection, ...],
    person_projections: tuple[PersonProjection, ...],
    technology_concept_projections: tuple[TechnologyConceptProjection, ...],
    technology_route_projections: tuple[TechnologyRouteProjection, ...],
) -> tuple[ProjectionManifest, ...]:
    public_by_domain = {
        domain: tuple(
            projection
            for projection in public_domain_projections
            if projection.entity_type == domain
        )
        for domain in _PUBLIC_DOMAINS
    }
    internal_by_type = {
        "person": person_projections,
        "technology_concept": technology_concept_projections,
        "technology_route": technology_route_projections,
    }
    public_manifests = tuple(
        _projection_manifest(
            release_id=release_id,
            owner=domain,
            projection_scope=ProjectionScope.public_domain,
            projection_kind="typed_current",
            projection_version=public_projection_version,
            records=public_by_domain[domain],
        )
        for domain in _PUBLIC_DOMAINS
    )
    internal_versions = {
        "person": PERSON_REFERENCE_PROJECTION_VERSION,
        "technology_concept": TECHNOLOGY_CONCEPT_PROJECTION_VERSION,
        "technology_route": TECHNOLOGY_ROUTE_PROJECTION_VERSION,
    }
    internal_manifests = tuple(
        _projection_manifest(
            release_id=release_id,
            owner=reference_type,
            projection_scope=ProjectionScope.internal_auxiliary,
            projection_kind="internal_reference",
            projection_version=internal_versions[reference_type],
            records=internal_by_type[reference_type],
        )
        for reference_type in _INTERNAL_REFERENCE_TYPES
    )
    return (*public_manifests, *internal_manifests)


class CandidateProjectionResult(ContractModel):
    """Typed public/internal populations and their exact owner-local manifests."""

    release_id: NonEmptyStr
    build_run_id: NonEmptyStr
    as_of: CanonicalDatetime
    projection_schema_version: Literal["canonical-v2-candidate-projection-v1"] = (
        CANDIDATE_PROJECTION_SCHEMA_VERSION
    )
    public_domain_projection_version: NonEmptyStr
    public_domain_projection_result_content_sha256: Sha256
    internal_reference_projection_result_content_sha256: Sha256
    public_domain_projections: tuple[PublicDomainProjection, ...]
    person_projections: tuple[PersonProjection, ...]
    technology_concept_projections: tuple[TechnologyConceptProjection, ...]
    technology_route_projections: tuple[TechnologyRouteProjection, ...]
    published_projections: tuple[ProjectionManifest, ...] = Field(
        min_length=7,
        max_length=7,
    )
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_projection_bundle(self) -> CandidateProjectionResult:
        public_keys = tuple(
            (projection.entity_type, projection.canonical_identity_id)
            for projection in self.public_domain_projections
        )
        if public_keys != tuple(sorted(public_keys)) or len(public_keys) != len(
            set(public_keys)
        ):
            raise ValueError("public domain projections must be sorted and unique")
        if any(
            projection.release_id != self.release_id
            or projection.as_of != self.as_of
            or projection.projection_version != self.public_domain_projection_version
            for projection in self.public_domain_projections
        ):
            raise ValueError(
                "public domain projections differ from the bundle envelope"
            )
        internal_groups = (
            self.person_projections,
            self.technology_concept_projections,
            self.technology_route_projections,
        )
        internal_keys = (
            tuple(
                projection.canonical_person_identity_id
                for projection in self.person_projections
            ),
            tuple(
                projection.canonical_technology_identity_id
                for projection in self.technology_concept_projections
            ),
            tuple(
                projection.canonical_technology_identity_id
                for projection in self.technology_route_projections
            ),
        )
        if any(keys != tuple(sorted(set(keys))) for keys in internal_keys):
            raise ValueError(
                "internal projection populations must be sorted and unique"
            )
        if any(
            projection.release_id != self.release_id or projection.as_of != self.as_of
            for group in internal_groups
            for projection in group
        ):
            raise ValueError("internal projections differ from the bundle envelope")
        expected_manifests = _published_projection_manifests(
            release_id=self.release_id,
            public_projection_version=self.public_domain_projection_version,
            public_domain_projections=self.public_domain_projections,
            person_projections=self.person_projections,
            technology_concept_projections=self.technology_concept_projections,
            technology_route_projections=self.technology_route_projections,
        )
        if self.published_projections != expected_manifests:
            raise ValueError(
                "published projection manifests must exactly bind their typed records"
            )
        payload = cast(
            JsonValue,
            self.model_dump(mode="json", exclude={"content_sha256"}),
        )
        if self.content_sha256 != _canonical_sha256(payload):
            raise ValueError("content_sha256 must bind the complete projection bundle")
        return self


def compose_candidate_projections(
    request: CandidateProjectionRequest,
) -> CandidateProjectionResult:
    """Replay one closed S6R graph and compose its seven projection populations."""

    try:
        validated_request = CandidateProjectionRequest.model_validate(
            request.model_dump(mode="python")
        )
        internal_result = validate_internal_reference_projection_result(
            validated_request.internal_reference_projection_request,
            validated_request.internal_reference_projection_result,
        )
    except (
        AttributeError,
        InternalReferenceProjectionIntegrityError,
        ValidationError,
        ValueError,
    ) as exc:
        raise CandidateProjectionIntegrityError(
            "candidate projection inputs failed exact replay"
        ) from exc

    public_result: DomainProjectionResult = validated_request.internal_reference_projection_request.public_domain_projection_result
    public_projections = tuple(public_result.projections)
    published_projections = _published_projection_manifests(
        release_id=validated_request.release_id,
        public_projection_version=public_result.projection_version,
        public_domain_projections=public_projections,
        person_projections=internal_result.person_projections,
        technology_concept_projections=(internal_result.technology_concept_projections),
        technology_route_projections=internal_result.technology_route_projections,
    )
    content = {
        "release_id": validated_request.release_id,
        "build_run_id": validated_request.build_run_id,
        "as_of": validated_request.as_of,
        "projection_schema_version": validated_request.projection_schema_version,
        "public_domain_projection_version": public_result.projection_version,
        "public_domain_projection_result_content_sha256": (
            public_result.content_sha256
        ),
        "internal_reference_projection_result_content_sha256": (
            internal_result.content_sha256
        ),
        "public_domain_projections": public_projections,
        "person_projections": internal_result.person_projections,
        "technology_concept_projections": (
            internal_result.technology_concept_projections
        ),
        "technology_route_projections": internal_result.technology_route_projections,
        "published_projections": published_projections,
    }
    provisional = CandidateProjectionResult.model_construct(
        **content,
        content_sha256="0" * 64,
    )
    payload = cast(
        JsonValue,
        provisional.model_dump(mode="json", exclude={"content_sha256"}),
    )
    return CandidateProjectionResult(
        **content,
        content_sha256=_canonical_sha256(payload),
    )


__all__ = [
    "CANDIDATE_PROJECTION_SCHEMA_VERSION",
    "CandidateProjectionIntegrityError",
    "CandidateProjectionRequest",
    "CandidateProjectionResult",
    "compose_candidate_projections",
]
