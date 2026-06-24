"""RED-phase tests for M6 Unit 1 — profile summary reinforcement."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.profile_summary_contract import (
    profile_summary_contract_violations,
)
from src.data_agents.professor import summary_reinforcement
from src.data_agents.professor.summary_reinforcement import (
    PaperContext,
    ReinforcementResult,
    generate_reinforced_profile_summary,
    summary_reinforcement_needed,
)

_VALID_SUMMARY = (
    "张三现任深圳大学教授，主要从事人工智能、机器学习与医学影像分析研究，"
    "关注算法可靠性、临床场景验证和多模态数据建模。其工作围绕智能诊断、"
    "影像分割和疾病风险评估展开，结合公开发表论文与团队项目积累，形成面向"
    "医疗应用的技术路线。相关研究强调模型解释性、数据质量和跨学科合作，"
    "为医学人工智能系统落地提供方法支持。近年来还参与科研项目和学生培养，"
    "持续推动算法在真实临床数据中的评估、优化与转化，并重视与医院、工程团队"
    "之间的协同验证。"
)

_SOURCE_LIMITATION_SUMMARY = (
    "何汝艳教授任职于深圳大学，是视觉智能研究中心的核心成员，主要致力于遥感图像"
    "处理与应用领域的研究工作。她的研究领域具有高度的交叉性与前沿性，涵盖了"
    "生态学、遥感图像处理、精准农业以及人工智能等多个重要方向。通过将人工智能"
    "技术与遥感技术深度融合，她致力于探索如何利用智能化手段提升对生态环境的"
    "监测能力，并推动精准农业的发展。尽管目前暂无收录的论文全文，但其研究布局"
    "展现出应用导向，也体现了视觉智能方法服务农业与生态监测场景的持续探索。"
)


# ----------------- summary_reinforcement_needed -----------------


@pytest.mark.parametrize(
    "profile_summary,expected",
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("tiny", True),
        ("x" * 199, True),  # below 200 default
        ("x" * 200, False),  # boundary
        ("x" * 200, False),
    ],
)
def test_reinforcement_needed_varies_by_length(profile_summary, expected):
    assert summary_reinforcement_needed(profile_summary) is expected


def test_reinforcement_needed_custom_min_length():
    assert summary_reinforcement_needed("x" * 40, min_length=100) is True
    assert summary_reinforcement_needed("x" * 120, min_length=100) is False


def test_profile_summary_contract_rejects_source_limitation_meta_language():
    assert 200 <= len(_SOURCE_LIMITATION_SUMMARY) <= 300

    violations = profile_summary_contract_violations(_SOURCE_LIMITATION_SUMMARY)

    assert "profile_summary_operator_meta_language" in violations


def test_no_paper_prompt_does_not_inject_source_limitation_meta_language():
    prompt = summary_reinforcement._build_user_prompt(
        prof_name="何汝艳",
        institution="深圳大学",
        research_directions=[],
        bio="何汝艳教授主要从事遥感图像处理与精准农业研究。",
        paper_contexts=[],
    )

    assert "暂无已收录" not in prompt
    assert "仅基于基本信息合成" not in prompt
    assert "不要提及资料缺失" in prompt


# ----------------- dataclass shapes -----------------


def test_paper_context_dataclass():
    ctx = PaperContext(title="T", abstract="A", intro="I", year=2023, venue="NeurIPS")
    assert ctx.year == 2023
    with pytest.raises((AttributeError, TypeError, Exception)):
        ctx.title = "mutated"


def test_reinforcement_result_dataclass():
    r = ReinforcementResult(summary="x" * 200, source_paper_count=3, error=None)
    assert r.source_paper_count == 3
    with pytest.raises((AttributeError, TypeError, Exception)):
        r.summary = "mutated"


# ----------------- generate_reinforced_profile_summary -----------------


def _make_llm_returning(text: str):
    llm = MagicMock()
    llm.chat.completions.create.return_value = _response(text)
    return llm


def _make_llm_returning_sequence(texts: list[str]):
    llm = MagicMock()
    llm.chat.completions.create.side_effect = [_response(text) for text in texts]
    return llm


def _response(text: str):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _paper(title="Paper", abstract="An abstract.", intro=None, year=2023, venue="X"):
    return PaperContext(
        title=title, abstract=abstract, intro=intro, year=year, venue=venue
    )


def test_generate_happy_path_returns_summary():
    llm = _make_llm_returning(_VALID_SUMMARY)
    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南方科技大学",
        research_directions=["机器人控制", "感知"],
        bio="王教授长期从事机器人学研究。",
        paper_contexts=[_paper(), _paper(title="Paper 2")],
        llm_client=llm,
        llm_model="gemma-4-26b-a4b-it",
    )
    assert isinstance(result, ReinforcementResult)
    assert result.source_paper_count == 2
    assert 200 <= len(result.summary) <= 300
    assert result.error is None
    # LLM was called exactly once with system + user roles.
    llm.chat.completions.create.assert_called_once()


def test_generate_caps_at_max_papers():
    llm = _make_llm_returning(_VALID_SUMMARY)
    many_papers = [_paper(title=f"P{i}") for i in range(10)]
    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南方科技大学",
        research_directions=[],
        bio=None,
        paper_contexts=many_papers,
        llm_client=llm,
        llm_model="gemma",
        max_papers=3,
    )
    assert result.source_paper_count == 3
    # The prompt should reference at most 3 papers.
    call_args = llm.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    prompt_text = "\n".join(m["content"] for m in messages)
    # Papers 0-2 should appear; papers 3-9 should NOT.
    assert "P0" in prompt_text
    assert "P2" in prompt_text
    assert "P5" not in prompt_text
    assert "P9" not in prompt_text


def test_generate_zero_papers_still_calls_llm():
    llm = _make_llm_returning(_VALID_SUMMARY)
    result = generate_reinforced_profile_summary(
        prof_name="李教授",
        institution="深圳大学",
        research_directions=["某方向"],
        bio=None,
        paper_contexts=[],
        llm_client=llm,
        llm_model="gemma",
    )
    assert result.source_paper_count == 0
    assert result.summary != ""
    llm.chat.completions.create.assert_called_once()


def test_generate_llm_exception_returns_empty_with_error():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("LLM down")
    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio=None,
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
    )
    assert result.summary == ""
    assert result.error is not None
    assert "LLM down" in result.error


def test_generate_llm_too_short_response_rejected():
    llm = _make_llm_returning("OK")  # below 100 chars
    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio=None,
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
    )
    assert result.summary == ""
    assert result.error is not None


def test_generate_strips_markdown_fences():
    fenced = "```\n" + _VALID_SUMMARY + "\n```"
    llm = _make_llm_returning(fenced)
    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio=None,
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
    )
    assert "```" not in result.summary
    assert result.summary.strip().startswith("张三")


def test_generate_rejects_overlong_output_instead_of_truncating():
    overlong = _VALID_SUMMARY + ("补充说明。" * 40)
    llm = _make_llm_returning(overlong)
    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio=None,
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
    )
    assert result.summary == ""
    assert result.error is not None
    assert "profile_summary_too_long" in result.error


def test_generate_retries_contract_violation_once_then_returns_valid_summary():
    overlong = _VALID_SUMMARY + ("补充说明。" * 40)
    llm = _make_llm_returning_sequence([overlong, _VALID_SUMMARY])

    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio=None,
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.summary == _VALID_SUMMARY
    assert result.error is None
    assert llm.chat.completions.create.call_count == 2
    retry_messages = llm.chat.completions.create.call_args_list[1].kwargs["messages"]
    retry_prompt = retry_messages[1]["content"]
    assert "上次输出违反摘要合同" in retry_prompt
    assert "profile_summary_too_long" in retry_prompt


def test_generate_uses_compression_retry_after_standard_attempts_exhausted():
    overlong = _VALID_SUMMARY + ("补充说明。" * 40)
    llm = _make_llm_returning_sequence([overlong, overlong, _VALID_SUMMARY])

    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio="王教授长期从事医学人工智能、影像分析和临床决策支持研究。",
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.summary == _VALID_SUMMARY
    assert result.error is None
    assert llm.chat.completions.create.call_count == 3
    compression_call = llm.chat.completions.create.call_args_list[2]
    assert compression_call.kwargs["max_tokens"] < 600
    compression_prompt = compression_call.kwargs["messages"][1]["content"]
    assert "压缩" in compression_prompt
    assert "profile_summary_too_long" in compression_prompt


def test_generate_tightens_second_compression_retry():
    overlong = _VALID_SUMMARY + ("补充说明。" * 40)
    llm = _make_llm_returning_sequence([overlong, overlong, _VALID_SUMMARY])

    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio="王教授长期从事医学人工智能、影像分析和临床决策支持研究。",
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
        max_attempts=1,
        compression_attempts=2,
    )

    assert result.summary == _VALID_SUMMARY
    assert llm.chat.completions.create.call_count == 3
    first_compression = llm.chat.completions.create.call_args_list[1]
    second_compression = llm.chat.completions.create.call_args_list[2]
    assert (
        second_compression.kwargs["max_tokens"]
        < first_compression.kwargs["max_tokens"]
    )
    second_prompt = second_compression.kwargs["messages"][1]["content"]
    assert "极限压缩" in second_prompt
    assert "220-250" in second_prompt


def test_generate_returns_contract_error_after_retry_exhausted():
    invalid_english = (
        "Professor Zhang is a professor at Shenzhen University. "
        "His research focuses on artificial intelligence and medical imaging. "
        "He has published papers in international journals and leads projects "
        "on robust clinical decision support systems."
    )
    llm = _make_llm_returning_sequence([invalid_english, invalid_english])

    result = generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio=None,
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
    )

    assert result.summary == ""
    assert result.error is not None
    assert "profile_summary_not_chinese" in result.error
    assert llm.chat.completions.create.call_count == 2


def test_generate_uses_temperature_and_max_tokens():
    llm = _make_llm_returning(_VALID_SUMMARY)
    generate_reinforced_profile_summary(
        prof_name="王教授",
        institution="南科大",
        research_directions=[],
        bio=None,
        paper_contexts=[_paper()],
        llm_client=llm,
        llm_model="gemma",
    )
    kwargs = llm.chat.completions.create.call_args.kwargs
    assert kwargs.get("temperature") == pytest.approx(0.2)
    assert kwargs.get("max_tokens") == 600


def test_generate_no_hardcoded_api_key():
    """Memory Shape 1: never inline os.getenv('GEMMA_API_KEY')."""
    import src.data_agents.professor.summary_reinforcement as mod
    import pathlib

    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "os.getenv" not in source
    assert "os.environ" not in source
