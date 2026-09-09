from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import src.data_agents.company.source_product_extractor as mod

from src.data_agents.company.source_product_extractor import (
    CompanySourceMaterial,
    extract_application_scenarios_from_source_text,
    extract_products_and_scenarios_with_llm_fallback,
    extract_products_from_source_text,
    persist_synthesized_products_and_scenarios,
    synthesize_products_and_scenarios_from_xlsx,
)


def test_extract_products_from_pitchhub_project_intro_detects_named_brand():
    products = extract_products_from_source_text(
        company_id="COMP-SEM",
        company_name="深圳旭宏医疗科技有限公司",
        source_url="https://pitchhub.36kr.com/project/1678475362006017",
        title="旭宏医疗",
        body_text=(
            "项目简介\n"
            "Semacare 专注创新心电系统开发，运用 AI 自动诊断技术支持临床和远程心电诊断及监护。\n"
            "融资历史\n2024-01-01 天使轮。"
        ),
    )

    assert len(products) == 1
    product = products[0]
    assert product.company_id == "COMP-SEM"
    assert product.product_name == "Semacare"
    assert "AI 自动诊断" in product.short_description
    assert product.official_product_url == "https://pitchhub.36kr.com/project/1678475362006017"
    assert "项目简介" in product.evidence_span
    assert product.confidence == Decimal("0.65")
    assert product.quality_status == "needs_review"
    assert product.product_category == "心电诊断系统"
    assert product.target_customers == ("医院/临床机构",)
    assert product.application_scenarios == (
        "临床心电诊断",
        "远程心电诊断",
        "心电监护",
    )
    assert product.technical_tags == ("AI自动诊断", "心电系统")


def test_extract_products_from_source_text_detects_named_platform():
    products = extract_products_from_source_text(
        company_id="COMP-1",
        company_name="深圳示例机器人有限公司",
        source_url="https://data.iyiou.com/company/details/example/profile",
        title="示例机器人_亿欧数据",
        body_text="产品服务：ExampleBot智能巡检平台，面向工厂提供机器人巡检和设备监测能力。",
    )

    assert [product.product_name for product in products] == ["ExampleBot智能巡检平台"]
    assert "设备监测" in products[0].short_description
    assert products[0].target_customers == ("工厂",)
    assert products[0].application_scenarios == ("机器人巡检", "设备监测")


def test_extract_application_scenarios_from_source_text_structures_use_cases():
    scenarios = extract_application_scenarios_from_source_text(
        company_id="COMP-SEM",
        company_name="深圳旭宏医疗科技有限公司",
        source_url="https://pitchhub.36kr.com/project/1678475362006017",
        title="旭宏医疗",
        body_text=(
            "项目简介\n"
            "Semacare 专注创新心电系统开发，运用 AI 自动诊断技术支持临床和远程心电诊断及监护。"
        ),
    )

    assert [scenario.scenario_name for scenario in scenarios] == [
        "临床心电诊断",
        "远程心电诊断",
        "心电监护",
    ]
    assert {scenario.related_product_name for scenario in scenarios} == {"Semacare"}
    assert {scenario.target_customer for scenario in scenarios} == {"医院/临床机构"}
    assert all(scenario.source_url.startswith("https://pitchhub.36kr.com/") for scenario in scenarios)
    assert all(scenario.quality_status == "needs_review" for scenario in scenarios)


def test_extract_products_from_source_text_rejects_generic_company_intro():
    products = extract_products_from_source_text(
        company_id="COMP-1",
        company_name="深圳示例科技有限公司",
        source_url="https://data.iyiou.com/company/details/example/profile",
        title="深圳示例科技",
        body_text="公司简介：深圳示例科技有限公司成立于2020年，团队来自知名高校。",
    )

    assert products == []


def test_extract_products_from_short_source_profile_uses_title_when_product_hints_exist():
    products = extract_products_from_source_text(
        company_id="COMP-SEM",
        company_name="深圳旭宏医疗科技",
        source_url="https://pitchhub.36kr.com/project/1678475362006017",
        title="旭宏医疗 - PitchHub 项目页",
        body_text="Semacare 专注创新心电系统开发，运用 AI 自动诊断技术支持临床和远程心电诊断及监护。",
    )

    assert len(products) == 1
    assert products[0].product_name == "Semacare"
    assert "AI 自动诊断" in products[0].short_description


