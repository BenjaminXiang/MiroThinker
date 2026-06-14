from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import UUID

from src.data_agents.company.narrative_enrichment import NarrativeResult
from src.data_agents.company.official_product_capture import (
    CompanyApplicationScenarioCandidate,
    CompanyProductCandidate,
)
from src.data_agents.company.team_parser import StructuredTeamMember


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_company_xlsx_team_synthesis.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_xlsx_team_synthesis", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_args_accepts_company_and_batch_scope():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--company-id",
            "COMP-1",
            "--enrichment-batch-id",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "--dry-run",
            "--include-source-materials",
            "--skip-team",
            "--skip-narrative",
            "--concurrency",
            "3",
            "--llm-timeout-seconds",
            "45",
            "--llm-retry-budget",
            "1",
            "--checkpoint-stage",
            "xlsx_team_synthesis",
        ]
    )

    assert args.company_id == ["COMP-1"]
    assert args.enrichment_batch_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert args.dry_run is True
    assert args.include_source_materials is True
    assert args.skip_team is True
    assert args.skip_narrative is True
    assert args.concurrency == 3
    assert args.llm_timeout_seconds == 45
    assert args.llm_retry_budget == 1
    assert args.checkpoint_stage == "xlsx_team_synthesis"


def test_open_llm_client_uses_company_task_routing(monkeypatch):
    cli = _import_cli()
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured["openai_kwargs"] = kwargs

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    monkeypatch.setattr(
        cli,
        "resolve_professor_llm_settings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("company xlsx synthesis must not use professor resolver")
        ),
        raising=False,
    )

    def _fake_resolve(task_type, *, timeout_seconds=None, retry_budget=None):
        captured["task_type"] = task_type
        captured["timeout_seconds"] = timeout_seconds
        captured["retry_budget"] = retry_budget
        return SimpleNamespace(
            base_url="https://api.deepseek.com",
            api_key="fake-key",
            model="deepseek-v4-lite",
            extra_body={"thinking": {"type": "disabled"}},
            timeout_seconds=12.0,
            retry_budget=1,
        )

    monkeypatch.setattr(
        cli,
        "resolve_company_llm_task_settings",
        _fake_resolve,
        raising=False,
    )
    monkeypatch.setattr(cli, "wrap_openai_client", lambda client, provider_key: client, raising=False)

    _client, model, extra_body = cli._open_llm_client(
        "trusted_xlsx_structuring",
        timeout_seconds=12.0,
        retry_budget=1,
    )

    assert captured["task_type"] == "trusted_xlsx_structuring"
    assert captured["timeout_seconds"] == 12.0
    assert captured["retry_budget"] == 1
    assert model == "deepseek-v4-lite"
    assert extra_body == {"thinking": {"type": "disabled"}}
    openai_kwargs = captured["openai_kwargs"]
    assert openai_kwargs["timeout"] == 12.0
    assert openai_kwargs["max_retries"] == 1


def test_process_company_generates_narrative_and_structures_team(monkeypatch):
    cli = _import_cli()
    persisted: list[str] = []

    monkeypatch.setattr(
        cli,
        "generate_company_narrative",
        lambda **_kwargs: NarrativeResult(
            profile_summary="长公司简介" * 80,
            technology_route_summary="技术路线" * 80,
            error=None,
        ),
    )
    monkeypatch.setattr(
        cli,
        "structure_team_raw_with_llm",
        lambda *_args, **_kwargs: [
            StructuredTeamMember(
                name="张三",
                role="创始人",
                background="长期从事心电算法研发。",
                experience_highlights=("心电算法研发",),
                relevance="负责产品研发",
                confidence=0.82,
                evidence_span="张三",
                raw_text="张三，职务：创始人，介绍：长期从事心电算法研发。",
            )
        ],
    )
    monkeypatch.setattr(
        cli,
        "_persist_narrative",
        lambda *_args, **kwargs: persisted.append(kwargs["company_id"]),
    )
    monkeypatch.setattr(
        cli,
        "persist_structured_team_members",
        lambda *_args, **_kwargs: 1,
    )

    report = cli._process_company(
        conn=SimpleNamespace(),
        row={
            "company_id": "COMP-1",
            "snapshot_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "industry": "医疗AI",
            "hq_city": "深圳",
            "description": "专注 AI 心电诊断平台。" * 10,
            "business": "AI 心电诊断平台",
            "team_raw": "张三，职务：创始人，介绍：长期从事心电算法研发。",
        },
        llm_client=SimpleNamespace(),
        llm_model="deepseek-v4-pro",
        extra_body={"thinking": {"type": "disabled"}},
        dry_run=False,
        run_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
    )

    assert report["narratives_written"] == 1
    assert report["team_members_written"] == 1
    assert persisted == ["COMP-1"]


