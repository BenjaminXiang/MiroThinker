"""D0-a publication cleaning: placeholders, glue damage, geography, directions.

Positive and negative samples are verbatim run15 serving-pack values
(``.agents/runs/data-cleaning-batch1/fixtures/run15-samples.json``); the
counts they belong to are asserted by the offline replay counter
(``.agents/runs/data-cleaning-batch1/count_cleaning_batch1.py``).
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from src.data_agents.canonical_v2 import knowledge_build_isolated
from src.data_agents.canonical_v2.domain_catalog import (
    CATALOG_CONTENT_SHA256,
    CATALOG_SCHEMA_VERSION,
    CATALOG_VERSION,
)
from src.data_agents.canonical_v2.domain_projection_models import (
    CompanyProjection,
    NamedReference,
    ProfessorProjection,
)
from src.data_agents.canonical_v2.publication_cleaning import (
    DISPOSITION_GLUE_KEPT,
    DISPOSITION_GLUE_WITHHELD,
    DISPOSITION_NO_INFORMATION,
    DISPOSITION_PLACEHOLDER,
    GLUE_TOKEN,
    PublicationQualityError,
    audit_lookup_documents,
    audit_projection_payload,
    assert_publication_quality,
    city_label,
    clean_projected_values,
    clean_text,
    derive_company_geography,
    placeholder_family,
    research_direction_rule,
    source_reference_id,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = json.loads(
    (
        REPO_ROOT / ".agents/runs/data-cleaning-batch1/fixtures/run15-samples.json"
    ).read_text(encoding="utf-8")
)


class _Document:
    """Minimal stand-in for a published lookup document."""

    def __init__(self, domain: str, content: dict[str, Any]) -> None:
        self.domain = domain
        self.lookup_content = json.dumps(content, ensure_ascii=False)


# --------------------------------------------------------------------------
# placeholders
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    ["未找到", "-", "–", "N/A", "  null ", "暂无数据", "无", "to be determined"],
)
def test_exact_placeholders_publish_as_absent(value: str) -> None:
    outcome = clean_text(value)
    assert outcome.value is None
    assert outcome.disposition == DISPOSITION_PLACEHOLDER


@pytest.mark.parametrize("value", FIXTURES["build_synthesized_placeholders"])
def test_build_synthesized_placeholders_are_covered(value: str) -> None:
    """The packing gate's own fallbacks must be recognised as placeholders."""
    assert placeholder_family(value) == "prefix"
    assert clean_text(value).value is None


def test_build_gate_literals_stay_pinned() -> None:
    """Pinned to the build constants (import-cycle-free equality test)."""
    assert (
        knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK
        in FIXTURES["build_synthesized_placeholders"]
    )
    assert (
        knowledge_build_isolated._PROFESSOR_PROFILE_SUMMARY_FALLBACK
        in FIXTURES["build_synthesized_placeholders"]
    )


def test_real_values_are_untouched() -> None:
    for value in (
        "深圳市普渡科技有限公司",
        "高电压固态锂金属电池电解质",
        "可用于多种场景的工业机器人研发商",
    ):
        outcome = clean_text(value)
        assert outcome.value == value
        assert outcome.disposition == "clean"


# --------------------------------------------------------------------------
# glue damage
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    [
        FIXTURES["glue_damaged"]["identifier"],
        FIXTURES["glue_damaged"]["version"],
        FIXTURES["glue_damaged"]["version_dot"],
        FIXTURES["glue_damaged"]["whole_token_glued"],
        "XP2未找到2未找到人脸识别测温机；一种基于机器视觉的智慧社区智能安防管理装置（专利）",
        "其服务主要应用于Web3.未找到技术领域的专业人才招聘场景。",
    ],
)
def test_glue_damage_is_withheld_not_guessed(value: str) -> None:
    outcome = clean_text(value)
    assert outcome.value is None
    assert outcome.disposition == DISPOSITION_GLUE_WITHHELD
    assert GLUE_TOKEN in value


def test_prefix_glued_value_is_a_placeholder_family() -> None:
    """The prefix family wins over the glue rule; still published as absent."""
    value = FIXTURES["glue_damaged"]["prefix_glued"]
    outcome = clean_text(value)
    assert outcome.value is None
    assert outcome.disposition == DISPOSITION_PLACEHOLDER


@pytest.mark.parametrize(
    "value",
    [
        FIXTURES["glue_legit_prose"]["patent_abstract"],
        FIXTURES["glue_legit_prose"]["self_declared_absence"],
    ],
)
def test_glue_in_legitimate_prose_is_kept(value: str) -> None:
    outcome = clean_text(value)
    assert outcome.value == value
    assert outcome.disposition == DISPOSITION_GLUE_KEPT


