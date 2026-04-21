from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass
from io import BytesIO

import httpx
from pdfminer.high_level import extract_text as pdfminer_extract_text

from .title_resolver import ResolvedPaper

logger = logging.getLogger(__name__)
_DEFAULT_TIMEOUT = 60.0
_MAX_PDF_BYTES = 30 * 1024 * 1024
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


def _download_pdf(url: str, *, http_client) -> tuple[bytes, str]:
    _ARXIV_PDF_GATE.wait()
    response = http_client.get(url, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()

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
    )


def fetch_and_extract_full_text(
    paper: ResolvedPaper,
    *,
    paper_id: str,
    http_client: httpx.Client | None = None,
) -> FullTextExtract:
    client = http_client or _make_http_client()
    owns_client = http_client is None
    last_fetch_error = "no_arxiv_id"

    try:
        if paper.arxiv_id:
            arxiv_pdf_url = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
            try:
                pdf_bytes, pdf_sha256 = _download_pdf(arxiv_pdf_url, http_client=client)
                text = _extract_text_from_pdf_bytes(pdf_bytes)
                if not text.strip():
                    last_fetch_error = "pdf_empty_text"
                else:
                    abstract, intro = _split_abstract_intro(text)
                    return FullTextExtract(
                        paper_id=paper_id,
                        abstract=abstract,
                        intro=intro,
                        pdf_url=arxiv_pdf_url,
                        pdf_sha256=pdf_sha256,
                        source="arxiv",
                        fetch_error=None,
                    )
            except httpx.TimeoutException as exc:
                last_fetch_error = "timeout"
                logger.warning("Timed out fetching full text for %s: %s", paper_id, exc)
            except httpx.HTTPStatusError as exc:
                last_fetch_error = _http_error_tag(exc)
                logger.warning(
                    "HTTP error fetching full text for %s: %s",
                    paper_id,
                    last_fetch_error,
                )
            except httpx.RequestError as exc:
                last_fetch_error = "network"
                logger.warning(
                    "Network error fetching full text for %s: %s", paper_id, exc
                )
            except _OversizeError as exc:
                last_fetch_error = "pdf_too_large"
                logger.warning("Oversize PDF for %s: %s", paper_id, exc)
            except _PdfParseError as exc:
                last_fetch_error = "pdf_parse_error"
                logger.warning("PDF parse error for %s: %s", paper_id, exc)

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


def _clean_section_text(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = text.strip().replace("\f", "\n")
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
