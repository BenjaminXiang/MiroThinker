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

from src.data_agents.paper.hybrid import (
    discover_professor_paper_candidates_from_hybrid_sources,
)
from src.data_agents.paper.cv_pdf import discover_professor_paper_candidates_from_cv_pdf
from src.data_agents.paper.google_scholar_profile import (
    discover_professor_paper_candidates_from_google_scholar_profile,
)
from src.data_agents.paper.models import DiscoveredPaper, ProfessorPaperDiscoveryResult
from src.data_agents.paper.orcid import discover_professor_paper_candidates_from_orcid
from src.data_agents.paper.title_cleaner import clean_paper_title

from .academic_tools import (
    AcademicAuthorInfo,
    RawPaperRecord,
    collect_papers,
)
from .identity_verifier import ProfessorContext
from .paper_identity_gate import (
    PaperIdentityCandidate,
    batch_verify_paper_identity,
)
from .cross_domain import PaperLink, PaperStagingRecord
from .institution_registry import resolve_openalex_institution_id
from .institution_names import get_primary_english_institution_name
from .name_utils import (
    derive_english_name_candidates_from_url,
    normalize_english_name,
    sanitize_english_person_name,
)
from .translation_spec import LLM_EXTRA_BODY
from .models import OfficialAnchorProfile

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_PAPER_TOKEN_RE = re.compile(r"[A-Za-z]{4,}|[一-鿿]{3,}")
_PAPER_TOKEN_STOPWORDS = frozenset({
    "research", "paper", "papers", "journal", "proceedings", "transactions",
    "student", "students", "education", "development", "university", "college",
    "model", "models", "analysis", "study", "studies", "system", "systems",
    "教师", "教授", "研究", "论文", "学术", "学校", "学院", "大学",
})
_DISCIPLINE_FAMILY_KEYWORDS = {
    "education": {"学生发展", "高等教育", "教师发展", "教育财政", "院校影响力", "education", "educational", "student", "students", "teaching", "teacher", "teachers", "school", "college", "university"},
    "formal_methods": {"model", "checking", "timed", "hybrid", "petri", "bip", "verification", "concurrent"},
    "medicine": {"中医", "临床", "血清", "结肠炎", "medical", "clinical", "hospital", "hospitals", "nursing", "patient", "patients", "infection"},
    "geology": {"矿物", "选矿", "地质", "找矿", "mineral", "geology", "ore"},
    "networking": {"网络", "通信", "ethernet", "latency", "signal", "network"},
}


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
    paper_source: str | None = None
    school_matched: bool = False
    fallback_used: bool = False
    name_disambiguation_conflict: bool = False


