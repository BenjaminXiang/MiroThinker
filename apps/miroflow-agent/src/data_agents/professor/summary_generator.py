# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Stage 3 — LLM-powered summary generation for professor profiles.

Replaces template-based summaries with substantive, paper-driven content.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .models import EnrichedProfessorProfile

logger = logging.getLogger(__name__)

BOILERPLATE_KEYWORDS = frozenset({
    "暂未获取",
    "持续补全",
    "仍在完善",
    "已整理",
    "可追溯来源",
    "已同步整理",
    "持续补充",
    "仍在持续",
})

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True)
class GeneratedSummaries:
    profile_summary: str
    evaluation_summary: str


def build_profile_summary_prompt(profile: EnrichedProfessorProfile) -> str:
    """Build prompt for profile_summary generation (200-300 chars)."""
    directions = "、".join(profile.research_directions[:5]) if profile.research_directions else "暂无具体方向"
    papers = "\n".join(
        f"- {p.title} ({p.year}, {p.venue}, 引用{p.citation_count})"
        for p in profile.top_papers[:5]
    ) or "无代表论文数据"

    awards_text = "、".join(profile.awards[:3]) if profile.awards else ""
    edu_text = "、".join(
        f"{e.school}{e.degree or ''}" for e in profile.education_structured[:3]
    ) if profile.education_structured else ""

    return f"""请为以下教授生成200-300字的中文简介（profile_summary）。

要求：
- 第一句：姓名+学校+院系+职称（身份锚定）
- 主体段落（最大篇幅）：具体研究方向和最近研究趋势，使用领域术语，到"基于Transformer的蛋白质结构预测"粒度
- 第三部分：代表性成果和学术影响力（高引论文、h-index）
- 第四部分：教育背景和关键履历（如有）
- 禁止套话、模糊表述、对缺失信息做推测
- 缺少信息的维度直接跳过
- 严格200-300字

教授信息：
姓名：{profile.name}
学校：{profile.institution}
院系：{profile.department or "未知"}
职称：{profile.title or "未知"}
研究方向：{directions}
h-index：{profile.h_index or "未知"}
总引用：{profile.citation_count or "未知"}
代表论文：
{papers}
{f"奖项：{awards_text}" if awards_text else ""}
{f"教育背景：{edu_text}" if edu_text else ""}

直接输出简介文本，不要包含任何前缀或标签："""


def build_evaluation_summary_prompt(profile: EnrichedProfessorProfile) -> str:
    """Build prompt for evaluation_summary generation (100-150 chars)."""
    return f"""请为以下教授生成100-150字的事实性评价摘要（evaluation_summary）。

要求：
- 仅使用客观信息：人才称号、学术指标（h-index、引用数、论文数）、代表论文影响力、重要奖项、学术兼职
- 禁止主观评价
- 没有数据的维度直接跳过
- 严格100-150字

教授信息：
姓名：{profile.name}
h-index：{profile.h_index or "未知"}
总引用：{profile.citation_count or "未知"}
论文数：{profile.paper_count or "未知"}
奖项：{"、".join(profile.awards[:3]) if profile.awards else "无"}
学术兼职：{"、".join(profile.academic_positions[:3]) if profile.academic_positions else "无"}
代表论文引用：{"、".join(f"{p.title}({p.citation_count}引用)" for p in profile.top_papers[:3]) if profile.top_papers else "无"}

直接输出评价文本，不要包含任何前缀或标签："""


def validate_profile_summary(summary: str) -> bool:
    """Check profile_summary meets quality requirements."""
    if not summary:
        return False
    length = len(summary)
    if length < 200 or length > 300:
        return False
    if any(kw in summary for kw in BOILERPLATE_KEYWORDS):
        return False
    return True


def validate_evaluation_summary(summary: str) -> bool:
    """Check evaluation_summary meets quality requirements."""
    if not summary:
        return False
    length = len(summary)
    return 100 <= length <= 150


async def generate_summaries(
    *,
    profile: EnrichedProfessorProfile,
    llm_client: Any,
    llm_model: str,
) -> GeneratedSummaries:
    """Generate profile and evaluation summaries using LLM."""
    profile_prompt = build_profile_summary_prompt(profile)
    eval_prompt = build_evaluation_summary_prompt(profile)

    # Generate profile_summary
    profile_summary = await _generate_single_summary(
        llm_client, llm_model, profile_prompt,
        validator=validate_profile_summary,
        summary_type="profile",
    )

    # Generate evaluation_summary
    evaluation_summary = await _generate_single_summary(
        llm_client, llm_model, eval_prompt,
        validator=validate_evaluation_summary,
        summary_type="evaluation",
    )

    return GeneratedSummaries(
        profile_summary=profile_summary,
        evaluation_summary=evaluation_summary,
    )


async def _generate_single_summary(
    llm_client: Any,
    llm_model: str,
    prompt: str,
    *,
    validator: Any,
    summary_type: str,
) -> str:
    """Generate a single summary with one retry on validation failure."""
    for attempt in range(2):
        try:
            response = llm_client.chat.completions.create(
                model=llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个学术信息摘要助手。请直接输出摘要文本，不要包含JSON、标签或前缀。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=1024,
            )
            text = response.choices[0].message.content.strip()
            # Remove any markdown fencing
            text = re.sub(r"^```\w*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

            if validator(text):
                return text

            if attempt == 0:
                prompt += f"\n\n注意：上次输出长度为{len(text)}字，不符合要求。请严格控制字数。"
        except Exception as e:
            logger.warning("Summary generation attempt %d failed: %s", attempt + 1, e)

    # Return whatever we have, even if it doesn't validate
    return text if text else ""
