from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests

from .models import DiscoveredProfessorSeed, ProfessorRosterSeed
from .roster import extract_roster_entries, extract_roster_page_links

FetchHtml = Callable[[str], str]
FetchJson = Callable[[str, dict[str, object]], object]

_SEED_FALLBACK_URLS: dict[str, tuple[str, ...]] = {
    "https://www.sustech.edu.cn/zh/letter/": (
        "https://www.sustech.edu.cn/zh/faculty_members.html",
    ),
    "https://www.szu.edu.cn/szdw/jsjj.htm": (
        "https://www.szu.edu.cn/yxjg/xbxy.htm",
    ),
    "https://rw.pkusz.edu.cn/szll.htm": (
        "https://shss.pkusz.edu.cn/szdw/jsml.htm",
    ),
    "https://scbb.pkusz.edu.cn/szdw.htm": (
        "https://scbb.pkusz.edu.cn/szdw/hxswx.htm",
        "https://scbb.pkusz.edu.cn/szdw/hchx.htm",
        "https://scbb.pkusz.edu.cn/szdw/jshx.htm",
        "https://scbb.pkusz.edu.cn/szdw/zhswx.htm",
        "https://scbb.pkusz.edu.cn/szdw/xdswjs.htm",
    ),
    "https://stl.pku.edu.cn/Faculty_Research/Resident_Faculty.htm": (
        "https://stl.pku.edu.cn/faculty/faculty/residentfaculty.html",
    ),
}
_SEED_OFFICIAL_DOMAIN_SUFFIXES: dict[str, tuple[str, ...]] = {
    "https://www.pkusz.edu.cn/szdw.htm": ("pkusz.edu.cn", "pku.edu.cn"),
}
_HOST_DIRECT_MIN_INTERVAL_SECONDS: dict[str, float] = {
    "med.szu.edu.cn": 1.2,
}
_HOST_DIRECT_SERIAL_LOCK = threading.Lock()
_last_direct_request_started_at_by_host: dict[str, float] = {}
_READER_SERIAL_LOCK = threading.Lock()
_READER_CONNECT_TIMEOUT_SECONDS = 8.0
_READER_MIN_INTERVAL_SECONDS = 2.0
_last_reader_request_started_at = 0.0


@dataclass(frozen=True, slots=True)
class DiscoveryLimits:
    max_depth: int = 2
    max_candidate_links_per_page: int = 32
    max_pages_per_seed: int = 32


@dataclass(frozen=True, slots=True)
class DiscoverySourceStatus:
    seed_url: str
    institution: str
    department: str | None
    status: str
    reason: str
    error: str | None = None
    visited_urls: list[str] = field(default_factory=list)
    discovered_professor_count: int = 0


@dataclass(frozen=True, slots=True)
class ProfessorSeedDiscoveryResult:
    professors: list[DiscoveredProfessorSeed]
    source_statuses: list[DiscoverySourceStatus]
    failed_fetch_urls: list[str]


@dataclass(frozen=True, slots=True)
class HtmlFetchResult:
    html: str | None
    used_browser: bool
    blocked_by_anti_scraping: bool
    request_error: str | None
    browser_error: str | None


@dataclass(frozen=True, slots=True)
class _PendingPage:
    url: str
    depth: int
    department: str | None


@dataclass(frozen=True, slots=True)
class _CandidatePage:
    url: str
    department: str | None


def discover_professor_seeds(
    seeds: list[ProfessorRosterSeed],
    fetch_html: FetchHtml | None = None,
    fetch_json: FetchJson | None = None,
    limits: DiscoveryLimits | None = None,
) -> ProfessorSeedDiscoveryResult:
    html_fetcher = fetch_html or _default_fetch_html
    json_fetcher = fetch_json or _default_fetch_json
    applied_limits = limits or DiscoveryLimits()

    discovered: list[DiscoveredProfessorSeed] = []
    source_statuses: list[DiscoverySourceStatus] = []
    failed_fetch_urls: set[str] = set()

    for seed in seeds:
        try:
            if _is_sigs_seed(seed.roster_url):
                try:
                    result = _discover_sigs_seed(seed, json_fetcher)
                except Exception:
                    result = _discover_recursive_seed(seed, html_fetcher, applied_limits)
            elif _is_hit_seed(seed.roster_url):
                try:
                    result = _discover_hit_seed(seed, json_fetcher)
                except Exception:
                    result = _discover_recursive_seed(seed, html_fetcher, applied_limits)
            else:
                result = _discover_recursive_seed(seed, html_fetcher, applied_limits)
        except Exception as exc:
            institution = (seed.institution or "").strip() or "UNKNOWN_INSTITUTION"
            result = _SeedDiscovery(
                professors=[],
                status=DiscoverySourceStatus(
                    seed_url=seed.roster_url,
                    institution=institution,
                    department=_normalize_text(seed.department),
                    status="failed",
                    reason="fetch_failed",
                    error=str(exc),
                    visited_urls=[seed.roster_url],
                    discovered_professor_count=0,
                ),
                failed_fetch_urls=[seed.roster_url],
            )

        discovered.extend(result.professors)
        source_statuses.append(result.status)
        failed_fetch_urls.update(result.failed_fetch_urls)

    return ProfessorSeedDiscoveryResult(
        professors=discovered,
        source_statuses=source_statuses,
        failed_fetch_urls=sorted(failed_fetch_urls),
    )


