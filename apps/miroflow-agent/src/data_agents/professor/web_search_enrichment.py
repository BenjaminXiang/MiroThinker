# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Layer 3 — Web search enrichment with identity verification.

Searches the web for additional professor information, crawls result pages,
verifies identity, and extracts new data to merge into the profile.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .direction_cleaner import clean_directions
from .homepage_crawler import (
    _FetchedPage,
    _extract_official_link_targets,
    _extract_official_publication_signals,
    _is_external_academic_profile_host,
)
from .identity_verifier import ProfessorContext, verify_identity
from .models import EducationEntry, EnrichedProfessorProfile, WorkEntry
from .publish_helpers import is_official_url
from .translation_spec import LLM_EXTRA_BODY, TRANSLATION_GUIDELINES

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# Max search result pages to crawl
MAX_PAGES_TO_CRAWL = 8


def _canonicalize_company_name(name: str) -> str:
    normalized = re.sub(r"[（(].*?[）)]", "", (name or "")).strip()
    return normalized or (name or "").strip()


_COMPANY_EXPANSION_STOP_TOKENS = (
    "及",
    "和",
    "与",
    "等",
    "共同",
    "团队",
    "多所",
    "多家",
    "，",
    ",",
    "。",
    "；",
    ";",
    "\n",
    "\r",
)
_COMPANY_EXPANSION_CHAR_RE = re.compile(r"[A-Za-z0-9一-鿿（）()·&\-\s]")


def _expand_company_name_from_text(company_name: str, text: str) -> str:
    normalized = _canonicalize_company_name(company_name)
    if not normalized or not text:
        return normalized

    best = normalized
    for match in re.finditer(re.escape(normalized), text):
        end = match.end()
        while end < len(text) and _COMPANY_EXPANSION_CHAR_RE.fullmatch(text[end]):
            end += 1
        candidate = text[match.start():end].strip()
        for token in _COMPANY_EXPANSION_STOP_TOKENS:
            token_index = candidate.find(token, len(normalized))
            if token_index != -1:
                candidate = candidate[:token_index].strip()
                break
        expanded = _canonicalize_company_name(candidate)
        if len(expanded) > len(best):
            best = expanded
    return best


@dataclass(frozen=True)
class CompanyMention:
    """A company mention found during web search."""

    company_name: str
    role: str
    evidence_url: str
    evidence_text: str = ""


class _WebExtractOutput(BaseModel):
    """Schema for LLM extraction from web page content."""

    awards: list[str] = []
    education_structured: list[EducationEntry] = []
    work_experience: list[WorkEntry] = []
    research_directions: list[str] = []
    academic_positions: list[str] = []
    company_mentions: list[_CompanyMentionModel] = []


class _CompanyMentionModel(BaseModel):
    company_name: str
    role: str = ""
    evidence_url: str = ""


# Re-order: _CompanyMentionModel must be defined before _WebExtractOutput references it
_WebExtractOutput.model_rebuild()


@dataclass
class WebSearchResult:
    """Result of web search enrichment."""

    profile: EnrichedProfessorProfile
    verified_urls: list[str] = field(default_factory=list)
    company_mentions: list[CompanyMention] = field(default_factory=list)
    pages_searched: int = 0
    pages_verified: int = 0
    error: str | None = None


_STEM_COMPANY_TOPIC_KEYWORDS = (
    "具身智能",
    "机器人",
    "触觉",
    "人工智能",
    "机器学习",
    "视觉",
    "语音",
    "芯片",
    "半导体",
    "微电子",
    "传感器",
    "新能源",
    "电池",
    "材料",
    "生物医药",
    "药物",
    "自动驾驶",
    "通信",
    "量子",
    "光电",
    "脑机",
)


def _extract_company_search_topics(profile: EnrichedProfessorProfile) -> list[str]:
    ranked_topics: list[tuple[int, int, str]] = []
    for direction in profile.research_directions or []:
        matches: list[str] = []
        match_priority = len(_STEM_COMPANY_TOPIC_KEYWORDS)
        for index, keyword in enumerate(_STEM_COMPANY_TOPIC_KEYWORDS):
            if keyword in direction and keyword not in matches:
                matches.append(keyword)
                match_priority = min(match_priority, index)
        if not matches:
            continue
        phrase = " ".join(matches[:2]).strip()
        if not phrase:
            continue
        ranked_topics.append((match_priority, -len(matches), phrase))

    topics: list[str] = []
    for _priority, _width, phrase in sorted(ranked_topics):
        if any(phrase == existing or phrase in existing for existing in topics):
            continue
        topics = [existing for existing in topics if existing not in phrase]
        topics.append(phrase)
        if len(topics) >= 1:
            break
    return topics


