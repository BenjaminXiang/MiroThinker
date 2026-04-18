from __future__ import annotations

import pytest
import requests

import src.data_agents.paper.semantic_scholar as semantic_scholar
from src.data_agents.paper.semantic_scholar import (
    discover_professor_paper_candidates,
    enrich_paper_metadata_from_semantic_scholar,
)


def test_discover_professor_paper_candidates_selects_exact_name_author_and_parses_papers():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/author/search"):
            assert params["query"] == "靳玉乐"
            return {
                "data": [
                    {
                        "authorId": "bad",
                        "name": "靳玉乐 张良",
                        "paperCount": 99,
                        "citationCount": 999,
                        "hIndex": 12,
                    },
                    {
                        "authorId": "136691277",
                        "name": "靳玉乐",
                        "paperCount": 18,
                        "citationCount": 7,
                        "hIndex": 3,
                    },
                ]
            }
        assert url.endswith("/author/136691277/papers")
        return {
            "data": [
                {
                    "paperId": "618beb097e1266e339db5ae81a75a8908dbe8a6b",
                    "title": "要认真对待高校课程思政的“泛意识形态化”倾向",
                    "venue": "江苏高教",
                    "year": 2021,
                    "publicationDate": "2021-04-15",
                    "citationCount": 2,
                    "url": (
                        "https://www.semanticscholar.org/paper/"
                        "618beb097e1266e339db5ae81a75a8908dbe8a6b"
                    ),
                    "externalIds": {
                        "DOI": "10.16697/J.1674-5485.2021.04.005",
                        "ArXiv": "2401.01234",
                    },
                    "abstract": "讨论高校课程思政泛意识形态化倾向的表现与治理路径。",
                    "authors": [
                        {"authorId": "136691277", "name": "靳玉乐"},
                        {"authorId": "2054877067", "name": "张良"},
                    ],
                }
            ]
        }

    result = discover_professor_paper_candidates(
        professor_id="PROF-1",
        professor_name="靳玉乐",
        institution="深圳大学",
        request_json=fake_request_json,
        max_papers=5,
    )

    assert result.author_id == "136691277"
    assert result.h_index == 3
    assert result.citation_count == 7
    assert len(result.papers) == 1
    paper = result.papers[0]
    assert paper.paper_id == "618beb097e1266e339db5ae81a75a8908dbe8a6b"
    assert paper.professor_ids == ("PROF-1",)
    assert paper.title == "要认真对待高校课程思政的“泛意识形态化”倾向"
    assert paper.venue == "江苏高教"
    assert paper.doi == "10.16697/J.1674-5485.2021.04.005"
    assert paper.arxiv_id == "2401.01234"
    assert paper.citation_count == 2
    assert paper.authors == ("靳玉乐", "张良")


def test_enrich_paper_metadata_from_semantic_scholar_by_doi():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        assert url == "https://api.semanticscholar.org/graph/v1/paper/DOI:10.16697/J.1674-5485.2021.04.005"
        assert "tldr" in str(params["fields"])
        return {
            "paperId": "618beb097e1266e339db5ae81a75a8908dbe8a6b",
            "title": "要认真对待高校课程思政的“泛意识形态化”倾向",
            "venue": "江苏高教",
            "year": 2021,
            "publicationDate": "2021-04-15",
            "citationCount": 8,
            "referenceCount": 25,
            "url": "https://www.semanticscholar.org/paper/618beb097e1266e339db5ae81a75a8908dbe8a6b",
            "abstract": "Semantic Scholar abstract.",
            "fieldsOfStudy": ["Education", "Political Science"],
            "tldr": {"text": "课程思政治理路径综述。"},
            "isOpenAccess": True,
            "openAccessPdf": {"url": "https://example.org/open.pdf"},
        }

    enrichment = enrich_paper_metadata_from_semantic_scholar(
        "10.16697/J.1674-5485.2021.04.005",
        request_json=fake_request_json,
    )

    assert enrichment is not None
    assert enrichment.abstract == "Semantic Scholar abstract."
    assert enrichment.venue == "江苏高教"
    assert enrichment.publication_date == "2021-04-15"
    assert enrichment.citation_count == 8
    assert enrichment.reference_count == 25
    assert enrichment.fields_of_study == ("Education", "Political Science")
    assert enrichment.tldr == "课程思政治理路径综述。"
    assert enrichment.oa_status == "open"
    assert enrichment.source_url == "https://www.semanticscholar.org/paper/618beb097e1266e339db5ae81a75a8908dbe8a6b"
    assert enrichment.enrichment_sources == ("semantic_scholar",)


def test_request_json_retries_429_with_short_bounded_backoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    sleeps: list[float] = []

    class FakeResponse:
        status_code = 429

        def raise_for_status(self) -> None:
            raise requests.HTTPError("429 Too Many Requests")

    def fake_get(url: str, params: dict[str, object], timeout: object) -> FakeResponse:
        calls.append((url, params))
        assert timeout == (5, 20)
        return FakeResponse()

    monkeypatch.setattr(
        semantic_scholar,
        "_CACHE_ROOT",
        tmp_path / "paper_semantic_scholar_cache",
    )
    monkeypatch.setattr(semantic_scholar.requests, "get", fake_get)
    monkeypatch.setattr(semantic_scholar.time, "sleep", sleeps.append)

    with pytest.raises(requests.HTTPError, match="429 Too Many Requests"):
        semantic_scholar._request_json(
            "https://api.semanticscholar.org/graph/v1/author/search",
            {"query": "靳玉乐"},
        )

    assert len(calls) == 2
    assert sleeps == [1.0]
