from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.contracts import PaperRecord, ReleasedObject
from src.data_agents.evidence import build_evidence
from src.data_agents.normalization import build_stable_id
from src.data_agents.publish import publish_jsonl

from .models import DiscoveredPaper

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}|[\u3400-\u4DBF\u4E00-\u9FFF]{2,8}")


@dataclass(frozen=True, slots=True)
class PaperReleaseReport:
    input_paper_count: int
    released_record_count: int
    duplicate_paper_count: int
    skipped_record_count: int
    skip_reasons: dict[str, int]


@dataclass(frozen=True, slots=True)
class PaperReleaseResult:
    paper_records: list[PaperRecord]
    released_objects: list[ReleasedObject]
    report: PaperReleaseReport


def build_paper_release(
    *,
    papers: list[DiscoveredPaper],
    now: datetime | None = None,
) -> PaperReleaseResult:
    generated_at = now or datetime.now(timezone.utc)
    merged_papers = _dedupe_papers(papers)
    paper_records: list[PaperRecord] = []
    released_objects: list[ReleasedObject] = []
    skip_reasons: Counter[str] = Counter()

    for paper in merged_papers:
        summary_zh = _build_summary_zh(paper)
        try:
            record = PaperRecord(
                id=build_stable_id("paper", _paper_identity_key(paper)),
                title=paper.title,
                title_zh=paper.title,
                authors=list(paper.authors),
                year=paper.year,
                venue=paper.venue,
                doi=paper.doi,
                arxiv_id=paper.arxiv_id,
                abstract=paper.abstract,
                publication_date=paper.publication_date,
                keywords=_extract_keywords(paper),
                citation_count=paper.citation_count,
                pdf_path=None,
                professor_ids=list(dict.fromkeys(paper.professor_ids)),
                summary_zh=summary_zh,
                summary_text=summary_zh,
                evidence=[
                    build_evidence(
                        source_type="academic_platform",
                        source_url=paper.source_url,
                        fetched_at=generated_at,
                        confidence=0.8,
                    )
                ],
                last_updated=generated_at,
            )
        except Exception:
            skip_reasons["contract_validation_failed"] += 1
            continue

        paper_records.append(record)
        released_objects.append(record.to_released_object())

    report = PaperReleaseReport(
        input_paper_count=len(papers),
        released_record_count=len(paper_records),
        duplicate_paper_count=len(papers) - len(merged_papers),
        skipped_record_count=len(merged_papers) - len(paper_records),
        skip_reasons=dict(skip_reasons),
    )
    return PaperReleaseResult(
        paper_records=paper_records,
        released_objects=released_objects,
        report=report,
    )


def publish_paper_release(
    release_result: PaperReleaseResult,
    *,
    paper_records_path: Path,
    released_objects_path: Path,
) -> None:
    publish_jsonl(paper_records_path, release_result.paper_records)
    publish_jsonl(released_objects_path, release_result.released_objects)


def _dedupe_papers(papers: list[DiscoveredPaper]) -> list[DiscoveredPaper]:
    merged: dict[str, DiscoveredPaper] = {}
    for paper in papers:
        key = _paper_identity_key(paper)
        current = merged.get(key)
        if current is None:
            merged[key] = paper
            continue
        merged[key] = _merge_paper(current, paper)
    return list(merged.values())


def _merge_paper(current: DiscoveredPaper, candidate: DiscoveredPaper) -> DiscoveredPaper:
    return DiscoveredPaper(
        paper_id=current.paper_id if len(current.paper_id) >= len(candidate.paper_id) else candidate.paper_id,
        title=current.title if len(current.title) >= len(candidate.title) else candidate.title,
        year=max(current.year, candidate.year),
        publication_date=current.publication_date or candidate.publication_date,
        venue=current.venue or candidate.venue,
        doi=current.doi or candidate.doi,
        arxiv_id=current.arxiv_id or candidate.arxiv_id,
        abstract=current.abstract if len(current.abstract or "") >= len(candidate.abstract or "") else candidate.abstract,
        authors=current.authors if len(current.authors) >= len(candidate.authors) else candidate.authors,
        professor_ids=tuple(dict.fromkeys([*current.professor_ids, *candidate.professor_ids])),
        citation_count=max(current.citation_count or 0, candidate.citation_count or 0),
        source_url=current.source_url or candidate.source_url,
    )


def _paper_identity_key(paper: DiscoveredPaper) -> str:
    if paper.doi:
        return f"doi:{paper.doi.strip().lower()}"
    if paper.arxiv_id:
        return f"arxiv:{paper.arxiv_id.strip().lower()}"
    return "|".join(
        [
            "title",
            re.sub(r"\s+", "", paper.title).lower(),
            str(paper.year),
            ",".join(sorted(author.strip().lower() for author in paper.authors if author.strip())),
        ]
    )


def _build_summary_zh(paper: DiscoveredPaper) -> str:
    title = paper.title.strip()
    venue = (paper.venue or "未标注期刊/会议").strip()
    abstract = (paper.abstract or "暂无公开摘要，当前摘要依据标题和发表信息生成。").strip()
    keywords = "、".join(_extract_keywords(paper)[:5]) or "暂无关键词"
    result = (
        f"what：论文《{title}》发表于{paper.year}年，发表载体为{venue}。"
        f" why：该工作围绕{keywords}等主题展开，可为相关研究检索和教授画像更新提供近期成果信号。"
        f" how：摘要要点为：{abstract}"
        f" result：当前记录已关联教授ID {', '.join(dict.fromkeys(paper.professor_ids))}，"
        f"引用数为{paper.citation_count or 0}。"
    )
    return result


def _extract_keywords(paper: DiscoveredPaper) -> list[str]:
    text = " ".join(part for part in (paper.title, paper.abstract or "") if part)
    keywords: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(text):
        item = token.strip()
        if len(item) < 2:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        keywords.append(item)
        if len(keywords) >= 12:
            break
    return keywords
