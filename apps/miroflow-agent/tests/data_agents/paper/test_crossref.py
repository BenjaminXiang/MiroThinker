from __future__ import annotations

from src.data_agents.paper.crossref import (
    discover_professor_paper_candidates_from_crossref,
)


def test_discover_professor_paper_candidates_from_crossref_filters_exact_author_names_and_parses_works() -> None:
    def fake_request_json(url: str, params: dict[str, object]) -> dict[str, object]:
        assert url == "https://api.crossref.org/works"
        assert params["query.author"] == "高会军"
        assert params["rows"] == 5
        return {
            "message": {
                "items": [
                    {
                        "DOI": "10.1360/bad-match",
                        "title": ["误匹配论文"],
                        "issued": {"date-parts": [[2012, 3, 1]]},
                        "container-title": ["Chinese Science Bulletin"],
                        "author": [
                            {"family": "高", "given": "雅"},
                            {"family": "王", "given": "会军"},
                        ],
                        "URL": "https://doi.org/10.1360/bad-match",
                        "is-referenced-by-count": 2,
                    },
                    {
                        "DOI": "10.1109/example",
                        "title": ["Networked Control Systems: A Survey"],
                        "published-online": {"date-parts": [[2017, 8, 1]]},
                        "short-container-title": ["IEEE TAC"],
                        "author": [
                            {"family": "高", "given": "会军"},
                            {"family": "Zhang", "given": "Wei"},
                        ],
                        "abstract": "<jats:p>Survey on networked control systems.</jats:p>",
                        "URL": "https://doi.org/10.1109/example",
                        "is-referenced-by-count": 123,
                    },
                ]
            }
        }

    result = discover_professor_paper_candidates_from_crossref(
        professor_id="PROF-1",
        professor_name="高会军",
        institution="哈尔滨工业大学（深圳）",
        request_json=fake_request_json,
        max_papers=5,
    )

    assert result.author_id == "crossref:PROF-1:高会军"
    assert result.h_index is None
    assert result.citation_count == 123
    assert len(result.papers) == 1
    paper = result.papers[0]
    assert paper.paper_id == "10.1109/example"
    assert paper.title == "Networked Control Systems: A Survey"
    assert paper.year == 2017
    assert paper.publication_date == "2017-08-01"
    assert paper.venue == "IEEE TAC"
    assert paper.doi == "10.1109/example"
    assert paper.abstract == "Survey on networked control systems."
    assert paper.authors == ("高会军", "Wei Zhang")
    assert paper.professor_ids == ("PROF-1",)
    assert paper.citation_count == 123
    assert paper.source_url == "https://doi.org/10.1109/example"