def fetch_html_with_fallback(
    url: str,
    timeout: float = 20.0,
    request_get: Callable[[str, float], requests.Response] | None = None,
    browser_fetch: Callable[[str, float], str] | None = None,
    reader_fetch: Callable[[str, float], str] | None = None,
) -> HtmlFetchResult:
    use_cache = request_get is None and browser_fetch is None and reader_fetch is None
    if use_cache:
        cached_html = _load_cached_html(url)
        if cached_html is not None:
            return HtmlFetchResult(
                html=cached_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
            )

    getter = request_get or _requests_get
    browser_renderer = browser_fetch or _render_html_with_playwright
    reader_renderer = reader_fetch or _render_text_with_reader

    request_error: str | None = None

    def _fetch_with_browser_fallback() -> HtmlFetchResult:
        browser_error: str | None = None
        try:
            rendered_html = browser_renderer(url, timeout)
        except Exception as exc:  # noqa: BLE001 - explicit reporting upstream.
            browser_error = str(exc)
            rendered_html = None
        else:
            if rendered_html and rendered_html.strip():
                if use_cache:
                    _store_cached_html(url, rendered_html)
                return HtmlFetchResult(
                    html=rendered_html,
                    used_browser=True,
                    blocked_by_anti_scraping=True,
                    request_error=request_error,
                    browser_error=None,
                )
        return HtmlFetchResult(
            html=None,
            used_browser=False,
            blocked_by_anti_scraping=True,
            request_error=request_error,
            browser_error=browser_error,
        )

    def _fetch_with_reader_fallback(browser_error: str | None) -> HtmlFetchResult:
        try:
            rendered_text = reader_renderer(url, timeout)
        except Exception as exc:  # noqa: BLE001 - explicit reporting upstream.
            composite_error = " | ".join(
                part for part in (browser_error, str(exc)) if part
            )
            return HtmlFetchResult(
                html=None,
                used_browser=False,
                blocked_by_anti_scraping=True,
                request_error=request_error,
                browser_error=composite_error or None,
            )
        return HtmlFetchResult(
            html=rendered_text,
            used_browser=False,
            blocked_by_anti_scraping=True,
            request_error=request_error,
            browser_error=browser_error,
        )

    try:
        response = getter(url, timeout)
    except requests.RequestException as exc:
        request_error = str(exc)
        browser_result = _fetch_with_browser_fallback()
        if browser_result.html is not None:
            return browser_result
        return _fetch_with_reader_fallback(browser_result.browser_error)

    html = _decode_response_text(response)
    blocked = _is_blocked_response(response.status_code, html)

    if blocked:
        if response.status_code >= 400:
            request_error = f"{response.status_code} Client Error"
        browser_result = _fetch_with_browser_fallback()
        if browser_result.html is not None:
            return browser_result
        return _fetch_with_reader_fallback(browser_result.browser_error)

    response.raise_for_status()
    if not html.strip():
        return HtmlFetchResult(
            html=None,
            used_browser=False,
            blocked_by_anti_scraping=False,
            request_error=None,
            browser_error=None,
        )
    if use_cache:
        _store_cached_html(url, html)
    return HtmlFetchResult(
        html=html,
        used_browser=False,
        blocked_by_anti_scraping=False,
        request_error=None,
        browser_error=None,
    )


