"""Hermetic contract tests for patent applicant → release company linking.

The linker recovers ``patent_has_applicant`` seeds for patents whose landing
``core_facts.company_ids`` is empty by matching applicant name strings against
released company names.  The invariants under test:

- exact display-name matches (punctuation/case-insensitive) are accepted;
- normalized matches (city prefixes and company suffixes stripped on BOTH
  sides) are accepted;
- any match that resolves to more than one distinct canonical company is
  abstained — a wrong link is worse than no link;
- non-company applicants (universities, institutes, persons) never match.
"""

from __future__ import annotations

import pytest
from src.data_agents.canonical_v2.patent_applicant_linking import (
    ApplicantCompanyResolution,
    CompanyNameEntry,
    build_company_name_index,
    company_name_key,
    normalized_company_name_key,
    resolve_applicant_company,
    resolve_patent_applicant_links,
)


def _entry(
    object_id: str,
    canonical_id: str,
    *names: str,
) -> CompanyNameEntry:
    return CompanyNameEntry(
        object_id=object_id,
        canonical_identity_id=canonical_id,
        names=tuple(names),
    )


def _pudu_index():
    return build_company_name_index(
        (
            _entry(
                "COMP-0A61012B350E",
                "company-c-pudu",
                "深圳市普渡科技有限公司",
                "普渡科技",
            ),
        )
    )


def test_company_name_key_mirrors_source_name_key_semantics() -> None:
    assert company_name_key("奇勃（深圳）科技有限公司") == company_name_key(
        "奇勃(深圳)科技有限公司"
    )
    assert company_name_key("ABC Def") == "abcdef"
    assert company_name_key("") is None
    assert company_name_key("   ") is None
    assert company_name_key(None) is None
    assert company_name_key("（）") is None


def test_normalized_company_name_key_strips_city_prefix_and_company_suffix() -> None:
    assert normalized_company_name_key("深圳市普渡科技有限公司") == "普渡科技"
    assert normalized_company_name_key("上海普渡科技有限责任公司") == "普渡科技"
    assert normalized_company_name_key("北京普渡科技") == "普渡科技"
    assert normalized_company_name_key("广州普渡科技") == "普渡科技"
    assert normalized_company_name_key("普渡科技") == "普渡科技"
    # Parenthesized city infixes are not leading prefixes and must survive.
    assert normalized_company_name_key("奇勃（深圳）科技有限公司") == "奇勃深圳科技"
    # Bare city names and too-short cores are not usable match keys.
    assert normalized_company_name_key("深圳市") is None
    assert normalized_company_name_key("广州云有限公司") is None
    assert normalized_company_name_key("") is None
    assert normalized_company_name_key(None) is None


def test_exact_display_name_match_accepted() -> None:
    resolution = resolve_applicant_company(
        applicant_name="深圳市普渡科技有限公司",
        index=_pudu_index(),
    )
    assert resolution.status == "accepted"
    assert resolution.match_kind == "exact"
    assert resolution.company_object_id == "COMP-0A61012B350E"
    assert resolution.company_canonical_identity_id == "company-c-pudu"
    assert resolution.matched_company_name == "深圳市普渡科技有限公司"


def test_exact_match_tolerates_punctuation_and_case_differences() -> None:
    index = build_company_name_index(
        (
            _entry(
                "COMP-1AE60F680FAC",
                "company-c-qibo",
                "奇勃（深圳）科技有限公司",
                "奇勃（深圳）科技",
            ),
        )
    )
    resolution = resolve_applicant_company(
        applicant_name="奇勃(深圳)科技有限公司",
        index=index,
    )
    assert resolution.status == "accepted"
    assert resolution.match_kind == "exact"
    assert resolution.company_canonical_identity_id == "company-c-qibo"


def test_normalized_match_strips_both_sides() -> None:
    index = build_company_name_index(
        (_entry("COMP-A", "company-c-huan", "深圳市欢创科技有限公司"),)
    )
    for applicant in ("欢创科技", "欢创科技有限公司", "上海欢创科技有限公司"):
        resolution = resolve_applicant_company(
            applicant_name=applicant,
            index=index,
        )
        assert resolution.status == "accepted", applicant
        assert resolution.match_kind == "normalized", applicant
        assert resolution.company_canonical_identity_id == "company-c-huan"


def test_normalized_match_uses_company_normalized_name() -> None:
    resolution = resolve_applicant_company(
        applicant_name="普渡科技有限责任公司",
        index=_pudu_index(),
    )
    assert resolution.status == "accepted"
    assert resolution.match_kind == "normalized"
    assert resolution.company_canonical_identity_id == "company-c-pudu"


