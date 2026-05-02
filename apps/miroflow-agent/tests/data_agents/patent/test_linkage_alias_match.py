from __future__ import annotations

from src.data_agents.patent.linkage import link_company_ids


def test_link_company_ids_uses_exact_normalized_then_alias_tiers() -> None:
    links = link_company_ids(
        ["公司A; 深圳市广和通无线股份有限公司; 芯视界传感器（深圳）有限公司"],
        {
            "公司A": "COMP-A",
            "广和通": "COMP-B",
            "感知科技": "COMP-C",
        },
        company_aliases_map={
            "芯视界传感器": "COMP-C",
        },
    )

    assert links == [
        (
            "COMP-A",
            "patent_xlsx_applicant_exact_match",
            "applicants_parsed[0]='公司A' exact match -> COMP-A",
        ),
        (
            "COMP-B",
            "patent_xlsx_applicant_normalized_match",
            "applicants_parsed[1]='深圳市广和通无线股份有限公司' normalized to "
            "'广和通' -> COMP-B",
        ),
        (
            "COMP-C",
            "patent_xlsx_applicant_normalized_match",
            "applicants_parsed[2]='芯视界传感器（深圳）有限公司' normalized to "
            "'芯视界传感器' alias match -> COMP-C",
        ),
    ]


def test_link_company_ids_prefers_normalized_name_match_before_alias_match() -> None:
    links = link_company_ids(
        ["深圳市广和通无线股份有限公司"],
        {"广和通": "COMP-NORMALIZED"},
        company_aliases_map={"广和通": "COMP-ALIAS"},
    )

    assert links == [
        (
            "COMP-NORMALIZED",
            "patent_xlsx_applicant_normalized_match",
            "applicants_parsed[0]='深圳市广和通无线股份有限公司' normalized to "
            "'广和通' -> COMP-NORMALIZED",
        )
    ]


def test_link_company_ids_returns_no_match_when_alias_misses() -> None:
    links = link_company_ids(
        ["未知科技有限公司"],
        {"感知科技": "COMP-C"},
        company_aliases_map={"芯视界传感器": "COMP-C"},
    )

    assert links == []
