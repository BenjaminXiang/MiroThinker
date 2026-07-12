#!/usr/bin/env python3
"""Validate the frozen, PRD-cited Canonical V2 domain catalog."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast


SCHEMA_VERSION = "canonical-v2-domain-catalog-v1"
CATALOG_VERSION = "canonical-v2-prd-catalog-2026-07-12"
ROOT_KEYS = {
    "catalog_version",
    "content_sha256",
    "deferred_owners",
    "domains",
    "layer_contracts",
    "relationship_families",
    "relationships",
    "scenario_accounting",
    "schema_version",
    "shared_projection_fields",
    "source_manifest",
    "status",
}
SOURCE_MANIFEST_KEYS = {"authority_tier", "citations", "path", "sha256"}
SOURCE_CITATION_KEYS = {"citation_id", "line_end", "line_start", "source_terms"}
FIELD_KEYS = {
    "cardinality",
    "catalog_item_id",
    "citation_ids",
    "evidence_obligation",
    "field_path",
    "requiredness",
    "requiredness_scope",
    "semantic_use",
    "temporal_class",
    "value_shape",
}
SUBOBJECT_KEYS = {
    "cardinality",
    "catalog_item_id",
    "citation_ids",
    "evidence_obligation",
    "identity_key",
    "members",
    "parent_domain",
    "subobject_type",
    "temporal_class",
}
SUBOBJECT_MEMBER_KEYS = {"member_name", "required", "value_shape"}
RELATIONSHIP_KEYS = {
    "allowed_states",
    "citation_ids",
    "direction",
    "endpoint_binding",
    "eligible_paths",
    "family",
    "layer",
    "persistence_status",
    "relationship_type_id",
    "required_evidence_kinds",
    "role_selection",
    "roles",
    "scenario_ids",
    "semantic_constraints",
    "source_entity_types",
    "target_entity_types",
    "time_semantics",
    "version",
}
RELATIONSHIP_ROLE_KEYS = {"applies_to", "description", "required", "role_id"}
RELATIONSHIP_FAMILY_IDS = {
    "company_business_product_event",
    "evidence_lineage",
    "identity_lifecycle",
    "intellectual_property",
    "organization_role",
    "scholarly_output",
    "taxonomy_topic_geography",
}
EXPECTED_RELATIONSHIP_IDS = {
    "artifact_derived_from_artifact",
    "assertion_supported_by_source_record",
    "canonical_decision_produced_by_run",
    "canonical_decision_selects_assertion",
    "canonical_decision_uses_policy",
    "canonical_identity_merged_into",
    "canonical_identity_split_from",
    "company_has_capability",
    "company_has_financing_event",
    "company_has_product",
    "company_has_public_update",
    "company_has_team_member",
    "company_in_industry",
    "company_located_in_geography",
    "company_serves_business_scenario",
    "identity_decision_reverses_identity_decision",
    "identity_decision_supersedes_identity_decision",
    "paper_has_author",
    "paper_has_topic",
    "paper_published_in_venue",
    "paper_references_paper",
    "patent_has_applicant",
    "patent_has_inventor",
    "patent_has_ipc_classification",
    "professor_affiliated_with_institution",
    "professor_attributed_to_paper",
    "professor_company_role",
    "professor_educated_at_institution",
    "professor_has_research_topic",
    "professor_held_role_at_non_company_organization",
    "professor_member_of_department",
    "professor_page_lists_patent",
    "source_identity_resolves_to_canonical_identity",
    "source_record_parsed_from_artifact",
}
IDENTITY_ENDPOINT_BINDINGS = {
    "canonical_identity_merged_into": "canonical_identity_lineage",
    "canonical_identity_split_from": "canonical_identity_lineage",
    "identity_decision_reverses_identity_decision": "identity_decision_lineage_metadata",
    "identity_decision_supersedes_identity_decision": "identity_decision_lineage_metadata",
    "source_identity_resolves_to_canonical_identity": "source_identity_to_canonical_identity_metadata",
}
REQUIRED_RELATIONSHIP_CITATIONS = {
    "artifact_derived_from_artifact": {"openspec.artifact_and_record_lineage"},
    "source_record_parsed_from_artifact": {"openspec.artifact_and_record_lineage"},
    "assertion_supported_by_source_record": {"openspec.decision_lineage"},
    "canonical_decision_produced_by_run": {"openspec.decision_lineage"},
    "canonical_decision_selects_assertion": {"openspec.decision_lineage"},
    "canonical_decision_uses_policy": {"openspec.decision_lineage"},
    "company_has_capability": {"s2.typed_business_facts"},
    "company_has_financing_event": {"s2.typed_business_facts"},
    "company_has_product": {"s2.typed_business_facts"},
    "company_has_public_update": {"s2.typed_business_facts"},
    "company_has_team_member": {"s2.typed_business_facts"},
    "company_serves_business_scenario": {"s2.typed_business_facts"},
    "paper_references_paper": {"paper.reference_phase2"},
    "patent_has_applicant": {"s2.typed_business_facts"},
    "patent_has_inventor": {"s2.typed_business_facts"},
    "professor_educated_at_institution": {"s2.typed_business_facts"},
    "professor_held_role_at_non_company_organization": {"s2.typed_business_facts"},
}
REQUIRED_RELATIONSHIP_CONSTRAINTS = {
    "canonical_decision_selects_assertion": {
        "decision_and_assertion_families_and_subjects_must_match"
    },
    "canonical_identity_merged_into": {"source_and_target_entity_types_must_match"},
    "canonical_identity_split_from": {"source_and_target_entity_types_must_match"},
    "patent_has_applicant": {
        "applicant_not_owner_or_assignee",
        "company_paths_require_target_type_company_and_accepted_company_identity",
    },
    "patent_has_inventor": {
        "professor_paths_require_target_type_professor_and_accepted_professor_identity"
    },
    "professor_held_role_at_non_company_organization": {
        "company_targets_require_professor_company_role"
    },
    "professor_attributed_to_paper": {
        "attribution_basis_is_evidence_metadata_not_business_role",
        "attribution_not_paper_existence",
    },
    "source_identity_resolves_to_canonical_identity": {
        "source_and_target_entity_types_must_match"
    },
}
REQUIRED_ROLE_OWNERSHIP = {
    "company_has_team_member": {"team_role": "target"},
    "paper_has_author": {"author": "target"},
    "patent_has_applicant": {"applicant": "target"},
    "patent_has_inventor": {"inventor": "target"},
    "professor_company_role": {
        "adviser": "source",
        "cooperator": "source",
        "employee": "source",
        "founder": "source",
        "investor": "source",
    },
    "professor_held_role_at_non_company_organization": {"position_title": "source"},
}
RELATIONSHIP_LAYERS = {"canonical", "derived", "session"}
TRAVERSAL_DIRECTIONS = {
    "company_to_patent",
    "company_to_professor",
    "paper_to_professor",
    "patent_to_company",
    "patent_to_professor",
    "professor_to_company",
    "professor_to_paper",
    "professor_to_patent",
}
DEFERRED_OWNER_IDS = {
    "derived_relationship_execution",
    "domain_inclusion_and_projection",
    "path_eligibility",
    "relationship_execution_and_persistence",
    "session_relationship_execution",
}
TIME_SEMANTICS = {
    "computed_at",
    "event_time",
    "none",
    "observed_at",
    "session_lifetime",
    "validity_interval",
}


class CatalogValidationError(ValueError):
    """The frozen catalog or one of its exact authority sources is invalid."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_number(value: str) -> None:
    raise CatalogValidationError(f"non-standard JSON number: {value}")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_catalog_bytes(catalog: dict[str, Any]) -> bytes:
    """Return the one checked-in byte representation for the frozen catalog."""
    return (
        json.dumps(
            catalog,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def catalog_content_sha256(catalog: dict[str, Any]) -> str:
    """Hash the canonical catalog payload with its self-hash field excluded."""
    hash_payload = dict(catalog)
    hash_payload.pop("content_sha256", None)
    return _sha256(canonical_catalog_bytes(hash_payload))


def _source_path(repo_root: Path, relative_path: str) -> Path:
    root = repo_root.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise CatalogValidationError(
            f"authority source escapes repository root: {relative_path}"
        )
    if not candidate.is_file():
        raise CatalogValidationError(f"authority source is missing: {relative_path}")
    return candidate


def _validate_source_manifest(catalog: dict[str, Any], *, repo_root: Path) -> set[str]:
    manifest = catalog.get("source_manifest")
    if not isinstance(manifest, list) or not manifest:
        raise CatalogValidationError("source_manifest must be a non-empty list")
    paths = cast(
        list[str],
        [entry.get("path") for entry in manifest if isinstance(entry, dict)],
    )
    if len(paths) != len(manifest) or any(
        not isinstance(path, str) or not path for path in paths
    ):
        raise CatalogValidationError("every authority source requires a path")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise CatalogValidationError(
            "authority source paths must be unique and deterministically sorted"
        )

    citation_ids: set[str] = set()
    for entry in manifest:
        if set(entry) != SOURCE_MANIFEST_KEYS:
            raise CatalogValidationError(
                f"authority source has unexpected fields: {entry.get('path')}"
            )
        source_path = _source_path(repo_root, entry["path"])
        source_bytes = source_path.read_bytes()
        if entry.get("sha256") != _sha256(source_bytes):
            raise CatalogValidationError(
                f"authority source hash changed: {entry['path']}"
            )
        authority_tier = entry.get("authority_tier")
        if not isinstance(authority_tier, str) or not authority_tier:
            raise CatalogValidationError(f"authority tier is missing: {entry['path']}")
        try:
            lines = source_bytes.decode("utf-8", errors="strict").splitlines()
        except UnicodeDecodeError as exc:
            raise CatalogValidationError(
                f"authority source is not strict UTF-8: {entry['path']}"
            ) from exc
        citations = entry.get("citations")
        if not isinstance(citations, list) or not citations:
            raise CatalogValidationError(
                f"authority source requires exact citations: {entry['path']}"
            )
        for citation in citations:
            if set(citation) != SOURCE_CITATION_KEYS:
                raise CatalogValidationError(
                    f"authority citation has unexpected fields: {entry['path']}"
                )
            citation_id = citation.get("citation_id")
            line_start = citation.get("line_start")
            line_end = citation.get("line_end")
            source_terms = citation.get("source_terms")
            if (
                not isinstance(citation_id, str)
                or not citation_id
                or citation_id in citation_ids
                or not isinstance(line_start, int)
                or not isinstance(line_end, int)
                or line_start <= 0
                or line_end < line_start
                or line_end > len(lines)
                or not isinstance(source_terms, list)
                or not source_terms
                or not all(isinstance(term, str) and term for term in source_terms)
            ):
                raise CatalogValidationError(
                    f"invalid authority citation in {entry['path']}"
                )
            excerpt = "\n".join(lines[line_start - 1 : line_end])
            missing_terms = [term for term in source_terms if term not in excerpt]
            if missing_terms:
                raise CatalogValidationError(
                    f"citation {citation_id} does not contain {missing_terms}"
                )
            citation_ids.add(citation_id)
    return citation_ids


def _validate_domain_items(catalog: dict[str, Any], *, citation_ids: set[str]) -> None:
    shared_fields = catalog.get("shared_projection_fields")
    domains = catalog.get("domains")
    if not isinstance(shared_fields, list) or not shared_fields:
        raise CatalogValidationError("shared projection fields are missing")
    if not isinstance(domains, list) or {
        domain.get("domain") for domain in domains if isinstance(domain, dict)
    } != {"company", "paper", "patent", "professor"}:
        raise CatalogValidationError("domain catalog must cover exactly four domains")

    all_items: list[tuple[str, dict[str, Any]]] = [
        ("field", item) for item in shared_fields if isinstance(item, dict)
    ]
    for domain in domains:
        if set(domain) != {"domain", "fields", "subobjects"}:
            raise CatalogValidationError(
                f"domain catalog has unexpected fields: {domain.get('domain')}"
            )
        fields = domain.get("fields")
        subobjects = domain.get("subobjects")
        if not isinstance(fields, list) or not fields:
            raise CatalogValidationError(f"{domain.get('domain')} fields are missing")
        if not isinstance(subobjects, list) or not subobjects:
            raise CatalogValidationError(
                f"{domain.get('domain')} sub-objects are missing"
            )
        if any(
            not isinstance(item, dict)
            or item.get("parent_domain") != domain.get("domain")
            for item in subobjects
        ):
            raise CatalogValidationError(
                f"{domain.get('domain')} sub-object parent is inconsistent"
            )
        all_items.extend(("field", item) for item in fields if isinstance(item, dict))
        all_items.extend(
            ("subobject", item) for item in subobjects if isinstance(item, dict)
        )

    catalog_item_ids: set[str] = set()
    for kind, item in all_items:
        item_id = item.get("catalog_item_id")
        expected_keys = FIELD_KEYS if kind == "field" else SUBOBJECT_KEYS
        if set(item) != expected_keys:
            raise CatalogValidationError(
                f"{kind} catalog item has unexpected fields: {item_id}"
            )
        item_citations = item.get("citation_ids")
        if (
            not isinstance(item_id, str)
            or not item_id
            or item_id in catalog_item_ids
            or not isinstance(item_citations, list)
            or not item_citations
            or not set(item_citations) <= citation_ids
            or item.get("temporal_class")
            not in {"event", "observation", "static", "validity_interval"}
            or not isinstance(item.get("evidence_obligation"), str)
            or not item["evidence_obligation"]
        ):
            raise CatalogValidationError(f"invalid {kind} catalog item: {item_id}")
        catalog_item_ids.add(item_id)
        if kind == "field":
            if (
                not isinstance(item.get("field_path"), str)
                or not item["field_path"]
                or item.get("cardinality") not in {"many", "one", "optional_one"}
                or item.get("requiredness")
                not in {"conditional", "optional", "required"}
                or not isinstance(item.get("requiredness_scope"), str)
                or not item["requiredness_scope"]
                or not isinstance(item.get("semantic_use"), str)
                or not item["semantic_use"]
                or not isinstance(item.get("value_shape"), str)
                or not item["value_shape"]
            ):
                raise CatalogValidationError(f"invalid field catalog item: {item_id}")
        else:
            members = item.get("members")
            if (
                not isinstance(item.get("subobject_type"), str)
                or not item["subobject_type"]
                or item.get("cardinality") not in {"many", "one", "optional_one"}
                or not isinstance(item.get("identity_key"), str)
                or not item["identity_key"]
                or item.get("parent_domain")
                not in {"company", "paper", "patent", "professor"}
                or not isinstance(members, list)
                or not members
                or any(
                    not isinstance(member, dict)
                    or set(member) != SUBOBJECT_MEMBER_KEYS
                    or not isinstance(member.get("member_name"), str)
                    or not member["member_name"]
                    or not isinstance(member.get("value_shape"), str)
                    or not member["value_shape"]
                    or not isinstance(member.get("required"), bool)
                    for member in members
                )
            ):
                raise CatalogValidationError(
                    f"invalid sub-object catalog item: {item_id}"
                )

    domain_by_name = {domain["domain"]: domain for domain in domains}
    paper_fields = {
        field["field_path"]: field for field in domain_by_name["paper"]["fields"]
    }
    professor_fields = {
        field["field_path"]: field for field in domain_by_name["professor"]["fields"]
    }
    if (
        paper_fields["venue"]["requiredness"] != "required"
        or paper_fields["venue"]["cardinality"] != "one"
        or professor_fields["patent_ids"]["requiredness"] != "required"
        or professor_fields["patent_ids"]["cardinality"] != "many"
        or any(
            paper_fields[name]["requiredness"] != "conditional"
            or paper_fields[name]["requiredness_scope"]
            != "quality_status_ready_only_not_canonical_inclusion"
            for name in ("summary_text", "summary_zh")
        )
    ):
        raise CatalogValidationError(
            "locked Paper/Professor requiredness precedence is inconsistent"
        )
    if any(
        field["temporal_class"] != "observation"
        for domain in domains
        for field in domain["fields"]
        if field["field_path"] == "last_updated"
    ):
        raise CatalogValidationError("last_updated must use observation semantics")


def _validate_relationship_catalog(
    catalog: dict[str, Any], *, citation_ids: set[str]
) -> None:
    families = catalog.get("relationship_families")
    if not isinstance(families, list):
        raise CatalogValidationError("relationship_families must be a list")
    family_ids = cast(
        list[str],
        [family.get("family_id") for family in families if isinstance(family, dict)],
    )
    if (
        len(family_ids) != len(families)
        or family_ids != sorted(family_ids)
        or set(family_ids) != RELATIONSHIP_FAMILY_IDS
    ):
        raise CatalogValidationError(
            "relationship families must be exact, unique, and sorted"
        )
    for family in families:
        if (
            set(family) != {"citation_ids", "family_id", "semantic_scope"}
            or not isinstance(family.get("semantic_scope"), str)
            or not family["semantic_scope"]
            or not isinstance(family.get("citation_ids"), list)
            or not family["citation_ids"]
            or not set(family["citation_ids"]) <= citation_ids
        ):
            raise CatalogValidationError(
                f"invalid relationship family: {family.get('family_id')}"
            )

    layer_contracts = catalog.get("layer_contracts")
    if not isinstance(layer_contracts, list):
        raise CatalogValidationError("layer_contracts must be a list")
    layers = cast(
        list[str],
        [layer.get("layer") for layer in layer_contracts if isinstance(layer, dict)],
    )
    if (
        len(layers) != len(layer_contracts)
        or layers != sorted(layers)
        or set(layers) != RELATIONSHIP_LAYERS
    ):
        raise CatalogValidationError(
            "relationship layer contracts must be exact, unique, and sorted"
        )
    for layer in layer_contracts:
        if (
            set(layer)
            != {
                "citation_ids",
                "layer",
                "allowed_time_semantics",
                "required_evidence_policy",
                "semantic_boundary",
                "type_freeze_status",
            }
            or not isinstance(layer.get("semantic_boundary"), str)
            or not layer["semantic_boundary"]
            or not isinstance(layer.get("type_freeze_status"), str)
            or not layer["type_freeze_status"]
            or layer.get("required_evidence_policy") not in {"forbidden", "required"}
            or not isinstance(layer.get("allowed_time_semantics"), list)
            or not layer["allowed_time_semantics"]
            or layer["allowed_time_semantics"]
            != sorted(set(layer["allowed_time_semantics"]))
            or not set(layer["allowed_time_semantics"]) <= TIME_SEMANTICS
            or not isinstance(layer.get("citation_ids"), list)
            or not layer["citation_ids"]
            or not set(layer["citation_ids"]) <= citation_ids
        ):
            raise CatalogValidationError(
                f"invalid relationship layer contract: {layer.get('layer')}"
            )
    layer_by_id = {layer["layer"]: layer for layer in layer_contracts}
    if (
        layer_by_id["canonical"]["required_evidence_policy"] != "required"
        or layer_by_id["canonical"]["allowed_time_semantics"]
        != ["event_time", "none", "observed_at", "validity_interval"]
        or layer_by_id["derived"]["required_evidence_policy"] != "forbidden"
        or layer_by_id["derived"]["allowed_time_semantics"] != ["computed_at"]
        or layer_by_id["session"]["required_evidence_policy"] != "forbidden"
        or layer_by_id["session"]["allowed_time_semantics"] != ["session_lifetime"]
    ):
        raise CatalogValidationError("relationship layer policies are inconsistent")

    relationships = catalog.get("relationships")
    if not isinstance(relationships, list) or not relationships:
        raise CatalogValidationError("canonical relationships are missing")
    relationship_ids = cast(
        list[str],
        [
            item.get("relationship_type_id")
            for item in relationships
            if isinstance(item, dict)
        ],
    )
    if (
        len(relationship_ids) != len(relationships)
        or relationship_ids != sorted(relationship_ids)
        or len(relationship_ids) != len(set(relationship_ids))
        or set(relationship_ids) != EXPECTED_RELATIONSHIP_IDS
    ):
        raise CatalogValidationError(
            "relationship type IDs must be unique and deterministically sorted"
        )

    covered_families: set[str] = set()
    for relationship in relationships:
        relationship_id = relationship.get("relationship_type_id")
        if set(relationship) != RELATIONSHIP_KEYS:
            raise CatalogValidationError(
                f"relationship type has unexpected fields: {relationship_id}"
            )
        family = relationship.get("family")
        source_types = relationship.get("source_entity_types")
        target_types = relationship.get("target_entity_types")
        evidence_kinds = relationship.get("required_evidence_kinds")
        paths = relationship.get("eligible_paths")
        relationship_citations = relationship.get("citation_ids")
        scenario_ids = relationship.get("scenario_ids")
        constraints = relationship.get("semantic_constraints")
        expected_states = (
            ["accepted"]
            if family in {"evidence_lineage", "identity_lifecycle"}
            else ["accepted", "unresolved", "rejected", "superseded"]
        )
        expected_endpoint_binding = IDENTITY_ENDPOINT_BINDINGS.get(
            relationship_id,
            (
                "evidence_lineage_metadata"
                if family == "evidence_lineage"
                else "typed_entity_or_subobject"
            ),
        )
        if (
            not isinstance(relationship_id, str)
            or not relationship_id
            or family not in RELATIONSHIP_FAMILY_IDS
            or relationship.get("version") != "canonical-v2-relationship-v1"
            or relationship.get("layer") != "canonical"
            or relationship.get("endpoint_binding") != expected_endpoint_binding
            or relationship.get("persistence_status") != "deferred_to_task_6_5"
            or relationship.get("direction") not in {"directed", "undirected"}
            or not isinstance(source_types, list)
            or not source_types
            or source_types != sorted(set(source_types))
            or not all(isinstance(value, str) and value for value in source_types)
            or not isinstance(target_types, list)
            or not target_types
            or target_types != sorted(set(target_types))
            or not all(isinstance(value, str) and value for value in target_types)
            or not isinstance(evidence_kinds, list)
            or not evidence_kinds
            or evidence_kinds != sorted(set(evidence_kinds))
            or relationship.get("time_semantics")
            not in {"event_time", "none", "observed_at", "validity_interval"}
            or relationship.get("allowed_states") != expected_states
            or not isinstance(paths, list)
            or not paths
            or paths != sorted(set(paths))
            or not all(isinstance(value, str) and value for value in paths)
            or not isinstance(relationship_citations, list)
            or not relationship_citations
            or relationship_citations != sorted(set(relationship_citations))
            or not set(relationship_citations) <= citation_ids
            or not isinstance(scenario_ids, list)
            or not scenario_ids
            or scenario_ids != sorted(set(scenario_ids))
            or not all(isinstance(value, str) and value for value in scenario_ids)
            or not isinstance(constraints, list)
            or constraints != sorted(set(constraints))
        ):
            raise CatalogValidationError(
                f"invalid canonical relationship type: {relationship_id}"
            )
        if not REQUIRED_RELATIONSHIP_CITATIONS.get(relationship_id, set()) <= set(
            relationship_citations
        ):
            raise CatalogValidationError(
                f"relationship type lacks exact citations: {relationship_id}"
            )
        if not REQUIRED_RELATIONSHIP_CONSTRAINTS.get(relationship_id, set()) <= set(
            constraints
        ):
            raise CatalogValidationError(
                f"relationship type lacks endpoint constraints: {relationship_id}"
            )
        if (
            relationship_id == "professor_held_role_at_non_company_organization"
            and "company" in target_types
        ):
            raise CatalogValidationError(
                "non-Company organization role cannot admit Company endpoints"
            )

        roles = relationship.get("roles")
        role_selection = relationship.get("role_selection")
        if not isinstance(roles, list) or role_selection not in {
            "exactly_one",
            "none",
            "one_or_more",
        }:
            raise CatalogValidationError(
                f"invalid relationship role policy: {relationship_id}"
            )
        role_ids = cast(
            list[str],
            [role.get("role_id") for role in roles if isinstance(role, dict)],
        )
        if any(
            isinstance(role, dict) and set(role) != RELATIONSHIP_ROLE_KEYS
            for role in roles
        ):
            raise CatalogValidationError(
                f"relationship role has unexpected fields: {relationship_id}"
            )
        if (
            len(role_ids) != len(roles)
            or role_ids != sorted(set(role_ids))
            or (not roles and role_selection != "none")
            or (roles and role_selection == "none")
            or any(
                not isinstance(role.get("role_id"), str)
                or not role["role_id"]
                or role.get("applies_to") not in {"relationship", "source", "target"}
                or not isinstance(role.get("description"), str)
                or not role["description"]
                or not isinstance(role.get("required"), bool)
                for role in roles
            )
        ):
            raise CatalogValidationError(
                f"invalid relationship roles: {relationship_id}"
            )
        actual_role_ownership = {role["role_id"]: role["applies_to"] for role in roles}
        expected_role_ownership = REQUIRED_ROLE_OWNERSHIP.get(relationship_id, {})
        if actual_role_ownership != expected_role_ownership:
            raise CatalogValidationError(
                f"relationship role ownership is inconsistent: {relationship_id}"
            )
        if relationship_id == "professor_attributed_to_paper" and (
            roles or role_selection != "none"
        ):
            raise CatalogValidationError(
                "Professor-Paper attribution basis belongs to evidence metadata"
            )
        covered_families.add(family)

    if covered_families != RELATIONSHIP_FAMILY_IDS:
        raise CatalogValidationError(
            "every canonical relationship family requires at least one type"
        )


def _validate_scenario_and_deferred_accounting(
    catalog: dict[str, Any], *, citation_ids: set[str]
) -> None:
    relationships = catalog["relationships"]
    relationship_by_id = {
        relationship["relationship_type_id"]: relationship
        for relationship in relationships
    }
    scenarios = catalog.get("scenario_accounting")
    if not isinstance(scenarios, list) or not scenarios:
        raise CatalogValidationError("scenario_accounting must be a non-empty list")
    scenario_ids = cast(
        list[str],
        [
            scenario.get("scenario_id")
            for scenario in scenarios
            if isinstance(scenario, dict)
        ],
    )
    if (
        len(scenario_ids) != len(scenarios)
        or scenario_ids != sorted(scenario_ids)
        or len(scenario_ids) != len(set(scenario_ids))
    ):
        raise CatalogValidationError("scenario IDs must be unique and sorted")

    type_scenario_relationships: set[str] = set()
    scenario_families: set[str] = set()
    traversal_directions: set[str] = set()
    outcomes: set[str] = set()
    for scenario in scenarios:
        scenario_id = scenario.get("scenario_id")
        kind = scenario.get("scenario_kind")
        family = scenario.get("family")
        relationship_type_ids = scenario.get("relationship_type_ids")
        scenario_citations = scenario.get("citation_ids")
        outcome = scenario.get("evidence_outcome")
        expected_keys = {
            "citation_ids",
            "evidence_basis",
            "evidence_outcome",
            "family",
            "relationship_type_ids",
            "scenario_id",
            "scenario_kind",
            "user_effect",
        }
        if kind == "traversal_direction":
            expected_keys.add("traversal_direction")
        if (
            set(scenario) != expected_keys
            or kind not in {"relationship_type", "traversal_direction"}
            or family not in RELATIONSHIP_FAMILY_IDS
            or not isinstance(relationship_type_ids, list)
            or not relationship_type_ids
            or relationship_type_ids != sorted(set(relationship_type_ids))
            or not set(relationship_type_ids) <= set(relationship_by_id)
            or any(
                relationship_by_id[relationship_id]["family"] != family
                for relationship_id in relationship_type_ids
            )
            or not isinstance(scenario_citations, list)
            or not scenario_citations
            or scenario_citations != sorted(set(scenario_citations))
            or not set(scenario_citations) <= citation_ids
            or outcome not in {"absent", "insufficient_evidence", "supported"}
            or not isinstance(scenario.get("evidence_basis"), str)
            or not scenario["evidence_basis"]
            or not isinstance(scenario.get("user_effect"), str)
            or not scenario["user_effect"]
        ):
            raise CatalogValidationError(f"invalid scenario accounting: {scenario_id}")
        if kind == "relationship_type":
            if len(relationship_type_ids) != 1:
                raise CatalogValidationError(
                    f"type scenario must bind one relationship type: {scenario_id}"
                )
            type_scenario_relationships.update(relationship_type_ids)
            scenario_families.add(family)
        else:
            direction = scenario.get("traversal_direction")
            if (
                direction not in TRAVERSAL_DIRECTIONS
                or "multi_turn.cross_domain_directions" not in scenario_citations
            ):
                raise CatalogValidationError(
                    f"invalid traversal direction scenario: {scenario_id}"
                )
            traversal_directions.add(direction)
        outcomes.add(outcome)

    referenced_scenarios = {
        scenario_id
        for relationship in relationships
        for scenario_id in relationship["scenario_ids"]
    }
    if referenced_scenarios != set(scenario_ids):
        raise CatalogValidationError(
            "relationship scenario references must exactly cover scenario accounting"
        )
    if type_scenario_relationships != set(relationship_by_id):
        raise CatalogValidationError(
            "every relationship type requires one accounting scenario"
        )
    if scenario_families != RELATIONSHIP_FAMILY_IDS:
        raise CatalogValidationError(
            "every relationship family requires scenario accounting"
        )
    if traversal_directions != TRAVERSAL_DIRECTIONS:
        raise CatalogValidationError(
            "all eight cross-domain traversal directions require accounting"
        )
    if outcomes != {"absent", "insufficient_evidence", "supported"}:
        raise CatalogValidationError(
            "scenario accounting must retain supported, absent, and insufficient outcomes"
        )

    deferred = catalog.get("deferred_owners")
    if not isinstance(deferred, list):
        raise CatalogValidationError("deferred_owners must be a list")
    deferred_ids = cast(
        list[str],
        [item.get("deferred_id") for item in deferred if isinstance(item, dict)],
    )
    if (
        len(deferred_ids) != len(deferred)
        or deferred_ids != sorted(deferred_ids)
        or set(deferred_ids) != DEFERRED_OWNER_IDS
    ):
        raise CatalogValidationError(
            "deferred owners must be exact, unique, and sorted"
        )
    for item in deferred:
        if (
            set(item) != {"citation_ids", "deferred_id", "owner", "scope"}
            or not isinstance(item.get("owner"), str)
            or not item["owner"]
            or not isinstance(item.get("scope"), str)
            or not item["scope"]
            or not isinstance(item.get("citation_ids"), list)
            or not item["citation_ids"]
            or item["citation_ids"] != sorted(set(item["citation_ids"]))
            or not set(item["citation_ids"]) <= citation_ids
        ):
            raise CatalogValidationError(
                f"invalid deferred owner: {item.get('deferred_id')}"
            )


def load_and_validate_catalog(*, repo_root: Path, catalog_path: Path) -> dict[str, Any]:
    """Load exact canonical JSON and fail closed on authority-source drift."""
    try:
        payload = catalog_path.read_bytes()
    except OSError as exc:
        raise CatalogValidationError(
            f"frozen domain catalog is missing or unreadable: {catalog_path}"
        ) from exc
    try:
        catalog = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonstandard_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogValidationError(
            "frozen domain catalog is not strict JSON"
        ) from exc
    if not isinstance(catalog, dict):
        raise CatalogValidationError("frozen domain catalog must be a JSON object")
    if set(catalog) != ROOT_KEYS:
        raise CatalogValidationError("frozen domain catalog has unexpected root fields")
    if catalog.get("schema_version") != SCHEMA_VERSION:
        raise CatalogValidationError("unexpected domain catalog schema_version")
    if catalog.get("catalog_version") != CATALOG_VERSION:
        raise CatalogValidationError("unexpected domain catalog_version")
    if catalog.get("status") != "frozen":
        raise CatalogValidationError("domain catalog status must be frozen")
    if canonical_catalog_bytes(catalog) != payload:
        raise CatalogValidationError(
            "frozen domain catalog bytes are not canonical and deterministic"
        )
    if catalog.get("content_sha256") != catalog_content_sha256(catalog):
        raise CatalogValidationError("frozen domain catalog content hash changed")
    citation_ids = _validate_source_manifest(catalog, repo_root=repo_root)
    _validate_domain_items(catalog, citation_ids=citation_ids)
    _validate_relationship_catalog(catalog, citation_ids=citation_ids)
    _validate_scenario_and_deferred_accounting(catalog, citation_ids=citation_ids)
    return catalog
