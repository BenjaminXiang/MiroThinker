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
from .translation_spec import LLM_EXTRA_BODY

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


def _build_affiliation_text(profile: EnrichedProfessorProfile) -> str:
    institution = profile.institution.strip() or "所属高校"
    department = (profile.department or "").strip()
    title = (profile.title or "").strip()
    if department and title:
        return f"{institution}{department}{title}"
    if department:
        return f"{institution}{department}教师"
    if title:
        return f"{institution}{title}"
    return f"{institution}教师"


def _ensure_sentence(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if text.endswith(("。", "！", "？")):
        return text
    return f"{text}。"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _ensure_summary_length(
    text: str,
    *,
    min_length: int,
    max_length: int,
    padding_sentences: tuple[str, ...],
) -> str:
    normalized = text.strip()
    if not normalized:
        normalized = ""
    normalized = _coerce_summary_length(normalized, min_length=min_length, max_length=max_length)
    if len(normalized) >= min_length:
        return normalized

    segments = [segment for segment in re.split(r"(?<=[。！？])", normalized) if segment.strip()]
    for sentence in padding_sentences:
        candidate = _ensure_sentence(sentence)
        if candidate not in segments:
            segments.append(candidate)
        joined = "".join(segments).strip()
        joined = _coerce_summary_length(joined, min_length=min_length, max_length=max_length)
        if len(joined) >= min_length:
            return joined

    fallback_tail = (
        "该摘要基于当前已核验的身份、研究方向与成果字段生成，可用于后续检索与人工复核。"
    )
    segments.append(fallback_tail)
    return _coerce_summary_length("".join(segments).strip(), min_length=min_length, max_length=max_length)


def _build_fallback_profile_summary(profile: EnrichedProfessorProfile) -> str:
    name = profile.name.strip() or "该教师"
    parts: list[str] = [f"{name}现任{_build_affiliation_text(profile)}。"]

    if profile.research_directions:
        directions = "、".join(_dedupe_preserve_order(profile.research_directions)[:5])
        parts.append(f"研究方向聚焦{directions}，相关描述来自官网结构化字段与个人资料页正文。")

    metric_fragments: list[str] = []
    if profile.paper_count:
        metric_fragments.append(f"已识别论文{profile.paper_count}篇")
    if profile.h_index:
        metric_fragments.append(f"h-index为{profile.h_index}")
    if profile.citation_count:
        metric_fragments.append(f"总引用约{profile.citation_count}")
    if profile.top_papers:
        representative_titles = "、".join(p.title for p in profile.top_papers[:2] if p.title.strip())
        if representative_titles:
            metric_fragments.append(f"代表论文包括{representative_titles}")
    if metric_fragments:
        parts.append("，".join(metric_fragments) + "。")

    if profile.awards:
        awards = "、".join(_dedupe_preserve_order(profile.awards)[:3])
        parts.append(f"公开资料中的代表性荣誉包括{awards}。")

    if profile.academic_positions:
        positions = "、".join(_dedupe_preserve_order(profile.academic_positions)[:2])
        parts.append(f"现有记录中的学术任职包括{positions}。")

    if profile.education_structured:
        education = "、".join(
            f"{item.school}{item.degree or ''}".strip()
            for item in profile.education_structured[:2]
            if item.school
        )
        if education:
            parts.append(f"教育背景包括{education}。")

    if profile.work_experience:
        recent_roles = "、".join(
            f"{item.organization}{item.role or ''}".strip()
            for item in profile.work_experience[:2]
            if item.organization
        )
        if recent_roles:
            parts.append(f"关键履历涵盖{recent_roles}。")

    base = "".join(_ensure_sentence(part) for part in parts if part.strip())
    return _ensure_summary_length(
        base,
        min_length=200,
        max_length=300,
        padding_sentences=(
            "摘要仅汇总当前已验证的身份、方向与成果信息，不对缺失经历做推断。",
            "现阶段可直接支撑按学校、院系与研究方向的细粒度检索与人工复核。",
        ),
    )


def _build_fallback_evaluation_summary(profile: EnrichedProfessorProfile) -> str:
    name = profile.name.strip() or "该教师"
    parts: list[str] = [name]
    metrics: list[str] = []
    if profile.h_index is not None:
        metrics.append(f"h-index为{profile.h_index}")
    if profile.citation_count is not None:
        metrics.append(f"总引用约{profile.citation_count}")
    if profile.paper_count is not None:
        metrics.append(f"论文数为{profile.paper_count}")
    if metrics:
        parts.append("，".join(metrics) + "。")
    if profile.awards:
        parts.append(f"代表性荣誉包括{'、'.join(_dedupe_preserve_order(profile.awards)[:2])}。")
    if profile.academic_positions:
        parts.append(f"学术任职包括{'、'.join(_dedupe_preserve_order(profile.academic_positions)[:2])}。")
    if profile.top_papers:
        top_title = next((paper.title for paper in profile.top_papers if paper.title.strip()), "")
        if top_title:
            parts.append(f"已识别代表论文《{top_title}》。")

    base = "".join(_ensure_sentence(part) for part in parts if part.strip())
    return _ensure_summary_length(
        base,
        min_length=100,
        max_length=150,
        padding_sentences=(
            "当前评价仅汇总已验证的客观指标与任职信息。",
            "可用于事实检索与后续人工复核。",
        ),
    )


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

    if not validate_profile_summary(profile_summary):
        profile_summary = _build_fallback_profile_summary(profile)
    if not validate_evaluation_summary(evaluation_summary):
        evaluation_summary = _build_fallback_evaluation_summary(profile)

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
    text = ""
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
                extra_body=LLM_EXTRA_BODY,
            )
            text = response.choices[0].message.content.strip()
            # Remove any markdown fencing
            text = re.sub(r"^```\w*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()
            if summary_type == "profile":
                text = _coerce_summary_length(text, min_length=200, max_length=300)
            elif summary_type == "evaluation":
                text = _coerce_summary_length(text, min_length=100, max_length=150)

            if validator(text):
                return text

            if attempt == 0:
                prompt += f"\n\n注意：上次输出长度为{len(text)}字，不符合要求。请严格控制字数。"
        except Exception as e:
            logger.warning("Summary generation attempt %d failed: %s", attempt + 1, e)

    # Return whatever we have, even if it doesn't validate
    return text if text else ""


def _coerce_summary_length(text: str, *, min_length: int, max_length: int) -> str:
    if len(text) <= max_length:
        return text

    cut_positions = [
        text.rfind(marker, min_length - 1, max_length + 1)
        for marker in ("。", "！", "？")
    ]
    cut_at = max(cut_positions)
    if cut_at != -1 and min_length <= cut_at + 1 <= max_length:
        return text[: cut_at + 1].strip()
    return text[:max_length].strip()
