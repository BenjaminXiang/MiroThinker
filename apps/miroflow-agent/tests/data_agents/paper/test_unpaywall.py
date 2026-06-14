from __future__ import annotations

import src.data_agents.paper.unpaywall as unpaywall


def test_enrich_paper_metadata_from_unpaywall_extracts_best_pdf_url():
    def fake_request_json(url: str) -> dict[str, object]:
        assert (
            url
            == "https://api.unpaywall.org/v2/10.1234%2Fexample?email=data%40example.org"
        )
        return {
            "doi": "10.1234/example",
            "oa_status": "green",
            "best_oa_location": {
                "url_for_pdf": "https://repository.example.org/paper.pdf",
                "url_for_landing_page": "https://repository.example.org/paper",
            },
        }

    result = unpaywall.enrich_paper_metadata_from_unpaywall(
        "10.1234/example",
        email="data@example.org",
        request_json=fake_request_json,
    )

    assert result is not None
    assert result.doi == "10.1234/example"
    assert result.oa_status == "green"
    assert result.pdf_url == "https://repository.example.org/paper.pdf"
    assert result.source_url == "https://repository.example.org/paper"
    assert result.enrichment_sources == ("unpaywall",)


def test_enrich_paper_metadata_from_unpaywall_uses_first_oa_location_fallback():
    def fake_request_json(_url: str) -> dict[str, object]:
        return {
            "doi": "10.1234/example",
            "is_oa": True,
            "oa_locations": [
                {
                    "url": "https://publisher.example.org/landing",
                },
                {
                    "url_for_pdf": "https://repo.example.org/fallback.pdf",
                    "url_for_landing_page": "https://repo.example.org/landing",
                },
            ],
        }

    result = unpaywall.enrich_paper_metadata_from_unpaywall(
        "10.1234/example",
        email="data@example.org",
        request_json=fake_request_json,
    )

    assert result is not None
    assert result.pdf_url == "https://repo.example.org/fallback.pdf"
    assert result.source_url == "https://repo.example.org/landing"


def test_enrich_paper_metadata_from_unpaywall_skips_without_email(monkeypatch):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)

    result = unpaywall.enrich_paper_metadata_from_unpaywall("10.1234/example")

    assert result is None
