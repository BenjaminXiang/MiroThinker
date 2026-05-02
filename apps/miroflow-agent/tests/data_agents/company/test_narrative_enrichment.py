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
    return "企" * 240


def _tech_text() -> str:
    return "技" * 360


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
    )
    assert "深圳示例科技" in prompt
    assert "机器人" in prompt
    assert "深圳" in prompt
    assert "这是一段企业介绍" in prompt


def test_generate_happy_path_parses_json():
    payload = {
        "profile_summary": _profile_text()[:240],
        "technology_route_summary": _tech_text()[:360],
    }
    llm = _make_llm_returning(json.dumps(payload, ensure_ascii=False))

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert 200 <= len(result.profile_summary) <= 300
    assert 300 <= len(result.technology_route_summary) <= 500
    llm.chat.completions.create.assert_called_once()


def test_generate_retries_once_for_length_violation():
    first = {
        "profile_summary": "太短",
        "technology_route_summary": _tech_text()[:360],
    }
    second = {
        "profile_summary": _profile_text()[:230],
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
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert llm.chat.completions.create.call_count == 2


def test_generate_json_parse_failure_falls_back_to_split_prompts():
    llm = _make_llm_returning(
        "不是 JSON",
        _profile_text()[:235],
        _tech_text()[:360],
    )

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.error is None
    assert 200 <= len(result.profile_summary) <= 300
    assert 300 <= len(result.technology_route_summary) <= 500
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
    assert result.error == "short_input"
    llm.chat.completions.create.assert_not_called()


def test_generate_llm_exception_returns_error():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("llm down")

    result = generate_company_narrative(
        company_name="深圳示例科技",
        industry="机器人",
        hq_city="深圳",
        description="深圳示例科技专注智能机器人和行业自动化解决方案。" * 4,
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
