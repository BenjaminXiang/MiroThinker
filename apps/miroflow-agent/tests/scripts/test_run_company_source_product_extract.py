from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.data_agents.company.official_product_capture import (
    CompanyApplicationScenarioCandidate,
    CompanyProductCandidate,
)

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_company_source_product_extract.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_source_product_extract", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_source_news_select_sql_filters_source_adapters():
    cli = _import_cli()

    sql, params = cli._build_source_news_select_sql(
        limit=10,
        source_adapters=("pitchhub_36kr", "iyiou"),
        company_ids=(),
    )

    assert "n.source_adapter IN (%s, %s)" in sql
    assert "n.summary_clean IS NOT NULL" in sql
    assert params == ("pitchhub_36kr", "iyiou", 10)


def test_build_source_news_select_sql_filters_company_ids():
    cli = _import_cli()

    sql, params = cli._build_source_news_select_sql(
        limit=None,
        source_adapters=("pitchhub_36kr",),
        company_ids=("COMP-1", "COMP-2"),
    )

    assert "n.company_id IN (%s, %s)" in sql
    assert params == ("pitchhub_36kr", "COMP-1", "COMP-2")


def test_parse_args_accepts_batch_and_llm_fallback_flags():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--enrichment-batch-id",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "--llm-structured-extract",
            "--concurrency",
            "4",
            "--llm-timeout-seconds",
            "45",
            "--llm-retry-budget",
            "1",
            "--checkpoint-stage",
            "source_product_extract",
        ]
    )

    assert args.enrichment_batch_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert args.llm_structured_extract is True
    assert args.concurrency == 4
    assert args.llm_timeout_seconds == 45
    assert args.llm_retry_budget == 1
    assert args.checkpoint_stage == "source_product_extract"


def test_cli_dry_run_extracts_products_without_insert(monkeypatch, capsys):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
            "source_adapter": "pitchhub_36kr",
            "title": "旭宏医疗",
            "summary_clean": "项目简介：Semacare 专注创新心电系统开发，运用 AI 自动诊断技术支持临床。",
        }
    ]
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(["--dry-run", "--limit", "1", "--source-adapter", "pitchhub_36kr"])

    report = json.loads(capsys.readouterr().out)
    assert report["news_processed"] == 1
    assert report["products_extracted"] == 1
    assert report["products_inserted"] == 0
    assert report["products_with_target_customers"] == 1
    assert report["scenarios_extracted"] == 1
    assert report["scenarios_inserted"] == 0
    assert report["source_adapter_counts"]["pitchhub_36kr"] == {
        "news_processed": 1,
        "products_extracted": 1,
        "products_inserted": 0,
        "scenarios_extracted": 1,
        "scenarios_inserted": 0,
        "product_gate_rejected": 0,
        "candidate_gate_rejected": 0,
    }
    assert set(report["items"][0]) == {
        "product_name",
        "product_description",
        "product_category",
        "technical_tags",
        "target_customers",
        "application_scenarios",
    }
    assert "Semacare" in report["items"][0]["product_description"]
    assert report["items"][0]["product_category"] == "心电诊断系统"
    assert report["scenario_items"][0]["scenario_name"] == "临床心电诊断"


def test_cli_checkpoints_each_requested_company_even_without_source_rows(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "source_url": "https://pitchhub.36kr.com/project/1678475362006017",
            "source_adapter": "pitchhub_36kr",
            "title": "旭宏医疗",
            "summary_clean": "项目简介：Semacare 专注创新心电系统开发，运用 AI 自动诊断技术支持临床。",
        }
    ]
    checkpoints: list[dict[str, object]] = []

    def mark_checkpoint(*_args, **kwargs):
        checkpoints.append(kwargs)

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(cli, "mark_company_stage_complete", mark_checkpoint)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--dry-run",
            "--source-adapter",
            "pitchhub_36kr",
            "--company-id",
            "COMP-1",
            "--company-id",
            "COMP-2",
            "--enrichment-batch-id",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "--checkpoint-stage",
            "source_product_extract",
        ]
    )

    json.loads(capsys.readouterr().out)
    by_company = {item["company_id"]: item for item in checkpoints}
    assert set(by_company) == {"COMP-1", "COMP-2"}
    assert by_company["COMP-1"]["status"] == "partial"
    assert by_company["COMP-1"]["counters"]["source_rows_processed"] == 1
    assert by_company["COMP-1"]["counters"]["product_count"] == 1
    assert by_company["COMP-2"]["status"] == "partial"
    assert by_company["COMP-2"]["miss_reason"] == "source_product_no_source_rows"
    assert by_company["COMP-2"]["counters"]["source_rows_processed"] == 0


