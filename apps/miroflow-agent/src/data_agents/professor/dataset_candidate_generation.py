from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Literal, Sequence

from .core_profile_paper_quality_audit import DatasetClosureBuckets
from .profile_summary_contract import (
    contains_operator_meta_language,
    extract_profile_fact_sentences,
)
from .profile_sections import extract_research_overview_text
from .output_summaries import PaperSummaryInput, select_eligible_paper_summary_inputs

CandidateLaneName = Literal[
    "profile_summary_repair",
    "research_overview_backfill",
    "professor_paper_summary_generation",
    "duplicate_paper_merge",
]

ProfileSummaryGenerationMethod = Literal[
    "deterministic_synthesis",
    "llm_synthesis",
]
ResearchOverviewGenerationMethod = Literal[
    "official_extract",
    "llm_translation",
]
PaperSummaryGenerationMethod = Literal[
    "deterministic_synthesis",
    "llm_synthesis",
]
DuplicateMergeEvidenceType = Literal[
    "doi_match",
    "arxiv_match",
    "source_supported_title_year_author_venue_match",
    "title_year_only",
]
PaperDuplicateStatus = Literal[
    "deduplicated",
    "unresolved_duplicate",
    "duplicate_blocked",
]
CandidateStatus = Literal["ready", "needs_review"]
SourceConfidence = Literal["strong", "medium", "weak"]
WriteRecommendation = Literal["auto_write_candidate", "review_before_write"]

_ALL_LANES: tuple[CandidateLaneName, ...] = (
    "profile_summary_repair",
    "research_overview_backfill",
    "professor_paper_summary_generation",
    "duplicate_paper_merge",
)
_LANE_TO_BLOCKER: dict[CandidateLaneName, str] = {
    "profile_summary_repair": "ready_summary_lt_200",
    "research_overview_backfill": "missing_research_overview_zh",
    "professor_paper_summary_generation": "missing_professor_paper_summary",
    "duplicate_paper_merge": "duplicate_verified_paper_title_year_groups",
}
_LANE_VALIDATION_RULES: dict[CandidateLaneName, tuple[str, ...]] = {
    "profile_summary_repair": ("profile_summary_200_300_zh_contract",),
    "research_overview_backfill": ("research_overview_zh_source_grounded",),
    "professor_paper_summary_generation": ("deduplicated_verified_paper_inputs",),
    "duplicate_paper_merge": ("safe_identifier_or_author_supported_merge",),
}
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_SAFE_DUPLICATE_EVIDENCE_TYPES = {
    "doi_match",
    "arxiv_match",
    "source_supported_title_year_author_venue_match",
}
_PROFILE_SUMMARY_FACT_TYPES = {
    "research_topic",
    "education",
    "work_experience",
    "academic_position",
    "award",
    "honor",
}
_WHITESPACE_RE = re.compile(r"\s+")
ProfileSummaryProvider = Callable[["ProfileSummaryInput"], Any]
ResearchOverviewTranslator = Callable[[str], Any]
ProfessorPaperSummaryProvider = Callable[["ProfessorPaperSummaryGenerationInput"], Any]


@dataclass(frozen=True, slots=True)
class CandidateValidationResult:
    valid: bool
    reason: str | None = None
    errors: tuple[str, ...] = ()
    next_action: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateLLMOutput:
    text: str
    provider_metadata: dict[str, Any] | None = None
    llm_self_check: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ProfileSummaryFact:
    fact_type: str
    value: str
    evidence_span: str
    source_page_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProfileSummaryInput:
    professor_id: str
    canonical_name: str
    institution: str
    department: str | None
    title: str | None
    source_page_id: str | None
    source_url: str | None
    profile_raw_text: str | None
    facts: tuple[ProfileSummaryFact, ...]
    paper_summary: str | None
    linked_output_titles: tuple[str, ...]
    source_text_hash: str
    source_ids: tuple[str, ...]
    input_facts: tuple[str, ...]

    @property
    def identity_line(self) -> str:
        suffix = "".join(
            part
            for part in (
                self.institution,
                self.department or "",
                self.title or "教师",
            )
            if part
        )
        return f"{self.canonical_name}现任{suffix}"

    @property
    def has_grounded_inputs(self) -> bool:
        return bool(
            self.profile_raw_text
            or self.input_facts
            or self.paper_summary
            or self.linked_output_titles
        )


@dataclass(frozen=True, slots=True)
class ProfessorPaperSummaryGenerationInput:
    professor_id: str
    professor_name: str
    eligible_papers: tuple[PaperSummaryInput, ...]
    excluded_paper_ids: tuple[str, ...]
    exclusion_reasons: dict[str, str]
    duplicate_status: PaperDuplicateStatus
    source_page_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DuplicatePaperRecord:
    paper_id: str
    title: str
    year: int | None
    doi: str | None
    arxiv_id: str | None
    authors_display: str | None
    venue: str | None
    canonical_source: str
    source_page_ids: tuple[str, ...]
    abstract_clean: str | None = None
    summary_zh: str | None = None
    citation_count: int | None = None


@dataclass(frozen=True, slots=True)
class ProfileSummaryCandidate:
    professor_id: str
    candidate_profile_summary: str
    source_ids: tuple[str, ...]
    source_text_hashes: tuple[str, ...]
    generation_method: ProfileSummaryGenerationMethod
    input_facts: tuple[str, ...]
    candidate_status: CandidateStatus = "ready"
    quality_flags: tuple[str, ...] = ()
    source_confidence: SourceConfidence = "strong"
    write_recommendation: WriteRecommendation = "auto_write_candidate"
    llm_self_check: dict[str, Any] | None = None
    provider_metadata: dict[str, Any] | None = None

    @property
    def lane(self) -> CandidateLaneName:
        return "profile_summary_repair"

    def to_write_evidence(self) -> dict[str, Any]:
        return {
            "candidate_profile_summary": self.candidate_profile_summary,
            "candidate_generation": {
                "lane": self.lane,
                "generation_method": self.generation_method,
                "source_ids": list(self.source_ids),
                "source_text_hashes": list(self.source_text_hashes),
                "input_facts": list(self.input_facts),
                "validation_rules": list(_LANE_VALIDATION_RULES[self.lane]),
                **_candidate_quality_evidence(self),
            },
        }


@dataclass(frozen=True, slots=True)
class ResearchOverviewCandidate:
    professor_id: str
    research_overview_content: str
    source_language: Literal["zh", "en"]
    source_text_hash: str
    source_span: str
    generation_method: ResearchOverviewGenerationMethod
    provider_metadata: dict[str, Any] | None = None
    candidate_status: CandidateStatus = "ready"
    quality_flags: tuple[str, ...] = ()
    source_confidence: SourceConfidence = "strong"
    write_recommendation: WriteRecommendation = "auto_write_candidate"
    llm_self_check: dict[str, Any] | None = None

    @property
    def lane(self) -> CandidateLaneName:
        return "research_overview_backfill"

    def to_write_evidence(self) -> dict[str, Any]:
        return {
            "research_overview_content": self.research_overview_content,
            "candidate_research_overview_zh": self.research_overview_content,
            "source_language": self.source_language,
            "source_text_hash": self.source_text_hash,
            "source_span": self.source_span,
            "generation_method": self.generation_method,
            "provider_metadata": dict(self.provider_metadata or {}),
            "candidate_generation": {
                "lane": self.lane,
                "generation_method": self.generation_method,
                "source_text_hash": self.source_text_hash,
                "source_language": self.source_language,
                "validation_rules": list(_LANE_VALIDATION_RULES[self.lane]),
                **_candidate_quality_evidence(self),
            },
        }


