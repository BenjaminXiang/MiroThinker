from __future__ import annotations

from datetime import date, datetime, timezone

from src.data_agents.company.news_connectors import (
    NewsRecord,
    PitchHubNewsConnector,
    YiouNewsConnector,
    YiouSearchContext,
    extract_yiou_search_hints_with_llm,
)


class _FixtureConnector:
    def __init__(self, records: list[NewsRecord]) -> None:
        self.records = records

    def fetch(self, _company_name: str, _since: date) -> list[NewsRecord]:
        return self.records


class _MappedFixtureConnector:
    def __init__(self, records_by_query: dict[str, list[NewsRecord]]) -> None:
        self.records_by_query = records_by_query
        self.queries: list[str] = []

    def fetch(self, company_name: str, _since: date) -> list[NewsRecord]:
        self.queries.append(company_name)
        return self.records_by_query.get(company_name, [])


def test_yiou_adapter_marks_data_iyiou_records_with_source_provenance():
    published_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    delegate = _FixtureConnector(
        [
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://data.iyiou.com/news/123",
                title="深圳示例科技发布工业机器人产品",
                summary="来自亿欧数据的正文摘要。",
                published_at=published_at,
                raw_text="来自亿欧数据的正文摘要。",
            )
        ]
    )
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_diagnostics("深圳示例科技", date(2026, 5, 1))

    assert result.diagnostics["items_seen"] == 1
    assert result.diagnostics["items_accepted"] == 1
    assert result.diagnostics["adapter"] == "iyiou"
    assert result.records[0].source_adapter == "iyiou"
    assert result.records[0].source_url == "https://data.iyiou.com/news/123"
    assert result.records[0].extraction_diagnostics == {
        "adapter": "iyiou",
        "status": "accepted",
        "source_domain": "data.iyiou.com",
    }


def test_yiou_adapter_filters_offsite_records_and_reports_diagnostics():
    delegate = _FixtureConnector(
        [
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://example.com/news/123",
                title="非亿欧来源",
                summary="snippet",
                published_at=None,
                raw_text="snippet",
            )
        ]
    )
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_diagnostics("深圳示例科技", date(2026, 5, 1))

    assert result.records == []
    assert result.diagnostics["items_seen"] == 1
    assert result.diagnostics["items_accepted"] == 0
    assert result.diagnostics["items_rejected_offsite"] == 1


def test_yiou_adapter_filters_generic_yiou_pages_and_reports_diagnostics():
    delegate = _FixtureConnector(
        [
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://data.iyiou.com/",
                title="亿欧数据首页",
                summary="generic",
                published_at=None,
                raw_text="generic",
            ),
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://data.iyiou.com/company",
                title="亿欧数据企业列表",
                summary="generic",
                published_at=None,
                raw_text="generic",
            ),
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://data.iyiou.com/company/details/abc/profile",
                title="深圳示例科技_亿欧数据",
                summary="company profile",
                published_at=None,
                raw_text="company profile",
            ),
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://data.iyiou.com/intelligence/details/def",
                title="深圳示例科技融资情报",
                summary="funding intelligence",
                published_at=None,
                raw_text="funding intelligence",
            ),
        ]
    )
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_diagnostics("深圳示例科技", date(2026, 5, 1))

    assert [record.source_url for record in result.records] == [
        "https://data.iyiou.com/company/details/abc/profile",
        "https://data.iyiou.com/intelligence/details/def",
    ]
    assert result.diagnostics["items_seen"] == 4
    assert result.diagnostics["items_accepted"] == 2
    assert result.diagnostics["items_rejected_irrelevant_path"] == 2


def test_yiou_adapter_retries_normalized_name_query_terms():
    delegate = _MappedFixtureConnector(
        {
            "映刻科技": [
                NewsRecord(
                    company_id="映刻科技",
                    source_url="https://data.iyiou.com/company/details/abc/profile",
                    title="映刻科技_深圳市映刻科技有限公司_亿欧数据",
                    summary="映刻科技企业画像。",
                    published_at=None,
                    raw_text="映刻科技企业画像。",
                )
            ]
        }
    )
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_diagnostics(
        "深圳市映刻科技有限公司", date(2026, 5, 1)
    )

    assert delegate.queries == ["深圳市映刻科技有限公司", "映刻科技"]
    assert [record.source_url for record in result.records] == [
        "https://data.iyiou.com/company/details/abc/profile"
    ]
    assert result.records[0].company_id == "深圳市映刻科技有限公司"
    assert result.diagnostics["records_by_query"] == {
        "深圳市映刻科技有限公司": 0,
        "映刻科技": 1,
    }


