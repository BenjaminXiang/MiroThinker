from __future__ import annotations

from datetime import datetime
from typing import Iterable
from urllib.parse import urlparse

from src.data_agents.contracts import Evidence, ProfessorRecord, normalize_quality_status
from src.data_agents.normalization import build_stable_id, normalize_person_name

from .models import EnrichedProfessorProfile
from .name_selection import is_obvious_non_person_name
from .quality_gate import evaluate_quality

DEFAULT_OFFICIAL_DOMAIN_SUFFIXES = (
    "sustech.edu.cn",
    "szu.edu.cn",
    "tsinghua.edu.cn",
    "sigs.tsinghua.edu.cn",
    "pkusz.edu.cn",
    "pku.edu.cn",
    "hitsz.edu.cn",
    "hit.edu.cn",
    "cuhk.edu.cn",
    "siat.ac.cn",
    "suat-sz.edu.cn",
    "sysu.edu.cn",
    "sztu.edu.cn",
)


def _normalize_domain_suffixes(
    domain_suffixes: Iterable[str],
) -> tuple[str, ...]:
    return tuple(
        suffix.strip().lower().strip(".")
        for suffix in domain_suffixes
        if suffix and suffix.strip()
    )


def is_official_url(
    url: str,
    *,
    official_domain_suffixes: Iterable[str] = DEFAULT_OFFICIAL_DOMAIN_SUFFIXES,
) -> bool:
    hostname = (urlparse(url).hostname or "").lower().strip(".")
    if not hostname:
        return False
    suffixes = _normalize_domain_suffixes(official_domain_suffixes)
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in suffixes
    )


def build_evidence(
    urls: list[str],
    fetched_at: datetime,
    *,
    official_domain_suffixes: Iterable[str] = DEFAULT_OFFICIAL_DOMAIN_SUFFIXES,
) -> list[Evidence]:
    seen: set[str] = set()
    evidence: list[Evidence] = []
    for url in urls:
        url = url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        source_type = (
            "official_site"
            if is_official_url(url, official_domain_suffixes=official_domain_suffixes)
            else "public_web"
        )
        evidence.append(
            Evidence(
                source_type=source_type,
                source_url=url,
                fetched_at=fetched_at,
                confidence=0.8,
            )
        )
    return evidence


def build_professor_natural_key(profile: EnrichedProfessorProfile) -> str:
    name = normalize_person_name(profile.name)
    institution = profile.institution.strip().lower()
    if profile.department:
        disambiguator = profile.department.strip().lower()
    elif profile.title:
        disambiguator = f"title:{profile.title.strip().lower()}"
    elif profile.profile_url:
        parsed = urlparse(profile.profile_url)
        hostname = (parsed.hostname or "").lower().strip(".")
        path = (parsed.path or "").strip().rstrip("/").lower()
        disambiguator = f"profile:{hostname}{path}"
    else:
        disambiguator = "missing-department-and-title"
    return f"{name}|{institution}|{disambiguator}"


def build_professor_id(profile: EnrichedProfessorProfile) -> str:
    return build_stable_id("PROF", build_professor_natural_key(profile))


def build_professor_record_from_enriched(
    profile: EnrichedProfessorProfile,
    now: datetime,
    *,
    official_domain_suffixes: Iterable[str] = DEFAULT_OFFICIAL_DOMAIN_SUFFIXES,
    quality_status: str | None = None,
    require_l1: bool = True,
) -> ProfessorRecord | None:
    """Convert an enriched profile into the shared ProfessorRecord contract."""
    name = profile.name.strip()
    institution = profile.institution.strip()
    if not name or not institution:
        return None
    if is_obvious_non_person_name(name):
        return None

    all_urls = list(profile.evidence_urls)
    if profile.profile_url and profile.profile_url not in all_urls:
        all_urls.insert(0, profile.profile_url)
    if profile.roster_source and profile.roster_source not in all_urls:
        all_urls.append(profile.roster_source)
    evidence = build_evidence(
        all_urls,
        now,
        official_domain_suffixes=official_domain_suffixes,
    )
    if not any(item.source_type == "official_site" for item in evidence):
        return None

    if quality_status is None:
        quality = evaluate_quality(profile)
        if require_l1 and not quality.passed_l1:
            return None
        effective_quality_status = quality.quality_status
    else:
        effective_quality_status = normalize_quality_status(quality_status)

    profile_summary = profile.profile_summary.strip()
    evaluation_summary = profile.evaluation_summary.strip()
    if not profile_summary:
        return None

    try:
        return ProfessorRecord(
            id=build_professor_id(profile),
            name=name,
            institution=institution,
            department=profile.department,
            title=profile.title,
            email=profile.email,
            homepage=profile.homepage or profile.profile_url,
            office=profile.office,
            research_directions=[
                direction.strip()
                for direction in profile.research_directions
                if direction.strip()
            ],
            education_structured=[
                item.model_dump(mode="json")
                for item in profile.education_structured
            ],
            work_experience=[
                formatted
                for item in profile.work_experience
                if (formatted := _format_work_entry(item))
            ],
            h_index=profile.h_index,
            citation_count=profile.citation_count,
            paper_count=profile.paper_count,
            awards=profile.awards or [],
            academic_positions=profile.academic_positions or [],
            projects=profile.projects or [],
            profile_summary=profile_summary,
            evaluation_summary=evaluation_summary,
            company_roles=[
                {
                    "company_name": role.company_name,
                    "role": role.role,
                }
                for role in profile.company_roles
            ],
            patent_ids=[
                item.patent_id.strip()
                for item in profile.patent_ids
                if item.patent_id and item.patent_id.strip()
            ],
            evidence=evidence,
            last_updated=now,
            quality_status=normalize_quality_status(effective_quality_status),
        )
    except Exception:
        return None


def _format_work_entry(item: object) -> str | None:
    if hasattr(item, "organization"):
        organization = getattr(item, "organization", None)
        role = getattr(item, "role", None)
        start_year = getattr(item, "start_year", None)
        end_year = getattr(item, "end_year", None)
    elif isinstance(item, dict):
        organization = item.get("organization")
        role = item.get("role")
        start_year = item.get("start_year")
        end_year = item.get("end_year")
    else:
        return str(item).strip() or None

    parts = []
    if start_year or end_year:
        parts.append(f"{start_year or '未知'}-{end_year or '至今'}")
    if organization:
        parts.append(str(organization).strip())
    if role:
        parts.append(str(role).strip())
    formatted = " ".join(part for part in parts if part)
    return formatted or None
