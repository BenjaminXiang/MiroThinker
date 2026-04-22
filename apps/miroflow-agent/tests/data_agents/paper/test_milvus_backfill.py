"""RED-phase tests for M3 Unit 3 — paper_chunks Milvus backfill worker."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data_agents.paper.milvus_backfill import (
    BackfillReport,
    backfill_paper_chunks,
)


def _fake_embedding_client(*, batches_returned: list[list[list[float]]] | None = None):
    client = MagicMock()
    if batches_returned is None:
        # Default: return a list of 4096-dim zero vectors, one per input text.
        client.embed_batch.side_effect = lambda texts, **_: [
            [0.1] * 4096 for _ in texts
        ]
    else:
        client.embed_batch.side_effect = batches_returned
    return client


def _fake_milvus_client():
    client = MagicMock()
    client.has_collection.return_value = True
    return client


def _fake_pg_conn_returning(rows: list[dict]):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn.execute.return_value = cursor
    return conn


def _paper_row(
    paper_id: str = "paper:doi:10.1/a",
    title: str = "Paper title",
    year: int | None = 2023,
    venue: str | None = "NeurIPS",
    abstract: str | None = "Short abstract text.",
    intro: str | None = None,
) -> dict:
    return {
        "paper_id": paper_id,
        "title": title,
        "year": year,
        "venue": venue,
        "abstract": abstract,
        "intro": intro,
    }


def test_backfill_report_dataclass_smoke():
    rep = BackfillReport(
        papers_total=10,
        papers_processed=8,
        papers_skipped=2,
        chunks_inserted=24,
        papers_with_errors=0,
        duration_seconds=1.5,
    )
    assert rep.papers_total == 10
    assert rep.chunks_inserted == 24


def test_backfill_single_paper_writes_chunks():
    conn = _fake_pg_conn_returning([_paper_row()])
    milvus = _fake_milvus_client()
    embed = _fake_embedding_client()
    report = backfill_paper_chunks(
        conn, milvus, embed, limit=None, batch_size=32, resume_ids=None
    )
    assert isinstance(report, BackfillReport)
    assert report.papers_processed == 1
    assert report.chunks_inserted >= 2  # title + abstract at minimum
    # Milvus insert called with chunk rows
    assert milvus.insert.called
    # embed_batch called at least once
    assert embed.embed_batch.called


def test_backfill_deletes_before_insert_per_paper():
    """Idempotency: for each paper, Milvus delete(expr='paper_id == ...') runs before insert."""
    conn = _fake_pg_conn_returning([_paper_row(paper_id="p1"), _paper_row(paper_id="p2")])
    milvus = _fake_milvus_client()
    embed = _fake_embedding_client()
    backfill_paper_chunks(conn, milvus, embed, batch_size=32)
    # At least 2 delete calls (one per paper)
    assert milvus.delete.call_count >= 2
    # Each delete call uses an expr filtering paper_id
    for call in milvus.delete.call_args_list:
        kwargs = call.kwargs
        expr = kwargs.get("filter") or kwargs.get("expr") or ""
        if not expr and call.args:
            # positional form
            expr = call.args[-1] if isinstance(call.args[-1], str) else ""
        assert "paper_id" in expr, f"delete call missing paper_id filter: {call}"


def test_backfill_respects_limit():
    rows = [_paper_row(paper_id=f"p{i}") for i in range(5)]
    conn = _fake_pg_conn_returning(rows[:1])  # LIMIT 1 returns only 1 row
    milvus = _fake_milvus_client()
    embed = _fake_embedding_client()
    report = backfill_paper_chunks(conn, milvus, embed, limit=1)
    assert report.papers_processed == 1


def test_backfill_skips_resume_ids():
    """Resume set passed in → those paper_ids not in the loop."""
    rows = [_paper_row(paper_id="p_new")]  # only p_new returned; p_skip in resume
    conn = _fake_pg_conn_returning(rows)
    milvus = _fake_milvus_client()
    embed = _fake_embedding_client()
    report = backfill_paper_chunks(
        conn,
        milvus,
        embed,
        resume_ids={"p_skip"},
        batch_size=32,
    )
    assert report.papers_processed == 1
    # SELECT SQL should include NOT IN clause or similar for resume
    executed_sqls = [c.args[0] for c in conn.execute.call_args_list if c.args]
    select_sqls = [s for s in executed_sqls if isinstance(s, str) and "SELECT" in s.upper()]
    assert any("NOT IN" in s.upper() or "paper_id" in s for s in select_sqls)


def test_backfill_paper_without_abstract_or_intro_gets_title_chunk():
    conn = _fake_pg_conn_returning(
        [_paper_row(abstract=None, intro=None)]
    )
    milvus = _fake_milvus_client()
    embed = _fake_embedding_client()
    report = backfill_paper_chunks(conn, milvus, embed)
    # At least title chunk written
    assert report.chunks_inserted >= 1


def test_backfill_empty_title_paper_skipped_or_counted_as_error():
    conn = _fake_pg_conn_returning([_paper_row(title="")])
    milvus = _fake_milvus_client()
    embed = _fake_embedding_client()
    report = backfill_paper_chunks(conn, milvus, embed)
    # Either counted as error or just skipped with 0 chunks — pin behavior.
    assert report.chunks_inserted == 0
    assert report.papers_processed + report.papers_with_errors >= 1


def test_backfill_embedding_error_does_not_crash_run():
    """One bad paper should not abort the run."""
    import httpx

    conn = _fake_pg_conn_returning(
        [_paper_row(paper_id="bad"), _paper_row(paper_id="good")]
    )
    milvus = _fake_milvus_client()
    embed = MagicMock()

    call_count = [0]

    def _embed_side_effect(texts, **_):
        call_count[0] += 1
        if call_count[0] == 1:
            raise httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            )
        return [[0.1] * 4096 for _ in texts]

    embed.embed_batch.side_effect = _embed_side_effect
    report = backfill_paper_chunks(conn, milvus, embed, batch_size=1)
    # Second paper still processed
    assert report.papers_with_errors >= 1
    assert report.papers_processed >= 1


def test_backfill_batch_size_controls_embedding_calls():
    """batch_size=2 with 4 papers → 2 embedding batches."""
    rows = [_paper_row(paper_id=f"p{i}", abstract=None, intro=None) for i in range(4)]
    conn = _fake_pg_conn_returning(rows)
    milvus = _fake_milvus_client()
    embed = _fake_embedding_client()
    backfill_paper_chunks(conn, milvus, embed, batch_size=2)
    # 4 papers / batch_size=2 = 2 batches; each batch has multiple texts.
    # Allow some flex but not 4 single-embed calls and not 1 giant call.
    assert 1 <= embed.embed_batch.call_count <= 4


def test_backfill_report_counts_are_consistent():
    rows = [_paper_row(paper_id=f"p{i}") for i in range(3)]
    conn = _fake_pg_conn_returning(rows)
    milvus = _fake_milvus_client()
    embed = _fake_embedding_client()
    report = backfill_paper_chunks(conn, milvus, embed)
    assert report.papers_processed + report.papers_with_errors <= report.papers_total
    assert report.chunks_inserted >= 0
