# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for Pipeline V3 orchestrator."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.data_agents.professor.cross_domain import CompanyLink, PaperLink, PaperStagingRecord
from src.data_agents.professor.paper_collector import PaperEnrichmentResult
from src.data_agents.professor.pipeline_v3 import (
    PipelineV3Config,
    PipelineV3Report,
    _refresh_academic_metrics_for_released_profiles,
    _build_llm_client,
    _build_fallback_llm_client,
    _merged_to_enriched,
    _process_single_professor_v3,
    run_professor_pipeline_v3,
)
from src.data_agents.professor.models import EnrichedProfessorProfile, MergedProfessorProfileRecord
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


def _make_merged_record(**kwargs) -> MergedProfessorProfileRecord:
    defaults = dict(
        name="李志",
        institution="南方科技大学",
        department="计算机科学与工程系",
        title=None,
        email="lizhi@sustech.edu.cn",
        office=None,
        homepage="https://faculty.sustech.edu.cn/lizhi/",
        profile_url="https://www.sustech.edu.cn/zh/lizhi",
        source_urls=("https://www.sustech.edu.cn/zh/lizhi",),
        evidence=("https://www.sustech.edu.cn/zh/lizhi",),
        research_directions=("机器视觉 主讲本科课程：传感器", "图像处理、模式识别"),
        extraction_status="structured",
        skip_reason=None,
        error=None,
        roster_source="https://www.sustech.edu.cn/zh/letter/",
    )
    defaults.update(kwargs)
    return MergedProfessorProfileRecord(**defaults)


class TestPipelineV3Config:
    """Test V3 config has required fields."""

    def test_config_has_v3_fields(self):
        from pathlib import Path
        config = PipelineV3Config(
            seed_doc=Path("/tmp/seeds.md"),
            output_dir=Path("/tmp/output"),
        )
        assert hasattr(config, "max_concurrent")
        assert hasattr(config, "identity_confidence_threshold")
        assert config.identity_confidence_threshold == 0.8

    def test_config_inherits_v2_fields(self):
        from pathlib import Path
        config = PipelineV3Config(
            seed_doc=Path("/tmp/seeds.md"),
            output_dir=Path("/tmp/output"),
        )
        assert hasattr(config, "local_llm_model")
        assert hasattr(config, "max_concurrent")


class TestPipelineV3Report:
    """Test V3 report has extended metrics."""

    def test_report_has_v3_metrics(self):
        report = PipelineV3Report()
        assert report.homepage_crawled_count == 0
        assert report.web_search_count == 0
        assert report.identity_verified_count == 0
        assert report.company_links_confirmed == 0
        assert report.direction_cleaned_count == 0


def test_build_fallback_llm_client_uses_primary_client_when_available():
    calls: list[tuple[str, str]] = []

    class _Completions:
        def __init__(self, label: str):
            self.label = label

        def create(self, **kwargs):
            calls.append((self.label, kwargs["model"]))
            return SimpleNamespace(source=self.label, model=kwargs["model"])

    primary_client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions("primary")))
    backup_client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions("backup")))

    client = _build_fallback_llm_client(
        primary_client=primary_client,
        primary_model="gemma-local",
        backup_client=backup_client,
        backup_model="qwen-online",
    )
    response = client.chat.completions.create(model="gemma-local", messages=[])

    assert response.source == "primary"
    assert calls == [("primary", "gemma-local")]


