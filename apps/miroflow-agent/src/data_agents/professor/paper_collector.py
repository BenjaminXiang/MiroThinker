# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Stage 2b — Paper collection and paper-driven research direction generation.

Orchestrates multi-source paper collection, generates research directions
via LLM clustering, selects top papers, and produces PaperStagingRecords.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from .academic_tools import (
    PaperCollectionResult,
    RawPaperRecord,
    collect_papers,
)
from .cross_domain import PaperLink, PaperStagingRecord

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True)
class PaperEnrichmentResult:
    """Result of Stage 2b for one professor."""

    research_directions: list[str]
    research_directions_source: str  # "paper_driven" | "official_only" | "merged"
    h_index: int | None
    citation_count: int | None
    paper_count: int | None
    top_papers: list[PaperLink]
    staging_records: list[PaperStagingRecord]
    disambiguation_confidence: float


async def enrich_from_papers(
    *,
    name: str,
    name_en: str | None,
    institution: str,
    institution_en: str | None,
    official_directions: list[str],
    professor_id: str,
    fetch_html: Any,
    llm_client: Any,
    llm_model: str,
    timeout: float = 30.0,
) -> PaperEnrichmentResult:
    """Run Stage 2b paper enrichment for one professor."""
    collection = collect_papers(
        name=name,
        name_en=name_en,
        institution=institution,
        institution_en=institution_en,
        existing_directions=official_directions,
        fetch_html=fetch_html,
        timeout=timeout,
    )

    if not collection.papers:
        return PaperEnrichmentResult(
            research_directions=official_directions,
            research_directions_source="official_only",
            h_index=collection.author_info.h_index if collection.author_info else None,
            citation_count=collection.author_info.citation_count if collection.author_info else None,
            paper_count=collection.author_info.paper_count if collection.author_info else None,
            top_papers=[],
            staging_records=[],
            disambiguation_confidence=collection.disambiguation_confidence,
        )

    directions, source = await generate_research_directions(
        papers=collection.papers,
        official_directions=official_directions,
        llm_client=llm_client,
        llm_model=llm_model,
    )

    top_papers = select_top_papers(collection.papers, limit=5)
    staging = build_staging_records(
        collection.papers,
        professor_id=professor_id,
        professor_name=name,
        institution=institution,
    )

    return PaperEnrichmentResult(
        research_directions=directions,
        research_directions_source=source,
        h_index=collection.author_info.h_index if collection.author_info else None,
        citation_count=collection.author_info.citation_count if collection.author_info else None,
        paper_count=collection.author_info.paper_count if collection.author_info else None,
        top_papers=top_papers,
        staging_records=staging,
        disambiguation_confidence=collection.disambiguation_confidence,
    )


async def generate_research_directions(
    *,
    papers: list[RawPaperRecord],
    official_directions: list[str],
    llm_client: Any,
    llm_model: str,
) -> tuple[list[str], str]:
    """Generate research directions by LLM clustering of paper titles/abstracts.

    Returns (directions, source_type) where source_type is one of:
    "paper_driven", "official_only", "merged".
    """
    if not papers:
        return official_directions, "official_only"

    paper_text = _build_paper_text_for_clustering(papers)
    prompt = _build_direction_prompt(paper_text, official_directions)

    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个学术方向分析助手。分析论文标题和摘要，"
                        "提取3-7个精细的研究方向标签。输出JSON数组。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        text = response.choices[0].message.content
        paper_directions = _parse_directions_response(text)
    except Exception:
        logger.warning("LLM direction clustering failed, using official directions")
        return official_directions, "official_only"

    if not paper_directions:
        return official_directions, "official_only"

    if official_directions:
        merged = _merge_directions(paper_directions, official_directions)
        return merged, "merged"

    return paper_directions, "paper_driven"