@dataclass(frozen=True, slots=True)
class ProfessorPaperSummaryCandidate:
    professor_id: str
    candidate_paper_summary: str
    verified_paper_ids: tuple[str, ...]
    excluded_paper_ids: tuple[str, ...]
    exclusion_reasons: dict[str, str]
    duplicate_status: PaperDuplicateStatus
    source_page_ids: tuple[str, ...]
    generation_method: PaperSummaryGenerationMethod
    candidate_status: CandidateStatus = "ready"
    quality_flags: tuple[str, ...] = ()
    source_confidence: SourceConfidence = "strong"
    write_recommendation: WriteRecommendation = "auto_write_candidate"
    llm_self_check: dict[str, Any] | None = None
    provider_metadata: dict[str, Any] | None = None

    @property
    def lane(self) -> CandidateLaneName:
        return "professor_paper_summary_generation"

    def to_write_evidence(self) -> dict[str, Any]:
        return {
            "candidate_paper_summary": self.candidate_paper_summary,
            "paper_ids": list(self.verified_paper_ids),
            "verified_paper_ids": list(self.verified_paper_ids),
            "excluded_paper_ids": list(self.excluded_paper_ids),
            "exclusion_reasons": dict(self.exclusion_reasons),
            "duplicate_status": self.duplicate_status,
            "source_page_provenance": list(self.source_page_ids),
            "generation_method": self.generation_method,
            "candidate_generation": {
                "lane": self.lane,
                "generation_method": self.generation_method,
                "source_page_ids": list(self.source_page_ids),
                "validation_rules": list(_LANE_VALIDATION_RULES[self.lane]),
                **_candidate_quality_evidence(self),
            },
        }


@dataclass(frozen=True, slots=True)
class DuplicatePaperMergeCandidate:
    professor_id: str
    duplicate_group_id: str
    canonical_paper_id: str
    old_paper_ids: tuple[str, ...]
    paper_ids: tuple[str, ...]
    evidence_type: DuplicateMergeEvidenceType
    confidence: float
    merge_reason: str
    source_page_ids: tuple[str, ...]
    candidate_status: CandidateStatus = "ready"
    quality_flags: tuple[str, ...] = ()
    source_confidence: SourceConfidence = "strong"
    write_recommendation: WriteRecommendation = "auto_write_candidate"
    llm_self_check: dict[str, Any] | None = None
    provider_metadata: dict[str, Any] | None = None

    @property
    def lane(self) -> CandidateLaneName:
        return "duplicate_paper_merge"

    def to_write_evidence(self) -> dict[str, Any]:
        return {
            "canonical_paper_id": self.canonical_paper_id,
            "old_paper_ids": list(self.old_paper_ids),
            "paper_ids": list(self.paper_ids),
            "merge_reason": self.merge_reason,
            "evidence_type": self.evidence_type,
            "confidence": self.confidence,
            "source_page_provenance": list(self.source_page_ids),
            "candidate_generation": {
                "lane": self.lane,
                "duplicate_group_id": self.duplicate_group_id,
                "evidence_type": self.evidence_type,
                "validation_rules": list(_LANE_VALIDATION_RULES[self.lane]),
                **_candidate_quality_evidence(self),
            },
        }


CandidateLike = (
    ProfileSummaryCandidate
    | ResearchOverviewCandidate
    | ProfessorPaperSummaryCandidate
    | DuplicatePaperMergeCandidate
)


@dataclass(frozen=True, slots=True)
class CandidateProviderFailure:
    lane: CandidateLaneName
    professor_id: str | None = None
    paper_id: str | None = None
    duplicate_group_id: str | None = None
    provider: str | None = None
    stage: str | None = None
    error_class: str | None = None
    retryable: bool = False
    next_action: str | None = None
    provider_metadata: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "professor_id": self.professor_id,
            "paper_id": self.paper_id,
            "duplicate_group_id": self.duplicate_group_id,
            "provider": self.provider,
            "stage": self.stage,
            "error_class": self.error_class,
            "retryable": self.retryable,
            "next_action": self.next_action,
            "provider_metadata": dict(self.provider_metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class CandidateRejection:
    lane: CandidateLaneName
    professor_id: str | None = None
    paper_id: str | None = None
    duplicate_group_id: str | None = None
    reason: str | None = None
    next_action: str | None = None
    evidence: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "professor_id": self.professor_id,
            "paper_id": self.paper_id,
            "duplicate_group_id": self.duplicate_group_id,
            "reason": self.reason,
            "next_action": self.next_action,
            "evidence": dict(self.evidence or {}),
        }


@dataclass(frozen=True, slots=True)
class LaneCandidateGenerationSummary:
    lane: CandidateLaneName
    blocker_type: str
    dataset_input_count: int
    input_count: int
    candidate_count: int
    validation_failure_count: int
    provider_failure_count: int
    skipped_count: int
    affected_professor_ids: tuple[str, ...]
    affected_paper_ids: tuple[str, ...]
    write_evidence_rows: tuple[dict[str, Any], ...]
    samples: tuple[dict[str, Any], ...]
    validation_failures: tuple[dict[str, Any], ...]
    provider_failures: tuple[dict[str, Any], ...]
    rejections: tuple[dict[str, Any], ...]
    validation_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatasetCandidateGenerationReport:
    mode: str
    dry_run: bool
    write_allowed: bool
    bucket_limit: int
    selection_hash: str
    closure_selection_hash: str
    lanes: tuple[LaneCandidateGenerationSummary, ...]


