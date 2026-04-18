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


def test_discover_professor_paper_candidates_from_openalex_prefers_institution_matched_author():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A1",
                        "display_name": "Zhi Li",
                        "display_name_alternatives": ["李志"],
                        "works_count": 200,
                        "cited_by_count": 4000,
                        "summary_stats": {"h_index": 30},
                        "last_known_institutions": [
                            {"display_name": "Other University"}
                        ],
                    },
                    {
                        "id": "https://openalex.org/A2",
                        "display_name": "Zhi Li",
                        "display_name_alternatives": ["李志"],
                        "works_count": 30,
                        "cited_by_count": 500,
                        "summary_stats": {"h_index": 10},
                        "last_known_institutions": [
                            {
                                "display_name": "Southern University of Science and Technology"
                            }
                        ],
                    },
                ]
            }
        assert params["filter"] == "authorships.author.id:https://openalex.org/A2"
        return {
            "results": [
                {
                    "id": "https://openalex.org/W2",
                    "display_name": "多模态学习研究",
                    "publication_year": 2024,
                    "publication_date": "2024-01-01",
                    "cited_by_count": 16,
                    "primary_location": {
                        "landing_page_url": "https://example.org/paper/w2",
                        "source": {"display_name": "AAAI"},
                    },
                    "authorships": [
                        {"author": {"display_name": "李志"}},
                    ],
                }
            ]
        }

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-2",
        professor_name="李志",
        institution="南方科技大学",
        request_json=fake_request_json,
        max_papers=5,
    )

    assert result.author_id == "https://openalex.org/A2"
    assert result.h_index == 10
    assert result.citation_count == 500
    assert result.paper_count == 30
    assert result.papers[0].title == "多模态学习研究"


def test_discover_professor_paper_candidates_from_openalex_uses_institution_id_filter_when_available():
    seen_author_params: dict[str, object] = {}

    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            seen_author_params.update(params)
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A9",
                        "display_name": "Yabei Wu",
                        "display_name_alternatives": ["吴亚北"],
                        "works_count": 70,
                        "cited_by_count": 708,
                        "summary_stats": {"h_index": 15},
                        "last_known_institutions": [
                            {
                                "id": "https://openalex.org/I3045169105",
                                "display_name": "Southern University of Science and Technology",
                            }
                        ],
                    }
                ]
            }
        assert params["filter"] == "authorships.author.id:https://openalex.org/A9"
        return {
            "results": [
                {
                    "id": "https://openalex.org/W9",
                    "display_name": "Twisted bilayer graphene",
                    "publication_year": 2024,
                    "publication_date": "2024-01-01",
                    "cited_by_count": 88,
                    "primary_location": {
                        "landing_page_url": "https://example.org/paper/w9",
                        "source": {"display_name": "Nature"},
                    },
                    "authorships": [
                        {"author": {"display_name": "Yabei Wu"}},
                    ],
                }
            ]
        }

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-9",
        professor_name="Yabei Wu",
        institution="南方科技大学",
        institution_id="I3045169105",
        request_json=fake_request_json,
        max_papers=5,
    )

    assert seen_author_params["search"] == "Yabei Wu"
    assert seen_author_params["filter"] == "last_known_institutions.id:I3045169105"
    assert result.author_id == "https://openalex.org/A9"
    assert result.paper_count == 70