def test_build_fallback_llm_client_falls_back_to_backup_model_on_exception():
    calls: list[tuple[str, str]] = []

    class _PrimaryCompletions:
        def create(self, **kwargs):
            calls.append(("primary", kwargs["model"]))
            raise RuntimeError("502 Bad Gateway")

    class _BackupCompletions:
        def create(self, **kwargs):
            calls.append(("backup", kwargs["model"]))
            return SimpleNamespace(source="backup", model=kwargs["model"])

    primary_client = SimpleNamespace(chat=SimpleNamespace(completions=_PrimaryCompletions()))
    backup_client = SimpleNamespace(chat=SimpleNamespace(completions=_BackupCompletions()))

    client = _build_fallback_llm_client(
        primary_client=primary_client,
        primary_model="gemma-local",
        backup_client=backup_client,
        backup_model="qwen-online",
    )
    response = client.chat.completions.create(model="gemma-local", messages=[])

    assert response.source == "backup"
    assert calls == [
        ("primary", "gemma-local"),
        ("backup", "qwen-online"),
    ]


def test_build_llm_client_sets_request_timeout(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))

    _build_llm_client("http://llm.local/v1", "EMPTY")

    assert seen["base_url"] == "http://llm.local/v1"
    assert seen["api_key"] == "EMPTY"
    assert seen["timeout"] == 60.0


def test_merged_to_enriched_sanitizes_reader_artifact_title():
    record = _make_merged_record(
        title="URL Source: https://example.com\nPublished Time: 2026-04-12\nMarkdown Content:\nTitle: Professor",
    )

    profile = _merged_to_enriched(record)

    assert profile.title is None


@pytest.mark.asyncio
async def test_process_single_professor_keeps_existing_profile_summary(monkeypatch: pytest.MonkeyPatch):
    config = PipelineV3Config(
        seed_doc=Path("/tmp/seeds.md"),
        output_dir=Path("/tmp/output"),
        skip_web_search=True,
        skip_vectorize=True,
    )
    report = PipelineV3Report()
    record = _make_merged_record()

    async def fake_crawl_homepage(**kwargs):
        profile = kwargs["profile"].model_copy(update={
            "name_en": "Yabei Wu",
            "profile_summary": "吴亚北现任南方科技大学教授，长期研究二维材料电子结构与莫尔超晶格物理行为。" * 6,
        })
        return SimpleNamespace(profile=profile, success=True, pages_fetched=1)

    async def fake_enrich_from_papers(**kwargs):
        return PaperEnrichmentResult(
            research_directions=["二维材料", "莫尔超晶格"],
            research_directions_source="merged",
            h_index=15,
            citation_count=708,
            paper_count=70,
            top_papers=[
                PaperLink(
                    title="Twisted bilayer graphene and emergent phases",
                    year=2024,
                    venue="Nature",
                    citation_count=88,
                    source="openalex",
                )
            ],
            staging_records=[],
            disambiguation_confidence=0.95,
        )

    async def fake_generate_summaries(**kwargs):
        raise AssertionError("summary generation should not run")

    monkeypatch.setattr("src.data_agents.professor.pipeline_v3.crawl_homepage", fake_crawl_homepage)
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.enrich_from_papers",
        fake_enrich_from_papers,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.discovery.fetch_html_with_fallback",
        lambda *_args, **_kwargs: SimpleNamespace(html="<html></html>"),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.assess_completeness",
        lambda profile: SimpleNamespace(should_trigger_agent=False, missing_fields=[]),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.summary_generator.generate_summaries",
        fake_generate_summaries,
    )

    profile, staging_records, company_mentions = await _process_single_professor_v3(
        record=record,
        config=config,
        local_client=MagicMock(),
        online_client=None,
        search_provider=None,
        semaphore=asyncio.Semaphore(1),
        report=report,
    )

    assert not staging_records
    assert not company_mentions
    assert profile.name_en == "Yabei Wu"
    assert profile.profile_summary.startswith("吴亚北现任南方科技大学教授")
    assert report.summary_generated_count == 0