def format_candidate_generation_report(report: DatasetCandidateGenerationReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _coerce_provider_output(value: Any) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    if isinstance(value, CandidateLLMOutput):
        return (
            _clean_text(value.text),
            dict(value.provider_metadata or {}),
            dict(value.llm_self_check or {}),
        )
    return _clean_text(value), None, None


def _merge_provider_metadata(
    provider_name: str | None,
    provider_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    merged = dict(provider_metadata or {})
    if provider_name:
        merged.setdefault("provider", provider_name)
    return merged or None


def _provider_failure_metadata(exc: BaseException) -> dict[str, Any]:
    metadata = getattr(exc, "provider_metadata", None)
    return dict(metadata or {})


def _provider_retryable(exc: BaseException, *, default: bool = True) -> bool:
    value = getattr(exc, "retryable", None)
    return bool(value) if value is not None else default


def validate_profile_summary_candidate(
    candidate: ProfileSummaryCandidate,
) -> CandidateValidationResult:
    text = candidate.candidate_profile_summary.strip()
    hard_errors: list[str] = []
    if not text:
        hard_errors.append("empty_profile_summary")
    if not _CHINESE_RE.search(text):
        hard_errors.append("missing_chinese_profile_summary")
    if contains_operator_meta_language(text):
        hard_errors.append("operator_meta_language")
    soft_flags = _profile_summary_quality_flags(candidate)
    if hard_errors:
        return CandidateValidationResult(
            valid=False,
            reason="invalid_profile_summary",
            errors=tuple([*hard_errors, *soft_flags]),
            next_action="regenerate_profile_summary_from_official_sources",
        )
    return CandidateValidationResult(
        valid=True,
        errors=soft_flags,
        next_action=(
            "review_profile_summary_candidate"
            if soft_flags
            else None
        ),
    )


def build_profile_summary_input(
    *,
    professor_id: str,
    canonical_name: str,
    institution: str,
    department: str | None,
    title: str | None,
    source_page_id: str | None,
    source_url: str | None,
    profile_raw_text: str | None,
    facts: Sequence[ProfileSummaryFact],
    paper_summary: str | None,
    linked_output_titles: Sequence[str],
) -> ProfileSummaryInput:
    normalized_facts = tuple(
        fact
        for fact in facts
        if fact.fact_type in _PROFILE_SUMMARY_FACT_TYPES and _clean_text(fact.value)
    )
    source_ids = _unique_sorted(
        (
            _clean_text(source_page_id),
            *(fact.source_page_id for fact in normalized_facts),
        )
    )
    normalized_raw = _optional_clean_text(profile_raw_text)
    normalized_paper_summary = _optional_clean_text(paper_summary)
    normalized_titles = tuple(
        title
        for title in (_clean_text(item) for item in linked_output_titles)
        if title
    )
    input_facts = tuple(
        f"{fact.fact_type}:{_clean_text(fact.value)}" for fact in normalized_facts
    )
    hash_basis = normalized_raw or "\n".join(
        (
            *input_facts,
            normalized_paper_summary or "",
            *normalized_titles,
        )
    )
    return ProfileSummaryInput(
        professor_id=_clean_text(professor_id),
        canonical_name=_clean_text(canonical_name) or "该教师",
        institution=_clean_text(institution) or "所属高校",
        department=_optional_clean_text(department),
        title=_optional_clean_text(title),
        source_page_id=_optional_clean_text(source_page_id),
        source_url=_optional_clean_text(source_url),
        profile_raw_text=normalized_raw,
        facts=normalized_facts,
        paper_summary=normalized_paper_summary,
        linked_output_titles=normalized_titles,
        source_text_hash=_hash_text(hash_basis) if hash_basis else "",
        source_ids=source_ids,
        input_facts=input_facts,
    )


def generate_profile_summary_candidate(
    profile_input: ProfileSummaryInput,
    *,
    provider: ProfileSummaryProvider | None = None,
    provider_name: str | None = None,
) -> ProfileSummaryCandidate | CandidateRejection | CandidateProviderFailure:
    if not profile_input.has_grounded_inputs:
        return CandidateRejection(
            lane="profile_summary_repair",
            professor_id=profile_input.professor_id,
            reason="missing_grounded_profile_inputs",
            next_action="recrawl_official_profile_or_add_grounded_facts",
        )

    generation_method: ProfileSummaryGenerationMethod
    if provider is not None:
        try:
            summary, provider_metadata, llm_self_check = _coerce_provider_output(
                provider(profile_input)
            )
        except Exception as exc:  # noqa: BLE001 - provider failure is report data
            return CandidateProviderFailure(
                lane="profile_summary_repair",
                professor_id=profile_input.professor_id,
                provider=provider_name,
                stage="profile_summary_generation",
                error_class=type(exc).__name__,
                retryable=_provider_retryable(exc),
                next_action="retry_with_same_grounded_profile_inputs",
                provider_metadata=_provider_failure_metadata(exc),
            )
        generation_method = "llm_synthesis"
    else:
        summary = _build_deterministic_profile_summary(profile_input)
        provider_metadata = None
        llm_self_check = None
        generation_method = "deterministic_synthesis"

    source_text_hashes = (
        (profile_input.source_text_hash,) if profile_input.source_text_hash else ()
    )
    candidate = ProfileSummaryCandidate(
        professor_id=profile_input.professor_id,
        candidate_profile_summary=summary,
        source_ids=profile_input.source_ids,
        source_text_hashes=source_text_hashes,
        generation_method=generation_method,
        input_facts=profile_input.input_facts,
        llm_self_check=llm_self_check,
        provider_metadata=_merge_provider_metadata(provider_name, provider_metadata),
    )
    validation = validate_profile_summary_candidate(candidate)
    if validation.valid:
        return _with_candidate_quality_evidence(candidate)
    return CandidateRejection(
        lane="profile_summary_repair",
        professor_id=profile_input.professor_id,
        reason="invalid_profile_summary_candidate",
        next_action="regenerate_profile_summary_from_official_sources",
        evidence={
            "errors": list(validation.errors),
            "candidate_length": len(summary),
            "generation_method": generation_method,
        },
    )


def validate_research_overview_candidate(
    candidate: ResearchOverviewCandidate,
) -> CandidateValidationResult:
    text = candidate.research_overview_content.strip()
    hard_errors: list[str] = []
    if not _CHINESE_RE.search(text):
        hard_errors.append("missing_chinese_research_overview")
    if len(text) < 10:
        hard_errors.append("research_overview_too_short")
    soft_flags = _research_overview_quality_flags(candidate)
    if hard_errors:
        return CandidateValidationResult(
            valid=False,
            reason="invalid_research_overview",
            errors=tuple([*hard_errors, *soft_flags]),
            next_action="extract_or_translate_research_overview_from_official_source",
        )
    return CandidateValidationResult(
        valid=True,
        errors=soft_flags,
        next_action=(
            "review_research_overview_candidate"
            if soft_flags
            else None
        ),
    )


def generate_research_overview_candidate(
    *,
    professor_id: str,
    profile_raw_text: str | None,
    source_page_id: str | None,
    source_url: str | None,
    translator: ResearchOverviewTranslator | None = None,
    provider_name: str | None = None,
) -> ResearchOverviewCandidate | CandidateRejection | CandidateProviderFailure:
    source_span = extract_research_overview_text(profile_raw_text)
    if source_span is None:
        return CandidateRejection(
            lane="research_overview_backfill",
            professor_id=_clean_text(professor_id),
            reason="source_missing",
            next_action="recrawl_official_profile_research_overview",
            evidence={
                "source_page_id": source_page_id,
                "source_url": source_url,
            },
        )

    source_language = _detect_language(source_span)
    source_text_hash = _hash_text(source_span)
    if source_language == "zh":
        candidate = ResearchOverviewCandidate(
            professor_id=_clean_text(professor_id),
            research_overview_content=_clean_text(source_span),
            source_language="zh",
            source_text_hash=source_text_hash,
            source_span=_clean_text(source_span),
            generation_method="official_extract",
        )
    else:
        if translator is None:
            return CandidateRejection(
                lane="research_overview_backfill",
                professor_id=_clean_text(professor_id),
                reason="translation_provider_required",
                next_action="configure_llm_translation_provider",
                evidence={
                    "source_page_id": source_page_id,
                    "source_url": source_url,
                    "source_text_hash": source_text_hash,
                    "source_language": source_language,
                },
            )
        try:
            translated, provider_metadata, llm_self_check = _coerce_provider_output(
                translator(source_span)
            )
        except Exception as exc:  # noqa: BLE001 - provider failure is evidence
            return CandidateProviderFailure(
                lane="research_overview_backfill",
                professor_id=_clean_text(professor_id),
                provider=provider_name,
                stage="llm_translation",
                error_class=type(exc).__name__,
                retryable=_provider_retryable(exc),
                next_action="retry_translation_with_same_source_hash",
                provider_metadata=_provider_failure_metadata(exc),
            )
        candidate = ResearchOverviewCandidate(
            professor_id=_clean_text(professor_id),
            research_overview_content=translated,
            source_language="en",
            source_text_hash=source_text_hash,
            source_span=_clean_text(source_span),
            generation_method="llm_translation",
            provider_metadata=_merge_provider_metadata(provider_name, provider_metadata),
            llm_self_check=llm_self_check,
        )

    validation = validate_research_overview_candidate(candidate)
    if validation.valid:
        return _with_candidate_quality_evidence(candidate)
    return CandidateRejection(
        lane="research_overview_backfill",
        professor_id=_clean_text(professor_id),
        reason="invalid_research_overview_candidate",
        next_action="repair_research_overview_source_or_translation",
        evidence={
            "errors": list(validation.errors),
            "source_page_id": source_page_id,
            "source_url": source_url,
            "source_text_hash": source_text_hash,
        },
    )


def validate_paper_summary_candidate(
    candidate: ProfessorPaperSummaryCandidate,
) -> CandidateValidationResult:
    text = candidate.candidate_paper_summary.strip()
    hard_errors: list[str] = []
    if not _CHINESE_RE.search(text):
        hard_errors.append("missing_chinese_paper_summary")
    if len(text) < 20:
        hard_errors.append("paper_summary_too_short")
    if not candidate.verified_paper_ids:
        hard_errors.append("missing_verified_paper_ids")
    soft_flags = _paper_summary_quality_flags(candidate)
    if hard_errors:
        return CandidateValidationResult(
            valid=False,
            reason="invalid_paper_summary",
            errors=tuple([*hard_errors, *soft_flags]),
            next_action="regenerate_paper_summary_from_deduplicated_verified_links",
        )
    return CandidateValidationResult(
        valid=True,
        errors=soft_flags,
        next_action=(
            "review_paper_summary_candidate"
            if soft_flags
            else None
        ),
    )


def generate_professor_paper_summary_candidate(
    *,
    professor_id: str,
    professor_name: str,
    paper_inputs: Sequence[PaperSummaryInput],
    source_page_ids: Sequence[str],
    duplicate_status: PaperDuplicateStatus = "deduplicated",
    provider: ProfessorPaperSummaryProvider | None = None,
    provider_name: str | None = None,
) -> ProfessorPaperSummaryCandidate | CandidateRejection | CandidateProviderFailure:
    eligible, excluded_reasons = _filter_eligible_paper_summary_inputs(paper_inputs)
    source_page_id_tuple = tuple(
        source_id for source_id in (_clean_text(item) for item in source_page_ids) if source_id
    )
    generation_input = ProfessorPaperSummaryGenerationInput(
        professor_id=_clean_text(professor_id),
        professor_name=_clean_text(professor_name) or "该教师",
        eligible_papers=eligible,
        excluded_paper_ids=tuple(excluded_reasons.keys()),
        exclusion_reasons=excluded_reasons,
        duplicate_status=duplicate_status,
        source_page_ids=source_page_id_tuple,
    )

    if not eligible:
        reason = (
            "provider_only_author_search"
            if excluded_reasons
            and set(excluded_reasons.values()) == {"provider_only_author_search"}
            else "missing_verified_paper_inputs"
        )
        return CandidateRejection(
            lane="professor_paper_summary_generation",
            professor_id=generation_input.professor_id,
            reason=reason,
            next_action=(
                "verify_papers_from_official_professor_page"
                if reason == "provider_only_author_search"
                else "collect_verified_professor_seeded_papers"
            ),
            evidence={
                "excluded_paper_ids": list(excluded_reasons.keys()),
                "exclusion_reasons": dict(excluded_reasons),
            },
        )
    if provider is not None:
        try:
            summary, provider_metadata, llm_self_check = _coerce_provider_output(
                provider(generation_input)
            )
        except Exception as exc:  # noqa: BLE001 - provider failure is evidence
            return CandidateProviderFailure(
                lane="professor_paper_summary_generation",
                professor_id=generation_input.professor_id,
                provider=provider_name,
                stage="paper_summary_generation",
                error_class=type(exc).__name__,
                retryable=_provider_retryable(exc),
                next_action="retry_with_same_verified_paper_inputs",
                provider_metadata=_provider_failure_metadata(exc),
            )
        generation_method: PaperSummaryGenerationMethod = "llm_synthesis"
    else:
        summary = _build_deterministic_paper_summary(generation_input)
        provider_metadata = None
        llm_self_check = None
        generation_method = "deterministic_synthesis"

    candidate = ProfessorPaperSummaryCandidate(
        professor_id=generation_input.professor_id,
        candidate_paper_summary=summary,
        verified_paper_ids=tuple(item.paper_id for item in eligible),
        excluded_paper_ids=generation_input.excluded_paper_ids,
        exclusion_reasons=generation_input.exclusion_reasons,
        duplicate_status=duplicate_status,
        source_page_ids=source_page_id_tuple,
        generation_method=generation_method,
        llm_self_check=llm_self_check,
        provider_metadata=_merge_provider_metadata(provider_name, provider_metadata),
    )
    validation = validate_paper_summary_candidate(candidate)
    if validation.valid:
        return _with_candidate_quality_evidence(candidate)
    return CandidateRejection(
        lane="professor_paper_summary_generation",
        professor_id=generation_input.professor_id,
        reason="invalid_paper_summary_candidate",
        next_action="regenerate_paper_summary_from_verified_papers",
        evidence={
            "errors": list(validation.errors),
            "eligible_paper_ids": [item.paper_id for item in eligible],
        },
    )


def validate_duplicate_merge_candidate(
    candidate: DuplicatePaperMergeCandidate,
) -> CandidateValidationResult:
    hard_errors: list[str] = []
    if not candidate.canonical_paper_id.strip():
        hard_errors.append("missing_canonical_paper_id")
    if not candidate.old_paper_ids:
        hard_errors.append("missing_old_paper_ids")
    if candidate.canonical_paper_id in set(candidate.old_paper_ids):
        hard_errors.append("canonical_in_old_paper_ids")
    expected_ids = {candidate.canonical_paper_id, *candidate.old_paper_ids}
    if not expected_ids.issubset(set(candidate.paper_ids)):
        hard_errors.append("paper_id_set_mismatch")
    soft_flags = _duplicate_merge_quality_flags(candidate)
    if hard_errors:
        return CandidateValidationResult(
            valid=False,
            reason="invalid_duplicate_merge",
            errors=tuple([*hard_errors, *soft_flags]),
            next_action="manual_duplicate_paper_review",
        )
    return CandidateValidationResult(
        valid=True,
        errors=soft_flags,
        next_action=(
            "manual_duplicate_paper_review"
            if soft_flags
            else None
        ),
    )


def plan_duplicate_paper_merge_candidate(
    *,
    professor_id: str,
    duplicate_group_id: str,
    papers: Sequence[DuplicatePaperRecord],
) -> DuplicatePaperMergeCandidate | CandidateRejection:
    normalized_papers = tuple(
        paper for paper in papers if _clean_text(paper.paper_id) and _clean_text(paper.title)
    )
    if len(normalized_papers) < 2:
        return CandidateRejection(
            lane="duplicate_paper_merge",
            professor_id=_clean_text(professor_id),
            duplicate_group_id=_clean_text(duplicate_group_id),
            reason="insufficient_duplicate_group",
            next_action="manual_duplicate_paper_review",
        )

    doi_candidate = _identifier_merge_candidate(
        professor_id=professor_id,
        duplicate_group_id=duplicate_group_id,
        papers=normalized_papers,
        identity_getter=_normalized_doi,
        evidence_type="doi_match",
        confidence=0.99,
    )
    if doi_candidate is not None:
        return doi_candidate

    arxiv_candidate = _identifier_merge_candidate(
        professor_id=professor_id,
        duplicate_group_id=duplicate_group_id,
        papers=normalized_papers,
        identity_getter=_normalized_arxiv_id,
        evidence_type="arxiv_match",
        confidence=0.98,
    )
    if arxiv_candidate is not None:
        return arxiv_candidate

    if _has_source_supported_identity(normalized_papers):
        return _merge_candidate_from_papers(
            professor_id=professor_id,
            duplicate_group_id=duplicate_group_id,
            papers=normalized_papers,
            evidence_type="source_supported_title_year_author_venue_match",
            confidence=0.93,
        )

    return _with_candidate_quality_evidence(
        _merge_candidate_from_papers(
            professor_id=professor_id,
            duplicate_group_id=duplicate_group_id,
            papers=normalized_papers,
            evidence_type="title_year_only",
            confidence=0.60,
        )
    )


def build_candidate_generation_report(
    buckets: DatasetClosureBuckets,
    *,
    candidates: Sequence[CandidateLike] = (),
    provider_failures: Sequence[CandidateProviderFailure] = (),
    rejections: Sequence[CandidateRejection] = (),
    lanes: Sequence[CandidateLaneName] | None = None,
) -> DatasetCandidateGenerationReport:
    normalized_lanes = tuple(lanes or _ALL_LANES)
    valid_by_lane: dict[CandidateLaneName, list[CandidateLike]] = {
        lane: [] for lane in normalized_lanes
    }
    validation_failures_by_lane: dict[CandidateLaneName, list[dict[str, Any]]] = {
        lane: [] for lane in normalized_lanes
    }
    for candidate in candidates:
        lane = candidate.lane
        if lane not in valid_by_lane:
            continue
        result = validate_candidate(candidate)
        if result.valid:
            valid_by_lane[lane].append(_with_candidate_quality_evidence(candidate))
        else:
            validation_failures_by_lane[lane].append(
                _validation_failure_payload(candidate, result)
            )

    provider_failures_by_lane = _group_payloads_by_lane(
        failure.to_payload() for failure in provider_failures
    )
    rejections_by_lane = _group_payloads_by_lane(
        rejection.to_payload() for rejection in rejections
    )
    summaries = tuple(
        _build_lane_summary(
            buckets,
            lane=lane,
            candidates=valid_by_lane[lane],
            validation_failures=tuple(validation_failures_by_lane[lane]),
            provider_failures=tuple(provider_failures_by_lane.get(lane, ())),
            rejections=tuple(rejections_by_lane.get(lane, ())),
        )
        for lane in normalized_lanes
    )
    return DatasetCandidateGenerationReport(
        mode="candidate_dry_run",
        dry_run=True,
        write_allowed=False,
        bucket_limit=buckets.bucket_limit,
        selection_hash=_selection_hash(
            bucket_limit=buckets.bucket_limit,
            lanes=normalized_lanes,
            summaries=summaries,
        ),
        closure_selection_hash=_closure_selection_hash(
            buckets=buckets,
            lanes=normalized_lanes,
        ),
        lanes=summaries,
    )


def build_candidate_generation_report_for_buckets(
    *,
    conn: Any,
    buckets: DatasetClosureBuckets,
    lanes: Sequence[CandidateLaneName],
    profile_summary_provider: ProfileSummaryProvider | None = None,
    research_translator: ResearchOverviewTranslator | None = None,
    paper_summary_provider: ProfessorPaperSummaryProvider | None = None,
    provider_name: str | None = None,
) -> DatasetCandidateGenerationReport:
    normalized_lanes = tuple(_normalize_lane(lane) for lane in lanes)
    candidates: list[CandidateLike] = []
    provider_failures: list[CandidateProviderFailure] = []
    rejections: list[CandidateRejection] = []
    for row in buckets.rows:
        lane = _normalize_lane(row.remediation_lane)
        if lane not in normalized_lanes:
            continue
        if not row.automatic_eligibility:
            rejections.append(
                CandidateRejection(
                    lane=lane,
                    professor_id=row.professor_id,
                    paper_id=row.paper_id,
                    duplicate_group_id=row.duplicate_group_id,
                    reason=row.skip_reason or "not_automatically_eligible",
                    next_action="manual_review_or_source_recollection",
                    evidence=row.evidence or {},
                )
            )
            continue
        result = _generate_candidate_for_row(
            conn=conn,
            row=row,
            lane=lane,
            profile_summary_provider=profile_summary_provider,
            research_translator=research_translator,
            paper_summary_provider=paper_summary_provider,
            provider_name=provider_name,
        )
        if isinstance(result, CandidateProviderFailure):
            provider_failures.append(result)
        elif isinstance(result, CandidateRejection):
            rejections.append(result)
        else:
            candidates.append(result)

    return build_candidate_generation_report(
        buckets,
        candidates=tuple(candidates),
        provider_failures=tuple(provider_failures),
        rejections=tuple(rejections),
        lanes=normalized_lanes,
    )


def enrich_buckets_with_candidate_write_evidence(
    buckets: DatasetClosureBuckets,
    *,
    candidate_payload: dict[str, Any],
) -> DatasetClosureBuckets:
    evidence_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for lane_payload in candidate_payload.get("lanes") or ():
        if not isinstance(lane_payload, dict):
            continue
        lane = str(lane_payload.get("lane") or "")
        for item in lane_payload.get("write_evidence_rows") or ():
            if not isinstance(item, dict):
                continue
            key = _payload_target_key(item)
            write_evidence = item.get("write_evidence")
            if key and isinstance(write_evidence, dict):
                evidence_by_key[(lane, key)] = write_evidence

    if not evidence_by_key:
        return buckets
    enriched_rows = []
    for row in buckets.rows:
        row_key = _bucket_row_key(row)
        evidence = evidence_by_key.get((row.remediation_lane, row_key))
        if evidence is None:
            enriched_rows.append(row)
            continue
        enriched_rows.append(
            replace(
                row,
                evidence={
                    **(row.evidence or {}),
                    **evidence,
                },
            )
        )
    return replace(buckets, rows=enriched_rows)


def validate_candidate(candidate: CandidateLike) -> CandidateValidationResult:
    if isinstance(candidate, ProfileSummaryCandidate):
        return validate_profile_summary_candidate(candidate)
    if isinstance(candidate, ResearchOverviewCandidate):
        return validate_research_overview_candidate(candidate)
    if isinstance(candidate, ProfessorPaperSummaryCandidate):
        return validate_paper_summary_candidate(candidate)
    if isinstance(candidate, DuplicatePaperMergeCandidate):
        return validate_duplicate_merge_candidate(candidate)
    raise TypeError(f"unsupported candidate type: {type(candidate).__name__}")


def _generate_candidate_for_row(
    *,
    conn: Any,
    row: Any,
    lane: CandidateLaneName,
    profile_summary_provider: ProfileSummaryProvider | None,
    research_translator: ResearchOverviewTranslator | None,
    paper_summary_provider: ProfessorPaperSummaryProvider | None,
    provider_name: str | None,
) -> CandidateLike | CandidateRejection | CandidateProviderFailure:
    if lane == "profile_summary_repair":
        profile_input = _load_profile_summary_input(conn, row)
        if profile_input is None:
            return CandidateRejection(
                lane=lane,
                professor_id=row.professor_id,
                reason="professor_missing",
                next_action="manual_professor_record_review",
            )
        return generate_profile_summary_candidate(
            profile_input,
            provider=profile_summary_provider,
            provider_name=provider_name,
        )
    if lane == "research_overview_backfill":
        raw = _load_professor_source_text(conn, row.professor_id)
        return generate_research_overview_candidate(
            professor_id=row.professor_id or "",
            profile_raw_text=raw.get("profile_raw_text"),
            source_page_id=raw.get("source_page_id") or row.source_page_id,
            source_url=raw.get("source_url") or row.source_url,
            translator=research_translator,
            provider_name=provider_name,
        )
    if lane == "professor_paper_summary_generation":
        professor_id = _clean_text(row.professor_id)
        paper_inputs = select_eligible_paper_summary_inputs(
            conn,
            professor_id=professor_id,
        )
        return generate_professor_paper_summary_candidate(
            professor_id=professor_id,
            professor_name=_professor_name_from_row(row),
            paper_inputs=paper_inputs,
            source_page_ids=_load_verified_paper_source_page_ids(conn, professor_id),
            duplicate_status=(
                "unresolved_duplicate"
                if (row.evidence or {}).get("duplicate_group_count")
                else "deduplicated"
            ),
            provider=paper_summary_provider,
            provider_name=provider_name,
        )
    if lane == "duplicate_paper_merge":
        return plan_duplicate_paper_merge_candidate(
            professor_id=row.professor_id or "",
            duplicate_group_id=row.duplicate_group_id or "",
            papers=_load_duplicate_paper_records(conn, row),
        )
    raise ValueError(f"unsupported candidate generation lane: {lane}")


def _build_lane_summary(
    buckets: DatasetClosureBuckets,
    *,
    lane: CandidateLaneName,
    candidates: Sequence[CandidateLike],
    validation_failures: tuple[dict[str, Any], ...],
    provider_failures: tuple[dict[str, Any], ...],
    rejections: tuple[dict[str, Any], ...],
) -> LaneCandidateGenerationSummary:
    blocker_type = _LANE_TO_BLOCKER[lane]
    rows = [row for row in buckets.rows if row.remediation_lane == lane]
    rejection_keys = {_target_key(payload) for payload in rejections}
    skipped_rows = [
        row
        for row in rows
        if not row.automatic_eligibility and _bucket_row_key(row) not in rejection_keys
    ]
    return LaneCandidateGenerationSummary(
        lane=lane,
        blocker_type=blocker_type,
        dataset_input_count=int(
            (buckets.summary.get(blocker_type) or {}).get("total") or 0
        ),
        input_count=len(rows),
        candidate_count=len(candidates),
        validation_failure_count=len(validation_failures),
        provider_failure_count=len(provider_failures),
        skipped_count=len(skipped_rows) + len(rejections),
        affected_professor_ids=_unique_sorted(
            _candidate_professor_id(candidate) for candidate in candidates
        ),
        affected_paper_ids=_unique_sorted(
            paper_id
            for candidate in candidates
            for paper_id in _candidate_paper_ids(candidate)
        ),
        write_evidence_rows=tuple(_candidate_sample(candidate) for candidate in candidates),
        samples=tuple(_candidate_sample(candidate) for candidate in candidates[:5]),
        validation_failures=validation_failures,
        provider_failures=provider_failures,
        rejections=rejections,
        validation_rules=_LANE_VALIDATION_RULES[lane],
    )


def _validation_failure_payload(
    candidate: CandidateLike,
    result: CandidateValidationResult,
) -> dict[str, Any]:
    return {
        "lane": candidate.lane,
        "professor_id": _candidate_professor_id(candidate),
        "paper_id": None,
        "duplicate_group_id": getattr(candidate, "duplicate_group_id", None),
        "reason": result.reason,
        "errors": list(result.errors),
        "next_action": result.next_action,
    }


def _candidate_sample(candidate: CandidateLike) -> dict[str, Any]:
    gate = _candidate_quality_evidence(candidate)
    return {
        "lane": candidate.lane,
        "professor_id": _candidate_professor_id(candidate),
        "duplicate_group_id": getattr(candidate, "duplicate_group_id", None),
        "paper_ids": list(_candidate_paper_ids(candidate)),
        "candidate_status": gate["candidate_status"],
        "quality_flags": gate["quality_flags"],
        "source_confidence": gate["source_confidence"],
        "write_recommendation": gate["write_recommendation"],
        "write_evidence": candidate.to_write_evidence(),
    }


def _with_candidate_quality_evidence(candidate: CandidateLike) -> CandidateLike:
    quality = _candidate_quality_values(candidate)
    return replace(
        candidate,
        candidate_status=quality["candidate_status"],
        quality_flags=tuple(quality["quality_flags"]),
        source_confidence=quality["source_confidence"],
        write_recommendation=quality["write_recommendation"],
        llm_self_check=quality["llm_self_check"],
    )


def _candidate_quality_evidence(candidate: CandidateLike) -> dict[str, Any]:
    quality = _candidate_quality_values(candidate)
    return {
        "candidate_status": quality["candidate_status"],
        "quality_flags": list(quality["quality_flags"]),
        "source_confidence": quality["source_confidence"],
        "write_recommendation": quality["write_recommendation"],
        "llm_self_check": quality["llm_self_check"],
        "provider_metadata": dict(
            getattr(candidate, "provider_metadata", None) or {}
        ),
    }


def _candidate_quality_values(candidate: CandidateLike) -> dict[str, Any]:
    flags = _candidate_quality_flags(candidate)
    candidate_status: CandidateStatus = (
        "needs_review"
        if flags or candidate.candidate_status == "needs_review"
        else "ready"
    )
    write_recommendation: WriteRecommendation = (
        "review_before_write"
        if candidate_status == "needs_review"
        or candidate.write_recommendation == "review_before_write"
        else "auto_write_candidate"
    )
    source_confidence = _candidate_source_confidence(candidate, flags)
    llm_self_check = dict(candidate.llm_self_check or {})
    llm_self_check.setdefault("hard_rejection", False)
    llm_self_check.setdefault("quality_flags", list(flags))
    llm_self_check.setdefault("review_required", candidate_status == "needs_review")
    llm_self_check.setdefault("source_confidence", source_confidence)
    return {
        "candidate_status": candidate_status,
        "quality_flags": flags,
        "source_confidence": source_confidence,
        "write_recommendation": write_recommendation,
        "llm_self_check": llm_self_check,
    }


def _candidate_source_confidence(
    candidate: CandidateLike,
    flags: tuple[str, ...],
) -> SourceConfidence:
    if candidate.source_confidence != "strong":
        return candidate.source_confidence
    source_flags = {
        "missing_profile_summary_sources",
        "missing_source_text_hash",
        "invalid_source_text_hash",
        "missing_source_span",
        "missing_source_page_provenance",
        "unsafe_duplicate_merge_evidence",
    }
    if source_flags.intersection(flags):
        return "weak"
    non_source_review_flags = set(flags) - {"profile_summary_length_out_of_range"}
    return "medium" if non_source_review_flags else "strong"


def _candidate_quality_flags(candidate: CandidateLike) -> tuple[str, ...]:
    if isinstance(candidate, ProfileSummaryCandidate):
        flags = _profile_summary_quality_flags(candidate)
    elif isinstance(candidate, ResearchOverviewCandidate):
        flags = _research_overview_quality_flags(candidate)
    elif isinstance(candidate, ProfessorPaperSummaryCandidate):
        flags = _paper_summary_quality_flags(candidate)
    elif isinstance(candidate, DuplicatePaperMergeCandidate):
        flags = _duplicate_merge_quality_flags(candidate)
    else:
        flags = ()
    return _dedupe_flags((*candidate.quality_flags, *flags))


def _profile_summary_quality_flags(
    candidate: ProfileSummaryCandidate,
) -> tuple[str, ...]:
    text = candidate.candidate_profile_summary.strip()
    flags: list[str] = []
    if text and not 200 <= len(text) <= 300:
        flags.append("profile_summary_length_out_of_range")
    if not candidate.source_ids and not candidate.source_text_hashes:
        flags.append("missing_profile_summary_sources")
    if not candidate.input_facts:
        flags.append("missing_profile_summary_input_facts")
    return tuple(flags)


def _research_overview_quality_flags(
    candidate: ResearchOverviewCandidate,
) -> tuple[str, ...]:
    flags: list[str] = []
    if not candidate.source_text_hash:
        flags.append("missing_source_text_hash")
    elif not _SHA256_RE.fullmatch(candidate.source_text_hash):
        flags.append("invalid_source_text_hash")
    if not candidate.source_span.strip():
        flags.append("missing_source_span")
    expected_method = (
        "official_extract" if candidate.source_language == "zh" else "llm_translation"
    )
    if candidate.generation_method != expected_method:
        flags.append("invalid_generation_method_for_language")
    return tuple(flags)


def _paper_summary_quality_flags(
    candidate: ProfessorPaperSummaryCandidate,
) -> tuple[str, ...]:
    flags: list[str] = []
    if not candidate.source_page_ids:
        flags.append("missing_source_page_provenance")
    if candidate.duplicate_status != "deduplicated":
        flags.append("unresolved_duplicate_status")
    return tuple(flags)


def _duplicate_merge_quality_flags(
    candidate: DuplicatePaperMergeCandidate,
) -> tuple[str, ...]:
    flags: list[str] = []
    if (
        candidate.evidence_type not in _SAFE_DUPLICATE_EVIDENCE_TYPES
        or candidate.confidence < 0.90
    ):
        flags.append("unsafe_duplicate_merge_evidence")
    if not candidate.source_page_ids:
        flags.append("missing_source_page_provenance")
    return tuple(flags)


def _dedupe_flags(flags: Sequence[str]) -> tuple[str, ...]:
    return tuple(_dedupe_preserve_order(flags))


def _group_payloads_by_lane(
    payloads: Sequence[dict[str, Any]] | Any,
) -> dict[CandidateLaneName, tuple[dict[str, Any], ...]]:
    grouped: dict[CandidateLaneName, list[dict[str, Any]]] = {}
    for payload in payloads:
        lane = str(payload.get("lane") or "")
        if lane not in _LANE_TO_BLOCKER:
            continue
        grouped.setdefault(lane, []).append(payload)  # type: ignore[arg-type]
    return {lane: tuple(items) for lane, items in grouped.items()}


def _candidate_professor_id(candidate: CandidateLike) -> str:
    return candidate.professor_id


def _candidate_paper_ids(candidate: CandidateLike) -> tuple[str, ...]:
    if isinstance(candidate, ProfessorPaperSummaryCandidate):
        return candidate.verified_paper_ids
    if isinstance(candidate, DuplicatePaperMergeCandidate):
        return candidate.paper_ids
    return ()


def _load_profile_summary_input(conn: Any, row: Any) -> ProfileSummaryInput | None:
    professor_id = _clean_text(row.professor_id)
    if not professor_id:
        return None
    profile = conn.execute(
        """
        SELECT p.professor_id,
               p.canonical_name,
               ''::text AS institution,
               NULL::text AS department,
               NULL::text AS title,
               p.primary_official_profile_page_id AS source_page_id,
               sp.url AS source_url,
               p.profile_raw_text,
               p.paper_summary
          FROM professor p
          LEFT JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE p.professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if profile is None:
        return None
    return build_profile_summary_input(
        professor_id=professor_id,
        canonical_name=str(_row_value(profile, "canonical_name", 1) or ""),
        institution=str(_row_value(profile, "institution", 2) or ""),
        department=_optional_clean_text(_row_value(profile, "department", 3)),
        title=_optional_clean_text(_row_value(profile, "title", 4)),
        source_page_id=_optional_clean_text(_row_value(profile, "source_page_id", 5)),
        source_url=_optional_clean_text(_row_value(profile, "source_url", 6)),
        profile_raw_text=_optional_clean_text(_row_value(profile, "profile_raw_text", 7)),
        facts=_load_profile_summary_facts(conn, professor_id),
        paper_summary=_optional_clean_text(_row_value(profile, "paper_summary", 8)),
        linked_output_titles=_load_verified_paper_titles(conn, professor_id),
    )


def _load_profile_summary_facts(
    conn: Any,
    professor_id: str,
) -> tuple[ProfileSummaryFact, ...]:
    rows = conn.execute(
        """
        SELECT fact_type, value_raw, evidence_span, source_page_id
          FROM professor_fact
         WHERE professor_id = %s
           AND status = 'active'
           AND fact_type = ANY(%s)
         ORDER BY fact_type, fact_id
         LIMIT 40
        """,
        (professor_id, list(_PROFILE_SUMMARY_FACT_TYPES)),
    ).fetchall()
    facts: list[ProfileSummaryFact] = []
    for row in rows:
        facts.append(
            ProfileSummaryFact(
                fact_type=str(_row_value(row, "fact_type", 0) or ""),
                value=str(_row_value(row, "value_raw", 1) or ""),
                evidence_span=str(_row_value(row, "evidence_span", 2) or ""),
                source_page_id=_optional_clean_text(_row_value(row, "source_page_id", 3)),
            )
        )
    return tuple(facts)


def _load_verified_paper_titles(conn: Any, professor_id: str) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT p.title_clean
          FROM professor_paper_link ppl
          JOIN paper p ON p.paper_id = ppl.paper_id
         WHERE ppl.professor_id = %s
           AND ppl.link_status = 'verified'
           AND NULLIF(BTRIM(COALESCE(p.title_clean, '')), '') IS NOT NULL
         ORDER BY p.year DESC NULLS LAST, p.title_clean ASC
         LIMIT 5
        """,
        (professor_id,),
    ).fetchall()
    return tuple(str(_row_value(row, "title_clean", 0) or "") for row in rows)


def _load_professor_source_text(conn: Any, professor_id: str | None) -> dict[str, str | None]:
    professor_id = _clean_text(professor_id)
    if not professor_id:
        return {}
    row = conn.execute(
        """
        SELECT p.profile_raw_text,
               p.primary_official_profile_page_id AS source_page_id,
               sp.url AS source_url
          FROM professor p
          LEFT JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE p.professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if row is None:
        return {}
    return {
        "profile_raw_text": _optional_clean_text(_row_value(row, "profile_raw_text", 0)),
        "source_page_id": _optional_clean_text(_row_value(row, "source_page_id", 1)),
        "source_url": _optional_clean_text(_row_value(row, "source_url", 2)),
    }


def _load_verified_paper_source_page_ids(conn: Any, professor_id: str) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT DISTINCT evidence_page_id::text AS source_page_id
          FROM professor_paper_link
         WHERE professor_id = %s
           AND link_status = 'verified'
           AND evidence_page_id IS NOT NULL
         ORDER BY evidence_page_id::text
         LIMIT 20
        """,
        (professor_id,),
    ).fetchall()
    return tuple(str(_row_value(row, "source_page_id", 0) or "") for row in rows)


def _load_duplicate_paper_records(conn: Any, row: Any) -> tuple[DuplicatePaperRecord, ...]:
    paper_ids = tuple(
        item
        for item in _string_tuple((row.evidence or {}).get("paper_ids"))
        if item
    )
    if not paper_ids:
        return ()
    rows = conn.execute(
        """
        SELECT p.paper_id,
               p.title_clean,
               p.year,
               p.doi,
               p.arxiv_id,
               p.authors_display,
               p.venue,
               p.canonical_source,
               p.abstract_clean,
               p.summary_zh,
               p.citation_count,
               array_remove(array_agg(DISTINCT ppl.evidence_page_id::text), NULL)
                 AS source_page_ids
          FROM paper p
          LEFT JOIN professor_paper_link ppl
            ON ppl.paper_id = p.paper_id
           AND ppl.professor_id = %s
           AND ppl.link_status = 'verified'
         WHERE p.paper_id = ANY(%s)
         GROUP BY p.paper_id
         ORDER BY p.paper_id
        """,
        (_clean_text(row.professor_id), list(paper_ids)),
    ).fetchall()
    return tuple(
        DuplicatePaperRecord(
            paper_id=str(_row_value(record, "paper_id", 0) or ""),
            title=str(_row_value(record, "title_clean", 1) or ""),
            year=_optional_int(_row_value(record, "year", 2)),
            doi=_optional_clean_text(_row_value(record, "doi", 3)),
            arxiv_id=_optional_clean_text(_row_value(record, "arxiv_id", 4)),
            authors_display=_optional_clean_text(_row_value(record, "authors_display", 5)),
            venue=_optional_clean_text(_row_value(record, "venue", 6)),
            canonical_source=str(_row_value(record, "canonical_source", 7) or ""),
            abstract_clean=_optional_clean_text(_row_value(record, "abstract_clean", 8)),
            summary_zh=_optional_clean_text(_row_value(record, "summary_zh", 9)),
            citation_count=_optional_int(_row_value(record, "citation_count", 10)),
            source_page_ids=tuple(
                str(source_page_id)
                for source_page_id in (_row_value(record, "source_page_ids", 11) or ())
                if source_page_id
            ),
        )
        for record in rows
    )


def _professor_name_from_row(row: Any) -> str:
    evidence = row.evidence or {}
    return _clean_text(evidence.get("canonical_name")) or _clean_text(row.professor_id)


def _normalize_lane(lane: str) -> CandidateLaneName:
    if lane not in _LANE_TO_BLOCKER:
        raise ValueError(f"unsupported candidate generation lane: {lane}")
    return lane  # type: ignore[return-value]


def _bucket_row_key(row: Any) -> str:
    if row.duplicate_group_id:
        return f"duplicate_group:{row.duplicate_group_id}"
    if row.paper_id:
        return f"paper:{row.paper_id}"
    if row.professor_id:
        return f"professor:{row.professor_id}"
    return f"{row.entity_type}:{row.blocker_type}"


def _target_key(payload: dict[str, Any]) -> str:
    duplicate_group_id = payload.get("duplicate_group_id")
    if duplicate_group_id:
        return f"duplicate_group:{duplicate_group_id}"
    paper_id = payload.get("paper_id")
    if paper_id:
        return f"paper:{paper_id}"
    professor_id = payload.get("professor_id")
    if professor_id:
        return f"professor:{professor_id}"
    return ""


def _payload_target_key(payload: dict[str, Any]) -> str:
    duplicate_group_id = payload.get("duplicate_group_id")
    if duplicate_group_id:
        return f"duplicate_group:{duplicate_group_id}"
    paper_ids = payload.get("paper_ids")
    if isinstance(paper_ids, list) and len(paper_ids) == 1:
        return f"paper:{paper_ids[0]}"
    professor_id = payload.get("professor_id")
    if professor_id:
        return f"professor:{professor_id}"
    return ""


def _selection_hash(
    *,
    bucket_limit: int,
    lanes: Sequence[CandidateLaneName],
    summaries: Sequence[LaneCandidateGenerationSummary],
) -> str:
    payload = {
        "bucket_limit": bucket_limit,
        "lanes": list(lanes),
        "summaries": [asdict(summary) for summary in summaries],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _closure_selection_hash(
    *,
    buckets: DatasetClosureBuckets,
    lanes: Sequence[CandidateLaneName],
) -> str:
    from .dataset_quality_closure import build_lane_dry_run_report

    return build_lane_dry_run_report(buckets, lanes=lanes).selection_hash


def _unique_sorted(values: Any) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if value}))


