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


def test_translate_abstract_to_zh_skips_empty_and_summarizes_chinese_input():
    summary = _valid_summary("该研究围绕中文摘要来源中的核心问题展开，")
    llm = _llm_with_outputs([summary])

    assert translate_abstract_to_zh("", llm_client=llm, llm_model="gemma") is None
    assert (
        translate_abstract_to_zh(
            "本文提出一种用于智能制造质量检测的深度学习方法，能够提升缺陷识别准确率，并在多条产线数据上验证了泛化能力。",
            llm_client=llm,
            llm_model="gemma",
        )
        == summary
    )
    assert llm.chat.completions.create.call_count == 1


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


def test_translate_abstract_to_zh_accepts_concise_informative_summary():
    summary = (
        "本文提出一种用于医学影像分割的轻量级多尺度网络，结合边界约束和注意力融合提升小病灶识别能力。"
        "实验在公开脑部MRI数据集上验证了Dice和召回率改进，并分析了模型在临床辅助诊断中的部署成本和泛化风险控制。"
    )
    assert 100 <= len(summary) < 150
    llm = _llm_with_outputs([summary])

    result = translate_abstract_to_zh(
        "A concise but specific medical image segmentation abstract.",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result == summary
    assert llm.chat.completions.create.call_count == 1


def test_translate_abstract_to_zh_accepts_detailed_seven_hundred_char_summary():
    summary = (
        "为了提升虚拟现实（VR）用户的视觉体验，VR360视频需要比传统视频更高的分辨率与画质。目前主流的VR360投影格式"
        "包括等距柱状投影（ERP）和立方体贴图投影（CMP），这些格式在投影至三维球面进行渲染时，对码率分配提出了新的"
        "挑战。传统的处理方式通常根据像素位置经验性地为编码单元分配固定量化参数（QP），这种方法缺乏精确性与合理性，"
        "限制了编码性能。针对这一问题，本研究提出了一种全新的熵平衡优化（EEO）方法，旨在提升VR360视频的编码效率。"
        "该方法通过开发球面码率均衡策略，在视频编码的率失真优化过程中获取块级拉格朗日乘子（λ），并根据该参数动态确定"
        "每个编码块的最佳QP值。基于EEO方法，研究进一步针对ERP和CMP格式分别开发了EEOA-ERP与EEOA-CMP两种算法。"
        "实验结果表明，两种算法在全内帧（AI）、低延迟（LD）及随机访问（RA）配置下均取得了显著的BD-Rate节省，性能优于"
        "HM16.17平台。具体而言，在低延迟配置下，EEOA-ERP较现有先进算法WSU-ERP实现了0.37%的BD-Rate节省；在随机访问"
        "配置下，EEOA-CMP在相同测试条件下较HM16.17 VR CMP实现了2.6%的客观质量提升。"
        "此外，研究比较了不同投影格式下的码率分布差异，说明所提出的熵平衡策略可以在复杂观看视角中保持稳定编码收益。"
        "消融实验进一步验证了拉格朗日乘子估计、块级QP调整和球面权重建模三个模块的独立贡献，说明该方法并非依赖单一"
        "数据集调参获得收益，而是在多种内容类型、运动强度和码率范围内保持一致改进。"
    )
    assert 650 < len(summary) < 800
    llm = _llm_with_outputs([summary])

    result = translate_abstract_to_zh(
        "A long technical abstract about VR 360-degree video coding.",
        llm_client=llm,
        llm_model="gemma",
    )

    assert result == summary
    assert llm.chat.completions.create.call_count == 1


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
