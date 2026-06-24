from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data_agents.paper.full_text_fetcher import FullTextExtract

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_paper_full_text_source_lane.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_paper_full_text_source_lane", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(**overrides):
    row = {
        "paper_id": "PAPER-1",
        "title_clean": "A Paper",
        "pdf_url": "https://example.org/paper.pdf",
        "full_text_source": "paper_full_text",
        "summary_zh": None,
        "abstract_clean": None,
        "full_text_abstract": None,
        "full_text_intro": None,
        "existing_pdf_sha256": None,
        "fetch_error": None,
    }
    row.update(overrides)
    return row


def _extract(**overrides):
    extract = FullTextExtract(
        paper_id="PAPER-1",
        abstract=None,
        intro=None,
        pdf_url="https://example.org/paper.pdf",
        pdf_sha256=None,
        source="failed",
        fetch_error=None,
    )
    return FullTextExtract(**{**asdict(extract), **overrides})


def test_cli_help(capsys):
    cli = _import_cli()

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--limit" in captured.out
    assert "--dry-run" in captured.out
    assert "--worker-count" in captured.out
    assert "--paper-id-file" in captured.out


def test_build_select_sql_targets_pdf_source_gaps():
    cli = _import_cli()

    sql, params = cli._build_select_sql(
        limit=25,
        paper_ids=(),
        worker_count=4,
        worker_index=2,
    )

    compact_sql = " ".join(sql.split())
    assert "JOIN paper_full_text pft ON pft.paper_id = p.paper_id" in compact_sql
    assert "pft.pdf_url IS NOT NULL" in compact_sql
    assert "NULLIF(BTRIM(COALESCE(pft.abstract, '')), '') IS NULL" in compact_sql
    assert "NULLIF(BTRIM(COALESCE(pft.intro, '')), '') IS NULL" in compact_sql
    assert "mod(abs(hashtext(p.paper_id)::bigint), %s) = %s" in compact_sql
    assert params == (4, 2, 25)


def test_full_text_lane_persists_usable_abstract_without_summary_write(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        _row(paper_id="PAPER-ABSTRACT", pdf_url="https://example.org/a.pdf")
    ]
    conn.execute.return_value = select_cursor
    upsert = MagicMock()

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "upsert_paper_full_text", upsert)
    monkeypatch.setattr(
        cli,
        "_resolve_checkpoint_path",
        lambda _run_id: tmp_path / "full-text.jsonl",
    )
    monkeypatch.setattr(
        cli,
        "fetch_pdf_url_full_text",
        lambda *_a, **_kw: _extract(
            paper_id="PAPER-ABSTRACT",
            abstract=(
                "This paper contains a usable abstract extracted from the PDF "
                "and can feed downstream source-grounded summary generation."
            ),
            pdf_sha256="sha-1",
            source="full_text_lane:paper_full_text",
            fetch_error=None,
        ),
    )

    cli.main(["--limit", "1"])

    upsert.assert_called_once()
    update_sqls = [
        call.args[0]
        for call in conn.execute.call_args_list
        if call.args and isinstance(call.args[0], str) and "UPDATE paper" in call.args[0]
    ]
    assert update_sqls == []
    report = json.loads(capsys.readouterr().out)
    assert report["papers_processed"] == 1
    assert report["fetch_attempted"] == 1
    assert report["fetch_persisted"] == 1
    assert report["summaries_written"] == 0
    assert report["fetched_no_usable_text"] == 0


@pytest.mark.parametrize(
    ("fetch_error", "expected_key"),
    [
        ("http_403", "http_status_counts"),
        ("timeout", "timeouts"),
        ("pdf_content_type_disallowed", "content_type_rejections"),
        ("pdf_too_large", "size_cap_rejections"),
        ("pdf_parse_error", "parse_failures"),
    ],
)
def test_full_text_lane_reports_fetch_failure_buckets(
    monkeypatch,
    tmp_path,
    capsys,
    fetch_error,
    expected_key,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [_row()]
    conn.execute.return_value = select_cursor

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "upsert_paper_full_text", MagicMock())
    monkeypatch.setattr(
        cli,
        "_resolve_checkpoint_path",
        lambda _run_id: tmp_path / "full-text.jsonl",
    )
    monkeypatch.setattr(
        cli,
        "fetch_pdf_url_full_text",
        lambda *_a, **_kw: _extract(fetch_error=fetch_error),
    )

    cli.main(["--limit", "1"])

    report = json.loads(capsys.readouterr().out)
    assert report["fetch_attempted"] == 1
    assert report["fetch_failed"] == 1
    if expected_key == "http_status_counts":
        assert report["http_status_counts"] == {"403": 1}
    else:
        assert report[expected_key] == 1
    assert report["failure_samples"][0]["reason"] == fetch_error
    assert report["failure_samples"][0]["retry_recommendation"]


def test_full_text_lane_reports_fetched_but_no_usable_text(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [_row()]
    conn.execute.return_value = select_cursor

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "upsert_paper_full_text", MagicMock())
    monkeypatch.setattr(
        cli,
        "_resolve_checkpoint_path",
        lambda _run_id: tmp_path / "full-text.jsonl",
    )
    monkeypatch.setattr(
        cli,
        "fetch_pdf_url_full_text",
        lambda *_a, **_kw: _extract(
            pdf_sha256="sha-no-text",
            source="full_text_lane:paper_full_text",
            fetch_error=None,
        ),
    )

    cli.main(["--limit", "1"])

    report = json.loads(capsys.readouterr().out)
    assert report["fetch_fetched"] == 1
    assert report["fetch_persisted"] == 0
    assert report["fetched_no_usable_text"] == 1


def test_full_text_lane_skips_duplicate_pdf_content(
    monkeypatch,
    tmp_path,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [_row()]
    conn.execute.return_value = select_cursor
    upsert = MagicMock()

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "open_pipeline_run", lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setattr(cli, "upsert_paper_full_text", upsert)
    monkeypatch.setattr(cli, "_find_duplicate_pdf_sha", lambda *_a, **_kw: "PAPER-OTHER")
    monkeypatch.setattr(
        cli,
        "_resolve_checkpoint_path",
        lambda _run_id: tmp_path / "full-text.jsonl",
    )
    monkeypatch.setattr(
        cli,
        "fetch_pdf_url_full_text",
        lambda *_a, **_kw: _extract(
            abstract=(
                "This paper contains a usable abstract extracted from the PDF "
                "but the PDF hash is already attached to another paper."
            ),
            pdf_sha256="sha-duplicate",
            source="full_text_lane:paper_full_text",
            fetch_error=None,
        ),
    )

    cli.main(["--limit", "1"])

    upsert.assert_not_called()
    report = json.loads(capsys.readouterr().out)
    assert report["duplicate_content"] == 1
    assert report["fetch_persisted"] == 0
    assert report["failure_samples"][0]["reason"] == "duplicate_pdf_sha256"