@pytest.mark.asyncio
async def test_process_single_professor_passes_official_publication_signals_to_paper_stage(
    monkeypatch: pytest.MonkeyPatch,
):
    config = PipelineV3Config(
        seed_doc=Path("/tmp/seeds.md"),
        output_dir=Path("/tmp/output"),
        skip_web_search=True,
        skip_vectorize=True,
    )
    report = PipelineV3Report()
    record = _make_merged_record()
    seen: dict[str, object] = {}

    async def fake_crawl_homepage(**kwargs):
        profile = kwargs["profile"].model_copy(update={
            "official_paper_count": 86,
            "official_top_papers": [
                PaperLink(
                    title="Microstructure-mediated phase transition mechanics in ferroic materials",
                    source="official_site",
                )
            ],
            "publication_evidence_urls": [
                "http://materials.sysu.edu.cn/teacher/162/publications"
            ],
            "cv_urls": ["http://materials.sysu.edu.cn/teacher/162/cv.pdf"],
            "profile_summary": "陈伟津现任中山大学（深圳）材料学院教授。" * 12,
        })
        return SimpleNamespace(profile=profile, success=True, pages_fetched=1)

    async def fake_enrich_from_papers(**kwargs):
        seen.update(kwargs)
        return PaperEnrichmentResult(
            research_directions=["功能材料固体力学"],
            research_directions_source="official_only",
            h_index=None,
            citation_count=None,
            paper_count=86,
            top_papers=[
                PaperLink(
                    title="Microstructure-mediated phase transition mechanics in ferroic materials",
                    source="official_site",
                )
            ],
            staging_records=[],
            disambiguation_confidence=0.9,
            paper_source="official_site",
        )

    monkeypatch.setattr("src.data_agents.professor.pipeline_v3.crawl_homepage", fake_crawl_homepage)
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.enrich_from_papers",
        fake_enrich_from_papers,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.discovery.fetch_html_with_fallback",
        lambda *_args, **_kwargs: SimpleNamespace(html="<html></html>"),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.assess_completeness",
        lambda profile: SimpleNamespace(should_trigger_agent=False, missing_fields=[]),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.summary_generator.generate_summaries",
        lambda **_kwargs: SimpleNamespace(
            profile_summary="陈伟津现任中山大学（深圳）材料学院教授。" * 12,
        ),
    )

    await _process_single_professor_v3(
        record=record,
        config=config,
        local_client=MagicMock(),
        online_client=None,
        search_provider=None,
        semaphore=asyncio.Semaphore(1),
        report=report,
    )

    assert seen["official_paper_count"] == 86
    assert seen["publication_evidence_urls"] == [
        "http://materials.sysu.edu.cn/teacher/162/publications"
    ]
    assert seen["cv_urls"] == ["http://materials.sysu.edu.cn/teacher/162/cv.pdf"]
    assert seen["official_top_papers"][0].source == "official_site"




