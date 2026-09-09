from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.data_agents.professor.academic_tools import (
    AcademicAuthorInfo,
    PaperCollectionResult,
    RawPaperRecord,
    collect_papers,
    disambiguate_author,
    merge_papers,
    scrape_arxiv,
    scrape_dblp,
    scrape_semantic_scholar,
)


def _mock_json_response(payload: dict) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def _mock_text_response(payload: str) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.text = payload
    return response


def _paper(
    *,
    title: str,
    authors: list[str] | None = None,
    year: int | None = 2024,
    venue: str | None = None,
    abstract: str | None = None,
    doi: str | None = None,
    citation_count: int | None = None,
    keywords: list[str] | None = None,
    source_url: str = "https://example.com/paper",
    source: str = "test",
) -> RawPaperRecord:
    return RawPaperRecord(
        title=title,
        authors=authors or [],
        year=year,
        venue=venue,
        abstract=abstract,
        doi=doi,
        citation_count=citation_count,
        keywords=keywords or [],
        source_url=source_url,
        source=source,
    )


def test_scrape_semantic_scholar_extracts_papers_and_hindex():
    payload = {
        "data": [
            {
                "name": "Ada Lovelace",
                "hIndex": 42,
                "citationCount": 1234,
                "paperCount": 56,
                "affiliations": ["Analytical Engine Institute"],
                "papers": [
                    {
                        "title": "Computing Machinery and Symbols",
                        "year": 2023,
                        "venue": "Journal of Symbolic Systems",
                        "citationCount": 88,
                        "externalIds": {"DOI": "10.1000/ada.1"},
                        "abstract": "A paper about symbolic computation.",
                    },
                    {
                        "title": "Notes on the Analytical Engine",
                        "year": 2021,
                        "venue": "Engine Proceedings",
                        "citationCount": 55,
                        "externalIds": {},
                        "abstract": "Observations on general-purpose machines.",
                    },
                ],
            }
        ]
    }

    with patch(
        "src.data_agents.professor.academic_tools.requests.get",
        return_value=_mock_json_response(payload),
    ) as mock_get:
        papers, author_info = scrape_semantic_scholar(
            "Ada Lovelace",
            "Analytical Engine",
            fetch_html=lambda *_: "",
            timeout=12,
        )

    assert len(papers) == 2
    assert papers[0].title == "Computing Machinery and Symbols"
    assert papers[0].authors == ["Ada Lovelace"]
    assert papers[0].venue == "Journal of Symbolic Systems"
    assert papers[0].doi == "10.1000/ada.1"
    assert papers[0].citation_count == 88
    assert papers[1].abstract == "Observations on general-purpose machines."
    assert author_info == AcademicAuthorInfo(
        h_index=42,
        citation_count=1234,
        paper_count=56,
        source="semantic_scholar",
    )
    mock_get.assert_called_once()


def test_scrape_dblp_extracts_papers():
    payload = {
        "result": {
            "hits": {
                "hit": [
                    {
                        "info": {
                            "title": "Distributed Notes for Engines",
                            "year": "2020",
                            "venue": "DB Systems",
                            "doi": "10.1000/dblp.1",
                            "authors": {
                                "author": [
                                    {"text": "Ada Lovelace"},
                                    {"text": "Charles Babbage"},
                                ]
                            },
                            "url": "https://dblp.org/rec/conf/example/ada2020",
                        }
                    },
                    {
                        "info": {
                            "title": "A Compiler for Numbers",
                            "year": "2019",
                            "venue": "Programming Languages Today",
                            "doi": "10.1000/dblp.2",
                            "authors": {"author": [{"text": "Ada Lovelace"}]},
                            "url": "https://dblp.org/rec/journals/example/ada2019",
                        }
                    },
                ]
            }
        }
    }

    with patch(
        "src.data_agents.professor.academic_tools.requests.get",
        return_value=_mock_json_response(payload),
    ):
        papers = scrape_dblp("Ada Lovelace", fetch_html=lambda *_: "", timeout=8)

    assert [paper.title for paper in papers] == [
        "Distributed Notes for Engines",
        "A Compiler for Numbers",
    ]
    assert papers[0].authors == ["Ada Lovelace", "Charles Babbage"]
    assert papers[0].year == 2020
    assert papers[0].venue == "DB Systems"
    assert papers[0].source == "dblp"
    assert papers[1].doi == "10.1000/dblp.2"


