# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.data_agents.contracts import PaperRecord, ProfessorRecord
from src.data_agents.evidence import build_evidence
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_url_md_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_professor_url_md_e2e.py"
    return _load_module("run_professor_url_md_e2e_gate", script_path)


def _base_profile(**overrides):
    profile = {
        "name": "张三",
        "institution": "南方科技大学",
        "department": "法学院",
        "profile_summary": (
            "张三现任南方科技大学法学院教授，研究方向包括国际法与比较法，"
            "曾获国家级教学成果一等奖并长期从事涉外法治研究。"
        ).ljust(250, "。"),
        "research_directions": ["国际法", "比较法"],
        "evidence_urls": ["https://law.sustech.edu.cn/faculty/zhangsan"],
        "top_papers": [],
        "paper_count": None,
        "projects": [],
        "awards": [],
        "profile_url": "https://law.sustech.edu.cn/faculty/zhangsan",
        "roster_source": "https://law.sustech.edu.cn/",
        "extraction_status": "structured",
    }
    profile.update(overrides)
    return profile


def test_evaluate_gate_accepts_hss_official_project_signal_without_papers(tmp_path: Path):
    module = _load_url_md_script()
    result = module._evaluate_gate(
        entry={
            "index": 1,
            "label": "南方科技大学 法学院",
            "url": "https://law.sustech.edu.cn/faculty/zhangsan",
            "institution": "南方科技大学",
        },
        rerun_id="001_南方科技大学_法学院",
        released=1,
        ready=1,
        profile=_base_profile(
            projects=["国家社科基金重大项目：涉外法治体系比较研究"],
        ),
        output_dir=tmp_path,
    )

    assert result.paper_backed_passed is True
    assert result.quality_status == "ready"
    assert result.gate_passed is True


def test_evaluate_gate_keeps_stem_profiles_strict_without_papers(tmp_path: Path):
    module = _load_url_md_script()
    result = module._evaluate_gate(
        entry={
            "index": 2,
            "label": "南方科技大学 计算机科学与工程系",
            "url": "https://cse.sustech.edu.cn/faculty/zhangsan",
            "institution": "南方科技大学",
        },
        rerun_id="002_南方科技大学_计算机科学与工程系",
        released=1,
        ready=0,
        profile=_base_profile(
            department="计算机科学与工程系",
            projects=["国家重点研发计划课题"],
            awards=["国家科技进步奖二等奖"],
            profile_url="https://cse.sustech.edu.cn/faculty/zhangsan",
            roster_source="https://cse.sustech.edu.cn/",
            evidence_urls=["https://cse.sustech.edu.cn/faculty/zhangsan"],
        ),
        output_dir=tmp_path,
    )

    assert result.paper_backed_passed is False
    assert result.quality_status == "needs_enrichment"
    assert result.gate_passed is False


def test_evaluate_gate_keeps_algorithm_department_strict_despite_fa_character(tmp_path: Path):
    module = _load_url_md_script()
    result = module._evaluate_gate(
        entry={
            "index": 3,
            "label": "南方科技大学 算法科学与工程系",
            "url": "https://cse.sustech.edu.cn/faculty/algorithms",
            "institution": "南方科技大学",
        },
        rerun_id="003_南方科技大学_算法科学与工程系",
        released=1,
        ready=0,
        profile=_base_profile(
            department="算法科学与工程系",
            awards=["国家级教学成果一等奖"],
            profile_url="https://cse.sustech.edu.cn/faculty/algorithms",
            roster_source="https://cse.sustech.edu.cn/",
            evidence_urls=["https://cse.sustech.edu.cn/faculty/algorithms"],
        ),
        output_dir=tmp_path,
    )

    assert result.paper_backed_passed is False
    assert result.quality_status == "needs_enrichment"
    assert result.gate_passed is False


def test_evaluate_gate_rejects_direct_profile_navigation_title_as_identity(tmp_path: Path):
    module = _load_url_md_script()
    result = module._evaluate_gate(
        entry={
            "index": 4,
            "label": "香港中文大学（深圳）",
            "url": "https://jianwei.cuhk.edu.cn/",
            "institution": "香港中文大学（深圳）",
        },
        rerun_id="004_香港中文大学_深圳",
        released=1,
        ready=1,
        profile=_base_profile(
            name="Teaching",
            institution="香港中文大学（深圳）",
            department="理工学院",
            profile_summary=(
                "黄建伟现任香港中文大学（深圳）理工学院教授，研究方向包括计算机系统与人工智能，"
                "主持多项科研项目并发表多篇代表性论文。"
            ).ljust(250, "。"),
            research_directions=["计算机系统", "人工智能"],
            evidence_urls=["https://jianwei.cuhk.edu.cn/"],
            top_papers=[{"title": "Systems Research Paper", "year": 2024}],
            paper_count=12,
            profile_url="https://jianwei.cuhk.edu.cn/teaching.html",
            roster_source="https://jianwei.cuhk.edu.cn/",
        ),
        output_dir=tmp_path,
    )

    assert result.identity_passed is False
    assert "identity_failed:香港中文大学（深圳）->香港中文大学（深圳）" in result.failure_reasons
    assert result.gate_passed is False


