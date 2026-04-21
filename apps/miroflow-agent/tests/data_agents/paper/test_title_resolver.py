"""RED-phase tests for M2.2 paper title resolver.

Source of truth: docs/plans/2026-04-21-002-m2.2-paper-title-resolver.md
Requirements: R1 signature, R2 dataclass fields, R3 cascade, R4 None below threshold,
R5 rate limits, R6 pure HTTP (no DB/FS), R7 hermetic (no live network),
R8 cache Protocol hook, R9 abstract reconstruction.

Organized by Unit:
  Unit 1 — helpers (dataclass, jaccard, inverted-index, cache key, Protocol)
  Unit 2 — OpenAlex title search
  Unit 3 — arxiv title search
  Unit 4 — orchestrator resolve_paper_by_title (cascade + cache + web_search)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.data_agents.paper.title_resolver import (
    ResolvedPaper,
    TitleResolutionCache,
    _arxiv_entry_to_resolved,
    _openalex_work_to_resolved,
    _reconstruct_abstract_from_inverted_index,
    _search_arxiv_by_title,
    _search_openalex_by_title,
    _search_web_by_title,
    _title_cache_key,
    _title_jaccard,
    resolve_paper_by_title,
)

# Capture real class references BEFORE any test patches httpx.Client
# Learned from M0.1: patch() mutates the shared httpx module for the with-scope.
_REAL_HTTPX_CLIENT = httpx.Client
_REAL_HTTPX_RESPONSE = httpx.Response


# =============================================================================
# Unit 1 — helpers + dataclass
# =============================================================================


def test_resolved_paper_dataclass_smoke():
    paper = ResolvedPaper(
        title="Deep Learning for Images",
        doi="10.1234/abc",
        openalex_id="W123",
        arxiv_id=None,
        abstract="We study ...",
        pdf_url=None,
        authors=("A. Smith", "B. Jones"),
        year=2023,
        venue="NeurIPS",
        match_confidence=0.92,
        match_source="openalex",
    )
    assert paper.doi == "10.1234/abc"
    assert paper.authors == ("A. Smith", "B. Jones")
    assert paper.match_source == "openalex"


def test_resolved_paper_is_frozen():
    paper = ResolvedPaper(
        title="T",
        doi=None,
        openalex_id=None,
        arxiv_id=None,
        abstract=None,
        pdf_url=None,
        authors=(),
        year=None,
        venue=None,
        match_confidence=0.0,
        match_source="openalex",
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        paper.title = "mutated"


def test_resolved_paper_authors_is_tuple_not_list():
    # Tuple required for hashability / frozen semantics.
    paper = ResolvedPaper(
        title="T",
        doi=None,
        openalex_id=None,
        arxiv_id=None,
        abstract=None,
        pdf_url=None,
        authors=("A", "B"),
        year=None,
        venue=None,
        match_confidence=0.5,
        match_source="arxiv",
    )
    assert isinstance(paper.authors, tuple)


# --- _title_jaccard ---


def test_jaccard_identical_titles():
    assert _title_jaccard("Deep Learning for Images", "Deep Learning for Images") == 1.0


def test_jaccard_case_punctuation_whitespace_insensitive():
    assert (
        _title_jaccard(
            "Deep Learning for Images", "DEEP  LEARNING, for Images!"
        )
        == 1.0
    )


def test_jaccard_disjoint_tokens():
    # Pure Latin vs pure Chinese — zero overlap after normalization.
    assert _title_jaccard("Totally Different Title", "完全不同的标题") == 0.0


def test_jaccard_partial_overlap_returns_fraction():
    # "Deep Learning for Images" vs "Deep Learning for Image"
    # intersection: {deep, learning, for} = 3
    # union: {deep, learning, for, images, image} = 5
    # jaccard = 3/5 = 0.6
    result = _title_jaccard(
        "Deep Learning for Images", "Deep Learning for Image"
    )
    assert 0.55 <= result <= 0.65


def test_jaccard_empty_string_returns_zero():
    assert _title_jaccard("", "anything") == 0.0
    assert _title_jaccard("anything", "") == 0.0
    assert _title_jaccard("", "") == 0.0


# --- _reconstruct_abstract_from_inverted_index ---


def test_reconstruct_abstract_happy_path():
    inverted = {
        "The": [0, 4],
        "cat": [1],
        "sat": [2, 6],
        "on": [3],
        "mat": [5],
        "there": [7],
    }
    result = _reconstruct_abstract_from_inverted_index(inverted)
    assert result is not None
    # Position order: 0=The, 1=cat, 2=sat, 3=on, 4=The, 5=mat, 6=sat, 7=there
    expected_tokens = ["The", "cat", "sat", "on", "The", "mat", "sat", "there"]
    assert result.split() == expected_tokens


def test_reconstruct_abstract_empty_dict_returns_none():
    assert _reconstruct_abstract_from_inverted_index({}) is None


def test_reconstruct_abstract_none_input_returns_none():
    assert _reconstruct_abstract_from_inverted_index(None) is None


def test_reconstruct_abstract_position_cap_rejects_pathological():
    # Positions over 5000 are treated as malformed — return None.
    assert _reconstruct_abstract_from_inverted_index({"word": [5001]}) is None


# --- _title_cache_key ---


def test_cache_key_stable_across_normalization():
    key_a = _title_cache_key("Foo Bar")
    key_b = _title_cache_key("foo bar")
    key_c = _title_cache_key("  Foo,  Bar!  ")
    assert key_a == key_b == key_c


def test_cache_key_is_hex_sha1():
    key = _title_cache_key("Some Title")
    # sha1 hex is 40 chars
    assert len(key) == 40
    assert all(c in "0123456789abcdef" for c in key)


def test_cache_key_differs_for_different_titles():
    assert _title_cache_key("Title One") != _title_cache_key("Title Two")


# --- TitleResolutionCache Protocol ---


def test_title_resolution_cache_protocol_duck_typed():
    """A dict-backed fake should satisfy the Protocol via duck typing."""

    class _FakeCache:
        def __init__(self):
            self._store: dict[str, ResolvedPaper] = {}

        def get(self, key: str) -> ResolvedPaper | None:
            return self._store.get(key)

        def set(self, key: str, value: ResolvedPaper) -> None:
            self._store[key] = value

    cache = _FakeCache()
    # Not asserting isinstance(cache, TitleResolutionCache) — Protocol may or may not
    # be runtime_checkable. Just verify the contract is usable.
    paper = ResolvedPaper(
        title="T",
        doi=None,
        openalex_id=None,
        arxiv_id=None,
        abstract=None,
        pdf_url=None,
        authors=(),
        year=None,
        venue=None,
        match_confidence=0.9,
        match_source="openalex",
    )
    cache.set("k", paper)
    assert cache.get("k") is paper
    assert cache.get("missing") is None


# =============================================================================
# Unit 2 — OpenAlex title search
# =============================================================================


def _openalex_work_fixture(
    *,
    title: str = "Deep Learning for Images",
    year: int | None = 2023,
    doi: str | None = "https://doi.org/10.1234/abc",
    openalex_id: str = "https://openalex.org/W123",
    authors: list[str] | None = None,
    inverted_index: dict | None = None,
    venue: str = "NeurIPS",
) -> dict:
    return {
        "id": openalex_id,
        "doi": doi,
        "title": title,
        "publication_year": year,
        "host_venue": {"display_name": venue},
        "authorships": [
            {"author": {"display_name": name}}
            for name in (authors or ["John Smith", "Jane Doe"])
        ],
        "abstract_inverted_index": inverted_index,
    }


def _mock_openalex_response(works: list[dict]):
    resp = MagicMock(spec=_REAL_HTTPX_RESPONSE)
    resp.json.return_value = {"results": works}
    resp.raise_for_status.return_value = None
    return resp


def _fake_http_client_returning(response):
    client = MagicMock(spec=_REAL_HTTPX_CLIENT)
    client.get.return_value = response
    client.trust_env = False
    return client


def test_openalex_search_returns_results_list():
    works = [_openalex_work_fixture()]
    http = _fake_http_client_returning(_mock_openalex_response(works))
    results = _search_openalex_by_title("Deep Learning for Images", http_client=http)
    assert len(results) == 1
    assert results[0]["title"] == "Deep Learning for Images"


def test_openalex_search_empty_results_returns_empty_list():
    http = _fake_http_client_returning(_mock_openalex_response([]))
    assert (
        _search_openalex_by_title("anything", http_client=http) == []
    )


def test_openalex_search_http_error_returns_empty_does_not_raise():
    resp = MagicMock(spec=_REAL_HTTPX_RESPONSE)
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=MagicMock(status_code=429)
    )
    http = _fake_http_client_returning(resp)
    # Should log warning and return empty, NOT propagate.
    assert _search_openalex_by_title("anything", http_client=http) == []


def test_openalex_search_json_decode_error_returns_empty():
    resp = MagicMock(spec=_REAL_HTTPX_RESPONSE)
    resp.json.side_effect = ValueError("bad json")
    resp.raise_for_status.return_value = None
    http = _fake_http_client_returning(resp)
    assert _search_openalex_by_title("anything", http_client=http) == []


def test_openalex_work_to_resolved_happy_path():
    inverted = {"We": [0], "study": [1], "neural": [2], "nets.": [3]}
    work = _openalex_work_fixture(inverted_index=inverted)
    resolved, confidence = _openalex_work_to_resolved(
        work,
        query_title="Deep Learning for Images",
        author_hint=None,
        year_hint=None,
    )
    assert resolved.title == "Deep Learning for Images"
    assert resolved.doi == "10.1234/abc"  # bare DOI
    assert resolved.openalex_id == "W123"  # bare W-form
    assert resolved.arxiv_id is None
    assert resolved.abstract is not None
    assert "neural" in resolved.abstract
    assert resolved.authors == ("John Smith", "Jane Doe")
    assert resolved.year == 2023
    assert resolved.venue == "NeurIPS"
    assert resolved.match_source == "openalex"
    assert confidence == 1.0


def test_openalex_work_to_resolved_year_hint_boost():
    work = _openalex_work_fixture(title="Deep Learning for Image")  # tokens differ by 1
    resolved, confidence_no_hint = _openalex_work_to_resolved(
        work,
        query_title="Deep Learning for Images",
        author_hint=None,
        year_hint=None,
    )
    # Matching year should give +0.05 boost.
    resolved_boost, confidence_boost = _openalex_work_to_resolved(
        work,
        query_title="Deep Learning for Images",
        author_hint=None,
        year_hint=2023,
    )
    assert confidence_boost > confidence_no_hint
    assert abs((confidence_boost - confidence_no_hint) - 0.05) < 1e-9


def test_openalex_work_to_resolved_author_hint_boost():
    work = _openalex_work_fixture(
        title="Deep Learning for Image",
        authors=["John Smith", "Jane Doe"],
    )
    _, confidence_no_hint = _openalex_work_to_resolved(
        work,
        query_title="Deep Learning for Images",
        author_hint=None,
        year_hint=None,
    )
    _, confidence_hint = _openalex_work_to_resolved(
        work,
        query_title="Deep Learning for Images",
        author_hint="Smith",
        year_hint=None,
    )
    assert confidence_hint > confidence_no_hint


def test_openalex_work_to_resolved_no_inverted_index_gives_none_abstract():
    work = _openalex_work_fixture(inverted_index=None)
    resolved, _conf = _openalex_work_to_resolved(
        work,
        query_title="Deep Learning for Images",
        author_hint=None,
        year_hint=None,
    )
    assert resolved.abstract is None


def test_openalex_work_to_resolved_strips_doi_url_prefix():
    work = _openalex_work_fixture(doi="https://doi.org/10.999/xyz")
    resolved, _conf = _openalex_work_to_resolved(
        work,
        query_title=work["title"],
        author_hint=None,
        year_hint=None,
    )
    assert resolved.doi == "10.999/xyz"


def test_openalex_work_to_resolved_strips_id_url_prefix():
    work = _openalex_work_fixture(openalex_id="https://openalex.org/W987")
    resolved, _conf = _openalex_work_to_resolved(
        work,
        query_title=work["title"],
        author_hint=None,
        year_hint=None,
    )
    assert resolved.openalex_id == "W987"


def test_openalex_owns_http_client_uses_trust_env_false():
    """When no http_client is injected, create one with trust_env=False."""
    with patch("src.data_agents.paper.title_resolver.httpx.Client") as ClientCls:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)
        owned.get.return_value = _mock_openalex_response([])
        ClientCls.return_value = owned
        _search_openalex_by_title("anything")
        assert ClientCls.called
        _, kwargs = ClientCls.call_args
        assert kwargs.get("trust_env") is False


# =============================================================================
# Unit 3 — arxiv title search
# =============================================================================


_ARXIV_ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2310.12345v3</id>
    <title>Deep Learning for Images</title>
    <summary>We propose a new method for learning from images.</summary>
    <published>2023-10-15T00:00:00Z</published>
    <author><name>John Smith</name></author>
    <author><name>Jane Doe</name></author>
    <link rel="related" type="application/pdf" href="http://arxiv.org/pdf/2310.12345v3"/>
  </entry>
</feed>
"""

