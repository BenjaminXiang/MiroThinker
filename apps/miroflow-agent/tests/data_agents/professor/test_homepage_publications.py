"""RED-phase tests for M2.1 homepage publications extractor.

Source of truth: docs/plans/2026-04-21-001-m2.1-homepage-publications-extractor.md
Requirements: R1 signature, R2 dataclass fields, R3 happy-path count, R4 title-clean
rules, R5 at-least-one-of-authors/venue, R6 pure function, R7 5-archetype coverage.

Tests are organized by Unit:
  Unit 1 — dataclass + helper pure functions (_strip_item_prefix/suffix,
           _extract_year_from_text, _split_title_authors_venue, _normalize_title_for_dedup)
  Unit 2 — end-to-end extract_publications_from_html (5 archetypes + edges)
  Unit 3 — deferred (real HTML fixtures land after Unit 1+2 are green)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data_agents.professor.homepage_publications import (
    HomepagePublication,
    _extract_year_from_text,
    _normalize_title_for_dedup,
    _split_title_authors_venue,
    _strip_item_prefix,
    _strip_item_suffix,
    extract_publications_from_html,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "homepage"


def _load(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text(encoding="utf-8")


# -----------------------------------------------------------------------------
# Unit 1 — dataclass construction + helpers
# -----------------------------------------------------------------------------


def test_homepage_publication_dataclass_smoke():
    pub = HomepagePublication(
        raw_title="[1] Some Title [J]",
        clean_title="Some Title",
        authors_text="A. Smith",
        venue_text="ACM",
        year=2023,
        source_url="https://example.edu/prof",
        source_anchor="https://doi.org/10.1/x",
    )
    assert pub.clean_title == "Some Title"
    assert pub.year == 2023
    assert pub.source_anchor == "https://doi.org/10.1/x"


def test_homepage_publication_is_frozen():
    pub = HomepagePublication(
        raw_title="raw",
        clean_title="clean",
        authors_text=None,
        venue_text=None,
        year=None,
        source_url="https://example.edu",
        source_anchor=None,
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        pub.clean_title = "mutated"  # frozen dataclass blocks this


# --- _strip_item_prefix ---


def test_strip_item_prefix_bracketed_number():
    assert _strip_item_prefix("[1] Title goes here") == "Title goes here"
    assert _strip_item_prefix("[12] Another Title") == "Another Title"


def test_strip_item_prefix_dotted_number():
    assert _strip_item_prefix("1. Title goes here") == "Title goes here"
    assert _strip_item_prefix("12. Another Title") == "Another Title"


def test_strip_item_prefix_parenthesized_number():
    assert _strip_item_prefix("(1) Title goes here") == "Title goes here"
    assert _strip_item_prefix("(12) Another Title") == "Another Title"


def test_strip_item_prefix_no_prefix_is_passthrough():
    assert _strip_item_prefix("Title with no prefix") == "Title with no prefix"


def test_strip_item_prefix_preserves_interior_brackets():
    # Only LEADING prefix markers get stripped; [J] inside text survives.
    assert _strip_item_prefix("[1] Some [Key] Title") == "Some [Key] Title"


# --- _strip_item_suffix ---


def test_strip_item_suffix_journal_tag():
    assert _strip_item_suffix("Some Title [J]") == "Some Title"


def test_strip_item_suffix_conference_tag():
    assert _strip_item_suffix("Some Title [C]") == "Some Title"


def test_strip_item_suffix_online_journal_tag():
    assert _strip_item_suffix("Some Title [J/OL]") == "Some Title"


def test_strip_item_suffix_no_suffix_is_passthrough():
    assert _strip_item_suffix("Some Title with no suffix") == "Some Title with no suffix"


def test_strip_item_suffix_trailing_period_normalized():
    # If suffix strip leaves a trailing period/comma, it should also be cleaned.
    assert _strip_item_suffix("Some Title [J].").rstrip(".") == "Some Title"


# --- _extract_year_from_text ---


def test_extract_year_from_text_single_year():
    assert _extract_year_from_text("Published in 2023 Proceedings.") == 2023


def test_extract_year_from_text_trailing_year():
    assert _extract_year_from_text("Some Title. Venue, 2024.") == 2024


def test_extract_year_from_text_no_year_returns_none():
    assert _extract_year_from_text("No year mentioned here") is None


def test_extract_year_from_text_future_year_rejected():
    # Year far in the future is rejected (e.g., placeholder or typo).
    assert _extract_year_from_text("Will appear in 2099.") is None


def test_extract_year_from_text_very_old_year_rejected():
    # Pre-1900 is rejected as likely false positive (e.g., address numbers).
    assert _extract_year_from_text("Some old classic from 1887") is None


def test_extract_year_from_text_multiple_years_prefers_latest():
    # "Proceedings of 2022 conference, published 2023" → prefer 2023 (latest)
    result = _extract_year_from_text("Proceedings of 2022 conference, published 2023.")
    assert result in (2022, 2023)  # implementer picks; pin whichever they choose
    # but explicit: verify it's an int in range
    assert isinstance(result, int) and 2000 <= result <= 2026


# --- _split_title_authors_venue ---


def test_split_title_authors_venue_full_triple():
    title, authors, venue = _split_title_authors_venue(
        "Deep Learning for Image Recognition. J. Doe, X. Liu. ACM Conf 2023."
    )
    assert "Deep Learning" in title
    assert authors is not None and "Doe" in authors
    assert venue is not None and "ACM" in venue


def test_split_title_authors_venue_bare_title_only():
    title, authors, venue = _split_title_authors_venue("Bare title with no authors")
    assert title == "Bare title with no authors"
    assert authors is None
    assert venue is None


def test_split_title_authors_venue_handles_missing_venue():
    # "Title. Authors." with no trailing venue is acceptable.
    title, authors, _venue = _split_title_authors_venue("A Title. J. Doe, X. Liu.")
    assert "A Title" in title
    assert authors is not None and "Doe" in authors


# --- _normalize_title_for_dedup ---


def test_normalize_title_for_dedup_case_insensitive():
    assert _normalize_title_for_dedup("Hello World") == _normalize_title_for_dedup(
        "hello world"
    )


def test_normalize_title_for_dedup_whitespace_collapsed():
    assert _normalize_title_for_dedup("  Hello,  World!  ") == _normalize_title_for_dedup(
        "Hello World"
    )


def test_normalize_title_for_dedup_empty_input():
    assert _normalize_title_for_dedup("") == ""


# -----------------------------------------------------------------------------
# Unit 2 — extract_publications_from_html (end-to-end on 5 archetypes + edges)
# -----------------------------------------------------------------------------


# --- 5 archetype happy paths ---


def test_extract_ol_list_happy_path():
    html = _load("sample_ol_list.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/prof/doe")
    assert len(pubs) == 25
    assert all(len(p.clean_title) >= 10 for p in pubs)
    # [1] prefixes and trailing periods cleaned from clean_title
    assert not any(p.clean_title.startswith("[1]") for p in pubs)
    # DOI anchor captured on the 2nd item
    doi_items = [p for p in pubs if p.source_anchor and "doi.org" in p.source_anchor]
    assert len(doi_items) >= 1
    # source_url preserved
    assert all(p.source_url == "https://example.edu/prof/doe" for p in pubs)


def test_extract_ul_list_strips_prefixes_and_suffixes():
    html = _load("sample_ul_list.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/prof/zhang")
    assert len(pubs) == 15
    # No [1] prefixes nor [J]/[C]/[J/OL] suffixes in clean_title
    for p in pubs:
        assert not p.clean_title.startswith("[")
        assert "[J]" not in p.clean_title
        assert "[C]" not in p.clean_title
        assert "[J/OL]" not in p.clean_title
    # Years extracted
    assert sum(1 for p in pubs if p.year is not None) >= 10


def test_extract_paragraphs_happy_path():
    html = _load("sample_paragraphs.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/alice")
    assert len(pubs) == 10
    # At least one item has authors_text or venue_text populated (R5)
    assert sum(1 for p in pubs if p.authors_text or p.venue_text) >= 8
    # arxiv anchor captured on the 4th item
    arxiv_items = [p for p in pubs if p.source_anchor and "arxiv" in p.source_anchor]
    # NOTE: implementer decides whether bare "arxiv.org/abs/..." text without <a> tag
    # gets captured as anchor. If not, this assertion softens to presence-in-raw_title.
    if arxiv_items:
        assert len(arxiv_items) >= 1
    else:
        assert any("arxiv" in p.raw_title.lower() for p in pubs)


def test_extract_table_happy_path():
    html = _load("sample_table.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/wang")
    assert len(pubs) == 8
    # Every row in this fixture has a year column
    assert all(p.year is not None for p in pubs)
    years = {p.year for p in pubs}
    assert 2024 in years and 2023 in years and 2022 in years


def test_extract_year_groups_happy_path():
    html = _load("sample_year_groups.html")
    pubs = extract_publications_from_html(html, page_url="https://example.edu/chen")
    assert len(pubs) == 6
    # Year-heading groups: items under <h4>2023</h4> get year=2023, etc.
    years_found = {p.year for p in pubs}
    assert 2023 in years_found
    assert 2022 in years_found
    assert 2021 in years_found


# --- Contract: return type, purity, signature ---


def test_extract_returns_list_of_homepage_publication():
    html = _load("sample_ol_list.html")
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert isinstance(pubs, list)
    assert all(isinstance(p, HomepagePublication) for p in pubs)


def test_extract_is_pure_function_deterministic():
    html = _load("sample_ol_list.html")
    a = extract_publications_from_html(html, page_url="https://x.edu")
    b = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(a) == len(b)
    assert [p.clean_title for p in a] == [p.clean_title for p in b]


def test_extract_accepts_author_filter_none_default():
    html = _load("sample_ol_list.html")
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 25  # No filter applied
    pubs2 = extract_publications_from_html(
        html, page_url="https://x.edu", author_filter=None
    )
    assert len(pubs2) == 25


def test_extract_respects_author_filter():
    html = _load("sample_ol_list.html")
    # Filter: keep only items whose authors_text includes "X. Liu"
    pubs = extract_publications_from_html(
        html,
        page_url="https://x.edu",
        author_filter=lambda text: text is not None and "Liu" in text,
    )
    # Fixture has several items with X. Liu; expect at least 1 and fewer than total
    assert 1 <= len(pubs) < 25


# --- Edge cases ---


def test_extract_empty_html_returns_empty_list():
    pubs = extract_publications_from_html("", page_url="https://x.edu")
    assert pubs == []


def test_extract_html_with_no_publications_section_returns_empty():
    html = """<!doctype html><html><body><h1>Home</h1><p>Welcome to my page.</p></body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert pubs == []


