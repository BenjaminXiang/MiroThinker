from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest


S6_ROOT = Path(__file__).resolve().parent
REPO_ROOT = S6_ROOT.parents[3]
VALIDATOR_PATH = S6_ROOT / "validate_domain_catalog.py"
CATALOG_PATH = S6_ROOT / "domain-catalog-v1.json"

EXPECTED_AUTHORITY_SOURCES = {
    ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/source-coverage-matrix.md",
    "docs/Company-Data-Agent-PRD.md",
    "docs/Data-Agent-Shared-Spec.md",
    "docs/Multi-turn-Context-Manager-Design.md",
    "docs/Paper-Data-Agent-PRD.md",
    "docs/Paper-Requirement-Review-2026-05-10.md",
    "docs/Patent-Data-Agent-PRD.md",
    "docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md",
    "docs/Professor-Requirement-Review-2026-05-10.md",
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/canonical-v2-knowledge/spec.md",
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/paper-identity-status/spec.md",
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/professor-retrieval-index-split/spec.md",
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/recovery-evidence-landing/spec.md",
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md",
}

EXPECTED_SHARED_FIELDS = {
    "core_facts",
    "display_name",
    "evidence",
    "id",
    "last_updated",
    "object_type",
    "quality_status",
    "run_id",
    "summary_fields",
}

EXPECTED_DOMAIN_FIELDS = {
    "company": {
        "aliases",
        "credit_code",
        "evidence",
        "founded_at",
        "geography",
        "id",
        "industry",
        "industry_tags",
        "key_personnel",
        "last_updated",
        "latest_public_updates",
        "legal_representative",
        "name",
        "normalized_name",
        "patent_count",
        "product_description",
        "profile_summary",
        "quality_status",
        "registered_address",
        "registered_capital",
        "run_id",
        "team_description",
        "tech_tags",
        "technology_route_summary",
        "website",
    },
    "paper": {
        "abstract",
        "arxiv_id",
        "authors",
        "citation_count",
        "doi",
        "enrichment_sources",
        "evidence",
        "fields_of_study",
        "funders",
        "id",
        "keywords",
        "last_updated",
        "license",
        "oa_status",
        "pdf_path",
        "professor_ids",
        "publication_date",
        "quality_status",
        "reference_count",
        "run_id",
        "summary_text",
        "summary_zh",
        "title",
        "title_zh",
        "tldr",
        "venue",
        "year",
    },
    "patent": {
        "abstract",
        "applicants",
        "company_ids",
        "evidence",
        "filing_date",
        "grant_date",
        "id",
        "inventors",
        "ipc_codes",
        "last_updated",
        "patent_number",
        "patent_type",
        "professor_ids",
        "publication_date",
        "quality_status",
        "run_id",
        "summary_text",
        "technology_effect",
        "title",
        "title_en",
    },
    "professor": {
        "aliases",
        "awards",
        "canonical_name_en",
        "canonical_name_zh",
        "citation_count",
        "company_roles",
        "department",
        "email",
        "evidence",
        "h_index",
        "homepage",
        "id",
        "institution",
        "last_updated",
        "lifecycle_state",
        "manual_override",
        "name",
        "office",
        "paper_count",
        "paper_summary",
        "patent_ids",
        "patent_summary",
        "phone",
        "profile_summary",
        "projects",
        "quality_status",
        "research_directions",
        "run_id",
        "title",
    },
}

EXPECTED_SUBOBJECTS = {
    "company": {
        "business_scenario",
        "capability",
        "financing_event",
        "key_personnel",
        "personnel_education",
        "personnel_work_experience",
        "product",
        "public_update",
    },
    "paper": {
        "author",
        "enrichment_provenance",
        "full_text",
        "funding",
        "identifier",
        "publication",
        "reference",
        "summary",
    },
    "patent": {
        "applicant",
        "inventor",
        "ipc_classification",
        "patent_milestone",
        "technical_summary",
    },
    "professor": {
        "affiliation_history",
        "award",
        "contact",
        "education_history",
        "metric_snapshot",
        "research_project",
        "work_history",
    },
}

