from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urljoin, urlparse

from psycopg import Connection
from psycopg.types.json import Jsonb
import requests
from bs4 import BeautifulSoup

from .adapter_resolution import resolve_seed_adapter_name
from .canonical_writer import upsert_source_page_for_url, write_professor_bundle
from .models import (
    EnrichedProfessorProfile,
    MergedProfessorProfileRecord,
    ProfessorRosterSeed,
)
from .name_selection import is_obvious_non_person_name
from .pipeline import ProfessorPipelineResult, run_professor_pipeline
from .publish_helpers import build_professor_id
from ..storage.postgres.connection import connect
from ..storage.postgres.pipeline_run import close_pipeline_run, open_pipeline_run

_REPORTED_BY = "professor_seed_runner"
_SZU_CSSE_INSTITUTION = "深圳大学"
_SZU_CSSE_DEPARTMENT = "计算机与软件学院"
_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX = "source_page_role:"
_SZU_CSSE_SUPPLEMENT_SOURCE_TIMEOUT = 5.0
_SZU_CSSE_OFFICIAL_SUPPLEMENT_SOURCE_URLS = (
    "https://bigdata.szu.edu.cn/kytd.htm",
    "https://aisc.szu.edu.cn/AISC/Faculty.htm",
    "https://csse.szu.edu.cn/se/team-Staff",
)
_SZU_CSSE_NON_PERSON_LABELS = {
    "about",
    "faculty",
    "home",
    "research",
    "staff",
    "team",
    "博士生导师",
    "副教授",
    "讲师",
    "教授",
    "科研成果",
    "科研团队",
    "人才培养",
    "师资队伍",
    "团队成员",
    "文化建设",
    "学院概况",
    "研究团队",
    "助理教授",
}
_CHINESE_PERSON_RE = re.compile(r"[\u4e00-\u9fff]")
_WHITESPACE_RE = re.compile(r"\s+")
_SZU_BIGDATA_PROFILE_PATH_RE = re.compile(r"^/info/\d+/\d+\.htm$")
_SZU_AISC_PROFILE_PATH_RE = re.compile(r"^/info/1060/\d+\.htm$")
_SZU_BIGDATA_PUBLICATION_PATH_RE = re.compile(r"^/kycg/lwfb(?:/\d+)?\.htm$")
_SZU_AISC_PUBLICATION_PATH_RE = re.compile(r"^/(?:aisc/)?kycg(?:/a\d+)?\.htm$")

AdapterResolver = Callable[[ProfessorRosterSeed], str | None]
PipelineRunner = Callable[[ProfessorRosterSeed, float], ProfessorPipelineResult]
ProfileWriter = Callable[
    [Connection],
    None,
]


@dataclass(frozen=True, slots=True)
class SingleSeedRunResult:
    seed_id: int
    run_id: str | None
    status: str
    items_processed: int
    items_failed: int
    adapter_name: str | None = None
    error: str | None = None


