from __future__ import annotations

import json
import threading
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


def test_parse_args_accepts_concurrency_and_checkpoint_stage():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--connector",
            "pitchhub",
            "--company-id",
            "COMP-1",
            "--concurrency",
            "2",
            "--llm-timeout-seconds",
            "45",
            "--llm-retry-budget",
            "1",
            "--checkpoint-stage",
            "news_pitchhub",
        ]
    )

    assert args.connector == "pitchhub"
    assert args.company_id == ["COMP-1"]
    assert args.concurrency == 2
    assert args.llm_timeout_seconds == 45
    assert args.llm_retry_budget == 1
    assert args.checkpoint_stage == "news_pitchhub"


def test_build_company_select_sql_top200_limits_rank():
    cli = _import_cli()

    sql, params = cli._build_company_select_sql(
        priority="top200",
        limit=5,
        company_ids=(),
    )

    assert "priority_rank <= 200" in sql
    assert "WHERE c.identity_status = 'resolved'" in sql
    assert "latest_snapshot.description" in sql
    assert "latest_snapshot.team_raw" in sql
    assert "latest_snapshot.project_name" in sql
    assert "c.registered_name" in sql
    assert "c.aliases" in sql
    assert "latest_snapshot.company_name_xlsx" in sql
    assert params == (5,)


def test_build_company_select_sql_others_excludes_top200():
    cli = _import_cli()

    sql, params = cli._build_company_select_sql(
        priority="others",
        limit=None,
        company_ids=(),
    )

    assert "priority_rank > 200" in sql
    assert params == ()


def test_build_company_select_sql_filters_uploaded_company_ids():
    cli = _import_cli()

    sql, params = cli._build_company_select_sql(
        priority="all",
        limit=10,
        company_ids=("COMP-2", "COMP-1"),
    )

    assert "company_id IN (%s, %s)" in sql
    assert "priority_rank <=" not in sql
    assert params == ("COMP-2", "COMP-1", 10)


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
        cli,
        "_build_connectors",
        lambda _selection, **_kwargs: [("fake", _Connector())],
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


def test_cli_dry_run_processes_companies_concurrently_when_configured(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "company_id": "COMP-1",
            "unified_credit_code": "91440300EXAMPLE1",
            "canonical_name": "深圳示例一科技",
            "website_host": "one.example",
            "priority_rank": 1,
        },
        {
            "company_id": "COMP-2",
            "unified_credit_code": "91440300EXAMPLE2",
            "canonical_name": "深圳示例二科技",
            "website_host": "two.example",
            "priority_rank": 2,
        },
    ]
    conn.execute.return_value = select_cursor
    barrier = threading.Barrier(2)

    class _Connector:
        def fetch(self, fetch_key, _since):
            barrier.wait(timeout=1)
            return [
                NewsRecord(
                    company_id=fetch_key,
                    source_url=f"https://example.com/{fetch_key}",
                    title=f"{fetch_key} 产品动态",
                    summary=f"{fetch_key} 发布产品。",
                    published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                    raw_text=f"{fetch_key} 发布产品。",
                )
            ]

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_build_connectors",
        lambda _selection, **_kwargs: [("fake", _Connector())],
    )
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
            "--limit",
            "2",
            "--sleep-seconds",
            "0",
            "--concurrency",
            "2",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["companies_processed"] == 2
    assert report["companies_with_errors"] == 0
    assert report["news_would_write"] == 2


def test_cli_dry_run_uses_canonical_name_for_yiou_connector(monkeypatch, capsys):
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
    fetched_keys: list[str] = []

    class _Connector:
        def fetch(self, fetch_key, _since):
            fetched_keys.append(fetch_key)
            return []

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_build_connectors",
        lambda _selection, **_kwargs: [("iyiou", _Connector())],
    )
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--connector",
            "iyiou",
            "--dry-run",
            "--since",
            "2026-05-01",
            "--limit",
            "1",
            "--sleep-seconds",
            "0",
        ]
    )

    json.loads(capsys.readouterr().out)
    assert fetched_keys == ["深圳示例科技"]