# --------------------------------------------------------------------------
# no-information sentences
# --------------------------------------------------------------------------
def test_pure_no_information_sentence_is_absent() -> None:
    outcome = clean_text(FIXTURES["no_information_sentence"]["pure"])
    assert outcome.value is None
    assert outcome.disposition == DISPOSITION_NO_INFORMATION


def test_no_information_sentence_with_content_is_kept() -> None:
    value = FIXTURES["no_information_sentence"]["with_content"]
    assert clean_text(value).value == value


# --------------------------------------------------------------------------
# geography
# --------------------------------------------------------------------------
def test_province_only_geography_is_filled_from_registered_address() -> None:
    outcome = derive_company_geography(
        FIXTURES["geography"]["company_named_reference"],
        FIXTURES["geography"]["registered_address"],
    )
    assert outcome.disposition == "geography_derived"
    assert outcome.value["name"] == "广东省-深圳市"
    assert outcome.value["reference_id"] == source_reference_id("广东省-深圳市")


def test_province_prefixed_address_does_not_swallow_the_province() -> None:
    outcome = derive_company_geography(
        "广东省", FIXTURES["geography"]["registered_address_with_province"]
    )
    assert outcome.value == "广东省-深圳市"


def test_city_label_handles_province_and_autonomous_region() -> None:
    assert city_label("广东省深圳市南山区科苑路15号") == "深圳市"
    assert city_label("新疆维吾尔自治区乌鲁木齐市天山区") == "乌鲁木齐市"
    assert city_label("无地址信息") is None


@pytest.mark.parametrize(
    "geography,address",
    [
        (
            FIXTURES["geography"]["city_level"],
            FIXTURES["geography"]["registered_address"],
        ),
        (None, FIXTURES["geography"]["registered_address"]),
        ("广东省", ""),
    ],
)
def test_geography_left_alone_when_not_province_only_or_unparseable(
    geography: Any, address: str
) -> None:
    outcome = derive_company_geography(geography, address)
    assert outcome.value == geography


# --------------------------------------------------------------------------
# research directions
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "key,rule",
    [
        ("nav_block", "layout_block"),
        ("glued_nav_block", "layout_block"),
        ("layout_dump_with_dates", "layout_block"),
        ("sentence_fragment", "sentence_fragment"),
        ("truncated_tail", "truncated_tail"),
        ("too_short", "too_short"),
        ("dated_dump", "dated_dump"),
    ],
)
def test_research_direction_junk_rules(key: str, rule: str) -> None:
    assert research_direction_rule(FIXTURES["research_directions"][key]) == rule


@pytest.mark.parametrize(
    "key", ["clean_short", "clean_slash", "clean_phrase", "clean_bilingual_long"]
)
def test_research_direction_clean_values_survive(key: str) -> None:
    assert research_direction_rule(FIXTURES["research_directions"][key]) is None


# --------------------------------------------------------------------------
# whole-payload cleaning
# --------------------------------------------------------------------------
def _company_payload() -> dict[str, Any]:
    return {
        "id": "company-c-fixture",
        "entity_type": "company",
        "name": "深圳市普渡科技有限公司",
        "normalized_name": "深圳市普渡科技有限公司",
        "profile_summary": FIXTURES["glue_damaged"]["identifier"],
        "technology_route_summary": "未找到",
        "product_description": FIXTURES["no_information_sentence"]["pure"],
        "team_description": "核心团队来自知名高校。",
        "geography": {
            "reference_id": "source-reference:province",
            "name": "广东省",
        },
        "registered_address": FIXTURES["geography"]["registered_address"],
        "website": "-",
        "industry": {"reference_id": "source-reference:industry", "name": "机器人"},
        "tech_tags": [
            {"reference_id": "source-reference:tag-1", "name": "未找到"},
            {"reference_id": "source-reference:tag-2", "name": "配送机器人"},
        ],
    }


def test_company_payload_cleaning_withholds_and_derives() -> None:
    cleaned, records = clean_projected_values(
        "company", _company_payload(), canonical_identity_id="company-c-fixture"
    )
    assert cleaned["profile_summary"] is None
    assert cleaned["technology_route_summary"] is None
    assert cleaned["product_description"] is None
    assert cleaned["team_description"] == "核心团队来自知名高校。"
    assert cleaned["website"] is None
    assert cleaned["geography"]["name"] == "广东省-深圳市"
    assert cleaned["tech_tags"] == [
        {"reference_id": "source-reference:tag-2", "name": "配送机器人"}
    ]
    withheld = [item for item in records if item.rule == DISPOSITION_GLUE_WITHHELD]
    assert [item.field_path for item in withheld] == ["profile_summary"]
    # the withheld text is preserved verbatim for D1 review, never destroyed
    assert withheld[0].value == FIXTURES["glue_damaged"]["identifier"]
    assert withheld[0].canonical_identity_id == "company-c-fixture"