EXPECTED_RELATIONSHIP_FAMILIES = {
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
    "company_serves_business_scenario",
    "company_located_in_geography",
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
    "source_record_parsed_from_artifact",
    "source_identity_resolves_to_canonical_identity",
}

EXPECTED_CROSS_DOMAIN_PATHS = {
    "company_to_patent",
    "company_to_professor",
    "paper_to_professor",
    "patent_to_company",
    "patent_to_professor",
    "professor_to_company",
    "professor_to_paper",
    "professor_to_patent",
}

EXPECTED_LAYER_CONTRACTS = {
    "canonical": (
        "source_grounded_accepted_relationship_facts",
        "frozen_in_task_6_1",
    ),
    "derived": (
        "release_scoped_reproducible_computations_not_canonical_facts",
        "deferred_to_s7_s8",
    ),
    "session": (
        "session_scoped_referents_sets_constraints_and_paths_not_canonical_facts",
        "deferred_to_s9",
    ),
}

EXPECTED_LAYER_POLICIES = {
    "canonical": (
        "required",
        ("event_time", "none", "observed_at", "validity_interval"),
    ),
    "derived": ("forbidden", ("computed_at",)),
    "session": ("forbidden", ("session_lifetime",)),
}

EXPECTED_DIRECTION_OUTCOMES = {
    "company_to_patent": "supported",
    "company_to_professor": "insufficient_evidence",
    "paper_to_professor": "supported",
    "patent_to_company": "supported",
    "patent_to_professor": "insufficient_evidence",
    "professor_to_company": "insufficient_evidence",
    "professor_to_paper": "supported",
    "professor_to_patent": "insufficient_evidence",
}

EXPECTED_DEFERRED_OWNERS = {
    "derived_relationship_execution": "s7_s8",
    "domain_inclusion_and_projection": "tasks_6_2_6_3",
    "path_eligibility": "tasks_6_6_6_7",
    "relationship_execution_and_persistence": "tasks_6_4_6_5",
    "session_relationship_execution": "s9",
}

EXPECTED_IDENTITY_ENDPOINT_BINDINGS = {
    "canonical_identity_merged_into": "canonical_identity_lineage",
    "canonical_identity_split_from": "canonical_identity_lineage",
    "identity_decision_reverses_identity_decision": "identity_decision_lineage_metadata",
    "identity_decision_supersedes_identity_decision": "identity_decision_lineage_metadata",
    "source_identity_resolves_to_canonical_identity": "source_identity_to_canonical_identity_metadata",
}


def _validator() -> ModuleType:
    assert VALIDATOR_PATH.is_file(), "Task 6.1 catalog validator is missing"
    spec = importlib.util.spec_from_file_location("s6_domain_catalog", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "s6_domain_catalog_builder",
        S6_ROOT / "build_domain_catalog.py",
    )
    assert spec is not None and spec.loader is not None
    sys.path.insert(0, str(S6_ROOT))
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(S6_ROOT))
    return module


def test_frozen_catalog_binds_exact_authority_sources_and_deterministic_bytes() -> None:
    validator = _validator()

    catalog = validator.load_and_validate_catalog(
        repo_root=REPO_ROOT,
        catalog_path=CATALOG_PATH,
    )

    assert catalog["schema_version"] == "canonical-v2-domain-catalog-v1"
    assert catalog["catalog_version"] == "canonical-v2-prd-catalog-2026-07-12"
    assert catalog["status"] == "frozen"
    assert {entry["path"] for entry in catalog["source_manifest"]} == (
        EXPECTED_AUTHORITY_SOURCES
    )
    assert validator.canonical_catalog_bytes(catalog) == CATALOG_PATH.read_bytes()


