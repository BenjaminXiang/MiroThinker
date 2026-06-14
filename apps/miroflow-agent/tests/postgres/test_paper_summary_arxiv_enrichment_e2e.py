from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from unittest.mock import MagicMock

import psycopg
from psycopg.rows import dict_row
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "run_paper_summary_zh_backfill.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_paper_summary_zh_backfill_e2e",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_arxiv_metadata_enrichment_updates_real_postgres(
    pg_migrated,
    pg_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del pg_migrated
    paper_id = "PAPER-ARXIV-E2E"
    with psycopg.connect(pg_dsn) as conn:
        conn.execute("TRUNCATE TABLE paper CASCADE")
        conn.execute(
            """
            INSERT INTO paper (
                paper_id,
                title_clean,
                arxiv_id,
                canonical_source,
                quality_status
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                paper_id,
                "Arxiv-only metadata paper",
                "2401.00001",
                "prof_page_only",
                "needs_enrichment",
            ),
        )
        conn.commit()

    cli = _import_cli()
    monkeypatch.setattr(
        cli,
        "_open_database_connection",
        lambda _dsn: psycopg.connect(pg_dsn, row_factory=dict_row),
    )
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "translate_abstract_to_zh",
        lambda *_args, **_kwargs: "这是一段足够长的中文论文摘要。" * 10,
    )
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        cli,
        "enrich_paper_with_hybrid_sources",
        lambda _doi, **_kwargs: cli.PaperMetadataEnrichment(
            abstract="Abstract from arXiv.",
            venue="arXiv",
            enrichment_sources=("arxiv",),
        ),
    )
    monkeypatch.setenv("DATABASE_URL", pg_dsn)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_paper_summary_zh_backfill.py",
            "--enrich-doi-metadata",
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
            SELECT abstract_clean, venue, summary_zh, quality_status
            FROM paper
            WHERE paper_id = %s
            """,
            (paper_id,),
        ).fetchone()
    assert row is not None
    assert row["abstract_clean"] == "Abstract from arXiv."
    assert row["venue"] == "arXiv"
    assert row["summary_zh"] == "这是一段足够长的中文论文摘要。" * 10
    assert row["quality_status"] == "partial"


def test_identifier_contradiction_writes_issue_and_blocks_ready(
    pg_migrated,
    pg_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del pg_migrated
    paper_id = "PAPER-CONFLICT-E2E"
    with psycopg.connect(pg_dsn) as conn:
        conn.execute("TRUNCATE TABLE pipeline_issue, paper CASCADE")
        conn.execute(
            """
            INSERT INTO paper (
                paper_id,
                title_clean,
                doi,
                year,
                venue,
                authors_display,
                canonical_source,
                quality_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                paper_id,
                "Identifier conflict paper",
                "10.1234/canonical",
                2026,
                "NeurIPS",
                "A. Smith",
                "prof_page_only",
                "needs_enrichment",
            ),
        )
        conn.commit()

    cli = _import_cli()
    monkeypatch.setattr(
        cli,
        "_open_database_connection",
        lambda _dsn: psycopg.connect(pg_dsn, row_factory=dict_row),
    )
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "translate_abstract_to_zh",
        lambda *_args, **_kwargs: "这是一段足够长的中文论文摘要。" * 10,
    )
    monkeypatch.setattr(cli, "judge_summary_boilerplate", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        cli,
        "enrich_paper_with_hybrid_sources",
        lambda _doi, **_kwargs: cli.PaperMetadataEnrichment(
            abstract="Abstract from conflicting source.",
            enrichment_sources=("crossref",),
            identifier_contradictions=(
                cli.PaperIdentifierContradiction(
                    identifier_type="doi",
                    canonical_value="10.1234/canonical",
                    source_value="10.1234/conflicting",
                    source="crossref",
                ),
            ),
        ),
    )
    monkeypatch.setenv("DATABASE_URL", pg_dsn)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_paper_summary_zh_backfill.py",
            "--enrich-doi-metadata",
            "--paper-id",
            paper_id,
            "--limit",
            "1",
        ],
    )

    cli.main()

    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        paper = conn.execute(
            """
            SELECT abstract_clean, summary_zh, quality_status
            FROM paper
            WHERE paper_id = %s
            """,
            (paper_id,),
        ).fetchone()
        issue = conn.execute(
            """
            SELECT stage,
                   severity,
                   evidence_snapshot->>'issue_type' AS issue_type,
                   evidence_snapshot->'contradictions'->0->>'source_value'
                       AS source_value
            FROM pipeline_issue
            WHERE institution = %s
            """,
            (f"paper:{paper_id}",),
        ).fetchone()

    assert paper is not None
    assert paper["abstract_clean"] == "Abstract from conflicting source."
    assert paper["summary_zh"] == "这是一段足够长的中文论文摘要。" * 10
    assert paper["quality_status"] == "needs_review"
    assert issue == {
        "stage": "paper_quality",
        "severity": "high",
        "issue_type": "identifier_contradiction",
        "source_value": "10.1234/conflicting",
    }
