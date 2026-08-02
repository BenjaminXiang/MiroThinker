"""Installed additive Person/Technology reference catalog for Canonical V2."""

from __future__ import annotations

import hashlib
from importlib.resources import files
import json
from typing import Any, Literal, cast

from pydantic import Field, JsonValue, model_validator

from .contracts import ContractModel, NonEmptyStr, Sha256


REFERENCE_CATALOG_RESOURCE = "catalogs/internal-reference-catalog-v1.json"
REFERENCE_CATALOG_SCHEMA_VERSION = "canonical-v2-reference-catalog-v1"
REFERENCE_CATALOG_VERSION = "canonical-v2-person-technology-reference-2026-07-13"
REFERENCE_CATALOG_CONTENT_SHA256 = (
    "f0b4c96aec3e26003823c50197718704d8357894ff44cbbd0281eb059b262f61"
)
REFERENCE_CATALOG_FILE_SHA256 = (
    "107ee75189cc7388099a77d7a90566b272e2fc1bb10315b43f5f431a91cb1473"
)
BASE_DOMAIN_CATALOG_CONTENT_SHA256 = (
    "26ec3ad046207665051ab7886fcef8fda748f331bddff69de486e90930b3398d"
)
BASE_DOMAIN_CATALOG_FILE_SHA256 = (
    "7c7d52009b2e963e191189f33d260e44dbd6ddc5c0c722e28127b929cc583809"
)
PUBLIC_DOMAIN_TYPES = ("company", "paper", "patent", "professor")
INTERNAL_REFERENCE_TYPES = ("person", "technology_concept", "technology_route")


def _reject_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate reference catalog key: {key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite reference catalog value is forbidden: {value}")


def _canonical_catalog_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


class BaseDomainCatalogIdentity(ContractModel):
    schema_version: Literal["canonical-v2-domain-catalog-v1"]
    catalog_version: Literal["canonical-v2-prd-catalog-2026-07-12"]
    content_sha256: Sha256
    file_sha256: Sha256

    @model_validator(mode="after")
    def validate_exact_historical_identity(self) -> BaseDomainCatalogIdentity:
        if self.content_sha256 != BASE_DOMAIN_CATALOG_CONTENT_SHA256:
            raise ValueError("base domain catalog content identity mismatch")
        if self.file_sha256 != BASE_DOMAIN_CATALOG_FILE_SHA256:
            raise ValueError("base domain catalog file identity mismatch")
        return self


class ReferenceCatalogCitation(ContractModel):
    citation_id: NonEmptyStr
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    source_terms: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> ReferenceCatalogCitation:
        if self.line_end < self.line_start:
            raise ValueError("reference catalog citation range is reversed")
        if len(self.source_terms) != len(set(self.source_terms)):
            raise ValueError("reference catalog source terms must be unique")
        return self


class ReferenceCatalogSource(ContractModel):
    path: NonEmptyStr
    sha256: Sha256
    citations: tuple[ReferenceCatalogCitation, ...] = Field(min_length=1)


class InternalReferenceTypeDefinition(ContractModel):
    reference_type: Literal["person", "technology_concept", "technology_route"]
    identity_entity_type: Literal["person", "technology_concept", "technology_route"]
    projection_schema_version: NonEmptyStr
    projection_scope: Literal["internal_auxiliary"]
    required_projection_fields: tuple[NonEmptyStr, ...] = Field(min_length=1)
    evidence_obligation: NonEmptyStr
    time_obligation: NonEmptyStr
    release_obligation: NonEmptyStr
    unresolved_policy: NonEmptyStr
    citation_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reference_identity(self) -> InternalReferenceTypeDefinition:
        if self.reference_type != self.identity_entity_type:
            raise ValueError("internal reference identity type mismatch")
        if len(self.required_projection_fields) != len(
            set(self.required_projection_fields)
        ):
            raise ValueError("internal reference projection fields must be unique")
        return self


class ReferenceRelationshipTypeDefinition(ContractModel):
    relationship_type_id: NonEmptyStr
    version: NonEmptyStr
    layer: Literal["canonical"]
    source_entity_types: tuple[NonEmptyStr, ...] = Field(min_length=1)
    target_entity_types: tuple[NonEmptyStr, ...] = Field(min_length=1)
    direction: Literal["directed"]
    role_id: NonEmptyStr
    required_evidence_kinds: tuple[NonEmptyStr, ...] = Field(min_length=1)
    time_semantics: Literal["none", "observed_at", "validity_interval"]
    eligible_paths: tuple[NonEmptyStr, ...] = Field(min_length=1)
    endpoint_binding: NonEmptyStr
    semantic_state: NonEmptyStr
    predecessor_version: NonEmptyStr | None
    version_coexistence: Literal["required", "not_applicable"]
    resolved_person_reference_required: bool
    unresolved_reference_not_canonical_endpoint: bool
    does_not_entail_product_capability: bool
    citation_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)


