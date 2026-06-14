from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal


JudgmentStatus = Literal["accepted", "rejected", "needs_review"]
SnippetSufficiency = Literal["sufficient", "insufficient", "irrelevant"]


@dataclass(frozen=True, slots=True)
class GenericSearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True, slots=True)
class SourceJudgment:
    status: JudgmentStatus
    reason: str
    evidence_span: str
    snippet_sufficiency: SnippetSufficiency
    confirms_identity: bool
    confirms_fact_attribution: bool
    should_fetch: bool = False


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    tool: Literal["judge_source", "fetch_webpage"]
    url: str
    status: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptedSourceMaterial:
    source_id: str
    source_tier: Literal["generic_web"]
    url: str
    title: str
    captured_text: str
    captured_at: datetime
    trust_reason: str
    evidence_span: str


@dataclass(frozen=True, slots=True)
class RejectedSourceResult:
    url: str
    title: str
    reason: str
    evidence_span: str | None = None


@dataclass(frozen=True, slots=True)
class GenericSourceWorkflowResult:
    accepted_sources: list[AcceptedSourceMaterial] = field(default_factory=list)
    rejected_results: list[RejectedSourceResult] = field(default_factory=list)
    steps: list[WorkflowStep] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)


JudgeSource = Callable[..., SourceJudgment]
FetchPage = Callable[[str], str]


def run_generic_source_workflow(
    *,
    company_name: str,
    trusted_identity_terms: tuple[str, ...] | list[str] | None = None,
    search_results: list[GenericSearchResult],
    judge_source: JudgeSource,
    fetch_page: FetchPage,
    max_results: int = 10,
    max_fetches: int = 3,
    max_body_chars: int = 8000,
) -> GenericSourceWorkflowResult:
    """Run a bounded, inspectable generic-web source judgment loop."""
    accepted: list[AcceptedSourceMaterial] = []
    rejected: list[RejectedSourceResult] = []
    steps: list[WorkflowStep] = []
    fetches = 0
    identity_terms = _trusted_identity_terms(company_name, trusted_identity_terms)

    for item in search_results[: max(0, max_results)]:
        if _looks_like_job_intent(item):
            rejected.append(
                RejectedSourceResult(
                    url=item.url,
                    title=item.title,
                    reason="job_intent_excluded",
                    evidence_span=item.snippet,
                )
            )
            continue

        snippet_judgment = judge_source(
            company_name=company_name,
            identity_terms=identity_terms,
            title=item.title,
            url=item.url,
            snippet=item.snippet,
            page_text=None,
        )
        steps.append(
            WorkflowStep(
                tool="judge_source",
                url=item.url,
                status=snippet_judgment.status,
                reason=snippet_judgment.reason,
            )
        )

        if snippet_judgment.status == "rejected" or not snippet_judgment.should_fetch:
            _apply_final_judgment(
                item=item,
                judgment=snippet_judgment,
                page_text=item.snippet,
                identity_terms=identity_terms,
                accepted=accepted,
                rejected=rejected,
            )
            continue

        if fetches >= max_fetches:
            rejected.append(
                RejectedSourceResult(
                    url=item.url,
                    title=item.title,
                    reason="fetch_limit_reached",
                    evidence_span=snippet_judgment.evidence_span,
                )
            )
            continue

        fetches += 1
        page_text = fetch_page(item.url)[:max_body_chars]
        steps.append(
            WorkflowStep(
                tool="fetch_webpage",
                url=item.url,
                status="fetched" if page_text else "empty",
                reason="snippet_insufficient",
            )
        )
        full_judgment = judge_source(
            company_name=company_name,
            identity_terms=identity_terms,
            title=item.title,
            url=item.url,
            snippet=item.snippet,
            page_text=page_text,
        )
        steps.append(
            WorkflowStep(
                tool="judge_source",
                url=item.url,
                status=full_judgment.status,
                reason=full_judgment.reason,
            )
        )
        _apply_final_judgment(
            item=item,
            judgment=full_judgment,
            page_text=page_text,
            identity_terms=identity_terms,
            accepted=accepted,
            rejected=rejected,
        )

    return GenericSourceWorkflowResult(
        accepted_sources=accepted,
        rejected_results=rejected,
        steps=steps,
        counters={
            "results_seen": min(len(search_results), max(0, max_results)),
            "fetch_count": fetches,
            "accepted_source_count": len(accepted),
            "rejected_source_count": len(rejected),
        },
    )


def _apply_final_judgment(
    *,
    item: GenericSearchResult,
    judgment: SourceJudgment,
    page_text: str,
    identity_terms: tuple[str, ...],
    accepted: list[AcceptedSourceMaterial],
    rejected: list[RejectedSourceResult],
) -> None:
    if judgment.status == "accepted":
        if not judgment.confirms_identity:
            rejected.append(
                RejectedSourceResult(
                    url=item.url,
                    title=item.title,
                    reason="company_identity_failed",
                    evidence_span=judgment.evidence_span,
                )
            )
            return
        if not judgment.confirms_fact_attribution:
            rejected.append(
                RejectedSourceResult(
                    url=item.url,
                    title=item.title,
                    reason="fact_attribution_failed",
                    evidence_span=judgment.evidence_span,
                )
            )
            return
        if not _has_trusted_identity_evidence(
            item=item,
            judgment=judgment,
            page_text=page_text,
            identity_terms=identity_terms,
        ):
            rejected.append(
                RejectedSourceResult(
                    url=item.url,
                    title=item.title,
                    reason="identity_evidence_missing",
                    evidence_span=judgment.evidence_span,
                )
            )
            return
        accepted.append(
            AcceptedSourceMaterial(
                source_id=_stable_source_id(item.url),
                source_tier="generic_web",
                url=item.url,
                title=item.title,
                captured_text=page_text,
                captured_at=datetime.now(timezone.utc),
                trust_reason=judgment.reason,
                evidence_span=judgment.evidence_span,
            )
        )
        return

    rejected.append(
        RejectedSourceResult(
            url=item.url,
            title=item.title,
            reason=judgment.reason,
            evidence_span=judgment.evidence_span,
        )
    )


