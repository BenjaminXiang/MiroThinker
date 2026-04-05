from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone

from src.data_agents.contracts import ProfessorRecord

from .models import AuthorPaperMetrics, DiscoveredPaper


_FOCUSED_TOPIC_RE = re.compile(
    r"课程思政|大语言模型|人工智能|机器学习|深度学习|计算机视觉|"
    r"机器人|芯片|集成电路|材料|肿瘤|免疫|哲学|教育"
)
_CHINESE_SEGMENT_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]{4,}")


def apply_paper_feedback_to_professors(
    *,
    professors: list[ProfessorRecord],
    papers: list[DiscoveredPaper],
    author_metrics: dict[str, AuthorPaperMetrics],
    now: datetime | None = None,
) -> list[ProfessorRecord]:
    updated_at = now or datetime.now(timezone.utc)
    papers_by_professor: dict[str, list[DiscoveredPaper]] = defaultdict(list)
    for paper in papers:
        for professor_id in paper.professor_ids:
            papers_by_professor[professor_id].append(paper)

    updated_professors: list[ProfessorRecord] = []
    for professor in professors:
        related_papers = sorted(
            papers_by_professor.get(professor.id, []),
            key=lambda paper: (paper.citation_count or 0, paper.year),
            reverse=True,
        )
        metrics = author_metrics.get(professor.id)
        profile_summary = _build_profile_summary_with_papers(
            professor,
            related_papers=related_papers,
        )
        evaluation_summary = _build_evaluation_summary_with_papers(
            professor,
            related_papers=related_papers,
            metrics=metrics,
        )
        updated_professors.append(
            professor.model_copy(
                update={
                    "research_directions": _merge_research_directions(
                        professor.research_directions,
                        related_papers,
                    ),
                    "h_index": metrics.h_index if metrics else professor.h_index,
                    "citation_count": (
                        metrics.citation_count
                        if metrics
                        else professor.citation_count
                    ),
                    "top_papers": [paper.title for paper in related_papers[:5]],
                    "profile_summary": profile_summary,
                    "evaluation_summary": evaluation_summary,
                    "last_updated": updated_at,
                }
            )
        )
    return updated_professors


def _merge_research_directions(
    current_directions: list[str],
    papers: list[DiscoveredPaper],
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [*current_directions, *_extract_paper_topics(papers)]:
        value = item.strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged


def _extract_paper_topics(papers: list[DiscoveredPaper]) -> list[str]:
    topics: list[str] = []
    for paper in papers:
        text = " ".join(part for part in (paper.title, paper.abstract or "") if part)
        topics.extend(_FOCUSED_TOPIC_RE.findall(text))
        for segment in _CHINESE_SEGMENT_RE.findall(text):
            if "课程思政" in segment:
                topics.append("课程思政")
            elif "人工智能" in segment:
                topics.append("人工智能")
            elif "集成电路" in segment:
                topics.append("集成电路")
    return topics


def _build_profile_summary_with_papers(
    professor: ProfessorRecord,
    *,
    related_papers: list[DiscoveredPaper],
) -> str:
    base_summary = professor.profile_summary.strip()
    if not related_papers:
        return base_summary
    top_titles = "、".join(paper.title for paper in related_papers[:3])
    return (
        f"{base_summary.rstrip('。')}。近期论文包括《{top_titles}》，"
        "论文信号已用于更新研究方向与代表成果字段。"
    )


def _build_evaluation_summary_with_papers(
    professor: ProfessorRecord,
    *,
    related_papers: list[DiscoveredPaper],
    metrics: AuthorPaperMetrics | None,
) -> str:
    summary = professor.evaluation_summary.strip()
    if not related_papers and metrics is None:
        return summary
    metrics_text = ""
    if metrics is not None:
        h_index = metrics.h_index if metrics.h_index is not None else 0
        citation_count = (
            metrics.citation_count if metrics.citation_count is not None else 0
        )
        metrics_text = f"h-index={h_index}，总引用数={citation_count}。"
    paper_text = ""
    if related_papers:
        paper_text = f"已关联{len(related_papers)}篇论文，代表作包括《{related_papers[0].title}》。"
    return f"{summary.rstrip('。')}。{metrics_text}{paper_text}".strip()
