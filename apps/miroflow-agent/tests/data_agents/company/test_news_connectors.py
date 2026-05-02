from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from src.data_agents.company.news_connectors import (
    CNStockConnector,
    TushareConnector,
    parse_news_payload,
)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_tushare_connector_parses_fields_items_response():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "code": 0,
            "data": {
                "fields": ["datetime", "title", "content", "url"],
                "items": [
                    [
                        "20260501",
                        "深圳示例科技完成A轮融资",
                        "深圳示例科技完成数千万元A轮融资。",
                        "https://finance.example.com/news/1",
                    ]
                ],
            },
        }
    )
    connector = TushareConnector("token", session=session)

    records = connector.fetch("91440300EXAMPLE", date(2026, 4, 1))

    assert len(records) == 1
    record = records[0]
    assert record.company_id == "91440300EXAMPLE"
    assert record.title == "深圳示例科技完成A轮融资"
    assert record.source_url == "https://finance.example.com/news/1"
    assert record.published_at.date().isoformat() == "2026-05-01"
    payload = session.post.call_args.kwargs["json"]
    assert payload["params"]["credit_code"] == "91440300EXAMPLE"
    assert payload["params"]["start_date"] == "20260401"


def test_tushare_connector_skips_when_token_missing():
    session = MagicMock()
    connector = TushareConnector("", session=session)

    assert connector.fetch("91440300EXAMPLE", date(2026, 4, 1)) == []
    session.post.assert_not_called()


def test_cnstock_connector_parses_article_response():
    session = MagicMock()
    session.get.return_value = _Response(
        {
            "articles": [
                {
                    "publish_time": "2026-05-01T09:30:00+08:00",
                    "headline": "示例科技发布新产品",
                    "description": "面向工业机器人场景。",
                    "link": "https://www.cnstock.com/company/robot.html",
                }
            ]
        }
    )
    connector = CNStockConnector("token", session=session)

    records = connector.fetch("91440300EXAMPLE", date(2026, 4, 1))

    assert len(records) == 1
    assert records[0].title == "示例科技发布新产品"
    assert records[0].summary == "面向工业机器人场景。"
    params = session.get.call_args.kwargs["params"]
    assert params["keyword"] == "91440300EXAMPLE"
    assert params["since"] == "2026-04-01"


def test_parse_news_payload_skips_rows_without_url_or_title():
    records = parse_news_payload(
        {
            "items": [
                {"title": "缺少URL", "summary": "x"},
                {"url": "https://example.com/news/2", "summary": "缺少标题"},
                {"title": "完整新闻", "url": "https://example.com/news/3"},
            ]
        },
        company_id="COMP-1",
    )

    assert [record.title for record in records] == ["完整新闻"]
