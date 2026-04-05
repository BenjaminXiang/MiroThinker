# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.professor.cross_domain import CompanyLink, PaperLink, PatentLink
from src.data_agents.professor.models import (
    EducationEntry,
    EnrichedProfessorProfile,
    WorkEntry,
)


def _full_enriched_profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "张三",
        "name_en": "San Zhang",
        "institution": "南方科技大学",
        "department": "计算机科学与工程系",
        "title": "教授",
        "email": "zhangsan@sustech.edu.cn",
        "homepage": "https://faculty.sustech.edu.cn/zhangsan",
        "office": "工学院南楼501",
        "research_directions": ["大语言模型安全对齐", "RLHF 训练策略", "多模态推理"],
        "research_directions_source": "paper_driven",
        "education_structured": [
            EducationEntry(school="清华大学", degree="博士", field="计算机科学", end_year=2010),
            EducationEntry(school="北京大学", degree="学士", field="数学", end_year=2005),
        ],
        "work_experience": [
            WorkEntry(organization="南方科技大学", role="教授", start_year=2015),
            WorkEntry(organization="Microsoft Research", role="Researcher", start_year=2010, end_year=2015),
        ],
        "h_index": 45,
        "citation_count": 12000,
        "paper_count": 150,
        "top_papers": [
            PaperLink(title="Safety Alignment for LLMs", year=2024, venue="NeurIPS", citation_count=500, source="semantic_scholar"),
        ],
        "awards": ["国家杰出青年科学基金"],
        "academic_positions": ["IEEE Senior Member"],
        "projects": ["国家重点研发计划"],
        "company_roles": [
            CompanyLink(company_name="深圳安全AI科技", role="首席科学家", source="web_search"),
        ],
        "patent_ids": [
            PatentLink(patent_title="一种大模型安全对齐方法", patent_number="CN2024001", source="web_search"),
        ],
        "profile_summary": "张三现任南方科技大学计算机科学与工程系教授，研究方向聚焦大语言模型安全对齐与RLHF训练策略。" * 3,
        "evaluation_summary": "张三h-index为45，总引用12000次，发表论文150篇。国家杰出青年科学基金获得者，IEEE Senior Member。" * 1,
        "enrichment_source": "agent_local",
        "evidence_urls": ["https://faculty.sustech.edu.cn/zhangsan", "https://semanticscholar.org/author/xxx"],
        "field_provenance": {"research_directions": "paper_analysis", "h_index": "semantic_scholar"},
        "profile_url": "https://faculty.sustech.edu.cn/zhangsan",
        "roster_source": "https://www.sustech.edu.cn/zh/faculty/",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def test_enriched_profile_all_fields_validates():
    profile = _full_enriched_profile()
    assert profile.name == "张三"
    assert profile.h_index == 45
    assert len(profile.top_papers) == 1
    assert len(profile.company_roles) == 1
    assert len(profile.education_structured) == 2
    assert profile.enrichment_source == "agent_local"


def test_enriched_profile_minimal_validates():
    profile = EnrichedProfessorProfile(
        name="李四",
        institution="深圳大学",
        profile_url="https://example.com/lisi",
        roster_source="https://www.szu.edu.cn/",
        extraction_status="partial",
    )
    assert profile.research_directions == []
    assert profile.top_papers == []
    assert profile.company_roles == []
    assert profile.education_structured == []
    assert profile.h_index is None
    assert profile.enrichment_source == "regex_only"
    assert profile.profile_summary == ""


def test_enriched_profile_serialization_roundtrip():
    profile = _full_enriched_profile()
    json_str = profile.model_dump_json()
    restored = EnrichedProfessorProfile.model_validate_json(json_str)
    assert restored.name == profile.name
    assert restored.h_index == profile.h_index
    assert restored.research_directions == profile.research_directions
    assert restored.top_papers[0].title == profile.top_papers[0].title
    assert restored.company_roles[0].company_name == profile.company_roles[0].company_name
    assert restored.education_structured[0].school == profile.education_structured[0].school
    assert restored.field_provenance == profile.field_provenance


def test_education_entry_validates():
    entry = EducationEntry(school="MIT", degree="PhD", field="CS", start_year=2015, end_year=2020)
    assert entry.school == "MIT"
    assert entry.end_year == 2020


def test_education_entry_minimal():
    entry = EducationEntry(school="清华大学")
    assert entry.degree is None
    assert entry.start_year is None


def test_work_entry_validates():
    entry = WorkEntry(organization="Google", role="Research Scientist", start_year=2020)
    assert entry.organization == "Google"
    assert entry.end_year is None


def test_enriched_profile_field_provenance():
    profile = _full_enriched_profile(
        field_provenance={
            "research_directions": "paper_analysis",
            "h_index": "semantic_scholar",
            "education_structured": "agent_official",
            "company_roles": "web_search",
        }
    )
    assert profile.field_provenance["research_directions"] == "paper_analysis"
    assert profile.field_provenance["company_roles"] == "web_search"