def test_cli_uses_llm_structured_extract_when_rules_find_no_candidate(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "深圳示例科技有限公司",
            "source_url": "https://pitchhub.36kr.com/project/1",
            "source_adapter": "pitchhub_36kr",
            "title": "示例科技",
            "summary_clean": "示例科技发布 CorrectOS，用于工厂设备管理。",
        }
    ]

    class _FakeLLM:
        calls = 0

        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    _FakeLLM.calls += 1
                    message = MagicMock()
                    if _FakeLLM.calls == 1:
                        message.content = (
                            '{"products":[{"product_name":"CorrectOS",'
                            '"short_description":"面向工厂的设备管理平台。",'
                            '"product_category":"设备管理平台",'
                            '"target_customers":["工厂"],'
                            '"application_scenarios":["设备管理"],'
                            '"technical_tags":["IoT"],'
                            '"evidence_span":"CorrectOS 面向工厂的设备管理平台。"}],'
                            '"scenarios":[]}'
                        )
                    else:
                        message.content = (
                            '{"keep_products":["CorrectOS"],'
                            '"keep_scenarios":[],'
                            '"reason":"source explicitly attributes CorrectOS to 示例科技"}'
                        )
                    choice = MagicMock()
                    choice.message = message
                    response = MagicMock()
                    response.choices = [choice]
                    return response

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_open_llm_client",
        lambda: (_FakeLLM(), "deepseek-v4-pro", {"thinking": {"type": "disabled"}}),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--dry-run",
            "--limit",
            "1",
            "--source-adapter",
            "pitchhub_36kr",
            "--llm-structured-extract",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert [item["product_name"] for item in report["items"]] == ["CorrectOS"]
    assert report["llm_fallback_used"] == 1


def test_cli_rejects_third_party_candidate_when_product_belongs_to_other_company(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-QIDUO",
            "canonical_name": "奇朵智能设备",
            "source_url": "https://pitchhub.36kr.com/project/1958568104891398",
            "source_adapter": "pitchhub_36kr",
            "title": "奇朵智能设备 - PitchHub",
            "summary_clean": (
                "页面正文包含相似项目和平台推荐：Arabica Coffee 是咖啡供应链品牌，"
                "提供咖啡豆种植、贸易和烘焙服务。该段落没有说明 Arabica Coffee "
                "属于奇朵智能设备或由其提供。"
            ),
        }
    ]

    class _FakeLLM:
        calls = 0

        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    _FakeLLM.calls += 1
                    message = MagicMock()
                    if _FakeLLM.calls == 1:
                        message.content = (
                            '{"products":[{"product_name":"Arabica Coffee",'
                            '"short_description":"咖啡供应链品牌。",'
                            '"product_category":"咖啡饮品",'
                            '"target_customers":[],'
                            '"application_scenarios":[],'
                            '"technical_tags":["咖啡豆种植","咖啡烘焙"],'
                            '"evidence_span":"Arabica Coffee 是咖啡供应链品牌"}],'
                            '"scenarios":[]}'
                        )
                    else:
                        message.content = (
                            '{"keep_products":[],'
                            '"keep_scenarios":[],'
                            '"reason":"candidate belongs to another company, not 奇朵智能设备"}'
                        )
                    choice = MagicMock()
                    choice.message = message
                    response = MagicMock()
                    response.choices = [choice]
                    return response

    inserted: list[str] = []
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_open_llm_client",
        lambda: (_FakeLLM(), "deepseek-v4-pro", {"thinking": {"type": "disabled"}}),
    )
    monkeypatch.setattr(
        cli,
        "upsert_company_product",
        lambda *_args, **_kwargs: inserted.append("product") or "PROD-1",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--limit",
            "1",
            "--source-adapter",
            "pitchhub_36kr",
            "--llm-structured-extract",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["products_extracted"] == 0
    assert report["products_inserted"] == 0
    assert report["source_candidate_gate_rejected"] == 1
    assert report["source_adapter_counts"]["pitchhub_36kr"]["candidate_gate_rejected"] == 1
    assert report["rejected_candidate_reasons"] == {
        "candidate belongs to another company, not 奇朵智能设备": 1
    }
    assert report["rejected_candidates"] == [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-QIDUO",
            "source_adapter": "pitchhub_36kr",
            "source_url": "https://pitchhub.36kr.com/project/1958568104891398",
            "gate": "product_candidate_attribution_gate",
            "reason": "candidate belongs to another company, not 奇朵智能设备",
            "rejected_count": 1,
        }
    ]
    assert inserted == []
    assert _FakeLLM.calls == 2