def test_cleaned_company_payload_validates_against_the_projection_model() -> None:
    cleaned, _ = clean_projected_values("company", _company_payload())
    model = CompanyProjection.model_validate(
        {
            **cleaned,
            "canonical_identity_id": "company-c-fixture",
            "identity_decision_id": "identity-decision:fixture",
            "inclusion_decision_id": "inclusion:fixture",
            "projection_version": "domain-projection-v1",
            "catalog_schema_version": CATALOG_SCHEMA_VERSION,
            "catalog_version": CATALOG_VERSION,
            "catalog_content_sha256": CATALOG_CONTENT_SHA256,
            "as_of": "2026-09-15T00:00:00+00:00",
            "last_updated": "2026-09-15T00:00:00+00:00",
            "quality_status": "partial",
            "run_id": "fixture-run",
            "content_sha256": "0" * 64,
            "release_id": "candidate-fixture",
            "field_lineage": [
                {
                    "field_path": "profile_summary",
                    "decision_id": "decision:fixture",
                    "supporting_assertion_ids": ["assertion:fixture"],
                }
            ],
            "evidence": [
                {
                    "assertion_id": "assertion:fixture",
                    "decision_id": "decision:fixture",
                    "field_path": "profile_summary",
                }
            ],
        },
        context={"allow_unbound_projection_hash": True},
    )
    assert model.profile_summary is None
    assert model.technology_route_summary is None
    assert model.geography == NamedReference(
        reference_id=source_reference_id("广东省-深圳市"), name="广东省-深圳市"
    )


def test_professor_payload_drops_junk_directions_and_placeholders() -> None:
    payload = {
        "id": "professor-c-fixture",
        "entity_type": "professor",
        "name": "张三",
        "canonical_name_zh": "张三",
        "institution": "南方科技大学",
        "department": {
            "reference_id": "source-reference:dept",
            "name": knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK,
        },
        "title": knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK,
        "email": knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK,
        "homepage": knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK,
        "profile_summary": knowledge_build_isolated._PROFESSOR_PROFILE_SUMMARY_FALLBACK,
        "paper_summary": knowledge_build_isolated._PROFESSOR_PROFILE_SUMMARY_FALLBACK,
        "patent_summary": knowledge_build_isolated._PROFESSOR_PROFILE_SUMMARY_FALLBACK,
        "research_directions": [
            {
                "reference_id": "source-reference:direction-1",
                "name": FIXTURES["research_directions"]["nav_block"],
            },
            {
                "reference_id": "source-reference:direction-2",
                "name": FIXTURES["research_directions"]["clean_short"],
            },
            {
                "reference_id": "source-reference:direction-3",
                "name": FIXTURES["research_directions"]["too_short"],
            },
        ],
    }
    cleaned, records = clean_projected_values(
        "professor", payload, canonical_identity_id="professor-c-fixture"
    )
    assert cleaned["department"] is None
    assert cleaned["title"] is None
    assert cleaned["email"] is None
    assert cleaned["homepage"] is None
    assert cleaned["profile_summary"] is None
    assert cleaned["paper_summary"] is None
    assert cleaned["patent_summary"] is None
    assert cleaned["research_directions"] == [
        {"reference_id": "source-reference:direction-2", "name": "人工智能"}
    ]
    dropped = {item.value: item for item in records}
    assert dropped["1"].rule == "too_short"
    assert dropped[FIXTURES["research_directions"]["nav_block"]].rule == "layout_block"
    assert dropped["1"].reference_id == "source-reference:direction-3", (
        "quarantined values stay traceable to their source reference"
    )


def test_cleaned_professor_payload_validates_against_the_projection_model() -> None:
    payload = {
        "canonical_identity_id": "professor-c-fixture",
        "identity_decision_id": "identity-decision:fixture",
        "inclusion_decision_id": "inclusion:fixture",
        "projection_version": "domain-projection-v1",
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_version": CATALOG_VERSION,
        "catalog_content_sha256": CATALOG_CONTENT_SHA256,
        "as_of": "2026-09-15T00:00:00+00:00",
        "last_updated": "2026-09-15T00:00:00+00:00",
        "quality_status": "partial",
        "run_id": "fixture-run",
        "content_sha256": "0" * 64,
        "release_id": "candidate-fixture",
        "field_lineage": [
            {
                "field_path": "title",
                "decision_id": "decision:fixture",
                "supporting_assertion_ids": ["assertion:fixture"],
            }
        ],
        "evidence": [
            {
                "assertion_id": "assertion:fixture",
                "decision_id": "decision:fixture",
                "field_path": "title",
            }
        ],
        "id": "professor-c-fixture",
        "name": "张三",
        "canonical_name_zh": "张三",
        "institution": "南方科技大学",
        "department": None,
        "title": None,
        "email": None,
        "homepage": None,
        "profile_summary": None,
        "paper_summary": None,
        "patent_summary": None,
        "research_directions": [],
        "patent_ids": [],
    }
    model = ProfessorProjection.model_validate(
        payload, context={"allow_unbound_projection_hash": True}
    )
    assert model.paper_summary is None
    assert model.department is None


