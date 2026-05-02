"""Supplementary professor homepage crawler for group/lab pages and CV PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import logging
import re
from typing import Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_GROUP_PATTERNS = (
    r"Group Website",
    r"实验室",
    r"课题组",
    r"Lab\b",
    r"Group\b",
    r"研究组",
    r"团队主页",
)
_LAB_URL_PATTERNS = (r"/lab(?:/|$)", r"/group(?:/|$)", r"/team(?:/|$)")
_CV_PATTERNS = (r"CV\b", r"个人简历", r"履历", r"resume\.pdf", r"-cv\.pdf")
_PDF_URL_PATTERNS = (r"\.pdf(?:\?|$)",)
_SKIP_SCHEMES = ("mailto:", "javascript:", "tel:")
_USER_AGENT = "MiroThinker professor multi-source crawler/1.0"
_HTML_TIMEOUT_SECONDS = 10.0
_PDF_TIMEOUT_SECONDS = 30.0
_MAX_SUB_LINKS_PER_DOMAIN = 5
_RAW_TEXT_CAP = 30_000


@dataclass(frozen=True, slots=True)
class LinkCandidate:
    url: str
    text: str
    title: str | None = None


def follow_supplementary_links(
    html: str,
    base_url: str,
    *,
    professor_name: str | None = None,
    max_hops: int = 2,
    max_sub_links_per_domain: int = _MAX_SUB_LINKS_PER_DOMAIN,
    raw_text_cap: int = _RAW_TEXT_CAP,
    fetch_html_fn: Callable[[str, float], object] | None = None,
    fetch_pdf_fn: Callable[[str, float], str] | None = None,
) -> list[str]:
    """Follow Group/Lab/CV links from a primary professor page.

    Returns text segments suitable for appending to profile_raw_text. Fetch and
    parse failures are logged and skipped.
    """
    if not html or max_hops <= 0:
        return []

    seen_urls = {base_url.rstrip("/")}
    segments: list[str] = []
    for link in _extract_links(html, base_url):
        key = link.url.rstrip("/")
        if key in seen_urls:
            continue
        seen_urls.add(key)

        if _is_cv_pdf_anchor(link.text, link.url):
            pdf_text = _safe_fetch_pdf_text(
                link.url,
                fetch_pdf_fn=fetch_pdf_fn,
                timeout=_PDF_TIMEOUT_SECONDS,
            )
            if pdf_text:
                segments.append(_format_segment(link.url, pdf_text))
            continue

        if not (
            _is_group_website_anchor(link.text, link.url)
            or _is_lab_anchor(link.text, link.url)
        ):
            continue

        group_html = _safe_fetch_html(
            link.url,
            fetch_html_fn=fetch_html_fn,
            timeout=_HTML_TIMEOUT_SECONDS,
        )
        if not group_html:
            continue
        group_text = extract_main_text(group_html)
        if group_text:
            segments.append(_format_segment(link.url, group_text))

        if max_hops < 2:
            continue
        sub_links = _select_personal_section_links(
            group_html,
            link.url,
            professor_name=professor_name,
            max_links=max_sub_links_per_domain,
        )
        for sub_link in sub_links:
            sub_key = sub_link.url.rstrip("/")
            if sub_key in seen_urls:
                continue
            seen_urls.add(sub_key)
            sub_html = _safe_fetch_html(
                sub_link.url,
                fetch_html_fn=fetch_html_fn,
                timeout=_HTML_TIMEOUT_SECONDS,
            )
            if not sub_html:
                continue
            sub_text = extract_main_text(sub_html)
            if sub_text:
                segments.append(_format_segment(sub_link.url, sub_text))

    return _cap_segments(segments, raw_text_cap)


def _is_group_website_anchor(text: str, href: str) -> bool:
    combined = f"{text or ''} {href or ''}"
    return any(
        re.search(pattern, combined, re.IGNORECASE) for pattern in _GROUP_PATTERNS
    )


def _is_lab_anchor(text: str, href: str) -> bool:
    combined = f"{text or ''} {href or ''}"
    return any(
        re.search(pattern, combined, re.IGNORECASE)
        for pattern in _GROUP_PATTERNS + _LAB_URL_PATTERNS
    )


def _is_cv_pdf_anchor(text: str, href: str) -> bool:
    if not any(
        re.search(pattern, href or "", re.IGNORECASE) for pattern in _PDF_URL_PATTERNS
    ):
        return False
    combined = f"{text or ''} {href or ''}"
    return any(re.search(pattern, combined, re.IGNORECASE) for pattern in _CV_PATTERNS)


def extract_main_text(html: str) -> str:
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "nav", "footer"]):
        node.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_links(html: str, base_url: str) -> list[LinkCandidate]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    links: list[LinkCandidate] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", *_SKIP_SCHEMES)):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        normalized = absolute.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        links.append(
            LinkCandidate(
                url=absolute,
                text=anchor.get_text(" ", strip=True),
                title=str(anchor.get("title")).strip() if anchor.get("title") else None,
            )
        )
    return links


def _select_personal_section_links(
    html: str,
    base_url: str,
    *,
    professor_name: str | None,
    max_links: int,
) -> list[LinkCandidate]:
    base_host = (urlparse(base_url).hostname or "").lower()
    selected: list[LinkCandidate] = []
    for link in _extract_links(html, base_url):
        parsed = urlparse(link.url)
        if (parsed.hostname or "").lower() != base_host:
            continue
        if _is_cv_pdf_anchor(link.text, link.url):
            continue
        if not _is_personal_section(link, professor_name=professor_name):
            continue
        selected.append(link)
        if len(selected) >= max_links:
            break
    return selected


def _is_personal_section(
    link: LinkCandidate,
    *,
    professor_name: str | None,
) -> bool:
    combined = f"{link.text or ''} {link.title or ''} {link.url}".lower()
    if (
        professor_name
        and professor_name.strip()
        and professor_name.strip().lower() in combined
    ):
        return True
    return any(
        token in combined
        for token in (
            "member",
            "people",
            "team",
            "profile",
            "bio",
            "about",
            "research",
            "publication",
            "成员",
            "团队",
            "个人",
            "简介",
            "研究",
            "成果",
        )
    )


def _safe_fetch_html(
    url: str,
    *,
    fetch_html_fn: Callable[[str, float], object] | None,
    timeout: float,
) -> str | None:
    try:
        if fetch_html_fn is not None:
            result = fetch_html_fn(url, timeout)
            html = result.html if hasattr(result, "html") else result
            return str(html) if html else None
        return _fetch_html_with_timeout(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Supplementary HTML fetch failed for %s: %s", url, exc)
        return None


def _fetch_html_with_timeout(
    url: str, *, timeout: float = _HTML_TIMEOUT_SECONDS
) -> str | None:
    import httpx

    response = httpx.get(
        url,
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )
    if response.status_code >= 400:
        return None
    return response.text


def _safe_fetch_pdf_text(
    url: str,
    *,
    fetch_pdf_fn: Callable[[str, float], str] | None,
    timeout: float,
) -> str | None:
    try:
        if fetch_pdf_fn is not None:
            return fetch_pdf_fn(url, timeout)
        return _fetch_pdf_to_text(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Supplementary PDF fetch/parse failed for %s: %s", url, exc)
        return None


def _fetch_pdf_to_text(
    url: str, *, timeout: float = _PDF_TIMEOUT_SECONDS
) -> str | None:
    import httpx

    response = httpx.get(
        url,
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )
    if response.status_code >= 400:
        return None
    content = response.content
    try:
        from pdfminer.high_level import extract_text

        text = extract_text(BytesIO(content))
    except Exception as pdfminer_exc:  # noqa: BLE001
        logger.warning(
            "pdfminer failed for %s: %s; trying pdfplumber", url, pdfminer_exc
        )
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(content)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception as pdfplumber_exc:  # noqa: BLE001
            logger.warning("pdfplumber failed for %s: %s", url, pdfplumber_exc)
            return None
    normalized = re.sub(r"\s+", " ", text or "").strip()
    return normalized or None


def _format_segment(url: str, text: str) -> str:
    return f"Source: {url}\n{text.strip()}"


def _cap_segments(segments: list[str], raw_text_cap: int) -> list[str]:
    capped: list[str] = []
    remaining = raw_text_cap
    for segment in segments:
        if remaining <= 0:
            break
        if len(segment) <= remaining:
            capped.append(segment)
            remaining -= len(segment)
            continue
        capped.append(segment[:remaining])
        break
    return capped
