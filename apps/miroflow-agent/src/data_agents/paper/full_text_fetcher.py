from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pdfminer.high_level import extract_text as pdfminer_extract_text

from .raw_pdf_store import persist_raw_pdf_bytes
from .text_sanitizer import sanitize_text_for_postgres
from .title_resolver import ResolvedPaper

logger = logging.getLogger(__name__)
_DEFAULT_TIMEOUT = 60.0
_MAX_PDF_BYTES = 30 * 1024 * 1024
_MAX_REDIRECTS = 5
_ALLOWED_PDF_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
        "binary/octet-stream",
    }
)
_INTRO_MAX_CHARS = 3000
_ABSTRACT_RE = re.compile(r"(?im)^[ \t]*abstract[ \t]*(?:[.:\-–—][ \t]*)?$")
_INTRO_RE = re.compile(
    r"(?im)^[ \t]*(?:1[ \t]*[.)]?[ \t]*)?introduction[ \t]*(?:[.:\-–—][ \t]*)?$"
)
_NEXT_SECTION_RE = re.compile(
    r"(?im)^[ \t]*(?:(?:[2-9]|[1-9]\d*)[ \t]*[.)]?[ \t]*)?"
    r"(?:related\s+work|background|methodology|methods|approach|"
    r"proposed\s+method|preliminaries|experiments?|evaluation|results?|"
    r"discussion|conclusion|conclusions|implementation|model|models|setup|"
    r"problem\s+formulation|materials\s+and\s+methods)[ \t]*(?:[.:\-–—][ \t]*)?$"
)


class _RateLimitGate:
    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_called_at: float | None = None

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._last_called_at is None:
                self._last_called_at = now
                return
            elapsed = now - self._last_called_at
            sleep_seconds = max(0.0, self._min_interval_seconds - elapsed)
            if sleep_seconds:
                time.sleep(sleep_seconds)
                now = time.monotonic()
            self._last_called_at = now


_ARXIV_PDF_GATE = _RateLimitGate(3.0)


class _OversizeError(Exception):
    pass


class _UnsupportedContentTypeError(Exception):
    pass


class _PdfParseError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class FullTextExtract:
    paper_id: str
    abstract: str | None
    intro: str | None
    pdf_url: str | None
    pdf_sha256: str | None
    source: str
    fetch_error: str | None
    pdf_byte_size: int | None = None
    raw_pdf_storage_ref: str | None = None


def _find_section_anchor(text: str, pattern_kind: str) -> object | None:
    if pattern_kind == "abstract":
        match = _ABSTRACT_RE.search(text)
    elif pattern_kind == "intro":
        match = _INTRO_RE.search(text)
    else:
        raise ValueError(f"unsupported pattern_kind: {pattern_kind}")
    if match is None:
        return None
    return (match.end(), match.end())


def _split_abstract_intro(text: str) -> tuple[str | None, str | None]:
    if not text:
        return (None, None)

    abstract_match = _ABSTRACT_RE.search(text)
    intro_match = _INTRO_RE.search(text)

    abstract: str | None = None
    intro: str | None = None

    if abstract_match is not None and (
        intro_match is None or abstract_match.start() < intro_match.start()
    ):
        abstract_end = len(text) if intro_match is None else intro_match.start()
        abstract = _clean_section_text(text[abstract_match.end() : abstract_end])

    if intro_match is not None:
        next_match = _NEXT_SECTION_RE.search(text, pos=intro_match.end())
        intro_end = len(text) if next_match is None else next_match.start()
        intro = _clean_section_text(text[intro_match.end() : intro_end])
        if intro is not None:
            intro = intro[:_INTRO_MAX_CHARS] or None

    return (abstract, intro)


def _fetch_via_jina_reader(url: str) -> str | None:
    """Fetch page text via the Jina reader (https://r.jina.ai/{url}).

    W2a: landing-page fallback for prof_page_only papers with no arxiv_id,
    no usable PDF, and no OpenAlex abstract. The reader renders the page
    (including JS-rendered content) and returns markdown/text.
    """
    reader_url = f"https://r.jina.ai/{url.strip()}"
    try:
        with httpx.Client(timeout=30.0, trust_env=True, follow_redirects=True) as client:
            response = client.get(reader_url)
            if response.status_code == 200 and response.text:
                return response.text
            logger.warning("Jina reader returned %d for %s", response.status_code, url)
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Jina reader failed for %s: %s", url, exc)
        return None