def test_cli_dry_run_passes_snapshot_context_to_yiou_connector(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "company_id": "COMP-1",
            "unified_credit_code": "91440300EXAMPLE",
            "canonical_name": "深圳市示例机器人有限公司",
            "normalized_name": "示例机器人",
            "website_host": "example.com",
            "priority_rank": 1,
            "project_name": "ExampleBot",
            "description": "公司简称ExampleBot，专注具身智能机器人。",
            "team_raw": "张三，职务：创始人，介绍：曾负责机器人产品研发。",
        }
    ]
    conn.execute.return_value = select_cursor
    contexts: list[object] = []

    class _Connector:
        def fetch_with_context(self, context, _since):
            contexts.append(context)
            return []

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_build_connectors",
        lambda _selection, **_kwargs: [("iyiou", _Connector())],
    )
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--connector",
            "iyiou",
            "--dry-run",
            "--since",
            "2026-05-01",
            "--limit",
            "1",
            "--sleep-seconds",
            "0",
        ]
    )

    json.loads(capsys.readouterr().out)
    assert len(contexts) == 1
    assert contexts[0].company_name == "深圳市示例机器人有限公司"
    assert contexts[0].normalized_name == "示例机器人"
    assert contexts[0].project_name == "ExampleBot"
    assert contexts[0].description == "公司简称ExampleBot，专注具身智能机器人。"
    assert contexts[0].team_raw == "张三，职务：创始人，介绍：曾负责机器人产品研发。"


def test_build_yiou_context_adds_llm_search_hints():
    cli = _import_cli()

    context = cli._build_yiou_context_from_company_row(
        {
            "company_id": "COMP-1",
            "canonical_name": "深圳市示例机器人有限公司",
            "normalized_name": "示例机器人",
            "project_name": "ExampleBot",
            "description": "专注具身智能机器人。",
            "team_raw": "张三，职务：创始人。",
        },
        search_hints=cli.YiouSearchHints(
            aliases=("示例Bot",),
            founder_names=("张三",),
            keywords=("具身智能",),
            source="llm",
        ),
    )

    assert context.aliases == ("示例Bot",)
    assert context.founder_names == ("张三",)
    assert context.keywords == ("具身智能",)


def test_fetch_generic_serper_uses_identity_queries_and_records_diagnostics():
    cli = _import_cli()
    fetched_keys: list[str] = []

    class _Connector:
        def fetch(self, fetch_key, _since):
            fetched_keys.append(fetch_key)
            if fetch_key == "旭宏医疗":
                return [
                    NewsRecord(
                        company_id=fetch_key,
                        source_url="https://example.com/xuhong",
                        title="旭宏医疗产品动态",
                        summary="旭宏医疗发布心电产品。",
                        published_at=None,
                        raw_text="旭宏医疗发布心电产品。",
                    )
                ]
            return []

    records, diagnostics = cli._fetch_generic_serper_identity_records(
        _Connector(),
        {
            "company_id": "COMP-1",
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "registered_name": "深圳旭宏医疗科技有限公司",
            "company_name_xlsx": "深圳旭宏医疗科技有限公司",
            "project_name": "旭宏医疗",
            "aliases": ["旭宏医疗", "旭宏医疗 王博洋", "医疗AI"],
        },
        datetime(2026, 5, 1, tzinfo=timezone.utc).date(),
    )

    assert fetched_keys == ["深圳旭宏医疗科技有限公司", "旭宏医疗"]
    assert [record.source_url for record in records] == ["https://example.com/xuhong"]
    assert diagnostics["records_by_query"] == {
        "深圳旭宏医疗科技有限公司": 0,
        "旭宏医疗": 1,
    }
    assert diagnostics["query_kind"] == "generic_identity"


def test_fetch_generic_serper_includes_only_llm_trusted_identity_aliases():
    cli = _import_cli()
    fetched_keys: list[str] = []

    class _Connector:
        def fetch(self, fetch_key, _since):
            fetched_keys.append(fetch_key)
            return []

    _records, diagnostics = cli._fetch_generic_serper_identity_records(
        _Connector(),
        {
            "company_id": "COMP-1",
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "registered_name": "深圳旭宏医疗科技有限公司",
            "company_name_xlsx": "深圳旭宏医疗科技有限公司",
            "project_name": "",
            "aliases": [],
        },
        datetime(2026, 5, 1, tzinfo=timezone.utc).date(),
        search_hints=cli.YiouSearchHints(
            identity_aliases=("旭宏医疗", "旭宏医疗 王博洋"),
            aliases=("心电系统", "医疗AI"),
            founder_names=("王博洋",),
            keywords=("心电",),
            source="llm",
        ),
    )

    assert fetched_keys == ["深圳旭宏医疗科技有限公司", "旭宏医疗"]
    assert diagnostics["query_terms"] == ["深圳旭宏医疗科技有限公司", "旭宏医疗"]
    assert "心电系统" not in diagnostics["query_terms"]
    assert "王博洋" not in diagnostics["query_terms"]
    assert "医疗AI" not in diagnostics["query_terms"]


