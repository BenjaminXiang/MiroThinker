from __future__ import annotations

import atexit
import contextvars
import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
import requests

from .name_selection import is_obvious_non_person_name, is_same_person_name_variant, normalize_name_key
from .profile import extract_professor_profile
from .models import DiscoveredProfessorSeed, ProfessorRosterSeed
from .roster import (
    extract_cuhk_markdown_profile_links,
    extract_cuhk_profile_links,
    extract_roster_entries,
    extract_roster_page_links,
)

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
    "http://sa.sysu.edu.cn/zh-hans/teacher/faculty": (
        "https://ab.sysu.edu.cn/zh-hans/teacher/faculty",
    ),
    "https://sa.sysu.edu.cn/zh-hans/teacher/faculty": (
        "https://ab.sysu.edu.cn/zh-hans/teacher/faculty",
    ),
}
_SEED_OFFICIAL_DOMAIN_SUFFIXES: dict[str, tuple[str, ...]] = {
    "https://www.pkusz.edu.cn/szdw.htm": ("pkusz.edu.cn", "pku.edu.cn"),
    "http://sa.sysu.edu.cn/zh-hans/teacher/faculty": ("sysu.edu.cn",),
    "https://sa.sysu.edu.cn/zh-hans/teacher/faculty": ("sysu.edu.cn",),
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
_BROWSER_FIRST_HOST_SUFFIXES: tuple[str, ...] = ("cuhk.edu.cn",)
_BROWSER_FIRST_HOSTS: set[str] = {
    "med.szu.edu.cn",
}
_BROWSER_FIRST_PATH_HINTS: tuple[str, ...] = (
    "teacher-search",
)
_learned_browser_first_hosts: set[str] = set()
_LEARNED_BROWSER_FIRST_LOCK = threading.Lock()
_learned_reader_first_hosts: set[str] = set()
_LEARNED_READER_FIRST_LOCK = threading.Lock()
_DISCOVERY_FETCH_POLICY_STATE: contextvars.ContextVar[tuple[set[str], set[str]] | None] = contextvars.ContextVar(
    "discovery_fetch_policy_state",
    default=None,
)
_THREAD_LOCAL_PLAYWRIGHT = threading.local()
_PLAYWRIGHT_RUNTIME_REGISTRY: list[_PlaywrightThreadState] = []
_SHARED_BROWSER_LOCK = threading.Lock()
_PLAYWRIGHT_CONTEXT_OPTIONS = {
    "locale": "zh-CN",
    "viewport": {"width": 1440, "height": 2200},
    "user_agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "extra_http_headers": {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    },
}
_PERSONAL_HOMEPAGE_NAV_HINTS = (
    "teaching",
    "research",
    "presentation",
    "presentations",
    "service",
    "bio",
    "cv",
    "publications",
)


_DIRECT_PROFILE_CONTENT_CLASS_HINTS = (
    "page_content_teacher",
    "content_teacher_box",
    "v_news_content",
    "teacher_inner",
    "introduce-main",
    "introduce",
    "message-left",
    "message-right",
    "teachercontent",
    "page_content_detail",
)
_DIRECT_PROFILE_TEXT_HINTS = (
    "研究方向",
    "研究领域",
    "电子邮箱",
    "邮箱",
    "email",
    "博士生导师",
    "研究助理教授",
    "助理教授",
    "副教授",
    "讲席教授",
)


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
    fetch_policy: str = "direct_first"
    fetch_method: str | None = None


@dataclass(slots=True)
class _PlaywrightThreadState:
    thread_id: int
    playwright: object
    browser: object
    render_lock: threading.Lock


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
    token = _DISCOVERY_FETCH_POLICY_STATE.set((set(), set()))
    try:
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
                elif _is_cuhk_seed(seed.roster_url):
                    try:
                        result = _discover_cuhk_seed(seed, html_fetcher, applied_limits)
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
    finally:
        _DISCOVERY_FETCH_POLICY_STATE.reset(token)


def fetch_html_with_fallback(
    url: str,
    timeout: float = 20.0,
    request_get: Callable[[str, float], requests.Response] | None = None,
    browser_fetch: Callable[[str, float], str] | None = None,
    reader_fetch: Callable[[str, float], str] | None = None,
) -> HtmlFetchResult:
    fetch_policy = _resolve_fetch_policy(url)
    use_cache = request_get is None and browser_fetch is None and reader_fetch is None
    if use_cache:
        cached_html = _load_cached_html(url)
        if cached_html is not None and not _should_refresh_cached_html(url, cached_html):
            return HtmlFetchResult(
                html=cached_html,
                used_browser=False,
                blocked_by_anti_scraping=False,
                request_error=None,
                browser_error=None,
                fetch_policy=fetch_policy,
                fetch_method="cache",
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
                if _is_blocked_response(200, rendered_html):
                    browser_error = "browser returned blocked page"
                else:
                    if use_cache:
                        _store_cached_html(url, rendered_html)
                    return HtmlFetchResult(
                        html=rendered_html,
                        used_browser=True,
                        blocked_by_anti_scraping=True,
                        request_error=request_error,
                        browser_error=None,
                        fetch_policy=fetch_policy,
                        fetch_method="browser",
                    )
        return HtmlFetchResult(
            html=None,
            used_browser=False,
            blocked_by_anti_scraping=True,
            request_error=request_error,
            browser_error=browser_error,
            fetch_policy=fetch_policy,
            fetch_method=None,
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
                fetch_policy=fetch_policy,
                fetch_method=None,
            )
        if request_error or browser_error:
            _remember_reader_first_host(url)
        return HtmlFetchResult(
            html=rendered_text,
            used_browser=False,
            blocked_by_anti_scraping=True,
            request_error=request_error,
            browser_error=browser_error,
            fetch_policy=fetch_policy,
            fetch_method="reader",
        )

    def _fetch_with_direct_request() -> HtmlFetchResult | None:
        nonlocal request_error
        try:
            response = getter(url, timeout)
        except requests.RequestException as exc:
            request_error = str(exc)
            _remember_browser_first_host(url)
            return None

        html = _decode_response_text(response)
        blocked = _is_blocked_response(response.status_code, html)

        if blocked:
            if response.status_code >= 400:
                request_error = f"{response.status_code} Client Error"
            else:
                request_error = f"{response.status_code} blocked (anti-scraping detected)"
            _remember_browser_first_host(url)
            return None

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            request_error = str(exc)
            return None
        if not html.strip():
            request_error = "empty response body"
            return None
        if use_cache:
            _store_cached_html(url, html)
        return HtmlFetchResult(
            html=html,
            used_browser=False,
            blocked_by_anti_scraping=False,
            request_error=None,
            browser_error=None,
            fetch_policy=fetch_policy,
            fetch_method="direct",
        )

    if fetch_policy == "browser_first":
        browser_result = _fetch_with_browser_fallback()
        if browser_result.html is not None:
            return browser_result
        direct_result = _fetch_with_direct_request()
        if direct_result is not None:
            return direct_result
        return _fetch_with_reader_fallback(browser_result.browser_error)

    if fetch_policy == "reader_first":
        reader_result = _fetch_with_reader_fallback(None)
        if reader_result.html is not None:
            return reader_result
        direct_result = _fetch_with_direct_request()
        if direct_result is not None:
            return direct_result
        browser_result = _fetch_with_browser_fallback()
        if browser_result.html is not None:
            return browser_result
        composite_error = " | ".join(
            part
            for part in (reader_result.browser_error, browser_result.browser_error)
            if part
        )
        return HtmlFetchResult(
            html=None,
            used_browser=False,
            blocked_by_anti_scraping=True,
            request_error=request_error,
            browser_error=composite_error or None,
            fetch_policy=fetch_policy,
            fetch_method=None,
        )

    direct_result = _fetch_with_direct_request()
    if direct_result is not None:
        return direct_result
    browser_result = _fetch_with_browser_fallback()
    if browser_result.html is not None:
        return browser_result
    return _fetch_with_reader_fallback(browser_result.browser_error)


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


def _should_refresh_cached_html(url: str, content: str) -> bool:
    path = urlparse(url).path.lower()
    lowered = content.lower()
    if "teacher-search" in path and lowered.startswith("title:"):
        return "/teacher/" not in lowered
    return False


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
    except Exception as exc:  # noqa: BLE001 - import/runtime surfaces upstream.
        raise RuntimeError(f"playwright unavailable: {exc}") from exc

    timeout_ms = int(timeout * 1000)
    for attempt in range(2):
        try:
            state = _get_shared_playwright_state()
            with state.render_lock:
                context = state.browser.new_context(**_PLAYWRIGHT_CONTEXT_OPTIONS)
                try:
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
                    except PlaywrightError:
                        pass
                    try:
                        page.mouse.wheel(0, 1200)
                        page.wait_for_timeout(350)
                    except PlaywrightError:
                        pass
                    return page.content()
                finally:
                    context.close()
        except PlaywrightError as exc:
            if attempt == 0 and _looks_like_stale_playwright_browser_error(exc):
                _shutdown_shared_playwright_browser(threading.get_ident())
                continue
            raise RuntimeError(f"playwright browser runtime unavailable: {exc}") from exc
    raise RuntimeError("playwright browser runtime unavailable: stale browser retry exhausted")


def _current_fetch_policy_state() -> tuple[set[str], set[str]]:
    state = _DISCOVERY_FETCH_POLICY_STATE.get()
    if state is not None:
        return state
    return _learned_browser_first_hosts, _learned_reader_first_hosts


def _snapshot_global_fetch_policy_state() -> tuple[set[str], set[str]]:
    with _LEARNED_BROWSER_FIRST_LOCK:
        learned_browser_hosts = set(_learned_browser_first_hosts)
    with _LEARNED_READER_FIRST_LOCK:
        learned_reader_hosts = set(_learned_reader_first_hosts)
    return learned_browser_hosts, learned_reader_hosts


def _looks_like_stale_playwright_browser_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "has been closed",
            "browser has been closed",
            "target closed",
            "connection closed",
            "context closed",
        )
    )


