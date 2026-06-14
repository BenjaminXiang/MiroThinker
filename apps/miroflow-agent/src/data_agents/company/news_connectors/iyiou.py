from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse

import requests

from ...normalization import normalize_company_name, normalize_company_name_v2
from ..team_parser import parse_team_raw
from .base import NewsConnector, NewsRecord

IYIOU_SITE_FILTER = "data.iyiou.com"
IYIOU_ACCEPTED_PATH_PREFIXES = (
    "/company/details/",
    "/intelligence/details/",
    "/news/",
)
PITCHHUB_SITE_FILTER = "pitchhub.36kr.com"
PITCHHUB_ACCEPTED_PATH_PREFIXES = (
    "/project/",
)
_DEFAULT_MAX_QUERY_TERMS = 8
_LLM_MAX_TOKENS = 400
_LLM_TEMPERATURE = 0
_ALIAS_RE = re.compile(
    r"(?:简称|品牌名|品牌|项目名)"
    r"\s*(?:为|是|叫|[:：])?\s*[\"'“”]?"
    r"([A-Za-z][A-Za-z0-9._-]{1,40}|[\u4e00-\u9fffA-Za-z0-9]{2,18})"
)
_BAD_ALIAS_PREFIXES = (
    "的",
    "和",
    "及",
    "为",
    "以",
    "由",
    "对",
    "提供",
    "打造",
    "通过",
)
_BAD_ALIAS_TERMS = {
    "开发",
    "研发",
    "运营",
    "机构",
    "服务",
    "产品",
    "提供",
    "方案",
    "技术",
    "平台",
}
_FOUNDER_ROLE_MARKERS = (
    "创始",
    "创办",
    "CEO",
    "首席执行",
    "董事长",
    "总经理",
)
_KEYWORD_CANDIDATES = (
    "具身智能",
    "工业自动化",
    "智能制造",
    "机器人",
    "人工智能",
    "计算机视觉",
    "医疗影像",
    "医疗器械",
    "生物医药",
    "激光雷达",
    "自动驾驶",
    "半导体",
    "芯片",
    "大模型",
    "AIGC",
    "新材料",
    "新能源",
    "低空经济",
    "传感器",
)


@dataclass(frozen=True, slots=True)
class YiouFetchResult:
    records: list[NewsRecord]
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class YiouSearchHints:
    identity_aliases: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    founder_names: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    source: str = "deterministic"
    error: str | None = None


@dataclass(frozen=True, slots=True)
class YiouSearchContext:
    company_name: str
    normalized_name: str | None = None
    description: str | None = None
    team_raw: str | None = None
    project_name: str | None = None
    identity_aliases: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    founder_names: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    max_query_terms: int = _DEFAULT_MAX_QUERY_TERMS

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "identity_aliases", _clean_terms(self.identity_aliases)
        )
        object.__setattr__(self, "aliases", _clean_terms(self.aliases))
        object.__setattr__(self, "founder_names", _clean_terms(self.founder_names))
        object.__setattr__(self, "keywords", _clean_terms(self.keywords))


