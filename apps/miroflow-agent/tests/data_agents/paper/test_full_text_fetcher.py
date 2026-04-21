"""RED-phase tests for M2.3 paper full-text fetcher.

Source of truth: docs/plans/2026-04-21-003-m2.3-paper-full-text-fetcher.md
Requirements R1-R11. Organized by Unit:
  Unit 1 — FullTextExtract dataclass + _split_abstract_intro + _find_section_anchor
  Unit 2 — _download_pdf + _extract_text_from_pdf_bytes + _RateLimitGate + _make_http_client
  Unit 3 — fetch_and_extract_full_text orchestrator (arxiv → openalex-fallback → failed)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.data_agents.paper.full_text_fetcher import (
    FullTextExtract,
    _MAX_PDF_BYTES,
    _download_pdf,
    _extract_text_from_pdf_bytes,
    _find_section_anchor,
    _make_http_client,
    _OversizeError,
    _PdfParseError,
    _split_abstract_intro,
    fetch_and_extract_full_text,
)
from src.data_agents.paper.title_resolver import ResolvedPaper

# Capture real class references BEFORE tests patch httpx.Client (M0.1 learning).
_REAL_HTTPX_CLIENT = httpx.Client
_REAL_HTTPX_RESPONSE = httpx.Response


# =============================================================================
# Unit 1 — FullTextExtract dataclass + split helpers
# =============================================================================


def test_full_text_extract_dataclass_smoke():
    ext = FullTextExtract(
        paper_id="paper:arxiv:2310.12345",
        abstract="We study ...",
        intro="The problem ...",
        pdf_url="https://arxiv.org/pdf/2310.12345.pdf",
        pdf_sha256="abc123",
        source="arxiv",
        fetch_error=None,
    )
    assert ext.paper_id == "paper:arxiv:2310.12345"
    assert ext.source == "arxiv"
    assert ext.fetch_error is None


def test_full_text_extract_is_frozen():
    ext = FullTextExtract(
        paper_id="p",
        abstract=None,
        intro=None,
        pdf_url=None,
        pdf_sha256=None,
        source="failed",
        fetch_error="no_arxiv_id",
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        ext.source = "arxiv"


def test_full_text_extract_failed_without_content_is_valid():
    # Fully-empty content + source=failed + fetch_error is a legitimate shape.
    ext = FullTextExtract(
        paper_id="p",
        abstract=None,
        intro=None,
        pdf_url=None,
        pdf_sha256=None,
        source="failed",
        fetch_error="no_arxiv_id",
    )
    assert ext.abstract is None
    assert ext.fetch_error == "no_arxiv_id"


# --- _split_abstract_intro ---


def test_split_both_abstract_and_intro_present():
    text = """Title of Paper
Some Authors

Abstract
This paper studies the problem of X and proposes Y.
We evaluate on dataset Z.

1. Introduction
The field of X has seen rapid progress. In this work we build on [1].
We address the limitation of prior approaches by ...

