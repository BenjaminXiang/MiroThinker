from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.paper.exact_backfill import (
    load_exact_backfill_papers,
    merge_release_outputs_by_id,
)
from src.data_agents.paper.models import DiscoveredPaper
from src.data_agents.paper.release import build_paper_release


TIMESTAMP = datetime(2026, 4, 16, tzinfo=timezone.utc)


def test_load_exact_backfill_papers_reads_jsonl(tmp_path: Path):
    path = tmp_path / "paper_backfill.jsonl"
    path.write_text(
        json.dumps({
            "paper_id": "manual-pfedgpa",
            "title": "pFedGPA: Diffusion-based Generative Parameter Aggregation for Personalized Federated Learning",
            "year": 2025,
            "publication_date": "2025-04-11",
            "venue": "Proceedings of the AAAI Conference on Artificial Intelligence",
            "doi": "10.1609/aaai.v39i17.33980",
            "arxiv_id": None,
            "abstract": "abstract",
            "authors": ["Wenbo Ding", "Yang Li"],
            "professor_ids": [],
            "citation_count": 0,
            "source_url": "https://doi.org/10.1609/aaai.v39i17.33980",
            "fields_of_study": ["Machine Learning"],
            "funders": [],
            "enrichment_sources": ["crossref_manual_backfill"],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    papers = load_exact_backfill_papers([path])

    assert len(papers) == 1
    paper = papers[0]
    assert isinstance(paper, DiscoveredPaper)
    assert paper.title.startswith("pFedGPA")
    assert paper.doi == "10.1609/aaai.v39i17.33980"
    assert paper.authors == ("Wenbo Ding", "Yang Li")
    assert paper.fields_of_study == ("Machine Learning",)
    assert paper.enrichment_sources == ("crossref_manual_backfill",)


def test_merge_release_outputs_by_id_deduplicates_supplement_records():
    primary = build_paper_release(
        papers=[
            DiscoveredPaper(
                paper_id="primary",
                title="pFedGPA: Diffusion-based Generative Parameter Aggregation for Personalized Federated Learning",
                year=2025,
                publication_date="2025-04-11",
                venue="AAAI",
                doi="10.1609/aaai.v39i17.33980",
                arxiv_id=None,
                abstract="primary",
                authors=("Wenbo Ding",),
                professor_ids=(),
                citation_count=0,
                source_url="https://doi.org/10.1609/aaai.v39i17.33980",
            )
        ],
        now=TIMESTAMP,
    )
    supplemental = build_paper_release(
        papers=[
            DiscoveredPaper(
                paper_id="supplement",
                title="pFedGPA: Diffusion-based Generative Parameter Aggregation for Personalized Federated Learning",
                year=2025,
                publication_date="2025-04-11",
                venue="AAAI",
                doi="10.1609/aaai.v39i17.33980",
                arxiv_id=None,
                abstract="supplement",
                authors=("Wenbo Ding", "Yang Li"),
                professor_ids=(),
                citation_count=0,
                source_url="https://doi.org/10.1609/aaai.v39i17.33980",
            )
        ],
        now=TIMESTAMP,
    )

    paper_records, released_objects = merge_release_outputs_by_id(
        primary.paper_records,
        primary.released_objects,
        supplemental.paper_records,
        supplemental.released_objects,
    )

    assert len(paper_records) == 1
    assert len(released_objects) == 1
    assert paper_records[0].doi == "10.1609/aaai.v39i17.33980"