def test_extract_products_from_source_text_rejects_company_alias_and_description_phrase():
    products = extract_products_from_source_text(
        company_id="COMP-1",
        company_name="深圳示例传感器有限公司",
        source_url="https://data.iyiou.com/company/details/example/profile",
        title="示例传感器 - 亿欧数据企业画像",
        body_text=(
            "示例传感器是一家产品研发商，集智能传感器产品的研发、"
            "销售和技术服务于一体，专注自动化精密检测技术提供整套专业的检测解决方案。"
        ),
    )

    assert products == []


def test_extract_products_from_source_text_requires_local_product_signal():
    products = extract_products_from_source_text(
        company_id="COMP-1",
        company_name="昂视智能",
        source_url="https://data.iyiou.com/company/details/example/profile",
        title="昂视智能 - 亿欧数据企业画像",
        body_text=(
            "昂视智能专注于研发、生产高端工业机器视觉检测智能化系统及等自动化工业产品，"
            "提供机器视觉系统、3D激光测量、读码器、传感器等。"
        ),
    )

    assert [product.product_name for product in products] == ["机器视觉系统"]


def test_llm_fallback_extracts_structured_product_and_scenario_when_rules_miss():
    class _FakeLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    class _Message:
                        content = (
                            '{"products":[{"product_name":"CareLink",'
                            '"short_description":"用于院内慢病随访管理。",'
                            '"product_category":"慢病管理平台",'
                            '"target_customers":["医院"],'
                            '"application_scenarios":["院内慢病随访"],'
                            '"technical_tags":["AI随访"],'
                            '"evidence_span":"CareLink 用于院内慢病随访管理。"}],'
                            '"scenarios":[{"scenario_name":"院内慢病随访",'
                            '"description":"医院使用 CareLink 做患者随访。",'
                            '"target_customer":"医院",'
                            '"scenario_category":"医疗服务",'
                            '"related_product_name":"CareLink",'
                            '"evidence_span":"医院使用 CareLink 做患者随访。"}]}'
                        )

                    class _Choice:
                        message = _Message()

                    class _Response:
                        choices = [_Choice()]

                    return _Response()

    products, scenarios = extract_products_and_scenarios_with_llm_fallback(
        company_id="COMP-1",
        company_name="深圳示例医疗科技有限公司",
        source_url="https://data.iyiou.com/company/details/example/profile",
        title="示例医疗",
        body_text="公司业务包含 CareLink，用于院内慢病随访管理。",
        existing_products=[],
        existing_scenarios=[],
        llm_client=_FakeLLM(),
        llm_model="gemma",
    )

    assert [product.product_name for product in products] == ["CareLink"]
    assert products[0].product_category == "慢病管理平台"
    assert products[0].target_customers == ("医院",)
    assert products[0].application_scenarios == ("院内慢病随访",)
    assert products[0].technical_tags == ("AI随访",)
    assert products[0].quality_status == "needs_review"
    assert [scenario.scenario_name for scenario in scenarios] == ["院内慢病随访"]
    assert scenarios[0].related_product_name == "CareLink"


def test_llm_fallback_derives_scenario_rows_from_product_application_scenarios():
    class _FakeLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    class _Message:
                        content = (
                            '{"products":[{"product_name":"Pliabot柔韧技术",'
                            '"short_description":"为各行各业打造软体机器人产品与解决方案。",'
                            '"product_category":"软体机器人技术",'
                            '"target_customers":["工业企业"],'
                            '"application_scenarios":["艰险繁复作业替代","机器人普及应用突破"],'
                            '"technical_tags":["软体机器人"],'
                            '"evidence_span":"Pliabot柔韧技术为各行各业打造机器人产品与解决方案。"}],'
                            '"scenarios":[]}'
                        )

                    class _Choice:
                        message = _Message()

                    class _Response:
                        choices = [_Choice()]

                    return _Response()

    products, scenarios = extract_products_and_scenarios_with_llm_fallback(
        company_id="COMP-SOFT",
        company_name="万勋科技",
        source_url="xlsx://company/COMP-SOFT",
        title="万勋科技",
        body_text="Pliabot柔韧技术为各行各业打造机器人产品与解决方案。",
        existing_products=[],
        existing_scenarios=[],
        llm_client=_FakeLLM(),
        llm_model="deepseek-v4-pro",
    )

    assert [product.product_name for product in products] == ["Pliabot柔韧技术"]
    assert [scenario.scenario_name for scenario in scenarios] == [
        "艰险繁复作业替代",
        "机器人普及应用突破",
    ]
    assert scenarios[0].related_product_name == "Pliabot柔韧技术"
    assert scenarios[0].target_customer == "工业企业"


