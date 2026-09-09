from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import threading
from urllib.parse import urljoin, urlparse
from weakref import WeakKeyDictionary

from bs4 import BeautifulSoup

from .name_selection import is_same_person_name_variant
from .models import (
    DiscoveredProfessorSeed,
    ExtractedProfessorProfile,
    MergedProfessorProfileRecord,
)
from .name_selection import select_canonical_name
from .profile import extract_professor_profile
from .roster import extract_szu_csse_roster_card_profile

_SZU_CSSE_BIGDATA_TEAM_URL = "https://bigdata.szu.edu.cn/kytd.htm"
_SZU_CSSE_FETCH_CACHE_LOCK = threading.Lock()
_SZU_CSSE_FETCH_CACHE_BY_FETCHER: WeakKeyDictionary[
    Callable[[str, float], str],
    dict[tuple[str, float], str],
] = WeakKeyDictionary()


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
    extracted_name = extracted.name if extracted else None
    if _has_synthetic_profile_fragment(roster_seed.profile_url):
        name = normalize_text(roster_seed.name)
    else:
        name = select_canonical_name(
            roster_name=roster_seed.name,
            extracted_name=extracted_name,
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
    education_structured = list(extracted.education_structured) if extracted else []
    work_experience = list(extracted.work_experience) if extracted else []
    awards = list(extracted.awards) if extracted else []
    academic_positions = list(extracted.academic_positions) if extracted else []
    profile_raw_text = normalize_text(extracted.profile_raw_text if extracted else None)
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
        profile_raw_text=profile_raw_text,
        education_structured=tuple(education_structured),
        work_experience=tuple(work_experience),
        awards=tuple(awards),
        academic_positions=tuple(academic_positions),
    )


def _has_synthetic_profile_fragment(url: str) -> bool:
    return urlparse(url).fragment.startswith("prof-")


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
    if profile.education_structured:
        informative_fields.append("education")
    if profile.work_experience:
        informative_fields.append("work")
    if profile.awards:
        informative_fields.append("awards")
    if profile.academic_positions:
        informative_fields.append("academic_positions")
    if normalize_text(profile.profile_raw_text):
        informative_fields.append("profile_raw_text")
    return any(field for field in informative_fields)


def extract_profile_record(
    roster_seed: DiscoveredProfessorSeed,
    timeout: float,
    fetch_html: Callable[[str, float], str],
    profile_extractor: Callable[
        [str, str, str | None, str | None], ExtractedProfessorProfile
    ] = extract_professor_profile,
) -> tuple[ExtractedProfessorProfile | None, str | None]:
    fallback = _extract_profile_from_roster_card(
        roster_seed,
        timeout=timeout,
        fetch_html=fetch_html,
    )
    if fallback is not None:
        return fallback, None

    try:
        html = fetch_html(roster_seed.profile_url, timeout)
        extracted = profile_extractor(
            html,
            roster_seed.profile_url,
            roster_seed.institution,
            roster_seed.department,
        )
        extracted = _augment_sigs_structured_fields(
            extracted,
            html=html,
            source_url=roster_seed.profile_url,
        )
    except Exception as exc:  # noqa: BLE001 - keep report resilient during e2e.
        original_error = f"{type(exc).__name__}: {exc}"
        fallback = _extract_profile_from_roster_card(
            roster_seed,
            timeout=timeout,
            fetch_html=fetch_html,
        )
        if fallback is not None:
            return fallback, None
        return None, original_error
    return extracted, None


def _extract_profile_from_roster_card(
    roster_seed: DiscoveredProfessorSeed,
    *,
    timeout: float,
    fetch_html: Callable[[str, float], str],
) -> ExtractedProfessorProfile | None:
    if not _is_szu_csse_profile_seed(roster_seed):
        return None
    try:
        roster_html = _fetch_szu_csse_cached_html(
            roster_seed.source_url,
            timeout=timeout,
            fetch_html=fetch_html,
        )
    except Exception:  # noqa: BLE001 - original detail error remains authoritative.
        return None
    card_profile = extract_szu_csse_roster_card_profile(roster_html, roster_seed)
    if card_profile is None:
        return None
    return (
        _supplement_szu_csse_profile_from_bigdata(
            card_profile,
            roster_seed=roster_seed,
            timeout=timeout,
            fetch_html=fetch_html,
        )
        or card_profile
    )


def _is_szu_csse_profile_seed(roster_seed: DiscoveredProfessorSeed) -> bool:
    return (
        urlparse(roster_seed.profile_url).hostname == "csse.szu.edu.cn"
        and urlparse(roster_seed.profile_url).path.rstrip("/").lower()
        == "/pages/user/index"
        and urlparse(roster_seed.source_url).hostname == "csse.szu.edu.cn"
    )