def run_single_seed(
    seed_id: int,
    *,
    dsn: str | None = None,
    run_id: str | None = None,
    timeout: float = 20.0,
    adapter_resolver: AdapterResolver | None = None,
    pipeline_runner: PipelineRunner | None = None,
    profile_writer: Callable[
        [Connection],
        None,
    ]
    | None = None,
) -> SingleSeedRunResult:
    """Run one admin-managed professor seed and persist terminal status."""
    with connect(dsn) as conn:
        opened_run = run_id is None
        if opened_run:
            seed = _load_seed(conn, seed_id)
            run_id = str(
                open_pipeline_run(
                    conn,
                    run_kind="roster_crawl",
                    run_scope={
                        "source": "admin-console",
                        "domain": "professor",
                        "action": "single_seed_run",
                        "seed_id": seed_id,
                        "school": seed.institution,
                        "department": seed.department,
                        "seed_url": seed.roster_url,
                    },
                    triggered_by="professor_seed_runner",
                )
            )
            conn.commit()
        try:
            result = run_single_seed_with_conn(
                conn,
                seed_id=seed_id,
                run_id=run_id,
                timeout=timeout,
                adapter_resolver=adapter_resolver,
                pipeline_runner=pipeline_runner,
                profile_writer=profile_writer,
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise


def run_single_seed_with_conn(
    conn: Connection,
    *,
    seed_id: int,
    run_id: str | None = None,
    timeout: float = 20.0,
    adapter_resolver: AdapterResolver | None = None,
    pipeline_runner: PipelineRunner | None = None,
    profile_writer: Callable[..., None] | None = None,
) -> SingleSeedRunResult:
    seed = _load_seed(conn, seed_id)
    resolved_adapter = (adapter_resolver or _default_adapter_resolver)(seed)
    if resolved_adapter is None:
        _set_seed_terminal_status(conn, seed_id=seed_id, status="adapter_missing")
        _file_pipeline_issue(
            conn,
            seed_id=seed_id,
            seed=seed,
            stage="adapter_missing",
            severity="medium",
            description=(
                "adapter_missing: no registered professor roster adapter for "
                f"{seed.institution} / {seed.department or 'school-wide'}"
            ),
            evidence={
                "seed_id": seed_id,
                "school": seed.institution,
                "department": seed.department,
                "seed_url": seed.roster_url,
                "run_id": str(run_id) if run_id is not None else None,
            },
        )
        if run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                items_processed=0,
                items_failed=1,
                error_summary={"error": "adapter_missing", "seed_id": seed_id},
            )
        return SingleSeedRunResult(
            seed_id=seed_id,
            run_id=str(run_id) if run_id is not None else None,
            status="adapter_missing",
            items_processed=0,
            items_failed=1,
            adapter_name=None,
            error="adapter_missing",
        )

    try:
        result = (pipeline_runner or _default_pipeline_runner)(seed, timeout)
        profiles = list(result.profiles)
        if _is_szu_csse_seed(seed):
            profiles = _prepare_szu_csse_profiles(seed, profiles, timeout=timeout)

        if _has_fatal_discovery_result(result) and not profiles:
            return _mark_failure(
                conn,
                seed_id=seed_id,
                seed=seed,
                run_id=run_id,
                description=_discovery_failure_description(result),
                evidence=_discovery_failure_evidence(result),
                items_processed=0,
                items_failed=1,
            )

        writer = profile_writer or _default_profile_writer
        written = 0
        for profile in profiles:
            if (
                profile.error
                or not (profile.name or "").strip()
                or not _profile_matches_seed_scope(seed, profile)
            ):
                continue
            writer(conn, profile=profile, run_id=run_id)
            written += 1

        if written == 0:
            return _mark_failure(
                conn,
                seed_id=seed_id,
                seed=seed,
                run_id=run_id,
                description="discovery produced no writable professor profiles",
                evidence=_discovery_failure_evidence(result),
                items_processed=0,
                items_failed=1,
            )

        _set_seed_terminal_status(conn, seed_id=seed_id, status="success")
        if run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="succeeded",
                items_processed=written,
                items_failed=0,
            )
        return SingleSeedRunResult(
            seed_id=seed_id,
            run_id=str(run_id) if run_id is not None else None,
            status="success",
            items_processed=written,
            items_failed=0,
            adapter_name=resolved_adapter,
        )
    except Exception as exc:
        return _mark_failure(
            conn,
            seed_id=seed_id,
            seed=seed,
            run_id=run_id,
            description=f"single seed pipeline failed: {type(exc).__name__}: {exc}",
            evidence={"error": str(exc), "error_type": type(exc).__name__},
            items_processed=0,
            items_failed=1,
        )


