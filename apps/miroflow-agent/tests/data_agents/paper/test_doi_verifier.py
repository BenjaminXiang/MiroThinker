from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from src.data_agents.paper import doi_verifier as verifier
from src.data_agents.paper.title_resolver import ResolvedPaper

_ATOM = "http://www.w3.org/2005/Atom"


def _resolved_paper(
    *,
    title: str = "Graph Neural Networks for Shenzhen Innovation",
    doi: str | None = "10.1234/example",
    openalex_id: str | None = "W123",
    arxiv_id: str | None = None,
    authors: tuple[str, ...] = ("Alice Smith", "Carol Zhang"),
    source: str = "openalex",
) -> ResolvedPaper:
    return ResolvedPaper(
        title=title,
        doi=doi,
        openalex_id=openalex_id,
        arxiv_id=arxiv_id,
        abstract=None,
        pdf_url=None,
        authors=authors,
        year=2024,
        venue="TestConf",
        match_confidence=0.93,
        match_source=source,
    )


def _openalex_work(
    *,
    title: str = "Graph Neural Networks for Shenzhen Innovation",
    authors: list[str] | None = None,
    doi: str | None = "https://doi.org/10.1234/example",
) -> dict[str, Any]:
    return {
        "id": "https://openalex.org/W123",
        "doi": doi,
        "title": title,
        "publication_year": 2024,
        "host_venue": {"display_name": "TestConf"},
        "authorships": [
            {"author": {"display_name": author}}
            for author in (authors or ["Alice Smith", "Carol Zhang"])
        ],
        "abstract_inverted_index": None,
    }


def _arxiv_entry(
    *,
    title: str = "Graph Neural Networks for Shenzhen Innovation",
    authors: tuple[str, ...] = ("Alice Smith", "Carol Zhang"),
) -> ET.Element:
    author_xml = "".join(
        f"<author><name>{author}</name></author>" for author in authors
    )
    return ET.fromstring(
        f"""
        <entry xmlns="{_ATOM}">
          <id>http://arxiv.org/abs/2401.00001v1</id>
          <title>{title}</title>
          <published>2024-01-02T00:00:00Z</published>
          <summary>We study innovation networks.</summary>
          {author_xml}
          <link href="http://arxiv.org/pdf/2401.00001v1" rel="related" type="application/pdf" />
        </entry>
        """
    )


def test_cache_hit_confirms_when_external_id_present() -> None:
    result = verifier.verify_via_cache(
        {"paper_id": "P1", "cached_resolution": _resolved_paper()}
    )

    assert result is not None
    assert result.status == "confirmed"
    assert result.source == "cache"
    assert result.external_id == "10.1234/example"


def test_openalex_fuzzy_hit_confirms(monkeypatch: Any) -> None:
    client = object()
    seen_client = []

    def _fake_search(title: str, *, http_client=None) -> list[dict[str, Any]]:
        seen_client.append(http_client)
        return [
            _openalex_work(
                title="Graph Neural Networks for Shenzhen Innovation",
                authors=["Alice Smith", "Carol Zhang"],
            )
        ]

    monkeypatch.setattr(verifier, "_search_openalex_by_title", _fake_search)

    result = verifier.verify_via_openalex(
        "Graph Neural Network for Shenzhen Innovation",
        ("Alice Smith", "Bob Li"),
        openalex_client=client,
    )

    assert result is not None
    assert result.status == "confirmed"
    assert result.source == "openalex"
    assert result.resolved.doi == "10.1234/example"
    assert result.title_score >= 85.0
    assert result.author_jaccard >= 0.3
    assert seen_client == [client]


def test_arxiv_hit_confirms(monkeypatch: Any) -> None:
    client = object()
    seen_client = []

    def _fake_search(title: str, *, http_client=None) -> list[ET.Element]:
        seen_client.append(http_client)
        return [_arxiv_entry()]

    monkeypatch.setattr(verifier, "_search_arxiv_by_title", _fake_search)

    result = verifier.verify_via_arxiv(
        "Graph Neural Network for Shenzhen Innovation",
        ("Alice Smith", "Bob Li"),
        arxiv_client=client,
    )

    assert result is not None
    assert result.status == "confirmed"
    assert result.source == "arxiv"
    assert result.resolved.arxiv_id == "2401.00001"
    assert seen_client == [client]


def test_all_sources_fail_returns_none(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        verifier,
        "_search_openalex_by_title",
        lambda title, *, http_client=None: [
            _openalex_work(authors=["Unrelated Author"])
        ],
    )
    monkeypatch.setattr(
        verifier,
        "_search_arxiv_by_title",
        lambda title, *, http_client=None: [],
    )

    result = verifier.verify_paper_row(
        {
            "paper_id": "P1",
            "title_clean": "Graph Neural Networks for Shenzhen Innovation",
            "authors_display": "Alice Smith, Bob Li",
        },
        cached_resolution=None,
        openalex_client=object(),
        arxiv_client=object(),
    )

    assert result is None


def test_title_clean_abnormal_characters_do_not_break_fuzzy_match(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        verifier,
        "_search_openalex_by_title",
        lambda title, *, http_client=None: [
            _openalex_work(
                title="Deep Learning for Images",
                authors=["Alice Smith", "Carol Zhang"],
            )
        ],
    )

    result = verifier.verify_via_openalex(
        "Deep\u200b <i>Learning</i>: for Images!!!",
        ("Alice Smith", "Bob Li"),
        openalex_client=object(),
    )

    assert result is not None
    assert result.status == "confirmed"
    assert result.title_score >= 85.0