def _is_useful_company_query_term(term: str) -> bool:
    normalized = term.strip()
    if not normalized:
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", normalized):
        return len(normalized) >= 4
    return len(normalized) >= 2


def _extract_follow_up_company_terms(
    company_name: str,
    evidence_text: str = "",
) -> list[str]:
    terms: list[str] = []

    def add(term: str) -> None:
        normalized = term.strip()
        if _is_useful_company_query_term(normalized) and normalized not in terms:
            terms.append(normalized)

    add(company_name)
    expanded = re.sub(r"[()（）]", " ", company_name)
    for part in re.split(r"[\s/|,，;；]+", expanded):
        add(part)

    for alias in re.findall(r"[（(]([A-Za-z][A-Za-z0-9 .&-]{2,})[）)]", evidence_text or ""):
        add(alias)
        for part in re.split(r"[\s/|,，;；]+", alias):
            add(part)
    return terms


def _build_company_follow_up_queries(
    profile: EnrichedProfessorProfile,
    company_mentions: list[CompanyMention],
) -> list[str]:
    queries: list[str] = []

    def add(query: str) -> None:
        normalized = query.strip()
        if normalized and normalized not in queries:
            queries.append(normalized)

    for mention in company_mentions:
        terms = _extract_follow_up_company_terms(mention.company_name, mention.evidence_text)
        for suffix in ("发起人", "创始人", ""):
            for term in terms:
                query = f"{profile.name} {term} {suffix}".strip() if suffix else f"{profile.name} {term}"
                add(query)
    return queries


def build_search_queries(profile: EnrichedProfessorProfile) -> list[str]:
    """Build search queries for a professor.

    Order matters because the search budget is intentionally capped. Prioritize
    official/homepage and academic-anchor discovery before company intent, then
    use company-oriented queries as later initial/follow-up candidates.
    """
    queries: list[str] = []

    def add(query: str) -> None:
        normalized = query.strip()
        if normalized and normalized not in queries:
            queries.append(normalized)

    add(f"{profile.name} {profile.institution}")
    add(f"{profile.name} {profile.institution} 个人主页")
    add(f"{profile.name} {profile.institution} scholar")

    for topic in _extract_company_search_topics(profile):
        add(f"{profile.name} {topic} 公司")

    add(f"{profile.name} {profile.institution} 公司")

    if profile.research_directions:
        add(f"{profile.name} {profile.institution} {profile.research_directions[0]}")

    return queries


def _build_extract_prompt(
    profile: EnrichedProfessorProfile,
    page_content: str,
    page_url: str,
) -> str:
    """Build LLM prompt for extracting information from a verified page."""
    schema = json.dumps(
        _WebExtractOutput.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )

    return f"""## 任务目标
从以下网页中提取关于教授 {profile.name}（{profile.institution}）的结构化信息。

## 网页内容
URL: {page_url}
{page_content[:4000]}

## 提取要求
1. 只提取与 {profile.name} 直接相关的信息
2. 如果提到该教授与某公司的关系（创始人、顾问、首席科学家等），填入 company_mentions
3. 不能编造信息，页面中没有的字段留空
4. 研究方向只提取学术研究主题

{TRANSLATION_GUIDELINES}

## 输出格式
严格按以下 JSON Schema 输出:
{schema}"""


def _parse_extract_output(text: str) -> _WebExtractOutput:
    """Parse LLM extraction response."""
    match = _JSON_FENCE_RE.search(text)
    content = match.group(1).strip() if match else text.strip()

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start : end + 1]

    data = json.loads(content)
    data["education_structured"] = _filter_education_entries(
        data.get("education_structured", [])
    )
    data["work_experience"] = _filter_work_entries(
        data.get("work_experience", [])
    )
    data["company_mentions"] = _filter_company_mentions(
        data.get("company_mentions", [])
    )
    return _WebExtractOutput.model_validate(data)


