from __future__ import annotations

from importlib.resources import files
import json
import subprocess
import sys
from typing import Any, get_args

from pydantic import ValidationError
import pytest

from src.data_agents.canonical_v2 import contracts
from src.data_agents.canonical_v2 import domain_catalog
from src.data_agents.canonical_v2.path_eligibility import Domain


PUBLIC_DOMAINS = ("company", "paper", "patent", "professor")
INTERNAL_REFERENCE_TYPES = ("person", "technology_concept", "technology_route")


def _raw_reference_catalog() -> dict[str, Any]:
    catalog_module: Any = domain_catalog
    raw = (
        files("src.data_agents.canonical_v2")
        .joinpath(catalog_module.REFERENCE_CATALOG_RESOURCE)
        .read_text(encoding="utf-8")
    )
    value = json.loads(raw)
    assert isinstance(value, dict)
    return value


def _raw_domain_catalog() -> dict[str, Any]:
    raw = (
        files("src.data_agents.canonical_v2")
        .joinpath(domain_catalog.CATALOG_RESOURCE)
        .read_text(encoding="utf-8")
    )
    value = json.loads(raw)
    assert isinstance(value, dict)
    return value


def test_catalog_keeps_four_public_domains_and_declares_internal_reference_types() -> (
    None
):
    catalog_module: Any = domain_catalog
    historical_catalog = domain_catalog.PACKAGED_CATALOG

    assert tuple(item.domain for item in historical_catalog.domains) == PUBLIC_DOMAINS
    assert (
        domain_catalog.CATALOG_CONTENT_SHA256
        == "8ad9e719579b834f51128788f49d091913c0c90e3b047aac9b2f83cc794441d7"
    )
    assert (
        domain_catalog.CATALOG_FILE_SHA256
        == "b227285fef5d49ad0b30871e5ccb0c1932443206fac99f5fa708ae586c5383c0"
    )
    catalog: Any = catalog_module.PACKAGED_REFERENCE_CATALOG
    assert catalog.public_domain_types == PUBLIC_DOMAINS
    assert (
        tuple(item.reference_type for item in catalog.internal_reference_types)
        == INTERNAL_REFERENCE_TYPES
    )
    reference_relationships = {
        (row["relationship_type_id"], row["version"]): row
        for row in _raw_reference_catalog()["relationship_types"]
    }
    historical_relationships = {
        (row["relationship_type_id"], row["version"]): row
        for row in _raw_domain_catalog()["relationships"]
    }
    for relationship_id in (
        "company_has_team_member",
        "paper_has_author",
        "patent_has_inventor",
    ):
        assert (
            relationship_id,
            "canonical-v2-relationship-v1",
        ) in historical_relationships
        current = reference_relationships[
            (relationship_id, "canonical-v2-relationship-v2")
        ]
        assert current["predecessor_version"] == "canonical-v2-relationship-v1"
        assert current["version_coexistence"] == "required"
        assert current["target_entity_types"] == ["person"]
        assert current["resolved_person_reference_required"] is True
        assert current["unresolved_reference_not_canonical_endpoint"] is True
    expected_technology_semantics = {
        "entity_discusses_or_mentions_technology": "discussion_or_mention",
        "entity_claims_adoption_of_technology": "claimed_adoption",
        "entity_demonstrates_use_of_technology": "demonstrated_use",
    }
    for relationship_id, semantics in expected_technology_semantics.items():
        row = reference_relationships[(relationship_id, "canonical-v2-relationship-v1")]
        assert row["semantic_state"] == semantics
        assert row["does_not_entail_product_capability"] is True
        assert row["unresolved_reference_not_canonical_endpoint"] is True
    assert tuple(get_args(Domain)) == PUBLIC_DOMAINS