def test_catalog_freezes_complete_typed_domain_fields_and_subobjects() -> None:
    catalog = _validator().load_and_validate_catalog(
        repo_root=REPO_ROOT,
        catalog_path=CATALOG_PATH,
    )

    assert {
        field["field_path"] for field in catalog["shared_projection_fields"]
    } == EXPECTED_SHARED_FIELDS
    domains = {domain["domain"]: domain for domain in catalog["domains"]}
    assert set(domains) == set(EXPECTED_DOMAIN_FIELDS)

    globally_unique_ids: set[str] = set()
    for domain_name, domain in domains.items():
        fields = domain["fields"]
        subobjects = domain["subobjects"]
        assert {field["field_path"] for field in fields} == EXPECTED_DOMAIN_FIELDS[
            domain_name
        ]
        assert {item["subobject_type"] for item in subobjects} == EXPECTED_SUBOBJECTS[
            domain_name
        ]
        assert "top_papers" not in {field["field_path"] for field in fields}
        for item in [*fields, *subobjects]:
            assert item["catalog_item_id"] not in globally_unique_ids
            globally_unique_ids.add(item["catalog_item_id"])
            assert item["citation_ids"]
            assert item["evidence_obligation"]
            assert item["temporal_class"] in {
                "event",
                "observation",
                "static",
                "validity_interval",
            }
        for field in fields:
            assert field["cardinality"] in {"many", "one", "optional_one"}
            assert field["requiredness"] in {
                "conditional",
                "optional",
                "required",
            }
            assert field["semantic_use"]
            assert field["requiredness_scope"]
            assert field["value_shape"]
            if field["requiredness"] == "required" and field["cardinality"] != "many":
                assert field["cardinality"] == "one"
        for subobject in subobjects:
            assert subobject["cardinality"] in {"many", "one", "optional_one"}
            assert subobject["identity_key"]
            assert subobject["members"]
            assert subobject["parent_domain"] == domain_name

    quality_field = next(
        field
        for field in catalog["shared_projection_fields"]
        if field["field_path"] == "quality_status"
    )
    assert quality_field["semantic_use"] == "quality_signal_not_path_admission"

    paper_fields = {field["field_path"]: field for field in domains["paper"]["fields"]}
    assert paper_fields["venue"]["requiredness"] == "required"
    assert paper_fields["venue"]["cardinality"] == "one"
    for summary_field in ("summary_text", "summary_zh"):
        assert paper_fields[summary_field]["requiredness"] == "conditional"
        assert paper_fields[summary_field]["requiredness_scope"] == (
            "quality_status_ready_only_not_canonical_inclusion"
        )
    professor_fields = {
        field["field_path"]: field for field in domains["professor"]["fields"]
    }
    assert professor_fields["patent_ids"]["requiredness"] == "required"
    assert professor_fields["patent_ids"]["cardinality"] == "many"
    assert all(
        field["temporal_class"] == "observation"
        for domain in domains.values()
        for field in domain["fields"]
        if field["field_path"] == "last_updated"
    )


