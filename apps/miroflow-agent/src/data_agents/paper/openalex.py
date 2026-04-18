from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Callable
import unicodedata

import requests

from src.data_agents.normalization import normalize_person_name
from src.data_agents.professor.institution_names import (
    get_institution_aliases,
    normalize_institution_text,
)

from .author_id_picker import AuthorCandidate
from .models import DiscoveredPaper, ProfessorPaperDiscoveryResult

_AUTHOR_SEARCH_ENDPOINT = "https://api.openalex.org/authors"
_WORKS_ENDPOINT = "https://api.openalex.org/works"
_CACHE_ROOT = (
    Path(__file__).resolve().parents[5] / "logs" / "debug" / "paper_openalex_cache"
)
_MAX_RETRIES = 2
_REQUEST_TIMEOUT = (5, 20)

RequestParams = Mapping[str, str | int]
RequestJson = Callable[[str, RequestParams], dict[str, object]]
_TOKEN_RE = re.compile(r"[0-9a-z\u4e00-\u9fff]+")


def discover_professor_paper_candidates_from_openalex(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    institution_id: str | None = None,
    request_json: RequestJson | None = None,
    max_papers: int = 20,
    author_picker: Callable[..., object] | None = None,
    target_research_directions: list[str] | None = None,
) -> ProfessorPaperDiscoveryResult:
    fetch_json = request_json or _request_json
    author_params: dict[str, str | int] = {
        "search": professor_name,
        "per-page": 10,
        "mailto": "mirothinker-data-agent@example.com",
    }
    normalized_institution_id = _normalize_openalex_institution_id(institution_id)
    author_payloads: list[dict[str, object]] = []
    if normalized_institution_id:
        filtered_params = dict(author_params)
        filtered_params["filter"] = (
            f"last_known_institutions.id:{normalized_institution_id}"
        )
        author_payloads.append(
            fetch_json(
                _AUTHOR_SEARCH_ENDPOINT,
                filtered_params,
            )
        )
    author_payloads.append(
        fetch_json(
            _AUTHOR_SEARCH_ENDPOINT,
            author_params,
        )
    )
    author = None
    school_matched = False
    name_disambiguation_conflict = False
    candidate_count = 0
    for author_payload in author_payloads:
        author, school_matched, name_disambiguation_conflict, candidate_count = (
            _select_exact_name_author(
                professor_name,
                author_payload.get("results", []),
                institution=institution,
                institution_id=normalized_institution_id,
            )
        )
        if author is not None:
            break

    if author_picker is not None and candidate_count >= 2:
        llm_choice = _resolve_with_picker(
            author_picker,
            candidates=[
                candidate
                for payload in author_payloads
                for candidate in payload.get("results", []) or []
                if isinstance(candidate, dict)
            ],
            professor_name=professor_name,
            institution=institution,
            research_directions=target_research_directions,
        )
        if llm_choice is not None:
            author = llm_choice
            school_matched = (
                _institution_id_match_quality(author, normalized_institution_id) > 0
                or _institution_match_quality(author, institution) > 0
            )
            name_disambiguation_conflict = False
        elif llm_choice is None:
            # LLM declined — don't trust the rule-based tiebreaker either.
            author = None
    if author is None:
        return ProfessorPaperDiscoveryResult(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
            author_id=None,
            h_index=None,
            citation_count=None,
            papers=[],
            paper_count=None,
            source="openalex",
            school_matched=False,
            fallback_used=False,
            name_disambiguation_conflict=name_disambiguation_conflict,
            candidate_count=candidate_count,
            query_name=professor_name,
        )

    author_id = str(author.get("id") or "").strip() or None
    h_index = _summary_h_index(author)
    citation_count = _coerce_non_negative_int(author.get("cited_by_count"))
    if not author_id:
        return ProfessorPaperDiscoveryResult(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
            author_id=None,
            h_index=None,
            citation_count=None,
            papers=[],
            paper_count=None,
            source="openalex",
            school_matched=school_matched,
            fallback_used=False,
            name_disambiguation_conflict=name_disambiguation_conflict,
            candidate_count=candidate_count,
            query_name=professor_name,
        )

    works_payload = fetch_json(
        _WORKS_ENDPOINT,
        {
            "filter": f"authorships.author.id:{author_id}",
            "sort": "cited_by_count:desc,publication_year:desc",
            "per-page": max_papers,
            "mailto": "mirothinker-data-agent@example.com",
        },
    )
    work_items = works_payload.get("results", [])
    if not isinstance(work_items, list):
        work_items = []
    papers = [
        paper
        for payload in work_items
        if (
            paper := _to_discovered_paper(
                payload,
                professor_id=professor_id,
            )
        )
        is not None
    ]

    return ProfessorPaperDiscoveryResult(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        author_id=author_id,
        h_index=h_index,
        citation_count=citation_count,
        papers=papers,
        paper_count=_coerce_non_negative_int(author.get("works_count")),
        source="openalex",
        school_matched=school_matched,
        fallback_used=False,
        name_disambiguation_conflict=name_disambiguation_conflict,
        candidate_count=candidate_count,
        query_name=professor_name,
    )