def test_xlsx_synthesis_uses_description_business_and_project_as_source_material():
    class _FakeLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    assert "XLSX" in kwargs["messages"][1]["content"]
                    assert "CardioAI" in kwargs["messages"][1]["content"]

                    class _Message:
                        content = (
                            '{"products":[{"product_name":"CardioAI心电平台",'
                            '"short_description":"面向医院的AI心电辅助诊断平台。",'
                            '"product_category":"心电诊断平台",'
                            '"target_customers":["医院"],'
                            '"application_scenarios":["临床心电诊断"],'
                            '"technical_tags":["AI心电分析"],'
                            '"evidence_span":"CardioAI心电平台面向医院提供AI心电辅助诊断。"}],'
                            '"scenarios":[{"scenario_name":"临床心电诊断",'
                            '"description":"医生使用平台进行心电辅助诊断。",'
                            '"target_customer":"医院",'
                            '"scenario_category":"医疗诊断",'
                            '"related_product_name":"CardioAI心电平台",'
                            '"evidence_span":"面向医院提供AI心电辅助诊断。"}]}'
                        )

                    class _Choice:
                        message = _Message()

                    class _Response:
                        choices = [_Choice()]

                    return _Response()

    products, scenarios = synthesize_products_and_scenarios_from_xlsx(
        company_id="COMP-XLSX",
        company_name="深圳示例医疗科技有限公司",
        project_name="CardioAI",
        description="CardioAI心电平台面向医院提供AI心电辅助诊断。",
        business="AI心电分析与临床辅助诊断服务。",
        team_raw="张三，职务：创始人，介绍：长期从事心电算法研发。",
        llm_client=_FakeLLM(),
        llm_model="deepseek-v4-flash",
    )

    assert [product.product_name for product in products] == ["CardioAI心电平台"]
    assert products[0].official_product_url == "xlsx://company/COMP-XLSX"
    assert products[0].product_category == "心电诊断平台"
    assert products[0].target_customers == ("医院",)
    assert products[0].application_scenarios == ("临床心电诊断",)
    assert products[0].technical_tags == ("AI心电分析",)
    assert [scenario.scenario_name for scenario in scenarios] == ["临床心电诊断"]
    assert scenarios[0].source_url == "xlsx://company/COMP-XLSX"


def test_xlsx_synthesis_uses_explicit_product_and_scenario_columns():
    class _FakeLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    prompt = kwargs["messages"][1]["content"]
                    assert "产品简介: 示例机器人平台用于工厂巡检。" in prompt
                    assert "产品特点: 具备机器视觉和自主导航能力。" in prompt
                    assert "应用场景: 工业园区巡检、设备监测" in prompt

                    class _Message:
                        content = (
                            '{"products":[{"product_name":"示例机器人平台",'
                            '"short_description":"用于工厂巡检的机器人平台。",'
                            '"product_category":"巡检机器人平台",'
                            '"target_customers":["工厂"],'
                            '"application_scenarios":["工业园区巡检","设备监测"],'
                            '"technical_tags":["机器视觉","自主导航"],'
                            '"evidence_span":"示例机器人平台用于工厂巡检，具备机器视觉和自主导航能力。"}],'
                            '"scenarios":[{"scenario_name":"工业园区巡检",'
                            '"description":"用于工业园区巡检。",'
                            '"target_customer":"工厂",'
                            '"scenario_category":"工业巡检",'
                            '"related_product_name":"示例机器人平台",'
                            '"evidence_span":"应用场景: 工业园区巡检"}]}'
                        )

                    class _Choice:
                        message = _Message()

                    class _Response:
                        choices = [_Choice()]

                    return _Response()

    products, scenarios = synthesize_products_and_scenarios_from_xlsx(
        company_id="COMP-XLSX",
        company_name="深圳示例机器人有限公司",
        project_name="示例机器人",
        industry="机器人",
        business="工业巡检机器人研发商",
        product_intro="示例机器人平台用于工厂巡检。",
        product_features="具备机器视觉和自主导航能力。",
        application_scenarios_raw="工业园区巡检、设备监测",
        llm_client=_FakeLLM(),
        llm_model="deepseek-v4-pro",
    )

    assert [product.product_name for product in products] == ["示例机器人平台"]
    assert products[0].application_scenarios == ("工业园区巡检", "设备监测")
    assert [scenario.scenario_name for scenario in scenarios] == ["工业园区巡检", "设备监测"]


