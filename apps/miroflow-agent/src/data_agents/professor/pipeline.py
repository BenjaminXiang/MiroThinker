from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .discovery import (
    DiscoverySourceStatus,
    ProfessorSeedDiscoveryResult,
    discover_professor_seeds,
    fetch_html_with_fallback,
    get_allowed_registered_domains,
    get_registered_domain,
)
from .enrichment import (
    build_profile_record,
    extract_profile_record,
    is_structured_profile,
    normalize_text,
)
from .models import (
    DiscoveredProfessorSeed,
    ExtractedProfessorProfile,
    MergedProfessorProfileRecord,
    ProfessorRosterSeed,
)
from .parser import parse_roster_seed_markdown

DiscoverProfessors = Callable[
    [list[ProfessorRosterSeed], float], ProfessorSeedDiscoveryResult
]
ExtractProfile = Callable[
    [DiscoveredProfessorSeed, float],
    tuple[ExtractedProfessorProfile | None, str | None],
]


@dataclass(frozen=True, slots=True)
class ProfessorPipelineReport:
    seed_url_count: int
    discovered_professor_count: int
    unique_professor_count: int
    duplicate_professor_count: int
    failed_roster_fetch_count: int
    unresolved_seed_source_count: int
    official_profile_candidate_count: int
    profile_fetch_success_count: int
    profile_fetch_failed_count: int
    skipped_external_profile_count: int
    structured_profile_count: int
    partial_profile_count: int


@dataclass(frozen=True, slots=True)
class ProfessorPipelineResult:
    profiles: list[MergedProfessorProfileRecord]
    source_statuses: list[DiscoverySourceStatus]
    failed_fetch_urls: list[str]
    report: ProfessorPipelineReport