def test_process_company_passes_products_and_source_materials_to_narrative(monkeypatch):
    cli = _import_cli()
    captured: dict[str, object] = {}

    def generate(**kwargs):
        captured.update(kwargs)
        return NarrativeResult(
            profile_summary="长公司简介" * 80,
            technology_route_summary="技术路线" * 80,
            error=None,
        )

    monkeypatch.setattr(cli, "generate_company_narrative", generate)
    monkeypatch.setattr(cli, "structure_team_raw_with_llm", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "_persist_narrative", lambda *_args, **_kwargs: None)

    report = cli._process_company(
        conn=SimpleNamespace(),
        row={
            "company_id": "COMP-1",
            "snapshot_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "industry": "医疗AI",
            "hq_city": "深圳",
            "description": "专注 AI 心电诊断平台。" * 10,
            "business": "AI 心电诊断平台",
            "team_raw": "张三，创始人。",
            "products_json": [
                {
                    "name": "Semacare",
                    "description": "AI 心电诊断系统。",
                    "target_customers": ["医院/临床机构"],
                }
            ],
            "source_materials_json": [
                {
                    "source_tier": "official_site",
                    "url": "https://example.com/product",
                    "title": "产品中心",
                    "captured_text": "Semacare 服务远程心电诊断场景。",
                }
            ],
        },
        llm_client=SimpleNamespace(),
        llm_model="deepseek-v4-pro",
        extra_body={"thinking": {"type": "disabled"}},
        dry_run=False,
        run_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        include_source_materials=True,
        skip_team=True,
    )

    assert report["narratives_written"] == 1
    assert report["team_members_extracted"] == 0
    assert captured["products"][0]["name"] == "Semacare"
    assert captured["source_materials"][0]["source_tier"] == "official_site"


def test_process_company_can_skip_narrative_and_only_structure_team(monkeypatch):
    cli = _import_cli()
    generate_calls = []

    monkeypatch.setattr(
        cli,
        "generate_company_narrative",
        lambda **_kwargs: generate_calls.append(_kwargs)
        or NarrativeResult(profile_summary="", technology_route_summary="", error=None),
    )
    monkeypatch.setattr(
        cli,
        "structure_team_raw_with_llm",
        lambda *_args, **_kwargs: [
            StructuredTeamMember(
                name="张三",
                role="创始人",
                background="长期从事心电算法研发。",
                experience_highlights=("心电算法研发",),
                relevance="负责产品研发",
                confidence=0.82,
                evidence_span="张三",
                raw_text="张三，创始人。",
            )
        ],
    )
    monkeypatch.setattr(
        cli,
        "persist_structured_team_members",
        lambda *_args, **_kwargs: 1,
    )

    report = cli._process_company(
        conn=SimpleNamespace(),
        row={
            "company_id": "COMP-1",
            "snapshot_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "industry": "医疗AI",
            "hq_city": "深圳",
            "description": "专注 AI 心电诊断平台。" * 10,
            "business": "AI 心电诊断平台",
            "team_raw": "张三，创始人。",
        },
        llm_client=SimpleNamespace(),
        llm_model="deepseek-v4-pro",
        extra_body={"thinking": {"type": "disabled"}},
        dry_run=False,
        run_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        skip_narrative=True,
    )

    assert report["narratives_written"] == 0
    assert report["narratives_rejected"] == 0
    assert report["team_members_written"] == 1
    assert generate_calls == []