def _build_deterministic_profile_summary(profile_input: ProfileSummaryInput) -> str:
    sentences: list[str] = [_ensure_sentence(profile_input.identity_line)]
    research_values = _fact_values(profile_input, "research_topic")
    if research_values:
        sentences.append(
            _ensure_sentence(f"研究方向包括{'、'.join(research_values[:4])}")
        )
    fact_sentences = extract_profile_fact_sentences(
        profile_input.profile_raw_text,
        max_sentences=3,
    )
    for sentence in fact_sentences:
        if sentence not in sentences:
            sentences.append(sentence)
    if profile_input.paper_summary:
        sentences.append(_ensure_sentence(_trim_text(profile_input.paper_summary, 110)))
    elif profile_input.linked_output_titles:
        titles = "、".join(profile_input.linked_output_titles[:2])
        sentences.append(_ensure_sentence(f"已验证论文包括{_trim_text(titles, 90)}"))
    education_values = _fact_values(profile_input, "education")
    if education_values:
        sentences.append(_ensure_sentence(f"教育背景包括{'、'.join(education_values[:2])}"))
    award_values = [
        *_fact_values(profile_input, "award"),
        *_fact_values(profile_input, "honor"),
    ]
    if award_values:
        sentences.append(_ensure_sentence(f"代表性荣誉包括{'、'.join(award_values[:2])}"))

    summary = "".join(_dedupe_preserve_order(sentences))
    return _coerce_text_length(summary, min_length=200, max_length=300)


