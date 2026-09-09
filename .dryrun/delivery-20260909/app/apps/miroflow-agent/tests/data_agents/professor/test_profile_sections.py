from __future__ import annotations

from src.data_agents.professor.profile_sections import (
    ResearchOverviewBuildResult,
    build_research_overview_section,
    persist_research_overview_section,
    validate_chinese_research_overview,
)


def test_build_research_overview_section_from_chinese_official_text() -> None:
    raw_text = (
        "基本信息：某教授。研究领域介绍：面向医学影像的可信人工智能、"
        "多模态数据融合和可解释诊断模型。教育经历：博士。"
    )

    result = build_research_overview_section(
        professor_id="PROF-ZH",
        profile_raw_text=raw_text,
        source_page_id="00000000-0000-0000-0000-000000000001",
        run_id="11111111-1111-1111-1111-111111111111",
    )

    assert result.status == "section_ready"
    assert result.section is not None
    assert result.section.section_type == "research_overview"
    assert result.section.language == "zh"
    assert result.section.source_language == "zh"
    assert result.section.generation_method == "official_extract"
    assert "可信人工智能" in result.section.content
    assert "教育经历" not in result.section.content


def test_build_research_overview_section_translates_english_source() -> None:
    raw_text = (
        "Research Overview: My research focuses on developing trustworthy "
        "artificial intelligence for medical image analysis, with a special "
        "emphasis on brain disease diagnosis and prognosis. Education: PhD."
    )
    calls: list[str] = []

    def translator(text: str) -> str:
        calls.append(text)
        return "我的研究聚焦于医学影像分析中的可信人工智能，重点关注脑疾病诊断与预后。"

    result = build_research_overview_section(
        professor_id="PROF-EN",
        profile_raw_text=raw_text,
        translator=translator,
    )

    assert result.status == "section_ready"
    assert len(calls) == 1
    assert calls[0].startswith("My research focuses")
    assert result.section is not None
    assert result.section.language == "zh"
    assert result.section.source_language == "en"
    assert result.section.generation_method == "llm_translation"
    assert result.section.source_text_hash
    assert result.section.source_text_hash != calls[0]


def test_build_research_overview_section_cleans_noisy_chinese_source() -> None:
    raw_text = (
        "研究方向：群体智能、社交网络传播动力学、网络科学、图神经网络。"
        "科研详情请访问：https://xiangrongwang.github.io/ "
        "欢迎研究生发送简历咨询。"
    )
    calls: list[str] = []

    def translator(text: str) -> str:
        calls.append(text)
        return "研究方向包括群体智能、社交网络传播动力学、网络科学和图神经网络。"

    result = build_research_overview_section(
        professor_id="PROF-NOISY-ZH",
        profile_raw_text=raw_text,
        translator=translator,
    )

    assert result.status == "section_ready"
    assert calls and "xiangrongwang.github.io" in calls[0]
    assert result.section is not None
    assert result.section.source_language == "zh"
    assert result.section.generation_method == "llm_cleaning"
    assert "https://" not in result.section.content
    assert "研究生" not in result.section.content


def test_build_research_overview_section_skips_navigation_label_noise() -> None:
    raw_text = (
        "个人简历 教学 研究领域 研究成果 奖励荣誉 概况 教育经历 "
        "社会兼职 教学课程 研究生指导 研究领域 My research focuses on "
        "developing trustworthy artificial intelligence for medical image "
        "analysis, with a special emphasis on brain disease diagnosis and "
        "prognosis. 主要项目 1. Shenzhen project."
    )
    calls: list[str] = []

    def translator(text: str) -> str:
        calls.append(text)
        return "我的研究聚焦于医学影像分析中的可信人工智能，重点关注脑疾病诊断与预后。"

    result = build_research_overview_section(
        professor_id="PROF-NAV",
        profile_raw_text=raw_text,
        translator=translator,
    )

    assert result.status == "section_ready"
    assert calls == [
        "My research focuses on developing trustworthy artificial intelligence "
        "for medical image analysis, with a special emphasis on brain disease "
        "diagnosis and prognosis."
    ]


def test_research_overview_source_hash_is_keyed_to_source_text() -> None:
    raw_text = (
        "Research Interests: My research focuses on trustworthy AI for "
        "medical image analysis and brain disease diagnosis. Education: PhD."
    )

    first = build_research_overview_section(
        professor_id="PROF-EN",
        profile_raw_text=raw_text,
        translator=lambda _text: "我的研究聚焦于医学影像分析中的可信人工智能和脑疾病诊断。",
    )
    second = build_research_overview_section(
        professor_id="PROF-EN",
        profile_raw_text=raw_text,
        translator=lambda _text: "本人研究可信人工智能在医学影像和脑疾病诊断中的应用。",
    )

    assert first.section is not None
    assert second.section is not None
    assert first.section.content != second.section.content
    assert first.section.source_text_hash == second.section.source_text_hash


def test_build_research_overview_section_requires_translator_for_english() -> None:
    result = build_research_overview_section(
        professor_id="PROF-EN",
        profile_raw_text="Research Interests: Trustworthy AI for medical imaging.",
    )

    assert result == ResearchOverviewBuildResult(
        professor_id="PROF-EN",
        status="translation_required",
        section=None,
        reason="english_source_requires_translator",
    )


def test_build_research_overview_section_reports_missing_source() -> None:
    result = build_research_overview_section(
        professor_id="PROF-MISSING",
        profile_raw_text="教育经历：博士。工作经历：助理教授。",
    )

    assert result.status == "missing_source"
    assert result.section is None
    assert result.reason == "research_overview_not_found"


def test_validate_chinese_research_overview_rejects_english_translation() -> None:
    assert validate_chinese_research_overview("Trustworthy AI medical imaging") == [
        "missing_chinese_text"
    ]


def test_persist_research_overview_section_writes_ready_section() -> None:
    class _Cursor:
        def fetchone(self):
            return {"section_id": "SECTION-1"}

    class _Conn:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))
            return _Cursor()

    result = build_research_overview_section(
        professor_id="PROF-ZH",
        profile_raw_text="研究方向：可信人工智能医学影像分析。教育经历：博士。",
    )
    conn = _Conn()

    persistence = persist_research_overview_section(conn, result)

    assert persistence == "SECTION-1"
    assert len(conn.calls) == 1
