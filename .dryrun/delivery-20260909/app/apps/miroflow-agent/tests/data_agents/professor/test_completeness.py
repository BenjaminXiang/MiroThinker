# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.professor.completeness import (
    AGENT_TARGET_FIELDS,
    AGENT_TRIGGER_THRESHOLD,
    assess_completeness,
)
from src.data_agents.professor.cross_domain import CompanyLink, PaperLink, PatentLink
from src.data_agents.professor.models import (
    EducationEntry,
    EnrichedProfessorProfile,
    WorkEntry,
)


def _profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "张三",
        "institution": "南方科技大学",
        "profile_url": "https://example.com/zs",
        "roster_source": "https://www.sustech.edu.cn/",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def test_all_fields_filled_no_agent_trigger():
    profile = _profile(
        department="计算机系",
        title="教授",
        education_structured=[EducationEntry(school="MIT")],
        work_experience=[WorkEntry(organization="Google")],
        awards=["杰青"],
        academic_positions=["IEEE Fellow"],
        projects=["国家重点研发"],
        company_roles=[CompanyLink(company_name="X", role="CTO", source="web_search")],
        patent_ids=[PatentLink(patent_title="Y", source="web_search")],
    )
    result = assess_completeness(profile)
    assert not result.should_trigger_agent
    assert result.gap_weighted_sum == 0.0
    assert result.missing_fields == []


def test_only_regex_fields_triggers_agent():
    profile = _profile(
        department="计算机系",
        title="教授",
    )
    result = assess_completeness(profile)
    assert result.should_trigger_agent
    assert "education_structured" in result.missing_fields
    assert "company_roles" in result.missing_fields
    assert result.gap_weighted_sum > AGENT_TRIGGER_THRESHOLD


def test_threshold_boundary_triggers():
    # company_roles (0.8) alone is >= 0.5 threshold
    profile = _profile(
        department="计算机系",
        title="教授",
        education_structured=[EducationEntry(school="MIT")],
        work_experience=[WorkEntry(organization="Google")],
        awards=["杰青"],
        academic_positions=["IEEE Fellow"],
        projects=["国重"],
        patent_ids=[PatentLink(patent_title="Y", source="ws")],
        # company_roles is missing → weight 0.8 >= threshold 0.5
    )
    result = assess_completeness(profile)
    assert result.should_trigger_agent
    assert result.gap_weighted_sum == 0.8


def test_below_threshold_no_trigger():
    # Only projects (0.4) and academic_positions (0.4) missing = 0.8, wait that's above
    # Only projects (0.4) missing = 0.4 < 0.5
    profile = _profile(
        department="计算机系",
        title="教授",
        education_structured=[EducationEntry(school="MIT")],
        work_experience=[WorkEntry(organization="Google")],
        awards=["杰青"],
        academic_positions=["IEEE Fellow"],
        company_roles=[CompanyLink(company_name="X", role="CTO", source="ws")],
        patent_ids=[PatentLink(patent_title="Y", source="ws")],
        # projects missing → weight 0.4 < 0.5
    )
    result = assess_completeness(profile)
    assert not result.should_trigger_agent
    assert result.gap_weighted_sum == 0.4


def test_priority_fields_sorted_by_weight():
    profile = _profile()  # All optional fields empty
    result = assess_completeness(profile)
    # company_roles (0.8), department (0.8), title (0.8) should be first
    high_weight_fields = {"company_roles", "department", "title"}
    top_three = set(result.priority_fields[:3])
    assert top_three == high_weight_fields


def test_missing_department_and_title_detected():
    profile = _profile(department=None, title=None)
    result = assess_completeness(profile)
    assert "department" in result.missing_fields
    assert "title" in result.missing_fields


def test_empty_string_department_treated_as_missing():
    profile = _profile(department="", title="  ")
    result = assess_completeness(profile)
    assert "department" in result.missing_fields
    assert "title" in result.missing_fields