def _filter_eligible_paper_summary_inputs(
    paper_inputs: Sequence[PaperSummaryInput],
) -> tuple[tuple[PaperSummaryInput, ...], dict[str, str]]:
    eligible: list[PaperSummaryInput] = []
    excluded: dict[str, str] = {}
    seen: set[str] = set()
    for paper in paper_inputs:
        paper_id = _clean_text(paper.paper_id)
        if not paper_id or paper_id in seen:
            continue
        seen.add(paper_id)
        if paper.link_status != "verified":
            excluded[paper_id] = "unverified_professor_paper_link"
            continue
        if _is_provider_only_author_search(paper):
            excluded[paper_id] = "provider_only_author_search"
            continue
        if not _clean_text(paper.title):
            excluded[paper_id] = "missing_paper_title"
            continue
        eligible.append(paper)
    return tuple(eligible), excluded


def _build_deterministic_paper_summary(
    generation_input: ProfessorPaperSummaryGenerationInput,
) -> str:
    paper_fragments: list[str] = []
    for paper in generation_input.eligible_papers[:5]:
        evidence = (
            _optional_clean_text(paper.summary_zh)
            or _optional_clean_text(paper.abstract_clean)
            or _optional_clean_text(paper.title)
        )
        if evidence:
            paper_fragments.append(_trim_text(evidence, 80))
    if not paper_fragments:
        return ""
    summary = (
        f"{generation_input.professor_name}的已验证论文围绕"
        f"{'、'.join(paper_fragments[:3])}展开。"
        "这些论文来自教师种子链路中的已验证论文记录，可用于支撑教师产出摘要。"
    )
    return _coerce_text_length(summary, min_length=20, max_length=500)


