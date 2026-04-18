# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for batch re-processing of existing professors through V3 pipeline."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.professor.batch_reprocess import (
    BatchReprocessConfig,
    BatchReprocessReport,
    _reprocess_single,
)
from src.data_agents.professor.cross_domain import CompanyLink
from src.data_agents.professor.models import EnrichedProfessorProfile


class TestLoadProfessorsFromStore:
    """Test loading existing professor records for re-processing."""

    def test_loads_professors_with_core_facts(self, tmp_path: Path) -> None:
        """Should convert store records to EnrichedProfessorProfile."""
        from src.data_agents.professor.batch_reprocess import (
            load_professors_from_store,
        )

        # Create a mock store with one professor
        store = _make_store_with_professors(tmp_path, [
            {
                "id": "PROF-001",
                "display_name": "张三",
                "core_facts": {
                    "name": "张三",
                    "institution": "南方科技大学",
                    "department": None,
                    "title": None,
                    "email": "zhang@sustech.edu.cn",
                    "homepage": "https://www.sustech.edu.cn/zh/faculties/zhangsan.html",
                    "research_directions": [],
                },
                "evidence": [
                    {
                        "source_type": "official_site",
                        "source_url": "https://www.sustech.edu.cn/zh/faculties/zhangsan.html",
                        "fetched_at": "2026-04-05T12:00:00Z",
                        "confidence": 0.8,
                    }
                ],
            }
        ])

        profiles = load_professors_from_store(store)
        assert len(profiles) == 1
        assert profiles[0].name == "张三"
        assert profiles[0].institution == "南方科技大学"
        assert profiles[0].email == "zhang@sustech.edu.cn"
        assert profiles[0].profile_url == "https://www.sustech.edu.cn/zh/faculties/zhangsan.html"

    def test_filters_by_institution(self, tmp_path: Path) -> None:
        """Should filter professors by institution name."""
        from src.data_agents.professor.batch_reprocess import (
            load_professors_from_store,
        )

        store = _make_store_with_professors(tmp_path, [
            _make_prof("PROF-001", "张三", "南方科技大学"),
            _make_prof("PROF-002", "李四", "深圳大学"),
            _make_prof("PROF-003", "王五", "南方科技大学"),
        ])

        profiles = load_professors_from_store(store, institution_filter="南方科技大学")
        assert len(profiles) == 2
        assert all(p.institution == "南方科技大学" for p in profiles)

    def test_respects_limit(self, tmp_path: Path) -> None:
        """Should limit number of professors loaded."""
        from src.data_agents.professor.batch_reprocess import (
            load_professors_from_store,
        )

        store = _make_store_with_professors(tmp_path, [
            _make_prof(f"PROF-{i:03d}", f"教授{i}", "南方科技大学")
            for i in range(10)
        ])

        profiles = load_professors_from_store(store, limit=3)
        assert len(profiles) == 3

    def test_loads_professors_without_homepage_but_with_evidence_url(self, tmp_path: Path) -> None:
        """Professors without homepage but with evidence URL should still be loaded
        since profile_url can be derived from evidence."""
        from src.data_agents.professor.batch_reprocess import (
            load_professors_from_store,
        )

        store = _make_store_with_professors(tmp_path, [
            {
                "id": "PROF-001",
                "display_name": "张三",
                "core_facts": {
                    "name": "张三",
                    "institution": "南方科技大学",
                    "homepage": None,
                    "research_directions": [],
                },
                "evidence": [
                    {
                        "source_type": "official_site",
                        "source_url": "https://www.sustech.edu.cn/zh/faculties/zhangsan.html",
                        "fetched_at": "2026-04-05T12:00:00Z",
                        "confidence": 0.8,
                    }
                ],
            },
        ])

        profiles = load_professors_from_store(store)
        assert len(profiles) == 1
        assert profiles[0].profile_url == "https://www.sustech.edu.cn/zh/faculties/zhangsan.html"


