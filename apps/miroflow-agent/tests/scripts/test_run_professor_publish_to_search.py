# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.contracts import ProfessorRecord
from src.data_agents.professor.cross_domain import PaperLink
from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


TIMESTAMP = datetime(2026, 4, 7, tzinfo=timezone.utc)


def _load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profile(**overrides) -> EnrichedProfessorProfile:
    defaults = {
        "name": "吴亚北",
        "name_en": "Yabei Wu",
        "institution": "南方科技大学",
        "department": "物理系",
        "email": "wuyb3@sustech.edu.cn",
        "homepage": "https://faculty.sustech.edu.cn/?cat=4&tagid=wuyb3",
        "research_directions": ["二维材料", "电子结构"],
        "h_index": 15,
        "citation_count": 708,
        "paper_count": 70,
        "top_papers": [
            PaperLink(
                title="Twisted bilayer graphene and emergent phases",
                year=2024,
                venue="Nature",
                citation_count=88,
                doi="10.1234/example",
                source="openalex",
            )
        ],
        "profile_summary": "吴亚北现任南方科技大学教授，长期从事二维材料电子结构与莫尔超晶格研究。" * 6,
        "evaluation_summary": "",
        "enrichment_source": "paper_enriched",
        "evidence_urls": ["https://www.sustech.edu.cn/zh/faculties/wuyabei.html"],
        "profile_url": "https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
        "roster_source": "https://www.sustech.edu.cn/zh/letter/",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def test_enriched_to_professor_record_preserves_paper_fields_and_quality_status():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )

    record = module.enriched_to_professor_record(_profile(), TIMESTAMP)

    assert record is not None
    assert record.h_index == 15
    assert record.citation_count == 708
    assert record.paper_count == 70
    assert record.quality_status == "ready"


def test_enriched_to_professor_record_marks_missing_papers_as_needs_enrichment():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )

    record = module.enriched_to_professor_record(
        _profile(top_papers=[], h_index=None, citation_count=None, paper_count=None),
        TIMESTAMP,
    )

    assert record is not None
    assert record.quality_status == "needs_enrichment"


def test_enriched_to_professor_record_rejects_obvious_non_person_name():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )

    record = module.enriched_to_professor_record(
        _profile(name="返回主站"),
        TIMESTAMP,
    )

    assert record is None


def test_resolve_enriched_inputs_prefers_discovered_e2e_files(tmp_path: Path):
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    batch_dir = tmp_path / "batch"
    first = batch_dir / "001_a" / "enriched_v3.jsonl"
    second = batch_dir / "002_b" / "enriched_v3.jsonl"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    fallback = tmp_path / "fallback.jsonl"
    fallback.write_text("", encoding="utf-8")

    resolved = module.resolve_enriched_inputs(
        enriched_jsonl=fallback,
        enriched_dir=batch_dir,
    )

    assert resolved == [first, second]


def test_load_enriched_profiles_accepts_multiple_paths(tmp_path: Path):
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text(_profile().model_dump_json() + "\n", encoding="utf-8")
    second.write_text(
        _profile(name="黄建华", profile_url="https://example.com/hjh").model_dump_json() + "\n",
        encoding="utf-8",
    )

    profiles = module.load_enriched_profiles([first, second])

    assert [profile.name for profile in profiles] == ["吴亚北", "黄建华"]