def _is_provider_only_author_search(paper: PaperSummaryInput) -> bool:
    canonical_source = _clean_text(paper.canonical_source).casefold()
    match_reason = _clean_text(paper.match_reason).casefold()
    if canonical_source in {
        "provider_only_author_search",
        "openalex_author_search",
        "semantic_scholar_author_search",
    }:
        return True
    return "author search" in match_reason and "official" not in match_reason


def _identifier_merge_candidate(
    *,
    professor_id: str,
    duplicate_group_id: str,
    papers: tuple[DuplicatePaperRecord, ...],
    identity_getter: Callable[[DuplicatePaperRecord], str | None],
    evidence_type: DuplicateMergeEvidenceType,
    confidence: float,
) -> DuplicatePaperMergeCandidate | None:
    identities = {identity for paper in papers if (identity := identity_getter(paper))}
    if len(identities) != 1:
        return None
    return _merge_candidate_from_papers(
        professor_id=professor_id,
        duplicate_group_id=duplicate_group_id,
        papers=papers,
        evidence_type=evidence_type,
        confidence=confidence,
    )


def _merge_candidate_from_papers(
    *,
    professor_id: str,
    duplicate_group_id: str,
    papers: tuple[DuplicatePaperRecord, ...],
    evidence_type: DuplicateMergeEvidenceType,
    confidence: float,
) -> DuplicatePaperMergeCandidate:
    canonical = _choose_canonical_paper(papers)
    paper_ids = tuple(sorted(paper.paper_id for paper in papers))
    old_paper_ids = tuple(paper_id for paper_id in paper_ids if paper_id != canonical.paper_id)
    return DuplicatePaperMergeCandidate(
        professor_id=_clean_text(professor_id),
        duplicate_group_id=_clean_text(duplicate_group_id),
        canonical_paper_id=canonical.paper_id,
        old_paper_ids=old_paper_ids,
        paper_ids=paper_ids,
        evidence_type=evidence_type,
        confidence=confidence,
        merge_reason=f"dataset_candidate_generation:{evidence_type}",
        source_page_ids=_unique_sorted(
            source_page_id
            for paper in papers
            for source_page_id in paper.source_page_ids
        ),
    )


