from __future__ import annotations

import hashlib
import html
import re
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .models import DiscoveredPaper, ProfessorPaperDiscoveryResult

_CACHE_ROOT = (
    Path(__file__).resolve().parents[5]
    / "logs"
    / "debug"
    / "paper_google_scholar_cache"
)
_REQUEST_TIMEOUT_SECONDS = "30"
_PROFILE_URL_RE = re.compile(
    r"^https?://(?:scholar\.google\.[^/]+|scholar\.google\.com)/citations\?.*user=",
    re.IGNORECASE,
)
_TABLE_ROW_RE = re.compile(r"<tr[^>]*>(?P<body>.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TABLE_VALUE_RE = re.compile(
    r"gsc_rsb_std[^>]*>(?P<value>.*?)<", re.IGNORECASE | re.DOTALL
)
_LABEL_RE = re.compile(r"gsc_rsb_sth[^>]*>(?P<label>.*?)<", re.IGNORECASE | re.DOTALL)
_ARTICLE_ROW_RE = re.compile(
    r'<tr class="gsc_a_tr"[^>]*>(?P<body>.*?)</tr>', re.IGNORECASE | re.DOTALL
)
_TITLE_RE = re.compile(
    r'class="gsc_a_at"[^>]*>(?P<title>.*?)</a>', re.IGNORECASE | re.DOTALL
)
_GRAY_RE = re.compile(
    r'<div class="gs_gray"[^>]*>(?P<value>.*?)</div>', re.IGNORECASE | re.DOTALL
)
_CITATION_RE = re.compile(
    r'class="gsc_a_ac(?:\s+gs_ibl)?"[^>]*>(?P<value>[0-9,]+)</a>',
    re.IGNORECASE | re.DOTALL,
)
_YEAR_RE = re.compile(
    r'class="gsc_a_h(?:\s+gsc_a_hc\s+gs_ibl)?"[^>]*>(?P<year>\d{4})<',
    re.IGNORECASE | re.DOTALL,
)
_CITATION_FOR_VIEW_RE = re.compile(r"citation_for_view=([^&\"']+)")

RequestText = Callable[[str], str]


def discover_professor_paper_candidates_from_google_scholar_profile(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    profile_url: str,
    request_text: RequestText | None = None,
    max_papers: int = 20,
) -> ProfessorPaperDiscoveryResult:
    normalized_profile_url = _normalize_profile_url(profile_url)
    if normalized_profile_url is None:
        return _empty_result(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
        )

    fetch_text = request_text or _request_text
    try:
        payload = fetch_text(normalized_profile_url)
    except Exception:
        return _empty_result(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
        )

    citation_count, h_index = _extract_metrics(payload)
    papers = _extract_papers(
        payload,
        professor_id=professor_id,
        professor_name=professor_name,
        profile_url=normalized_profile_url,
        max_papers=max_papers,
    )
    author_id = (
        normalized_profile_url if (papers or citation_count or h_index) else None
    )

    return ProfessorPaperDiscoveryResult(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        author_id=author_id,
        h_index=h_index,
        citation_count=citation_count,
        papers=papers,
        paper_count=len(papers) or None,
        source="official_linked_google_scholar",
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
        source="official_linked_google_scholar",
        school_matched=True,
        fallback_used=False,
        name_disambiguation_conflict=False,
        candidate_count=0,
        query_name=professor_name,
    )


def _normalize_profile_url(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not _PROFILE_URL_RE.match(normalized):
        return None
    return normalized.replace("http://", "https://", 1)


def _request_text(url: str) -> str:
    cache_path = _CACHE_ROOT / f"{_cache_key(url)}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    payload = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            _REQUEST_TIMEOUT_SECONDS,
            "-A",
            "Mozilla/5.0",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(payload, encoding="utf-8")
    return payload


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _extract_metrics(payload: str) -> tuple[int | None, int | None]:
    citation_count: int | None = None
    h_index: int | None = None
    for row_match in _TABLE_ROW_RE.finditer(payload):
        body = row_match.group("body")
        label_match = _LABEL_RE.search(body)
        if label_match is None:
            continue
        label = _clean_text(label_match.group("label")).lower()
        values = [
            _parse_int(_clean_text(match.group("value")))
            for match in _TABLE_VALUE_RE.finditer(body)
        ]
        values = [value for value in values if value is not None]
        if not values:
            continue
        if "citation" in label or "引用" in label:
            citation_count = values[0]
        elif "h-index" in label or "h index" in label:
            h_index = values[0]
    return citation_count, h_index


def _extract_papers(
    payload: str,
    *,
    professor_id: str,
    professor_name: str,
    profile_url: str,
    max_papers: int,
) -> list[DiscoveredPaper]:
    papers: list[DiscoveredPaper] = []
    profile_key = _profile_key(profile_url)
    for index, row_match in enumerate(_ARTICLE_ROW_RE.finditer(payload), start=1):
        if len(papers) >= max_papers:
            break
        body = row_match.group("body")
        title_match = _TITLE_RE.search(body)
        if title_match is None:
            continue
        title = _clean_text(title_match.group("title"))
        if not title:
            continue
        gray_values = [
            _clean_text(match.group("value")) for match in _GRAY_RE.finditer(body)
        ]
        authors = _parse_authors(gray_values[0] if gray_values else "")
        venue = gray_values[1] if len(gray_values) > 1 else None
        citation_count = None
        citation_match = _CITATION_RE.search(body)
        if citation_match is not None:
            citation_count = _parse_int(citation_match.group("value"))
        year = None
        year_match = _YEAR_RE.search(body)
        if year_match is not None:
            year = _parse_int(year_match.group("year"))
        if year is None:
            continue
        paper_id = _extract_citation_for_view(body) or f"scholar:{profile_key}:{index}"
        papers.append(
            DiscoveredPaper(
                paper_id=paper_id,
                title=title,
                year=year,
                publication_date=None,
                venue=venue,
                doi=None,
                arxiv_id=None,
                abstract=None,
                authors=tuple(authors) or (professor_name,),
                professor_ids=(professor_id,),
                citation_count=citation_count,
                source_url=profile_url,
            )
        )
    return papers


def _profile_key(profile_url: str) -> str:
    query = parse_qs(urlparse(profile_url).query)
    user_values = query.get("user")
    if user_values:
        return user_values[0]
    return _cache_key(profile_url)[:12]


def _extract_citation_for_view(body: str) -> str | None:
    match = _CITATION_FOR_VIEW_RE.search(body)
    if match is None:
        return None
    return html.unescape(match.group(1))


def _parse_authors(value: str) -> list[str]:
    if not value:
        return []
    authors: list[str] = []
    for raw in value.split(","):
        normalized = raw.strip()
        if not normalized or normalized == "...":
            continue
        authors.append(normalized)
    return authors


def _parse_int(value: str | None) -> int | None:
    digits = re.sub(r"[^0-9]", "", value or "")
    if not digits:
        return None
    return int(digits)


def _clean_text(value: str | None) -> str:
    normalized = html.unescape(value or "")
    normalized = re.sub(r"<[^>]+>", "", normalized)
    normalized = normalized.replace("\u202a", "").replace("\u202c", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" ,;:\n\t")