def test_catalog_freezes_relationship_type_contracts_and_three_layers() -> None:
    from src.data_agents.canonical_v2.contracts import RelationshipType

    catalog = _validator().load_and_validate_catalog(
        repo_root=REPO_ROOT,
        catalog_path=CATALOG_PATH,
    )

    families = catalog["relationship_families"]
    assert {family["family_id"] for family in families} == (
        EXPECTED_RELATIONSHIP_FAMILIES
    )
    assert all(family["citation_ids"] for family in families)

    layer_contracts = {
        item["layer"]: (item["semantic_boundary"], item["type_freeze_status"])
        for item in catalog["layer_contracts"]
    }
    assert layer_contracts == EXPECTED_LAYER_CONTRACTS
    assert {
        item["layer"]: (
            item["required_evidence_policy"],
            tuple(item["allowed_time_semantics"]),
        )
        for item in catalog["layer_contracts"]
    } == EXPECTED_LAYER_POLICIES

    relationships = {
        item["relationship_type_id"]: item for item in catalog["relationships"]
    }
    assert set(relationships) == EXPECTED_RELATIONSHIP_IDS
    for relationship in relationships.values():
        contract_fields = {
            key: relationship[key] for key in RelationshipType.model_fields
        }
        relationship_type = RelationshipType.model_validate(contract_fields)
        assert relationship_type.layer.value == "canonical"
        assert relationship["family"] in EXPECTED_RELATIONSHIP_FAMILIES
        assert relationship["citation_ids"]
        assert relationship["scenario_ids"]
        assert relationship["persistence_status"] == "deferred_to_task_6_5"
        expected_states = (
            ("accepted",)
            if relationship["family"] in {"evidence_lineage", "identity_lifecycle"}
            else ("accepted", "unresolved", "rejected", "superseded")
        )
        assert relationship_type.allowed_states == expected_states
        expected_binding = EXPECTED_IDENTITY_ENDPOINT_BINDINGS.get(
            relationship["relationship_type_id"],
            (
                "evidence_lineage_metadata"
                if relationship["family"] == "evidence_lineage"
                else "typed_entity_or_subobject"
            ),
        )
        assert relationship["endpoint_binding"] == expected_binding
        assert relationship_type.time_semantics.value in {
            "event_time",
            "none",
            "observed_at",
            "validity_interval",
        }
        assert "ready" not in relationship_type.eligible_paths

    professor_company = relationships["professor_company_role"]
    assert {role["role_id"] for role in professor_company["roles"]} == {
        "adviser",
        "cooperator",
        "employee",
        "founder",
        "investor",
    }
    assert professor_company["role_selection"] == "exactly_one"
    assert all(role["applies_to"] == "source" for role in professor_company["roles"])
    team = relationships["company_has_team_member"]
    assert team["roles"][0]["applies_to"] == "target"
    attribution = relationships["professor_attributed_to_paper"]
    assert attribution["roles"] == []
    assert attribution["role_selection"] == "none"
    assert (
        "attribution_basis_is_evidence_metadata_not_business_role"
        in attribution["semantic_constraints"]
    )
    assert (
        "attribution_not_paper_existence"
        in relationships["professor_attributed_to_paper"]["semantic_constraints"]
    )
    assert (
        "applicant_not_owner_or_assignee"
        in relationships["patent_has_applicant"]["semantic_constraints"]
    )

    frozen_paths = {
        path
        for relationship in relationships.values()
        for path in relationship["eligible_paths"]
        if path in EXPECTED_CROSS_DOMAIN_PATHS
    }
    assert frozen_paths == EXPECTED_CROSS_DOMAIN_PATHS
    assert "unresolved_task" not in json.dumps(catalog, ensure_ascii=False)


def test_relationship_semantics_are_source_exact_and_endpoint_conditional() -> None:
    catalog = _validator().load_and_validate_catalog(
        repo_root=REPO_ROOT,
        catalog_path=CATALOG_PATH,
    )
    relationships = {
        item["relationship_type_id"]: item for item in catalog["relationships"]
    }

    required_citations_by_group = {
        "openspec.artifact_and_record_lineage": {
            "artifact_derived_from_artifact",
            "source_record_parsed_from_artifact",
        },
        "openspec.decision_lineage": {
            "assertion_supported_by_source_record",
            "canonical_decision_produced_by_run",
            "canonical_decision_selects_assertion",
            "canonical_decision_uses_policy",
        },
        "s2.typed_business_facts": {
            "company_has_capability",
            "company_has_financing_event",
            "company_has_product",
            "company_has_public_update",
            "company_has_team_member",
            "company_serves_business_scenario",
            "patent_has_applicant",
            "patent_has_inventor",
            "professor_educated_at_institution",
            "professor_held_role_at_non_company_organization",
        },
        "paper.reference_phase2": {"paper_references_paper"},
    }
    for citation_id, relationship_ids in required_citations_by_group.items():
        for relationship_id in relationship_ids:
            assert citation_id in relationships[relationship_id]["citation_ids"]

    assert "canonical_identity_alias_of" not in relationships
    non_company_role = relationships["professor_held_role_at_non_company_organization"]
    assert "company" not in non_company_role["target_entity_types"]
    assert (
        "company_targets_require_professor_company_role"
        in non_company_role["semantic_constraints"]
    )
    assert (
        "company_paths_require_target_type_company_and_accepted_company_identity"
        in relationships["patent_has_applicant"]["semantic_constraints"]
    )
    assert (
        "professor_paths_require_target_type_professor_and_accepted_professor_identity"
        in relationships["patent_has_inventor"]["semantic_constraints"]
    )
    for relationship_id in (
        "canonical_identity_merged_into",
        "canonical_identity_split_from",
        "source_identity_resolves_to_canonical_identity",
    ):
        assert (
            "source_and_target_entity_types_must_match"
            in relationships[relationship_id]["semantic_constraints"]
        )
    assert (
        "decision_and_assertion_families_and_subjects_must_match"
        in relationships["canonical_decision_selects_assertion"]["semantic_constraints"]
    )

    direction_scenarios = [
        scenario
        for scenario in catalog["scenario_accounting"]
        if scenario["scenario_kind"] == "traversal_direction"
    ]
    assert all(
        "multi_turn.cross_domain_directions" in scenario["citation_ids"]
        for scenario in direction_scenarios
    )


