from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


S6_DIR = Path(__file__).resolve().parent
REPO_ROOT = S6_DIR.parents[3]
BUILDER_PATH = S6_DIR / "build_catalog_candidates.py"
SEED_PATH = S6_DIR / "catalog-candidate-seeds.json"
ARTIFACT_PATH = S6_DIR / "catalog-candidates.json"

REQUIRED_DOMAINS = {"company", "paper", "patent", "professor"}
REQUIRED_RELATIONSHIP_FAMILIES = {
    "company_business_product_event",
    "evidence_lineage",
    "identity_lifecycle",
    "intellectual_property",
    "organization_role",
    "scholarly_output",
    "taxonomy_topic_geography",
}


def _builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("s6_catalog_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load builder at {BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_catalog_matches_checked_in_artifact_and_is_deterministic() -> None:
    module = _builder()

    first = module.build_catalog(repo_root=REPO_ROOT, seed_path=SEED_PATH)
    second = module.build_catalog(repo_root=REPO_ROOT, seed_path=SEED_PATH)
    expected = ARTIFACT_PATH.read_bytes()

    assert first == second
    assert module.canonical_json_bytes(first) == expected
    assert first["status"] == "preparation_only"
    assert first["dependencies"]["task_5_5"] == "not_accepted"
    assert first["dependencies"]["task_5_6"] == "not_accepted"


def test_catalog_covers_four_domains_and_required_relationship_families() -> None:
    catalog = _builder().build_catalog(repo_root=REPO_ROOT, seed_path=SEED_PATH)

    assert {field["field_name"] for field in catalog["shared_projection_fields"]} == {
        "core_facts",
        "display_name",
        "object_type",
        "summary_fields",
    }
    assert {domain["domain"] for domain in catalog["domains"]} == REQUIRED_DOMAINS
    for domain in catalog["domains"]:
        assert domain["fields"]
        assert domain["subobjects"]

    relationships = catalog["relationships"]
    assert {item["family"] for item in relationships} == REQUIRED_RELATIONSHIP_FAMILIES
    relationship_ids = {item["candidate_id"] for item in relationships}
    assert {
        "relationship.decision.uses_policy",
        "relationship.professor.member_of_department",
    } <= relationship_ids
    for relationship in relationships:
        assert relationship["source_type"]
        assert relationship["target_type"]
        assert relationship["direction"] in {"directed", "undirected"}
        assert relationship["roles"]
        assert relationship["evidence_obligation"]
        assert relationship["allowed_state_policy"] == "unresolved_task_6_5"
        assert relationship["time_semantics"] == "unresolved_task_5_5"


def test_every_candidate_has_verified_exact_source_citations() -> None:
    module = _builder()
    catalog = module.build_catalog(repo_root=REPO_ROOT, seed_path=SEED_PATH)

    cited_items = [
        *catalog["shared_projection_fields"],
        *(field for domain in catalog["domains"] for field in domain["fields"]),
        *(
            subobject
            for domain in catalog["domains"]
            for subobject in domain["subobjects"]
        ),
        *catalog["relationships"],
        *catalog["unresolved_records"],
    ]
    assert cited_items
    for item in cited_items:
        assert item["citations"], item["candidate_id"]
        for citation in item["citations"]:
            assert citation["line_start"] > 0
            assert citation["line_end"] >= citation["line_start"]
            assert len(citation["source_sha256"]) == 64
            assert len(citation["excerpt_sha256"]) == 64
            assert citation["excerpt"].strip()

    module.validate_catalog(catalog)


def test_unstable_temporal_and_conflicting_policies_remain_explicitly_unresolved() -> (
    None
):
    catalog = _builder().build_catalog(repo_root=REPO_ROOT, seed_path=SEED_PATH)

    unresolved = {item["candidate_id"]: item for item in catalog["unresolved_records"]}
    assert {
        "unresolved.company_geography_and_foundation_fields",
        "unresolved.professor_inclusion_seed_vs_shenzhen_wording",
        "unresolved.professor_patent_attribution_evidence",
        "unresolved.professor_top_papers_field_vs_derived_relation",
        "unresolved.paper_required_fields_shared_vs_prd_review",
        "unresolved.quality_status_shared_vs_paper",
        "unresolved.relationship_state_catalog",
        "unresolved.relationship_time_catalog",
    } <= set(unresolved)
    assert all(item["resolution"] == "deferred" for item in unresolved.values())

    serialized = json.dumps(catalog, ensure_ascii=False, sort_keys=True)
    assert '"time_semantics": "unresolved_task_5_5"' in serialized
    assert '"allowed_state_policy": "unresolved_task_6_5"' in serialized
    assert '"time_semantics": "validity_interval"' not in serialized