class YiouNewsConnector:
    """Named adapter for data.iyiou.com company enrichment records."""

    adapter_name = "iyiou"
    site_filter = IYIOU_SITE_FILTER
    accepted_path_prefixes = IYIOU_ACCEPTED_PATH_PREFIXES

    def __init__(
        self,
        delegate: NewsConnector,
        *,
        adapter_name: str | None = None,
        site_filter: str | None = None,
        accepted_path_prefixes: tuple[str, ...] | None = None,
    ) -> None:
        self.delegate = delegate
        self.adapter_name = adapter_name or self.adapter_name
        self.site_filter = site_filter or self.site_filter
        self.accepted_path_prefixes = (
            accepted_path_prefixes or self.accepted_path_prefixes
        )

    def fetch(self, company_canonical_name: str, since: date) -> list[NewsRecord]:
        return self.fetch_with_diagnostics(company_canonical_name, since).records

    def fetch_with_diagnostics(
        self, company_canonical_name: str, since: date
    ) -> YiouFetchResult:
        return self.fetch_with_context(
            YiouSearchContext(company_name=company_canonical_name),
            since,
        )

    def fetch_with_context(
        self, context: YiouSearchContext, since: date
    ) -> YiouFetchResult:
        query_terms = _build_yiou_query_terms(context)
        match_terms = _build_yiou_match_terms(context, query_terms)
        founder_terms = _build_founder_terms(context)
        keyword_terms = _build_keyword_terms(context)
        raw_records: list[NewsRecord] = []
        records_by_query: dict[str, int] = {}
        for query_term in query_terms:
            query_records = self.delegate.fetch(query_term, since)
            records_by_query[query_term] = len(query_records)
            raw_records.extend(query_records)
        raw_records = _dedupe_records_by_source_url(raw_records)

        accepted: list[NewsRecord] = []
        seen_urls: set[str] = set()
        rejected_offsite = 0
        rejected_irrelevant_path = 0
        rejected_name_mismatch = 0
        for record in raw_records:
            source_domain = _source_domain(record.source_url)
            if not _is_site_domain(source_domain, self.site_filter):
                rejected_offsite += 1
                continue
            if not _is_enrichment_path(record.source_url, self.accepted_path_prefixes):
                rejected_irrelevant_path += 1
                continue
            if not _record_mentions_company(record, match_terms):
                rejected_name_mismatch += 1
                continue
            if record.source_url in seen_urls:
                continue
            seen_urls.add(record.source_url)
            accepted.append(
                NewsRecord(
                    company_id=context.company_name,
                    source_url=record.source_url,
                    title=record.title,
                    summary=record.summary,
                    published_at=record.published_at,
                    raw_text=record.raw_text,
                    source_adapter=self.adapter_name,
                    extraction_diagnostics={
                        "adapter": self.adapter_name,
                        "status": "accepted",
                        "source_domain": source_domain,
                    },
                )
            )
        return YiouFetchResult(
            records=accepted,
            diagnostics={
                "adapter": self.adapter_name,
                "site_filter": self.site_filter,
                "items_seen": len(raw_records),
                "items_accepted": len(accepted),
                "items_rejected_offsite": rejected_offsite,
                "items_rejected_irrelevant_path": rejected_irrelevant_path,
                "items_rejected_name_mismatch": rejected_name_mismatch,
                "query_terms": query_terms,
                "aliases": _build_alias_terms(context),
                "founder_terms": founder_terms,
                "keyword_terms": keyword_terms,
                "records_by_query": records_by_query,
            },
        )