def test_ambiguous_normalized_match_abstained() -> None:
    index = build_company_name_index(
        (
            _entry("COMP-SZ", "company-c-lanhu-sz", "深圳市蓝弧科技有限公司"),
            _entry("COMP-BJ", "company-c-lanhu-bj", "北京蓝弧科技有限公司"),
        )
    )
    resolution = resolve_applicant_company(
        applicant_name="蓝弧科技",
        index=index,
    )
    assert resolution.status == "abstained_ambiguous"
    assert resolution.match_kind is None
    assert resolution.company_object_id is None
    assert resolution.candidate_canonical_identity_ids == (
        "company-c-lanhu-bj",
        "company-c-lanhu-sz",
    )


def test_ambiguous_exact_match_abstained() -> None:
    index = build_company_name_index(
        (
            _entry("COMP-1", "company-c-one", "深圳市普渡科技有限公司"),
            _entry("COMP-2", "company-c-two", "深圳市普渡科技有限公司"),
        )
    )
    resolution = resolve_applicant_company(
        applicant_name="深圳市普渡科技有限公司",
        index=index,
    )
    assert resolution.status == "abstained_ambiguous"
    assert resolution.candidate_canonical_identity_ids == (
        "company-c-one",
        "company-c-two",
    )


def test_multiple_objects_merged_into_one_canonical_company_accepted() -> None:
    index = build_company_name_index(
        (
            _entry("COMP-1", "company-c-same", "深圳市普渡科技有限公司"),
            _entry("COMP-2", "company-c-same", "深圳市普渡科技有限公司"),
        )
    )
    resolution = resolve_applicant_company(
        applicant_name="深圳市普渡科技有限公司",
        index=index,
    )
    assert resolution.status == "accepted"
    assert resolution.company_canonical_identity_id == "company-c-same"
    # Deterministic source-object choice for the seed endpoint.
    assert resolution.company_object_id == "COMP-1"


@pytest.mark.parametrize(
    "applicant",
    (
        "哈尔滨工业大学（深圳）",
        "清华大学",
        "深圳先进技术研究院",
        "中国科学院深圳先进技术研究院",
        "深圳市机器人协会",
        "张三",
    ),
)
def test_non_company_applicants_abstained(applicant: str) -> None:
    resolution = resolve_applicant_company(
        applicant_name=applicant,
        index=_pudu_index(),
    )
    assert resolution.status == "abstained_no_match"
    assert resolution.company_object_id is None
    assert resolution.company_canonical_identity_id is None


def test_parenthesized_city_infix_does_not_normalize_away() -> None:
    resolution = resolve_applicant_company(
        applicant_name="普渡科技(北京)有限公司",
        index=_pudu_index(),
    )
    assert resolution.status == "abstained_no_match"


@pytest.mark.parametrize(
    "applicant", ("", "   ", None, 123, ["深圳市普渡科技有限公司"])
)
def test_blank_or_malformed_applicants_abstained(applicant: object) -> None:
    resolution = resolve_applicant_company(
        applicant_name=applicant,
        index=_pudu_index(),
    )
    assert resolution.status == "abstained_no_match"


def test_too_short_normalized_core_abstained() -> None:
    index = build_company_name_index(
        (_entry("COMP-Y", "company-c-yun", "广州云有限公司"),)
    )
    resolution = resolve_applicant_company(applicant_name="云", index=index)
    assert resolution.status == "abstained_no_match"


def test_resolve_patent_applicant_links_preserves_order_and_classes() -> None:
    index = build_company_name_index(
        (
            _entry("COMP-A", "company-c-pudu", "深圳市普渡科技有限公司", "普渡科技"),
            _entry("COMP-SZ", "company-c-lanhu-sz", "深圳市蓝弧科技有限公司"),
            _entry("COMP-BJ", "company-c-lanhu-bj", "北京蓝弧科技有限公司"),
        )
    )
    resolutions = resolve_patent_applicant_links(
        applicant_names=(
            "深圳市普渡科技有限公司",
            "蓝弧科技",
            "哈尔滨工业大学（深圳）",
        ),
        index=index,
    )
    assert [item.status for item in resolutions] == [
        "accepted",
        "abstained_ambiguous",
        "abstained_no_match",
    ]
    assert all(isinstance(item, ApplicantCompanyResolution) for item in resolutions)
    assert resolutions[0].applicant_name == "深圳市普渡科技有限公司"