def test_discover_professor_paper_candidates_from_openalex_falls_back_when_filtered_search_misses():
    author_calls: list[dict[str, object]] = []

    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            author_calls.append(dict(params))
            if "filter" in params:
                return {"results": []}
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A7",
                        "display_name": "Xian-En Zhang",
                        "display_name_alternatives": ["张先恩"],
                        "works_count": 7,
                        "cited_by_count": 120,
                        "summary_stats": {"h_index": 6},
                    }
                ]
            }
        assert params["filter"] == "authorships.author.id:https://openalex.org/A7"
        return {
            "results": [
                {
                    "id": "https://openalex.org/W7",
                    "display_name": "Synthetic biology and sensors",
                    "publication_year": 2024,
                    "publication_date": "2024-01-01",
                    "cited_by_count": 30,
                    "primary_location": {
                        "landing_page_url": "https://example.org/paper/w7",
                        "source": {"display_name": "Nature Biotechnology"},
                    },
                    "authorships": [
                        {"author": {"display_name": "Xian-En Zhang"}},
                    ],
                }
            ]
        }

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-7",
        professor_name="Xian-En Zhang",
        institution="深圳理工大学",
        institution_id="I4405255904",
        request_json=fake_request_json,
        max_papers=5,
    )

    assert [call.get("filter") for call in author_calls] == [
        "last_known_institutions.id:I4405255904",
        None,
    ]
    assert result.author_id == "https://openalex.org/A7"
    assert result.paper_count == 7
    assert result.papers[0].title == "Synthetic biology and sensors"


def test_discover_professor_paper_candidates_from_openalex_does_not_mark_parent_university_as_branch_school_match():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            if "filter" in params:
                return {"results": []}
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A11",
                        "display_name": "Wenbo Ding",
                        "display_name_alternatives": ["丁文伯"],
                        "works_count": 112,
                        "cited_by_count": 7910,
                        "summary_stats": {"h_index": 36},
                        "last_known_institutions": [
                            {
                                "id": "https://openalex.org/I75558411",
                                "display_name": "Tsinghua University",
                            }
                        ],
                    }
                ]
            }
        assert params["filter"] == "authorships.author.id:https://openalex.org/A11"
        return {
            "results": [
                {
                    "id": "https://openalex.org/W11",
                    "display_name": "A paper by another Wenbo Ding",
                    "publication_year": 2024,
                    "publication_date": "2024-01-01",
                    "cited_by_count": 30,
                    "primary_location": {
                        "landing_page_url": "https://example.org/paper/w11",
                        "source": {"display_name": "Nature"},
                    },
                    "authorships": [
                        {"author": {"display_name": "Wenbo Ding"}},
                    ],
                }
            ]
        }

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-11",
        professor_name="Wenbo Ding",
        institution="清华大学深圳国际研究生院",
        institution_id="I4210111368",
        request_json=fake_request_json,
        max_papers=5,
    )

    assert result.author_id == "https://openalex.org/A11"
    assert result.school_matched is False


def test_discover_professor_paper_candidates_from_openalex_matches_reordered_ascii_folded_names():
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        if url.endswith("/authors"):
            return {
                "results": [
                    {
                        "id": "https://openalex.org/A8",
                        "display_name": "Miha Brešar",
                        "display_name_alternatives": ["Brešar, Miha"],
                        "works_count": 9,
                        "cited_by_count": 180,
                        "summary_stats": {"h_index": 8},
                    }
                ]
            }
        assert params["filter"] == "authorships.author.id:https://openalex.org/A8"
        return {
            "results": [
                {
                    "id": "https://openalex.org/W8",
                    "display_name": "Graph theory advances",
                    "publication_year": 2023,
                    "publication_date": "2023-01-01",
                    "cited_by_count": 18,
                    "primary_location": {
                        "landing_page_url": "https://example.org/paper/w8",
                        "source": {"display_name": "Discrete Mathematics"},
                    },
                    "authorships": [
                        {"author": {"display_name": "Miha Brešar"}},
                    ],
                }
            ]
        }

    result = discover_professor_paper_candidates_from_openalex(
        professor_id="PROF-8",
        professor_name="BRESAR, Miha",
        institution="香港中文大学（深圳）",
        request_json=fake_request_json,
        max_papers=5,
    )

    assert result.author_id == "https://openalex.org/A8"
    assert result.paper_count == 9
    assert result.papers[0].title == "Graph theory advances"


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
