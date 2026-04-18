from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from pathlib import Path

from src.data_agents.contracts import PaperRecord, ReleasedObject
from src.data_agents.evidence import build_evidence
from src.data_agents.normalization import build_stable_id
from src.data_agents.publish import publish_jsonl

from .models import DiscoveredPaper
from .title_cleaner import clean_paper_title

logger = logging.getLogger(__name__)

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
        cleaned_title = clean_paper_title(paper.title)
        summary_zh = _build_summary_zh(paper)
        try:
            record = PaperRecord(
                id=build_stable_id("paper", _paper_identity_key(paper)),
                title=cleaned_title,
                title_zh=cleaned_title,
                authors=list(paper.authors),
                year=paper.year,
                venue=paper.venue,
                doi=paper.doi,
                arxiv_id=paper.arxiv_id,
                abstract=paper.abstract,
                publication_date=paper.publication_date,
                keywords=_extract_keywords(paper),
                citation_count=paper.citation_count,
                fields_of_study=list(paper.fields_of_study),
                tldr=paper.tldr,
                license=paper.license,
                funders=list(paper.funders),
                oa_status=paper.oa_status,
                reference_count=paper.reference_count,
                enrichment_sources=list(paper.enrichment_sources),
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
        except ValidationError:
            skip_reasons["contract_validation_failed"] += 1
            continue
        except Exception:
            logger.exception("Unexpected paper release failure for %s", paper.paper_id)
            raise

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


def _merge_paper(
    current: DiscoveredPaper, candidate: DiscoveredPaper
) -> DiscoveredPaper:
    return DiscoveredPaper(
        paper_id=current.paper_id
        if len(current.paper_id) >= len(candidate.paper_id)
        else candidate.paper_id,
        title=(
            current.title
            if len(clean_paper_title(current.title))
            >= len(clean_paper_title(candidate.title))
            else candidate.title
        ),
        year=max(current.year, candidate.year),
        publication_date=current.publication_date or candidate.publication_date,
        venue=current.venue or candidate.venue,
        doi=current.doi or candidate.doi,
        arxiv_id=current.arxiv_id or candidate.arxiv_id,
        abstract=current.abstract
        if len(current.abstract or "") >= len(candidate.abstract or "")
        else candidate.abstract,
        authors=current.authors
        if len(current.authors) >= len(candidate.authors)
        else candidate.authors,
        professor_ids=tuple(
            dict.fromkeys([*current.professor_ids, *candidate.professor_ids])
        ),
        citation_count=max(current.citation_count or 0, candidate.citation_count or 0),
        source_url=current.source_url or candidate.source_url,
        fields_of_study=_merge_unique_strings(
            current.fields_of_study, candidate.fields_of_study
        ),
        tldr=current.tldr or candidate.tldr,
        license=current.license or candidate.license,
        funders=_merge_unique_strings(current.funders, candidate.funders),
        oa_status=current.oa_status or candidate.oa_status,
        reference_count=max(
            current.reference_count or 0, candidate.reference_count or 0
        )
        or None,
        enrichment_sources=_merge_unique_strings(
            current.enrichment_sources,
            candidate.enrichment_sources,
        ),
    )


def _paper_identity_key(paper: DiscoveredPaper) -> str:
    if paper.doi:
        return f"doi:{paper.doi.strip().lower()}"
    if paper.arxiv_id:
        return f"arxiv:{paper.arxiv_id.strip().lower()}"
    return "|".join(
        [
            "title",
            re.sub(r"\s+", "", clean_paper_title(paper.title)).lower(),
            str(paper.year),
            ",".join(
                sorted(
                    author.strip().lower() for author in paper.authors if author.strip()
                )
            ),
        ]
    )


def _build_summary_zh(paper: DiscoveredPaper) -> str:
    title = clean_paper_title(paper.title).strip()
    venue = (paper.venue or "未标注期刊/会议").strip()
    abstract = (
        paper.abstract or "暂无公开摘要，当前摘要依据标题和发表信息生成。"
    ).strip()
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


def _merge_unique_strings(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in [*left, *right]:
        item = value.strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return tuple(merged)