@pytest.mark.asyncio
async def test_process_single_professor_merges_web_search_official_signals_and_retries_paper_collection(
    monkeypatch: pytest.MonkeyPatch,
):
    config = PipelineV3Config(
        seed_doc=Path("/tmp/seeds.md"),
        output_dir=Path("/tmp/output"),
        skip_web_search=False,
        skip_vectorize=True,
    )
    report = PipelineV3Report()
    record = _make_merged_record(
        institution="清华大学深圳国际研究生院",
        department="数据与信息学院",
        name="丁文伯",
        profile_url="https://www.sigs.tsinghua.edu.cn/dwb/",
        homepage="https://www.sigs.tsinghua.edu.cn/dwb/",
        research_directions=("机器人触觉感知",),
    )
    paper_calls: list[dict[str, object]] = []

    async def fake_crawl_homepage(**kwargs):
        profile = kwargs["profile"].model_copy(update={
            "profile_summary": "丁文伯是清华大学深圳国际研究生院副教授。" * 12,
            "evidence_urls": ["https://www.sigs.tsinghua.edu.cn/dwb/"],
        })
        return SimpleNamespace(profile=profile, success=True, pages_fetched=1)

    async def fake_enrich_from_papers(**kwargs):
        paper_calls.append(kwargs)
        if kwargs["official_paper_count"] == 42:
            return PaperEnrichmentResult(
                research_directions=["机器人触觉感知"],
                research_directions_source="official_only",
                h_index=18,
                citation_count=320,
                paper_count=42,
                top_papers=[
                    PaperLink(title="Verified official paper", source="official_site")
                ],
                staging_records=[],
                disambiguation_confidence=0.99,
                paper_source="official_site",
            )
        return PaperEnrichmentResult(
            research_directions=["机器人触觉感知"],
            research_directions_source="official_only",
            h_index=None,
            citation_count=None,
            paper_count=None,
            top_papers=[],
            staging_records=[],
            disambiguation_confidence=0.0,
            paper_source=None,
        )

    async def fake_search_and_enrich(**kwargs):
        mutated_profile = kwargs["profile"].model_copy(update={
            "official_paper_count": 42,
            "publication_evidence_urls": ["https://www.sigs.tsinghua.edu.cn/dwb/publications"],
            "scholarly_profile_urls": ["https://scholar.google.com/citations?user=verified"],
        })
        return SimpleNamespace(
            profile=mutated_profile,
            verified_urls=["https://news.example.com/founder-profile"],
            company_mentions=[
                SimpleNamespace(
                    company_name="无界智航",
                    role="发起人",
                    evidence_url="https://news.example.com/founder-profile",
                    evidence_text="丁文伯是无界智航发起人。",
                )
            ],
            pages_searched=1,
            pages_verified=1,
            error=None,
        )

    async def fake_verify_company_link(**kwargs):
        return SimpleNamespace(
            company_link=CompanyLink(
                company_name="无界智航",
                role="发起人",
                evidence_url="https://news.example.com/founder-profile",
                source="web_search",
            )
        )

    monkeypatch.setattr("src.data_agents.professor.pipeline_v3.crawl_homepage", fake_crawl_homepage)
    monkeypatch.setattr(
        "src.data_agents.professor.paper_collector.enrich_from_papers",
        fake_enrich_from_papers,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.search_and_enrich",
        fake_search_and_enrich,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.verify_company_link",
        fake_verify_company_link,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.discovery.fetch_html_with_fallback",
        lambda *_args, **_kwargs: SimpleNamespace(html="<html></html>"),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.assess_completeness",
        lambda profile: SimpleNamespace(should_trigger_agent=False, missing_fields=[]),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.summary_generator.generate_summaries",
        lambda **_kwargs: SimpleNamespace(
            profile_summary="丁文伯是清华大学深圳国际研究生院副教授。" * 12,
        ),
    )

    profile, staging_records, company_mentions = await _process_single_professor_v3(
        record=record,
        config=config,
        local_client=MagicMock(),
        online_client=None,
        search_provider=MagicMock(),
        semaphore=asyncio.Semaphore(1),
        report=report,
    )

    assert not staging_records
    assert len(company_mentions) == 1
    assert len(paper_calls) == 2
    assert paper_calls[0]["official_paper_count"] is None
    assert paper_calls[1]["official_paper_count"] == 42
    assert paper_calls[1]["publication_evidence_urls"] == ["https://www.sigs.tsinghua.edu.cn/dwb/publications"]
    assert paper_calls[1]["scholarly_profile_urls"] == ["https://scholar.google.com/citations?user=verified"]
    assert profile.research_directions == ["机器人触觉感知"]
    assert profile.official_paper_count == 42
    assert profile.publication_evidence_urls == ["https://www.sigs.tsinghua.edu.cn/dwb/publications"]
    assert profile.scholarly_profile_urls == ["https://scholar.google.com/citations?user=verified"]
    assert profile.paper_count == 42
    assert profile.top_papers[0].title == "Verified official paper"
    assert profile.company_roles[0].company_name == "无界智航"
    assert report.company_links_confirmed == 1