async def enrich_from_papers(
    *,
    name: str,
    name_en: str | None,
    institution: str,
    institution_en: str | None,
    official_directions: list[str],
    official_paper_count: int | None = None,
    official_top_papers: list[PaperLink] | None = None,
    official_anchor_profile: OfficialAnchorProfile | dict[str, Any] | None = None,
    publication_evidence_urls: list[str] | None = None,
    scholarly_profile_urls: list[str] | None = None,
    cv_urls: list[str] | None = None,
    professor_id: str,
    homepage_url: str | None = None,
    allow_legacy_fallback: bool = False,
    fetch_html: Any,
    llm_client: Any,
    llm_model: str,
    timeout: float = 30.0,
    identity_gate_enabled: bool = True,   # Round 7.13: default-on after 7.6/7.14 validated
    identity_gate_llm_client: Any | None = None,
    identity_gate_llm_model: str | None = None,
    author_picker: Any | None = None,
) -> PaperEnrichmentResult:
    """Run Stage 2b paper enrichment for one professor."""
    collection_papers: list[RawPaperRecord]
    collection_author_info: AcademicAuthorInfo | None
    disambiguation_confidence: float
    official_top_papers = list(official_top_papers or [])
    anchor_profile = _coerce_official_anchor_profile(official_anchor_profile)
    publication_evidence_urls = list(publication_evidence_urls or [])
    scholarly_profile_urls = list(scholarly_profile_urls or [])
    cv_urls = list(cv_urls or [])

    hybrid_result = _reject_result_if_official_anchor_conflicts(
        _discover_best_hybrid_result(
        name=name,
        name_en=name_en,
        institution=institution,
        institution_en=institution_en,
        professor_id=professor_id,
        homepage_url=homepage_url,
        author_picker=author_picker,
        target_research_directions=official_directions,
    ),
        anchor_profile=anchor_profile,
    )
    orcid_result = _reject_result_if_official_anchor_conflicts(
        _discover_official_linked_orcid_result(
        scholarly_profile_urls=scholarly_profile_urls,
        professor_id=professor_id,
        professor_name=name,
        institution=institution,
    ),
        anchor_profile=anchor_profile,
    )
    scholar_result = _reject_result_if_official_anchor_conflicts(
        _discover_official_linked_scholar_result(
        scholarly_profile_urls=scholarly_profile_urls,
        professor_id=professor_id,
        professor_name=name,
        institution=institution,
    ),
        anchor_profile=anchor_profile,
    )
    cv_result = _reject_result_if_official_anchor_conflicts(
        _discover_official_linked_cv_result(
        cv_urls=cv_urls,
        professor_id=professor_id,
        professor_name=name,
        institution=institution,
    ),
        anchor_profile=anchor_profile,
    )
    selected_result = _select_preferred_official_anchor_result(
        orcid_result=orcid_result,
        scholar_result=scholar_result,
        cv_result=cv_result,
    )
    official_collection_papers = _official_top_papers_to_raw_papers(
        official_top_papers,
        publication_evidence_urls=publication_evidence_urls,
        homepage_url=homepage_url,
    )
    usable_official_collection_papers = _select_usable_official_publication_papers(
        official_collection_papers
    )
    metadata_result = selected_result or hybrid_result
    legacy_used = False

    if usable_official_collection_papers and (selected_result is None or len(usable_official_collection_papers) >= 3):
        collection_papers = usable_official_collection_papers
        collection_author_info = AcademicAuthorInfo(
            h_index=metadata_result.h_index if metadata_result is not None else None,
            citation_count=metadata_result.citation_count if metadata_result is not None else None,
            paper_count=official_paper_count or len(collection_papers) or None,
            source="official_site",
        )
        disambiguation_confidence = 0.99 if publication_evidence_urls else 0.97
    elif selected_result is not None and selected_result.papers:
        source = selected_result.source or _infer_source(selected_result)
        collection_papers = [
            _discovered_to_raw_paper(paper, source=source)
            for paper in selected_result.papers
        ]
        collection_author_info = AcademicAuthorInfo(
            h_index=selected_result.h_index,
            citation_count=selected_result.citation_count,
            paper_count=selected_result.paper_count or len(collection_papers),
            source=source,
        )
        disambiguation_confidence = _anchored_disambiguation_confidence(selected_result)
    elif hybrid_result is not None and hybrid_result.papers:
        selected_result = hybrid_result
        source = hybrid_result.source or _infer_source(hybrid_result)
        collection_papers = [
            _discovered_to_raw_paper(paper, source=source)
            for paper in hybrid_result.papers
        ]
        collection_author_info = AcademicAuthorInfo(
            h_index=hybrid_result.h_index,
            citation_count=hybrid_result.citation_count,
            paper_count=hybrid_result.paper_count or len(collection_papers),
            source=source,
        )
        disambiguation_confidence = 0.95
    elif selected_result is not None and selected_result.author_id:
        collection_papers = []
        collection_author_info = AcademicAuthorInfo(
            h_index=selected_result.h_index,
            citation_count=selected_result.citation_count,
            paper_count=selected_result.paper_count,
            source=selected_result.source or _infer_source(selected_result),
        )
        disambiguation_confidence = _anchored_disambiguation_confidence(selected_result)
    elif hybrid_result is not None and hybrid_result.author_id:
        selected_result = hybrid_result
        collection_papers = []
        collection_author_info = AcademicAuthorInfo(
            h_index=hybrid_result.h_index,
            citation_count=hybrid_result.citation_count,
            paper_count=hybrid_result.paper_count,
            source=hybrid_result.source or _infer_source(hybrid_result),
        )
        disambiguation_confidence = 0.7
    elif allow_legacy_fallback:
        collection = collect_papers(
            name=name,
            name_en=name_en,
            institution=institution,
            institution_en=institution_en or get_primary_english_institution_name(institution),
            existing_directions=official_directions,
            fetch_html=fetch_html,
            timeout=timeout,
        )
        legacy_used = True
        collection_papers = collection.papers
        collection_author_info = collection.author_info
        disambiguation_confidence = collection.disambiguation_confidence
    else:
        collection_papers = usable_official_collection_papers
        collection_author_info = (
            AcademicAuthorInfo(
                h_index=None,
                citation_count=None,
                paper_count=official_paper_count or (len(collection_papers) or None),
                source="official_site",
            )
            if collection_papers or official_paper_count
            else None
        )
        disambiguation_confidence = 0.8 if collection_author_info else 0.0

    school_matched = selected_result.school_matched if selected_result is not None else False
    if collection_author_info and collection_author_info.source == "official_site":
        school_matched = True
    fallback_used = legacy_used or (selected_result.fallback_used if selected_result is not None else False)

    if collection_papers and collection_author_info and collection_author_info.source != "official_site":
        filtered_collection_papers = _filter_collection_papers_by_official_anchor(
            collection_papers,
            anchor_profile,
        )
        if filtered_collection_papers != collection_papers:
            collection_papers = filtered_collection_papers
            collection_author_info = AcademicAuthorInfo(
                h_index=collection_author_info.h_index,
                citation_count=collection_author_info.citation_count,
                paper_count=len(collection_papers) or None,
                source=collection_author_info.source,
            )

    if not collection_papers:
        return PaperEnrichmentResult(
            research_directions=official_directions,
            research_directions_source="official_only",
            h_index=collection_author_info.h_index if collection_author_info else None,
            citation_count=collection_author_info.citation_count if collection_author_info else None,
            paper_count=collection_author_info.paper_count if collection_author_info else None,
            top_papers=[],
            staging_records=[],
            disambiguation_confidence=disambiguation_confidence,
            paper_source=(
                selected_result.source
                if selected_result is not None
                else (collection_author_info.source if collection_author_info else None)
            ),
            school_matched=school_matched,
            fallback_used=fallback_used,
            name_disambiguation_conflict=(
                selected_result.name_disambiguation_conflict if selected_result is not None else False
            ),
        )

    if (
        identity_gate_enabled
        and collection_author_info
        and collection_author_info.source != "official_site"
    ):
        collection_papers = await _apply_identity_gate(
            collection_papers,
            name=name,
            institution=institution,
            directions_hint=official_directions,
            llm_client=identity_gate_llm_client or llm_client,
            llm_model=identity_gate_llm_model or llm_model,
        )

    directions, source = await generate_research_directions(
        papers=collection_papers,
        official_directions=official_directions,
        llm_client=llm_client,
        llm_model=llm_model,
    )

    top_papers = select_top_papers(collection_papers, limit=5)
    staging = build_staging_records(
        collection_papers,
        professor_id=professor_id,
        professor_name=name,
        institution=institution,
    )

    return PaperEnrichmentResult(
        research_directions=directions,
        research_directions_source=source,
        h_index=collection_author_info.h_index if collection_author_info else None,
        citation_count=collection_author_info.citation_count if collection_author_info else None,
        paper_count=collection_author_info.paper_count if collection_author_info else None,
        top_papers=top_papers,
        staging_records=staging,
        disambiguation_confidence=disambiguation_confidence,
        paper_source=collection_author_info.source if collection_author_info else None,
        school_matched=school_matched,
        fallback_used=fallback_used,
        name_disambiguation_conflict=(
            selected_result.name_disambiguation_conflict if selected_result is not None else False
        ),
    )