def _load_seed(conn: Connection, seed_id: int) -> ProfessorRosterSeed:
    row = conn.execute(
        """
        SELECT school, department, seed_url
          FROM professor_seed
         WHERE id = %s
        """,
        (seed_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"professor_seed {seed_id} not found")
    if isinstance(row, dict):
        school = row["school"]
        department = row["department"]
        seed_url = row["seed_url"]
    else:
        school, department, seed_url = row
    return ProfessorRosterSeed(
        institution=school,
        department=department,
        roster_url=seed_url,
    )


def _default_adapter_resolver(seed: ProfessorRosterSeed) -> str | None:
    return resolve_seed_adapter_name(seed)


def _default_pipeline_runner(
    seed: ProfessorRosterSeed,
    timeout: float,
) -> ProfessorPipelineResult:
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as tmp:
        seed_doc = Path(tmp.name)
        tmp.write(
            f"{seed.institution or ''} "
            f"{seed.department or ''} "
            f"{seed.roster_url}\n"
        )
    try:
        return run_professor_pipeline(
            seed_doc,
            timeout=timeout,
            include_external_profiles=False,
            max_workers=4,
        )
    finally:
        seed_doc.unlink(missing_ok=True)


def _prepare_szu_csse_profiles(
    seed: ProfessorRosterSeed,
    profiles: list[MergedProfessorProfileRecord],
    *,
    timeout: float,
) -> list[MergedProfessorProfileRecord]:
    scoped_profiles = [
        profile for profile in profiles if _profile_matches_seed_scope(seed, profile)
    ]
    supplement_profiles = _collect_szu_csse_official_supplement_profiles(
        seed,
        timeout=timeout,
    )
    return _attach_szu_csse_official_supplement_sources(
        seed,
        _dedupe_szu_csse_profiles([*scoped_profiles, *supplement_profiles]),
        timeout=timeout,
    )


def _collect_szu_csse_official_supplement_profiles(
    seed: ProfessorRosterSeed,
    *,
    timeout: float,
    fetch_source_page: Callable[[str, float], str] | None = None,
) -> list[MergedProfessorProfileRecord]:
    if not _is_szu_csse_seed(seed):
        return []
    pages = _fetch_szu_csse_official_supplement_pages(
        timeout=timeout,
        fetch_source_page=fetch_source_page,
    )
    profiles: list[MergedProfessorProfileRecord] = []
    for source_url, html in pages.items():
        if not html.strip():
            continue
        if source_url == "https://bigdata.szu.edu.cn/kytd.htm":
            profiles.extend(_parse_szu_bigdata_supplement_profiles(seed, source_url, html))
        elif source_url == "https://aisc.szu.edu.cn/AISC/Faculty.htm":
            profiles.extend(_parse_szu_aisc_supplement_profiles(seed, source_url, html))
        elif source_url == "https://csse.szu.edu.cn/se/team-Staff":
            profiles.extend(_parse_szu_lab_staff_supplement_profiles(seed, source_url, html))
    return _dedupe_szu_csse_profiles(
        [
            profile
            for profile in profiles
            if _profile_matches_seed_scope(seed, profile)
        ]
    )


def _fetch_szu_csse_official_supplement_pages(
    *,
    timeout: float,
    fetch_source_page: Callable[[str, float], str] | None = None,
) -> dict[str, str]:
    fetcher = fetch_source_page or _fetch_szu_csse_supplement_source_page_no_env
    source_timeout = min(max(timeout, 0.1), _SZU_CSSE_SUPPLEMENT_SOURCE_TIMEOUT)
    pages: dict[str, str] = {}
    for source_url in _SZU_CSSE_OFFICIAL_SUPPLEMENT_SOURCE_URLS:
        try:
            pages[source_url] = fetcher(source_url, source_timeout)
        except Exception:
            pages[source_url] = ""
    return pages


def _fetch_szu_csse_supplement_source_page_no_env(
    url: str,
    timeout: float,
) -> str:
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()
    encoding = response.encoding or response.apparent_encoding or "utf-8"
    return response.content.decode(encoding, errors="replace")


def _parse_szu_bigdata_supplement_profiles(
    seed: ProfessorRosterSeed,
    source_url: str,
    html: str,
) -> list[MergedProfessorProfileRecord]:
    soup = BeautifulSoup(html, "html.parser")
    profiles: list[MergedProfessorProfileRecord] = []
    cards = soup.select(".gbteam1")
    for card in cards:
        name = _clean_szu_csse_text(card.find("h3").get_text(" ", strip=True) if card.find("h3") else "")
        if not _is_szu_csse_probable_person_name(name):
            continue
        profile_url = _first_szu_csse_profile_link(card, source_url)
        if profile_url is None:
            continue
        profiles.append(
            _build_szu_csse_supplement_profile(
                seed=seed,
                source_url=source_url,
                name=name,
                profile_url=profile_url,
                research_directions=_extract_szu_csse_research_directions(card),
            )
        )
    return profiles


def _parse_szu_aisc_supplement_profiles(
    seed: ProfessorRosterSeed,
    source_url: str,
    html: str,
) -> list[MergedProfessorProfileRecord]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("main") or soup.body or soup
    profiles: list[MergedProfessorProfileRecord] = []
    for anchor in container.find_all("a", href=True):
        name = _clean_szu_csse_text(anchor.get_text(" ", strip=True))
        if not _is_szu_csse_probable_person_name(name):
            continue
        profile_url = urljoin(source_url, anchor["href"])
        if not _is_szu_csse_supplement_profile_url(profile_url, source_url):
            continue
        profiles.append(
            _build_szu_csse_supplement_profile(
                seed=seed,
                source_url=source_url,
                name=name,
                profile_url=profile_url,
                research_directions=(),
            )
        )
    return profiles


def _parse_szu_lab_staff_supplement_profiles(
    seed: ProfessorRosterSeed,
    source_url: str,
    html: str,
) -> list[MergedProfessorProfileRecord]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".staff-list article") or soup.find_all("article")
    profiles: list[MergedProfessorProfileRecord] = []
    for card in cards:
        name_node = card.find("h3")
        name = _clean_szu_csse_text(
            name_node.get_text(" ", strip=True) if name_node else ""
        )
        if not _is_szu_csse_probable_person_name(name):
            continue
        profile_url = _first_szu_csse_profile_link(card, source_url)
        if profile_url is None:
            continue
        profiles.append(
            _build_szu_csse_supplement_profile(
                seed=seed,
                source_url=source_url,
                name=name,
                profile_url=profile_url,
                research_directions=_extract_szu_csse_research_directions(card),
            )
        )
    return profiles