def _looks_like_job_intent(item: GenericSearchResult) -> bool:
    text = f"{item.title}\n{item.url}\n{item.snippet}".lower()
    return any(
        marker in text
        for marker in (
            "招聘",
            "岗位",
            "职位",
            "薪资",
            "job",
            "jobs.",
            "/jobs",
            "career",
            "lagou",
            "zhipin",
        )
    )


def _trusted_identity_terms(
    company_name: str,
    trusted_identity_terms: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    terms: list[str] = []
    for value in (company_name, *(trusted_identity_terms or ())):
        for text in _identity_term_variants(str(value or "")):
            normalized = _normalize_identity_text(text)
            if not text or len(normalized) < 3:
                continue
            if normalized in {_normalize_identity_text(item) for item in terms}:
                continue
            terms.append(text)
    return tuple(terms)


def _has_trusted_identity_evidence(
    *,
    item: GenericSearchResult,
    judgment: SourceJudgment,
    page_text: str,
    identity_terms: tuple[str, ...],
) -> bool:
    if not identity_terms:
        return False
    evidence_text = "\n".join(
        part
        for part in (
            item.title,
            item.snippet,
            judgment.evidence_span,
            page_text,
        )
        if part
    )
    normalized_evidence = _normalize_identity_text(evidence_text)
    normalized_terms = tuple(_normalize_identity_text(term) for term in identity_terms)
    if not any(term in normalized_evidence for term in normalized_terms):
        return False

    strong_terms = tuple(term for term in normalized_terms if len(term) >= 6)
    if strong_terms and any(term in normalized_evidence for term in strong_terms):
        return True

    legal_entities = _extract_legal_entity_names(evidence_text)
    if legal_entities:
        normalized_legal_entities = tuple(
            _normalize_identity_text(entity) for entity in legal_entities
        )
        return any(
            term in legal_entity or legal_entity in term
            for term in strong_terms
            for legal_entity in normalized_legal_entities
        )

    return True


def _normalize_identity_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(
        char
        for char in normalized
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


_LEGAL_ENTITY_SUFFIXES = (
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "有限公司",
)

_LOCATION_PREFIXES = (
    "深圳市",
    "深圳",
    "北京市",
    "北京",
    "上海市",
    "上海",
    "广州市",
    "广州",
    "杭州市",
    "杭州",
    "南京市",
    "南京",
    "天津市",
    "天津",
    "重庆市",
    "重庆",
)

_BUSINESS_DESCRIPTOR_SUFFIXES = (
    "医疗科技",
    "智能科技",
    "信息技术",
    "网络科技",
    "生物科技",
    "数字科技",
    "物联网设备",
    "物联网",
    "微电子",
    "半导体",
    "机器人",
    "科技",
    "技术",
    "医疗",
    "电子",
    "智能",
    "软件",
    "设备",
)


def _identity_term_variants(value: str) -> tuple[str, ...]:
    text = value.strip()
    if not text:
        return ()

    variants: list[str] = []

    def add(candidate: str) -> bool:
        cleaned = candidate.strip()
        if not cleaned:
            return False
        normalized = _normalize_identity_text(cleaned)
        if len(normalized) < 3:
            return False
        if normalized in {_normalize_identity_text(item) for item in variants}:
            return True
        variants.append(cleaned)
        return True

    add(text)
    without_legal_suffix = _strip_legal_suffix(text)
    add(without_legal_suffix)
    without_parentheses = _remove_parenthetical_segments(without_legal_suffix)
    add(without_parentheses)
    without_location_prefix = _strip_location_prefix(without_parentheses)
    add(without_location_prefix)
    for descriptor in _BUSINESS_DESCRIPTOR_SUFFIXES:
        if without_location_prefix.endswith(descriptor):
            if add(without_location_prefix[: -len(descriptor)]):
                break

    return tuple(variants)


def _strip_legal_suffix(value: str) -> str:
    for suffix in _LEGAL_ENTITY_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _strip_location_prefix(value: str) -> str:
    for prefix in _LOCATION_PREFIXES:
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _remove_parenthetical_segments(value: str) -> str:
    result: list[str] = []
    skip_until: str | None = None
    closing = {"（": "）", "(": ")"}
    for char in value:
        if skip_until:
            if char == skip_until:
                skip_until = None
            continue
        if char in closing:
            skip_until = closing[char]
            continue
        result.append(char)
    return "".join(result).strip()


def _extract_legal_entity_names(value: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for suffix in _LEGAL_ENTITY_SUFFIXES:
        start = 0
        while True:
            suffix_at = value.find(suffix, start)
            if suffix_at < 0:
                break
            left = suffix_at
            while left > 0 and _is_legal_name_char(value[left - 1]):
                left -= 1
            candidate = value[left : suffix_at + len(suffix)].strip()
            if candidate and candidate not in candidates:
                candidates.append(candidate)
            start = suffix_at + len(suffix)
    return tuple(candidates)


def _is_legal_name_char(char: str) -> bool:
    category = unicodedata.category(char)
    if char.isspace() or category.startswith("P"):
        return char in {"（", "）", "(", ")"}
    return char.isalnum() or "\u4e00" <= char <= "\u9fff"


def _stable_source_id(url: str) -> str:
    import hashlib

    return "SRC-" + hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:16].upper()