def _download_pdf(url: str, *, http_client) -> tuple[bytes, str]:
    _ARXIV_PDF_GATE.wait()
    response = http_client.get(url)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type")
    if content_type is not None and not _is_allowed_pdf_content_type(content_type):
        raise _UnsupportedContentTypeError("pdf_content_type_disallowed")

    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_PDF_BYTES:
                raise _OversizeError("pdf_too_large")
        except ValueError:
            pass

    pdf_bytes = bytes(response.content)
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise _OversizeError("pdf_too_large")

    return (pdf_bytes, hashlib.sha256(pdf_bytes).hexdigest())


def _is_allowed_pdf_content_type(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().casefold()
    return not media_type or media_type in _ALLOWED_PDF_CONTENT_TYPES


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
        raise _PdfParseError("pdf_parse_error")
    try:
        text = pdfminer_extract_text(BytesIO(pdf_bytes), maxpages=4)
    except Exception as exc:
        raise _PdfParseError("pdf_parse_error") from exc
    if not isinstance(text, str):
        raise _PdfParseError("pdf_parse_error")
    return text


def _make_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=_DEFAULT_TIMEOUT,
        trust_env=False,
        follow_redirects=True,
        max_redirects=_MAX_REDIRECTS,
    )


def _is_arxiv_pdf_url(pdf_url: str | None) -> bool:
    if not pdf_url:
        return False
    parsed = urlparse(pdf_url)
    hostname = (parsed.hostname or "").lower()
    return hostname.endswith("arxiv.org") and parsed.path.startswith("/pdf/")


def _direct_professor_page_pdf_url(paper: ResolvedPaper) -> str | None:
    if not paper.pdf_url or _is_arxiv_pdf_url(paper.pdf_url):
        return None
    return paper.pdf_url


def _fetch_pdf_source(
    pdf_url: str,
    *,
    paper_id: str,
    source: str,
    http_client,
    raw_pdf_store_dir: str | Path | None = None,
) -> tuple[FullTextExtract | None, str | None]:
    try:
        pdf_bytes, pdf_sha256 = _download_pdf(pdf_url, http_client=http_client)
        raw_pdf_storage_ref = persist_raw_pdf_bytes(
            pdf_bytes,
            pdf_sha256,
            storage_dir=raw_pdf_store_dir,
        )
        text = _extract_text_from_pdf_bytes(pdf_bytes)
        if not text.strip():
            return None, "pdf_empty_text"
        abstract, intro = _split_abstract_intro(text)
        return (
            FullTextExtract(
                paper_id=paper_id,
                abstract=abstract,
                intro=intro,
                pdf_url=pdf_url,
                pdf_sha256=pdf_sha256,
                source=source,
                fetch_error=None,
                pdf_byte_size=len(pdf_bytes),
                raw_pdf_storage_ref=raw_pdf_storage_ref,
            ),
            None,
        )
    except httpx.TimeoutException as exc:
        logger.warning("Timed out fetching full text for %s: %s", paper_id, exc)
        return None, "timeout"
    except httpx.TooManyRedirects as exc:
        logger.warning("Redirect cap exceeded fetching full text for %s: %s", paper_id, exc)
        return None, "redirect_cap_exceeded"
    except httpx.HTTPStatusError as exc:
        error_tag = _http_error_tag(exc)
        logger.warning("HTTP error fetching full text for %s: %s", paper_id, error_tag)
        return None, error_tag
    except httpx.RequestError as exc:
        logger.warning("Network error fetching full text for %s: %s", paper_id, exc)
        return None, "network"
    except _OversizeError as exc:
        logger.warning("Oversize PDF for %s: %s", paper_id, exc)
        return None, "pdf_too_large"
    except _UnsupportedContentTypeError as exc:
        logger.warning("Unsupported PDF content type for %s: %s", paper_id, exc)
        return None, "pdf_content_type_disallowed"
    except _PdfParseError as exc:
        logger.warning("PDF parse error for %s: %s", paper_id, exc)
        return None, "pdf_parse_error"


