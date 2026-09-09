"""Tests for ``judge_summary_boilerplate`` (T6.2 / T6.3).

Per OpenSpec change ``prof-paper-patent-from-page-flow`` spec
Requirement "summary_zh generation" Scenario "Boilerplate-rejected
summary" + design.md §11.

The judge is a deliberately separate LLM call after translation. It
fails open (returns False on transport / parse errors) so a transient
outage cannot silently null out every newly generated summary; the
trade-off accepted in the design doc is that a few boilerplate
summaries may slip through until the next cron pass.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.data_agents.paper.abstract_translator import (
    _JUDGE_BOILERPLATE_VERDICT,
    _JUDGE_INFORMATIVE_VERDICT,
    _parse_judge_verdict,
    judge_summary_boilerplate,
)


def _llm_with_reply(reply: str):
    """Build a minimal MagicMock that returns the given reply once."""
    client = MagicMock()
    message = MagicMock()
    message.content = reply
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client.chat.completions.create.return_value = response
    return client


# --- _parse_judge_verdict --------------------------------------------------


def test_parse_judge_verdict_exact_token():
    assert _parse_judge_verdict("BOILERPLATE") == _JUDGE_BOILERPLATE_VERDICT
    assert _parse_judge_verdict("INFORMATIVE") == _JUDGE_INFORMATIVE_VERDICT


def test_parse_judge_verdict_case_insensitive():
    assert _parse_judge_verdict("boilerplate") == _JUDGE_BOILERPLATE_VERDICT
    assert _parse_judge_verdict("Informative") == _JUDGE_INFORMATIVE_VERDICT


def test_parse_judge_verdict_verbose_reply():
    assert (
        _parse_judge_verdict("I think this summary is BOILERPLATE because ...")
        == _JUDGE_BOILERPLATE_VERDICT
    )
    assert (
        _parse_judge_verdict("Verdict: INFORMATIVE. Reason: ...")
        == _JUDGE_INFORMATIVE_VERDICT
    )


def test_parse_judge_verdict_co_occurrence_respects_negation_and_first_verdict():
    """Weak gate: do not reject an informative verdict just because the
    explanation mentions "not BOILERPLATE"."""
    text = "Decision: not INFORMATIVE; it is BOILERPLATE."
    assert _parse_judge_verdict(text) == _JUDGE_BOILERPLATE_VERDICT
    assert (
        _parse_judge_verdict("INFORMATIVE, not BOILERPLATE.")
        == _JUDGE_INFORMATIVE_VERDICT
    )


def test_parse_judge_verdict_unknown_defaults_to_informative():
    """When the judge replies with neither token (truncated / off-prompt
    output), default to INFORMATIVE (= keep the summary). The translator
    already rejected obvious failures via regex; the judge is the
    finer-grained step and shouldn't over-block on parse failure."""
    assert _parse_judge_verdict("OK") == _JUDGE_INFORMATIVE_VERDICT
    assert _parse_judge_verdict("") == _JUDGE_INFORMATIVE_VERDICT
    assert _parse_judge_verdict(MagicMock()) == _JUDGE_INFORMATIVE_VERDICT


# --- judge_summary_boilerplate ---------------------------------------------


def test_judge_returns_true_when_llm_says_boilerplate():
    llm = _llm_with_reply("BOILERPLATE")
    assert judge_summary_boilerplate(
        "本文研究了一个重要问题，提出了一种新方法，实验证明了有效性。",
        llm_client=llm,
        llm_model="gemma",
    ) is True
    assert llm.chat.completions.create.call_count == 1


def test_judge_returns_false_for_substantive_summary():
    llm = _llm_with_reply("INFORMATIVE")
    summary = (
        "本文提出一种基于 Transformer 的高分辨率显微图像分类方法，"
        "通过自适应稀疏注意力降低显存占用 38%，在 BACH 与 BreakHis "
        "两个公开数据集上分别达到 92.6% 与 88.1% 准确率，已在某三甲医院"
        "病理科部署半年累计辅助阅片 4500 例。"
    )
    assert judge_summary_boilerplate(
        summary, llm_client=llm, llm_model="gemma"
    ) is False


def test_judge_does_not_hard_reject_substantive_summary_on_false_positive():
    llm = _llm_with_reply("BOILERPLATE")
    summary = (
        "属性网络中异常普遍存在，却隐匿于复杂拓扑结构与高维节点属性之中。"
        "现有属性网络异常检测研究虽提出多种技术，但较少关注小样本异常检测问题。"
        "该研究面向仅有少量标记异常的实际系统场景，讨论网络风险识别和数据质量提升。"
    )

    assert judge_summary_boilerplate(
        summary, llm_client=llm, llm_model="gemma"
    ) is False


def test_judge_returns_false_when_llm_call_fails():
    """Fail-open: transient outage must not turn every freshly
    generated summary into a quality_status=rejected row."""
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("network down")
    assert judge_summary_boilerplate(
        "本文提出了一种...",
        llm_client=llm,
        llm_model="gemma",
    ) is False


def test_judge_returns_false_for_blank_input_without_llm_call():
    """Skip the LLM call entirely when there is nothing to judge."""
    llm = MagicMock()
    assert judge_summary_boilerplate(None, llm_client=llm, llm_model="x") is False
    assert judge_summary_boilerplate("", llm_client=llm, llm_model="x") is False
    assert judge_summary_boilerplate("   \n", llm_client=llm, llm_model="x") is False
    assert llm.chat.completions.create.call_count == 0


def test_judge_strips_markdown_fences_in_reply():
    """Some LLMs wrap the verdict in markdown code fences. The parser
    looks for the token anywhere in the reply so fenced output works."""
    llm = _llm_with_reply("```\nBOILERPLATE\n```")
    assert judge_summary_boilerplate(
        "本文研究了一个重要问题。",
        llm_client=llm,
        llm_model="gemma",
    ) is True


def test_judge_temperature_is_zero_for_determinism():
    """The judge prompt is binary classification; we want deterministic
    output. This is implementation detail but worth pinning."""
    llm = _llm_with_reply("INFORMATIVE")
    judge_summary_boilerplate(
        "某真实摘要内容。",
        llm_client=llm,
        llm_model="gemma",
    )
    _, kwargs = llm.chat.completions.create.call_args
    assert kwargs["temperature"] == 0.0


def test_judge_includes_extra_body_when_provided():
    llm = _llm_with_reply("INFORMATIVE")
    judge_summary_boilerplate(
        "某摘要",
        llm_client=llm,
        llm_model="gemma",
        extra_body={"foo": "bar"},
    )
    _, kwargs = llm.chat.completions.create.call_args
    assert kwargs["extra_body"] == {"foo": "bar"}


def test_judge_extra_body_defaults_to_empty_dict():
    llm = _llm_with_reply("INFORMATIVE")
    judge_summary_boilerplate("某摘要", llm_client=llm, llm_model="gemma")
    _, kwargs = llm.chat.completions.create.call_args
    assert kwargs["extra_body"] == {}