def select_top_papers(
    papers: list[RawPaperRecord],
    *,
    limit: int = 5,
) -> list[PaperLink]:
    """Select top papers by citation count, ensuring at least one recent paper."""
    if not papers:
        return []

    sorted_papers = sorted(
        papers,
        key=lambda p: p.citation_count or 0,
        reverse=True,
    )

    selected = sorted_papers[:limit]

    # Ensure at least one recent paper (last 2 years)
    import datetime

    current_year = datetime.datetime.now(datetime.timezone.utc).year
    has_recent = any(p.year and p.year >= current_year - 2 for p in selected)

    if not has_recent:
        recent = [p for p in papers if p.year and p.year >= current_year - 2]
        if recent:
            best_recent = max(recent, key=lambda p: p.citation_count or 0)
            if best_recent not in selected:
                selected = selected[: limit - 1] + [best_recent]

    return [
        PaperLink(
            title=p.title,
            year=p.year,
            venue=p.venue,
            citation_count=p.citation_count,
            doi=p.doi,
            source=p.source,
        )
        for p in selected[:limit]
    ]


def build_staging_records(
    papers: list[RawPaperRecord],
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
) -> list[PaperStagingRecord]:
    """Convert RawPaperRecords to PaperStagingRecords for paper domain consumption."""
    return [
        PaperStagingRecord(
            title=p.title,
            authors=p.authors,
            year=p.year,
            venue=p.venue,
            abstract=p.abstract,
            doi=p.doi,
            citation_count=p.citation_count,
            keywords=p.keywords,
            source_url=p.source_url,
            source=p.source,
            anchoring_professor_id=professor_id,
            anchoring_professor_name=professor_name,
            anchoring_institution=institution,
        )
        for p in papers
    ]


def _build_paper_text_for_clustering(
    papers: list[RawPaperRecord],
    max_chars: int = 4000,
) -> str:
    """Build concatenated text from paper titles and abstracts for LLM input."""
    parts: list[str] = []
    total = 0
    for p in papers:
        entry = f"- {p.title}"
        if p.abstract:
            entry += f": {p.abstract[:200]}"
        if p.keywords:
            entry += f" [{', '.join(p.keywords[:5])}]"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)
    return "\n".join(parts)


def _build_direction_prompt(
    paper_text: str,
    official_directions: list[str],
) -> str:
    prompt = f"""请分析以下论文列表，提取该作者的3-7个精细研究方向标签。

要求：
- 标签要具体到二级领域（如"基于Transformer的蛋白质结构预测"而非"人工智能"）
- 如果有近期研究方向转变，突出新方向
- 去除过于宽泛的标签
- 输出JSON数组格式，如 ["方向1", "方向2", ...]

论文列表：
{paper_text}
"""
    if official_directions:
        prompt += f"\n官网已标注的方向（供参考，可补充但不必全部采用）：{', '.join(official_directions)}"

    return prompt


def _parse_directions_response(text: str) -> list[str]:
    """Parse LLM response to extract direction list."""
    # Try JSON fence first
    match = _JSON_FENCE_RE.search(text)
    content = match.group(1).strip() if match else text.strip()

    # Find JSON array in text
    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []

    try:
        raw = json.loads(content[start : end + 1])
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _merge_directions(
    paper_directions: list[str],
    official_directions: list[str],
) -> list[str]:
    """Merge paper-driven and official directions, deduplicating."""
    merged: list[str] = []
    seen_lower: set[str] = set()

    # Paper directions first (higher priority)
    for d in paper_directions:
        key = d.strip().lower()
        if key not in seen_lower:
            seen_lower.add(key)
            merged.append(d.strip())

    # Add official directions not covered
    for d in official_directions:
        key = d.strip().lower()
        if key not in seen_lower:
            # Check if paper direction already covers this (substring match)
            if not any(key in existing.lower() for existing in merged):
                seen_lower.add(key)
                merged.append(d.strip())

    return merged[:7]  # Cap at 7 directions