def _request_json(url: str, params: RequestParams) -> dict[str, object]:
    cache_path = _CACHE_ROOT / f"{_cache_key(url, params)}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload

    response = None
    for attempt in range(_MAX_RETRIES):
        response = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        if response.status_code < 500 and response.status_code != 429:
            break
        if attempt + 1 >= _MAX_RETRIES:
            break
        time.sleep(float(min(2**attempt, 4)))
    if response is None:
        raise RuntimeError(f"OpenAlex request did not run: {url}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected OpenAlex payload from {url}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _author_to_candidate(
    payload: dict[str, object], *, index: int
) -> AuthorCandidate | None:
    author_id = str(payload.get("id") or "").strip()
    display_name = str(payload.get("display_name") or "").strip()
    if not author_id or not display_name:
        return None
    alt_names = payload.get("display_name_alternatives")
    alt_list: list[str] = []
    if isinstance(alt_names, list):
        alt_list = [str(n).strip() for n in alt_names if str(n).strip()]
    institutions: list[str] = []
    lki = payload.get("last_known_institutions")
    if isinstance(lki, list):
        for inst in lki:
            if isinstance(inst, dict):
                name = str(inst.get("display_name") or "").strip()
                if name:
                    institutions.append(name)
    topics: list[str] = []
    concepts = payload.get("x_concepts")
    if isinstance(concepts, list):
        for concept in concepts[:8]:
            if isinstance(concept, dict):
                name = str(concept.get("display_name") or "").strip()
                if name:
                    topics.append(name)
    return AuthorCandidate(
        index=index,
        author_id=author_id,
        display_name=display_name,
        display_name_alternatives=alt_list,
        institutions=institutions,
        topics=topics,
        works_count=_coerce_non_negative_int(payload.get("works_count")),
        cited_by_count=_coerce_non_negative_int(payload.get("cited_by_count")),
        h_index=_summary_h_index(payload),
        source="openalex",
    )


def _resolve_with_picker(
    author_picker: Callable[..., object],
    *,
    candidates: list[dict[str, object]],
    professor_name: str,
    institution: str,
    research_directions: list[str] | None,
) -> dict[str, object] | None:
    """Invoke the LLM picker and return the chosen raw candidate, or None."""
    candidate_records: list[AuthorCandidate] = []
    candidate_by_id: dict[str, dict[str, object]] = {}
    for idx, payload in enumerate(candidates):
        rec = _author_to_candidate(payload, index=idx)
        if rec is None:
            continue
        if rec.author_id in candidate_by_id:
            continue
        candidate_records.append(rec)
        candidate_by_id[rec.author_id] = payload
    if not candidate_records:
        return None
    try:
        decision = author_picker(
            target_name=professor_name,
            target_institution=institution,
            target_directions=research_directions,
            candidates=candidate_records,
        )
    except Exception:
        return None
    accepted = getattr(decision, "accepted_author_id", None)
    if not accepted:
        return None
    return candidate_by_id.get(accepted)


def _select_exact_name_author(
    professor_name: str,
    candidates: object,
    institution: str | None = None,
    institution_id: str | None = None,
) -> tuple[dict[str, object] | None, bool, bool, int]:
    if not isinstance(candidates, list):
        return None, False, False, 0

    target_names = _build_exact_name_variants(professor_name)
    if not target_names:
        return None, False, False, 0
    exact_matches: list[
        tuple[dict[str, object], tuple[int, int, int, int, int, str]]
    ] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        name_match = _name_match_quality(item, target_names)
        if name_match <= 0:
            continue
        exact_matches.append(
            (
                item,
                (
                    _institution_id_match_quality(item, institution_id),
                    _institution_match_quality(item, institution),
                    name_match,
                    _summary_h_index(item) or 0,
                    _coerce_non_negative_int(item.get("cited_by_count")) or 0,
                    _coerce_non_negative_int(item.get("works_count")) or 0,
                    str(item.get("id") or ""),
                ),
            )
        )
    if not exact_matches:
        return None, False, False, 0

    selected_author, selected_score = max(exact_matches, key=lambda item: item[1])
    selected_score_without_id = selected_score[:-1]
    top_score_count = sum(
        1 for _, score in exact_matches if score[:-1] == selected_score_without_id
    )
    school_matched = (
        _institution_id_match_quality(selected_author, institution_id) > 0
        or _institution_match_quality(selected_author, institution) > 0
    )
    return selected_author, school_matched, top_score_count > 1, len(exact_matches)


def _institution_id_match_quality(
    author: dict[str, object], institution_id: str | None
) -> int:
    normalized_target = _normalize_openalex_institution_id(institution_id)
    if not normalized_target:
        return 0
    candidate_ids = {
        candidate_id
        for candidate_id in _iter_author_institution_ids(author)
        if candidate_id
    }
    if normalized_target in candidate_ids:
        return 3
    return 0


