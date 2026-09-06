"""admit-unanchored-papers (G3): resolved applicant bindings seed
patent_has_applicant relationships. RED evidence for the seeds seam —
the binding merge's canonical ids were invisible to the old seeding paths
(core_facts.company_ids absent for P4 patents; name resolution only saw
released companies).
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module

build = import_module("src.data_agents.canonical_v2.knowledge_build_isolated")

NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


def _company_row(object_id: str) -> object:
    payload = {
        "id": object_id,
        "object_type": "company",
        "core_facts": {"name": "深圳智赛精密装备有限公司"},
    }
    record = build.SourceRecord(
        record_id=f"record:sha256:{'3' * 64}",
        artifact_id="artifact:company-bound",
        source_batch_id="p4-company-full-v1",
        record_locator="companies.jsonl#1",
        parse_run_id="seed-test-run",
        parser_name="historical_jsonl",
        parser_version="v1",
        schema_version="historical-jsonl-record-v1",
        parse_status=build.ParseStatus.parsed,
        payload=payload,
        parsed_at=NOW,
    )
    artifact = build.EvidenceArtifact(
        artifact_id="artifact:company-bound",
        source_kind="historical_jsonl",
        source_locator="companies.jsonl",
        content_sha256="4" * 64,
        byte_size=16,
        acquired_at=NOW,
        run_id="seed-test-run",
    )
    return build._ParsedReleasedObject(
        source_id=build._P4_COMPANY_FULL_SOURCE_ID,
        source_batch_id="p4-company-full-v1",
        record=record,
        artifact=artifact,
        payload=payload,
    )


def _patent_row() -> object:
    payload = {
        "id": "PATENT-BOUND-1",
        "object_type": "patent",
        "core_facts": {"patent_number": "CN100TEST", "applicants": ["深圳智赛精密装备有限公司"]},
    }
    record = build.SourceRecord(
        record_id="record:sha256:" + "1" * 64,
        artifact_id="artifact:patent-bound",
        source_batch_id="p4-patent-full-v1",
        record_locator="patents.jsonl#1",
        parse_run_id="seed-test-run",
        parser_name="historical_jsonl",
        parser_version="v1",
        schema_version="historical-jsonl-record-v1",
        parse_status=build.ParseStatus.parsed,
        payload=payload,
        parsed_at=NOW,
    )
    artifact = build.EvidenceArtifact(
        artifact_id="artifact:patent-bound",
        source_kind="historical_jsonl",
        source_locator="patents.jsonl",
        content_sha256="2" * 64,
        byte_size=16,
        acquired_at=NOW,
        run_id="seed-test-run",
    )
    return build._ParsedReleasedObject(
        source_id=build._P4_PATENT_FULL_SOURCE_ID,
        source_batch_id="p4-patent-full-v1",
        record=record,
        artifact=artifact,
        payload=payload,
    )


def test_resolved_binding_seeds_patent_applicant_relationship() -> None:
    # the seed must carry the SOURCE OBJECT id (the relationship authority
    # maps endpoints via source-released-object:{id}); the binding's
    # canonical id is reverse-mapped inside the seeds function.
    company_object_id = "COMPANY-BOUND-1"
    company_canonical = "company-c-877827059543f86e22bc9c90"
    seeds = build._typed_relationship_seeds(
        source_rows=(_patent_row(), _company_row(company_object_id)),
        canonical_by_source={
            "source-released-object:PATENT-BOUND-1": "patent-c-1",
            f"source-released-object:{company_object_id}": company_canonical,
        },
        canonical_domains={
            "patent-c-1": "patent",
            company_canonical: "company",
        },
        bound_company_ids_by_patent={"PATENT-BOUND-1": (company_canonical,)},
    )
    applicant_seeds = [
        seed
        for seed in seeds
        if seed.relationship_type_id == "patent_has_applicant"
        and seed.target_object_id == company_object_id
    ]
    assert len(applicant_seeds) == 1
    assert applicant_seeds[0].evidence_metadata["match_kind"] == "resolved_binding"


def test_without_binding_mapping_no_applicant_seed_for_p4_patent() -> None:
    seeds = build._typed_relationship_seeds(
        source_rows=(_patent_row(),),
        canonical_by_source={"source-released-object:PATENT-BOUND-1": "patent-c-1"},
        canonical_domains={"patent-c-1": "patent"},
    )
    assert not [
        seed for seed in seeds if seed.relationship_type_id == "patent_has_applicant"
    ]