def test_catalog_accounts_for_every_type_family_direction_and_deferred_owner() -> None:
    validator = _validator()
    catalog = validator.load_and_validate_catalog(
        repo_root=REPO_ROOT,
        catalog_path=CATALOG_PATH,
    )

    scenarios = {
        scenario["scenario_id"]: scenario for scenario in catalog["scenario_accounting"]
    }
    relationship_scenario_ids = {
        scenario_id
        for relationship in catalog["relationships"]
        for scenario_id in relationship["scenario_ids"]
    }
    assert relationship_scenario_ids <= set(scenarios)
    assert {
        scenario["family"]
        for scenario in scenarios.values()
        if scenario["scenario_kind"] == "relationship_type"
    } == EXPECTED_RELATIONSHIP_FAMILIES
    assert {
        relationship_id
        for scenario in scenarios.values()
        for relationship_id in scenario["relationship_type_ids"]
    } == EXPECTED_RELATIONSHIP_IDS
    assert {scenario["evidence_outcome"] for scenario in scenarios.values()} == {
        "absent",
        "insufficient_evidence",
        "supported",
    }

    direction_outcomes = {
        scenario["traversal_direction"]: scenario["evidence_outcome"]
        for scenario in scenarios.values()
        if scenario["scenario_kind"] == "traversal_direction"
    }
    assert direction_outcomes == EXPECTED_DIRECTION_OUTCOMES
    assert {
        item["deferred_id"]: item["owner"] for item in catalog["deferred_owners"]
    } == EXPECTED_DEFERRED_OWNERS
    assert catalog["content_sha256"] == validator.catalog_content_sha256(catalog)

    seed = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    seed["relationships"] = []
    seed["relationship_families"] = []
    seed["layer_contracts"] = []
    seed["scenario_accounting"] = []
    seed["deferred_owners"] = []
    rebuilt = _builder().build_catalog(seed)
    assert validator.canonical_catalog_bytes(rebuilt) == CATALOG_PATH.read_bytes()


def test_validator_rejects_hash_source_duplicate_and_unknown_schema_drift(
    tmp_path: Path,
) -> None:
    validator = _validator()
    catalog = validator.load_and_validate_catalog(
        repo_root=REPO_ROOT,
        catalog_path=CATALOG_PATH,
    )
    candidate_path = tmp_path / "domain-catalog-v1.json"

    tampered = json.loads(json.dumps(catalog))
    tampered["relationships"][0]["time_semantics"] = "validity_interval"
    candidate_path.write_bytes(validator.canonical_catalog_bytes(tampered))
    with pytest.raises(validator.CatalogValidationError, match="content hash"):
        validator.load_and_validate_catalog(
            repo_root=REPO_ROOT,
            catalog_path=candidate_path,
        )

    wrong_source = json.loads(json.dumps(catalog))
    wrong_source["source_manifest"][0]["sha256"] = "0" * 64
    wrong_source["content_sha256"] = validator.catalog_content_sha256(wrong_source)
    candidate_path.write_bytes(validator.canonical_catalog_bytes(wrong_source))
    with pytest.raises(validator.CatalogValidationError, match="source hash changed"):
        validator.load_and_validate_catalog(
            repo_root=REPO_ROOT,
            catalog_path=candidate_path,
        )

    duplicate_key_payload = CATALOG_PATH.read_bytes().replace(
        b'  "status": "frozen"\n',
        b'  "status": "frozen",\n  "status": "frozen"\n',
        1,
    )
    candidate_path.write_bytes(duplicate_key_payload)
    with pytest.raises(validator.CatalogValidationError, match="duplicate JSON key"):
        validator.load_and_validate_catalog(
            repo_root=REPO_ROOT,
            catalog_path=candidate_path,
        )

    for mutate in (
        lambda value: value["relationships"][0].update({"unknown": True}),
        lambda value: value["domains"][0]["fields"][0].update({"unknown": True}),
        lambda value: value["source_manifest"][0]["citations"][0].update(
            {"unknown": True}
        ),
    ):
        unknown_schema = json.loads(json.dumps(catalog))
        mutate(unknown_schema)
        unknown_schema["content_sha256"] = validator.catalog_content_sha256(
            unknown_schema
        )
        candidate_path.write_bytes(validator.canonical_catalog_bytes(unknown_schema))
        with pytest.raises(validator.CatalogValidationError, match="unexpected"):
            validator.load_and_validate_catalog(
                repo_root=REPO_ROOT,
                catalog_path=candidate_path,
            )


