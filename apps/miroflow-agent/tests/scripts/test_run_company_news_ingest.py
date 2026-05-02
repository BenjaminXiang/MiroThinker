from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.data_agents.company.news_connectors import NewsRecord

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_company_news_ingest.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_news_ingest", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_company_select_sql_top200_limits_rank():
    cli = _import_cli()

    sql, params = cli._build_company_select_sql(priority="top200", limit=5)

    assert "priority_rank <= 200" in sql
    assert "unified_credit_code IS NOT NULL" in sql
    assert params == (5,)


def test_build_company_select_sql_others_excludes_top200():
    cli = _import_cli()

    sql, params = cli._build_company_select_sql(priority="others", limit=None)

    assert "priority_rank > 200" in sql
    assert params == ()


def test_dedupe_by_source_url_preserves_first_record():
    cli = _import_cli()
    records = [
        NewsRecord("COMP-1", "https://example.com/1", "first", None, None, None),
        NewsRecord("COMP-1", "https://example.com/1", "duplicate", None, None, None),
        NewsRecord("COMP-1", "https://example.com/2", "second", None, None, None),
    ]

    deduped = cli._dedupe_by_source_url(records)

    assert [record.title for record in deduped] == ["first", "second"]


def test_insert_news_records_uses_source_url_conflict_dedup():
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {
        "news_id": "11111111-1111-1111-1111-111111111111"
    }
    records = [
        NewsRecord(
            company_id="COMP-1",
            source_url="https://www.cnstock.com/company/1",
            title="示例科技发布新产品",
            summary="新闻摘要",
            published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            raw_text="新闻正文",
        )
    ]

    inserted = cli._insert_news_records(
        conn,
        records=records,
        run_id="11111111-1111-1111-1111-111111111111",
        company_host=None,
    )

    assert inserted == 1
    sql = conn.execute.call_args.args[0]
    assert "company_news_item" in sql
    assert "ON CONFLICT (source_url) DO NOTHING" in sql
    params = conn.execute.call_args.args[1]
    assert params[0] == "COMP-1"
    assert params[2] == "cnstock.com"
    assert params[3] == "trusted"


def test_insert_news_records_rejects_dry_run_sentinel_run_id():
    cli = _import_cli()
    conn = MagicMock()
    records = [NewsRecord("COMP-1", "https://example.com/1", "title", None, None, None)]

    with pytest.raises(ValueError, match="sentinel"):
        cli._insert_news_records(
            conn,
            records=records,
            run_id=UUID("00000000-0000-0000-0000-000000000000"),
            company_host=None,
        )
    conn.execute.assert_not_called()


def test_cli_dry_run_fetches_without_news_insert(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "company_id": "COMP-1",
            "unified_credit_code": "91440300EXAMPLE",
            "canonical_name": "深圳示例科技",
            "website_host": "example.com",
            "priority_rank": 1,
        }
    ]
    conn.execute.return_value = select_cursor

    class _Connector:
        def fetch(self, _credit_code, _since):
            return [
                NewsRecord(
                    company_id="91440300EXAMPLE",
                    source_url="https://www.cnstock.com/company/1",
                    title="深圳示例科技完成融资",
                    summary="数千万元融资。",
                    published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                    raw_text="数千万元融资。",
                )
            ]

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli, "_build_connectors", lambda _selection: [("fake", _Connector())]
    )
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        ["--dry-run", "--since", "2026-05-01", "--limit", "1", "--sleep-seconds", "0"]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["news_would_write"] == 1
    assert report["news_inserted"] == 0
    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any("INSERT INTO company_news_item" in sql for sql in sqls)


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)

    with pytest.raises(SystemExit) as exc:
        cli.main(["--limit", "1"])
    assert exc.value.code != 0