# --------------------------------------------------------------------------
# audit + gate
# --------------------------------------------------------------------------
def test_audit_counts_findings_and_gate_passes_clean_documents() -> None:
    documents = [
        _Document("company", _company_payload()),
        _Document("professor", {"id": "p1", "research_directions": []}),
    ]
    report = audit_lookup_documents(documents)
    assert report.documents == 2
    assert report.placeholder_hits == 4
    assert report.glue_damaged_values == 1
    assert report.geography_total == 1
    assert report.geography_city_level == 0
    assert_publication_quality(
        audit_lookup_documents(
            [
                _Document(
                    "company",
                    {
                        **clean_projected_values("company", _company_payload())[0],
                        "geography": {
                            "reference_id": source_reference_id("广东省-深圳市"),
                            "name": "广东省-深圳市",
                        },
                    },
                )
            ]
        )
    )


def test_gate_refuses_to_publish_placeholder_text() -> None:
    report = audit_lookup_documents(
        [_Document("company", {"id": "c1", "profile_summary": "未找到"})]
    )
    with pytest.raises(PublicationQualityError, match="placeholder"):
        assert_publication_quality(report)


def test_gate_failure_names_its_offenders() -> None:
    report = audit_lookup_documents(
        [_Document("company", {"id": "c1", "profile_summary": "未找到"})]
    )
    assert report.placeholder_examples == ("company.profile_summary: 未找到",)
    with pytest.raises(PublicationQualityError) as excinfo:
        assert_publication_quality(report)
    assert "company.profile_summary: 未找到" in str(excinfo.value)


def test_paper_venue_placeholder_reference_is_not_published() -> None:
    """A placeholder venue reference (the P4 salvage fallback) never publishes."""
    cleaned, _ = clean_projected_values(
        "paper",
        {
            "venue": {
                "reference_id": source_reference_id("未提供期刊出处"),
                "name": "未提供期刊出处",
            }
        },
    )
    assert cleaned.get("venue") is None
    report = audit_lookup_documents([_Document("paper", {"id": "paper-1", **cleaned})])
    assert report.placeholder_hits == 0


def test_every_build_fallback_literal_is_recognized_by_the_cleaner() -> None:
    """Every build-side fallback sentence must be placeholder-family text.

    The build writes fallback values into landed records when a source has no
    value (`_P4_PAPER_VENUE_FALLBACK` and friends); the cleaning rules are what
    keep them out of the pack, so a new literal must be classified too.
    """
    literals = {
        name: value
        for name, value in vars(knowledge_build_isolated).items()
        if name.endswith("_FALLBACK") and isinstance(value, str)
    }
    assert literals
    for name, value in sorted(literals.items()):
        assert placeholder_family(value) is not None, name


def test_gate_refuses_research_direction_junk_and_thin_geography() -> None:
    report = audit_lookup_documents(
        [
            _Document(
                "professor",
                {
                    "id": "p1",
                    "research_directions": [
                        {"name": FIXTURES["research_directions"]["truncated_tail"]}
                    ],
                },
            ),
            _Document(
                "company",
                {
                    "id": "c1",
                    "geography": {
                        "reference_id": "source-reference:province",
                        "name": "广东省",
                    },
                },
            ),
        ]
    )
    with pytest.raises(PublicationQualityError) as excinfo:
        assert_publication_quality(report)
    message = str(excinfo.value)
    assert "research-direction junk" in message
    assert "city-level ratio" in message


def test_audit_reports_nothing_for_clean_payloads() -> None:
    findings = audit_projection_payload(
        "company",
        {
            "profile_summary": "深圳市普渡科技，配送机器人。",
            "tech_tags": [{"name": "配送机器人"}],
        },
    )
    assert findings == {
        "placeholder_hits": 0,
        "glue_damaged_values": 0,
        "glue_legit_values": 0,
        "research_direction_entries": 0,
        "research_direction_junk": 0,
    }


def test_index_projection_gate_is_wired_into_the_build() -> None:
    module = import_module("src.data_agents.canonical_v2.index_projection")
    assert module.assert_publication_quality is assert_publication_quality
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "assert_publication_quality(publication_report)" in source
    assert "publication_report = audit_lookup_documents(" in source