def test_yiou_adapter_rejects_name_mismatch_records():
    delegate = _FixtureConnector(
        [
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://data.iyiou.com/company/details/abc/profile",
                title="无关企业_亿欧数据",
                summary="另一家企业的画像。",
                published_at=None,
                raw_text="另一家企业的画像。",
            )
        ]
    )
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_diagnostics("深圳示例科技", date(2026, 5, 1))

    assert result.records == []
    assert result.diagnostics["items_seen"] == 1
    assert result.diagnostics["items_rejected_name_mismatch"] == 1


def test_yiou_adapter_uses_description_alias_and_founder_query_terms():
    delegate = _MappedFixtureConnector(
        {
            "ExampleBot": [
                NewsRecord(
                    company_id="ExampleBot",
                    source_url="https://data.iyiou.com/company/details/example/profile",
                    title="ExampleBot_深圳市示例机器人有限公司_亿欧数据",
                    summary="ExampleBot是一家具身智能机器人公司。",
                    published_at=None,
                    raw_text="ExampleBot是一家具身智能机器人公司。",
                )
            ],
            "ExampleBot 张三": [],
        }
    )
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="深圳市示例机器人有限公司",
            normalized_name="示例机器人",
            description="公司简称ExampleBot，专注具身智能机器人与工业自动化。",
            team_raw="张三，职务：创始人，介绍：曾负责机器人产品研发。",
        ),
        date(2026, 5, 1),
    )

    assert "ExampleBot" in delegate.queries
    assert "ExampleBot 张三" in delegate.queries
    assert [record.source_url for record in result.records] == [
        "https://data.iyiou.com/company/details/example/profile"
    ]
    assert "ExampleBot" in result.diagnostics["query_terms"]
    assert "张三" in result.diagnostics["founder_terms"]


def test_pitchhub_adapter_rejects_records_matching_only_llm_product_aliases():
    delegate = _MappedFixtureConnector(
        {
            "停车机器人": [
                NewsRecord(
                    company_id="停车机器人",
                    source_url="https://pitchhub.36kr.com/project/2002545744060296",
                    title="智象机器人 | 项目信息-36氪",
                    summary="智象机器人是一家停车机器人研发商。",
                    published_at=None,
                    raw_text="智象机器人是一家停车机器人研发商。",
                )
            ]
        }
    )
    connector = PitchHubNewsConnector(delegate)

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="深圳闪移技术",
            normalized_name="闪移技术",
            aliases=("挪车机器人", "停车机器人"),
            keywords=("机器人停车解决方案",),
        ),
        date(2026, 5, 1),
    )

    assert "停车机器人" in result.diagnostics["query_terms"]
    assert result.records == []
    assert result.diagnostics["items_seen"] == 1
    assert result.diagnostics["items_rejected_name_mismatch"] == 1


def test_yiou_adapter_does_not_use_broad_llm_alias_as_identity_match():
    delegate = _MappedFixtureConnector(
        {
            "奇朵": [
                NewsRecord(
                    company_id="奇朵",
                    source_url=(
                        "https://data.iyiou.com/company/details/"
                        "3b8111604605d266c9e763c8d7344ea3/profile"
                    ),
                    title="Arabica Coffee_上海拉比卡咖啡有限公司 - 亿欧数据",
                    summary="Arabica Coffee只贩售意式浓缩、玛奇朵、拿铁等咖啡饮品。",
                    published_at=None,
                    raw_text="Arabica Coffee只贩售意式浓缩、玛奇朵、拿铁等咖啡饮品。",
                )
            ]
        }
    )
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="奇朵智能设备",
            normalized_name="奇朵智能设备",
            aliases=("奇朵",),
            identity_aliases=("奇朵智能",),
        ),
        date(2026, 5, 1),
    )

    assert "奇朵" in result.diagnostics["query_terms"]
    assert result.records == []
    assert result.diagnostics["items_rejected_name_mismatch"] == 1


def test_pitchhub_adapter_rejects_investor_organization_pages():
    delegate = _FixtureConnector(
        [
            NewsRecord(
                company_id="深圳示例科技",
                source_url="https://pitchhub.36kr.com/organization/1678245605127170",
                title="科大讯飞 | 投资机构信息-36氪",
                summary="投资机构页面包含深圳示例科技相关项目。",
                published_at=None,
                raw_text="投资机构页面包含深圳示例科技相关项目。",
            )
        ]
    )
    connector = PitchHubNewsConnector(delegate)

    result = connector.fetch_with_diagnostics("深圳示例科技", date(2026, 5, 1))

    assert result.records == []
    assert result.diagnostics["items_rejected_irrelevant_path"] == 1


