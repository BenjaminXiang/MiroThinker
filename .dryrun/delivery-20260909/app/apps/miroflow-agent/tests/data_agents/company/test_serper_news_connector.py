from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import requests

from src.data_agents.company.news_connectors.serper import (
    SerperNewsConnector,
    SerperSearchConnector,
    _build_query,
    _extract_text,
    _normalize_site_filters,
    _parse_serper_date,
    build_generic_identity_queries,
)


class _Response:
    def __init__(
        self,
        payload,
        *,
        error: Exception | None = None,
        text: str = "",
    ) -> None:
        self._payload = payload
        self._error = error
        self.text = text

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


def test_search_connector_parses_organic_items_for_site_filtered_sources():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "organic": [
                {
                    "title": "旭宏医疗_深圳旭宏医疗科技有限公司_亿欧数据",
                    "link": "https://data.iyiou.com/company/details/d3b449/profile",
                    "snippet": "旭宏医疗是一家医疗科技公司。",
                }
            ]
        }
    )
    connector = SerperSearchConnector(
        "serper-key",
        session=session,
        site_filters=("data.iyiou.com",),
    )

    records = connector.fetch("深圳旭宏医疗科技有限公司", date(2026, 1, 1))

    assert len(records) == 1
    assert records[0].company_id == "深圳旭宏医疗科技有限公司"
    assert records[0].title == "旭宏医疗_深圳旭宏医疗科技有限公司_亿欧数据"
    assert records[0].source_url == "https://data.iyiou.com/company/details/d3b449/profile"
    assert records[0].summary == "旭宏医疗是一家医疗科技公司。"
    assert session.post.call_args.args[0] == "https://google.serper.dev/search"
    payload = session.post.call_args.kwargs["json"]
    assert payload["q"] == "深圳旭宏医疗科技有限公司 site:data.iyiou.com"
    assert "tbs" not in payload


def test_serper_connector_reuses_recent_query_cache(
    monkeypatch,
    tmp_path,
):
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "organic": [
                {
                    "title": "旭宏医疗_深圳旭宏医疗科技有限公司_亿欧数据",
                    "link": "https://data.iyiou.com/company/details/d3b449/profile",
                    "snippet": "旭宏医疗是一家医疗科技公司。",
                }
            ]
        }
    )
    monkeypatch.setenv("MIROTHINKER_COMPANY_SOURCE_CACHE_DIR", str(tmp_path))
    connector = SerperSearchConnector(
        "serper-key",
        session=session,
        site_filters=("data.iyiou.com",),
    )

    first = connector.fetch("深圳旭宏医疗科技有限公司", date(2026, 1, 1))
    second = connector.fetch("深圳旭宏医疗科技有限公司", date(2026, 1, 1))

    assert len(first) == 1
    assert len(second) == 1
    assert session.post.call_count == 1
    assert list(tmp_path.glob("*.json"))


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


def test_query_contains_site_filters_and_limits_tail():
    session = MagicMock()
    session.post.return_value = _Response({"news": []})
    connector = SerperNewsConnector(
        "serper-key",
        session=session,
        site_filters=("data.iyiou.com", "tech.example.com"),
    )

    connector.fetch("深圳示例科技", date(2026, 5, 1))

    payload = session.post.call_args.kwargs["json"]
    query = payload["q"]
    assert "site:data.iyiou.com" in query
    assert "site:tech.example.com" in query
    assert (
        " (融资 OR 发布 OR 收购 OR 上市 OR 任命 OR 中标 OR 产品) -招聘 -招标公告" in query
    )
    assert payload["tbs"].startswith("qdr:")


def test_site_filters_skip_non_matching_serper_items():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "news": [
                {
                    "title": "目标企业新闻",
                    "link": "https://data.iyiou.com/news/1",
                    "snippet": "匹配到目标站点。",
                    "date": "2026-05-01",
                },
                {
                    "title": "非目标站点新闻",
                    "link": "https://tech.example.com/news/2",
                    "snippet": "不该出现。",
                    "date": "2026-05-01",
                },
            ]
        }
    )
    connector = SerperNewsConnector(
        "serper-key",
        session=session,
        site_filters=("data.iyiou.com",),
    )

    records = connector.fetch("深圳示例科技", date(2026, 5, 1))

    assert len(records) == 1
    assert records[0].source_url == "https://data.iyiou.com/news/1"


def test_fetch_article_text_replaces_summary_when_available_and_trimmed():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "news": [
                {
                    "title": "示例融资公告",
                    "link": "https://data.iyiou.com/news/1",
                    "snippet": "这是简短摘要。",
                    "date": "2026-05-01",
                }
            ]
        }
    )
    session.get.return_value = _Response(
        {},
        text="<html><body><h1>标题</h1><p>正文第一段</p><p>正文第二段</p></body></html>",
    )
    connector = SerperNewsConnector(
        "serper-key",
        session=session,
        site_filters=("data.iyiou.com",),
        fetch_article_content=True,
        article_max_chars=80,
    )

    records = connector.fetch("深圳示例科技", date(2026, 5, 1))

    assert len(records) == 1
    assert records[0].summary == "标题\n正文第一段\n正文第二段"
    assert records[0].raw_text == "标题\n正文第一段\n正文第二段"
    assert records[0].summary == records[0].raw_text


