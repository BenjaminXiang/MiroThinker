#!/usr/bin/env python3
"""Validate the additive Canonical V2 Person/Technology reference catalog."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast


SCHEMA_VERSION = "canonical-v2-reference-catalog-v1"
CATALOG_VERSION = "canonical-v2-person-technology-reference-2026-07-13"
BASE_DOMAIN_CATALOG = {
    "schema_version": "canonical-v2-domain-catalog-v1",
    "catalog_version": "canonical-v2-prd-catalog-2026-07-12",
    "content_sha256": "8ad9e719579b834f51128788f49d091913c0c90e3b047aac9b2f83cc794441d7",
    "file_sha256": "b227285fef5d49ad0b30871e5ccb0c1932443206fac99f5fa708ae586c5383c0",
}
PUBLIC_DOMAIN_TYPES = ("company", "paper", "patent", "professor")
INTERNAL_REFERENCE_TYPES = ("person", "technology_concept", "technology_route")
ROOT_KEYS = {
    "base_domain_catalog",
    "catalog_version",
    "content_sha256",
    "internal_reference_types",
    "public_domain_types",
    "relationship_types",
    "schema_version",
    "source_manifest",
    "status",
}
BASE_CATALOG_KEYS = {
    "catalog_version",
    "content_sha256",
    "file_sha256",
    "schema_version",
}
REFERENCE_KEYS = {
    "citation_ids",
    "evidence_obligation",
    "identity_entity_type",
    "projection_schema_version",
    "projection_scope",
    "reference_type",
    "release_obligation",
    "required_projection_fields",
    "time_obligation",
    "unresolved_policy",
}
RELATIONSHIP_KEYS = {
    "citation_ids",
    "direction",
    "does_not_entail_product_capability",
    "eligible_paths",
    "endpoint_binding",
    "layer",
    "predecessor_version",
    "relationship_type_id",
    "required_evidence_kinds",
    "resolved_person_reference_required",
    "role_id",
    "semantic_state",
    "source_entity_types",
    "target_entity_types",
    "time_semantics",
    "unresolved_reference_not_canonical_endpoint",
    "version",
    "version_coexistence",
}
SOURCE_KEYS = {"citations", "path", "sha256"}
CITATION_KEYS = {"citation_id", "line_end", "line_start", "source_terms"}
EXPECTED_PERSON_RELATIONSHIPS = {
    "company_has_team_member": {
        "source_entity_types": ["company"],
        "role_id": "team_role",
        "required_evidence_kinds": ["company_personnel_assertion"],
        "time_semantics": "validity_interval",
        "eligible_paths": ["relationship_traversal", "structured_filter"],
        "semantic_state": "company_personnel_membership",
        "citation_ids": ["person.internal_role_neutral_boundary"],
    },
    "paper_has_author": {
        "source_entity_types": ["paper"],
        "role_id": "author",
        "required_evidence_kinds": ["paper_author_assertion"],
        "time_semantics": "none",
        "eligible_paths": ["relationship_traversal", "structured_filter"],
        "semantic_state": "authorship",
        "citation_ids": ["person.internal_role_neutral_boundary"],
    },
    "patent_has_inventor": {
        "source_entity_types": ["patent"],
        "role_id": "inventor",
        "required_evidence_kinds": ["patent_inventor_assertion"],
        "time_semantics": "none",
        "eligible_paths": [
            "patent_to_professor",
            "professor_to_patent",
            "relationship_traversal",
            "structured_filter",
        ],
        "semantic_state": "inventorship",
        "citation_ids": ["person.internal_role_neutral_boundary"],
    },
}
EXPECTED_TECHNOLOGY_RELATIONSHIPS = {
    "entity_discusses_or_mentions_technology": (
        "discussion_or_mention",
        "technology_discussion_assertion",
        "observed_at",
    ),
    "entity_claims_adoption_of_technology": (
        "claimed_adoption",
        "technology_adoption_claim_assertion",
        "validity_interval",
    ),
    "entity_demonstrates_use_of_technology": (
        "demonstrated_use",
        "technology_demonstrated_use_assertion",
        "validity_interval",
    ),
}


class CatalogValidationError(ValueError):
    """The additive catalog or one of its bound authority sources is invalid."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise CatalogValidationError(f"non-finite catalog value is forbidden: {value}")


def canonical_catalog_bytes(payload: dict[str, Any]) -> bytes:
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


