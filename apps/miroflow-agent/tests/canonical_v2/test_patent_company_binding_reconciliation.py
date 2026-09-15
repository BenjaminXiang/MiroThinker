"""C1 / D0: the document↔relationship applicant-binding caliber must be checked.

The document layer (patents' ``applicants[].canonical_company_id`` field
assertions, served directly by the G3-simple scan) and the relationship layer
(``patent_has_applicant`` edges) describe the same fact.  run15 shipped 123
edges against 7,042 bound patents because the seed stage indexed raw landing
rows instead of the mapped object universe; these tests lock the reconciliation
that makes that impossible to ship again.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib import import_module

build = import_module("src.data_agents.canonical_v2.knowledge_build_isolated")

NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)

PATENT_OBJECT_ID = "PAT-002AF039E85C"
COMPANY_OBJECT_ID = "COMP-0204DFDE8E12"
PATENT_CANONICAL = "patent-c-d68059d3e421131d18d0664d"
COMPANY_CANONICAL = "company-c-be3bebaa74536edff6e2a879"
UNINDEXED_COMPANY_CANONICAL = "company-c-0000000000000000000000"


def _row(
    *,
    object_id: str,
    object_type: str,
    core_facts: dict[str, object],
    source_id: str,
    seed: str,
) -> object:
    payload = {"id": object_id, "object_type": object_type, "core_facts": core_facts}
    record = build.SourceRecord(
        record_id=f"record:sha256:{seed * 64}",
        artifact_id=f"artifact:{object_type}",
        source_batch_id="p4-full-v1",
        record_locator=f"{object_type}.jsonl#1",
        parse_run_id="c1-run",
        parser_name="historical_jsonl",
        parser_version="v1",
        schema_version="historical-jsonl-record-v1",
        parse_status=build.ParseStatus.parsed,
        payload=payload,
        parsed_at=NOW,
    )
    artifact = build.EvidenceArtifact(
        artifact_id=f"artifact:{object_type}",
        source_kind="historical_jsonl",
        source_locator=f"{object_type}.jsonl",
        content_sha256=seed * 64,
        byte_size=16,
        acquired_at=NOW,
        run_id="c1-run",
    )
    return build._ParsedReleasedObject(
        source_id=source_id,
        source_batch_id="p4-full-v1",
        record=record,
        artifact=artifact,
        payload=payload,
    )


def _universe() -> dict[str, object]:
    patent = _row(
        object_id=PATENT_OBJECT_ID,
        object_type="patent",
        core_facts={"patent_number": "CN100TEST", "applicants": []},
        source_id=build._P4_PATENT_FULL_SOURCE_ID,
        seed="1",
    )
    company = _row(
        object_id=COMPANY_OBJECT_ID,
        object_type="company",
        core_facts={"name": "中建钢构股份有限公司"},
        source_id=build._P4_COMPANY_FULL_SOURCE_ID,
        seed="2",
    )
    return {patent.payload["id"]: patent, COMPANY_OBJECT_ID: company}


CANONICAL_BY_SOURCE = {
    f"source-released-object:{PATENT_OBJECT_ID}": PATENT_CANONICAL,
    f"source-released-object:{COMPANY_OBJECT_ID}": COMPANY_CANONICAL,
}
CANONICAL_DOMAINS = {PATENT_CANONICAL: "patent", COMPANY_CANONICAL: "company"}


def _seeds() -> tuple[object, ...]:
    return build._typed_relationship_seeds(
        object_rows_by_id=_universe(),
        supplemental_rows=(),
        canonical_by_source=CANONICAL_BY_SOURCE,
        canonical_domains=CANONICAL_DOMAINS,
        bound_company_ids_by_patent={PATENT_OBJECT_ID: (COMPANY_CANONICAL,)},
    )


def _ledger(captured: str) -> dict[str, object]:
    line = next(
        item
        for item in captured.splitlines()
        if item.startswith("PATENT_COMPANY_BINDING_LEDGER ")
    )
    return json.loads(line.removeprefix("PATENT_COMPANY_BINDING_LEDGER "))


def test_reconciliation_accepts_a_fully_projected_document_layer(capsys) -> None:
    seeds = _seeds()
    assert len(seeds) == 1
    build._reconcile_patent_company_bindings(
        bound_company_ids_by_patent={PATENT_OBJECT_ID: (COMPANY_CANONICAL,)},
        seed_object_rows=build._relationship_seed_object_rows(_universe()),
        canonical_by_source=CANONICAL_BY_SOURCE,
        typed_seeds=seeds,
    )
    ledger = _ledger(capsys.readouterr().out)
    assert ledger["document_binding_pairs"] == 1
    assert ledger["document_bound_patents"] == 1
    assert ledger["document_bound_companies"] == 1
    assert ledger["seeded_pairs"] == 1
    assert ledger["unindexed_pairs"] == 0
    assert ledger["unexplained_missing"] == 0
    assert ledger["seed_lanes"] == {"resolved_binding": 1}
    assert ledger["typed_seed_types"] == {"patent_has_applicant": 1}


def test_reconciliation_raises_when_a_document_binding_is_unseeded(capsys) -> None:
    # the document layer claims a binding the seed stage never produced and
    # whose endpoints ARE admitted objects: this is the C1 defect class.
    seeds = build._typed_relationship_seeds(
        object_rows_by_id=_universe(),
        supplemental_rows=(),
        canonical_by_source=CANONICAL_BY_SOURCE,
        canonical_domains=CANONICAL_DOMAINS,
    )
    assert not seeds
    try:
        build._reconcile_patent_company_bindings(
            bound_company_ids_by_patent={PATENT_OBJECT_ID: (COMPANY_CANONICAL,)},
            seed_object_rows=build._relationship_seed_object_rows(_universe()),
            canonical_by_source=CANONICAL_BY_SOURCE,
            typed_seeds=seeds,
        )
    except build.IsolatedKnowledgeBuildError as exc:
        assert "not projected as patent_has_applicant" in str(exc)
        assert PATENT_CANONICAL in str(exc)
    else:
        raise AssertionError("unseeded document binding must fail the build")
    ledger = _ledger(capsys.readouterr().out)
    assert ledger["unexplained_missing"] == 1
    assert ledger["unindexed_pairs"] == 0
    assert ledger["unexplained_missing_sample"] == [
        [PATENT_CANONICAL, COMPANY_CANONICAL]
    ]


def test_reconciliation_counts_an_unindexed_company_as_explainable(capsys) -> None:
    # a binding whose company never became an admitted object cannot be
    # projected: counted, not fatal.
    build._reconcile_patent_company_bindings(
        bound_company_ids_by_patent={
            PATENT_OBJECT_ID: (UNINDEXED_COMPANY_CANONICAL,),
        },
        seed_object_rows=build._relationship_seed_object_rows(_universe()),
        canonical_by_source=CANONICAL_BY_SOURCE,
        typed_seeds=(),
    )
    ledger = _ledger(capsys.readouterr().out)
    assert ledger["document_binding_pairs"] == 1
    assert ledger["seeded_pairs"] == 0
    assert ledger["unindexed_pairs"] == 1
    assert ledger["unexplained_missing"] == 0


def test_seed_object_universe_indexes_the_mapped_object_rows() -> None:
    universe = _universe()
    indexed = build._relationship_seed_object_rows(universe)
    assert set(indexed) == {PATENT_OBJECT_ID, COMPANY_OBJECT_ID}
