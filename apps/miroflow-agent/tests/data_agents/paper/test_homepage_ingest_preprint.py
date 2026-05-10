"""Tests for the preprint / page-only fallback path in homepage_ingest.

Per OpenSpec change `prof-paper-patent-from-page-flow` spec Requirement
"Preprint listed on professor page" + Paper Review §3.1 P4.

The pre-existing CLI tests in tests/scripts/ exercise the orchestrator
shell; these tests target the new pure helpers added in T3:
`_synthesize_page_only_resolution` and `_split_page_authors`.
"""

from __future__ import annotations

from src.data_agents.paper.homepage_ingest import (
    _PROF_PAGE_ONLY_SOURCE,
    _split_page_authors,
    _synthesize_page_only_resolution,
)
from src.data_agents.professor.homepage_publications import HomepagePublication


def _make_publication(**overrides) -> HomepagePublication:
    base = dict(
        raw_title="Foo Bar",
        clean_title="Foo Bar",
        authors_text=None,
        venue_text=None,
        year=None,
        source_url="https://example.test/prof",
        source_anchor=None,
    )
    base.update(overrides)
    return HomepagePublication(**base)


# --- _split_page_authors ----------------------------------------------------


def test_split_page_authors_handles_comma_delimited():
    assert _split_page_authors("Smith, J., Lee, K., Wang, X.") == [
        "Smith",
        "J.",
        "Lee",
        "K.",
        "Wang",
        "X.",
    ]
    # Note: this naive split does not handle "Last, First" — admin/spec
    # accepts low fidelity; future enrichment will replace via OpenAlex.


def test_split_page_authors_handles_semicolon_delimited():
    assert _split_page_authors("Smith J.; Lee K.; Wang X.") == [
        "Smith J.",
        "Lee K.",
        "Wang X.",
    ]


def test_split_page_authors_handles_chinese_enumeration():
    assert _split_page_authors("张三、李四、王五") == ["张三", "李四", "王五"]


def test_split_page_authors_strips_whitespace_and_empty():
    assert _split_page_authors("  Smith J.  ,  ,  Lee K.  ") == [
        "Smith J.",
        "Lee K.",
    ]


def test_split_page_authors_returns_empty_list_on_blank():
    assert _split_page_authors("") == []
    assert _split_page_authors("   ") == []


# --- _synthesize_page_only_resolution ---------------------------------------


def test_synthesize_preprint_minimum_fields():
    """Scenario: Preprint listed on prof page (Paper Review §3.1 P4 +
    spec Requirement "Preprint listed on professor page")."""
    pub = _make_publication(
        clean_title="Foo Bar",
        year=2026,
        venue_text=None,  # preprint — no venue
        authors_text=None,  # only prof name available
    )
    resolved = _synthesize_page_only_resolution(pub, canonical_name="张三")
    assert resolved.title == "Foo Bar"
    assert resolved.year == 2026
    assert resolved.venue is None
    assert resolved.doi is None
    assert resolved.arxiv_id is None
    assert resolved.openalex_id is None
    assert resolved.abstract is None
    assert resolved.match_source == _PROF_PAGE_ONLY_SOURCE
    assert resolved.match_confidence == 1.0
    # When authors_text is None, fallback to "<prof> et al."
    assert resolved.authors == ("张三 et al.",)


def test_synthesize_preserves_page_authors_when_available():
    pub = _make_publication(
        clean_title="A Better Paper",
        year=2026,
        authors_text="Smith J., Lee K., 张三",
    )
    resolved = _synthesize_page_only_resolution(pub, canonical_name="张三")
    assert "Smith J." in resolved.authors
    assert "Lee K." in resolved.authors
    assert "张三" in resolved.authors


def test_synthesize_preserves_venue_when_available():
    pub = _make_publication(
        clean_title="Accepted at TopVenue",
        year=2026,
        venue_text="ICML 2026",
        authors_text=None,
    )
    resolved = _synthesize_page_only_resolution(pub, canonical_name="李四")
    assert resolved.venue == "ICML 2026"
    assert resolved.year == 2026


def test_synthesize_handles_missing_year():
    """Some prof pages list publications without explicit year."""
    pub = _make_publication(clean_title="Untimed Paper", year=None)
    resolved = _synthesize_page_only_resolution(pub, canonical_name="王五")
    assert resolved.year is None
    assert resolved.title == "Untimed Paper"


def test_synthesize_blank_authors_text_uses_fallback():
    """authors_text='' or '   ' falls back to '<prof> et al.'."""
    pub_empty = _make_publication(authors_text="")
    pub_ws = _make_publication(authors_text="   ")
    for pub in (pub_empty, pub_ws):
        resolved = _synthesize_page_only_resolution(pub, canonical_name="赵六")
        assert resolved.authors == ("赵六 et al.",)