def test_cli_requires_llm_confirmation_for_generic_web_products(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "深圳示例科技有限公司",
            "source_url": "https://example.com/news",
            "source_adapter": "generic_web",
            "title": "示例科技发布新闻",
            "summary_clean": "产品服务：NoiseBot智能巡检平台，面向工厂提供机器人巡检。",
        }
    ]

    class _FakeLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    message = MagicMock()
                    message.content = '{"products": [], "scenarios": []}'
                    choice = MagicMock()
                    choice.message = message
                    response = MagicMock()
                    response.choices = [choice]
                    return response

    inserted: list[str] = []
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_open_llm_client",
        lambda: (_FakeLLM(), "deepseek-v4-pro", {"thinking": {"type": "disabled"}}),
    )
    monkeypatch.setattr(
        cli,
        "upsert_company_product",
        lambda *_args, **_kwargs: inserted.append("product") or "PROD-1",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--limit",
            "1",
            "--source-adapter",
            "generic_web",
            "--llm-structured-extract",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["products_extracted"] == 0
    assert report["products_inserted"] == 0
    assert report["generic_web_product_gate_rejected"] == 1
    assert inserted == []


def test_cli_llm_gates_generic_registry_scope_before_product_extraction(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "深圳鼎讯智城科技有限公司",
            "source_url": "https://www.tianyancha.com/company/3450910951",
            "source_adapter": "generic_web",
            "title": "深圳鼎讯智城科技有限公司 - 天眼查",
            "summary_clean": (
                "深圳鼎讯智城科技有限公司经营范围包括云计算和大数据的开发与销售，"
                "企业信息化项目的设计、开发、建设、运营与维护。"
            ),
        }
    ]

    class _FakeLLM:
        calls: list[str] = []

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    _FakeLLM.calls.append(kwargs["messages"][1]["content"])
                    message = MagicMock()
                    message.content = (
                        '{"allow_product_extraction": false, '
                        '"reason": "工商注册经营范围，不是具体产品或解决方案材料"}'
                    )
                    choice = MagicMock()
                    choice.message = message
                    response = MagicMock()
                    response.choices = [choice]
                    return response

    inserted: list[str] = []
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_open_llm_client",
        lambda: (_FakeLLM(), "deepseek-v4-pro", {"thinking": {"type": "disabled"}}),
    )
    monkeypatch.setattr(
        cli,
        "upsert_company_product",
        lambda *_args, **_kwargs: inserted.append("product") or "PROD-1",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--limit",
            "1",
            "--source-adapter",
            "generic_web",
            "--llm-structured-extract",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["products_extracted"] == 0
    assert report["scenarios_extracted"] == 0
    assert report["generic_web_product_gate_rejected"] == 1
    assert report["source_adapter_counts"]["generic_web"]["product_gate_rejected"] == 1
    assert report["rejected_candidate_reasons"] == {
        "工商注册经营范围，不是具体产品或解决方案材料": 1
    }
    assert report["rejected_candidates"][0]["gate"] == "generic_product_source_gate"
    assert report["rejected_candidates"][0]["reason"] == (
        "工商注册经营范围，不是具体产品或解决方案材料"
    )
    assert inserted == []
    assert len(_FakeLLM.calls) == 1


def test_cli_allows_generic_named_product_page_after_llm_gate(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "深圳百威雷科技有限公司",
            "source_url": "https://www.powerarena.com/zh-hans/",
            "source_adapter": "generic_web",
            "title": "PowerArena HOP 人因作业平台",
            "summary_clean": (
                "PowerArena HOP 人因作业平台通过AI计算机视觉技术，为制造装配线"
                "提供可靠且公正的数据洞察，实现AI优化人因装配线。"
            ),
        }
    ]

    class _FakeLLM:
        calls = 0

        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    _FakeLLM.calls += 1
                    message = MagicMock()
                    if _FakeLLM.calls == 1:
                        message.content = (
                            '{"allow_product_extraction": true, '
                            '"reason": "source explicitly names a product platform"}'
                        )
                    elif _FakeLLM.calls == 2:
                        message.content = (
                            '{"products":[{"product_name":"PowerArena HOP 人因作业平台",'
                            '"short_description":"面向制造装配线的AI视觉分析平台。",'
                            '"product_category":"AI视觉分析平台",'
                            '"target_customers":["制造企业"],'
                            '"application_scenarios":["人因装配线优化"],'
                            '"technical_tags":["AI计算机视觉"],'
                            '"evidence_span":"PowerArena HOP 人因作业平台通过AI计算机视觉技术"}],'
                            '"scenarios":[]}'
                        )
                    else:
                        message.content = (
                            '{"keep_products":["PowerArena HOP 人因作业平台"],'
                            '"keep_scenarios":[],'
                            '"reason":"concrete named product platform"}'
                        )
                    choice = MagicMock()
                    choice.message = message
                    response = MagicMock()
                    response.choices = [choice]
                    return response

    inserted: list[str] = []
    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_open_llm_client",
        lambda: (_FakeLLM(), "deepseek-v4-pro", {"thinking": {"type": "disabled"}}),
    )
    monkeypatch.setattr(
        cli,
        "upsert_company_product",
        lambda *_args, **_kwargs: inserted.append("product") or "PROD-1",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--limit",
            "1",
            "--source-adapter",
            "generic_web",
            "--llm-structured-extract",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert [item["product_name"] for item in report["items"]] == [
        "PowerArena HOP 人因作业平台"
    ]
    assert report["llm_fallback_used"] == 1
    assert report["generic_web_product_gate_rejected"] == 0
    assert report["generic_web_candidate_gate_rejected"] == 0
    assert inserted == ["product"]
    assert _FakeLLM.calls == 3


def test_cli_skips_llm_product_fallback_for_strong_rule_candidate(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "深圳示例科技有限公司",
            "source_url": "https://example.com/product",
            "source_adapter": "generic_web",
            "title": "NoiseBot智能巡检平台",
            "summary_clean": "产品服务：NoiseBot智能巡检平台，面向工厂提供机器人巡检。",
        }
    ]

    class _FakeLLM:
        calls = 0

        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    _FakeLLM.calls += 1
                    message = MagicMock()
                    if _FakeLLM.calls == 1:
                        message.content = (
                            '{"allow_product_extraction": true, '
                            '"reason": "source explicitly names a product platform"}'
                        )
                    else:
                        message.content = (
                            '{"keep_products":["NoiseBot智能巡检平台"],'
                            '"keep_scenarios":["机器人巡检"],'
                            '"reason":"specific product and scenario"}'
                        )
                    choice = MagicMock()
                    choice.message = message
                    response = MagicMock()
                    response.choices = [choice]
                    return response

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_open_llm_client",
        lambda: (_FakeLLM(), "deepseek-v4-pro", {"thinking": {"type": "disabled"}}),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--dry-run",
            "--limit",
            "1",
            "--source-adapter",
            "generic_web",
            "--llm-structured-extract",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert [item["product_name"] for item in report["items"]] == ["NoiseBot智能巡检平台"]
    assert report["llm_fallback_used"] == 0
    assert report["generic_web_candidate_gate_rejected"] == 0
    assert _FakeLLM.calls == 2