_ARXIV_ATOM_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>
"""


def _mock_arxiv_response(text: str):
    resp = MagicMock(spec=_REAL_HTTPX_RESPONSE)
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


def test_arxiv_search_returns_entries():
    http = _fake_http_client_returning(_mock_arxiv_response(_ARXIV_ATOM_FIXTURE))
    results = _search_arxiv_by_title("Deep Learning for Images", http_client=http)
    assert len(results) == 1


def test_arxiv_search_empty_feed_returns_empty():
    http = _fake_http_client_returning(_mock_arxiv_response(_ARXIV_ATOM_EMPTY))
    assert _search_arxiv_by_title("anything", http_client=http) == []


def test_arxiv_search_malformed_xml_returns_empty():
    http = _fake_http_client_returning(_mock_arxiv_response("<feed><<<not valid xml"))
    assert _search_arxiv_by_title("anything", http_client=http) == []


def test_arxiv_search_http_error_returns_empty():
    resp = MagicMock(spec=_REAL_HTTPX_RESPONSE)
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=MagicMock(status_code=429)
    )
    http = _fake_http_client_returning(resp)
    assert _search_arxiv_by_title("anything", http_client=http) == []


def test_arxiv_entry_to_resolved_happy_path():
    http = _fake_http_client_returning(_mock_arxiv_response(_ARXIV_ATOM_FIXTURE))
    entries = _search_arxiv_by_title("Deep Learning for Images", http_client=http)
    resolved, confidence = _arxiv_entry_to_resolved(
        entries[0],
        query_title="Deep Learning for Images",
        author_hint=None,
        year_hint=None,
    )
    assert resolved.arxiv_id == "2310.12345"  # version stripped
    assert resolved.doi is None
    assert resolved.openalex_id is None
    assert resolved.venue == "arXiv"
    assert resolved.year == 2023
    assert resolved.authors == ("John Smith", "Jane Doe")
    assert resolved.abstract is not None
    assert "images" in resolved.abstract.lower()
    assert resolved.pdf_url is not None
    assert "arxiv.org" in resolved.pdf_url
    assert resolved.match_source == "arxiv"
    assert confidence == 1.0


def test_arxiv_entry_to_resolved_strips_version_suffix():
    """arxiv returns `2310.12345v3`; our arxiv_id must be `2310.12345`."""
    http = _fake_http_client_returning(_mock_arxiv_response(_ARXIV_ATOM_FIXTURE))
    entries = _search_arxiv_by_title("Deep Learning for Images", http_client=http)
    resolved, _c = _arxiv_entry_to_resolved(
        entries[0],
        query_title="Deep Learning for Images",
        author_hint=None,
        year_hint=None,
    )
    assert "v3" not in resolved.arxiv_id
    assert resolved.arxiv_id == "2310.12345"


def test_arxiv_entry_pdf_url_constructed_when_no_explicit_pdf_link():
    atom_no_pdf = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001</id>
    <title>Paper Without PDF Link</title>
    <summary>A study.</summary>
    <published>2024-01-01T00:00:00Z</published>
    <author><name>Alice</name></author>
  </entry>
</feed>
"""
    http = _fake_http_client_returning(_mock_arxiv_response(atom_no_pdf))
    entries = _search_arxiv_by_title("Paper Without PDF Link", http_client=http)
    resolved, _c = _arxiv_entry_to_resolved(
        entries[0],
        query_title="Paper Without PDF Link",
        author_hint=None,
        year_hint=None,
    )
    # pdf_url should be constructed from arxiv_id
    assert resolved.pdf_url is not None
    assert "2401.00001" in resolved.pdf_url
    assert resolved.pdf_url.endswith(".pdf")