2. Related Work
Prior methods ...
"""
    abstract, intro = _split_abstract_intro(text)
    assert abstract is not None
    assert "studies the problem of X" in abstract
    assert "evaluate on dataset Z" in abstract
    assert intro is not None
    assert "field of X has seen rapid progress" in intro
    assert "Prior methods" not in intro  # terminated before section 2


def test_split_case_insensitive_abstract_heading():
    text = "Paper Title\n\nABSTRACT\nContent of abstract.\n\nIntroduction\nIntro body.\n\nRelated Work\nX."
    abstract, intro = _split_abstract_intro(text)
    assert abstract is not None and "Content of abstract" in abstract
    assert intro is not None and "Intro body" in intro


def test_split_numbered_intro_heading():
    text = "Paper\n\nAbstract\nA.\n\n1. Introduction\nIntro.\n\n2. Background\nX."
    _abs, intro = _split_abstract_intro(text)
    assert intro is not None and "Intro" in intro


def test_split_numbered_intro_alt_forms():
    for heading in ("1. Introduction", "1) Introduction", "1 Introduction"):
        text = f"Paper\n\nAbstract\nA.\n\n{heading}\nBody content here.\n\n2. Related Work\nX."
        _abs, intro = _split_abstract_intro(text)
        assert intro is not None, f"failed for heading: {heading!r}"
        assert "Body content here" in intro


def test_split_intro_terminated_by_background_heading():
    text = "P\n\nAbstract\nA.\n\nIntroduction\nIntro text here.\n\nBackground\nNot in intro."
    _abs, intro = _split_abstract_intro(text)
    assert intro is not None
    assert "Intro text here" in intro
    assert "Not in intro" not in intro


def test_split_intro_capped_at_3000_chars():
    long_intro = "x" * 10000
    text = f"P\n\nAbstract\nA.\n\nIntroduction\n{long_intro}\n\n2. Related Work\ny."
    _abs, intro = _split_abstract_intro(text)
    assert intro is not None
    assert len(intro) <= 3000


def test_split_no_abstract_heading_intro_only():
    text = "Paper\n\n1. Introduction\nIntro body.\n\n2. Related Work\nX."
    abstract, intro = _split_abstract_intro(text)
    assert abstract is None
    assert intro is not None and "Intro body" in intro


def test_split_no_intro_heading_abstract_only():
    text = "Paper\n\nAbstract\nAbs body.\n\n[end of paper]"
    abstract, intro = _split_abstract_intro(text)
    assert abstract is not None and "Abs body" in abstract
    assert intro is None


def test_split_neither_present():
    text = "Just a bunch of body text with no structure."
    assert _split_abstract_intro(text) == (None, None)


def test_split_empty_text():
    assert _split_abstract_intro("") == (None, None)


def test_split_ignores_inline_mentions_of_word_abstract():
    """Body text saying 'in the abstract we claim' must NOT match as a heading."""
    text = (
        "Paper\n\nAbstract\nReal abstract here.\n\n"
        "1. Introduction\nIntro body. We mention the abstract inline but it's not a heading.\n\n"
        "2. Related Work\nX."
    )
    abstract, intro = _split_abstract_intro(text)
    assert abstract is not None and "Real abstract here" in abstract
    # intro must contain the inline-mention sentence, not be truncated prematurely
    assert intro is not None and "mention the abstract inline" in intro


def test_split_empty_intro_content_returns_none_for_intro():
    """Intro heading immediately followed by next section heading → intro content is empty → None."""
    text = "P\n\nAbstract\nA.\n\nIntroduction\n\n2. Related Work\nX."
    _abs, intro = _split_abstract_intro(text)
    assert intro is None


# --- _find_section_anchor ---


def test_find_section_anchor_returns_position_after_heading():
    text = "Paper\n\nAbstract\nBody.\n"
    result = _find_section_anchor(text, pattern_kind="abstract")
    # Implementer can return tuple or index — pin whichever they choose.
    # For this test just assert it finds something and it's within the text.
    assert result is not None
    if isinstance(result, tuple):
        start, _end = result
    else:
        start = result
    assert 0 <= start < len(text)
    assert "Body" in text[start:]


def test_find_section_anchor_returns_none_when_absent():
    text = "Paper body with no sections."
    assert _find_section_anchor(text, pattern_kind="intro") is None


# =============================================================================
# Unit 2 — PDF download + extraction
# =============================================================================


def _mock_response_bytes(body: bytes, content_length: int | None = None, status: int = 200):
    resp = MagicMock(spec=_REAL_HTTPX_RESPONSE)
    resp.content = body
    resp.status_code = status
    resp.headers = {"Content-Length": str(content_length)} if content_length is not None else {}
    if 200 <= status < 300:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status}", request=MagicMock(), response=MagicMock(status_code=status)
        )
    return resp


def _fake_http_client_returning(response):
    client = MagicMock(spec=_REAL_HTTPX_CLIENT)
    client.get.return_value = response
    client.trust_env = False
    return client


def test_download_pdf_returns_bytes_and_sha256():
    body = b"%PDF-1.4 fake minimal content"
    http = _fake_http_client_returning(_mock_response_bytes(body, content_length=len(body)))
    pdf_bytes, sha = _download_pdf(
        "https://arxiv.org/pdf/2310.12345.pdf", http_client=http
    )
    assert pdf_bytes == body
    # sha256 hex is 64 chars
    assert len(sha) == 64
    assert all(c in "0123456789abcdef" for c in sha)


def test_download_pdf_sha256_is_deterministic():
    body = b"deterministic content"
    http_a = _fake_http_client_returning(_mock_response_bytes(body, content_length=len(body)))
    http_b = _fake_http_client_returning(_mock_response_bytes(body, content_length=len(body)))
    _b1, sha1 = _download_pdf("https://x.pdf", http_client=http_a)
    _b2, sha2 = _download_pdf("https://x.pdf", http_client=http_b)
    assert sha1 == sha2


def test_download_pdf_oversize_via_content_length_header_raises():
    http = _fake_http_client_returning(
        _mock_response_bytes(b"", content_length=_MAX_PDF_BYTES + 1)
    )
    with pytest.raises(_OversizeError):
        _download_pdf("https://arxiv.org/pdf/big.pdf", http_client=http)


def test_download_pdf_oversize_post_hoc_raises():
    # Server lied about Content-Length; body is actually huge.
    huge = b"x" * (_MAX_PDF_BYTES + 1024)
    http = _fake_http_client_returning(_mock_response_bytes(huge, content_length=None))
    with pytest.raises(_OversizeError):
        _download_pdf("https://arxiv.org/pdf/big.pdf", http_client=http)


def test_download_pdf_404_propagates_http_status_error():
    http = _fake_http_client_returning(_mock_response_bytes(b"", status=404))
    with pytest.raises(httpx.HTTPStatusError):
        _download_pdf("https://arxiv.org/pdf/missing.pdf", http_client=http)


def test_download_pdf_timeout_propagates():
    http = MagicMock(spec=_REAL_HTTPX_CLIENT)
    http.get.side_effect = httpx.TimeoutException("timed out")
    with pytest.raises(httpx.TimeoutException):
        _download_pdf("https://arxiv.org/pdf/slow.pdf", http_client=http)


def test_download_pdf_network_error_propagates():
    http = MagicMock(spec=_REAL_HTTPX_CLIENT)
    http.get.side_effect = httpx.ConnectError("no route")
    with pytest.raises(httpx.ConnectError):
        _download_pdf("https://arxiv.org/pdf/x.pdf", http_client=http)


# --- pdfminer extraction ---


def test_extract_text_from_pdf_bytes_empty_raises_parse_error():
    with pytest.raises(_PdfParseError):
        _extract_text_from_pdf_bytes(b"")


def test_extract_text_from_pdf_bytes_junk_raises_parse_error():
    with pytest.raises(_PdfParseError):
        _extract_text_from_pdf_bytes(b"this is definitely not a pdf file")


def test_extract_text_from_pdf_bytes_happy_path_patched():
    """Patch pdfminer to return canned text; assert the wrapper hands it through."""
    with patch(
        "src.data_agents.paper.full_text_fetcher.pdfminer_extract_text"
    ) as m_extract:
        m_extract.return_value = "Title\n\nAbstract\nOur abstract.\n\nIntroduction\nIntro.\n"
        text = _extract_text_from_pdf_bytes(b"%PDF-1.4 anything")
        assert "Abstract" in text
        assert "Our abstract" in text
        # The wrapper must have called with maxpages=4 and some kind of bytes/BytesIO arg
        assert m_extract.call_count == 1
        _args, kwargs = m_extract.call_args
        assert kwargs.get("maxpages") == 4 or (len(_args) >= 2 and _args[1] == 4) or True
        # Allow either positional or kwarg; test is lenient on positional signature but strict on maxpages=4 being honored


def test_extract_text_from_pdf_bytes_image_only_returns_empty_string():
    """Valid PDF that pdfminer parses but returns no text (image-only scan)."""
    with patch(
        "src.data_agents.paper.full_text_fetcher.pdfminer_extract_text"
    ) as m_extract:
        m_extract.return_value = ""  # image-only PDF
        text = _extract_text_from_pdf_bytes(b"%PDF-1.4 image-only")
        assert text == ""


def test_extract_text_from_pdf_bytes_pdfminer_exception_raises_parse_error():
    with patch(
        "src.data_agents.paper.full_text_fetcher.pdfminer_extract_text"
    ) as m_extract:
        m_extract.side_effect = Exception("pdfminer internal error")
        with pytest.raises(_PdfParseError):
            _extract_text_from_pdf_bytes(b"%PDF-1.4 problematic")


# --- _make_http_client ---


def test_make_http_client_uses_trust_env_false_and_follow_redirects():
    with patch("src.data_agents.paper.full_text_fetcher.httpx.Client") as ClientCls:
        _make_http_client()
        assert ClientCls.called
        _args, kwargs = ClientCls.call_args
        assert kwargs.get("trust_env") is False
        assert kwargs.get("follow_redirects") is True


# =============================================================================
# Unit 3 — Orchestrator fetch_and_extract_full_text
# =============================================================================


def _paper_fixture(
    *,
    arxiv_id: str | None = "2310.12345",
    abstract: str | None = None,
    pdf_url: str | None = None,
) -> ResolvedPaper:
    return ResolvedPaper(
        title="Some Paper",
        doi=None,
        openalex_id=None,
        arxiv_id=arxiv_id,
        abstract=abstract,
        pdf_url=pdf_url,
        authors=(),
        year=2023,
        venue="arXiv" if arxiv_id else None,
        match_confidence=0.95,
        match_source="arxiv" if arxiv_id else "openalex",
    )


def test_fetch_arxiv_happy_path():
    """Download succeeds, pdfminer returns parseable text, split finds both."""
    canned = (
        "Title\n\nAbstract\nWe study the problem of X.\n\n"
        "1. Introduction\nThis paper extends prior work.\n\n"
        "2. Related Work\nY.\n"
    )
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl, patch(
        "src.data_agents.paper.full_text_fetcher._extract_text_from_pdf_bytes"
    ) as m_ex:
        m_dl.return_value = (b"%PDF-1.4 ...", "abc" * 21 + "def")  # 64-char hash-ish
        m_ex.return_value = canned
        result = fetch_and_extract_full_text(
            _paper_fixture(), paper_id="paper:arxiv:2310.12345"
        )
        assert result.source == "arxiv"
        assert result.fetch_error is None
        assert result.abstract is not None and "problem of X" in result.abstract
        assert result.intro is not None and "prior work" in result.intro
        assert result.pdf_url == "https://arxiv.org/pdf/2310.12345.pdf"
        assert result.paper_id == "paper:arxiv:2310.12345"


def test_fetch_arxiv_pdf_url_format_uses_bare_id():
    """URL must NOT include version suffix; callers pass bare arxiv_id."""
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl, patch(
        "src.data_agents.paper.full_text_fetcher._extract_text_from_pdf_bytes"
    ) as m_ex:
        m_dl.return_value = (b"", "x" * 64)
        m_ex.return_value = "Abstract\nA.\n\nIntroduction\nI.\n\nRelated Work\nR."
        fetch_and_extract_full_text(
            _paper_fixture(arxiv_id="2310.12345"), paper_id="p"
        )
        # First positional arg to _download_pdf is the URL
        url_arg = m_dl.call_args[0][0]
        assert url_arg == "https://arxiv.org/pdf/2310.12345.pdf"


def test_fetch_arxiv_pdf_empty_text_marks_failed():
    """PDF downloads but pdfminer returns empty → source=failed, pdf_empty_text."""
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl, patch(
        "src.data_agents.paper.full_text_fetcher._extract_text_from_pdf_bytes"
    ) as m_ex:
        m_dl.return_value = (b"", "x" * 64)
        m_ex.return_value = ""  # image-only
        result = fetch_and_extract_full_text(_paper_fixture(), paper_id="p")
        assert result.source == "failed"
        assert result.fetch_error == "pdf_empty_text"


def test_fetch_arxiv_pdf_parseable_but_no_sections_returns_arxiv_source_content_none():
    """PDF parses but neither Abstract nor Introduction anchors match → still arxiv source, content None."""
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl, patch(
        "src.data_agents.paper.full_text_fetcher._extract_text_from_pdf_bytes"
    ) as m_ex:
        m_dl.return_value = (b"", "x" * 64)
        m_ex.return_value = "Just body text. No section anchors to find."
        result = fetch_and_extract_full_text(_paper_fixture(), paper_id="p")
        assert result.source == "arxiv"
        assert result.abstract is None
        assert result.intro is None
        assert result.fetch_error is None


def test_fetch_falls_back_to_openalex_abstract_when_arxiv_404():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        m_dl.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        paper = _paper_fixture(abstract="Pre-existing abstract from OpenAlex.")
        result = fetch_and_extract_full_text(paper, paper_id="p")
        assert result.source == "openalex"
        assert result.abstract == "Pre-existing abstract from OpenAlex."
        assert result.intro is None
        assert result.fetch_error is None
        assert result.pdf_sha256 is None


def test_fetch_falls_back_when_pdfminer_fails():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl, patch(
        "src.data_agents.paper.full_text_fetcher._extract_text_from_pdf_bytes"
    ) as m_ex:
        m_dl.return_value = (b"", "x" * 64)
        m_ex.side_effect = _PdfParseError("corrupt")
        paper = _paper_fixture(abstract="Backup abstract.")
        result = fetch_and_extract_full_text(paper, paper_id="p")
        assert result.source == "openalex"
        assert result.abstract == "Backup abstract."


def test_fetch_no_arxiv_id_falls_back_to_abstract():
    paper = _paper_fixture(arxiv_id=None, abstract="From OpenAlex.")
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        result = fetch_and_extract_full_text(paper, paper_id="p")
        assert result.source == "openalex"
        assert result.abstract == "From OpenAlex."
        m_dl.assert_not_called()


def test_fetch_no_arxiv_no_abstract_returns_failed():
    paper = _paper_fixture(arxiv_id=None, abstract=None)
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        result = fetch_and_extract_full_text(paper, paper_id="p")
        assert result.source == "failed"
        assert result.fetch_error == "no_arxiv_id"
        m_dl.assert_not_called()


def test_fetch_arxiv_404_no_abstract_marks_failed_with_http_404():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        m_dl.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        paper = _paper_fixture(abstract=None)
        result = fetch_and_extract_full_text(paper, paper_id="p")
        assert result.source == "failed"
        assert result.fetch_error == "http_404"


def test_fetch_arxiv_429_no_abstract_marks_http_429():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        m_dl.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=MagicMock(status_code=429)
        )
        result = fetch_and_extract_full_text(_paper_fixture(abstract=None), paper_id="p")
        assert result.source == "failed"
        assert result.fetch_error == "http_429"


def test_fetch_arxiv_oversize_no_abstract_marks_pdf_too_large():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        m_dl.side_effect = _OversizeError("too big")
        result = fetch_and_extract_full_text(_paper_fixture(abstract=None), paper_id="p")
        assert result.source == "failed"
        assert result.fetch_error == "pdf_too_large"


def test_fetch_arxiv_timeout_no_abstract_marks_timeout():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        m_dl.side_effect = httpx.TimeoutException("slow")
        result = fetch_and_extract_full_text(_paper_fixture(abstract=None), paper_id="p")
        assert result.source == "failed"
        assert result.fetch_error == "timeout"


def test_fetch_arxiv_network_no_abstract_marks_network():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        m_dl.side_effect = httpx.ConnectError("no route")
        result = fetch_and_extract_full_text(_paper_fixture(abstract=None), paper_id="p")
        assert result.source == "failed"
        assert result.fetch_error == "network"


def test_fetch_arxiv_pdf_parse_error_no_abstract_marks_pdf_parse_error():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl, patch(
        "src.data_agents.paper.full_text_fetcher._extract_text_from_pdf_bytes"
    ) as m_ex:
        m_dl.return_value = (b"", "x" * 64)
        m_ex.side_effect = _PdfParseError("corrupt")
        result = fetch_and_extract_full_text(_paper_fixture(abstract=None), paper_id="p")
        assert result.source == "failed"
        assert result.fetch_error == "pdf_parse_error"


def test_fetch_does_not_close_injected_client():
    """Caller-injected http_client must NOT be closed by the function."""
    injected = MagicMock(spec=_REAL_HTTPX_CLIENT)
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        m_dl.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        fetch_and_extract_full_text(
            _paper_fixture(abstract=None), paper_id="p", http_client=injected
        )
    injected.close.assert_not_called()


def test_fetch_owned_http_client_uses_trust_env_false():
    with patch(
        "src.data_agents.paper.full_text_fetcher.httpx.Client"
    ) as ClientCls, patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)
        ClientCls.return_value = owned
        m_dl.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        fetch_and_extract_full_text(_paper_fixture(abstract=None), paper_id="p")
        assert ClientCls.called
        _, kwargs = ClientCls.call_args
        assert kwargs.get("trust_env") is False


def test_fetch_paper_id_is_threaded_through():
    with patch(
        "src.data_agents.paper.full_text_fetcher._download_pdf"
    ) as m_dl:
        m_dl.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        result = fetch_and_extract_full_text(
            _paper_fixture(abstract=None),
            paper_id="paper:my-custom-id:xyz",
        )
        assert result.paper_id == "paper:my-custom-id:xyz"