def fetch_and_extract_full_text(
    paper: ResolvedPaper,
    *,
    paper_id: str,
    http_client: httpx.Client | None = None,
    raw_pdf_store_dir: str | Path | None = None,
) -> FullTextExtract:
    client = http_client or _make_http_client()
    owns_client = http_client is None
    last_fetch_error = "no_arxiv_id"

    try:
        professor_page_pdf_url = _direct_professor_page_pdf_url(paper)
        if professor_page_pdf_url:
            extract, fetch_error = _fetch_pdf_source(
                professor_page_pdf_url,
                paper_id=paper_id,
                source="prof_page_pdf",
                http_client=client,
                raw_pdf_store_dir=raw_pdf_store_dir,
            )
            if extract is not None:
                return extract
            if fetch_error is not None:
                last_fetch_error = fetch_error

        if paper.arxiv_id:
            arxiv_pdf_url = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
            extract, fetch_error = _fetch_pdf_source(
                arxiv_pdf_url,
                paper_id=paper_id,
                source="arxiv",
                http_client=client,
                raw_pdf_store_dir=raw_pdf_store_dir,
            )
            if extract is not None:
                return extract
            if fetch_error is not None:
                last_fetch_error = fetch_error

        fallback_abstract = _clean_section_text(paper.abstract)
        if fallback_abstract is not None:
            return FullTextExtract(
                paper_id=paper_id,
                abstract=fallback_abstract,
                intro=None,
                pdf_url=paper.pdf_url,
                pdf_sha256=None,
                source="openalex",
                fetch_error=None,
            )

        # W2a: Jina reader fallback for prof_page_only papers with no arxiv_id,
        # no usable PDF, and no OpenAlex abstract. Fetch the landing page via
        # the reader and extract the abstract from the rendered text.
        if paper.pdf_url and not paper.arxiv_id:
            reader_text = _fetch_via_jina_reader(paper.pdf_url)
            if reader_text:
                # Strip markdown heading prefixes so _split_abstract_intro
                # can find "Abstract" (## Abstract → Abstract).
                reader_text_clean = re.sub(r'^#+\s*', '', reader_text, flags=re.MULTILINE)
                abstract, intro = _split_abstract_intro(reader_text_clean)
                if abstract:
                    return FullTextExtract(
                        paper_id=paper_id,
                        abstract=abstract,
                        intro=intro,
                        pdf_url=paper.pdf_url,
                        pdf_sha256=None,
                        source="landing_page_reader",
                        fetch_error=None,
                    )
                last_fetch_error = "reader_no_abstract"
            # If reader fails (None), keep the original last_fetch_error
            # (e.g., "timeout" from the prof_page_pdf attempt).

        return FullTextExtract(
            paper_id=paper_id,
            abstract=None,
            intro=None,
            pdf_url=paper.pdf_url,
            pdf_sha256=None,
            source="failed",
            fetch_error=last_fetch_error,
        )
    finally:
        if owns_client:
            client.close()


def fetch_pdf_url_full_text(
    pdf_url: str,
    *,
    paper_id: str,
    source: str,
    http_client: httpx.Client | None = None,
    raw_pdf_store_dir: str | Path | None = None,
) -> FullTextExtract:
    client = http_client or _make_http_client()
    owns_client = http_client is None
    try:
        extract, fetch_error = _fetch_pdf_source(
            pdf_url,
            paper_id=paper_id,
            source=source,
            http_client=client,
            raw_pdf_store_dir=raw_pdf_store_dir,
        )
        if extract is not None:
            return extract
        return FullTextExtract(
            paper_id=paper_id,
            abstract=None,
            intro=None,
            pdf_url=pdf_url,
            pdf_sha256=None,
            source="failed",
            fetch_error=fetch_error or "pdf_extract_failed",
        )
    finally:
        if owns_client:
            client.close()


def _clean_section_text(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = sanitize_text_for_postgres(text.strip())
    return cleaned or None


def _http_error_tag(exc: httpx.HTTPStatusError) -> str:
    status_code = exc.response.status_code
    if status_code == 404:
        return "http_404"
    if status_code == 429:
        return "http_429"
    if 500 <= status_code <= 599:
        return "http_5xx"
    return f"http_{status_code}"