def test_process_company_synthesizes_publishable_products_from_xlsx(monkeypatch):
    cli = _import_cli()
    persisted: dict[str, object] = {}

    monkeypatch.setattr(cli, "generate_company_narrative", lambda **_kwargs: NarrativeResult("", "", None))
    monkeypatch.setattr(cli, "structure_team_raw_with_llm", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        cli,
        "synthesize_products_and_scenarios_from_xlsx",
        lambda **_kwargs: (
            [
                CompanyProductCandidate(
                    company_id="COMP-1",
                    product_name="Semacare AI心电诊断平台",
                    short_description="面向医院和临床机构的AI心电诊断平台。",
                    official_product_url="xlsx://company/COMP-1",
                    evidence_span="Semacare AI心电诊断平台服务医院和临床心电诊断。",
                    confidence=0.9,
                    product_category="医疗AI诊断平台",
                    target_customers=("医院/临床机构",),
                    application_scenarios=("临床心电诊断",),
                    technical_tags=("AI心电诊断",),
                )
            ],
            [
                CompanyApplicationScenarioCandidate(
                    company_id="COMP-1",
                    scenario_name="临床心电诊断",
                    description="医院使用AI心电诊断平台辅助心电图分析。",
                    source_url="xlsx://company/COMP-1",
                    evidence_span="服务医院和临床心电诊断。",
                    confidence=0.9,
                    scenario_category="医疗诊断",
                    target_customer="医院/临床机构",
                    related_product_name="Semacare AI心电诊断平台",
                )
            ],
        ),
        raising=False,
    )

    def persist(**kwargs):
        persisted.update(kwargs)
        return {"products_inserted": len(kwargs["products"]), "scenarios_inserted": len(kwargs["scenarios"])}

    monkeypatch.setattr(cli, "persist_synthesized_products_and_scenarios", persist, raising=False)

    report = cli._process_company(
        conn=SimpleNamespace(),
        row={
            "company_id": "COMP-1",
            "snapshot_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "industry": "医疗AI",
            "hq_city": "深圳",
            "description": "Semacare AI心电诊断平台服务医院和临床心电诊断。",
            "business": "AI心电诊断平台",
            "team_raw": "",
        },
        llm_client=SimpleNamespace(),
        llm_model="deepseek-v4-pro",
        extra_body={"thinking": {"type": "disabled"}},
        dry_run=False,
        run_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        skip_narrative=True,
        skip_team=True,
    )

    assert report["products_synthesized"] == 1
    assert report["products_with_target_customers"] == 1
    assert report["scenarios_synthesized"] == 1
    assert report["products_written"] == 1
    assert report["scenarios_written"] == 1
    assert persisted["source_materials"][0].source_tier == "xlsx"


def test_process_company_runs_xlsx_product_synthesis_in_post_collection_stage(monkeypatch):
    cli = _import_cli()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "generate_company_narrative",
        lambda **_kwargs: NarrativeResult(
            profile_summary="长公司简介" * 80,
            technology_route_summary="技术路线" * 80,
            error=None,
        ),
    )
    monkeypatch.setattr(cli, "structure_team_raw_with_llm", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "_persist_narrative", lambda *_args, **_kwargs: None)

    def synthesize(**kwargs):
        captured.update(kwargs)
        return (
            [
                CompanyProductCandidate(
                    company_id="COMP-17d68ddf7fd6",
                    product_name="友心",
                    short_description="专注提升用户粘性的积分商城服务。",
                    official_product_url="xlsx://company/COMP-17d68ddf7fd6",
                    evidence_span="友心是深圳市一股科技有限公司精心打造、专注提升用户粘性的积分积分商城。",
                    confidence=0.9,
                    product_category="积分商城服务",
                    target_customers=("企业客户",),
                    application_scenarios=("用户积分兑换",),
                    technical_tags=("积分商城", "CRM"),
                )
            ],
            [
                CompanyApplicationScenarioCandidate(
                    company_id="COMP-17d68ddf7fd6",
                    scenario_name="用户积分兑换",
                    description="企业客户通过友心积分商城提升用户粘性。",
                    source_url="xlsx://company/COMP-17d68ddf7fd6",
                    evidence_span="专注提升用户粘性的积分积分商城。",
                    confidence=0.9,
                    scenario_category="会员运营",
                    target_customer="企业客户",
                    related_product_name="友心",
                )
            ],
        )

    monkeypatch.setattr(cli, "synthesize_products_and_scenarios_from_xlsx", synthesize)
    monkeypatch.setattr(
        cli,
        "persist_synthesized_products_and_scenarios",
        lambda **kwargs: {
            "products_inserted": len(kwargs["products"]),
            "scenarios_inserted": len(kwargs["scenarios"]),
        },
        raising=False,
    )

    report = cli._process_company(
        conn=SimpleNamespace(),
        row={
            "company_id": "COMP-17d68ddf7fd6",
            "snapshot_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "canonical_name": "一股科技",
            "industry": "电子商务",
            "hq_city": "深圳",
            "description": "友心是专注提升用户粘性的积分商城服务。",
            "business": "积分商城服务商",
            "team_raw": "",
            "products_json": [],
            "source_materials_json": [],
        },
        llm_client=SimpleNamespace(name="narrative-lite"),
        llm_model="deepseek-v4-lite",
        extra_body={"thinking": {"type": "disabled"}},
        product_llm_client=SimpleNamespace(name="product-pro"),
        product_llm_model="deepseek-v4-pro",
        product_extra_body={"thinking": {"type": "disabled"}},
        dry_run=False,
        run_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        include_source_materials=True,
        skip_team=True,
    )

    assert captured["llm_client"].name == "product-pro"
    assert captured["llm_model"] == "deepseek-v4-pro"
    assert report["products_synthesized"] == 1
    assert report["products_written"] == 1
    assert report["scenarios_synthesized"] == 1
    assert report["scenarios_written"] == 1


