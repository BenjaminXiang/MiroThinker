from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx

from src.data_agents.company.generic_source_judgment import SourceJudgment
from src.data_agents.company.news_connectors.base import NewsRecord


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_company_generic_source_judgment.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_generic_source_judgment", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_args_accepts_concurrency_and_checkpoint_stage():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--company-id",
            "COMP-1",
            "--concurrency",
            "3",
            "--llm-timeout-seconds",
            "45",
            "--llm-retry-budget",
            "1",
            "--checkpoint-stage",
            "generic_source_judgment",
        ]
    )

    assert args.company_id == ["COMP-1"]
    assert args.concurrency == 3
    assert args.llm_timeout_seconds == 45
    assert args.llm_retry_budget == 1
    assert args.checkpoint_stage == "generic_source_judgment"


def test_identity_terms_include_trusted_short_brand_variants():
    cli = _import_cli()

    terms = cli._identity_terms_for_guard(
        {
            "canonical_name": "中农美蔬（深圳）科技",
            "registered_name": "中农美蔬（深圳）科技有限公司",
            "company_name_xlsx": "中农美蔬（深圳）科技有限公司",
            "project_name": None,
            "aliases": [],
        }
    )

    assert "中农美蔬（深圳）科技" in terms
    assert "中农美蔬" in terms


def test_identity_terms_keep_three_character_brand_variants():
    cli = _import_cli()

    terms = cli._identity_terms_for_guard(
        {
            "canonical_name": "偲百创（深圳）科技",
            "registered_name": "偲百创（深圳）科技有限公司",
            "company_name_xlsx": "偲百创（深圳）科技有限公司",
            "project_name": None,
            "aliases": [],
        }
    )

    assert "偲百创" in terms


def test_process_company_runs_react_judgment_records_audit_and_persists(monkeypatch):
    cli = _import_cli()
    audit_calls: list[dict] = []
    inserted_sources: list[str] = []
    identity_terms_seen: list[tuple[str, ...]] = []

    class _Connector:
        def fetch(self, query, since):
            assert since == date(2000, 1, 1)
            if query == "深圳旭宏医疗科技有限公司":
                return [
                    NewsRecord(
                        company_id="深圳旭宏医疗科技有限公司",
                        source_url="https://example.com/xuhong",
                        title="旭宏医疗产品进展",
                        summary="旭宏医疗发布 AI 心电产品。",
                        raw_text="旭宏医疗发布 AI 心电产品。",
                        published_at=None,
                    )
                ]
            return []

    def _judge(*, page_text=None, identity_terms=(), **_kwargs):
        identity_terms_seen.append(tuple(identity_terms))
        if page_text is None:
            return SourceJudgment(
                status="needs_review",
                reason="snippet_insufficient",
                evidence_span="旭宏医疗",
                snippet_sufficiency="insufficient",
                confirms_identity=True,
                confirms_fact_attribution=False,
                should_fetch=True,
            )
        return SourceJudgment(
            status="accepted",
            reason="company_identity_and_fact_attribution_confirmed",
            evidence_span="深圳旭宏医疗科技有限公司发布 AI 心电产品",
            snippet_sufficiency="sufficient",
            confirms_identity=True,
            confirms_fact_attribution=True,
            should_fetch=False,
        )

    monkeypatch.setattr(
        cli,
        "record_search_audit",
        lambda _conn, **kwargs: audit_calls.append(kwargs) or 1,
    )
    monkeypatch.setattr(
        cli,
        "_insert_accepted_sources",
        lambda _conn, *, company, accepted_sources, dry_run, run_id: inserted_sources.extend(
            source.url for source in accepted_sources
        )
        or len(accepted_sources),
    )

    report = cli._process_company(
        conn=SimpleNamespace(),
        company={
            "company_id": "COMP-1",
            "canonical_name": "深圳旭宏医疗科技有限公司",
            "registered_name": "深圳旭宏医疗科技有限公司",
            "company_name_xlsx": "深圳旭宏医疗科技有限公司",
            "project_name": "旭宏医疗",
            "aliases": [],
            "website_host": "xuhong.example",
        },
        connector=_Connector(),
        since=date(2000, 1, 1),
        batch_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        dry_run=False,
        run_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        judge_source=_judge,
        fetch_page=lambda url: "深圳旭宏医疗科技有限公司发布 AI 心电产品，服务基层医疗机构。",
    )

    assert report["queries_run"] == 2
    assert report["results_seen"] == 1
    assert report["fetch_count"] == 1
    assert report["accepted_sources"] == 1
    assert report["inserted_sources"] == 1
    assert inserted_sources == ["https://example.com/xuhong"]
    assert audit_calls[0]["source_adapter"] == "generic_web"
    diagnostics = audit_calls[0]["diagnostics"]
    assert diagnostics["query_kind"] == "generic_identity"
    assert diagnostics["trusted_identity_terms"][0] == "深圳旭宏医疗科技有限公司"
    assert "旭宏医疗" in diagnostics["trusted_identity_terms"]
    assert diagnostics["source_judgment"]["accepted"] == 1
    assert diagnostics["fetch_count"] == 1
    assert len(identity_terms_seen) == 2
    assert identity_terms_seen[0][0] == "深圳旭宏医疗科技有限公司"
    assert "旭宏医疗" in identity_terms_seen[0]
    assert identity_terms_seen[1] == identity_terms_seen[0]


def test_insert_accepted_sources_writes_generic_web_news_rows():
    cli = _import_cli()
    executed: list[tuple[str, object]] = []

    class _Conn:
        def execute(self, sql, params):
            executed.append((sql, params))
            return SimpleNamespace(fetchone=lambda: {"news_id": "NEWS-1"})

    source = cli.AcceptedSourceMaterial(
        source_id="SRC-1",
        source_tier="generic_web",
        url="https://example.com/xuhong",
        title="旭宏医疗产品进展",
        captured_text="深圳旭宏医疗科技有限公司发布 AI 心电产品。",
        captured_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        trust_reason="company_identity_and_fact_attribution_confirmed",
        evidence_span="发布 AI 心电产品",
    )

    inserted = cli._insert_accepted_sources(
        _Conn(),
        company={
            "company_id": "COMP-1",
            "website_host": "xuhong.example",
        },
        accepted_sources=[source],
        dry_run=False,
        run_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    )

    assert inserted == 1
    sql, params = executed[0]
    assert "INSERT INTO company_news_item" in sql
    assert params["source_adapter"] == "generic_web"
    assert params["is_company_confirmed"] is True
    assert params["diagnostics"].obj["source_judgment_status"] == "accepted"


def test_fetch_page_text_skips_pdf_content(monkeypatch):
    cli = _import_cli()

    def _fake_get(*_args, **_kwargs):
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.7\n%binary",
            request=httpx.Request("GET", "https://example.com/file.pdf"),
        )

    monkeypatch.setattr(cli.httpx, "get", _fake_get)

    assert cli._fetch_page_text("https://example.com/file.pdf", max_chars=200) == ""


def test_fetch_page_text_returns_empty_on_parser_error(monkeypatch):
    cli = _import_cli()

    def _fake_get(*_args, **_kwargs):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body>broken</body></html>",
            request=httpx.Request("GET", "https://example.com/page"),
        )

    class _BrokenSoup:
        def __init__(self, *_args, **_kwargs):
            raise ValueError("parser failed")

    monkeypatch.setattr(cli.httpx, "get", _fake_get)
    monkeypatch.setattr(cli, "BeautifulSoup", _BrokenSoup)

    assert cli._fetch_page_text("https://example.com/page", max_chars=200) == ""
