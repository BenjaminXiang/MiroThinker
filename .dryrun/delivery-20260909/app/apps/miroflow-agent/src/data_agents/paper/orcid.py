from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Callable

import requests

from .models import DiscoveredPaper, ProfessorPaperDiscoveryResult

_CACHE_ROOT = (
    Path(__file__).resolve().parents[5] / "logs" / "debug" / "paper_orcid_cache"
)
_REQUEST_TIMEOUT = (5, 20)
_ORCID_ID_RE = re.compile(r"(?P<id>\d{4}-\d{4}-\d{4}-\d{3}[0-9X])", re.IGNORECASE)

RequestJson = Callable[[str], dict[str, object]]


def discover_professor_paper_candidates_from_orcid(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    orcid_url: str,
    request_json: RequestJson | None = None,
    max_papers: int = 20,
) -> ProfessorPaperDiscoveryResult:
    normalized_orcid_url = _normalize_orcid_url(orcid_url)
    if normalized_orcid_url is None:
        return _empty_result(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
        )

    fetch_json = request_json or _request_json
    works_url = (
        normalized_orcid_url.replace(
            "https://orcid.org/", "https://pub.orcid.org/v3.0/"
        )
        + "/works"
    )
    payload = fetch_json(works_url)
    groups = payload.get("group")
    if not isinstance(groups, list):
        groups = []

    papers: list[DiscoveredPaper] = []
    for index, group in enumerate(groups):
        if len(papers) >= max_papers:
            break
        paper = _group_to_discovered_paper(
            group,
            professor_id=professor_id,
            professor_name=professor_name,
            normalized_orcid_url=normalized_orcid_url,
            fallback_index=index,
        )
        if paper is not None:
            papers.append(paper)

    return ProfessorPaperDiscoveryResult(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        author_id=normalized_orcid_url,
        h_index=None,
        citation_count=None,
        papers=papers,
        paper_count=len(groups) or (len(papers) or None),
        source="official_linked_orcid",
        school_matched=True,
        fallback_used=False,
        name_disambiguation_conflict=False,
        candidate_count=1,
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
        source="official_linked_orcid",
        school_matched=True,
        fallback_used=False,
        name_disambiguation_conflict=False,
        candidate_count=0,
        query_name=professor_name,
    )


def _request_json(url: str) -> dict[str, object]:
    cache_path = _CACHE_ROOT / f"{_cache_key(url)}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload

    response = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MiroThinker-ProfessorAgent/1.0",
        },
        timeout=_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected ORCID payload from {url}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _normalize_orcid_url(value: str | None) -> str | None:
    match = _ORCID_ID_RE.search((value or "").strip())
    if match is None:
        return None
    return f"https://orcid.org/{match.group('id').upper()}"


def _group_to_discovered_paper(
    payload: object,
    *,
    professor_id: str,
    professor_name: str,
    normalized_orcid_url: str,
    fallback_index: int,
) -> DiscoveredPaper | None:
    if not isinstance(payload, dict):
        return None
    work_summaries = payload.get("work-summary")
    if not isinstance(work_summaries, list) or not work_summaries:
        return None
    summary = work_summaries[0]
    if not isinstance(summary, dict):
        return None

    title = _extract_title(summary)
    year = _extract_year(summary)
    if not title or year is None:
        return None

    doi = _extract_doi(summary)
    source_url = _extract_source_url(summary, normalized_orcid_url, doi)
    put_code = str(summary.get("put-code") or "").strip() or str(fallback_index)
    paper_id = doi or f"orcid:{normalized_orcid_url.rsplit('/', 1)[-1]}:{put_code}"

    return DiscoveredPaper(
        paper_id=paper_id,
        title=title,
        year=year,
        publication_date=_extract_publication_date(summary),
        venue=_extract_optional_value(summary.get("journal-title")),
        doi=doi,
        arxiv_id=None,
        abstract=None,
        authors=(professor_name,),
        professor_ids=(professor_id,),
        citation_count=None,
        source_url=source_url,
    )


def _extract_title(summary: dict[str, object]) -> str | None:
    title_wrapper = summary.get("title")
    if not isinstance(title_wrapper, dict):
        return None
    title_value = title_wrapper.get("title")
    if not isinstance(title_value, dict):
        return None
    return _extract_optional_value(title_value)


def _extract_year(summary: dict[str, object]) -> int | None:
    publication_date = summary.get("publication-date")
    if not isinstance(publication_date, dict):
        return None
    year_value = publication_date.get("year")
    if not isinstance(year_value, dict):
        return None
    raw = _extract_optional_value(year_value)
    if raw is None:
        return None
    try:
        parsed = int(raw)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _extract_publication_date(summary: dict[str, object]) -> str | None:
    publication_date = summary.get("publication-date")
    if not isinstance(publication_date, dict):
        return None
    year = _extract_optional_value(publication_date.get("year"))
    month = _extract_optional_value(publication_date.get("month"))
    day = _extract_optional_value(publication_date.get("day"))
    if year is None:
        return None
    components = [year]
    if month is not None:
        components.append(month.zfill(2))
    if day is not None:
        components.append(day.zfill(2))
    return "-".join(components)


def _extract_doi(summary: dict[str, object]) -> str | None:
    external_ids = summary.get("external-ids")
    if not isinstance(external_ids, dict):
        return None
    values = external_ids.get("external-id")
    if not isinstance(values, list):
        return None
    for item in values:
        if not isinstance(item, dict):
            continue
        if _extract_optional_value(item.get("external-id-type")) != "doi":
            continue
        normalized = item.get("external-id-normalized")
        if isinstance(normalized, dict):
            normalized_value = _extract_optional_value(normalized.get("value"))
            if normalized_value:
                return normalized_value.lower()
        raw_value = _extract_optional_value(item.get("external-id-value"))
        if raw_value:
            return raw_value.lower()
    return None


def _extract_source_url(
    summary: dict[str, object],
    normalized_orcid_url: str,
    doi: str | None,
) -> str:
    if doi:
        return f"https://doi.org/{doi}"
    url_value = summary.get("url")
    if isinstance(url_value, dict):
        extracted = _extract_optional_value(url_value.get("value"))
        if extracted:
            return extracted
    return normalized_orcid_url


def _extract_optional_value(value: object) -> str | None:
    if isinstance(value, dict):
        candidate = value.get("value")
        if isinstance(candidate, str):
            stripped = candidate.strip()
            return stripped or None
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None
