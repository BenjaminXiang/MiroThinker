from __future__ import annotations

import inspect
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.data_agents.company import canonical_import as company_import
from src.data_agents.paper.canonical_writer import upsert_paper
from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.professor import canonical_writer as professor_writer
from src.data_agents.storage.postgres.paper_full_text import upsert_paper_full_text

SENTINEL_RUN_ID = UUID("00000000-0000-0000-0000-000000000000")


WRITER_FUNCTIONS = (
    upsert_paper,
    upsert_paper_full_text,
    professor_writer.write_professor_bundle,
    professor_writer.upsert_professor_metrics,
    professor_writer.upsert_source_page_for_url,
    professor_writer._upsert_professor_paper_link,
    company_import._upsert_company,
)


@pytest.mark.parametrize("writer_fn", WRITER_FUNCTIONS)
def test_writer_requires_run_id_signature(writer_fn):
    parameter = inspect.signature(writer_fn).parameters["run_id"]
    assert parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize(
    ("writer_fn", "sample_args"),
    [
        (
            upsert_paper,
            {
                "title_clean": "Run ID Wiring Paper",
                "title_raw": "Run ID Wiring Paper",
                "doi": None,
                "arxiv_id": None,
                "openalex_id": None,
                "semantic_scholar_id": None,
                "year": 2026,
                "venue": None,
                "abstract_clean": None,
                "authors_display": None,
                "citation_count": None,
                "canonical_source": "manual",
            },
        ),
        (
            upsert_paper_full_text,
            {
                "paper_id": "PAPER-run-id",
                "extract": FullTextExtract(
                    paper_id="PAPER-run-id",
                    abstract=None,
                    intro=None,
                    pdf_url=None,
                    pdf_sha256=None,
                    source="failed",
                    fetch_error="not_fetched",
                ),
            },
        ),
        (professor_writer.write_professor_bundle, {"enriched": object()}),
        (
            professor_writer.upsert_professor_metrics,
            {
                "professor_id": "PROF-run-id",
                "h_index": 1,
                "citation_count": 2,
                "metrics_source": "openalex",
            },
        ),
        (
            professor_writer.upsert_source_page_for_url,
            {
                "url": "https://example.edu/profile",
                "page_role": "official_profile",
            },
        ),
        (
            professor_writer._upsert_professor_paper_link,
            {
                "professor_id": "PROF-run-id",
                "paper_id": "PAPER-run-id",
                "link_status": "verified",
                "evidence_source_type": "personal_homepage",
                "evidence_page_id": None,
                "evidence_api_source": None,
                "match_reason": "run_id_wiring_test",
                "author_name_match_score": Decimal("1.0"),
                "topic_consistency_score": None,
                "institution_consistency_score": None,
                "is_officially_listed": True,
            },
        ),
        (
            company_import._upsert_company,
            {
                "batch_id": UUID("00000000-0000-0000-0000-000000000001"),
                "values": {"company_name_xlsx": "深圳测试科技有限公司"},
            },
        ),
    ],
)
def test_writer_rejects_dry_run_sentinel_run_id(writer_fn, sample_args):
    conn = MagicMock()
    with pytest.raises(ValueError, match="sentinel"):
        writer_fn(conn, run_id=SENTINEL_RUN_ID, **sample_args)
    conn.execute.assert_not_called()