def test_xlsx_synthesis_does_not_invent_target_customers_from_industry_only():
    products, scenarios = synthesize_products_and_scenarios_from_xlsx(
        company_id="COMP-XLSX",
        company_name="深圳示例医疗科技有限公司",
        industry="医疗AI",
        llm_client=None,
        llm_model="deepseek-v4-flash",
    )

    assert products == []
    assert scenarios == []


def test_xlsx_synthesis_does_not_treat_source_marker_as_product_name():
    products, _scenarios = synthesize_products_and_scenarios_from_xlsx(
        company_id="COMP-XLSX",
        company_name="深圳示例医疗科技有限公司",
        description="专注 AI 心电诊断平台。" * 3,
        business="AI 心电诊断平台",
        team_raw="张三，长期从事心电算法研发。",
        llm_client=None,
        llm_model="deepseek-v4-flash",
    )

    assert all(
        product.product_name not in {"Source", "XLSX trusted baseline"}
        for product in products
    )


def test_xlsx_service_product_uses_llm_fallback_for_onegu_style_baseline():
    class _FakeLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    assert kwargs["model"] == "deepseek-v4-pro"
                    assert "友心" in kwargs["messages"][1]["content"]
                    assert "积分商城" in kwargs["messages"][1]["content"]

                    class _Message:
                        content = (
                            '{"products":[{"product_name":"友心",'
                            '"short_description":"专注提升用户粘性的积分商城服务，覆盖高端商品定制、红包体系、线上支付、CRM信息化管理、数据挖掘、采购供应链、协同管理及实体货架陈列。",'
                            '"product_category":"积分商城服务",'
                            '"target_customers":["企业客户"],'
                            '"application_scenarios":["用户积分兑换","会员权益运营","营销活动奖励兑换"],'
                            '"technical_tags":["积分商城","CRM","数据挖掘","供应链管理"],'
                            '"evidence_span":"友心是深圳市一股科技有限公司精心打造、专注提升用户粘性的积分积分商城。"}],'
                            '"scenarios":[{"scenario_name":"用户积分兑换",'
                            '"description":"企业客户通过友心积分商城提升用户粘性。",'
                            '"target_customer":"企业客户",'
                            '"scenario_category":"会员运营",'
                            '"related_product_name":"友心",'
                            '"evidence_span":"专注提升用户粘性的积分积分商城"}]}'
                        )

                    class _Choice:
                        message = _Message()

                    class _Response:
                        choices = [_Choice()]

                    return _Response()

    products, scenarios = synthesize_products_and_scenarios_from_xlsx(
        company_id="COMP-17d68ddf7fd6",
        company_name="一股科技",
        project_name="一股科技",
        industry="电子商务",
        description=(
            "友心是深圳市一股科技有限公司精心打造、专注提升用户粘性的积分积分商城。"
            "区别于传统低价值感的积分模块，致力于高端商品定制、红包体系搭建、"
            "线上支付、CRM信息化管理、数据挖掘、采购供应链、协同管理及实体货架陈列等多元服务体系建设。"
        ),
        business="积分商城服务商",
        team_raw="李林，职务：执行董事&总经理，介绍：李林，友心执行董事&总经理。",
        llm_client=_FakeLLM(),
        llm_model="deepseek-v4-pro",
    )

    assert [product.product_name for product in products] == ["友心"]
    assert products[0].product_category == "积分商城服务"
    assert products[0].target_customers == ("企业客户",)
    assert "CRM" in products[0].technical_tags
    assert [scenario.scenario_name for scenario in scenarios] == [
        "用户积分兑换",
        "会员权益运营",
        "营销活动奖励兑换",
    ]


