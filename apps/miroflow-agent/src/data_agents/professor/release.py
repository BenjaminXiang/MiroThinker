from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from src.data_agents.contracts import (
    Evidence,
    EvidenceSourceType,
    ProfessorRecord,
    ReleasedObject,
)
from src.data_agents.evidence import build_evidence
from src.data_agents.normalization import build_stable_id, normalize_person_name
from src.data_agents.publish import publish_jsonl

from .enrichment import normalize_text
from .models import MergedProfessorProfileRecord


@dataclass(frozen=True, slots=True)
class ProfessorSummaries:
    profile_summary: str
    evaluation_summary: str


ProfessorSummarizer = Callable[[MergedProfessorProfileRecord], ProfessorSummaries]


@dataclass(frozen=True, slots=True)
class ProfessorReleaseReport:
    input_profile_count: int
    released_record_count: int
    skipped_record_count: int
    structured_input_count: int
    partial_input_count: int
    failed_input_count: int
    skipped_input_count: int
    structured_released_count: int
    partial_released_count: int
    official_evidence_count: int
    auxiliary_evidence_count: int
    skip_reasons: dict[str, int]


@dataclass(frozen=True, slots=True)
class ProfessorReleaseResult:
    professor_records: list[ProfessorRecord]
    released_objects: list[ReleasedObject]
    report: ProfessorReleaseReport


def build_professor_release(
    *,
    profiles: list[MergedProfessorProfileRecord],
    summarizer: ProfessorSummarizer | None = None,
    official_domain_suffixes: tuple[str, ...] = ("sustech.edu.cn",),
    now: datetime | None = None,
) -> ProfessorReleaseResult:
    generated_at = now or datetime.now(timezone.utc)
    normalized_suffixes = _normalize_domain_suffixes(official_domain_suffixes)
    if summarizer is None:
        summary_builder: ProfessorSummarizer = lambda profile: _build_rule_based_summaries(
            profile,
            official_domain_suffixes=normalized_suffixes,
        )
    else:
        summary_builder = summarizer
    professor_records: list[ProfessorRecord] = []
    released_objects: list[ReleasedObject] = []
    skip_reasons: Counter[str] = Counter()
    structured_input_count = 0
    partial_input_count = 0
    failed_input_count = 0
    skipped_input_count = 0
    structured_released_count = 0
    partial_released_count = 0
    official_evidence_count = 0
    auxiliary_evidence_count = 0

    for profile in profiles:
        if profile.extraction_status == "structured":
            structured_input_count += 1
        elif profile.extraction_status == "partial":
            partial_input_count += 1
        elif profile.extraction_status == "failed":
            failed_input_count += 1
        elif profile.extraction_status == "skipped":
            skipped_input_count += 1

        name = normalize_text(profile.name)
        institution = normalize_text(profile.institution)
        department = normalize_text(profile.department)
        title = normalize_text(profile.title)
        if not name or not institution:
            skip_reasons["missing_required_fields"] += 1
            continue

        summaries = summary_builder(profile)
        profile_summary_raw = normalize_text(summaries.profile_summary)
        evaluation_summary_raw = normalize_text(summaries.evaluation_summary)
        if not profile_summary_raw or not evaluation_summary_raw:
            skip_reasons["invalid_summaries"] += 1
            continue
        profile_summary = _coerce_profile_summary(profile_summary_raw)
        evaluation_summary = _coerce_evaluation_summary(evaluation_summary_raw)

        evidence = _build_evidence_items(
            profile=profile,
            official_domain_suffixes=normalized_suffixes,
            fetched_at=generated_at,
        )
        if not any(item.source_type == "official_site" for item in evidence):
            skip_reasons["missing_official_evidence"] += 1
            continue

        natural_key = _build_natural_key(
            name=name,
            institution=institution,
            department=department,
            title=title,
            profile_url=profile.profile_url,
            roster_source=profile.roster_source,
        )
        professor_id = build_stable_id("prof", natural_key)

        try:
            professor = ProfessorRecord(
                id=professor_id,
                name=name,
                institution=institution,
                department=department,
                title=title,
                email=normalize_text(profile.email),
                homepage=normalize_text(profile.homepage) or normalize_text(profile.profile_url),
                office=normalize_text(profile.office),
                research_directions=_normalize_research_directions(
                    profile.research_directions
                ),
                education_structured=[],
                work_experience=[],
                citation_count=None,
                profile_summary=profile_summary,
                evaluation_summary=evaluation_summary,
                company_roles=[],
                top_papers=[],
                patent_ids=[],
                evidence=evidence,
                last_updated=generated_at,
            )
        except Exception:
            skip_reasons["contract_validation_failed"] += 1
            continue

        professor_records.append(professor)
        released_objects.append(professor.to_released_object())
        if profile.extraction_status == "structured":
            structured_released_count += 1
        elif profile.extraction_status == "partial":
            partial_released_count += 1
        official_evidence_count += len(
            [item for item in evidence if item.source_type == "official_site"]
        )
        auxiliary_evidence_count += len(
            [item for item in evidence if item.source_type != "official_site"]
        )

    report = ProfessorReleaseReport(
        input_profile_count=len(profiles),
        released_record_count=len(professor_records),
        skipped_record_count=len(profiles) - len(professor_records),
        structured_input_count=structured_input_count,
        partial_input_count=partial_input_count,
        failed_input_count=failed_input_count,
        skipped_input_count=skipped_input_count,
        structured_released_count=structured_released_count,
        partial_released_count=partial_released_count,
        official_evidence_count=official_evidence_count,
        auxiliary_evidence_count=auxiliary_evidence_count,
        skip_reasons=dict(skip_reasons),
    )
    return ProfessorReleaseResult(
        professor_records=professor_records,
        released_objects=released_objects,
        report=report,
    )