def get_registered_domain(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower().strip(".")
    if not hostname:
        return ""
    labels = hostname.split(".")
    if len(labels) <= 2:
        return hostname
    if hostname.endswith(".edu.cn") or hostname.endswith(".org.cn") or hostname.endswith(".com.cn"):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def get_allowed_registered_domains(seed_url: str) -> tuple[str, ...]:
    domains = {get_registered_domain(seed_url)}
    domains.update(_SEED_OFFICIAL_DOMAIN_SUFFIXES.get(seed_url, ()))
    return tuple(sorted(domain for domain in domains if domain))


def _default_fetch_html(url: str) -> str:
    result = fetch_html_with_fallback(url)
    if result.html is not None:
        return result.html
    if result.request_error or result.browser_error:
        detail = " | ".join(
            part for part in (result.request_error, result.browser_error) if part
        )
        raise RuntimeError(detail)
    raise RuntimeError(f"unable to fetch usable html from {url}")


def _default_fetch_json(url: str, payload: dict[str, object]) -> object:
    response = _request_with_env_fallback(
        "post",
        url,
        timeout=20,
        data=payload,
    )
    response.raise_for_status()
    return response.json()


def _render_text_with_reader(url: str, timeout: float) -> str:
    cached_html = _load_cached_html(url)
    if cached_html is not None:
        return cached_html

    reader_url = f"https://r.jina.ai/http://{url}"
    last_error: Exception | None = None
    global _last_reader_request_started_at
    for attempt in range(3):
        with _READER_SERIAL_LOCK:
            remaining_delay = _READER_MIN_INTERVAL_SECONDS - (
                time.monotonic() - _last_reader_request_started_at
            )
            if remaining_delay > 0:
                time.sleep(remaining_delay)
            response = _request_with_env_fallback(
                "get",
                reader_url,
                timeout=(
                    _READER_CONNECT_TIMEOUT_SECONDS,
                    max(timeout, 40.0),
                ),
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                },
            )
            _last_reader_request_started_at = time.monotonic()
        if response.status_code == 429 and attempt < 2:
            time.sleep(10 * (attempt + 1))
            continue
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            last_error = exc
            break
        text = response.text
        if text.lstrip().startswith("{") and '"readableMessage"' in text:
            last_error = RuntimeError(text.strip())
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            break
        _store_cached_html(url, text)
        return text

    cached_html = _load_cached_html(url)
    if cached_html is not None:
        return cached_html
    assert last_error is not None
    raise last_error


def _requests_get(url: str, timeout: float) -> requests.Response:
    return _request_with_env_fallback(
        "get",
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )


