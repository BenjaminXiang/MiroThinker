from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "rebuild_shared_store_from_batch_dbs.py"
    return _load_module("rebuild_shared_store_from_batch_dbs", script_path)


def _released_object(object_id: str, object_type: str, display_name: str, *, core_facts: dict | None = None, summary_fields: dict | None = None) -> ReleasedObject:
    return ReleasedObject(
        id=object_id,
        object_type=object_type,
        display_name=display_name,
        core_facts=core_facts or {"name": display_name},
        summary_fields=summary_fields or {"profile_summary": f"{display_name} summary"},
        evidence=[
            Evidence(
                source_type="official_site",
                source_url="https://example.com",
                fetched_at=datetime.now(timezone.utc),
            )
        ],
        last_updated=datetime.now(timezone.utc),
        quality_status="ready",
    )




def test_rebuild_shared_store_merges_multiple_batch_dbs(tmp_path: Path):
    module = _load_script()
    base_db = tmp_path / "base.db"
    batch_db_a = tmp_path / "batch_a.db"
    batch_db_b = tmp_path / "batch_b.db"
    target_db = tmp_path / "target.db"

    base_store = SqliteReleasedObjectStore(base_db)
    base_store.upsert_released_objects([
        _released_object("COMP-1", "company", "保留公司"),
    ])

    SqliteReleasedObjectStore(batch_db_a).upsert_released_objects([
        _released_object(
            "PROF-A",
            "professor",
            "教授A",
            core_facts={"name": "教授A", "company_roles": [], "top_papers": [], "patent_ids": []},
            summary_fields={"profile_summary": "教授A summary", "evaluation_summary": "评价"},
        ),
        _released_object(
            "PAPER-A",
            "paper",
            "论文A",
            core_facts={"title": "论文A", "authors": ["作者A"], "professor_ids": ["PROF-A"]},
            summary_fields={"summary_text": "摘要", "summary_zh": "摘要"},
        ),
    ])
    SqliteReleasedObjectStore(batch_db_b).upsert_released_objects([
        _released_object(
            "PROF-B",
            "professor",
            "教授B",
            core_facts={"name": "教授B", "company_roles": [], "top_papers": [], "patent_ids": []},
            summary_fields={"profile_summary": "教授B summary", "evaluation_summary": "评价"},
        ),
        _released_object(
            "PAPER-B",
            "paper",
            "论文B",
            core_facts={"title": "论文B", "authors": ["作者B"], "professor_ids": ["PROF-B"]},
            summary_fields={"summary_text": "摘要", "summary_zh": "摘要"},
        ),
        _released_object(
            "PPL-B",
            "professor_paper_link",
            "教授B -> 论文B",
            core_facts={"professor_id": "PROF-B", "paper_id": "PAPER-B", "link_status": "verified"},
            summary_fields={"profile_summary": "link"},
        ),
    ])

    counts = module.rebuild_shared_store_from_batch_dbs(
        target_path=target_db,
        base_db_path=base_db,
        batch_db_paths=[batch_db_a, batch_db_b],
        professor_company_backfill_paths=[],
        paper_exact_backfill_paths=[],
    )

    rebuilt = SqliteReleasedObjectStore(target_db)
    assert counts == rebuilt.count_by_domain()
    assert {obj.display_name for obj in rebuilt.list_domain_objects("company")} == {"保留公司"}
    assert {obj.display_name for obj in rebuilt.list_domain_objects("professor")} == {"教授A", "教授B"}
    assert {obj.display_name for obj in rebuilt.list_domain_objects("paper")} == {"论文A", "论文B"}
    assert {obj.display_name for obj in rebuilt.list_domain_objects("professor_paper_link")} == {"教授B -> 论文B"}

