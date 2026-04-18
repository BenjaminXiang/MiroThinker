from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

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
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "consolidate_to_shared_store.py"
    return _load_module("consolidate_to_shared_store", script_path)


def _released_object(object_id: str, object_type: str, display_name: str) -> ReleasedObject:
    return ReleasedObject(
        id=object_id,
        object_type=object_type,
        display_name=display_name,
        core_facts={"name": display_name},
        summary_fields={"profile_summary": f"{display_name} summary"},
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


def test_consolidate_from_logs_keeps_target_unchanged_when_source_load_fails(tmp_path: Path):
    module = _load_script()
    logs_dir = tmp_path / "logs"
    target_path = logs_dir / "data_agents" / "released_objects.db"
    target_store = SqliteReleasedObjectStore(target_path)
    target_store.upsert_released_objects([_released_object("COMP-OLD", "company", "旧公司")])

    prof_db = logs_dir / "data_agents" / "professor" / "search_service" / "released_objects.sqlite3"
    prof_store = SqliteReleasedObjectStore(prof_db)
    prof_store.upsert_released_objects([_released_object("PROF-1", "professor", "丁文伯")])

    bad_company_jsonl = logs_dir / "debug" / "company_release_e2e_bad" / "released_objects.jsonl"
    bad_company_jsonl.parent.mkdir(parents=True, exist_ok=True)
    bad_company_jsonl.write_text('{bad json}\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        module.consolidate_from_logs(logs_dir, target_path)

    names = [obj.display_name for obj in target_store.list_domain_objects("company")]
    assert names == ["旧公司"]
    assert target_store.list_domain_objects("professor") == []


def test_consolidate_from_logs_leaves_readable_target_without_temp_wal(tmp_path: Path):
    module = _load_script()
    logs_dir = tmp_path / "logs"
    target_path = logs_dir / "data_agents" / "released_objects.db"

    existing_target = SqliteReleasedObjectStore(target_path)
    existing_target.upsert_released_objects(
        [_released_object("COMP-OLD", "company", "旧公司")]
    )

    prof_db = logs_dir / "data_agents" / "professor" / "search_service" / "released_objects.sqlite3"
    prof_store = SqliteReleasedObjectStore(prof_db)
    prof_store.upsert_released_objects(
        [_released_object("PROF-1", "professor", "丁文伯")]
    )

    company_jsonl = logs_dir / "debug" / "company_release_e2e_ok" / "released_objects.jsonl"
    company_jsonl.parent.mkdir(parents=True, exist_ok=True)
    company_jsonl.write_text(
        _released_object("COMP-1", "company", "新公司").model_dump_json() + "\n",
        encoding="utf-8",
    )

    counts, _ = module.consolidate_from_logs(logs_dir, target_path)

    assert counts["company"] == 1
    assert counts["professor"] == 1
    assert not target_path.with_suffix(target_path.suffix + ".tmp-wal").exists()
    reopened = SqliteReleasedObjectStore(target_path)
    assert reopened.count_by_domain() == {"company": 1, "professor": 1}



def test_consolidate_from_logs_cleans_temp_files_when_write_fails(tmp_path: Path, monkeypatch):
    module = _load_script()
    logs_dir = tmp_path / "logs"
    target_path = logs_dir / "data_agents" / "released_objects.db"
    temp_path = target_path.with_suffix(target_path.suffix + ".tmp")

    target_store = SqliteReleasedObjectStore(target_path)
    target_store.upsert_released_objects([_released_object("COMP-OLD", "company", "旧公司")])

    prof_db = logs_dir / "data_agents" / "professor" / "search_service" / "released_objects.sqlite3"
    prof_store = SqliteReleasedObjectStore(prof_db)
    prof_store.upsert_released_objects([_released_object("PROF-1", "professor", "丁文伯")])

    company_jsonl = logs_dir / "debug" / "company_release_e2e_ok" / "released_objects.jsonl"
    company_jsonl.parent.mkdir(parents=True, exist_ok=True)
    company_jsonl.write_text(
        _released_object("COMP-1", "company", "新公司").model_dump_json() + "\n",
        encoding="utf-8",
    )

    original_upsert = module.SqliteReleasedObjectStore.upsert_released_objects

    def failing_upsert(self, objects):
        if self.db_path == temp_path:
            raise RuntimeError("boom")
        return original_upsert(self, objects)

    monkeypatch.setattr(module.SqliteReleasedObjectStore, "upsert_released_objects", failing_upsert)

    with pytest.raises(RuntimeError, match="boom"):
        module.consolidate_from_logs(logs_dir, target_path)

    assert target_store.count_by_domain() == {"company": 1}
    assert not temp_path.exists()
    assert not temp_path.with_name(temp_path.name + "-wal").exists()
    assert not temp_path.with_name(temp_path.name + "-shm").exists()
