"""RED-phase tests for M6 Unit 1 — profile summary reinforcement."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data_agents.professor.summary_reinforcement import (
    PaperContext,
    ReinforcementResult,
    generate_reinforced_profile_summary,
    summary_reinforcement_needed,
)


# ----------------- summary_reinforcement_needed -----------------


@pytest.mark.parametrize(
    "profile_summary,expected",
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("tiny", True),
        ("x" * 30, True),  # below 50 default
        ("x" * 50, False),  # boundary
        ("x" * 200, False),
    ],
)
def test_reinforcement_needed_varies_by_length(profile_summary, expected):
    assert summary_reinforcement_needed(profile_summary) is expected


def test_reinforcement_needed_custom_min_length():
    assert summary_reinforcement_needed("x" * 40, min_length=100) is True
    assert summary_reinforcement_needed("x" * 120, min_length=100) is False


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
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    llm.chat.completions.create.return_value = resp
    return llm


def _paper(title="Paper", abstract="An abstract.", intro=None, year=2023, venue="X"):
    return PaperContext(title=title, abstract=abstract, intro=intro, year=year, venue=venue)


def test_generate_happy_path_returns_summary():
    llm = _make_llm_returning("教授研究机器人控制与感知，近年来专注于双足平衡控制、" * 5)
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
    assert len(result.summary) >= 100
    assert result.error is None
    # LLM was called exactly once with system + user roles.
    llm.chat.completions.create.assert_called_once()


def test_generate_caps_at_max_papers():
    llm = _make_llm_returning("合成后的画像。" * 30)
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
    llm = _make_llm_returning("基于姓名+机构合成的画像。" * 20)
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
    fenced = "```\n" + ("教授专注于某方向。" * 20) + "\n```"
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
    assert result.summary.strip().startswith("教授")


def test_generate_caps_overlong_output_at_800_chars():
    overlong = "x" * 2000
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
    assert len(result.summary) <= 800


def test_generate_uses_temperature_and_max_tokens():
    llm = _make_llm_returning("教授研究某方向。" * 20)
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