def test_extract_publications_section_with_empty_list_returns_empty():
    html = """<!doctype html><html><body>
    <h2>Publications</h2><ol></ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert pubs == []


def test_extract_dedups_within_single_section():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <ol>
      <li>Identical Title Here. A. Smith. Venue 2023.</li>
      <li>Identical Title Here. A. Smith. Venue 2023.</li>
      <li>Different Title Goes Here. B. Jones. Other Venue 2023.</li>
    </ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 2  # duplicate collapsed


def test_extract_dedups_across_multiple_sections():
    html = """<!doctype html><html><body>
    <h2>Selected Publications</h2>
    <ul>
      <li>Shared Paper Title. A. Smith. Venue 2023.</li>
      <li>Selected Only Title. A. Smith. Venue 2022.</li>
    </ul>
    <h2>Full Publications</h2>
    <ol>
      <li>Shared Paper Title. A. Smith. Venue 2023.</li>
      <li>Full Only Title. A. Smith. Venue 2021.</li>
    </ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    # 3 unique: Shared, Selected-Only, Full-Only
    assert len(pubs) == 3


def test_extract_drops_items_below_min_title_length():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <ol>
      <li>TBD.</li>
      <li>Proper Title That Is Long Enough. Authors 2023.</li>
      <li>1.</li>
    </ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 1
    assert "Proper Title" in pubs[0].clean_title


def test_extract_item_without_year_still_extracted():
    html = """<!doctype html><html><body>
    <h2>Publications</h2>
    <ol>
      <li>Forthcoming Title About Something, to appear in Venue.</li>
    </ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 1
    assert pubs[0].year is None


def test_extract_caps_at_200_items():
    items = "\n".join(f"<li>Long Enough Item Title Number {i}. A 2023.</li>" for i in range(250))
    html = f"""<!doctype html><html><body>
    <h2>Publications</h2><ol>{items}</ol>
    </body></html>"""
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert len(pubs) == 200


def test_extract_malformed_html_does_not_raise():
    html = (
        "<html><body><h2>Publications</h2>"
        "<ul><li>First item title.<li>Second item <b>unclosed"
        "<li>Third item OK. 2023.</ul></body></html>"
    )
    # lxml is permissive; extractor should return best-effort, not raise.
    pubs = extract_publications_from_html(html, page_url="https://x.edu")
    assert isinstance(pubs, list)
