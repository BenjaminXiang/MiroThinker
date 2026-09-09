# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.agent_enrichment import (
    AgentOutputModel,
    build_agent_prompt,
    _merge_agent_output,
    run_agent_enrichment,
)
from src.data_agents.professor.cross_domain import CompanyLink
from src.data_agents.professor.models import (
    EducationEntry,
    EnrichedProfessorProfile,
    WorkEntry,
)


def _profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "张三",
        "institution": "南方科技大学",
        "department": None,
        "title": None,
        "research_directions": ["大语言模型"],
        "profile_url": "https://example.com",
        "roster_source": "https://example.com",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def _mock_llm(response_text: str) -> MagicMock:
    mock = MagicMock()
    choice = SimpleNamespace(message=SimpleNamespace(content=response_text))
    mock.chat.completions.create.return_value = SimpleNamespace(choices=[choice])
    return mock


def _valid_agent_output() -> str:
    return json.dumps({
        "education_structured": [
            {"school": "清华大学", "degree": "博士", "field": "计算机科学", "end_year": 2010}
        ],
        "work_experience": [
            {"organization": "微软亚洲研究院", "role": "研究员", "start_year": 2010, "end_year": 2015}
        ],
        "awards": ["国家杰青"],
        "company_roles": [
            {"company_name": "深圳AI科技", "role": "首席科学家", "source": "web_search"}
        ],
        "department": "计算机系",
        "title": "教授",
    }, ensure_ascii=False)


def test_build_agent_prompt_includes_known_fields():
    profile = _profile(
        research_directions=["大语言模型", "RLHF"],
        h_index=45,
    )
    prompt = build_agent_prompt(profile, ["education_structured", "department"], "")
    assert "张三" in prompt
    assert "大语言模型" in prompt
    assert "education_structured" in prompt
    assert "department" in prompt
    assert "45" in prompt


def test_build_agent_prompt_lists_only_missing_fields():
    profile = _profile()
    prompt = build_agent_prompt(profile, ["education_structured"], "")
    assert "education_structured" in prompt
    # The gap list section should only contain the explicitly listed missing fields
    lines = prompt.split("\n")
    gap_section = False
    gap_lines = []
    for line in lines:
        if "待补全字段" in line:
            gap_section = True
            continue
        if gap_section and line.startswith("##"):
            break
        if gap_section and line.strip().startswith("- "):
            gap_lines.append(line.strip())
    assert any("education_structured" in g for g in gap_lines)
    assert not any("company_roles" in g for g in gap_lines)


@pytest.mark.asyncio
async def test_agent_with_valid_output_updates_profile():
    profile = _profile()
    llm = _mock_llm(_valid_agent_output())
    result = await run_agent_enrichment(
        profile=profile,
        missing_fields=["education_structured", "department"],
        html_text="",
        local_llm_client=llm,
        local_llm_model="test",
    )
    assert result.enrichment_source == "agent_local"
    assert len(result.profile.education_structured) == 1
    assert result.profile.department == "计算机系"
    assert result.profile.education_structured[0].school == "清华大学"


@pytest.mark.asyncio
async def test_local_fails_escalates_to_online():
    profile = _profile()
    local_llm = MagicMock()
    local_llm.chat.completions.create.side_effect = RuntimeError("Local LLM down")
    online_llm = _mock_llm(_valid_agent_output())

    result = await run_agent_enrichment(
        profile=profile,
        missing_fields=["education_structured"],
        html_text="",
        local_llm_client=local_llm,
        local_llm_model="local",
        online_llm_client=online_llm,
        online_llm_model="online",
    )
    assert result.enrichment_source == "agent_online"
    assert len(result.profile.education_structured) == 1