def test_upsert_shared_professor_objects_replaces_professor_domain_only(tmp_path: Path):
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    shared_db = tmp_path / "shared.db"
    store = SqliteReleasedObjectStore(shared_db)
    stale_professor = ProfessorRecord(
        id="PROF-OLD",
        name="返回主站",
        institution="南方科技大学",
        department="物理系",
        profile_summary="旧的脏教授对象。",
        evidence=module._build_evidence(
            ["https://www.sustech.edu.cn/zh/faculties/bad.html"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    ).to_released_object()
    company = module.ReleasedObject(
        id="COMP-1",
        object_type="company",
        display_name="深圳科创有限公司",
        core_facts={"name": "深圳科创有限公司", "industry": "人工智能"},
        summary_fields={"profile_summary": "测试公司"},
        evidence=module._build_evidence(
            ["https://www.sustech.edu.cn/zh/company/demo.html"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
        quality_status="ready",
    )
    store.upsert_released_objects([stale_professor, company])

    fresh_record = module.enriched_to_professor_record(_profile(), TIMESTAMP)

    assert fresh_record is not None

    module.upsert_shared_professor_objects(
        released_objects=[fresh_record.to_released_object()],
        shared_db_path=shared_db,
        replace_domain=True,
    )

    updated_store = SqliteReleasedObjectStore(shared_db)
    professors = updated_store.list_domain_objects("professor")
    companies = updated_store.list_domain_objects("company")

    assert [item.display_name for item in professors] == ["吴亚北"]
    assert [item.display_name for item in companies] == ["深圳科创有限公司"]


def test_dedupe_professor_records_for_search_merges_same_anchor_identity():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    shared_url = "http://www.sigs.tsinghua.edu.cn/yzys/main.htm"
    roster_url = "https://www.sigs.tsinghua.edu.cn/7644/list.htm"
    record_a = ProfessorRecord(
        id="PROF-A",
        name="尤政院士",
        institution="清华大学深圳国际研究生院",
        title="院士",
        homepage=shared_url,
        research_directions=["储能用碳材料和先进电池"],
        profile_summary="尤政院士长期从事储能与先进电池研究。" * 6,
        evidence=module._build_evidence([shared_url, roster_url], TIMESTAMP),
        last_updated=TIMESTAMP,
        quality_status="needs_enrichment",
    )
    record_b = ProfessorRecord(
        id="PROF-B",
        name="尤政院士",
        institution="清华大学深圳国际研究生院",
        homepage=shared_url,
        research_directions=["先进电池", "储能用碳材料和先进电池"],
        awards=["中国科学院院士"],
        profile_summary="尤政院士长期从事储能与先进电池研究。" * 6,
        evidence=module._build_evidence([shared_url, roster_url], TIMESTAMP),
        last_updated=TIMESTAMP,
        quality_status="needs_enrichment",
    )

    deduped = module.dedupe_professor_records_for_search([record_a, record_b])

    assert len(deduped) == 1
    merged = deduped[0]
    assert merged.name == "尤政院士"
    assert merged.title == "院士"
    assert merged.homepage == shared_url
    assert merged.research_directions == ["储能用碳材料和先进电池", "先进电池"]
    assert merged.awards == ["中国科学院院士"]
    assert len(merged.evidence) == 2


def test_dedupe_professor_records_for_search_keeps_same_name_when_anchors_differ():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    record_a = ProfessorRecord(
        id="PROF-A",
        name="刘清侠",
        institution="深圳技术大学",
        department="人工智能学院",
        homepage="https://ai.sztu.edu.cn/info/1332/6057.htm",
        research_directions=["物质表面和界面分子间作用力基础理论"],
        profile_summary="刘清侠现任深圳技术大学讲席教授，长期从事材料与能源研究。" * 6,
        evidence=module._build_evidence(
            [
                "https://ai.sztu.edu.cn/info/1332/6057.htm",
                "https://ai.sztu.edu.cn/szdw/jytd/jxjs.htm",
            ],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )
    record_b = ProfessorRecord(
        id="PROF-B",
        name="刘清侠",
        institution="深圳技术大学",
        department="新材料与新能源学院",
        homepage="https://nmne.sztu.edu.cn/info/1033/3214.htm",
        research_directions=["新能源材料"],
        profile_summary="刘清侠现任深圳技术大学讲席教授，长期从事材料与能源研究。" * 6,
        evidence=module._build_evidence(
            [
                "https://nmne.sztu.edu.cn/info/1033/3214.htm",
                "https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004",
            ],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )

    deduped = module.dedupe_professor_records_for_search([record_a, record_b])

    assert len(deduped) == 2
    assert {item.department for item in deduped} == {"人工智能学院", "新材料与新能源学院"}


def test_dedupe_professor_records_for_search_merges_same_name_when_summary_similarity_is_high():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    record_a = ProfessorRecord(
        id="PROF-A",
        name="樊建平",
        institution="深圳理工大学",
        department="计算机科学与人工智能学院",
        title="讲席教授",
        email="fanjianping@suat-sz.edu.cn",
        homepage="https://csce.suat-sz.edu.cn/info/1008/1027.htm",
        research_directions=["并行计算机系统软件", "体系结构", "曙光计算机产业化最早主要领导者"],
        profile_summary=(
            "樊建平是深圳理工大学讲席教授，主要从事并行计算机系统软件和体系结构研究，"
            "曾获国家科技进步二等奖、中国青年科技奖，并享受国务院特殊津贴。"
        )
        * 3,
        evidence=module._build_evidence(
            ["https://csce.suat-sz.edu.cn/info/1008/1027.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
        quality_status="needs_enrichment",
    )
    record_b = ProfessorRecord(
        id="PROF-B",
        name="樊建平",
        institution="深圳理工大学",
        department="算力微电子学院",
        title="讲席教授",
        homepage="https://cme.suat-sz.edu.cn/info/1012/1222.htm",
        research_directions=["并行计算机系统软件", "体系结构", "低成本健康的倡导者与的引领者"],
        profile_summary=(
            "樊建平是深圳理工大学讲席教授，研究方向聚焦并行计算机系统软件和体系结构，"
            "荣获国家科技进步二等奖、中国青年科技奖，并享受国务院特殊津贴。"
        )
        * 3,
        evidence=module._build_evidence(
            ["https://cme.suat-sz.edu.cn/info/1012/1222.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
        quality_status="needs_enrichment",
    )

    deduped = module.dedupe_professor_records_for_search([record_a, record_b])

    assert len(deduped) == 1
    assert deduped[0].department == "计算机科学与人工智能学院"
    assert "低成本健康的倡导者与的引领者" in deduped[0].research_directions


def test_dedupe_professor_records_for_search_ignores_generic_public_email_conflict():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    record_a = ProfessorRecord(
        id="PROF-A",
        name="樊建平",
        institution="深圳理工大学",
        department="计算机科学与人工智能学院",
        title="讲席教授",
        email="fanjianping@suat-sz.edu.cn",
        homepage="https://csce.suat-sz.edu.cn/info/1008/1027.htm",
        research_directions=["并行计算机系统软件", "体系结构", "曙光计算机产业化最早主要领导者"],
        profile_summary=(
            "樊建平是深圳理工大学讲席教授，主要从事并行计算机系统软件和体系结构研究，"
            "曾获国家科技进步二等奖、中国青年科技奖，并享受国务院特殊津贴。"
        )
        * 3,
        evidence=module._build_evidence(
            ["https://csce.suat-sz.edu.cn/info/1008/1027.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
        quality_status="needs_enrichment",
    )
    record_b = ProfessorRecord(
        id="PROF-B",
        name="樊建平",
        institution="深圳理工大学",
        department="算力微电子学院",
        title="讲席教授",
        email="cm-public@suat-sz.edu.cncopyright",
        homepage="https://cme.suat-sz.edu.cn/info/1012/1222.htm",
        research_directions=["并行计算机系统软件", "体系结构", "低成本健康的倡导者与的引领者"],
        profile_summary=(
            "樊建平是深圳理工大学讲席教授，研究方向聚焦并行计算机系统软件和体系结构，"
            "荣获国家科技进步二等奖、中国青年科技奖，并享受国务院特殊津贴。"
        )
        * 3,
        evidence=module._build_evidence(
            ["https://cme.suat-sz.edu.cn/info/1012/1222.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
        quality_status="needs_enrichment",
    )

    deduped = module.dedupe_professor_records_for_search([record_a, record_b])

    assert len(deduped) == 1


def test_dedupe_professor_records_for_search_merges_same_name_when_strong_identity_anchor_matches():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    record_a = ProfessorRecord(
        id="PROF-A",
        name="刘清侠",
        institution="深圳技术大学",
        department="人工智能学院",
        title="讲席教授",
        homepage="https://ai.sztu.edu.cn/info/1332/6057.htm",
        research_directions=["环境保护", "清洁能源"],
        profile_summary=(
            "刘清侠，加拿大工程院院士，深圳技术大学讲席教授。"
            "曾在中国矿业大学和麦吉尔大学获得博士学位，研究聚焦环境保护与清洁能源。"
        )
        * 3,
        evidence=module._build_evidence(
            ["https://ai.sztu.edu.cn/info/1332/6057.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )
    record_b = ProfessorRecord(
        id="PROF-B",
        name="刘清侠",
        institution="深圳技术大学",
        department="新材料与新能源学院",
        title="讲席教授",
        homepage="https://nmne.sztu.edu.cn/info/1033/3214.htm",
        research_directions=["新能源材料", "先进储能技术"],
        profile_summary=(
            "刘清侠，加拿大工程院院士，现任深圳技术大学新材料与新能源学院讲席教授。"
            "曾任加拿大阿尔伯塔大学终身教授，研究方向包括新能源材料与先进储能技术。"
        )
        * 3,
        evidence=module._build_evidence(
            ["https://nmne.sztu.edu.cn/info/1033/3214.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )

    deduped = module.dedupe_professor_records_for_search([record_a, record_b])

    assert len(deduped) == 1
    assert deduped[0].department in {"人工智能学院", "新材料与新能源学院"}
    assert "新能源材料" in deduped[0].research_directions


def test_dedupe_professor_records_for_search_keeps_same_name_when_only_generic_title_matches():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    record_a = ProfessorRecord(
        id="PROF-A",
        name="张伟",
        institution="深圳大学",
        department="计算机学院",
        title="教授",
        homepage="https://cs.szu.edu.cn/info/1001/2001.htm",
        research_directions=["操作系统"],
        profile_summary="张伟是深圳大学计算机学院教授，主要研究操作系统与分布式系统。" * 4,
        evidence=module._build_evidence(
            ["https://cs.szu.edu.cn/info/1001/2001.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )
    record_b = ProfessorRecord(
        id="PROF-B",
        name="张伟",
        institution="深圳大学",
        department="材料学院",
        title="教授",
        homepage="https://mse.szu.edu.cn/info/1001/3001.htm",
        research_directions=["高分子材料"],
        profile_summary="张伟是深圳大学材料学院教授，主要研究高分子材料与复合材料设计。" * 4,
        evidence=module._build_evidence(
            ["https://mse.szu.edu.cn/info/1001/3001.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )

    deduped = module.dedupe_professor_records_for_search([record_a, record_b])

    assert len(deduped) == 2


def test_dedupe_professor_records_for_search_assigns_distinct_ids_to_distinct_same_name_clusters():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    record_a = ProfessorRecord(
        id="PROF-A",
        name="张伟",
        institution="深圳大学",
        department="计算机学院",
        title="讲席教授",
        homepage="https://cs.szu.edu.cn/info/1001/2001.htm",
        profile_summary="张伟现任深圳大学计算机学院讲席教授，主要从事操作系统研究。" * 4,
        evidence=module._build_evidence(
            ["https://cs.szu.edu.cn/info/1001/2001.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )
    record_b = ProfessorRecord(
        id="PROF-B",
        name="张伟",
        institution="深圳大学",
        department="计算机学院",
        title="讲席教授",
        homepage="https://cs.szu.edu.cn/info/1001/2001.htm",
        profile_summary="张伟现任深圳大学计算机学院讲席教授，主要从事操作系统研究。" * 4,
        evidence=module._build_evidence(
            ["https://cs.szu.edu.cn/info/1001/2001.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )
    record_c = ProfessorRecord(
        id="PROF-C",
        name="张伟",
        institution="深圳大学",
        department="材料学院",
        title="讲席教授",
        homepage="https://mse.szu.edu.cn/info/1001/3001.htm",
        profile_summary="张伟现任深圳大学材料学院讲席教授，主要从事高分子材料研究。" * 4,
        evidence=module._build_evidence(
            ["https://mse.szu.edu.cn/info/1001/3001.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )
    record_d = ProfessorRecord(
        id="PROF-D",
        name="张伟",
        institution="深圳大学",
        department="材料学院",
        title="讲席教授",
        homepage="https://mse.szu.edu.cn/info/1001/3001.htm",
        profile_summary="张伟现任深圳大学材料学院讲席教授，主要从事高分子材料研究。" * 4,
        evidence=module._build_evidence(
            ["https://mse.szu.edu.cn/info/1001/3001.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )

    deduped = module.dedupe_professor_records_for_search([record_a, record_b, record_c, record_d])

    assert len(deduped) == 2
    assert {item.department for item in deduped} == {"计算机学院", "材料学院"}
    assert len({item.id for item in deduped}) == 2


def test_dedupe_professor_records_for_search_merges_transitively_even_when_input_order_is_bad():
    module = _load_module_from_path(
        "run_professor_publish_to_search",
        Path(__file__).resolve().parents[2] / "scripts" / "run_professor_publish_to_search.py",
    )
    record_a = ProfessorRecord(
        id="PROF-A",
        name="刘清侠",
        institution="深圳技术大学",
        department="人工智能学院",
        title="讲席教授",
        homepage="https://ai.sztu.edu.cn/info/1332/6057.htm",
        profile_summary="刘清侠现任深圳技术大学讲席教授，长期从事环境保护研究。" * 4,
        evidence=module._build_evidence(
            ["https://ai.sztu.edu.cn/info/1332/6057.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )
    record_b = ProfessorRecord(
        id="PROF-B",
        name="刘清侠",
        institution="深圳技术大学",
        department="人工智能学院",
        title="讲席教授",
        homepage="https://ai.sztu.edu.cn/info/1332/6057.htm",
        profile_summary=(
            "刘清侠，加拿大工程院院士，现任深圳技术大学讲席教授，"
            "研究方向包括新能源材料与先进储能技术。"
        )
        * 3,
        evidence=module._build_evidence(
            ["https://ai.sztu.edu.cn/info/1332/6057.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )
    record_c = ProfessorRecord(
        id="PROF-C",
        name="刘清侠",
        institution="深圳技术大学",
        department="新材料与新能源学院",
        title="讲席教授",
        homepage="https://nmne.sztu.edu.cn/info/1033/3214.htm",
        profile_summary=(
            "刘清侠，加拿大工程院院士，现任深圳技术大学讲席教授，"
            "研究方向包括新能源材料与先进储能技术。"
        )
        * 3,
        evidence=module._build_evidence(
            ["https://nmne.sztu.edu.cn/info/1033/3214.htm"],
            TIMESTAMP,
        ),
        last_updated=TIMESTAMP,
    )

    deduped = module.dedupe_professor_records_for_search([record_a, record_c, record_b])

    assert len(deduped) == 1
