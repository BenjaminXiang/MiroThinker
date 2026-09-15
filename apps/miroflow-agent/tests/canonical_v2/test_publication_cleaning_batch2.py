"""D0-b cleaning: venue merging, geography repair, applicants, dead fields.

Samples are verbatim run15 values
(``.agents/runs/data-cleaning-batch1/fixtures/run15-samples.json`` -> ``batch2``).
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from src.data_agents.canonical_v2.publication_cleaning import (
    ApplicantAudit,
    PublicationQualityError,
    PublicationQualityReport,
    assert_publication_quality,
    audit_lookup_documents,
    audit_patent_applicants,
    canonicalize_venue_label,
    canonicalize_venue_reference,
    compose_publication_quality_report,
    derive_company_geography,
    quarantine_records_from_selections,
    venue_canonical_map,
    venue_group_key,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = json.loads(
    (
        REPO_ROOT / ".agents/runs/data-cleaning-batch1/fixtures/run15-samples.json"
    ).read_text(encoding="utf-8")
)["batch2"]


class _Document:
    def __init__(self, domain: str, content: dict[str, Any]) -> None:
        self.domain = domain
        self.lookup_content = json.dumps(content, ensure_ascii=False)


# --------------------------------------------------------------------------
# venue merging
# --------------------------------------------------------------------------
def test_venue_group_key_ignores_case_punctuation_and_prefix_family() -> None:
    venue = FIXTURES["venue"]
    assert venue_group_key(venue["arxiv_qualified"]) == venue_group_key(
        venue["arxiv_plain"]
    )
    assert venue_group_key(venue["plos_upper"]) == venue_group_key(venue["plos_title"])
    assert venue_group_key(venue["year_suffix"]) == venue_group_key("Neurocomputing")
    assert venue_group_key(venue["proceedings_of_the"]) == venue_group_key(
        "AAAI Conference on Artificial Intelligence"
    )
    assert venue_group_key(venue["journal_punct"]) == venue_group_key(
        venue["journal_plain"]
    )


def test_venue_group_key_keeps_distinct_venues_apart() -> None:
    assert venue_group_key("Physical Review Letters") != venue_group_key(
        "Physical Review B"
    )
    assert venue_group_key("Nature Communications") != venue_group_key(
        "Scientific Reports"
    )


def test_canonicalize_venue_label_strips_qualifiers_and_years() -> None:
    venue = FIXTURES["venue"]
    assert canonicalize_venue_label(venue["arxiv_qualified"]) == "arXiv"
    assert canonicalize_venue_label(venue["year_suffix"]) == "Neurocomputing"
    assert (
        canonicalize_venue_label(venue["proceedings_stripped"])
        == "AAAI Conference on Artificial Intelligence"
    )
    assert canonicalize_venue_label("Nature Communications") == "Nature Communications"


def test_venue_map_merges_the_most_frequent_variant() -> None:
    venue = FIXTURES["venue"]
    labels = [venue["arxiv_qualified"]] * 418 + [venue["arxiv_plain"]] * 242
    mapping = venue_canonical_map(labels)
    assert mapping[venue["arxiv_qualified"]] == "arXiv"
    assert mapping[venue["arxiv_plain"]] == "arXiv"


def test_venue_map_is_deterministic_and_order_independent() -> None:
    labels = [
        FIXTURES["venue"]["arxiv_qualified"],
        FIXTURES["venue"]["arxiv_plain"],
    ]
    forward = venue_canonical_map(labels)
    backward = venue_canonical_map(list(reversed(labels)))
    assert forward == backward
    # Equal counts -> lexicographically smallest label wins ("arXiv" is the
    # prefix of the qualified spelling, so it sorts first).
    assert forward[FIXTURES["venue"]["arxiv_qualified"]] == "arXiv"
    assert forward[FIXTURES["venue"]["arxiv_plain"]] == "arXiv"


def test_venue_map_leaves_singletons_alone() -> None:
    mapping = venue_canonical_map([FIXTURES["venue"]["singleton"]])
    assert mapping == {FIXTURES["venue"]["singleton"]: FIXTURES["venue"]["singleton"]}


def test_canonicalize_venue_reference_rewrites_the_label_and_reference() -> None:
    venue = FIXTURES["venue"]
    mapping = venue_canonical_map(
        [venue["arxiv_qualified"]] * 4 + [venue["arxiv_plain"]]
    )
    outcome = canonicalize_venue_reference(
        {"reference_id": "source-reference:old", "name": venue["arxiv_qualified"]},
        mapping,
    )
    assert outcome.disposition == "venue_merged"
    assert outcome.value["name"] == "arXiv"
    assert outcome.value["reference_id"] != "source-reference:old"
    assert outcome.value["reference_id"].startswith("source-reference:")


def test_canonicalize_venue_reference_leaves_singletons_untouched() -> None:
    value = {"reference_id": "source-reference:x", "name": "Nature Communications"}
    outcome = canonicalize_venue_reference(value, venue_canonical_map([value["name"]]))
    assert outcome.value == value
    assert outcome.disposition == "clean"


# --------------------------------------------------------------------------
# dirty geography
# --------------------------------------------------------------------------
def test_stray_separator_is_stripped() -> None:
    outcome = derive_company_geography(FIXTURES["geography_dirty"]["separator"], "")
    assert outcome.value == "开曼群岛"
    assert outcome.disposition == "geography_separator"


def test_city_without_suffix_gains_it_for_a_known_prefecture_city() -> None:
    outcome = derive_company_geography(
        FIXTURES["geography_dirty"]["city_without_suffix"], ""
    )
    assert outcome.value == "广东省-珠海市"
    assert outcome.disposition == "geography_city_suffix"


def test_district_like_tail_is_not_suffixed() -> None:
    outcome = derive_company_geography(
        FIXTURES["geography_dirty"]["district_like_tail"], ""
    )
    assert outcome.value == FIXTURES["geography_dirty"]["district_like_tail"]
    assert outcome.disposition == "clean"


def test_city_only_label_gains_the_province_from_the_address() -> None:
    outcome = derive_company_geography(
        FIXTURES["geography_dirty"]["city_without_province"],
        FIXTURES["geography_dirty"]["province_for_suzhou"],
    )
    assert outcome.value == "江苏省-苏州市"
    assert outcome.disposition == "geography_province"


def test_city_only_label_without_a_province_stays_put_and_is_counted() -> None:
    outcome = derive_company_geography("苏州市", "苏州工业园区星湖街328号")
    assert outcome.value == "苏州市"
    assert outcome.disposition == "geography_unparsed"


def test_final_form_geography_is_not_touched() -> None:
    for label in ("广东省-深圳市", "北京市-北京市", "开曼群岛"):
        outcome = derive_company_geography(label, "深圳市南山区科苑路15号")
        assert outcome.value == label
        assert outcome.disposition == "clean"


# --------------------------------------------------------------------------
# applicants
# --------------------------------------------------------------------------
def test_applicant_audit_counts_bound_unbound_nameless_and_invalid() -> None:
    rows = FIXTURES["applicants"]
    audit = audit_patent_applicants(
        {"applicants": [rows["bound_row"], rows["unbound_row"]]},
        released_company_ids=frozenset({"company-c-1"}),
    )
    assert audit == ApplicantAudit(
        rows=2, bound_rows=1, unbound_rows=1, nameless_rows=0, invalid_binding_rows=0
    )


def test_applicant_audit_flags_nameless_rows_and_invalid_bindings() -> None:
    rows = FIXTURES["applicants"]
    audit = audit_patent_applicants(
        {"applicants": [rows["nameless_row"], rows["invalid_row"]]},
        released_company_ids=frozenset({"company-c-1"}),
    )
    assert audit.nameless_rows == 1
    assert audit.invalid_binding_rows == 1


def test_unbound_but_named_applicants_are_publishable() -> None:
    """The run15 shape (4,951 unbound rows, every one named) must pass the gate."""
    rows = FIXTURES["applicants"]
    report = audit_lookup_documents(
        [
            _Document(
                "patent", {"id": "patent-c-1", "applicants": [rows["unbound_row"]]}
            )
        ],
        released_company_ids=frozenset({"company-c-1"}),
    )
    assert report.applicant_unbound_rows == 1
    assert_publication_quality(report)


def test_gate_refuses_nameless_applicant_rows() -> None:
    rows = FIXTURES["applicants"]
    report = audit_lookup_documents(
        [
            _Document(
                "patent", {"id": "patent-c-1", "applicants": [rows["nameless_row"]]}
            )
        ],
        released_company_ids=frozenset({"company-c-1"}),
    )
    with pytest.raises(PublicationQualityError, match="without any name"):
        assert_publication_quality(report)


def test_gate_refuses_bindings_outside_the_released_company_set() -> None:
    rows = FIXTURES["applicants"]
    report = audit_lookup_documents(
        [
            _Document(
                "patent", {"id": "patent-c-1", "applicants": [rows["invalid_row"]]}
            )
        ],
        released_company_ids=frozenset({"company-c-1"}),
    )
    with pytest.raises(PublicationQualityError, match="released company set"):
        assert_publication_quality(report)


# --------------------------------------------------------------------------
# dead declarations
# --------------------------------------------------------------------------
def test_declared_never_filled_fields_are_measured_per_domain() -> None:
    """The report names every field a domain declares but never fills."""
    report = audit_lookup_documents(
        [
            _Document(
                "company",
                {
                    "id": "company-c-1",
                    "patent_count": None,
                    "products": [],
                    "name": "A",
                },
            ),
            _Document(
                "company",
                {
                    "id": "company-c-2",
                    "patent_count": None,
                    "products": [],
                    "name": "B",
                },
            ),
            _Document("professor", {"id": "professor-c-1", "awards": []}),
            _Document(
                "professor",
                {
                    "id": "professor-c-2",
                    "awards": [{"name": "国家科技进步奖"}],
                },
            ),
        ]
    )
    assert report.declared_never_filled_fields["company"] == (
        "patent_count",
        "products",
    )
    # professor.awards is filled on one document, so it is not "never filled".
    assert "awards" not in report.declared_never_filled_fields["professor"]
    assert report.as_dict()["declared_never_filled_field_count"] == 2
    # Measurement only: it never fails the build.
    assert_publication_quality(report)


def test_never_filled_measurement_ignores_partially_declared_fields() -> None:
    report = audit_lookup_documents(
        [
            _Document("company", {"id": "company-c-1", "patent_count": None}),
            _Document("company", {"id": "company-c-2"}),
        ]
    )
    assert "patent_count" not in report.declared_never_filled_fields.get("company", ())


# --------------------------------------------------------------------------
# quality report
# --------------------------------------------------------------------------
def test_quarantine_records_are_derived_from_the_source_selections() -> None:
    records = quarantine_records_from_selections(
        [
            (
                "professor",
                "professor-c-1",
                "research_directions",
                [
                    {
                        "reference_id": "source-reference:direction-1",
                        "name": FIXTURES["research_direction_nav_block"],
                    },
                    {
                        "reference_id": "source-reference:direction-2",
                        "name": "人工智能",
                    },
                ],
            ),
            (
                "company",
                "company-c-1",
                "profile_summary",
                "多参数监护仪（如DM-7未找到未找到C,DM-8未找到未找到C系列）",
            ),
            ("company", "company-c-2", "profile_summary", "深圳市的工业机器人企业。"),
        ]
    )
    rules = sorted(record.rule for record in records)
    assert rules == ["glue_damage", "layout_block"]
    nav = next(record for record in records if record.rule == "layout_block")
    assert nav.reference_id == "source-reference:direction-1"
    assert nav.canonical_identity_id == "professor-c-1"


def test_compose_publication_quality_report_payload_shape() -> None:
    report = PublicationQualityReport(
        documents=3,
        placeholder_hits=0,
        glue_damaged_values=0,
        glue_legit_values=1,
        geography_total=2,
        geography_city_level=2,
        research_direction_entries=5,
        research_direction_junk=0,
        applicant_rows=4,
        applicant_bound_rows=3,
        applicant_unbound_rows=1,
    )
    records = quarantine_records_from_selections(
        [("company", "company-c-1", "profile_summary", "SBC89未找到")]
    )
    payload = compose_publication_quality_report(
        release_id="candidate-v2-fixture",
        report=report,
        quarantine=records,
    )
    assert payload["schema_version"] == "canonical-v2-publication-quality-report-v1"
    assert payload["release_id"] == "candidate-v2-fixture"
    assert payload["publication_audit"]["documents"] == 3
    assert payload["publication_audit"]["applicant"]["unbound_rows"] == 1
    assert payload["quarantine_by_rule"] == {"glue_damage": 1}
    assert payload["quarantine_records"][0]["value"] == "SBC89未找到"


def test_index_materializer_writes_the_report_outside_the_pack() -> None:
    module = import_module("src.data_agents.canonical_v2.index_projection_isolated")
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert (
        '_PUBLICATION_QUALITY_REPORT_FILENAME = "publication-quality-report.json"'
        in source
    )
    assert "_write_publication_quality_report(" in source
    assert "quarantine_records_from_selections(" in source


def test_build_deduplicates_professor_paper_links() -> None:
    module = import_module("src.data_agents.canonical_v2.knowledge_build_isolated")

    class _Row:
        def __init__(self, link_id: str, professor: str, paper: str) -> None:
            self.payload = {
                "id": link_id,
                "core_facts": {"professor_id": professor, "paper_id": paper},
            }

    rows = [
        _Row("p4-professor-paper-link:aaa", "professor-c-1", "paper-c-1"),
        _Row("PROF-PAPER-LINK-01F0F4DECE25", "professor-c-1", "paper-c-1"),
        _Row("derived-professor-paper-link:bbb", "professor-c-2", "paper-c-2"),
    ]
    kept, dropped = module._dedupe_professor_paper_links(rows)
    assert [row.payload["id"] for row in kept] == [
        "PROF-PAPER-LINK-01F0F4DECE25",
        "derived-professor-paper-link:bbb",
    ]
    assert dropped == ("p4-professor-paper-link:aaa",)


def test_relationship_projection_asserts_edge_uniqueness() -> None:
    module = import_module("src.data_agents.canonical_v2.relationship_projection")
    assert "def _assert_unique_relationship_edges(" in Path(module.__file__).read_text(
        encoding="utf-8"
    )
    module._assert_unique_relationship_edges([])