# =============================================================================
# Unit 4 — orchestrator resolve_paper_by_title
# =============================================================================


class _FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, ResolvedPaper] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, ResolvedPaper]] = []

    def get(self, key: str) -> ResolvedPaper | None:
        self.get_calls.append(key)
        return self.store.get(key)

    def set(self, key: str, value: ResolvedPaper) -> None:
        self.set_calls.append((key, value))
        self.store[key] = value


def _resolved_fixture(source: str, confidence: float) -> ResolvedPaper:
    return ResolvedPaper(
        title="Some Paper",
        doi="10.1/x" if source == "openalex" else None,
        openalex_id="W1" if source == "openalex" else None,
        arxiv_id="2301.00001" if source == "arxiv" else None,
        abstract="abs",
        pdf_url=None,
        authors=("A",),
        year=2023,
        venue="X",
        match_confidence=confidence,
        match_source=source,
    )


def test_resolve_short_circuits_on_openalex_hit():
    """OpenAlex hits ≥ 0.85 → arxiv and web_search must NOT be called."""
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._search_arxiv_by_title"
    ) as m_ax, patch(
        "src.data_agents.paper.title_resolver._openalex_work_to_resolved"
    ) as m_oa_to_r:
        m_oa.return_value = [{"fake": "work"}]
        m_oa_to_r.return_value = (_resolved_fixture("openalex", 0.90), 0.90)
        result = resolve_paper_by_title("A Paper Title")
        assert result is not None
        assert result.match_source == "openalex"
        assert result.match_confidence == 0.90
        m_ax.assert_not_called()