@pytest.mark.asyncio
async def test_both_tiers_fail_returns_original():
    profile = _profile()
    local_llm = MagicMock()
    local_llm.chat.completions.create.side_effect = RuntimeError("fail")
    online_llm = MagicMock()
    online_llm.chat.completions.create.side_effect = RuntimeError("fail")

    result = await run_agent_enrichment(
        profile=profile,
        missing_fields=["education_structured"],
        html_text="",
        local_llm_client=local_llm,
        local_llm_model="local",
        online_llm_client=online_llm,
        online_llm_model="online",
    )
    # Original profile returned
    assert result.profile.education_structured == []


@pytest.mark.asyncio
async def test_agent_drops_invalid_company_roles_instead_of_failing_whole_output():
    profile = _profile()
    llm = _mock_llm(json.dumps({
        "company_roles": [
            {"company_name": "深圳AI科技", "role": None, "source": "web_search"},
            {"company_name": "深圳AI科技", "role": "首席科学家", "source": "web_search"}
        ],
        "department": "计算机系"
    }, ensure_ascii=False))

    result = await run_agent_enrichment(
        profile=profile,
        missing_fields=["company_roles", "department"],
        html_text="",
        local_llm_client=llm,
        local_llm_model="test",
    )

    assert result.enrichment_source == "agent_local"
    assert result.profile.department == "计算机系"
    assert len(result.profile.company_roles) == 1
    assert result.profile.company_roles[0].company_name == "深圳AI科技"
    assert result.profile.company_roles[0].role == "首席科学家"


@pytest.mark.asyncio
async def test_agent_drops_invalid_education_entries_instead_of_failing_whole_output():
    profile = _profile()
    llm = _mock_llm(json.dumps({
        "education_structured": [
            {"school": None, "degree": "博士"},
            {"school": "清华大学", "degree": "博士", "field": "计算机科学"}
        ],
        "department": "计算机系"
    }, ensure_ascii=False))

    result = await run_agent_enrichment(
        profile=profile,
        missing_fields=["education_structured", "department"],
        html_text="",
        local_llm_client=llm,
        local_llm_model="test",
    )

    assert result.enrichment_source == "agent_local"
    assert result.profile.department == "计算机系"
    assert [item.school for item in result.profile.education_structured] == ["清华大学"]


@pytest.mark.asyncio
async def test_agent_does_not_overwrite_existing_fields():
    profile = _profile(
        department="已有院系",
        education_structured=[EducationEntry(school="已有学校")],
    )
    output = json.dumps({
        "education_structured": [{"school": "新学校"}],
        "department": "新院系",
        "title": "教授",
    })
    llm = _mock_llm(output)

    result = await run_agent_enrichment(
        profile=profile,
        missing_fields=["title"],
        html_text="",
        local_llm_client=llm,
        local_llm_model="test",
    )
    # Existing fields preserved
    assert result.profile.department == "已有院系"
    assert result.profile.education_structured[0].school == "已有学校"
    # New field filled
    assert result.profile.title == "教授"


def test_merge_agent_output_preserves_distinct_school_and_organization_entries():
    profile = _profile(
        education_structured=[EducationEntry(school="MIT", degree="博士")],
        work_experience=[WorkEntry(organization="微软亚洲研究院", role="研究员")],
    )
    output = AgentOutputModel(
        education_structured=[
            EducationEntry(school="MIT", degree="博士"),
            EducationEntry(school="Stanford", degree="博士"),
        ],
        work_experience=[
            WorkEntry(organization="微软亚洲研究院", role="研究员"),
            WorkEntry(organization="Google", role="研究员"),
        ],
    )

    result = _merge_agent_output(profile, output)

    assert [item.school for item in result.education_structured] == ["MIT", "Stanford"]
    assert [item.organization for item in result.work_experience] == ["微软亚洲研究院", "Google"]


def test_merge_agent_output_sanitizes_reader_artifact_title():
    profile = _profile()
    output = AgentOutputModel(
        title="URL Source: https://example.com\nPublished Time: 2026-04-12\nMarkdown Content:\nTitle: Professor",
    )

    result = _merge_agent_output(profile, output)

    assert result.title is None