def test_yiou_adapter_does_not_use_generic_product_phrases_as_aliases():
    delegate = _MappedFixtureConnector({})
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="深圳市路可为科技有限公司",
            normalized_name="路可为科技",
            description="公司提供产品的研发为配套，提供工业自动化相关技术开发和销售及技术服务。",
            team_raw="彭志毅，职务：创始人，介绍：负责产品研发。",
        ),
        date(2026, 5, 1),
    )

    assert result.diagnostics["aliases"] == []
    assert result.diagnostics["query_terms"] == [
        "深圳市路可为科技有限公司",
        "路可为科技",
    ]


def test_yiou_adapter_does_not_use_provide_as_deterministic_alias():
    delegate = _MappedFixtureConnector({})
    connector = YiouNewsConnector(delegate)

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="图灵集市（深圳）科技有限公司",
            normalized_name="图灵集市科技",
            description="公司品牌提供AI服务与企业服务平台。",
        ),
        date(2026, 5, 1),
    )

    assert all(
        not alias.startswith("提供") for alias in result.diagnostics["aliases"]
    )
    assert all(
        not term.startswith("提供") for term in result.diagnostics["query_terms"]
    )
    assert result.diagnostics["query_terms"] == [
        "图灵集市（深圳）科技有限公司",
        "图灵集市科技",
        "图灵集市（深圳）科技",
    ]


def test_yiou_llm_hint_extraction_parses_alias_founder_and_keywords():
    class _Message:
        content = (
            '{"identity_aliases":["示例机器人"],'
            '"aliases":["ExampleBot","示例机器人"],'
            '"founder_names":["张三"],'
            '"keywords":["具身智能","工业自动化"]}'
        )

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **_kwargs):
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    hints = extract_yiou_search_hints_with_llm(
        company_name="深圳市示例机器人有限公司",
        description="公司简称ExampleBot，专注具身智能机器人与工业自动化。",
        team_raw="张三，职务：创始人，介绍：曾负责机器人产品研发。",
        llm_client=_Client(),
        llm_model="fake-model",
    )

    assert hints.aliases == ("ExampleBot", "示例机器人")
    assert hints.identity_aliases == ("示例机器人",)
    assert hints.founder_names == ("张三",)
    assert hints.keywords == ("具身智能", "工业自动化")
    assert hints.source == "llm"


def test_pitchhub_adapter_uses_same_context_queries_and_provenance():
    delegate = _MappedFixtureConnector(
        {
            "旭宏医疗": [
                NewsRecord(
                    company_id="旭宏医疗",
                    source_url="https://pitchhub.36kr.com/project/1678475362006017",
                    title="旭宏医疗| 项目信息 - 创投平台",
                    summary="深圳旭宏医疗科技有限公司是一家海归创业的高科技企业。",
                    published_at=None,
                    raw_text="深圳旭宏医疗科技有限公司是一家海归创业的高科技企业。",
                )
            ],
            "旭宏医疗 李四": [],
            "深圳旭宏医疗科技有限公司": [],
        }
    )
    connector = PitchHubNewsConnector(delegate)

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="深圳旭宏医疗科技有限公司",
            normalized_name="深圳旭宏医疗科技",
            description="企业简称旭宏医疗，专注创新心电系统开发。",
            team_raw="李四，职务：创始人，介绍：海归创业者。",
        ),
        date(2026, 5, 1),
    )

    assert "深圳旭宏医疗科技有限公司" in delegate.queries
    assert "旭宏医疗" in delegate.queries
    assert "旭宏医疗 李四" in delegate.queries
    assert result.records[0].source_adapter == "pitchhub_36kr"
    assert result.records[0].source_url == (
        "https://pitchhub.36kr.com/project/1678475362006017"
    )
    assert result.diagnostics["site_filter"] == "pitchhub.36kr.com"