def test_resolve_falls_through_to_arxiv_when_openalex_below_threshold():
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._openalex_work_to_resolved"
    ) as m_oa_to_r, patch(
        "src.data_agents.paper.title_resolver._search_arxiv_by_title"
    ) as m_ax, patch(
        "src.data_agents.paper.title_resolver._arxiv_entry_to_resolved"
    ) as m_ax_to_r:
        m_oa.return_value = [{"fake": "low"}]
        m_oa_to_r.return_value = (_resolved_fixture("openalex", 0.70), 0.70)
        m_ax.return_value = [{"fake": "arxiv_entry"}]
        m_ax_to_r.return_value = (_resolved_fixture("arxiv", 0.92), 0.92)
        result = resolve_paper_by_title("A Paper Title")
        assert result is not None
        assert result.match_source == "arxiv"


def test_resolve_returns_none_when_all_sources_miss_and_no_web_search():
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._search_arxiv_by_title"
    ) as m_ax:
        m_oa.return_value = []
        m_ax.return_value = []
        result = resolve_paper_by_title("Very Obscure Paper Title")
        assert result is None


def test_resolve_uses_web_search_when_provided_and_both_miss():
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._search_arxiv_by_title"
    ) as m_ax, patch(
        "src.data_agents.paper.title_resolver._search_web_by_title"
    ) as m_web:
        m_oa.return_value = []
        m_ax.return_value = []
        m_web.return_value = _resolved_fixture("web_search", 0.88)
        web_provider = MagicMock()
        result = resolve_paper_by_title("Title", web_search=web_provider)
        assert result is not None
        assert result.match_source == "web_search"
        m_web.assert_called_once()