def _choose_canonical_paper(
    papers: tuple[DuplicatePaperRecord, ...],
) -> DuplicatePaperRecord:
    return sorted(
        papers,
        key=lambda paper: (-_paper_richness_score(paper), paper.paper_id),
    )[0]


def _paper_richness_score(paper: DuplicatePaperRecord) -> int:
    score = 0
    if _clean_text(paper.canonical_source) != "prof_page_only":
        score += 100
    if _optional_clean_text(paper.summary_zh):
        score += 25
    if _optional_clean_text(paper.abstract_clean):
        score += 20
    if _optional_clean_text(paper.doi):
        score += 10
    if _optional_clean_text(paper.arxiv_id):
        score += 10
    if paper.citation_count is not None:
        score += min(max(int(paper.citation_count), 0), 50)
    return score


def _has_source_supported_identity(
    papers: tuple[DuplicatePaperRecord, ...],
) -> bool:
    title_keys = {_paper_title_key(paper.title) for paper in papers}
    years = {paper.year for paper in papers}
    venues = {_paper_title_key(paper.venue or "") for paper in papers if paper.venue}
    has_source_page = any(paper.source_page_ids for paper in papers)
    has_enriched_row = any(
        _clean_text(paper.canonical_source) != "prof_page_only" for paper in papers
    )
    if len(title_keys) != 1 or len(years) != 1 or len(venues) != 1:
        return False
    if not has_source_page or not has_enriched_row:
        return False
    author_sets = [_author_tokens(paper.authors_display or "") for paper in papers]
    if any(not author_set for author_set in author_sets):
        return False
    common_authors = set.intersection(*author_sets)
    return bool(common_authors)