def catalog_content_sha256(payload: dict[str, Any]) -> str:
    hash_payload = dict(payload)
    hash_payload.pop("content_sha256", None)
    return hashlib.sha256(canonical_catalog_bytes(hash_payload)).hexdigest()


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise CatalogValidationError(
            f"{label} keys differ: expected={sorted(expected)}, actual={sorted(value)}"
        )


def _require_string_list(value: Any, label: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise CatalogValidationError(f"{label} must be a non-empty string list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise CatalogValidationError(f"{label} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise CatalogValidationError(f"{label} must not contain duplicates")
    return cast(list[str], value)


def _validate_reference_types(
    value: Any,
    *,
    citation_ids: set[str],
) -> None:
    if not isinstance(value, list) or len(value) != len(INTERNAL_REFERENCE_TYPES):
        raise CatalogValidationError(
            "catalog must contain three internal reference types"
        )
    rows = cast(list[Any], value)
    names: list[str] = []
    expected_contracts = {
        "person": {
            "projection_schema_version": "person-reference-projection-v1",
            "required_projection_fields": {
                "canonical_person_identity_id",
                "display_name",
                "aliases",
                "reference_ids",
                "supporting_assertion_ids",
                "source_anchor_ids",
                "identity_decision_id",
                "as_of",
                "release_id",
                "content_sha256",
            },
            "evidence_obligation": "accepted_four_domain_anchor_and_identity_decision",
            "time_obligation": "projection_as_of_and_source_observation_time",
            "release_obligation": "bind_exact_accepted_release_and_content_hash",
            "unresolved_policy": "retain_reference_without_canonical_identity",
            "citation_ids": [
                "person.internal_role_neutral_boundary",
                "release.internal_auxiliary_scope",
            ],
        },
        "technology_concept": {
            "projection_schema_version": "technology-concept-projection-v1",
            "required_projection_fields": {
                "canonical_technology_identity_id",
                "preferred_name",
                "aliases",
                "definition",
                "parent_concept_ids",
                "supporting_assertion_ids",
                "source_anchor_ids",
                "observed_at",
                "release_id",
                "content_sha256",
            },
            "evidence_obligation": "accepted_public_domain_or_typed_product_anchor",
            "time_obligation": "source_observed_at_and_optional_validity",
            "release_obligation": "bind_exact_accepted_release_and_content_hash",
            "unresolved_policy": "retain_term_or_alias_candidate_until_offline_acceptance",
            "citation_ids": [
                "technology.internal_model",
                "release.internal_auxiliary_scope",
            ],
        },
        "technology_route": {
            "projection_schema_version": "technology-route-projection-v1",
            "required_projection_fields": {
                "canonical_technology_identity_id",
                "preferred_name",
                "aliases",
                "definition",
                "concept_ids",
                "supporting_assertion_ids",
                "source_anchor_ids",
                "observed_at",
                "release_id",
                "content_sha256",
            },
            "evidence_obligation": "accepted_public_domain_or_typed_product_anchor",
            "time_obligation": "source_observed_at_and_optional_validity",
            "release_obligation": "bind_exact_accepted_release_and_content_hash",
            "unresolved_policy": "retain_term_or_alias_candidate_until_offline_acceptance",
            "citation_ids": [
                "technology.internal_model",
                "release.internal_auxiliary_scope",
            ],
        },
    }
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise CatalogValidationError(
                f"internal reference type {index} must be an object"
            )
        row = cast(dict[str, Any], raw)
        _require_exact_keys(row, REFERENCE_KEYS, f"internal reference type {index}")
        name = row["reference_type"]
        names.append(name)
        if row["identity_entity_type"] != name:
            raise CatalogValidationError(
                "internal reference identity type must match reference type"
            )
        if row["projection_scope"] != "internal_auxiliary":
            raise CatalogValidationError(
                "internal reference projection scope must be internal_auxiliary"
            )
        fields = set(
            _require_string_list(row["required_projection_fields"], f"{name} fields")
        )
        row_citations = _require_string_list(
            row["citation_ids"], f"{name} citation_ids"
        )
        if not set(row_citations) <= citation_ids:
            raise CatalogValidationError(f"{name} references unknown citation IDs")
        expected = expected_contracts.get(name)
        actual = {
            "projection_schema_version": row["projection_schema_version"],
            "required_projection_fields": fields,
            "evidence_obligation": row["evidence_obligation"],
            "time_obligation": row["time_obligation"],
            "release_obligation": row["release_obligation"],
            "unresolved_policy": row["unresolved_policy"],
            "citation_ids": row_citations,
        }
        if expected is None or actual != expected:
            raise CatalogValidationError(f"{name} reference definition differs")
    if tuple(names) != INTERNAL_REFERENCE_TYPES:
        raise CatalogValidationError(
            "internal reference types must use the frozen order"
        )


def _validate_relationship_types(
    value: Any,
    *,
    citation_ids: set[str],
) -> None:
    if not isinstance(value, list) or len(value) != 6:
        raise CatalogValidationError(
            "catalog must contain exactly six additive relationship types"
        )
    rows = cast(list[Any], value)
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise CatalogValidationError(f"relationship type {index} must be an object")
        row = cast(dict[str, Any], raw)
        _require_exact_keys(row, RELATIONSHIP_KEYS, f"relationship type {index}")
        key = (row["relationship_type_id"], row["version"])
        if key in indexed:
            raise CatalogValidationError("duplicate relationship type and version")
        indexed[key] = row
        if row["layer"] != "canonical" or row["direction"] != "directed":
            raise CatalogValidationError(
                "additive relationships must be canonical and directed"
            )
        for field in (
            "source_entity_types",
            "target_entity_types",
            "required_evidence_kinds",
            "eligible_paths",
            "citation_ids",
        ):
            _require_string_list(row[field], f"relationship {key} {field}")
        if not set(row["citation_ids"]) <= citation_ids:
            raise CatalogValidationError(
                f"relationship {key} references unknown citation IDs"
            )
        if row["relationship_type_id"] == "product_has_capability":
            raise CatalogValidationError("product_has_capability is forbidden")

    for relationship_id, expected_semantics in EXPECTED_PERSON_RELATIONSHIPS.items():
        key = (relationship_id, "canonical-v2-relationship-v2")
        row = indexed.get(key)
        if row is None:
            raise CatalogValidationError(
                f"missing exact Person relationship version: {key}"
            )
        if (
            row["target_entity_types"] != ["person"]
            or row["endpoint_binding"] != "resolved_internal_reference_registry"
            or row["predecessor_version"] != "canonical-v2-relationship-v1"
            or row["version_coexistence"] != "required"
            or row["resolved_person_reference_required"] is not True
            or row["unresolved_reference_not_canonical_endpoint"] is not True
            or row["does_not_entail_product_capability"] is not False
            or {key: row[key] for key in expected_semantics} != expected_semantics
        ):
            raise CatalogValidationError(f"Person relationship contract differs: {key}")

    technology_sources = ["company", "paper", "patent", "product"]
    technology_targets = ["technology_concept", "technology_route"]
    for relationship_id, (
        semantics,
        evidence_kind,
        time_semantics,
    ) in EXPECTED_TECHNOLOGY_RELATIONSHIPS.items():
        key = (relationship_id, "canonical-v2-relationship-v1")
        row = indexed.get(key)
        if row is None:
            raise CatalogValidationError(
                f"missing exact Technology relationship version: {key}"
            )
        if (
            row["source_entity_types"] != technology_sources
            or row["target_entity_types"] != technology_targets
            or row["semantic_state"] != semantics
            or row["required_evidence_kinds"] != [evidence_kind]
            or row["time_semantics"] != time_semantics
            or row["endpoint_binding"]
            != "public_or_typed_subobject_to_internal_reference_registry"
            or row["role_id"] != "technology"
            or row["eligible_paths"]
            != ["exact_lookup", "semantic_recall", "relationship_traversal"]
            or row["citation_ids"]
            != [
                "technology.relationship_states",
                "product.capability_answer_boundary",
            ]
        ):
            raise CatalogValidationError("technology relationship semantics differ")
        if (
            row["does_not_entail_product_capability"] is not True
            or row["resolved_person_reference_required"] is not False
            or row["unresolved_reference_not_canonical_endpoint"] is not True
            or row["predecessor_version"] is not None
            or row["version_coexistence"] != "not_applicable"
        ):
            raise CatalogValidationError("Technology relationship boundary differs")


def _resolve_authority_path(repo_root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise CatalogValidationError("authority path must be repository-relative")
    root = repo_root.resolve()
    resolved = (root / relative).resolve()
    if resolved == root or root not in resolved.parents:
        raise CatalogValidationError("authority path escapes repository root")
    if not resolved.is_file():
        raise CatalogValidationError(f"authority source is not a file: {relative_path}")
    return resolved


def _validate_source_manifest(value: Any, *, repo_root: Path) -> set[str]:
    if not isinstance(value, list) or not value:
        raise CatalogValidationError("source_manifest must be a non-empty list")
    sources = cast(list[Any], value)
    paths: list[str] = []
    citation_ids: set[str] = set()
    for index, raw in enumerate(sources):
        if not isinstance(raw, dict):
            raise CatalogValidationError(
                f"source manifest item {index} must be an object"
            )
        item = cast(dict[str, Any], raw)
        _require_exact_keys(item, SOURCE_KEYS, f"source manifest item {index}")
        path = item["path"]
        if not isinstance(path, str) or not path:
            raise CatalogValidationError("source manifest path must be non-empty")
        paths.append(path)
        source_path = _resolve_authority_path(repo_root, path)
        source_bytes = source_path.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != item["sha256"]:
            raise CatalogValidationError(f"authority source hash changed: {path}")
        text_lines = source_bytes.decode("utf-8", errors="strict").splitlines()
        citations = item["citations"]
        if not isinstance(citations, list) or not citations:
            raise CatalogValidationError(f"source {path} must contain citations")
        for raw_citation in citations:
            if not isinstance(raw_citation, dict):
                raise CatalogValidationError(
                    f"source {path} citation must be an object"
                )
            citation = cast(dict[str, Any], raw_citation)
            _require_exact_keys(citation, CITATION_KEYS, f"source {path} citation")
            citation_id = citation["citation_id"]
            if not isinstance(citation_id, str) or not citation_id:
                raise CatalogValidationError("citation_id must be non-empty")
            if citation_id in citation_ids:
                raise CatalogValidationError(f"duplicate citation ID: {citation_id}")
            citation_ids.add(citation_id)
            start = citation["line_start"]
            end = citation["line_end"]
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < 1
                or end < start
                or end > len(text_lines)
            ):
                raise CatalogValidationError(
                    f"citation range is invalid: {citation_id}"
                )
            terms = _require_string_list(
                citation["source_terms"], f"citation {citation_id} source_terms"
            )
            excerpt = "\n".join(text_lines[start - 1 : end])
            for term in terms:
                if term not in excerpt:
                    raise CatalogValidationError(
                        f"citation source term changed: {citation_id}: {term}"
                    )
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise CatalogValidationError("source manifest paths must be unique and sorted")
    return citation_ids


def validate_catalog_payload(payload: dict[str, Any], *, repo_root: Path) -> None:
    _require_exact_keys(payload, ROOT_KEYS, "root")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise CatalogValidationError("catalog schema version differs")
    if payload["catalog_version"] != CATALOG_VERSION:
        raise CatalogValidationError("catalog version differs")
    if payload["status"] != "frozen":
        raise CatalogValidationError("catalog status must be frozen")
    base = payload["base_domain_catalog"]
    if not isinstance(base, dict):
        raise CatalogValidationError("base_domain_catalog must be an object")
    _require_exact_keys(base, BASE_CATALOG_KEYS, "base_domain_catalog")
    if base != BASE_DOMAIN_CATALOG:
        raise CatalogValidationError("base domain catalog identity differs")
    if tuple(payload["public_domain_types"]) != PUBLIC_DOMAIN_TYPES:
        raise CatalogValidationError(
            "catalog must retain the four ordered public domains"
        )
    citation_ids = _validate_source_manifest(
        payload["source_manifest"], repo_root=repo_root
    )
    _validate_reference_types(
        payload["internal_reference_types"], citation_ids=citation_ids
    )
    _validate_relationship_types(
        payload["relationship_types"], citation_ids=citation_ids
    )
    claimed_hash = payload["content_sha256"]
    if not isinstance(claimed_hash, str) or claimed_hash != catalog_content_sha256(
        payload
    ):
        raise CatalogValidationError("catalog content hash mismatch")


def load_and_validate_catalog(
    *,
    repo_root: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    try:
        raw_bytes = catalog_path.read_bytes()
        value = json.loads(
            raw_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_non_finite,
        )
    except CatalogValidationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogValidationError(f"cannot load catalog: {catalog_path}") from exc
    if not isinstance(value, dict):
        raise CatalogValidationError("catalog root must be an object")
    payload = cast(dict[str, Any], value)
    validate_catalog_payload(payload, repo_root=repo_root)
    return payload


__all__ = [
    "BASE_DOMAIN_CATALOG",
    "CATALOG_VERSION",
    "CatalogValidationError",
    "INTERNAL_REFERENCE_TYPES",
    "PUBLIC_DOMAIN_TYPES",
    "SCHEMA_VERSION",
    "canonical_catalog_bytes",
    "catalog_content_sha256",
    "load_and_validate_catalog",
    "validate_catalog_payload",
]
