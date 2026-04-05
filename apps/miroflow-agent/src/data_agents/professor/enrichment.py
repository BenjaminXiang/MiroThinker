from __future__ import annotations

from collections.abc import Callable

from .models import (
    DiscoveredProfessorSeed,
    ExtractedProfessorProfile,
    MergedProfessorProfileRecord,
)
from .name_selection import select_canonical_name
from .profile import extract_professor_profile


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.replace("\u3000", " ").split()).strip()
    return normalized or None


def build_profile_record(
    roster_seed: DiscoveredProfessorSeed,
    extracted: ExtractedProfessorProfile | None,
    extraction_status: str,
    skip_reason: str | None,
    error: str | None = None,
) -> MergedProfessorProfileRecord:
    name = select_canonical_name(
        roster_name=roster_seed.name,
        extracted_name=extracted.name if extracted else None,
    )
    institution = normalize_text(extracted.institution if extracted else None) or normalize_text(
        roster_seed.institution
    )
    department = normalize_text(extracted.department if extracted else None) or normalize_text(
        roster_seed.department
    )
    title = normalize_text(extracted.title if extracted else None)
    email = normalize_text(extracted.email if extracted else None)
    office = normalize_text(extracted.office if extracted else None)
    homepage = normalize_text(extracted.homepage_url if extracted else None)
    research_directions = list(extracted.research_directions) if extracted else []
    source_urls = list(extracted.source_urls) if extracted else []
    if roster_seed.source_url not in source_urls:
        source_urls.append(roster_seed.source_url)
    if roster_seed.profile_url not in source_urls:
        source_urls.append(roster_seed.profile_url)

    source_urls_tuple = tuple(source_urls)
    evidence_tuple = tuple(source_urls)
    research_directions_tuple = tuple(research_directions)

    return MergedProfessorProfileRecord(
        name=name,
        institution=institution,
        department=department,
        title=title,
        email=email,
        office=office,
        homepage=homepage,
        profile_url=roster_seed.profile_url,
        source_urls=source_urls_tuple,
        evidence=evidence_tuple,
        research_directions=research_directions_tuple,
        extraction_status=extraction_status,
        skip_reason=skip_reason,
        error=error,
        roster_source=roster_seed.source_url,
    )


def is_structured_profile(profile: ExtractedProfessorProfile) -> bool:
    informative_fields = [
        normalize_text(profile.title),
        normalize_text(profile.email),
        normalize_text(profile.office),
    ]
    homepage = normalize_text(profile.homepage_url)
    if homepage and homepage != normalize_text(profile.profile_url):
        informative_fields.append(homepage)
    if profile.research_directions:
        informative_fields.append("research")
    return any(field for field in informative_fields)


def extract_profile_record(
    roster_seed: DiscoveredProfessorSeed,
    timeout: float,
    fetch_html: Callable[[str, float], str],
    profile_extractor: Callable[
        [str, str, str | None, str | None], ExtractedProfessorProfile
    ] = extract_professor_profile,
) -> tuple[ExtractedProfessorProfile | None, str | None]:
    try:
        html = fetch_html(roster_seed.profile_url, timeout)
        extracted = profile_extractor(
            html,
            roster_seed.profile_url,
            roster_seed.institution,
            roster_seed.department,
        )
    except Exception as exc:  # noqa: BLE001 - keep report resilient during e2e.
        return None, f"{type(exc).__name__}: {exc}"
    return extracted, None
