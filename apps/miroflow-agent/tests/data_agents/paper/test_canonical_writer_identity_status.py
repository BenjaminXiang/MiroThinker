from __future__ import annotations

from unittest.mock import MagicMock

from src.data_agents.paper.canonical_writer import upsert_paper


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _upsert_with_source(
    source: str | None,
    *,
    canonical_source: str = "manual",
    quality_status: str | None = None,
) -> tuple[str, tuple[object, ...]]:
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None

    upsert_paper(
        conn,
        title_clean="Identity Status Paper",
        title_raw="Identity Status Paper",
        doi=None,
        arxiv_id=None,
        openalex_id="W123" if source == "openalex" else None,
        semantic_scholar_id=None,
        year=2026,
        venue=None,
        abstract_clean=None,
        authors_display=None,
        citation_count=None,
        canonical_source=canonical_source,
        run_id=RUN_ID,
        title_resolution_source=source,
        quality_status=quality_status,
    )

    insert_call = conn.execute.call_args_list[1]
    return insert_call.args[0], insert_call.args[1]


def test_upsert_paper_marks_identity_confirmed_for_openalex_resolution():
    sql, params = _upsert_with_source("openalex", canonical_source="openalex")

    assert "identity_status" in sql
    assert params[13] == "confirmed"


def test_upsert_paper_marks_identity_unverified_for_llm_only_resolution():
    _, params = _upsert_with_source("llm_only")

    assert params[13] == "unverified"


def test_upsert_paper_can_initialize_page_only_quality_status():
    sql, params = _upsert_with_source(
        "prof_page_only",
        canonical_source="prof_page_only",
        quality_status="needs_enrichment",
    )

    assert "quality_status" in sql
    assert "updated_at" in sql
    assert params[14] == "needs_enrichment"


def test_upsert_paper_conflict_updates_quality_status_monotonically():
    sql, _params = _upsert_with_source(
        "openalex",
        canonical_source="openalex",
        quality_status="partial",
    )

    update_sql = sql.split("DO UPDATE", maxsplit=1)[1]
    assert "quality_status" in update_sql
    assert "paper.quality_status IN ('rejected', 'ready', 'needs_review')" in update_sql
    assert "EXCLUDED.quality_status = 'partial'" in update_sql