def _supplement_szu_csse_profile_from_bigdata(
    card_profile: ExtractedProfessorProfile,
    *,
    roster_seed: DiscoveredProfessorSeed,
    timeout: float,
    fetch_html: Callable[[str, float], str],
) -> ExtractedProfessorProfile | None:
    try:
        index_html = _fetch_szu_csse_cached_html(
            _SZU_CSSE_BIGDATA_TEAM_URL,
            timeout=timeout,
            fetch_html=fetch_html,
        )
        supplemental_url = _szu_csse_bigdata_profile_url_for_name(
            index_html,
            roster_seed.name,
        )
        if supplemental_url is None:
            return None
        detail_html = _fetch_szu_csse_cached_html(
            supplemental_url,
            timeout=timeout,
            fetch_html=fetch_html,
        )
    except Exception:  # noqa: BLE001 - sparse official CSSE card remains usable.
        return None

    supplemental = extract_professor_profile(
        detail_html,
        supplemental_url,
        roster_seed.institution,
        roster_seed.department,
    )
    if not _is_same_szu_csse_person(roster_seed.name, supplemental.name):
        return None
    return _merge_szu_csse_supplemental_profile(card_profile, supplemental)


def _fetch_szu_csse_cached_html(
    url: str,
    *,
    timeout: float,
    fetch_html: Callable[[str, float], str],
) -> str:
    cache_key = (url, timeout)
    try:
        with _SZU_CSSE_FETCH_CACHE_LOCK:
            fetcher_cache = _SZU_CSSE_FETCH_CACHE_BY_FETCHER.setdefault(fetch_html, {})
            cached = fetcher_cache.get(cache_key)
        if cached is not None:
            return cached
    except TypeError:
        return fetch_html(url, timeout)

    html = fetch_html(url, timeout)
    with _SZU_CSSE_FETCH_CACHE_LOCK:
        fetcher_cache = _SZU_CSSE_FETCH_CACHE_BY_FETCHER.setdefault(fetch_html, {})
        fetcher_cache.setdefault(cache_key, html)
    return html


def _szu_csse_bigdata_profile_url_for_name(
    html: str,
    roster_name: str,
) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select(".gbteam1"):
        name_node = card.find("h3")
        if name_node is None:
            continue
        candidate_name = normalize_text(name_node.get_text(" ", strip=True))
        if not _is_same_szu_csse_person(roster_name, candidate_name):
            continue
        anchor = card.find("a", href=True)
        if anchor is None:
            continue
        href = str(anchor.get("href", "")).strip()
        if not href or href.lower().startswith(("javascript:", "#")):
            continue
        return urljoin(_SZU_CSSE_BIGDATA_TEAM_URL, href)
    return None


def _is_same_szu_csse_person(left: str | None, right: str | None) -> bool:
    left_text = normalize_text(left)
    right_text = normalize_text(right)
    if not left_text or not right_text:
        return False
    return left_text == right_text or is_same_person_name_variant(left_text, right_text)


def _merge_szu_csse_supplemental_profile(
    card_profile: ExtractedProfessorProfile,
    supplemental: ExtractedProfessorProfile,
) -> ExtractedProfessorProfile:
    source_urls = _dedupe_texts(
        [
            *card_profile.source_urls,
            *supplemental.source_urls,
            supplemental.profile_url,
        ]
    )
    raw_text = "\n".join(
        _dedupe_texts(
            [
                supplemental.profile_raw_text,
                card_profile.profile_raw_text,
            ]
        )
    )
    research_directions = (
        supplemental.research_directions or card_profile.research_directions
    )
    academic_positions = tuple(
        _dedupe_texts(
            [
                *card_profile.academic_positions,
                *supplemental.academic_positions,
            ]
        )
    )
    return ExtractedProfessorProfile(
        name=card_profile.name or supplemental.name,
        institution=card_profile.institution or supplemental.institution,
        department=card_profile.department or supplemental.department,
        title=card_profile.title or supplemental.title,
        email=card_profile.email or supplemental.email,
        homepage_url=supplemental.homepage_url or supplemental.profile_url,
        profile_url=card_profile.profile_url,
        office=card_profile.office or supplemental.office,
        research_directions=tuple(research_directions),
        source_urls=tuple(source_urls),
        profile_raw_text=raw_text or None,
        education_structured=tuple(supplemental.education_structured),
        work_experience=tuple(supplemental.work_experience),
        awards=tuple(supplemental.awards),
        academic_positions=academic_positions,
    )


def _dedupe_texts(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = normalize_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _augment_sigs_structured_fields(
    extracted: ExtractedProfessorProfile,
    *,
    html: str,
    source_url: str,
) -> ExtractedProfessorProfile:
    if "sigs.tsinghua.edu.cn" not in source_url:
        return extracted

    from .homepage_crawler import _extract_sigs_tab_homepage_output

    output = _extract_sigs_tab_homepage_output(html, source_url)
    if not (
        output.education_structured
        or output.work_experience
        or output.awards
        or output.academic_positions
    ):
        return extracted
    return replace(
        extracted,
        education_structured=tuple(output.education_structured),
        work_experience=tuple(output.work_experience),
        awards=tuple(output.awards),
        academic_positions=tuple(output.academic_positions),
    )
