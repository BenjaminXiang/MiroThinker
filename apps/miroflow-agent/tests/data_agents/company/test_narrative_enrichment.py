from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.data_agents.company.narrative_enrichment import (
    NarrativeResult,
    build_user_prompt,
    generate_company_narrative,
)


def _profile_text() -> str:
    return "企" * 620


def _tech_text() -> str:
    return "技" * 360


def _long_profile_text() -> str:
    return "长" * 1450


def _long_tech_text() -> str:
    return "路" * 760


def _make_llm_returning(*texts: str):
    llm = MagicMock()

    def _create(**_kwargs):
        text = texts[_create.index]
        _create.index += 1
        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    _create.index = 0
    llm.chat.completions.create.side_effect = _create
    return llm


def test_narrative_result_is_frozen():
    result = NarrativeResult(
        profile_summary="x" * 220,
        technology_route_summary="y" * 350,
        error=None,
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        result.profile_summary = "mutated"


def test_build_user_prompt_includes_company_context():
    prompt = build_user_prompt(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="这是一段企业介绍。",
        business="机器人视觉和自动化系统",
        products=[
            {
                "name": "示例机器人平台",
                "description": "面向工厂的视觉检测和搬运协同平台。",
            }
        ],
        source_materials=[
            {
                "source_tier": "official",
                "title": "产品中心",
                "text": "官网介绍示例机器人平台服务工业客户。",
                "trust_reason": "official_site",
            }
        ],
    )
    assert "深圳示例科技" in prompt
    assert "机器人" in prompt
    assert "深圳" in prompt
    assert "这是一段企业介绍" in prompt
    assert "机器人视觉和自动化系统" in prompt
    assert "示例机器人平台" in prompt
    assert "官网介绍示例机器人平台服务工业客户" in prompt


def test_generate_happy_path_parses_json():
    payload = {
        "profile_summary": _profile_text()[:620],
        "technology_route_summary": _tech_text()[:360],
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
        business="机器人视觉和自动化系统",
        products=[{"name": "示例机器人平台", "description": "视觉检测平台"}],
        source_materials=[
            {
                "source_tier": "official",
                "title": "产品中心",
                "text": "官网介绍示例机器人平台覆盖工厂检测、产线协同和质量管理。",
            }
        ],
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert 500 <= len(result.profile_summary) <= 1800
    assert 300 <= len(result.technology_route_summary) <= 900
    llm.chat.completions.create.assert_called_once()


def test_generate_accepts_longer_search_rich_narratives():
    payload = {
        "profile_summary": _long_profile_text(),
        "technology_route_summary": _long_tech_text(),
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 8,
        business="机器人视觉和自动化系统",
        products=[{"name": "示例机器人平台", "description": "视觉检测平台"}],
        source_materials=[
            {
                "source_tier": "official",
                "title": "产品中心",
                "text": "官网介绍示例机器人平台覆盖工厂检测、产线协同和质量管理。" * 6,
            }
        ],
        llm_client=llm,
        llm_model="deepseek-v4-pro",
    )

    assert result.error is None
    assert len(result.profile_summary) == 1450
    assert len(result.technology_route_summary) == 760


def test_generate_trims_overlong_json_fields_without_rejecting():
    payload = {
        "profile_summary": "企" * 1900,
        "technology_route_summary": "技" * 960,
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 8,
        business="机器人视觉和自动化系统",
        products=[{"name": "示例机器人平台", "description": "视觉检测平台"}],
        source_materials=[
            {
                "source_tier": "official",
                "title": "产品中心",
                "text": "官网介绍示例机器人平台覆盖工厂检测、产线协同和质量管理。" * 6,
            }
        ],
        llm_client=llm,
        llm_model="deepseek-v4-pro",
    )

    assert result.error is None
    assert len(result.profile_summary) == 1800
    assert len(result.technology_route_summary) == 900
    llm.chat.completions.create.assert_called_once()


def test_generate_trims_overlong_split_fallback_fields_without_rejecting():
    llm = _make_llm_returning(
        "不是 JSON",
        "企" * 1900,
        "技" * 960,
    )

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 8,
        business="机器人视觉和自动化系统",
        products=[{"name": "示例机器人平台", "description": "视觉检测平台"}],
        source_materials=[
            {
                "source_tier": "official",
                "title": "产品中心",
                "text": "官网介绍示例机器人平台覆盖工厂检测、产线协同和质量管理。" * 6,
            }
        ],
        llm_client=llm,
        llm_model="deepseek-v4-pro",
    )

    assert result.error is None
    assert len(result.profile_summary) == 1800
    assert len(result.technology_route_summary) == 900
    assert llm.chat.completions.create.call_count == 3


def test_generate_prompt_uses_business_products_and_accepted_source_tiers():
    payload = {
        "profile_summary": _profile_text()[:620],
        "technology_route_summary": _tech_text()[:360],
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
        business="机器人视觉和产线自动化",
        products=[
            {
                "name": "示例机器人平台",
                "description": "面向工厂产线的视觉检测平台。",
                "technical_tags": ["机器视觉", "产线协同"],
            }
        ],
        source_materials=[
            {"source_tier": "official", "text": "官网产品页介绍工业客户案例。"},
            {"source_tier": "yiou", "text": "亿欧页面提到产品和融资信息。"},
            {
                "source_tier": "pitchhub_36kr",
                "text": "PitchHub 页面包含项目定位和产品线。",
            },
            {"source_tier": "generic_web", "text": "已通过身份判断的网页材料。"},
        ],
        llm_client=llm,
        llm_model="gemma",
    )

    prompt = llm.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "机器人视觉和产线自动化" in prompt
    assert "示例机器人平台" in prompt
    assert "official" in prompt
    assert "yiou" in prompt
    assert "pitchhub_36kr" in prompt
    assert "generic_web" in prompt


def test_generate_retries_once_for_length_violation():
    first = {
        "profile_summary": "太短",
        "technology_route_summary": _tech_text()[:360],
    }
    second = {
        "profile_summary": _profile_text()[:610],
        "technology_route_summary": _tech_text()[:350],
    }
    llm = _make_llm_returning(
        json.dumps(first, ensure_ascii=False),
        json.dumps(second, ensure_ascii=False),
    )

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
        business="机器人视觉和自动化系统",
        products=[{"name": "示例机器人平台", "description": "视觉检测平台"}],
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert llm.chat.completions.create.call_count == 2


def test_generate_json_parse_failure_falls_back_to_split_prompts():
    llm = _make_llm_returning(
        "不是 JSON",
        _profile_text()[:610],
        _tech_text()[:360],
    )

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
        business="机器人视觉和自动化系统",
        products=[{"name": "示例机器人平台", "description": "视觉检测平台"}],
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert 500 <= len(result.profile_summary) <= 1800
    assert 300 <= len(result.technology_route_summary) <= 900
    assert llm.chat.completions.create.call_count == 3


def test_generate_rejects_short_input_without_llm_call():
    llm = MagicMock()
    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="太短",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.profile_summary == ""
    assert result.technology_route_summary == ""
    assert result.error == "sparse_material"
    assert "sparse_material" in result.blockers
    llm.chat.completions.create.assert_not_called()


def test_generate_llm_exception_returns_error():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("llm down")

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
        business="机器人视觉和自动化系统",
        products=[{"name": "示例机器人平台", "description": "视觉检测平台"}],
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.profile_summary == ""
    assert result.technology_route_summary == ""
    assert "llm down" in result.error


def test_generate_no_environment_secret_reads():
    import pathlib
    import src.data_agents.company.narrative_enrichment as mod

    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "os.getenv" not in source
    assert "os.environ" not in source