def _request_with_env_fallback(
    method: str,
    url: str,
    *,
    timeout: float | tuple[float, float],
    headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> requests.Response:
    direct_error: requests.RequestException | None = None
    try:
        return _request_with_trust_env(
            method,
            url,
            timeout=timeout,
            headers=headers,
            trust_env=False,
            **kwargs,
        )
    except requests.RequestException as exc:
        direct_error = exc

    try:
        return _request_with_trust_env(
            method,
            url,
            timeout=timeout,
            headers=headers,
            trust_env=True,
            **kwargs,
        )
    except requests.RequestException:
        assert direct_error is not None
        raise direct_error


def _request_with_trust_env(
    method: str,
    url: str,
    *,
    timeout: float | tuple[float, float],
    headers: dict[str, str] | None,
    trust_env: bool,
    **kwargs: Any,
) -> requests.Response:
    if not trust_env:
        _wait_for_direct_host_rate_limit(url)
    with requests.Session() as session:
        session.trust_env = trust_env
        response = session.request(
            method=method,
            url=url,
            timeout=timeout,
            headers=headers,
            **kwargs,
        )
        if not trust_env and _is_direct_rate_limited_response(url, response):
            time.sleep(max(_HOST_DIRECT_MIN_INTERVAL_SECONDS.get((urlparse(url).hostname or "").lower(), 0.0), 1.2))
            _wait_for_direct_host_rate_limit(url)
            response = session.request(
                method=method,
                url=url,
                timeout=timeout,
                headers=headers,
                **kwargs,
            )
        return response


def _wait_for_direct_host_rate_limit(url: str) -> None:
    hostname = (urlparse(url).hostname or "").lower()
    min_interval = _HOST_DIRECT_MIN_INTERVAL_SECONDS.get(hostname)
    if min_interval is None:
        return
    global _last_direct_request_started_at_by_host
    with _HOST_DIRECT_SERIAL_LOCK:
        remaining_delay = min_interval - (
            time.monotonic() - _last_direct_request_started_at_by_host.get(hostname, 0.0)
        )
        if remaining_delay > 0:
            time.sleep(remaining_delay)
        _last_direct_request_started_at_by_host[hostname] = time.monotonic()


def _is_direct_rate_limited_response(url: str, response: requests.Response) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    if hostname != "med.szu.edu.cn":
        return False
    if response.status_code != 403:
        return False
    text = response.text
    return "短时间内发起多次请求" in text or "cc攻击" in text.lower()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _cache_dir() -> Path:
    return _repo_root() / "logs" / "debug" / "professor_fetch_cache"


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{digest}.json"


def _load_cached_html(url: str) -> str | None:
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return content


def _store_cached_html(url: str, content: str) -> None:
    normalized = content.strip()
    if not normalized:
        return
    path = _cache_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": url,
        "content": normalized,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _decode_response_text(response: requests.Response) -> str:
    encoding = (response.encoding or "").lower()
    apparent = getattr(response, "apparent_encoding", None)
    if (not encoding or encoding == "iso-8859-1") and apparent:
        response.encoding = apparent
    return response.text


def _is_blocked_response(status_code: int, html: str) -> bool:
    lowered = html.lower()
    return status_code in {401, 403, 412, 429, 503} or any(
        marker in lowered
        for marker in ("access denied", "forbidden", "captcha", "just a moment", "bot verification")
    )


def _render_html_with_playwright(url: str, timeout: float) -> str:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001 - import/runtime surfaces upstream.
        raise RuntimeError(f"playwright unavailable: {exc}") from exc

    timeout_ms = int(timeout * 1000)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            content = page.content()
            browser.close()
            return content
    except PlaywrightError as exc:
        raise RuntimeError(f"playwright browser runtime unavailable: {exc}") from exc


@dataclass(frozen=True, slots=True)
class _SeedDiscovery:
    professors: list[DiscoveredProfessorSeed]
    status: DiscoverySourceStatus
    failed_fetch_urls: list[str]


def _discover_recursive_seed(
    seed: ProfessorRosterSeed,
    fetch_html: FetchHtml,
    limits: DiscoveryLimits,
) -> _SeedDiscovery:
    institution = (seed.institution or "").strip() or "UNKNOWN_INSTITUTION"
    queue: deque[_PendingPage] = deque(
        [_PendingPage(url=seed.roster_url, depth=0, department=_normalize_text(seed.department))]
    )
    visited_order: list[str] = []
    visited_set: set[str] = set()
    failed_fetch_urls: list[str] = []
    discovered: list[DiscoveredProfessorSeed] = []

    while queue and len(visited_order) < limits.max_pages_per_seed:
        current = queue.popleft()
        if current.url in visited_set:
            continue
        visited_set.add(current.url)
        visited_order.append(current.url)

        try:
            html = fetch_html(current.url)
        except Exception:
            failed_fetch_urls.append(current.url)
            _enqueue_seed_fallback_pages(
                queue=queue,
                visited_set=visited_set,
                seed_url=seed.roster_url,
                current_url=current.url,
                current_depth=current.depth,
                department=current.department,
            )
            continue

        entries = extract_roster_entries(
            html=html,
            institution=institution,
            department=current.department,
            source_url=current.url,
        )
        if entries:
            discovered.extend(entries)
            continue

        if current.depth >= limits.max_depth:
            _enqueue_seed_fallback_pages(
                queue=queue,
                visited_set=visited_set,
                seed_url=seed.roster_url,
                current_url=current.url,
                current_depth=current.depth,
                department=current.department,
            )
            continue

        candidates = _bounded_candidates(
            seed_url=seed.roster_url,
            links=extract_roster_page_links(html, current.url),
            current_department=current.department,
            max_candidates=limits.max_candidate_links_per_page,
        )
        if not candidates:
            _enqueue_seed_fallback_pages(
                queue=queue,
                visited_set=visited_set,
                seed_url=seed.roster_url,
                current_url=current.url,
                current_depth=current.depth,
                department=current.department,
            )
        for candidate in candidates:
            if candidate.url not in visited_set:
                queue.append(
                    _PendingPage(
                        url=candidate.url,
                        depth=current.depth + 1,
                        department=candidate.department,
                    )
                )

    professors = _dedupe_professors(discovered)
    if professors:
        status = DiscoverySourceStatus(
            seed_url=seed.roster_url,
            institution=institution,
            department=_normalize_text(seed.department),
            status="resolved",
            reason="recursive_roster_discovery",
            error=None,
            visited_urls=visited_order,
            discovered_professor_count=len(professors),
        )
    elif failed_fetch_urls and len(failed_fetch_urls) == len(visited_order):
        status = DiscoverySourceStatus(
            seed_url=seed.roster_url,
            institution=institution,
            department=_normalize_text(seed.department),
            status="failed",
            reason="fetch_failed",
            error="; ".join(failed_fetch_urls),
            visited_urls=visited_order,
            discovered_professor_count=0,
        )
    else:
        status = DiscoverySourceStatus(
            seed_url=seed.roster_url,
            institution=institution,
            department=_normalize_text(seed.department),
            status="unresolved",
            reason="no_professor_entries_found",
            error=None,
            visited_urls=visited_order,
            discovered_professor_count=0,
        )
    return _SeedDiscovery(
        professors=professors,
        status=status,
        failed_fetch_urls=failed_fetch_urls,
    )


def _seed_entry_urls(seed_url: str) -> tuple[str, ...]:
    candidates = [seed_url]
    for fallback_url in _SEED_FALLBACK_URLS.get(seed_url, ()):
        if fallback_url not in candidates:
            candidates.append(fallback_url)
    return tuple(candidates)


def _enqueue_seed_fallback_pages(
    *,
    queue: deque[_PendingPage],
    visited_set: set[str],
    seed_url: str,
    current_url: str,
    current_depth: int,
    department: str | None,
) -> None:
    if current_depth != 0 or current_url != seed_url:
        return
    scheduled_urls = {pending.url for pending in queue}
    for fallback_url in _seed_entry_urls(seed_url)[1:]:
        if fallback_url in visited_set or fallback_url in scheduled_urls:
            continue
        queue.append(_PendingPage(url=fallback_url, depth=0, department=department))


def _bounded_candidates(
    seed_url: str,
    links: list[tuple[str, str]],
    current_department: str | None,
    max_candidates: int,
) -> list[_CandidatePage]:
    allowed_domains = set(get_allowed_registered_domains(seed_url))
    candidates: list[_CandidatePage] = []
    for url, label in links:
        if allowed_domains and get_registered_domain(url) not in allowed_domains:
            continue
        candidates.append(
            _CandidatePage(
                url=url,
                department=current_department or _normalize_department_label(label),
            )
        )
        if len(candidates) >= max_candidates:
            break
    return candidates


def _discover_sigs_seed(
    seed: ProfessorRosterSeed,
    fetch_json: FetchJson,
) -> _SeedDiscovery:
    endpoint = "https://www.sigs.tsinghua.edu.cn/_wp3services/generalQuery?queryObj=teacherHome"
    payload = {
        "siteId": 3,
        "pageIndex": 1,
        "rows": 999,
        "conditions": json.dumps(
            [{"conditions": [{"field": "published", "value": "1", "judge": "="}]}],
            ensure_ascii=False,
        ),
        "orders": json.dumps([{"field": "firstLetter", "type": "asc"}], ensure_ascii=False),
        "returnInfos": json.dumps(
            [
                {"field": "title", "name": "title"},
                {"field": "cnUrl", "name": "cnUrl"},
                {"field": "email", "name": "email"},
                {"field": "exField1", "name": "exField1"},
                {"field": "exField3", "name": "exField3"},
                {"field": "exField5", "name": "exField5"},
                {"field": "exField8", "name": "exField8"},
            ],
            ensure_ascii=False,
        ),
        "articleType": 1,
        "level": 1,
    }
    raw_response = fetch_json(endpoint, payload)
    data = raw_response.get("data", []) if isinstance(raw_response, dict) else []
    professors = _build_professor_seeds_from_records(
        records=data,
        institution=(seed.institution or "").strip() or "UNKNOWN_INSTITUTION",
        department=_normalize_text(seed.department),
        source_url=seed.roster_url,
        name_key="title",
        url_key="cnUrl",
    )
    status = DiscoverySourceStatus(
        seed_url=seed.roster_url,
        institution=(seed.institution or "").strip() or "UNKNOWN_INSTITUTION",
        department=_normalize_text(seed.department),
        status="resolved" if professors else "unresolved",
        reason="sigs_teacher_api" if professors else "sigs_teacher_api_empty",
        error=None,
        visited_urls=[seed.roster_url, endpoint],
        discovered_professor_count=len(professors),
    )
    return _SeedDiscovery(professors=professors, status=status, failed_fetch_urls=[])


def _discover_hit_seed(
    seed: ProfessorRosterSeed,
    fetch_json: FetchJson,
) -> _SeedDiscovery:
    root_url = "https://homepage.hit.edu.cn/"
    department_endpoint = urljoin(root_url, "sysBrowseShow/executeBrowseAllOfSchoolDepartSz.do")
    teacher_endpoint = urljoin(root_url, "sysBrowseShow/getUserInfoByDeptId.do")

    raw_departments = fetch_json(department_endpoint, {"id": "1", "campusId": "999960"})
    departments = _extract_json_list(raw_departments)
    professors: list[DiscoveredProfessorSeed] = []
    visited_urls = [seed.roster_url, department_endpoint]
    if departments:
        for department in departments:
            if not isinstance(department, dict):
                continue
            dept_id = str(department.get("id", "")).strip()
            if not dept_id or int(department.get("value", 0) or 0) <= 0:
                continue
            raw_teachers = fetch_json(
                teacher_endpoint,
                {"deptId": dept_id, "id": "1", "orderType": "1"},
            )
            visited_urls.append(f"{teacher_endpoint}?deptId={dept_id}")
            teachers = _extract_json_list(raw_teachers)
            if not teachers:
                continue
            professors.extend(
                _build_professor_seeds_from_records(
                    records=teachers,
                    institution=(seed.institution or "").strip() or "UNKNOWN_INSTITUTION",
                    department=_normalize_text(seed.department)
                    or _normalize_text(str(department.get("deptname", "")).strip()),
                    source_url=seed.roster_url,
                    name_key="userName",
                    url_key="url",
                    url_formatter=lambda value: urljoin(root_url, f"{value}?lang=zh"),
                    department_key="department",
                )
            )
    professors = _dedupe_professors(professors)
    status = DiscoverySourceStatus(
        seed_url=seed.roster_url,
        institution=(seed.institution or "").strip() or "UNKNOWN_INSTITUTION",
        department=_normalize_text(seed.department),
        status="resolved" if professors else "unresolved",
        reason="hit_teacher_api" if professors else "hit_teacher_api_empty",
        error=None,
        visited_urls=visited_urls,
        discovered_professor_count=len(professors),
    )
    return _SeedDiscovery(professors=professors, status=status, failed_fetch_urls=[])


def _build_professor_seeds_from_records(
    records: list[object],
    institution: str,
    department: str | None,
    source_url: str,
    name_key: str,
    url_key: str,
    url_formatter: Callable[[str], str] | None = None,
    department_key: str | None = None,
) -> list[DiscoveredProfessorSeed]:
    discovered: list[DiscoveredProfessorSeed] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        raw_name = _normalize_text(str(record.get(name_key, "")).strip())
        raw_url = _normalize_text(str(record.get(url_key, "")).strip())
        if not raw_name or not raw_url:
            continue
        profile_url = url_formatter(raw_url) if url_formatter else urljoin(source_url, raw_url)
        discovered.append(
            DiscoveredProfessorSeed(
                name=raw_name,
                institution=institution,
                department=_normalize_text(str(record.get(department_key, "")).strip())
                if department_key and record.get(department_key)
                else department,
                profile_url=profile_url,
                source_url=source_url,
            )
        )
    return _dedupe_professors(discovered)


def _extract_json_list(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        items = payload.get("list")
        if isinstance(items, list):
            return items
    return []


def _dedupe_professors(
    professors: list[DiscoveredProfessorSeed],
) -> list[DiscoveredProfessorSeed]:
    deduped: dict[tuple[str, str, str], DiscoveredProfessorSeed] = {}
    for professor in professors:
        key = (
            _normalize_text(professor.name) or "",
            _normalize_text(professor.institution) or "",
            _normalize_text(professor.department) or "",
        )
        deduped.setdefault(key, professor)
    return list(deduped.values())


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.replace("\u3000", " ").split()).strip()
    return normalized or None


def _normalize_department_label(label: str | None) -> str | None:
    normalized = _normalize_text(label)
    if not normalized or "研究生院" in normalized:
        return None
    if any(token in normalized for token in ("学院", "系", "中心", "研究所", "实验室", "学部", "书院")):
        return normalized
    return None


def _is_sigs_seed(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() == "www.sigs.tsinghua.edu.cn" and parsed.path.endswith(
        "/7644/list.htm"
    )


def _is_hit_seed(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() == "homepage.hit.edu.cn" and "school-dept" in parsed.path