async def _apply_identity_gate(
    papers: list[RawPaperRecord],
    *,
    name: str,
    institution: str,
    directions_hint: list[str],
    llm_client: Any,
    llm_model: str,
) -> list[RawPaperRecord]:
    """Run the batch identity gate and return only papers the gate accepts.

    If the gate call fails entirely (e.g. no LLM available), fall back to
    the unfiltered list rather than silently dropping all papers.
    """
    if not papers:
        return papers
    context = ProfessorContext(
        name=name,
        institution=institution,
        research_directions=list(directions_hint) if directions_hint else None,
    )
    candidates = [
        PaperIdentityCandidate(
            index=i,
            title=p.title,
            authors=list(p.authors or []),
            year=p.year,
            venue=p.venue,
            abstract=p.abstract,
        )
        for i, p in enumerate(papers)
    ]
    try:
        decisions = await batch_verify_paper_identity(
            professor_context=context,
            candidates=candidates,
            llm_client=llm_client,
            llm_model=llm_model,
        )
    except Exception as exc:  # pragma: no cover - LLM transport faults
        logger.warning(
            "identity gate unavailable, keeping all %d papers: %s", len(papers), exc
        )
        return papers
    if all(d.error is not None for d in decisions):
        logger.warning("identity gate errored for every batch; keeping all papers")
        return papers
    kept = [p for p, d in zip(papers, decisions) if d.accepted]
    logger.info(
        "identity gate kept %d/%d papers for %s",
        len(kept),
        len(papers),
        name,
    )
    return kept


