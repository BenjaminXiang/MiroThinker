from __future__ import annotations

from unittest.mock import MagicMock

from src.data_agents.paper.abstract_translator import (
    _zh_char_ratio,
    translate_abstract_to_zh,
)


def _llm_with_outputs(outputs: list[str]):
    client = MagicMock()
    responses = []
    for output in outputs:
        message = MagicMock()
        message.content = output
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        responses.append(response)
    client.chat.completions.create.side_effect = responses
    return client


def _valid_summary(prefix: str = "") -> str:
    return (
        prefix
        + "本文提出一种面向复杂系统建模的深度学习方法，通过结合结构化先验、多尺度特征提取和任务自适应优化，"
        "提升模型在小样本、强噪声和跨场景迁移条件下的稳定性与泛化能力。实验在多个公开数据集和真实业务数据上验证了"
        "该方法相较传统基线的性能优势，并展示其在智能制造、科学计算、自动化决策和工程监测中的应用潜力。"
        "论文进一步分析了关键模块的贡献、参数敏感性和失败案例，为后续系统化部署提供了可复用的验证思路。"
    )


def test_translate_abstract_to_zh_returns_valid_summary():
    summary = _valid_summary()
    llm = _llm_with_outputs([summary])

    result = translate_abstract_to_zh(
        "This paper proposes a deep learning method for complex system modeling.",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result == summary
    assert llm.chat.completions.create.call_count == 1


def test_translate_abstract_to_zh_skips_empty_or_chinese_input():
    llm = _llm_with_outputs([])

    assert translate_abstract_to_zh("", llm_client=llm, llm_model="gemma") is None
    assert (
        translate_abstract_to_zh(
            "这是一段已经是中文的摘要，介绍方法、结果和应用场景。",
            llm_client=llm,
            llm_model="gemma",
        )
        is None
    )
    assert llm.chat.completions.create.call_count == 0


def test_translate_abstract_to_zh_retries_invalid_length_once():
    valid_summary = _valid_summary("该研究围绕无线感知场景中的鲁棒建模问题展开，")
    llm = _llm_with_outputs(["太短", valid_summary])

    result = translate_abstract_to_zh(
        "Wireless sensing abstract.",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result == valid_summary
    assert llm.chat.completions.create.call_count == 2


def test_translate_abstract_to_zh_returns_none_on_llm_error():
    llm = MagicMock()
    llm.chat.completions.create.side_effect = RuntimeError("boom")

    result = translate_abstract_to_zh(
        "This paper proposes a model.",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result is None


def test_zh_char_ratio():
    assert _zh_char_ratio("中文摘要") == 1.0
    assert _zh_char_ratio("English abstract") == 0.0