def test_rebuild_shared_store_replaces_professor_domains_and_preserves_other_domains(tmp_path: Path):
    module = _load_script()
    base_db = tmp_path / "base.db"
    batch_db = tmp_path / "batch.db"
    target_db = tmp_path / "target.db"

    base_store = SqliteReleasedObjectStore(base_db)
    base_store.upsert_released_objects([
        _released_object("COMP-1", "company", "旧公司"),
        _released_object(
            "PAT-1",
            "patent",
            "旧专利",
            core_facts={"title": "旧专利", "patent_number": "CN0001A"},
            summary_fields={"summary_text": "摘要", "summary_zh": "摘要"},
        ),
        _released_object("PROF-OLD", "professor", "旧教授"),
        _released_object(
            "PAPER-OLD",
            "paper",
            "旧论文",
            core_facts={"title": "旧论文", "authors": [], "professor_ids": []},
            summary_fields={"summary_text": "摘要", "summary_zh": "摘要"},
        ),
    ])

    batch_store = SqliteReleasedObjectStore(batch_db)
    batch_store.upsert_released_objects([
        _released_object(
            "PROF-NEW",
            "professor",
            "新教授",
            core_facts={"name": "新教授", "company_roles": [], "top_papers": [], "patent_ids": []},
            summary_fields={"profile_summary": "新教授 summary", "evaluation_summary": "评价"},
        ),
        _released_object(
            "PAPER-NEW",
            "paper",
            "新论文",
            core_facts={"title": "新论文", "authors": ["作者A"], "professor_ids": ["PROF-NEW"]},
            summary_fields={"summary_text": "摘要", "summary_zh": "摘要"},
        ),
        _released_object(
            "PPL-1",
            "professor_paper_link",
            "新教授 -> 新论文",
            core_facts={"professor_id": "PROF-NEW", "paper_id": "PAPER-NEW", "link_status": "verified"},
            summary_fields={"profile_summary": "link"},
        ),
    ])

    counts = module.rebuild_shared_store_from_batch_dbs(
        target_path=target_db,
        base_db_path=base_db,
        batch_db_paths=[batch_db],
        professor_company_backfill_paths=[],
        paper_exact_backfill_paths=[],
    )

    rebuilt = SqliteReleasedObjectStore(target_db)
    assert counts == rebuilt.count_by_domain()
    assert {obj.display_name for obj in rebuilt.list_domain_objects("company")} == {"旧公司"}
    assert {obj.display_name for obj in rebuilt.list_domain_objects("patent")} == {"旧专利"}
    assert {obj.display_name for obj in rebuilt.list_domain_objects("professor")} == {"新教授"}
    assert {obj.display_name for obj in rebuilt.list_domain_objects("paper")} == {"新论文"}
    assert {obj.display_name for obj in rebuilt.list_domain_objects("professor_paper_link")} == {"新教授 -> 新论文"}