def _select_usable_official_publication_papers(papers: list[RawPaperRecord]) -> list[RawPaperRecord]:
    usable = [paper for paper in papers if _is_usable_official_publication_title(paper.title)]
    return usable


def _is_usable_official_publication_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", (title or "").strip())
    if not normalized:
        return False
    if _looks_like_author_list_entry(normalized):
        return False

    has_year = bool(re.search(r"\b(?:19|20)\d{2}\b", normalized))
    tokens = [token for token in re.split(r"[^A-Za-z0-9一-鿿]+", normalized) if token]
    latin_word_count = sum(1 for token in tokens if re.search(r"[A-Za-z]", token))
    cjk_char_count = sum(1 for char in normalized if "一" <= char <= "鿿")
    last_token = tokens[-1] if tokens else ""

    if not has_year and len(normalized) < 30:
        return False
    if not has_year and re.fullmatch(r"[A-Za-z]{1,2}", last_token):
        return False
    if not has_year and latin_word_count < 5 and cjk_char_count < 10:
        return False
    return True


def _looks_like_author_list_entry(title: str) -> bool:
    segments = [segment.strip() for segment in title.split(",") if segment.strip()]
    if len(segments) < 3:
        return False
    name_like = 0
    for segment in segments:
        cleaned = re.sub(r"[#*]+", "", segment).strip()
        if re.fullmatch(r"[A-Z][a-z]{0,3}(?:\s+[A-Z]{1,3})?", cleaned):
            name_like += 1
            continue
        if re.fullmatch(r"[A-Z][a-z]{0,3}\s+[A-Z][a-z]{0,3}", cleaned):
            name_like += 1
            continue
        if re.fullmatch(r"[A-Z]{1,4}\s*[A-Z]{0,4}", cleaned):
            name_like += 1
            continue
    return name_like >= len(segments) - 1


def _coerce_official_anchor_profile(
    value: OfficialAnchorProfile | dict[str, Any] | None,
) -> OfficialAnchorProfile | None:
    if value is None:
        return None
    if isinstance(value, OfficialAnchorProfile):
        return value
    return OfficialAnchorProfile.model_validate(value)


def _english_name_token_set(value: str | None) -> set[str]:
    normalized = sanitize_english_person_name(value) or normalize_english_name(value)
    if not normalized:
        return set()
    return {token.casefold() for token in normalized.split()}