def test_scrape_arxiv_extracts_papers():
    xml_payload = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <published>2024-01-20T00:00:00Z</published>
    <title>Neural Engines for Symbolic Analysis</title>
    <summary>We study symbolic analysis with neural engines.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Charles Babbage</name></author>
    <category term="cs.AI" />
    <category term="cs.LG" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2305.67890v2</id>
    <published>2023-05-02T00:00:00Z</published>
    <title>On Machine Imagination</title>
    <summary>Generative programs for scientific reasoning.</summary>
    <author><name>Ada Lovelace</name></author>
    <category term="cs.CL" />
  </entry>
</feed>
"""

    with patch(
        "src.data_agents.professor.academic_tools.requests.get",
        return_value=_mock_text_response(xml_payload),
    ):
        papers = scrape_arxiv("Ada Lovelace", fetch_html=lambda *_: "", timeout=10)

    assert len(papers) == 2
    assert papers[0].title == "Neural Engines for Symbolic Analysis"
    assert papers[0].authors == ["Ada Lovelace", "Charles Babbage"]
    assert papers[0].year == 2024
    assert papers[0].abstract == "We study symbolic analysis with neural engines."
    assert papers[0].keywords == ["cs.AI", "cs.LG"]
    assert papers[0].source_url == "http://arxiv.org/abs/2401.12345v1"
    assert papers[1].keywords == ["cs.CL"]


def test_merge_papers_dedup_by_doi():
    richer = _paper(
        title="Shared DOI Paper",
        authors=["Ada Lovelace"],
        year=2024,
        venue="Journal of Engines",
        abstract="Rich metadata.",
        doi="10.1000/shared",
        citation_count=15,
        keywords=["engines"],
        source_url="https://example.com/rich",
        source="semantic_scholar",
    )
    thinner = _paper(
        title="Shared DOI Paper",
        authors=["Ada Lovelace"],
        year=2024,
        doi="10.1000/shared",
        source_url="https://example.com/thin",
        source="dblp",
    )

    merged = merge_papers([thinner], [richer])

    assert merged == [richer]


def test_merge_papers_dedup_by_title_year():
    richer = _paper(
        title="A Theory, Of Engines!",
        authors=["Ada Lovelace"],
        year=2022,
        venue="Symbolic Systems",
        abstract="Longer abstract",
        source_url="https://example.com/one",
        source="arxiv",
    )
    thinner = _paper(
        title="A Theory of Engines",
        authors=["Ada Lovelace"],
        year=2022,
        source_url="https://example.com/two",
        source="dblp",
    )

    merged = merge_papers([richer, thinner])

    assert merged == [richer]


def test_disambiguate_high_confidence():
    candidates = [
        _paper(
            title="Machine Learning for Engines",
            authors=["Ada Lovelace"],
            year=2024,
            venue="Oxford Computational Institute",
            keywords=["machine learning", "symbolic reasoning"],
            source_url="https://oxford.example.edu/paper-1",
            source="semantic_scholar",
        )
    ]

    filtered, confidence = disambiguate_author(
        candidates,
        target_name="Ada Lovelace",
        target_institution="Oxford",
        existing_directions=["machine learning", "program synthesis"],
    )

    assert filtered == candidates
    assert confidence > 0.5


def test_disambiguate_low_confidence():
    candidates = [
        _paper(
            title="Marine Biology Field Notes",
            authors=["Random Researcher"],
            year=2020,
            venue="Coastal Ecology Review",
            keywords=["fish", "estuaries"],
            source_url="https://coastal.example.org/paper",
            source="dblp",
        )
    ]

    filtered, confidence = disambiguate_author(
        candidates,
        target_name="Ada Lovelace",
        target_institution="Oxford",
        existing_directions=["machine learning", "program synthesis"],
    )

    assert filtered == []
    assert confidence < 0.5


def test_collect_papers_partial_failure():
    semantic_payload = {
        "data": [
            {
                "name": "Ada Lovelace",
                "hIndex": 12,
                "citationCount": 200,
                "paperCount": 8,
                "affiliations": ["Oxford University"],
                "papers": [
                    {
                        "title": "Machine Learning for Engines",
                        "year": 2024,
                        "venue": "Oxford Computational Institute",
                        "citationCount": 10,
                        "externalIds": {"DOI": "10.1000/oxford.1"},
                        "abstract": "Machine learning systems for engines.",
                    }
                ],
            }
        ]
    }
    arxiv_payload = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2402.11111v1</id>
    <published>2024-02-10T00:00:00Z</published>
    <title>Program Synthesis for Engines</title>
    <summary>Program synthesis methods for reliable engines.</summary>
    <author><name>Ada Lovelace</name></author>
    <category term="program synthesis" />
  </entry>
</feed>
"""

    def _requests_side_effect(url: str, *args, **kwargs) -> Mock:
        del args, kwargs
        if "semanticscholar" in url:
            return _mock_json_response(semantic_payload)
        if "dblp.org" in url:
            raise requests.RequestException("temporary DBLP failure")
        if "arxiv.org" in url:
            return _mock_text_response(arxiv_payload)
        raise AssertionError(f"unexpected url {url}")

    import requests

    with patch(
        "src.data_agents.professor.academic_tools.requests.get",
        side_effect=_requests_side_effect,
    ), patch("src.data_agents.professor.academic_tools.time.sleep") as mock_sleep:
        result = collect_papers(
            name="艾达",
            name_en="Ada Lovelace",
            institution="牛津大学",
            institution_en="Oxford University",
            existing_directions=["machine learning", "program synthesis"],
            fetch_html=lambda *_: "",
            timeout=9,
            crawl_delay=0.01,
        )

    assert isinstance(result, PaperCollectionResult)
    assert len(result.papers) == 2
    assert result.author_info == AcademicAuthorInfo(
        h_index=12,
        citation_count=200,
        paper_count=8,
        source="semantic_scholar",
    )
    assert result.disambiguation_confidence > 0.5
    assert result.sources_attempted == ["semantic_scholar", "dblp", "arxiv"]
    assert result.sources_succeeded == ["semantic_scholar", "arxiv"]
    assert mock_sleep.call_count == 2


def test_collect_papers_all_empty():
    empty_semantic_payload = {"data": []}
    empty_dblp_payload = {"result": {"hits": {"hit": []}}}
    empty_arxiv_payload = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>
"""

    responses = [
        _mock_json_response(empty_semantic_payload),
        _mock_json_response(empty_dblp_payload),
        _mock_text_response(empty_arxiv_payload),
    ]

    with patch(
        "src.data_agents.professor.academic_tools.requests.get",
        side_effect=responses,
    ), patch("src.data_agents.professor.academic_tools.time.sleep"):
        result = collect_papers(
            name="Ada Lovelace",
            name_en="Ada Lovelace",
            institution="Oxford",
            institution_en="Oxford",
            existing_directions=[],
            fetch_html=lambda *_: "",
            timeout=5,
            crawl_delay=0.01,
        )

    assert result == PaperCollectionResult(
        papers=[],
        author_info=None,
        disambiguation_confidence=0.0,
        sources_attempted=["semantic_scholar", "dblp", "arxiv"],
        sources_succeeded=["semantic_scholar", "dblp", "arxiv"],
    )
