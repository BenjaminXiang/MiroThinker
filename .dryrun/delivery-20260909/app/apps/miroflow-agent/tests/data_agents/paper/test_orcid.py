# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.paper.orcid import discover_professor_paper_candidates_from_orcid


def test_discover_professor_paper_candidates_from_orcid_extracts_public_works() -> None:
    payload = {
        "group": [
            {
                "work-summary": [
                    {
                        "put-code": 202824943,
                        "title": {
                            "title": {
                                "value": "Hydride ionic conductors: Bridging ionic transport mechanisms and design strategies for sustainable energy systems"
                            }
                        },
                        "external-ids": {
                            "external-id": [
                                {
                                    "external-id-type": "doi",
                                    "external-id-value": "10.1016/J.SUSMAT.2025.E01820",
                                    "external-id-normalized": {
                                        "value": "10.1016/j.susmat.2025.e01820"
                                    },
                                }
                            ]
                        },
                        "url": {"value": "https://publons.example.com/work/1"},
                        "publication-date": {"year": {"value": "2026"}},
                        "journal-title": {"value": "Sustainable Materials and Technologies"},
                    }
                ]
            }
        ]
    }

    result = discover_professor_paper_candidates_from_orcid(
        professor_id="PROF-001",
        professor_name="李海文",
        institution="中山大学（深圳）",
        orcid_url="https://orcid.org/0000-0001-7223-1754",
        request_json=lambda _url: payload,
        max_papers=5,
    )

    assert result.author_id == "https://orcid.org/0000-0001-7223-1754"
    assert result.source == "official_linked_orcid"
    assert result.paper_count == 1
    assert result.school_matched is True
    assert len(result.papers) == 1
    assert result.papers[0].title.startswith("Hydride ionic conductors")
    assert result.papers[0].year == 2026
    assert result.papers[0].venue == "Sustainable Materials and Technologies"
    assert result.papers[0].doi == "10.1016/j.susmat.2025.e01820"
    assert result.papers[0].authors == ("李海文",)
    assert result.papers[0].source_url == "https://doi.org/10.1016/j.susmat.2025.e01820"


def test_discover_professor_paper_candidates_from_orcid_rejects_invalid_orcid_url() -> None:
    result = discover_professor_paper_candidates_from_orcid(
        professor_id="PROF-001",
        professor_name="李海文",
        institution="中山大学（深圳）",
        orcid_url="https://example.com/not-orcid",
        request_json=lambda _url: (_ for _ in ()).throw(AssertionError("should not fetch")),
        max_papers=5,
    )

    assert result.author_id is None
    assert result.papers == []
    assert result.paper_count is None
    assert result.source == "official_linked_orcid"