def test_cli_dry_run_passes_snapshot_context_to_pitchhub_connector(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    select_cursor = MagicMock()
    select_cursor.fetchall.return_value = [
        {
            "company_id": "COMP-1",
            "unified_credit_code": "91440300EXAMPLE",
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "normalized_name": "深圳旭宏医疗科技",
            "website_host": "example.com",
            "priority_rank": 1,
            "project_name": "旭宏医疗",
            "description": "企业简称旭宏医疗，专注创新心电系统开发。",
            "team_raw": "李四，职务：创始人，介绍：海归创业者。",
        }
    ]
    conn.execute.return_value = select_cursor
    contexts: list[object] = []

    class _Connector:
        def fetch_with_context(self, context, _since):
            contexts.append(context)
            return []

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_build_connectors",
        lambda _selection, **_kwargs: [("pitchhub", _Connector())],
    )
    monkeypatch.setattr(
        cli,
        "open_pipeline_run",
        lambda *_a, **_kw: "11111111-1111-1111-1111-111111111111",
    )
    monkeypatch.setattr(cli, "close_pipeline_run", lambda *_a, **_kw: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--connector",
            "pitchhub",
            "--dry-run",
            "--since",
            "2026-05-01",
            "--limit",
            "1",
            "--sleep-seconds",
            "0",
        ]
    )

    json.loads(capsys.readouterr().out)
    assert len(contexts) == 1
    assert contexts[0].company_name == "深圳旭宏医疗科技有限公司"
    assert contexts[0].project_name == "旭宏医疗"


def test_cli_missing_database_url_exits_nonzero(monkeypatch):
    cli = _import_cli()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_TEST", raising=False)

    with pytest.raises(SystemExit) as exc:
        cli.main(["--limit", "1"])
    assert exc.value.code != 0


def test_parse_args_accepts_serper_connector():
    cli = _import_cli()

    args = cli._parse_args(["--connector", "serper"])

    assert args.connector == "serper"


def test_parse_args_accepts_yiou_connector():
    cli = _import_cli()

    args = cli._parse_args(["--connector", "iyiou"])

    assert args.connector == "iyiou"


def test_parse_args_accepts_pitchhub_connector():
    cli = _import_cli()

    args = cli._parse_args(["--connector", "pitchhub"])

    assert args.connector == "pitchhub"


def test_parse_args_accepts_company_ids_and_llm_search_hints():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--connector",
            "iyiou",
            "--company-id",
            "COMP-1",
            "--company-id",
            "COMP-2",
            "--llm-search-hints",
        ]
    )

    assert args.company_id == ["COMP-1", "COMP-2"]
    assert args.llm_search_hints is True


def test_parse_args_accepts_enrichment_batch_id():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--connector",
            "iyiou",
            "--enrichment-batch-id",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        ]
    )

    assert args.enrichment_batch_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_record_fetch_audit_persists_connector_diagnostics():
    cli = _import_cli()
    conn = MagicMock()

    inserted = cli._record_fetch_audit(
        conn,
        batch_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        company_id="COMP-1",
        connector_name="iyiou",
        diagnostics={
            "records_by_query": {"旭宏医疗": 2},
            "items_accepted": 0,
            "items_rejected_name_mismatch": 2,
        },
        search_hints=cli.YiouSearchHints(
            aliases=("旭宏医疗",),
            founder_names=(),
            keywords=("心电",),
            source="llm",
        ),
    )

    assert inserted == 1
    conn.execute.assert_called()
    assert "company_enrichment_search_audit" in conn.execute.call_args.args[0]
    params = conn.execute.call_args.args[1]
    assert params["query_text"] == "旭宏医疗"
    assert params["miss_reason"] == "all_results_rejected"