def run_professor_pipeline(
    seed_doc: Path,
    *,
    timeout: float = 20.0,
    official_domain_suffixes: tuple[str, ...] = ("sustech.edu.cn",),
    include_external_profiles: bool = False,
    skip_profile_fetch: bool = False,
    discover_professors: DiscoverProfessors | None = None,
    extract_profile: ExtractProfile | None = None,
    max_workers: int | None = None,
) -> ProfessorPipelineResult:
    markdown = seed_doc.read_text(encoding="utf-8")
    seeds = parse_roster_seed_markdown(markdown)
    discoverer = discover_professors or _default_discover_professors
    extractor = extract_profile or _default_extract_profile

    discovery = discoverer(seeds, timeout)
    discovered_professors = discovery.professors
    official_suffixes = _normalize_domain_suffixes(official_domain_suffixes)
    official_suffixes.update(
        domain
        for seed in seeds
        for domain in get_allowed_registered_domains(seed.roster_url)
    )
    identity_counter: Counter[tuple[str, str, str]] = Counter(
        _identity_key(seed) for seed in discovered_professors
    )
    unique_professors: dict[tuple[str, str, str], DiscoveredProfessorSeed] = {}
    for discovered in discovered_professors:
        key = _identity_key(discovered)
        existing = unique_professors.get(key)
        if existing is None:
            unique_professors[key] = discovered
            continue
        unique_professors[key] = _select_preferred_seed(
            current=existing,
            candidate=discovered,
            official_suffixes=official_suffixes,
        )

    official_profile_candidate_count = 0
    profile_fetch_success_count = 0
    profile_fetch_failed_count = 0
    skipped_external_profile_count = 0
    structured_profile_count = 0
    partial_profile_count = 0

    ordered_professors = list(unique_professors.values())
    fetched_profile_records: dict[int, MergedProfessorProfileRecord] = {}
    profile_jobs: list[tuple[int, DiscoveredProfessorSeed]] = []

    for index, roster_seed in enumerate(ordered_professors):
        is_official_profile = _is_official_domain(
            roster_seed.profile_url,
            allowed_suffixes=tuple(sorted(official_suffixes)),
        )
        if is_official_profile:
            official_profile_candidate_count += 1

        if not is_official_profile and not include_external_profiles:
            skipped_external_profile_count += 1
            fetched_profile_records[index] = build_profile_record(
                roster_seed=roster_seed,
                extracted=None,
                extraction_status="skipped",
                skip_reason="external_profile_domain_not_allowed_by_default",
            )
            continue
        if skip_profile_fetch:
            fetched_profile_records[index] = build_profile_record(
                roster_seed=roster_seed,
                extracted=None,
                extraction_status="skipped",
                skip_reason="profile_fetch_disabled",
            )
            skipped_external_profile_count += 1
            continue
        profile_jobs.append((index, roster_seed))

    if profile_jobs:
        resolved_workers = max_workers or min(4, max(1, len(profile_jobs)))
        with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
            future_to_job = {
                executor.submit(extractor, roster_seed, timeout): (index, roster_seed)
                for index, roster_seed in profile_jobs
            }
            for future in as_completed(future_to_job):
                index, roster_seed = future_to_job[future]
                try:
                    extracted, error = future.result()
                except Exception as exc:  # pragma: no cover - defensive guard for unexpected failures
                    profile_fetch_failed_count += 1
                    fetched_profile_records[index] = build_profile_record(
                        roster_seed=roster_seed,
                        extracted=None,
                        extraction_status="failed",
                        skip_reason=None,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    continue

                if error is not None:
                    profile_fetch_failed_count += 1
                    fetched_profile_records[index] = build_profile_record(
                        roster_seed=roster_seed,
                        extracted=None,
                        extraction_status="failed",
                        skip_reason=None,
                        error=error,
                    )
                    continue

                assert extracted is not None
                profile_fetch_success_count += 1
                extraction_status = (
                    "structured" if is_structured_profile(extracted) else "partial"
                )
                if extraction_status == "structured":
                    structured_profile_count += 1
                else:
                    partial_profile_count += 1
                fetched_profile_records[index] = build_profile_record(
                    roster_seed=roster_seed,
                    extracted=extracted,
                    extraction_status=extraction_status,
                    skip_reason=None,
                )

    profiles: list[MergedProfessorProfileRecord] = []
    for index in range(len(ordered_professors)):
        record = fetched_profile_records.get(index)
        if record is not None:
            profiles.append(record)

    duplicate_professor_count = sum(
        count - 1 for count in identity_counter.values() if count > 1
    )
    report = ProfessorPipelineReport(
        seed_url_count=len(seeds),
        discovered_professor_count=len(discovered_professors),
        unique_professor_count=len(unique_professors),
        duplicate_professor_count=duplicate_professor_count,
        failed_roster_fetch_count=len(discovery.failed_fetch_urls),
        unresolved_seed_source_count=len(
            [status for status in discovery.source_statuses if status.status == "unresolved"]
        ),
        official_profile_candidate_count=official_profile_candidate_count,
        profile_fetch_success_count=profile_fetch_success_count,
        profile_fetch_failed_count=profile_fetch_failed_count,
        skipped_external_profile_count=skipped_external_profile_count,
        structured_profile_count=structured_profile_count,
        partial_profile_count=partial_profile_count,
    )
    return ProfessorPipelineResult(
        profiles=profiles,
        source_statuses=discovery.source_statuses,
        failed_fetch_urls=discovery.failed_fetch_urls,
        report=report,
    )


def _default_discover_professors(
    seeds: list[ProfessorRosterSeed],
    timeout: float,
) -> ProfessorSeedDiscoveryResult:
    return discover_professor_seeds(
        seeds=seeds,
        fetch_html=lambda url: _fetch_html(url, timeout),
    )


def _default_extract_profile(
    roster_seed: DiscoveredProfessorSeed,
    timeout: float,
) -> tuple[ExtractedProfessorProfile | None, str | None]:
    return extract_profile_record(
        roster_seed=roster_seed,
        timeout=timeout,
        fetch_html=_fetch_html,
    )


def _fetch_html(url: str, timeout: float) -> str:
    result = fetch_html_with_fallback(url, timeout=timeout)
    if result.html is not None:
        return result.html
    if result.browser_error:
        raise RuntimeError(result.browser_error)
    raise RuntimeError(f"unable to fetch usable html from {url}")


def _identity_key(seed: DiscoveredProfessorSeed) -> tuple[str, str, str]:
    return (
        normalize_text(seed.name) or "",
        normalize_text(seed.institution) or "",
        normalize_text(seed.department) or "",
    )


def _normalize_domain_suffixes(suffixes: tuple[str, ...]) -> set[str]:
    normalized: set[str] = set()
    for suffix in suffixes:
        item = suffix.lower().strip().lstrip(".")
        if item:
            normalized.add(item)
    return normalized


def _is_official_domain(url: str, allowed_suffixes: tuple[str, ...]) -> bool:
    hostname = (urlparse(url).hostname or "").lower().strip(".")
    if not hostname:
        return False
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in allowed_suffixes
    )


def _select_preferred_seed(
    *,
    current: DiscoveredProfessorSeed,
    candidate: DiscoveredProfessorSeed,
    official_suffixes: set[str],
) -> DiscoveredProfessorSeed:
    current_is_official = _is_official_domain(
        current.profile_url,
        tuple(sorted(official_suffixes)),
    )
    candidate_is_official = _is_official_domain(
        candidate.profile_url,
        tuple(sorted(official_suffixes)),
    )
    if candidate_is_official and not current_is_official:
        return candidate
    return current