class TestBatchReprocessConfig:
    """Test batch reprocess configuration."""

    def test_config_defaults(self) -> None:
        """Should have sensible defaults."""
        from src.data_agents.professor.batch_reprocess import BatchReprocessConfig

        config = BatchReprocessConfig(
            store_db_path="/tmp/test.db",
            output_dir=Path("/tmp/output"),
        )
        assert config.skip_web_search is False
        assert config.skip_vectorize is False
        assert config.limit is None
        assert config.institution_filter is None


# ── Helpers ──

def _make_prof(prof_id: str, name: str, institution: str) -> dict:
    return {
        "id": prof_id,
        "display_name": name,
        "core_facts": {
            "name": name,
            "institution": institution,
            "department": None,
            "title": None,
            "email": f"{name}@test.edu.cn",
            "homepage": f"https://www.test.edu.cn/{name}.html",
            "research_directions": [],
        },
        "evidence": [
            {
                "source_type": "official_site",
                "source_url": f"https://www.test.edu.cn/{name}.html",
                "fetched_at": "2026-04-05T12:00:00Z",
                "confidence": 0.8,
            }
        ],
    }


def _make_store_with_professors(tmp_path: Path, professors: list[dict]):
    """Create a real SQLite store with professor records."""
    from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

    db_path = tmp_path / "test.db"
    store = SqliteReleasedObjectStore(db_path)

    objects = []
    for prof in professors:
        evidence = [
            Evidence(
                source_type=e.get("source_type", "official_site"),
                source_url=e.get("source_url", ""),
                fetched_at=e.get("fetched_at", "2026-04-05T12:00:00Z"),
                confidence=e.get("confidence", 0.8),
            )
            for e in prof.get("evidence", [])
        ]
        obj = ReleasedObject(
            id=prof["id"],
            object_type="professor",
            display_name=prof["display_name"],
            core_facts=prof.get("core_facts", {}),
            summary_fields=prof.get("summary_fields", {}),
            evidence=evidence,
            quality_status="needs_review",
            last_updated="2026-04-05T12:00:00Z",
        )
        objects.append(obj)

    store.upsert_released_objects(objects)
    return store


@pytest.mark.asyncio
async def test_reprocess_single_uses_web_search_only_for_company_evidence(
    monkeypatch: pytest.MonkeyPatch,
):
    config = BatchReprocessConfig(
        store_db_path="/tmp/test.db",
        output_dir=Path("/tmp/output"),
        skip_homepage_crawl=True,
        skip_papers=True,
        skip_agent_enrichment=True,
        skip_summary=True,
        skip_web_search=False,
    )
    report = BatchReprocessReport()
    profile = EnrichedProfessorProfile(
        name="丁文伯",
        institution="清华大学深圳国际研究生院",
        department="数据与信息学院",
        title="副教授",
        profile_url="https://www.sigs.tsinghua.edu.cn/dwb/",
        homepage="https://www.sigs.tsinghua.edu.cn/dwb/",
        roster_source="https://www.sigs.tsinghua.edu.cn/faculty/",
        extraction_status="structured",
        research_directions=["机器人触觉感知"],
    )

    async def fake_search_and_enrich(**kwargs):
        mutated_profile = kwargs["profile"].model_copy(update={
            "research_directions": ["错误的公网研究方向"],
            "official_paper_count": 42,
            "publication_evidence_urls": ["https://public.example.com/publications"],
        })
        return MagicMock(
            profile=mutated_profile,
            pages_verified=1,
            company_mentions=[
                MagicMock(
                    company_name="无界智航",
                    role="发起人",
                    evidence_url="https://news.example.com/founder-profile",
                    evidence_text="丁文伯是无界智航发起人。",
                )
            ],
        )

    async def fake_verify_company_link(**kwargs):
        return MagicMock(
            company_link=CompanyLink(
                company_name="无界智航",
                role="发起人",
                evidence_url="https://news.example.com/founder-profile",
                source="web_search",
            )
        )

    monkeypatch.setattr(
        "src.data_agents.professor.web_search_enrichment.search_and_enrich",
        fake_search_and_enrich,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.company_linker.verify_company_link",
        fake_verify_company_link,
    )
    monkeypatch.setattr(
        "src.data_agents.professor.batch_reprocess.fetch_html_with_fallback",
        lambda *_args, **_kwargs: MagicMock(html="<html></html>"),
        raising=False,
    )

    enriched, company_mentions = await _reprocess_single(
        profile=profile,
        config=config,
        local_client=MagicMock(),
        online_client=None,
        search_provider=MagicMock(),
        semaphore=asyncio.Semaphore(1),
        report=report,
    )

    assert len(company_mentions) == 1
    assert enriched.research_directions == ["机器人触觉感知"]
    assert enriched.official_paper_count is None
    assert enriched.publication_evidence_urls == []
    assert enriched.company_roles[0].company_name == "无界智航"
    assert report.web_searched == 1
    assert report.company_links == 1


