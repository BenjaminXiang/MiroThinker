from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from types import ModuleType
from typing import Any

import pytest


S6R_ROOT = Path(__file__).resolve().parent
REPO_ROOT = S6R_ROOT.parents[3]
BUILDER_PATH = S6R_ROOT / "build_internal_reference_catalog.py"
VALIDATOR_PATH = S6R_ROOT / "validate_internal_reference_catalog.py"
EVIDENCE_CATALOG = S6R_ROOT / "internal-reference-catalog-v1.json"
PACKAGED_CATALOG = (
    REPO_ROOT
    / "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs"
    / "internal-reference-catalog-v1.json"
)
HISTORICAL_EVIDENCE_CATALOG = (
    REPO_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s6/domain-catalog-v1.json"
)
HISTORICAL_PACKAGED_CATALOG = (
    REPO_ROOT
    / "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/domain-catalog-v1.json"
)
EXPECTED_PUBLIC_DOMAINS = ("company", "paper", "patent", "professor")
EXPECTED_REFERENCE_TYPES = ("person", "technology_concept", "technology_route")
EXPECTED_REFERENCE_CONTRACTS = {
    "person": {
        "projection_schema_version": "person-reference-projection-v1",
        "evidence_obligation": "accepted_four_domain_anchor_and_identity_decision",
        "time_obligation": "projection_as_of_and_source_observation_time",
        "release_obligation": "bind_exact_accepted_release_and_content_hash",
        "unresolved_policy": "retain_reference_without_canonical_identity",
    },
    "technology_concept": {
        "projection_schema_version": "technology-concept-projection-v1",
        "evidence_obligation": "accepted_public_domain_or_typed_product_anchor",
        "time_obligation": "source_observed_at_and_optional_validity",
        "release_obligation": "bind_exact_accepted_release_and_content_hash",
        "unresolved_policy": "retain_term_or_alias_candidate_until_offline_acceptance",
    },
    "technology_route": {
        "projection_schema_version": "technology-route-projection-v1",
        "evidence_obligation": "accepted_public_domain_or_typed_product_anchor",
        "time_obligation": "source_observed_at_and_optional_validity",
        "release_obligation": "bind_exact_accepted_release_and_content_hash",
        "unresolved_policy": "retain_term_or_alias_candidate_until_offline_acceptance",
    },
}
EXPECTED_PERSON_RELATIONSHIPS = {
    "company_has_team_member": {
        "role_id": "team_role",
        "required_evidence_kinds": ["company_personnel_assertion"],
        "time_semantics": "validity_interval",
        "eligible_paths": ["relationship_traversal", "structured_filter"],
        "semantic_state": "company_personnel_membership",
    },
    "paper_has_author": {
        "role_id": "author",
        "required_evidence_kinds": ["paper_author_assertion"],
        "time_semantics": "none",
        "eligible_paths": ["relationship_traversal", "structured_filter"],
        "semantic_state": "authorship",
    },
    "patent_has_inventor": {
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
    },
}
EXPECTED_TECHNOLOGY_RELATIONSHIPS = {
    "entity_discusses_or_mentions_technology": {
        "semantic_state": "discussion_or_mention",
        "required_evidence_kinds": ["technology_discussion_assertion"],
        "time_semantics": "observed_at",
    },
    "entity_claims_adoption_of_technology": {
        "semantic_state": "claimed_adoption",
        "required_evidence_kinds": ["technology_adoption_claim_assertion"],
        "time_semantics": "validity_interval",
    },
    "entity_demonstrates_use_of_technology": {
        "semantic_state": "demonstrated_use",
        "required_evidence_kinds": ["technology_demonstrated_use_assertion"],
        "time_semantics": "validity_interval",
    },
}


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validator() -> ModuleType:
    return _load_module(VALIDATOR_PATH, "canonical_v2_s6r_validator_test")


def _builder() -> ModuleType:
    return _load_module(BUILDER_PATH, "canonical_v2_s6r_builder_test")