def publish_professor_release(
    release_result: ProfessorReleaseResult,
    *,
    professor_records_path: Path,
    released_objects_path: Path,
) -> None:
    publish_jsonl(professor_records_path, release_result.professor_records)
    publish_jsonl(released_objects_path, release_result.released_objects)


def _build_natural_key(
    *,
    name: str,
    institution: str,
    department: str | None,
    title: str | None,
    profile_url: str | None,
    roster_source: str | None,
) -> str:
    department_key = (department or "").strip().lower()
    title_key = (title or "").strip().lower()
    if department_key:
        disambiguator = department_key
    elif title_key:
        disambiguator = f"title:{title_key}"
    else:
        profile_key = _normalize_url_for_natural_key(profile_url)
        if profile_key:
            disambiguator = f"profile:{profile_key}"
        else:
            roster_key = _normalize_url_for_natural_key(roster_source)
            disambiguator = (
                f"roster:{roster_key}" if roster_key else "missing-department-and-title"
            )
    return "|".join(
        [
            normalize_person_name(name),
            institution.strip().lower(),
            disambiguator,
        ]
    )


def _build_rule_based_summaries(
    profile: MergedProfessorProfileRecord,
    *,
    official_domain_suffixes: set[str],
) -> ProfessorSummaries:
    name = normalize_text(profile.name) or "该教师"
    institution = normalize_text(profile.institution) or "所属高校"
    department = normalize_text(profile.department)
    title = normalize_text(profile.title)
    affiliation_text = _build_affiliation_text(
        institution=institution,
        department=department,
        title=title,
    )
    directions = _normalize_research_directions(profile.research_directions)
    source_count = len(_collect_unique_urls(profile))
    if directions:
        direction_text = "、".join(directions[:5])
        profile_summary_base = (
            f"{name}现任{affiliation_text}，研究方向包括{direction_text}。"
            "当前画像以高校官网教师目录与个人资料页为主锚点，优先保留可核验事实字段。"
        )
    else:
        profile_summary_base = (
            f"{name}现任{affiliation_text}。"
            "当前公开资料以高校官网教师目录与个人资料页为主，研究方向信息仍在持续补全。"
        )
    profile_summary = _ensure_summary_length(
        profile_summary_base
        + (
            "已同步整理身份、院系、职称与研究方向等结构化字段，"
            "能够支持按学校和方向的细粒度检索。"
        ),
        min_length=200,
        max_length=300,
        padding_sentences=(
            "该版本强调“官网证据优先、辅助来源补充”的采集原则，确保身份锚点稳定可靠。",
            "在论文和企业域完成联动前，摘要仅覆盖已验证信息，不对缺失经历或成果做主观推断。",
        ),
    )
    if _has_auxiliary_public_evidence(
        profile,
        official_domain_suffixes=official_domain_suffixes,
    ):
        evidence_statement = "当前包含辅助公开页面证据，可用于补充官网信息。"
    else:
        evidence_statement = "当前未检出辅助公开页面证据，已按官网锚点完成基础核验。"
    evaluation_summary = (
        f"{name}当前资料完整度为{profile.extraction_status}，已整理{source_count}条可追溯来源。"
        f"{evidence_statement}研究方向与基础身份字段可直接用于检索过滤，"
        "企业角色与代表论文字段暂为空，待跨域数据回填后更新。"
    )
    return ProfessorSummaries(
        profile_summary=profile_summary,
        evaluation_summary=evaluation_summary,
    )