def _result_name_conflicts(
    result: ProfessorPaperDiscoveryResult,
    anchor_profile: OfficialAnchorProfile,
) -> bool:
    if not anchor_profile.english_name_candidates:
        return False
    anchor_sets = [
        _english_name_token_set(candidate)
        for candidate in anchor_profile.english_name_candidates
        if _english_name_token_set(candidate)
    ]
    if not anchor_sets:
        return False

    candidate_names: list[str] = []
    if result.professor_name:
        candidate_names.append(result.professor_name)
    for paper in result.papers[:5]:
        candidate_names.extend(paper.authors[:3])

    english_candidates = [
        _english_name_token_set(candidate)
        for candidate in candidate_names
        if _english_name_token_set(candidate)
    ]
    if not english_candidates:
        return False

    for candidate in english_candidates:
        for anchor_set in anchor_sets:
            if len(candidate & anchor_set) >= 2:
                return False
    return True


def _tokenize_paper_text(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _PAPER_TOKEN_RE.finditer(text or ""):
        token = match.group(0).strip()
        if not token:
            continue
        lowered = token.casefold()
        if lowered in _PAPER_TOKEN_STOPWORDS or token in _PAPER_TOKEN_STOPWORDS:
            continue
        tokens.add(token)
    return tokens


def _paper_result_tokens(result: ProfessorPaperDiscoveryResult) -> set[str]:
    ranked_papers = sorted(
        result.papers,
        key=lambda paper: ((paper.citation_count or 0), (paper.year or 0)),
        reverse=True,
    )[:15]
    combined = "\n".join(
        " ".join(part for part in (paper.title, paper.venue or "", paper.abstract or "") if part)
        for paper in ranked_papers
    )
    return _tokenize_paper_text(combined)


def _infer_discipline_families(tokens: set[str]) -> set[str]:
    families: set[str] = set()
    lowered_tokens = {token.casefold() for token in tokens}
    for family, keywords in _DISCIPLINE_FAMILY_KEYWORDS.items():
        keyword_lower = {keyword.casefold() for keyword in keywords}
        if lowered_tokens & keyword_lower:
            families.add(family)
    return families


def _result_topic_conflicts(
    result: ProfessorPaperDiscoveryResult,
    anchor_profile: OfficialAnchorProfile,
) -> bool:
    anchor_tokens = set(anchor_profile.topic_tokens)
    if len(anchor_tokens) < 3 or len(result.papers) < 5:
        return False
    candidate_tokens = _paper_result_tokens(result)
    if len(candidate_tokens) < 5:
        return False
    overlap = len(anchor_tokens & candidate_tokens) / max(len(anchor_tokens), 1)
    if overlap >= 0.15:
        return False
    anchor_families = _infer_discipline_families(anchor_tokens)
    candidate_families = _infer_discipline_families(candidate_tokens)
    if anchor_families and candidate_families and anchor_families.isdisjoint(candidate_families):
        return True
    return len(anchor_tokens & candidate_tokens) == 0


def _reject_result_if_official_anchor_conflicts(
    result: ProfessorPaperDiscoveryResult | None,
    *,
    anchor_profile: OfficialAnchorProfile | None,
) -> ProfessorPaperDiscoveryResult | None:
    if result is None or anchor_profile is None:
        return result
    if _result_name_conflicts(result, anchor_profile):
        return None
    if _result_topic_conflicts(result, anchor_profile):
        return None
    return result


def _paper_tokens(paper: RawPaperRecord) -> set[str]:
    parts = [paper.title, paper.venue or "", paper.abstract or "", " ".join(paper.keywords or [])]
    return _tokenize_paper_text(" ".join(part for part in parts if part))


def _paper_matches_official_anchor(
    paper: RawPaperRecord,
    anchor_profile: OfficialAnchorProfile,
) -> bool:
    anchor_tokens = set(anchor_profile.topic_tokens)
    if len(anchor_tokens) < 3 or anchor_profile.sparse_anchor:
        return True
    paper_tokens = _paper_tokens(paper)
    if not paper_tokens:
        return True
    anchor_families = _infer_discipline_families(anchor_tokens)
    paper_families = _infer_discipline_families(paper_tokens)
    if anchor_families and paper_families and anchor_families.isdisjoint(paper_families):
        return False
    if anchor_tokens & paper_tokens:
        return True
    # This filter is intentionally narrow: it only rejects papers with explicit
    # discipline-family conflicts, and otherwise lets ambiguous papers survive.
    return True


def _filter_collection_papers_by_official_anchor(
    papers: list[RawPaperRecord],
    anchor_profile: OfficialAnchorProfile | None,
) -> list[RawPaperRecord]:
    if anchor_profile is None or len(papers) <= 1:
        return papers
    filtered = [paper for paper in papers if _paper_matches_official_anchor(paper, anchor_profile)]
    return filtered or []


def _select_preferred_official_anchor_result(
    *,
    orcid_result: ProfessorPaperDiscoveryResult | None,
    scholar_result: ProfessorPaperDiscoveryResult | None,
    cv_result: ProfessorPaperDiscoveryResult | None,
) -> ProfessorPaperDiscoveryResult | None:
    for result in (orcid_result, scholar_result, cv_result):
        if result is None:
            continue
        if result.papers or result.paper_count or result.h_index or result.citation_count or result.author_id:
            return result
    return None


def _anchored_disambiguation_confidence(result: ProfessorPaperDiscoveryResult) -> float:
    source = (result.source or '').lower()
    if source == 'official_linked_orcid':
        return 0.98
    if source == 'official_linked_google_scholar':
        return 0.97
    if source == 'official_linked_cv':
        return 0.97
    return 0.95


def _discover_official_linked_orcid_result(
    *,
    scholarly_profile_urls: list[str],
    professor_id: str,
    professor_name: str,
    institution: str,
) -> ProfessorPaperDiscoveryResult | None:
    for url in scholarly_profile_urls:
        if "orcid.org" not in url.lower():
            continue
        result = discover_professor_paper_candidates_from_orcid(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
            orcid_url=url,
        )
        if result.papers or result.paper_count:
            return result
    return None


def _discover_official_linked_scholar_result(
    *,
    scholarly_profile_urls: list[str],
    professor_id: str,
    professor_name: str,
    institution: str,
) -> ProfessorPaperDiscoveryResult | None:
    for url in scholarly_profile_urls:
        lowered = url.lower()
        if "scholar.google" not in lowered:
            continue
        result = discover_professor_paper_candidates_from_google_scholar_profile(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
            profile_url=url,
        )
        if result.papers or result.paper_count or result.h_index or result.citation_count:
            return result
    return None


def _discover_official_linked_cv_result(
    *,
    cv_urls: list[str],
    professor_id: str,
    professor_name: str,
    institution: str,
) -> ProfessorPaperDiscoveryResult | None:
    for url in cv_urls:
        if not url.lower().endswith(".pdf"):
            continue
        result = discover_professor_paper_candidates_from_cv_pdf(
            professor_id=professor_id,
            professor_name=professor_name,
            institution=institution,
            cv_url=url,
        )
        if result.papers or result.paper_count or result.h_index or result.citation_count:
            return result
    return None


def _discover_best_hybrid_result(
    *,
    name: str,
    name_en: str | None,
    institution: str,
    institution_en: str | None,
    professor_id: str,
    homepage_url: str | None,
    author_picker: Any | None = None,
    target_research_directions: list[str] | None = None,
) -> ProfessorPaperDiscoveryResult | None:
    institution_query = institution_en or get_primary_english_institution_name(institution) or institution
    institution_id = resolve_openalex_institution_id(institution)

    best_result: ProfessorPaperDiscoveryResult | None = None
    best_score: tuple[int, int, int, int, int, int] | None = None
    for query_name in _build_query_names(name=name, name_en=name_en, homepage_url=homepage_url):
        result = discover_professor_paper_candidates_from_hybrid_sources(
            professor_id=professor_id,
            professor_name=query_name,
            institution=institution_query,
            institution_id=institution_id,
            max_papers=20,
            author_picker=author_picker,
            target_research_directions=target_research_directions,
        )
        if not _has_any_paper_signal(result):
            continue
        if _should_reject_weak_discovery_result(
            query_name=query_name,
            institution_id=institution_id,
            result=result,
        ):
            continue
        score = (
            int(bool(result.papers)),
            len(result.papers),
            _source_quality(result),
            result.paper_count or 0,
            result.h_index or 0,
            result.citation_count or 0,
            _query_name_quality(query_name),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_result = result
    return best_result


def _query_name_quality(query_name: str) -> int:
    normalized = sanitize_english_person_name(query_name)
    if normalized is None:
        return 0
    return 1


def _source_quality(result: ProfessorPaperDiscoveryResult) -> int:
    author_id = (result.author_id or "").lower()
    if "openalex.org" in author_id:
        return 2
    if author_id.startswith("semantic_scholar:"):
        return 1
    if author_id.startswith("crossref:"):
        return 0
    if result.papers:
        return 0
    return -1


def _has_any_paper_signal(result: ProfessorPaperDiscoveryResult) -> bool:
    return bool(
        result.papers
        or result.paper_count
        or result.h_index
        or result.citation_count
    )


def _should_reject_weak_discovery_result(
    *,
    query_name: str,
    institution_id: str | None,
    result: ProfessorPaperDiscoveryResult,
) -> bool:
    if institution_id:
        return not result.school_matched
    if _query_name_quality(query_name) > 0:
        return False
    paper_count = result.paper_count or len(result.papers)
    if paper_count > 1:
        return False
    if (result.h_index or 0) > 1:
        return False
    if (result.citation_count or 0) > 5:
        return False
    return bool(result.papers)


def _build_query_names(
    *,
    name: str,
    name_en: str | None,
    homepage_url: str | None,
) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str | None) -> None:
        english_name = sanitize_english_person_name(candidate)
        item = english_name or (candidate or "").strip()
        if not item:
            return
        key = item.casefold().replace(" ", "")
        if key in seen:
            return
        seen.add(key)
        candidates.append(item)

    add(name_en)
    for candidate in derive_english_name_candidates_from_url(homepage_url):
        add(candidate)
    add(name)
    return candidates


def _discovered_to_raw_paper(
    paper: DiscoveredPaper,
    *,
    source: str,
) -> RawPaperRecord:
    return RawPaperRecord(
        title=clean_paper_title(paper.title),
        authors=list(paper.authors),
        year=paper.year,
        venue=paper.venue,
        abstract=paper.abstract,
        doi=paper.doi,
        citation_count=paper.citation_count,
        keywords=[],
        source_url=paper.source_url,
        source=source,
    )


def _infer_source(result: ProfessorPaperDiscoveryResult) -> str:
    author_id = (result.author_id or "").lower()
    if "openalex.org" in author_id:
        return "openalex"
    if author_id.startswith("crossref:"):
        return "crossref"
    return "semantic_scholar"


def _official_top_papers_to_raw_papers(
    papers: list[PaperLink],
    *,
    publication_evidence_urls: list[str],
    homepage_url: str | None,
) -> list[RawPaperRecord]:
    if not papers:
        return []
    source_url = (
        publication_evidence_urls[0]
        if publication_evidence_urls
        else (homepage_url or "")
    )
    return [
        RawPaperRecord(
            title=clean_paper_title(paper.title),
            authors=[],
            year=paper.year,
            venue=paper.venue,
            abstract=None,
            doi=paper.doi,
            citation_count=paper.citation_count,
            keywords=[],
            source_url=source_url,
            source="official_site",
        )
        for paper in papers
        if clean_paper_title(paper.title)
    ]


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
            extra_body=LLM_EXTRA_BODY,
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
