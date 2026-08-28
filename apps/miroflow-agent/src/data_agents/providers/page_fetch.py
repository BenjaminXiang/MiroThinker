"""Bounded direct page fetch with BeautifulSoup main-text extraction.

The serving Web lane uses this to deepen high-quality search results: fetch the
page itself and ground the answer in its actual content instead of a thin
snippet. No external reader service is required (the deployment network cannot
reach r.jina.ai); everything degrades to the original snippet on any failure.

Fetching is tiered: `create_tiered_page_fetcher` keeps the direct httpx+BS4
fetch as tier 0 and only escalates thin or blocked results (JS shells, access
gates) to a lazily-started headless Chromium tier 1. Headless failures fall
back to the tier-0 result, preserving the snippet semantics.
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic
from typing import Any, Callable, Protocol, cast

from bs4 import BeautifulSoup
import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "form",
    "aside",
    "iframe",
    "svg",
    "button",
    "select",
)
_MAIN_SELECTORS = (
    "article",
    "main",
    "[role='main']",
    ".article",
    ".article-content",
    ".entry-content",
    ".post-content",
    ".content",
)
_MIN_TEXT_CHARS = 40


def extract_main_text(html: bytes | str, *, max_chars: int = 3000) -> str | None:
    """Extract bounded main text from an HTML document."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = None
    for selector in _MAIN_SELECTORS:
        root = soup.select_one(selector)
        if root is not None:
            break
    if root is None:
        root = soup.body or soup
    text = re.sub(r"\s+", " ", root.get_text(" ", strip=True)).strip()
    if len(text) < _MIN_TEXT_CHARS:
        return None
    return text[:max_chars]


def fetch_page_text(
    url: str,
    *,
    timeout: float = 5.0,
    max_bytes: int = 1_048_576,
    max_chars: int = 3000,
    client: Any | None = None,
) -> str | None:
    """Fetch one page and return bounded main text; None on any failure."""
    if not url.startswith(("http://", "https://")):
        return None
    try:
        if client is not None:
            response = client.get(url, timeout=timeout)
        else:
            with httpx.Client(
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                max_redirects=3,
                trust_env=False,
                timeout=timeout,
            ) as session:
                response = session.get(url)
        if response.status_code != 200:
            return None
        content_type = response.headers.get("content-type", "").casefold()
        if content_type and "html" not in content_type:
            return None
        return extract_main_text(response.content[:max_bytes], max_chars=max_chars)
    except Exception:
        return None


_MIN_RICH_TEXT_CHARS = 400
_SCRIPT_RATIO_LIMIT = 0.6
_BROWSER_TEXT_LIMIT = 8000
_BLOCK_MARKERS = (
    "访问验证",
    "安全验证",
    "请开启JavaScript",
    "请开启 JavaScript",
    "403 Forbidden",
    "Too Many Requests",
)
_SCRIPT_RE = re.compile(r"(?s)<script[^>]*>.*?</script>")


def _is_thin_or_blocked(html_or_text: str | None) -> bool:
    """Decide whether a tier-0 result is too thin or blocked to keep.

    The input is whatever the direct fetcher returned: either extracted main
    text (the real `fetch_page_text`) or a raw shell page (JS app shells and
    access gates that slipped past extraction). None, near-empty text, known
    block markers, or a page dominated by <script> markup all count as thin.
    """
    if html_or_text is None:
        return True
    if any(marker in html_or_text for marker in _BLOCK_MARKERS):
        return True
    if len(html_or_text.strip()) < _MIN_RICH_TEXT_CHARS:
        return True
    script_chars = sum(len(match.group(0)) for match in _SCRIPT_RE.finditer(html_or_text))
    return script_chars / len(html_or_text) > _SCRIPT_RATIO_LIMIT