@pytest.mark.asyncio
async def test_run_professor_pipeline_v3_upserts_released_paper_and_link_into_shared_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    seed_doc = tmp_path / "seeds.md"
    seed_doc.write_text("- https://www.suat-sz.edu.cn/\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    shared_db_path = tmp_path / "released_objects.db"

    config = PipelineV3Config(
        seed_doc=seed_doc,
        output_dir=output_dir,
        local_llm_base_url="http://example.local/v1",
        local_llm_model="gemma4",
        local_llm_api_key="EMPTY",
        online_llm_base_url="http://example.online/v1",
        online_llm_model="qwen",
        online_llm_api_key="EMPTY",
        skip_web_search=True,
        skip_vectorize=True,
        store_db_path=str(shared_db_path),
    )

    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.run_professor_pipeline",
        lambda *_args, **_kwargs: SimpleNamespace(
            report=SimpleNamespace(
                seed_url_count=1,
                discovered_professor_count=1,
                unique_professor_count=1,
                structured_profile_count=1,
                partial_profile_count=0,
            ),
            profiles=[_make_merged_record(name="唐志敏", institution="深圳理工大学", department="算力微电子学院")],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._build_llm_client",
        lambda *_args, **_kwargs: MagicMock(),
    )

    enriched = EnrichedProfessorProfile(
        name="唐志敏",
        institution="深圳理工大学",
        department="算力微电子学院",
        title="讲席教授",
        email="tangzhimin@suat-sz.edu.cn",
        homepage="https://www.suat-sz.edu.cn/info/1154/1850.htm",
        research_directions=["并行计算", "体系结构"],
        paper_count=20,
        top_papers=[
            PaperLink(
                title="JIAJIA: A software DSM system based on a new cache coherence protocol",
                year=1993,
                venue="International Conference on Parallel Processing",
                citation_count=12,
                doi="10.1000/jiajia.1993",
                source="official_linked_google_scholar",
            )
        ],
        profile_summary="唐志敏现任深圳理工大学算力微电子学院讲席教授，长期从事并行计算与体系结构研究。" * 6,
        enrichment_source="paper_enriched",
        evidence_urls=["https://www.suat-sz.edu.cn/info/1154/1850.htm"],
        profile_url="https://www.suat-sz.edu.cn/info/1154/1850.htm",
        roster_source="https://cme.suat-sz.edu.cn/info/1021/1179.htm",
        extraction_status="structured",
    )
    staging = [
        PaperStagingRecord(
            title="JIAJIA: A software DSM system based on a new cache coherence protocol",
            authors=["唐志敏", "张三"],
            year=1993,
            venue="International Conference on Parallel Processing",
            abstract="A DSM protocol paper.",
            doi="10.1000/jiajia.1993",
            citation_count=12,
            keywords=["DSM", "Cache Coherence"],
            source_url="https://scholar.google.com/citations?user=LchbZ8wAAAAJ",
            source="official_linked_google_scholar",
            anchoring_professor_id="PROF-TANG",
            anchoring_professor_name="唐志敏",
            anchoring_institution="深圳理工大学",
        )
    ]

    async def fake_process_single_professor_v3(**_kwargs):
        return enriched, staging, []

    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._process_single_professor_v3",
        fake_process_single_professor_v3,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._build_professor_id",
        lambda _profile: "PROF-TANG",
    )

    result = await run_professor_pipeline_v3(config)

    store = SqliteReleasedObjectStore(shared_db_path)
    professors = store.list_domain_objects("professor")
    papers = store.list_domain_objects("paper")
    links = store.list_domain_objects("professor_paper_link")

    assert result.report.released_count == 1
    assert [item.display_name for item in professors] == ["唐志敏"]
    assert len(papers) == 1
    assert papers[0].core_facts["doi"] == "10.1000/jiajia.1993"
    assert len(links) == 1
    assert links[0].core_facts["professor_id"] == "PROF-TANG"
    assert links[0].core_facts["paper_id"] == papers[0].id
    assert links[0].core_facts["link_status"] == "verified"