def test_evaluate_gate_rejects_faculty_section_heading_as_identity(tmp_path: Path):
    module = _load_url_md_script()
    result = module._evaluate_gate(
        entry={
            "index": 39,
            "label": "中山大学（深圳） 柔性电子学院",
            "url": "http://sofe.sysu.edu.cn/zh-hans/teachers/full-time",
            "institution": "中山大学（深圳）",
        },
        rerun_id="039_中山大学_深圳__柔性电子学院",
        released=1,
        ready=1,
        profile=_base_profile(
            name="专任教师",
            name_en="Tianshi Qin",
            institution="中山大学（深圳）",
            department="柔性电子学院",
            profile_summary=(
                "该教授任职于中山大学（深圳）柔性电子学院，研究方向涵盖钙钛矿光电器件、"
                "功能材料设计与器件制备，并发表多篇代表性论文。"
            ).ljust(250, "。"),
            research_directions=["钙钛矿光电器件", "功能材料设计"],
            evidence_urls=["http://sofe.sysu.edu.cn/zh-hans/teachers/full-time"],
            top_papers=[{"title": "Perovskite Paper", "year": 2024, "source": "openalex"}],
            paper_count=115,
            profile_url="http://sofe.sysu.edu.cn/zh-hans/teachers/full-time",
            roster_source="http://sofe.sysu.edu.cn/zh-hans/teachers/full-time",
        ),
        output_dir=tmp_path,
    )

    assert result.identity_passed is False
    assert result.quality_status == "low_confidence"
    assert "identity_failed:中山大学（深圳）->中山大学（深圳）" in result.failure_reasons
    assert result.gate_passed is False


def test_consolidate_batch_store_merges_per_url_released_object_dbs(tmp_path: Path):
    module = _load_url_md_script()
    batch_dir = tmp_path / "batch"
    run_a = batch_dir / "001_school_a"
    run_b = batch_dir / "002_school_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    prof = ProfessorRecord(
        id="PROF-1",
        name="吴亚北",
        institution="南方科技大学",
        department="物理系",
        title="教授",
        research_directions=["二维材料"],
        profile_summary="吴亚北现任南方科技大学教授，长期从事二维材料研究。" * 8,
        evidence=[build_evidence(source_type="official_site", source_url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html", fetched_at=datetime.now(timezone.utc), confidence=0.9)],
        last_updated=datetime.now(timezone.utc),
    ).to_released_object()
    paper = PaperRecord(
        id="PAPER-1",
        title="Twisted bilayer graphene and emergent phases",
        title_zh="Twisted bilayer graphene and emergent phases",
        authors=["吴亚北"],
        year=2024,
        doi="10.1000/example",
        summary_zh="摘要",
        summary_text="摘要",
        evidence=[build_evidence(source_type="academic_platform", source_url="https://openalex.org/W1", fetched_at=datetime.now(timezone.utc), confidence=0.8)],
        last_updated=datetime.now(timezone.utc),
    ).to_released_object()
    store_a = SqliteReleasedObjectStore(run_a / "released_objects.db")
    store_b = SqliteReleasedObjectStore(run_b / "released_objects.db")
    store_a.upsert_released_objects([prof])
    store_b.upsert_released_objects([paper])

    target_path = batch_dir / "released_objects.db"
    counts = module._consolidate_batch_store(batch_dir, target_path)

    consolidated = SqliteReleasedObjectStore(target_path)
    assert counts == {"paper": 1, "professor": 1}
    assert consolidated.count_by_domain() == {"paper": 1, "professor": 1}


def test_parse_seed_lines_supports_markdown_direct_profile_links(tmp_path: Path):
    module = _load_url_md_script()
    seed_doc = tmp_path / "seeds.md"
    seed_doc.write_text("[丁文伯](http://www.sigs.tsinghua.edu.cn/dwb/main.htm)\n[王学谦](http://www.sigs.tsinghua.edu.cn/wxq/main.htm)\n", encoding="utf-8")

    entries = module._parse_seed_lines(seed_doc)

    assert [(entry["label"], entry["url"], entry["institution"]) for entry in entries] == [
        ("丁文伯", "http://www.sigs.tsinghua.edu.cn/dwb/main.htm", "清华大学深圳国际研究生院"),
        ("王学谦", "http://www.sigs.tsinghua.edu.cn/wxq/main.htm", "清华大学深圳国际研究生院"),
    ]
