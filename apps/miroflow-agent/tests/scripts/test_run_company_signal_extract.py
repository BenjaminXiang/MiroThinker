from __future__ import annotations

import json
import openai
import threading
import time
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


def test_parse_args_accepts_concurrency_and_checkpoint_stage():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--company-id",
            "COMP-1",
            "--concurrency",
            "2",
            "--llm-timeout-seconds",
            "45",
            "--llm-retry-budget",
            "1",
            "--checkpoint-stage",
            "signal_extract",
        ]
    )

    assert args.company_id == ["COMP-1"]
    assert args.concurrency == 2
    assert args.llm_timeout_seconds == 45
    assert args.llm_retry_budget == 1
    assert args.checkpoint_stage == "signal_extract"


def test_process_news_rows_uses_configured_worker_concurrency(monkeypatch):
    cli = _import_cli()
    active = 0
    max_active = 0
    lock = threading.Lock()

    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))

    def fake_extract_signal_events_from_news(**_kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return SignalExtractionResult(events=(), error=None)

    monkeypatch.setattr(
        cli,
        "extract_signal_events_from_news",
        fake_extract_signal_events_from_news,
    )
    rows = [
        {
            "company_id": f"COMP-{index}",
            "canonical_name": f"公司{index}",
            "news_id": f"news-{index}",
            "title": f"融资新闻{index}",
            "summary_clean": "完成融资。",
            "published_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
            "source_adapter": "pitchhub_36kr",
            "source_url": "https://pitchhub.36kr.com/project/1",
            "latest_funding_round": None,
            "latest_funding_time": None,
        }
        for index in range(4)
    ]

    results = cli._process_news_rows(
        rows,
        concurrency=2,
        llm_timeout_seconds=None,
        llm_retry_budget=None,
    )

    assert len(results) == 4
    assert max_active > 1


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
        status="needs_review",
    )


def test_build_news_select_sql_excludes_processed_by_default():
    cli = _import_cli()

    sql, params = cli._build_news_select_sql(
        since=date(2026, 5, 1),
        limit=10,
        include_processed=False,
        source_adapters=(),
        company_ids=(),
    )

    assert "NOT EXISTS" in sql
    assert "company_signal_event" in sql
    assert params == (date(2026, 5, 1), 10)


def test_build_news_select_sql_filters_source_adapters():
    cli = _import_cli()

    sql, params = cli._build_news_select_sql(
        since=date(2026, 5, 1),
        limit=None,
        include_processed=True,
        source_adapters=("iyiou", "pitchhub_36kr"),
        company_ids=(),
    )

    assert "n.source_adapter IN (%s, %s)" in sql
    assert "source_adapter" in sql
    assert params == (date(2026, 5, 1), "iyiou", "pitchhub_36kr")


def test_build_news_select_sql_filters_company_ids():
    cli = _import_cli()

    sql, params = cli._build_news_select_sql(
        since=date(2026, 5, 1),
        limit=None,
        include_processed=True,
        source_adapters=(),
        company_ids=("COMP-1", "COMP-2"),
    )

    assert "n.company_id IN (%s, %s)" in sql
    assert "NOT EXISTS" not in sql
    assert params == (date(2026, 5, 1), "COMP-1", "COMP-2")


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
    assert "status" in sql
    assert "ON CONFLICT (company_id, event_type, dedup_key) DO NOTHING" in sql
    params = conn.execute.call_args.args[1]
    assert params[-1] == "needs_review"


def test_insert_signal_events_counts_duplicate_conflict_as_zero_inserted():
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None

    inserted = cli._insert_signal_events(
        conn,
        events=(_event(),),
        run_id="11111111-1111-1111-1111-111111111111",
    )

    assert inserted == 0
    sql = conn.execute.call_args.args[0]
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
            "source_adapter": "pitchhub_36kr",
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
    assert report["source_adapter_counts"] == {
        "pitchhub_36kr": {
            "news_processed": 1,
            "events_extracted": 1,
            "events_would_write": 1,
            "events_inserted": 0,
        }
    }
    sqls = [call.args[0] for call in conn.execute.call_args_list if call.args]
    assert not any("INSERT INTO company_signal_event" in sql for sql in sqls)


def test_cli_accepts_source_adapter_filter(monkeypatch, capsys):
    cli = _import_cli()
    captured: dict[str, object] = {}

    def _fake_build_news_select_sql(**kwargs):
        captured.update(kwargs)
        return "SELECT 1 WHERE false", ()

    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "_open_llm_client", lambda: (MagicMock(), "gemma", {}))
    monkeypatch.setattr(cli, "_build_news_select_sql", _fake_build_news_select_sql)
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--dry-run",
            "--since",
            "2026-05-01",
            "--source-adapter",
            "iyiou",
            "--source-adapter",
            "pitchhub_36kr",
        ]
    )

    json.loads(capsys.readouterr().out)
    assert captured["source_adapters"] == ("iyiou", "pitchhub_36kr")


def test_open_llm_client_disables_proxy_env(monkeypatch):
    cli = _import_cli()
    captured: dict[str, object] = {}
    fake_http_client = object()

    def fake_httpx_client(**kwargs):
        captured["httpx_kwargs"] = kwargs
        return fake_http_client

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["openai_kwargs"] = kwargs

    class FakeTaskSettings:
        base_url = "http://127.0.0.1:1234/v1"
        api_key = "EMPTY"
        model = "deepseek-v4-pro"
        extra_body = {"thinking": {"type": "disabled"}}
        timeout_seconds = 90.0
        retry_budget = 1

    def fake_resolve_company_llm_task_settings(task_type, **kwargs):
        captured["task_type"] = task_type
        captured["settings_kwargs"] = kwargs
        return FakeTaskSettings()

    monkeypatch.setattr(
        cli,
        "resolve_company_llm_task_settings",
        fake_resolve_company_llm_task_settings,
    )
    monkeypatch.setattr(cli.httpx, "Client", fake_httpx_client)
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)

    client, model, extra_body = cli._open_llm_client(
        timeout_seconds=45.0,
        retry_budget=1,
    )

    assert isinstance(client, FakeOpenAI)
    assert model == "deepseek-v4-pro"
    assert extra_body == {"thinking": {"type": "disabled"}}
    assert captured["task_type"] == "financing_extraction"
    assert captured["settings_kwargs"] == {
        "timeout_seconds": 45.0,
        "retry_budget": 1,
    }
    assert captured["httpx_kwargs"] == {"timeout": 90.0, "trust_env": False}
    assert captured["openai_kwargs"]["http_client"] is fake_http_client
    assert captured["openai_kwargs"]["max_retries"] == 1


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)

    with pytest.raises(SystemExit) as exc:
        cli.main(["--limit", "1"])
    assert exc.value.code != 0