@pytest.mark.asyncio
async def test_run_professor_pipeline_v3_metrics_stage_uses_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    seed_doc = tmp_path / "seeds.md"
    seed_doc.write_text("- https://www.sustech.edu.cn/zh/letter/\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    fixed_run_id = UUID("00000000-0000-0000-0000-000000000123")

    config = PipelineV3Config(
        seed_doc=seed_doc,
        output_dir=output_dir,
        local_llm_base_url="http://example.local/v1",
        local_llm_model="gemma4",
        local_llm_api_key="EMPTY",
        online_llm_base_url="http://example.online/v1",
        online_llm_model="qwen",
        online_llm_api_key="EMPTY",
        skip_web_search=True,
        skip_vectorize=True,
    )

    enriched = EnrichedProfessorProfile(
        name="吴亚北",
        institution="南方科技大学",
        department="物理系",
        title="教授",
        email="wuyb3@sustech.edu.cn",
        homepage="https://faculty.sustech.edu.cn/?tagid=wuyb3",
        research_directions=["二维材料", "电子结构"],
        profile_summary="吴亚北现任南方科技大学教授，长期从事二维材料电子结构与莫尔超晶格研究。" * 6,
        enrichment_source="paper_enriched",
        evidence_urls=["https://www.sustech.edu.cn/zh/faculties/wuyabei.html"],
        profile_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
        extraction_status="structured",
    )
    conn = SimpleNamespace(
        commit=MagicMock(),
        rollback=MagicMock(),
        execute=MagicMock(return_value=SimpleNamespace(rowcount=1)),
    )

    async def fake_process_single_professor_v3(**_kwargs):
        return enriched, [], []

    class _ConnContext:
        def __enter__(self):
            return conn

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.run_professor_pipeline",
        lambda *_args, **_kwargs: SimpleNamespace(
            report=SimpleNamespace(
                seed_url_count=1,
                discovered_professor_count=1,
                unique_professor_count=1,
                structured_profile_count=1,
                partial_profile_count=0,
            ),
            profiles=[_make_merged_record(name="吴亚北", department="物理系")],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._build_llm_client",
        lambda *_args, **_kwargs: MagicMock(),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._process_single_professor_v3",
        fake_process_single_professor_v3,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._build_professor_id",
        lambda _profile: "PROF-WUYABEI",
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.open_pipeline_run",
        lambda *_args, **_kwargs: fixed_run_id,
    )
    close_run = MagicMock()
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.close_pipeline_run",
        close_run,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.pg_connect",
        lambda: _ConnContext(),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.get_professor_orcid",
        lambda _conn, _professor_id: "0000-0002-1825-009X",
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.fetch_openalex_metrics",
        lambda **_kwargs: SimpleNamespace(
            source="openalex",
            h_index=15,
            citation_count=708,
        ),
    )
    upsert_metrics = MagicMock()
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.upsert_professor_metrics",
        upsert_metrics,
    )

    result = await run_professor_pipeline_v3(config)

    assert result.report.metrics_refreshed_count == 1
    assert result.report.metrics_openalex_count == 1
    upsert_metrics.assert_called_once()
    assert upsert_metrics.call_args.kwargs["professor_id"] == "PROF-WUYABEI"
    assert upsert_metrics.call_args.kwargs["h_index"] == 15
    assert upsert_metrics.call_args.kwargs["citation_count"] == 708
    assert upsert_metrics.call_args.kwargs["metrics_source"] == "openalex"
    assert upsert_metrics.call_args.kwargs["run_id"] == str(fixed_run_id)
    close_run.assert_called_once()