def _attach_szu_csse_official_supplement_sources(
    seed: ProfessorRosterSeed,
    profiles: list[MergedProfessorProfileRecord],
    *,
    timeout: float,
    fetch_source_page: Callable[[str, float], str] | None = None,
) -> list[MergedProfessorProfileRecord]:
    if not _is_szu_csse_seed(seed):
        return profiles
    pages = _fetch_szu_csse_official_supplement_pages(
        timeout=timeout,
        fetch_source_page=fetch_source_page,
    )
    updated_profiles: list[MergedProfessorProfileRecord] = []
    for profile in profiles:
        additions: list[str] = []
        for source_url, html in pages.items():
            if not html.strip() or not _szu_csse_page_mentions_profile(html, profile):
                continue
            additions.append(source_url)
            additions.extend(
                _discover_szu_csse_supplement_publication_source_urls(source_url, html)
            )
        if additions:
            updated_profiles.append(
                replace(
                    profile,
                    source_urls=tuple(_dedupe_szu_csse_urls([*profile.source_urls, *additions])),
                    evidence=tuple(_dedupe_szu_csse_urls([*profile.evidence, *additions])),
                )
            )
            continue
        updated_profiles.append(profile)
    return updated_profiles


def _build_szu_csse_supplement_profile(
    *,
    seed: ProfessorRosterSeed,
    source_url: str,
    name: str,
    profile_url: str,
    research_directions: tuple[str, ...],
) -> MergedProfessorProfileRecord:
    urls = tuple(_dedupe_szu_csse_urls([source_url, profile_url]))
    return MergedProfessorProfileRecord(
        name=name,
        institution=seed.institution,
        department=seed.department,
        title=None,
        email=None,
        office=None,
        homepage=profile_url,
        profile_url=profile_url,
        source_urls=urls,
        evidence=urls,
        research_directions=research_directions,
        extraction_status="structured",
        skip_reason=None,
        error=None,
        roster_source=source_url,
    )


def _first_szu_csse_profile_link(node: Any, source_url: str) -> str | None:
    for anchor in node.find_all("a", href=True):
        profile_url = urljoin(source_url, anchor["href"])
        if _is_szu_csse_supplement_profile_url(profile_url, source_url):
            return profile_url
    return None


