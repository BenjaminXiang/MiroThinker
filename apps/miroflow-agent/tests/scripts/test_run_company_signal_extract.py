from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.data_agents.company.signal_event_extractor import (
    SignalEventExtraction,
    SignalExtractionResult,
)

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_company_signal_extract.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_signal_extract", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event() -> SignalEventExtraction:
    return SignalEventExtraction(
        company_id="COMP-1",
        primary_news_id="11111111-1111-1111-1111-111111111111",
        event_type="funding",
        event_date=date(2026, 5, 1),
        event_subject_normalized={"company_name": "示例科技"},
        event_summary="深圳示例科技完成A轮融资。",
        confidence=Decimal("0.86"),
        corroborating_news_ids=("11111111-1111-1111-1111-111111111111",),
        dedup_key="dedup-key",
    )


def test_build_news_select_sql_excludes_processed_by_default():
    cli = _import_cli()

    sql, params = cli._build_news_select_sql(
        since=date(2026, 5, 1),
        limit=10,
        include_processed=False,
    )

    assert "NOT EXISTS" in sql
    assert "company_signal_event" in sql
    assert params == (date(2026, 5, 1), 10)


def test_insert_signal_events_uses_dedup_conflict():
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {
        "event_id": "22222222-2222-2222-2222-222222222222"
    }

    inserted = cli._insert_signal_events(
        conn,
        events=(_event(),),
        run_id="11111111-1111-1111-1111-111111111111",
    )

    assert inserted == 1
    sql = conn.execute.call_args.args[0]
    assert "company_signal_event" in sql
    assert "ON CONFLICT (company_id, event_type, dedup_key) DO NOTHING" in sql


def test_insert_signal_events_rejects_dry_run_sentinel_run_id():
    cli = _import_cli()
    conn = MagicMock()

    with pytest.raises(ValueError, match="sentinel"):
        cli._insert_signal_events(
            conn,
            events=(_event(),),
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
        )
    conn.execute.assert_not_called()


def test_cli_dry_run_extracts_without_signal_insert(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "深圳示例科技",
            "source_url": "https://www.cnstock.com/company/1",
            "title": "深圳示例科技完成A轮融资",
            "summary_clean": "数千万元融资。",
            "published_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
            "fetched_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        }
    ]
    conn.execute.return_value = select_cursor

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(
        cli,
        "extract_signal_events_from_news",
        lambda **_kwargs: SignalExtractionResult(events=(_event(),), error=None),
    )
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(["--dry-run", "--since", "2026-05-01", "--limit", "1"])

    report = json.loads(capsys.readouterr().out)
    assert report["events_extracted"] == 1
    assert report["events_would_write"] == 1
    assert report["events_inserted"] == 0
    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any("INSERT INTO company_signal_event" in sql for sql in sqls)


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)

    with pytest.raises(SystemExit) as exc:
        cli.main(["--limit", "1"])
    assert exc.value.code != 0