def _resolve_fetch_policy(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    path = urlparse(url).path.lower()
    registered_domain = get_registered_domain(url)
    state = _DISCOVERY_FETCH_POLICY_STATE.get()
    if state is None:
        learned_browser_hosts, learned_reader_hosts = _snapshot_global_fetch_policy_state()
    else:
        learned_browser_hosts, learned_reader_hosts = state
    if hostname in learned_reader_hosts:
        return "reader_first"
    if hostname in _BROWSER_FIRST_HOSTS:
        return "browser_first"
    if registered_domain and any(
        registered_domain.endswith(suffix) for suffix in _BROWSER_FIRST_HOST_SUFFIXES
    ):
        return "browser_first"
    if any(hint in path for hint in _BROWSER_FIRST_PATH_HINTS):
        return "browser_first"
    if hostname in learned_browser_hosts:
        return "browser_first"
    return "direct_first"


def _reset_learned_fetch_policy_state() -> None:
    with _LEARNED_BROWSER_FIRST_LOCK:
        _learned_browser_first_hosts.clear()
    with _LEARNED_READER_FIRST_LOCK:
        _learned_reader_first_hosts.clear()


def _remember_browser_first_host(url: str) -> None:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return
    state = _DISCOVERY_FETCH_POLICY_STATE.get()
    if state is not None:
        state[0].add(hostname)
        return
    with _LEARNED_BROWSER_FIRST_LOCK:
        _learned_browser_first_hosts.add(hostname)


def _remember_reader_first_host(url: str) -> None:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return
    state = _DISCOVERY_FETCH_POLICY_STATE.get()
    if state is not None:
        state[1].add(hostname)
        return
    with _LEARNED_READER_FIRST_LOCK:
        _learned_reader_first_hosts.add(hostname)


def _get_shared_playwright_state() -> _PlaywrightThreadState:
    state = getattr(_THREAD_LOCAL_PLAYWRIGHT, "state", None)
    if state is not None:
        return state
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001 - import/runtime surfaces upstream.
        raise RuntimeError(f"playwright unavailable: {exc}") from exc
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(headless=True)
    except Exception:
        try:
            playwright.stop()
        except Exception:
            pass
        raise
    state = _PlaywrightThreadState(
        thread_id=threading.get_ident(),
        playwright=playwright,
        browser=browser,
        render_lock=threading.Lock(),
    )
    with _SHARED_BROWSER_LOCK:
        existing = getattr(_THREAD_LOCAL_PLAYWRIGHT, "state", None)
        if existing is not None:
            try:
                browser.close()
            except Exception:
                pass
            try:
                playwright.stop()
            except Exception:
                pass
            return existing
        _THREAD_LOCAL_PLAYWRIGHT.state = state
        _PLAYWRIGHT_RUNTIME_REGISTRY.append(state)
    return state


def _get_shared_playwright_browser():
    return _get_shared_playwright_state().browser


def _shutdown_shared_playwright_browser(thread_id: int | None = None) -> None:
    with _SHARED_BROWSER_LOCK:
        current_state = getattr(_THREAD_LOCAL_PLAYWRIGHT, "state", None)
        if thread_id is None:
            runtimes = list(_PLAYWRIGHT_RUNTIME_REGISTRY)
            _PLAYWRIGHT_RUNTIME_REGISTRY.clear()
            if current_state is not None:
                delattr(_THREAD_LOCAL_PLAYWRIGHT, "state")
        else:
            runtimes = [state for state in _PLAYWRIGHT_RUNTIME_REGISTRY if state.thread_id == thread_id]
            _PLAYWRIGHT_RUNTIME_REGISTRY[:] = [
                state for state in _PLAYWRIGHT_RUNTIME_REGISTRY if state.thread_id != thread_id
            ]
            if current_state is not None and current_state.thread_id == thread_id:
                delattr(_THREAD_LOCAL_PLAYWRIGHT, "state")
    for state in runtimes:
        try:
            state.browser.close()
        except Exception:
            pass
        try:
            state.playwright.stop()
        except Exception:
            pass


def _shutdown_current_thread_playwright_browser() -> None:
    _shutdown_shared_playwright_browser(threading.get_ident())


atexit.register(_shutdown_current_thread_playwright_browser)


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
    seed_label = _normalize_text(seed.label)

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

        if (
            current.depth == 0
            and current.url == seed.roster_url
            and not seed_label
        ):
            homepage_name = _extract_person_name_from_root_homepage(
                current.url,
                html,
                institution=institution,
                department=seed.department,
            )
            if homepage_name:
                professors = [
                    DiscoveredProfessorSeed(
                        name=homepage_name,
                        institution=institution,
                        department=_normalize_text(seed.department),
                        profile_url=seed.roster_url,
                        source_url=seed.roster_url,
                    )
                ]
                status = DiscoverySourceStatus(
                    seed_url=seed.roster_url,
                    institution=institution,
                    department=_normalize_text(seed.department),
                    status="resolved",
                    reason="direct_profile_homepage",
                    error=None,
                    visited_urls=[seed.roster_url],
                    discovered_professor_count=1,
                )
                return _SeedDiscovery(
                    professors=professors,
                    status=status,
                    failed_fetch_urls=failed_fetch_urls,
                )

        direct_seed_name, direct_seed_reason = _resolve_direct_profile_seed_after_fetch(
            seed=seed,
            institution=institution,
            current=current,
            html=html,
            seed_label=seed_label,
        )
        if direct_seed_name:
            professors = [
                DiscoveredProfessorSeed(
                    name=direct_seed_name,
                    institution=institution,
                    department=_normalize_text(seed.department),
                    profile_url=seed.roster_url,
                    source_url=seed.roster_url,
                )
            ]
            status = DiscoverySourceStatus(
                seed_url=seed.roster_url,
                institution=institution,
                department=_normalize_text(seed.department),
                status="resolved",
                reason=direct_seed_reason,
                error=None,
                visited_urls=[seed.roster_url],
                discovered_professor_count=1,
            )
            return _SeedDiscovery(
                professors=professors,
                status=status,
                failed_fetch_urls=failed_fetch_urls,
            )

        entries = extract_roster_entries(
            html=html,
            institution=institution,
            department=current.department,
            source_url=current.url,
        )
        if entries:
            discovered.extend(entries)
            continue

        prioritize_seed_fallback = _should_prioritize_seed_fallback(
            seed_url=seed.roster_url,
            current_url=current.url,
            current_depth=current.depth,
            html=html,
        )
        if prioritize_seed_fallback:
            _enqueue_seed_fallback_pages(
                queue=queue,
                visited_set=visited_set,
                seed_url=seed.roster_url,
                current_url=current.url,
                current_depth=current.depth,
                department=current.department,
            )

        if current.depth >= limits.max_depth:
            if not prioritize_seed_fallback:
                _enqueue_seed_fallback_pages(
                    queue=queue,
                    visited_set=visited_set,
                    seed_url=seed.roster_url,
                    current_url=current.url,
                    current_depth=current.depth,
                    department=current.department,
                )
            continue

        if prioritize_seed_fallback:
            candidates: list[_CandidatePage] = []
        else:
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


def _path_looks_like_roster_seed(path: str) -> bool:
    lowered = path.lower()
    return any(token in lowered for token in ("/teacher", "/teachers", "/faculty", "/szdw", "/jsjj"))


def _should_prioritize_seed_fallback(
    *,
    seed_url: str,
    current_url: str,
    current_depth: int,
    html: str,
) -> bool:
    if current_depth != 0 or current_url != seed_url:
        return False
    if seed_url not in _SEED_FALLBACK_URLS:
        return False
    seed_path = urlparse(seed_url).path.rstrip("/")
    if not _path_looks_like_roster_seed(seed_path):
        return False
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    canonical_tag = soup.find("link", rel=lambda value: isinstance(value, str) and value.lower() == "canonical")
    canonical_href = canonical_tag.get("href", "") if canonical_tag else ""
    canonical_path = urlparse(str(canonical_href)).path.rstrip("/")
    if not canonical_path or canonical_path == seed_path:
        return False
    if _path_looks_like_roster_seed(canonical_path):
        return False
    return "首页" in title or title.startswith("home")


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


def _discover_cuhk_seed(
    seed: ProfessorRosterSeed,
    fetch_html: FetchHtml,
    limits: DiscoveryLimits | None = None,
) -> _SeedDiscovery:
    institution = (seed.institution or "").strip() or "UNKNOWN_INSTITUTION"
    department = _normalize_text(seed.department)
    professors: list[DiscoveredProfessorSeed] = []
    visited_urls: list[str] = []
    seen_profile_urls: set[str] = set()
    applied_limits = limits or DiscoveryLimits()

    for page_index in range(applied_limits.max_pages_per_seed):
        page_url = _cuhk_page_url(seed.roster_url, page_index)
        visited_urls.append(page_url)
        html = fetch_html(page_url)
        soup = BeautifulSoup(html, "html.parser")
        profile_links = extract_cuhk_profile_links(soup)
        if not profile_links:
            profile_links = extract_cuhk_markdown_profile_links(html)
        if not profile_links:
            break
        new_links_found = False
        for raw_url, raw_name in profile_links:
            name = _normalize_text(raw_name)
            if not name:
                continue
            profile_url = urljoin(page_url, raw_url)
            if profile_url in seen_profile_urls:
                continue
            seen_profile_urls.add(profile_url)
            new_links_found = True
            professors.append(
                DiscoveredProfessorSeed(
                    name=name,
                    institution=institution,
                    department=department,
                    profile_url=profile_url,
                    source_url=page_url,
                )
            )
        if not new_links_found:
            break

    professors = _dedupe_professors(professors)
    status = DiscoverySourceStatus(
        seed_url=seed.roster_url,
        institution=institution,
        department=department,
        status="resolved" if professors else "unresolved",
        reason="cuhk_teacher_search" if professors else "cuhk_teacher_search_empty",
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


def _looks_like_direct_profile_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    if not path:
        return False
    if any(
        token in path
        for token in (
            "list",
            "index",
            "search",
            "letter",
            "directory",
            "roster",
            "faculty_members",
            "jsjj",
            "szdw",
            "szll",
            "jsml",
            "jxjs",
            "qbjs",
            "news",
            "notice",
            "notices",
            "event",
            "events",
            "article",
            "articles",
        )
    ):
        return False
    leaf = path.rsplit("/", 1)[-1]
    stem = leaf.rsplit(".", 1)[0]
    if any(
        token in path
        for token in (
            "teacher/",
            "teachers/",
            "faculty/",
            "faculties/",
            "profile/",
            "people/",
        )
    ):
        if stem in {
            "teacher",
            "teachers",
            "faculty",
            "faculties",
            "profile",
            "profiles",
            "people",
            "staff",
            "team",
            "group",
            "list",
            "index",
            "professor",
            "associate-professor",
            "assistant-professor",
            "full-time",
            "part-time",
            "adjunct",
            "emeritus",
            "famous",
            "shuangpin",
        }:
            return False
        return True
    if not leaf.endswith((".htm", ".html")):
        return False
    blocked_leafs = {
        "list.htm",
        "list.html",
        "index.htm",
        "index.html",
        "about.htm",
        "about.html",
        "contact.htm",
        "contact.html",
        "news.htm",
        "news.html",
        "szll.htm",
        "szll.html",
        "jsml.htm",
        "jsml.html",
        "jxjs.htm",
        "jxjs.html",
        "qbjs.htm",
        "qbjs.html",
    }
    return leaf not in blocked_leafs and not path.startswith("/info/") and any(char.isdigit() for char in stem)


def _looks_like_labeled_direct_profile_seed_url(url: str) -> bool:
    if _looks_like_direct_profile_url(url):
        return True
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    if not path or not path.endswith((".htm", ".html")):
        return False
    if any(
        token in path
        for token in (
            "list",
            "index",
            "search",
            "letter",
            "directory",
            "roster",
            "faculty_members",
            "jsjj",
            "szdw",
            "szll",
            "jsml",
            "jxjs",
            "qbjs",
            "news",
            "notice",
            "notices",
            "event",
            "events",
            "article",
            "articles",
        )
    ):
        return False
    leaf = path.rsplit("/", 1)[-1]
    stem = leaf.rsplit(".", 1)[0]
    if stem not in {"main", "home", "homepage", "profile"}:
        return False
    return path.count("/") >= 2 and not path.startswith("/info/")


def _looks_like_root_homepage_direct_profile_seed(
    url: str,
    *,
    seed_label: str,
    institution: str | None,
    department: str | None,
) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.strip()
    if path not in ("", "/"):
        return False
    if parsed.query or parsed.fragment:
        return False
    registered_domain = get_registered_domain(url)
    if hostname == registered_domain:
        return False
    subdomain = hostname[: -(len(registered_domain) + 1)] if registered_domain and hostname.endswith(f".{registered_domain}") else ""
    first_label = subdomain.split(".", 1)[0] if subdomain else ""
    if first_label in {"", "www", "faculty", "teacher", "teachers", "people", "profile", "home"}:
        return False

    normalized_label = _normalize_text(seed_label)
    if not normalized_label or is_obvious_non_person_name(normalized_label):
        return False

    label_key = normalize_name_key(normalized_label)
    if not label_key:
        return False
    context_keys = {
        normalize_name_key(institution),
        normalize_name_key(department),
    }
    if label_key in context_keys:
        return False

    if re.fullmatch(
        r"[\u4e00-\u9fff·]{2,4}(?:院士|教授|副教授|讲师|研究员|副研究员|助理教授|老师|博士)?",
        normalized_label,
    ):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z ,.'-]{1,39}", normalized_label) and (
        " " in normalized_label or "," in normalized_label
    ):
        return True
    return False


def _looks_like_unlabeled_direct_profile_seed_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").lower()
    if not path:
        return False
    return any(
        marker in path
        for marker in (
            "/teacher/",
            "/teachers/",
            "/faculty/",
            "/faculties/",
            "/profile/",
            "/people/",
        )
    )


def _profile_detail_marker_score(html: str) -> int:
    lowered = html.lower()
    score = sum(1 for hint in _DIRECT_PROFILE_CONTENT_CLASS_HINTS if hint in lowered)
    score += sum(1 for hint in _DIRECT_PROFILE_TEXT_HINTS if hint.casefold() in lowered)
    return score


def _extract_name_from_profile_like_detail_page(
    *,
    url: str,
    html: str,
    institution: str | None,
    department: str | None,
) -> str | None:
    if _profile_detail_marker_score(html) < 1:
        return None
    extracted = extract_professor_profile(
        html,
        source_url=url,
        institution=institution,
        department=department,
    )
    candidate = _normalize_text(extracted.name)
    if not candidate or is_obvious_non_person_name(candidate):
        return None
    return candidate


def _resolve_direct_profile_seed_after_fetch(
    *,
    seed: ProfessorRosterSeed,
    institution: str,
    current: _PendingPage,
    html: str,
    seed_label: str,
) -> tuple[str | None, str | None]:
    if current.depth != 0 or current.url != seed.roster_url:
        return None, None

    direct_profile_like = (
        (seed_label and _looks_like_labeled_direct_profile_seed_url(seed.roster_url))
        or (
            _looks_like_direct_profile_url(seed.roster_url)
            and (seed_label or _looks_like_unlabeled_direct_profile_seed_url(seed.roster_url))
        )
    )
    root_homepage_like = seed_label and _looks_like_root_homepage_direct_profile_seed(
        seed.roster_url,
        seed_label=seed_label,
        institution=institution,
        department=seed.department,
    )
    if seed_label and (direct_profile_like or root_homepage_like):
        return seed_label, "direct_profile_seed_fetched"

    profile_like_name = _extract_name_from_profile_like_detail_page(
        url=seed.roster_url,
        html=html,
        institution=institution,
        department=seed.department,
    )
    if seed_label and profile_like_name and is_same_person_name_variant(seed_label, profile_like_name):
        return seed_label, "direct_profile_seed_fetched"
    if not seed_label and profile_like_name:
        return profile_like_name, "direct_profile_seed_fetched"

    if not seed_label and _looks_like_direct_profile_url(seed.roster_url):
        soup = BeautifulSoup(html, "html.parser")
        title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
        candidate = _extract_person_name_from_title_text(
            title_text,
            institution=institution,
            department=seed.department,
        )
        if candidate:
            return candidate, "direct_profile_seed_fetched"

    if not seed_label:
        homepage_name = _extract_person_name_from_root_homepage(
            seed.roster_url,
            html,
            institution=institution,
            department=seed.department,
        )
        if homepage_name:
            return homepage_name, "direct_profile_homepage"

    return None, None


def _extract_person_name_from_root_homepage(
    url: str,
    html: str,
    *,
    institution: str | None,
    department: str | None,
) -> str | None:
    parsed = urlparse(url)
    if parsed.path.strip() not in ("", "/"):
        return None
    if parsed.query or parsed.fragment:
        return None

    lowered_html = html.lower()
    nav_hint_count = sum(hint in lowered_html for hint in _PERSONAL_HOMEPAGE_NAV_HINTS)
    if nav_hint_count < 2:
        return None

    soup = BeautifulSoup(html, "html.parser")
    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
    candidate = _extract_person_name_from_title_text(
        title_text,
        institution=institution,
        department=department,
    )
    if candidate:
        return candidate

    return None


def _extract_person_name_from_title_text(
    title_text: str,
    *,
    institution: str | None,
    department: str | None,
) -> str | None:
    normalized_title = _normalize_text(title_text)
    if not normalized_title:
        return None

    for separator in ("@", "-", "_", "|", "－", "—"):
        if separator not in normalized_title:
            continue
        prefix = _normalize_text(normalized_title.split(separator, 1)[0])
        if _looks_like_person_name_text(prefix):
            return prefix

    for context_text in (institution, department):
        normalized_context = _normalize_text(context_text or "")
        if normalized_context and normalized_title.endswith(normalized_context):
            prefix = _normalize_text(normalized_title[: -len(normalized_context)])
            if _looks_like_person_name_text(prefix):
                return prefix

    if _looks_like_person_name_text(normalized_title):
        return normalized_title
    return None


def _looks_like_person_name_text(value: str | None) -> bool:
    normalized = _normalize_text(value)
    if not normalized or is_obvious_non_person_name(normalized):
        return False
    if re.fullmatch(
        r"[\u4e00-\u9fff·]{2,4}(?:院士|教授|副教授|讲师|研究员|副研究员|助理教授|老师|博士)?",
        normalized,
    ):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z ,.'-]{1,39}", normalized) and (
        " " in normalized or "," in normalized
    ):
        return True
    return False


def _cuhk_page_url(seed_url: str, page_index: int) -> str:
    parsed = urlparse(seed_url)
    if page_index == 0:
        return seed_url
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "page"
    ]
    query_items.append(("page", str(page_index)))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def _is_sigs_seed(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() == "www.sigs.tsinghua.edu.cn" and parsed.path.endswith(
        "/7644/list.htm"
    )


def _is_hit_seed(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() == "homepage.hit.edu.cn" and "school-dept" in parsed.path


def _is_cuhk_seed(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname.endswith("cuhk.edu.cn") and "teacher-search" in parsed.path