def test_parse_args_accepts_serper_site_and_article_options():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--connector",
            "serper",
            "--serper-site",
            "data.iyiou.com",
            "--serper-fetch-article-text",
            "--serper-article-max-chars",
            "1200",
        ]
    )

    assert args.connector == "serper"
    assert args.serper_site == ["data.iyiou.com"]
    assert args.serper_fetch_article_text is True
    assert args.serper_article_max_chars == 1200


def test_build_connectors_serper_only_when_selected(monkeypatch):
    cli = _import_cli()
    constructed: list[tuple[str, str]] = []

    class _FakeSerper:
        def __init__(self, api_key, **kwargs):
            constructed.append(("serper", api_key))

    class _UnexpectedLegacy:
        def __init__(self, _api_key):
            raise AssertionError("legacy connector should not be constructed")

    monkeypatch.setattr(cli, "SerperNewsConnector", _FakeSerper)
    monkeypatch.setattr(cli, "TushareConnector", _UnexpectedLegacy)
    monkeypatch.setattr(cli, "CNStockConnector", _UnexpectedLegacy)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-token")
    monkeypatch.setenv("CNSTOCK_TOKEN", "cnstock-token")

    connectors = cli._build_connectors("serper")

    assert [name for name, _connector in connectors] == ["serper"]
    assert constructed == [("serper", "serper-key")]


def test_build_connectors_passes_serper_site_and_article_options(monkeypatch):
    cli = _import_cli()
    captured: dict[str, object] = {}

    class _FakeSerper:
        def __init__(self, api_key, **kwargs):
            captured["api_key"] = api_key
            captured["site_filters"] = kwargs.get("site_filters")
            captured["fetch_article_content"] = kwargs.get("fetch_article_content")
            captured["article_max_chars"] = kwargs.get("article_max_chars")

    monkeypatch.setattr(cli, "SerperNewsConnector", _FakeSerper)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")

    connectors = cli._build_connectors(
        "serper",
        serper_site_filters=["data.iyiou.com"],
        fetch_article_text=True,
        article_max_chars=1200,
    )

    assert [name for name, _connector in connectors] == ["serper"]
    assert captured["api_key"] == "serper-key"
    assert captured["site_filters"] == ["data.iyiou.com"]
    assert captured["fetch_article_content"] is True
    assert captured["article_max_chars"] == 1200


def test_build_connectors_yiou_wraps_serper_search_with_data_iyiou_filter(monkeypatch):
    cli = _import_cli()
    captured: dict[str, object] = {}

    class _FakeSerperSearch:
        def __init__(self, api_key, **kwargs):
            captured["api_key"] = api_key
            captured["site_filters"] = kwargs.get("site_filters")
            captured["fetch_article_content"] = kwargs.get("fetch_article_content")
            captured["article_max_chars"] = kwargs.get("article_max_chars")
            captured["reader_fallback_prefix"] = kwargs.get("reader_fallback_prefix")
            captured["reader_fallback_prefix"] = kwargs.get("reader_fallback_prefix")

    class _FakeYiou:
        def __init__(self, delegate):
            captured["delegate"] = delegate

    monkeypatch.setattr(cli, "SerperSearchConnector", _FakeSerperSearch)
    monkeypatch.setattr(cli, "YiouNewsConnector", _FakeYiou)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")

    connectors = cli._build_connectors(
        "iyiou",
        fetch_article_text=True,
        article_max_chars=1200,
    )

    assert [name for name, _connector in connectors] == ["iyiou"]
    assert captured["api_key"] == "serper-key"
    assert captured["site_filters"] == ["data.iyiou.com"]
    assert captured["fetch_article_content"] is True
    assert captured["article_max_chars"] == 1200
    assert captured["delegate"] is not None