def _filter_education_entries(entries: object) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        school = item.get("school") or item.get("institution")
        if not school:
            continue
        normalized = dict(item)
        normalized["school"] = school
        filtered.append(normalized)
    return filtered


def _filter_work_entries(entries: object) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        organization = item.get("organization") or item.get("institution")
        if not organization:
            continue
        normalized = dict(item)
        normalized["organization"] = organization
        filtered.append(normalized)
    return filtered


def _filter_company_mentions(entries: object) -> list[dict[str, str]]:
    if not isinstance(entries, list):
        return []
    filtered: list[dict[str, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        company_name = _canonicalize_company_name((item.get("company_name") or "").strip())
        if not company_name:
            continue
        filtered.append(
            {
                "company_name": company_name,
                "role": str(item.get("role") or "").strip(),
                "evidence_url": str(item.get("evidence_url") or "").strip(),
            }
        )
    return filtered


def _merge_web_extract(
    profile: EnrichedProfessorProfile,
    output: _WebExtractOutput,
) -> EnrichedProfessorProfile:
    """Merge web extraction into profile, not overwriting existing fields."""
    updates: dict[str, Any] = {}

    if output.awards and not profile.awards:
        updates["awards"] = output.awards
    elif output.awards and profile.awards:
        existing = set(profile.awards)
        merged = list(profile.awards)
        for a in output.awards:
            if a not in existing:
                existing.add(a)
                merged.append(a)
        if len(merged) > len(profile.awards):
            updates["awards"] = merged

    if output.education_structured:
        if not profile.education_structured:
            updates["education_structured"] = output.education_structured
        else:
            existing_keys = {
                (
                    e.school.lower() if getattr(e, "school", None) else "",
                    e.degree.lower() if getattr(e, "degree", None) else "",
                )
                for e in profile.education_structured
            }
            merged = list(profile.education_structured)
            for e in output.education_structured:
                key = (
                    e.school.lower() if getattr(e, "school", None) else "",
                    e.degree.lower() if getattr(e, "degree", None) else "",
                )
                if key not in existing_keys:
                    existing_keys.add(key)
                    merged.append(e)
            if len(merged) > len(profile.education_structured):
                updates["education_structured"] = merged

    if output.work_experience:
        if not profile.work_experience:
            updates["work_experience"] = output.work_experience
        else:
            existing_keys = {
                (
                    w.organization.lower() if getattr(w, "organization", None) else "",
                    w.role.lower() if getattr(w, "role", None) else "",
                )
                for w in profile.work_experience
            }
            merged = list(profile.work_experience)
            for w in output.work_experience:
                key = (
                    w.organization.lower() if getattr(w, "organization", None) else "",
                    w.role.lower() if getattr(w, "role", None) else "",
                )
                if key not in existing_keys:
                    existing_keys.add(key)
                    merged.append(w)
            if len(merged) > len(profile.work_experience):
                updates["work_experience"] = merged

    if output.research_directions:
        cleaned = clean_directions(output.research_directions)
        if cleaned and not profile.research_directions:
            updates["research_directions"] = cleaned
        elif cleaned and profile.research_directions:
            existing = set(d.lower() for d in profile.research_directions)
            merged = list(profile.research_directions)
            for d in cleaned:
                if d.lower() not in existing:
                    existing.add(d.lower())
                    merged.append(d)
            if len(merged) > len(profile.research_directions):
                updates["research_directions"] = merged

    if output.academic_positions:
        if not profile.academic_positions:
            updates["academic_positions"] = output.academic_positions
        else:
            existing = {p.lower() for p in profile.academic_positions}
            merged = list(profile.academic_positions)
            for p in output.academic_positions:
                if p.lower() not in existing:
                    existing.add(p.lower())
                    merged.append(p)
            if len(merged) > len(profile.academic_positions):
                updates["academic_positions"] = merged

    if updates:
        return profile.model_copy(update=updates)
    return profile


def _is_known_url(url: str, profile: EnrichedProfessorProfile) -> bool:
    """Check if URL is already known (profile_url, homepage, evidence_urls)."""
    known = {profile.profile_url, profile.homepage or ""}
    known.update(profile.evidence_urls)
    normalized = url.rstrip("/")
    return any(normalized == k.rstrip("/") for k in known if k)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _normalize_match_text(value: str) -> str:
    return "".join((value or "").casefold().split())


def _contains_normalized(haystack: str, needle: str | None) -> bool:
    target = _normalize_match_text(needle or "")
    if not target:
        return False
    return target in _normalize_match_text(haystack)


def _is_high_confidence_identity_search_hit(
    profile: EnrichedProfessorProfile,
    candidate: dict[str, str],
) -> bool:
    combined = " ".join(
        part
        for part in (
            candidate.get("title", ""),
            candidate.get("snippet", ""),
            candidate.get("link", ""),
        )
        if part
    )
    if not _contains_normalized(combined, profile.name):
        return False
    if any(
        _contains_normalized(combined, value)
        for value in (profile.institution, profile.department, profile.email)
        if value
    ):
        return True

    query = candidate.get("_query", "")
    if any(keyword in query for keyword in ("发起人", "创始人")):
        query_company_terms = _extract_query_company_terms(profile, query)
        if (
            query_company_terms
            and any(_contains_normalized(combined, term) for term in query_company_terms)
            and any(keyword in combined for keyword in ("发起人", "创始人", "联合创始"))
        ):
            return True
    return False


def _merge_verified_page_signals(
    profile: EnrichedProfessorProfile,
    verified_pages: list[_FetchedPage],
) -> EnrichedProfessorProfile:
    official_pages = [
        page
        for page in verified_pages
        if is_official_url(page.url)
    ]
    if not official_pages:
        return profile

    publication_signals = _extract_official_publication_signals(official_pages)
    scholarly_profile_urls, cv_urls = _extract_official_link_targets(official_pages)
    if not (
        publication_signals.paper_count is not None
        or publication_signals.top_papers
        or publication_signals.evidence_urls
        or scholarly_profile_urls
        or cv_urls
    ):
        return profile

    existing_titles = {paper.title.casefold() for paper in profile.official_top_papers}
    merged_top_papers = list(profile.official_top_papers)
    for paper in publication_signals.top_papers:
        key = paper.title.casefold()
        if key in existing_titles:
            continue
        existing_titles.add(key)
        merged_top_papers.append(paper)

    merged_official_paper_count = profile.official_paper_count
    if publication_signals.paper_count is not None:
        merged_official_paper_count = max(
            profile.official_paper_count or 0,
            publication_signals.paper_count,
        ) or publication_signals.paper_count

    merged_evidence_urls = _dedupe_preserve_order(
        list(profile.evidence_urls)
        + publication_signals.evidence_urls
        + scholarly_profile_urls
        + cv_urls
    )
    merged_publication_evidence_urls = _dedupe_preserve_order(
        list(profile.publication_evidence_urls)
        + publication_signals.evidence_urls
    )
    merged_scholarly_profile_urls = _dedupe_preserve_order(
        list(profile.scholarly_profile_urls) + scholarly_profile_urls
    )
    merged_cv_urls = _dedupe_preserve_order(list(profile.cv_urls) + cv_urls)

    return profile.model_copy(update={
        "official_paper_count": merged_official_paper_count,
        "official_top_papers": merged_top_papers,
        "publication_evidence_urls": merged_publication_evidence_urls,
        "scholarly_profile_urls": merged_scholarly_profile_urls,
        "cv_urls": merged_cv_urls,
        "evidence_urls": merged_evidence_urls,
    })


async def _collect_search_candidates(
    *,
    profile: EnrichedProfessorProfile,
    search_provider: Any,
    queries: list[str],
    seen_urls: set[str],
    max_queries: int | None = None,
) -> tuple[list[dict[str, str]], int]:
    candidates: list[dict[str, str]] = []
    selected_queries = queries
    if max_queries is not None:
        selected_queries = queries[: max(0, max_queries)]
    for query in selected_queries:
        search_result = await asyncio.to_thread(search_provider.search, query)
        for item in search_result.get("organic", []):
            url = item.get("link", "")
            normalized = url.rstrip("/")
            if not url or _is_known_url(url, profile) or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            candidate = dict(item)
            candidate["_query"] = query
            candidates.append(candidate)
    return (
        sorted(candidates, key=lambda item: _candidate_priority(item, profile), reverse=True),
        len(selected_queries),
    )


def _candidate_preview_text(candidate: dict[str, str]) -> str:
    return "\n".join(
        part for part in (candidate.get("title", ""), candidate.get("snippet", "")) if part
    ).strip()


def _extract_query_company_terms(
    profile: EnrichedProfessorProfile,
    query: str,
) -> list[str]:
    remainder = query.replace(profile.name, " ")
    for token in ("发起人", "创始人", "公司"):
        remainder = remainder.replace(token, " ")
    terms: list[str] = []
    for part in re.split(r"[\s/|,，;；]+", remainder):
        normalized = part.strip()
        if _is_useful_company_query_term(normalized) and normalized not in terms:
            terms.append(normalized)
    return terms


def _reserved_follow_up_budget(max_pages: int) -> int:
    if max_pages <= 1:
        return 0
    if max_pages <= 3:
        return 1
    return min(2, max_pages - 1)


def _reserved_follow_up_query_budget(max_queries: int | None) -> int | None:
    if max_queries is None:
        return None
    if max_queries <= 2:
        return 0
    if max_queries <= 4:
        return 1
    return min(2, max_queries - 2)


def _is_direct_academic_profile_url(url: str) -> bool:
    parsed = urlparse(url)
    return _is_external_academic_profile_host(parsed.hostname)


def _is_direct_cv_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _candidate_priority(
    candidate: dict[str, str],
    profile: EnrichedProfessorProfile | None = None,
) -> tuple[int, int]:
    query = candidate.get("_query", "")
    url = candidate.get("link", "")
    preview = _candidate_preview_text(candidate)
    score = 0
    if any(keyword in query for keyword in ("发起人", "创始人")):
        score += 80
    elif "公司" in query:
        score += 45
    elif "创业" in query:
        score += 15

    if profile is not None and profile.name and profile.name in preview:
        score += 20
    if any(keyword in preview for keyword in ("联合", "创办", "创始", "发起", "公司", "企业")):
        score += 20
    if not is_official_url(url):
        score += 5
    else:
        score -= 5
    return score, -len(url)


async def search_and_enrich(
    *,
    profile: EnrichedProfessorProfile,
    search_provider: Any,
    fetch_html_fn: Callable,
    llm_client: Any,
    llm_model: str,
    max_pages: int = MAX_PAGES_TO_CRAWL,
    max_search_queries: int | None = 4,
) -> WebSearchResult:
    """Search the web for professor info, verify identity, extract and merge."""
    result = WebSearchResult(profile=profile)
    seen_urls: set[str] = set()

    remaining_search_queries = None
    initial_query_budget = None
    if max_search_queries is not None:
        remaining_search_queries = max(0, max_search_queries)
        reserved_follow_up_queries = _reserved_follow_up_query_budget(remaining_search_queries)
        if reserved_follow_up_queries is None:
            initial_query_budget = None
        else:
            initial_query_budget = max(0, remaining_search_queries - reserved_follow_up_queries)

    try:
        unique_candidates, queries_used = await _collect_search_candidates(
            profile=profile,
            search_provider=search_provider,
            queries=build_search_queries(profile),
            seen_urls=seen_urls,
            max_queries=initial_query_budget,
        )
        if remaining_search_queries is not None:
            remaining_search_queries = max(0, remaining_search_queries - queries_used)
    except Exception as e:
        logger.warning("Web search failed for %s: %s", profile.name, e)
        result.error = str(e)
        return result

    if not unique_candidates:
        return result

    ctx = ProfessorContext(
        name=profile.name,
        institution=profile.institution,
        department=profile.department,
        email=profile.email,
        research_directions=profile.research_directions,
    )

    all_company_mentions: list[CompanyMention] = []
    seen_company_mentions: set[tuple[str, str, str]] = set()
    enriched_profile = profile
    verified_pages: list[_FetchedPage] = []

    async def process_candidates(
        candidates: list[dict[str, str]],
        *,
        page_budget: int | None = None,
    ) -> list[dict[str, str]]:
        nonlocal enriched_profile
        pages_before = result.pages_searched
        for index, candidate in enumerate(candidates):
            if result.pages_searched >= max_pages:
                return candidates[index:]
            if (
                page_budget is not None
                and (result.pages_searched - pages_before) >= page_budget
            ):
                return candidates[index:]

            url = candidate.get("link", "")
            result.pages_searched += 1
            preview_text = _candidate_preview_text(candidate)
            html = ""
            blocked_by_anti_scraping = False

            try:
                fetch_result = await asyncio.to_thread(fetch_html_fn, url, 20.0)
                html = fetch_result.html if hasattr(fetch_result, "html") else (fetch_result or "")
                blocked_by_anti_scraping = bool(
                    getattr(fetch_result, "blocked_by_anti_scraping", False)
                )
            except Exception as e:
                logger.debug("Failed to fetch %s: %s", url, e)

            page_content = html
            if blocked_by_anti_scraping or not page_content:
                page_content = preview_text or html
            if not page_content:
                continue

            verification = await verify_identity(
                professor_context=ctx,
                page_url=url,
                page_content=page_content[:3000],
                llm_client=llm_client,
                llm_model=llm_model,
            )
            if not verification.is_same_person:
                continue

            result.pages_verified += 1
            result.verified_urls.append(url)
            if _is_direct_academic_profile_url(url):
                enriched_profile = enriched_profile.model_copy(update={
                    "scholarly_profile_urls": _dedupe_preserve_order(
                        list(enriched_profile.scholarly_profile_urls) + [url]
                    ),
                    "evidence_urls": _dedupe_preserve_order(
                        list(enriched_profile.evidence_urls) + [url]
                    ),
                })
            elif _is_direct_cv_url(url):
                enriched_profile = enriched_profile.model_copy(update={
                    "cv_urls": _dedupe_preserve_order(list(enriched_profile.cv_urls) + [url]),
                    "evidence_urls": _dedupe_preserve_order(
                        list(enriched_profile.evidence_urls) + [url]
                    ),
                })
            if is_official_url(url) and html and not blocked_by_anti_scraping:
                verified_pages.append(_FetchedPage(url=url, html=html, publication_candidate=False))

            extraction_text = page_content
            if preview_text and html and preview_text not in html:
                extraction_text = f"{preview_text}\n\n{html}"
            try:
                prompt = _build_extract_prompt(enriched_profile, extraction_text, url)
                response = llm_client.chat.completions.create(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": "你是一个教授信息采集助手。请严格按JSON格式输出。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                    extra_body=LLM_EXTRA_BODY,
                )
                text = response.choices[0].message.content
                extract_output = _parse_extract_output(text)
                enriched_profile = _merge_web_extract(enriched_profile, extract_output)

                for mention in extract_output.company_mentions:
                    resolved_company_name = _expand_company_name_from_text(
                        mention.company_name,
                        extraction_text,
                    )
                    evidence_url = mention.evidence_url or url
                    key = (resolved_company_name, mention.role, evidence_url)
                    if key in seen_company_mentions:
                        continue
                    seen_company_mentions.add(key)
                    all_company_mentions.append(CompanyMention(
                        company_name=resolved_company_name,
                        role=mention.role,
                        evidence_url=evidence_url,
                        evidence_text=extraction_text[:2000],
                    ))
            except (ValidationError, json.JSONDecodeError) as e:
                logger.warning("Web extraction failed for %s: %s", url, e)
            except Exception:
                logger.exception("Unexpected web extraction failure for %s", url)
        return []

    reserved_follow_up_budget = _reserved_follow_up_budget(max_pages)
    initial_budget = max_pages - reserved_follow_up_budget
    remaining_initial_candidates = await process_candidates(
        unique_candidates,
        page_budget=initial_budget,
    )

    if (
        all_company_mentions
        and result.pages_searched < max_pages
        and (remaining_search_queries is None or remaining_search_queries > 0)
    ):
        try:
            follow_up_candidates, queries_used = await _collect_search_candidates(
                profile=enriched_profile,
                search_provider=search_provider,
                queries=_build_company_follow_up_queries(enriched_profile, all_company_mentions),
                seen_urls=seen_urls,
                max_queries=remaining_search_queries,
            )
            if remaining_search_queries is not None:
                remaining_search_queries = max(0, remaining_search_queries - queries_used)
        except Exception as e:
            logger.warning("Company follow-up search failed for %s: %s", profile.name, e)
        else:
            await process_candidates(
                follow_up_candidates,
                page_budget=max_pages - result.pages_searched,
            )

    if remaining_initial_candidates and result.pages_searched < max_pages:
        await process_candidates(
            remaining_initial_candidates,
            page_budget=max_pages - result.pages_searched,
        )

    enriched_profile = _merge_verified_page_signals(enriched_profile, verified_pages)
    result.profile = enriched_profile
    result.company_mentions = all_company_mentions
    return result