def test_pitchhub_adapter_fetches_detail_text_after_acceptance():
    delegate = _MappedFixtureConnector(
        {
            "旭宏医疗": [
                NewsRecord(
                    company_id="旭宏医疗",
                    source_url="https://pitchhub.36kr.com/project/1678475362006017",
                    title="旭宏医疗| 项目信息 - 创投平台",
                    summary="深圳旭宏医疗科技有限公司是一家海归创业的高科技企业。",
                    published_at=None,
                    raw_text="深圳旭宏医疗科技有限公司是一家海归创业的高科技企业。",
                )
            ]
        }
    )

    class _Response:
        text = "## 旭宏医疗\n## 项目简介\n## 融资历史\nA轮 2020-07 数千万人民币"

        def raise_for_status(self):
            return None

    class _Session:
        def __init__(self):
            self.urls: list[str] = []

        def get(self, url, **_kwargs):
            self.urls.append(url)
            return _Response()

    session = _Session()
    connector = PitchHubNewsConnector(
        delegate,
        reader_fallback_prefix="https://r.jina.ai/http://r.jina.ai/http://",
        session=session,
    )

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="深圳旭宏医疗科技有限公司",
            description="企业简称旭宏医疗，专注创新心电系统开发。",
        ),
        date(2026, 5, 1),
    )

    assert "融资历史" in result.records[0].raw_text
    assert result.records[0].extraction_diagnostics["detail_fetch_status"] == (
        "reader_fallback_success"
    )
    assert result.diagnostics["detail_fetch_attempts"] == 1
    assert result.diagnostics["detail_fetch_success"] == 1
    assert session.urls == [
        "https://r.jina.ai/http://r.jina.ai/http://"
        "https://pitchhub.36kr.com/project/1678475362006017"
    ]


def test_pitchhub_adapter_rejects_detail_page_when_primary_entity_mismatches():
    delegate = _MappedFixtureConnector(
        {
            "拨云见日": [
                NewsRecord(
                    company_id="拨云见日",
                    source_url="https://pitchhub.36kr.com/project/1678236619387904",
                    title="上声电子 | 项目信息-36氪",
                    summary="相关项目里提到了拨云见日，但该页主体是上声电子。",
                    published_at=None,
                    raw_text="相关项目里提到了拨云见日，但该页主体是上声电子。",
                )
            ]
        }
    )

    class _Response:
        text = (
            "Title: 上声电子 | 项目信息-36氪\n\n"
            "URL Source: https://pitchhub.36kr.com/project/1678236619387904\n\n"
            "Markdown Content:\n\n## 上声电子\n\n汽车扬声器供应商。"
        )

        def raise_for_status(self):
            return None

    class _Session:
        def get(self, _url, **_kwargs):
            return _Response()

    connector = PitchHubNewsConnector(
        delegate,
        reader_fallback_prefix="https://r.jina.ai/http://r.jina.ai/http://",
        session=_Session(),
    )

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="拨云见日（深圳）智能科技有限公司",
            normalized_name="拨云见日深圳智能科技",
            description="企业简称拨云见日，是智慧工厂一站式解决方案提供商。",
        ),
        date(2026, 5, 1),
    )

    assert result.records == []
    assert result.diagnostics["detail_identity_rejected"] == 1


def test_pitchhub_adapter_accepts_detail_page_when_primary_entity_matches():
    delegate = _MappedFixtureConnector(
        {
            "拨云见日": [
                NewsRecord(
                    company_id="拨云见日",
                    source_url="https://pitchhub.36kr.com/project/2011619802646018",
                    title="拨云见日 | 项目信息-36氪",
                    summary="拨云见日是一家智慧工厂方案商。",
                    published_at=None,
                    raw_text="拨云见日是一家智慧工厂方案商。",
                )
            ]
        }
    )

    class _Response:
        text = (
            "Title: 拨云见日 | 项目信息-36氪\n\n"
            "URL Source: https://pitchhub.36kr.com/project/2011619802646018\n\n"
            "Markdown Content:\n\n## 拨云见日\n\n智慧工厂方案商。"
        )

        def raise_for_status(self):
            return None

    class _Session:
        def get(self, _url, **_kwargs):
            return _Response()

    connector = PitchHubNewsConnector(
        delegate,
        reader_fallback_prefix="https://r.jina.ai/http://r.jina.ai/http://",
        session=_Session(),
    )

    result = connector.fetch_with_context(
        YiouSearchContext(
            company_name="拨云见日（深圳）智能科技有限公司",
            normalized_name="拨云见日深圳智能科技",
            description="企业简称拨云见日，是智慧工厂一站式解决方案提供商。",
        ),
        date(2026, 5, 1),
    )

    assert [record.source_url for record in result.records] == [
        "https://pitchhub.36kr.com/project/2011619802646018"
    ]
    assert result.diagnostics["detail_identity_rejected"] == 0