def test_fetch_article_text_skips_waf_like_pages_and_keeps_snippet():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "news": [
                {
                    "title": "示例融资公告",
                    "link": "https://data.iyiou.com/news/1",
                    "snippet": "这是简短摘要。",
                    "date": "2026-05-01",
                }
            ]
        }
    )
    session.get.return_value = _Response(
        {},
        text="<html><head><script>window.location.href='/';</script></head>"
        "<body><div>x-waf-captcha-referer</div></body></html>",
    )
    connector = SerperNewsConnector(
        "serper-key",
        session=session,
        site_filters=("data.iyiou.com",),
        fetch_article_content=True,
        article_max_chars=100,
    )

    records = connector.fetch("深圳示例科技", date(2026, 5, 1))

    assert len(records) == 1
    assert records[0].summary == "这是简短摘要。"
    assert records[0].raw_text == "这是简短摘要。"


def test_fetch_article_text_uses_reader_fallback_when_direct_fetch_fails():
    session = MagicMock()
    session.post.return_value = _Response(
        {
            "organic": [
                {
                    "title": "旭宏医疗| 项目信息 - 创投平台",
                    "link": "https://pitchhub.36kr.com/project/1678475362006017",
                    "snippet": "搜索摘要",
                }
            ]
        }
    )
    session.get.side_effect = [
        _Response({}, error=requests.exceptions.SSLError("ssl eof")),
        _Response(
            {},
            text=(
                "Title: 旭宏医疗 | 项目信息-36氪\n\n"
                "## 项目简介\n深圳旭宏医疗科技有限公司是一家海归创业的高科技企业。\n"
                "## 融资历史\nA轮 2020-07 数千万人民币 力合科创"
            ),
        ),
    ]
    connector = SerperSearchConnector(
        "serper-key",
        session=session,
        site_filters=("pitchhub.36kr.com",),
        fetch_article_content=True,
        reader_fallback_prefix="https://r.jina.ai/http://r.jina.ai/http://",
    )

    records = connector.fetch("深圳旭宏医疗科技有限公司", date(2026, 1, 1))

    assert records[0].summary.startswith("Title: 旭宏医疗")
    assert "融资历史" in records[0].raw_text
    assert session.get.call_args_list[1].args[0] == (
        "https://r.jina.ai/http://r.jina.ai/http://"
        "https://pitchhub.36kr.com/project/1678475362006017"
    )


def test_normalize_site_filters_removes_protocol_and_subpath():
    assert _normalize_site_filters(("https://Data.IYIOU.com/abc", "  ", "www.abc.com/path")) == (
        "abc.com",
        "data.iyiou.com",
    )


def test_build_query_appends_site_filters_before_keywords():
    query = _build_query("深圳示例科技", site_filters=("data.iyiou.com", "tech.example.com"))
    assert query.startswith("深圳示例科技 site:data.iyiou.com site:tech.example.com")
    assert "产品" in query


def test_extract_text_removes_script_style_and_compacts_spaces():
    html = """
      <html><head><script>window.bad()</script><style>body{}</style></head>
      <body><p>一  </p><p>  二  </p><script>skip</script></body></html>
    """
    text = _extract_text(html)

    assert text == "一\n二"


def test_query_contains_canonical_name_noise_filters_and_qdr():
    session = MagicMock()
    session.post.return_value = _Response({"news": []})
    connector = SerperNewsConnector("serper-key", session=session)

    connector.fetch("深圳示例科技", datetime.now(timezone.utc).date() - timedelta(days=7))

    payload = session.post.call_args.kwargs["json"]
    assert payload["q"] == "深圳示例科技"
    assert "融资" not in payload["q"]
    assert "发布" not in payload["q"]
    assert "产品" not in payload["q"]
    assert "招聘" not in payload["q"]
    assert "创始人" not in payload["q"]
    assert "医疗AI" not in payload["q"]
    assert payload["tbs"] == "qdr:w"
    assert payload["num"] == 10
    assert payload["hl"] == "zh-cn"
    assert payload["gl"] == "cn"
    assert session.post.call_args.kwargs["headers"] == {
        "X-API-KEY": "serper-key",
        "Content-Type": "application/json",
    }


def test_build_generic_identity_queries_uses_trusted_names_without_keyword_tails():
    queries = build_generic_identity_queries(
        "深圳旭宏医疗科技有限公司",
        registered_name="深圳旭宏医疗科技有限公司",
        xlsx_company_name="深圳旭宏医疗科技有限公司",
        project_name="旭宏医疗",
        aliases=("旭宏医疗", "旭宏医疗 王博洋", "医疗AI", "融资动态"),
    )

    assert queries == ["深圳旭宏医疗科技有限公司", "旭宏医疗"]
    assert all(" " not in query for query in queries)
    assert all("融资" not in query for query in queries)
    assert all("产品" not in query for query in queries)
    assert all("创始" not in query for query in queries)
    assert all("医疗AI" not in query for query in queries)