def _catalog() -> dict[str, Any]:
    value = json.loads(EVIDENCE_CATALOG.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_rehashed(
    validator: ModuleType,
    path: Path,
    payload: dict[str, Any],
) -> None:
    candidate = dict(payload)
    candidate.pop("content_sha256", None)
    candidate["content_sha256"] = validator.catalog_content_sha256(candidate)
    path.write_bytes(validator.canonical_catalog_bytes(candidate))


def _copy_authority_snapshot(tmp_path: Path, catalog: dict[str, Any]) -> None:
    for item in catalog["source_manifest"]:
        relative = Path(item["path"])
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)


def test_builder_is_deterministic_and_evidence_matches_packaged_catalog() -> None:
    builder = _builder()
    validator = _validator()

    built = builder.build_catalog(repo_root=REPO_ROOT)
    installed = validator.load_and_validate_catalog(
        repo_root=REPO_ROOT,
        catalog_path=EVIDENCE_CATALOG,
    )

    assert built == installed
    assert EVIDENCE_CATALOG.read_bytes() == PACKAGED_CATALOG.read_bytes()
    assert (
        HISTORICAL_EVIDENCE_CATALOG.read_bytes()
        == HISTORICAL_PACKAGED_CATALOG.read_bytes()
    )
    assert installed["base_domain_catalog"] == {
        "schema_version": "canonical-v2-domain-catalog-v1",
        "catalog_version": "canonical-v2-prd-catalog-2026-07-12",
        "content_sha256": (
            "8ad9e719579b834f51128788f49d091913c0c90e3b047aac9b2f83cc794441d7"
        ),
        "file_sha256": (
            "b227285fef5d49ad0b30871e5ccb0c1932443206fac99f5fa708ae586c5383c0"
        ),
    }