def _extract_szu_csse_research_directions(node: Any) -> tuple[str, ...]:
    for text_node in node.find_all(["p", "span", "li"]):
        text = _clean_szu_csse_text(text_node.get_text(" ", strip=True))
        match = re.search(r"研究方向\s*[:：]\s*(.+)", text)
        if match:
            value = _clean_szu_csse_text(match.group(1))
            return (value,) if value else ()
    return ()


def _discover_szu_csse_supplement_publication_source_urls(
    source_url: str,
    html: str,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    publication_urls: list[str] = []
    for anchor in soup.find_all("a", href=True):
        candidate = urljoin(source_url, anchor["href"])
        if _is_szu_csse_publication_evidence_source_url(candidate):
            publication_urls.append(candidate)
    return _dedupe_szu_csse_urls(publication_urls)


def _profile_matches_seed_scope(
    seed: ProfessorRosterSeed,
    profile: MergedProfessorProfileRecord,
) -> bool:
    if not _is_szu_csse_seed(seed):
        return True
    name = _clean_szu_csse_text(profile.name)
    if not _is_szu_csse_probable_person_name(name):
        return False
    scoped_urls = [
        profile.profile_url,
        profile.homepage,
        profile.roster_source,
        *profile.source_urls,
        *profile.evidence,
    ]
    for url in scoped_urls:
        if not url:
            continue
        if _is_szu_csse_roster_profile_url(url):
            return True
        if _is_szu_csse_supplement_profile_url(url, profile.roster_source):
            return True
        if _is_szu_csse_official_supplement_source_url(url):
            return True
    return False


def _is_szu_csse_seed(seed: ProfessorRosterSeed) -> bool:
    hostname = (urlparse(seed.roster_url).hostname or "").lower()
    institution = seed.institution or ""
    department = seed.department or ""
    return (
        hostname == "csse.szu.edu.cn"
        and _SZU_CSSE_INSTITUTION in institution
        and _SZU_CSSE_DEPARTMENT in department
    )


def _is_szu_csse_probable_person_name(name: str | None) -> bool:
    text = _clean_szu_csse_text(name)
    if not text:
        return False
    if text in _SZU_CSSE_NON_PERSON_LABELS:
        return False
    if text.casefold() in _SZU_CSSE_NON_PERSON_LABELS:
        return False
    chinese_chars = _CHINESE_PERSON_RE.findall(text)
    if chinese_chars:
        return 2 <= len(chinese_chars) <= 4 and len(text) <= 8
    if is_obvious_non_person_name(text):
        return False
    normalized = text.replace("'", " ").replace("-", " ")
    tokens = [token for token in normalized.split() if token]
    return 2 <= len(tokens) <= 4 and all(token.isalpha() for token in tokens)


def _is_szu_csse_roster_profile_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != "csse.szu.edu.cn":
        return False
    if parsed.path != "/pages/user/index":
        return False
    return any(key == "id" and value.isdigit() for key, value in parse_qsl(parsed.query))


def _is_szu_csse_supplement_profile_url(
    profile_url: str | None,
    source_url: str | None,
) -> bool:
    if not profile_url:
        return False
    parsed = urlparse(profile_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path
    if hostname == "bigdata.szu.edu.cn":
        return bool(_SZU_BIGDATA_PROFILE_PATH_RE.match(path))
    if hostname == "aisc.szu.edu.cn":
        return bool(_SZU_AISC_PROFILE_PATH_RE.match(path))
    if hostname == "csse.szu.edu.cn":
        path_lower = path.lower()
        return (
            path_lower != "/se/team-staff"
            and path_lower.startswith("/se/")
            and any(
                segment in path_lower
                for segment in ("/member/", "/members/", "/people/", "/staff/")
            )
        )
    source_host = (urlparse(source_url or "").hostname or "").lower()
    return hostname == source_host and bool(path)


def _is_szu_csse_official_supplement_source_url(url: str | None) -> bool:
    return _strip_url_fragment(url) in _SZU_CSSE_OFFICIAL_SUPPLEMENT_SOURCE_URLS


def _is_szu_csse_publication_evidence_source_url(url: str | None) -> bool:
    if not url:
        return False
    stripped = _strip_url_fragment(url)
    if stripped == "https://bigdata.szu.edu.cn/kytd.htm":
        return True
    parsed = urlparse(stripped)
    hostname = (parsed.hostname or "").lower()
    path_lower = parsed.path.lower()
    if hostname == "bigdata.szu.edu.cn":
        return bool(_SZU_BIGDATA_PUBLICATION_PATH_RE.match(path_lower))
    if hostname == "aisc.szu.edu.cn":
        return bool(_SZU_AISC_PUBLICATION_PATH_RE.match(path_lower))
    return False


def _szu_csse_page_mentions_profile(
    html: str,
    profile: MergedProfessorProfileRecord,
) -> bool:
    name_key = _szu_csse_person_match_key(profile.name)
    if not name_key:
        return False
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "footer"]):
        node.decompose()
    page_key = _szu_csse_person_match_key(soup.get_text(" ", strip=True))
    return name_key in page_key


