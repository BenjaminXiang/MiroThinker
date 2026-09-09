# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Shared homepage fetch: static first, headless-browser fallback for anti-scrape (412/403).

Cross-domain (used by professor field-completion L2/L4 AND paper collection). A real
browser session carries anti-scrape cookies/tokens that a plain HTTP client lacks, which
resolves most WAF 412/403 (e.g. SZU csse). If minimal rendering is insufficient, add
playwright-stealth patches (navigator.webdriver / CDP fingerprint) here.
"""

from __future__ import annotations

import os

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
    cdp_renderer: "CDPChromeRenderer | None" = None,
) -> tuple[str, str]:
    """Static fetch first; on anti-scrape (4xx) or too-short, fall back to a browser render.

    Tiered: static → headless Playwright (cookie-based anti-scrape) → optional CDP Chrome
    (passes JS anti-bot challenges like 瑞数/Rishu that fingerprint Playwright automation).
    Returns ``(html, method)`` where method is ``"static"``/``"browser"``/``"cdp"``/``"failed"``.
    """
    try:
        html = fetch_homepage_html(url)
        if html and len(html.strip()) >= min_text_len:
            return html, "static"
    except Exception:
        pass
    try:
        html = render_html_with_browser(url, timeout=timeout)
        if html and len(html.strip()) >= min_text_len:
            return html, "browser"
    except Exception:
        pass
    if cdp_renderer is not None:
        try:
            html = cdp_renderer.render(url, timeout=timeout)
            if html and len(html.strip()) >= min_text_len:
                return html, "cdp"
        except Exception:
            pass
    return "", "failed"


class CDPChromeRenderer:
    """Persistent headful Chrome (no automation flags) connected over CDP.

    Solves JS anti-bot challenges (瑞数信息/Rishu, common on Chinese .edu.cn WAFs) that
    fingerprint Playwright's ``--enable-automation`` flags and block headless/headful
    Playwright with a 412 + empty body. A manually-launched Chrome (no Playwright flags)
    executes the challenge JS → solves → loads the real page.

    Launch once, render many URLs (efficient for batches). **Must run under a display**
    (wrap the caller in ``xvfb-run``); it launches headful Chrome.
    """

    def __init__(self, chrome_path: str | None = None) -> None:
        import glob
        import subprocess

        self._proc: subprocess.Popen | None = None
        candidates = []
        if chrome_path:
            candidates.append(chrome_path)
        env_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        if env_path:
            candidates.append(env_path)
        candidates += sorted(
            glob.glob(
                os.path.expanduser(
                    "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
                )
            )
        )
        if not candidates:
            raise RuntimeError("no chromium binary found for CDPChromeRenderer")
        self._chrome = candidates[-1]
        port = 9222 + (os.getpid() % 1000)
        self._port = port
        self._proc = subprocess.Popen(
            [
                self._chrome,
                f"--remote-debugging-port={port}",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir=/tmp/cdp_chrome_{os.getpid()}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import time

        time.sleep(5)  # let Chrome boot + open the debug port
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(f"http://localhost:{port}")

    def render(
        self, url: str, *, timeout: float = 90.0, wait_after_ms: int = 8000
    ) -> str:
        context = self._browser.new_context(
            user_agent=_BROWSER_UA,
            locale="zh-CN",
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()
        try:
            try:
                page.goto(url, wait_until="networkidle", timeout=int(timeout * 1000))
            except Exception:
                page.goto(
                    url, wait_until="domcontentloaded", timeout=int(timeout * 1000)
                )
            page.wait_for_timeout(wait_after_ms)  # let the challenge JS solve + reload
            return page.content()
        finally:
            context.close()

    def close(self) -> None:
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except Exception:
                self._proc.kill()
