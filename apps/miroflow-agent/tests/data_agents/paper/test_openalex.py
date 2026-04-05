from __future__ import annotations

import pytest
import requests

import src.data_agents.paper.openalex as openalex
from src.data_agents.paper.openalex import (
    discover_professor_paper_candidates_from_openalex,
)


def test_discover_professor_paper_candidates_from_openalex_selects_exact_name_author_and_parses_works():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            assert params["search"] == "白志强"
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A1",
                        "display_name": "白志强 BAI Zhiqiang",
                        "works_count": 99,
                        "cited_by_count": 900,
                        "summary_stats": {"h_index": 25},
                    },
                    {
                        "id": "https://openalex.org/A2",
                        "display_name": "白志强",
                        "works_count": 21,
                        "cited_by_count": 18,
                        "summary_stats": {"h_index": 4},
                    },
                ]
            }
        assert url.endswith("/works")
        assert params["filter"] == "authorships.author.id:https://openalex.org/A2"
        return {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "display_name": "CT 三维重建解剖学研究",
                    "publication_year": 2014,
                    "publication_date": "2014-01-01",
                    "cited_by_count": 8,
                    "doi": "https://doi.org/10.1234/example",
                    "abstract_inverted_index": {
                        "CT": [0],
                        "三维重建": [1],
                        "解剖学": [2],
                    },
                    "primary_location": {
                        "landing_page_url": "https://example.org/paper/w1",
                        "source": {"display_name": "解剖学报"},
                    },
                    "authorships": [
                        {"author": {"display_name": "白志强"}},
                        {"author": {"display_name": "陶宝虹"}},
                    ],
                }
            ]
        }

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-1",
        professor_name="白志强",
        institution="北京大学深圳研究生院",
        request_json=fake_request_json,
        max_papers=5,
    )

    assert result.author_id == "https://openalex.org/A2"
    assert result.h_index == 4
    assert result.citation_count == 18
    assert len(result.papers) == 1
    paper = result.papers[0]
    assert paper.paper_id == "https://openalex.org/W1"
    assert paper.title == "CT 三维重建解剖学研究"
    assert paper.venue == "解剖学报"
    assert paper.doi == "10.1234/example"
    assert paper.abstract == "CT 三维重建 解剖学"
    assert paper.authors == ("白志强", "陶宝虹")
    assert paper.professor_ids == ("PROF-1",)


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

    monkeypatch.setattr(openalex, "_CACHE_ROOT", tmp_path / "paper_openalex_cache")
    monkeypatch.setattr(openalex.requests, "get", fake_get)
    monkeypatch.setattr(openalex.time, "sleep", sleeps.append)

    with pytest.raises(requests.HTTPError, match="429 Too Many Requests"):
        openalex._request_json("https://api.openalex.org/authors", {"search": "高会军"})

    assert len(calls) == 2
    assert sleeps == [1.0]
