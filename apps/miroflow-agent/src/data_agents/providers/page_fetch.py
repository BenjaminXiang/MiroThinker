"""Bounded direct page fetch with BeautifulSoup main-text extraction.

The serving Web lane uses this to deepen high-quality search results: fetch the
page itself and ground the answer in its actual content instead of a thin
snippet. No external reader service is required (the deployment network cannot
reach r.jina.ai); everything degrades to the original snippet on any failure.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
import httpx

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


__all__ = ["extract_main_text", "fetch_page_text"]
