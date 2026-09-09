"""Installed immutable domain catalog for Canonical V2 product code.

The source-of-truth evidence used to approve the catalog lives outside the
runtime package.  Product code consumes this packaged, content-addressed copy
and refuses startup when its identity or bytes drift.
"""

from __future__ import annotations

import hashlib
from importlib import import_module
from importlib.resources import files
import json
from typing import TYPE_CHECKING, Any, cast

from pydantic import Field, JsonValue, model_validator

from .contracts import ContractModel, NonEmptyStr, Sha256

if TYPE_CHECKING:
    from .internal_reference_catalog import (
        PACKAGED_REFERENCE_CATALOG,
        REFERENCE_CATALOG_CONTENT_SHA256,
        REFERENCE_CATALOG_FILE_SHA256,
        REFERENCE_CATALOG_RESOURCE,
        REFERENCE_CATALOG_SCHEMA_VERSION,
        REFERENCE_CATALOG_VERSION,
        InstalledInternalReferenceCatalog,
        InternalReferenceTypeDefinition,
        ReferenceRelationshipTypeDefinition,
    )


CATALOG_RESOURCE = "catalogs/domain-catalog-v1.json"
CATALOG_SCHEMA_VERSION = "canonical-v2-domain-catalog-v1"
CATALOG_VERSION = "canonical-v2-prd-catalog-2026-07-12"
CATALOG_CONTENT_SHA256 = (
    "26ec3ad046207665051ab7886fcef8fda748f331bddff69de486e90930b3398d"
)
CATALOG_FILE_SHA256 = "7c7d52009b2e963e191189f33d260e44dbd6ddc5c0c722e28127b929cc583809"


def _reject_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate catalog key: {key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite catalog value is forbidden: {value}")


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


class CatalogFieldDefinition(ContractModel):
    catalog_item_id: NonEmptyStr
    field_path: NonEmptyStr
    value_shape: NonEmptyStr
    cardinality: NonEmptyStr
    requiredness: NonEmptyStr
    requiredness_scope: NonEmptyStr
    temporal_class: NonEmptyStr
    semantic_use: NonEmptyStr
    evidence_obligation: NonEmptyStr
    citation_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)


class CatalogSubobjectMember(ContractModel):
    member_name: NonEmptyStr
    value_shape: NonEmptyStr
    required: bool


class CatalogSubobjectDefinition(ContractModel):
    catalog_item_id: NonEmptyStr
    parent_domain: NonEmptyStr
    subobject_type: NonEmptyStr
    identity_key: NonEmptyStr
    cardinality: NonEmptyStr
    temporal_class: NonEmptyStr
    evidence_obligation: NonEmptyStr
    citation_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    members: tuple[CatalogSubobjectMember, ...] = Field(min_length=1)


class CatalogDomainDefinition(ContractModel):
    domain: NonEmptyStr
    fields: tuple[CatalogFieldDefinition, ...] = Field(min_length=1)
    subobjects: tuple[CatalogSubobjectDefinition, ...] = Field(min_length=1)


class InstalledDomainCatalog(ContractModel):
    schema_version: NonEmptyStr
    catalog_version: NonEmptyStr
    content_sha256: Sha256
    file_sha256: Sha256
    domains: tuple[CatalogDomainDefinition, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_complete_catalog(self) -> InstalledDomainCatalog:
        domain_names = tuple(domain.domain for domain in self.domains)
        if domain_names != ("company", "paper", "patent", "professor"):
            raise ValueError("installed catalog must contain the four ordered domains")
        if sum(len(domain.fields) for domain in self.domains) != 101:
            raise ValueError("installed catalog must contain all 101 domain fields")
        if sum(len(domain.subobjects) for domain in self.domains) != 28:
            raise ValueError("installed catalog must contain all 28 sub-object types")
        return self


def _load_packaged_catalog() -> InstalledDomainCatalog:
    raw_bytes = files(__package__).joinpath(CATALOG_RESOURCE).read_bytes()
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if file_sha256 != CATALOG_FILE_SHA256:
        raise RuntimeError("packaged domain catalog file hash mismatch")
    value = json.loads(
        raw_bytes.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_finite,
    )
    if not isinstance(value, dict):
        raise RuntimeError("packaged domain catalog must be a JSON object")
    payload = cast(dict[str, Any], value)
    hash_payload = dict(payload)
    claimed_content_sha256 = hash_payload.pop("content_sha256", None)
    computed_content_sha256 = hashlib.sha256(
        _canonical_catalog_bytes(hash_payload)
    ).hexdigest()
    if claimed_content_sha256 != computed_content_sha256:
        raise RuntimeError("packaged domain catalog content hash mismatch")
    identity = (
        payload.get("schema_version"),
        payload.get("catalog_version"),
        claimed_content_sha256,
    )
    expected_identity = (
        CATALOG_SCHEMA_VERSION,
        CATALOG_VERSION,
        CATALOG_CONTENT_SHA256,
    )
    if identity != expected_identity:
        raise RuntimeError("packaged domain catalog identity mismatch")
    return InstalledDomainCatalog.model_validate(
        {
            "schema_version": payload["schema_version"],
            "catalog_version": payload["catalog_version"],
            "content_sha256": claimed_content_sha256,
            "file_sha256": file_sha256,
            "domains": payload["domains"],
        }
    )


PACKAGED_CATALOG = _load_packaged_catalog()


_REFERENCE_CATALOG_EXPORTS = frozenset(
    {
        "InstalledInternalReferenceCatalog",
        "InternalReferenceTypeDefinition",
        "PACKAGED_REFERENCE_CATALOG",
        "REFERENCE_CATALOG_CONTENT_SHA256",
        "REFERENCE_CATALOG_FILE_SHA256",
        "REFERENCE_CATALOG_RESOURCE",
        "REFERENCE_CATALOG_SCHEMA_VERSION",
        "REFERENCE_CATALOG_VERSION",
        "ReferenceRelationshipTypeDefinition",
    }
)


def __getattr__(name: str) -> Any:
    """Lazily expose additive reference knowledge without coupling v1 imports."""
    if name not in _REFERENCE_CATALOG_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(".internal_reference_catalog", package=__package__)
    for export_name in _REFERENCE_CATALOG_EXPORTS:
        globals()[export_name] = getattr(module, export_name)
    return globals()[name]


def __dir__() -> list[str]:
    return sorted({*globals(), *_REFERENCE_CATALOG_EXPORTS})


__all__ = [
    "CATALOG_CONTENT_SHA256",
    "CATALOG_FILE_SHA256",
    "CATALOG_SCHEMA_VERSION",
    "CATALOG_VERSION",
    "CatalogDomainDefinition",
    "CatalogFieldDefinition",
    "CatalogSubobjectDefinition",
    "CatalogSubobjectMember",
    "InstalledDomainCatalog",
    "InstalledInternalReferenceCatalog",
    "InternalReferenceTypeDefinition",
    "PACKAGED_CATALOG",
    "PACKAGED_REFERENCE_CATALOG",
    "REFERENCE_CATALOG_CONTENT_SHA256",
    "REFERENCE_CATALOG_FILE_SHA256",
    "REFERENCE_CATALOG_RESOURCE",
    "REFERENCE_CATALOG_SCHEMA_VERSION",
    "REFERENCE_CATALOG_VERSION",
    "ReferenceRelationshipTypeDefinition",
]
