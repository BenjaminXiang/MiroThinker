from __future__ import annotations

from src.data_agents.linking import build_normalized_index, link_normalized_values
from src.data_agents.normalization import normalize_company_name
from src.data_agents.patent.linkage import link_company_ids


def test_link_company_ids_splits_mixed_applicant_delimiters_into_tokens():
    links = link_company_ids(
        ["公司A; 公司B；公司C\n公司D"],
        {
            "公司A": "COMP-A",
            "公司B有限公司": "COMP-B",
            "公司C": "COMP-C",
            "公司D": "COMP-D",
        },
    )

    assert [link[0] for link in links] == ["COMP-A", "COMP-B", "COMP-C", "COMP-D"]


def test_link_company_ids_marks_exact_and_normalized_matches():
    links = link_company_ids(
        ["公司A; 深圳市公司B有限公司"],
        {
            "公司A": "COMP-A",
            "公司B": "COMP-B",
        },
    )

    assert links[0][1] == "patent_xlsx_applicant_exact_match"
    assert links[1][1] == "patent_xlsx_applicant_normalized_match"


def test_link_company_ids_populates_bounded_match_reason():
    links = link_company_ids(
        ["深圳市公司B有限公司"],
        {"公司B": "COMP-B"},
    )

    match_reason = links[0][2]
    assert match_reason
    assert len(match_reason) <= 200
    assert "COMP-B" in match_reason


def test_multi_applicant_hit_rate_is_at_least_2x_single_token_baseline():
    applicants = ["公司A; 公司B；公司C\n公司D"]
    company_name_to_id = {
        "公司A": "COMP-A",
        "公司B": "COMP-B",
        "公司C": "COMP-C",
        "公司D": "COMP-D",
    }
    baseline = link_normalized_values(
        applicants,
        build_normalized_index(company_name_to_id, normalizer=normalize_company_name),
        normalizer=normalize_company_name,
    )
    improved = link_company_ids(applicants, company_name_to_id)

    assert len(improved) >= 2 * max(1, len(baseline))