class InstalledInternalReferenceCatalog(ContractModel):
    schema_version: Literal["canonical-v2-reference-catalog-v1"]
    catalog_version: Literal["canonical-v2-person-technology-reference-2026-07-13"]
    status: Literal["frozen"]
    base_domain_catalog: BaseDomainCatalogIdentity
    public_domain_types: tuple[
        Literal["company", "paper", "patent", "professor"], ...
    ] = Field(min_length=4, max_length=4)
    internal_reference_types: tuple[InternalReferenceTypeDefinition, ...] = Field(
        min_length=3,
        max_length=3,
    )
    relationship_types: tuple[ReferenceRelationshipTypeDefinition, ...] = Field(
        min_length=6,
        max_length=6,
    )
    source_manifest: tuple[ReferenceCatalogSource, ...] = Field(min_length=1)
    content_sha256: Sha256
    file_sha256: Sha256

    @model_validator(mode="after")
    def validate_frozen_boundaries(self) -> InstalledInternalReferenceCatalog:
        if self.public_domain_types != PUBLIC_DOMAIN_TYPES:
            raise ValueError(
                "reference catalog must retain four ordered public domains"
            )
        reference_names = tuple(
            item.reference_type for item in self.internal_reference_types
        )
        if reference_names != INTERNAL_REFERENCE_TYPES:
            raise ValueError("reference catalog internal types differ")
        relationship_keys = tuple(
            (item.relationship_type_id, item.version)
            for item in self.relationship_types
        )
        expected_keys = (
            ("company_has_team_member", "canonical-v2-relationship-v2"),
            ("paper_has_author", "canonical-v2-relationship-v2"),
            ("patent_has_inventor", "canonical-v2-relationship-v2"),
            (
                "entity_discusses_or_mentions_technology",
                "canonical-v2-relationship-v1",
            ),
            (
                "entity_claims_adoption_of_technology",
                "canonical-v2-relationship-v1",
            ),
            (
                "entity_demonstrates_use_of_technology",
                "canonical-v2-relationship-v1",
            ),
        )
        if relationship_keys != expected_keys:
            raise ValueError("reference catalog relationship versions differ")
        if self.relationship_types[3].semantic_state != "discussion_or_mention":
            raise ValueError("Technology discussion semantics differ")
        if self.relationship_types[4].semantic_state != "claimed_adoption":
            raise ValueError("Technology claimed-adoption semantics differ")
        if self.relationship_types[5].semantic_state != "demonstrated_use":
            raise ValueError("Technology demonstrated-use semantics differ")
        if any(
            item.relationship_type_id == "product_has_capability"
            for item in self.relationship_types
        ):
            raise ValueError("Product capability relationship is forbidden")
        if self.content_sha256 != REFERENCE_CATALOG_CONTENT_SHA256:
            raise ValueError("reference catalog content identity mismatch")
        if self.file_sha256 != REFERENCE_CATALOG_FILE_SHA256:
            raise ValueError("reference catalog file identity mismatch")
        return self


def _load_packaged_reference_catalog() -> InstalledInternalReferenceCatalog:
    raw_bytes = files(__package__).joinpath(REFERENCE_CATALOG_RESOURCE).read_bytes()
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if file_sha256 != REFERENCE_CATALOG_FILE_SHA256:
        raise RuntimeError("packaged reference catalog file hash mismatch")
    value = json.loads(
        raw_bytes.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_finite,
    )
    if not isinstance(value, dict):
        raise RuntimeError("packaged reference catalog must be a JSON object")
    payload = cast(dict[str, Any], value)
    hash_payload = dict(payload)
    claimed_content_sha256 = hash_payload.pop("content_sha256", None)
    computed_content_sha256 = hashlib.sha256(
        _canonical_catalog_bytes(hash_payload)
    ).hexdigest()
    if claimed_content_sha256 != computed_content_sha256:
        raise RuntimeError("packaged reference catalog content hash mismatch")
    identity = (
        payload.get("schema_version"),
        payload.get("catalog_version"),
        claimed_content_sha256,
    )
    expected_identity = (
        REFERENCE_CATALOG_SCHEMA_VERSION,
        REFERENCE_CATALOG_VERSION,
        REFERENCE_CATALOG_CONTENT_SHA256,
    )
    if identity != expected_identity:
        raise RuntimeError("packaged reference catalog identity mismatch")
    return InstalledInternalReferenceCatalog.model_validate(
        {
            **payload,
            "content_sha256": claimed_content_sha256,
            "file_sha256": file_sha256,
        }
    )


PACKAGED_REFERENCE_CATALOG = _load_packaged_reference_catalog()


__all__ = [
    "BASE_DOMAIN_CATALOG_CONTENT_SHA256",
    "BASE_DOMAIN_CATALOG_FILE_SHA256",
    "BaseDomainCatalogIdentity",
    "INTERNAL_REFERENCE_TYPES",
    "InstalledInternalReferenceCatalog",
    "InternalReferenceTypeDefinition",
    "PACKAGED_REFERENCE_CATALOG",
    "PUBLIC_DOMAIN_TYPES",
    "REFERENCE_CATALOG_CONTENT_SHA256",
    "REFERENCE_CATALOG_FILE_SHA256",
    "REFERENCE_CATALOG_RESOURCE",
    "REFERENCE_CATALOG_SCHEMA_VERSION",
    "REFERENCE_CATALOG_VERSION",
    "ReferenceCatalogCitation",
    "ReferenceCatalogSource",
    "ReferenceRelationshipTypeDefinition",
]