def test_build_connectors_pitchhub_wraps_serper_search_with_pitchhub_filter(monkeypatch):
    cli = _import_cli()
    captured: dict[str, object] = {}

    class _FakeSerperSearch:
        def __init__(self, api_key, **kwargs):
            captured["api_key"] = api_key
            captured["site_filters"] = kwargs.get("site_filters")
            captured["fetch_article_content"] = kwargs.get("fetch_article_content")
            captured["article_max_chars"] = kwargs.get("article_max_chars")
            captured["reader_fallback_prefix"] = kwargs.get("reader_fallback_prefix")

    class _FakePitchHub:
        def __init__(self, delegate, **kwargs):
            captured["delegate"] = delegate
            captured["pitchhub_reader_fallback_prefix"] = kwargs.get(
                "reader_fallback_prefix"
            )
            captured["pitchhub_article_max_chars"] = kwargs.get("article_max_chars")

    monkeypatch.setattr(cli, "SerperSearchConnector", _FakeSerperSearch)
    monkeypatch.setattr(cli, "PitchHubNewsConnector", _FakePitchHub)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")

    connectors = cli._build_connectors(
        "pitchhub",
        fetch_article_text=True,
        article_max_chars=1200,
    )

    assert [name for name, _connector in connectors] == ["pitchhub"]
    assert captured["api_key"] == "serper-key"
    assert captured["site_filters"] == ["pitchhub.36kr.com"]
    assert captured["fetch_article_content"] is False
    assert captured["article_max_chars"] == 1200
    assert captured["reader_fallback_prefix"] is None
    assert captured["pitchhub_reader_fallback_prefix"] == cli.READER_FALLBACK_PREFIX
    assert captured["pitchhub_article_max_chars"] == 4000
    assert captured["delegate"] is not None


def test_build_connectors_all_defaults_to_serper_only(monkeypatch):
    cli = _import_cli()
    constructed: list[str] = []

    class _FakeSerper:
        def __init__(self, _api_key, **_kwargs):
            constructed.append("serper")

    class _UnexpectedLegacy:
        def __init__(self, _api_key):
            raise AssertionError("legacy connector should not be constructed")

    monkeypatch.setattr(cli, "SerperNewsConnector", _FakeSerper)
    monkeypatch.setattr(cli, "TushareConnector", _UnexpectedLegacy)
    monkeypatch.setattr(cli, "CNStockConnector", _UnexpectedLegacy)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-token")
    monkeypatch.setenv("CNSTOCK_TOKEN", "cnstock-token")

    connectors = cli._build_connectors("all")

    assert [name for name, _connector in connectors] == ["serper"]
    assert constructed == ["serper"]


def test_build_connectors_all_skips_gracefully_without_serper_key(monkeypatch, caplog):
    caplog.set_level("INFO")
    cli = _import_cli()
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-token")
    monkeypatch.setenv("CNSTOCK_TOKEN", "cnstock-token")

    connectors = cli._build_connectors("all")

    assert connectors == []
    assert "Skipping Serper connector: SERPER_API_KEY is not set" in caplog.text


def test_build_connectors_tushare_explicit_still_works(monkeypatch):
    cli = _import_cli()
    constructed: list[tuple[str, str]] = []

    class _FakeTushare:
        def __init__(self, token):
            constructed.append(("tushare", token))

    class _UnexpectedOther:
        def __init__(self, _api_key):
            raise AssertionError("other connector should not be constructed")

    monkeypatch.setattr(cli, "TushareConnector", _FakeTushare)
    monkeypatch.setattr(cli, "SerperNewsConnector", _UnexpectedOther)
    monkeypatch.setattr(cli, "CNStockConnector", _UnexpectedOther)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-token")
    monkeypatch.setenv("CNSTOCK_TOKEN", "cnstock-token")

    connectors = cli._build_connectors("tushare")

    assert [name for name, _connector in connectors] == ["tushare"]
    assert constructed == [("tushare", "tushare-token")]


def test_build_connectors_cnstock_explicit_still_works(monkeypatch):
    cli = _import_cli()
    constructed: list[tuple[str, str]] = []

    class _FakeCNStock:
        def __init__(self, token):
            constructed.append(("cnstock", token))

    class _UnexpectedOther:
        def __init__(self, _api_key):
            raise AssertionError("other connector should not be constructed")

    monkeypatch.setattr(cli, "CNStockConnector", _FakeCNStock)
    monkeypatch.setattr(cli, "SerperNewsConnector", _UnexpectedOther)
    monkeypatch.setattr(cli, "TushareConnector", _UnexpectedOther)
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-token")
    monkeypatch.setenv("CNSTOCK_TOKEN", "cnstock-token")

    connectors = cli._build_connectors("cnstock")

    assert [name for name, _connector in connectors] == ["cnstock"]
    assert constructed == [("cnstock", "cnstock-token")]