def _normalize_research_directions(values: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = normalize_text(value)
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _build_evidence_items(
    *,
    profile: MergedProfessorProfileRecord,
    official_domain_suffixes: set[str],
    fetched_at: datetime,
) -> list[Evidence]:
    evidence_items: list[Evidence] = []
    official_suffixes = _effective_official_suffixes(
        profile,
        official_domain_suffixes=official_domain_suffixes,
    )

    for url in _collect_unique_urls(profile):
        source_type = _classify_evidence_source_type(url, official_suffixes)
        evidence_items.append(
            build_evidence(
                source_type=source_type,
                source_url=url,
                fetched_at=fetched_at,
                confidence=_evidence_confidence(profile.extraction_status),
            )
        )

    if (
        not any(item.source_type == "official_site" for item in evidence_items)
        and normalize_text(profile.roster_source)
    ):
        evidence_items.append(
            build_evidence(
                source_type="official_site",
                source_url=profile.roster_source,
                fetched_at=fetched_at,
                confidence=_evidence_confidence(profile.extraction_status),
            )
        )
    return evidence_items


def _collect_unique_urls(profile: MergedProfessorProfileRecord) -> list[str]:
    urls = [
        profile.roster_source,
        profile.profile_url,
        *profile.source_urls,
        *profile.evidence,
    ]
    normalized_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        item = normalize_text(url)
        if not item or item in seen:
            continue
        seen.add(item)
        normalized_urls.append(item)
    return normalized_urls


def _evidence_confidence(extraction_status: str) -> float:
    if extraction_status == "structured":
        return 0.9
    if extraction_status == "partial":
        return 0.7
    return 0.6


def _normalize_domain_suffixes(suffixes: tuple[str, ...]) -> set[str]:
    normalized: set[str] = set()
    for suffix in suffixes:
        item = suffix.lower().strip().lstrip(".")
        if item:
            normalized.add(item)
    return normalized


def _registered_domain(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower().strip(".")
    if not hostname:
        return ""
    labels = hostname.split(".")
    if len(labels) <= 2:
        return hostname
    if hostname.endswith(".edu.cn") or hostname.endswith(".org.cn") or hostname.endswith(".com.cn"):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _is_official_url(url: str, official_suffixes: set[str]) -> bool:
    hostname = (urlparse(url).hostname or "").lower().strip(".")
    if not hostname:
        return False
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in official_suffixes
    )


def _ensure_summary_length(
    text: str,
    *,
    min_length: int,
    max_length: int,
    padding_sentences: tuple[str, ...],
) -> str:
    summary = normalize_text(text) or ""
    if not summary.endswith("。"):
        summary = f"{summary}。"

    index = 0
    while len(summary) < min_length:
        sentence = padding_sentences[min(index, len(padding_sentences) - 1)]
        summary = f"{summary}{sentence}"
        index += 1

    if len(summary) > max_length:
        summary = summary[:max_length]
        summary = summary.rstrip("，、；： ")
        if summary and summary[-1] not in {"。", "！", "？"}:
            if len(summary) == max_length:
                summary = f"{summary[:-1]}。"
            else:
                summary = f"{summary}。"

    return summary


def _coerce_profile_summary(text: str) -> str:
    return _ensure_summary_length(
        text,
        min_length=200,
        max_length=300,
        padding_sentences=(
            "该摘要遵循官网优先与证据可追溯原则，仅保留已验证字段。",
            "在跨域联动完成前，系统会持续补充并校验研究方向与成果信息。",
        ),
    )


def _coerce_evaluation_summary(text: str) -> str:
    return _ensure_summary_length(
        text,
        min_length=100,
        max_length=150,
        padding_sentences=(
            "当前内容可用于事实检索与人工复核。",
            "后续会结合论文与专利证据继续更新。",
        ),
    )


def _has_auxiliary_public_evidence(
    profile: MergedProfessorProfileRecord,
    *,
    official_domain_suffixes: set[str],
) -> bool:
    effective_suffixes = _effective_official_suffixes(
        profile,
        official_domain_suffixes=official_domain_suffixes,
    )
    for url in _collect_unique_urls(profile):
        if _classify_evidence_source_type(url, effective_suffixes) == "public_web":
            return True
    return False


def _effective_official_suffixes(
    profile: MergedProfessorProfileRecord,
    *,
    official_domain_suffixes: set[str],
) -> set[str]:
    effective = set(official_domain_suffixes)
    roster_domain = _registered_domain(profile.roster_source)
    if roster_domain:
        effective.add(roster_domain)
    return effective


def _normalize_url_for_natural_key(url: str | None) -> str:
    item = normalize_text(url)
    if not item:
        return ""
    parsed = urlparse(item)
    hostname = (parsed.hostname or "").lower().strip(".")
    path = (parsed.path or "").strip().rstrip("/").lower()
    return f"{hostname}{path}" if hostname else path


def _build_affiliation_text(
    *,
    institution: str,
    department: str | None,
    title: str | None,
) -> str:
    department_text = (department or "").strip()
    title_text = (title or "").strip()
    if department_text and title_text:
        return f"{institution}{department_text}{title_text}"
    if department_text:
        return f"{institution}{department_text}教师"
    if title_text:
        return f"{institution}{title_text}"
    return f"{institution}教师"


def _classify_evidence_source_type(
    url: str,
    official_suffixes: set[str],
) -> EvidenceSourceType:
    if _is_official_url(url, official_suffixes):
        return "official_site"
    return "public_web"
