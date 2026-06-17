# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Shared homepage fetch: static first, headless-browser fallback for anti-scrape (412/403).

Cross-domain (used by professor field-completion L2/L4 AND paper collection). A real
browser session carries anti-scrape cookies/tokens that a plain HTTP client lacks, which
resolves most WAF 412/403 (e.g. SZU csse). If minimal rendering is insufficient, add
playwright-stealth patches (navigator.webdriver / CDP fingerprint) here.
"""

from __future__ import annotations

from src.data_agents.paper.homepage_http import fetch_homepage_html

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def render_html_with_browser(
    url: str,
    *,
    timeout: float = 60.0,
    wait_after_ms: int = 4000,
) -> str:
    """Render a page with headless Chromium and return the DOM HTML.

    A real browser session acquires/carries the anti-scrape cookies and challenge tokens
    that static HTTP clients miss (the common cause of 412 Precondition Failed).
    """
    from playwright.sync_api import sync_playwright

    timeout_ms = max(1_000, int(timeout * 1000))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=_BROWSER_UA)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except Exception:
                pass
            page.wait_for_timeout(wait_after_ms)
            return page.content()
        finally:
            browser.close()


def fetch_html_with_browser_fallback(
    url: str,
    *,
    min_text_len: int = 60,
    timeout: float = 60.0,
) -> tuple[str, str]:
    """Static fetch first; on anti-scrape (4xx) or too-short result, fall back to a browser render.

    Returns ``(html, method)`` where method is ``"static"`` / ``"browser"`` / ``"failed"``.
    """
    try:
        html = fetch_homepage_html(url)
        if html and len(html.strip()) >= min_text_len:
            return html, "static"
    except Exception:
        pass
    try:
        return render_html_with_browser(url, timeout=timeout), "browser"
    except Exception:
        return "", "failed"