def test_llm_fallback_records_provider_or_parse_failure_diagnostics():
    class _FailingLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    raise RuntimeError("provider rejected model")

    diagnostics: dict[str, object] = {}

    products, scenarios = extract_products_and_scenarios_with_llm_fallback(
        company_id="COMP-XLSX",
        company_name="一股科技",
        source_url="xlsx://company/COMP-XLSX",
        title="一股科技",
        body_text="友心是专注提升用户粘性的积分商城服务。",
        existing_products=[],
        existing_scenarios=[],
        llm_client=_FailingLLM(),
        llm_model="deepseek-v4-lite",
        diagnostics=diagnostics,
    )

    assert products == []
    assert scenarios == []
    assert diagnostics["llm_fallback_error"] == "provider rejected model"


def test_llm_fallback_uses_large_output_budget_and_records_parse_diagnostics():
    captured: dict[str, object] = {}

    class _MalformedLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)

                    class _Message:
                        content = '{"products": [{"product_name": "智能制造专业建设服务"'

                    class _Choice:
                        message = _Message()
                        finish_reason = "length"

                    class _Response:
                        choices = [_Choice()]

                    return _Response()

    diagnostics: dict[str, object] = {}

    products, scenarios = extract_products_and_scenarios_with_llm_fallback(
        company_id="COMP-XLSX",
        company_name="示例科技",
        source_url="xlsx://company/COMP-XLSX",
        title="示例科技",
        body_text="提供智能制造领域的专业建设解决方案，面向职业院校。",
        existing_products=[],
        existing_scenarios=[],
        llm_client=_MalformedLLM(),
        llm_model="deepseek-v4-pro",
        diagnostics=diagnostics,
    )

    assert products == []
    assert scenarios == []
    assert captured["max_tokens"] >= 4096
    assert diagnostics["llm_fallback_error"] == "json_parse_failed"
    assert diagnostics["llm_fallback_finish_reason"] == "length"
    assert diagnostics["llm_fallback_raw_length"] > 0


def test_llm_fallback_prompt_accepts_service_solution_and_core_technology_offerings():
    captured: dict[str, object] = {}

    class _PromptCapturingLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured.update(kwargs)

                    class _Message:
                        content = '{"products": [], "scenarios": []}'

                    class _Choice:
                        message = _Message()
                        finish_reason = "stop"

                    class _Response:
                        choices = [_Choice()]

                    return _Response()

    extract_products_and_scenarios_with_llm_fallback(
        company_id="COMP-SOFT",
        company_name="万勋科技",
        source_url="xlsx://company/COMP-SOFT",
        title="万勋科技",
        body_text="Pliabot柔韧技术为各行各业打造安全、灵巧、轻盈、可负担的机器人产品与解决方案。",
        existing_products=[],
        existing_scenarios=[],
        llm_client=_PromptCapturingLLM(),
        llm_model="deepseek-v4-pro",
    )

    user_prompt = captured["messages"][1]["content"]
    assert "services, solutions, platforms, technical systems" in user_prompt
    assert "core technology offerings" in user_prompt
    assert "never use the company name alone as a product" in user_prompt


def test_source_material_model_preserves_tier_url_text_and_trust_reason():
    material = CompanySourceMaterial(
        source_id="xlsx:COMP-1",
        source_tier="xlsx",
        url="xlsx://company/COMP-1",
        title="XLSX baseline",
        captured_text="CardioAI心电平台面向医院提供AI心电辅助诊断。",
        captured_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        trust_reason="trusted_operator_xlsx",
    )

    assert material.source_tier == "xlsx"
    assert material.url == "xlsx://company/COMP-1"
    assert "CardioAI" in material.captured_text
    assert material.trust_reason == "trusted_operator_xlsx"


