from __future__ import annotations

from importlib import import_module


TARGET_MODULE = "src.data_agents.canonical_v2.internal_reference_projection"


def test_internal_reference_request_accepts_only_closed_lineage_inputs() -> None:
    module = import_module(TARGET_MODULE)

    fields = set(module.InternalReferenceProjectionRequest.model_fields)
    assert {
        "reference_catalog_identity",
        "public_domain_projection_request",
        "public_domain_projection_result",
        "person_identity_resolution_request",
        "person_identity_resolution_result",
        "person_evidence_locators",
        "technology_identity_resolution_request",
        "technology_identity_resolution_result",
        "technology_evidence_locators",
    } <= fields
    assert {
        "public_evidence_anchors",
        "person_identities",
        "person_references",
        "person_projection_seeds",
        "technology_identities",
        "technology_concept_seeds",
        "technology_route_seeds",
        "technology_evidence_relations",
    }.isdisjoint(fields)

    locator_fields = set(module.PersonEvidenceLocator.model_fields)
    assert locator_fields == {
        "reference_id",
        "source_kind",
        "root_canonical_identity_id",
        "source_subobject_id",
        "source_identity_id",
    }
    assert "resolution_state" not in locator_fields
    assert "canonical_person_identity_id" not in locator_fields

    technology_locator_fields = set(module.TechnologyEvidenceLocator.model_fields)
    assert technology_locator_fields == {
        "reference_id",
        "reference_type",
        "technology_source_identity_id",
        "public_domain",
        "root_canonical_identity_id",
        "source_field_path",
        "source_subobject_type",
        "source_subobject_id",
    }
    assert "canonical_technology_identity_id" not in technology_locator_fields
    assert "preferred_name" not in technology_locator_fields
    assert "definition" not in technology_locator_fields
    assert "resolution_state" not in technology_locator_fields


def test_internal_reference_result_binds_catalog_and_identity_resolution() -> None:
    module = import_module(TARGET_MODULE)

    result_fields = set(module.InternalReferenceProjectionResult.model_fields)
    projection_fields = set(module.PersonProjection.model_fields)
    for fields in (result_fields, projection_fields):
        assert {
            "reference_catalog_schema_version",
            "reference_catalog_version",
            "reference_catalog_content_sha256",
        } <= fields
    assert "identity_resolution_content_sha256" in projection_fields
    assert "source_identity_ids" in projection_fields
    assert "source_record_ids" in projection_fields
    assert "assignment_decision_ids" in projection_fields
    assert "identity_verdict_ids" in projection_fields
    assert hasattr(module, "validate_internal_reference_projection_result")

    anchor_fields = set(module.PublicDomainEvidenceAnchor.model_fields)
    reference_fields = set(module.PersonReference.model_fields)
    assert {"person_name", "source_record_ids"} <= anchor_fields
    assert {"identity_assertion_ids", "shared_source_record_ids"} <= reference_fields
    assert "person_orcid" in anchor_fields
    assert hasattr(module, "PersonEvidenceCrosswalk")

    technology_result_fields = {
        "technology_identity_resolution_content_sha256",
        "technology_evidence_anchors",
        "technology_concept_projections",
        "technology_route_projections",
        "unresolved_technology_references",
    }
    assert technology_result_fields <= result_fields
    assert "technology_relationships" not in result_fields
    for model in (
        module.TechnologyConceptProjection,
        module.TechnologyRouteProjection,
    ):
        fields = set(model.model_fields)
        assert {
            "canonical_technology_identity_id",
            "source_anchor_ids",
            "source_identity_ids",
            "supporting_assertion_ids",
            "source_record_ids",
            "identity_decision_id",
            "technology_identity_resolution_content_sha256",
            "field_lineage",
            "release_id",
            "content_sha256",
        } <= fields