def test_resolve_web_search_not_called_when_web_search_is_none():
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._search_arxiv_by_title"
    ) as m_ax, patch(
        "src.data_agents.paper.title_resolver._search_web_by_title"
    ) as m_web:
        m_oa.return_value = []
        m_ax.return_value = []
        result = resolve_paper_by_title("Title")
        assert result is None
        m_web.assert_not_called()


def test_resolve_cache_hit_skips_all_searches():
    cache = _FakeCache()
    cached_paper = _resolved_fixture("openalex", 0.95)
    key = _title_cache_key("Cached Paper")
    cache.store[key] = cached_paper
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._search_arxiv_by_title"
    ) as m_ax:
        result = resolve_paper_by_title("Cached Paper", cache=cache)
        assert result is cached_paper
        m_oa.assert_not_called()
        m_ax.assert_not_called()


def test_resolve_cache_set_on_miss_then_hit():
    cache = _FakeCache()
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._openalex_work_to_resolved"
    ) as m_oa_to_r:
        m_oa.return_value = [{"fake": "work"}]
        m_oa_to_r.return_value = (_resolved_fixture("openalex", 0.92), 0.92)
        resolve_paper_by_title("New Paper", cache=cache)
    # cache.set should have been called once with the result
    assert len(cache.set_calls) == 1


