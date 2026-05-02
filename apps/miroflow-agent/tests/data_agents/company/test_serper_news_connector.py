from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import requests

from src.data_agents.company.news_connectors.serper import (
    SerperNewsConnector,
    _parse_serper_date,
)


class _Response:
    def __init__(self, payload, *, error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


def test_empty_api_key_skips_without_http_call(caplog):
    caplog.set_level("INFO")
    session = MagicMock()
    connector = SerperNewsConnector("", session=session)

    records = connector.fetch("深圳示例科技", date(2026, 5, 1))

    assert records == []
    session.post.assert_not_called()
    assert "Skipping Serper fetch: SERPER_API_KEY not set" in caplog.text


def test_http_200_parses_news_items_to_records():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "news": [
                {
                    "title": "深圳示例科技完成A轮融资",
                    "link": "https://finance.example.com/news/1",
                    "snippet": "深圳示例科技完成数千万元A轮融资。",
                    "date": "2026-05-01T09:30:00+08:00",
                },
                {
                    "title": "深圳示例科技发布机器人新品",
                    "link": "https://tech.example.com/news/2",
                    "snippet": "新品面向工业机器人场景。",
                    "date": "Apr 30, 2026",
                },
                {
                    "title": "深圳示例科技中标项目",
                    "link": "https://gov.example.com/news/3",
                    "snippet": "中标智能制造项目。",
                    "date": "2 hours ago",
                },
            ]
        }
    )
    connector = SerperNewsConnector("serper-key", session=session)

    records = connector.fetch("深圳示例科技", date(2000, 1, 1))

    assert len(records) == 3
    assert records[0].company_id == "深圳示例科技"
    assert records[0].title == "深圳示例科技完成A轮融资"
    assert records[0].source_url == "https://finance.example.com/news/1"
    assert records[0].summary == "深圳示例科技完成数千万元A轮融资。"
    assert records[0].raw_text == "深圳示例科技完成数千万元A轮融资。"
    assert records[0].published_at == datetime(
        2026, 5, 1, 1, 30, tzinfo=timezone.utc
    )
    assert records[1].published_at == datetime(2026, 4, 30, tzinfo=timezone.utc)


def test_http_5xx_returns_empty_and_logs_warning(caplog):
    session = MagicMock()
    session.post.return_value = _Response(
        {},
        error=requests.exceptions.HTTPError("500 Server Error"),
    )
    connector = SerperNewsConnector("serper-key", session=session)

    records = connector.fetch("深圳示例科技", date(2026, 5, 1))

    assert records == []
    assert "Serper fetch failed for 深圳示例科技" in caplog.text


def test_http_401_returns_empty_gracefully():
    session = MagicMock()
    session.post.return_value = _Response(
        {},
        error=requests.exceptions.HTTPError("401 Client Error"),
    )
    connector = SerperNewsConnector("serper-key", session=session)

    assert connector.fetch("深圳示例科技", date(2026, 5, 1)) == []


def test_since_filter_drops_older_published_at():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "news": [
                {
                    "title": "旧新闻",
                    "link": "https://example.com/old",
                    "snippet": "早于 since。",
                    "date": "2026-04-30",
                },
                {
                    "title": "新新闻",
                    "link": "https://example.com/new",
                    "snippet": "等于 since。",
                    "date": "2026-05-01",
                },
            ]
        }
    )
    connector = SerperNewsConnector("serper-key", session=session)

    records = connector.fetch("深圳示例科技", date(2026, 5, 1))

    assert [record.source_url for record in records] == ["https://example.com/new"]


def test_dedup_by_source_url_preserves_first_result():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "news": [
                {
                    "title": "首条新闻",
                    "link": "https://example.com/news",
                    "snippet": "first",
                    "date": "2026-05-01",
                },
                {
                    "title": "重复新闻",
                    "link": "https://example.com/news",
                    "snippet": "duplicate",
                    "date": "2026-05-01",
                },
            ]
        }
    )
    connector = SerperNewsConnector("serper-key", session=session)

    records = connector.fetch("深圳示例科技", date(2026, 5, 1))

    assert [record.title for record in records] == ["首条新闻"]


def test_parse_serper_date_days_ago():
    parsed = _parse_serper_date("2 days ago")

    assert parsed is not None
    delta = datetime.now(timezone.utc) - parsed
    assert timedelta(days=2) - timedelta(seconds=2) <= delta <= timedelta(
        days=2, seconds=2
    )


def test_parse_serper_date_month_name():
    assert _parse_serper_date("Apr 30, 2026") == datetime(
        2026, 4, 30, tzinfo=timezone.utc
    )


def test_parse_serper_date_nonsense():
    assert _parse_serper_date("not a date") is None


def test_parse_serper_date_common_chinese_relative_forms():
    parsed = _parse_serper_date("2 小时前")

    assert parsed is not None
    delta = datetime.now(timezone.utc) - parsed
    assert timedelta(hours=2) - timedelta(seconds=2) <= delta <= timedelta(
        hours=2, seconds=2
    )


def test_query_contains_canonical_name_noise_filters_and_qdr():
    session = MagicMock()
    session.post.return_value = _Response({"news": []})
    connector = SerperNewsConnector("serper-key", session=session)

    connector.fetch("深圳示例科技", datetime.now(timezone.utc).date() - timedelta(days=7))

    payload = session.post.call_args.kwargs["json"]
    assert payload["q"] == (
        "深圳示例科技 (融资 OR 发布 OR 收购 OR 上市 OR 任命 OR 中标) -招聘 -招标公告"
    )
    assert payload["tbs"] == "qdr:w"
    assert payload["num"] == 10
    assert payload["hl"] == "zh-cn"
    assert payload["gl"] == "cn"
    assert session.post.call_args.kwargs["headers"] == {
        "X-API-KEY": "serper-key",
        "Content-Type": "application/json",
    }