def test_rebuild_shared_store_applies_professor_company_and_paper_backfills(tmp_path: Path):
    module = _load_script()
    base_db = tmp_path / "base.db"
    batch_db = tmp_path / "batch.db"
    target_db = tmp_path / "target.db"
    backfill_jsonl = tmp_path / "professor_company_roles.jsonl"
    paper_backfill_jsonl = tmp_path / "paper_exact_identifier_backfills.jsonl"

    base_store = SqliteReleasedObjectStore(base_db)
    base_store.upsert_released_objects([
        _released_object("COMP-1", "company", "深圳无界智航科技有限公司"),
    ])

    batch_store = SqliteReleasedObjectStore(batch_db)
    batch_store.upsert_released_objects([
        _released_object(
            "PROF-DWB",
            "professor",
            "丁文伯",
            core_facts={"name": "丁文伯", "company_roles": [], "top_papers": [], "patent_ids": []},
            summary_fields={"profile_summary": "丁文伯 summary", "evaluation_summary": "评价"},
        ),
    ])

    backfill_jsonl.write_text(
        json.dumps({
            "professor_name": "丁文伯",
            "company_name": "深圳无界智航科技有限公司",
            "role": "发起人",
            "source_url": "https://example.com/dwb-xspark",
            "snippet": "丁文伯｜清华大学 长聘副教授、Xspark AI发起人",
            "confidence": 0.72,
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paper_backfill_jsonl.write_text(
        json.dumps({
            "paper_id": "manual-pfedgpa-aaai-2025",
            "title": "pFedGPA: Diffusion-based Generative Parameter Aggregation for Personalized Federated Learning",
            "year": 2025,
            "publication_date": "2025-04-11",
            "venue": "AAAI",
            "doi": "10.1609/aaai.v39i17.33980",
            "arxiv_id": "2409.05701",
            "abstract": "abstract",
            "authors": ["Wenbo Ding"],
            "professor_ids": [],
            "citation_count": 0,
            "source_url": "https://doi.org/10.1609/aaai.v39i17.33980",
            "fields_of_study": ["Machine Learning"],
            "tldr": None,
            "license": None,
            "funders": [],
            "oa_status": None,
            "reference_count": 0,
            "enrichment_sources": ["crossref_manual_backfill"],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    module.rebuild_shared_store_from_batch_dbs(
        target_path=target_db,
        base_db_path=base_db,
        batch_db_paths=[batch_db],
        professor_company_backfill_paths=[backfill_jsonl],
        paper_exact_backfill_paths=[paper_backfill_jsonl],
    )

    rebuilt = SqliteReleasedObjectStore(target_db)
    professor = rebuilt.get_object("professor", "PROF-DWB")
    assert professor is not None
    assert professor.core_facts["company_roles"] == [
        {"company_name": "深圳无界智航科技有限公司", "role": "发起人"}
    ]
    company = rebuilt.get_object("company", "COMP-1")
    assert company is not None
    assert company.core_facts["professor_ids"] == ["PROF-DWB"]
    paper_titles = {obj.display_name for obj in rebuilt.list_domain_objects("paper")}
    assert any("pFedGPA" in title for title in paper_titles)


def test_rebuild_shared_store_keeps_target_unchanged_when_temp_write_fails(tmp_path: Path, monkeypatch):
    module = _load_script()
    base_db = tmp_path / "base.db"
    target_db = tmp_path / "target.db"
    batch_db = tmp_path / "batch.db"
    temp_path = target_db.with_suffix(target_db.suffix + ".tmp")

    base_store = SqliteReleasedObjectStore(base_db)
    base_store.upsert_released_objects([_released_object("COMP-1", "company", "旧公司")])

    target_store = SqliteReleasedObjectStore(target_db)
    target_store.upsert_released_objects([_released_object("COMP-TARGET", "company", "目标旧公司")])

    batch_store = SqliteReleasedObjectStore(batch_db)
    batch_store.upsert_released_objects([
        _released_object("PROF-NEW", "professor", "新教授", core_facts={"name": "新教授", "company_roles": [], "top_papers": [], "patent_ids": []}, summary_fields={"profile_summary": "新教授 summary", "evaluation_summary": "评价"}),
    ])

    original_upsert = module.SqliteReleasedObjectStore.upsert_released_objects

    def failing_upsert(self, objects):
        if self.db_path == temp_path and any(obj.object_type == "professor" for obj in objects):
            raise RuntimeError("boom")
        return original_upsert(self, objects)

    monkeypatch.setattr(module.SqliteReleasedObjectStore, "upsert_released_objects", failing_upsert)

    with pytest.raises(RuntimeError, match="boom"):
        module.rebuild_shared_store_from_batch_dbs(
            target_path=target_db,
            base_db_path=base_db,
            batch_db_paths=[batch_db],
            professor_company_backfill_paths=[],
            paper_exact_backfill_paths=[],
        )

    rebuilt = SqliteReleasedObjectStore(target_db)
    assert {obj.display_name for obj in rebuilt.list_domain_objects("company")} == {"目标旧公司"}
    assert rebuilt.list_domain_objects("professor") == []
    assert not temp_path.exists()
    assert not temp_path.with_name(temp_path.name + "-wal").exists()
    assert not temp_path.with_name(temp_path.name + "-shm").exists()
