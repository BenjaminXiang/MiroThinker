from __future__ import annotations

from src.data_agents.paper.arxiv import enrich_paper_metadata_from_arxiv
from src.data_agents.paper.models import PaperAuthorMetadata


def test_enrich_paper_metadata_from_arxiv_by_id() -> None:
    def fake_request_text(url: str, params: dict[str, object]) -> str:
        assert url == "https://export.arxiv.org/api/query"
        assert params == {"id_list": "2401.00001"}
        return """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <id>http://arxiv.org/abs/2401.00001v2</id>
            <published>2024-01-01T00:00:00Z</published>
            <title>Example arXiv Paper</title>
            <summary>
              This is the arXiv abstract.
            </summary>
            <author><name>Ada Lovelace</name></author>
            <author><name>Charles Babbage</name></author>
            <arxiv:primary_category term="cs.AI" />
            <category term="cs.AI" />
            <category term="cs.LG" />
          </entry>
        </feed>
        """

    enrichment = enrich_paper_metadata_from_arxiv(
        "2401.00001",
        request_text=fake_request_text,
    )

    assert enrichment is not None
    assert enrichment.abstract == "This is the arXiv abstract."
    assert enrichment.venue == "arXiv"
    assert enrichment.publication_date == "2024-01-01"
    assert enrichment.fields_of_study == ("cs.AI", "cs.LG")
    assert enrichment.source_url == "http://arxiv.org/abs/2401.00001v2"
    assert enrichment.authors == (
        PaperAuthorMetadata(display_name="Ada Lovelace", source="arxiv"),
        PaperAuthorMetadata(display_name="Charles Babbage", source="arxiv"),
    )
    assert enrichment.enrichment_sources == ("arxiv",)


def test_enrich_paper_metadata_from_arxiv_returns_none_for_blank_id() -> None:
    assert enrich_paper_metadata_from_arxiv("") is None