def _paper_title_key(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", _clean_text(text).casefold())


def _author_tokens(authors_display: str) -> set[str]:
    tokens: set[str] = set()
    for raw_token in re.split(r"[,;，；]\s*|\s+and\s+", authors_display.casefold()):
        token = _clean_text(raw_token)
        if token:
            tokens.add(token)
    return tokens


def _normalized_doi(paper: DuplicatePaperRecord) -> str | None:
    value = _clean_text(paper.doi).casefold()
    if not value:
        return None
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return value or None


def _normalized_arxiv_id(paper: DuplicatePaperRecord) -> str | None:
    value = _clean_text(paper.arxiv_id).casefold()
    if not value:
        return None
    value = value.removeprefix("arxiv:")
    value = value.removeprefix("https://arxiv.org/abs/")
    return value or None


def _fact_values(profile_input: ProfileSummaryInput, fact_type: str) -> list[str]:
    return _dedupe_preserve_order(
        [
            _trim_text(_clean_text(fact.value), 48)
            for fact in profile_input.facts
            if fact.fact_type == fact_type and _clean_text(fact.value)
        ]
    )


def _coerce_text_length(text: str, *, min_length: int, max_length: int) -> str:
    normalized = _clean_text(text)
    if len(normalized) <= max_length:
        return normalized
    cut_at = max(
        normalized.rfind(marker, min_length - 1, max_length + 1)
        for marker in ("。", "！", "？")
    )
    if min_length <= cut_at + 1 <= max_length:
        return normalized[: cut_at + 1].strip()
    return normalized[:max_length].strip()


def _trim_text(text: str, max_length: int) -> str:
    normalized = _clean_text(text)
    if len(normalized) <= max_length:
        return normalized
    trimmed = normalized[:max_length].rstrip("，、；;：: ")
    return trimmed


def _ensure_sentence(text: str) -> str:
    normalized = _clean_text(text)
    if not normalized:
        return ""
    if normalized.endswith(("。", "！", "？", "!", "?")):
        return normalized
    return f"{normalized}。"


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _clean_text(value)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _detect_language(text: str) -> Literal["zh", "en"]:
    return "zh" if len(_CHINESE_RE.findall(text)) >= 4 else "en"


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError):
        return row[index]


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ()
    text = str(value).strip()
    return (text,) if text else ()


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _optional_clean_text(value: object) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value)).strip()