def test_update_store_with_enriched_filters_profiles_that_fail_release_gate(tmp_path: Path) -> None:
    from src.data_agents.professor.batch_reprocess import _update_store_with_enriched
    from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

    store = SqliteReleasedObjectStore(tmp_path / "released.db")
    enriched_path = tmp_path / "enriched_v3.jsonl"
    profile = EnrichedProfessorProfile(
        name="教师队伍",
        institution="南方科技大学",
        department="计算机科学与工程系",
        title="教授",
        profile_url="https://www.sustech.edu.cn/zh/faculties/team.html",
        homepage="https://www.sustech.edu.cn/zh/faculties/team.html",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
        extraction_status="structured",
        research_directions=["机器学习"],
        paper_count=5,
        profile_summary="教师队伍长期围绕机器学习与数据智能开展研究，形成稳定科研方向。" * 4,
        evaluation_summary="具备基础科研画像。",
        evidence_urls=["https://www.sustech.edu.cn/zh/faculties/team.html"],
    )
    enriched_path.write_text(json.dumps(profile.model_dump(mode="json"), ensure_ascii=False) + "\n", encoding="utf-8")

    updated = _update_store_with_enriched(store, enriched_path)

    assert updated == 0
    assert store.list_domain_objects("professor") == []


def test_update_store_with_enriched_uses_release_gate_quality_status(tmp_path: Path) -> None:
    from src.data_agents.professor.batch_reprocess import _update_store_with_enriched
    from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

    store = SqliteReleasedObjectStore(tmp_path / "released.db")
    enriched_path = tmp_path / "enriched_v3.jsonl"
    profile = EnrichedProfessorProfile(
        name="李志",
        institution="南方科技大学",
        department="计算机科学与工程系",
        title="教授",
        email="lizhi@sustech.edu.cn",
        profile_url="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
        homepage="https://www.sustech.edu.cn/zh/faculties/lizhi.html",
        roster_source="https://www.sustech.edu.cn/zh/letter/",
        extraction_status="structured",
        research_directions=["机器学习", "数据库系统"],
        paper_count=12,
        profile_summary=("李志现任南方科技大学计算机科学与工程系教授，长期从事机器学习、数据库系统与数据智能方向研究，围绕高效数据管理、复杂场景下的智能分析与系统优化持续开展工作，并在相关方向形成稳定研究主题与可核验学术产出。" * 2),
        evaluation_summary="李志已形成可核验论文画像。",
        evidence_urls=["https://www.sustech.edu.cn/zh/faculties/lizhi.html"],
    )
    enriched_path.write_text(json.dumps(profile.model_dump(mode="json"), ensure_ascii=False) + "\n", encoding="utf-8")

    updated = _update_store_with_enriched(store, enriched_path)

    objects = store.list_domain_objects("professor")
    assert updated == 1
    assert len(objects) == 1
    assert objects[0].quality_status == "ready"
    assert objects[0].core_facts["paper_count"] == 12