class _PlaywrightPagePool:
    """Lazily-started headless Chromium pinned to one dedicated thread.

    Playwright's sync dispatcher is bound to the thread that started it, while
    the serving Web lane calls the fetcher from a shared thread pool. Every
    browser operation is therefore submitted to a single dedicated worker, so
    T1 throughput is one page at a time by design (bounded by the 5s page
    timeout). A browser that fails to launch is never retried; tier 0 keeps
    serving alone thereafter.
    """

    def __init__(self, browser_factory: Callable[[], Any] | None = None) -> None:
        self._browser_factory = browser_factory
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._launch_failed = False
        self._lock = Lock()
        self._t1 = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="canonical-v2-tiered-fetch",
        )

    def _start_browser(self) -> Any:
        if self._browser_factory is not None:
            return self._browser_factory()
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            playwright.stop()  # do not leak the driver when launch fails
            raise
        self._playwright = playwright
        return browser

    def _browser_instance(self) -> Any:
        with self._lock:
            if self._browser is None:
                if self._launch_failed:
                    raise RuntimeError("headless Chromium launch previously failed")
                try:
                    self._browser = self._start_browser()
                except Exception:
                    self._launch_failed = True
                    raise
        return self._browser

    def _fetch_on_t1(self, url: str, *, timeout_ms: int) -> str | None:
        page = self._browser_instance().new_page()
        try:
            page.set_default_timeout(timeout_ms)
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            text = page.eval_on_selector("body", "el => el.innerText")
        finally:
            close = getattr(page, "close", None)
            if callable(close):
                close()
        if not isinstance(text, str) or not text.strip():
            return None
        return text.strip()[:_BROWSER_TEXT_LIMIT]

    def fetch(self, url: str, *, timeout_ms: int = 5000) -> str | None:
        future = self._t1.submit(self._fetch_on_t1, url, timeout_ms=timeout_ms)
        return future.result()

    def warm(self, timeout: float = 10.0) -> bool:
        """Start the browser on the dedicated thread without poisoning retries.

        A warm-up failure must not set ``_launch_failed``: the real fetch path
        stays able to retry the launch on demand.  Idempotent once running.
        """

        def start_once() -> Any:
            with self._lock:
                if self._browser is not None:
                    return self._browser
                if self._launch_failed:
                    raise RuntimeError("headless Chromium launch previously failed")
                try:
                    self._browser = self._start_browser()
                except Exception:
                    # Warm-up must not poison the real fetch path: only the
                    # fetch-side _browser_instance marks the launch failed.
                    raise
            return self._browser

        future = self._t1.submit(start_once)
        try:
            future.result(timeout=timeout)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("headless Chromium warm-up failed: %s", exc)
            return False


def create_tiered_page_fetcher(
    *,
    browser_factory: Callable[[], Any] | None = None,
    direct_fetcher: Callable[[str], str | None] | None = None,
) -> "TieredPageFetcher":
    """T0 direct fetch with a T1 headless-Chromium fallback on thin results.

    Tier 0 is `direct_fetcher or fetch_page_text` (raised extraction budget:
    max_chars=8000 — leaderboard tails beyond the old 3000-char cut never
    reached the selector). When tier 0 is thin or blocked, tier 1 renders the
    page in headless Chromium (browser started lazily, one page at a time on
    a dedicated thread). Any tier failure keeps the tier-0 result, so the
    caller still degrades to the original snippet.

    Results are cached per URL for a short TTL (default 900 s, env
    CANONICAL_V2_PAGE_CACHE_TTL): every turn re-fetching with a fresh
    TCP+TLS connection inside a 2 s race was the dominant source of
    turn-to-turn evidence drift (2026-08-28 G7 essence analysis).

    The returned object is callable (``fetcher(url)``) and additionally
    exposes ``warm()`` for boot/keepwarm browser pre-start.
    """
    direct = direct_fetcher or (
        lambda url: fetch_page_text(url, max_chars=8000)
    )
    pool = _PlaywrightPagePool(browser_factory)
    cache_ttl = max(0.0, float(os.getenv("CANONICAL_V2_PAGE_CACHE_TTL", "900")))
    cache: dict[str, tuple[float, str]] = {}
    cache_lock = Lock()

    def fetch(url: str) -> str | None:
        now = monotonic()
        with cache_lock:
            hit = cache.get(url)
        if hit is not None and now - hit[0] < cache_ttl:
            return hit[1]
        direct_text = direct(url)
        if not _is_thin_or_blocked(direct_text):
            text = direct_text
        else:
            try:
                rendered = pool.fetch(url)
            except Exception:  # noqa: BLE001 - headless failure keeps the snippet
                rendered = None
            text = rendered if rendered is not None else direct_text
        if text:
            with cache_lock:
                if len(cache) >= 1024:
                    oldest = min(cache, key=lambda key: cache[key][0])
                    cache.pop(oldest, None)
                cache[url] = (now, text)
        return text

    fetcher: TieredPageFetcher = cast(
        TieredPageFetcher,
        fetch,
    )
    fetcher.warm = pool.warm  # type: ignore[attr-defined]
    return fetcher


class TieredPageFetcher(Protocol):
    """Callable page fetcher with an optional browser warm-up hook."""

    def __call__(self, url: str) -> str | None: ...

    def warm(self, timeout: float = 10.0) -> bool: ...


__all__ = [
    "TieredPageFetcher",
    "create_tiered_page_fetcher",
    "extract_main_text",
    "fetch_page_text",
]
