from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.deps import get_store
from backend.main import app
from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _evidence() -> Evidence:
    return Evidence(
        source_type="official_site",
        source_url="https://www.sustech.edu.cn",
        fetched_at=TIMESTAMP,
        snippet="Test evidence.",
    )


def _released_object(
    id: str,
    object_type: str = "professor",
    display_name: str = "Test",
    quality_status: str = "ready",
) -> ReleasedObject:
    return ReleasedObject(
        id=id,
        object_type=object_type,
        display_name=display_name,
        core_facts={"name": display_name},
        summary_fields={"profile_summary": "A test record."},
        evidence=[_evidence()],
        last_updated=TIMESTAMP,
        quality_status=quality_status,
    )


@pytest.fixture()
def store(tmp_path) -> SqliteReleasedObjectStore:
    return SqliteReleasedObjectStore(tmp_path / "test.db")


@pytest.fixture()
def populated_store(store: SqliteReleasedObjectStore) -> SqliteReleasedObjectStore:
    professors = [
        _released_object("PROF-1", "professor", "靳玉乐", "ready"),
        _released_object("PROF-2", "professor", "李明", "ready"),
        _released_object("PROF-3", "professor", "王芳", "needs_review"),
    ]
    companies = [
        _released_object("COMP-1", "company", "深圳科创有限公司", "ready"),
    ]
    store.upsert_released_objects(professors + companies)
    return store


@pytest.fixture()
def client(populated_store: SqliteReleasedObjectStore) -> TestClient:
    app.dependency_overrides[get_store] = lambda: populated_store
    yield TestClient(app)
    app.dependency_overrides.clear()