def test_catalog_freezes_four_public_domains_three_internal_types_and_exact_relations() -> (
    None
):
    catalog = _catalog()

    assert tuple(catalog["public_domain_types"]) == EXPECTED_PUBLIC_DOMAINS
    definitions = {
        item["reference_type"]: item for item in catalog["internal_reference_types"]
    }
    assert tuple(definitions) == EXPECTED_REFERENCE_TYPES
    for reference_type, expected in EXPECTED_REFERENCE_CONTRACTS.items():
        assert {key: definitions[reference_type][key] for key in expected} == expected
    assert (
        "definition" in definitions["technology_concept"]["required_projection_fields"]
    )
    assert (
        "parent_concept_ids"
        in definitions["technology_concept"]["required_projection_fields"]
    )
    assert (
        "concept_ids" in definitions["technology_route"]["required_projection_fields"]
    )
    relationships = {
        (item["relationship_type_id"], item["version"]): item
        for item in catalog["relationship_types"]
    }
    for relationship_id, expected in EXPECTED_PERSON_RELATIONSHIPS.items():
        item = relationships[(relationship_id, "canonical-v2-relationship-v2")]
        assert item["predecessor_version"] == "canonical-v2-relationship-v1"
        assert item["version_coexistence"] == "required"
        assert item["target_entity_types"] == ["person"]
        assert item["resolved_person_reference_required"] is True
        assert item["unresolved_reference_not_canonical_endpoint"] is True
        assert {key: item[key] for key in expected} == expected
    for relationship_id, expected in EXPECTED_TECHNOLOGY_RELATIONSHIPS.items():
        item = relationships[(relationship_id, "canonical-v2-relationship-v1")]
        assert {key: item[key] for key in expected} == expected
        assert item["does_not_entail_product_capability"] is True
        assert item["unresolved_reference_not_canonical_endpoint"] is True
    assert not any(
        item["relationship_type_id"] == "product_has_capability"
        for item in catalog["relationship_types"]
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda payload: payload.update({"unexpected": True}), "root keys"),
        (
            lambda payload: payload["base_domain_catalog"].update(
                {"content_sha256": "0" * 64}
            ),
            "base domain catalog identity",
        ),
        (
            lambda payload: payload["public_domain_types"].append("person"),
            "four ordered public domains",
        ),
        (
            lambda payload: payload["relationship_types"].__setitem__(
                5, dict(payload["relationship_types"][0])
            ),
            "duplicate relationship type and version",
        ),
        (
            lambda payload: payload["relationship_types"][3].update(
                {"semantic_state": "claimed_adoption"}
            ),
            "technology relationship semantics",
        ),
        (
            lambda payload: payload["internal_reference_types"][1].update(
                {
                    "projection_schema_version": "bogus",
                    "evidence_obligation": "accept_unresolved",
                    "release_obligation": "unbound",
                    "unresolved_policy": "promote_online",
                }
            ),
            "technology_concept reference definition differs",
        ),
        (
            lambda payload: payload["relationship_types"][0].update(
                {
                    "required_evidence_kinds": ["unrelated"],
                    "semantic_state": "unrelated",
                    "time_semantics": "observed_at",
                    "eligible_paths": ["made_up"],
                }
            ),
            "Person relationship contract differs",
        ),
    ),
)
def test_validator_rejects_rehashed_structural_and_semantic_tampering(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    validator = _validator()
    payload = _catalog()
    mutation(payload)
    candidate = tmp_path / "candidate.json"
    _write_rehashed(validator, candidate, payload)

    with pytest.raises(validator.CatalogValidationError, match=message):
        validator.load_and_validate_catalog(
            repo_root=REPO_ROOT,
            catalog_path=candidate,
        )


def test_validator_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    validator = _validator()
    raw = EVIDENCE_CATALOG.read_text(encoding="utf-8")
    candidate = tmp_path / "duplicate.json"
    candidate.write_text(
        raw.replace(
            '  "status": "frozen"', '  "status": "frozen",\n  "status": "frozen"'
        ),
        encoding="utf-8",
    )

    with pytest.raises(validator.CatalogValidationError, match="duplicate JSON key"):
        validator.load_and_validate_catalog(
            repo_root=REPO_ROOT,
            catalog_path=candidate,
        )


def test_validator_binds_exact_authority_source_hashes(tmp_path: Path) -> None:
    validator = _validator()
    catalog = _catalog()
    _copy_authority_snapshot(tmp_path, catalog)
    source = tmp_path / catalog["source_manifest"][0]["path"]
    source.write_text(
        source.read_text(encoding="utf-8") + "\nsource drift\n", encoding="utf-8"
    )

    with pytest.raises(
        validator.CatalogValidationError, match="authority source hash changed"
    ):
        validator.load_and_validate_catalog(
            repo_root=tmp_path,
            catalog_path=EVIDENCE_CATALOG,
        )


def test_builder_check_rejects_catalog_byte_drift(tmp_path: Path) -> None:
    builder = _builder()
    candidate = tmp_path / "catalog.json"
    candidate.write_bytes(EVIDENCE_CATALOG.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="catalog bytes drifted"):
        builder.check_catalog(
            repo_root=REPO_ROOT,
            catalog_paths=(candidate,),
        )


def test_catalog_writer_rejects_symlinked_parent_escape(tmp_path: Path) -> None:
    builder = _builder()
    catalog = _catalog()
    repo_root = tmp_path / "repo"
    outside_root = tmp_path / "outside"
    repo_root.mkdir()
    (outside_root / "agents").mkdir(parents=True)
    (outside_root / "apps").mkdir(parents=True)
    _copy_authority_snapshot(repo_root, catalog)
    (repo_root / ".agents").symlink_to(
        outside_root / "agents", target_is_directory=True
    )
    (repo_root / "apps").symlink_to(outside_root / "apps", target_is_directory=True)
    catalog_paths = (
        repo_root
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s6r"
        / "internal-reference-catalog-v1.json",
        repo_root
        / "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs"
        / "internal-reference-catalog-v1.json",
    )

    with pytest.raises(ValueError, match="symlink|escapes repository root"):
        builder.write_catalog(repo_root=repo_root, catalog_paths=catalog_paths)

    assert not any(outside_root.rglob("internal-reference-catalog-v1.json"))
