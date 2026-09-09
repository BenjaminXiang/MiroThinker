from __future__ import annotations

import hashlib
import re
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Callable

import pdfminer.high_level
import requests

from .models import DiscoveredPaper, ProfessorPaperDiscoveryResult

_CACHE_ROOT = (
    Path(__file__).resolve().parents[5] / "logs" / "debug" / "paper_cv_pdf_cache"
)
_REQUEST_TIMEOUT = (5, 30)
_CV_URL_RE = re.compile(r"^https?://.+\.pdf(?:\?.*)?$", re.IGNORECASE)
_HEAD_LIMIT_LINES = 160
_PUBLICATION_ENTRY_RE = re.compile(
    r"(?P<label>(?:\([JC]\d+\)|\[[JC]\d+\]))\s*(?P<body>.*?)(?=(?:\n(?:\([JC]\d+\)|\[[JC]\d+\]))|\Z)",
    re.DOTALL,
)
_TITLE_PATTERNS = (
    re.compile(r"[“\"](?P<title>[^”\"]{10,260})[”\"]"),
    re.compile(r"《(?P<title>[^》]{5,260})》"),
)
_JOURNAL_COUNT_RE = re.compile(
    r"([0-9]{1,5})\s+(?:journal(?:/magazine)?|journal articles?)\s+papers?",
    re.IGNORECASE,
)
_CONFERENCE_COUNT_RE = re.compile(r"([0-9]{1,5})\s+conference\s+papers?", re.IGNORECASE)
_GENERIC_PAPER_COUNT_PATTERNS = (
    re.compile(
        r"(?:发表|已发表|累计发表|共发表)(?:了)?\s*([0-9]{1,5})\s*(?:余|多)?\s*篇\s*(?:学术|研究|SCI|高水平)?\s*论文"
    ),
    re.compile(
        r"(?:published|has published)\s+(?:over|more than|about|approximately)?\s*([0-9]{1,5})\s+(?:research\s+)?(?:papers?|publications?)",
        re.IGNORECASE,
    ),
)
_H_INDEX_PATTERNS = (
    re.compile(r"\bH[- ]?Index\b\s*[:：]?\s*([0-9]{1,4})", re.IGNORECASE),
    re.compile(r"\bh-index\b\s*(?:is|=|:)?\s*([0-9]{1,4})", re.IGNORECASE),
)
_CITATION_PATTERNS = (
    re.compile(r"\bGoogle Scholar citations?\b\s*[:：]?\s*([0-9]{1,7})", re.IGNORECASE),
    re.compile(r"\bcitations?\b\s*[:：]?\s*([0-9]{1,7})", re.IGNORECASE),
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_LIGATURES = str.maketrans(
    {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }
)

RequestBytes = Callable[[str], bytes]
ExtractText = Callable[[bytes], str]


def discover_professor_paper_candidates_from_cv_pdf(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    cv_url: str,
    request_bytes: RequestBytes | None = None,
    extract_text: ExtractText | None = None,
    max_papers: int = 20,
) -> ProfessorPaperDiscoveryResult:
    normalized_cv_url = _normalize_cv_url(cv_url)
    if normalized_cv_url is None:
        return _empty_result(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
        )

    fetch_bytes = request_bytes or _request_bytes
    extract_text_fn = extract_text or _extract_text
    try:
        pdf_bytes = fetch_bytes(normalized_cv_url)
        text = _normalize_text(extract_text_fn(pdf_bytes))
    except Exception:
        return _empty_result(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
        )

    papers = _extract_publication_papers(
        text,
        professor_id=professor_id,
        professor_name=professor_name,
        cv_url=normalized_cv_url,
        max_papers=max_papers,
    )
    paper_count = _extract_paper_count(text) or (len(papers) or None)
    h_index = _extract_metric(text, _H_INDEX_PATTERNS)
    citation_count = _extract_metric(text, _CITATION_PATTERNS)
    author_id = (
        normalized_cv_url
        if (papers or paper_count or h_index or citation_count)
        else None
    )

    return ProfessorPaperDiscoveryResult(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        author_id=author_id,
        h_index=h_index,
        citation_count=citation_count,
        papers=papers,
        paper_count=paper_count,
        source="official_linked_cv",
        school_matched=True,
        fallback_used=False,
        name_disambiguation_conflict=False,
        candidate_count=1 if author_id else 0,
        query_name=professor_name,
    )


def _empty_result(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
) -> ProfessorPaperDiscoveryResult:
    return ProfessorPaperDiscoveryResult(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        author_id=None,
        h_index=None,
        citation_count=None,
        papers=[],
        paper_count=None,
        source="official_linked_cv",
        school_matched=True,
        fallback_used=False,
        name_disambiguation_conflict=False,
        candidate_count=0,
        query_name=professor_name,
    )


def _normalize_cv_url(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not _CV_URL_RE.match(normalized):
        return None
    return normalized


def _request_bytes(url: str) -> bytes:
    cache_path = _CACHE_ROOT / f"{_cache_key(url)}.pdf"
    if cache_path.exists():
        return cache_path.read_bytes()

    headers = {
        "User-Agent": "MiroThinker-ProfessorAgent/1.0",
        "Accept": "application/pdf,*/*",
    }
    try:
        response = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.content
    except Exception:
        payload = subprocess.run(
            ["curl", "-fsSL", "--max-time", "30", "-A", headers["User-Agent"], url],
            check=True,
            capture_output=True,
        ).stdout

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(payload)
    return payload


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _extract_text(pdf_bytes: bytes) -> str:
    return pdfminer.high_level.extract_text(BytesIO(pdf_bytes))


def _normalize_text(text: str) -> str:
    normalized = (text or "").translate(_LIGATURES).replace("\f", "\n")
    normalized = re.sub(r"[ \t\r\v]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _extract_metric(text: str, patterns: tuple[re.Pattern[str], ...]) -> int | None:
    head = _head_text(text)
    values: list[int] = []
    for pattern in patterns:
        for match in pattern.finditer(head):
            try:
                values.append(int(match.group(1)))
            except (TypeError, ValueError):
                continue
    return max(values, default=None)


def _head_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:_HEAD_LIMIT_LINES])


def _extract_paper_count(text: str) -> int | None:
    head = _head_text(text)
    category_counts: list[int] = []
    for pattern in (_JOURNAL_COUNT_RE, _CONFERENCE_COUNT_RE):
        for match in pattern.finditer(head):
            try:
                category_counts.append(int(match.group(1)))
            except (TypeError, ValueError):
                continue
    if category_counts:
        return sum(category_counts)

    generic_counts: list[int] = []
    for pattern in _GENERIC_PAPER_COUNT_PATTERNS:
        for match in pattern.finditer(head):
            try:
                generic_counts.append(int(match.group(1)))
            except (TypeError, ValueError):
                continue
    return max(generic_counts, default=None)


def _extract_publication_papers(
    text: str,
    *,
    professor_id: str,
    professor_name: str,
    cv_url: str,
    max_papers: int,
) -> list[DiscoveredPaper]:
    papers: list[DiscoveredPaper] = []
    url_key = _cache_key(cv_url)[:12]
    for index, match in enumerate(_PUBLICATION_ENTRY_RE.finditer(text), start=1):
        if len(papers) >= max_papers:
            break
        label = match.group("label")
        if not (label.startswith("(J") or label.startswith("[C")):
            continue
        body = re.sub(r"\s+", " ", match.group("body")).strip()
        title = _extract_title(body)
        year = _extract_year(body)
        if not title or year is None:
            continue
        venue = _extract_venue(body, title)
        papers.append(
            DiscoveredPaper(
                paper_id=f"cv:{url_key}:{index}",
                title=title,
                year=year,
                publication_date=None,
                venue=venue,
                doi=None,
                arxiv_id=None,
                abstract=None,
                authors=(professor_name,),
                professor_ids=(professor_id,),
                citation_count=None,
                source_url=cv_url,
            )
        )
    return papers


def _extract_title(body: str) -> str | None:
    for pattern in _TITLE_PATTERNS:
        match = pattern.search(body)
        if match is not None:
            title = re.sub(r"\s+", " ", match.group("title")).strip(" ,.;:")
            if title:
                return title
    return None


def _extract_year(body: str) -> int | None:
    matches = _YEAR_RE.findall(body)
    if not matches:
        return None
    year_match = re.search(r"\b((?:19|20)\d{2})\b", body[::-1])
    if year_match is None:
        all_years = re.findall(r"\b((?:19|20)\d{2})\b", body)
        return int(all_years[-1]) if all_years else None
    return int(year_match.group(1)[::-1])


def _extract_venue(body: str, title: str) -> str | None:
    remainder: str | None = None
    for pattern in _TITLE_PATTERNS:
        match = pattern.search(body)
        if match is None:
            continue
        candidate = match.group("title")
        if re.sub(r"\s+", " ", candidate).strip(" ,.;:") != title:
            continue
        remainder = body[match.end() :]
        break
    if remainder is None:
        return None
    normalized = remainder.lstrip(" ,.;:-")
    if not normalized:
        return None
    venue = normalized.split(",", 1)[0].strip(" ,.;:-")
    return venue or None