def test_process_company_uses_trusted_xlsx_narrative_fallback_after_llm_rejection(
    monkeypatch,
):
    cli = _import_cli()
    persisted: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "generate_company_narrative",
        lambda **_kwargs: NarrativeResult(
            profile_summary="",
            technology_route_summary="",
            error="profile_summary_too_short: 42",
        ),
    )
    monkeypatch.setattr(cli, "structure_team_raw_with_llm", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        cli,
        "synthesize_products_and_scenarios_from_xlsx",
        lambda **_kwargs: (
            [
                CompanyProductCandidate(
                    company_id="COMP-1",
                    product_name="智能终端显示组件",
                    short_description="面向智能终端的显示组件研发。",
                    official_product_url="xlsx://company/COMP-1",
                    evidence_span="智能终端显示组件研发商",
                    confidence=0.9,
                    product_category="显示组件",
                    target_customers=(),
                    application_scenarios=(),
                    technical_tags=("智能终端", "显示组件"),
                )
            ],
            [],
        ),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "persist_synthesized_products_and_scenarios",
        lambda **kwargs: {
            "products_inserted": len(kwargs["products"]),
            "scenarios_inserted": len(kwargs["scenarios"]),
        },
        raising=False,
    )

    def persist_narrative(*_args, **kwargs):
        persisted.update(kwargs)

    monkeypatch.setattr(cli, "_persist_narrative", persist_narrative)

    report = cli._process_company(
        conn=SimpleNamespace(),
        row={
            "company_id": "COMP-1",
            "snapshot_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "canonical_name": "竣浩科技",
            "project_name": "日行光学",
            "industry": None,
            "hq_city": "深圳",
            "description": None,
            "business": "智能终端显示组件研发商",
            "product_intro": None,
            "product_features": None,
            "application_scenarios_raw": None,
            "team_raw": "",
        },
        llm_client=SimpleNamespace(),
        llm_model="deepseek-v4-pro",
        extra_body={"thinking": {"type": "disabled"}},
        dry_run=False,
        run_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        skip_team=True,
    )

    assert report["narratives_written"] == 1
    assert report["narratives_rejected"] == 0
    assert report["narrative_fallback_used"] is True
    assert report["original_narrative_error"] == "profile_summary_too_short: 42"
    assert report["error"] is None
    result = persisted["result"]
    assert "导入 XLSX 可信基线" in result.profile_summary
    assert "智能终端显示组件" in result.profile_summary
    assert "智能终端" in result.technology_route_summary


def test_build_select_sql_can_include_multisource_materials():
    cli = _import_cli()

    sql, params = cli._build_select_sql(
        company_ids=("COMP-1",),
        limit=5,
        include_source_materials=True,
    )

    assert "products.products_json" in sql
    assert "source_materials.source_materials_json" in sql
    assert "company_product" in sql
    assert "company_news_item" in sql
    assert "company_signal_event" in sql
    assert params == ("COMP-1", 5)


def test_build_select_sql_uses_only_ready_structured_products_as_narrative_facts():
    cli = _import_cli()

    sql, _params = cli._build_select_sql(
        company_ids=(),
        limit=None,
        include_source_materials=True,
    )

    products_section = sql.split("FROM company_product cp", 1)[1].split(
        ") products ON true",
        1,
    )[0]
    scenarios_section = sql.split("FROM company_application_scenario s", 1)[1].split(
        "UNION ALL",
        1,
    )[0]
    assert "cp.quality_status = 'ready'" in products_section
    assert "OR EXISTS" not in products_section
    assert "s.quality_status = 'ready'" in scenarios_section
    assert "OR EXISTS" not in scenarios_section