def test_cli_rejects_generic_web_seo_title_product_candidate(
    monkeypatch,
    capsys,
):
    cli = _import_cli()
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        {
            "news_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "COMP-1",
            "canonical_name": "南科佳安机器人科技",
            "source_url": "https://kaanh.cn/",
            "source_adapter": "generic_web",
            "title": "佳安智能机器人【官网】-工业具身;移动机器人;核心部件",
            "summary_clean": (
                "佳安智能是一家专注于机器人智能磨抛工作站及核心部件研发、"
                "生产、销售的高新技术企业。"
            ),
        }
    ]

    class _FakeLLM:
        calls = 0

        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    _FakeLLM.calls += 1
                    message = MagicMock()
                    if _FakeLLM.calls == 1:
                        message.content = (
                            '{"allow_product_extraction": true, '
                            '"reason": "source mentions productized robotics offerings"}'
                        )
                    elif _FakeLLM.calls == 2:
                        message.content = (
                            '{"products":[{"product_name":"佳安智能机器人【官网】-工业具身;移动机器人;核心部件",'
                            '"short_description":"机器人企业官网标题。",'
                            '"product_category":"工业机器人",'
                            '"target_customers":["企业客户"],'
                            '"application_scenarios":[],'
                            '"technical_tags":["机器人"],'
                            '"evidence_span":"佳安智能是一家专注于机器人智能磨抛工作站及核心部件研发"}],'
                            '"scenarios":[]}'
                        )
                    else:
                        message.content = (
                            '{"keep_products":[],'
                            '"keep_scenarios":[],'
                            '"reason":"candidate is an SEO page title/company profile, not a product"}'
                        )
                    choice = MagicMock()
                    choice.message = message
                    response = MagicMock()
                    response.choices = [choice]
                    return response

    monkeypatch.setattr(cli, "_open_database_connection", lambda _url: conn)
    monkeypatch.setattr(
        cli,
        "_open_llm_client",
        lambda: (_FakeLLM(), "deepseek-v4-pro", {"thinking": {"type": "disabled"}}),
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/test")

    cli.main(
        [
            "--dry-run",
            "--limit",
            "1",
            "--source-adapter",
            "generic_web",
            "--llm-structured-extract",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["products_extracted"] == 0
    assert report["generic_web_candidate_gate_rejected"] >= 1
    assert _FakeLLM.calls >= 2


def test_insert_products_uses_upsert_writer(monkeypatch):
    cli = _import_cli()
    conn = MagicMock()
    product = CompanyProductCandidate(
        company_id="COMP-1",
        product_name="Semacare",
        short_description="AI心电智能筛查服务。",
        official_product_url="https://pitchhub.36kr.com/project/1",
        evidence_span="项目简介：AI心电智能筛查服务。",
        confidence="0.65",
    )
    inserted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        cli,
        "upsert_company_product",
        lambda _conn, _product, **kwargs: inserted.append((_product.product_name, kwargs)) or "PROD-1",
    )

    assert cli._insert_products(conn, [product], source_tier="generic_web") == 1
    assert inserted == [("Semacare", {"extractor_version": "source_product_extractor.v1", "source_tier": "generic_web"})]


def test_insert_application_scenarios_uses_upsert_writer(monkeypatch):
    cli = _import_cli()
    conn = MagicMock()
    scenario = CompanyApplicationScenarioCandidate(
        company_id="COMP-1",
        scenario_name="远程心电诊断",
        description="支持临床和远程心电诊断及监护。",
        source_url="https://pitchhub.36kr.com/project/1",
        evidence_span="项目简介：支持临床和远程心电诊断及监护。",
        confidence="0.65",
        related_product_name="Semacare",
    )
    inserted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        cli,
        "upsert_company_application_scenario",
        lambda _conn, _scenario, **kwargs: inserted.append((_scenario.scenario_name, kwargs)) or "SCEN-1",
    )

    assert (
        cli._insert_application_scenarios(
            conn,
            [scenario],
            source_tier="generic_web",
        )
        == 1
    )
    assert inserted == [("远程心电诊断", {"extractor_version": "source_product_extractor.v1", "source_tier": "generic_web"})]


def test_supported_source_url_rejects_pitchhub_organization_pages():
    cli = _import_cli()

    assert cli._is_supported_source_url("https://pitchhub.36kr.com/project/1") is True
    assert cli._is_supported_source_url("https://pitchhub.36kr.com/organization/1") is False


def test_supported_source_url_allows_generic_web_after_source_judgment():
    cli = _import_cli()

    assert (
        cli._is_supported_source_url(
            "https://example.com/company-report",
            source_adapter="generic_web",
        )
        is True
    )
    assert (
        cli._is_supported_source_url(
            "https://example.com/company-report",
            source_adapter="serper",
        )
        is False
    )