def _szu_csse_person_match_key(value: str | None) -> str:
    text = _clean_szu_csse_text(value)
    return re.sub(r"[\s·\-.']", "", text).casefold()


def _clean_szu_csse_text(value: str | None) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value)).strip(" \t\r\n:：|/-")


def _dedupe_szu_csse_profiles(
    profiles: list[MergedProfessorProfileRecord],
) -> list[MergedProfessorProfileRecord]:
    deduped: list[MergedProfessorProfileRecord] = []
    seen: set[tuple[str, str]] = set()
    for profile in profiles:
        key = (_szu_csse_person_match_key(profile.name), profile.profile_url.casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(profile)
    return deduped


def _dedupe_szu_csse_urls(urls: list[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        stripped = _strip_url_fragment(url)
        if not stripped:
            continue
        key = stripped.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(stripped)
    return deduped


def _strip_url_fragment(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    return parsed._replace(fragment="").geturl()


def _default_profile_writer(
    conn: Connection,
    *,
    profile: MergedProfessorProfileRecord,
    run_id: str | None,
) -> None:
    if run_id is None:
        raise ValueError("run_id is required for canonical professor writes")
    enriched = _merged_to_enriched(profile)
    fetched_at = datetime.now(timezone.utc)
    professor_id = build_professor_id(enriched)
    primary_page_id = upsert_source_page_for_url(
        conn,
        url=enriched.profile_url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref=None,
        fetched_at=fetched_at,
        is_official_source=_is_official_source(enriched.profile_url),
        run_id=run_id,
    )
    if enriched.roster_source and enriched.roster_source != enriched.profile_url:
        upsert_source_page_for_url(
            conn,
            url=enriched.roster_source,
            page_role="roster_seed",
            owner_scope_kind="institution",
            owner_scope_ref=enriched.institution,
            fetched_at=fetched_at,
            is_official_source=_is_official_source(enriched.roster_source),
            run_id=run_id,
        )
    for publication_url in enriched.publication_evidence_urls:
        upsert_source_page_for_url(
            conn,
            url=publication_url,
            page_role="official_publication_page",
            owner_scope_kind="professor",
            owner_scope_ref=professor_id,
            fetched_at=fetched_at,
            is_official_source=_is_official_source(publication_url),
            run_id=run_id,
        )
    write_professor_bundle(
        conn,
        enriched=enriched,
        paper_staging=None,
        official_profile_page_id=primary_page_id,
        run_id=run_id,
    )


def _merged_to_enriched(
    profile: MergedProfessorProfileRecord,
) -> EnrichedProfessorProfile:
    publication_evidence_urls = [
        url
        for url in _dedupe_szu_csse_urls([*profile.evidence, *profile.source_urls])
        if _is_szu_csse_publication_evidence_source_url(url)
    ]
    field_provenance = {
        f"{_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX}{url}": "official_publication_page"
        for url in publication_evidence_urls
    }
    return EnrichedProfessorProfile(
        name=(profile.name or "").strip(),
        institution=(profile.institution or "").strip(),
        department=profile.department,
        title=profile.title,
        email=profile.email,
        homepage=profile.homepage,
        office=profile.office,
        research_directions=list(profile.research_directions),
        research_directions_source="official_only",
        profile_url=profile.profile_url,
        roster_source=profile.roster_source,
        extraction_status=profile.extraction_status,
        enrichment_source="regex_only",
        evidence_urls=list(profile.evidence),
        publication_evidence_urls=publication_evidence_urls,
        field_provenance=field_provenance,
    )


def _is_official_source(url: str | None) -> bool:
    if not url:
        return False
    hostname = (urlparse(url).hostname or "").lower()
    return hostname.endswith(".edu.cn") or hostname.endswith(".gov.cn") or hostname.endswith(".ac.cn")


def _has_fatal_discovery_result(result: ProfessorPipelineResult) -> bool:
    if result.report.unique_professor_count <= 0:
        return True
    return any(
        status.status == "failed" and status.discovered_professor_count <= 0
        for status in result.source_statuses
    )


def _discovery_failure_description(result: ProfessorPipelineResult) -> str:
    if not result.source_statuses:
        return "discovery failed: no source status returned"
    status = result.source_statuses[0]
    return (
        "discovery failed: "
        f"{status.reason}"
        + (f" ({status.error})" if status.error else "")
    )


def _discovery_failure_evidence(result: ProfessorPipelineResult) -> dict[str, Any]:
    return {
        "source_statuses": [
            {
                "seed_url": status.seed_url,
                "status": status.status,
                "reason": status.reason,
                "error": status.error,
                "visited_urls": status.visited_urls,
                "discovered_professor_count": status.discovered_professor_count,
            }
            for status in result.source_statuses
        ],
        "failed_fetch_urls": list(result.failed_fetch_urls),
        "report": {
            "seed_url_count": result.report.seed_url_count,
            "unique_professor_count": result.report.unique_professor_count,
            "failed_roster_fetch_count": result.report.failed_roster_fetch_count,
            "unresolved_seed_source_count": result.report.unresolved_seed_source_count,
        },
    }


def _mark_failure(
    conn: Connection,
    *,
    seed_id: int,
    seed: ProfessorRosterSeed,
    run_id: str | None,
    description: str,
    evidence: dict[str, Any],
    items_processed: int,
    items_failed: int,
) -> SingleSeedRunResult:
    _set_seed_terminal_status(conn, seed_id=seed_id, status="failure")
    _file_pipeline_issue(
        conn,
        seed_id=seed_id,
        seed=seed,
        stage="discovery",
        severity="high",
        description=description,
        evidence={
            **evidence,
            "seed_id": seed_id,
            "school": seed.institution,
            "department": seed.department,
            "seed_url": seed.roster_url,
            "run_id": str(run_id) if run_id is not None else None,
        },
    )
    if run_id is not None:
        close_pipeline_run(
            conn,
            run_id,
            status="failed",
            items_processed=items_processed,
            items_failed=items_failed,
            error_summary={"message": description, "seed_id": seed_id},
        )
    return SingleSeedRunResult(
        seed_id=seed_id,
        run_id=str(run_id) if run_id is not None else None,
        status="failure",
        items_processed=items_processed,
        items_failed=items_failed,
        error=description,
    )


def _set_seed_terminal_status(
    conn: Connection,
    *,
    seed_id: int,
    status: str,
) -> None:
    conn.execute(
        """
        UPDATE professor_seed
           SET last_run_status = %s,
               last_run_at = now(),
               updated_at = now()
         WHERE id = %s
        """,
        (status, seed_id),
    )


def _file_pipeline_issue(
    conn: Connection,
    *,
    seed_id: int,
    seed: ProfessorRosterSeed,
    stage: str,
    severity: str,
    description: str,
    evidence: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_issue (
            institution, stage, severity, description, evidence_snapshot, reported_by
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            seed.institution or f"seed:{seed_id}",
            stage,
            severity,
            description,
            Jsonb(json.loads(json.dumps(evidence, ensure_ascii=False, default=str))),
            _REPORTED_BY,
        ),
    )
