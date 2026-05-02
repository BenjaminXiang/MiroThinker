from __future__ import annotations

from unittest.mock import MagicMock

from src.data_agents.paper.canonical_writer import upsert_paper


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _upsert_with_source(
    source: str | None,
    *,
    canonical_source: str = "manual",
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