def _name_match_quality(author: dict[str, object], target_names: set[str]) -> int:
    display_names = _build_exact_name_variants(str(author.get("display_name") or ""))
    if display_names & target_names:
        return 3

    alternatives = author.get("display_name_alternatives")
    if isinstance(alternatives, list):
        for alternative in alternatives:
            if _build_exact_name_variants(str(alternative or "")) & target_names:
                return 2

    for candidate_name in display_names:
        if any(
            target_name
            and (target_name in candidate_name or candidate_name in target_name)
            for target_name in target_names
        ):
            return 1
    return 0


def _build_exact_name_variants(value: str | None) -> set[str]:
    raw = str(value or "").strip()
    variants: set[str] = set()
    normalized = _normalize_match_name(raw)
    if normalized:
        variants.add(normalized)
    if "," in raw:
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if len(parts) == 2:
            reordered = _normalize_match_name(f"{parts[1]} {parts[0]}")
            if reordered:
                variants.add(reordered)
    return variants


def _normalize_match_name(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    folded = unicodedata.normalize("NFKD", raw)
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    normalized = normalize_person_name(stripped).casefold()
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    return normalized


def _institution_match_quality(
    author: dict[str, object], institution: str | None
) -> int:
    aliases = {
        normalize_institution_text(alias)
        for alias in get_institution_aliases(institution)
        if alias
    }
    if not aliases:
        return 0

    candidate_names = {
        normalize_institution_text(name)
        for name in _iter_author_institution_names(author)
        if name
    }
    if not candidate_names:
        return 0
    if aliases & candidate_names:
        return 2

    alias_tokens = {token for alias in aliases for token in _TOKEN_RE.findall(alias)}
    if not alias_tokens:
        return 0
    for candidate in candidate_names:
        if alias_tokens & set(_TOKEN_RE.findall(candidate)):
            return 1
    return 0


def _iter_author_institution_names(author: dict[str, object]) -> list[str]:
    names: list[str] = []
    for field_name in ("last_known_institutions", "affiliations"):
        raw_items = author.get(field_name)
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            institution = (
                item.get("institution") if field_name == "affiliations" else item
            )
            if not isinstance(institution, dict):
                continue
            display_name = str(institution.get("display_name") or "").strip()
            if display_name:
                names.append(display_name)
    return names


def _iter_author_institution_ids(author: dict[str, object]) -> list[str]:
    ids: list[str] = []
    for field_name in ("last_known_institutions", "affiliations"):
        raw_items = author.get(field_name)
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            institution = (
                item.get("institution") if field_name == "affiliations" else item
            )
            if not isinstance(institution, dict):
                continue
            normalized = _normalize_openalex_institution_id(institution.get("id"))
            if normalized:
                ids.append(normalized)
    return ids


def _summary_h_index(author: dict[str, object]) -> int | None:
    stats = author.get("summary_stats")
    if not isinstance(stats, dict):
        return None
    return _coerce_non_negative_int(stats.get("h_index"))


def _normalize_openalex_institution_id(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("https://openalex.org/"):
        raw = raw.rsplit("/", 1)[-1]
    return raw or None


def _to_discovered_paper(
    payload: object,
    *,
    professor_id: str,
) -> DiscoveredPaper | None:
    if not isinstance(payload, dict):
        return None
    paper_id = str(payload.get("id") or "").strip()
    title = str(payload.get("display_name") or "").strip()
    year = _coerce_non_negative_int(payload.get("publication_year"))
    if not paper_id or not title or year is None:
        return None

    primary_location = payload.get("primary_location")
    if not isinstance(primary_location, dict):
        primary_location = {}
    source = primary_location.get("source")
    if not isinstance(source, dict):
        source = {}
    source_url = str(primary_location.get("landing_page_url") or "").strip() or paper_id
    authorships = payload.get("authorships", [])
    if not isinstance(authorships, list):
        authorships = []
    authors = tuple(
        str((authorship.get("author") or {}).get("display_name") or "").strip()
        for authorship in authorships
        if isinstance(authorship, dict)
        and isinstance(authorship.get("author"), dict)
        and str((authorship.get("author") or {}).get("display_name") or "").strip()
    )
    if not authors:
        return None

    return DiscoveredPaper(
        paper_id=paper_id,
        title=title,
        year=year,
        publication_date=_normalize_optional_str(payload.get("publication_date")),
        venue=_normalize_optional_str(source.get("display_name")),
        doi=_normalize_doi(payload.get("doi")),
        arxiv_id=None,
        abstract=_decode_abstract(payload.get("abstract_inverted_index")),
        authors=authors,
        professor_ids=(professor_id,),
        citation_count=_coerce_non_negative_int(payload.get("cited_by_count")),
        source_url=source_url,
    )


def _decode_abstract(value: object) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    positioned_tokens: list[tuple[int, str]] = []
    for token, positions in value.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                positioned_tokens.append((position, token))
    if not positioned_tokens:
        return None
    return " ".join(token for _, token in sorted(positioned_tokens))


def _normalize_doi(value: object) -> str | None:
    item = _normalize_optional_str(value)
    if item and item.lower().startswith("https://doi.org/"):
        return item[16:]
    return item


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _normalize_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    item = value.strip()
    return item or None


def _cache_key(url: str, params: RequestParams) -> str:
    payload = json.dumps(
        {"url": url, "params": params},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