class PitchHubNewsConnector(YiouNewsConnector):
    """Named adapter for 36Kr PitchHub company enrichment records."""

    adapter_name = "pitchhub_36kr"
    site_filter = PITCHHUB_SITE_FILTER
    accepted_path_prefixes = PITCHHUB_ACCEPTED_PATH_PREFIXES

    def __init__(
        self,
        delegate: NewsConnector,
        *,
        reader_fallback_prefix: str | None = None,
        article_max_chars: int = 4000,
        article_timeout_seconds: float = 20.0,
        session: Any | None = None,
    ) -> None:
        super().__init__(delegate)
        self.reader_fallback_prefix = reader_fallback_prefix
        self.article_max_chars = article_max_chars
        self.article_timeout_seconds = article_timeout_seconds
        self.session = session or requests.Session()

    def fetch_with_context(
        self, context: YiouSearchContext, since: date
    ) -> YiouFetchResult:
        result = super().fetch_with_context(context, since)
        enriched_records: list[NewsRecord] = []
        detail_fetch_success = 0
        detail_identity_rejected = 0
        match_terms = _build_yiou_match_terms(
            context,
            _build_yiou_query_terms(context),
        )
        for record in result.records:
            detail_text = self._fetch_detail_text(record.source_url)
            if detail_text:
                if not _pitchhub_detail_primary_entity_matches(
                    detail_text,
                    match_terms,
                ):
                    detail_identity_rejected += 1
                    continue
                detail_fetch_success += 1
                enriched_records.append(
                    NewsRecord(
                        company_id=record.company_id,
                        source_url=record.source_url,
                        title=record.title,
                        summary=detail_text,
                        published_at=record.published_at,
                        raw_text=detail_text,
                        source_adapter=record.source_adapter,
                        extraction_diagnostics={
                            **record.extraction_diagnostics,
                            "detail_fetch_status": "reader_fallback_success",
                        },
                    )
                )
            else:
                enriched_records.append(record)

        diagnostics = dict(result.diagnostics)
        diagnostics["detail_fetch_attempts"] = len(result.records)
        diagnostics["detail_fetch_success"] = detail_fetch_success
        diagnostics["detail_identity_rejected"] = detail_identity_rejected
        return YiouFetchResult(records=enriched_records, diagnostics=diagnostics)

    def _fetch_detail_text(self, url: str) -> str | None:
        if not self.reader_fallback_prefix:
            return None
        try:
            response = self.session.get(
                f"{self.reader_fallback_prefix}{url}",
                timeout=self.article_timeout_seconds,
            )
            response.raise_for_status()
        except Exception:
            return None
        text = response.text.strip()
        if len(text) > self.article_max_chars:
            return text[: self.article_max_chars].rstrip()
        return text or None


def _pitchhub_detail_primary_entity_matches(
    detail_text: str,
    match_terms: list[str],
) -> bool:
    entity_names = _extract_pitchhub_primary_entity_names(detail_text)
    if not entity_names:
        return True
    normalized_terms = [term for term in match_terms if term]
    if not normalized_terms:
        return True
    for entity_name in entity_names:
        normalized_entity = _normalize_match_text(entity_name)
        if not normalized_entity:
            continue
        if any(
            normalized_entity in term or term in normalized_entity
            for term in normalized_terms
        ):
            return True
    return False


def _extract_pitchhub_primary_entity_names(detail_text: str) -> list[str]:
    names: list[str] = []
    for raw_line in detail_text.splitlines()[:80]:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Title:"):
            _append_pitchhub_entity_name(names, line.removeprefix("Title:"))
            continue
        heading = re.match(r"^#{1,4}\s+(.+)$", line)
        if heading:
            _append_pitchhub_entity_name(names, heading.group(1))
        if len(names) >= 4:
            break
    return names


def _append_pitchhub_entity_name(names: list[str], value: str) -> None:
    name = value.strip()
    for separator in ("|", "｜", "- 创投平台", "-36氪"):
        if separator in name:
            name = name.split(separator, 1)[0].strip()
    name = name.strip("# ").strip()
    if not name:
        return
    if name in {
        "Markdown Content",
        "公司/项目名/投资机构/赛道",
        "项目简介",
        "融资历史",
        "核心成员",
        "投资机构",
    }:
        return
    if name.startswith("Image "):
        return
    _append_unique(names, name)