def test_persist_synthesized_products_and_scenarios_uses_upsert_paths_and_quality_gate(
    monkeypatch,
):
    product = mod.CompanyProductCandidate(
        company_id="COMP-XLSX",
        product_name="CardioAI心电平台",
        short_description="面向医院的AI心电辅助诊断平台。",
        official_product_url="xlsx://company/COMP-XLSX",
        evidence_span="CardioAI心电平台面向医院提供AI心电辅助诊断。",
        confidence=Decimal("0.82"),
        quality_status="needs_review",
        product_category="心电诊断平台",
        target_customers=("医院",),
        application_scenarios=("临床心电诊断",),
        technical_tags=("AI心电分析",),
    )
    scenario = mod.CompanyApplicationScenarioCandidate(
        company_id="COMP-XLSX",
        scenario_name="临床心电诊断",
        description="医生使用平台进行心电辅助诊断。",
        source_url="xlsx://company/COMP-XLSX",
        evidence_span="面向医院提供AI心电辅助诊断。",
        confidence=Decimal("0.80"),
        quality_status="needs_review",
        scenario_category="医疗诊断",
        target_customer="医院",
        related_product_name="CardioAI心电平台",
    )
    inserted_products = []
    inserted_scenarios = []
    monkeypatch.setattr(
        mod,
        "upsert_company_product",
        lambda _conn, item, **kwargs: inserted_products.append((item, kwargs)) or "PROD-1",
    )
    monkeypatch.setattr(
        mod,
        "upsert_company_application_scenario",
        lambda _conn, item, **kwargs: inserted_scenarios.append((item, kwargs)) or "SCEN-1",
    )

    report = persist_synthesized_products_and_scenarios(
        object(),
        products=[product],
        scenarios=[scenario],
        source_materials=[
            CompanySourceMaterial(
                source_id="xlsx:COMP-XLSX",
                source_tier="xlsx",
                url="xlsx://company/COMP-XLSX",
                title="XLSX baseline",
                captured_text="CardioAI心电平台面向医院提供AI心电辅助诊断。",
                trust_reason="trusted_operator_xlsx",
            )
        ],
    )

    assert report == {"products_inserted": 1, "scenarios_inserted": 1}
    assert inserted_products[0][0].quality_status == "ready"
    assert inserted_products[0][1]["source_tier"] == "xlsx"
    assert inserted_scenarios[0][0].quality_status == "ready"
    assert inserted_scenarios[0][1]["source_tier"] == "xlsx"


def test_xlsx_product_with_explicit_description_can_publish_without_all_optional_fields(
    monkeypatch,
):
    product = mod.CompanyProductCandidate(
        company_id="COMP-XLSX",
        product_name="CardioAI心电平台",
        short_description="面向医院的AI心电辅助诊断平台。",
        official_product_url="xlsx://company/COMP-XLSX",
        evidence_span="CardioAI心电平台面向医院提供AI心电辅助诊断。",
        confidence=Decimal("0.82"),
        quality_status="needs_review",
        product_category=None,
        target_customers=(),
        application_scenarios=(),
        technical_tags=("AI心电分析",),
    )
    inserted_products = []
    monkeypatch.setattr(
        mod,
        "upsert_company_product",
        lambda _conn, item, **kwargs: inserted_products.append((item, kwargs)) or "PROD-1",
    )

    persist_synthesized_products_and_scenarios(
        object(),
        products=[product],
        scenarios=[],
        source_materials=[
            CompanySourceMaterial(
                source_id="xlsx:COMP-XLSX",
                source_tier="xlsx",
                url="xlsx://company/COMP-XLSX",
                title="XLSX baseline",
                captured_text="CardioAI心电平台面向医院提供AI心电辅助诊断。",
                trust_reason="trusted_operator_xlsx",
            )
        ],
    )

    assert inserted_products[0][0].quality_status == "ready"
    assert inserted_products[0][1]["source_tier"] == "xlsx"