def test_validator_rejects_requiredness_role_and_endpoint_semantic_drift(
    tmp_path: Path,
) -> None:
    validator = _validator()
    catalog = validator.load_and_validate_catalog(
        repo_root=REPO_ROOT,
        catalog_path=CATALOG_PATH,
    )
    candidate_path = tmp_path / "semantic-drift.json"

    def assert_rejected(mutated: dict[str, Any], match: str) -> None:
        mutated["content_sha256"] = validator.catalog_content_sha256(mutated)
        candidate_path.write_bytes(validator.canonical_catalog_bytes(mutated))
        with pytest.raises(validator.CatalogValidationError, match=match):
            validator.load_and_validate_catalog(
                repo_root=REPO_ROOT,
                catalog_path=candidate_path,
            )

    wrong_requiredness = json.loads(json.dumps(catalog))
    paper = next(
        domain
        for domain in wrong_requiredness["domains"]
        if domain["domain"] == "paper"
    )
    venue = next(field for field in paper["fields"] if field["field_path"] == "venue")
    venue["requiredness"] = "optional"
    assert_rejected(wrong_requiredness, "requiredness precedence")

    wrong_role_owner = json.loads(json.dumps(catalog))
    professor_company = next(
        relationship
        for relationship in wrong_role_owner["relationships"]
        if relationship["relationship_type_id"] == "professor_company_role"
    )
    professor_company["roles"][0]["applies_to"] = "relationship"
    assert_rejected(wrong_role_owner, "role ownership")

    for relationship_id, constraint in (
        (
            "canonical_identity_merged_into",
            "source_and_target_entity_types_must_match",
        ),
        (
            "canonical_decision_selects_assertion",
            "decision_and_assertion_families_and_subjects_must_match",
        ),
        (
            "patent_has_applicant",
            "company_paths_require_target_type_company_and_accepted_company_identity",
        ),
    ):
        missing_constraint = json.loads(json.dumps(catalog))
        relationship = next(
            item
            for item in missing_constraint["relationships"]
            if item["relationship_type_id"] == relationship_id
        )
        relationship["semantic_constraints"].remove(constraint)
        assert_rejected(missing_constraint, "endpoint constraints")


def test_builder_confines_and_atomically_validates_catalog_writes(
    tmp_path: Path,
) -> None:
    builder = _builder()
    output_root = tmp_path / "approved-output"
    output_root.mkdir()

    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside-sentinel")
    with pytest.raises(ValueError, match="approved output root"):
        builder.confined_catalog_path(outside, output_root=output_root)
    assert outside.read_bytes() == b"outside-sentinel"

    symlink = output_root / "catalog-link.json"
    symlink.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        builder.confined_catalog_path(symlink, output_root=output_root)
    assert outside.read_bytes() == b"outside-sentinel"

    target = output_root / "domain-catalog-v1.json"
    target.write_bytes(b"valid-prior-sentinel")
    with pytest.raises(ValueError):
        builder.write_validated_catalog(
            b'{"invalid": true}\n',
            catalog_path=target,
            repo_root=REPO_ROOT,
            output_root=output_root,
        )
    assert target.read_bytes() == b"valid-prior-sentinel"
    assert set(output_root.iterdir()) == {symlink, target}