def test_historical_domain_catalog_import_does_not_eagerly_load_reference_catalog() -> (
    None
):
    script = """
import sys
from src.data_agents.canonical_v2 import domain_catalog
reference_module = "src.data_agents.canonical_v2.internal_reference_catalog"
assert reference_module not in sys.modules
assert domain_catalog.PACKAGED_CATALOG.catalog_version == "canonical-v2-prd-catalog-2026-07-12"
assert reference_module not in sys.modules
assert domain_catalog.PACKAGED_REFERENCE_CATALOG.catalog_version == "canonical-v2-person-technology-reference-2026-07-13"
assert reference_module in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True)


def test_projection_manifests_distinguish_public_and_internal_scope() -> None:
    contracts_module: Any = contracts
    projection_scope = contracts_module.ProjectionScope
    public = contracts_module.IndexProjectionManifest(
        projection_id="index:company:identity",
        release_id="candidate-s6r-r1",
        projection_scope=projection_scope.public_domain,
        domain="company",
        reference_type=None,
        path="exact_lookup",
        projection_version="company-identity-v1",
        schema_version="index-v1",
        embedding_model="recorded-fake-v1",
        eligibility_policy_version="exact-v1",
        point_count=1,
        entity_ids_sha256="1" * 64,
        content_sha256="2" * 64,
        full_rebuild=True,
    )
    auxiliary = contracts_module.IndexProjectionManifest(
        projection_id="index:internal:person",
        release_id="candidate-s6r-r1",
        projection_scope=projection_scope.internal_auxiliary,
        domain=None,
        reference_type="person",
        path="exact_lookup",
        projection_version="person-reference-v1",
        schema_version="index-v1",
        embedding_model="recorded-fake-v1",
        eligibility_policy_version="internal-reference-v1",
        point_count=1,
        entity_ids_sha256="3" * 64,
        content_sha256="4" * 64,
        full_rebuild=True,
    )
    published_public = contracts_module.ProjectionManifest(
        projection_id="publish:company:current",
        release_id="candidate-s6r-r1",
        projection_scope=projection_scope.public_domain,
        projection_kind="typed_current",
        domain="company",
        reference_type=None,
        path=None,
        projection_version="company-current-v1",
        record_count=1,
        content_sha256="5" * 64,
    )
    published_auxiliary = contracts_module.ProjectionManifest(
        projection_id="publish:internal:technology-route",
        release_id="candidate-s6r-r1",
        projection_scope=projection_scope.internal_auxiliary,
        projection_kind="internal_reference_lookup",
        domain=None,
        reference_type="technology_route",
        path="exact_lookup",
        projection_version="technology-route-reference-v1",
        record_count=1,
        content_sha256="6" * 64,
    )

    assert public.domain == "company" and public.reference_type is None
    assert auxiliary.domain is None and auxiliary.reference_type == "person"
    assert published_public.domain == "company"
    assert published_public.reference_type is None
    assert published_auxiliary.domain is None
    assert published_auxiliary.reference_type == "technology_route"
    for manifest in (public, auxiliary, published_public, published_auxiliary):
        for required_field in ("projection_scope", "reference_type"):
            payload = manifest.model_dump()
            payload.pop(required_field)
            with pytest.raises(ValidationError, match=required_field):
                type(manifest)(**payload)
    with pytest.raises(ValidationError, match="internal_auxiliary"):
        contracts_module.IndexProjectionManifest(
            **{
                **auxiliary.model_dump(),
                "domain": "company",
            }
        )
    with pytest.raises(ValidationError, match="internal_auxiliary"):
        contracts_module.IndexProjectionManifest(
            **{
                **auxiliary.model_dump(),
                "reference_type": None,
            }
        )
    with pytest.raises(ValidationError, match="public_domain"):
        contracts_module.IndexProjectionManifest(
            **{
                **public.model_dump(),
                "reference_type": "person",
            }
        )
    with pytest.raises(ValidationError, match="public_domain"):
        contracts_module.IndexProjectionManifest(
            **{
                **public.model_dump(),
                "domain": None,
            }
        )
    with pytest.raises(ValidationError, match="internal_auxiliary"):
        contracts_module.ProjectionManifest(
            **{
                **published_auxiliary.model_dump(),
                "domain": "company",
            }
        )
    with pytest.raises(ValidationError, match="internal_auxiliary"):
        contracts_module.ProjectionManifest(
            **{
                **published_auxiliary.model_dump(),
                "reference_type": None,
            }
        )
    with pytest.raises(ValidationError, match="public_domain"):
        contracts_module.ProjectionManifest(
            **{
                **published_public.model_dump(),
                "reference_type": "technology_route",
            }
        )
    with pytest.raises(ValidationError, match="public_domain"):
        contracts_module.ProjectionManifest(
            **{
                **published_public.model_dump(),
                "domain": None,
            }
        )

    relationship_ids = {
        row["relationship_type_id"]
        for row in _raw_reference_catalog()["relationship_types"]
    }
    assert "product_has_capability" not in relationship_ids
