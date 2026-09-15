"""admit-unanchored-papers (G3) + C1: resolved applicant bindings seed
patent_has_applicant relationships.

The seeds must be built from the **mapped admitted-object universe**
(``_map_public_authority``'s ``row_by_object``), not from the raw landed rows:
only the released-objects source lands in released-object payload shape, every
supplemental batch keeps its native keys (``patent_id`` / ``company_name``) and
is turned into a released object only by ``_merge_p4_created_rows``.  Indexing
raw rows cut the run15 relationship layer to 123 of the 7,611 document-layer
bindings (C1).
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


COMPANY_OBJECT_ID = "COMPANY-BOUND-1"
COMPANY_CANONICAL = "company-c-877827059543f86e22bc9c90"


def _mapped_universe() -> dict[str, object]:
    patent = _patent_row()
    company = _company_row(COMPANY_OBJECT_ID)
    return {patent.payload["id"]: patent, COMPANY_OBJECT_ID: company}


def test_resolved_binding_seeds_patent_applicant_relationship() -> None:
    # the seed must carry the SOURCE OBJECT id (the relationship authority
    # maps endpoints via source-released-object:{id}); the binding's
    # canonical id is reverse-mapped inside the seeds function.
    seeds = build._typed_relationship_seeds(
        object_rows_by_id=_mapped_universe(),
        supplemental_rows=(),
        canonical_by_source={
            "source-released-object:PATENT-BOUND-1": "patent-c-1",
            f"source-released-object:{COMPANY_OBJECT_ID}": COMPANY_CANONICAL,
        },
        canonical_domains={
            "patent-c-1": "patent",
            COMPANY_CANONICAL: "company",
        },
        bound_company_ids_by_patent={"PATENT-BOUND-1": (COMPANY_CANONICAL,)},
    )
    applicant_seeds = [
        seed
        for seed in seeds
        if seed.relationship_type_id == "patent_has_applicant"
        and seed.target_object_id == COMPANY_OBJECT_ID
    ]
    assert len(applicant_seeds) == 1
    assert applicant_seeds[0].evidence_metadata["match_kind"] == "resolved_binding"


def test_without_binding_mapping_no_applicant_seed_for_p4_patent() -> None:
    seeds = build._typed_relationship_seeds(
        object_rows_by_id={"PATENT-BOUND-1": _patent_row()},
        supplemental_rows=(),
        canonical_by_source={"source-released-object:PATENT-BOUND-1": "patent-c-1"},
        canonical_domains={"patent-c-1": "patent"},
    )
    assert not [
        seed for seed in seeds if seed.relationship_type_id == "patent_has_applicant"
    ]


def test_raw_landing_rows_are_not_a_seed_universe() -> None:
    """C1 RED: the raw supplemental rows must not be treated as objects.

    ``p4-patent-full-v1`` / ``p4-company-full-v1`` rows key their identity as
    ``patent_id`` / ``company_name``; only the mapped universe carries the
    synthesized released-object payload.  Before the fix the seeds indexed the
    raw rows, so this binding produced nothing.
    """
    universe = _mapped_universe()
    binding = {
        "source-released-object:PATENT-BOUND-1": "patent-c-1",
        f"source-released-object:{COMPANY_OBJECT_ID}": COMPANY_CANONICAL,
    }
    domains = {"patent-c-1": "patent", COMPANY_CANONICAL: "company"}

    # mapped universe → seeded
    from_universe = build._typed_relationship_seeds(
        object_rows_by_id=universe,
        supplemental_rows=(),
        canonical_by_source=binding,
        canonical_domains=domains,
        bound_company_ids_by_patent={"PATENT-BOUND-1": (COMPANY_CANONICAL,)},
    )
    # raw rows passed where only the universe belongs → nothing
    patent = _patent_row()
    company = _company_row(COMPANY_OBJECT_ID)
    raw_payload_rows = {
        patent.payload["id"]: build._ParsedReleasedObject(
            source_id=patent.source_id,
            source_batch_id=patent.source_batch_id,
            record=patent.record,
            artifact=patent.artifact,
            payload={"patent_id": patent.payload["id"], "applicants": ["x"]},
        ),
        COMPANY_OBJECT_ID: build._ParsedReleasedObject(
            source_id=company.source_id,
            source_batch_id=company.source_batch_id,
            record=company.record,
            artifact=company.artifact,
            payload={"company_name": "深圳智赛精密装备有限公司"},
        ),
    }
    from_raw_rows = build._typed_relationship_seeds(
        object_rows_by_id=raw_payload_rows,
        supplemental_rows=(),
        canonical_by_source=binding,
        canonical_domains=domains,
        bound_company_ids_by_patent={"PATENT-BOUND-1": (COMPANY_CANONICAL,)},
    )
    assert len(from_universe) == 1
    assert not from_raw_rows