def test_resolve_does_not_cache_none_results():
    cache = _FakeCache()
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._search_arxiv_by_title"
    ) as m_ax:
        m_oa.return_value = []
        m_ax.return_value = []
        result = resolve_paper_by_title("Obscure", cache=cache)
        assert result is None
    assert cache.set_calls == []


def test_resolve_empty_title_returns_none_without_http():
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa:
        result = resolve_paper_by_title("")
        assert result is None
        m_oa.assert_not_called()


def test_resolve_web_search_provider_raising_does_not_propagate():
    """If Serper quota is exhausted and provider raises, return None gracefully."""
    with patch(
        "src.data_agents.paper.title_resolver._search_openalex_by_title"
    ) as m_oa, patch(
        "src.data_agents.paper.title_resolver._search_arxiv_by_title"
    ) as m_ax, patch(
        "src.data_agents.paper.title_resolver._search_web_by_title"
    ) as m_web:
        m_oa.return_value = []
        m_ax.return_value = []
        m_web.side_effect = RuntimeError("quota exceeded")
        result = resolve_paper_by_title("Title", web_search=MagicMock())
        assert result is None


# --- _search_web_by_title filters non-scholarly domains ---


def test_search_web_filters_non_scholarly_domains():
    """Organic results from blog.example.com / github.com should be filtered out."""
    web_provider = MagicMock()
    web_provider.search.return_value = {
        "organic": [
            {
                "title": "Some Paper on Arxiv",
                "link": "https://arxiv.org/abs/2310.12345",
                "snippet": "Abstract of the paper.",
            },
            {
                "title": "Blog post about the paper",
                "link": "https://blog.example.com/some-paper",
                "snippet": "Blog summary.",
            },
            {
                "title": "GitHub repo",
                "link": "https://github.com/user/repo",
                "snippet": "Code for the paper.",
            },
        ]
    }
    result = _search_web_by_title(
        "Some Paper on Arxiv",
        web_search=web_provider,
        author_hint=None,
        year_hint=None,
    )
    # arxiv result should rank; blog/github filtered out.
    assert result is not None
    assert result.match_source == "web_search"
    assert "arxiv" in result.title.lower() or "2310" in (result.arxiv_id or "")
