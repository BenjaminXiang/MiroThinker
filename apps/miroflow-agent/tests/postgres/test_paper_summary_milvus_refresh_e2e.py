from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from unittest.mock import MagicMock

import psycopg
from psycopg.rows import dict_row
import pytest

from src.data_agents.paper.milvus_backfill import backfill_paper_chunks
from src.data_agents.storage.milvus_collections import PAPER_CHUNKS_COLLECTION


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "run_paper_summary_zh_backfill.py"
)


def _import_summary_cli():
    spec = importlib.util.spec_from_file_location(
        "run_paper_summary_zh_backfill_milvus_refresh_e2e",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeMilvus:
    def __init__(self) -> None:
        self.deleted_filters: list[str] = []
        self.inserted_rows: list[dict[str, object]] = []

    def has_collection(self, _collection_name: str) -> bool:
        return True

    def delete(self, *, collection_name: str, filter: str) -> None:  # noqa: A002
        assert collection_name == PAPER_CHUNKS_COLLECTION
        self.deleted_filters.append(filter)

    def insert(self, *, collection_name: str, data: list[dict[str, object]]) -> None:
        assert collection_name == PAPER_CHUNKS_COLLECTION
        self.inserted_rows.extend(data)


class _FakeEmbedding:
    def __init__(self) -> None:
        self.text_batches: list[list[str]] = []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.text_batches.append(list(texts))
        return [[0.1] * 4096 for _ in texts]


def test_summary_backfill_updated_at_selects_paper_for_targeted_milvus_refresh(
    pg_migrated,
    pg_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del pg_migrated
    paper_id = "PAPER-SUMMARY-MILVUS-E2E"
    summary_zh = "这是用于向量刷新验证的新中文摘要。" * 12

    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        conn.execute("TRUNCATE TABLE paper_full_text, paper CASCADE")
        refresh_floor = conn.execute("SELECT now() AS ts").fetchone()["ts"]
        conn.execute(
            """
            INSERT INTO paper (
                paper_id,
                title_clean,
                year,
                venue,
                authors_display,
                abstract_clean,
                canonical_source,
                quality_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                paper_id,
                "Targeted paper vector refresh",
                2026,
                "NeurIPS",
                "A. Smith",
                "This paper tests a deterministic summary refresh contract.",
                "prof_page_only",
                "needs_enrichment",
            ),
        )
        conn.commit()

    cli = _import_summary_cli()
    monkeypatch.setattr(
        cli,
        "_open_database_connection",
        lambda _dsn: psycopg.connect(pg_dsn, row_factory=dict_row),
    )
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "translate_abstract_to_zh",
        lambda *_args, **_kwargs: summary_zh,
    )
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_args, **_kwargs: False)
    monkeypatch.setenv("DATABASE_URL", pg_dsn)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_paper_summary_zh_backfill.py",
            "--paper-id",
            paper_id,
            "--limit",
            "1",
        ],
    )

    cli.main()

    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            """
            SELECT summary_zh, updated_at
            FROM paper
            WHERE paper_id = %s
            """,
            (paper_id,),
        ).fetchone()
        assert row is not None
        assert row["summary_zh"] == summary_zh
        assert row["updated_at"] >= refresh_floor

        milvus = _FakeMilvus()
        embedding = _FakeEmbedding()
        report = backfill_paper_chunks(
            conn,
            milvus,
            embedding,
            changed_since=refresh_floor,
            batch_size=8,
        )

    assert report.papers_processed == 1
    assert any(paper_id in item for item in milvus.deleted_filters)
    abstract_chunks = [
        row for row in milvus.inserted_rows if row["chunk_type"] == "abstract"
    ]
    assert abstract_chunks
    assert abstract_chunks[0]["content_text"] == summary_zh