def _source_domain(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc and "://" not in url:
        parsed = urlparse(f"https://{url}")
    host = (parsed.netloc or parsed.path.split("/", 1)[0]).lower()
    host = host.split("@")[-1].split(":", 1)[0]
    return host.removeprefix("www.")


def _is_site_domain(domain: str, site_filter: str) -> bool:
    return domain == site_filter or domain.endswith(f".{site_filter}")


def _is_enrichment_path(url: str, accepted_path_prefixes: tuple[str, ...]) -> bool:
    parsed = urlparse(url)
    path = parsed.path or "/"
    return any(path.startswith(prefix) for prefix in accepted_path_prefixes)


def extract_yiou_search_hints_with_llm(
    *,
    company_name: str,
    description: str | None,
    team_raw: str | None,
    llm_client: Any,
    llm_model: str,
    project_name: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> YiouSearchHints:
    """Ask an LLM for Yiou search hints.

    The returned hints only broaden search queries. Result acceptance still
    requires deterministic company-name or alias confirmation.
    """
    prompt = "\n".join(
        [
            "Extract public web-search hints for finding this company on data.iyiou.com.",
            "Return strict JSON with keys identity_aliases, aliases, founder_names, keywords.",
            "Rules:",
            "- identity_aliases: only company short names, legal-name abbreviations, brand or project names that identify this company; no product, founder, industry, financing, or recruiting terms.",
            "- aliases: broader site-search aliases, brands, project names, and distinctive product names; no generic industry words.",
            "- founder_names: founder, co-founder, CEO, chairman, or general manager names from team text.",
            "- keywords: 1-4 distinctive industry or product terms from the description.",
            "- Use only the provided text; do not invent.",
            "",
            f"Company: {company_name}",
            f"Project name: {project_name or ''}",
            "Description:",
            (description or "")[:1200],
            "Team:",
            (team_raw or "")[:1200],
        ]
    )
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You extract concise company search hints and output JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=_LLM_TEMPERATURE,
            max_tokens=_LLM_MAX_TOKENS,
            extra_body=extra_body or {},
        )
        raw_text = (response.choices[0].message.content or "").strip()
        payload = _extract_json_object(raw_text)
    except Exception as exc:  # noqa: BLE001
        return YiouSearchHints(source="llm_failed", error=str(exc))

    if not isinstance(payload, dict):
        return YiouSearchHints(source="llm_failed", error="json_not_object")

    return YiouSearchHints(
        identity_aliases=_clean_terms(payload.get("identity_aliases") or ()),
        aliases=_clean_terms(payload.get("aliases") or ()),
        founder_names=_clean_terms(payload.get("founder_names") or ()),
        keywords=_clean_terms(payload.get("keywords") or ()),
        source="llm",
    )


def _build_yiou_query_terms(context: YiouSearchContext) -> list[str]:
    terms: list[str] = []
    identity_terms = _build_identity_terms(context)
    alias_terms = _build_alias_terms(context)
    founder_terms = _build_founder_terms(context)
    keyword_terms = _build_keyword_terms(context)

    for candidate in (*identity_terms, *alias_terms):
        _append_unique(terms, candidate)

    for alias in alias_terms[:3]:
        for founder in founder_terms[:2]:
            _append_unique(terms, f"{alias} {founder}")
        for keyword in keyword_terms[:2]:
            _append_unique(terms, f"{alias} {keyword}")
        if len(terms) >= context.max_query_terms:
            break

    return terms[: max(1, context.max_query_terms)]


def _build_identity_terms(context: YiouSearchContext) -> list[str]:
    terms: list[str] = []
    for candidate in (
        context.company_name,
        context.normalized_name,
        normalize_company_name(context.company_name),
    ):
        _append_unique(terms, candidate)
    return terms


def _build_alias_terms(context: YiouSearchContext) -> list[str]:
    terms: list[str] = []
    deterministic = _build_deterministic_hints(context)
    for candidate in (
        context.project_name,
        *context.identity_aliases,
        *context.aliases,
        *deterministic.aliases,
    ):
        _append_unique(terms, candidate)
    return terms


def _build_founder_terms(context: YiouSearchContext) -> list[str]:
    terms: list[str] = []
    deterministic = _build_deterministic_hints(context)
    for candidate in (*context.founder_names, *deterministic.founder_names):
        _append_unique(terms, candidate)
    return terms


def _build_keyword_terms(context: YiouSearchContext) -> list[str]:
    terms: list[str] = []
    deterministic = _build_deterministic_hints(context)
    for candidate in (*context.keywords, *deterministic.keywords):
        _append_unique(terms, candidate)
    return terms


def _build_deterministic_hints(context: YiouSearchContext) -> YiouSearchHints:
    aliases = _extract_aliases_from_description(context.description)
    founders = _extract_founders_from_team(context.team_raw)
    keywords = _extract_keywords_from_description(context.description)
    return YiouSearchHints(
        aliases=aliases,
        founder_names=founders,
        keywords=keywords,
        source="deterministic",
    )


def _build_yiou_match_terms(
    context: YiouSearchContext, _query_terms: list[str]
) -> list[str]:
    terms: list[str] = []
    deterministic = _build_deterministic_hints(context)
    for candidate in (
        context.company_name,
        context.normalized_name,
        normalize_company_name(context.company_name),
        normalize_company_name_v2(context.company_name),
        context.project_name,
        *context.identity_aliases,
        *deterministic.aliases,
    ):
        _append_match_term(terms, candidate)
    return terms


def _append_match_term(terms: list[str], candidate: str | None) -> None:
    normalized = _normalize_match_text(candidate)
    if len(normalized) >= 2 and normalized not in terms:
        terms.append(normalized)


def _record_mentions_company(record: NewsRecord, match_terms: list[str]) -> bool:
    if not match_terms:
        return True
    haystack = _normalize_match_text(
        " ".join(
            value
            for value in (record.title, record.summary, record.raw_text)
            if value
        )
    )
    return any(term in haystack for term in match_terms)


def _dedupe_records_by_source_url(records: list[NewsRecord]) -> list[NewsRecord]:
    seen: set[str] = set()
    deduped: list[NewsRecord] = []
    for record in records:
        url = record.source_url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(record)
    return deduped


def _normalize_match_text(value: str | None) -> str:
    return normalize_company_name_v2(value or "")


def _extract_aliases_from_description(description: str | None) -> tuple[str, ...]:
    aliases: list[str] = []
    for match in _ALIAS_RE.finditer(description or ""):
        candidate = match.group(1)
        if _looks_like_alias(candidate):
            _append_unique(aliases, candidate)
    return tuple(aliases[:4])


def _extract_founders_from_team(team_raw: str | None) -> tuple[str, ...]:
    founders: list[str] = []
    for member in parse_team_raw(team_raw):
        role_intro = " ".join(
            value for value in (member.raw_role, member.raw_intro) if value
        )
        if any(marker in role_intro for marker in _FOUNDER_ROLE_MARKERS):
            _append_unique(founders, member.raw_name)
    return tuple(founders[:4])


def _extract_keywords_from_description(description: str | None) -> tuple[str, ...]:
    text = description or ""
    keywords: list[str] = []
    for keyword in _KEYWORD_CANDIDATES:
        if keyword in text:
            _append_unique(keywords, keyword)
    return tuple(keywords[:4])


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _clean_terms(values: Any) -> tuple[str, ...]:
    terms: list[str] = []
    if isinstance(values, str):
        iterable: list[Any] = [values]
    elif isinstance(values, tuple | list | set):
        iterable = list(values)
    else:
        iterable = []
    for value in iterable:
        _append_unique(terms, value)
    return tuple(terms)


def _append_unique(terms: list[str], value: Any) -> None:
    cleaned = _clean_term(value)
    if cleaned and cleaned not in terms:
        terms.append(cleaned)


def _clean_term(value: Any) -> str:
    text = str(value or "").strip().strip("，,。.;；:：\"'“”‘’")
    return text if len(text) >= 2 else ""


def _looks_like_alias(value: str) -> bool:
    cleaned = _clean_term(value)
    if not cleaned:
        return False
    if cleaned.startswith(_BAD_ALIAS_PREFIXES):
        return False
    if cleaned in _BAD_ALIAS_TERMS:
        return False
    if len(cleaned) > 18 and not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{1,40}", cleaned):
        return False
    return True