def test_generic_web_only_products_remain_review_gated_without_strong_judgment(
    monkeypatch,
):
    product = mod.CompanyProductCandidate(
        company_id="COMP-GEN",
        product_name="GenericAI平台",
        short_description="面向企业客户的AI分析平台。",
        official_product_url="https://example.com/article",
        evidence_span="GenericAI平台面向企业客户提供AI分析。",
        confidence=Decimal("0.88"),
        quality_status="needs_review",
        product_category="AI分析平台",
        target_customers=("企业客户",),
        application_scenarios=("企业分析",),
        technical_tags=("AI分析",),
    )
    inserted_products = []
    monkeypatch.setattr(
        mod,
        "upsert_company_product",
        lambda _conn, item, **kwargs: inserted_products.append((item, kwargs)) or "PROD-1",
    )

    persist_synthesized_products_and_scenarios(
        object(),
        products=[product],
        scenarios=[],
        source_materials=[
            CompanySourceMaterial(
                source_id="generic:https://example.com/article",
                source_tier="generic_web",
                url="https://example.com/article",
                title="Generic article",
                captured_text="GenericAI平台面向企业客户提供AI分析。",
                trust_reason="identity_confirmed_but_fact_attribution_medium",
            )
        ],
    )

    assert inserted_products[0][0].quality_status == "needs_review"
    assert inserted_products[0][1]["source_tier"] == "generic_web"


def test_generic_web_products_require_accepted_source_judgment_before_ready(
    monkeypatch,
):
    product = mod.CompanyProductCandidate(
        company_id="COMP-GEN",
        product_name="GenericAI平台",
        short_description="面向企业客户的AI分析平台。",
        official_product_url="https://example.com/article",
        evidence_span="GenericAI平台面向企业客户提供AI分析。",
        confidence=Decimal("0.91"),
        quality_status="needs_review",
        product_category="AI分析平台",
        target_customers=("企业客户",),
        application_scenarios=("企业分析",),
        technical_tags=("AI分析",),
    )
    inserted_products = []
    monkeypatch.setattr(
        mod,
        "upsert_company_product",
        lambda _conn, item, **kwargs: inserted_products.append((item, kwargs)) or "PROD-1",
    )

    persist_synthesized_products_and_scenarios(
        object(),
        products=[product],
        scenarios=[],
        source_materials=[
            CompanySourceMaterial(
                source_id="generic:https://example.com/article",
                source_tier="generic_web",
                url="https://example.com/article",
                title="Generic article",
                captured_text="GenericAI平台面向企业客户提供AI分析。",
                trust_reason="strong identity and fact attribution evidence",
                source_judgment_confidence=Decimal("0.95"),
            )
        ],
    )

    assert inserted_products[0][0].quality_status == "needs_review"


def test_generic_web_products_can_be_ready_with_accepted_strong_judgment(
    monkeypatch,
):
    product = mod.CompanyProductCandidate(
        company_id="COMP-GEN",
        product_name="GenericAI平台",
        short_description="面向企业客户的AI分析平台。",
        official_product_url="https://example.com/article",
        evidence_span="GenericAI平台面向企业客户提供AI分析。",
        confidence=Decimal("0.91"),
        quality_status="needs_review",
        product_category="AI分析平台",
        target_customers=("企业客户",),
        application_scenarios=("企业分析",),
        technical_tags=("AI分析",),
    )
    inserted_products = []
    monkeypatch.setattr(
        mod,
        "upsert_company_product",
        lambda _conn, item, **kwargs: inserted_products.append((item, kwargs)) or "PROD-1",
    )

    persist_synthesized_products_and_scenarios(
        object(),
        products=[product],
        scenarios=[],
        source_materials=[
            CompanySourceMaterial(
                source_id="generic:https://example.com/article",
                source_tier="generic_web",
                url="https://example.com/article",
                title="Generic article",
                captured_text="GenericAI平台面向企业客户提供AI分析。",
                trust_reason="strong identity and fact attribution evidence",
                source_judgment_status="accepted",
                source_judgment_confidence=Decimal("0.95"),
            )
        ],
    )

    assert inserted_products[0][0].quality_status == "ready"