def test_pipeline_v3_metrics_failure_files_issue_and_continues(
    monkeypatch: pytest.MonkeyPatch,
):
    report = PipelineV3Report()
    profile = EnrichedProfessorProfile(
        name="吴亚北",
        institution="南方科技大学",
        department="物理系",
        research_directions=["二维材料"],
        profile_summary="吴亚北现任南方科技大学教授。" * 12,
        evidence_urls=["https://www.sustech.edu.cn/zh/faculties/wuyabei.html"],
        profile_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
        extraction_status="structured",
    )
    conn = SimpleNamespace(
        commit=MagicMock(),
        rollback=MagicMock(),
        execute=MagicMock(return_value=SimpleNamespace(rowcount=1)),
    )

    class _ConnContext:
        def __enter__(self):
            return conn

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.pg_connect",
        lambda: _ConnContext(),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.get_professor_orcid",
        lambda _conn, _professor_id: "0000-0002-1825-009X",
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.fetch_openalex_metrics",
        MagicMock(side_effect=RuntimeError("openalex 503")),
    )

    _refresh_academic_metrics_for_released_profiles(
        released_profiles=[("PROF-WUYABEI", profile, "ready")],
        run_id="run-1",
        report=report,
    )

    assert report.metrics_failed_count == 1
    assert report.metrics_refreshed_count == 0
    assert any("INSERT INTO pipeline_issue" in call.args[0] for call in conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_run_professor_pipeline_v3_upserts_released_professor_into_shared_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    seed_doc = tmp_path / "seeds.md"
    seed_doc.write_text("- https://www.sustech.edu.cn/zh/letter/\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    shared_db_path = tmp_path / "released_objects.db"

    config = PipelineV3Config(
        seed_doc=seed_doc,
        output_dir=output_dir,
        local_llm_base_url="http://example.local/v1",
        local_llm_model="gemma4",
        local_llm_api_key="EMPTY",
        online_llm_base_url="http://example.online/v1",
        online_llm_model="qwen",
        online_llm_api_key="EMPTY",
        skip_web_search=True,
        skip_vectorize=True,
        store_db_path=str(shared_db_path),
    )

    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.run_professor_pipeline",
        lambda *_args, **_kwargs: SimpleNamespace(
            report=SimpleNamespace(
                seed_url_count=1,
                discovered_professor_count=1,
                unique_professor_count=1,
                structured_profile_count=1,
                partial_profile_count=0,
            ),
            profiles=[_make_merged_record(name="吴亚北", department="物理系")],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._build_llm_client",
        lambda *_args, **_kwargs: MagicMock(),
    )

    enriched = EnrichedProfessorProfile(
        name="吴亚北",
        institution="南方科技大学",
        department="物理系",
        title="教授",
        email="wuyb3@sustech.edu.cn",
        homepage="https://faculty.sustech.edu.cn/?tagid=wuyb3",
        research_directions=["二维材料", "电子结构"],
        h_index=15,
        citation_count=708,
        paper_count=70,
        top_papers=[
            PaperLink(
                title="Twisted bilayer graphene and emergent phases",
                year=2024,
                venue="Nature",
                citation_count=88,
                source="openalex",
            )
        ],
        profile_summary="吴亚北现任南方科技大学教授，长期从事二维材料电子结构与莫尔超晶格研究。" * 6,
        enrichment_source="paper_enriched",
        evidence_urls=["https://www.sustech.edu.cn/zh/faculties/wuyabei.html"],
        profile_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
        extraction_status="structured",
    )

    async def fake_process_single_professor_v3(**_kwargs):
        return enriched, [], []

    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._process_single_professor_v3",
        fake_process_single_professor_v3,
    )

    result = await run_professor_pipeline_v3(config)

    store = SqliteReleasedObjectStore(shared_db_path)
    objects = store.list_domain_objects("professor")

    assert result.report.released_count == 1
    assert [item.display_name for item in objects] == ["吴亚北"]
    assert objects[0].core_facts["paper_count"] == 70


@pytest.mark.asyncio
async def test_run_professor_pipeline_v3_resume_reloads_paper_staging_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    seed_doc = tmp_path / "seeds.md"
    seed_doc.write_text("- https://www.suat-sz.edu.cn/\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    shared_db_path = tmp_path / "released_objects.db"

    config = PipelineV3Config(
        seed_doc=seed_doc,
        output_dir=output_dir,
        local_llm_base_url="http://example.local/v1",
        local_llm_model="gemma4",
        local_llm_api_key="EMPTY",
        online_llm_base_url="http://example.online/v1",
        online_llm_model="qwen",
        online_llm_api_key="EMPTY",
        skip_web_search=True,
        skip_vectorize=True,
        store_db_path=str(shared_db_path),
    )

    enriched = EnrichedProfessorProfile(
        name="唐志敏",
        institution="深圳理工大学",
        department="算力微电子学院",
        title="讲席教授",
        email="tangzhimin@suat-sz.edu.cn",
        homepage="https://www.suat-sz.edu.cn/info/1154/1850.htm",
        research_directions=["并行计算", "体系结构"],
        paper_count=20,
        top_papers=[
            PaperLink(
                title="JIAJIA: A software DSM system based on a new cache coherence protocol",
                year=1993,
                venue="International Conference on Parallel Processing",
                citation_count=12,
                doi="10.1000/jiajia.1993",
                source="official_linked_google_scholar",
            )
        ],
        profile_summary="唐志敏现任深圳理工大学算力微电子学院讲席教授，长期从事并行计算与体系结构研究。" * 6,
        enrichment_source="paper_enriched",
        evidence_urls=["https://www.suat-sz.edu.cn/info/1154/1850.htm"],
        profile_url="https://www.suat-sz.edu.cn/info/1154/1850.htm",
        roster_source="https://cme.suat-sz.edu.cn/info/1021/1179.htm",
        extraction_status="structured",
    )
    staging = PaperStagingRecord(
        title="JIAJIA: A software DSM system based on a new cache coherence protocol",
        authors=["唐志敏", "张三"],
        year=1993,
        venue="International Conference on Parallel Processing",
        abstract="A DSM protocol paper.",
        doi="10.1000/jiajia.1993",
        citation_count=12,
        keywords=["DSM", "Cache Coherence"],
        source_url="https://scholar.google.com/citations?user=LchbZ8wAAAAJ",
        source="official_linked_google_scholar",
        anchoring_professor_id="PROF-TANG",
        anchoring_professor_name="唐志敏",
        anchoring_institution="深圳理工大学",
    )

    (output_dir / "enriched_v3.jsonl").write_text(
        json.dumps(enriched.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "paper_staging.jsonl").write_text(
        json.dumps(staging.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3.run_professor_pipeline",
        lambda *_args, **_kwargs: SimpleNamespace(
            report=SimpleNamespace(
                seed_url_count=1,
                discovered_professor_count=1,
                unique_professor_count=1,
                structured_profile_count=1,
                partial_profile_count=0,
            ),
            profiles=[_make_merged_record(name="唐志敏", institution="深圳理工大学", department="算力微电子学院", profile_url="https://www.suat-sz.edu.cn/info/1154/1850.htm")],
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._build_llm_client",
        lambda *_args, **_kwargs: MagicMock(),
    )
    monkeypatch.setattr(
        "src.data_agents.professor.pipeline_v3._build_professor_id",
        lambda _profile: "PROF-TANG",
    )

    result = await run_professor_pipeline_v3(config)

    store = SqliteReleasedObjectStore(shared_db_path)
    papers = store.list_domain_objects("paper")
    links = store.list_domain_objects("professor_paper_link")

    assert result.report.released_count == 1
    assert len(papers) == 1
    assert papers[0].core_facts["doi"] == "10.1000/jiajia.1993"
    assert len(links) == 1
    assert links[0].core_facts["professor_id"] == "PROF-TANG"
